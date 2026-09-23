# Mortimer release acceptance runbook

This runbook closes the remaining evidence gates for the automated-memory and
Command Center plans. It does not change code, enable a provider, or alter the
database. Run it against the signed candidate whose executable hash is recorded
in the active receipt.

## 1. Freeze the candidate

From the release-review checkout:

```sh
cd /Users/larryfix/Documents/Codex/2026-09-09/can/work/release-review
shasum -a 256 macos/MortimerHost/.build/MortimerHost.app/Contents/MacOS/MortimerHost
git rev-parse HEAD
git status --short
```

Record the output with the date. Do not replace the candidate during the
acceptance session. A code change starts a new candidate and resets the
five-day observation period.

## 2. Physical display recovery

With the candidate open and the supporting display showing a graph or response:

1. Record the two-screen topology with `bash scripts/run_display_topology_probe.sh`.
2. Close and reopen the supporting display; verify one bounded stage and the
   main-window return locator.
3. Physically disconnect the external display, wait for the macOS window
   transition, and verify the content remains in the main window with no extra
   windows.
4. Reconnect it, reopen the supporting display, and verify the same result IDs,
   selected tab, draft state, and panel count.
5. Repeat with the display mirrored and with three displays if available.

Pass requires a screenshot or accessibility capture for each topology, the
visible tile IDs, and no duplicate fetch/subscription event. A virtual-screen
unit test is supporting evidence only; it cannot close this gate.

## 3. Live voice and response routing

Connect the candidate and confirm `READY VOICE`. Speak one request that returns
text and one that returns a research/display result. Verify:

- the user and Mortimer meters respond independently and honestly;
- the full Mortimer answer appears in one results card;
- streamed/tool subturns update that card instead of creating cards/windows;
- the supporting display owns the full answer when open;
- the conversation surface retains only brief captions;
- closing the supporting display returns the same answer to the main results area.

Record the request timestamp, result ID, visible tile count, and any audio
startup/reconnect error. A `READY VOICE` label alone is not a spoken-response
pass; output speech and both measured channels must be observed.

## 4. Sharing and accessibility

Use a real text result and a real image result. Verify preview, copy, save,
system share, cancel, picker return, VoiceOver labels, keyboard navigation,
font-size changes, reduced motion, and liquid-glass styling. No recipient
delivery may be claimed from opening a picker. The inbound path requires an
explicit approval offer, provider/model disclosure, bounded transfer progress,
cancel, reconnect, and ephemeral cleanup.

## 5. Memory staged rollout

Use the runtime vault path already documented in the memory status; never copy
secrets into the release-review checkout. Run the provider shadow first:

```sh
UV_CACHE_DIR=/private/tmp/jarvis-uv-cache uv run \
  --with-requirements requirements-lock.txt \
  python scripts/run_memory_provider_shadow.py \
  --profile claude-sonnet-5 \
  --vault-path /Users/larryfix/jarvis-voice-ai-clean/data/secrets.vault
```

Only after the shadow receipt is accepted, enable `shadow` for one daily-driver
day, then `explicit_preferences`, then `corroborated_inferences`. Capture
redacted counts, latency, calls, cost, interruptions, stale-use cases,
duplicate rows, privacy events, and the first 20 reversible decisions. Disable
immediately on a privacy, scope, duplicate, budget, or stale-use regression.
The stage is selected only through `JARVIS_MEMORY_AUTOMATION_STAGE`; unknown
values fail closed. Keep the existing automation enable/shadow switches and
the stage change in the same dated rollout receipt.

The 28-exchange recovery is already a separate completed repair and must not be
combined with rollout measurement.

## 6. Closure record

Update `docs/acceptance/adaptive-interface/RELEASE_READINESS.md` only after
each exact gate has its receipt. Then update both plan status files and run:

```sh
/Users/larryfix/jarvis-voice-ai-clean/.venv/bin/python -m pytest -q
/Users/larryfix/jarvis-voice-ai-clean/.venv/bin/python -m pytest -q tests/unit/test_plan_manifests.py
git diff --check
```

No item is closed from a synthetic test, an old receipt, an installed path, or
an implementation claim alone.
