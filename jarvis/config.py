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

import os
import re
import warnings
from pathlib import Path
from zoneinfo import ZoneInfo

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
