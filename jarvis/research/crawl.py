"""Tavily /crawl client + digest assembly for site research & comparison.

Pure logic (MORTIMER_SITE_RESEARCH_AND_COMPARISON_PLAN.md R1-R5, R9):
no DB, no pipecat, an INJECTED httpx client so this is unit-testable with
zero network — same discipline as every other logic.py in this repo.

R2 — crawl bounds are config, never model-chosen, and are clamped TWICE:
once against config/research.yaml (a typo guard) and once against
RESEARCH_HARD_PAGE_CAP (a model/config-can't-widen-spend guard). Two
independent bounds because a config typo is a plausible accident and an
unbounded crawl is not recoverable after the fact.

R3 — `instructions` is ALWAYS sent, because Tavily only unlocks
`chunks_per_source` (the thing that caps page content) when instructions
are present. Omitting instructions when the user names no focus would
silently take the uncapped path — so a neutral default is used instead of
omitting the field.

R9 — Tavily's own error taxonomy is preserved rather than collapsed into
one generic failure, mirroring jarvis/keyhealth.py's rejected/unfunded/
unreachable discipline: 432/433 (plan/PayGo credit limit) is a BUDGET
problem naming the limit; 429 is a RATE problem (retry later, not a
config issue); 401/403/400 are INVALID (bad key, bad URL, not supported);
5xx and network/timeout errors are UNREACHABLE (Tavily's own outage, not
ours). One site's failure never sinks the other (§0/R9) — crawl_site
returns a per-site result dict, never raises for an ordinary API failure.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx
import yaml

TAVILY_CRAWL_URL = "https://api.tavily.com/crawl"
TAVILY_API_KEY_ENV = "TAVILY_API_KEY"

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "research.yaml"

# R2 — the hard cap the model and a config typo both bounce off. Not the
# same number as config's own `limit` (40): this is the ceiling that
# clamps whatever config says, so raising config past this silently does
# nothing until this constant is deliberately changed too.
RESEARCH_HARD_PAGE_CAP = 60

# R3 — used when the user (or the analyst, on their behalf) names no
# specific comparison angle. Never omit `instructions` instead of falling
# back to this: omitting it disables chunking entirely (§0.2).
DEFAULT_FOCUS = "Identify what this site offers, who it is for, and what distinguishes it"

# Per-chunk cap Tavily documents for chunks_per_source (500 chars each);
# used only to keep a defensively-truncated title/content read legible if
# a future response ever exceeds it.
_TITLE_MAX_CHARS = 120


def load_research_config(path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    """Load config/research.yaml. A missing file falls back to the same
    defaults the file ships with, so a fresh checkout without the file
    still behaves — this mirrors load_model_registry's missing-file
    fallback in jarvis/agents/upgrade_agent.py."""
    p = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    defaults = {
        "max_depth": 2,
        "max_breadth": 20,
        "limit": 40,
        "extract_depth": "basic",
        "chunks_per_source": 3,
        "timeout_s": 120,
        "max_sites": 2,
    }
    if not p.exists():
        return defaults
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    defaults.update({k: v for k, v in data.items() if k in defaults})
    return defaults


class TavilyCrawlClient:
    """Duck-typed httpx.Client wrapper, matching mcp_selfedit.logic.
    AdminClient's seam-for-tests convention. `post` returns
    (status_code, json_body_or_None)."""

    def __init__(self, timeout: float = 150.0):
        self._client = httpx.Client(timeout=timeout)

    def post(self, url: str, headers: dict, json: dict) -> tuple[int, dict | None]:
        try:
            resp = self._client.post(url, headers=headers, json=json)
        except httpx.TimeoutException:
            return (0, None)  # 0 is this module's sentinel for "no response at all"
        except httpx.HTTPError:
            return (-1, None)  # -1: transport-level failure, not an HTTP status
        try:
            body = resp.json()
        except ValueError:
            body = None
        return (resp.status_code, body)


# R9 — status code -> taxonomy. Anything not listed here (a genuinely
# unexpected code) is treated as unreachable rather than invalid: an
# unrecognized failure should not be reported as "your input was wrong".
_BUDGET_CODES = {432, 433}
_RATE_CODES = {429}
_INVALID_CODES = {400, 401, 403}


def _classify_status(status: int) -> str:
    if status in _BUDGET_CODES:
        return "budget"
    if status in _RATE_CODES:
        return "rate"
    if status in _INVALID_CODES:
        return "invalid"
    if status in (0, -1) or status >= 500:
        return "unreachable"
    return "unreachable"


def _extract_error_message(body: dict | None, status: int) -> str:
    if isinstance(body, dict):
        detail = body.get("detail")
        if isinstance(detail, dict) and detail.get("error"):
            return str(detail["error"])
        if body.get("error"):
            return str(body["error"])
    return f"HTTP {status}" if status > 0 else "no response (timeout or connection failure)"


def _derive_title(url: str, raw_content: str) -> str:
    """Tavily's /crawl response has no separate title field (only `url`
    and `raw_content`) — the first non-empty line of the content is the
    closest thing to a page title and is what every real page's markdown
    extraction leads with."""
    for line in (raw_content or "").splitlines():
        stripped = line.strip().lstrip("#").strip()
        if stripped:
            return stripped[:_TITLE_MAX_CHARS]
    return url


def crawl_site(
    client: TavilyCrawlClient,
    url: str,
    focus: str,
    api_key: str,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Crawl one site. Never raises for an ordinary API failure (R9) — the
    caller (the sidecar's background job) is responsible for producing a
    partial comparison when one site fails, never an all-or-nothing one.

    Returns either:
      {"ok": True, "url", "pages": [{"url","title","content"}, ...],
       "credits", "page_count"}
      {"ok": False, "url", "error", "error_kind"}
    """
    cfg = config or load_research_config()
    instructions = (focus or "").strip() or DEFAULT_FOCUS
    # R2 — double clamp: config's own limit, then the hard cap regardless
    # of what config says.
    limit = min(int(cfg.get("limit", 40)), RESEARCH_HARD_PAGE_CAP)

    payload = {
        "url": url,
        "instructions": instructions,  # R3 — always present
        "chunks_per_source": int(cfg.get("chunks_per_source", 3)),
        "max_depth": int(cfg.get("max_depth", 2)),
        "max_breadth": int(cfg.get("max_breadth", 20)),
        "limit": limit,
        "extract_depth": cfg.get("extract_depth", "basic"),
        "timeout": float(cfg.get("timeout_s", 120)),
        "include_usage": True,  # R8 — cost is reported, every time
    }
    status, body = client.post(
        TAVILY_CRAWL_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json=payload,
    )
    if status != 200:
        return {
            "ok": False,
            "url": url,
            "error": _extract_error_message(body, status),
            "error_kind": _classify_status(status),
        }
    if not isinstance(body, dict):
        return {"ok": False, "url": url, "error": "malformed response", "error_kind": "unreachable"}

    results = body.get("results") or []
    pages = [
        {
            "url": r.get("url", ""),
            "title": _derive_title(r.get("url", ""), r.get("raw_content", "")),
            "content": r.get("raw_content", ""),
        }
        for r in results
        if r.get("url")
    ]
    credits = (body.get("usage") or {}).get("credits", 0) or 0
    if not pages:
        return {
            "ok": False, "url": url,
            "error": "the crawl completed but found no pages",
            "error_kind": "empty",
        }
    return {
        "ok": True, "url": url, "pages": pages,
        "credits": credits, "page_count": len(pages),
    }


def build_site_digest(site_result: dict[str, Any]) -> str:
    """R5 — the deterministic, code-assembled digest for ONE site: what
    the model is allowed to know about this crawl. The model never sees
    raw HTTP responses, credit accounting internals, or anything the
    crawler did beyond what's rendered here."""
    if not site_result.get("ok"):
        return (
            f"### {site_result.get('url', '(unknown)')}\n"
            f"CRAWL FAILED ({site_result.get('error_kind', 'unknown')}): "
            f"{site_result.get('error', 'unknown error')}\n"
        )
    lines = [f"### {site_result['url']} ({site_result['page_count']} pages crawled)"]
    for page in site_result.get("pages", []):
        lines.append(f"\n**{page['title']}** — {page['url']}\n{page['content']}")
    return "\n".join(lines)


def assemble_digests(site_a: dict[str, Any], site_b: dict[str, Any]) -> str:
    """R5 — both sites' digests, concatenated, for the RESEARCH_PROMPT's
    {digests} slot. Order matches the URLs the user gave, so "Site A" in
    the prompt always means the first URL named."""
    return build_site_digest(site_a) + "\n\n" + build_site_digest(site_b)


def total_credits(*site_results: dict[str, Any]) -> int:
    """R8 — summed across whichever sites actually returned usage; a
    failed crawl (no `credits` key) contributes 0, never an error."""
    return sum(int(r.get("credits") or 0) for r in site_results)
