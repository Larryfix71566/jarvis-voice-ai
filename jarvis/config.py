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
    # Engine install required: pip install deepfilternet (or pyrnnoise).
    jarvis_ns_enabled: bool = False  # feature flag + kill switch (plan A2)
    jarvis_ns_filter: str = "deepfilternet"  # deepfilternet | rnnoise | null | none
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

    # Interruption awareness (plan Phase 3) — surface a short context note
    # to the Supervisor when the user genuinely barges in on a reply.
    jarvis_interruption_notice_enabled: bool = True

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
        if name in ("JARVIS_DB_PATH", "JARVIS_TIMEZONE", "TAVILY_API_KEY"):
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
