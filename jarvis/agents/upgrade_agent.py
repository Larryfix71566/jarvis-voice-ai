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

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Callable

import yaml

from jarvis.repo_map import load_repo_map_suffix
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

When you decline, you MUST call session_decline with the reason. Do not
decline in prose alone.

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
    {
        "type": "function",
        "function": {
            "name": "session_decline",
            "description": "Decline the goal because it requires changes "
                           "outside the self-edit allowlist. Provide the "
                           "reason. Use this INSTEAD of replying in prose "
                           "that you cannot do it.",
            "parameters": {
                "type": "object",
                "properties": {"reason": {"type": "string"}},
                "required": ["reason"],
            },
        },
    },
]


def load_agent_config(path: str | Path | None = None, section: str | None = None) -> dict:
    """`section`, when given (D1/D7: e.g. "app_build"), overlays that
    subsection's `max_iterations`/`max_session_minutes` on top of the
    top-level provider/model/base_url/temperature defaults — those stay
    self-edit's legacy fallback values either way; the registry profile
    resolution in UpgradeAgent.__init__ overrides them for both workflows
    whenever config/upgrade_models.yaml has profiles, which it does. A
    missing section falls back to the top-level (self-edit) loop bounds,
    so an app_build section left unconfigured degrades gracefully rather
    than raising."""
    cfg_path = Path(path) if path else DEFAULT_CONFIG_PATH
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    bounds = data.get(section, {}) if section else data
    if not isinstance(bounds, dict):
        bounds = {}
    return {
        "provider": data.get("provider", "openai"),
        "model": os.environ.get("JARVIS_UPGRADE_MODEL")
                 or data.get("model", "gpt-4.1-mini"),
        "base_url": os.environ.get("JARVIS_UPGRADE_BASE_URL")
                    or data.get("base_url", "https://api.openai.com/v1"),
        "temperature": float(data.get("temperature", 0.2)),
        "max_iterations": int(bounds.get("max_iterations", data.get("max_iterations", 10))),
        "max_session_minutes": int(
            bounds.get("max_session_minutes", data.get("max_session_minutes", 30))
        ),
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
    """List planner profiles for pickers — includes key presence, never key material.

    `tier` (economy | mid | frontier | None) is surfaced here so the
    council module (jarvis/council/config.py) and the console's membership
    picker (MORTIMER_LLM_COUNCIL_PLAN.md D9) read it from this one place
    rather than re-parsing the registry YAML themselves.
    """
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
                "tier": prof.get("tier"),
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
        *,
        config_section: str | None = None,
        system_prompt: str | None = None,
        council_workflow: str = "selfedit",
    ):
        self.service = service
        self.cfg = load_agent_config(config_path, section=config_section)
        self._system_prompt = system_prompt or SYSTEM_PROMPT
        # G5 (MORTIMER_SESSION_GAPS_AND_SELFEDIT_CONVERGENCE_PLAN.md): the
        # developer-loop (SubAgent) has read docs/REPO_MAP.md into its
        # prompt since the Model Discipline plan; this loop — which does
        # most of the actual self-edit authoring — never did, so a self-
        # edit session rediscovered the codebase from scratch every run.
        # `load_repo_map_suffix` is the SAME shared helper SubAgent uses
        # (jarvis/repo_map.py) — one read/cap/skip implementation, not two.
        self._system_prompt += load_repo_map_suffix()
        # D7 — council rounds convened from this loop are tagged with the
        # workflow that started them ("selfedit" vs "appbuild"), so
        # compute_agreement (which excludes only workflow="planning") keeps
        # treating both as judge-quality evidence without special-casing.
        self._council_workflow = council_workflow

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

        # MORTIMER_LLM_COUNCIL_PLAN.md D2.1/D8.1 — escalation state. Reset
        # to a clean slate at the top of run() too, so a reused agent
        # instance starts clean (a fresh UpgradeAgent per session is the
        # normal case, but tests and any future pooling should not leak
        # escalation counters across sessions).
        self._escalations_used = 0
        self._pending_council_round_id: str | None = None
        # MORTIMER_LLM_COUNCIL_V2_PLAN.md V1 — the tier-1 winning proposal,
        # carried forward into a tier-2 convene as an additional candidate.
        # (profile, content); reset alongside the other escalation state.
        self._last_council_winner: tuple[str, str] | None = None
        # V14 — at most one scope-advisor council per run (E2); reset in
        # run(), same lifecycle as the escalation counters above.
        self._scope_council_used: bool = False

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

    def run(
        self, goal: str, on_event: Callable[[dict], None] | None = None,
        *, plan: str | None = None,
    ) -> dict:
        """Execute a full session: start → edit loop → validate → submit.

        Never raises; returns a result dict with ok/summary plus session state.

        `plan` (MORTIMER_PLANNING_PATHWAY_PLAN.md P7): an optional pre-
        written implementation plan — from the planning pathway's
        POST /api/plan/adopt or POST /api/selfedit/run's own `plan` param
        — injected as a system message right after the goal, before the
        edit loop's first completion call. Same injection SHAPE as the
        mid-run council escalation brief below (a system message wrapping
        the plan text), just at session start instead of after a failure.
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

        # D2.1 — a reused agent instance starts with a clean escalation slate.
        self._escalations_used = 0
        self._pending_council_round_id = None
        self._last_council_winner = None  # V1 — clean slate per session
        self._scope_council_used = False  # V14 — clean slate per session

        started = time.monotonic()
        if not self.service.branch:
            res = self.service.start_session(goal)
            if not res["ok"]:
                return {"ok": False, "summary": res["error"],
                        "status": self.service.status()}

        messages = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": goal},
        ]
        if plan:
            messages.append({
                "role": "system",
                "content": (
                    "A pre-written implementation plan for this goal "
                    "follows. Follow it.\n\n" + plan
                ),
            })
        repairs_used = 0
        summary = "the agent reached its iteration limit without finishing"
        ok = False

        # MORTIMER_LLM_COUNCIL_V2_PLAN.md V10 — the ONLY structural change
        # to this loop: a growable budget instead of a fixed range(), so a
        # tier-2 escalation late in a session can't win a council round and
        # then die on the iteration cap before the retry acts. The
        # wall-clock check inside the loop body is unchanged and stays the
        # absolute outer bound.
        iterations_used = 0
        iterations_budget = self.cfg["max_iterations"]
        # G6 (MORTIMER_SESSION_GAPS_AND_SELFEDIT_CONVERGENCE_PLAN.md):
        # halfway through the ORIGINAL budget (not a council-extended one —
        # this checkpoint is about the session's initial allotment, not a
        # moving target), if zero edits have been proposed yet, force a
        # convergence nudge. Two live self-edit runs (the independent-
        # display-windows build and the model-card fix) died at the cap
        # having produced ZERO edit_propose calls — the whole budget spent
        # reading/orienting. Equality (not >=) makes this fire exactly
        # once: iterations_used only increases, and a later council-retry
        # budget extension can't push it back to this value.
        halfway_checkpoint = self.cfg["max_iterations"] // 2
        while iterations_used < iterations_budget:
            iterations_used += 1
            if iterations_used == halfway_checkpoint and not self.service.proposals:
                messages.append({
                    "role": "system",
                    "content": (
                        "You are halfway through this session's iteration budget "
                        "and have not proposed a single edit yet. Stop reading "
                        "further files unless strictly necessary — call "
                        "edit_propose now with a concrete change, even a partial "
                        "one, so the remaining iterations can refine it instead "
                        "of being spent entirely on exploration."
                    ),
                })
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
                if tc.function.name == "session_decline" and result.get("declined"):
                    reason = result.get("reason", "")
                    messages.append({
                        "role": "tool", "tool_call_id": tc.id,
                        "content": json.dumps(result),
                    })
                    # MORTIMER_LLM_COUNCIL_V2_PLAN.md V14 — E2: at most one
                    # scope-advisor council per run (by counter, not
                    # judgment). Advisory only: the brief rides in
                    # `summary`; the session still ends declined either way.
                    scope_brief = None
                    if not self._scope_council_used:
                        self._scope_council_used = True
                        try:
                            allowlist_text = self.service.describe_boundary()
                        except Exception:  # noqa: BLE001 — best-effort context
                            allowlist_text = "(allowlist file unavailable)"
                        scope_brief = self._maybe_scope_council(
                            goal=goal, reason=reason, allowlist=allowlist_text,
                        )
                    if scope_brief:
                        reason = reason + "\n\n[Council scope advice]\n" + scope_brief
                    self._emit(on_event, {"type": "agent_done", "ok": False,
                                          "declined": True})
                    return {"ok": False, "declined": True, "summary": reason,
                            "status": self.service.status()}
                if tc.function.name == "session_validate":
                    # D8.1 — the FIRST validate result after an escalation
                    # is what "did the retry validate" means; recorded
                    # once, then cleared, regardless of ok/fail, so a
                    # later un-escalated validate in the same retry's own
                    # one-repair budget doesn't overwrite it.
                    if self._pending_council_round_id is not None:
                        round_id = self._pending_council_round_id
                        self._pending_council_round_id = None
                        try:
                            from jarvis.council.council import record_retry_validated
                            record_retry_validated(round_id, bool(result.get("ok")))
                        except Exception:  # noqa: BLE001 — never break the agent loop
                            logger.warning(
                                "council_record_retry_validated_call_failed "
                                "round_id=%s", round_id, exc_info=True,
                            )
                if tc.function.name == "session_validate" and not result.get("ok"):
                    repairs_used += 1
                    if repairs_used > 1:
                        council_brief = self._maybe_escalate(
                            goal=goal, trigger="E1",
                            context={"diff": self.service.proposals,
                                     "checks": result.get("checks")},
                        )
                        if council_brief is None:
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
                            "role": "tool", "tool_call_id": tc.id,
                            "content": json.dumps(result),
                        })
                        # Correction to the plan's literal D2.1 snippet: the
                        # inner `for tc in tool_calls` loop is nested inside
                        # the outer iteration-budget `while` loop (V10), so
                        # a bare `continue` here would only advance to the
                        # NEXT tool_call in this same batch, not resume the
                        # outer loop as the plan's own prose says it should.
                        # `break` is what actually resumes the outer loop,
                        # since the inner loop is the last statement in the
                        # outer loop's body. Any tool_calls in this batch
                        # that were never reached still need a tool-role
                        # response before the next completion() call, or the
                        # API rejects the next request — so they get an
                        # explicit "skipped" result rather than being
                        # silently dropped from `messages`.
                        for remaining_tc in tool_calls[tool_calls.index(tc) + 1:]:
                            messages.append({
                                "role": "tool", "tool_call_id": remaining_tc.id,
                                "content": json.dumps({
                                    "ok": False,
                                    "error": "skipped — a council escalation "
                                             "started before this tool call "
                                             "was processed",
                                }),
                            })
                        # Retry once with the council's winning approach as
                        # added context.
                        messages.append({
                            "role": "system",
                            "content": (
                                "A council of models reviewed this failure. Their "
                                "highest-scored corrected approach follows. Follow it, then "
                                "validate again.\n\n" + council_brief
                            ),
                        })
                        repairs_used = 0          # the retry gets its own repair budget
                        # V10 — grant extra iterations so this council-
                        # guided retry isn't starved by budget the failed
                        # attempts already spent. Lazy import: same
                        # circular-import rationale as _maybe_escalate's.
                        from jarvis.council.config import COUNCIL_RETRY_EXTRA_ITERATIONS
                        iterations_budget += COUNCIL_RETRY_EXTRA_ITERATIONS
                        break                     # resume the outer `while` loop
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result)[:8000],
                })

        # G6 — name the REAL cause of a natural iteration-budget exhaustion
        # when it happened with zero edit proposals: not a failed edit, a
        # session that never got to a first one. Only reachable when the
        # loop exited by exhausting `iterations_budget` (the time-limit and
        # validation-failure paths already set/return their own summary).
        if (
            not ok
            and summary == "the agent reached its iteration limit without finishing"
            and not self.service.proposals
        ):
            summary = (
                "the session never converged on a first edit within its "
                "iteration budget — every iteration was spent reading and "
                "orienting, not failing on a bad edit; a plan_path or named "
                "files would likely narrow this"
            )

        self._emit(on_event, {"type": "agent_done", "ok": ok})
        return {"ok": ok, "summary": summary, "status": self.service.status()}

    def _maybe_escalate(self, *, goal: str, trigger: str,
                        context: dict) -> str | None:
        """MORTIMER_LLM_COUNCIL_PLAN.md D2.1. Returns the winning
        proposal's content, or None to fall through to the ordinary
        failure path. Never raises (D13).

        Lazy imports: jarvis.council.council and jarvis.council.config
        both import jarvis.agents.upgrade_agent at module level (for
        load_model_registry/available_models), so importing them here —
        inside the method, not at module load time — avoids a circular
        import.
        """
        from jarvis.council.config import COUNCIL_MAX_ESCALATIONS

        if self._escalations_used >= COUNCIL_MAX_ESCALATIONS:
            return None
        tier = self._escalations_used + 1          # 1st -> tier 1, 2nd -> tier 2
        self._escalations_used += 1
        # MORTIMER_LLM_COUNCIL_V2_PLAN.md V1 — carry the previous tier's
        # winning proposal into tier >= 2 as an additional candidate.
        if tier >= 2 and self._last_council_winner is not None:
            context = dict(context)
            context["carry_forward"] = {
                "profile": self._last_council_winner[0],
                "content": self._last_council_winner[1],
            }
        try:
            from jarvis.council.council import convene
            result = asyncio.run(convene(
                workflow=self._council_workflow, placement="planner", trigger=trigger,
                goal=goal, tier=tier, context=context,
            ))
        except Exception:                           # noqa: BLE001
            logger.warning("council_escalation_failed", exc_info=True)
            return None
        if result is None or result.winner is None:
            return None
        # V1 — remembered immediately, before the existing
        # _pending_council_round_id write-back, so a subsequent tier-2
        # escalation in the same session carries this round's winner.
        self._last_council_winner = (result.winner.profile, result.winner.content)
        # D8.1 — remembered so the NEXT session_validate result (the
        # retry this brief produces) can be written back as
        # retry_validated.
        self._pending_council_round_id = result.round_id
        return result.winner.content

    def _maybe_scope_council(self, *, goal: str, reason: str,
                             allowlist: str) -> str | None:
        """MORTIMER_LLM_COUNCIL_V2_PLAN.md V14 — E2. Shaped exactly like
        `_maybe_escalate` (lazy imports, `asyncio.run`, catches
        everything, returns `result.winner.content` or `None`), but for
        the scope-advisor prompt pair: `placement='scope'`, always tier
        1 (there is no "second failure" concept for a decline), and does
        NOT touch `_escalations_used` — the escalation ladder is for E1
        only. Advisory only: the caller decides what to do with the
        returned brief; nothing here executes it."""
        try:
            from jarvis.council.council import convene
            result = asyncio.run(convene(
                workflow=self._council_workflow, placement="scope", trigger="E2",
                goal=goal, tier=1,
                context={"reason": reason, "allowlist": allowlist},
            ))
        except Exception:                           # noqa: BLE001
            logger.warning("council_scope_council_failed", exc_info=True)
            return None
        if result is None or result.winner is None:
            return None
        return result.winner.content

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
        if name == "session_decline":
            return {"ok": False, "declined": True,
                    "reason": str(args.get("reason", ""))}
        return {"ok": False, "error": f"unknown tool: {name}"}

    @staticmethod
    def _emit(on_event: Callable[[dict], None] | None, event: dict) -> None:
        if on_event is not None:
            try:
                on_event(event)
            except Exception:  # noqa: BLE001 — observers must not break agents
                logger.exception("on_event callback failed")


APPBUILD_PROFILE_ENV = "JARVIS_APPBUILD_PROFILE"

APP_BUILD_SYSTEM_PROMPT = """You are the Mortimer App-Build Agent. You develop
applications by proposing code edits inside the app's OWN private GitHub
repository, under these NON-NEGOTIABLE rules:

1. The app's default branch changes only via a human merging a pull request
   on GitHub. You can only open PRs. You can never merge, force-push, or
   touch the default branch directly.
2. You may edit any file in the app's repo EXCEPT .git/**, .env and .env.*,
   any *.vault file, and .github/workflows/** — you must never grant
   yourself CI powers on the app repo. If the goal requires touching one of
   those, decline that part and say it requires human development.
3. Your only tools are file_read, edit_propose, session_validate,
   session_submit. There is no shell and no git tool.
4. Propose edits with edit_propose, then call session_validate, and only if
   every check passes call session_submit. If validation fails you get ONE
   repair attempt; if it fails again, stop and report the failure. If the
   app has no mortimer.app.yaml validation manifest, session_validate will
   say so explicitly — treat that PR as UNVALIDATED in your summary, never
   as passing.
5. Keep edits small, self-contained, and explained by a one-line rationale.

When you decline, you MUST call session_decline with the reason. Do not
decline in prose alone.

Work style: first read the files relevant to the goal, then propose complete
new file contents for each file you change, then validate, then submit.
Reply to the user with a concise summary of what you changed (or why you
declined), in plain language."""


class AppBuildAgent(UpgradeAgent):
    """D1/D7: the SAME edit loop as UpgradeAgent, bound to an AppWorkspace
    instead of a SelfEditWorkspace — a foreign app repo instead of
    Mortimer's own. Three differences from the base class, all supplied
    via UpgradeAgent's existing constructor parameters (no loop code is
    duplicated): the app-build system prompt, the `app_build:` loop-bound
    section of config/upgrade_agent.yaml (own max_iterations/
    max_session_minutes — app builds legitimately run longer than
    self-edits), and JARVIS_APPBUILD_PROFILE as the env-level profile
    fallback (independent of self-edit's JARVIS_UPGRADE_PROFILE, so the
    two workflows can be pointed at different planner tiers). Council
    escalation rounds this agent convenes are tagged
    workflow="appbuild" (D7) via the base class's `council_workflow` param."""

    def __init__(
        self,
        workspace: Any,
        config_path: str | Path | None = None,
        registry_path: str | os.PathLike[str] | None = None,
        profile: str | None = None,
        client_factory: Callable[[], Any] | None = None,
    ):
        # Selection order mirrors resolve_profile's own: explicit >
        # env > registry default. resolve_profile only checks
        # JARVIS_UPGRADE_PROFILE, so the app-build env fallback is applied
        # here, before the base class ever calls it.
        profile = profile or os.environ.get(APPBUILD_PROFILE_ENV)
        super().__init__(
            workspace, config_path=config_path, registry_path=registry_path,
            profile=profile, client_factory=client_factory,
            config_section="app_build", system_prompt=APP_BUILD_SYSTEM_PROMPT,
            council_workflow="appbuild",
        )


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
