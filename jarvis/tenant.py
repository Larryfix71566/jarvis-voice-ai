"""Tenant identity (gap-closure plan GC8, contract GC-T). Column-only today:
every table carries user_id DEFAULT 'local'; nothing filters by it yet."""
from __future__ import annotations
import logging, os, re
logger = logging.getLogger(__name__)
DEFAULT_USER_ID = "local"
USER_ID_ENV = "JARVIS_USER_ID"
_VALID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

def current_user_id() -> str:
    raw = (os.environ.get(USER_ID_ENV) or "").strip()
    if not raw:
        return DEFAULT_USER_ID
    if not _VALID.match(raw):
        logger.warning("tenant_user_id_invalid value=%r using default", raw)
        return DEFAULT_USER_ID
    return raw
