# Acceptance campaign — 2026-10-17

Recorder: Codex. Operator: Larry. Session:
`01a14bae-5269-78b0-abe8-6611e9c357dc`. Branch:
`codex/acceptance-campaign-20261017`.

Larry requested all existing acceptance testing, offering human intervention.
New development remains deferred. No provider/source/auth activation, production
source edit, deployment, rollback or feature implementation is part of this slice.

## Candidate identity

- Automated source: `9f9bc71c26c82c832121be118346abaa1b4f89a4` (merged main).
- Installed/live source: `575cc7b770b621b5c8049097ef63e93618ba3016`.
- App: `/Users/larryfix/jarvis-voice-ai-clean/macos/MortimerHost/.build/MortimerHost.app`.
- Executable SHA-256: `6c67661bb94ddde5fa95d0a807dd77e5d837483a69c0d979412064fdcd3eaf29`.
- Bundle configuration: debug. Live app PID: 21674.
- Admin 1045, knowledge service 1052 and bot 1056 use the production working
  directories; their processes started October 13 at 22:33:11 local. October 17
  health checks returned HTTP 200 on ports 7861, 8484 and 7860 respectively.
- Installed source, Info.plist source marker and October 13 deployment receipt
  agree. Source differences through merged main are documentation and the mail
  preflight checker/tests; application/server runtime code is unchanged.
  This affected-file comparison does not equate different Git revisions or
  provide an exact-candidate release receipt.
- Production has one preexisting tracked acceptance-data modification and
  untracked files/directories. They were not inspected or cleaned; the source
  comparison and installed artifact identity do not assert a clean checkout.
- Operator has AirPods, no external monitor. Physical external/mirrored/three-
  display gates remain open.

## WS-18 — passed physical switch gate

At 17:56–17:57 EDT Larry requested the seasons explanation and switched
AirPods → Mac speakers → AirPods during speech. He reported both directions
worked, the app stayed connected, and there was no noticeable silence or only
brief gaps. Codex observed the same PID 21674, READY VOICE and preserved
conversation after the switches.

The bounded audio diagnostics record device-change notifications followed by
`audio output flowing` at 17:56:44.623, 17:56:46.712, 17:56:52.663 and
17:57:03.387, each 200 ms after the corresponding engine start. That 200 ms
value is **not** an end-to-end measurement of the audible switching gap.
Larry's audible report supplies the short-gap observation. This satisfies
WS-18's named live switch criterion on installed `575cc7b`.

This does not close the separate two-AirPods-configuration echo measurements,
earbud-removal, wake/mute, device-denial, interruption or combined-load gates.

## WS-17 — bounded conversation evidence

Larry completed the initial five-sentence autumn-leaves request and four
follow-ups about red leaves, evergreens, a one-sentence summary and two yellow-
leaf trees. He reported complete answers at normal speed. Codex inspected the
ordered user/assistant transcript, including the full five-sentence answer
longer than 160 characters. Ordinary answers created no result cards or tabs;
the microphone was muted after the sequence.

Recognition was not flawless: the initial red-leaves follow-up was
mistranscribed and needed repeating. The forests prompt also needed a
clarification/repetition. Preserve these observations. Protected turns,
reading-focus/scroll/size cases and the remaining card/Recents/reuse cases
remain separate; UI2-22 is not marked complete from this subset.

Larry then asked “Why do leaves fall from trees?” while Folly Beach was open.
He confirmed the complete answer and preserved result focus; Codex observed
Folly Beach still selected, then verified the ordered question/full answer in
Conversation with the same two weather cards. This closes that bounded reading-
focus subcheck, not protected-content or the full UI2-22 gate.

## WS-17 — weather arrivals, reuse and Recents

Requested Folly Beach weather opened from Conversation. While Folly Beach was
being read, requested Atlanta weather preserved Folly Beach and showed a New
notice. Its Show action opened Atlanta; Conversation returned to both cards.
These are bounded UI2-23 passes. Research/image/background/supporting-display
cases remain separate.

**UI2-25 failed:** the correctly transcribed “What's the weather in Folly
Beach, South Carolina?” repeated the forecast but stayed in Conversation,
without a reuse reference line or reopened result. The count remained two.
Read-only agent-event metadata records the initial Folly Beach and Atlanta
weather/radar lookups; no new tool call was recorded for that repeat. This
establishes the missing visible behavior, not successful cache reuse or
stable UUIDs. The UI did not expose UUIDs in the captured accessibility tree.

Two subsequent subject-reopen attempts were recognition-confounded: “Show the
Folly Beach weather again” became “Show the file of each weather again”; “Show
the Atlanta weather again” became “So the Atlanta weather again.” The former
received a raw-files refusal and the latter another forecast. Do not interpret
either as proof that the stored weather result was absent.

**UI2-24 failed: stale Recents and incomplete numbered voice selection:**

1. Open Recents after Folly Beach arrives: its sole row is number 1, Folly Beach.
2. Request Atlanta while Folly Beach is shown. Two cards/results now exist.
3. Reopen Recents: it still shows only “1 Weather · Folly Beach · now,” including
   on repeated menu dismissal/reopening several minutes later. Both the native
   accessibility tree and the displayed menu showed the stale single row.
4. Atlanta's inline Open button correctly opens Atlanta.
5. From Conversation Larry says “Open result number one,” correctly transcribed.
   Atlanta appears and the console reports “Console action applied.” Larry
   confirms Atlanta. However, the assistant says it opened the results view
   and asks which result to open. This does not establish that numeric target
   resolution chose Atlanta; the command did not complete the requested selection.
6. Recents still labels number 1 as Folly Beach. Clicking that row opens Folly
   Beach. Preserve the stale-menu failure separately from the incomplete voice action.

Both bodies remain accessible; this is not evidence of lost weather data.
Keep Recents/reuse and dependent UI2-04/09/13 acceptance open. A menu snapshot
refresh defect is a plausible explanation, not an established root cause.

Card actions also passed a bounded pointer check: Atlanta Pin displayed its
Pinned marker and changed the card menu to Unpin; Compare with Folly Beach
opened both weather bodies; End comparison returned to Atlanta. Unpin and
Conversation restored both cards without the pin marker. Recents still omitted
Atlanta even while pinned. Close/Output preservation and full voice parity
remain open.

## Automated evidence and remaining work

| Check | Observed outcome | Scope / limit |
|---|---|---|
| Roadmap checker; CI policy tests | 0 errors / 0 warnings; 9 passed | Documentation/protocol only |
| Sandbox controller tests and shell syntax | 134 passed; syntax checks passed | Does not substitute for independent VM |
| JarvisKit on host | 232 tests, 0 failures | First restricted toolchain attempt could not initialize; host-permission run passed |
| MortimerHost on host | 551 executed, 6 skipped, 1 failure | Five active-app/WindowServer prerequisites and one external-monitor skip; wide Skills selection p95 22.77575 ms exceeded unchanged 20 ms limit under concurrent load |
| Skills benchmark alone | 1 passed | Wide selection 15.28025 ms, compact 8.5905 ms; cached navigation 49.996 / 30.771 ms under 100 ms. This does not erase the original failure or accept combined load |
| Knowledge service | 17 passed | Isolated environment with declared test dependencies; borrowed environments initially lacked pytest/watchdog |
| Web | Dependency setup and production build passed | Isolated worktree; npm setup used `--ignore-scripts` |
| Scripted latency fixture | Passed | Nondelegated p50 1153 ms ≤1200; delegated 1412 ms ≤2500; overall p90 1353 ms ≤3500. Synthetic, not live latency |
| Initial restricted combined Python | 107 failed / 6582 passed / 15 skipped / 4 errors | Local socket/process permissions and environment contamination; retained, not a product pass |
| Exact failed-node host retry | 111 passed | Narrow rerun only |
| Complete combined host Python | 5 failed / 6688 passed / 15 skipped | One audio-filter factory default and four bot-wiring function lists; 2 subtests passed |
| Separate integration process | 4 failed / 193 passed / 4 skipped | Same four bot-wiring failures; therefore not merely unit-to-integration ordering |
| Separate scripted evaluations | 13 passed | No live provider evaluations |
| Python with automatic dotenv discovery disabled | Pending completion | Same unchanged runtime/tests; clean environment, temporary DB/home and nonexistent vault |
| Independent twelve-check VM | Pending completion | Exact committed `9f9bc71`, unchanged profile; dedicated offline clones, no production config/credentials |

Host runtime/test files match `9f9bc71`; acceptance documentation changed in
the same worktree during execution. Host runs therefore are not immutable
full-tree release receipts. The VM exports committed Git objects and repeats
baseline/candidate checks on that same source; it is not a new historical-
baseline comparison and does not replace the approved October 11 comparison.
The installed `575cc7b` remains a different release identity.

**Python environment investigation:** Pipecat's installed runner calls
`load_dotenv(override=True)` at import, searching upward from its package path
inside the borrowed production venv. The application's import wrapper restores
preexisting environment entries but retains newly added entries. This can
introduce production feature flags into tests even when the test checkout has
no `.env`. The controlled rerun sets `PYTHON_DOTENV_DISABLED=1`; explicit
Pydantic dotenv fixtures remain in the suite. No assertions, thresholds or
runtime code were changed. Initial runs cannot be described as fully isolated
from production configuration; the vault and test database overrides were
explicitly set. No production file was edited.

**Mail preflight remains open:** synthetic, credential-free probes reproduce
both existing review findings in merged `scripts/check_mail_env.py`: variables
unset by the startup shell remain in the parent's overlay, and a relative
`--env-file child/.env` is resolved again after changing working directory.
The first can misreport effective configuration; the second fails startup for
an existing file. These are checker defects, not evidence of live mail failure.
The formal M1-1 production repeat is not closed from this campaign.

## Remaining acceptance disposition

| Area | Disposition after this session |
|---|---|
| WS-18 named output-switch criterion | Accepted from both directions, Larry's audible report and diagnostic corroboration |
| WS-17 UI2-22/23 | Bounded passes above; protected turns, other result kinds/background cases, close/Output preservation and remaining display/size/scroll cases open |
| WS-17 UI2-24/25 | Failed; stale Recents, incomplete explicit voice selection and missing fresh-result reopen/reference require repair and affected-case retest |
| WS-09/11 changed UI2-04/09/13 | Held until WS-17 prerequisites pass; broader accessibility/sharing/load/rollback coverage remains |
| WS-01/09/11 release | Exact release verification, all required outcomes/limitations, rollback and five frozen daily-driver days remain separate; no new release in this session |
| WS-21 physical transfers and multi-display recovery | External/mirrored/three-display hardware unavailable; not passed |
| Remaining audio matrix | AirPods switch passed only; echo benches, interruption, earbud removal, denial, sleep/wake and combined load still open |
| WS-02/05 model and source/runtime gates | Existing source/operator/account/confidential-route and review prerequisites unresolved; no new provider or source authority inferred |
| WS-03/04 authenticated Skills and onboarding | Onboarding implementation/decision and separate credential preparation/activation precede enabled-mode tests |
| WS-06/07 recovery/workflow/guard | Missing eleven-check mapping, route/evaluation prerequisites, genuine guard evidence and mode decision remain; no guard change |
| WS-10 memory rollout | Separate stage approvals, real first-20 review, budgets/benefit/privacy and observation durations remain; no enablement |
| WS-13 | Preserve earlier live mail evidence; current preflight defects and formal production repeat remain; later calendar/brief increments keep their own claims/decisions |
| WS-20/22 | Evidence publication does not close the full roadmap or change checker enforcement; new-development workflow stays parked |

Unavailable or unbuilt prerequisites are not failed tests, and no missing
hardware or observation duration has been silently waived. The next development
slice should repair acceptance blockers before starting WS-22.
