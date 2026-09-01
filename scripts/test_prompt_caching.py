"""scripts/test_prompt_caching.py — standalone diagnostic
(MORTIMER_OPTIMIZATION_PLAN.md Phase 0, readiness checklist step 4): does
this deployment's Anthropic-compat path (chat.completions.create via
AsyncOpenAI) report prompt-cache usage at all?

Not wired into production and never will be — this is a one-off answer,
not a permanent code path. Two other paths in this repo were considered
and rejected for this question:
  - usage_watcher.py's MetricsFrame observer can only ever see whatever
    pipecat's own LLMTokenUsage already extracted (cache_read only, never
    cache_write — see that file's docstring), so it can't settle this.
  - record_completion()'s JARVIS_DEBUG_USAGE_LEDGER=1 print never fires
    for the supervisor rung, since that path doesn't call
    record_completion() at all (see jarvis/bot/usage_watcher.py).

This script hits the API directly with the SAME client construction the
live app uses (jarvis.config.load_settings) and prints the full raw
usage object from two back-to-back calls sharing an identical, large
(>1024 token) system-prompt prefix — large enough to clear Anthropic's
minimum cacheable-prefix size, so a second identical-prefix call is the
simplest real test of whether caching is happening at all, independent
of whether this deployment is doing anything to opt into it.

Run: python scripts/test_prompt_caching.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

# Running `python scripts/test_prompt_caching.py` puts scripts/ on
# sys.path, not the repo root — same fix scripts/list_voices.py and
# every other script here already applies.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openai import AsyncOpenAI  # noqa: E402

from jarvis.config import load_settings  # noqa: E402

# Comfortably over Anthropic's minimum cacheable prefix (1024 tokens for
# Claude); repeated filler so token count is easy to reason about.
LARGE_SYSTEM_PROMPT = (
    "You are a test assistant used only to probe prompt-caching support. "
    + ("The quick brown fox jumps over the lazy dog. " * 250)
)


def _dump_usage(usage) -> str:
    if usage is None:
        return "None"
    if hasattr(usage, "model_dump"):
        return json.dumps(usage.model_dump(), indent=2, default=str)
    return repr(usage)


async def one_call(client: AsyncOpenAI, model: str, tag: str) -> None:
    stream = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": LARGE_SYSTEM_PROMPT},
            {"role": "user", "content": f"Say hello in exactly one word. [{tag}]"},
        ],
        stream=True,
        stream_options={"include_usage": True},
    )
    last_chunk = None
    async for chunk in stream:
        last_chunk = chunk
    usage = getattr(last_chunk, "usage", None) if last_chunk is not None else None
    print(f"--- {tag}: raw usage object ---")
    print(_dump_usage(usage))
    print()


async def main() -> None:
    settings = load_settings()
    client = AsyncOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
    )
    print(f"provider base_url={settings.openai_base_url} model={settings.openai_model}")
    print(f"system prompt length (chars): {len(LARGE_SYSTEM_PROMPT)}")
    print()

    # Call 1: cold — nothing to read from cache yet, but if this endpoint
    # writes a cache entry on first sight, cache_creation/cache_write
    # fields (if reported at all) would show up here.
    await one_call(client, settings.openai_model, "call 1 (cold)")

    # Call 2: identical prefix, sent right after — if caching is active,
    # THIS is where a cache_read/cached_tokens field should show a
    # nonzero value close to the system prompt's token count.
    await one_call(client, settings.openai_model, "call 2 (identical prefix, should hit cache if supported)")


if __name__ == "__main__":
    asyncio.run(main())
