"""Logging setup (plan Phase 0, step 0.3). Stdlib logging only."""

from __future__ import annotations

import logging

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def setup_logging(level: str = "INFO") -> None:
    """Configure root logging. Level comes from JARVIS_LOG_LEVEL."""
    numeric = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(level=numeric, format=LOG_FORMAT, force=True)
