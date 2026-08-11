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
