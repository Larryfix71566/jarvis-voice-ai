# Phase 8 Acceptance — Hardening, Docs & Fresh-Clone Verification

## 8.2 Fresh-clone verification log

Clone: `git clone <repo> /tmp/jarvis-clone`, then follow ONLY README.md.

| Step | Result |
|---|---|
| `uv venv` + `uv pip install -r requirements-lock.txt` | PASS (first attempt FAILED: lock contained sandbox-internal `agent-gw`; lock re-frozen to the 148-package project closure, clone test restarted — see DEVIATIONS D-006c) |
| `cp .env.example .env` + fill keys | PASS |
| `python scripts/check_env.py` | PASS 8/8 |
| `python scripts/init_db.py` | PASS (migrations applied: 0001_init) |
| `pytest tests/unit tests/integration -q` | PASS — 180 passed, 3 skipped (live-gated) |
| `RUN_LIVE=1 pytest tests/integration -q` | PASS — 26 passed |
| `RUN_LIVE=1 python -m tests.evals.routing_eval` | PASS — 28/30 = 93% (threshold 90%; see routing-eval-run-phase8.txt) |
| `./scripts/run_bot.sh` | PASS (uvicorn on :7860, `/client/` 200; uses `.venv/bin/python` when present) |
| web: `npm install --no-bin-links` + `npm run build` | PASS (strict TS clean, production build) |

README fixes made during verification: venv activation added to quickstart;
run_bot.sh venv preference added; NLTK `punkt_tab` pre-seed row added to
troubleshooting.

**Restart-from-scratch pass (after fixes, final commit):** second fresh clone
(`/tmp/jarvis-verify`) — locked quickstart install from the corrected
requirements-lock.txt PASS; check_env 8/8 PASS; init_db PASS; unit+integration
180 passed / 3 skipped; web build PASS; run_bot.sh booted with
`.venv/bin/python` and served `/client/` 200. One new issue found and fixed:
pipecat's first import downloads NLTK `punkt_tab`, which stalls on restricted
networks — documented in the troubleshooting table (pre-seed command).

## 8.3 Master Acceptance Test — "The Jarvis Demo Script" (§8)

Executed in the browser against the fresh clone. **Status: blocked for audio
verification** — the ElevenLabs account returns 401 `detected_unusual_activity`
on TTS generation, so no spoken output exists until the account is upgraded or
unblocked. Rows are scripted here for manual sign-off; every non-audio
expectation is covered by the automated gates above (routing, reminders rows,
notes rows, voice switching frames, watcher injection, transcript logging).

| # | Say | Expected | Verify |
|---|-----|----------|--------|
| 1 | "Hello Jarvis." | Brief spoken greeting, no delegation | ears + transcript |
| 2 | "What time is it?" | Acknowledgment, then correct current time spoken | ears + log `TURN` ≤ 2500 ms |
| 3 | "Remind me to call the dentist tomorrow at 9 AM." | Confirmation with resolved absolute date/time | `reminders` row, `due_at` correct for `JARVIS_TIMEZONE` |
| 4 | "What's on my schedule tomorrow?" | The dentist reminder spoken back | ears |
| 5 | "Actually, move that to 9:30." | Updated confirmation | `due_at` updated |
| 6 | "Remember that Dr. Patel's office is on Main Street." | Stored confirmation | `notes` row exists |
| 7 | "Where is my dentist's office?" | "Main Street" spoken from memory | ears |
| 8 | "What's the weather in London right now?" | Current conditions + temp in one breath | ears |
| 9 | "Search the web for the latest SpaceX news." | ≤ 60-word spoken brief | ears |
| 10 | "How is my computer holding up?" | CPU/mem/disk spoken; flags anything ≥ 85 % | ears |
| 11 | "Switch to the <other> voice." | Confirmation **in the new voice** | ears |
| 12 | (While Jarvis speaks a long answer) "Jarvis, stop — what's two plus two?" | Speech cuts ≤ 1 s; answers "Four." | ears |
| 13 | "Set a reminder to stand up in 2 minutes." | Confirmation | row exists |
| 14 | *(wait ~2.5 min, stay connected)* | Jarvis speaks the reminder **unprompted** | ears + `delivered=1` |
| 15 | "Thanks, Jarvis." | Short, warm sign-off; no tools called | transcript |

## 8.4 DEVIATIONS audit

All six entries (D-001…D-006) re-read on 2026-08-05: each is still accurate
and wiring-level only (library version/API adaptations, sandbox filesystem
workarounds, lock-file repair). None is architecture-shaped. The locked
9-processor pipeline order, the delegate_task mechanism, the five MCP servers,
and the SQLite schema are unchanged from the plan.
