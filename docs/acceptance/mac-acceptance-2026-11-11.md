# Mortimer: revised Mac acceptance checklist

Source: `ROADMAP.md` on `origin/main` at `4e58eaa`, read 2026-11-11 (#322 and #324, merged after it, change no acceptance box). Line numbers below are that file's lines. Companion to [the release closure plan](../plans/MORTIMER_RELEASE_CLOSURE_PLAN.md), whose item ids (A1, C8 and so on) this list uses. Written for Larry, who runs the boxes. Nothing here ticks a box or changes a row; the rewritten boxes reach `ROADMAP.md` only through item C8, after his decisions.

## Counts, checked against the file

117 boxes in `ROADMAP.md` (102 current, 15 parked in WS-23 to WS-26).

| Group | Boxes | What happens |
|---|---|---|
| UI, dropped | 1 | 828 becomes a design rule (below) |
| UI, rewritten for the new design | 19 | Run once, on the final build (section 4) |
| UI, kept and open | 18 | Run now, on the frozen main build (section 2) |
| UI, kept and already passed | 1 | 1064 (WS-18 AirPods switch), nothing to do |
| Non-UI, run now | 9 | Section 2 |
| Non-UI, final build | 11 | Section 5 |
| Non-UI, blocked | 54 | Section 6 (39 current plus the 15 parked) |
| Non-UI, already checked | 4 | 435, 436, 437, 705 |

Run now: 27 boxes (9 non-UI plus 18 kept UI). Final build: 30 boxes (19 rewritten plus 11 final-build), then five days of use.

If you'd rather wait and run everything on the final build: no freeze or `next` branch is needed and every box runs once, but the 27 boxes and the combined-source review start about three weeks later, and any non-UI defect then delays the release by its fix time.

---

## 0. Before anything runs (not yours to do, except the merges)

- [ ] **A1.** Merge #322 (read cap) and #324 (its review log). Claude then adds `next` to the CI triggers in `validate.yml`, `sandbox.yml` and `knowledge-base.yml`; Codex reviews; you merge.
- [ ] **A2.** You record the freeze SHA in WS-17. Claude cuts `next` from it. From here, main takes only acceptance fixes you approve by name; everything else lands on `next`.
- [ ] **A3.** Kimi's combined-source independent review and combined-main validation at the freeze SHA (the WS-17 next step). Claude reviews any files Kimi writes for it.

## 1. Deploy and prepare (about 25 minutes)

- [ ] **M2. Deploy main at the freeze SHA.** `bash scripts/deploy_main.sh` from any checkout. Passing: phases A to D complete (build and all three suites in a throwaway worktree, services restarted, health checks pass, app reopened) and a receipt lands under `~/MortimerRollback/logs`.
- [ ] **548, WS-01 preparation.** Receipts for the deployed build identify source, app, backend, configuration, executable hash and date. Use current answer routing, not the older captions wording.
- [ ] **802, WS-09 preparation.** Same build: record the loaded path, executable hash and date in one manifest that names source, app, backend and configuration. Map each remaining preservation requirement to evidence; the ones this checklist rewrites map to section 4, not to this build.
- [ ] **M6. WS-13 mail card.** Ask Mortimer about your mail. Passing: a card shows Gmail and AT&T, each with its real status and count (never a false zero) and up to ten headlines. With `JARVIS_BRIEF_ENABLED=false`, Mortimer says "Mail isn't connected to me yet."
- [ ] **M7. WS-13 mail preflight.** From production after the deploy: `python scripts/check_mail_env.py`. Passing: PASS, with the mail names actually set.

## 2. Run now, on the frozen build (27 boxes, two sittings, about 2 to 2.5 hours)

Kept boxes test views whose insides don't change in the new design, so a pass now stands. Stop at the first failure in a sitting and send it back; a fix goes to main by name and merges forward into `next`.

### Sitting 1: console and views (about 75 minutes)

- [ ] **201, WS-17 roadmap view.** "Show the roadmap" opens a readable view sourced from `ROADMAP.md`: every workstream, expandable status, owner, next step and acceptance, open work first, nothing silently cut.
- [ ] **205, WS-17 roadmap provenance and refresh.** Shows checkout revision, content hash, read time and whether local content is modified; tells the local checkout apart from GitHub main and the deployed app. Refresh rereads and keeps the same result.
- [ ] **213, WS-17 roadmap filters.** Voice and pointer filters: current blockers, your pending acceptance and decisions, owner, topic plus open status, a named WS's remaining checklist, completed and open work, dated change logs. Chips, counts, combined filters, clear/reset and empty states behave; refresh, sharing and transfer keep the filtered subset.
- [ ] **322, WS-13 brief card.** The brief card renders as its own typed view with the mail summary from M6; an unknown brief version falls back to the plain body.
- [ ] **550, WS-01 Atlas freshness.** Authenticated refresh, source change, empty or partial failure, expired auth, reconnect and late responses; context comes before research results; moving a view doesn't refetch.
- [ ] **551, WS-01 sharing journeys.** Remaining spoken and result actions: preview, copy, save, share and share-cancel, approved inbound transfer. (Its accessibility part moves to rewritten box 882.)
- [ ] **695, WS-03 SW-D recorded runs.** Real successful, failed, skipped, unknown and legacy runs plus reconnect events in the Skills workspace: intended steps stay separate from the actual trace, no invented progress, no extra windows. The owner-scoped part still waits on WS-04 auth.
- [ ] **700, WS-03 SW-I Skills workspace voice and accessibility.** Each control has its voice action; VoiceOver, keyboard, large type, contrast; search and filter persist; usable without hover.
- [ ] **772, WS-07 workflows gallery.** "Show me the workflows" and each Workflows button open the gallery; the availability flow shows three wrapped steps; five draft cards stay dashed.
- [ ] **804, WS-09 Atlas and graph.** Source and provenance, grouping, pins and comparison, graph select, search, filter, path, camera and fallback; honest missing data; refresh, failure and reconnect keep identity and reading state with no duplicate fetch.
- [ ] **806, WS-09 outward sharing.** Real selected text and image: preview, copy into another app, save and reopen, folder access, cancel, return from the Share picker. Only the selected item leaves the app.
- [ ] **807, WS-09 inbound analysis.** Paste, drop, choose and batches show the exact preview, provider/model and progress; cancel, failure, reconnect and cleanup work; malformed, oversize and injected-instruction inputs refuse safely. (In the new design the entry point moves into the composer; the checks inside stay.)
- [ ] **881, WS-11 drawer round trips.** Agents ticker, Repo/Edit/Memory/Runs round trips, Output and Log lineage. Use disposable write targets. (The legacy-layout P0 part is dropped: layouts 0 and 1 are deleted in C1a.)
- [ ] **737, WS-06 spoken status.** Ask which models work, whether services are up, whether the app rebuilt and where you are. Answers use the actual tools, in one turn, with no unsolicited terminal commands or delegation.
- [ ] **739, WS-06 corrected retry.** "Alfreda" then "I meant Alpharetta" succeeds without the old retry lockout.
- [ ] **741, WS-06 graph and source checks.** An unknown graph topic gives the truthful overview; sports answers are structured, or the search fallback is marked unconfirmed. The one-day reconnect log is collected across the following day.
- [ ] **771, WS-07 workflow live record.** Record the workflow-enabled and disabled routing and voice outcomes and the unrecorded end-of-run live checks.
- [ ] **769, WS-07 reply-guard evidence.** Starts now and runs through normal use: Claude reviews real guard events in `log` mode and records precision and false refusals. Nothing for you to do but use the app.

### Sitting 2: second screen, audio and recovery (about 45 to 60 minutes; needs the external monitor)

These five WS-21 boxes stay here because you kept the second screen's grid (decision 4).

- [ ] **468 to 472, WS-21 transfer set.** Send the weather radar to the external screen by voice and pointer: it appears, and success is spoken only after confirmation. Ask again: "already showing", same result, no refetch. Monitor unplugged: says unavailable, opens nothing. Unplug mid-transfer: truthful failure, prior state restored, no leftover window. The inventory matches what's on the screen. Conversation stays on the main window throughout.
- [ ] **883, WS-11 physical audio.** Built-in, headphones, AirPods: mute, push-to-talk, quiet, loud, noise, interruption, output switch, reconnect, sleep and wake, mic denial. No echo-only false turns or duplicate session.
- [ ] **740, WS-06 process recovery.** A long developer run survives a three-minute client disconnect and reports after reconnect (no `Available: none`). The controlled `mcp-web` crash needs its separately approved test scope; skip that half if it isn't approved yet.

## 3. Design rule replacing box 828

- **828, WS-09 single transcript surface (dropped).** The new thread is the only transcript, so duplication can't happen. It becomes a rule in the C0 contracts: one conversation surface, no compact rail, no second copy of live text anywhere. Any view that adds one fails review.

## 4. Rewritten UI boxes (run once, on the final build)

These replace the old wording for the new design: Composed Answers, the result carousel (A in the open area, B as "show all results"), the glass orb, the thread's activity row, inline approvals, the composer and capsule controls. Colours follow decision 2, the approved orb palette: listening `#6673FF`, your teal `#2DD4BF`, Mortimer's rust `#E07020`, OK `#A6FFC1`, the needs-you ring `#FFD84A`, error `#FF598B`. They enter `ROADMAP.md` through C8 with Codex reviewing. Original pass conditions are kept wherever they still apply.

### Conversation and results (WS-17)

- [ ] **192, conversation thread.** Five turns, by voice and by the composer. Both speakers' full text stays ordered, including one answer over 160 characters. While Mortimer works, one activity row under your request names the current step and updates in place; it never becomes a separate message. Ordinary speech creates no carousel card. Reading a card keeps focus while the thread updates. Protected-content rules hold.
- [ ] **193, arrival routing.** The answer to your still-active request comes to the front of the carousel, including a fresh weather-cache hit. Unrelated, background, superseded, stale or cancelled arrivals join the carousel unread without moving focus or the front card. With the second screen open, a web result goes there and the conversation stays on the main window.
- [ ] **194, carousel inventory.** Every card keeps its stable identity; open, pinned and Output history survive; numbered inventory lists pinned cards first; unread and updated markers show on the card and in "show all results"; ambiguous or stale targets get a truthful question, never a guess.
- [ ] **195, carousel controls.** By voice and pointer: select, close, pin and unpin, reopen by number and by subject, step left and right. Actions match what's visible; the carousel stops at both ends rather than looping. With pins plus about ten cards, nothing open, pinned or in Output is discarded; "show all results" shows the same set as the carousel.
- [ ] **196, reuse.** Weather, then Atlanta, then the original weather: two cards. A fresh original (15 minutes or less) comes to the front without fetching and the thread adds a reference line; a stale one refreshes in place under the same identity. (This failed on Oct 17; the repair rides with the carousel work.)
- [ ] **197, dependent closure.** Record the outcomes of 192 to 196 on the final build, then finish 803, 808 and 882. Nothing closes from earlier partial checks.
- [ ] **209, roadmap voice and controls.** Voice shows the roadmap, a named WS item, and refreshes it. Select, pin and close work through the carousel; sharing and confirmed second-screen transfer still work. Viewing never starts a self-edit or changes a box.
- [ ] **219, roadmap acceptance.** Every workstream and acceptance item is reachable, including past character 30,000; the roadmap view works as a carousel card, expanded in "show all results", with VoiceOver, and on the second screen. Missing, malformed or unreadable source and failed refresh are explained truthfully; an old view is labelled stale.

### Controls and recovery (WS-05, WS-01, WS-03)

- [ ] **505, WS-05 route-selection controls.** Native and spoken route selection from the capsule control bar: draft, confirm, cancel, unavailable choices and stale selections. The visible route and the actual route agree; voice, results and monitor behaviour stay intact. (Still blocked on WS-05's route gates; it's listed here because its wording changes.)
- [ ] **549, WS-01 display recovery.** Research, graph and developer results through close and reopen, monitor unplug and reconnect, backend and voice reconnect. One carousel owner on each screen; identities, selection, pins and drafts survive with no duplicate fetches and no window growth. Mirrored and three-screen cases stay open if the hardware isn't there.
- [ ] **694, WS-03 SW-A baseline.** Original skills, the thread with composer, voice, mute and the glass orb, the drawer's tabs, memory, Atlas, sharing and developer grouping keep their behaviour. Preexisting faults are listed separately.
- [ ] **701, WS-03 SW-J creator card.** One or two displays, two research results and a creator run: move, close and reopen, unplug during validation, reconnect and restart. One creator card in the carousel keeps its steps, retries and selection; no duplicates, focus theft, orphans or unintended new job. (The creator run still needs SW-F readiness.)

### Console, voice, load (WS-09)

- [ ] **803, console and accessibility.** The drawer's tabs, header scroll, font size, attention, an unsent composer draft, keyboard (⌘K focuses the composer; Space reaches the focused control and still works as push-to-talk elsewhere), VoiceOver, contrast and notices. Approvals appear inline in the thread in the needs-you yellow (`#FFD84A`) with Approve and Decline; errors are pink-red (`#FF598B`); nothing important relies on colour alone. Live text stays in the thread; voice and mic controls remain.
- [ ] **805, display governance.** One, two, three and mirrored screens, manual placement, return-all, card limit and pin overflow in the carousel and in "show all results". Stable identities, drafts, pins and selection survive; no duplicate renderer, subscription, fetch or window storm. Missing hardware is recorded as a limitation, never a pass.
- [ ] **808, voice parity.** Every enabled action works by voice and by pointer or keyboard: carousel move, select, pin, close and "show all", sharing, inline approve and decline, composer send, graph focus, filter and path. Ambiguous or stale targets clarify or refuse; late or unavailable-display outcomes are truthful; mute, push-to-talk, wake and OS dialogs are untouched.
- [ ] **810, load and glass.** Graph plus six carousel cards plus the largest accepted attachment load, during voice: audio holds and memory stays bounded. Selection p95 at most 16.7 ms, navigation acknowledgement p95 at most 200 ms, graph pan and zoom p95 at most 33.3 ms; more than 10% worse than baseline is a regression. The glass orb and carousel panels follow Liquid Glass on and off, and fall back to flat panels with Reduce Transparency and to still frames with Reduce Motion.

### Coverage and screens (WS-11)

- [ ] **880, coverage.** Freeze the final build's source, fingerprint, loaded artifact, configuration and topology. Map every remaining C8 and native-client row to a dated result against the new design; rows that only described layouts 0 and 1 are closed as removed, with the C1a commit as evidence.
- [ ] **882, visual and accessibility matrix.** Thread and carousel at 900×600, 1280×800, 1440×900, ultrawide and portrait; Retina and non-Retina where available; the drawer docked and detached; overflow and drafts, long and error results, two pins and comparison, graph states, font size, keyboard and VoiceOver. No clipping, lost reading state or unreachable controls. The orb is signed off afresh: it reacts to your voice and Mortimer's, shows thinking without motion when Reduce Motion is on, and stays readable over real wallpapers.
- [ ] **884, monitor tails.** One, two, mirrored and three screens; loss of the screen holding a card or draft; changed order or resolution; manual placement; close and reopen; lock, sleep and Reset Layout. Controls are reachable within 1 second of a stable topology; drafts, cards, pins and graph state survive with no snap-back. (The old layout-rollback case is removed with layouts 0 and 1; rollback is now the deploy snapshot.)

## 5. Final build, non-UI (11 boxes), then five days

Run these with section 4 on the final build (about 90 minutes together), then use the app normally for five days. A material fix restarts the count; calendar time alone isn't evidence.

- [ ] **438, WS-20 evidence linking.** Final Phase A/B exit record links the evidence.
- [ ] **552, WS-01 dependencies.** Dependent rows recorded against the final build.
- [ ] **553, WS-01 release closure.** Five stable days on the final build.
- [ ] **702, WS-03 SW-K performance.** Voice p95 regression at most 50 ms; ten-minute memory growth at most 10 MiB. Codex measures; you run it on the exact Mac and build.
- [ ] **703, WS-03 SW-L release and handoff.**
- [ ] **743, WS-06 completeness.** A week of use with no unsolicited commands.
- [ ] **770, WS-07 guard decision.** You pick `log` or `correct` from the 769 evidence.
- [ ] **773, WS-07 closure.**
- [ ] **809, WS-09 contracts.** Rerun after the layout field lands.
- [ ] **811, WS-09 release closure.** With rollback proof and an independent verifier receipt.
- [ ] **885, WS-11 closure.** Same.

## 6. Blocked (54), unchanged by this plan

- **WS-05 (9: 498 to 504, 506, 507):** your prerequisite decisions, Claude's review of #177, and an eligible confidential route.
- **WS-04 (8: 579 to 586):** your onboarding choice, then Codex builds and proves it, then live preparation and activation.
- **WS-02 (6: 663 to 668):** runtime identity, isolation and account allowance.
- **WS-10 (6: 846 to 851):** needs WS-05's route gates, then your staged approvals and the first 20 real decisions.
- **WS-13 (4: 318 to 321):** the calendar and the rest of P3 are unbuilt; account access still to be supplied.
- **WS-03 (4: 696 to 699):** auth, a real VM, provider budget and maintainer review.
- **WS-06 (2: 738, 742):** probe and catalog scope, sandbox-loop scope.
- **Parked WS-23 to WS-26 (15):** not before closure (decision 7).

## Not tested from this session

- Whether the kept boxes really don't change. That rests on the C0 contracts keeping those views' insides as they are; if C0 changes one, it moves to section 4.
- Session times. They're scaled from the Nov 5 checklist's estimates, not timed.
- The rewritten wording against the built interface. It's written from the mockups and the plan; C8 checks it against the code before it enters `ROADMAP.md`.
- Whether the controlled `mcp-web` crash in 740 has an approved test scope yet.
