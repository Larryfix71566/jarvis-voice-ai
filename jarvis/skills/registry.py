"""SkillRegistry: MCP client manager (plan Phase 2, step 2.1).

Loads config/mcp_servers.yaml, spawns each server over stdio with the
official mcp client, keeps one persistent ClientSession per server, and
exposes discovered tools as OpenAI-format function schemas.

Locked behavior:
- ${VAR} placeholders in server env entries expand from the process
  environment (plan §6.3) — via jarvis.config.expand_env_vars.
- Tool-name collision across servers -> ValueError at start() naming both.
- call() never raises: failures return "<tool> failed: <reason>" strings.
  Per-call timeout: 30 s.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

import yaml
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from jarvis.config import expand_env_vars
from jarvis.runlog.context import get_run_id, get_run_logger
from jarvis.toolresult import classify_tool_result

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
CALL_TIMEOUT = 30.0

# Server entry "command: python" means "the interpreter running this
# process" — guarantees the child uses the same environment.
_PYTHON_COMMANDS = {"python", "python3"}


class SkillRegistry:
    def __init__(self, config_path: Path):
        self._config_path = Path(config_path)
        self._server_configs: list[dict[str, Any]] = []
        self._stack: AsyncExitStack | None = None
        self._sessions: dict[str, ClientSession] = {}
        self._tools: dict[str, tuple[str, Any]] = {}  # tool -> (server, Tool)

    @property
    def server_names(self) -> list[str]:
        return [entry["name"] for entry in self._server_configs]

    async def start(self) -> None:
        """Spawn all servers, initialize sessions, discover tools."""
        if self._stack is not None:
            return  # idempotent
        config = yaml.safe_load(self._config_path.read_text())
        self._server_configs = list(config["servers"])
        self._stack = AsyncExitStack()
        try:
            for entry in self._server_configs:
                await self._start_server(entry)
        except Exception:
            await self.stop()
            raise

    async def stop(self) -> None:
        """Terminate all child processes. Idempotent; never raises."""
        stack, self._stack = self._stack, None
        self._sessions = {}
        self._tools = {}
        if stack is not None:
            try:
                await stack.aclose()
            except Exception as exc:  # shutdown noise must not propagate
                logger.warning("registry_stop_error: %s", exc)

    def openai_tools(self, server_names: list[str] | None = None) -> list[dict]:
        """Discovered tools as OpenAI function schemas, optionally filtered."""
        allowed = set(server_names) if server_names is not None else None
        schemas = []
        for tool_name, (server, tool) in self._tools.items():
            if allowed is not None and server not in allowed:
                continue
            schemas.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": tool.inputSchema
                    or {"type": "object", "properties": {}},
                },
            })
        return schemas

    def tools_for(self, server_names: list[str]) -> list[str]:
        """Tool names owned by the given servers."""
        allowed = set(server_names)
        return [name for name, (server, _) in self._tools.items() if server in allowed]

    async def call(
        self,
        tool_name: str,
        arguments: dict,
        server_names: list[str] | None = None,
    ) -> str:
        """Invoke a tool. Returns plain text (JSON for dict results) or a
        one-line failure string. Never raises."""
        entry = self._tools.get(tool_name)
        if entry is None:
            available = ", ".join(sorted(self._tools)) or "none"
            return f"Unknown tool '{tool_name}'. Available: {available}."
        server, _tool = entry
        if server_names is not None and server not in set(server_names):
            return f"Tool '{tool_name}' is not available in this context."
        session = self._sessions[server]
        # Run-logging plan D3/D18/§5.6: record one mcp_call event with the
        # *exact* ok signal for this call (unlike SubAgent's tool_result,
        # which can only infer ok from this function's return string).
        # Skipped entirely when there is no active run (e.g. a direct
        # Supervisor tool call) — this is the normal case, not a warning.
        runlog = get_run_logger()
        call_start = time.perf_counter()
        try:
            result = await asyncio.wait_for(
                session.call_tool(tool_name, arguments), timeout=CALL_TIMEOUT
            )
        except asyncio.TimeoutError:
            latency_ms = int((time.perf_counter() - call_start) * 1000)
            error = f"timed out after {int(CALL_TIMEOUT)}s"
            if runlog is not None:
                runlog.mcp_call(tool_name, server, ok=False,
                                 latency_ms=latency_ms, error=error)
            return f"{tool_name} failed: {error}."
        except Exception as exc:
            latency_ms = int((time.perf_counter() - call_start) * 1000)
            error = type(exc).__name__
            logger.warning("tool_call_failed tool=%s error=%s run_id=%s",
                            tool_name, exc, get_run_id())
            if runlog is not None:
                runlog.mcp_call(tool_name, server, ok=False,
                                 latency_ms=latency_ms, error=error)
            return f"{tool_name} failed: {error}."

        latency_ms = int((time.perf_counter() - call_start) * 1000)
        if getattr(result, "isError", False):
            text = " ".join(
                getattr(c, "text", "") for c in result.content
            ).strip()
            error = text or "unknown error"
            if runlog is not None:
                runlog.mcp_call(tool_name, server, ok=False,
                                 latency_ms=latency_ms, error=error)
            return f"{tool_name} failed: {error}"

        structured = getattr(result, "structuredContent", None)
        if structured is not None:
            text_result = json.dumps(structured, default=str)
        else:
            text_result = "\n".join(
                getattr(c, "text", "") for c in result.content
            ).strip()

        # D1/D2 (MORTIMER_AGENT_TRUST_PLAN.md): the MCP transport succeeded
        # (no isError above), but the tool's own JSON body may still say it
        # failed — e.g. mcp_apps returning {"ok": false, "error": "...401..."}
        # as a perfectly normal MCP response. classify_tool_result is the
        # single place that judgement is made; this call must never be
        # replaced with a bare ok=True.
        outcome = classify_tool_result(tool_name, text_result)
        if runlog is not None:
            runlog.mcp_call(
                tool_name, server, ok=outcome.ok, latency_ms=latency_ms,
                error=outcome.error,
            )
        return text_result

    async def _start_server(self, entry: dict[str, Any]) -> None:
        name = entry["name"]
        env = dict(os.environ)
        for key, value in (entry.get("env") or {}).items():
            env[key] = expand_env_vars(str(value))
        env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")

        command = entry["command"]
        if command in _PYTHON_COMMANDS:
            command = sys.executable
        kwargs = {"command": command, "args": list(entry["args"]), "env": env}
        try:
            params = StdioServerParameters(cwd=str(REPO_ROOT), **kwargs)
        except TypeError:  # older SDKs lack cwd; repo root is inherited cwd
            params = StdioServerParameters(**kwargs)

        assert self._stack is not None
        read, write = await self._stack.enter_async_context(stdio_client(params))
        session = await self._stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        discovered = (await session.list_tools()).tools
        self._sessions[name] = session
        for tool in discovered:
            if tool.name in self._tools:
                other = self._tools[tool.name][0]
                raise ValueError(
                    f"Tool name collision: '{tool.name}' is provided by both "
                    f"'{other}' and '{name}'."
                )
            self._tools[tool.name] = (name, tool)
        logger.info("mcp_server_started name=%s tools=%d", name, len(discovered))
