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
- Supervision (status spec T3.1, L11): one owner task per server holds its
  contexts; a server that fails to start is marked down without stopping
  the others; a dead child is restarted (backoff: 3 per 60 s) and the
  failing call retried once; a down server's tools answer "unavailable".
"""

from __future__ import annotations

import asyncio
import contextvars
import copy
import json
import logging
import os
import sys
import time
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

import anyio
import yaml
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.shared.exceptions import McpError
from mcp.types import Tool

from jarvis.config import bridge_settings_to_env, expand_env_vars
from jarvis.bot.sensitive_turn import current_sensitive_turn
from jarvis.runlog.context import get_run_id, get_run_logger
from jarvis.toolresult import classify_tool_result

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
CALL_TIMEOUT = 30.0

# These MCP servers can transmit task/argument content beyond the Mac. A
# sensitive turn must fail closed before the child is invoked; local-only
# servers (notes, memory, repo, git, time, etc.) remain available.
EXTERNAL_TOOL_SERVERS = frozenset({
    "mcp-web", "mcp-apps", "mcp-screen", "mcp-selfedit",
    # Status spec I3/T2.6: its P4 tools (catalogs, subscription probes,
    # GitHub reads) leave the machine.
    "mcp-status",
})

# Server entry "command: python" means "the interpreter running this
# process" — guarantees the child uses the same environment.
_PYTHON_COMMANDS = {"python", "python3"}

# ⚙ TUNING KNOB (plan §6, D-H1) — the ONLY variables every MCP child
# receives regardless of what it declares. This tuple is contract K2 and is
# copied verbatim from MORTIMER_PLATFORM_ROADMAP.md's cross-plan contracts;
# do not reorder or extend it without amending K2, because six plans agree
# on it. Names are copied only when PRESENT in os.environ.
BASE_ENV_KEYS = (
    "PATH", "HOME", "PYTHONPATH", "VIRTUAL_ENV", "LANG", "LC_ALL",
    "TMPDIR", "TZ", "JARVIS_DB_PATH", "JARVIS_TIMEZONE",
    "JARVIS_ADMIN_URL", "JARVIS_LOG_LEVEL",
)

# Kill switch (plan §6, D-H10). Read HERE and nowhere else in the codebase.
ENV_SCOPING_ENABLED_ENV = "JARVIS_ENV_SCOPING_ENABLED"

#: MORTIMER_GRAPH_LAYER_PLAN.md GL9 (contract G2). call() overwrites `run_id` in
#: these tools' arguments with the delegating run's id (or "" outside a run) and
#: openai_tools() strips the parameter from their schemas so the model never sees
#: it. The ContextVar cannot cross the MCP child-process boundary; this is the one
#: point that both knows the run and touches every tool call.
RUN_ID_INJECTED_TOOLS: frozenset[str] = frozenset({"selfedit_start", "plan_start"})

#: skill.yaml requires_env_dynamic sources. Closed set — an unrecognised
#: source is a hard error, because a typo that silently grants nothing is
#: exactly the failure this track exists to prevent.
_DYNAMIC_SOURCES = ("upgrade_models_api_keys", "vault_names")

#: (server, var) pairs already warned about, so a permanently-unset
#: optional variable warns once per process rather than once per spawn.
_WARNED_MISSING: set[tuple[str, str]] = set()


def env_scoping_enabled() -> bool:
    """True unless JARVIS_ENV_SCOPING_ENABLED is an explicit false value."""
    return os.environ.get(ENV_SCOPING_ENABLED_ENV, "").strip().lower() not in (
        "0", "false", "no", "off",
    )


def _skill_yaml_path(server_name: str) -> Path:
    """config server name 'mcp-web' -> mcp_servers/mcp_web/skill.yaml."""
    return REPO_ROOT / "mcp_servers" / server_name.replace("-", "_") / "skill.yaml"


def load_requires_env(server_name: str) -> tuple[list[str], list[str], list[dict]]:
    """Return (requires_env, optional_env, requires_env_dynamic) for one server.

    A missing skill.yaml, an unreadable one, or a missing key yields
    ([], [], []) plus a WARNING — a server with no declaration gets
    BASE_ENV_KEYS only, which is the safe direction. Never raises.
    """
    path = _skill_yaml_path(server_name)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except FileNotFoundError:
        logger.warning("skill_yaml_missing server=%s path=%s "
                       "(child gets BASE_ENV_KEYS only)", server_name, path)
        return [], [], []
    except Exception as exc:  # noqa: BLE001
        logger.warning("skill_yaml_unreadable server=%s error=%s "
                       "(child gets BASE_ENV_KEYS only)", server_name, exc)
        return [], [], []
    required = [str(n) for n in (data.get("requires_env") or [])]
    optional = [str(n) for n in (data.get("optional_env") or [])]
    dynamic = list(data.get("requires_env_dynamic") or [])
    return required, optional, dynamic


def _resolve_dynamic_env(server_name: str, dynamic: list[dict]) -> list[str]:
    """Expand requires_env_dynamic entries into concrete variable names.

    Raises ValueError on an unrecognised source (D-H2). The raise is CAUGHT by
    build_child_env (review F16) so a typo cannot brick the voice loop; the
    same validation runs at check-time in scripts/check_skills.py (Step 1d),
    which is where a manifest error belongs.
    """
    names: set[str] = set()
    for entry in dynamic:
        source = (entry or {}).get("source")
        if source not in _DYNAMIC_SOURCES:
            raise ValueError(
                f"{_skill_yaml_path(server_name)}: requires_env_dynamic "
                f"source {source!r} is not one of {_DYNAMIC_SOURCES}"
            )
        if source == "vault_names":
            raise ValueError(
                "requires_env_dynamic source 'vault_names' is not available "
                "before T4b (MORTIMER_SECURITY_HARDENING_PLAN.md D-H2)"
            )
        # upgrade_models_api_keys (the source keeps its historical name; it
        # means "every api_key_env in the model registry"). Read through the
        # ONE loader so the key names come from the JOINED view — after the
        # registry split they live in config/model_endpoints.yaml, not in the
        # profile file (docs/plans/MORTIMER_MODEL_REGISTRY_SPLIT_PLAN.md D2).
        names.add("OPENAI_API_KEY")  # mcp_screen/logic.py:282 default
        try:
            from jarvis.agents.upgrade_agent import load_model_registry
            registry = load_model_registry()
        except Exception as exc:  # noqa: BLE001 — degrade to the default only
            logger.warning("upgrade_models_unreadable server=%s error=%s",
                           server_name, exc)
            continue
        for value in _walk_api_key_envs(registry):
            names.add(value)
    return sorted(names)


def _walk_api_key_envs(node: Any) -> Iterator[str]:
    """Yield every `api_key_env` value anywhere in a parsed YAML tree.

    Walks rather than assuming a shape, because the model registry groups
    profiles under keys this module has no business knowing about.
    """
    if isinstance(node, dict):
        value = node.get("api_key_env")
        if isinstance(value, str) and value:
            yield value
        for child in node.values():
            yield from _walk_api_key_envs(child)
    elif isinstance(node, list):
        for child in node:
            yield from _walk_api_key_envs(child)


def build_child_env(entry: dict[str, Any]) -> dict[str, str]:
    """Build the environment for one MCP child (K2, plan D-H1).

    BASE_ENV_KEYS (when present) + the server's requires_env (+ dynamic)
    + the server's explicit `env:` map, expanded. Nothing else.

    JARVIS_ENV_SCOPING_ENABLED=false restores full inheritance, and says so
    once at WARNING level so a machine running unscoped is never quiet
    about it.
    """
    name = entry["name"]
    if not env_scoping_enabled():
        logger.warning("mcp_env_scoping_disabled server=%s "
                       "(JARVIS_ENV_SCOPING_ENABLED=false — child inherits "
                       "the FULL parent environment)", name)
        return dict(os.environ)

    env: dict[str, str] = {}
    for key in BASE_ENV_KEYS:
        value = os.environ.get(key)
        if value is not None:
            env[key] = value

    required, optional, dynamic = load_requires_env(name)
    for key in required:
        if key in BASE_ENV_KEYS:
            continue
        value = os.environ.get(key)
        if value is None:
            # K2: spawn proceeds; a WARNING names the server and the
            # variable. Same posture as the existing
            # mcp_server_env_unresolved warning below — a degraded server
            # beats a dead voice loop. Deduplicated per process so a
            # permanently-unset var does not reprint on every restart.
            if (name, key) not in _WARNED_MISSING:
                _WARNED_MISSING.add((name, key))
                logger.warning(
                    "mcp_server_env_missing server=%s var=%s "
                    "(declared in skill.yaml requires_env but not set in "
                    "this process — the child will not receive it)",
                    name, key)
            continue
        env[key] = value

    # optional_env (plan Step 1, review F7/F21): forwarded when present,
    # SILENT when absent — these names have a code default in the server, so
    # a permanently-unset one is normal and must not warn.
    for key in optional:
        if key in BASE_ENV_KEYS or key in env:
            continue
        value = os.environ.get(key)
        if value is not None:
            env[key] = value

    # Dynamic names are "whichever of these exists", not "all of these" —
    # mcp-screen needs ONE vision key and the source yields four. Absence
    # is therefore normal and silent here; mcp_screen/logic.py already
    # produces a precise user-facing error naming the key it wanted.
    #
    # review F16: an unrecognised source raises inside _resolve_dynamic_env;
    # SkillRegistry.start() used to wrap _start_server in `except: stop();
    # raise`, so an unguarded raise here brought the whole voice loop down for
    # a single skill.yaml typo (since T3.1 it would take that one server
    # down instead — still wrong for a typo). Catch it, log at ERROR, and degrade to
    # base+required+optional — the same "degraded server beats a dead voice
    # loop" posture as the missing-variable case. The typo is still caught
    # loudly at check-time by scripts/check_skills.py (Step 1d).
    try:
        resolved = _resolve_dynamic_env(name, dynamic)
    except ValueError as exc:
        logger.error("mcp_requires_env_dynamic_invalid server=%s error=%s "
                     "(child gets base+requires_env+optional_env only)",
                     name, exc)
        resolved = []
    for key in resolved:
        if key in BASE_ENV_KEYS or key in env:
            continue
        value = os.environ.get(key)
        if value is not None:
            env[key] = value
    return env


#: Status spec T3.1 (L11, fact 3.4a): after an MCP child dies,
#: ClientSession.call_tool raises one of these FOREVER — nothing in the SDK
#: reconnects. call() treats them as "the server stopped", restarts it once
#: and retries the call. McpError counts only for "Connection closed".
_TRANSPORT_ERRORS = (
    anyio.ClosedResourceError, anyio.BrokenResourceError, anyio.EndOfStream,
    McpError,
)

#: Restart backoff: at most RESTART_LIMIT restarts per server inside
#: RESTART_WINDOW_S; past that the server stays down (its tools answer
#: "unavailable") until the window clears.
RESTART_WINDOW_S = 60.0
RESTART_LIMIT = 3
RESTART_STOP_TIMEOUT_S = 10.0
RESTART_READY_TIMEOUT_S = 30.0
STOP_TIMEOUT_S = 10.0

#: The AsyncExitStack of the owner task currently running `_serve`. Set
#: inside the owner task only (each asyncio task has its own context), so
#: `_start_server` can only ever enter contexts into the stack of the task
#: that will also exit them (fact 3.4c).
_OWNER_STACK: contextvars.ContextVar[AsyncExitStack | None] = contextvars.ContextVar(
    "mcp_owner_stack", default=None)


def _is_transport_error(exc: BaseException) -> bool:
    if isinstance(exc, McpError):
        return "Connection closed" in str(exc)
    return isinstance(exc, _TRANSPORT_ERRORS)


@dataclass
class _ServerHandle:
    """One MCP server and the owner task that holds its contexts (T3.1)."""

    name: str
    entry: dict
    state: str = "starting"          # starting | up | down
    session: ClientSession | None = None
    tools: dict[str, Tool] = field(default_factory=dict)
    last_error: str = ""
    restarts: list[float] = field(default_factory=list)   # monotonic times
    stop: asyncio.Event = field(default_factory=asyncio.Event)
    ready: asyncio.Event = field(default_factory=asyncio.Event)
    # Set when this generation's owner task ends, so a call already in
    # flight learns the child is gone instead of waiting out CALL_TIMEOUT.
    gone: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class SkillRegistry:
    """Supervised MCP client manager (status spec T3.1, L11).

    Each server lives in its own OWNER TASK (`_serve`), which is the only
    task that enters and exits that server's stdio/ClientSession contexts —
    exiting them from any other task logs "Attempted to exit cancel scope in
    a different task" and leaks the child (fact 3.4c). A server that fails
    to start is marked down without stopping the others; a server whose
    child dies is restarted once per failing call, with backoff.
    """

    def __init__(self, config_path: Path):
        self._config_path = Path(config_path)
        self._server_configs: list[dict[str, Any]] = []
        self._handles: dict[str, _ServerHandle] = {}
        self._sessions: dict[str, ClientSession] = {}
        self._tools: dict[str, tuple[str, Any]] = {}  # tool -> (server, Tool)
        # tool -> server, from every listing ever seen, so a down server's
        # tools answer "unavailable" rather than "Unknown tool".
        self._known_tools: dict[str, str] = {}
        self._restart_tasks: set[asyncio.Task] = set()

    @property
    def server_names(self) -> list[str]:
        return [entry["name"] for entry in self._server_configs]

    async def start(self) -> None:
        """Spawn every server in its own owner task and discover tools.

        A server that fails to start is logged and left down; it never
        stops the others. A tool name offered by two servers that are up
        still raises ValueError (after stopping everything)."""
        if self._handles:
            return  # idempotent
        # MORTIMER_ENV_BRIDGE_PLAN.md E1 — bridge Settings into os.environ
        # HERE, not at each caller. `.env` is a file; os.environ is a
        # process, and _start_server below expands ${VAR} against the
        # process. Three entrypoints remembered to call this; routing_eval
        # did not, and every set_reminder in it died on the literal string
        # "${JARVIS_TIMEZONE}". Idempotent (setdefault), so the callers that
        # already bridge are unaffected.
        bridge_settings_to_env()
        config = yaml.safe_load(self._config_path.read_text())
        self._server_configs = list(config["servers"])
        handles = [_ServerHandle(name=entry["name"], entry=entry)
                   for entry in self._server_configs]
        self._handles = {h.name: h for h in handles}
        for h in handles:
            h.task = asyncio.create_task(self._serve(h), name=f"mcp:{h.name}")
        await asyncio.gather(*(h.ready.wait() for h in handles))
        try:
            self._rebuild_tools()
        except ValueError:
            await self.stop()
            raise
        for h in handles:
            if h.state != "up":
                logger.warning("mcp_server_start_failed name=%s error=%s",
                               h.name, h.last_error)

    async def stop(self) -> None:
        """Stop every owner task and clear state. Idempotent; never raises.

        Safe from any task: each owner task closes its own contexts."""
        try:
            handles = list(self._handles.values())
            for h in handles:
                h.stop.set()
            for task in list(self._restart_tasks):
                task.cancel()
            tasks = {h.task for h in handles
                     if h.task is not None and not h.task.done()}
            if tasks:  # asyncio.wait raises on an empty set
                _done, pending = await asyncio.wait(tasks, timeout=STOP_TIMEOUT_S)
                for task in pending:
                    logger.warning("registry_stop_straggler task=%s", task.get_name())
                    task.cancel()
                if pending:
                    await asyncio.wait(pending, timeout=STOP_TIMEOUT_S)
        except Exception as exc:  # shutdown noise must not propagate
            logger.warning("registry_stop_error: %s", exc)
        finally:
            self._sessions = {}
            self._tools = {}
            self._handles = {}
            self._known_tools = {}

    def status(self) -> dict[str, dict]:
        """{server: {state, last_error, restarts_last_60s, tools}}."""
        now = time.monotonic()
        out: dict[str, dict] = {}
        for name, h in self._handles.items():
            out[name] = {
                "state": h.state,
                "last_error": h.last_error,
                "restarts_last_60s": sum(
                    1 for t in h.restarts if now - t < RESTART_WINDOW_S),
                "tools": sum(1 for server, _ in self._tools.values()
                             if server == name),
            }
        return out

    def openai_tools(self, server_names: list[str] | None = None) -> list[dict]:
        """Discovered tools as OpenAI function schemas, optionally filtered.

        Reading the menu also revives down servers (revive_down), so a
        server comes back once its backoff clears without any call."""
        self.revive_down()
        allowed = set(server_names) if server_names is not None else None
        schemas = []
        for tool_name, (server, tool) in self._tools.items():
            if allowed is not None and server not in allowed:
                continue
            parameters = tool.inputSchema or {"type": "object", "properties": {}}
            if tool_name in RUN_ID_INJECTED_TOOLS:
                parameters = copy.deepcopy(parameters)          # GL9: the model never sees run_id
                (parameters.get("properties") or {}).pop("run_id", None)
                if isinstance(parameters.get("required"), list):
                    parameters["required"] = [r for r in parameters["required"] if r != "run_id"]
            schemas.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": parameters,
                },
            })
        return schemas

    def tools_for(self, server_names: list[str]) -> list[str]:
        """Tool names owned by the given servers (revives down ones too)."""
        self.revive_down()
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
        if entry is not None:
            server = entry[0]
        else:
            server = self._known_tools.get(tool_name, "")
            if server not in self._handles:
                available = ", ".join(sorted(self._tools)) or "none"
                return f"Unknown tool '{tool_name}'. Available: {available}."
        if server_names is not None and server not in set(server_names):
            return f"Tool '{tool_name}' is not available in this context."
        holder = current_sensitive_turn.get()
        if (server in EXTERNAL_TOOL_SERVERS and holder is not None
                and holder.is_armed()):
            # The current turn may contain financial/private material. Do not
            # let an external MCP child receive it; the model gets a truthful
            # tool failure and can choose a local-only alternative.
            return (
                f"{tool_name} failed: protected turn cannot call external "
                "tool server."
            )
        session = self._sessions.get(server)
        if entry is None or session is None:
            # T3.1: the tool's server is down. Say so truthfully (never
            # "Unknown tool", which invites the model to invent another
            # name) and let a background restart bring it back.
            h = self._handles[server]
            self._restart_in_background(server)
            return (f"{tool_name} failed: {server} is unavailable "
                    f"({h.last_error or h.state}); it restarts automatically.")
        if tool_name in RUN_ID_INJECTED_TOOLS:
            arguments = {**arguments, "run_id": get_run_id() or ""}   # GL9: always overwrites
        # Run-logging plan D3/D18/§5.6: record one mcp_call event with the
        # *exact* ok signal for this call (unlike SubAgent's tool_result,
        # which can only infer ok from this function's return string).
        # Skipped entirely when there is no active run (e.g. a direct
        # Supervisor tool call) — this is the normal case, not a warning.
        runlog = get_run_logger()
        return await self._invoke(tool_name, server, session, arguments,
                                  runlog, allow_restart=True)

    async def _call_watching(self, server: str, session: Any,
                             tool_name: str, arguments: dict) -> Any:
        """session.call_tool, raced against the owner task's end.

        A write to a child that just died crashes the stdio task group and
        ends the owner task, but the request already handed to the session
        never gets an answer or an error — measured: the call sat until
        CALL_TIMEOUT. The owner's `gone` event turns that into the same
        transport error a call after the crash gets."""
        h = self._handles.get(server)
        if h is None or h.session is not session:
            return await session.call_tool(tool_name, arguments)
        gone = h.gone
        call = asyncio.ensure_future(session.call_tool(tool_name, arguments))
        watch = asyncio.ensure_future(gone.wait())
        try:
            await asyncio.wait({call, watch}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            watch.cancel()
            if not call.done():
                call.cancel()
        if call.done() and not call.cancelled():
            return call.result()
        raise anyio.ClosedResourceError(f"{server} owner task ended during the call")

    async def _invoke(self, tool_name: str, server: str, session: Any,
                      arguments: dict, runlog: Any, *,
                      allow_restart: bool) -> str:
        call_start = time.perf_counter()
        try:
            result = await asyncio.wait_for(
                self._call_watching(server, session, tool_name, arguments),
                timeout=CALL_TIMEOUT,
            )
        except asyncio.TimeoutError:
            latency_ms = int((time.perf_counter() - call_start) * 1000)
            error = f"timed out after {int(CALL_TIMEOUT)}s"
            if runlog is not None:
                runlog.mcp_call(tool_name, server, ok=False,
                                 latency_ms=latency_ms, error=error)
            return f"{tool_name} failed: {error}."
        except Exception as exc:
            if _is_transport_error(exc) and server in self._handles:
                # T3.1 (fact 3.4a): the child is gone. Restart it and retry
                # ONCE; the runlog event records the final outcome only.
                h = self._handles[server]
                h.last_error = f"{type(exc).__name__}: {exc}"[:200]
                logger.warning("mcp_server_transport_error name=%s tool=%s error=%s",
                               server, tool_name, h.last_error)
                ok = False
                if allow_restart:
                    ok = await self._restart(server, failed_session=session)
                new_session = self._sessions.get(server)
                if ok and tool_name in self._tools and new_session is not None:
                    return await self._invoke(tool_name, server, new_session,
                                              arguments, runlog,
                                              allow_restart=False)
                latency_ms = int((time.perf_counter() - call_start) * 1000)
                if runlog is not None:
                    runlog.mcp_call(tool_name, server, ok=False,
                                     latency_ms=latency_ms,
                                     error=type(exc).__name__)
                return (f"{tool_name} failed: {server} stopped and could not "
                        f"be restarted ({h.last_error}).")
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

    # ------------------------------------------------------------------ #
    # Supervision (status spec T3.1)
    # ------------------------------------------------------------------ #

    def _rebuild_tools(self) -> None:
        """self._tools from the handles that are up, in config order."""
        tools: dict[str, tuple[str, Any]] = {}
        for h in self._handles.values():
            if h.state != "up":
                continue
            for tool_name, tool in h.tools.items():
                if tool_name in tools:
                    raise ValueError(
                        f"Tool name collision: '{tool_name}' is provided by both "
                        f"'{tools[tool_name][0]}' and '{h.name}'."
                    )
                tools[tool_name] = (h.name, tool)
        self._tools = tools

    def _drop_server_tools(self, name: str) -> None:
        self._tools = {tool: entry for tool, entry in self._tools.items()
                       if entry[0] != name}

    def _install_server_tools(self, h: _ServerHandle) -> None:
        """Put an up server's tools on the menu; a name another server
        already owns is logged and skipped (start() raises on it instead)."""
        self._drop_server_tools(h.name)
        for tool_name, tool in h.tools.items():
            other = self._tools.get(tool_name)
            if other is not None:
                logger.error("mcp_server_tool_collision tool=%s servers=%s,%s",
                             tool_name, other[0], h.name)
                continue
            self._tools[tool_name] = (h.name, tool)

    async def _serve(self, h: _ServerHandle) -> None:
        """Owner task for one server: the ONLY task that enters and exits its
        stdio_client/ClientSession contexts (fact 3.4c). Never re-raises."""
        session: Any = None
        gone = h.gone
        try:
            async with AsyncExitStack() as stack:
                _OWNER_STACK.set(stack)   # this task's context only
                session, discovered = await self._start_server(h.entry)
                old_tools = set(h.tools)
                h.session = session
                h.tools = {tool.name: tool for tool in discovered}
                for tool in discovered:
                    self._known_tools[tool.name] = h.name
                self._sessions[h.name] = session
                h.state = "up"
                h.last_error = ""
                # Review finding 1: the owner registers its own tools, so a
                # restart whose caller was cancelled mid-wait still puts them
                # back on the menu (start() rebuilds and checks collisions
                # once every server has answered).
                if old_tools and set(h.tools) != old_tools:
                    logger.warning("mcp_server_tools_changed name=%s added=%s removed=%s",
                                   h.name, sorted(set(h.tools) - old_tools),
                                   sorted(old_tools - set(h.tools)))
                self._install_server_tools(h)
                h.ready.set()
                logger.info("mcp_server_started name=%s tools=%d",
                            h.name, len(discovered))
                await h.stop.wait()
        except Exception as exc:  # noqa: BLE001 — a dead server never escapes
            h.last_error = f"{type(exc).__name__}: {exc}"[:200]
            logger.warning("mcp_server_down name=%s error=%s", h.name, h.last_error)
        finally:
            h.state = "down"
            h.session = None
            if session is None or self._sessions.get(h.name) is session:
                self._sessions.pop(h.name, None)
            self._drop_server_tools(h.name)
            h.ready.set()
            gone.set()

    def _recent_restarts(self, h: _ServerHandle) -> int:
        now = time.monotonic()
        h.restarts[:] = [t for t in h.restarts if now - t < RESTART_WINDOW_S]
        return len(h.restarts)

    def _restart_in_background(self, server: str) -> bool:
        """Fire-and-forget restart of a down server, if backoff allows and
        no restart of it is already running. True when one was scheduled."""
        h = self._handles.get(server)
        if h is None or h.lock.locked() or self._recent_restarts(h) >= RESTART_LIMIT:
            return False
        task = asyncio.create_task(self._restart(server, only_if_down=True), name=f"mcp-restart:{server}")
        self._restart_tasks.add(task)
        task.add_done_callback(self._restart_tasks.discard)
        return True

    def revive_down(self) -> int:
        """Review finding 2: background-restart every server that is not up
        and whose owner task has ended — down after a crash, after a refused
        restart, or since a failed first start(). A down server's tools are
        on no menu, so no call would ever name them. The backoff
        (RESTART_LIMIT per RESTART_WINDOW_S) is the rate limit: a refused
        server is skipped without spawning anything. Returns how many
        restarts were scheduled; 0 outside a running event loop."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return 0
        scheduled = 0
        for name, h in list(self._handles.items()):
            if h.state == "up" or (h.task is not None and not h.task.done()):
                continue
            if self._restart_in_background(name):
                scheduled += 1
        if scheduled:
            logger.info("mcp_registry_revive scheduled=%d", scheduled)
        return scheduled

    async def _restart(self, server: str, failed_session: Any = None,
                       only_if_down: bool = False) -> bool:
        """Restart one server's owner task. True when it is up afterwards.

        `failed_session` is the session a caller saw fail: if the server is
        already up on a DIFFERENT session, a concurrent caller restarted it
        and this one only needs to retry. `only_if_down` (background
        restarts) skips a server that came back up meanwhile."""
        h = self._handles.get(server)
        if h is None:
            return False
        async with h.lock:
            if only_if_down and h.state == "up":
                return True
            if (failed_session is not None and h.state == "up"
                    and h.session is not None and h.session is not failed_session):
                return True   # a concurrent caller already restarted it
            if self._recent_restarts(h) >= RESTART_LIMIT:
                h.state = "down"
                h.stop.set()
                self._sessions.pop(server, None)
                self._drop_server_tools(server)
                h.last_error = (f"restart limit reached: {RESTART_LIMIT} restarts "
                                f"in {int(RESTART_WINDOW_S)} s")
                logger.warning("mcp_server_restart_backoff name=%s restarts=%d",
                               server, len(h.restarts))
                return False
            h.stop.set()
            if h.task is not None and not h.task.done():
                # asyncio.wait, not wait_for: it neither cancels the owner
                # task if THIS caller is cancelled nor re-raises its outcome.
                done, _ = await asyncio.wait({h.task}, timeout=RESTART_STOP_TIMEOUT_S)
                if not done:
                    logger.warning("mcp_server_stop_timeout name=%s", server)
                    h.task.cancel()
                    await asyncio.wait({h.task}, timeout=RESTART_STOP_TIMEOUT_S)
            h.stop = asyncio.Event()
            h.ready = asyncio.Event()
            h.gone = asyncio.Event()
            h.state = "starting"
            # Review finding 1: counted with the spawn, not after the ready
            # wait, so a cancelled caller cannot skip the backoff bookkeeping
            # (and the new owner registers its own tools when it is up).
            h.restarts.append(time.monotonic())
            h.task = asyncio.create_task(self._serve(h), name=f"mcp:{server}")
            try:
                await asyncio.wait_for(h.ready.wait(), RESTART_READY_TIMEOUT_S)
            except asyncio.TimeoutError:
                h.last_error = f"restart timed out after {int(RESTART_READY_TIMEOUT_S)} s"
                h.stop.set()
                h.task.cancel()
            ok = h.state == "up"
            logger.info("mcp_server_restarted name=%s ok=%s", server, ok)
            logger.info("mcp_registry_status %s", json.dumps(self.status()))
            return ok

    async def _start_server(self, entry: dict[str, Any]) -> tuple[Any, list[Any]]:
        """Open one server's contexts on the CALLING owner task's stack and
        return (session, tools). Called only from `_serve`."""
        name = entry["name"]
        env = build_child_env(entry)
        for key, value in (entry.get("env") or {}).items():
            expanded = expand_env_vars(str(value))
            # E2 — expand_env_vars leaves an unresolved ${VAR} as literal
            # text BY DESIGN, and that design is relied on elsewhere. But
            # handing a child the seven characters "${JARVIS_TIMEZONE}" is
            # never correct; it surfaced as a ZoneInfoNotFoundError five
            # frames deep inside a subprocess, naming nothing useful.
            #
            # A warning, not a refusal: refusing would turn a degraded
            # reminder into a dead voice loop, and mcp_git/mcp_repo already
            # set the precedent of IGNORING "${"-containing values rather
            # than raising. This makes the condition visible in the parent,
            # at the moment it happens, with the variable named.
            if "${" in expanded:
                logger.warning(
                    "mcp_server_env_unresolved server=%s var=%s value=%s "
                    "(the variable is not set in this process — the child "
                    "will receive the literal placeholder)",
                    name, key, expanded)
            env[key] = expanded
        env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")

        command = entry["command"]
        if command in _PYTHON_COMMANDS:
            command = sys.executable
        kwargs = {"command": command, "args": list(entry["args"]), "env": env}
        try:
            params = StdioServerParameters(cwd=str(REPO_ROOT), **kwargs)
        except TypeError:  # older SDKs lack cwd; repo root is inherited cwd
            params = StdioServerParameters(**kwargs)

        stack = _OWNER_STACK.get()
        if stack is None:
            raise RuntimeError("_start_server must run inside an owner task (_serve)")
        read, write = await stack.enter_async_context(stdio_client(params))
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        discovered = (await session.list_tools()).tools
        return session, list(discovered)
