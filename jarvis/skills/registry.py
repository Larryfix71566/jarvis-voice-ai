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
import copy
import json
import logging
import os
import sys
import time
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, Iterator

import yaml
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

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
        # upgrade_models_api_keys
        names.add("OPENAI_API_KEY")  # mcp_screen/logic.py:282 default
        try:
            with open(REPO_ROOT / "config" / "upgrade_models.yaml", "r",
                      encoding="utf-8") as fh:
                registry = yaml.safe_load(fh) or {}
        except Exception as exc:  # noqa: BLE001 — degrade to the default only
            logger.warning("upgrade_models_unreadable server=%s error=%s",
                           server_name, exc)
            continue
        for value in _walk_api_key_envs(registry):
            names.add(value)
    return sorted(names)


def _walk_api_key_envs(node: Any) -> Iterator[str]:
    """Yield every `api_key_env` value anywhere in a parsed YAML tree.

    Walks rather than assuming a shape, because config/upgrade_models.yaml
    groups profiles under keys this module has no business knowing about.
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
    # SkillRegistry.start() wraps _start_server in `except: stop(); raise`,
    # so an unguarded raise here would bring the whole voice loop down for a
    # single skill.yaml typo. Catch it, log at ERROR, and degrade to
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
        session = self._sessions[server]
        if tool_name in RUN_ID_INJECTED_TOOLS:
            arguments = {**arguments, "run_id": get_run_id() or ""}   # GL9: always overwrites
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
