# C0 — Preparation record (closure plan §4 C0)

Date: 2026-09-11. Performed from the Cowork session against the installed checkout `~/jarvis-voice-ai-clean` (HEAD `2ccf66c`) and the candidate `~/Documents/Codex/2026-09-09/can/work/active-repo` (HEAD `6bf0270`, `feat/adaptive-compact-conversation`). No application code was changed. Nothing was committed; every file below is untracked in the candidate for Larry to review and commit.

## C0.1 Rebase check — partial (network unavailable)

- `2ccf66c` is an ancestor of the candidate HEAD `6bf0270` (`git merge-base --is-ancestor`: yes). Candidate working tree is clean apart from the two review/plan documents added today.
- `git fetch origin main` could not run from this session in either checkout ("could not read Username for https://github.com" — no network/credentials in the sandbox VM). The last fetched `origin/main` in both checkouts is `2ccf66c`.
- **Known movement not yet fetched:** `P6-interim-checks.md:92-96` records that PR #64 (the interface plan document) was merged and that remote `main` was `d36299bc` on 2026-09-11. So `origin/main` has moved by at least that documentation commit. Whether anything else landed is **untested**. Larry: run `git fetch origin && git log --oneline 2ccf66c..origin/main -- macos sandbox jarvis/bot` in either checkout and paste the result into this record before C9. If any commit touches `macos/`, `sandbox/`, or `jarvis/bot/`, the C9 rebase order needs re-checking; documentation-only commits change nothing.

## C0.2 Production local-patch inventory — done

Five diffs captured verbatim under `production-local-patches/` with a README carrying what each does, whether the candidate already covers it, and a recommendation. Summary:

- `bundle.sh` — fully covered by the candidate (framework copy + refuse-if-missing, plus signing/verification the patch lacked). Discard at C10.2 per L2.
- `progress_watcher.py`, `admin/server.py`, `launchd template` — 2026-09-08 observability/PATH fixes, not covered; recommended as one small backend PR to `main`, with a unit test for `_live_progress_for_run`.
- `prompts.py` — changes the self-edit confirmation policy (speak preview, confirm in the same turn); **this is a behavior decision for Larry**, not housekeeping; `tests/unit/test_prompts.py` asserts on rule 9 wording and must be run either way.

No credential-shaped strings in any diff. Decision column in the README is blank for Larry.

## C0.3 Pre-existing deviations — done

Appended "Pre-existing at baseline" to `P0-preservation-checklist.md`: the `WakeWordListener` capture tap, the 400×300 / 900×600 dual minimum (900×600 SwiftUI named as the contract), the `GraphImageView` bare `URLSession` (closed by C3.3), and the Edit-draft-on-pop-out loss (closed by L3).

## C0.4 Baseline captures — pending on Larry (needs the Mac)

Not performed: this session cannot drive the installed app. Required before any candidate is installed on the MacBook Air (C8/C10 compare against it):

1. Screenshots of every tab docked and detached; the console at 900×600 and at native size; the display window with two panels; one- and two-screen states if a second display is available.
2. The attach lines from `logs/mortimerhost-window.log` for the current build.
3. Twenty paired trials of connection time and user-stop-to-first-AI-audio on the current WebRTC path (same devices and network as C8 will use).

Store under `docs/acceptance/adaptive-interface/baseline/` with private memory text blurred. This is the §7 comparison baseline; without it the ">10% degradation" gate in C8 cannot be evaluated.

## C0.5 Retire the WebRTC observation design — done

`P2-additive-observation-design.md` now opens with a RETIRED line citing closure L1. No other edit.

## Toolchain limitation for C1 onward

The phases after C0 change Swift and must be compiled and tested by `swift test` on macOS (the project's disposable Tart sandbox or the host Mac). This Cowork session has no macOS toolchain — the cloud workspace is Linux and the device-side shell is a Linux VM — so it cannot compile, run, or verify any Swift change. Writing the C1–C4 edits here would produce uncompiled, untested code, which the interface plan's UI-7 and this plan's "no unmeasured claims" rule forbid presenting as done. C1+ therefore has to run where `swift test` runs: the project's own sandbox implementer (`selfedit_start` with `plan_path=docs/plans/MORTIMER_ADAPTIVE_INTERFACE_CLOSURE_PLAN.md`, one phase per run) or a coding session on the Mac.

## Files produced (all untracked in the candidate)

- `docs/acceptance/adaptive-interface/C0-preparation.md` (this file)
- `docs/acceptance/adaptive-interface/production-local-patches/README.md` + five `.diff` files + `bundle.sh.production-vs-candidate.diff`
- `docs/acceptance/adaptive-interface/P0-preservation-checklist.md` (appended section)
- `docs/acceptance/adaptive-interface/P2-additive-observation-design.md` (status line)
- `docs/plans/MORTIMER_ADAPTIVE_INTERFACE_CLOSURE_PLAN.md`, `docs/reviews/MORTIMER_ADAPTIVE_INTERFACE_PLAN_REVIEW.md` (from earlier today)
