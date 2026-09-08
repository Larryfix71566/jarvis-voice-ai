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
import threading
import time
from pathlib import Path
from typing import Any, Callable

import yaml

from jarvis import effort, llm_client
from jarvis.repo_map import load_repo_map_suffix
from jarvis.selfedit.service import SelfEditService
from jarvis.usage_ledger import record_completion, provider_from_base_url

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "upgrade_agent.yaml"
)
DEFAULT_REGISTRY_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "upgrade_models.yaml"
)
REGISTRY_PATH_ENV = "JARVIS_UPGRADE_MODELS"
PROFILE_ENV = "JARVIS_UPGRADE_PROFILE"

# Planner call bounds + model failover (Larry 2026-08-22: "if we are going
# to choose a model that ends up unreachable then we need a way to kill the
# request so that it can be delegated to another model — spin on a dead
# model is not a great look").
#
# 120s matches COUNCIL_MEMBER_TIMEOUT_S deliberately: the council already
# solved this exact problem (bound the call, drop the member, keep going)
# and one number is better than two that drift. Calibration note from the
# same day: a measured kimi-k3 planner call took 112.2s for a two-sentence
# answer (always-on thinking, 1,369 completion tokens), so kimi-k3 sits
# just inside this bound and WILL trip it under any additional load. That
# is the correct outcome, not a mis-set threshold — a planner that needs
# ~2 minutes per round cannot finish a 25-round session inside
# max_session_minutes anyway, so failing over is strictly better than
# spinning.
PLANNER_CALL_TIMEOUT_S = 120.0

# At most two failovers per session: three distinct models failing
# unreachably is an outage, not a bad pick, and continuing to shop makes
# the user wait longer for the same bad news.
MAX_PLANNER_FAILOVERS = 2

SYSTEM_PROMPT = """You are the Jarvis Upgrade Agent. You develop upgrades to the
Jarvis interface by proposing code edits, under these NON-NEGOTIABLE rules:

1. `main` changes only via a human merging a pull request on GitHub. You can
   only open PRs. You can never merge, force-push, or touch main.
2. You may only read and edit files on the self-edit allowlist. Routine
   (Tier A): UI sources under web/src and web/public, non-secret config,
   jarvis/prompts.py, jarvis/skills, jarvis/services, mcp_servers, tests,
   docs. Core (Tier B): the rest of jarvis/ — the voice pipeline
   (jarvis/bot), the agents (jarvis/agents), memory, wake word, scripts —
   is EDITABLE too, with ceremony: a core edit runs an extra import gate
   and its PR is flagged CORE CHANGE for a human run before merge. Do not
   decline a core goal because it is "not UI" — do it, carefully, in
   small self-contained edits. Human-only (Tier 0), decline that part:
   the self-edit machinery itself (jarvis/selfedit, jarvis/admin,
   upgrade_agent.py), the allowlist and model registry, jarvis/db.py
   migrations, the vault and .env, CI, dependency manifests, macos/.
   A file_read/edit_propose on a Tier-0 path is refused by the tool — if
   that happens, decline that part with the path named.
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

# MORTIMER_OPTIMIZATION_PLAN.md Phase 3 — "the executor's escalation rule
# is load-bearing." Injected by run() only alongside a supplied `plan`
# (P7's plan-adoption kwarg): the invariant a plan gives the executor is
# NOT "this spec is complete" (no spec is) — it is that every
# irreversible or architectural decision already got made IN the plan.
# When what the executor actually finds diverges from what the plan
# describes, the correct move is to stop and report the divergence, not
# bridge the gap with its own architectural judgment — that decision
# belongs in a plan revision (a human, or the planning pathway), not a
# silent edit. An unplanned single-file self-edit has no spec to diverge
# from, so this text is meaningless noise there and stays out.
PLAN_DIVERGENCE_RULE = (
    "A pre-written plan may not perfectly match what you actually find in "
    "the repository. That is expected. What is NOT allowed is bridging a "
    "real divergence yourself: if the plan's design assumptions do not "
    "hold, or an irreversible/architectural decision the plan should have "
    "made was left for you, stop and report the divergence in your "
    "summary instead of deciding it on your own. The plan is where "
    "architectural decisions live; your job is executing it, not "
    "revising it."
)

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
            "description": "Run the validation gates (allowlist, backend "
                           "imports, core imports for a core change, "
                           "pytest).",
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
        run_id: str | None = None,
    ):
        self.service = service
        # MORTIMER_GRAPH_LAYER_PLAN.md GL9 (contract G2): the delegating sub-agent
        # run, threaded from SkillRegistry.call() through the sidecar; None for a
        # console-initiated run. Every convene() below passes it through.
        self._run_id = run_id
        self.cfg = load_agent_config(config_path, section=config_section)
        self._system_prompt = system_prompt or SYSTEM_PROMPT
        # Cooperative cancel (Larry 2026-08-30/31: a kimi-k3 planner sat
        # "still running" for the caption goal and nothing could stop it —
        # selfedit_revert refuses while busy, and there was no cancel at
        # all). POST /api/selfedit/cancel sets this; the edit loop checks
        # it before every planner step. It cannot interrupt a completion
        # call already in flight (that returns or hits its own read
        # timeout first), so "cancel" means "stop at the next step".
        self._cancel = threading.Event()
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
        # Kept so _next_failover_profile resolves against the SAME registry
        # this agent was constructed from (tests point it elsewhere).
        self._registry_path = registry_path
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
            # Phase 1b (effort control) -- optional per-profile
            # output_config.effort override (upgrade_models.yaml); absent
            # means self.cfg.get("effort") stays None, and
            # extra_body_for() emits nothing, exactly like an agents.yaml
            # entry with no `effort:` field.
            if "effort" in prof:
                self.cfg["effort"] = prof["effort"]
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
        # Phase 3 Rev 3.3 — 'planned' | 'planless' for this session's
        # ledger rows (usage_ledger.record_call's plan_state); set at the
        # top of run() from whether a `plan` was supplied.
        self._plan_state: str | None = None
        self._submit_result: dict | None = None

        # Defer client construction when the key is absent: run() fails fast
        # with a clear summary instead of the SDK raising at construction.
        self._key_missing = client_factory is None and not os.environ.get(self._api_key_env)
        # Failover state (Larry 2026-08-22: "spin on a dead model is not a
        # great look"). Profiles that have already failed UNREACHABLY this
        # session are never selected again by _completion_with_failover.
        self._failed_profiles: set[str] = set()
        self._failover_notes: list[str] = []

        self._client: Any = None
        if client_factory is not None:
            self._client = client_factory()
        elif not self._key_missing:
            self._client = self._build_client(
                self._api_key_env, self.cfg["base_url"], self.cfg.get("provider"))

    def _build_client(self, api_key_env: str, base_url: str | None,
                      provider: str | None = None) -> Any:
        """Construct the planner client with a BOUNDED call timeout.

        Before 2026-08-22 this passed no `timeout`, so the openai SDK's
        default applied: a 600-second read timeout. `max_session_minutes`
        could not save it — that bound is checked BETWEEN iterations, and a
        hung call blocks inside the HTTP read where the loop never regains
        control. One unreachable kimi-k3 call therefore spun for up to ten
        minutes. `max_retries=0` is deliberate and load-bearing: the SDK's
        default of 2 would silently turn a 120s bound into a 360s one, and
        retrying a model that just proved unreachable is strictly worse
        than failing over to one that answers.

        `provider` (MORTIMER_OPTIMIZATION_PLAN.md Phase 1, Rev 3.2, landing
        step (ii), 2026-09-02): optional so every existing caller and test
        that only ever passed two positional args keeps working — falls
        back to base_url-detection inside llm_client.make_sync_client
        itself when omitted. Routes to jarvis/anthropic_shim.py (prompt
        caching) instead of the plain OpenAI-compat client when the
        resolved provider is "anthropic" and JARVIS_ANTHROPIC_NATIVE is
        not "0".
        """
        return llm_client.make_sync_client(
            api_key=os.environ[api_key_env],
            base_url=base_url,
            provider=provider,
            timeout=PLANNER_CALL_TIMEOUT_S,
            max_retries=0,
        )

    def model_label(self) -> str:
        """Human-readable 'profile (model)' for status lines and TTS summaries."""
        if self.profile_name:
            return f"{self.profile_name} ({self.model})"
        return self.model

    @staticmethod
    def _is_unreachable(exc: Exception) -> bool:
        """Is this failure the UNREACHABLE class, i.e. worth failing over?

        Deliberately narrow, mirroring `jarvis/keyhealth.py`'s three-verdict
        discipline (rejected / unfunded / unreachable): only a timeout, a
        connection failure, or a 5xx means "this endpoint isn't answering,
        try another one." A 4xx is a REAL error that would repeat
        identically on every profile — and worse, failing over on 4xx would
        MASK it. That is not hypothetical: on 2026-08-22 `claude-opus` sent
        a `temperature` the model rejects, 400ing every self-edit in ~38ms;
        had failover been triggered by 4xx, it would have burned through
        every profile in the registry and reported an outage instead of the
        one-line config bug it actually was.
        """
        from openai import APIConnectionError, APIStatusError, APITimeoutError

        if isinstance(exc, (APITimeoutError, APIConnectionError)):
            return True
        if isinstance(exc, APIStatusError):
            return getattr(exc, "status_code", 0) >= 500
        return False

    def _next_failover_profile(self) -> dict[str, Any] | None:
        """The next key-present registry profile that has not failed yet.

        Registry order, skipping the current profile, anything already
        failed this session, and anything whose key is absent. Returns the
        resolved profile dict, or None when nothing is left to try.
        """
        try:
            registry = load_model_registry(self._registry_path)
        except Exception:  # noqa: BLE001 — failover must never itself raise
            return None
        for entry in available_models(self._registry_path):
            name = entry["name"]
            if name == self.profile_name or name in self._failed_profiles:
                continue
            if not entry.get("key_present"):
                continue
            try:
                return resolve_profile(registry, name)
            except Exception:  # noqa: BLE001 — try the next candidate
                continue
        return None

    def _completion(self, request: dict[str, Any]) -> Any:
        """One completion call, bounded and failover-capable.

        On an UNREACHABLE-class failure the current profile is retired for
        this session and the next key-present profile takes over mid-run —
        the conversation so far (`request["messages"]`) carries across
        unchanged, so the new model resumes rather than restarting.

        Larry chose announce-then-failover (2026-08-22) over ask-first even
        for an explicitly NAMED model. That is a deliberate, recorded
        narrowing of the F6-F9 rule ("an explicit request always REFUSES
        rather than silently falling back"): F6-F9 governs RESOLUTION
        failure — an unknown profile or missing key, knowable BEFORE any
        work starts — whereas this is a runtime timeout on a model that
        resolved fine and may have already done half the session. The
        no-silent-substitution half of that rule is preserved by
        `_failover_notes`, which the run summary appends mechanically, so
        Mortimer can never report work as done by a model that did not do
        it.
        """
        attempts = 0
        while True:
            # Phase 1b -- recomputed on EVERY iteration, not just once
            # before the loop: unlike SubAgent._loop (client/model fixed
            # for the whole run), a failover below can reassign
            # self._client mid-loop, and output_config.effort must track
            # whatever profile actually ends up making the request.
            # `request` itself is never mutated with this -- an ephemeral
            # copy per attempt, so a failover onto a non-Anthropic profile
            # drops it cleanly rather than leaving a stale key behind.
            # getattr(..., "") rather than a bare attribute access: the
            # record_completion call below already tolerated a test double
            # with no .base_url (it sat inside a bare try/except Exception
            # before this Phase 1b change moved the access earlier) -- a
            # fake client missing base_url now resolves to
            # provider="unknown" (never "anthropic"), so extra_body_for()
            # cleanly returns {} instead of the whole call raising.
            provider = provider_from_base_url(str(getattr(self._client, "base_url", "")))
            extra_body = effort.extra_body_for(
                rung=f"{self._council_workflow}_executor", provider=provider,
                explicit=self.cfg.get("effort"), model=self.model,
            )
            call_request = {**request, "extra_body": extra_body} if extra_body else request
            try:
                response = self._client.chat.completions.create(**call_request)
                try:
                    record_completion(
                        rung=f"{self._council_workflow}_executor",
                        provider=provider,
                        model=self.model,
                        response=response,
                        plan_state=self._plan_state,
                    )
                except Exception:
                    pass
                return response
            except Exception as exc:  # noqa: BLE001 — classified immediately below
                if not self._is_unreachable(exc) or attempts >= MAX_PLANNER_FAILOVERS:
                    raise
                failed_name = self.profile_name or self.model
                self._failed_profiles.add(failed_name)
                nxt = self._next_failover_profile()
                if nxt is None:
                    logger.warning(
                        "planner_failover_exhausted failed=%s error=%s",
                        failed_name, type(exc).__name__,
                    )
                    raise
                note = (
                    f"{failed_name} did not respond "
                    f"({type(exc).__name__}); continued on {nxt['name']}"
                )
                logger.warning("planner_failover from=%s to=%s error=%s",
                               failed_name, nxt["name"], type(exc).__name__)
                self._failover_notes.append(note)

                self.profile_name = nxt["name"]
                self.cfg["model"] = nxt.get("model", self.cfg["model"])
                self.cfg["base_url"] = nxt.get("base_url") or self.cfg["base_url"]
                self.cfg["temperature"] = nxt.get("temperature")
                # Phase 1 Rev 3.2 fix (2026-09-02): this line's four
                # siblings above already refresh from `nxt` on every
                # failover; `provider` was the one field nothing consumed
                # until now, so it went stale silently. A native-vs-compat
                # client-construction decision now reads it, and a
                # failover FROM an Anthropic profile TO a differently-
                # provided one (or vice versa) must not build the wrong
                # kind of client on the new profile's base_url.
                self.cfg["provider"] = nxt.get("provider", self.cfg["provider"])
                # Phase 1b -- mirrors the provider refresh immediately
                # above: a failover profile's own effort setting (or its
                # absence) must replace the old profile's, not linger.
                if "effort" in nxt:
                    self.cfg["effort"] = nxt["effort"]
                self._api_key_env = nxt.get("api_key_env", "OPENAI_API_KEY")
                self.model = self.cfg["model"]
                self.base_url = self.cfg["base_url"]
                self._client = self._build_client(
                    self._api_key_env, self.cfg["base_url"], self.cfg.get("provider"))

                # The retry must carry the NEW model and its temperature
                # rule (D-003), not the dead profile's.
                request["model"] = self.cfg["model"]
                request.pop("temperature", None)
                if self.cfg["temperature"] is not None:
                    request["temperature"] = self.cfg["temperature"]
                attempts += 1

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
        PLAN_DIVERGENCE_RULE (Phase 3) rides in the same message, ahead
        of the plan text — see that constant's comment.
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
        self._failed_profiles = set()     # failover — clean slate per session
        self._failover_notes = []
        self._plan_state = "planned" if plan else "planless"  # Rev 3.3 ledger tag
        # 2026-09-07 (review F6): a run "ended" is not a run "submitted".
        # The loop's `ok` means the planner stopped cleanly — including by
        # writing prose after a failed validation. What the user needs to
        # hear is whether a pull request exists, so the submit result is
        # recorded here mechanically (never from the planner's prose) and
        # returned alongside `ok`.
        self._submit_result: dict | None = None

        started = time.monotonic()
        if not self.service.branch:
            # SE8 — the planner path carries the same run_id the developer
            # path does, so a session opened here is joinable to its
            # delegating run without a timestamp join.
            res = self.service.start_session(goal, run_id=self._run_id)
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
                    PLAN_DIVERGENCE_RULE + "\n\n"
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
        cancelled = False
        # Phase 3 Rev 3.3 — why the loop stopped, for _close_pending_round
        # (only consulted when a council brief was injected and its retry
        # never reached session_validate). Falls through as
        # "iteration_limit" when the `while` condition itself ends the loop.
        end_reason = "iteration_limit"
        while iterations_used < iterations_budget:
            if self._cancel.is_set():
                cancelled = True
                end_reason = "cancelled"
                summary = ("cancelled by the user before the next planner step; "
                           "no changes were submitted")
                break
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
                end_reason = "time_limit"
                summary = "session time limit reached; no changes were submitted"
                break
            request: dict[str, Any] = {
                "model": self.cfg["model"],
                "messages": messages,
                "tools": TOOL_SPECS,
            }
            if self.cfg["temperature"] is not None:
                request["temperature"] = self.cfg["temperature"]
            response = self._completion(request)
            message = response.choices[0].message
            tool_calls = list(getattr(message, "tool_calls", None) or [])
            if not tool_calls:
                summary = message.content or ""
                ok = True
                end_reason = "prose_end"
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
                    self._close_pending_round("declined")
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
                            self._close_pending_round("unfinished")
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

        # Failover disclosure — a MECHANICAL backstop, not a prompt
        # instruction, mirroring the `[ran on <model>]` suffix delegate.py
        # appends: grounded by construction, so Mortimer can never report
        # work as done by a model that did not do it. This is what keeps
        # announce-then-failover honest for an explicitly NAMED model.
        if self._failover_notes:
            summary = (summary or "") + " [" + "; ".join(self._failover_notes) + "]"

        self._close_pending_round(end_reason)
        self._emit(on_event, {"type": "agent_done", "ok": ok})
        return {
            "ok": ok, "summary": summary, "status": self.service.status(),
            "failovers": list(self._failover_notes),
            "final_profile": self.profile_name,
            "cancelled": cancelled,
            "submitted": self._submit_result is not None,
            "pr_url": (self._submit_result or {}).get("pr_url"),
        }

    def request_cancel(self) -> None:
        """Ask the running edit loop to stop at its next step (see
        __init__). Safe to call from any thread; idempotent."""
        self._cancel.set()

    @property
    def cancel_requested(self) -> bool:
        return self._cancel.is_set()

    def _close_pending_round(self, reason: str) -> None:
        """MORTIMER_OPTIMIZATION_PLAN.md Phase 3 Rev 3.3 (2026-09-03). Called
        from every session exit. If a council brief was injected this
        session and its retry never reached session_validate (which is the
        only place _pending_council_round_id is otherwise cleared), record
        WHY as council_rounds.retry_outcome = "no_retry:<reason>" and say so
        at WARNING — before this, that case wrote nothing, and
        retry_validated stayed NULL on every round ever recorded, so "is
        the council earning its cost" had no data behind it at all.
        Never raises (D13); lazy import for the usual circular-import
        reason."""
        round_id = self._pending_council_round_id
        if round_id is None:
            return
        self._pending_council_round_id = None
        logger.warning(
            "council_retry_never_validated round_id=%s reason=%s", round_id, reason,
        )
        try:
            from jarvis.council.council import record_retry_outcome
            record_retry_outcome(round_id, f"no_retry:{reason}")
        except Exception:  # noqa: BLE001 — never break the agent loop
            logger.warning(
                "council_record_retry_outcome_call_failed round_id=%s",
                round_id, exc_info=True,
            )

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
        from jarvis.council.config import (
            COUNCIL_MAX_ESCALATIONS, COUNCIL_PLANNER_START_TIER,
        )

        if self._escalations_used >= COUNCIL_MAX_ESCALATIONS:
            return None
        # MORTIMER_OPTIMIZATION_PLAN.md Phase 3: this placement="planner"
        # escalation starts at COUNCIL_PLANNER_START_TIER (2), not tier 1 —
        # see council/config.py's comment on that constant for why (in
        # short: with only tiers 1-2 defined, this caps a session to one
        # real escalation attempt; a would-be 2nd attempt computes tier=3,
        # which resolve_members() rejects, and falls through below exactly
        # like "council unavailable").
        tier = self._escalations_used + COUNCIL_PLANNER_START_TIER
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
                goal=goal, tier=tier, context=context, run_id=self._run_id,
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
                context={"reason": reason, "allowlist": allowlist}, run_id=self._run_id,
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
            result = self.service.submit()
            if result.get("ok"):
                self._submit_result = result
            return result
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
        run_id: str | None = None,
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
            council_workflow="appbuild", run_id=run_id,
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
