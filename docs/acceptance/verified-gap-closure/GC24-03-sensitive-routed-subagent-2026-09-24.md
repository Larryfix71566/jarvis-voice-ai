# GC24-03 — Sensitive-turn policy propagation progress

**Date:** 2026-09-24  
**Branch:** `codex/isolated-20260924`  
**Base:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`; working tree is dirty.  
**State:** one sink path tightened; GC24-03 remains open.

## Gap addressed

Routed SubAgent requests previously initialized their `ModelExecutionRequest`
policy from the resolved route's privacy label. A sensitive turn could
therefore inherit `approved_external` and pass that same label for its full
context/tool-result history. The request now combines the route policy with
the inherited `SensitiveTurn` signal using the existing strictest-policy
function. When the turn is sensitive, its effective policy is at least
`confidential`; `execute_chat` checks that policy before creating a provider
client, so an `approved_external` route is rejected before transmission.

The request context—including tool results carried to the next model round—
uses the tightened policy. Existing sensitive run-log snapshots continue to
redact persisted task/tool payloads. No route fallback or model substitution
was added.

## Validation

- Focused SubAgent, agent-event, and privacy-policy suites: **72 passed**.
- `RUN_LIVE=0 .venv/bin/python -m pytest tests/unit tests/integration -q`:
  **2,813 passed, 4 skipped, 11 warnings, 2 subtests passed**.
- SubAgent evaluation: **13 passed**.
- Call-site audit: **25 entries, 0 review-required**.
- Latency fixture probe passed unchanged thresholds.
- Ruff import sorting and `git diff --check` passed.

## Remaining GC24-03 work

This is not an end-to-end privacy audit. It covers only routed SubAgent calls
and the existing per-turn sensitive signal. Continue with source classification
for other caller families and explicit checks at council/planner continuations,
supervisor context, speech, display/share, exports, logs, and provider-session
persistence. Each forbidden sink needs a negative canary proving zero
transmission and no persisted payload. Direct, routing-disabled callers also
need a reviewed policy path. Keep the current voice-supervisor exception
explicit and do not claim the complete voice conversation is private.

No Mac/live-provider acceptance, merge, deployment, or release is claimed.
