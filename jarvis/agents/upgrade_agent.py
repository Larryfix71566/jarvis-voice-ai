"""LLM brain of the self-development loop.

The upgrade agent plans edits to Mortimer's own codebase. It never touches
git directly: it works through a closed toolset exposed by
:class:`jarvis.selfedit.service.SelfEditService` (file_read, edit_propose,
session_validate, session_submit) and the service alone owns the sandboxed
branch, validation, and PR creation.

Planner model
-------------
Which model does the planning is chosen from the registry in
``config/upgrade_models.yaml`` (override path via ``JARVIS_UPGRADE_MODELS``).
Selection order: an explicit per-session ``profile`` argument >
``JARVIS_UPGRADE_PROFILE`` env > the registry's ``default`` key. Profiles are
OpenAI-compatible endpoints; API keys come only from the environment
(``api_key_env``). ``temperature: null`` in a profile means the parameter is
omitted from requests entirely (D-003: kimi-k2.x rejects any value != 1).

If no registry file exists, the agent falls back to the legacy single-slot
config in ``config/upgrade_agent.yaml`` (``model``/``base_url``/``api_key_env``)
— byte-identical behavior to before the registry existed.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Callable

import yaml

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "upgrade_agent.yaml"
DEFAULT_REGISTRY_PATH = Path(__file__).resolve().parents[2] / "config" / "upgrade_models.yaml"
REGISTRY_PATH_ENV = "JARVIS_UPGRADE_MODELS"
PROFILE_ENV = "JARVIS_UPGRADE_PROFILE"

PLANNER_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "file_read",
            "description": "Read a repository file (allowlisted paths only).",
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
            "description": (
                "Propose a full-file replacement for one allowlisted path. "
                "The edit is staged in the sandbox session; nothing is committed "
                "until validation passes and the user confirms submission."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                    "rationale": {"type": "string"},
                },
                "required": ["path", "content", "rationale"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "session_validate",
            "description": (
                "Run the validation pipeline (allowlist, backend imports, "
                "frontend build) against the staged proposals."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "session_submit",
            "description": (
                "Open a pull request with the validated proposals. Call this ONLY "
                "after validation has passed and the caller has explicitly asked "
                "for submission. The PR is never merged by the agent."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

SYSTEM_PROMPT = """You are Mortimer's upgrade planner. You improve Mortimer's own \
codebase exactly as the goal describes — no more, no less.

Rules:
- Read before you write. Never propose an edit to a file you have not read.
- Stay inside the goal's scope. Drive-by refactors are rejected.
- Every edit_propose call needs a one-sentence rationale.
- When the goal is satisfied, call session_validate, then stop and report.
- Call session_submit ONLY if the goal explicitly says to submit.
- You cannot merge, force-push, or touch main. Ever.
"""


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
    data = yaml.safe_load(p.read_text()) or {}
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
    """Closed-toolset planner for self-development edits."""

    def __init__(
        self,
        service: Any,
        config_path: str | os.PathLike[str] | None = None,
        registry_path: str | os.PathLike[str] | None = None,
        profile: str | None = None,
        client_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.service = service
        cfg = yaml.safe_load(Path(config_path or DEFAULT_CONFIG_PATH).read_text()) or {}
        self.max_iterations = int(cfg.get("max_iterations", 10))
        self.max_minutes = float(cfg.get("max_minutes", 30))

        registry = load_model_registry(registry_path)
        self.profile_name: str | None = None
        if registry.get("profiles"):
            prof = resolve_profile(registry, profile)
            self.profile_name = prof["name"]
            self._profile_label = prof.get("label", prof["name"])
            self.model = prof.get("model", "")
            self.base_url = prof.get("base_url") or None
            self.temperature = prof.get("temperature", None)
            self._api_key_env = prof.get("api_key_env", "OPENAI_API_KEY")
        else:
            # Legacy single-slot config (pre-registry behavior).
            self.model = cfg.get("model", "gpt-4.1-mini")
            self.base_url = cfg.get("base_url") or None
            self.temperature = cfg.get("temperature", 0.2)
            self._api_key_env = cfg.get("api_key_env", "OPENAI_API_KEY")

        # Defer client construction when the key is absent: run() fails fast
        # with a clear summary instead of the SDK raising at import time.
        self._key_missing = client_factory is None and not os.environ.get(self._api_key_env)
        self._client: Any = None
        if client_factory is not None:
            self._client = client_factory()
        elif not self._key_missing:
            from openai import OpenAI

            self._client = OpenAI(
                api_key=os.environ[self._api_key_env], base_url=self.base_url
            )

    def model_label(self) -> str:
        """Human-readable 'profile (model)' for status lines and TTS summaries."""
        if self.profile_name:
            return f"{self.profile_name} ({self.model})"
        return self.model

    def run(self, goal: str) -> dict[str, Any]:
        """Plan and stage edits for ``goal``. Returns a summary dict."""
        if self._key_missing:
            return {
                "ok": False,
                "summary": (
                    f"the {self._api_key_env} environment variable is not set, so the "
                    f"{self.model_label()} planner cannot run — add it to .env and restart"
                ),
                "session_started": False,
                "iterations": 0,
            }

        session = self.service.start_session(goal)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Goal: {goal}"},
        ]
        started = time.monotonic()
        iterations = 0
        submitted = False

        while iterations < self.max_iterations:
            if (time.monotonic() - started) > self.max_minutes * 60:
                break
            iterations += 1

            request: dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "tools": PLANNER_TOOLS,
                "tool_choice": "auto",
            }
            if self.temperature is not None:
                request["temperature"] = self.temperature
            resp = self._client.chat.completions.create(**request)
            msg = resp.choices[0].message
            messages.append(msg.model_dump(exclude_none=True))

            tool_calls = getattr(msg, "tool_calls", None) or []
            if not tool_calls:
                break
            for call in tool_calls:
                name = call.function.name
                args = json.loads(call.function.arguments or "{}")
                result = self._dispatch(name, args)
                if name == "session_submit" and result.get("ok"):
                    submitted = True
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(result),
                    }
                )

        status = self.service.status()
        proposals = status.get("proposals", [])
        summary_parts = [
            f"{iterations} planning iterations with {self.model_label()}",
            f"{len(proposals)} file edit(s) proposed",
        ]
        if status.get("validated_ok"):
            summary_parts.append("validation passed")
        if submitted:
            summary_parts.append(f"PR opened: {status.get('pr_url', '')}".rstrip())
        return {
            "ok": True,
            "summary": ", ".join(summary_parts),
            "session_started": True,
            "iterations": iterations,
            "submitted": submitted,
            "status": status,
        }

    def _dispatch(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        try:
            if name == "file_read":
                return self.service.file_read(args["path"])
            if name == "edit_propose":
                return self.service.propose_edit(
                    args["path"], args["content"], args.get("rationale", "")
                )
            if name == "session_validate":
                return self.service.validate()
            if name == "session_submit":
                return self.service.submit()
            return {"ok": False, "error": f"unknown tool {name!r}"}
        except Exception as exc:  # surface tool failures to the planner, never crash
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
