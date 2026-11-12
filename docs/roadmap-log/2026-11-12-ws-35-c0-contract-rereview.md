---
date: 2026-11-12
system: codex
rows: [WS-35]
prs: [332, 334]
---

# WS-35: revised C0/C0b contract re-review

**Verdict: APPROVE for Codex's contract review.** R1–R3 from #334 and the
origin-stamping note are addressed. No new blocking contract finding in Codex's
primary sections 1 and 4. This is not approval of implementation PRs, a Kimi
review, a deployment decision or UI acceptance. Larry's outstanding decisions
below are not silently resolved by this verdict.

- Reviewed #332 head `14fa78b3e90a758c699927cc5f857700d249ff0f`.
- Previous review: `1f8aca7ee086912d1c9ffddcedbd65af738ca38b`, recorded in #334.
- Main read: `4a0dd9635227cce51b01fcfcd584b3850ae81042`; frozen code:
  `5777e98cf1cdbaa65eb13079044693794c071927`.
- #332 targets `next`, `a1369e223e51cc499c8f942fae95133994a4facb`.
- System/session: Codex, `codex/ws35-c0-rereview-20261112`, Larry's
  2026-11-12 release-closure queue, item 1.
- Read origin/main AGENTS.md, ROADMAP protocol/WS-35/conflicts and closure
  plan section 4 first. This new review-record branch is based on current main
  and changes documentation only. It does not change the author's branch or
  rewrite #334's historical verdict. Build work still targets next.

## Rechecked disposition

1. **R1 resolved** (contract sections 1.2, 1.5 rule 11, 1.8): every composed
   message carries answer identity and top-level revision, including no-layout
   fallback. Clients reject older/replayed revisions, preserve card identity,
   pin and position, and use legacy fields for absent/invalid/unknown layouts.
   The forward/reverse fallback transitions and malformed revision cases have
   explicit fixture requirements.
2. **R2 resolved** (1.5 rules 4, 5, 5a and 7): direct-tool results complete
   immediately when no delegation is in flight; concurrent delegations are
   tracked per request; no-origin results are complete standalone answers;
   delayed results join retained answers or start new identities after eviction.
   Retention is bounded to eight answers and seven results per answer. Complete
   is explicitly a current in-flight state, not an irreversible finality signal;
   clients must not wait on it. Briefs remain uncomposed/protected.
3. **R3 resolved** (4.2–4.3): C5 owns deleting the transcript-to-result route,
   its response payload initializer and the old thread-off preference. A false-
   preference regression covers cards and second-screen transcript leakage.
   Audits now include the subscriber and executable frame cases; the approved
   Log history exception is preserved.
4. **Origin note addressed** (1.5 rule 10): `_prepare_app_message` remains the
   trusted stamping point. Eviction's closing message must use its answer's
   owning request, not the request causing eviction; an end-to-end emitter test
   is required. C3 should include rule 11's standalone overflow fallback in that
   test too: the invariant says standalone origin is absent, while the current
   emitter stamps its active foreground context unless deliberately overridden.
   This is implementation follow-through, not a new contract blocker.

Since `1f8aca7`, three commits (`ad4d907`, `322e9bd`, `14fa78b`) change only
this contract, +268/-60 lines. The revised text also specifies bounded approval
arguments and operation identity, local/silent decline, enqueue-before-settle,
explicit sensitive guards, stale-session responses and bounded replay. Those
approval rules still require Kimi's independent review and implementation tests.
The approved C0b palette/system-font decisions remain unchanged.

## Section 4.3 grep execution on the exact reviewed tree

All five commands were copied from section 4.3 and run without changing their
patterns or excluding additional files. Source trees `jarvis`, `macos` and `ios`
have no diff between reviewed #332 and main. Results are **not** an all-green
UI migration gate: section 4.3 itself says checks 1, 2 and 4 retain violations
until C1a/C5/C6 land. Only checks 3's line selection and 5 match their current
allowlists. The body inspection required after check 3 still finds the legacy
response route; C5 owns removing it.

Commands, verbatim:

```bash
# 1. Who reads the transcript. Allowed: ConversationThreadView.swift and LogTab.swift (§7 question 3: the Log tab stays).
grep -rn "conversation\.entries\|\.latestCaptions\|liveCaption(" macos/MortimerHost/Sources --include=*.swift \
  | grep -v "Stores/ConversationStore.swift"

# 2. The compact rail is gone. Allowed: nothing.
grep -rn "compactConversation\|compactPresentation" macos/MortimerHost/Sources --include=*.swift

# 3. Who subscribes to the client's transcript. Allowed: one line, the sink at AppMessageRouter.swift:46.
#    Then read that closure: its body may call conversation?.set(entries) and nothing else that takes the entries.
grep -rn '\$transcript' macos/MortimerHost/Sources --include=*.swift

# 4. The transcript-to-result route is gone (4.2, Codex R3). Allowed: nothing.
grep -rn "ResponseResultRouter\|responseText:\|presentResponse\|updateResponse\|routesSpokenAnswersToResults\|interface\.conversationThread" \
  macos/MortimerHost/Sources macos/JarvisKit/Sources --include=*.swift

# 5. Code that consumes the transcription frames. Sources only, quoted frame names only, comment lines removed,
#    so explanatory comments and test fixtures do not match. Allowed: the two `case` lines in JarvisClient.swift
#    (:588, :598 today) and the one in AppMessageRouter.swift (:464 today), which feeds the request tracker
#    timestamps and ids, not text for display.
grep -rn '"user-transcription"\|"bot-llm-text"' macos/MortimerHost/Sources macos/JarvisKit/Sources --include=*.swift \
  | grep -v '^[^:]*:[0-9]*:[[:space:]]*//'
```

### Check 1

8 lines: 2 allowed thread/Log readers and 6 legacy OrbField/AdaptiveStage matches. Not the final allowlist-only state; assigned migration remains.

```text
macos/MortimerHost/Sources/MortimerHost/Drawer/LogTab.swift:40:        let bubbles = conversation.entries.map(LogItem.bubble)
macos/MortimerHost/Sources/MortimerHost/Console/OrbFieldView.swift:390:        conversation.entries.last {
macos/MortimerHost/Sources/MortimerHost/Console/OrbFieldView.swift:396:        conversation.entries.last {
macos/MortimerHost/Sources/MortimerHost/Console/OrbFieldView.swift:423:                             ? ConversationStore.liveCaption(bot.text)
macos/MortimerHost/Sources/MortimerHost/Console/ConversationThreadView.swift:246:        let rows = ConversationThread.rows(conversation.entries)
macos/MortimerHost/Sources/MortimerHost/Console/AdaptiveStageView.swift:87:                                if conversation.entries.isEmpty {
macos/MortimerHost/Sources/MortimerHost/Console/AdaptiveStageView.swift:91:                                    ForEach(InterfaceLayoutVersion.resolve(layoutVersion) == 2 ? conversation.latestCaptions : conversation.entries) { entry in
macos/MortimerHost/Sources/MortimerHost/Console/AdaptiveStageView.swift:92:                                        Text(InterfaceLayoutVersion.resolve(layoutVersion) == 2 ? ConversationStore.liveCaption(entry.text) : entry.text)
```

### Check 2

14 lines: compactConversation/compactPresentation remain. Expected empty only after the assigned layout/orb work, not for this docs-only contract.

```text
macos/MortimerHost/Sources/MortimerHost/Console/OrbFieldView.swift:36:    var compactPresentation = false
macos/MortimerHost/Sources/MortimerHost/Console/OrbFieldView.swift:63:            if compactPresentation {
macos/MortimerHost/Sources/MortimerHost/Console/ConsoleActionBar.swift:27:    @AppStorage("mortimer.interface.compactConversation") private var compactConversation = true
macos/MortimerHost/Sources/MortimerHost/Console/ConsoleActionBar.swift:527:        let title = compactConversation ? "Expand voice" : "Keep voice compact"
macos/MortimerHost/Sources/MortimerHost/Console/ConsoleActionBar.swift:528:        return Button { compactConversation.toggle() } label: {
macos/MortimerHost/Sources/MortimerHost/Console/ConsoleActionBar.swift:529:            barLabel(title, icon: compactConversation ? "waveform" : "rectangle.compress.vertical", icons: icons)
macos/MortimerHost/Sources/MortimerHost/Console/AdaptiveStageView.swift:19:    @AppStorage("mortimer.interface.compactConversation") private var compactConversation = true
macos/MortimerHost/Sources/MortimerHost/Console/AdaptiveStageView.swift:56:    static func mode(showsConversation: Bool, compactConversation: Bool,
macos/MortimerHost/Sources/MortimerHost/Console/AdaptiveStageView.swift:58:        if showsConversation && !compactConversation { return .conversation }
macos/MortimerHost/Sources/MortimerHost/Console/AdaptiveStageView.swift:66:                                 compactConversation: compactConversation,
macos/MortimerHost/Sources/MortimerHost/Console/AdaptiveStageView.swift:115:                            OrbFieldView(voiceState: voiceState, compactPresentation: true, hidesLettering: true, presentation: voicePresentation())
macos/MortimerHost/Sources/MortimerHost/Console/AdaptiveStageView.swift:130:                            OrbFieldView(voiceState: voiceState, compactPresentation: true, hidesLettering: true, presentation: voicePresentation())
macos/MortimerHost/Sources/MortimerHost/Console/AdaptiveStageView.swift:160:        Button(compactConversation ? "Expand voice" : "Keep voice compact") {
macos/MortimerHost/Sources/MortimerHost/Console/AdaptiveStageView.swift:161:            compactConversation.toggle()
```

### Check 3

1 line: AppMessageRouter.swift:46, exactly the allowed subscriber. Its closure still calls responseRouter.receive at line 54; therefore the final closure-body restriction is not yet satisfied.

```text
macos/MortimerHost/Sources/MortimerHost/App/AppMessageRouter.swift:46:        transcriptSink = client.$transcript.sink { [weak self] entries in
```

### Check 4

13 lines: the old router, initializer, preference and forwarding helpers remain, including one documentation comment. All are in the C5 deletion scope. Not empty yet.

```text
macos/MortimerHost/Sources/MortimerHost/Stores/WorkspaceStore.swift:473:    func updateResponse(_ result: WorkspaceResult) {
macos/MortimerHost/Sources/MortimerHost/Display/DisplayWindowStore.swift:253:    func presentResponse(_ result: WorkspaceResult, isNew: Bool) {
macos/MortimerHost/Sources/MortimerHost/Console/ConversationThreadView.swift:12:/// mortimer.interface.conversationThread -bool false` restores the previous
macos/MortimerHost/Sources/MortimerHost/Console/ConversationThreadView.swift:15:    static let flagKey = "mortimer.interface.conversationThread"
macos/MortimerHost/Sources/MortimerHost/Console/ConversationThreadView.swift:23:    static func routesSpokenAnswersToResults(layoutVersion: Int, threadEnabled: Bool) -> Bool {
macos/MortimerHost/Sources/MortimerHost/App/ResponseResultRouter.swift:7:final class ResponseResultRouter {
macos/MortimerHost/Sources/MortimerHost/App/ResponseResultRouter.swift:42:            payload: DisplayPayload(responseText: body, timestamp: receivedAt.timeIntervalSince1970),
macos/MortimerHost/Sources/MortimerHost/App/ResponseResultRouter.swift:47:            workspace.updateResponse(result)
macos/MortimerHost/Sources/MortimerHost/App/ResponseResultRouter.swift:48:            display.presentResponse(result, isNew: false)
macos/MortimerHost/Sources/MortimerHost/App/ResponseResultRouter.swift:58:        display.presentResponse(result, isNew: true)
macos/MortimerHost/Sources/MortimerHost/App/AppMessageRouter.swift:20:    private let responseRouter = ResponseResultRouter()
macos/MortimerHost/Sources/MortimerHost/App/AppMessageRouter.swift:51:            if ConversationThread.routesSpokenAnswersToResults(
macos/JarvisKit/Sources/JarvisKit/AppMessage.swift:247:    public init(responseText: String, timestamp: Double) {
```

### Check 5

3 lines: exactly AppMessageRouter.swift:464 and JarvisClient.swift:588,598. Allowed executable frame cases only; passes.

```text
macos/MortimerHost/Sources/MortimerHost/App/AppMessageRouter.swift:464:                    case "user-transcription": currentRequests.transcription(raw)
macos/JarvisKit/Sources/JarvisKit/JarvisClient.swift:588:            case "user-transcription":
macos/JarvisKit/Sources/JarvisKit/JarvisClient.swift:598:            case "bot-llm-text":
```

## Decisions and remaining gates

- Contract 3.10/8 still asks Larry to confirm the zero-tracked-approval bare-yes
  exception. This report does not infer an answer.
- Whether the stored approve turn includes canonical arguments in the user's
  transcript (and therefore memory input) is explicitly undecided.
- A voice-confirmed operation with restated arguments may leave its no-ref
  approval open until expiry; a later tap can deliver another confirmation.
  The contract records this risk and needs live evaluation, not weaker matching
  silently introduced by a reviewer.
- Kimi's review, the C0 types and C3/C7-py implementation tests remain distinct.
  C4 must not start until #332 merges; C1a is also a C4 dependency in the plan.
- Next queue item is #342 B2 review, then #338's hosted Swift compiler repair.
  Larry retains every merge, the C10 baseline run and named F1 approval.

## Validation and limits

- `python3 scripts/check_roadmap.py` on reviewed head: 0 errors, 0 warnings.
- Same checker on the main-based review record: 0 errors, 0 warnings.
- `git diff --check`: clean.
- All five section 4.3 greps ran, with counts 8 / 14 / 1 / 13 / 3 as recorded.
- Static documentation and source review only. No Swift build, runtime suites,
  live build checks 6–10, defaults changes, deployment, real sandbox operations,
  model change, external review posting or merge. The Mac was unavailable;
  an isolated cloud checkout was sufficient for the requested source greps.
