"""MORTIMER_HOME resolution and retrieval.yaml config (§2, §9 of spec)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_RETRIEVAL_CONFIG = {
    "fts_k": 8,
    "link_hops": 1,
    "max_results": 8,
    "max_injected_tokens": 4000,
    "recency_half_life_days": 30,
    "confidence_weights": {"high": 1.0, "medium": 0.7, "low": 0.4},
}


def mortimer_home() -> Path:
    home = os.environ.get("MORTIMER_HOME")
    if home:
        return Path(home).expanduser()
    return Path.home() / "Mortimer"


@dataclass
class Paths:
    home: Path
    vault: Path
    users: Path
    index_dir: Path
    index_db: Path
    config_dir: Path
    retrieval_config: Path
    logs_dir: Path
    log_file: Path

    @classmethod
    def build(cls, home: Path | None = None) -> "Paths":
        home = home or mortimer_home()
        vault = home / "vault"
        return cls(
            home=home,
            vault=vault,
            users=vault / "users",
            index_dir=home / "index",
            index_db=home / "index" / "vault.db",
            config_dir=home / "config",
            retrieval_config=home / "config" / "retrieval.yaml",
            logs_dir=home / "logs",
            log_file=home / "logs" / "vault.log",
        )

    def user_dir(self, user_id: str) -> Path:
        return self.users / user_id

    def ensure_layout(self, user_id: str) -> None:
        for sub in ("areas", "sessions", "inbox"):
            (self.user_dir(user_id) / sub).mkdir(parents=True, exist_ok=True)
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)


def load_retrieval_config(paths: Paths) -> dict:
    """Load retrieval.yaml, creating it with defaults if absent (§9).

    link_hops must equal 1 in v1; other values are rejected at load.
    """
    if not paths.retrieval_config.exists():
        paths.config_dir.mkdir(parents=True, exist_ok=True)
        with open(paths.retrieval_config, "w") as f:
            yaml.safe_dump(DEFAULT_RETRIEVAL_CONFIG, f, sort_keys=False)
        return dict(DEFAULT_RETRIEVAL_CONFIG)

    with open(paths.retrieval_config) as f:
        cfg = yaml.safe_load(f) or {}

    merged = {**DEFAULT_RETRIEVAL_CONFIG, **cfg}
    if merged.get("link_hops") != 1:
        raise ValueError(
            f"link_hops must be 1 in v1; got {merged.get('link_hops')!r}"
        )
    return merged
