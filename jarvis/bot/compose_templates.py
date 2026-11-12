"""Fixed templates for composed answers (interface contracts 1.5 to 1.7).

Pure functions over plain dicts.  A template reads ONE legacy display payload
(plus the optional private ``layout_hints`` dict that
``display.build_display_payload(layout_hints=True)`` adds for the two tools
whose structure the legacy fields flatten) and returns a "part": the template
name, the content blocks it yields (without ids), the links it offers, and the
legacy title/body used to build the fallback fields of a joined answer.

``build_layout`` assembles the parts of one answer into a layout (header,
each part's blocks in arrival order, one merged sources block) and
``legacy_fields`` builds the fallback fields for old clients (1.5 rule 9).
No model chooses blocks; everything here is code (1.6, 1.9.6).
"""
from __future__ import annotations

import time
from typing import Any

from jarvis.bot.compose_schema import (
    LAYOUT_VERSION,
    MAX_SUMMARY,
    MAX_TEXT_CHARS,
    MAX_TITLE,
    sanitize_url,
)

# tool -> template name (contract 1.7).  A tool absent here is not composed.
TEMPLATES: dict[str, str] = {
    "web_search": "research",
    "get_weather": "weather",
    "get_weather_radar": "radar",
    "weather_report": "weather",
    "app_create": "app",
    "app_write_file": "code",
    "git_diff_summary": "code",
    "repo_read_file": "document",
    "plan_ready": "document",
    "research_report": "document",
    "memory_graph_view": "graph",
    "graph_view": "graph",
    "show_commands": "commands",
    "shared_content": "analysis",
}

JOINED_TEMPLATE = "joined"
MAX_MEDIA_URLS = 9
MAX_SOURCES = 12
MAX_LIST_ITEMS = 12
MAX_HEADER_AGENTS = 6


def _clip(value: Any, limit: int) -> str:
    return value[:limit] if isinstance(value, str) else ""


def _text_block(text: Any, fmt: str = "markdown") -> dict | None:
    text = _clip(text, MAX_TEXT_CHARS)
    if not text.strip():
        return None
    return {"_slot": "text", "type": "text", "format": fmt, "text": text}


def _media_block(images: Any, basemap: Any, a11y: str) -> dict | None:
    urls = [u for u in (images or []) if sanitize_url(u) is not None][:MAX_MEDIA_URLS]
    if not urls:
        return None
    block: dict[str, Any] = {"_slot": "media", "type": "media", "images": urls,
                             "a11y": _clip(a11y, 300) or "Image"}
    base = [u for u in (basemap or []) if sanitize_url(u) is not None][:MAX_MEDIA_URLS]
    if base:
        block["basemap_images"] = base
    return block


def _list_block(hint: Any) -> dict | None:
    if not isinstance(hint, dict):
        return None
    items = []
    for raw in hint.get("items") or []:
        if not isinstance(raw, dict):
            continue
        title = _clip(raw.get("title"), MAX_TITLE)
        if not title:
            continue
        item = {"title": title}
        detail = _clip(raw.get("detail"), 240)
        if detail:
            item["detail"] = detail
        meta = _clip(raw.get("meta"), 40)
        if meta:
            item["meta"] = meta
        items.append(item)
    if not items:
        return None
    extra = max(0, len(items) - MAX_LIST_ITEMS)
    block: dict[str, Any] = {"_slot": "list", "type": "list", "items": items[:MAX_LIST_ITEMS]}
    title = _clip(hint.get("title"), MAX_TITLE)
    if title:
        block["title"] = title
    more = hint.get("more_count")
    more = more if type(more) is int and more >= 0 else 0
    if more + extra:
        block["more_count"] = more + extra
    return block


def _compact(blocks: list[dict | None]) -> list[dict]:
    return [b for b in blocks if b]


def _commands_body(payload: dict) -> str:
    cmds = payload.get("commands")
    lines = [c if isinstance(c, str) else str(c) for c in (cmds if isinstance(cmds, list) else [])]
    body = "```\n" + "\n".join(lines) + "\n```" if lines else ""
    note = payload.get("note")
    if isinstance(note, str) and note.strip():
        body = (body + "\n\n" if body else "") + note
    return body


def part_for(payload: dict, hints: dict | None = None) -> dict | None:
    """Return the part for one legacy payload, or None when it cannot be built."""
    tool = payload.get("tool")
    template = TEMPLATES.get(tool) if isinstance(tool, str) else None
    if template is None:
        return None
    hints = hints if isinstance(hints, dict) else {}
    body = payload.get("body") if isinstance(payload.get("body"), str) else ""
    title = payload.get("title") if isinstance(payload.get("title"), str) else ""
    images = payload.get("images") if isinstance(payload.get("images"), list) else []
    basemap = payload.get("basemap_images") if isinstance(payload.get("basemap_images"), list) else []
    links = payload.get("links") if isinstance(payload.get("links"), list) else []
    legacy_body = body
    blocks: list[dict | None]

    if tool in ("web_search", "get_weather", "app_write_file", "git_diff_summary"):
        blocks = [_text_block(body)]
    elif tool == "get_weather_radar":
        blocks = [_media_block(images, basemap, body or title or "Radar")]
    elif tool == "weather_report":
        if isinstance(payload.get("weather"), dict):
            blocks = [{"_slot": "w", "type": "weather", "weather": payload["weather"]}]
        else:
            blocks = [_text_block(body), _media_block(images, basemap, body or title or "Weather")]
    elif tool == "app_create":
        text = hints.get("text", body)
        blocks = [_text_block(text), _list_block(hints.get("list"))]
    elif tool == "repo_read_file":
        if isinstance(payload.get("roadmap"), dict):
            template = "roadmap"
            wrapper: dict[str, Any] = {"_slot": "w", "type": "roadmap", "roadmap": payload["roadmap"]}
            tz = payload.get("roadmap_timezone")
            if isinstance(tz, str) and 1 <= len(tz) <= 80:
                wrapper["roadmap_timezone"] = tz
            blocks = [wrapper]
        else:
            if title == "Roadmap unavailable":
                template = "notice"
            blocks = [_text_block(body)]
    elif tool == "plan_ready":
        text = body
        if images and isinstance(images[0], str) and images[0].startswith("saved to "):
            text = body + "\n\n_" + images[0] + "_"
        legacy_body = text
        blocks = [_text_block(text)]
    elif tool == "research_report":
        text = hints.get("text", body)
        blocks = [_text_block(text), _list_block(hints.get("list"))]
    elif tool in ("memory_graph_view", "graph_view"):
        url = images[0] if images else None
        if sanitize_url(url) is None:
            return None
        wrapper = {"_slot": "w", "type": "graph", "image_url": url}
        if body:
            wrapper["summary"] = body[:MAX_SUMMARY]
        blocks = [wrapper]
    elif tool == "show_commands":
        cmds = payload.get("commands")
        if not isinstance(cmds, list):
            return None
        wrapper = {"_slot": "w", "type": "commands", "commands": cmds}
        note = payload.get("note")
        if isinstance(note, str) and note:
            wrapper["note"] = note[:MAX_SUMMARY]
        if type(payload.get("expect_output")) is bool:
            wrapper["expect_output"] = payload["expect_output"]
        legacy_body = _commands_body(payload)
        blocks = [wrapper]
    elif tool == "shared_content":
        text = payload.get("text") if isinstance(payload.get("text"), str) else ""
        legacy_body = text
        blocks = [_text_block(text, "plain")]
    else:  # pragma: no cover - TEMPLATES and this chain are kept in step
        return None

    return {
        "template": template,
        "blocks": _compact(blocks),
        "links": [x for x in links if isinstance(x, dict)],
        "title": title,
        "body": legacy_body,
        "payload": payload,
    }


def _part_title(part: dict) -> str:
    return _clip(part["title"], MAX_TITLE).strip() or "Result"


def _source(payload: dict) -> dict | None:
    src: dict[str, str] = {}
    for key, limit in (("tool", 80), ("run_id", 120), ("agent", 80)):
        value = payload.get(key)
        if isinstance(value, str) and value:
            src[key] = value[:limit]
    return src or None


def _merged_sources(parts: list[dict]) -> dict | None:
    items: list[dict] = []
    seen: set[str] = set()
    for part in parts:
        for link in part["links"]:
            url = link.get("url") if isinstance(link.get("url"), str) else ""
            label = link.get("label") if isinstance(link.get("label"), str) else ""
            key = url or label
            if not key or key in seen:
                continue
            seen.add(key)
            item = {"label": _clip(label or url, 120) or "Source"}
            if sanitize_url(url) is not None:
                item["url"] = url
            items.append(item)
            if len(items) >= MAX_SOURCES:
                break
        if len(items) >= MAX_SOURCES:
            break
    if not items:
        return None
    return {"id": "sources", "type": "sources", "items": items}


def header_title(parts: list[dict]) -> str:
    return _part_title(parts[0])


def build_layout(parts: list[dict], *, revision: int, complete: bool) -> dict:
    """Assemble the layout of one answer (2.5, same for one result or many)."""
    title = header_title(parts)
    if len(parts) == 1:
        summary = ""
    else:
        summary = f"{len(parts)} results: " + "; ".join(_part_title(p) for p in parts)
        summary = summary[:MAX_SUMMARY]
    agents: list[dict] = []
    for part in parts:
        name = part["payload"].get("agent")
        if isinstance(name, str) and name and all(a["name"] != name[:80] for a in agents):
            agents.append({"name": name[:80]})
    header: dict[str, Any] = {"id": "h", "type": "header", "title": title, "summary": summary}
    if agents:
        header["agents"] = agents[:MAX_HEADER_AGENTS]
    blocks: list[dict] = [header]
    for k, part in enumerate(parts, 1):
        src = _source(part["payload"])
        for raw in part["blocks"]:
            block = {key: value for key, value in raw.items() if key != "_slot"}
            block = {"id": f"r{k}.{raw['_slot']}", **block}
            if src:
                block["source"] = dict(src)
            blocks.append(block)
    sources = _merged_sources(parts)
    if sources:
        blocks.append(sources)
    return {
        "version": LAYOUT_VERSION,
        "revision": revision,
        "template": parts[0]["template"] if len(parts) == 1 else JOINED_TEMPLATE,
        "title": title,
        "summary": summary,
        "complete": complete,
        "blocks": blocks,
    }


def _ts(payload: dict, now: float) -> float:
    ts = payload.get("ts")
    return float(ts) if type(ts) in (int, float) else now


def legacy_fields(parts: list[dict], layout_title: str, *, now: float | None = None) -> dict:
    """Fallback fields for old clients (contract 1.2 and 1.5 rule 9)."""
    now = time.time() if now is None else now
    if len(parts) == 1:
        out = dict(parts[0]["payload"])
        defaults = {
            "kind": "markdown", "title": "Result",
            "body": parts[0]["body"] if out.get("tool") == "shared_content" else "",
            "images": [], "basemap_images": [], "links": [],
            "agent": "Mortimer", "run_id": None, "ts": now, "surface": "drawer",
        }
        for key, value in defaults.items():
            out.setdefault(key, value)
        return out
    payloads = [p["payload"] for p in parts]
    first_imgs = next((p for p in payloads if p.get("images")), {})
    agents = {p.get("agent") for p in payloads if isinstance(p.get("agent"), str) and p.get("agent")}
    links: list[dict] = []
    seen: set[str] = set()
    for part in parts:
        for link in part["links"]:
            key = str(link.get("url") or link.get("label") or "")
            if key and key not in seen:
                seen.add(key)
                links.append(link)
    return {
        "kind": "markdown",
        "title": layout_title,
        "body": "\n\n".join(f"## {_part_title(p)}\n\n{p['body']}".rstrip() for p in parts),
        "images": list(first_imgs.get("images") or []),
        "basemap_images": list(first_imgs.get("basemap_images") or []),
        "links": links,
        "agent": next(iter(agents)) if len(agents) == 1 else "Mortimer",
        "run_id": payloads[0].get("run_id"),
        "ts": max(_ts(p, now) for p in payloads),
        "surface": "window" if any(p.get("surface") == "window" for p in payloads) else "drawer",
        "tool": "composed_answer",
    }
