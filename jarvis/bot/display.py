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
}
DEFAULT_DISPLAY_SURFACE = "drawer"

MAX_SNIPPETS = 6


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
}
