# Mortimer native client — full macOS view port (T1.3)

**Status:** DRAFT for Larry's approval, 2026-08-27. Implements roadmap track **T1.3** (the full macOS SwiftUI view port that `MORTIMER_NATIVE_CLIENT_CORE_PLAN.md` (T1.1/T1.2) explicitly deferred).

**Author / origin (Larry's words, quoted from the roadmap's origin section):**
- *"The plan is to migrate away from the web part since it is holding us back from what we want to do related to multiscreen and transparent windows."*
- *"the usefulness of the web interface has been lost since the integration of the swift wrapper — we have to rebuild the app with any changes anyway. I propose that we move away from the web portion of the interface and use swift for the UI."*
- Larry 2026-08-18 (`macos/MortimerShell/Sources/MortimerShell/WindowVibrancy.swift:2-3`): *"the display window/panel is not like liquid glass, I would like it see through like liquid glass."*

This plan is the **T1.3** half of the native track that `CROSS_PLAN_RESOLUTION.md` §C F12 named: `MORTIMER_NATIVE_CLIENT_CORE_PLAN.md` (T1.1/T1.2) shipped `JarvisKit` (the RTVI client + `AppMessage` + `AdminAPI` with typed routes but `JSONValue` responses) and `MortimerHost` (a bare G1(b) harness). This plan builds the real product on top: the three native windows and the seven drawer tabs as SwiftUI over `JarvisKit`, and — per F12 — the concrete per-tab `AdminAPI` **response** structs that CORE deliberately deferred.

**Roadmap constraints this plan is bound by:**

| C | How this plan honours it |
|---|---|
| **C1** — backend contract does not change | No file under `jarvis/`, `mcp_servers/`, or `config/` is created, modified, or deleted (§4 manifest is entirely under `macos/`). The one backend gap — no RTVI transcript messages exist for a native Log tab — is carried as a **dependency and flagged as C1** (§3 P16, §10 R-A1), never worked around with a server change. |
| **C2** — localhost is the trust boundary until G2 | This plan adds no networking of its own; every request goes through `JarvisKit`'s `JarvisConfig`/`JarvisHTTP` (CORE §3 N13), whose loopback defaults and `validate()` refusal are unchanged. |
| **C3** — sensitive tier waits for G3 | No financial data, no second store, no new Keychain item. Views render what the sidecar returns; they never persist it. The Output tab's clipboard `content` field is display-only and never written to disk (§3 P9). |
| **C4** — every mutation stays draft → confirm | The Repo and Edit tabs surface the sidecar's draft routes and confirm routes as **two separate user actions** with a visible pending state (§3 P6); there is no one-tap "commit and push". |
| **C5** — Supervisor owns interface chrome | The three UI commands `JarvisKit` owns (`mic_mute`/`wake_on`/`wake_off`) are applied by their state owners; every other `ui` app-message (tab switch, drawer open, display surface) is applied by the **view** that owns that state through the *same* setter its buttons call (§3 P4), exactly as the web `uiCommands.ts` store does. No view originates a `ui` message. |
| **C6** — untrusted content never shares an agent with an outbound channel | No agent, no MCP server, no `config/agents.yaml` change. |
| **C7** — routing eval ≥ 90 % | No Supervisor, prompt, or agent change. |
| **C8** — self-edit allow/deny changes are human commits | `macos/**` is on the deny list (`config/self_edit_allowlist.json`); this plan does not change it. Every file here is a normal working-tree write committed by Larry (§0.2). |
| **C9** — secrets in the vault | This plan stores no secret. The bearer token lives in `KeychainStore` (CORE §3 N12); this plan reads it only through `JarvisConfig`. |
| **C10** — degradation-proof | Every tab has a specified empty state, loading state, and error state (§3 P7, §5). A tab whose backend returns `{"ok": false}` renders the error string, never a blank pane or a crash. The Log tab, whose stream is silent today, has a specified "waiting for backend support" empty state (§3 P16). |

**Contracts this plan INTRODUCES (consumed by later plans):**
- **The per-tab `AdminAPI` response structs** (P2–P5 below): `GitStatus`, `SelfEditModels`/`SelfEditStatus`, `MemoryOverview`/`MemoryReviews`/`KnowledgeOverview`, `RunsList`/`RunDetail`, plus their leaf types. Named and typed member-by-member here, added **inside** `macos/JarvisKit/Sources/JarvisKit/AdminAPI.swift` (the file CORE created). Consumed by the T1.5 iOS-app plan, which renders the same tabs on a phone. This discharges `CROSS_PLAN_RESOLUTION.md` §C F12: "the sole consumer that adds concrete per-tab `AdminAPI` response structs."

**Contracts this plan CONSUMES (by doc + section):**
- **K8 — JarvisKit public surface.** `MORTIMER_NATIVE_CLIENT_CORE_PLAN.md` §3 N5–N16, §5. This plan consumes `JarvisClient` (state, `botIsSpeaking`, `transcript`, `messageStream()`/`subscribe`, `send`), `AppMessage` (all ten cases, N7), `ClientMessage` (N8), `JarvisConfig`/`JarvisFlags` (N16), `AdminAPI` (the seventeen typed routes, N14), and `ScreenPlacement` (ported to `MortimerHost` by CORE §3 N15). It does not restate them.
- **K1 — client bearer tokens** and **K5 — host/URL configuration.** Consumed transitively through `JarvisConfig`; not restated (see CORE header).

**Corrections to the roadmap:** none beyond those `MORTIMER_NATIVE_CLIENT_CORE_PLAN.md` already recorded (its corrections 1–6). Correction 6 (no RTVI transcript messages are emitted, so a native Log tab is silent against today's bot) is the direct precondition for this plan's §3 P16 and §10 R-A1; it is consumed, not re-derived.

---

## §0 Binding constraints for the implementing model

0.1 **You may not edit anything outside `macos/`.** The complete allowed write set is `macos/JarvisKit/**` (adding the response structs + additive `AdminAPI` methods) and `macos/MortimerHost/**` (the views). If a step seems to require a change under `jarvis/`, `mcp_servers/`, `config/`, or `web/`, **stop and report** — that is C1 being violated.

0.2 **You may not run `git`.** The sandbox leaves an `index.lock`. Larry commits. Branch name: `native-client-app`.

0.3 **You cannot build Swift in this sandbox** (no Xcode, no toolchain, no Mac). Every Swift file is written without compiling it. Therefore: (a) write nothing that depends on an API not quoted in this plan, in CORE, or in an existing file under `macos/`; (b) every JarvisKit symbol used is declared in CORE §3/§5 (cited, never guessed); (c) §8 is the compile-and-run gate, and Larry runs it.

0.4 **This plan depends on T1.0 sign-off** (§1.0). Before writing any view, confirm the design review is complete. If not, stop and report.

0.5 **Every number lives in exactly one place**, listed in §6 (`AppTuning`). If you type a literal number a second time, import the constant.

0.6 **The visual treatment is a layer, never baked into a view** (§3 P10). No view hardcodes a colour, blur radius, or material. Every glass surface calls `.mortimerGlass(_:)`; every colour comes from `AppTheme`. This is what lets T1.0's chosen look drop in without touching view bodies.

0.7 **When this plan gives a literal Codable struct, use it verbatim** — the `CodingKeys`, the optionality, and the `Int`-vs-`Bool` choices were each read from the sidecar's real response and are load-bearing (a wrong optionality is a silent decode failure, an empty tab). Do not "tidy" them.

0.8 **A tab never crashes or blanks on a bad response.** Every HTTP tab renders one of exactly four states — loading, loaded, empty, error (§3 P7) — and a `{"ok": false, "error": ...}` body maps to the error state showing the string. C10.

## §1 What exists today (verified, `path:line`) and the gap

### 1.0 Precondition — Larry's Liquid Glass design review (T1.0) has happened
This plan **depends on T1.0** (roadmap R3, Larry's Liquid Glass design review) being complete before implementation starts. T1.0 answers, with Larry's sign-off, the two questions the CORE spike (`MORTIMER_NATIVE_CLIENT_CORE_PLAN.md` §5 steps 11-13, `macos/GlassSpike/`) raised: does `.glassEffect()` over a transparent `NSWindow` read as glass, and is text on it legible over a busy desktop. This plan is written so the *view structure* is fixed and the *visual treatment is a layer on top* (§3 P10): every surface is a plain SwiftUI view whose glass is applied by one modifier (`.mortimerGlass(_:)`), so T1.0's chosen materials drop in without re-laying-out a single view. If T1.0 has **not** signed off when implementation begins, **stop and report** — building the glass layer against an unreviewed direction is the rework Larry's options-first preference exists to prevent.

### 1.1 What CORE (T1.1/T1.2) delivered that this plan builds on
Verified against `MORTIMER_NATIVE_CLIENT_CORE_PLAN.md`:
- `macos/JarvisKit` — the Swift package (tools 6.0, macOS 26 / iOS 26). `JarvisClient` (`@MainActor ObservableObject`): `state: ConnectionState` (`offline|connecting|connected|failed(String)`, N5), `botIsSpeaking: Bool` (N5), `transcript: [ConversationEntry]` (N7, empty against today's bot), `messageStream() -> AsyncStream<AppMessage>` + `subscribe(_:) -> JarvisSubscription` (N6, both receive every message), `send(_ msg: ClientMessage)` (N8), `connect()`/`disconnect()`. `AppMessage` — ten cases (N7). `AdminAPI` — seventeen typed **read** routes, responses as `JSONValue` (N14), the per-tab response structs **deferred to this plan** (F12). `JarvisConfig`/`JarvisFlags` (N16), `KeychainStore` (N12).
- `macos/MortimerHost` — the G1(b) harness: one window, a connect button, a state label, mic/wake toggles, a debug `List`. Deliberately no views, no glass, no tabs (CORE §3 N2). `ScreenPlacement.swift` was ported into it with `HostWindowKind` (`.console`/`.display`/`.drawer`) and `findHostWindow` (CORE §3 N15). **This plan turns `MortimerHost` into the real three-window app** (§3 P1).

### 1.2 The web UI this plan ports — every surface enumerated
Read from `web/src/`. The three window surfaces and their contents:

**Console window** (`App.tsx:530-669`): full-viewport `VoiceWave` background (`VoiceWave.tsx`, a `<canvas>` whose amplitude reads the mic level via `getUserMedia`+`AnalyserNode`, `VoiceWave.tsx:115-125`, falling back to a simulated envelope keyed on `VoiceState`); a topbar (`brand`, `ConnectButton`, `VoicePicker`, `CapabilityChip`, the single drawer toggle, the display toggle); the stage (`OrbField.tsx` — agent satellites + beams + wake ripple + readout over the wave, `OrbField.tsx:220-...`; the old central orb was removed — the wave owns voice display, `voiceState.ts:6`); a speaker-gate notice chip; a bottombar (`MicControls`, `SoundToggle`, hints); two headless RTVI listeners (`ConversationFeeder` → `conversationFeed.ts`; `AgentRunFeeder.tsx` → `agentRuns.ts`); the floating `DisplayPanel` overlay. `voiceState` is derived: `connected ? (speaking ? "speaking" : "listening") : (connecting ? "connecting" : "offline")`, `speaking` from `BotStartedSpeaking`/`BotStoppedSpeaking` (`App.tsx:194-206`).

**Display window** (`displayMain.tsx` → `DisplayWindowApp.tsx`, a separate Vite entry): renders `surface: "window"` informational payloads (weather, radar, research) through `DisplayContent.tsx`; a stack of independent `SingleDisplayPanel`s from `displayWindow.ts`'s registry, each draggable/resizable (`DisplayPanel.tsx:120-...`). Parked on a second monitor.

**Drawer window** (`drawerMain.tsx` → `DrawerWindowApp.tsx`, a third Vite entry): the `SideDrawer` popped out, hosting the same seven tab bodies.

**The seven drawer tabs** (`SideDrawer.tsx:33-64`, tab order and labels are load-bearing — voice `ui_control` aliases resolve to these keys): `repo` "Repo" (`GitPanel.tsx`), `edit` "Edit" (`EditModePanel.tsx`), `memory` "Memory" (`MemoryPanel.tsx`), `runs` "Runs" (`RunsPanel.tsx`), `agents` "Agents" (`AgentsTab.tsx`), `output` "Output" (`OutputTab.tsx`), `transcript` "Log" (`Transcript.tsx`).

**Which tabs are HTTP-backed vs RTVI-fed** — the split the brief names:
- **HTTP-backed** (poll the sidecar over `AdminAPI`): Repo (`/api/git/status` + the draft→confirm write routes, `GitPanel.tsx:30,55-75`), Edit (`/api/selfedit/models`,`/status`, + `run`/`validate`/`submit`/`revert`, `EditModePanel.tsx:210-345`), Memory (`/api/memory`,`/memory/reviews`,`/knowledge`, + `DELETE /memory/fact/{key}`, `resolve`), Runs (`/api/runs`,`/api/runs/{id}`).
- **RTVI-fed** (driven by the `AppMessage` stream, no HTTP): Agents (`agentRuns.ts`'s store, fed by `agent`/`agent_tool`/`agent_activity` messages, `agentRuns.ts:276-392`), Output (`displayResults.ts`, fed by `display` messages with `surface != "window"`), Log (`conversationFeed.ts` + `agentRuns.ts`, `Transcript.tsx:29-62`).

### 1.3 The existing native shell (untouched by this plan)
`macos/MortimerShell/` — the WKWebView shell, 10 Swift files (CORE correction 3), including `ScreenPlacement.swift` (DP8 semantics, CORE §1.4) and the UNVERIFIED `WindowVibrancy.swift` recipe. **Not deleted here** — deletion is T1.4 (`MORTIMER_WEB_RETIREMENT_PLAN.md`), gated on G1(e). `macos/**` is on the self-edit deny list.

### 1.4 The gap this plan closes
| Wanted | Today | This plan |
|---|---|---|
| Three native windows in SwiftUI over JarvisKit | `MortimerHost` is a one-window debug harness | §3 P1, §5 steps 1-4 |
| The seven drawer tabs, native | Only `web/` renders them | §3 P2-P5 (HTTP), P8 (RTVI); §5 steps 6-12 |
| Concrete per-tab `AdminAPI` response structs | `JSONValue` only (CORE deferred them, F12) | §3 P2-P5 — the F12 deliverable |
| Multi-display placement, native | `ScreenPlacement` ran only under the WKWebView shell | §3 P11 — consumed from `MortimerHost` (CORE §3 N15) |
| Liquid Glass on real content | An UNVERIFIED `NSVisualEffectView` recipe | §3 P10 — one `.mortimerGlass()` layer, materials from T1.0 |
| Voice controls / transcript / orb, native | `MicControls`/`Transcript`/`OrbField`+`VoiceWave` are web-only | §3 P8/P12/P13, §5 steps 5, 12-13 |

## §2 Non-goals

- **Deleting `web/` or `macos/MortimerShell/`** — that is T1.4 (`MORTIMER_WEB_RETIREMENT_PLAN.md`, `CROSS_PLAN_RESOLUTION.md` §C F12). Both trees survive this plan untouched. The G1(e) daily-driver gate (§8) runs *before* T1.4.
- **Any backend change.** C1. The Log tab's silent stream (§3 P16) is a stated dependency on a future backend plan (`RTVIObserver`, CORE R-N6), **not** worked around here. If a step seems to need a `jarvis/` edit, stop and report.
- **The T4b sensitive-tier Keychain key.** `CROSS_PLAN_RESOLUTION.md` §C F13: `KeychainStore` holds the K1 bearer token only. This plan adds no Keychain item and no `SecAccessControl` user-presence gate; the T4b tier key is a different item introduced by the (unwritten) T4b plan.
- **The Edit tab's council & plan-authoring sub-surfaces.** The web `EditModePanel.tsx` (35 KB) also drives council convene/rounds (`/api/council/*`), plan authoring (`/api/plan/*`), and `verify-appearance`. Porting the **self-edit run lifecycle** (models, status/proposals, run/validate/submit/revert) is in scope (§3 P3); the council and plan-authoring panels are a large secondary surface that grew organically in the web and are **deferred to a follow-up native plan**, matching the repo's own "no v1 panel until there's real use to grow from" discipline (CLAUDE.md, app-build engine). Voice still reaches council/plan via the bot; only the *native panel* is deferred.
- **iOS (T1.5).** `JarvisKit` already targets iOS 26; this plan writes only macOS views (`MortimerHost`). The T1.5 plan reuses this plan's `AdminAPI` response structs (§ header, INTRODUCES).
- **T2 auth, T3 local models, T5 mail/calendar, T6 Xcode packaging.** Not this plan.
- **A new mic-level audio tap.** The native `VoiceWave` drives its amplitude from `JarvisClient.botIsSpeaking` + a simulated envelope (the web's own fallback path, `VoiceWave.tsx:125`), so this plan adds **no** input-audio-level publisher to JarvisKit (§3 P13). A real input-level meter is a later enhancement, noted as a tuning knob, not built here.

## §3 Decisions — P-lettered, each with a *why*

### P1 — `MortimerHost` becomes the three-window SwiftUI app; the debug harness view is retired.
The `MortimerHost` target CORE created (its `WindowGroup` + debug `VStack`, CORE §3 N2) is rebuilt as three `Window`/`WindowGroup` scenes — `ConsoleScene`, `DisplayScene`, `DrawerScene` — each stamped with an `NSWindow.identifier` (`"console"`/`"display"`/`"drawer"`) so `MortimerHost`'s ported `ScreenPlacement`/`findHostWindow(kind:)` (CORE §3 N15) can find them by `HostWindowKind`. One `JarvisClient` is created at app scope and injected into every scene as an `@EnvironmentObject`, so state (connection, `botIsSpeaking`, `transcript`, the run store) survives any window opening or closing. **Why:** CORE's harness proved the package; the roadmap sequences T1.3 as the view port on top. Three `Window` scenes (not three `NSWindow`s created by hand) is the SwiftUI-native way and is what lets the ported `ScreenPlacement` keep working — it matches on the identifier SwiftUI sets from the scene. The debug `List` moves to a Debug-menu window so the G1(b) affordance is not lost.

### P2 — Repo tab: `GitStatus` response struct + draft→confirm write methods (added to `AdminAPI`).
The concrete decode of `/api/git/status` (which returns `mcp_git/logic.py:129 git_status()` **verbatim**, no `{"ok":...}` wrapper):
```swift
public struct GitStatus: Codable, Sendable {
    public let branch: String
    public let clean: Bool
    public let changedFiles: [String]
    public let ahead: Int
    public let behind: Int
    enum CodingKeys: String, CodingKey {
        case branch, clean, ahead, behind
        case changedFiles = "changed_files"
    }
}
```
The web GitPanel also drafts and confirms commits/pushes (`GitPanel.tsx:55-75`) — `/api/git/prepare-commit`, `/api/git/commit`, `/api/git/prepare-push`, `/api/git/push`. These are **not** among CORE's seventeen read routes, so this plan **adds four methods to `AdminAPI`** (additive to K8, declared in the header), with the request bodies typed from `server.py`'s Pydantic models (`MessageIn{message}`, `ActionIn{action_id: int}`) and the draft response typed:
```swift
public struct GitDraft: Codable, Sendable {   // prepare-commit / prepare-push
    public let ok: Bool
    public let actionId: Int?
    public let summary: String?
    public let error: String?
    enum CodingKeys: String, CodingKey { case ok, summary, error; case actionId = "action_id" }
}
public struct GitActionResult: Codable, Sendable { public let ok: Bool; public let error: String? }  // commit / push
```
Methods: `gitStatusTyped() async throws -> GitStatus`, `prepareCommit(message: String) async throws -> GitDraft`, `commit(actionId: Int) async throws -> GitActionResult`, `preparePush() async throws -> GitDraft`, `push(actionId: Int) async throws -> GitActionResult`. **Why draft→confirm is two methods, not one (C4):** the mutation must stay a two-step user action — draft shows the summary, a second explicit tap confirms — exactly as `GitPanel` renders "Confirm commit"/"Confirm push". `AdminAPI` exposes them separately; the view holds the returned `actionId` between the two taps and shows the pending state (§5 step 6).

### P3 — Edit tab: `SelfEditModels` + `SelfEditStatus` structs + lifecycle write methods.
`/api/selfedit/models` → `{"ok": true, "models": available_models()}` (`upgrade_agent.py:239`):
```swift
public struct SelfEditModel: Codable, Sendable {
    public let name: String
    public let label: String
    public let provider: String
    public let model: String
    public let keyEnv: String
    public let keyPresent: Bool
    public let isDefault: Bool
    public let tier: String?          // economy|mid|frontier|null
    enum CodingKeys: String, CodingKey {
        case name, label, provider, model, tier
        case keyEnv = "key_env", keyPresent = "key_present", isDefault = "default"
    }
}
public struct SelfEditModels: Codable, Sendable { public let ok: Bool; public let models: [SelfEditModel] }
```
`/api/selfedit/status` has **two** response shapes: the busy shape `{"ok": false, "error": ...}` (`server.py:760`), and `SelfEditService.status()` (`service.py:565`, which has **no** `ok` key). One struct decodes both — every field except is optional; the view branches on `error != nil`:
```swift
public struct SelfEditProposal: Codable, Sendable {
    public let path: String; public let rationale: String; public let diff: String
}
public struct SelfEditStatus: Codable, Sendable {
    public let ok: Bool?              // present (false) only on the busy shape; nil on a real status
    public let error: String?
    public let active: Bool?
    public let branch: String?
    public let rollbackTag: String?
    public let goal: String?
    public let proposals: [SelfEditProposal]?
    public let validatedOk: Bool?
    enum CodingKeys: String, CodingKey {
        case ok, error, active, branch, goal, proposals
        case rollbackTag = "rollback_tag", validatedOk = "validated_ok"
    }
}
```
Write methods added to `AdminAPI` (all bodyless POSTs returning `JSONValue` — their result shapes are `SelfEditService`-internal and vary, so `JSONValue` per N14's response rule; the view reads `ok`/`error`): `selfeditValidate()`, `selfeditSubmit()`, `selfeditRevert()`. `selfeditRun(...)` already exists in CORE (typed body from `GoalIn`). **Why the run lifecycle only (council/plan deferred, §2):** the self-edit loop is the Edit tab's core and is a bounded surface; the council/plan panels are large and grew from real use, so they wait for real native use (matching the repo's own scoping discipline).

### P4 — Memory tab: `MemoryOverview` + `MemoryReviews` + `KnowledgeOverview` structs + `deleteFact`/`resolveReview`.
`/api/memory` (`server.py:1214`) → `list_facts`/`get_summary_text`/`list_observation_groups`/`memory_usage` (`memory.py:660,679,694,730`):
```swift
public struct MemoryFact: Codable, Sendable {
    public let key: String
    public let content: String
    public let sourceSessionId: String?      // nullable in SQL
    public let updatedAt: String
    public let tier: String
    public let audience: String
    enum CodingKeys: String, CodingKey {
        case key, content, tier, audience
        case sourceSessionId = "source_session_id", updatedAt = "updated_at"
    }
}
public struct MemoryObservation: Codable, Sendable {
    public let key: String
    public let sessions: Int
    public let promoteAfter: Int
    public let latestContent: String
    public let promoted: Bool
    enum CodingKeys: String, CodingKey {
        case key, sessions, promoted
        case promoteAfter = "promote_after", latestContent = "latest_content"
    }
}
public struct MemoryUsage: Codable, Sendable {
    public let factCount: Int
    public let tiers: [String: Int]
    public let caps: [String: Int]
    public let maxContextChars: Int
    public let overCapacity: Bool
    enum CodingKeys: String, CodingKey {
        case tiers, caps
        case factCount = "fact_count", maxContextChars = "max_context_chars", overCapacity = "over_capacity"
    }
}
public struct MemoryOverview: Codable, Sendable {
    public let ok: Bool
    public let facts: [MemoryFact]
    public let summary: String
    public let observations: [MemoryObservation]
    public let usage: MemoryUsage
}
```
`/api/memory/reviews` (`server.py:1461`) → `{"ok": true, "reviews": list_open_reviews()}` (`memory_sweep.py:722`) or `{"ok": false, "error": ...}`:
```swift
public struct MemoryReview: Codable, Sendable {
    public let id: Int
    public let kind: String
    public let keysJson: String
    public let detail: String
    public let status: String
    public let createdAt: String
    public let keys: [String]
    enum CodingKeys: String, CodingKey {
        case id, kind, detail, status, keys
        case keysJson = "keys_json", createdAt = "created_at"
    }
}
public struct MemoryReviews: Codable, Sendable {
    public let ok: Bool; public let reviews: [MemoryReview]?; public let error: String?
}
```
`/api/knowledge` (`server.py:1226`) → the four-layer nested read (`server.py:1240-1324`):
```swift
public struct KnowledgeMemory: Codable, Sendable {
    public let live: Int; public let archived: Int; public let tiers: [String: Int]
    public let reachingPrompt: Int; public let notReachingPrompt: Int; public let contextChars: Int
    enum CodingKeys: String, CodingKey {
        case live, archived, tiers
        case reachingPrompt = "reaching_prompt", notReachingPrompt = "not_reaching_prompt", contextChars = "context_chars"
    }
}
public struct KnowledgeSkillEntry: Codable, Sendable {
    public let name: String; public let hasScripts: Bool
    enum CodingKeys: String, CodingKey { case name; case hasScripts = "has_scripts" }
}
public struct KnowledgeSkills: Codable, Sendable {
    public let onDisk: Int; public let invalid: Int; public let registered: Int; public let enabled: [KnowledgeSkillEntry]
    enum CodingKeys: String, CodingKey { case invalid, registered, enabled; case onDisk = "on_disk" }
}
public struct KnowledgeWorkflow: Codable, Sendable {
    public let name: String; public let source: String; public let hasDoneWhen: Bool
    enum CodingKeys: String, CodingKey { case name, source; case hasDoneWhen = "has_done_when" }
}
public struct KnowledgeOverview: Codable, Sendable {
    public let ok: Bool
    public let memory: KnowledgeMemory?
    public let procedures: [String: Int]?
    public let skills: KnowledgeSkills?
    public let workflows: [KnowledgeWorkflow]?
    public let error: String?
}
```
Write methods: `deleteFact(key:)` and `resolveReview(id:action:rewriteContent:)` already exist in CORE (N14). **Why `notReachingPrompt` is surfaced prominently (§5 step 8):** it is the one number the `/api/knowledge` endpoint exists to make visible (`server.py:1226` docstring — silent truncation must not be archaeology); the native Memory tab renders it as the loud element, matching the web's amber `.knowledge-warn` line.

### P5 — Runs tab: `RunsList` + `RunDetail` structs.
`/api/runs` (`server.py:1501`) → `{"ok": true, "runs": list_runs()}`; each run is an `agent_runs` row (`db.py:132`) with the D9 display status applied (`store.py:396`). **`latencyMs` is `Int?`** (nullable column) and **`toolCount` is non-optional** (`NOT NULL DEFAULT 0`):
```swift
public struct RunSummary: Codable, Sendable {
    public let runId: String
    public let sessionId: String?
    public let agent: String
    public let displayName: String
    public let task: String
    public let status: String          // running|ok|failed|timeout|orphaned
    public let startedAt: String
    public let endedAt: String?
    public let latencyMs: Int?
    public let toolCount: Int
    public let error: String?
    public let replyPreview: String?
    public let payloadPath: String?
    enum CodingKeys: String, CodingKey {
        case agent, task, status, error
        case runId = "run_id", sessionId = "session_id", displayName = "display_name"
        case startedAt = "started_at", endedAt = "ended_at", latencyMs = "latency_ms"
        case toolCount = "tool_count", replyPreview = "reply_preview", payloadPath = "payload_path"
    }
}
public struct RunsList: Codable, Sendable { public let ok: Bool; public let runs: [RunSummary] }
```
`/api/runs/{run_id}` (`server.py:1518`) → `{"ok": true, "run": ..., "events": [...], "payload": [...]}` or `{"ok": false, "error": "not found"}`. `agent_events.ok` is **`Int?` (1|0|NULL), not `Bool`** (`db.py:151` `ok INTEGER`); `payload` is arbitrary parsed JSONL, so `[JSONValue]` (CORE's `JSONValue`):
```swift
public struct RunEvent: Codable, Sendable {
    public let id: Int
    public let runId: String
    public let seq: Int
    public let type: String            // tool_call|tool_result|mcp_call
    public let tool: String?
    public let server: String?
    public let ok: Int?                 // 1|0|NULL — NOT a Bool
    public let latencyMs: Int?
    public let argsPreview: String?
    public let resultPreview: String?
    public let createdAt: String
    enum CodingKeys: String, CodingKey {
        case id, seq, type, tool, server, ok
        case runId = "run_id", latencyMs = "latency_ms"
        case argsPreview = "args_preview", resultPreview = "result_preview", createdAt = "created_at"
    }
}
public struct RunDetail: Codable, Sendable {
    public let ok: Bool
    public let run: RunSummary?
    public let events: [RunEvent]?
    public let payload: [JSONValue]?
    public let error: String?
}
```
**Why these are typed here and nowhere else (F12):** these are the concrete structs CORE deferred; T1.5 (iOS) and any later native surface read them from `AdminAPI` rather than re-deriving. Every non-optional scalar decodes with `decodeIfPresent` + a default (CORE §5 step 4, F8), so a field an older sidecar omits degrades to a default rather than a decode failure.

### P6 — HTTP tabs are `@Observable` view-models that poll; mutations are draft→confirm two-step.
Each HTTP tab (Repo/Edit/Memory/Runs) is a `@MainActor @Observable` view-model owning `state: TabState<T>` (P7), a `Task` that calls its `AdminAPI` read on appear and every `AppTuning.httpPollSeconds`, and cancels the task on disappear. Mutations (commit/push, run/validate/submit/revert, deleteFact, resolveReview) are explicit user actions that call the write method, then immediately re-poll. Draft→confirm (Repo commit/push; §5 step 6) holds the `GitDraft.actionId` in the view-model between the two taps and renders a distinct pending row until the confirm call returns. **Why a view-model, not a raw `.task` in the view:** the drawer tab views mount/unmount on every tab switch (the web forced `agentRuns.ts` to be a module store for exactly this reason, `agentRuns.ts:9-11`); a view-model owned by the drawer scene (not the tab view) keeps a poll from restarting on every switch and keeps a half-finished draft alive across a switch.

### P7 — Every HTTP tab renders exactly one of four states.
`enum TabState<T> { case loading; case loaded(T); case empty; case error(String) }`. Mapping rule (deterministic, C10): a thrown `JarvisError` → `.error(message)`; a decoded body with `ok == false` → `.error(body.error ?? "request failed")`; a decoded body whose list payload is empty → `.empty` with the tab's specified empty copy; otherwise `.loaded`. `JarvisError.unauthorized` (a 401) renders `.error("Token required — set it in the Debug menu")` and does **not** retry (CORE §3 N13 discipline). **Copy (item 5 — named and specified):** Repo empty "Working tree clean." · Edit empty "No self-edit session. Say \"start a self-edit\" or pick a model and a goal." · Memory empty "No facts stored yet." · Runs empty "No agent runs yet." · Loading state is a single centered `ProgressView` with the tab name. **Why enumerate the states:** an unspecified empty/error state is self-audit item 5; the web tabs each have one (`GitPanel.tsx:22 unreachable`, `AgentsTab.tsx:115`, `OutputTab.tsx:56`), and the native tabs must not regress to a blank pane.

### P8 — RTVI-fed tabs read from three `@MainActor @Observable` stores fed by ONE `messageStream()` consumer.
Ported from `agentRuns.ts`/`displayResults.ts`/`conversationFeed.ts`. Three stores at app scope: `AgentRunStore`, `DisplayResultStore`, `ConversationStore`. **Exactly one** `Task` (the app-scope `AppMessageRouter`, §5 step 5) consumes `client.messageStream()` and dispatches each `AppMessage` to the store(s) that own it — the native analogue of the web's single-listener rule (`agentRuns.ts:16-21`, plan D10). The tab views (`AgentsView`, `OutputView`, `LogView`) only *read* their store; they register no stream consumer. Store shapes mirror the TS exactly (self-audit item 1 — multi-consumer contract typed member-by-member):
- `AgentRunStore.runs: [AgentRun]` where `AgentRun` mirrors `RunState` (`agentRuns.ts:81-114`): `id, name, displayName, runId, task, tools:[String], activity:[ActivityLine], stage:Int, startedAt:Date, doneAt:Date?, ok, detail, model, modelFallback, modelUnusable, modelUnusableDetail, plannerModel`; `ActivityLine = (tool, ok, latencyMs, ts)`. The reducer is `applyServerMessage`'s logic verbatim (`agentRuns.ts:276-392`): `agentWorking` inserts/replaces (append for self-edit runs, cap `AppTuning.maxAgentRuns`), `agentActivity` appends a ticker line matched by `runId` else live run (cap `AppTuning.maxActivity`) and sticks `plannerModel`, `agentTool` appends a tool + advances `stage` via `toolStage`, `agentDone` sets `doneAt`/`ok`/`detail` (non-self-edit success fades after `AppTuning.doneFadeSeconds`).
- `DisplayResultStore.results: [DisplayResult]` — newest-first, from `display` messages whose `surface != "window"` (the drawer-routed work products; `displayResults.ts`), bounded `AppTuning.maxDisplayResults`; a payload with `surface == "window"` goes to the display window instead (P14).
- `ConversationStore.entries: [ConversationEntry]` — from `JarvisClient.transcript` (which CORE already maintains from RTVI transcription decoders, N7). **Empty against today's bot (P16).**

**Why derive `AgentRun` from the message stream, not from `/api/runs`:** the Agents tab is live sub-agent progress (working/tool/done ticker), which arrives only as `AppMessage`s during a session; `/api/runs` is the persisted history the *Runs* tab reads. They are two different surfaces with two different sources, and conflating them is self-audit item 4.

### P9 — Clipboard `content` and any transcript text are display-only; never persisted.
The `display` payload's `content` field (clipboard text from `read_clipboard`, `displayResults.ts:42-45`) and `ConversationEntry.text` are rendered and held in memory only. No store writes them to disk, `UserDefaults`, or the Keychain. **Why (C3):** the handoff loop deliberately keeps clipboard text out of any durable store (CLAUDE.md handoff loop); the native port must not reintroduce a persistence path a password could land in. This is a construction property — the stores have no disk backing at all.

### P10 — The visual treatment is one layer on top of a fixed view structure.
Every surface is a plain SwiftUI view. Glass is applied by exactly one modifier, `.mortimerGlass(_ role: GlassRole)` (`GlassRole ∈ {panel, drawer, display, chip, card}`), and every colour comes from `AppTheme` tokens (ported from `App.css`'s `--glass-*`/`--bg`, CLAUDE.md "Vibrancy glass"). `.mortimerGlass` has two implementations selected by `JarvisFlags.glassEnabled` (CORE §3 N16, default true): glass-on uses the material/`.glassEffect()` **that T1.0 signs off** (§1.0); glass-off is an opaque `AppTheme.panelOpaque` fill (the §9 rollback). **Why a modifier, not a baked style:** T1.0 has not finalized the exact material, and Larry's history here is three rounds of glass CSS (CLAUDE.md); putting the treatment behind one modifier means the review's outcome changes one file (`Glass.swift`), not thirty view bodies. This is self-audit item 3 (how a value is applied): the glass is applied as a background material on the container, never as per-view opacity — the exact mistake `WindowVibrancy.swift:153-164` documents (a subview draws over its parent, dimming everything).

### P11 — Multi-display placement consumes `MortimerHost`'s ported `ScreenPlacement` (DP8 semantics), unchanged.
`MortimerHost` already owns `ScreenPlacement.swift` with `HostWindowKind` and `findHostWindow` (CORE §3 N15). This plan wires the three scenes to it and adds **no new placement logic**. DP8 semantics, verbatim from `MortimerShell` (CORE §1.4): observe `NSApplication.didChangeScreenParametersNotification`; `extendedScreens()` = every `NSScreen` that is not the console's, in `NSScreen.screens` order, `dropFirst()` fallback; one auxiliary fills `visibleFrame`; two auxiliaries on one extended screen split 60% left / 40% right; two auxiliaries on two-or-more extended screens each fill one; no extended screen → do nothing. The "open the display window" and "pop out the drawer" affordances call `ScreenPlacement.place(kind:)`. **Why consume, not rewrite:** the roadmap names `ScreenPlacement` a surviving piece; the 60/40 split and `visibleFrame`-not-`frame` are decisions Larry already lives with. The one native change is that placement now moves real `NSWindow` scenes (found via `findHostWindow`) instead of WKWebView-hosted windows — the window *lookup* is CORE's, this plan only calls it.

### P12 — Voice controls port `MicControls` semantics onto `JarvisClient`; no `mic_unmute`.
`MicControlsView` binds to `JarvisClient`: mute toggles `client.setMicEnabled(_:)` (CORE's `RTCAudioTrack.isEnabled = false`, N9 obligation 4 — track stays alive with silence), the wake toggle drives CORE's wake path (N10), push-to-talk (hold, macOS key monitor) enables the mic while held. The three `ui` commands the client owns (`mic_mute`/`wake_on`/`wake_off`, CORE §3 N10 / C5) are applied here through the *same* setters the buttons call; there is deliberately **no `mic_unmute`** (`MicControls.tsx:90` — while muted the user cannot be heard; the wake word is the way back). A `ui` command that changes nothing sends `ClientMessage.uiNoop(reason:)` and the bot voices it (N8). **Why (C5):** the state owner applies its own commands through its own setters, so voice and click can never diverge — the native form of `MicControls.tsx:93-136`.

### P13 — Orb/wave amplitude is driven by `botIsSpeaking` + `voiceState`, not a new audio tap.
`VoiceWaveView` (the full-bleed background) and `OrbFieldView` (satellites + readout) both take a derived `VoiceState` (`offline|connecting|listening|speaking`), computed exactly as the web does: `state == .connected ? (botIsSpeaking ? .speaking : .listening) : (state == .connecting ? .connecting : .offline)`. Wave amplitude uses a `TimelineView`-driven simulated envelope keyed on that state (the web's own fallback, `VoiceWave.tsx:125`), louder while `.speaking`. The satellites read `AgentRunStore` (working pulse / done tick / last task on tap → switches the drawer to Runs, `OrbField.tsx:148-174`). **Why no real input meter:** reading the live mic level would need a new audio-level publisher on `JarvisClient` (a K8 change) and an audio tap that competes with the WebRTC track; the simulated envelope is what the web falls back to whenever `getUserMedia` for the meter fails, and it is visually sufficient. A real meter is a §6 tuning-knob-guarded later enhancement (§2).

### P14 — Display surface: `surface == "window"` → the display window; everything else → the Output tab.
Ported from `App.tsx:238-241`/`displayResults.ts`. The `AppMessageRouter` (§5 step 5) routes each `display` `AppMessage` by `payload.surface` (defaulting nil/unrecognised to `.drawer`, CORE §3 N7 `DisplayPayload.surface` decoder): `.window` → `DisplayWindowStore` (rendered by `DisplayScene`, placed via P11); `.drawer` → `DisplayResultStore` (the Output tab). `DisplayContentView` is one shared renderer (markdown/image/links, mirroring `DisplayContent.tsx`) used by both the Output tab and the display window. **Why one router, one renderer:** the web has exactly one display listener (`App.tsx:217`) and one `DisplayContent` component shared by three consumers; duplicating the surface-split or the renderer is self-audit item 4.

### P15 — Tab identity and voice aliases are preserved exactly.
The seven tab keys stay `repo|edit|memory|runs|agents|output|transcript` with labels `Repo|Edit|Memory|Runs|Agents|Output|Log` (`SideDrawer.tsx:33-64`). A `ui` app-message with `action == "drawer_tab"` and a `tab` value switches the active tab through the drawer scene's setter (C5, the state owner). **Why exact keys:** `jarvis/bot/ui_control.py`'s `TAB_ALIASES` resolves "developer"/"dev"/"agent" → `agents` server-side *before* sending the `ui` message, so the client only ever receives a real key; changing a key here would silently break "show me the developer tab". This plan changes no key.

### P16 — The Log tab is built and wired, but its stream is silent against today's bot; the empty state says so.
Per CORE correction 6 / R-N6: this bot emits no RTVI transcription messages, so `JarvisClient.transcript` stays empty and the `ConversationStore` never fills. `LogView` is still built (it interleaves `ConversationStore.entries` with `AgentRunStore` run chips, exactly as `Transcript.tsx:37-62` merges conversation and runs) — the **run chips work today** (they come from the live `AppMessage` stream), so the Log is not wholly empty; only the spoken bubbles are absent. The empty/partial state copy is specified: when there are run chips but no bubbles, a one-line footer "Spoken transcript needs a backend change (RTVIObserver) — tracked as R-A1." **Why build it now and flag the dependency (C1, C10):** the tab structure, the run-chip interleave, and the store are all client work with no backend dependency; only the bubble source is missing. Building it against the empty stream (which CORE already unit-tests the decoder for, N7) means the day the backend plan lands `RTVIObserver`, the bubbles appear with **no** native change. Inventing the backend change here is forbidden by C1; it is carried as R-A1 (§10) for the backend plan to schedule — **flagged, not worked around.**

## §4 Files — complete manifest

Every file touched in §5 appears here; nothing here is absent from §5. **Delete: none** (T1.4 owns deletion — §0, §2).

### Modify — `macos/JarvisKit/` (additive: the F12 response structs + write methods)

| Path | Change | Step |
|---|---|---|
| `macos/JarvisKit/Sources/JarvisKit/AdminAPI.swift` | Add the per-tab response structs (`GitStatus`, `GitDraft`, `GitActionResult`, `SelfEditModel(s)`, `SelfEditStatus`, `SelfEditProposal`, `MemoryOverview` + leaves, `MemoryReviews`, `KnowledgeOverview` + leaves, `RunsList`/`RunSummary`, `RunDetail`/`RunEvent`) and the additive methods (`gitStatusTyped`, `prepareCommit`/`commit`/`preparePush`/`push`, `selfeditValidate`/`selfeditSubmit`/`selfeditRevert`, plus typed wrappers `memoryOverview`/`memoryReviewsTyped`/`knowledgeTyped`/`runsTyped`/`runTyped`) — §3 P2-P5 verbatim | 6-9 |
| `macos/JarvisKit/README.md` | Note the additive structs/methods and that they are the F12 deliverable | 6 |

### Create — `macos/MortimerHost/Sources/MortimerHost/` (the views)

| Path | Purpose | Step |
|---|---|---|
| `App/MortimerHostApp.swift` | replaces the harness: app-scope `JarvisClient` + three stores + router; `ConsoleScene`/`DisplayScene`/`DrawerScene`; Debug menu (`Clear stored token`, `Show message log`) | 1 |
| `App/AppMessageRouter.swift` | the ONE `messageStream()` consumer → dispatch to the three stores + display window (P8, P14) | 5 |
| `App/AppTheme.swift` | colour tokens ported from `App.css` `--glass-*`/`--bg` | 4 |
| `App/Glass.swift` | `.mortimerGlass(_:)` + `GlassRole`; glass-on (T1.0 material) / glass-off (opaque) arms (P10) | 4 |
| `App/VoiceState.swift` | the derived `VoiceState` enum + derivation (P13) | 4 |
| `App/AppTuning.swift` | every number, one place (§6) | 4 |
| `Stores/AgentRunStore.swift` | `@Observable`, `applyServerMessage` reducer ported from `agentRuns.ts` (P8) | 5 |
| `Stores/DisplayResultStore.swift` | `@Observable`, drawer-routed display results (P8, P14) | 5 |
| `Stores/ConversationStore.swift` | `@Observable`, reads `JarvisClient.transcript` (P8, P16) | 5 |
| `Console/ConsoleView.swift` | topbar + stage + bottombar over the wave (P1) | 4 |
| `Console/VoiceWaveView.swift` | full-bleed `TimelineView` wave (P13) | 13 |
| `Console/OrbFieldView.swift` | satellites + beams + readout (P13) | 13 |
| `Console/MicControlsView.swift` | mute / wake / PTT bound to `JarvisClient` (P12) | 5 |
| `Console/TopBarView.swift` | brand, connect, voice picker, capability chip, drawer + display toggles | 4 |
| `Display/DisplayWindowView.swift` | the `DisplayScene` body — stack of display panels (P14) | 12 |
| `Display/DisplayContentView.swift` | shared markdown/image/links renderer (P14) | 12 |
| `Display/DisplayWindowStore.swift` | `@Observable`, `surface == "window"` payloads (P14) | 12 |
| `Drawer/DrawerView.swift` | the tab strip + active-tab body; the `DrawerScene` body (P15) | 6 |
| `Drawer/RepoTab.swift` | `RepoViewModel` + view (P2, P6, P7) | 6 |
| `Drawer/EditTab.swift` | `EditViewModel` + view (P3, P6, P7) | 7 |
| `Drawer/MemoryTab.swift` | `MemoryViewModel` + view (P4, P6, P7) | 8 |
| `Drawer/RunsTab.swift` | `RunsViewModel` + view (P5, P6, P7) | 9 |
| `Drawer/AgentsTab.swift` | reads `AgentRunStore` (P8) | 10 |
| `Drawer/OutputTab.swift` | reads `DisplayResultStore` (P8) | 11 |
| `Drawer/LogTab.swift` | reads `ConversationStore` + `AgentRunStore` (P8, P16) | 11 |
| `Placement/WindowPlacement.swift` | thin caller of `MortimerHost`'s ported `ScreenPlacement` for the three scenes (P11) | 2 |

### Create — tests

| Path | Purpose | Step |
|---|---|---|
| `macos/JarvisKit/Tests/JarvisKitTests/AdminResponseDecodeTests.swift` | §7.1 — decode each response struct from a captured fixture | 6-9 |
| `macos/MortimerHost/Tests/MortimerHostTests/AgentRunStoreTests.swift` | §7.2 — the reducer, ported from the `agentRuns.ts` behaviour | 5 |
| `macos/MortimerHost/Tests/MortimerHostTests/TabStateTests.swift` | §7.3 — the four-state mapping (P7) | 6 |
| `macos/JarvisKit/Tests/JarvisKitTests/fixtures/` | 9 captured JSON bodies (one per read route) | 6-9 |

## §5 Implementation steps, in order

**Step 0 — Larry confirms T1.0 sign-off (§0.4) and creates branch `native-client-app`.** If T1.0 is not signed off, stop.

**Step 1 — `MortimerHostApp.swift`: three scenes, app-scope state (P1).** Replace the harness `WindowGroup`. Create `@StateObject var client = JarvisClient(config: .fromEnvironment())` and `@State` instances of `AgentRunStore`/`DisplayResultStore`/`ConversationStore`/`DisplayWindowStore`, injected via `.environment`. Three scenes: `Window("Mortimer", id: "console") { ConsoleView() }`, `Window("Display", id: "display") { DisplayWindowView() }`, `Window("Panels", id: "drawer") { DrawerView() }`. Each scene's root uses `.background(WindowIdentifierSetter(kind:))` (a tiny `NSViewRepresentable` that sets `window.identifier` so `findHostWindow` matches). Debug menu: `Clear stored token` (calls `KeychainStore.clear`), `Show message log` (opens the ported debug `List`). **Test:** compile gate (§8 V1).

**Step 2 — `WindowPlacement.swift` (P11).** A `@MainActor enum` wrapping `MortimerHost`'s ported `ScreenPlacement`: `openDisplay()` opens the `display` scene (`@Environment(\.openWindow)`) then calls `ScreenPlacement.place(kind: .display)`; `popOutDrawer()` likewise for `.drawer`; both re-run on `didChangeScreenParametersNotification` (the observer already lives in `ScreenPlacement`). No new placement math. **Test:** §8 V7 (Larry, multi-display).

**Step 3 — `AppTuning.swift` + `AppTheme.swift` + `Glass.swift` + `VoiceState.swift` (P10, P13, §6).** Constants (§6). Theme tokens from `App.css`. `.mortimerGlass(_:)` with the two arms; the glass-on arm uses the T1.0-signed material (leave a single `// T1.0:` marker at the one line the review fills — the rest of the view tree never changes). `VoiceState.derive(state:botIsSpeaking:)`.

**Step 4 — Console chrome: `ConsoleView` + `TopBarView` + `MicControlsView` shell (P1, P12).** Lay out topbar / stage / bottombar. `VoiceWaveView`/`OrbFieldView` are placeholders until step 13. `TopBarView`: `ConnectButton` (binds `client.connect/disconnect` + `client.state`), a voice picker (reads `voiceCatalog`/`voiceCurrent` `AppMessage`s, sends `ClientMessage.voiceSet`), a capability chip (reads `.capability`), the drawer toggle, the display toggle (`WindowPlacement.openDisplay`). **Test:** §8 V2 (connect/talk against a live bot).

**Step 5 — The three stores + `AppMessageRouter` + `MicControlsView` behaviour (P8, P12, P14).** Write `AgentRunStore` (reducer ported verbatim from `agentRuns.ts:276-392` — §7.2 pins it), `DisplayResultStore`, `ConversationStore` (subscribes to `client.$transcript`). `AppMessageRouter`: one `Task { for await m in client.messageStream() { dispatch(m) } }` started at app scope, dispatching `agent*`→`AgentRunStore`, `display`→router-by-surface (P14), leaving `voice*`/`ui`/`speakerGate` to their owners. `MicControlsView`: mute/wake/PTT (P12) + apply the three owned `ui` commands via `subscribe`. **Test:** §7.2, §8 V3 (a delegated run shows live in Agents).

**Step 6 — Repo tab (P2, P6, P7).** Add `GitStatus`/`GitDraft`/`GitActionResult` + methods to `AdminAPI` (§3 P2 verbatim). `RepoViewModel`: poll `gitStatusTyped` every `httpPollSeconds`; render branch/clean/ahead/behind + `changedFiles` list. Commit row: text field → `prepareCommit` → show `GitDraft.summary` + "Confirm commit" → `commit(actionId:)` → re-poll. Push: `preparePush` → "Confirm push" → `push(actionId:)`. `DrawerView` tab strip (P15). **Test:** §7.1 (decode `GitStatus`), §7.3 (states), §8 V4.

**Step 7 — Edit tab (P3).** Add `SelfEditModel(s)`/`SelfEditStatus`/`SelfEditProposal` + `selfeditValidate`/`selfeditSubmit`/`selfeditRevert`. `EditViewModel`: poll `selfeditStatus`; on `error != nil` show error state; else render active/branch/goal + a proposals list (`path` + collapsible `diff`) + `validatedOk`. Model picker from `selfeditModels`. Buttons: run (`selfeditRun`, existing), validate, submit, revert — each re-polls. **Test:** §7.1 (decode both `SelfEditStatus` shapes), §8 V4.

**Step 8 — Memory tab (P4).** Add the memory/knowledge structs. `MemoryViewModel`: poll `memoryOverview` + `memoryReviewsTyped` + `knowledgeTyped`. Render: fact cards (key/content/tier/audience), the review queue (each with the kind-appropriate resolve actions → `resolveReview`), a per-fact delete (`deleteFact`, with a confirm), and the knowledge readout with `notReachingPrompt` as the loud line (P4). **Test:** §7.1, §8 V4.

**Step 9 — Runs tab (P5).** Add `RunsList`/`RunSummary`/`RunDetail`/`RunEvent`. `RunsViewModel`: poll `runsTyped`; list rows (agent, task, status colour, latency); tapping a row loads `runTyped(id:)` and shows events (`type`/`tool`/`ok`/`latencyMs`) + the JSONL payload count. Satellite-click filter (P13) pre-selects an agent. **Test:** §7.1 (decode `RunDetail`, incl. `RunEvent.ok` as `Int?`), §8 V4.

**Step 10 — Agents tab (P8).** `AgentsView` reads `AgentRunStore.runs` (newest first, `maxAgentRuns`); render the card (name, model chip with fallback/unusable colour, planner chip, task, activity ticker, stages, detail on failure) — the SwiftUI form of `AgentsTab.tsx`. **Test:** §8 V3.

**Step 11 — Output + Log tabs (P8, P16).** `OutputView` reads `DisplayResultStore` (collapsible newest-first, `DisplayContentView` bodies). `LogView` interleaves `ConversationStore.entries` + `AgentRunStore` run chips by timestamp (`Transcript.tsx:37-62`); the P16 footer when only chips are present. **Test:** §8 V5 (a work-product result lands in Output; run chips appear in Log).

**Step 12 — Display window (P14).** `DisplayWindowStore` (`surface == "window"` payloads, cascade-offset stack), `DisplayWindowView` (draggable/resizable panels), `DisplayContentView` (shared). Router already routes to it (step 5). **Test:** §8 V6.

**Step 13 — Orb + wave (P13).** `VoiceWaveView` (`TimelineView` simulated envelope keyed on `VoiceState`), `OrbFieldView` (satellites from `AgentRunStore`, beams, readout, wake ripple). Apply `.mortimerGlass` to every panel/card/chip. **Test:** §8 V8 (glass legible over a busy desktop — the T1.0 acceptance).

**Step 14 — Larry commits `native-client-app`** after §8 passes.

## §6 Tuning knobs — `AppTuning.swift`, one place each

| Constant | Default | Meaning | Override |
|---|---|---|---|
| `httpPollSeconds` | 3.0 | HTTP tab poll interval (matches web's 3 s, `EditModePanel` council poll) | `UserDefaults` `JARVIS_HTTP_POLL_SECONDS` |
| `maxAgentRuns` | 20 | Agents tab run cap (`agentRuns.ts:79`) | compile-time |
| `maxActivity` | 50 | ticker lines per run (`agentRuns.ts:61`) | compile-time |
| `maxTools` | 10 | tool chips per run (`agentRuns.ts:54`) | compile-time |
| `doneFadeSeconds` | 8.0 | non-self-edit success fade (`agentRuns.ts:53`) | compile-time |
| `maxDisplayResults` | 6 | Output tab cap (`MAX_OPEN_DISPLAY_PANELS`) | compile-time |
| `maxConversationEntries` | 200 | Log cap (`conversationFeed.ts:36`) | compile-time |
| `drawerDefaultWidth` | 400 | drawer width (`SideDrawer.tsx:70`) | `UserDefaults` `JARVIS_DRAWER_WIDTH` |
| `displaySplitLeftFraction` | 0.60 | two-panel extended-screen split (DP8, CORE §1.4) | compile-time |

Flags (from `JarvisFlags`, CORE §3 N16, `UserDefaults`): `JARVIS_GLASS_ENABLED` (glass on/off, §9), `JARVIS_WAKEWORD_ENABLED`, `JARVIS_CLIENT_AUTH_ENABLED`. This plan adds **no new flag** — glass on/off reuses CORE's `JARVIS_GLASS_ENABLED`.

## §7 Tests

The sandbox cannot build Swift (§0.3), so these are written, not run here; Larry runs them (§8 V1). Fixtures are **captured from Larry's running sidecar** once and committed (the exact `curl` per route is in §8 V0), never hand-authored — a hand-authored fixture cannot catch a shape drift, which is the whole point of typing the structs.

### 7.1 `AdminResponseDecodeTests.swift` (JarvisKit)
One test per response struct, decoding its captured fixture and asserting a representative field of each type — the test that would catch a `CodingKeys` typo or an `Int`/`Bool` mismatch:
| Test | Fixture route | Asserts |
|---|---|---|
| `testDecodeGitStatus` | `/api/git/status` | `changedFiles` non-nil, `ahead`/`behind` are `Int` |
| `testDecodeSelfEditModels` | `/api/selfedit/models` | `models[0].keyPresent` is `Bool`, `isDefault` decoded from `"default"`, `tier` optional |
| `testDecodeSelfEditStatusReal` | `/api/selfedit/status` (idle) | `ok == nil`, `proposals` decoded; `testDecodeSelfEditStatusBusy` from an `{"ok":false,"error":...}` fixture asserts `ok == false`, `error != nil` |
| `testDecodeMemoryOverview` | `/api/memory` | `facts[0].sourceSessionId` optional, `usage.tiers` is `[String:Int]`, `usage.overCapacity` is `Bool` |
| `testDecodeMemoryReviews` | `/api/memory/reviews` | `reviews[0].keys` is `[String]`, `id` is `Int` |
| `testDecodeKnowledge` | `/api/knowledge` | `memory.notReachingPrompt` is `Int`, `skills.enabled[0].hasScripts` is `Bool` |
| `testDecodeRunsList` | `/api/runs` | `runs[0].latencyMs` is `Int?`, `toolCount` non-optional |
| `testDecodeRunDetail` | `/api/runs/{id}` | **`events[0].ok` decodes as `Int?` (1/0/null), NOT `Bool`** (the load-bearing one), `payload` is `[JSONValue]` |
| `testDecodeOlderSidecarMissingField` | a fixture with `tool_count` removed | `toolCount` defaults (no throw) — the `decodeIfPresent`+default rule (F8) |

### 7.2 `AgentRunStoreTests.swift` (MortimerHost)
Ports the `agentRuns.ts` behaviour that has no equivalent web test but is load-bearing:
| Test | Input `AppMessage`s | Expected |
|---|---|---|
| `testWorkingInsertsRun` | `agentWorking` | one run, `doneAt == nil`, `model`/`modelFallback` set |
| `testActivityMatchedByRunId` | `agentWorking(runId:"r1")`, `agentActivity(runId:"r1")` | ticker line on r1, matched by id not name |
| `testActivityFallsBackToLiveRun` | `agentWorking(runId:"")`, `agentActivity(runId:"")` | line lands on the live run |
| `testPlannerModelSticks` | activity with `planner_model` then activity without | `plannerModel` retained (`agentRuns.ts:327-341`) |
| `testSelfEditRunsAppendAndCap` | 21 self-edit `agentWorking` | capped at `maxAgentRuns`, a live run never evicted |
| `testNonSelfEditReplaces` | two `agentWorking` for the same non-self-edit agent | one card (replace, `agentRuns.ts:258`) |
| `testDoneSetsOkAndDetail` | `agentWorking`, `agentDone(ok:false,detail:)` | `doneAt` set, `ok == false`, `detail` clamped |

### 7.3 `TabStateTests.swift` (MortimerHost)
| Test | Input | Expected `TabState` |
|---|---|---|
| `testThrowMapsToError` | a thrown `JarvisError.http(500,"x")` | `.error` |
| `testOkFalseMapsToError` | `{"ok":false,"error":"nope"}` | `.error("nope")` |
| `testEmptyListMapsToEmpty` | `RunsList(ok:true,runs:[])` | `.empty` |
| `testUnauthorizedNoRetry` | `JarvisError.unauthorized` | `.error("Token required — set it in the Debug menu")`, poll task does not re-fire |

## §8 Verification Larry runs on his hardware
(The sandbox lacks Xcode, a Mac, Keychain, mic, and network to the bot.)

- **V0 — capture fixtures.** With `./scripts/mortimer.sh start` running, `curl -s localhost:7861/api/git/status`, `/api/selfedit/models`, `/api/selfedit/status`, `/api/memory`, `/api/memory/reviews`, `/api/knowledge`, `/api/runs`, and `/api/runs/$(curl -s localhost:7861/api/runs | python3 -c 'import sys,json;print(json.load(sys.stdin)["runs"][0]["run_id"])')` into `macos/JarvisKit/Tests/JarvisKitTests/fixtures/`. Plus a hand-trimmed busy-status fixture (`{"ok":false,"error":"an upgrade run is in progress"}`).
- **V1 — build + unit tests.** `cd macos/JarvisKit && swift test` and `cd macos/MortimerHost && swift test` both green (§7).
- **V2 — connect and talk.** Launch `MortimerHost`; the console window shows the wave; connect; hold-to-talk; the bot replies (proves JarvisKit still works under the new views).
- **V3 — Agents tab live.** Ask for something that delegates ("what's the weather"); the Agents tab shows a live card with the ticker advancing and a model chip, settling to done.
- **V4 — the four HTTP tabs.** Repo shows the branch + changed files, and a commit draft→confirm round-trips; Edit shows models and (after "start a self-edit") a proposals list, and validate/submit/revert work; Memory shows facts + the review queue + the `notReachingPrompt` line, and a review resolves; Runs lists runs and a row expands to events + payload count.
- **V5 — Output + Log.** A work-product result (a repo write) lands in Output; the Log shows run chips interleaved. The P16 footer appears (no spoken bubbles today) — this is expected, not a defect.
- **V6 — display window.** "Show the radar" opens the display window with the weather/radar card; it can be dragged and resized.
- **V7 — multi-display (DP8).** With one extended screen, "open the display window" parks it full on the extended screen; popping the drawer too splits 60/40; unplugging/replugging a monitor relocates live windows (P11).
- **V8 — glass acceptance (the T1.0 gate).** Over a busy desktop, every panel/drawer/display reads as Liquid Glass and its text stays legible (the answer the CORE spike raised); toggling `defaults write <bundle-id> JARVIS_GLASS_ENABLED -bool false` makes them opaque (§9).
- **V9 — daily-driver period (gate G1(e)).** Larry runs `MortimerHost` as the primary interface for **five days** before T1.4 deletes `web/`. Any tab that a real session needs and this plan missed is filed against a follow-up, not against T1.4's deletion trigger.

## §9 Rollback
- **Glass:** `defaults write <bundle-id> JARVIS_GLASS_ENABLED -bool false` → every `.mortimerGlass` surface becomes opaque (`AppTheme.panelOpaque`); no rebuild (P10, §6).
- **The whole app:** `web/` and `macos/MortimerShell/` are untouched (§2), so the WKWebView shell and the browser console both still run. Reverting is not launching `MortimerHost`; nothing to undo, no data migration (this plan writes no data — the stores are in-memory, P9).
- **A single broken tab:** each tab is an independent view-model; a tab throwing renders its `.error` state (P7) rather than taking down the drawer or the app.

## §10 Risks

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| **R-A1** | The Log tab's spoken transcript is empty because no `RTVIObserver` is wired server-side (CORE R-N6 / correction 6) | certain today | Log shows run chips but no bubbles | Built and wired now (P16); the empty state says so; the bubbles light up with **no** native change the day the backend plan lands `RTVIObserver`. **C1 forbids adding it here** — flagged, not worked around. |
| **R-A2** | A sidecar response shape drifts after the fixtures are captured | low | one tab's decode throws → `.error` state, not a crash | The `decodeIfPresent`+default rule (F8) tolerates *added/removed* optional fields; a changed *type* is caught by §7.1 the next time fixtures are recaptured. The tab degrades to its error state (P7), never a blank. |
| **R-A3** | The additive `AdminAPI` write methods (git commit/push, selfedit validate/submit/revert) are read as a K8 change that breaks CORE's "seventeen routes" checkbox | low | contract confusion | Declared in the header (INTRODUCES) as **additive**; CORE's seventeen read routes are unchanged; §12 scopes the addition. |
| **R-A4** | T1.0 has not actually signed off when implementation starts | medium | the glass layer is built against an unreviewed direction and redone | §0.4 hard gate: confirm sign-off first, else stop. The view structure is glass-agnostic (P10), so even a late review changes one file. |
| **R-A5** | The council/plan Edit sub-panels are missed by a user who used them in the web | medium | a feature gap during the daily-driver period | Explicit non-goal (§2) with voice still reaching them; V9 files any real need against a follow-up, not against T1.4. |
| **R-A6** | The simulated wave envelope reads as less "alive" than the web's mic-driven wave | low | cosmetic | P13 matches the web's own fallback; a real input meter is a §6-guarded later enhancement. |
| **R-A7** | `KeychainStore` is mistaken for the T4b sensitive-tier key holder | low | a security-tier confusion | §2 / `CROSS_PLAN_RESOLUTION.md` §C F13: it holds the K1 bearer token only; T4b is a different item, a different plan. |

## §11 Self-audit (the 9-item taxonomy, item by item)

1. **Multi-consumer contracts typed member-by-member.** The nine `AdminAPI` response structs (P2-P5) are the F12 deliverable — every member has a Swift type, an optionality mirroring the SQL/emitter, and a `CodingKeys` entry; the three RTVI store shapes (P8) mirror `agentRuns.ts`/`displayResults.ts`/`conversationFeed.ts` member-for-member. Checked: `RunEvent.ok` is `Int?` (SQL `ok INTEGER`), not `Bool`; `latencyMs`/`sourceSessionId` are optional (nullable columns); `toolCount` is non-optional (`NOT NULL DEFAULT 0`).
2. **Lifecycle (unmounted vs hidden; does state survive).** Stated: the app-scope `JarvisClient` + three stores survive any window/tab open or close (P1, P6, P8) — the exact reason the web made `agentRuns.ts` a module store (`agentRuns.ts:9-11`). A drawer tab view unmounting does not restart its poll (view-model owned by the scene) nor lose a half-finished draft (P6).
3. **How a value is applied (which property, which transition).** Glass is a background material on the container, applied by `.mortimerGlass`, never per-view opacity (P10) — the documented `WindowVibrancy.swift:153-164` mistake. Mute is `RTCAudioTrack.isEnabled = false` (track alive with silence), not `stop()` (P12).
4. **Two sections describing the same behaviour differently.** Checked: the Agents tab (live, from `AppMessage`) and the Runs tab (persisted, from `/api/runs`) are two surfaces with two sources (P8) — not the same data twice. One display router, one `DisplayContentView` (P14).
5. **Copy and visual states named.** The four `TabState` cases and each tab's empty copy are specified (P7); the P16 Log footer copy is specified; loading/error copy is specified.
6. **Initialization timing.** The single `AppMessageRouter` `Task` starts at app scope (step 5), before any tab view exists, so no message is missed while a tab is unmounted (the store is always alive, the view is not). Poll tasks start on tab appear, cancel on disappear (P6).
7. **Signatures agree; every schema column populated; every value derivable.** Every `agent_runs`/`agent_events` column maps to a `RunSummary`/`RunEvent` field (P5); every `memory`/`knowledge` sub-field maps (P4). The additive `AdminAPI` method signatures (§4, §5) match their P2-P5 request bodies. `VoiceState` is derivable from `state` + `botIsSpeaking` (P13, both published by CORE's `JarvisClient`).
8. **Judgment removed.** No "use your judgment": the four-state mapping is a deterministic rule (P7); the display-surface split is `payload.surface` with a specified default (P14); T1.0-not-signed and shape-drift are stop-and-report / degrade-to-error branches (§0.4, R-A2).
9. **Plan drift.** Every file in §5 is in §4's manifest and vice versa; the delete section is deliberately empty (T1.4 owns it). The additive `AdminAPI` structs/methods are declared as INTRODUCES in the header and appear in both §3 and §4. No section says "X exists" that another says "write X".

## §12 Approval checklist
- [ ] Larry confirms **T1.0 (Liquid Glass design review) has signed off** — this plan's hard precondition (§0.4, §1.0).
- [ ] Larry accepts the **nine per-tab `AdminAPI` response structs** (§3 P2-P5) as the F12 deliverable, added inside `macos/JarvisKit/Sources/JarvisKit/AdminAPI.swift`.
- [ ] Larry accepts the **additive `AdminAPI` write methods** (git commit/push draft→confirm; selfedit validate/submit/revert) as an additive extension of K8 (not a change to CORE's seventeen read routes) — R-A3, §2.
- [ ] Larry accepts the **Edit-tab scope**: self-edit run lifecycle in; council & plan-authoring panels deferred to a follow-up (§2).
- [ ] Larry accepts the **Log tab shipping with a silent transcript** today, wired for the backend `RTVIObserver` change to light it up later (P16, R-A1) — C1 forbids the backend change here.
- [ ] Larry accepts that `KeychainStore` holds the **K1 bearer token only**; the T4b tier key is a different plan (§2, F13).
- [ ] Larry runs §8 V0-V9, including the **five-day daily-driver period (G1(e))** before T1.4 deletes `web/`.
