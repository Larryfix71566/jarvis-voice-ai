"""Mortimer's own live status (MORTIMER_SELF_SERVICE_ACCESS_AND_RECOVERY spec P2).

Status facts are computed in code, in the admin sidecar, and relayed by the
voice tool `system_status` and the `mcp-status` MCP server (spec L2, I4).
This package is pure logic: every module reads data Mortimer's own
processes already hold, and nothing here writes (I2).

`status_enabled()` is the single enforcement point of the
`JARVIS_STATUS_TOOLS_ENABLED` kill switch (R9, I7). Default on.
"""

from __future__ import annotations

import os

KILL_SWITCH_ENV = "JARVIS_STATUS_TOOLS_ENABLED"


def status_enabled() -> bool:
    """On unless the switch is set to a falsy spelling. Off means the voice
    tool is not registered, its prompt addendum is omitted, and the
    sidecar's /api/status/* routes answer "status tools are disabled"."""
    value = os.environ.get(KILL_SWITCH_ENV)
    if value is None:
        return True
    return value.strip().lower() not in ("0", "false", "no", "off")
