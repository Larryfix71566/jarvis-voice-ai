"""jarvis/effort.py — output_config.effort control for Path B (native
Anthropic) call sites.

MORTIMER_OPTIMIZATION_PLAN.md Phase 1b (Rev 3.2, "gate mostly resolved
by documentation"), landing after Phase 1 (i)/(ii)/(iii).

Goal: stop paying default-high adaptive-thinking depth on rungs that
don't need it. Claude 5-class models think adaptively at effort=high by
default, thinking tokens bill as output tokens, and until this lands no
call site sets effort at all.

Facts this rests on (platform.claude.com, 2026-09-01 — see the plan's
Phase 1b section for the full citation):
  - The parameter is `output_config: {"effort": "low"|"medium"|"high"|
    "xhigh"|"max"}`, top-level on the native Messages API, no beta
    header. Sending "high" is identical to omitting the field.
  - Supported: Sonnet 5, Opus 5, Fable 5. NOT listed for Haiku 4.5 — a
    400 on the voice path is the one failure mode this phase cannot
    afford to discover live, so extra_body_for() refuses to emit
    anything for a Haiku model regardless of what's configured.
  - Through the OpenAI-compatibility layer `reasoning_effort` is
    IGNORED (not merely unsupported — silently dropped), so effort only
    ever takes effect on the native path: provider == "anthropic" AND
    JARVIS_ANTHROPIC_NATIVE != "0" (jarvis/llm_client.py's own gate).
    This module does not re-check the native-enabled flag itself —
    that's llm_client's job; extra_body_for() only ever gates on
    `provider`, the one thing every caller has already resolved through
    the same authoritative source llm_client.py's factory uses.
  - **Cache rule, a requirement, not a preference:** changing
    output_config.effort between requests on the SAME cacheable prefix
    invalidates the prompt cache (documented, not inferred). Every call
    site wires a STATIC per-rung value — never a per-call choice — so
    this never trips. The one live-tunable knob is the
    JARVIS_EFFORT_<RUNG> env var below, meant to be set once per
    session to test or roll back a rung, never toggled request to
    request.

Usage (mirrors jarvis/anthropic_shim.py's S8 passthrough rule — the shim
merges `extra_body`'s keys as top-level native-request fields; the real
openai client spreads `extra_body` into the request body the same way,
so this module needs no Path-B-specific branch):

    extra_body = effort.extra_body_for(
        rung=self.name, provider=provider, explicit=self._effort, model=model,
    )
    request = {"model": model, "messages": messages, **extra_body and {"extra_body": extra_body} or {}}
"""

from __future__ import annotations

import os
from typing import Any

VALID_LEVELS = frozenset({"low", "medium", "high", "xhigh", "max"})


def extra_body_for(rung: str, provider: str, explicit: str | None = None,
                    model: str | None = None) -> dict[str, Any]:
    """Returns `{"output_config": {"effort": level}}` when a level is
    configured for `rung` and the call is going out over the native
    Anthropic path; `{}` otherwise, so every existing caller's
    `**extra_body`-style unpacking is a no-op until effort is actually
    configured for that rung.

    provider: the CALLER's already-resolved provider (the same
    authoritative source jarvis/llm_client.py's factory takes —
    typically `profile.get("provider")` or an equivalent already-known
    value, never re-derived here). `output_config` only exists on
    Anthropic's native Messages API, so any other provider (moonshot,
    openrouter, plain openai) always gets `{}` regardless of `explicit`.
    This is deliberately stricter than the plan's literal guard text
    (which names only the Haiku case): sending `output_config` to a
    non-Anthropic endpoint as an unrecognized top-level field risks the
    exact "discover a 400 live" failure mode the Haiku guard exists to
    prevent, just on a different rung.

    model: gates out Haiku 4.5 specifically (not a supported model for
    this parameter, confirmed 2026-09-01) — checked by substring,
    case-insensitive, so any Haiku-family model string is caught the
    same way this codebase already checks for it elsewhere. The
    Supervisor (the only Haiku rung, and Path A, not Path B) never
    calls this function today — the guard holds regardless, since a
    future call site could pass a Haiku model here too.

    explicit: the level the CALLER already resolved from its own
    config (config/agents.yaml's `effort:` for a SubAgent, or an
    upgrade_models.yaml profile's optional `effort:` — see the plan's
    Phase 1b task 2). A `JARVIS_EFFORT_<RUNG>` environment variable,
    when set, overrides it — a live, no-restart way to test or roll
    back a single rung's effort level without touching config (same
    pattern as `JARVIS_ANTHROPIC_NATIVE`, `JARVIS_UI_CONTROL_ENABLED`,
    etc. elsewhere in this repo). Read fresh on every call, never
    cached at import time.

    Raises ValueError on an unrecognized level — the same "never drop
    an unexpected value silently" discipline jarvis/anthropic_shim.py's
    S8 rule already applies to unknown kwargs: a typo in agents.yaml or
    an env var should fail loudly at the first call, not produce a
    mysterious 400 from the API three layers away.
    """
    if provider != "anthropic":
        return {}
    if "haiku" in (model or "").lower():
        return {}
    env_var = f"JARVIS_EFFORT_{rung.upper()}"
    level = os.environ.get(env_var) or explicit
    if not level:
        return {}
    if level not in VALID_LEVELS:
        raise ValueError(
            f"invalid effort level {level!r} for rung {rung!r} "
            f"(from {env_var} or config); must be one of {sorted(VALID_LEVELS)}"
        )
    return {"output_config": {"effort": level}}
