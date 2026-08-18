"""Display payloads: sub-agent tool results -> UI display-panel messages.

When a sub-agent's tool produces something worth SEEING (research
findings, a weather radar, a new project plan, a coding/commit summary)
the pipeline forwards it to the frontend's DisplayPanel as
{"type": "display", "display": <payload>} over the RTVI server-message
channel. This module decides which tools are display-worthy (a whitelist)
and formats their results into the locked payload shape:

    {"kind": "markdown" | "image" | "links",
     "title": str, "body": str (markdown),
     "images": [url, ...], "links": [{"label", "url"}, ...],
     "agent": str, "ts": epoch_seconds}

Only successful results are displayed (error dicts are spoken, not
shown). Pure logic — no pipecat imports, fully unit-testable offline.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

# Tools whose results open the display panel. Everything else stays voice-only.
DISPLAY_TOOLS = {
    "web_search",
    "get_weather",
    "get_weather_radar",
    "app_create",
    "app_write_file",
    "git_diff_summary",
    "prepare_commit",
    "commit",
    "prepare_push",
    "push",
    # MORTIMER_PLANNING_PATHWAY_PLAN.md P5/P6.
    "repo_write_file",
    "repo_read_file",
    # F4 (MORTIMER_CONFIRMATION_AND_CAPABILITY_PLAN.md) — a pseudo-tool,
    # not a real MCP tool: jarvis/bot/plan_watcher.py pushes a finished
    # plan/review through this SAME display pipeline rather than opening
    # a second display code path.
    "plan_ready",
}

# Which surface a tool's result belongs on (side-drawer plan D36).
# "window" — an answer to a question the user just asked: glanceable,
#            transient, and on a multi-monitor setup parkable on a second
#            screen. "drawer" — work product: read carefully, kept.
DISPLAY_SURFACE: dict[str, str] = {
    "web_search": "window",
    "get_weather": "window",
    "get_weather_radar": "window",
    "app_create": "drawer",
    "app_write_file": "drawer",
    "git_diff_summary": "drawer",
    "prepare_commit": "drawer",
    "commit": "drawer",
    "prepare_push": "drawer",
    "push": "drawer",
    # P5 — draft review content is work product, kept in the Output tab
    # so the amber attention dot points at a fully reviewable document.
    "repo_write_file": "drawer",
    # P6 — an informational read, parkable on a second screen like the
    # other "window" surfaces.
    "repo_read_file": "window",
    # F4 — a finished plan is the answer to something the user asked for
    # and is parkable on a second screen while they read it.
    "plan_ready": "window",
}
DEFAULT_DISPLAY_SURFACE = "drawer"

MAX_SNIPPETS = 6

# MORTIMER_PLANNING_PATHWAY_PLAN.md P5/P6 — display truncation for full
# document content (distinct from PREVIEW_CHARS in jarvis/runlog/store.py,
# which bounds SQLite preview columns, not the UI). 30,000 chars comfortably
# covers a full plan/spec document while keeping the payload bounded.
DOC_DISPLAY_MAX_CHARS = 30_000
_TRUNCATION_SUFFIX = "\n\n… (truncated for display — the draft itself is complete)"


def _truncate_doc(text: str) -> str:
    if len(text) <= DOC_DISPLAY_MAX_CHARS:
        return text
    return text[:DOC_DISPLAY_MAX_CHARS] + _TRUNCATION_SUFFIX


def build_display_payload(
    agent: str,
    display_name: str,
    tool: str,
    arguments: dict[str, Any],
    result_str: str,
) -> dict | None:
    """Format a tool result as a display payload, or None to stay voice-only."""
    if tool not in DISPLAY_TOOLS:
        return None
    try:
        data = json.loads(result_str)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    # Failures are spoken by the agent — never pop a window for them.
    if data.get("error") or data.get("ok") is False:
        return None

    formatter = _FORMATTERS.get(tool)
    if formatter is None:
        return None
    built = formatter(arguments, data)
    if built is None:
        return None
    kind, title, body, images, links = built
    return {
        "kind": kind,
        "title": title,
        "body": body,
        "images": images,
        "links": links,
        "agent": display_name or agent,
        "ts": time.time(),
        "surface": DISPLAY_SURFACE.get(tool, DEFAULT_DISPLAY_SURFACE),
        # MORTIMER_ENGAGEMENT_DESIGN_PLAN.md E1 — additive (same D36
        # discipline as `surface`): lets the client derive deterministic
        # state from WHICH tool produced a payload — the amber
        # needs-your-confirmation signal (newest drawer item is a
        # draft-gated tool) and the ambient weather cache (tool ==
        # "get_weather") both read it.
        "tool": tool,
    }


# ------------------------------------------------------------- formatters
# Each returns (kind, title, body, images, links) or None.


def _fmt_web_search(args: dict, data: dict) -> tuple | None:
    results = [r for r in data.get("results", []) if r.get("url")]
    answer = (data.get("answer") or "").strip()
    if not answer and not results:
        return None
    query = (args.get("query") or "web search").strip()
    parts = []
    if answer:
        parts.append(answer)
    for i, r in enumerate(results[:MAX_SNIPPETS], 1):
        snippet = (r.get("snippet") or "").strip()
        parts.append(f"**{i}. {r.get('title', r['url'])}**\n{snippet}".rstrip())
    links = [
        {"label": r.get("title") or r["url"], "url": r["url"]}
        for r in results[:MAX_SNIPPETS]
    ]
    return ("markdown", f"Research — {query}", "\n\n".join(parts), [], links)


def _fmt_get_weather(args: dict, data: dict) -> tuple | None:
    city = data.get("city") or (args.get("city") or "").strip()
    human = (data.get("human") or "").strip()
    daily = data.get("daily") or []
    parts = [human] if human else []
    if daily:
        rows = [
            "| Date | High | Low | Precip | Conditions |",
            "|---|---|---|---|---|",
        ]
        for d in daily:
            precip = d.get("precip_probability")
            rows.append(
                f"| {d.get('date', '')} "
                f"| {d.get('max_c', '?')}°C "
                f"| {d.get('min_c', '?')}°C "
                f"| {precip if precip is not None else '?'}% "
                f"| {d.get('condition', '')} |"
            )
        parts.append("\n".join(rows))
    if not parts:
        return None
    return ("markdown", f"Weather — {city}", "\n\n".join(parts), [], [])


def _fmt_get_weather_radar(args: dict, data: dict) -> tuple | None:
    tiles = [u for u in data.get("tiles", []) if isinstance(u, str) and u]
    if not tiles:
        return None
    city = data.get("city") or (args.get("city") or "").strip()
    stamp = ""
    ts = data.get("ts")
    if isinstance(ts, (int, float)):
        stamp = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%H:%M UTC")
    body = f"Latest precipitation radar ({stamp or 'time unknown'}) centered on {city}."
    return ("image", f"Radar — {city}", body, tiles, [])


def _fmt_app_create(args: dict, data: dict) -> tuple | None:
    name = data.get("name") or data.get("proposed_name") or args.get("name") or "app"
    pending = data.get("pending")
    title = f"Project plan — {name}" if pending else f"Project created — {name}"
    parts = []
    summary = (data.get("summary") or "").strip()
    if summary:
        parts.append(summary)
    files = data.get("files") or []
    if files:
        parts.append("**Files**\n" + "\n".join(f"- `{p}`" for p in files))
    links = []
    if data.get("repo_url"):
        links.append({"label": f"{name} on GitHub", "url": data["repo_url"]})
    return ("markdown", title, "\n\n".join(parts), [], links)


def _fmt_app_write_file(args: dict, data: dict) -> tuple | None:
    app = data.get("app") or args.get("app") or ""
    path = data.get("path") or args.get("path") or ""
    parts = []
    summary = (data.get("summary") or "").strip()
    if summary:
        parts.append(summary)
    rationale = (args.get("rationale") or "").strip()
    if rationale:
        parts.append(f"_{rationale}_")
    commit = (data.get("commit") or "")[:7]
    if commit:
        parts.append(f"Commit `{commit}` on `main`.")
    return ("markdown", f"Code — {app}/{path}", "\n\n".join(parts), [], [])


def _fmt_git_diff_summary(args: dict, data: dict) -> tuple | None:
    stat = data.get("stat") or []
    if not stat:
        return None
    body = (
        f"**{data.get('summary_line', 'changes')}**\n\n"
        "```\n" + "\n".join(stat[:20]) + "\n```"
    )
    return ("markdown", "Working tree changes", body, [], [])


def _fmt_git_draft(tool: str):
    def fmt(args: dict, data: dict) -> tuple | None:
        summary = (data.get("summary") or "").strip()
        if not summary:
            return None
        verb = "commit" if tool == "prepare_commit" else "push"
        return ("markdown", f"Git — draft {verb}", summary, [], [])

    return fmt


def _fmt_git_executed(tool: str):
    def fmt(args: dict, data: dict) -> tuple | None:
        result = (data.get("result") or "").strip()
        verb = "committed" if tool == "commit" else "pushed"
        body = f"```\n{result}\n```" if result else f"Changes {verb}."
        return ("markdown", f"Git — {verb}", body, [], [])

    return fmt


def _fmt_repo_write_draft(args: dict, data: dict) -> tuple | None:
    """P5 — the phantom-completion fix's display half: the draft's FULL
    content (not just a commit-list summary, which is all _fmt_git_draft
    has to show), so the amber dot points at something actually reviewable.
    Content comes from the tool call's arguments (what was drafted), not
    `data` (the write-preview response, which never echoes it back)."""
    content = args.get("content")
    if not isinstance(content, str) or not content:
        return None
    action = data.get("action") or "write"
    path = data.get("path") or args.get("path") or ""
    return ("markdown", f"Repo — draft {action} {path}",
            _truncate_doc(content), [], [])


def _fmt_repo_read(args: dict, data: dict) -> tuple | None:
    """P6 — "show me the geolocation plan" renders the committed doc
    through the same display pipeline drafts use."""
    content = data.get("content")
    if not isinstance(content, str) or not content:
        return None
    path = data.get("path") or args.get("path") or ""
    return ("markdown", f"Repo — {path}", _truncate_doc(content), [], [])


def _fmt_plan_ready(args: dict, data: dict) -> tuple | None:
    """F4 — the planning pathway's finished document, pushed by
    plan_watcher.py when a background plan/review job reaches `done`.
    Titled by job kind so a review never reads as a fresh plan."""
    plan = data.get("plan")
    if not isinstance(plan, str) or not plan.strip():
        return None
    noun = "Review" if data.get("review_path") else "Plan"
    goal = str(data.get("goal") or "").strip()
    saved = str(data.get("saved_path") or "").strip()
    title = f"{noun} — {goal}" if goal else noun
    footer = [f"saved to {saved}"] if saved else []
    return ("markdown", title, _truncate_doc(plan), footer, [])


_FORMATTERS = {
    "web_search": _fmt_web_search,
    "get_weather": _fmt_get_weather,
    "get_weather_radar": _fmt_get_weather_radar,
    "app_create": _fmt_app_create,
    "app_write_file": _fmt_app_write_file,
    "git_diff_summary": _fmt_git_diff_summary,
    "prepare_commit": _fmt_git_draft("prepare_commit"),
    "prepare_push": _fmt_git_draft("prepare_push"),
    "commit": _fmt_git_executed("commit"),
    "push": _fmt_git_executed("push"),
    "repo_write_file": _fmt_repo_write_draft,
    "repo_read_file": _fmt_repo_read,
    "plan_ready": _fmt_plan_ready,
}
