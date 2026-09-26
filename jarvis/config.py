"""Configuration system (plan §6.2).

Single pydantic-settings `Settings` class exposing every environment
variable from §6.1, plus the `${VAR}` expansion helper used by
`SkillRegistry` when loading config/mcp_servers.yaml (§6.3).

Validation rules (locked by the plan):
- Missing OPENAI_API_KEY, DEEPGRAM_API_KEY or ELEVENLABS_API_KEY -> startup
  error listing exactly which are missing.
- Missing TAVILY_API_KEY -> warning only (mcp-web degraded mode).
- JARVIS_TIMEZONE must be a valid IANA name.
"""

from __future__ import annotations

import logging
import os
import re
import warnings
from pathlib import Path
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REQUIRED_ENV_VARS = ("OPENAI_API_KEY", "DEEPGRAM_API_KEY", "ELEVENLABS_API_KEY")

_ENV_VAR_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)\}")


def expand_env_vars(value: str) -> str:
    """Expand ${VAR} placeholders from the process environment.

    Unknown variables are left as-is (literal "${VAR}") so misconfiguration
    surfaces downstream instead of silently becoming an empty string.
    """

    def _sub(match: re.Match[str]) -> str:
        return os.environ.get(match.group(1), match.group(0))

    return _ENV_VAR_PATTERN.sub(_sub, value)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # LLM (OpenAI-compatible)
    openai_api_key: str
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4.1-mini"

    # Speech
    deepgram_api_key: str
    elevenlabs_api_key: str

    # Skills (optional -> degraded mode)
    tavily_api_key: str | None = None

    # Noise suppression (voice isolation plan, Workstream A) — OFF by default.
    # Engine install required: pip install pyrnnoise (see requirements.txt).
    jarvis_ns_enabled: bool = False  # feature flag + kill switch (plan A2)
    # Default is rnnoise, NOT deepfilternet: DFN proved uninstallable on
    # py3.12 (no cp312 wheels ever; imports an API torchaudio removed;
    # unmaintained) — a default that cannot install is a trap. The
    # "deepfilternet" branch in jarvis/audio/filters.py remains for a
    # future where the project revives. (TIER12 plan §10, 2026-08-21.)
    jarvis_ns_filter: str = "rnnoise"  # rnnoise | deepfilternet | null | none
    jarvis_ns_atten_lim_db: float | None = None  # ⚙ strength knob (plan A3); None = full
    jarvis_ns_post_filter: bool = False
    jarvis_ns_log_stats: bool = True  # [ns] RTF telemetry (plan A2 step 4 / V1a)

    # Runtime
    jarvis_db_path: str = "data/jarvis.db"
    jarvis_log_level: str = "INFO"
    jarvis_bot_port: int = 7860
    jarvis_webrtc_endpoint: str = "http://localhost:7860/api/offer"
    jarvis_timezone: str = "America/New_York"
    jarvis_user_name: str = "Boss"
    jarvis_name: str = "Mortimer"
    # GC8 (gap-closure plan, 2026-09-04, contract GC-T) -- column-only
    # tenant identity; jarvis.tenant.current_user_id() is the one reader
    # of JARVIS_USER_ID. Nothing filters by this yet.
    jarvis_user_id: str = "local"

    # W3 (MORTIMER_WEATHER_FAHRENHEIT_AND_RADAR_PLAN.md) — a durable,
    # locale-derived display setting, the same kind of thing as
    # jarvis_timezone above and deliberately placed beside it: NOT a memory
    # fact (a memory fact carrying this rule was live and correct on
    # 2026-08-20 while the weather display still rendered Celsius, because
    # nothing in the code path ever read it — config is read by
    # get_weather and turned into arithmetic, memory is only ever advisory
    # to a model). "imperial" | "metric"; imperial is correct for this
    # deployment's user.
    jarvis_units: str = "imperial"

    # Interruption awareness (plan Phase 3) — surface a short context note
    # to the Supervisor when the user genuinely barges in on a reply.
    jarvis_interruption_notice_enabled: bool = True

    # MORTIMER_SESSION_MISSES_PLAN.md S6-S8 — rewrite a barge-in late-result
    # note in place once it has been relayed, so its "Relay this to the
    # user" imperative cannot be obeyed a second time on the next turn.
    # False restores the exact pre-plan behaviour (jarvis/bot/late_result.py).
    jarvis_late_result_neutralize_enabled: bool = True

    # MORTIMER_VOICE_WORKFLOWS_PLAN.md D16 — voice workflows (the user and
    # result hooks) and the reply guard. JARVIS_REPLY_GUARD_MODE is off |
    # log | correct; any other value runs as log
    # (jarvis.voice_workflows.normalize_guard_mode).
    jarvis_voice_workflows_enabled: bool = True
    # Ships in log (Larry, 2026-09-25): speak everything, record what it
    # would have stopped; switch to correct once the live log confirms the
    # corpus false-flag rate.
    jarvis_reply_guard_mode: str = "log"

    # Parallel delegation (plan Phase 4) — pipecat dispatches multiple
    # delegate_task calls from one assistant turn concurrently by default
    # (LLMService run_in_parallel=True); this bounds how many of OUR
    # delegate_task handlers may actually be running at once so a
    # pathological multi-part request can't spawn unbounded concurrent
    # sub-agent LLM calls.
    jarvis_max_parallel_delegations: int = 3

    # Run logging (MORTIMER_RUN_LOGGING_PLAN.md D17/D10) — durable records
    # of every sub-agent delegation and the MCP calls it made. Disabling
    # makes every RunLogger method a no-op (kill switch, plan §8 rollback).
    # Retention in days for agent_runs/agent_events rows and logs/agents/
    # date directories, pruned once at bot startup; <= 0 disables pruning.
    jarvis_runlog_enabled: bool = True
    jarvis_runlog_retention_days: int = 30

    # Reliable-memory plan D4 — how often MemorySweepWatcher folds the live
    # session into long-term memory while it is still running, not just at
    # teardown. Bounds data loss on an unclean disconnect (crash, closed
    # tab) to at most one interval. A tuning knob, not a hardcoded value.
    jarvis_memory_sweep_interval_s: float = 300.0

    # Automated memory classification/maintenance (MORTIMER_MEMORY_AUTOCONSOLIDATION_PLAN.md B).
    # Shadow is deliberately independent so policy can be measured without writes.
    jarvis_memory_automation_enabled: bool = False
    jarvis_memory_automation_shadow: bool = True
    # Ordered release gate: shadow -> explicit_preferences ->
    # corroborated_inferences. Unknown values fail closed at validation time.
    jarvis_memory_automation_stage: str = "shadow"
    # Background extraction/classification must not inherit the voice
    # Supervisor's OPENAI_MODEL. This profile is resolved through the single
    # registry and its own credential variable by jarvis.memory_model.
    jarvis_memory_profile: str = "claude-sonnet-5"
    # Non-voice maintenance (KB digests and procedure descriptions) also has
    # an explicit registry route. It must never inherit the Supervisor's
    # OPENAI_MODEL, which is the only route allowed to use Haiku.
    jarvis_background_profile: str = "claude-sonnet-5"

    # Model Use Enhancements — route policy file and explicit route controls.
    # Workload-specific JARVIS_MODEL_ROUTE_<WORKLOAD> and
    # JARVIS_MODEL_PROFILE_<WORKLOAD> overrides are read by
    # jarvis.model_routing; they never contain credential material.
    jarvis_model_access_config: str = "config/model_access.yaml"
    jarvis_model_route_voice_supervisor: str = "direct_api"
    jarvis_model_route_memory: str = "direct_api"
    jarvis_model_route_background: str = "direct_api"
    # Staged rollout gate. False preserves existing provider behavior while
    # route adapters and privacy policy are validated; true enables the shared
    # model-access policy at background call sites.
    jarvis_model_routing_enabled: bool = False

    # Command Console / shared-content gates. Shared content is subordinate
    # to the console gate and can never enable itself independently.
    jarvis_command_console_enabled: bool = False
    jarvis_shared_content_enabled: bool = False

    # Procedures-as-hints (MORTIMER_MEMORY_PROCEDURES_PLAN.md D20) — kill
    # switch. False makes match_procedure/learn_from_run no-ops: no hint is
    # ever injected, no candidate is ever created. Single enforcement point
    # inside jarvis/procedures.py itself, not re-checked at any call site.
    jarvis_procedures_enabled: bool = True

    # LLM Council (MORTIMER_LLM_COUNCIL_PLAN.md D11) — kill switch. False
    # disables convene() entirely: no fan-out, no logging, no cost.
    # Escalation then falls through to the ordinary failure path exactly
    # as it behaved before the council existed. Enforced at exactly one
    # place — jarvis/council/council.py's own env read at the top of
    # convene() — so this Settings field and that read can never
    # disagree on the default (true); this field exists for discoverability
    # (matching jarvis_procedures_enabled/jarvis_runlog_enabled) rather
    # than being consulted directly by council.py, which cannot import
    # jarvis.config without a circular import (config.py doesn't import
    # jarvis.agents/jarvis.council, but jarvis.council.council is invoked
    # from deep inside jarvis.agents.upgrade_agent, which must stay
    # import-light).
    jarvis_council_enabled: bool = True

    # Voice UI control (MORTIMER_VOICE_UI_PLAN.md U6) — kill switch. False
    # means the ui_control tool is not registered and not in the schema
    # list, and the prompt addendum is omitted: the Supervisor cannot call
    # what it cannot see. Enforced at exactly one place — the registration
    # site in jarvis/bot/pipeline.py's own env read — so this field and
    # that read can never disagree on the default (true); this field
    # exists for discoverability, matching jarvis_council_enabled.
    jarvis_ui_control_enabled: bool = True

    # LLM Council v2 (MORTIMER_LLM_COUNCIL_V2_PLAN.md V11) — retention for
    # council_rounds/council_scores and logs/council/, pruned once at bot
    # startup beside the runlog prune. Deliberately much longer than the
    # runlog's 30 days: D8.2.4's judge-tier decision needs >= 20 SHADOWED
    # rounds, which accumulate slowly (25% sample of escalated rounds
    # only) — pruning faster than they accumulate would permanently
    # starve the measurement. <= 0 disables.
    jarvis_council_retention_days: int = 180

    @field_validator("jarvis_timezone")
    @classmethod
    def _timezone_must_be_iana(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except Exception as exc:  # ZoneInfoNotFoundError, ValueError
            raise ValueError(
                f"JARVIS_TIMEZONE is not a valid IANA timezone: {v!r}"
            ) from exc
        return v

    @field_validator("jarvis_units")
    @classmethod
    def _units_must_be_known(cls, v: str) -> str:
        # W3 — no `false`/off state and no silent degrade: an unrecognized
        # value is rejected outright, matching the timezone validator just
        # above rather than defaulting quietly to one system or the other.
        if v not in ("imperial", "metric"):
            raise ValueError(
                f"JARVIS_UNITS must be 'imperial' or 'metric', got {v!r}"
            )
        return v

    @field_validator("jarvis_memory_automation_stage")
    @classmethod
    def _memory_rollout_stage_must_be_known(cls, v: str) -> str:
        if v not in {"shadow", "explicit_preferences", "corroborated_inferences"}:
            raise ValueError(
                "JARVIS_MEMORY_AUTOMATION_STAGE must be shadow, "
                "explicit_preferences, or corroborated_inferences"
            )
        return v

    @property
    def db_path(self) -> Path:
        return Path(self.jarvis_db_path)


def load_settings(env_file: str | None = ".env") -> Settings:
    """Load and validate settings.

    Raises RuntimeError with a clear message listing exactly which required
    environment variables are missing. Warns (does not fail) when
    TAVILY_API_KEY is absent.
    """
    # Credential vault (MORTIMER_CREDENTIAL_VAULT_PLAN.md S4, call site
    # 1 of 3): copy vault secrets into os.environ BEFORE Settings is
    # constructed, so pydantic's env lookup, the registry's ${VAR}
    # expansion for MCP child processes (spawned after this point), and
    # everything downstream see them as ordinary environment variables.
    # No-op when the vault is absent or disabled; hard error when the
    # vault exists but can't be opened (S6 — never run half-configured).
    from jarvis.vault import inject_env

    inject_env()

    # _env_file=None explicitly disables dotenv loading (the class-level
    # model_config default would otherwise still read ./.env).
    kwargs: dict = {"_env_file": None} if env_file is None else {"_env_file": env_file}
    try:
        settings = Settings(**kwargs)
    except Exception as exc:
        missing = [name for name in REQUIRED_ENV_VARS if not os.environ.get(name)]
        hint = (
            f" Missing required environment variables: {', '.join(missing)}."
            if missing
            else ""
        )
        raise RuntimeError(f"Configuration error.{hint} Details: {exc}") from exc

    if not settings.tavily_api_key:
        warnings.warn(
            "TAVILY_API_KEY not set — mcp-web will run in degraded mode "
            "(web_search unavailable)."
        )
    return settings


def bridge_settings_to_env(settings=None) -> None:
    """Copy Settings values MCP children need into `os.environ`.

    MORTIMER_ENV_BRIDGE_PLAN.md E1. `.env` is a FILE; `os.environ` is a
    PROCESS. pydantic-settings reads the file into a Settings object and puts
    nothing into the environment, so a stdio child inherits none of it unless
    something explicitly bridges — and `SkillRegistry._start_server` expands
    `${VAR}` against `os.environ`.

    Lived in jarvis/cli.py and had to be REMEMBERED by every entrypoint that
    starts a registry. Three remembered; `tests/evals/routing_eval.py` did
    not, so every set_reminder in that eval crashed with
    `ZoneInfoNotFoundError: 'No time zone found with key ${JARVIS_TIMEZONE}'`
    — the literal placeholder, five frames deep inside a subprocess, naming
    nothing useful. It now lives here, beside load_settings and
    expand_env_vars (the module that owns "where configuration comes from"),
    and SkillRegistry.start() calls it so no future entrypoint can forget.

    `setdefault`, never assignment: a real environment variable is the
    CI/override channel and must keep winning. That also makes this
    idempotent, which is why cli.py and pipeline.py keep their own calls —
    bridging before doing other work is not wrong, and removing those lines
    would be an unrelated edit.

    `settings=None` loads them. Best-effort: a Settings that cannot be built
    must not turn one stale env entry into a bot that will not start.
    """
    try:
        if settings is None:
            settings = load_settings()
        os.environ.setdefault("JARVIS_DB_PATH", settings.jarvis_db_path)
        os.environ.setdefault("JARVIS_TIMEZONE", settings.jarvis_timezone)
        # W3 — same transport JARVIS_TIMEZONE already uses to reach MCP
        # children; mcp_web.get_weather reads this to decide its primary
        # unit. setdefault keeps a real env var winning, same precedence
        # rule as every other bridged name here.
        os.environ.setdefault(
            "JARVIS_UNITS", getattr(settings, "jarvis_units", "imperial")
        )
        # GC8 -- same bridge as JARVIS_UNITS above; MCP children do NOT see
        # this (K2 forwards only BASE_ENV_KEYS plus declared optional_env,
        # and no server declares it yet). Only the bot process needs it.
        os.environ.setdefault(
            "JARVIS_USER_ID", getattr(settings, "jarvis_user_id", "local")
        )
        # Memory automation is consumed by the sweep and fact-upsert paths
        # through the process environment. Bridge the typed setting once at
        # startup so enabling it in Settings actually reaches those paths;
        # a real environment override keeps precedence.
        os.environ.setdefault(
            "JARVIS_MEMORY_AUTOMATION_ENABLED",
            "true" if getattr(settings, "jarvis_memory_automation_enabled", False) else "false",
        )
        os.environ.setdefault(
            "JARVIS_MEMORY_AUTOMATION_SHADOW",
            "true" if getattr(settings, "jarvis_memory_automation_shadow", True) else "false",
        )
        os.environ.setdefault(
            "JARVIS_MEMORY_AUTOMATION_STAGE",
            getattr(settings, "jarvis_memory_automation_stage", "shadow"),
        )
        os.environ.setdefault(
            "JARVIS_COMMAND_CONSOLE_ENABLED",
            "true" if getattr(settings, "jarvis_command_console_enabled", False) else "false",
        )
        os.environ.setdefault(
            "JARVIS_SHARED_CONTENT_ENABLED",
            "true" if (getattr(settings, "jarvis_command_console_enabled", False)
                        and getattr(settings, "jarvis_shared_content_enabled", False)) else "false",
        )
        if getattr(settings, "tavily_api_key", None):
            os.environ.setdefault("TAVILY_API_KEY", settings.tavily_api_key)
        return
    except Exception as exc:  # noqa: BLE001 — must never block startup
        logger.warning("settings_env_bridge_degraded error=%s", exc)

    # Settings validation FAILS without OPENAI/DEEPGRAM/ELEVENLABS keys —
    # none of which this function needs. Left there, a fresh checkout or a
    # CI run gets no bridge at all and children see the literal ${VAR}
    # again: the original bug, surviving in a different form. Read the three
    # names straight out of .env instead. Same setdefault precedence, so a
    # real environment variable still wins.
    for name, value in _dotenv_values().items():
        if name in (
            "JARVIS_DB_PATH", "JARVIS_TIMEZONE", "TAVILY_API_KEY",
            "JARVIS_UNITS", "JARVIS_USER_ID",
            "JARVIS_MEMORY_AUTOMATION_ENABLED", "JARVIS_MEMORY_AUTOMATION_SHADOW",
            "JARVIS_MEMORY_AUTOMATION_STAGE",
            "JARVIS_COMMAND_CONSOLE_ENABLED", "JARVIS_SHARED_CONTENT_ENABLED",
        ):
            if value:
                os.environ.setdefault(name, value)


def _dotenv_values(path: Path | None = None) -> dict[str, str]:
    """Minimal KEY=VALUE parse of the repo .env. Deliberately NOT a second
    configuration system — it exists only so bridge_settings_to_env can
    still do its one job when full Settings validation is impossible."""
    env_file = path or (Path(__file__).resolve().parent.parent / ".env")
    values: dict[str, str] = {}
    try:
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip().strip('"').strip("'")
    except OSError:
        pass
    return values
