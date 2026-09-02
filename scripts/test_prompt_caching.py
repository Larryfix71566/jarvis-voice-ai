"""scripts/test_prompt_caching.py — Phase 1 verification gate
(MORTIMER_OPTIMIZATION_PLAN.md, Rev 3.2, landing step (ii) task 8, sub-
agent/council half; step (iii) adds the live-voice-session half): does
the NATIVE Anthropic path actually cache, for the models really in use?

Rewritten from the Phase 0 diagnostic (which answered a narrower
question: does the OpenAI-COMPATIBILITY layer report cache usage fields
at all — it does not, confirmed 2026-09-01, which is why Phase 1 exists).
This version drives the same client-construction path the real call
sites use now — `jarvis.llm_client.make_async_client(...)` — so a clean
result here is evidence the actual code path caches, not just that the
API can.

Two things this rewrite fixes, both from Rev 3.2's own findings:
  - The filler prompt used to target ~1,024 tokens. Haiku 4.5's cacheable
    minimum is 4,096 tokens (Sonnet 5 / Opus 5 / Fable 5 float lower, at
    1,024 / 512 / 512) — the old filler would have reported a false
    negative (nothing cached, silently) on the Supervisor's own model.
    The filler below comfortably clears 4,096 for every model tested.
  - The old script used `stream=True` — `jarvis/anthropic_shim.py`
    deliberately rejects that (S8: no Path-B caller streams, so a
    stream=True request raises ShimError rather than being silently
    dropped). This version makes a plain, non-streaming call and reads
    `response.usage` directly, which every model tested here returns
    whether native (the shim) or compat.

What "pass" looks like for each model probed: call 1 (cold) reports
`cache_creation_input_tokens > 0` — proof the prefix cleared that
model's floor and a cache entry was written; call 2 (same prefix, sent
right after) reports `cache_read_input_tokens` close to call 1's
creation count — proof the write was actually read back. Zero on both
calls for a model at or above its stated floor means caching did not
happen and is worth raw-dumping the usage object for (which this script
always does, pass or fail).

Models probed, and why these three specifically: they are the only
Anthropic-direct models this deployment actually assigns to a rung today
(config/agents.yaml, config/upgrade_models.yaml) —
  - the Supervisor's own model (Haiku 4.5, via `jarvis.config.
    load_settings()` — the voice-model client), the 4,096-token case;
  - `claude-sonnet-5` and `claude-fable-5` (`config/upgrade_models.yaml`
    profiles — sub-agents/executor/council all resolve through the same
    registry), the 1,024/512-token cases.
`claude-opus` is deliberately not probed here — same registry, same
mechanism, no incremental information; add it if it's ever actually
assigned to a rung.

Run: python scripts/test_prompt_caching.py
(Reads real API keys from the environment exactly like the app does —
this makes real, billed API calls.)
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

# Running `python scripts/test_prompt_caching.py` puts scripts/ on
# sys.path, not the repo root — same fix every other script here applies.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jarvis import llm_client  # noqa: E402
from jarvis.agents.upgrade_agent import load_model_registry, resolve_profile  # noqa: E402
from jarvis.config import load_settings  # noqa: E402

# ~700 repetitions of a short sentence: comfortably over Haiku 4.5's
# 4,096-token floor even under a pessimistic 6-characters-per-token
# estimate (~5,260 tokens, ~28% headroom; a typical ~4 chars/token
# estimate puts it closer to ~7,900) — real margin, not a hair over the
# line, the highest floor of any model probed here.
LARGE_SYSTEM_PROMPT = (
    "You are a test assistant used only to probe prompt-caching support. "
    + ("The quick brown fox jumps over the lazy dog. " * 700)
)

REGISTRY_PROFILES_TO_PROBE = ("claude-sonnet-5", "claude-fable-5")


def _dump_usage(usage) -> str:
    if usage is None:
        return "None"
    if hasattr(usage, "model_dump"):
        return json.dumps(usage.model_dump(), indent=2, default=str)
    return repr(usage)


async def one_call(client, model: str, tag: str):
    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": LARGE_SYSTEM_PROMPT},
            {"role": "user", "content": f"Say hello in exactly one word. [{tag}]"},
        ],
    )
    usage = getattr(response, "usage", None)
    print(f"--- {tag}: raw usage object ---")
    print(_dump_usage(usage))
    print()
    return usage


def _int_field(usage, name: str) -> int:
    if usage is None:
        return 0
    details = getattr(usage, "prompt_tokens_details", None)
    for source in (usage, details):
        val = getattr(source, name, None) if source is not None else None
        if val is not None:
            return int(val)
    return 0


async def probe(label: str, client, model: str) -> None:
    print(f"=== {label} (model={model}) ===")
    u1 = await one_call(client, model, f"{label}: call 1 (cold)")
    u2 = await one_call(client, model, f"{label}: call 2 (identical prefix, should hit cache)")

    write1 = _int_field(u1, "cache_creation_input_tokens") or _int_field(u1, "cache_write_tokens")
    read2 = _int_field(u2, "cache_read_input_tokens") or _int_field(u2, "cached_tokens")

    if write1 > 0 and read2 > 0:
        verdict = f"PASS — call 1 wrote {write1} cache tokens, call 2 read {read2} back."
    elif write1 == 0:
        verdict = "FAIL — call 1 reported no cache_creation_input_tokens; the prefix may not have cleared this model's floor, or caching isn't active on this path."
    else:
        verdict = f"FAIL — call 1 wrote {write1} cache tokens but call 2 read {read2} back (expected close to {write1})."
    print(f"VERDICT: {verdict}")
    print()


async def main() -> None:
    settings = load_settings()

    # 1. The Supervisor's own model (Haiku 4.5), via the same Settings-
    #    based client base.py's fallback/no-profile sites use. Path A
    #    itself (pipecat's AnthropicLLMService) is landing step (iii),
    #    not yet wired — this still answers whether the Supervisor's
    #    actual prefix clears Haiku's 4,096-token floor, which (iii)
    #    needs known before it lands.
    haiku_client = llm_client.make_async_client(
        api_key=settings.openai_api_key, base_url=settings.openai_base_url,
    )
    await probe("supervisor model (4,096-token floor)", haiku_client, settings.openai_model)

    # 2/3. sonnet-5 / fable-5 via the same registry base.py/upgrade_agent
    #    .py/council.py resolve profiles from.
    registry = load_model_registry()
    for profile_name in REGISTRY_PROFILES_TO_PROBE:
        try:
            profile = resolve_profile(registry, profile_name)
        except Exception as exc:  # noqa: BLE001 — report and move on
            print(f"=== {profile_name}: SKIPPED ({exc}) ===\n")
            continue
        key_env = profile.get("api_key_env", "OPENAI_API_KEY")
        if not os.environ.get(key_env):
            print(f"=== {profile_name}: SKIPPED ({key_env} is not set) ===\n")
            continue
        client = llm_client.make_async_client(
            api_key=os.environ[key_env], base_url=profile["base_url"],
            provider=profile.get("provider"),
        )
        await probe(f"{profile_name} (1,024/512-token floor)", client, profile["model"])


if __name__ == "__main__":
    asyncio.run(main())
