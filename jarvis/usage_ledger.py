"""usage_ledger.py — per-call LLM usage ledger for Mortimer.

Drop into jarvis/. One integration point: call record_call() wherever the
LLM client factory returns a completion. Adapters below normalize
Anthropic / OpenAI / OpenRouter response shapes.

Design decisions (agreed 2026-09-01):
- SQLite at data/costs.db (billing-period queries are a DB workload)
- Raw token counts always stored; computed_cost derived from a versioned
  price map (config/model_prices.yaml) so provider price changes are a
  config edit with an effective date, not a code change
- OpenRouter reported cost stored as ground truth when present
- Calendar-month billing periods

Rev 3 (2026-09-01, conflict resolution):
- WAL + busy_timeout on every connection (two writer PROCESSES from day
  one: bot and admin sidecar — see _conn()).
- DB/price-map paths anchored to the repo root, not CWD.
- Rung names are a closed vocabulary (RUNGS below) so cost_report.py's
  sub-agent vs background vs planner/executor split is not a guess:
    voice/dispatch : supervisor, scheduler, librarian, analyst, systems,
                     developer
    background     : memory_merge, memory_classify, memory_extraction,
                     kb_digest, procedures_describe
    planner        : planning (draft_candidates + single-mode plan
                     author), council (E1/E2/E3 escalation rounds)
    executor       : selfedit_executor, appbuild_executor (UpgradeAgent /
                     AppBuildAgent edit loop — the sidecar's own
                     completion calls, previously left UNPATCHED)
    other          : research (site-comparison writer)
"""

from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

try:
    import yaml  # PyYAML, already a dependency via config loading
except ImportError:  # pragma: no cover
    yaml = None

RUNGS = frozenset({
    "supervisor", "scheduler", "librarian", "analyst", "systems", "developer",
    "memory_merge", "memory_classify", "memory_extraction", "kb_digest",
    "procedures_describe",
    "planning", "council",
    "selfedit_executor", "appbuild_executor",
    "research",
})

# Rev 3 (2026-09-01): anchored to the repo root from this module's own
# __file__, never the process CWD — the ledger is written from TWO
# processes (bot :7860 and admin sidecar :7861) started by different
# scripts, and a CWD-relative "data/costs.db" would silently give each
# its own file. Same pattern jarvis/repo_map.py uses. Env override kept.
_REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("JARVIS_COSTS_DB") or _REPO_ROOT / "data" / "costs.db")
PRICE_MAP_PATH = Path(os.environ.get("JARVIS_PRICE_MAP")
                      or _REPO_ROOT / "config" / "model_prices.yaml")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS llm_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,                 -- ISO8601 UTC
    month TEXT NOT NULL,              -- 'YYYY-MM' (calendar billing period)
    session_id TEXT,
    rung TEXT NOT NULL,               -- supervisor|extraction|sweep_merge|council|developer|...
    provider TEXT NOT NULL,           -- anthropic|openai|openrouter|local
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cache_write_tokens INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens INTEGER NOT NULL DEFAULT 0,
    reported_cost REAL,               -- provider-reported USD (OpenRouter); NULL for native
    computed_cost REAL,               -- from price map; NULL if model missing from map
    gen_id TEXT                       -- OpenRouter generation id, for later enrichment
);
CREATE INDEX IF NOT EXISTS idx_calls_month ON llm_calls (month);
CREATE INDEX IF NOT EXISTS idx_calls_rung ON llm_calls (month, rung);
CREATE INDEX IF NOT EXISTS idx_calls_model ON llm_calls (month, provider, model);
"""

_lock = threading.Lock()
_price_map_cache: Optional[dict] = None


# ---------------------------------------------------------------- price map

def load_price_map(force: bool = False) -> dict:
    """Load config/model_prices.yaml. Cached; force=True to reload."""
    global _price_map_cache
    if _price_map_cache is not None and not force:
        return _price_map_cache
    if yaml is None or not PRICE_MAP_PATH.exists():
        _price_map_cache = {"models": {}}
        return _price_map_cache
    with open(PRICE_MAP_PATH, "r", encoding="utf-8") as f:
        _price_map_cache = yaml.safe_load(f) or {"models": {}}
    return _price_map_cache


def compute_cost(provider: str,
                 model: str,
                 input_tokens: int,
                 output_tokens: int,
                 cache_write_tokens: int = 0,
                 cache_read_tokens: int = 0) -> Optional[float]:
    """USD cost from the price map. Returns None (not 0) when the model is
    unmapped — an unmapped model must show up as a gap in reports, never as
    free. input_tokens here means UNCACHED input (see adapters).

    Keyed as "{provider}/{model}", built here rather than trusted from the
    caller — confirmed 2026-09-01 that base.py stores only the bare wire
    string (profile["model"], e.g. "claude-opus-5") while council.py has
    profile["identity"] (vendor-prefixed, e.g. "anthropic/claude-opus-5")
    available. Keying by bare model alone would let the same model reached
    two different ways collide under one price row with only one of the
    two actual rates. provider comes from provider_from_base_url() or
    profile["provider"] — either way it's the real route, not a filename."""
    key = f"{provider}/{model}"
    entry = load_price_map().get("models", {}).get(key)
    if not entry:
        return None
    in_rate = entry.get("input_per_m", 0.0) / 1_000_000
    out_rate = entry.get("output_per_m", 0.0) / 1_000_000
    cw_mult = entry.get("cache_write_mult", 1.25)
    cr_mult = entry.get("cache_read_mult", 0.10)
    return (
        input_tokens * in_rate
        + cache_write_tokens * in_rate * cw_mult
        + cache_read_tokens * in_rate * cr_mult
        + output_tokens * out_rate
    )


# ---------------------------------------------------------------- ledger

def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Rev 3: WAL + busy_timeout from day one, not "when a future concurrent
    # writer appears". There are two writers from the FIRST council round:
    # council.py/upgrade_agent.py run inside the admin sidecar process,
    # every other call site runs inside the bot process. `_lock` below only
    # serializes threads WITHIN one process; cross-process safety is
    # SQLite's job, and WAL is what lets the sidecar's INSERT and the bot's
    # INSERT (and costs_api's reads) overlap without SQLITE_BUSY. WAL is
    # persistent per database file, so setting it on every connect is
    # idempotent and costs nothing.
    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.executescript(_SCHEMA)
    return conn


def record_call(rung: str,
                provider: str,
                model: str,
                input_tokens: int = 0,
                output_tokens: int = 0,
                cache_write_tokens: int = 0,
                cache_read_tokens: int = 0,
                reported_cost: Optional[float] = None,
                gen_id: Optional[str] = None,
                session_id: Optional[str] = None,
                ts: Optional[datetime] = None) -> None:
    """Write one call to the ledger. Never raises — cost logging must not
    take down the pipeline. Failures go to stderr."""
    try:
        if rung not in RUNGS:
            # Unknown rung: still record (never lose a row over a label),
            # but say so once — cost_report.py buckets by this vocabulary.
            import sys
            print(f"usage_ledger: unknown rung {rung!r} (not in RUNGS)",
                  file=sys.stderr)
        ts = ts or datetime.now(timezone.utc)
        month = ts.strftime("%Y-%m")
        computed = compute_cost(provider, model, input_tokens, output_tokens,
                                cache_write_tokens, cache_read_tokens)
        with _lock, _conn() as conn:
            conn.execute(
                "INSERT INTO llm_calls (ts, month, session_id, rung, provider,"
                " model, input_tokens, output_tokens, cache_write_tokens,"
                " cache_read_tokens, reported_cost, computed_cost, gen_id)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (ts.isoformat(), month, session_id, rung, provider, model,
                 input_tokens, output_tokens, cache_write_tokens,
                 cache_read_tokens, reported_cost, computed, gen_id),
            )
    except Exception as exc:  # pragma: no cover
        import sys
        print(f"usage_ledger: record failed: {exc}", file=sys.stderr)


# ---------------------------------------------------------------- adapter
#
# jarvis-voice-ai-clean confirmed (2026-09-01): every profile — direct
# Anthropic, direct Moonshot, and OpenRouter — is reached through the SAME
# AsyncOpenAI client class, just pointed at a different base_url. There is
# no native Anthropic Messages API client anywhere in this repo. That means
# every response has the same OpenAI-wire `usage` shape regardless of which
# vendor actually answered — one adapter, not three.
#
# PROVIDER LABEL comes from what construction already resolved (an
# api_key_env / model_profile match), never guessed from the SDK class,
# since there's only one class. Pass it in explicitly from the call site —
# see PROVIDER_BY_KEY_ENV below for the mapping used at base.py's call site.
#
# CACHE FIELDS ARE UNVERIFIED THROUGH THIS PATH. OpenAI's own API reports
# prompt_tokens_details.cached_tokens; whether Anthropic's and Moonshot's
# OpenAI-compatible endpoints populate that same field (or any cache field
# at all) when hit via chat.completions.create is not yet confirmed for
# this deployment — same class of risk as the OpenRouter+Claude caching
# passthrough gap, now potentially affecting the direct claude-opus
# (developer) rung too. This adapter checks a short list of known aliases
# and otherwise reports zero rather than guessing — a persistent zero on a
# cached session is the signal to inspect the raw response, not proof
# caching failed. Set JARVIS_DEBUG_USAGE_LEDGER=1 to print the raw usage
# object once per call site so the actual shape can be eyeballed per
# provider before trusting the cache columns.

def provider_from_base_url(base_url: str) -> str:
    """Derive the real provider from the live client's base_url rather than
    from an env var NAME — confirmed 2026-09-01 that OPENAI_API_KEY/
    OPENAI_BASE_URL in this deployment actually point at Anthropic
    (api.anthropic.com), so the key's name is not trustworthy as a label.
    base_url is: self-updating if .env is ever repointed, and available at
    every call site via the already-constructed client (client.base_url)."""
    b = (base_url or "").lower()
    if "anthropic.com" in b:
        return "anthropic"
    if "openrouter.ai" in b:
        return "openrouter"
    if "moonshot" in b:
        return "moonshot"
    if "openai.com" in b:
        return "openai"
    return "unknown"

_CACHED_TOKEN_ALIASES = (
    ("prompt_tokens_details", "cached_tokens"),   # OpenAI shape
    (None, "cache_read_input_tokens"),            # in case a proxy passes
    (None, "cached_tokens"),                      # this through unnested
)
_CACHE_WRITE_ALIASES = (
    (None, "cache_creation_input_tokens"),
    ("prompt_tokens_details", "cache_write_tokens"),  # OpenRouter shape, and
    # what jarvis/anthropic_shim.py's _convert_response() produces directly
    # (Phase 1, Rev 3.2, landing step (i)) — openai's own
    # PromptTokensDetails already has this field natively at the pinned
    # openai==2.53.0, verified 2026-09-01.
)


def _get(obj: Any, key: str, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _find_first(usage: Any, aliases) -> int:
    for container_key, field in aliases:
        container = _get(usage, container_key) if container_key else usage
        val = _get(container, field)
        if val is not None:
            return val
    return 0


def record_completion(rung: str,
                      provider: str,
                      model: str,
                      response: Any,
                      session_id: Optional[str] = None,
                      gen_id: Optional[str] = None,
                      reported_cost: Optional[float] = None) -> None:
    """The one adapter for every call site in this repo — all are
    chat.completions.create via AsyncOpenAI regardless of upstream vendor.

    provider: pass provider_from_base_url(str(client.base_url)) — every
              call site already has the constructed client in scope, so
              no config lookup or key-env guessing is needed.
    reported_cost/gen_id: pass through when routed via OpenRouter and
              usage-accounting is enabled inline; otherwise leave None
              and let scripts/pull_openrouter_activity.py backfill by
              gen_id later.
    """
    u = _get(response, "usage") or {}
    if os.environ.get("JARVIS_DEBUG_USAGE_LEDGER") == "1":
        import sys
        print(f"usage_ledger DEBUG rung={rung} provider={provider} "
              f"model={model} raw_usage={u!r}", file=sys.stderr)

    prompt = _get(u, "prompt_tokens") or 0
    completion = _get(u, "completion_tokens") or 0
    cached = _find_first(u, _CACHED_TOKEN_ALIASES)
    cache_write = _find_first(u, _CACHE_WRITE_ALIASES)

    record_call(
        rung=rung, provider=provider, model=model, session_id=session_id,
        # Rev 3.2 fix (2026-09-01): subtract cache WRITES too, not only
        # reads. Before caching went live this was a no-op (cache_write
        # was always 0). With it live, a cache-write token is part of
        # `prompt` (OpenAI-inclusive semantics) but is billed at its own
        # 1.25x/2.0x multiplier by compute_cost()'s cache_write_tokens
        # argument below -- leaving it in input_tokens double-billed it
        # at 1.25x AND the full 1.0x input rate.
        input_tokens=max(prompt - cached - cache_write, 0),
        output_tokens=completion,
        cache_write_tokens=cache_write,
        cache_read_tokens=cached,
        reported_cost=reported_cost,
        gen_id=gen_id or _get(response, "id"),
    )
