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
import hashlib
import json
import logging
import os
import sys
import time
from collections.abc import Iterator
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import anyio
import yaml
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.shared.exceptions import McpError
from mcp.types import Tool

from jarvis.bot.sensitive_turn import current_sensitive_turn, is_sensitive
from jarvis.config import bridge_settings_to_env, expand_env_vars
from jarvis.runlog.context import get_run_id, get_run_logger
from jarvis.privacy_policy import (
    DataPolicy, ToolExecutionScope, ToolResultBindingError, ToolResultEnvelope,
    issue_tool_result, make_tool_execution_scope, unclassified_tool_result,
    validate_tool_result,
)
from jarvis.toolresult import classify_tool_result
from jarvis.yaml_utils import load_unique_yaml_file

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
RUN_ID_INJECTED_TOOLS: frozenset[str] = frozenset({
    "selfedit_start", "plan_start", "app_build_start",
    "research_compare_start", "research_status",
})

# Source authority is bound to the actual installed module/session generation,
# then to an exact operation. Neither a server name nor returned JSON labels
# establish that newly acquired content is approved for external processing.
_PUBLIC_SOURCE_OPERATIONS = {
    "mcp-time": frozenset({"get_current_time", "resolve_date_expression", "date_add", "date_diff"}),
    "mcp-web": frozenset({"web_search", "get_weather", "get_weather_radar", "sports_scores"}),
    "mcp-system": frozenset({"get_system_status"}),
    "mcp-status": frozenset({"status_models", "status_services", "status_overview",
                              "status_build", "status_catalog", "status_subscription"}),
}
_REPO_SOURCE_OPERATIONS = frozenset({"repo_read_file", "repo_list_files", "repo_search"})
_WORKSPACE_SOURCE_OPERATIONS = {
    'mcp-selfedit': frozenset({'selfedit_start', 'selfedit_status', 'selfedit_read',
                              'selfedit_write', 'selfedit_finish'}),
    'mcp-apps': frozenset({'app_build_start', 'app_build_status', 'app_build_submit'}),
}
_PINNED_SOURCE_MODULES = {
    server: f"mcp_servers.{server.replace('-', '_')}.server"
    for server in (*_PUBLIC_SOURCE_OPERATIONS, "mcp-repo", *_WORKSPACE_SOURCE_OPERATIONS)
}


@dataclass(frozen=True)
class _ToolSourceContract:
    server: str
    module: str
    session: Any = field(repr=False, compare=False)
    repo_root: Path | None = field(default=None, repr=False)
    local_admin: bool = field(default=False, repr=False)

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
        logger.warning("skill_yaml_missing server=%s "
                       "(child gets BASE_ENV_KEYS only)", server_name)
        return [], [], []
    except Exception:  # noqa: BLE001
        logger.warning("skill_yaml_unreadable server=%s "
                       "(child gets BASE_ENV_KEYS only)", server_name)
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
            logger.warning(
                "upgrade_models_unreadable server=%s error_type=%s",
                server_name, type(exc).__name__[:64])
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
    except ValueError:
        logger.error("mcp_requires_env_dynamic_invalid server=%s "
                     "(child gets base+requires_env+optional_env only)",
                     name)
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
        self._source_contracts: dict[str, _ToolSourceContract] = {}
        self._tools: dict[str, tuple[str, Any]] = {}  # tool -> (server, Tool)
        # tool -> server, from every listing ever seen, so a down server's
        # tools answer "unavailable" rather than "Unknown tool".
        self._known_tools: dict[str, str] = {}
        self._restart_tasks: set[asyncio.Task] = set()
        # Review finding 4: set for the whole of stop(), so a restart (or a
        # revive) that resumes after stop() began creates nothing.
        self._closing = False

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
        self._closing = False
        # MORTIMER_ENV_BRIDGE_PLAN.md E1 — bridge Settings into os.environ
        # HERE, not at each caller. `.env` is a file; os.environ is a
        # process, and _start_server below expands ${VAR} against the
        # process. Three entrypoints remembered to call this; routing_eval
        # did not, and every set_reminder in it died on the literal string
        # "${JARVIS_TIMEZONE}". Idempotent (setdefault), so the callers that
        # already bridge are unaffected.
        bridge_settings_to_env()
        config = load_unique_yaml_file(self._config_path)
        self._server_configs = list(config["servers"])
        handles = [_ServerHandle(name=entry["name"], entry=entry)
                   for entry in self._server_configs]
        self._handles = {h.name: h for h in handles}
        try:
            await self._start_owners(handles)
        except asyncio.CancelledError:
            # Review finding 4: a cancelled start() must not leave the owner
            # tasks it spawned running.
            await self.stop()
            raise

    async def _start_owners(self, handles: list[_ServerHandle]) -> None:
        for h in handles:
            h.task = asyncio.create_task(self._serve(h), name=f"mcp:{h.name}")
        # Review finding 3: bounded. shared.py holds its lock across start(),
        # so one child that never answers `initialize` must not block every
        # session; the straggler is stopped and left down (revive_down
        # retries it later, under the backoff).
        waits = {asyncio.ensure_future(h.ready.wait()): h for h in handles}
        try:
            _done, pending = await asyncio.wait(
                waits, timeout=RESTART_READY_TIMEOUT_S)
        finally:
            for wait in waits:
                wait.cancel()
        for wait in pending:
            h = waits[wait]
            logger.warning("mcp_server_start_timeout name=%s timeout_s=%d",
                           h.name, int(RESTART_READY_TIMEOUT_S))
            h.stop.set()
            if h.task is not None:
                h.task.cancel()
            h.state = "down"
            h.last_error = "start timed out"
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
        self._closing = True
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
            # Shutdown failures can carry subprocess diagnostics, paths, or
            # provider text. Keep the owner task alive but never log payloads.
            logger.warning("registry_stop_error error_type=%s",
                           type(exc).__name__[:80])
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

    def _source_contract_for(
        self, tool_name: str, server: str, session: Any,
    ) -> _ToolSourceContract | None:
        contract = self._source_contracts.get(server)
        handle = self._handles.get(server)
        if (contract is None or contract.session is not session or session is None
                or handle is None or handle.session is not session
                or contract.server != server
                or contract.module != _PINNED_SOURCE_MODULES.get(server)
                or self._tools.get(tool_name, (None,))[0] != server):
            return None
        return contract

    @staticmethod
    def _repo_source_refs(
        contract: _ToolSourceContract, tool_name: str, arguments: dict,
        body: dict | None,
    ) -> tuple[str, ...]:
        """Verify requested scope and exact locally readable result references.

        Host-side checks use the same guard as the installed reader. Returned
        paths, snippets and labels cannot broaden the requested repository or
        claim that unrelated content originated in an approved project.
        """
        from mcp_servers.mcp_repo.logic import (
            REPO_READ_MAX_BYTES, REPO_SEARCH_MAX_RESULTS,
            resolve_repo_path,
        )

        root = contract.repo_root
        if root is None or not root.is_dir():
            raise ValueError("tool_source_scope_invalid")
        if tool_name == "repo_read_file":
            if set(arguments) != {"path"} or type(arguments["path"]) is not str:
                raise ValueError("tool_source_scope_invalid")
            expected = resolve_repo_path(root, arguments["path"])
            if body is None:
                return (str(expected),)
            if (set(body) != {"ok", "path", "bytes", "content"}
                    or body["ok"] is not True or type(body["path"]) is not str
                    or type(body["bytes"]) is not int or type(body["content"]) is not str
                    or body["path"] != expected.relative_to(root).as_posix()
                    or resolve_repo_path(root, body["path"]) != expected
                    or not expected.is_file() or expected.stat().st_size > REPO_READ_MAX_BYTES
                    or body["bytes"] != expected.stat().st_size
                    or expected.read_text(encoding="utf-8") != body["content"]):
                raise ValueError("tool_source_scope_invalid")
            return (str(expected),)
        allowed = {"subdir", "pattern"} if tool_name == "repo_list_files" else {"query", "subdir"}
        if (not set(arguments).issubset(allowed)
                or any(type(value) is not str for value in arguments.values())
                or (tool_name == "repo_search" and not arguments.get("query", "").strip())):
            raise ValueError("tool_source_scope_invalid")
        subdir = arguments.get("subdir", "")
        base = resolve_repo_path(root, subdir) if subdir else root
        if body is None:
            return (str(base),)
        value_key = "files" if tool_name == "repo_list_files" else "matches"
        if (set(body) != {"ok", value_key, "truncated"} or body["ok"] is not True
                or type(body["truncated"]) is not bool or type(body[value_key]) is not list
                or len(body[value_key]) > REPO_SEARCH_MAX_RESULTS):
            raise ValueError("tool_source_scope_invalid")
        refs: list[str] = []
        text_by_path: dict[Path, list[str]] = {}
        for item in body[value_key]:
            if tool_name == "repo_list_files":
                path = item
            else:
                if (type(item) is not dict or set(item) != {"path", "line", "text"}
                        or type(item["line"]) is not int or item["line"] < 1
                        or type(item["text"]) is not str):
                    raise ValueError("tool_source_scope_invalid")
                path = item["path"]
            if type(path) is not str:
                raise ValueError("tool_source_scope_invalid")
            resolved = resolve_repo_path(root, path)
            if (not resolved.is_relative_to(base) or path != resolved.relative_to(root).as_posix()
                    or not resolved.is_file()):
                raise ValueError("tool_source_scope_invalid")
            if tool_name == "repo_list_files":
                if arguments.get("pattern") and not resolved.match(arguments["pattern"]):
                    raise ValueError("tool_source_scope_invalid")
            else:
                if resolved.stat().st_size > REPO_READ_MAX_BYTES:
                    raise ValueError("tool_source_scope_invalid")
                if resolved not in text_by_path:
                    text_by_path[resolved] = resolved.read_text(encoding="utf-8").splitlines()
                lines = text_by_path[resolved]
                if (item["line"] > len(lines) or arguments["query"] not in lines[item["line"] - 1]
                        or item["text"] != lines[item["line"] - 1].strip()[:200]):
                    raise ValueError("tool_source_scope_invalid")
            refs.append(str(resolved))
        return tuple(dict.fromkeys(refs)) or (str(base),)

    def _classified_result(
        self, tool_name: str, server: str, session: Any, arguments: dict,
        content: str, execution_scope: ToolExecutionScope | None,
        runlog: Any, *, failure_category: str | None = None, host_failure: str | None = None,
    ) -> str | ToolResultEnvelope:
        if execution_scope is None:
            return content
        contract = self._source_contract_for(tool_name, server, session)
        envelope: ToolResultEnvelope | None = None
        if host_failure is not None:
            # These branches acquired no source content. Release only a
            # closed, generated category; names, paths and last-error text
            # from the legacy status string do not enter the envelope.
            content = json.dumps({"ok": False, "error": host_failure}, separators=(",", ":"))
            envelope = issue_tool_result(
                execution_scope, content, DataPolicy("approved_external", "host-generated-tool-status"),
                "host-generated-tool-status", (),
            )
        outcome = classify_tool_result(tool_name, content)
        if envelope is None and contract is not None and server == 'mcp-apps' and tool_name == 'app_write_file':
            from mcp_servers.development_boundary import sandbox_required
            expected = sandbox_required(application=True)
            try:
                if json.loads(content) == expected:
                    envelope = issue_tool_result(execution_scope, content,
                        DataPolicy('approved_external', 'host-generated-development-refusal'),
                        'host-generated-development-refusal')
            except (ValueError, TypeError):
                pass
        if envelope is None and contract is not None:
            source_scope = f"public-operation:{server}:{tool_name}"
            refs: tuple[str, ...] = ()
            approved = tool_name in _PUBLIC_SOURCE_OPERATIONS.get(server, ())
            if server == "mcp-repo" and tool_name in _REPO_SOURCE_OPERATIONS:
                from mcp_servers.mcp_repo.logic import RepoPathError

                source_scope = "repository:" + hashlib.sha256(
                    str(contract.repo_root).encode("utf-8")
                ).hexdigest()
                try:
                    body = json.loads(content) if outcome.ok else None
                    if outcome.ok and type(body) is not dict:
                        raise ValueError("tool_source_scope_invalid")
                    refs = self._repo_source_refs(contract, tool_name, arguments, body)
                    approved = True
                except (RepoPathError, ValueError, TypeError, OSError, UnicodeError):
                    content = '{"ok":false,"error":"tool_source_scope_invalid"}'
                    approved = False
                    envelope = unclassified_tool_result(execution_scope, content)
            if approved:
                if not outcome.ok:
                    # Explicit host reduction: remove every byte of raw MCP,
                    # HTTP and tool failure text. This fixed generated result
                    # preserves useful public failure/constraint continuation.
                    content = json.dumps({"ok": False, "error": failure_category or "tool_reported_failure"},
                                         separators=(",", ":"))
                try:
                    envelope = issue_tool_result(
                        execution_scope, content,
                        DataPolicy("approved_external", "verified-host-tool-source"),
                        source_scope, refs,
                    )
                except ValueError:
                    envelope = unclassified_tool_result(execution_scope,
                        '{"ok":false,"error":"tool_source_scope_invalid"}')
        if envelope is None:
            try:
                envelope = unclassified_tool_result(execution_scope, content)
            except ValueError:
                envelope = unclassified_tool_result(execution_scope,
                    '{"ok":false,"error":"invalid_tool_result_content"}')
        policy, _ = validate_tool_result(execution_scope, envelope)
        if policy.level in {"confidential", "local_only"}:
            holder = current_sensitive_turn.get()
            if holder is not None:
                holder.arm("tool_source_policy", execution_scope.parent_request_id)
            if runlog is not None:
                runlog.mark_sensitive()
        return envelope

    def _finish_invocation(
        self, tool_name: str, server: str, session: Any, arguments: dict,
        content: str, runlog: Any, latency_ms: int,
        execution_scope: ToolExecutionScope | None, *, failure_category: str | None = None,
    ) -> str | ToolResultEnvelope:
        value = self._classified_result(
            tool_name, server, session, arguments, content, execution_scope,
            runlog, failure_category=failure_category,
        )
        observed = value.content if isinstance(value, ToolResultEnvelope) else value
        outcome = classify_tool_result(tool_name, observed)
        if runlog is not None:
            # No raw provider/MCP error is telemetry, even in legacy mode.
            runlog.mcp_call(tool_name, server, ok=outcome.ok, latency_ms=latency_ms,
                            error=(failure_category or "tool_reported_failure") if not outcome.ok else None)
        return value

    async def call(
        self,
        tool_name: str,
        arguments: dict,
        server_names: list[str] | None = None,
    ) -> str:
        """Invoke a tool. Returns plain text (JSON for dict results) or a
        one-line failure string. Never raises."""
        return await self._call(tool_name, arguments, server_names)

    async def call_classified(
        self, tool_name: str, arguments: dict, server_names: list[str] | None = None,
        *, execution_scope: ToolExecutionScope,
    ) -> ToolResultEnvelope:
        """Invoke with host-issued source policy before any result sink.

        Scope arguments bind the caller's model-visible call, before GL9's
        trusted run_id injection. That injection is ownership, not source
        approval. A scope mismatch refuses before touching an MCP child.
        """
        try:
            expected = make_tool_execution_scope(
                execution_scope.parent_request_id, execution_scope.task_id,
                execution_scope.tool_call_id, tool_name, arguments, execution_scope.input_policy,
            )
            runlog = get_run_logger()
            if (type(execution_scope) is not ToolExecutionScope
                    or execution_scope.tool_name != tool_name
                    or execution_scope.argument_digest != expected.argument_digest
                    or (runlog is not None and runlog.run_id != execution_scope.parent_request_id)):
                raise ToolResultBindingError()
        except (ValueError, TypeError, AttributeError):
            raise ToolResultBindingError() from None
        if execution_scope.input_policy.level in {"confidential", "local_only"}:
            holder = current_sensitive_turn.get()
            if holder is not None:
                holder.arm("tool_source_policy", execution_scope.parent_request_id)
            if runlog is not None:
                runlog.mark_sensitive()
        value = await self._call(tool_name, arguments, server_names, execution_scope=execution_scope)
        if not isinstance(value, ToolResultEnvelope):
            raise ToolResultBindingError()
        return value

    async def _call(
        self, tool_name: str, arguments: dict, server_names: list[str] | None = None,
        *, execution_scope: ToolExecutionScope | None = None,
    ) -> str | ToolResultEnvelope:
        # Do not let a caller or adapter mutate the arguments after the scope
        # was checked and bind a different asynchronous invocation to it.
        source_arguments = copy.deepcopy(arguments) if execution_scope is not None else arguments
        arguments = copy.deepcopy(source_arguments) if execution_scope is not None else arguments
        runlog = get_run_logger()
        entry = self._tools.get(tool_name)
        if entry is not None:
            server = entry[0]
        else:
            server = self._known_tools.get(tool_name, "")
            if server not in self._handles:
                available = ", ".join(sorted(self._tools)) or "none"
                return self._classified_result(tool_name, server, None, arguments,
                    f"Unknown tool '{tool_name}'. Available: {available}.", execution_scope, runlog,
                    host_failure="tool_unknown")
        if server_names is not None and server not in set(server_names):
            return self._classified_result(tool_name, server, None, arguments,
                f"Tool '{tool_name}' is not available in this context.", execution_scope, runlog,
                host_failure="tool_not_available")
        if server in EXTERNAL_TOOL_SERVERS and is_sensitive():
            # The current turn may contain financial/private material. Do not
            # let an external MCP child receive it; the model gets a truthful
            # tool failure and can choose a local-only alternative.
            content = (
                f"{tool_name} failed: protected turn cannot call external "
                "tool server."
            )
            return self._classified_result(tool_name, server, None, arguments, content,
                                           execution_scope, runlog, host_failure="tool_protected")
        session = self._sessions.get(server)
        if entry is None or session is None:
            # T3.1: the tool's server is down. Say so truthfully (never
            # "Unknown tool", which invites the model to invent another
            # name) and let a background restart bring it back.
            h = self._handles[server]
            self._restart_in_background(server)
            content = (f"{tool_name} failed: {server} is unavailable "
                       f"({h.last_error or h.state}); it restarts automatically.")
            return self._classified_result(tool_name, server, None, arguments, content,
                                           execution_scope, runlog, host_failure="tool_unavailable")
        if tool_name in RUN_ID_INJECTED_TOOLS:
            arguments = {**arguments, "run_id": get_run_id() or ""}   # GL9: always overwrites
        # Run-logging plan D3/D18/§5.6: record one mcp_call event with the
        # *exact* ok signal for this call (unlike SubAgent's tool_result,
        # which can only infer ok from this function's return string).
        # Skipped entirely when there is no active run (e.g. a direct
        # Supervisor tool call) — this is the normal case, not a warning.
        return await self._invoke(tool_name, server, session, arguments,
                                  runlog, allow_restart=True, execution_scope=execution_scope,
                                  source_arguments=source_arguments)

    async def _call_watching(self, server: str, session: Any,
                             tool_name: str, arguments: dict, *, meta: dict | None = None) -> Any:
        """session.call_tool, raced against the owner task's end.

        A write to a child that just died crashes the stdio task group and
        ends the owner task, but the request already handed to the session
        never gets an answer or an error — measured: the call sat until
        CALL_TIMEOUT. The owner's `gone` event turns that into the same
        transport error a call after the crash gets."""
        h = self._handles.get(server)
        kwargs = {} if meta is None else {'meta': meta}
        if h is None or h.session is not session:
            return await session.call_tool(tool_name, arguments, **kwargs)
        gone = h.gone
        call = asyncio.ensure_future(session.call_tool(tool_name, arguments, **kwargs))
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

    @staticmethod
    def _workspace_live_run(runlog, scope, *, check_floor=True, expected_agent='developer'):
        from jarvis.runlog.store import get_run, SENSITIVE_SENTINEL
        from jarvis.skill_runtime import runtime_owner

        if runlog is None or runlog.run_id != scope.parent_request_id:
            raise ToolResultBindingError()
        detail = get_run(scope.parent_request_id)
        run = detail.get('run') if type(detail) is dict else None
        if (type(run) is not dict or run.get('agent') != expected_agent or run.get('status') != 'running'
                or run.get('user_id') != runlog.user_id or run.get('session_id') != runlog.session_id
                or runtime_owner(runlog.session_id) != runlog.user_id):
            raise ToolResultBindingError()
        floor = DataPolicy('approved_external', 'verified-workspace-caller')
        if any(run.get(key) == SENSITIVE_SENTINEL for key in ('task', 'task_preview', 'reply_preview')):
            floor = DataPolicy('confidential', 'protected-workspace-caller')
        if check_floor:
            from jarvis.development_sources import workspace_floor
            from jarvis.privacy_policy import strictest
            floor = strictest(floor, workspace_floor(run))
        return floor

    async def _workspace_source_invocation(self, tool, server, session, arguments,
                                            source_arguments, runlog, scope):
        from jarvis.development_attestation import (new_source_challenge, pin_source_authority,
            verify_workspace_source, _workspace_context, DevelopmentSourceAttestationError)
        from jarvis.model_routing import ModelRouteError
        from jarvis.privacy_policy import strictest
        expected_agent = 'app_builder' if server == 'mcp-apps' else 'developer'

        try:
            self._workspace_live_run(runlog, scope, check_floor=False, expected_agent=expected_agent)
            metadata = {'owner_id': runlog.user_id, 'bot_session_id': runlog.session_id,
                        'developer_run_id': scope.parent_request_id, 'tool_name': tool,
                        'arguments': source_arguments}
            async def phase(name, extra=None):
                return await self._call_watching(server, session, tool, arguments,
                    meta={'mortimer_development_source': {**metadata, 'phase': name, **(extra or {})}})

            associated = await phase('associate')
            if getattr(associated, 'isError', False) or getattr(associated, 'structuredContent', None) != {'ok': True}:
                raise ToolResultBindingError()
            pin = pin_source_authority()  # before preparation or any operation
            challenge = new_source_challenge()
            call_binding = {'source_challenge': challenge,
                'source_task_id': scope.task_id, 'source_tool_call_id': scope.tool_call_id,
                'source_input_policy': scope.input_policy.level}
            prepared = await phase('prepare', call_binding)
            hidden = (getattr(prepared, 'meta', None) or {}).get('mortimer_development_source')
            if (getattr(prepared, 'isError', False) or type(hidden) is not dict
                    or set(hidden) != {'source_context', 'source_preparation_id'}):
                raise ToolResultBindingError()
            context = _workspace_context(hidden['source_context'])
            if (context['owner_id'] != runlog.user_id or context['bot_session_id'] != runlog.session_id
                    or context['developer_run_id'] != scope.parent_request_id
                    or context['workspace_kind'] != ('app-build' if server == 'mcp-apps' else 'selfedit')
                    or pin_source_authority() != pin):
                raise ToolResultBindingError()
            self._workspace_live_run(runlog, scope, expected_agent=expected_agent)
            result = await phase('execute', {**call_binding, 'source_context': context,
                'source_preparation_id': hidden['source_preparation_id']})
            hidden = (getattr(result, 'meta', None) or {}).get('mortimer_development_source')
            if (getattr(result, 'isError', False) or type(hidden) is not dict
                    or set(hidden) != {'source_receipt'}):
                raise ToolResultBindingError()
            envelope = verify_workspace_source(pin, scope, hidden['source_receipt'],
                                               context=context, challenge=challenge)
            policy, content = validate_tool_result(scope, envelope)
            structured = getattr(result, 'structuredContent', None)
            text = '\n'.join(getattr(block, 'text', '') for block in result.content).strip()
            if (structured is None or unclassified_tool_result(scope, structured).content != content
                    or text != content):
                raise ToolResultBindingError()
            floor = self._workspace_live_run(runlog, scope, expected_agent=expected_agent)
            if pin_source_authority() != pin or self._source_contract_for(tool, server, session) is None:
                raise ToolResultBindingError()
            return issue_tool_result(scope, content, strictest(policy, floor),
                                     envelope.source_scope, envelope.canonical_refs)
        except (ToolResultBindingError, DevelopmentSourceAttestationError, ModelRouteError, ValueError, TypeError, KeyError):
            # No unverified body is released. This is an explicit host
            # reduction to a fixed generated refusal, preserving retries.
            floor = scope.input_policy
            try:
                floor = strictest(floor, self._workspace_live_run(runlog, scope, expected_agent=expected_agent))
            except (ToolResultBindingError, ModelRouteError, DevelopmentSourceAttestationError):
                floor = strictest(floor, DataPolicy('confidential', 'unverified-workspace-floor'))
            return issue_tool_result(scope, '{"error":"workspace_source_unavailable","ok":false}',
                floor, 'host-generated-workspace-refusal')

    def _finish_workspace_source(self, envelope, scope, tool, server, runlog, latency_ms):
        policy, content = validate_tool_result(scope, envelope)
        if policy.level in {'confidential', 'local_only'}:
            holder = current_sensitive_turn.get()
            if holder is not None:
                holder.arm('tool_source_policy', scope.parent_request_id)
            if runlog is not None:
                runlog.mark_sensitive()
        if runlog is not None:
            outcome = classify_tool_result(tool, content)
            runlog.mcp_call(tool, server, ok=outcome.ok, latency_ms=latency_ms,
                           error='development_operation_failed' if not outcome.ok else None)
        return envelope

    async def _invoke(self, tool_name: str, server: str, session: Any,
                      arguments: dict, runlog: Any, *,
                      allow_restart: bool,
                      execution_scope: ToolExecutionScope | None = None,
                      source_arguments: dict | None = None) -> str | ToolResultEnvelope:
        source_arguments = arguments if source_arguments is None else source_arguments
        call_start = time.perf_counter()
        try:
            contract = self._source_contract_for(tool_name, server, session)
            workspace = (execution_scope is not None and contract is not None and contract.local_admin
                         and tool_name in _WORKSPACE_SOURCE_OPERATIONS.get(server, ()))
            result = await asyncio.wait_for(
                self._workspace_source_invocation(tool_name, server, session, arguments,
                    source_arguments, runlog, execution_scope) if workspace
                else self._call_watching(server, session, tool_name, arguments),
                timeout=CALL_TIMEOUT,
            )
        except asyncio.TimeoutError:
            latency_ms = int((time.perf_counter() - call_start) * 1000)
            error = f"timed out after {int(CALL_TIMEOUT)}s"
            return self._finish_invocation(tool_name, server, session, source_arguments,
                f"{tool_name} failed: {error}.", runlog, latency_ms, execution_scope,
                failure_category="tool_timeout")
        except Exception as exc:  # noqa: BLE001 — contain and redact MCP/provider failures
            if _is_transport_error(exc) and server in self._handles:
                # T3.1 (fact 3.4a): the child is gone. Restart it and retry
                # ONCE; the runlog event records the final outcome only.
                h = self._handles[server]
                # Transport exception messages can include argv, request
                # details or provider data. Keep the status/log marker safe.
                h.last_error = type(exc).__name__[:64]
                logger.warning("mcp_server_transport_error name=%s tool=%s error_type=%s",
                               server, tool_name, h.last_error)
                ok = False
                if allow_restart:
                    ok = await self._restart(server, failed_session=session)
                new_session = self._sessions.get(server)
                if ok and tool_name in self._tools and new_session is not None:
                    return await self._invoke(tool_name, server, new_session,
                                              arguments, runlog,
                                              allow_restart=False, execution_scope=execution_scope,
                                              source_arguments=source_arguments)
                latency_ms = int((time.perf_counter() - call_start) * 1000)
                content = (f"{tool_name} failed: {server} stopped and could not "
                           f"be restarted ({h.last_error}).")
                return self._finish_invocation(tool_name, server, session, source_arguments,
                    content, runlog, latency_ms, execution_scope, failure_category="tool_transport_error")
            latency_ms = int((time.perf_counter() - call_start) * 1000)
            error = type(exc).__name__
            # Provider/MCP exception messages can contain request arguments,
            # response bodies, credentials, or user content. Keep logs to a
            # stable error category; the caller receives the same bounded code.
            logger.warning("tool_call_failed error_type=%s", error[:64])
            return self._finish_invocation(tool_name, server, session, source_arguments,
                f"{tool_name} failed: {error}.", runlog, latency_ms, execution_scope,
                failure_category="tool_exception")

        latency_ms = int((time.perf_counter() - call_start) * 1000)
        if isinstance(result, ToolResultEnvelope):
            return self._finish_workspace_source(result, execution_scope, tool_name, server, runlog, latency_ms)
        if getattr(result, "isError", False):
            text = " ".join(
                getattr(c, "text", "") for c in result.content
            ).strip()
            error = text or "unknown error"
            return self._finish_invocation(tool_name, server, session, source_arguments,
                f"{tool_name} failed: {error}", runlog, latency_ms, execution_scope,
                failure_category="mcp_tool_error")

        structured = getattr(result, "structuredContent", None)
        if structured is not None:
            if execution_scope is None:
                text_result = json.dumps(structured, default=str)
            else:
                try:
                    text_result = unclassified_tool_result(execution_scope, structured).content
                except ValueError:
                    text_result = '{"ok":false,"error":"invalid_tool_result_content"}'
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
        return self._finish_invocation(tool_name, server, session, source_arguments,
            text_result, runlog, latency_ms, execution_scope)

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
            # The MCP/provider exception may include arguments, response
            # bodies, a path, or a credential. Status and logs expose only
            # its stable type; detailed diagnostics stay out of band.
            h.last_error = type(exc).__name__[:80]
            logger.warning("mcp_server_down name=%s error_type=%s",
                           h.name, h.last_error)
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
        if (self._closing or h is None or h.lock.locked()
                or self._recent_restarts(h) >= RESTART_LIMIT):
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
        if self._closing:
            return 0
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
            # Review finding 4: checked after every await below — stop()
            # may have run meanwhile, and nothing may be spawned after it.
            if self._closing:
                return False
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
            if self._closing:
                return False
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
            if self._closing:
                return False
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
        module = _PINNED_SOURCE_MODULES.get(name)
        self._source_contracts.pop(name, None)
        if command == sys.executable and list(entry["args"]) == ["-m", module] and module is not None:
            repo_root = None
            if name == "mcp-repo":
                # Capture the actual host-supplied child root now. Later
                # changes to process environment or returned JSON cannot
                # change this generation's authorized project scope.
                value = env.get("JARVIS_REPO_ROOT", "")
                configured = Path(value) if value.strip() and "${" not in value else REPO_ROOT
                if not configured.is_absolute():
                    configured = REPO_ROOT / configured
                try:
                    repo_root = configured.resolve(strict=False)
                except (OSError, ValueError):
                    repo_root = None
            local_admin = False
            if name in _WORKSPACE_SOURCE_OPERATIONS:
                from urllib.parse import urlsplit
                from jarvis.urls import ADMIN_URL_ENV, DEFAULT_ADMIN_URL
                try:
                    origin = urlsplit(env.get(ADMIN_URL_ENV) or DEFAULT_ADMIN_URL)
                    local_admin = (origin.scheme in {'http', 'https'}
                        and origin.hostname in {'localhost', '127.0.0.1', '::1'}
                        and not origin.username and not origin.password
                        and origin.path in {'', '/'} and not origin.query and not origin.fragment)
                except ValueError:
                    pass
            self._source_contracts[name] = _ToolSourceContract(name, module, session, repo_root, local_admin)
        return session, list(discovered)
