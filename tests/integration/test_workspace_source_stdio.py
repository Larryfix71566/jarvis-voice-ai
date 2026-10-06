"""Actual pinned MCP processes; local synthetic admin RPC, no VM/provider."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading

import pytest
from fastapi import HTTPException

from jarvis.privacy_policy import DataPolicy, make_tool_execution_scope, validate_tool_result
from jarvis.runlog.context import run_logger_scope
from jarvis.runlog.store import RunLogger
from jarvis.skills.registry import SkillRegistry
from jarvis.tenant import user_id_scope
from tests.unit.test_development_sources import workspace
from tests.unit.test_workspace_source_bridge import bridge


@pytest.fixture
def admin_transport(bridge, monkeypatch):
    admin = bridge.admin
    paths = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_POST(self):
            assert self.headers['Authorization'] == 'Bearer synthetic-source-fixture'
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            paths.append(self.path)
            try:
                if self.path.endswith('/associate'):
                    result = admin.associate_workspace_source(admin.WorkspaceSourceAssociationIn(**body), bridge.request)
                elif self.path.endswith('/prepare'):
                    result = admin.prepare_workspace_source(admin.WorkspaceSourcePrepareIn(**body), bridge.request)
                else:
                    assert self.path.endswith('/tool')
                    result = admin.execute_workspace_source(admin.WorkspaceSourceToolIn(**body), bridge.request)
                status = 200
            except HTTPException:
                result, status = {'ok': False, 'error': 'workspace_source_unavailable'}, 409
            encoded = json.dumps(result).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv('JARVIS_ADMIN_URL', 'http://127.0.0.1:' + str(server.server_port))
    monkeypatch.setenv('JARVIS_SERVICE_TOKEN', 'synthetic-source-fixture')
    yield paths
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


@pytest.mark.parametrize('server_name,tool,args', [
    ('mcp-selfedit', 'selfedit_read', {'path': 'jarvis/app.py'}),
    ('mcp-apps', 'app_build_start', {'app': 'public-fixture', 'goal': 'caller public preview'}),
])
async def test_actual_stdio_roundtrip_and_schemas_hide_workspace_metadata(bridge, admin_transport,
                                                                        tmp_path, server_name, tool, args):
    config = tmp_path / 'servers.yaml'
    config.write_text('servers:\n  - name: ' + server_name + '\n    command: python\n    args: ["-m", "mcp_servers.'
                      + server_name.replace('-', '_') + '.server"]\n    env: {}\n')
    registry = SkillRegistry(config)
    await registry.start()
    try:
        contract = registry._source_contracts[server_name]
        assert contract.session is registry._sessions[server_name] and contract.local_admin
        schema = next(item for item in registry.openai_tools() if item['function']['name'] == tool)
        assert 'ctx' not in schema['function']['parameters'].get('properties', {})
        assert 'source' not in json.dumps(schema)
        runlog = bridge.logger
        if server_name == 'mcp-apps':
            import uuid
            with user_id_scope(bridge.owner):
                runlog = RunLogger(str(uuid.uuid4()), 'app_builder', 'App Builder', 'public app preview',
                                  session_id=bridge.session_id, root=tmp_path)
                runlog.start()
        scope = make_tool_execution_scope(runlog.run_id, 'stdio-task', 'stdio-call', tool, args,
                                         DataPolicy('approved_external', 'caller-public'))
        with run_logger_scope(runlog):
            envelope = await registry.call_classified(tool, args, execution_scope=scope)
        policy, content = validate_tool_result(scope, envelope)
        result = json.loads(content)
        assert policy.level == 'approved_external' and result['ok'], result
        assert admin_transport == ['/api/development/source/associate', '/api/development/source/prepare',
                                   '/api/development/source/tool']
        assert 'source_receipt' not in content and 'signature' not in content and '_seal_key' not in content
        if tool == 'selfedit_read':
            assert result['content'] == 'print("public code")\n' and len(bridge.w.calls) == 1
        else:
            assert result['needs_confirmation'] and 'caller public preview' in result['summary']
            assert not bridge.w.calls
    finally:
        await registry.stop()
