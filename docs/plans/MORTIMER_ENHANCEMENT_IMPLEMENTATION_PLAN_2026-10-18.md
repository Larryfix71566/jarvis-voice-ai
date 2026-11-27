# Mortimer enhancement implementation plan

**Date:** 2026-10-18 · **Roadmap authority:** [WS-27](../../ROADMAP.md#ws-27)
**State:** documentation only; proposed implementation and all benchmarks parked.
**Source baseline:** main `28420af29191716945e55f6aeec1f0fd125ea931`; refreshed
to documentation-only main `9ea27c7` after #218/#219 merged during publication.
**Planning preference:** GPT-6.1 Sol, high effort, as requested by Larry; this is
not a claim about independently observed model telemetry.

This plan turns the discussion into staged, reviewable work after the current
release and acceptance campaign. Its technical appendices are the
[sandbox voice evaluation protocol](MORTIMER_VOICE_EVALUATION_PROTOCOL_2026-10-18.md)
and [private local-model runbook](MORTIMER_PRIVATE_LOCAL_MODEL_RUNBOOK_2026-10-18.md).
They are parts of this one plan, not additional workstream claims. No model has
been installed or benchmarked for this plan; all result cells remain unmeasured.

## 1. Authority, baseline and dependencies

The Git [master roadmap](../../ROADMAP.md) remains the shared record for Codex,
Claude and Larry. Existing acceptance gates retain priority. A plan review is
not permission to implement, enable a provider, spend money, grant credentials,
change security settings, merge, deploy, send messages or ingest private data.
Before each later slice: fetch main, reconcile claims and PRs, dispatch a named
owner/branch/scope, reserve any new identifiers, and preserve existing owners.

| Evidence inspected on 2026-10-18 | Consequence for this plan |
|---|---|
| Main `28420af`, merged #216; draft [#218](https://github.com/Larryfix71566/jarvis-voice-ai/pull/218) head `7da4a91` | Source repair is distinct from installed build, deployment and live acceptance. #218 merged as `0b49706`; its WS-17 status update is incorporated without changing release gates. |
| Later merged [#219](https://github.com/Larryfix71566/jarvis-voice-ai/pull/219) head `40c357d` | It merged as `9ea27c7` during publication. The intake, four parked cards and WS-22 dependency note are preserved; do not create competing verification/task/commitment/event systems. |
| [WS-22 evidence workflow](MORTIMER_EVIDENCE_WORKFLOW_IMPLEMENTATION_PLAN.md) | Reuse investigation, requirement/evidence and handoff contracts; reconcile schemas with proposed WS-24 before code. |
| [WS-05 model access](MORTIMER_MODEL_USE_ENHANCEMENTS_PLAN.md), [access config](../../config/model_access.yaml), [route clients](../../jarvis/model_routing.py) | Existing policy/execution boundaries are the integration authority. `local_runtime` is declared but both sync/async clients explicitly refuse with “local model runtime is not configured.” A localhost URL alone does not implement the private route. |
| [Pipeline](../../jarvis/bot/pipeline.py), [observer](../../jarvis/bot/transcript_log.py), [prior voice bench](MORTIMER_VOICE_MODEL_BENCH_PLAN.md) | Current source separates Deepgram Flux `flux-general-en`, conversational LLM and ElevenLabs Flash TTS. Source supports native Google, native Anthropic (conditional on `native_enabled`) and OpenAI-compatible service paths. Effective installed model/adapter/settings must be observed later. The existing observer measures backend speaking-stop → outbound audio frame, not acoustic end → actual client playback. Preserve historical bench results and locked backend targets; do not treat them as new playback results. |
| [WS-13 canonical revised mail plan](MORTIMER_MAIL_CALENDAR_BRIEF_PLAN.md), [architecture](../ARCHITECTURE.md) | Local bounded IMAP header reader and deterministic protected brief P1–P3 precede optional private model-written P4 and interactive P5. Larry already has mail in his daily report; the actual deployed report path remains unverified. Extend verified gaps only. |
| [#210 findings](../roadmap-log/2026-10-17-ws-20-codex-three-pr-review.md), [later claim evidence](../roadmap-log/2026-10-17-ws-17-codex-ui2-24-25-repair-claim.md) | #210 merged as `34e5d55` despite the stale deletion-plan race and omitted cleanup runner fingerprint. Diff of its head `8842503` to inspected main for `sandbox/prune.py`/`sandbox/verify.py` is empty. No prune/reclaim or normal clone path that invokes it until independently repaired/reviewed. |

Only #218 and #219 were open at initial preparation; both merged during
publication. Main `9ea27c7` is incorporated with both documentation intents
preserved; only draft #220 remained open at refresh. Active runtime locks remain
untouched. The source inventory links retain their original commit for stability. No pending Codex
conflict grants scope here, including WS-04 onboarding (CX-11). Resolve owning
rows' blockers there; this documentation does not start feature work.

## 2. Scope, roles and routing contract

Preserve the Supervisor and the six specialist roles in
[agents.yaml](../../config/agents.yaml): Scheduler, Librarian, Analyst, Systems,
Developer and App Builder. Do not add a general autonomous “acceptance agent.”
Proposed role labels below describe responsibilities, not assignments to Claude,
Codex, running agents or other sessions.

| Work package | Proposed responsible role after dispatch | Dependencies and boundary |
|---|---|---|
| Host routing/state and evaluation harness | Assigned runtime engineer + independent reviewer | WS-05/06/07 and current locks; harness separate from live pipeline |
| Verification checklist | Systems constrained verifier | Proposed WS-23; evidence only, no repair/release authority |
| Durable tasks/checkpoints | Assigned lifecycle engineer | Proposed WS-24 + WS-22; select existing authority first |
| Commitments and relevant events | Scheduler + Librarian responsibilities | Proposed WS-25/26; host timing, source/privacy rules and WS-24 |
| Private model/provider and retrieval | Assigned local/privacy engineer | WS-05/10, T3/T4 and WS-13; synthetic proof before records |
| Mail/report extensions | Existing WS-13 owner, after fresh claim | No reassignment; read-only isolated mail tools |
| Product decisions, listening and releases | Larry | Explicit gates; no proposal below delegates his authority |

### 2.1 Workflow first, then agent and tools

Host resolution order: **target + existing task ID → workflow → eligible
agent/model → permitted tool subset**. Resolve a known task before classifying
its wording as new work. Preserve deterministic UI/status/weather shortcuts;
material ambiguity gets one focused clarification rather than a guessed target.
Reuse current durable self-edit/app-build/planning authority and UUIDs.

| Initial workflow | Target and allowed behavior | Must not do |
|---|---|---|
| Mortimer repair | Own repository, exact source/revision, inspect → propose → separately authorized execute through existing self-edit service | Supervisor edits code itself; new job for an existing task; bypass sandbox/review/deploy |
| Separate-app change | Explicit external application/workspace ID, App Builder workspace seam and existing job/approval | Route an unspecified app into Mortimer self-edit or broaden source access |
| Existing-task status | Authoritative task/run ID and evidence, read-only status or clarification | Start/retry/commit/publish because a status question mentions those words |

Resolve Supervisor/Developer/App Builder conflicts by making this contract
common to prompts, host dispatch, schemas and UI. Supervisor may retain bounded
direct chrome/status/weather tools; Developer handles Mortimer investigation and
repair, App Builder a separate app. A repository plan uses the existing planning
pathway. Requests such as “commit these changes” must either perform the exact
already-authorized direct action through its host gate or obtain the material
missing authority, rather than merely say it can. An eval passes only when the
expected allowed call graph and final state occur. Existing routing floor ≥90%
remains; the newer evaluation protocol proposes stricter targets for review.

### 2.2 Enforce capabilities outside prompts

Define host-owned modes, with tool inventories filtered **and invocation checked**:

- **Inspect:** admitted source/status/read tools only; no mutating calls or tool
  side effects through nested delegation.
- **Propose:** inspect plus bounded draft/artifact creation in the task workspace;
  no execution, publication or live settings changes.
- **Execute:** only authorized workflow operations with exact target, approval
  scope, expiry, privacy label, idempotency key and retained task authority.

Approval, tool/argument/source validation, money limits, model floor and
cancellation are host checks. A confident model, a verifier pass, retrieved
instructions or another agent's handoff cannot enlarge them. Benchmark token,
iteration, timeout and concurrency budgets on real workload classes in the
sandbox before proposing changes; preserve current caps until separately decided.

### 2.3 Librarian selection and communication

Select the store by user intent and retention/privacy, not tool availability:
short durable personal facts/corrections → existing memory admission/review;
explicit authored note → notes; long source-backed knowledge → KB retrieval and
its existing digest path. `mcp_kb` is read-only today; do not expose its internal
write/delete functions as a shortcut. Resolve contradictions with provenance and
existing WS-10 staged approval. No new fourth general memory store.

Private finance/email and derived facts must not enter ordinary memory/notes/KB,
cloud embeddings, session extraction or a general conversation replay. Preserve
labels through retrieval, tool returns, drafts, errors and background jobs.
Speech may be brief (“The task is queued; I’ll report the result”) while the
protected/full artifact retains complete requirements, reasoning evidence,
failures and next steps. Spoken brevity must not truncate stored work or imply
completion before evidence exists.

## 3. Phases and exit criteria

Every phase is proposed. Existing acceptance closure and a fresh scoped dispatch
are prerequisites to new development; offline document review can happen now.
The sandbox evaluation sequence below is agreed in direction, not authority to
build the harness, install assets, record audio or make billable calls.

| Phase | Implementation tasks after authorization | Acceptance/tests and exit gate |
|---|---|---|
| P0 — Reconcile and freeze | Record source, installed artifact/hash, backend PID/config and effective Haiku endpoint/adapter/settings separately; inventory deployed daily report and existing task/run/outbox stores; refresh current main/PRs and cleanup blockers | Exact-source evidence map; no false gate closures. Larry resolves existing acceptance and assigns bounded work. Missing deployed identity stays unknown. |
| P1 — Sandbox voice measurement and optimization | Standalone harness, isolated test client/config/ports/storage, immutable incumbent baseline. Add acoustic/end/transcript/LLM/tool/TTS/render timing. Optimize shared turn detection, streaming and buffers by one-factor ablations; retest incumbent | Full [protocol](MORTIMER_VOICE_EVALUATION_PROTOCOL_2026-10-18.md): production untouched, attribution proven, pause/correction/barge-in/cancel/duplicate regressions pass. Freeze optimized shared cascade before comparison. |
| P2 — Newer models and architecture decision | Track A fixed STT/TTS conversational models; bounded per-model dev tuning; held-out comparisons. Separately Track B baseline/winning cascade versus Live/Realtime frontends with same backend; optional fully local Track C | Quality/privacy hard gates, real playback p50/p95, costs and listening preference with uncertainty. Publish no-winner if inconclusive; Larry chooses direction. Jev remains ON HOLD until this resolves. No automatic production switch. |
| P3 — Agent/workflow contract | Implement §2 in fresh scopes: target/task resolution, host inspect/propose/execute, store selection, truthful states and expected-action routing evals | Stubbed end-to-end allowed/forbidden call graphs; identical user request cannot create duplicate workflow. Unauthorized tools refuse even when directly invoked. Full artifacts survive brief speech. No timeout/concurrency increase without measured budget decision. |
| P4 — Durable lifecycle and verification | Under proposed WS-24 and WS-23, inventory/reuse authority, add missing checkpoints/fencing and constrained evidence verifier; integrate WS-22 rather than new stores | Restart/kill/network/cancel race tests and seeded bad evidence. One task identity, fenced stale workers, idempotent outbox, correct failed/blocked/untested verdicts; missing physical evidence never passes. |
| P5 — Local private route and synthetic retrieval | Implement missing local provider boundary under WS-05 after runbook proof. Host labels, before-recording mode selection, private sinks, protected local retrieval, deterministic financial arithmetic and encrypted user-presence tier | [Runbook matrix](MORTIMER_PRIVATE_LOCAL_MODEL_RUNBOOK_2026-10-18.md#6-test-matrix-and-release-gates) passes including runtime unavailable/no fallback, synthetic leakage, injection, lock/expiry, arithmetic and combined-load tests. Hardware/quality gate + Larry's private-data pilot approval; no real records before then. |
| P6 — Mail Q&A, commitments and events | Extend existing daily report only for verified missing P4/P5 behavior under WS-13; proposed WS-25 commitments and WS-26 relevant events reuse WS-24/outbox/reminders | Source-cited bounded read-only mail answers, explicit incomplete retrieval, no duplicate brief. Corrections/cancel/completion suppress stale reminders; no inferred commitment becomes authorization. |
| P7 — Optional pilots and release | If P2 decision supports it, separate scoped production integration of selected cascade/frontend. Jev decision-only experiment may be considered later. Canary/rollback under existing release owners | Independent exact-build verification, Larry listening/live acceptance, content-free diagnostics and approved rollback; separate merge/deploy decisions. No optional work is implicitly scheduled. |

### 3.1 Voice optimization details

P1 must compare Flux semantic end-of-turn against the existing Silero fallback
without blindly reducing the present `stop_secs=2.5` pause tolerance. Trace which
end event the installed aggregator actually uses. Measure pause retention,
corrections (“Boston—actually Atlanta”), background speech and false barge-in.
Test TTS chunk size/first useful phrase, stream flush and playback/jitter queues
individually; record tradeoffs in intelligibility and interruption stop time.
Keep the unchanged snapshot and ablation receipts. Improvements belong only to
the sandbox variant until the separate production decision.

Speculative preparation, if separately approved, may only perform bounded
read-only preparation with no externally visible side effect. Cancel and discard
it when speech resumes. No tool execution, reminder, edit, message, commitment or
other action may originate from provisional transcripts. Speech interruption
stops speech; it does not cancel durable work unless the user asks to cancel it.
Late results must bind to the original task and be suppressed or delivered
according to that task's current state, privacy and notification policy.

### 3.2 Optional voice frontend versus existing cascade

Evaluate both improving the existing pipeline and a separate full-duplex voice
frontend over Mortimer orchestration. Do not assume migration is necessary.
The primary comparison fixes backend model, prompt, tool fixtures, delays,
authority and task IDs. Compare native frontend tool-calling modes separately
so a changed backend does not masquerade as better audio latency. Specify
asynchronous result correlation, reconnect/session expiry, interruption versus
cancellation, long-running work, context transfer, idle session billing and
private-mode boundaries. Cloud frontend audio is ineligible for private finance
or mail by default even when the backend is local.

### 3.3 Jev — ON HOLD

Do not integrate, acquire credentials or benchmark Jev until voice optimization
and newer-version comparison are resolved and Larry makes a fresh decision.
Only then consider one typed bounded public/synthetic decision pilot (e.g.
select a workflow from a closed list with abstention). It must **replace** a
slower decision and demonstrate net end-to-end benefit, not add a serial model
hop. No text/audio generation, private content, permission authority or automatic
execution. Host checks still decide whether an option is allowed.

[TypeSafe models](https://docs.typesafe.ai/models) documents versioned Jev IDs
and moving aliases; pin a version and record the returned version if a later
pilot is approved. [Confidence](https://docs.typesafe.ai/confidence) is derived
from answer distributions, not a permission or correctness guarantee.
[Legal](https://docs.typesafe.ai/legal) describes default retention and enterprise
ZDR: verify the exact account/endpoint terms before any pilot. No such account
configuration is established here. Official documentation checked 2026-10-18.

### 3.4 Bitcoin research, then a native workspace

This public-market research track takes **Option 2 → Option 3** under this
plan. It follows existing acceptance priorities and requires fresh, scoped
dispatches for implementation. It is not part of WS-35 C9 or the active
WS-37 interface and WS-38 request-resolution work.

#### Option 2: Read-only research skill and chart-first result

- Start offline with a pinned, independently reproducible BTC/USD daily
  snapshot. Use one deterministic local calculator and a dated output shared
  by the card, exports, Daily Brief and future workspace. Record the provider,
  licensing, input checksum, price fixing time, acquisition time and method
  version. Use synthetic fixtures in source control unless redistribution is
  cleared. Carry both the provider date label and UTC fixing time; Coin Metrics
  daily `PriceUSD` labeled D fixes at the following UTC midnight.
- One explicit voice or typed request returns one result in the existing
  carousel. Put the daily price chart first, with the preceding 84-day closing
  high and low lines, 200-day moving average, provisional low, retest and
  reversed-signal markers. Give the cutoff, stance and next condition in text
  alongside an accessible chart summary. Reuse the existing graph/media result
  and authenticated asset path described by the
  [interface contract](https://github.com/Larryfix71566/jarvis-voice-ai/blob/00af821c18819bd6735240f2b588c8f521c908f1/docs/contracts/MORTIMER_INTERFACE_CONTRACTS.md);
  verify asset loading rather than assuming local file URLs work. Do not change the
  bar-only v1 chart contract. If the image cannot display, return the same
  figures and stance as text. No new permanent navigation.
- The rolling band excludes the current close. Use 200 consecutive closes
  through the current fix for the average. A recovery trigger requires both
  a close above the prior 84-day closing high and seven consecutive closes
  above their respective 200-day averages. Missing dates or insufficient
  warm-up make the affected signal unavailable. Track a provisional low and
  any later lower close; distinguish a partial recovery, a qualifying signal
  and a reversal. Historical lows are retrospective, and halving midpoints are
  context, not signals. Show historical misses and sample size, not an implied
  probability. Secondary ETF, macro, on-chain and sentiment evidence stays
  separately dated; social posts are leads, not indicators.
- **Exit:** Validate calculations against frozen reference values, including a
  later reversal and no look-ahead. On the identified Mac app and bot build,
  verify voice/typed parity, chart-without-Inspect, accessibility, text fallback,
  stale/missing data and intact approval and protected-content behavior. Larry
  records the gate before Option 3 starts.

#### Backtest of the recovery rule (amended 2026-11-26)

Larry asked for backtesting on 2026-11-26. TradingView has no data API, so it
stays an optional manual check; the backtest is the Option 2 calculator run
over full history, not a second implementation.

- **Data:** Coin Metrics community `PriceUSD` daily (CC BY-NC 4.0, no key, no
  cost). Its GitHub CSV archive covers 2010-07-18 to 2026-05-23 with no gaps
  but stopped updating on 2026-05-24; the tail comes from the keyless
  community API, unverified at writing. The first build step checks that
  endpoint and records whether `PriceUSD` is still offered after Coin Metrics'
  announced community-data retirements (Talos, 2025-10-27); if not, use the
  free CM Reference Rate and record a method change. Pin the joined file as
  the snapshot above. Run a one-time Bitstamp daily-close comparison as a join
  check only; never mix series. Keep real data out of git; commit the
  manifest, checksum and synthetic fixtures.
- **Replay:** for every fix time after warm-up, call the same calculator with
  only rows whose fix time is at or before it, and store each day's state.
  Reports come only from that table. A faster incremental path must match the
  truncated call on sampled dates. A future-perturbation test (change every
  price after a date; the state at that date must not change) proves no
  look-ahead. The replay uses the provisional low; the retrospective low is
  report-only.
- **Cycle definition:** a bear starts at the first close at least 50% below
  the prior all-time closing high and ends at the next new high. Through
  2026-05-23 that gives seven completed bears, three since 2014.
- **Report:** one row per bear: start, low (marked retrospective), broken
  provisional lows, first partial recovery, first qualifying signal, delay
  and percentage above the low, reversals, the close 180 days after the signal
  and the worst drawdown inside it (unfinished until 180 days pass). Totals
  give cycles, signals, reversals, signals lower after 180 days, data range,
  snapshot checksum and method version, plus every firing outside a bear.
  Counts with sample size only; never an implied probability.
- **Overfitting guard:** the 84-day, seven-close, 200-day and 180-day values
  are fixed as written before the first run. The backtest has no tunable
  parameters and the product has no parameter sweep. A later rule change is a
  written plan change, decided on data through 2018 and reported separately
  for 2019 onward.
- **Exit:** the Option 2 exit above, plus synthetic series (flat, V-shaped,
  slow grind, reversal), rule edges (equal is not above, six closes is not
  seven, current close excluded), missing dates, checksum refusal and
  card/brief/replay parity for the same fix.

#### Second indicator: price against the 4-year average (amended 2026-11-26)

Larry asked on 2026-11-26 to test a claim from a paid trade-alert seller's
video: dips below the 4-year moving average marked buying zones. It is a lead
under test, not a trusted signal.

- **Definition:** the mean of the previous 1,460 daily closes, current close
  excluded; the indicator is the close's distance from it. Same calculator
  module, replay and future-perturbation test as the recovery rule. Warm-up
  means it starts on 2014-07-17 for Bitcoin and is unavailable before.
- **Report:** one row per episode below the line (episodes split by a 90-day
  gap): first and last close below, days below and longest run, further
  drawdown before the turn, closes 180 and 365 days after the first close
  below ("unfinished" until then), and every bear it missed, with totals,
  data range and checksum. Counts with sample size only. The 365-day horizon
  is fixed for this indicator only, before the real run.
- **Orientation probe (unpinned CSV, not committed):** five episodes since
  2014 (January and August 2015, March 2020, June 2022 to March 2023, June to
  October 2023); all higher 365 days later, one lower at 180 days, a further
  22% fall after the first 2022 close below; it missed the 2018 bear (4.5%
  above the average at the low).
- **200-week variant:** the previous 1,400 closes, reported beside it in the
  backtest only; the product shows the 4-year average alone.
- **Total crypto market cap:** optional and not built. No free, verified
  daily history source was found; a claim must name its source and cost
  first, and the series is never mixed with Bitcoin's.
- **Where it shows:** a line on the workspace's long-range chart, a context
  line on the card and in the Daily Brief ("Bitcoin is X% above/below its
  4-year average") from the daily fix. Never a buy signal and never an input
  to the stance.
- **Exit:** window excludes the current close; fewer than 1,460 closes is
  unavailable; equal is not below; no look-ahead; card, brief and replay
  agree on one fix.

#### Daily Brief: One Bitcoin recommendation

After the Option 2 card, add a separately gated section to the **existing**
Daily Brief; it does not wait for Option 3. Use the same local calculation
from public data. Give a concise market stance (**Wait for confirmation**,
**Watch the recovery**, or **Recovery rule met**), the main reason, one
condition that would change it, and the UTC cutoff. Lead with a change,
broken provisional low, or reversal; otherwise label the stance unchanged.
A trigger is not proof of a bull market. Do not use holdings, suggest position
sizes or prices to trade at, or place orders. If spoken, read the stance and
one next check under the existing protected-output rules.

Enable only after testing a current-data path and setting a provider-specific
grace window. A missed daily fix beyond that window yields **No fresh call**
and the last verified cutoff, not a recycled recommendation. Delayed secondary
feeds can be omitted or labeled with their own cutoff. Bitcoin failure must not
hold up mail, calendar, or the rest of the brief. Keep confidential brief
inputs and outputs on their existing path; the market tool receives no mail or
calendar payload, no cloud model gets the combined brief, and the public
composed-answer path cannot carry confidential results. Reuse the existing
cadence, with no separate notifications or schedule. Verify all stances,
reversals, unchanged and missing data, card/brief parity for the same fix,
and isolation from other brief sections.

**Frozen acceptance example (not a current recommendation):** “Wait for
confirmation. The July low is still provisional. Watch for seven closes
above the 200-day average and a close above the prior 84-day high. Data:
November 23, 2026, 00:00 UTC.” The frozen fix is $61,103.71; its 200-day
average is $72,319.11 and prior 84-day closing high is $86,520.80.

**Additions (amended 2026-11-26):** Larry asked that what the backtest and
live price add reach the brief. The rules above still bind: one stance from
the daily fix, no holdings, sizes, trade prices or orders, and a Bitcoin
failure never holds up the brief. Defaults:

- **Progress toward the rule (on):** closes above the 200-day average out of
  seven and the prior 84-day closing high to beat, from the daily fix.
- **History clause (on change days only):** when the stance changes, a
  provisional low breaks, the rule fires or a signal reverses, one clause of
  backtest counts with the sample size and data range (for example, fired
  after N of M past bears; K were lower 180 days later). Never a percentage
  chance.
- **Last price (on):** one public fetch while the brief is built, with its
  venue and time, labelled as not a close and never used for the stance. It is
  omitted as "live price unavailable" after a 5-second timeout and never
  delays the brief.
- **Cycle age (off):** days since the last halving against past cycles at the
  same age; context only.
- **4-year average (on):** one context line, distance from the 4-year
  average at the daily fix; never a buy signal or a stance input.
- **Spoken:** still the stance and one next check only.

#### Option 3: Native Mac workspace

Open from the Bitcoin result first; a command-palette entry can follow. Put
charts above the evidence and sources:

1. **Current bear:** Default view, with toggles for price, closing-high and
   closing-low lines, and the moving average. Surface the provisional low,
   retests, prior signal reversals and current rule state.
2. **Past recoveries:** Separate historical lows from first qualifying signals;
   show delay, price difference and available 180-day outcomes, including
   failures. Do not grade an unfinished horizon.
3. **Halving cycles:** Compare cycles at the same age. Label observed versus
   estimated calendar midpoints and distinguish them from the mined halfway
   block. Do not use either midpoint as a trading signal.

Review and separately claim a bounded, versioned, read-only native series
payload. Keep v1 bar charts unchanged and fall back to the Option 2 card and
text for older clients. Verify keyboard and VoiceOver access, large text,
contrast, narrow windows, and performance against the existing Mac gates.
iPhone follows separately after its result transport and device acceptance.

Use fresh owner/branch/scope claims before code, including any shared renderer
or routing handoff. A separately scoped public refresh may atomically replace
a validated local snapshot; on failure retain the last known good snapshot
and show its age. Keep rollback independent of other routing and preserve the
card fallback. No accounts, exchange credentials, orders, background
monitoring, deployment or harness-controller changes are part of this design.
The 2026-11-26 live price layer below changes the background-monitoring line
only as far as polling while the workspace is on screen and single fetches
for a card request or brief.

**Live price layer (amended 2026-11-26):** Larry asked for current pricing
shown as a graph next to the snapshot charts.

- Draw a live point and a "today so far" candle at the right edge of the daily
  chart and the halving-cycle graphs, styled apart from closed days, labelled
  with venue and time, with a stale warning after 2 minutes without an update
  and "No live price" when the feed fails. Snapshot series are unchanged.
- The Option 2 card makes one fetch per request and shows a "last price" line;
  it does not poll.
- Default feed: Kraken public Ticker (`/0/public/Ticker`, no authentication
  declared, today's open/high/low start at midnight UTC, matching the daily
  fix day). Fallback: Coinbase Exchange public ticker (documented public limit
  10 requests per second per IP). Poll every 30 seconds only while the
  workspace is on screen; stop when hidden, minimised or closed. No background
  task, schedule or notification. Check both venues' terms at claim time.
- A live price is never a close: stance, rule, backtest and brief stance read
  daily closes only. After the UTC day changes the candle reads "awaiting
  official close" until the next validated daily fix.
- **Exit:** feed down, stale and malformed replies; polling stops when hidden;
  changing live values moves no computed state; every live value shows venue
  and time.

#### Dashboard charts and reference bands (amended 2026-11-27)

Larry asked on 2026-11-27, in his Claude Duet channel, for charts for the
Bitcoin data (21:41:16 UTC, "I want some charts/dashboards for the bitcoin
data as well"), for upper and lower bounds on the chart (21:43:05 UTC). Offered
the power-law corridor, the rainbow chart, Mayer Multiple bands and Bollinger
Bands, he answered "Add each of the are beneficial" (21:44:40 UTC). He agreed
to a short brief with the charts on a dashboard (21:46:03 UTC, "Agreed. I like
to see axis data for each for reference") and asked for these to be added to
Mortimer (21:47:05 UTC). The brief layout itself is a WS-13 change, proposed
for the mail, calendar and brief plan §R.0g in PR #428. A test stand-in of the dashboard,
built outside Mortimer from this section's rules, is the prototype; nothing
here depends on it.

**Rule that binds every band:** the four bands are reference lines drawn on
charts. They are never inputs to the stance, the recovery rule, the 4-year
average line, the backtest or the history clause, and the brief's stance text
never names a band. A band is computed only from validated daily closes of the
pinned snapshot above, never from a live price, and draws nothing where its
window or warm-up is incomplete. No band label says buy, sell, cheap, expensive
or any equivalent.

**Three charts.** One plain line of text under each chart says where the
latest close sits; that line is also the chart's accessible summary.

1. **Cycle view (all history, log price).** Daily closes from the first
   snapshot row, the power-law corridor's floor and ceiling, and the rainbow
   zones between them. Plain line, for example: "The close is 1.9x the
   power-law floor, in zone 3 of 9."
2. **Stance view (last 365 days).** Daily closes, the 200-day average and the
   prior 84-day closing high exactly as Option 2 defines them, and the Mayer
   bands. Plain line, for example: "The close is 0.84x its 200-day average."
3. **Short-term view (last 90 days).** Daily closes and the Bollinger Bands.
   Plain line, for example: "The close is inside the bands, in the lower
   third."

**Axes on every chart.** Larry asked to see the axis data on each chart. Every
chart has a title, a labelled date axis with tick values (years on the cycle
view, months on the other two), a labelled USD price axis with tick values in
dollars, a legend naming every line and band, and a footer with the source and
the daily fix it was drawn from. The cycle view's price axis is logarithmic,
says so in its label, and puts ticks at round values that stay readable at
the narrowest supported window. Tick labels never overlap or truncate.

**Proposed defaults, open for Larry's decision.** These were proposed by
Claude, not chosen by Larry; each needs his yes, or another value, before a
claim builds it. Each is a fixed, written parameter, never tuned against the
backtest.

- **Power-law corridor:** an ordinary least-squares fit of log10(close)
  against log10(days since 2009-01-03), over every snapshot close through the
  fix, refitted at each daily fix. The floor and ceiling run parallel to the
  fit, offset by the smallest and largest residual through the fix, so by
  construction they contain every past close; the chart says so, and the
  corridor is described as a fit to the past, not a forecast. Coefficients,
  fit window and offsets are recorded with the output. Alternative: published
  fixed coefficients from a third-party model, which adds an outside
  dependency.
- **Rainbow zones:** nine zones of equal width in log price between that
  floor and ceiling, numbered 1 (lowest) to 9 and coloured from cool to warm,
  with no trading names (the popular chart's labels such as "fire sale" are
  not used). Alternative: a separate log regression fit, as some published
  rainbow charts use.
- **Mayer bands:** 0.8x and 2.4x the 200-day average defined in Option 2
  (no second average). The plain line gives the close's Mayer Multiple
  (close divided by that average) to two decimals.
- **Bollinger Bands:** a 20-close simple average through the fix, plus and
  minus 2 population standard deviations of the same 20 closes.

**Where it shows.** The three charts are a dashboard that opens to the latest
validated daily fix every time, from the brief's Bitcoin section, the Option 2
result and the command palette. Proposed default: the dashboard is the Option 3
workspace's default view, ahead of its current-bear, past-recoveries and
halving-cycle views, and it uses the same reviewed, versioned native series
payload; the v1 bar-only chart contract does not change. Until Option 3 lands,
the brief and the Option 2 card are unchanged and show no dashboard control.
Alternative, also open: an earlier dashboard result in the carousel, rendered
as chart images through the existing graph/media asset path. The dashboard
holds public market data only: no mail, calendar or other brief content
reaches it, and the market tool still receives no brief payload. The live
price layer may draw its live point on the stance and short-term views; it
moves no band, line or plain-line text.

- **Exit:** frozen reference values for each band on synthetic series and on
  the pinned snapshot's fix of 2026-11-23; every band unavailable, not zero,
  before its warm-up (200 closes for Mayer, 20 for Bollinger); a parameter-perturbation test (change every band
  parameter; stance, rule state, 4-year line, backtest output and brief stance
  text are byte-identical); a live-price test (changing live values moves no
  band); every chart shows labelled axes with tick values, a legend, the
  source and the fix on the identified Mac build, including the narrowest
  window, large text and VoiceOver reading the plain line; the plain line and
  the chart agree for the same fix; no band label carries a trading word; and
  card, brief and dashboard show the same fix.

## 4. Durable task, evidence and proactive follow-through contract

The proposed WS-24 record is the overall-task authority; agent runs, attempts,
results and notifications are related identities, not interchangeable IDs.
Select/reuse existing SQLite job/task/run storage and outbox/reminders before
proposing a schema. Reconcile WS-22's lifecycle with that choice. No migration
or new daemon is reserved by this document.

Persist goal/source request, owner, workflow/target, requirement/stopping
condition, approval/privacy scope, dependencies/blocker, next check, attempts,
checkpoint, evidence and pending result delivery. Host transitions distinguish
**queued, running, refused, failed, cancelled and complete**; blocked/waiting
conditions must also be explicit. Map legacy states without inventing a success.
Accepted/enqueued is not running; successful tool transport is not task complete;
a refused preflight is not a failed execution; stopping audio is not cancellation.
Use exclusive claims, lease/version fencing and compare-and-set transitions.
An uncertain write after crash is reconciled before retry, never blindly repeated.

A constrained Systems Acceptance Verifier (proposed WS-23) reads only admitted
build/source identity, criteria, diagnostics and receipts. It returns passed,
failed, blocked or untested per criterion. It cannot edit code, weaken tests,
change acceptance requirements, repair evidence or authorize release. Independent
VM results do not prove physical-Mac behavior. Verification must bind the exact
artifact; changed source/settings invalidate affected evidence.

WS-22 handoff carries source/build hashes, requirement/evidence mapping,
observations versus inferences, decisions, contradictions, unknowns, checkpoint,
remaining authority and next action. Test a fresh eligible model resuming from
that packet without recovering an entire private chat. A model swap must not
lose commitments or revive cancelled work.

Proposed WS-25 extends Scheduler/Librarian: distinguish Larry's explicit
commitments from tentative plans, assistant suggestions and third-party mail
requests; support date corrections, completion and cancellation with provenance.
Review suggestions before creating new commitments or writing calendar entries.
Proposed WS-26 consumes relevant build completion, deadline change or blocker
resolution events through existing outbox/watchers. Deduplicate out-of-order
updates, recover after downtime, expire stale events and respect quiet times.
Generic notices disclose no private payload; protected results carry details.
No autonomous outreach or automatic calendar writes are included.

## 5. Privacy, finance and the existing mail report

Cloud services remain suitable for permitted public research, weather and app
building. Finance and private email content, attachments, subjects/metadata and
derived summaries are **local by default**. Reading from the original mail
provider or obtaining public market prices is distinct from sending private
material to a cloud AI. No real financial/email records are accessed in this work.

Select local private mode **before recording**, unless every initial STT path
is local. Cloud STT receives raw audio before text redaction. A private answer
requires local TTS or text-only output (default for finance). Isolate recall,
background extraction, logs, notifications, tool outputs, prompt/response caches,
crash reports, backups and conversation history as well as storage. No silent
cloud fallback on overload, timeout, unsupported schema or model unavailability.

**Explicit reconciliation:** [platform roadmap T3.4/R7 and T4b](MORTIMER_PLATFORM_ROADMAP.md)
previously retain ElevenLabs and describe private spoken output as an accepted
residual. Larry's latest requirement supersedes that allowance for this proposed
private scope: private financial/email speech may not go to ElevenLabs by
default. Public voice can keep ElevenLabs. Before implementation, the existing
T3/T4 owner must reconcile those canonical sections with this decision; until
then use text-only private output and do not rely on the older residual to send
private data. The user-presence-unlocked encrypted finance tier and read-only
analysis remain prerequisites; no trading, transfers or account mutation.
The verified Air is a prototype target, not automatic satisfaction of the older
mini/G3 financial activation gate. Larry must explicitly reconcile that hardware
gate after local evidence; no ordinary-memory substitution for the encrypted tier.

Use deterministic Decimal or integer-cents calculations with typed currencies,
rounding/date rules, source rows and reproducible formulas. The LLM extracts or
explains; generated prose does not calculate authoritative balances/tax/returns.
Abstain on missing, stale, conflicting or unreconciled records. Local models
still need device protection, least privilege and prompt-injection defenses.

### 5.1 Mail enhancement boundary

First identify the actual deployed daily-report trigger, reader, source limits,
protected result and generic notification without fetching real mail in this
planning task. Preserve the WS-13 revised §R.1 P1–P3 design: bounded isolated
header reader, deterministic host-produced brief, no LLM mail content, fixed
generic spoken notification. Header-only source evidence cannot establish body
or attachment Q&A support. P4 optional model-written prose and P5 interactive
retrieval require an eligible private route and their own authorization.

Later read-only Q&A can locate an appointment message, summarize a selected
thread, explain a report item and propose commitments. Each answer cites message
identity/source, selection/window and completeness; “not found” cannot imply an
exhaustive mailbox search when limits/partial errors apply. Treat hostile mail as
data, never instructions to use network/tools, reveal other mail or create events.
Preserve the mail worker's process isolation and restricted tool surface; do not
add general shell/screen/web tools or route mail through cloud Librarian defaults.
Mail sending, marking/moving messages, calendar writes and automatic commitment
creation are separate features/authorizations, absent from this plan's read scope.

### 5.2 Optional cloud exception — default off, per request

This is a proposed mitigation path, **not approved sharing**. The local host
prepares a preview of the **exact selected excerpt**, destination provider,
model, endpoint, purpose and retention profile. Larry approves that specific
payload for one request; changed content, derived summary, destination, retry
policy or purpose needs a new decision. A refusal or missing policy fails closed.
Never automatically send full records, private audio, attachments or histories.

Before enabling such an exception, verify the exact account/feature's no-training
configuration, storage settings, retention/abuse-monitoring rules and eligibility.
Use ZDR only when supported **and actually enabled** for that endpoint/features;
no-training alone is not ZDR. [OpenAI data controls](https://developers.openai.com/api/docs/guides/your-data)
and [Anthropic API retention](https://platform.claude.com/docs/en/manage-claude/api-and-data-retention)
were checked 2026-10-18; refresh them at approval. ZDR does not remove remote
processing, account, legal or implementation risk. Local redaction/minimization,
restricted network destinations/tools, payload-bound approval and content-free
audits are still required. Test synthetic secret markers through logs, retries,
cache/history replay, tools and background jobs. No cloud exception is required
for useful local finance or mail analysis.

## 6. Rollout, rollback and decisions

Each dispatched increment needs focused offline unit/contract and integration
checks for its actual behavior, the sandbox protocol where voice changes, and
existing required repository/independent verification. Run no live API suite as
part of documentation validation. Record exact tested revisions/settings and
which evidence is simulated versus physical. Existing acceptance requirements
are never replaced by the proposed targets in the appendix.

Roll out later as: synthetic/offline → isolated approved sandbox → reviewed
exact-source candidate → separately authorized narrow pilot → existing release
verification → Larry's merge/deployment/live acceptance. Gate each optional
feature independently; do not activate unrelated memory/mail stages together.

Rollback must restore the last approved model/adapter/config and app artifact
with the existing deploy/rollback mechanism, stop new candidate admission, drain
or fence owned workers, preserve task/result IDs and privacy labels, and reconcile
pending outbox/cancelled actions before resuming. A failed local private route
stays unavailable; rollback never routes private work to cloud. Disable a pilot
without deleting user records, commitments or audit receipts. New schema changes
must document reversible migration or compatible forward recovery before claim.

| Decision still needed | Evidence required before deciding |
|---|---|
| Existing release/acceptance closure after #218/#219 integration | Owning rows' exact-build outcomes; cleanup race/fingerprint repair/review; no gate waiver here |
| Harness implementer, isolated environment, setup/microphone permission and paid-run scope | Non-destructive sandbox isolation receipt, fixture-only tools, explicit provider access and total/per-session spend cap |
| Playback/quality targets and candidate promotion rule | Calibrated unchanged baseline and instrumentation uncertainty; approve proposed thresholds before held-out runs |
| Optimized cascade versus optional Live/Realtime architecture | Paired reliability, useful-audio p50/p95, full cost and blinded preference; retain baseline if inconclusive |
| Local model/runtime revision and private pilot; Air versus mini/G3 | Pinned manifest, quality/resource/coexistence tests and production isolation; explicit canonical hardware-gate reconciliation |
| Private input/output, sink isolation and encrypted tier | No-egress synthetic proof, user-presence unlock/expiry and text-only/local voice decision |
| Any cloud excerpt exception | Exact content/destination/purpose preview and enabled endpoint-specific retention profile; default stays off |
| Mail P4/P5, commitments/events and Jev reconsideration | Verified report gap, private routing/lifecycle prerequisites; Jev only after voice decision and net-benefit replacement design |

## 7. Dated progress

2026-10-18: Saved this plan and both appendices as documentation in WS-27.
Current main/PRs, prior bench, routing/local-runtime refusal and mail/finance
constraints inspected; official source checks are linked. No runtime changes,
models installed, private records read, paid benchmarks, merge or deployment.

2026-11-24 (daily batch): #408 merged into `main` on 11-23 (`6ff8702`) added §3.4, the Bitcoin research track (read-only skill and chart-first card, a separately gated Daily Brief recommendation, later a native Mac workspace). Documentation only; implementation needs fresh scoped dispatches ([log](../roadmap-log/2026-11-23-ws-27-bitcoin-research-enhancement-design.md)).
