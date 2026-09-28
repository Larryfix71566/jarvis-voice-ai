"""Shared base URLs for Mortimer services (Remote Access plan K5)."""

from __future__ import annotations

import os

ADMIN_URL_ENV = "JARVIS_ADMIN_URL"
BOT_URL_ENV = "JARVIS_BOT_URL"

DEFAULT_ADMIN_URL = "http://127.0.0.1:7861"
DEFAULT_BOT_URL = "http://127.0.0.1:7860"


def admin_url() -> str:
    return (os.environ.get(ADMIN_URL_ENV) or "").strip() or DEFAULT_ADMIN_URL


def bot_url() -> str:
    return (os.environ.get(BOT_URL_ENV) or "").strip() or DEFAULT_BOT_URL
