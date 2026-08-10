"""Upgrade Agent: the LLM-driven brain of the self-development loop (plan section 3.5).

The agent interprets a natural-language goal, reads allowlisted source files,
and produces edits — but its only tools are the closed set below, backed by
jarvis/selfedit/service.py. It never gets shell or raw git access.

Behavior contract (any model swapped in via config must pass this — it is the
acceptance suite for the agent's brain):
- Present every proposed diff before validating; summarize validation
  results before submitting. No silent edits.
- One automatic repair attempt after a failed validation; if it fails again,
  end the session and report. Never retry-submit in a loop.
- Decline goals that require off-allowlist changes and say they need human
  development.
- Hard loop bounds: max_iterations tool cycles and max_session_minutes
  wall-clock, from config/upgrade_agent.yaml (overridable via env).

Planner model
-------------
Which model does the planning comes from the registry in
``config/upgrade_models.yaml`` (override path via ``JARVIS_UPGRADE_MODELS``).
Selection order: an explicit per-session ``profile`` argument >
``JARVIS_UPGRADE_PROFILE`` env > the registry's ``default`` key. Profiles are
OpenAI-compatible endpoints; the API key comes from the profile's
``api_key_env`` — keys live in the environment, never in config. A profile
with ``temperature: null`` OMITS the parameter entirely (DEVIATIONS.md D-003:
kimi-k2.x rejects any value other than 1).

If no registry file exists, the agent falls back to the legacy single-slot
config in ``config/upgrade_agent.yaml`` (provider/model/base_url/temperature,
with JARVIS_UPGRADE_MODEL / JARVIS_UPGRADE_BASE_URL env overrides) —
byte-identical behavior to before the registry existed.

The client factory is injectable for tests.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Callable

import yaml

from jarvis.selfedit.service import SelfEditService

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "upgrade_agent.yaml"
)
DEFAULT_REGISTRY_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "upgrade_models.yaml"
)
REGISTRY_PATH_ENV = "JARVIS_UPGRADE_MODELS"
PROFILE_ENV = "JARVIS_UPGRADE_PROFILE"

SYSTEM_PROMPT = """You are the Jarvis Upgrade Agent. You develop upgrades to the
Jarvis interface by proposing code edits, under these NON-NEGOTIABLE rules:

1. `main` changes only via a human merging a pull request on GitHub. You can
   only open PRs. You can never merge, force-push, or touch main.
2. You may only read and edit files on the self-edit allowlist (UI sources
   under web/src, web/public, non-secret config, jarvis/prompts.py,
   jarvis/skills, docs). If the user's goal requires anything else — wake
   word, agents, admin, CI, dependencies, the self-edit machinery itself —
   decline that part and say it requires human development.
3. Your only tools are file_read, edit_propose, session_validate,
   session_submit. There is no shell and no git tool.
4. Propose edits with edit_propose, then call session_validate, and only if
   every check passes call session_submit. If validation fails you get ONE
   repair attempt; if it fails again, stop and report the failure.
5. Keep edits small, self-contained, and explained by a one-line rationale.

Work style: first read the files relevant to the goal, then propose complete
new file contents for each file you change, then validate, then submit.
Reply to the user with a concise summary of what you changed (or why you
declined), in plain language."""

TOOL_SPECS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "file_read",
            "description": "Read an allowlisted repo file.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_propose",
            "description": "Propose a full-file replacement for an allowlisted "
                           "path. Returns the diff.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "new_content": {"type": "string"},
                    "rationale": {"type": "string"},
                },
                "required": ["path", "new_content", "rationale"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "session_validate",
            "description": "Run the validation gate (allowlist, backend "
                           "imports, frontend build).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "session_submit",
            "description": "Commit, push the session branch and open a PR. "
                           "Only works after validation has passed. Merge "
                           "remains manual on GitHub.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


def load_agent_config(path: str | Path | None = None) -> dict:
    cfg_path = Path(path) if path else DEFAULT_CONFIG_PATH
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    return {
        "provider": data.get("provider", "openai"),
        "model": os.environ.get("JARVIS_UPGRADE_MODEL")
                 or data.get("model", "gpt-4.1-mini"),
        "base_url": os.environ.get("JARVIS_UPGRADE_BASE_URL")
                    or data.get("base_url", "https://api.openai.com/v1"),
        "temperature": float(data.get("temperature", 0.2)),
        "max_iterations": int(data.get("max_iterations", 10)),
        "max_session_minutes": int(data.get("max_session_minutes", 30)),
    }


class UnknownModelProfileError(ValueError):
    """Raised when a requested planner profile is not in the registry."""


def load_model_registry(path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    """Load the planner model registry.

    Path precedence: explicit ``path`` > ``JARVIS_UPGRADE_MODELS`` env >
    ``config/upgrade_models.yaml``. A missing file returns the empty registry
    ``{"default": None, "profiles": {}}`` so callers fall back to legacy mode.
    """
    if path is None:
        path = os.environ.get(REGISTRY_PATH_ENV) or DEFAULT_REGISTRY_PATH
    p = Path(path)
    if not p.exists():
        return {"default": None, "profiles": {}}
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    profiles = {prof["name"]: prof for prof in data.get("profiles", []) or []}
    return {"default": data.get("default"), "profiles": profiles}


def resolve_profile(registry: dict[str, Any], requested: str | None = None) -> dict[str, Any]:
    """Resolve which profile to use: explicit > env > registry default."""
    profiles: dict[str, dict[str, Any]] = registry.get("profiles", {})
    name = requested or os.environ.get(PROFILE_ENV) or registry.get("default")
    if not name or name not in profiles:
        available = ", ".join(sorted(profiles)) or "(none)"
        raise UnknownModelProfileError(
            f"unknown upgrade model profile {name!r}; available profiles: {available}"
        )
    return profiles[name]


def available_models(registry_path: str | os.PathLike[str] | None = None) -> list[dict[str, Any]]:
    """List planner profiles for pickers — includes key presence, never key material."""
    registry = load_model_registry(registry_path)
    default = registry.get("default")
    out: list[dict[str, Any]] = []
    for name, prof in sorted(registry.get("profiles", {}).items()):
        key_env = prof.get("api_key_env", "")
        out.append(
            {
                "name": name,
                "label": prof.get("label", name),
                "provider": prof.get("provider", ""),
                "model": prof.get("model", ""),
                "key_env": key_env,
                "key_present": bool(key_env and os.environ.get(key_env)),
                "default": name == default,
            }
        )
    return out


class UpgradeAgent:
    """Drives one self-edit session from a natural-language goal."""

    def __init__(
        self,
        service: SelfEditService,
        config_path: str | Path | None = None,
        registry_path: str | os.PathLike[str] | None = None,
        profile: str | None = None,
        client_factory: Callable[[], Any] | None = None,
    ):
        self.service = service
        self.cfg = load_agent_config(config_path)

        # Registry mode overlays the planner slot; loop bounds always come
        # from the agent config.
        self.profile_name: str | None = None
        registry = load_model_registry(registry_path)
        if registry.get("profiles"):
            prof = resolve_profile(registry, profile)
            self.profile_name = prof["name"]
            self.cfg["provider"] = prof.get("provider", self.cfg["provider"])
            self.cfg["model"] = prof.get("model", self.cfg["model"])
            self.cfg["base_url"] = prof.get("base_url") or self.cfg["base_url"]
            if "temperature" in prof:
                # null means: omit the parameter entirely (D-003)
                self.cfg["temperature"] = prof["temperature"]
            self._api_key_env = prof.get("api_key_env", "OPENAI_API_KEY")
        else:
            self._api_key_env = "OPENAI_API_KEY"

        # Uniform attribute view for status lines and tests.
        self.model = self.cfg["model"]
        self.base_url = self.cfg["base_url"]

        # Defer client construction when the key is absent: run() fails fast
        # with a clear summary instead of the SDK raising at construction.
        self._key_missing = client_factory is None and not os.environ.get(self._api_key_env)
        self._client: Any = None
        if client_factory is not None:
            self._client = client_factory()
        elif not self._key_missing:
            from openai import OpenAI

            self._client = OpenAI(
                api_key=os.environ[self._api_key_env],
                base_url=self.cfg["base_url"],
            )

    def model_label(self) -> str:
        """Human-readable 'profile (model)' for status lines and TTS summaries."""
        if self.profile_name:
            return f"{self.profile_name} ({self.model})"
        return self.model

    def run(self, goal: str, on_event: Callable[[dict], None] | None = None) -> dict:
        """Execute a full session: start → edit loop → validate → submit.

        Never raises; returns a result dict with ok/summary plus session state.
        """
        if self._key_missing:
            return {
                "ok": False,
                "summary": (
                    f"the {self._api_key_env} environment variable is not set, so the "
                    f"{self.model_label()} planner cannot run — add it to .env and restart"
                ),
                "session_started": False,
                "status": self.service.status(),
            }

        started = time.monotonic()
        if not self.service.branch:
            res = self.service.start_session(goal)
            if not res["ok"]:
                return {"ok": False, "summary": res["error"],
                        "status": self.service.status()}

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": goal},
        ]
        repairs_used = 0
        summary = "the agent reached its iteration limit without finishing"
        ok = False

        for _ in range(self.cfg["max_iterations"]):
            if time.monotonic() - started > self.cfg["max_session_minutes"] * 60:
                summary = "session time limit reached; no changes were submitted"
                break
            request: dict[str, Any] = {
                "model": self.cfg["model"],
                "messages": messages,
                "tools": TOOL_SPECS,
            }
            if self.cfg["temperature"] is not None:
                request["temperature"] = self.cfg["temperature"]
            response = self._client.chat.completions.create(**request)
            message = response.choices[0].message
            tool_calls = list(getattr(message, "tool_calls", None) or [])
            if not tool_calls:
                summary = message.content or ""
                ok = True
                break
            messages.append(_assistant_message(message))
            for tc in tool_calls:
                self._emit(on_event, {"type": "agent_tool", "tool": tc.function.name})
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = self._dispatch(tc.function.name, args)
                if tc.function.name == "session_validate" and not result.get("ok"):
                    repairs_used += 1
                    if repairs_used > 1:
                        result = {
                            "ok": False,
                            "error": "validation failed again after the single "
                                     "allowed repair attempt — stop and report "
                                     "the failure to the user",
                            "checks": result.get("checks"),
                        }
                        messages.append({
                            "role": "tool", "tool_call_id": tc.id,
                            "content": json.dumps(result),
                        })
                        summary = ("validation failed twice; session ended without "
                                   "submitting. " + json.dumps(result.get("checks")))
                        self._emit(on_event, {"type": "agent_done", "ok": False})
                        return {"ok": False, "summary": summary,
                                "status": self.service.status()}
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result)[:8000],
                })

        self._emit(on_event, {"type": "agent_done", "ok": ok})
        return {"ok": ok, "summary": summary, "status": self.service.status()}

    def _dispatch(self, name: str, args: dict) -> dict:
        """Closed toolset — unknown tools are refused outright."""
        if name == "file_read":
            return self.service.read_file(str(args.get("path", "")))
        if name == "edit_propose":
            return self.service.propose_edit(
                str(args.get("path", "")),
                str(args.get("new_content", "")),
                str(args.get("rationale", "")),
            )
        if name == "session_validate":
            return self.service.validate()
        if name == "session_submit":
            return self.service.submit()
        return {"ok": False, "error": f"unknown tool: {name}"}

    @staticmethod
    def _emit(on_event: Callable[[dict], None] | None, event: dict) -> None:
        if on_event is not None:
            try:
                on_event(event)
            except Exception:  # noqa: BLE001 — observers must not break agents
                logger.exception("on_event callback failed")


def _assistant_message(message: Any) -> dict:
    return {
        "role": "assistant",
        "content": message.content,
        "tool_calls": [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.function.name,
                             "arguments": tc.function.arguments},
            }
            for tc in message.tool_calls
        ],
    }
