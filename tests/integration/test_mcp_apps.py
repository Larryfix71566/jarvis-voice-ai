"""Integration test: spawn the mcp-apps server over stdio, assert the exact
tool set, and verify degraded mode without GITHUB_TOKEN (no network calls).
A live end-to-end creation test requires a real token and creates a real
repo, so it stays manual (see tests/acceptance)."""

import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

EXPECTED_TOOLS = {
    "app_create", "app_write_file", "app_register", "app_list", "app_read",
    # D6 (MORTIMER_MODEL_DISCIPLINE_AND_MAC_SHELL_PLAN.md): thin HTTP
    # clients of the admin sidecar, not GitHub — GITHUB_TOKEN degraded
    # mode above doesn't apply to these three.
    "app_build_start", "app_build_status", "app_build_submit",
}


def _params(extra_env: dict) -> StdioServerParameters:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env.update(extra_env)
    kwargs = {
        "command": sys.executable,
        "args": ["-m", "mcp_servers.mcp_apps.server"],
        "env": env,
    }
    try:
        return StdioServerParameters(cwd=str(REPO_ROOT), **kwargs)
    except TypeError:  # older SDK without cwd support
        return StdioServerParameters(**kwargs)


async def test_mcp_apps_tool_set_and_degraded_mode():
    async with stdio_client(_params({"GITHUB_TOKEN": ""})) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = {t.name for t in (await session.list_tools()).tools}
            assert tools == EXPECTED_TOOLS
            result = await session.call_tool("app_list", {})
            payload = json.loads(result.content[0].text)
            assert payload["ok"] is False
            assert "GITHUB_TOKEN" in payload["error"]
            result = await session.call_tool("app_write_file", {
                "app": "test-app", "path": "src/app.js", "content": "unverified",
            })
            payload = json.loads(result.content[0].text)
            assert payload["ok"] is False
            assert payload["code"] == "sandbox_required"
            assert "app_build_start" in payload["replacement_tools"]
