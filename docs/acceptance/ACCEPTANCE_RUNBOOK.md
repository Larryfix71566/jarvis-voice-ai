# Mortimer release acceptance runbook

This runbook closes the remaining evidence gates for the automated-memory and
Command Center plans. It does not change code, enable a provider, or alter the
database. Run it against the signed candidate whose executable hash is recorded
in the active receipt.

The candidate checkout must be the exact source used to build the signed
candidate. Do not assume the historical `release-review` path still contains
that source. The current deployment baseline and its inspection limits are
recorded in
[`verified-gap-closure/GC24-00-baseline-2026-09-25.md`](verified-gap-closure/GC24-00-baseline-2026-09-25.md).

## 1. Freeze the candidate

From the verified candidate checkout, set `CANDIDATE_ROOT` to its repository
root before running:

```sh
cd "$CANDIDATE_ROOT"
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

Status (reconciled 2026-09-22 against main `88b206f`): committed prose
receipts cover steps 3–4 on one external monitor:
`command-console/receipts/candidate-monitor-unplug-2026-09-18.md`,
`candidate-monitor-reconnect-2026-09-18.md` and
`candidate-monitor-auto-rehome-2026-09-18.md`. They record unplug with manual
and automatic rehome, and reconnect with the same two results restored in one
stage. They do not include committed screenshot or accessibility captures,
visible tile IDs, or duplicate-fetch evidence. Step 5 (mirrored and
three-display) has not been run. This section's pass criteria are therefore
not fully met.

## 3. Live voice and response routing

**CC7a reconciliation, 2026-10-17:** use the current conversation-first
requirements below. The September 18 evidence predates CC7a and cannot prove
these changed behaviors. An ordinary spoken answer belongs in the full
conversation thread; it must not create a result card or tab. The earlier
instruction to put every full answer in a card and leave only brief captions
is superseded by the approved WS-17 design.

Connect the identified installed candidate and confirm `READY VOICE`. Keep
background audio quiet and mute between controlled prompts. Record the actual
input/output devices; a connected label is not proof of speech or playout.
Verify the user and Mortimer activity channels respond independently and
truthfully; the device-switch check alone does not establish that full matrix.

1. **UI2-22:** five spoken turns, one answer longer than 160 characters. Both
   speakers' full words stay ordered in one thread. Check protected-turn rules,
   scroll/reading state, and a new ordinary answer while a result is open.
2. **UI2-23:** request weather/research/image results. From Conversation, the
   just-requested result opens; a late/background completion stays a card.
   While reading another result, arrival preserves focus and gives a notice.
   Verify Open/Back, compare/pin, and that closing a card preserves its Output
   record. Supporting-display cases need the corresponding topology.
3. **UI2-24:** one console row and no result tab strip. Exercise Recents
   select/close/pin/unpin/reopen through voice and pointer. Ambiguous/stale
   selections must clarify/refuse rather than change the wrong result.
4. **UI2-25:** original weather → Atlanta → original produces two identities.
   A fresh request reuses the original (15-minute window) without a second
   fetch; a stale request refreshes that same identity. Record inventory and
   fetch evidence, not just matching titles.
5. **WS-18/shared audio:** AirPods → Mac speakers → AirPods during speech.
   Record each direction, audible gap/speed, app survival, connection continuity
   and `audio output flowing` diagnostics after rebuild. This does not alone
   close the separate echo, wake, denial, interruption or performance gates.

For each case record timestamp, source/artifact identity, observed result IDs
and count where applicable, operator report and direct UI/log evidence. Use
synthetic or public-content prompts. Do not mark a parent requirement passed
from a subset, and do not use model-generated claims as evidence of success.
An unavailable display, provider prerequisite or required decision remains open.

Historical September 18 receipt:
`command-console/receipts/candidate-live-response-display-2026-09-18.md`
records READY VOICE and the old close-and-return path, without a recorded
spoken request/response. It is retained with that scope.

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

Status (reconciled 2026-09-22 against main `88b206f`): the provider shadow
step has a committed receipt,
`memory-automation/provider-shadow-receipt.json` (2026-09-18,
`claude-sonnet-5`, 8/8 synthetic cases, no regression, no database or
production writes). The staged daily-driver enablement has not been recorded.
The committed rollout receipt's "first 20 reviewed decisions" are synthetic
fixture rows, not a review of real decisions.

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
