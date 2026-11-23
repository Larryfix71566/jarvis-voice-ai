"""Public-source fetch and parse for the daily new-model check (WS-41).

``fetch_public`` reads a fixed allowlist of public pages (HTTPS, no
redirects, no cookies or auth, no proxy environment, 2 MiB cap). The parsers
are pure and never raise on junk input; they return empty results instead.

Best effort: the Anthropic feed, the Anthropic deprecations table and the npm
JSON are parsed against real captured copies. The Codex changelog, the Codex
models page and the Kimi changelog were unreachable from the build container,
so those three parsers are modelled on snippets and synthetic fixtures, are
deliberately lenient, and must be checked against the live pages on the Mac.
"""
from __future__ import annotations

import hashlib
import html
import http.client
import json
import re
import ssl
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Callable
from urllib.parse import urlsplit

from jarvis.model_sync import ids

PUBLIC_SOURCES: dict[str, str] = {
    "anthropic_release_notes": "https://platform.claude.com/docs/en/release-notes/feed.xml",
    "anthropic_deprecations": "https://platform.claude.com/docs/en/about-claude/model-deprecations.md",
    "codex_changelog": "https://learn.chatgpt.com/docs/changelog",
    "codex_models": "https://learn.chatgpt.com/docs/models.md",
    "kimi_changelog": "https://platform.kimi.ai/docs/platform-changelog",
    "npm_claude_code": "https://registry.npmjs.org/@anthropic-ai/claude-code/latest",
    "npm_codex": "https://registry.npmjs.org/@openai/codex/latest",
}

MAX_BYTES = 2 * 1024 * 1024
USER_AGENT = "Mortimer-model-sync/1"


def fetch_public(name: str, *, timeout: float = 10.0) -> str:
    """Fetch one allowlisted public page. No redirects, cookies, auth or proxy env."""
    if name not in PUBLIC_SOURCES:
        raise ValueError("unapproved public source")
    target = urlsplit(PUBLIC_SOURCES[name])
    path = target.path + ("?" + target.query if target.query else "")
    connection = http.client.HTTPSConnection(
        target.hostname, timeout=timeout, context=ssl.create_default_context())
    try:
        connection.request("GET", path, headers={
            "User-Agent": USER_AGENT, "Accept": "text/plain,text/html,application/xml,application/json"})
        response = connection.getresponse()
        if response.status != 200:
            raise ValueError(f"source returned HTTP {response.status}")
        body = response.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise ValueError("source exceeds size limit")
        return body.decode("utf-8", errors="replace")
    finally:
        connection.close()


# --------------------------------------------------------------------------
# text and date helpers
# --------------------------------------------------------------------------

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_MON = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?"
_D_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_D_FULL = re.compile(r"\b(" + _MON + r")\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b")
_D_MD = re.compile(r"\b(" + _MON + r")\s+(\d{1,2})(?:st|nd|rd|th)?\b(?!,?\s*\d{4})")
_BLOCK_TAGS = re.compile(r"</?(?:h[1-6]|p|li|ul|ol|div|br|tr|table|section|article|pre|hr)\b[^>]*>", re.I)
_TAGS = re.compile(r"<[^>]*>")


def _mk(y: int, m: int, d: int) -> str | None:
    try:
        return date(y, m, d).isoformat()
    except ValueError:
        return None


def _month(word: str) -> int | None:
    return _MONTHS.get(word.lower()[:3])


def _find_date(text: str, year: int | None = None) -> str | None:
    """First date in ``text`` as ISO. Month-day without a year needs ``year``."""
    best: tuple[int, str] | None = None
    for rx, kind in ((_D_ISO, "iso"), (_D_FULL, "full"), (_D_MD, "md")):
        for m in rx.finditer(text):
            if kind == "iso":
                v = _mk(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            elif kind == "full":
                mo = _month(m.group(1))
                v = _mk(int(m.group(3)), mo, int(m.group(2))) if mo else None
            else:
                mo = _month(m.group(1))
                v = _mk(year, mo, int(m.group(2))) if (mo and year) else None
            if v and (best is None or m.start() < best[0]):
                best = (m.start(), v)
            if v:
                break
    return best[1] if best else None


def _plain(text: str) -> str:
    """HTML or markdown to plain text with one block per line."""
    if not isinstance(text, str):
        return ""
    text = _BLOCK_TAGS.sub("\n", text)
    text = _TAGS.sub(" ", text)
    text = html.unescape(text)
    text = text.replace("`", "").replace("**", "")
    return text


_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(])")


def _sentences(text: str, default_year: int | None = None):
    """Yield (sentence, heading_date, year_hint). Heading date is the nearest
    preceding line that is only a date."""
    heading: str | None = None
    year = default_year
    for raw in _plain(text).splitlines():
        line = raw.strip()
        if not line:
            continue
        bare = re.sub(r"^[#*\s>\-|]+|[#*\s:|]+$", "", line)
        if len(bare) <= 40:
            d = _find_date(bare, None)
            if d and len(_D_ISO.sub("", _D_FULL.sub("", bare)).strip(" ,.-—")) == 0:
                heading, year = d, int(d[:4])
                continue
        for sent in _SENT_SPLIT.split(line):
            sent = sent.strip()
            if sent:
                yield sent, heading, year


# --------------------------------------------------------------------------
# Anthropic release-notes feed
# ---------------------------------------------------------------------------

_ITEM = re.compile(r"<item\b[^>]*>(.*?)(?:</item>|\Z)", re.S | re.I)
_LAUNCH_WORDS = re.compile(r"launch|now available|introducing", re.I)


def _field(item: str, tag: str) -> str | None:
    m = re.search(r"<%s\b[^>]*>(.*?)(?:</%s>|\Z)" % (tag, tag), item, re.S | re.I)
    if not m:
        return None
    v = m.group(1).strip()
    cd = re.fullmatch(r"<!\[CDATA\[(.*?)(?:\]\]>)?", v, re.S)
    return cd.group(1) if cd else v


def parse_anthropic_feed(xml_text: str) -> list[dict]:
    try:
        return _parse_anthropic_feed(xml_text)
    except Exception:
        return []


def _parse_anthropic_feed(xml_text: str) -> list[dict]:
    if not isinstance(xml_text, str):
        return []
    found: dict[tuple[str, str], str] = {}
    for im in _ITEM.finditer(xml_text):
        item = im.group(1)
        pub = _field(item, "pubDate")
        desc = _field(item, "description")
        if not pub or not desc:
            continue
        try:
            when = parsedate_to_datetime(pub).date().isoformat()
        except (TypeError, ValueError):
            continue
        if "&lt;" in desc:
            desc = html.unescape(desc)
        text = html.unescape(_plain(desc))
        for sent in _SENT_SPLIT.split(text.replace("\n", ". ")):
            for model in ids.find_ids(sent):
                p = ids.parse(model)
                if p is None or p.vendor != "anthropic":
                    continue
                kind = "launch" if _LAUNCH_WORDS.search(sent) else "mention"
                key = (model, kind)
                if key not in found or when < found[key]:
                    found[key] = when
    return [{"model": m, "vendor": "anthropic", "date": d, "kind": k,
             "source": "anthropic_release_notes"}
            for (m, k), d in sorted(found.items(), key=lambda kv: (kv[1], kv[0]), reverse=True)]


# --------------------------------------------------------------------------
# Anthropic deprecations (markdown tables)
# --------------------------------------------------------------------------

def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _clean(cell: str) -> str:
    return cell.replace("`", "").replace("*", "").strip()


def _table_date(cell: str) -> str | None:
    return _find_date(_clean(cell))


def parse_anthropic_deprecations(md_text: str) -> list[dict]:
    try:
        return _parse_anthropic_deprecations(md_text)
    except Exception:
        return []


def _parse_anthropic_deprecations(md_text: str) -> list[dict]:
    if not isinstance(md_text, str):
        return []
    rows: list[dict] = []
    repl: list[tuple[str, str]] = []
    mode: str | None = None
    for line in md_text.splitlines():
        if not line.lstrip().startswith("|"):
            mode = None
            continue
        cells = _cells(line)
        low = [_clean(c).lower() for c in cells]
        if low[:4] == ["api model name", "current state", "deprecated", "tentative retirement date"]:
            mode = "main"
            continue
        if low[:3] == ["retirement date", "deprecated model", "recommended replacement"]:
            mode = "repl"
            continue
        if all(re.fullmatch(r":?-{2,}:?", c.strip()) for c in cells if c.strip()):
            continue
        if mode == "main" and len(cells) >= 4:
            model = _clean(cells[0]).lower()
            state = _clean(cells[1]).lower()
            if not model or not state:
                continue
            retire_cell = _clean(cells[3])
            nst = re.match(r"not sooner than", retire_cell, re.I)
            rows.append({
                "model": model, "state": state,
                "deprecated": _table_date(cells[2]),
                "retirement": None if nst else _table_date(retire_cell),
                "earliest_retirement": _table_date(retire_cell) if nst else None,
                "replacement": None, "source": "anthropic_deprecations"})
        elif mode == "repl" and len(cells) >= 3:
            old = ids.find_ids(cells[1]) or [_clean(cells[1]).lower()]
            new = ids.find_ids(cells[2]) or [_clean(cells[2]).lower()]
            if old[0] and new[0]:
                repl.append((old[0], new[0]))
    for row in rows:
        for old, new in repl:
            if ids.same_model(row["model"], old):
                row["replacement"] = new
                break
    return rows


# --------------------------------------------------------------------------
# OpenAI / Codex
# --------------------------------------------------------------------------

_GPT_NAME = re.compile(
    r"(?i:gpt)-(\d{1,2}(?:\.\d{1,2})?)(?:-([A-Za-z]+(?:-[A-Za-z]+)*))?(?:[ \t]+([A-Z][a-z]+))?")
_EXTRA = re.compile(r"\s*(?:,|,?\s+and|,?\s+&)\s+([A-Z][a-z]+)")
_NAME_STOP = frozenset({
    "The", "And", "Is", "Has", "Now", "In", "For", "With", "Users", "Added", "Is", "As", "On", "To",
    "Are", "Was", "Will", "Can", "Via", "Also", "From", "It", "This", "That", "When", "Retires",
    "Models", "Model", "Default", "Instead", "Support", "Supports", "By", "Or", "Of", "At"})


def _openai_models(sentence: str) -> list[tuple[str, int]]:
    """(model id, position) for each GPT model named in the sentence,
    expanding 'GPT-6.2 Sol and Astra' into both."""
    out: list[tuple[str, int]] = []
    pos = 0
    while True:
        m = _GPT_NAME.search(sentence, pos)
        if not m:
            break
        ver, fam, word = m.group(1), m.group(2), m.group(3)
        end = m.end()
        names: list[str] = []
        if fam:
            names.append("gpt-%s-%s" % (ver, fam.lower()))
            end = m.end(2)
        elif word and word not in _NAME_STOP:
            names.append("gpt-%s-%s" % (ver, word.lower()))
            end = m.end(3)
            while True:
                x = _EXTRA.match(sentence, end)
                if not x or x.group(1) in _NAME_STOP:
                    break
                names.append("gpt-%s-%s" % (ver, x.group(1).lower()))
                end = x.end()
        else:
            names.append("gpt-%s" % ver)
            end = m.end(1)
        for n in names:
            if ids.parse(n) is not None:
                out.append((n, m.start()))
        pos = max(end, m.end(1))
    return out


_RETIRE = re.compile(r"retire|retirement|deprecat", re.I)
_LAUNCH = re.compile(r"added|launch|introduc|now available|default", re.I)
_REPLACEMENT_CTX = re.compile(r"(?:use|to|with|by|recommended|instead of|migrate to|switch to)\s*$", re.I)


def parse_openai_changelog(text: str, *, default_year: int | None = None) -> dict:
    try:
        return _parse_openai_changelog(text, default_year)
    except Exception:
        return {"launches": [], "retirements": []}


def _parse_openai_changelog(text: str, default_year: int | None) -> dict:
    launches: dict[str, dict] = {}
    retirements: dict[str, dict] = {}
    for sent, heading, year in _sentences(text, default_year):
        models = _openai_models(sent)
        if not models:
            continue
        inline = _find_date(sent, year)
        if _RETIRE.search(sent):
            when = inline
            for model, pos in models:
                if _REPLACEMENT_CTX.search(sent[max(0, pos - 20):pos]):
                    continue
                retirements.setdefault(model, {"model": model, "retirement": when,
                                               "source": "codex_changelog"})
        elif _LAUNCH.search(sent):
            when = inline or heading
            for model, _ in models:
                cur = launches.get(model)
                if cur is None or (when and (cur["date"] is None or when < cur["date"])):
                    launches[model] = {"model": model, "vendor": "openai", "date": when,
                                       "kind": "launch", "source": "codex_changelog"}
    return {"launches": list(launches.values()), "retirements": list(retirements.values())}


def parse_openai_models(text: str) -> list[dict]:
    try:
        seen: dict[str, dict] = {}
        for sent, _h, _y in _sentences(text):
            for model, _ in _openai_models(sent):
                seen.setdefault(model, {"model": model, "vendor": "openai", "date": None,
                                        "kind": "listed", "source": "codex_models"})
        return list(seen.values())
    except Exception:
        return []


# --------------------------------------------------------------------------
# Kimi
# --------------------------------------------------------------------------

_KIMI_NAME = re.compile(r"\bKimi[ \t-]+K(\d{1,2}(?:\.\d{1,2})?)(?:[ \t-]+([A-Z][a-z]+))?")
_KIMI_STOP = _NAME_STOP | {"Api", "Cli", "Sdk", "Platform"}


def _kimi_models(sentence: str) -> list[str]:
    out = [m for m in ids.find_ids(sentence.lower())
           if getattr(ids.parse(m), "vendor", None) == "moonshot"]
    for m in _KIMI_NAME.finditer(sentence):
        fam = m.group(2)
        n = "kimi-k%s" % m.group(1)
        if fam and fam not in _KIMI_STOP:
            n += "-" + fam.lower()
        if ids.parse(n) is not None:
            out.append(n)
    return list(dict.fromkeys(out))


def parse_kimi_changelog(text: str, *, default_year: int | None = None) -> list[dict]:
    try:
        found: dict[str, dict] = {}
        for sent, heading, year in _sentences(text, default_year):
            when = _find_date(sent, year) or heading
            for model in _kimi_models(sent):
                cur = found.get(model)
                if cur is None or (when and (cur["date"] is None or when < cur["date"])):
                    found[model] = {"model": model, "vendor": "moonshot", "date": when,
                                    "kind": "launch", "source": "kimi_changelog"}
        return list(found.values())
    except Exception:
        return []


# --------------------------------------------------------------------------
# npm
# --------------------------------------------------------------------------

_SEMVER = re.compile(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?")


def parse_npm_latest(json_text: str) -> str | None:
    try:
        v = json.loads(json_text).get("version")
    except Exception:
        return None
    return v if isinstance(v, str) and _SEMVER.fullmatch(v) else None


# --------------------------------------------------------------------------
# collect
# --------------------------------------------------------------------------

def collect_public(*, fetch: Callable[[str], str] = fetch_public, now: datetime | None = None) -> dict:
    now = (now or datetime.now(timezone.utc))
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    stamp = now.isoformat(timespec="seconds")
    result: dict = {"sources": {}, "launches": [], "deprecations": [],
                    "cli_latest": {"claude": None, "codex": None}}
    launches: list[dict] = []

    for name in PUBLIC_SOURCES:
        entry = {"ok": False, "error": None, "fetched_at": stamp, "sha256": None}
        result["sources"][name] = entry
        try:
            text = fetch(name)
            if not isinstance(text, str):
                raise TypeError("fetch returned non-text")
            entry["sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
            if name == "anthropic_release_notes":
                launches += parse_anthropic_feed(text)
            elif name == "anthropic_deprecations":
                result["deprecations"] += parse_anthropic_deprecations(text)
            elif name == "codex_changelog":
                parsed = parse_openai_changelog(text, default_year=now.year)
                launches += parsed["launches"]
                for r in parsed["retirements"]:
                    result["deprecations"].append({
                        "model": r["model"], "state": "deprecated", "deprecated": None,
                        "retirement": r["retirement"], "earliest_retirement": None,
                        "replacement": None, "source": r["source"]})
            elif name == "codex_models":
                launches += parse_openai_models(text)
            elif name == "kimi_changelog":
                launches += parse_kimi_changelog(text, default_year=now.year)
            elif name == "npm_claude_code":
                result["cli_latest"]["claude"] = parse_npm_latest(text)
            elif name == "npm_codex":
                result["cli_latest"]["codex"] = parse_npm_latest(text)
            entry["ok"] = True
        except Exception as exc:  # one source failing never stops the others
            entry["error"] = f"{type(exc).__name__}: {exc}"[:200]

    best: dict[tuple[str, str], dict] = {}
    for item in launches:
        key = (item["model"], item["source"])
        cur = best.get(key)
        if cur is None or _launch_rank(item) < _launch_rank(cur):
            best[key] = item
    result["launches"] = list(best.values())
    return result


def _launch_rank(item: dict) -> tuple[int, str]:
    return (0 if item.get("kind") == "launch" else 1, item.get("date") or "9999-99-99")
