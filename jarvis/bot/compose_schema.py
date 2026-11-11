"""Composed-answer layout schema: pure validators and size truncation.

Implements the ``layout`` object of the interface contracts (section 1:
envelope fields 1.2, layout 1.3, block kit 1.4, URL rule 1.9, versioning 1.8,
size limits 1.10).  No pipecat, no network, no database.  The composer that
joins results into answers and the templates (contract 1.5 to 1.7) are a
later item and do not live here.

Style follows ``console_protocol``: plain functions over plain dicts.
``validate_layout`` returns a list of problems (empty means valid) so a
caller can log every problem at once; ``require_valid_layout`` raises
``LayoutError`` (a ``ValueError``) for callers that prefer an exception.

The bot-side validator is deliberately STRICTER than the client rules of
1.8: unknown keys and unknown block types are errors here, because the bot
authors every layout from fixed templates and an unknown key means a bug,
not a newer peer.
"""
from __future__ import annotations

import copy
import json
import math
import uuid
from typing import Any
from urllib.parse import urlsplit

from jarvis.bot.console_protocol import ALLOWED_ACTIONS

LAYOUT_VERSION = 1

# 1.10 size limits
MAX_DISPLAY_MESSAGE_BYTES = 1200 * 1024
MAX_LAYOUT_BYTES = 256 * 1024
MAX_ROADMAP_BYTES = 1024 * 1024
MAX_BLOCKS = 24
MAX_TEXT_CHARS = 30_000  # display.DOC_DISPLAY_MAX_CHARS

# 1.3 layout field limits
MAX_TEMPLATE = 40
MAX_TITLE = 120
MAX_SUMMARY = 600
MAX_BLOCK_ID = 40
MAX_A11Y = 300
MAX_URL = 2048

TONES = frozenset({"neutral", "ok", "approval", "error"})
BLOCK_TYPES = frozenset({
    "header", "stats", "list", "chart", "text", "media", "sources", "actions",
    "weather", "brief", "roadmap", "commands", "graph",
})
WRAPPER_FIELDS = {
    "weather": ("weather",),
    "brief": ("brief",),
    "roadmap": ("roadmap", "roadmap_timezone"),
    "commands": ("commands", "note", "expect_output"),
    "graph": ("image_url", "summary"),
}
ACTION_KINDS = frozenset({"ask", "console"})
TEXT_FORMATS = frozenset({"markdown", "plain"})
TRUNCATION_NOTICE = "More results were left out to fit."
TRUNCATION_BLOCK_ID = "truncated"

_LAYOUT_KEYS = frozenset({"version", "revision", "template", "title", "summary", "complete", "blocks"})
_COMMON_BLOCK_KEYS = frozenset({"id", "type", "a11y", "source"})
_BLOCK_KEYS: dict[str, frozenset[str]] = {
    "header": frozenset({"title", "summary", "agents"}),
    "stats": frozenset({"items"}),
    "list": frozenset({"title", "items", "more_count"}),
    "chart": frozenset({"title", "chart", "unit", "points"}),
    "text": frozenset({"format", "text"}),
    "media": frozenset({"images", "basemap_images", "caption"}),
    "sources": frozenset({"items"}),
    "actions": frozenset({"items"}),
    "weather": frozenset({"weather"}),
    "brief": frozenset({"brief"}),
    "roadmap": frozenset({"roadmap", "roadmap_timezone"}),
    "commands": frozenset({"commands", "note", "expect_output"}),
    "graph": frozenset({"image_url", "summary"}),
}
_SOURCE_KEYS = frozenset({"tool", "run_id", "agent"})


class LayoutError(ValueError):
    """Raised by ``require_valid_layout``; ``problems`` lists every issue."""

    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems[:5]) or "invalid layout")
        self.problems = list(problems)


# ---------------------------------------------------------------- helpers

def _is_int(value: Any) -> bool:
    return type(value) is int


def _is_number(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _str(value: Any, lo: int, hi: int) -> bool:
    return isinstance(value, str) and lo <= len(value) <= hi


def sanitize_url(url: Any) -> str | None:
    """Return ``url`` if it is an acceptable link, else None (contract 1.9.5).

    Only ``http`` and ``https`` with a host and no user-info part pass.
    ``file:``, ``data:``, ``javascript:`` and relative references are dropped.
    """
    if not isinstance(url, str) or not url or len(url) > MAX_URL:
        return None
    if any(ord(c) < 0x21 or ord(c) == 0x7F for c in url):
        return None
    try:
        parts = urlsplit(url)
        host = parts.hostname
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https") or not host:
        return None
    if "@" in parts.netloc or parts.username is not None or parts.password is not None:
        return None
    return url


def compact_size(value: Any) -> int:
    """Compact UTF-8 JSON byte size of ``value``."""
    return len(json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def layout_size(layout: dict[str, Any], *, include_wrappers: bool = False) -> int:
    """Byte size of a layout; wrapper data is excluded by default (1.10)."""
    if include_wrappers or not isinstance(layout.get("blocks"), list):
        return compact_size(layout)
    stripped = dict(layout)
    blocks = []
    for block in layout["blocks"]:
        if isinstance(block, dict) and block.get("type") in WRAPPER_FIELDS:
            block = {k: v for k, v in block.items() if k not in WRAPPER_FIELDS[block["type"]]}
        blocks.append(block)
    stripped["blocks"] = blocks
    return compact_size(stripped)


# ------------------------------------------------------------- validation

def _check_keys(obj: dict, allowed: frozenset[str], required: frozenset[str], path: str, errs: list[str]) -> None:
    for key in sorted(set(obj) - allowed):
        errs.append(f"{path}: unknown key {key!r}")
    for key in sorted(required - set(obj)):
        errs.append(f"{path}: missing {key!r}")


def _check_tone(item: dict, path: str, errs: list[str]) -> None:
    if "tone" in item and item["tone"] not in TONES:
        errs.append(f"{path}.tone: not one of {sorted(TONES)}")


def _check_source(source: Any, path: str, errs: list[str]) -> None:
    if not isinstance(source, dict):
        errs.append(f"{path}: must be an object")
        return
    for key in sorted(set(source) - _SOURCE_KEYS):
        errs.append(f"{path}: unknown key {key!r}")
    limits = {"tool": 80, "run_id": 120, "agent": 80}
    for key, value in source.items():
        if key in limits and not _str(value, 0, limits[key]):
            errs.append(f"{path}.{key}: must be a string of at most {limits[key]}")


def _items(block: dict, path: str, lo: int, hi: int, errs: list[str]) -> list[dict]:
    items = block.get("items")
    if not isinstance(items, list) or not lo <= len(items) <= hi:
        errs.append(f"{path}.items: must be a list of {lo} to {hi}")
        return []
    good = []
    for i, item in enumerate(items):
        if isinstance(item, dict):
            good.append((i, item))
        else:
            errs.append(f"{path}.items[{i}]: must be an object")
    return good


def _url_list(block: dict, key: str, path: str, lo: int, errs: list[str]) -> None:
    urls = block.get(key, [] if lo == 0 else None)
    if not isinstance(urls, list) or not lo <= len(urls) <= 9:
        errs.append(f"{path}.{key}: must be a list of {lo} to 9 URLs")
        return
    for i, url in enumerate(urls):
        if sanitize_url(url) is None:
            errs.append(f"{path}.{key}[{i}]: not an acceptable http(s) URL")


def _validate_block(block: Any, index: int, errs: list[str]) -> None:
    path = f"blocks[{index}]"
    if not isinstance(block, dict):
        errs.append(f"{path}: must be an object")
        return
    btype = block.get("type")
    if btype not in BLOCK_TYPES:
        errs.append(f"{path}.type: unknown block type")
        return
    allowed = _COMMON_BLOCK_KEYS | _BLOCK_KEYS[btype]
    required = {"id", "type"}
    if btype in ("chart", "media"):
        required.add("a11y")
    if btype in ("stats", "sources", "actions"):
        required.add("items")
    if btype == "list":
        required.update({"items"})
    if btype == "header":
        required.update({"title", "summary"})
    if btype == "chart":
        required.update({"chart", "points"})
    if btype == "text":
        required.update({"format", "text"})
    if btype == "media":
        required.add("images")
    if btype in WRAPPER_FIELDS:
        required.add(WRAPPER_FIELDS[btype][0])
    _check_keys(block, allowed, frozenset(required), path, errs)
    if "id" in block and not _str(block["id"], 1, MAX_BLOCK_ID):
        errs.append(f"{path}.id: must be a string of 1 to {MAX_BLOCK_ID}")
    if "a11y" in block and not _str(block["a11y"], 1 if btype in ("chart", "media") else 0, MAX_A11Y):
        errs.append(f"{path}.a11y: must be a string of at most {MAX_A11Y}")
    if "source" in block:
        _check_source(block["source"], f"{path}.source", errs)

    if btype == "header":
        if not _str(block.get("title"), 1, MAX_TITLE):
            errs.append(f"{path}.title: must be a string of 1 to {MAX_TITLE}")
        if not _str(block.get("summary"), 0, MAX_SUMMARY):
            errs.append(f"{path}.summary: must be a string of at most {MAX_SUMMARY}")
        agents = block.get("agents", [])
        if not isinstance(agents, list) or len(agents) > 6:
            errs.append(f"{path}.agents: must be a list of at most 6")
        else:
            for i, agent in enumerate(agents):
                ap = f"{path}.agents[{i}]"
                if not isinstance(agent, dict):
                    errs.append(f"{ap}: must be an object")
                    continue
                _check_keys(agent, frozenset({"name", "latency_ms"}), frozenset({"name"}), ap, errs)
                if not _str(agent.get("name"), 1, 80):
                    errs.append(f"{ap}.name: must be a string of 1 to 80")
                if "latency_ms" in agent and not (_is_int(agent["latency_ms"]) and agent["latency_ms"] >= 0):
                    errs.append(f"{ap}.latency_ms: must be an integer >= 0")
    elif btype == "stats":
        for i, item in _items(block, path, 1, 4, errs):
            ip = f"{path}.items[{i}]"
            _check_keys(item, frozenset({"value", "label", "tone"}), frozenset({"value", "label"}), ip, errs)
            if not _str(item.get("value"), 1, 16):
                errs.append(f"{ip}.value: must be a string of 1 to 16")
            if not _str(item.get("label"), 1, 60):
                errs.append(f"{ip}.label: must be a string of 1 to 60")
            _check_tone(item, ip, errs)
    elif btype == "list":
        if "title" in block and not _str(block["title"], 1, MAX_TITLE):
            errs.append(f"{path}.title: must be a string of 1 to {MAX_TITLE}")
        for i, item in _items(block, path, 1, 12, errs):
            ip = f"{path}.items[{i}]"
            _check_keys(item, frozenset({"title", "detail", "meta", "tone"}), frozenset({"title"}), ip, errs)
            if not _str(item.get("title"), 1, MAX_TITLE):
                errs.append(f"{ip}.title: must be a string of 1 to {MAX_TITLE}")
            if "detail" in item and not _str(item["detail"], 0, 240):
                errs.append(f"{ip}.detail: must be a string of at most 240")
            if "meta" in item and not _str(item["meta"], 0, 40):
                errs.append(f"{ip}.meta: must be a string of at most 40")
            _check_tone(item, ip, errs)
        if "more_count" in block and not (_is_int(block["more_count"]) and block["more_count"] >= 0):
            errs.append(f"{path}.more_count: must be an integer >= 0")
    elif btype == "chart":
        if "title" in block and not _str(block["title"], 1, MAX_TITLE):
            errs.append(f"{path}.title: must be a string of 1 to {MAX_TITLE}")
        if block.get("chart") != "bar":
            errs.append(f"{path}.chart: only 'bar' is defined in v1")
        if "unit" in block and not _str(block["unit"], 0, 16):
            errs.append(f"{path}.unit: must be a string of at most 16")
        points = block.get("points")
        if not isinstance(points, list) or not 2 <= len(points) <= 48:
            errs.append(f"{path}.points: must be a list of 2 to 48")
        else:
            for i, point in enumerate(points):
                pp = f"{path}.points[{i}]"
                if not isinstance(point, dict):
                    errs.append(f"{pp}: must be an object")
                    continue
                _check_keys(point, frozenset({"label", "value", "highlight"}), frozenset({"label", "value"}), pp, errs)
                if not _str(point.get("label"), 1, 16):
                    errs.append(f"{pp}.label: must be a string of 1 to 16")
                if not _is_number(point.get("value")):
                    errs.append(f"{pp}.value: must be a finite number")
                if "highlight" in point and type(point["highlight"]) is not bool:
                    errs.append(f"{pp}.highlight: must be a boolean")
    elif btype == "text":
        if block.get("format") not in TEXT_FORMATS:
            errs.append(f"{path}.format: must be 'markdown' or 'plain'")
        if not _str(block.get("text"), 0, MAX_TEXT_CHARS):
            errs.append(f"{path}.text: must be a string of at most {MAX_TEXT_CHARS}")
    elif btype == "media":
        _url_list(block, "images", path, 1, errs)
        if "basemap_images" in block:
            _url_list(block, "basemap_images", path, 0, errs)
        if "caption" in block and not _str(block["caption"], 0, 240):
            errs.append(f"{path}.caption: must be a string of at most 240")
    elif btype == "sources":
        for i, item in _items(block, path, 1, 12, errs):
            ip = f"{path}.items[{i}]"
            _check_keys(item, frozenset({"label", "url"}), frozenset({"label"}), ip, errs)
            if not _str(item.get("label"), 1, 120):
                errs.append(f"{ip}.label: must be a string of 1 to 120")
            if "url" in item and sanitize_url(item["url"]) is None:
                errs.append(f"{ip}.url: not an acceptable http(s) URL")
    elif btype == "actions":
        for i, item in _items(block, path, 1, 4, errs):
            ip = f"{path}.items[{i}]"
            kind = item.get("kind")
            extra = {"ask": {"text"}, "console": {"action", "target", "args"}}.get(kind, set())
            _check_keys(item, frozenset({"id", "label", "kind"} | extra), frozenset({"id", "label", "kind"}), ip, errs)
            if not _str(item.get("id"), 1, MAX_BLOCK_ID):
                errs.append(f"{ip}.id: must be a string of 1 to {MAX_BLOCK_ID}")
            if not _str(item.get("label"), 1, 40):
                errs.append(f"{ip}.label: must be a string of 1 to 40")
            if kind not in ACTION_KINDS:
                errs.append(f"{ip}.kind: must be 'ask' or 'console'")
            elif kind == "ask":
                if not _str(item.get("text"), 1, 400):
                    errs.append(f"{ip}.text: must be a string of 1 to 400")
            else:
                action = item.get("action")
                if action not in ALLOWED_ACTIONS:
                    errs.append(f"{ip}.action: not an allowed console action")
                if "target" in item and not _str(item["target"], 1, 200):
                    errs.append(f"{ip}.target: must be a string of 1 to 200")
                if "args" in item and not isinstance(item["args"], dict):
                    errs.append(f"{ip}.args: must be an object")
    elif btype in ("weather", "brief", "roadmap"):
        if not isinstance(block.get(btype), dict):
            errs.append(f"{path}.{btype}: must be an object")
        if btype == "roadmap":
            if "roadmap_timezone" in block and not _str(block["roadmap_timezone"], 1, 80):
                errs.append(f"{path}.roadmap_timezone: must be a string of 1 to 80")
            if isinstance(block.get("roadmap"), dict) and compact_size(block["roadmap"]) > MAX_ROADMAP_BYTES:
                errs.append(f"{path}.roadmap: larger than {MAX_ROADMAP_BYTES} bytes")
    elif btype == "commands":
        if not isinstance(block.get("commands"), list):
            errs.append(f"{path}.commands: must be a list")
        if "note" in block and not _str(block["note"], 0, MAX_SUMMARY):
            errs.append(f"{path}.note: must be a string of at most {MAX_SUMMARY}")
        if "expect_output" in block and type(block["expect_output"]) is not bool:
            errs.append(f"{path}.expect_output: must be a boolean")
    elif btype == "graph":
        if sanitize_url(block.get("image_url")) is None:
            errs.append(f"{path}.image_url: not an acceptable http(s) URL")
        if "summary" in block and not _str(block["summary"], 0, MAX_SUMMARY):
            errs.append(f"{path}.summary: must be a string of at most {MAX_SUMMARY}")


def validate_layout(layout: Any) -> list[str]:
    """Return every problem with ``layout`` (contract 1.3, 1.4, 1.10).

    An empty list means valid.  Never raises on malformed input.
    """
    errs: list[str] = []
    if not isinstance(layout, dict):
        return ["layout: must be an object"]
    _check_keys(layout, _LAYOUT_KEYS, _LAYOUT_KEYS, "layout", errs)
    if "version" in layout and not (_is_int(layout["version"]) and layout["version"] == LAYOUT_VERSION):
        errs.append(f"layout.version: must be {LAYOUT_VERSION}")
    if "revision" in layout and not (_is_int(layout["revision"]) and layout["revision"] >= 1):
        errs.append("layout.revision: must be an integer >= 1")
    if "template" in layout and not _str(layout["template"], 1, MAX_TEMPLATE):
        errs.append(f"layout.template: must be a string of 1 to {MAX_TEMPLATE}")
    if "title" in layout and not _str(layout["title"], 1, MAX_TITLE):
        errs.append(f"layout.title: must be a string of 1 to {MAX_TITLE}")
    if "summary" in layout and not _str(layout["summary"], 0, MAX_SUMMARY):
        errs.append(f"layout.summary: must be a string of at most {MAX_SUMMARY}")
    if "complete" in layout and type(layout["complete"]) is not bool:
        errs.append("layout.complete: must be a boolean")
    blocks = layout.get("blocks")
    if "blocks" in layout:
        if not isinstance(blocks, list) or not 1 <= len(blocks) <= MAX_BLOCKS:
            errs.append(f"layout.blocks: must be a list of 1 to {MAX_BLOCKS}")
        if isinstance(blocks, list) and blocks:
            seen: set[str] = set()
            for i, block in enumerate(blocks):
                _validate_block(block, i, errs)
                if isinstance(block, dict):
                    bid = block.get("id")
                    if isinstance(bid, str):
                        if bid in seen:
                            errs.append(f"blocks[{i}].id: duplicate id {bid!r}")
                        seen.add(bid)
                    if block.get("type") == "header" and i != 0:
                        errs.append(f"blocks[{i}]: a header must be the first block")
            headers = sum(1 for b in blocks if isinstance(b, dict) and b.get("type") == "header")
            if headers > 1:
                errs.append("layout.blocks: at most one header")
    if errs:
        return errs
    try:
        if layout_size(layout) > MAX_LAYOUT_BYTES:
            errs.append(f"layout: larger than {MAX_LAYOUT_BYTES} bytes without wrapper data")
    except (TypeError, ValueError):
        errs.append("layout: not JSON serialisable")
    return errs


def require_valid_layout(layout: Any) -> dict[str, Any]:
    """Raise ``LayoutError`` unless ``layout`` is valid; return it."""
    problems = validate_layout(layout)
    if problems:
        raise LayoutError(problems)
    return layout


def validate_envelope(payload: Any) -> list[str]:
    """Check the envelope fields of a display payload (contract 1.2, 1.9).

    ``layout`` and ``answer_id`` travel together: both or neither.  A payload
    that carries a layout must still carry the legacy ``kind``, ``title`` and
    ``body`` strings (1.2, 1.8).
    """
    if not isinstance(payload, dict):
        return ["display: must be an object"]
    has_layout, has_id = "layout" in payload, "answer_id" in payload
    if not has_layout and not has_id:
        return []
    errs: list[str] = []
    if has_layout != has_id:
        errs.append("display: layout and answer_id must be sent together")
    if has_id:
        aid = payload["answer_id"]
        try:
            uuid.UUID(aid if isinstance(aid, str) else "")
        except ValueError:
            errs.append("display.answer_id: must be a UUID")
    if has_layout:
        errs.extend(validate_layout(payload["layout"]))
        for key in ("kind", "title", "body"):
            if not isinstance(payload.get(key), str):
                errs.append(f"display.{key}: legacy field must be a string")
    return errs


# ------------------------------------------------------ URL sanitising

def sanitize_layout_urls(layout: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``layout`` with unacceptable URLs dropped (1.9.5).

    Source links lose their ``url``; media images are filtered and a media or
    graph block left with nothing to show is removed.  The input is not
    modified.  The result may need re-validation (it can have zero blocks).
    """
    out = copy.deepcopy(layout)
    kept = []
    for block in out.get("blocks", []):
        if not isinstance(block, dict):
            kept.append(block)
            continue
        btype = block.get("type")
        if btype == "sources":
            for item in block.get("items", []):
                if isinstance(item, dict) and "url" in item and sanitize_url(item["url"]) is None:
                    del item["url"]
        elif btype == "media":
            for key in ("images", "basemap_images"):
                if isinstance(block.get(key), list):
                    block[key] = [u for u in block[key] if sanitize_url(u) is not None]
            if not block.get("images"):
                continue
        elif btype == "graph" and sanitize_url(block.get("image_url")) is None:
            continue
        kept.append(block)
    out["blocks"] = kept
    return out


# ----------------------------------------------------------- truncation

def truncate_layout(layout: dict[str, Any], *,
                    max_bytes: int = MAX_LAYOUT_BYTES,
                    envelope_bytes: int = 0,
                    max_message_bytes: int = MAX_DISPLAY_MESSAGE_BYTES) -> dict[str, Any] | None:
    """Fit ``layout`` to the size limits of contract 1.10, or return None.

    ``envelope_bytes`` is the compact size of the rest of the display message
    (legacy fields included) so the 1,200 KiB whole-message ceiling can be
    honoured.  A layout that already fits is returned as an unchanged copy.
    Otherwise trailing blocks are dropped one at a time and a last ``text``
    block, "More results were left out to fit.", is appended.  Wrapper data is
    never cut.  None means the caller must send the legacy payload with no
    ``layout``; it is also returned for a layout that is invalid for any
    reason other than size.
    """
    def fits(candidate: dict[str, Any]) -> bool:
        return (layout_size(candidate) <= max_bytes and
                envelope_bytes + compact_size(candidate) <= max_message_bytes)

    if not isinstance(layout, dict) or not isinstance(layout.get("blocks"), list):
        return None
    # Only size and block-count problems may be cured by dropping blocks.
    problems = validate_layout(layout)
    structural = [p for p in problems
                  if "larger than" not in p and not p.startswith("layout.blocks: must be a list of")]
    if structural or (problems and not layout["blocks"]):
        return None
    if not problems and fits(layout):
        return copy.deepcopy(layout)
    blocks = layout["blocks"]
    for keep in range(min(len(blocks) - 1, MAX_BLOCKS - 1), 0, -1):
        candidate = copy.deepcopy(layout)
        candidate["blocks"] = copy.deepcopy(blocks[:keep]) + [{
            "id": TRUNCATION_BLOCK_ID, "type": "text", "format": "plain", "text": TRUNCATION_NOTICE,
        }]
        if any(b.get("id") == TRUNCATION_BLOCK_ID for b in blocks[:keep]):
            candidate["blocks"][-1]["id"] = TRUNCATION_BLOCK_ID + "-2"
        if not validate_layout(candidate) and fits(candidate):
            return candidate
    return None
