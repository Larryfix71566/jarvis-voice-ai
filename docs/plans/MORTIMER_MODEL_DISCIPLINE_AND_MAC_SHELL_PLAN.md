# MORTIMER MODEL DISCIPLINE + MAC SHELL — implementation plan

**The two decisions this implements (Larry, 2026-08-17):**

1. The voice model (Haiku) is an interface and a dispatcher, never a
   design/build model. The logs show it doing design work in three
   places: the developer sub-agent runs ON Haiku (every sub-agent
   inherits the voice model — `config/agents.yaml` routes tools, not
   brains); the Supervisor rewrites failed tasks with invented specifics
   (six re-delegations of one dismiss-button request, one inventing
   "authentication keys from the vault"); and the developer starts every
   run blind, burning its 5-iteration budget rediscovering its own
   codebase (observed verbatim: "The current repository appears to be
   the Mortimer backend (Python/FastAPI), not a frontend repository").
   Developer failure rate: 22 of 53 runs all-time not ok.
2. The frontend becomes a **SwiftUI shell hosting the existing web
   surfaces in WKWebViews** — native macOS windows, menu-bar app feel,
   real multi-screen placement (Safari has no Window Management API, so
   every browser-side placement feature is dead on Larry's machine) —
   while `web/src/**` remains the agent-editable UI with the existing
   npm-build validation gate.

Model-selection assurance is deliberately NOT council-per-task (the
council's founding rule: convening is never predictive; cost rises only
after demonstrated difficulty). Assurance comes from: deterministic tier
assignment at dispatch (A1), the existing E1 escalation council when the
assigned model demonstrably fails, and run-log evidence (`model` column,
migration 0011) for periodic tuning.

**Ground rule (same as every plan in this repo):** every decision below
has already been made. Implement it exactly as written; if something is
genuinely undecided, that is a defect in this document — stop and report
it rather than choosing.

---

## Part A — Model discipline (A1–A5)

### A1 — Per-agent model profiles in `config/agents.yaml`

Each `sub_agents:` entry gains one optional field, `model_profile:`,
naming a profile in `config/upgrade_models.yaml` — the ONE model
registry (reusing `jarvis/agents/upgrade_agent.py`'s
`load_model_registry`/`resolve_profile`; never a second registry, same
rule as the vault's never-a-second-storage-path).

- `SubAgent.__init__` gains `model_profile: str | None = None` (threaded
  from the agents.yaml loader in `jarvis/agents/supervisor.py`). When
  set and resolvable: the client is
  `AsyncOpenAI(api_key=os.environ[profile["api_key_env"]],
  base_url=profile["base_url"])` and every chat call uses
  `profile["model"]` instead of `settings.openai_model`. Temperature
  stays omitted (D-003, unchanged).
- Resolution failures fail soft, loudly: unknown profile name or missing
  API key at construction → `logger.warning` + fall back to the settings
  client exactly as today. Voice must boot on a fresh checkout with one
  key; the run log's `model` column makes the fallback visible on every
  run.
- An injected `client_factory` (the unit-test seam) always wins: when
  present, profile resolution is skipped entirely — existing tests and
  fakes must not need changes to keep passing.
- The RESOLVED model string is what `SubAgent.run()` passes to
  `RunLogger` (P3's `model=` param) — the log records what actually ran,
  never what was configured.
- Assignment, locked: `developer` gets `model_profile: kimi-k3`
  (registry default tier-`mid`-or-better build model; one YAML line to
  change). Scheduler, librarian, analyst, systems: no `model_profile` —
  Haiku is correct for conversation-grade work.
- `config/agents.yaml` is already on the self-edit deny list —
  reassigning brains stays a human decision.

### A2 — Supervisor stop rule (prompt) + retry guard (mechanical)

Two layers, because last night's six-delegation storm shows the prompt
alone cannot be trusted:

- **Prompt:** `SUPERVISOR_PROMPT` (`jarvis/prompts.py`) gains one rule
  (append to the numbered delegation rules, taking the next number),
  verbatim: `"When a delegation returns FAILED, report the sub-agent's
  stated reason to the user in your own brief words and ask how to
  proceed. Never immediately re-delegate a reworded version of the same
  task, and never add details the user did not say (branch names,
  credentials, file paths) — invented specifics are how retries fail
  twice."`
- **Mechanical retry guard** in `jarvis/agents/delegate.py`'s handler
  closure (state lives in `build_delegate_tool`'s scope, per session):
  remember, per agent, the last FAILED task text and its timestamp. A
  new delegation to the same agent is REFUSED — without running — when
  BOTH: it arrives within `RETRY_GUARD_WINDOW_S = 120.0` of that
  failure, AND its task overlaps the failed task at ≥
  `RETRY_GUARD_OVERLAP = 0.5` using the existing symmetric token-overlap
  scorer from `jarvis/procedures.py` (`len(a & b) / min(len(a),
  len(b))` on the same stopword-filtered tokens — reuse the existing
  helper, do not re-implement). The refusal returns a normal tool-result
  string: `"REFUSED: the developer just failed this same task
  ({reason}). Report that failure to the user and ask how to proceed —
  do not retry with reworded instructions."` (agent name interpolated).
  A successful delegation to that agent clears its guard entry. A
  genuinely new user instruction produces different wording (overlap
  drops) or arrives later (window expires) — both pass. Constants live
  beside `DEFAULT_MAX_PARALLEL_DELEGATIONS`.

### A3 — Repo map: `docs/REPO_MAP.md`, injected for the developer

New file `docs/REPO_MAP.md` — a compact "where things live" map, ≤
`REPO_MAP_MAX_CHARS = 8000` when injected. Initial content: the
authoritative section list — repo layout (one line per top-level dir),
the web console's component map (`web/src/components/` by function:
`AmbientStrip.tsx` = upper-left clock/reminders/weather strip,
`OrbField.tsx` = wave + satellites, `SideDrawer.tsx` = right tabbed
drawer, `DisplayPanel.tsx` = floating result overlay, etc.), backend map
(`jarvis/bot/` pipeline, `jarvis/agents/` supervisor+subagents,
`jarvis/admin/` sidecar, `mcp_servers/*` skills), config map, docs map,
and a final line stating the current branch is whatever `git status`
says — never assume a branch name. Write it during implementation from
the tree itself; keep every entry to one line.

- Injection: `config/agents.yaml`'s developer entry gains
  `inject_repo_map: true`. When set, `SubAgent.__init__` reads
  `docs/REPO_MAP.md` at construction, resolving the repo root exactly
  the way the agents.yaml loader already resolves its own config path
  (one convention, not a second root-finding heuristic; missing file =
  skip silently — fresh checkout must not crash), truncates at
  `REPO_MAP_MAX_CHARS`, and appends it to the agent's system prompt
  under a `"Repository map (maintained, may lag reality — verify with
  tools before writing):"` header. Construction-time read is deliberate:
  one read per boot, not per run.
- Maintenance rule (one line added to CLAUDE.md): structural changes
  (new top-level modules, moved directories) update `docs/REPO_MAP.md`
  in the same change. It lives in `docs/**`, which is self-edit
  allowlisted — Mortimer can maintain its own map.

### A4 — Tests

- `tests/unit/test_subagent.py`: A1 — profile resolution (resolved model
  used in calls + passed to RunLogger; unknown profile falls back with
  warning; missing key falls back), A3 — repo map injected when flag
  set, skipped when file missing, truncated at the cap.
- `tests/unit/test_delegate.py`: A2 — guard refuses within
  window+overlap, allows after success, allows different task, allows
  after window expiry; refusal string shape.
- No routing-eval changes: the failures A2/A3 fix are intra-turn and
  intra-agent, invisible to supervisor-routing accuracy.

### A5 — Docs

CLAUDE.md: delegation-model paragraph gains `model_profile:` +
`inject_repo_map:` + the retry guard (short additions to the existing
paragraph, matching its style). `tests/acceptance/model-discipline.md`:
re-run the dismiss-button request end-to-end — developer (now on
kimi-k3, with the map) either does the small edit or routes to
selfedit_start, and a forced failure produces ONE report-and-ask, never
a retry storm. `.env.example`: unchanged (no new env vars).

---

## Part B — SwiftUI shell + WKWebViews (B0–B7)

### B0 — Spike first: two go/no-go questions, fallbacks predecided

New Xcode project `macos/MortimerShell/` (SwiftUI App lifecycle,
minimum macOS 14). The spike builds ONLY: one window hosting a
`WKWebView` on `http://127.0.0.1:5173/`, a second window on
`/display.html`, both sharing one `WKProcessPool` and the default
`WKWebsiteDataStore`. It answers two questions:

1. **Mic/WebRTC capture inside WKWebView.** Entitlement
   `com.apple.security.device.audio-input`,
   `NSMicrophoneUsageDescription` in Info.plist, and the
   `WKUIDelegate` media-capture permission callback returning `.grant`
   for this app's own origin. PASS = a full live voice turn (connect,
   speak, hear TTS) inside the shell window. FAIL fallback
   (predecided): the shell ships hosting Display + Drawer windows only;
   the console (mic) window stays in the browser; native audio capture
   is a future plan. Partial adoption still delivers the multi-screen
   goal.
2. **BroadcastChannel across two WKWebViews.** PASS = the display
   window's presence heartbeat reaches the console webview (same
   mechanism as the browser). FAIL fallback (predecided): a shell-side
   relay — a `WKUserScript` shim injected at documentStart that mirrors
   `BroadcastChannel` traffic up through a `WKScriptMessageHandler` and
   back down into the other webviews; `popoutWindow.ts` unchanged (the
   shim wraps the channel, pages don't know).

The spike result is recorded as two checked boxes + a sentence each in
this plan file before Part B proper begins.

### B1 — Window model: three scenes, reusing the three existing entries

Console (`/`), Display (`/display.html`), Drawer (`/drawer.html`) — the
Vite entries that already exist and already speak the presence/relay
protocol. The shell owns window chrome: native titlebars, resize,
fullscreen, per-screen placement. The web pages' own pop-out machinery
keeps working in plain browsers (nothing web-side is removed).

### B2 — Shell detection and the `⧉` buttons

A `WKUserScript` (documentStart, all frames = false) injects
`window.mortimerShell = { version: 1 }` plus a
`webkit.messageHandlers.mortimer` post channel. `popoutWindow.ts`'s
`open()` gains one branch at the top: when `window.mortimerShell`
exists, post `{cmd: "openWindow", name}` to the shell (which opens or
focuses the native Display/Drawer window) and return `null` — presence
(hasLive*) is already heartbeat-based since the console-reload fix, so
the in-page hide rules work identically with no `Window` ref. Voice
`display_popout`/`drawer_popout` therefore work unchanged. Browser
without the shell: existing behavior, untouched.

### B3 — Placement policy moves to Swift (shell mode)

The shell observes `NSScreen.screens` +
`NSApplication.didChangeScreenParametersNotification` and applies DP8's
exact semantics natively: one auxiliary window → fills the non-console
screen; Display + Drawer both open on one extended screen → Display
left 60% / Drawer right 40%; a monitor plugged in later relocates live
windows; no extended screen → windows open beside the console. Web-side
`placeOnExtendedScreen` short-circuits when `window.mortimerShell`
exists (the shell owns placement; double-placement must be impossible).
No Safari limitation applies — this is the point of the shell.

### B4 — Loading source and failure mode

The shell always loads `http://127.0.0.1:5173` (the console dev server
`./scripts/mortimer.sh` already starts). Unreachable → a native retry
screen: "Mortimer stack isn't running — start it with
./scripts/mortimer.sh", with a Retry button. Production
packaging/notarization/bundled static assets: explicit NON-GOALS of
this plan.

### B5 — Self-edit boundary

`macos/**` joins the self-edit deny list in
`config/self_edit_allowlist.json` — the agent must never edit the shell
that hosts it (same never-touch-your-own-machinery rule as the vault
and the model registry). `web/src/**` remains the agent-editable UI;
validation stays `npm run build` exactly as today. New
`scripts/build_shell.sh` wraps `xcodebuild` for humans; CI is untouched
(no macOS runner assumptions).

### B6 — Scope guard

v1 is: three windows, native placement, mic passthrough, retry screen.
NOT in v1: menu-bar extra, global hotkeys, dock badges, login item,
auto-start of the Python stack, packaging. Each is a separate future
decision.

### B7 — Naming

The app is "Mortimer" (shell implied). In code and docs the component
is "the shell" — never "sidecar" (the `:7861` admin process), never
"drawer" (the tabbed panel it hosts).

---

## §2 Files

**Part A — modified:** `config/agents.yaml` (A1 `model_profile`, A3
`inject_repo_map`); `jarvis/agents/supervisor.py` (thread new fields);
`jarvis/agents/base.py` (A1 client/model resolution, A3 map injection);
`jarvis/agents/delegate.py` (A2 guard + constants);
`jarvis/prompts.py` (A2 supervisor rule); `CLAUDE.md` (A5);
`tests/unit/test_subagent.py`, `tests/unit/test_delegate.py`.
**Part A — new:** `docs/REPO_MAP.md`,
`tests/acceptance/model-discipline.md`.

**Part B — new:** `macos/MortimerShell/` (Xcode project: App entry,
WebView wrapper, window controller, placement controller, injected
shim), `scripts/build_shell.sh`, `tests/acceptance/mac-shell.md`.
**Part B — modified:** `web/src/popoutWindow.ts` (B2 shell branch, B3
short-circuit); `config/self_edit_allowlist.json` (B5 deny `macos/**`);
`CLAUDE.md` (shell paragraph); `.gitignore` (Xcode noise: `xcuserdata/`,
`build/`, `DerivedData/`).

---

## §3 Implementation order

1. A1 per-agent profiles + tests (the single highest-leverage change).
2. A3 repo map + injection + tests.
3. A2 stop rule + retry guard + tests.
4. A5 docs + acceptance; full pytest; **restart the bot** (prompt and
   config changes are read at boot — last night's failures ran on
   pre-fix prompts for exactly this reason).
5. B0 spike; record both verdicts in this file.
6. B1–B4 shell windows + placement + web-side branches (order inside:
   B2 shim first, then windows, then placement).
7. B5 boundary + build script; B7 naming sweep; acceptance checklists;
   web tsc/lint; full pytest.

Part A ships and is verified live before B0 begins — the shell is built
by voice-driven self-edits wherever possible, which is itself the first
real test of Part A.

---

## §4 Verification (two acceptance files, key items)

- [ ] A1: `python -m jarvis.runlog` shows `model` = the kimi profile
      string on new developer runs; other agents unchanged; removing the
      key env var falls back with a logged warning, run log shows the
      fallback model.
- [ ] A2: a forced FAILED delegation followed by an immediate retry of
      the same task is refused with the REFUSED string; the Supervisor
      reports and asks instead of retrying; a retry after new user
      wording passes the guard.
- [ ] A3: "make the upper-left updates dismissible" — the developer
      finds `AmbientStrip.tsx` without exhausting iterations on search
      (map present in its system prompt), and routes the edit correctly.
- [ ] B0: both spike verdicts recorded here with PASS/FAIL + fallback
      taken.
- [ ] B: three native windows on the right screens per B3's table; both
      voice popout commands work in-shell; `⧉` in a plain browser still
      works; drawer/display single-place rules hold in both modes;
      `macos/**` refused by a test self-edit.
- [ ] Full pytest + web build/lint clean after every step above.

---

## §5 Risks

| Risk | Level | Mitigation |
|---|---|---|
| kimi-k3 also underperforms as developer brain | Medium | One YAML line to reassign; run-log `model` column gives per-model evidence; E1 council remains the failure backstop |
| Retry guard blocks a legitimate retry | Low | Dual gate (120s AND 0.5 overlap); success clears; user rewording passes; constants in one place |
| Repo map goes stale and misleads | Medium | Injected header says verify-before-write; maintenance rule in CLAUDE.md; map is self-edit-editable so Mortimer can fix it |
| WKWebView mic fails (B0-1) | Medium | Predecided partial-adoption fallback keeps console in browser; multi-screen goal still met |
| BroadcastChannel doesn't span webviews (B0-2) | Medium | Predecided shim relay; pages unchanged |
| Shell drifts into an app platform | Low | B6 scope guard: three windows and placement, nothing else in v1 |

---

## §6 Rollback

A1/A3: remove the YAML fields — construction falls back to today's
behavior; `docs/REPO_MAP.md` inert when unreferenced. A2: delete the
guard block + prompt rule. B: the shell is additive — deleting
`macos/` and the two web-side branches restores the browser-only
console; `web/src` never depends on the shell's presence (every branch
is feature-detected). No migrations, no data.

---

## §7 Approval

- [ ] Larry approves.
- [ ] Implementation may begin.
