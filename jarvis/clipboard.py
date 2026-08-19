"""Clipboard handoff — MORTIMER_HANDOFF_LOOP_PLAN.md H4/H5.

Larry, 2026-08-18: there was no way to give Mortimer a blob of text. Voice
is the only input, and STT cannot carry a JSON payload, a URL, or a stack
trace. So an investigation that needed a command's output simply stopped:
*"I cannot curl localhost:7861/api/ambient."*

This module is the return channel. It runs in the ADMIN SIDECAR, which is
a normal user process on Larry's Mac, so `pbpaste`/`pbcopy` are reachable
directly — no Swift change, no new bridge pattern, and no client→server
channel (the WKWebView bridge is fire-and-forget with no reply path, and
browser clipboard READ needs a user gesture that a voice command cannot
provide).

Three properties, and the first two hold by construction:

1. **ARMED, not free.** `clear()` wipes the clipboard and sets an armed
   flag; `read()` refuses unless armed, then disarms. Larry's own
   proposal made mechanical: "clear it first" as a habit protects only
   when remembered, which is the "a rule without a backstop is a wish"
   failure this codebase keeps rediscovering. Mortimer can therefore only
   ever read content copied AFTER an explicit clear.

2. **Fixed argv, zero parameters.** `["pbcopy"]` and `["pbpaste"]` — an
   argument list, never a shell, nothing interpolated. This is
   deliberately the safe end of the command-execution spectrum and is NOT
   a precedent for a general allowlist.

3. **Never remembered.** The caller must keep clipboard text out of the
   transcript (H5): `MemoryWatcher` folds the transcript into long-term
   memory via an LLM extraction call, so a password copied thirty seconds
   earlier could otherwise be persisted as a durable fact. That exclusion
   lives at the injection site in the bot; this module simply never
   writes anything down.

Deliberately NOT here: credential-detection heuristics. A regex for `sk-`
or a base64 blob false-positives on real terminal output and, worse,
creates false confidence that a filter is working. Showing Larry what was
read is stronger protection than guessing.
"""

from __future__ import annotations

import logging
import os
import subprocess

logger = logging.getLogger(__name__)

CLIPBOARD_ENABLED_ENV = "JARVIS_CLIPBOARD_ENABLED"

# Bounded for the same reason every other payload here is: a clipboard can
# hold megabytes, and the text is going into a voice model's context.
CLIPBOARD_MAX_CHARS = 20_000

CLIPBOARD_TIMEOUT_S = 5

# Armed state. Module-level because the sidecar is one process serving one
# Larry; there is no session to key it by, and persisting it would mean an
# arm could survive a restart, which is the opposite of what arming means.
_armed = False


def clipboard_enabled() -> bool:
    """The single kill-switch check point, matching screen_enabled()."""
    return os.environ.get(CLIPBOARD_ENABLED_ENV, "").strip().lower() not in (
        "false", "0", "no",
    )


def _disabled() -> dict:
    return {"ok": False,
            "error": "Clipboard access is disabled (JARVIS_CLIPBOARD_ENABLED=false)."}


def _run(argv: list[str], stdin: str | None = None) -> tuple[int, str]:
    """Argument-list subprocess, never a shell. Mirrors
    jarvis/selfedit/service.py's _run, including its exit-code convention:
    127 for a missing binary, 124 for a timeout."""
    try:
        proc = subprocess.run(
            argv,
            input=stdin if stdin is not None else "",
            capture_output=True,
            text=True,
            timeout=CLIPBOARD_TIMEOUT_S,
        )
        return proc.returncode, proc.stdout
    except FileNotFoundError as exc:
        return 127, str(exc)
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {CLIPBOARD_TIMEOUT_S}s"


def is_armed() -> bool:
    return _armed


def reset_for_tests() -> None:
    """Test seam only — the armed flag is process state."""
    global _armed
    _armed = False


def clear() -> dict:
    """Wipe the clipboard and arm a subsequent read.

    Clearing is destructive to whatever Larry had copied. That is
    acceptable because it only ever happens on an explicit request (voice)
    or as the declared side effect of Mortimer showing him a command it
    expects output from (H3.4).
    """
    global _armed
    if not clipboard_enabled():
        return _disabled()
    code, out = _run(["pbcopy"], stdin="")
    if code != 0:
        _armed = False
        logger.warning("clipboard_clear_failed code=%s out=%s", code, out[:200])
        return {"ok": False, "error": f"could not clear the clipboard ({out[:200]})"}
    _armed = True
    logger.info("clipboard_cleared armed=True")
    return {"ok": True, "armed": True}


def read() -> dict:
    """Read the clipboard, but only if a clear armed it. Disarms on read.

    Refusing an unarmed read is the whole safety property: without it,
    "read my clipboard" returns whatever happened to be there, which may
    be a credential Larry copied for an unrelated reason.
    """
    global _armed
    if not clipboard_enabled():
        return _disabled()
    if not _armed:
        # H6.4 — a refusal is the highest-attention moment a user has;
        # spending it on instruction rather than only on diagnosis is free.
        return {
            "ok": False,
            "armed": False,
            "error": (
                "Nothing has been copied since I last cleared the clipboard. "
                "Say 'clear my clipboard', then copy what you want me to "
                "read."
            ),
        }
    code, out = _run(["pbpaste"])
    if code != 0:
        logger.warning("clipboard_read_failed code=%s", code)
        return {"ok": False, "error": f"could not read the clipboard ({out[:200]})"}

    _armed = False          # one read per arm, always
    text = out
    truncated = len(text) > CLIPBOARD_MAX_CHARS
    if truncated:
        text = text[:CLIPBOARD_MAX_CHARS]
    # Length and a short prefix only — the content itself is never logged,
    # because the log is on disk and this text is explicitly not remembered.
    logger.info("clipboard_read chars=%d truncated=%s", len(text), truncated)
    return {
        "ok": True,
        "text": text,
        "chars": len(text),
        "truncated": truncated,
        "empty": not text.strip(),
    }
