"""Installed advisory MCP framing over synthetic authenticated loopback HTTP."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi import HTTPException

from jarvis.admin import server as admin
from jarvis.bot.sensitive_turn import SensitiveTurn, current_sensitive_turn
from jarvis.model_budget import begin_model_task_budget
from jarvis.model_routing import WorkloadLimits
from jarvis.privacy_policy import DataPolicy, make_tool_execution_scope, validate_tool_result
from jarvis.runlog.context import run_logger_scope
from jarvis.skills.registry import SkillRegistry
from jarvis.tenant import user_id_scope
from tests.unit.test_advisory_source_bridge import advisory, immediate_workers
from tests.unit.test_council_budget_ownership import transport_env


@pytest.fixture
def advisory_http(advisory, monkeypatch):
    paths = []
    endpoints = {'associate': admin.associate_advisory_source, 'prepare': admin.prepare_advisory_source,
                 'tool': admin.execute_advisory_source, 'cancel': admin.cancel_advisory_source}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            assert self.headers['Authorization'] == 'Bearer synthetic-advisory-fixture'
            assert self.path.startswith('/api/advisory/source/')
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            paths.append(self.path)
            try:
                with user_id_scope('alice'):
                    result = endpoints[self.path.rsplit('/', 1)[-1]](admin.AdvisorySourceIn(**body), advisory.request)
                status = 200
            except HTTPException:
                result, status = {'ok': False, 'error': 'advisory_source_unavailable'}, 409
            encoded = json.dumps(result).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv('JARVIS_ADMIN_URL', f'http://127.0.0.1:{server.server_port}')
    monkeypatch.setenv('JARVIS_SERVICE_TOKEN', 'synthetic-advisory-fixture')
    yield paths
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


@pytest.mark.parametrize('server_name,role,tool,arguments', [
    ('mcp-selfedit', 'developer', 'plan_start', {'goal': 'public planner preview'}),
    ('mcp-web', 'analyst', 'research_compare_start', {'urls': ['https://a.invalid', 'https://b.invalid']}),
])
async def test_actual_advisory_stdio_hides_metadata_and_preserves_preview(advisory, advisory_http, tmp_path,
                                                                      server_name, role, tool, arguments):
    config = tmp_path / 'servers.yaml'
    config.write_text(f'servers:\n  - name: {server_name}\n    command: python\n'
                      f'    args: ["-m", "mcp_servers.{server_name.replace("-", "_")}.server"]\n    env: {{}}\n')
    registry = SkillRegistry(config)
    await registry.start()
    token = current_sensitive_turn.set(SensitiveTurn())
    try:
        contract = registry._source_contracts[server_name]
        assert contract.local_admin and contract.session is registry._sessions[server_name]
        schema = next(item for item in registry.openai_tools() if item['function']['name'] == tool)
        properties = schema['function']['parameters'].get('properties', {})
        assert 'ctx' not in properties and 'run_id' not in properties
        assert 'source_receipt' not in json.dumps(schema) and 'scope_id' not in json.dumps(schema)
        caller = advisory.caller(role)
        scope = make_tool_execution_scope(caller.run_id, 'stdio-task', 'stdio-call', tool, arguments,
                                         DataPolicy('approved_external', 'public-synthetic-input'))
        entered = time.time()
        with user_id_scope('alice'):
            budget = begin_model_task_budget(role, caller.run_id, WorkloadLimits(), started_at=entered)
            with run_logger_scope(caller):
                envelope = await registry.call_classified(tool, arguments, execution_scope=scope,
                    task_budget=budget, task_started_at=entered)
        policy, content = validate_tool_result(scope, envelope)
        result = json.loads(content)
        assert policy.level == 'approved_external' and result.get('needs_confirmation') is True, (result, advisory_http)
        assert advisory_http == ['/api/advisory/source/associate', '/api/advisory/source/prepare',
                                 '/api/advisory/source/tool']
        assert 'source_receipt' not in content and 'scope_id' not in content and 'signature' not in content
        assert not advisory.state.clients and not advisory.state.sent
    finally:
        current_sensitive_turn.reset(token)
        await registry.stop()
