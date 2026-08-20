"""mcp-screen: screen enumeration + vision-assisted screen viewing
(MORTIMER_SHELL_FIX_AND_SCREEN_VISION_PLAN.md Part V).

Sync functions, plain dicts in/out, failures return {"error": ...} —
never raise — matching mcp_web's convention (the same discipline this
codebase already applies to every other network/subprocess-backed MCP
server).

Guardrails (V4): capture only ever happens inside a tool call — no
watcher, no schedule, nothing proactive. `screen_enabled()` is the ONE
kill-switch check point (JARVIS_SCREEN_ENABLED=false), called at the top
of every public function here so both this MCP server's tools AND the
Supervisor's direct `view_screen` tool (jarvis/bot/screen_tool.py, which
calls these same functions rather than duplicating logic) share one
off switch. The captured screenshot is a temp file, read once, and
deleted in a `finally` no matter what happens after capture — it is
never written under `data/`, never logged, and never returned to a
caller; only the vision model's TEXT answer crosses back into the loop.

Trade-off Larry accepted 2026-08-18: every screen_view call sends the
captured image to a cloud vision API. Anything visible on the captured
display leaves the machine. JARVIS_SCREEN_ENABLED=false is the off-ramp.

DIAGNOSTICS (MORTIMER_SKILL_LIBRARY_PLAN.md Part G, Larry 2026-08-18:
*"since computer vision is untested ... add what it sees into the logs,
not indefinitely, only for a short period"*). Two tiers, and the
paragraph above is now conditionally false, which is why this note
exists:

  Tier 1 (always on) — one structured log line per capture: the model's
  TEXT answer preview, display index, image byte size, low_confidence,
  profile, and latency. The answer already crosses back to the caller,
  so logging it adds no exposure; the byte size and latency are what
  actually diagnose a bad capture.

  G3 (always on) — an image whose capture came back `low_confidence` IS
  retained under logs/screen/. That is a few KB of wallpaper, it is the
  exact artifact proving a missing Screen Recording grant, and it is the
  one case where the image is nearly certain to contain nothing private.

Tier 2 — retaining EVERY captured image — was designed (a self-expiring
`JARVIS_SCREEN_DEBUG_UNTIL` deadline) and deliberately NOT built: Tier 1
and G3 are cheap and may well be sufficient. Do not add it without a
real failure that survives them, and if it is added, the deadline must
be an absolute timestamp with no boolean form — "remember to turn it
off" is a wish, not a backstop.

Retention is JARVIS_SCREEN_RETENTION_HOURS (default 48) — by a wide
margin the shortest in the system (run log: 30 days; council: 180), and
deliberately so.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import subprocess
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from jarvis.agents.upgrade_agent import load_model_registry

logger = logging.getLogger(__name__)

SCREEN_ENABLED_ENV = "JARVIS_SCREEN_ENABLED"
VISION_PROFILE_ENV = "JARVIS_VISION_PROFILE"
SCREEN_RETENTION_ENV = "JARVIS_SCREEN_RETENTION_HOURS"

# logs/ is gitignored, so nothing retained here can reach GitHub.
SCREEN_LOG_DIR = Path(__file__).resolve().parents[2] / "logs" / "screen"

DEFAULT_RETENTION_HOURS = 48

# Only a preview of the answer goes to the log line; the full text is
# already returned to the caller, and an unbounded log line is how a log
# becomes unreadable.
ANSWER_PREVIEW_CHARS = 200

# A real screenshot of any populated display is comfortably above this;
# an empty/wallpaper-only capture (the classic symptom of a missing
# macOS Screen Recording grant — V5) tends to compress far smaller. This
# is a best-effort heuristic, not a certainty, hence "low_confidence"
# rather than an outright error.
MIN_SCREENSHOT_BYTES = 2000

CAPTURE_TIMEOUT_S = 10
PROFILER_TIMEOUT_S = 10


def screen_enabled() -> bool:
    """The single JARVIS_SCREEN_ENABLED check point (V4)."""
    return os.environ.get(SCREEN_ENABLED_ENV, "").strip().lower() not in (
        "false", "0", "no",
    )


def _disabled_error() -> dict:
    return {"error": "Screen vision is disabled (JARVIS_SCREEN_ENABLED=false)."}


def retention_hours() -> int:
    """How long a retained diagnostic image lives. Never raises."""
    raw = os.environ.get(SCREEN_RETENTION_ENV, "").strip()
    if not raw:
        return DEFAULT_RETENTION_HOURS
    try:
        value = int(raw)
    except ValueError:
        logger.warning("screen_retention_unparseable value=%r using=%d",
                       raw, DEFAULT_RETENTION_HOURS)
        return DEFAULT_RETENTION_HOURS
    return max(0, value)


def prune_screen_logs(directory: Path | None = None, now: float | None = None) -> int:
    """Delete retained diagnostic images older than the retention window.

    Called at bot startup beside the run-log prune. Returns the number
    deleted. Never raises — a prune failure must not stop a boot.

    This is the backstop that makes retention real rather than promised:
    even if nothing else runs, an image cannot outlive the window.
    """
    directory = directory or SCREEN_LOG_DIR
    if not directory.exists():
        return 0
    hours = retention_hours()
    cutoff = (now if now is not None else time.time()) - hours * 3600
    deleted = 0
    try:
        for path in directory.rglob("*.png"):
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink()
                    deleted += 1
            except OSError:
                continue
        # Tidy empty date folders so the directory does not accumulate.
        for child in sorted(directory.glob("*"), reverse=True):
            if child.is_dir() and not any(child.iterdir()):
                child.rmdir()
    except Exception:  # noqa: BLE001 — pruning must never break startup
        logger.exception("screen_prune_failed dir=%s", directory)
    if deleted:
        logger.info("screen_logs_pruned deleted=%d older_than_hours=%d",
                    deleted, hours)
    return deleted


def _retain_failed_capture(image_bytes: bytes, display: int,
                           directory: Path | None = None) -> str | None:
    """G3 — keep a LOW-CONFIDENCE capture only.

    Deliberately not a general "save the screenshot" helper: it is called
    from exactly one branch, the one where the image is almost certainly
    wallpaper and the question is whether macOS granted Screen Recording
    at all. Returns the path written, or None. Never raises — a
    diagnostic must not break the tool it is diagnosing.
    """
    directory = directory or SCREEN_LOG_DIR
    try:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        folder = directory / day
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%H%M%S")
        path = folder / f"lowconf-display{display}-{stamp}.png"
        path.write_bytes(image_bytes)
        logger.warning(
            "screen_lowconf_retained path=%s bytes=%d — kept for "
            "troubleshooting; pruned after %dh",
            path, len(image_bytes), retention_hours())
        return str(path)
    except Exception:  # noqa: BLE001
        logger.exception("screen_lowconf_retain_failed display=%s", display)
        return None


# --- screen_list -------------------------------------------------------


def _system_profiler_displays() -> list[dict]:
    """Real backend for screen_list: shells out to `system_profiler
    SPDisplaysDataType -json` and returns a best-effort list of
    {"resolution": str, "main": bool} dicts in display order.

    Apple's JSON shape for this command varies across macOS versions and
    has never been exercised against real hardware from this sandbox
    (no macOS available) — a parse failure returns an empty list rather
    than raising, so screen_list degrades to "no display info" instead
    of crashing. Confirm the real shape during S5/V-track live
    verification and adjust the key names below if they don't match.
    """
    try:
        proc = subprocess.run(
            ["system_profiler", "SPDisplaysDataType", "-json"],
            capture_output=True, text=True, timeout=PROFILER_TIMEOUT_S, check=True,
        )
        data = json.loads(proc.stdout)
    except Exception:
        return []
    out: list[dict] = []
    for adapter in data.get("SPDisplaysDataType", []) or []:
        entries = adapter.get("spdisplays_ndrvs") or adapter.get("spdisplays_displays") or []
        for d in entries:
            if not isinstance(d, dict):
                continue
            out.append({
                "resolution": (
                    d.get("_spdisplays_resolution")
                    or d.get("spdisplays_resolution")
                    or "unknown"
                ),
                "main": d.get("spdisplays_main") == "spdisplays_yes",
            })
    return out


def screen_list(fetch: Callable[[], list[dict]] = _system_profiler_displays) -> dict:
    """Enumerate connected displays: 1-based index (matching
    `screencapture -D <n>`), resolution, and which one is the main
    display. `fetch` is the injected test seam."""
    if not screen_enabled():
        return _disabled_error()
    raw = fetch()
    displays = [
        {
            "index": i + 1,
            "resolution": d.get("resolution", "unknown"),
            "main": bool(d.get("main")),
        }
        for i, d in enumerate(raw)
    ]
    if not displays:
        # Best-effort fallback: at least one display always exists if
        # anything is running at all. Better than an empty, useless list.
        displays = [{"index": 1, "resolution": "unknown", "main": True}]
    return {"displays": displays}


# --- screen_view ---------------------------------------------------------


def _capture_screenshot(display: int) -> Path:
    """Real backend: `screencapture -x -D <display> <tmpfile>`. -x
    suppresses the capture sound. Injectable test seam."""
    fd, path_str = tempfile.mkstemp(suffix=".png", prefix="mortimer-screen-")
    os.close(fd)
    path = Path(path_str)
    subprocess.run(
        ["screencapture", "-x", "-D", str(display), str(path)],
        check=True, timeout=CAPTURE_TIMEOUT_S,
    )
    return path


class NoVisionProfileError(RuntimeError):
    """No usable (vision-capable, key-present) model profile was found."""


def _resolve_vision_profile(registry: dict[str, Any] | None = None) -> dict[str, Any]:
    """V2: JARVIS_VISION_PROFILE env wins if set and valid; otherwise the
    first key-present `vision: true` profile in registry order. Raises
    NoVisionProfileError (caught by screen_view, turned into an {"error":
    ...} dict) rather than returning one directly, so callers that want
    to resolve a profile without a capture (future use) can reuse this."""
    reg = registry if registry is not None else load_model_registry()
    profiles: dict[str, Any] = reg.get("profiles", {})

    requested = os.environ.get(VISION_PROFILE_ENV)
    if requested:
        prof = profiles.get(requested)
        if prof is None or not prof.get("vision"):
            raise NoVisionProfileError(
                f"{VISION_PROFILE_ENV}={requested!r} is not a known "
                "vision-capable profile in config/upgrade_models.yaml."
            )
        key_env = prof.get("api_key_env", "OPENAI_API_KEY")
        if not os.environ.get(key_env):
            raise NoVisionProfileError(
                f"Vision profile {requested!r} is missing its API key "
                f"({key_env})."
            )
        return prof

    for prof in profiles.values():
        if not prof.get("vision"):
            continue
        key_env = prof.get("api_key_env", "OPENAI_API_KEY")
        if os.environ.get(key_env):
            return prof

    raise NoVisionProfileError(
        "No vision-capable model profile has its API key set. Add "
        "`vision: true` to a profile in config/upgrade_models.yaml with "
        "a present api_key_env, or set JARVIS_VISION_PROFILE."
    )


def _default_vision_client(profile: dict[str, Any]) -> tuple[Any, str]:
    """Real backend: an OpenAI-compatible client against the resolved
    profile, same construction SubAgent already uses for planner
    profiles (jarvis/agents/base.py) — one client-construction pattern,
    not a second one. Sync client (screen_view is a sync MCP tool,
    matching mcp_web's convention)."""
    from openai import OpenAI

    key_env = profile.get("api_key_env", "OPENAI_API_KEY")
    return (
        OpenAI(api_key=os.environ[key_env], base_url=profile["base_url"]),
        profile["model"],
    )


def screen_view(
    question: str,
    display: int = 1,
    *,
    capture_fn: Callable[[int], Path] = _capture_screenshot,
    client_factory: Callable[[dict[str, Any]], tuple[Any, str]] = _default_vision_client,
    registry: dict[str, Any] | None = None,
) -> dict:
    """Capture `display` and ask a vision model `question` about what's
    showing. The image is analyzed in ONE one-shot call and never
    persists or returns to the caller — only the model's text answer
    does (V2/V4). `capture_fn`/`client_factory`/`registry` are injected
    test seams; production callers use the defaults."""
    if not screen_enabled():
        return _disabled_error()

    try:
        profile = _resolve_vision_profile(registry)
    except NoVisionProfileError as exc:
        return {"error": str(exc)}

    started = time.perf_counter()
    try:
        path = capture_fn(display)
    except Exception as exc:  # subprocess failure, bad display index, etc.
        logger.warning("screen_view display=%s outcome=capture_failed error=%s",
                       display, exc)
        return {"error": f"Screen capture failed: {exc}"}

    try:
        image_bytes = path.read_bytes()
        if len(image_bytes) < MIN_SCREENSHOT_BYTES:
            # V5 — the classic symptom of a missing macOS Screen Recording
            # grant: screencapture silently produces a near-empty image
            # rather than erroring. Report this plainly instead of
            # sending a useless image to the vision model and presenting
            # its confused answer as a real one.
            # G3 — this is the one image worth keeping.
            retained = _retain_failed_capture(image_bytes, display)
            logger.warning(
                "screen_view display=%s outcome=low_confidence bytes=%d "
                "min_bytes=%d profile=%s retained=%s ms=%d",
                display, len(image_bytes), MIN_SCREENSHOT_BYTES,
                profile.get("name"), retained,
                int((time.perf_counter() - started) * 1000))
            return {
                "answer": (
                    "The captured image looks empty or wallpaper-only — "
                    "this usually means Mortimer hasn't been granted "
                    "Screen Recording permission (System Settings > "
                    "Privacy & Security > Screen Recording)."
                ),
                "display": display,
                "profile": profile.get("name"),
                "low_confidence": True,
            }

        b64 = base64.b64encode(image_bytes).decode("ascii")
        try:
            client, model = client_factory(profile)
            response = client.chat.completions.create(
                model=model,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": question},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64}"},
                        },
                    ],
                }],
            )
            answer = response.choices[0].message.content or ""
        except Exception as exc:
            # MORTIMER_KEY_VALIDITY_PLAN.md K7 — an auth failure is named as
            # one, never folded into a generic "vision model call failed"
            # that reads like a capture problem.
            #
            # MIN_SCREENSHOT_BYTES above exists because macOS Screen
            # Recording denial fails SILENTLY into a wallpaper-only image.
            # There was no equivalent for a dead credential, and since every
            # `vision: true` profile is Anthropic, one bad ANTHROPIC_API_KEY
            # kills screen vision entirely while _resolve_vision_profile
            # reports success — because the key is PRESENT. The user then
            # sees a capture-shaped error for a credential-shaped problem,
            # which is the same mistake that once reported a GitHub 401 as
            # "the sidecar may be offline" (AGENT_TRUST_PLAN D8).
            status = getattr(exc, "status_code", None)
            name = type(exc).__name__
            rejected = (status in (401, 403)
                        or name in ("AuthenticationError", "PermissionDeniedError"))
            outcome = "auth_rejected" if rejected else "model_failed"
            logger.warning(
                "screen_view display=%s outcome=%s bytes=%d "
                "profile=%s error=%s ms=%d",
                display, outcome, len(image_bytes), profile.get("name"), exc,
                int((time.perf_counter() - started) * 1000))
            if rejected:
                key_env = profile.get("api_key_env", "the vision API key")
                return {
                    "error": (
                        f"The vision model rejected the credential "
                        f"(HTTP {status}). The screen was captured fine — "
                        f"{key_env} for profile "
                        f"{profile.get('name')!r} is dead or wrong. Check it "
                        f"with `python scripts/check_keys.py`."
                    ),
                    "auth_rejected": True,
                    "profile": profile.get("name"),
                }
            return {"error": f"Vision model call failed: {exc}"}

        # Tier 1 — the diagnostic record. The answer already crosses back
        # to the caller, so a bounded preview here costs no new exposure;
        # bytes and latency are what actually distinguish "the capture was
        # wrong" from "the model was wrong", which is the question the
        # direct view_screen path could not answer at all before this
        # (it is not a delegation, so it writes no run-log row).
        logger.info(
            "screen_view display=%s outcome=ok bytes=%d profile=%s ms=%d "
            "answer=%r",
            display, len(image_bytes), profile.get("name"),
            int((time.perf_counter() - started) * 1000),
            answer[:ANSWER_PREVIEW_CHARS])

        return {
            "answer": answer,
            "display": display,
            "profile": profile.get("name"),
            "low_confidence": False,
        }
    finally:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
