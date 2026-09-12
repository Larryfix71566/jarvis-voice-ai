# C5 — Graphics-attached verification runner (G20, G21)

Date: 2026-09-12. Candidate base `6bf0270` (the committed tree; the C1–C4 working-tree edits are not in any commit yet, so this receipt covers the runner and the committed candidate, not the closure edits — see "What this receipt is"). Sandbox changes are in the working tree: `sandbox/guest/worker.sh`, `sandbox/guest/desktop-probe.sh` (new), `sandbox/verify.py`, `sandbox/images.py`, `sandbox/control.py`, `sandbox/tests/test_verify.py`.

## Root cause, with evidence

The nine native failures in the earlier receipts (`P6-interim-checks.md`, attempts `9a6e0bb5…` and `77a62a47…`) were never a Tart display problem. Diagnostics run through the sandbox's own controller on the deployment Mac (`closure-checks/logs/diag-c5c.log` … `diag-c5i.log`, each with a `.done` SHA-256):

1. `diag-c5c` / `diag-c5d` (an old verification clone, `e3263c285144`): the console user was **admin**, the Tart guest agent (`/Library/LaunchAgents/org.cirruslabs.tart-guest-agent.plist`, `--run-agent`) ran in admin's Aqua session, and `tart exec` reached the worker only through `sudo -u mortimer-dev` — a UID-502 process inside a UID-501 session. That clone had been hydrated with a `worker.sh` that only set auto-login for admin (`input/worker.sh:55`); the later `worker.sh` (candidate `bae4aa5`) sets it for the worker.
2. `diag-c5e` (fresh clone, current `worker.sh`): auto-login now lands on `mortimer-dev` (`who`: `mortimer-dev console`; `launchctl managername` Aqua, `manageruid` 502; the guest agent runs as `mortimer-dev`). The session is right — and the probe window was still not visible.
3. `diag-c5g` (host screenshot of the guest window + process list): the worker's **first login was running Setup Assistant** (`Setup Assistant -MiniBuddyYes`, the Accessibility page on screen) with a **SecurityAgent prompt** on top — "Spotlight wants to use the 'sandbox' keychain" — because `worker.sh` made a custom keychain with its own password the default store, and a keychain that loginwindow cannot unlock is prompted for by every system service. No plain desktop ever existed for the AppKit checks.
4. `diag-c5f`: one hydration failed with `chown: mortimer-dev: illegal user name` — Directory Services had not yet published the record `dscl` had just created. A pre-existing race in `worker.sh`.
5. `diag-c5h`: with Setup Assistant suppressed and a login keychain, the guest shows a plain Finder desktop (host screenshot), but my first probe still read `occlusionState.visible == false` — because the probe pumped only the run loop. Occlusion changes arrive as AppKit events; `WindowVisibilityTests.pumpEvents` pumps `NSApp.nextEvent`. A probe artefact, not a sandbox fact.
6. `diag-c5i`: probe pumping events like the tests → `visible=true isVisible=true activeSpace=true appActive=true`, and the real gate, `swift test --filter WindowVisibilityTests` **inside the guest: 4 tests, 0 failures**.

## Changes

| Item | Change | Evidence |
|---|---|---|
| C5.1 worker session | `worker.sh`: waits for the new account to resolve (bounded 30 s) before `chown`; the worker's keychain is now `login.keychain-db`, created with the same random login password that auto-login uses, so loginwindow unlocks it and no service prompts; every Setup Assistant page is marked seen for the running OS build (`com.apple.SetupAssistant` keys + `LastSeenCloudProductVersion`/`LastSeenBuddyBuildVersion`), the way the image builder did for `admin`. The auto-login/restart sequence itself is unchanged. | diag-c5f (race), diag-c5g (assistant + prompt), diag-c5h/i (plain desktop; probe and `WindowVisibilityTests` green in the guest) |
| C5.1 probe | `sandbox/guest/desktop-probe.sh` (copied into every task's input by `images.create`, part of `runner_fingerprint`): as the worker, asserts Aqua manager and console ownership, no Setup Assistant process, builds and runs a Swift window that must report `occlusionState.visible` after pumping AppKit events, and proves the login keychain accepts a write without a SecurityAgent prompt (bounded 20 s). `Verifier.desktop_probe` runs it after the graphics restart and before the first check; its exit code, duration and log hash are bound into the receipt (`desktop_probe`), the log saved beside the check logs, and a failure raises before any check runs (fail closed, never a skip). | `sandbox/tests/test_verify.py`: probe ordered before the first check and recorded; a non-zero or wrong-output probe aborts with no check executed and a failed journal entry; headless profiles never run it |
| C5.1 keychain step | `Verifier.run_check` re-selects `login.keychain-db` before native checks and no longer issues `unlock-keychain` — the password is a guest-only secret; the probe has already shown the store is unlocked. | `test_native_checks_reselect_synthetic_keychain_before_execution` updated to the two-step form (contract change, disclosed) |
| C5.3 sandbox suite | 111 tests. | `python3 -m unittest discover -s sandbox/tests` on the Mac (python 3.9.6): `verify-c5.log` "Ran 111 tests … OK"; also green under Linux python 3.10 in the session VM |
| C5.2 receipt in tree | `docs/acceptance/adaptive-interface/receipts/<attempt>.json` — the receipt only: fingerprints, check names, return codes, durations, log SHA-256s, desktop-probe record. No logs, no source. | `closure-checks/c5_verify_head.py` copies it; `verify-c5.log` |

## What this receipt is

`closure-checks/run-verify-c5.command` → `closure-checks/logs/verify-c5.log`, SHA-256 `ac8dd9421853b781ffcb10220631f712ab5992df6d88fe813566e9f36b990ad4`. Driven through `Verifier.verify` exactly as the sandbox session would (development task `c0960a0c15a4` from `HEAD` = `6bf0270…`, frozen candidate `6a22be31…` = baseline, verification clone `d9bdd45f9ebe`, image `32a82fdd…`, profile `c400d0df…`, runner `d5627d02…`).

**Attempt `25d16062811a4f478c0d4ba3075f0bcc`: status `passed`, `source_unchanged: true`, all twelve required checks exit 0 — 1,048 s end to end.**

| Check | rc | seconds | log SHA-256 (prefix) |
|---|---|---|---|
| backend-imports | 0 | 6.5 | `01ba4719c80b6fe9` |
| baseline-backend | 0 | 318.4 | `75aafd95348e0d70` |
| backend | 0 | 314.9 | `425856880cc86fcf` |
| scripted-evals | 0 | 2.5 | `047b22e7b2c79ac3` |
| latency | 0 | 0.3 | `c192bbb7b228dedb` |
| knowledge-base | 0 | 3.3 | `928e3932db4e7ca8` |
| baseline-knowledge-base | 0 | 3.7 | `e5f30cfe3a94fcbf` |
| web | 0 | 31.1 | `ab6f464ca2abe72f` |
| native-library | 0 | 78.0 | `99eb0a123e6af1c3` |
| **native-app** (candidate MortimerHost, the suite with nine failures in every earlier receipt) | 0 | 58.8 | `729d33b2d46c04bf` |
| baseline-native-library | 0 | 9.8 | `f04339e0f31d5a35` |
| baseline-native-app | 0 | 57.6 | `847f8a75b260e145` |

Desktop probe: rc 0, 22.4 s, log `adbe9a91…`. Receipt copied to `docs/acceptance/adaptive-interface/receipts/25d16062811a4f478c0d4ba3075f0bcc.json` (4,100 bytes; fingerprints, names, codes, durations, hashes only). The 900-second backend budget is unchanged (both backend suites ran in ~315 s).

This is the plan's acceptance for G20 taken literally ("a passing receipt for a candidate later than `4d188e8`"): `6bf0270` is that candidate. It is **not** yet the C9 gate for the closure edits, because C1–C4 are uncommitted and the sandbox verifies committed trees only.

Second run, on the merge commit `b2955c3` (closure branch merged with `main`, PR #68): attempt `7ef13e358d79483ba5673cb24fe05a94`, **failed** — 11/12 checks passed (desktop probe rc 0), `baseline-native-app` rc 1 with exactly one assertion: `WindowVisibilityTests.testActualWindowHideShowAndDetachUpdateVisibility:49` "Ordering the window out must suspend animation" read `true` after a fixed 0.3 s event pump; the candidate `native-app` run of the identical source two minutes earlier passed (`push-merge.log`, `inspect2.log`). The occlusion event's latency in the guest exceeded a fixed wait once; the fix (`fix/window-visibility-wait`) replaces the fixed pumps in that test with bounded condition waits (3 s) — the assertions are unchanged. The failed receipt is kept as `receipts/7ef13e358d79483ba5673cb24fe05a94.json`.

Third run, on `5035325` (the visibility-wait fix): attempt `d68e28c13b9e4042858b3102f1c772da` — **all twelve checks passed** (baseline-native-app rc 0, 92.5 s) and the desktop probe passed, yet `status: failed` with `source_unchanged: false`: the C3 frame-time test rewrote the tracked `docs/acceptance/adaptive-interface/P4-frame-time.json` during `native-app`, which the verifier correctly counts as candidate mutation (`7ef13e35…` had the same flag under its test failure). Fixed in the same branch: the test now writes under `macos/MortimerHost/.build/` (excluded from capture); see the C3 record's amendment. Receipt kept as `receipts/d68e28c13b9e4042858b3102f1c772da.json`.

Fourth run, on `2837a12` (frame-time JSON moved out of the tree): the verifier aborted before `native-library` with a bare `SandboxError("Guest command failed")` from the keychain re-selection step (`security list-keychains` / `default-keychain` as the worker), verification clone `01ff3480fc10`, after all eight non-native checks had run. The same step had succeeded in the three previous attempts, and `_capture` discarded the command's output, so the cause is undiagnosed. Change: `Verifier.run_check` now records the failing `security` command, its exit code and its output into the check's log before raising (`test_failed_keychain_selection_is_logged_and_stops_the_native_check`); the next occurrence will carry its evidence. Run repeated on the same commit.

Evidence retained: `closure-checks/logs/verify-c5.log` (SHA-256 in `verify-c5.done`), the sandbox home's `tasks/<dev task>/verification/<attempt>/` (receipt, every check log, `desktop-probe.log`). The five disposable diagnostic clones were destroyed at the start of the run (`control.destroy`); the diagnostic scripts stay in `closure-checks/` (ignored) for reuse.

Fifth run, on `8c1fb5a` (the merged tree: `main` at `55d5ac7` = closure C0–C5 + PR #69's three fixes), `closure-checks/logs/fix3.log`, SHA-256 `1e5e0f832ea9d84185918fea6ac6e5e778977224886a2e3a86bea5ca0de55dbd`: **attempt `a56c192c20704ab5a7d59366a9e52d43` — status `passed`, `source_unchanged: true`, 12/12 checks exit 0, desktop probe rc 0 (23.9 s), 1,111 s end to end.** Development task `3e5a1d4b5c82`, verification task `7a21634cb1ec`, candidate = baseline `bb795d04…` (the hydrated tree of `8c1fb5a`), image `32a82fdd…`, profile `c400d0df…`, runner `1b80cf58…` (the runner fingerprint changed with the `run_check` logging fix). `native-app` 90.5 s / `baseline-native-app` 90.0 s (both now include the P4 frame-time gate). The keychain-selection step that aborted the fourth run passed; its new logging did not fire, so the fourth run's cause remains unreproduced. Receipt: `receipts/a56c192c20704ab5a7d59366a9e52d43.json`.

**This is the C9 gate receipt for `main`**: the first fully passing independent verification of a tree that contains C1–C5. Open only: the same run on whatever later commit is deployed (C10). The keychain/Setup-Assistant seeding is specific to the worker account the sandbox creates; a future image with a different first-login flow would fail the probe, not pass silently.

PR: "Sandbox — graphics-attached native verification" (C9 step 3).
