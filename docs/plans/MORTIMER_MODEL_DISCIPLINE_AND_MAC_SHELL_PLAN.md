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

**Extended scope (Larry, 2026-08-17, second decision round):** three
capability gaps between "what a Cowork session can do" and "what
Mortimer can do from its own interface" are folded in as Parts C and D —
(C1) Mortimer cannot read its own run logs, so diagnosis has no agent
pathway; (C2) the self-edit validation gate does not run the test suite,
so a self-edit's quality bar is below a human session's; (D) building
separate applications still runs through the primitive per-file voice
pathway — the project's founding goal has no equivalent of the
UpgradeAgent loop.

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

## Part C — Investigator + test gate (C1–C2)

### C1 — `mcp_runlog`: read-only run-log access for agents

New MCP server `mcp_servers/mcp_runlog/` (`logic.py` + `server.py` +
`skill.yaml`, the standard convention — logic pure, DB connection
injected), READ-ONLY by construction: no tool writes anything. Backed by
the same `jarvis/runlog/store.py` read helpers the CLI, sidecar, and
Runs panel already share — a fourth consumer must not grow its own
query layer. Four tools:

- `runlog_list(agent="", status="", since="", task_contains="",
  limit=20)` — filters matching the CLI's; `limit` capped at 50; rows
  return run_id, started_at, agent, status, latency_ms,
  tools_ok/tools_failed, model, and the task preview.
- `runlog_detail(run_id)` — the run row plus its events with the
  bounded previews already stored (never the raw JSONL payload; the
  detail includes the payload file's path as a string for human
  follow-up).
- `runlog_stats(since="7d")` — per-agent, per-status counts and
  per-model success rates: the "is the tier table working" evidence
  query, precomputed so a small model can't misaggregate it.
- `council_list(limit=10)` — round_id, workflow, placement, status,
  goal preview, winner profile.

Registered in `config/mcp_servers.yaml`; granted to the `developer`
agent in `config/agents.yaml` (tool descriptions start with "Run log
(read-only):" per the D13/D14 selection-happens-off-schema-text rule).
`tests/integration/test_registry.py`'s `TOTAL_TOOLS` becomes 52
(+4). Every tool description states timestamps are UTC. Non-goal
(explicit): no `runlog_export`/document-dump tool in v1 — deep
"have Fable diagnose twenty runs" analysis waits until a real need
defines its shape; the developer summarizing `runlog_list`/`detail`
output covers the observed use case ("review the recent logs and find
why this failed").

### C2 — pytest joins the self-edit validation gate

`jarvis/selfedit/service.py`'s validation sequence gains one check
after the existing three (allowlist → backend import → frontend build):
`pytest tests/unit -q`, run as a subprocess from the repo root with the
same interpreter/venv the import-smoke check uses, timeout
`VALIDATE_PYTEST_TIMEOUT_S = 300.0` (suite currently ~20s; headroom is
for cold caches, and a hang must not wedge the sidecar). Output handling
matches the existing checks: pass/fail plus a bounded output tail in
the check result. `tests/integration` stays OUT of the gate
(deliberate: slower, and `test_mcp_web_server`-style
environment-sensitive tests must not block an edit). A failed suite
fails validation, which feeds the existing repair attempt and E1
council escalation unchanged — the quality loop comes free.

CI (`.github/workflows/validate.yml`): the `pytest tests/unit` step
flips from non-blocking to BLOCKING in the same change — self-edits are
now held to that bar locally, so CI holding humans to less would be
backwards.

---

## Part D — App-build engine (D1–D8)

The founding goal: build entire separate applications by voice. Today
`mcp_apps` scaffolds a repo and writes files one at a time through the
5-iteration voice loop — no iteration engine exists for apps. Part D
generalizes the UpgradeAgent loop to foreign repos.

### D1 — `Workspace` seam, then `AppBuildAgent`

`jarvis/agents/upgrade_agent.py`'s edit loop is parameterized by a
small `Workspace` interface — repo root, write-boundary check,
validation command list, branch/PR operations — with two
implementations: `SelfEditWorkspace` (exactly today's behavior: the
Mortimer repo, the allowlist, allowlist→import→build→pytest checks) and
`AppWorkspace` (D2–D4). `UpgradeAgent` + `SelfEditWorkspace` must be
behavior-identical to today — the refactor lands FIRST, alone, with the
full existing self-edit test suite green, before `AppBuildAgent`
exists (same lands-alone rule as the popoutWindow extraction).
`AppBuildAgent` is the same loop bound to an `AppWorkspace`; loop
bounds come from `config/upgrade_agent.yaml` under a new `app_build:`
section (own max iterations/minutes — app builds legitimately run
longer than self-edits; values: `max_iterations: 40`,
`max_minutes: 60`).

### D2 — Workspace on disk

`data/app_workspaces/<app-name>/` — cloned via the existing
`mcp_apps/github.py` authenticated client (the ONLY network-touching
module, unchanged rule). `data/**` is already self-edit-denied and
gitignored; nothing new leaks into Mortimer's repo. Clone on first
build; `git pull --ff-only` on subsequent builds; a dirty workspace or
failed pull refuses the start synchronously (same read-and-refuse
discipline as review_path).

### D3 — Per-app validation manifest

`mortimer.app.yaml` at the app repo's root: `build:` and `test:` —
each a list of shell commands run in the workspace root, in order, all
must exit 0. `app_create`'s scaffold writes a starter manifest from now
on. An app with no manifest validates as "no checks defined" — the
build proceeds but the PR body and the spoken summary both say so
explicitly (an unvalidated PR must never be mistaken for a validated
one). Command execution uses the same subprocess pattern as C2, timeout
per command `APP_CHECK_TIMEOUT_S = 600.0`.

### D4 — Write boundary for foreign repos

Inside the workspace tree only, deny-listed: `.git/**`, `.env`,
`.env.*`, `**/*.vault`, `.github/workflows/**` (an agent must not
grant itself CI powers on the app repo either). Everything else is
writable WITHOUT per-file draft→confirm — confirmation happens at the
two boundaries that matter: the user approves the start (goal + plan +
app name, two-phase like selfedit_start), and the PR is opened only
after validation passes AND the user explicitly confirms submission in
a new turn (same rule as selfedit_submit). Merging stays human, on
GitHub, always.

### D5 — Sidecar job slot + endpoints

`_appbuild_job`/`_appbuild_lock` in `jarvis/admin/server.py`, the same
background-thread-plus-polling shape as `_run_job`/`_plan_job`:
`POST /api/appbuild/start {app, goal, profile?, plan?, plan_path?}`
(plan_path read-and-refuse identical to selfedit's),
`GET /api/appbuild/job`, `POST /api/appbuild/submit`,
`POST /api/appbuild/cancel`. One app build at a time (one slot), and an
app build does not block self-edit jobs (separate slots, separate
locks).

### D6 — Voice tools

`mcp_apps` gains `app_build_start` / `app_build_status` /
`app_build_submit` — thin two-phase HTTP passthroughs, same convention
as `selfedit_*`/`plan_*`. `TOTAL_TOOLS` becomes 55 (+3 on top of C1's
52). The developer prompt's app-development paragraph is extended: an
app implementation of any size goes through `app_build_start` (with
`plan_path` when a plan exists — plans for apps are authored through
the existing planning pathway, which is app-agnostic already);
`app_write_file` remains only for small dictated single-file edits,
the same routing rule Part A's self-edit sentence uses.

### D7 — Model + escalation

Profile resolution: explicit spoken choice → `JARVIS_APPBUILD_PROFILE`
env → registry default (mirrors self-edit's order). Council escalation:
`AppBuildAgent` inherits the E1 trigger through the shared loop
(validation failed twice + repair failed → convene), rounds written
with `workflow="appbuild"` — `compute_agreement` needs no change
(it excludes by workflow only for `"planning"`; appbuild rounds are
judge-quality evidence like self-edit rounds). No kill switch: an app
build only runs when explicitly started and confirmed (same rationale
as DP10).

### D8 — v1 UI: none

Status by voice (`app_build_status`) and `GET /api/appbuild/job` only.
No console panel in v1 — the Edit panel grew organically from real use;
the app-build panel should too. Explicit scope guard.

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

**Part C — new:** `mcp_servers/mcp_runlog/{logic.py,server.py,skill.yaml}`,
`tests/unit/test_mcp_runlog_logic.py`. **Part C — modified:**
`config/mcp_servers.yaml` + `config/agents.yaml` (register + grant);
`jarvis/selfedit/service.py` (C2 check + constant);
`.github/workflows/validate.yml` (pytest blocking);
`tests/integration/test_registry.py` (`TOTAL_TOOLS` 48→52);
`tests/unit/test_selfedit_service.py` (C2 gate tests).

**Part D — new:** `jarvis/agents/workspace.py` (the `Workspace` seam +
both implementations), `jarvis/agents/app_build_agent.py`,
`tests/unit/test_workspace.py`, `tests/unit/test_app_build_agent.py`,
`tests/unit/test_admin_appbuild.py`, `tests/acceptance/app-build.md`.
**Part D — modified:** `jarvis/agents/upgrade_agent.py` (loop
parameterized by Workspace — behavior-identical refactor);
`config/upgrade_agent.yaml` (`app_build:` bounds);
`jarvis/admin/server.py` (D5 slot + endpoints);
`mcp_servers/mcp_apps/{logic.py,server.py,skill.yaml}` (D6 tools +
scaffold manifest); `jarvis/prompts.py` (D6 routing sentence);
`tests/integration/test_registry.py` (`TOTAL_TOOLS` 52→55);
`.env.example` (`JARVIS_APPBUILD_PROFILE`).

---

## §3 Implementation order

1. A1 per-agent profiles + tests (the single highest-leverage change).
2. A3 repo map + injection + tests.
3. A2 stop rule + retry guard + tests.
4. A5 docs + acceptance; full pytest; **restart the bot** (prompt and
   config changes are read at boot — last night's failures ran on
   pre-fix prompts for exactly this reason).
5. C1 `mcp_runlog` server + registration + tests (`TOTAL_TOOLS` 52) —
   the investigator then helps verify everything after it.
6. C2 pytest validation gate + CI flip + tests.
7. B0 spike; record both verdicts in this file.
8. B1–B4 shell windows + placement + web-side branches (order inside:
   B2 shim first, then windows, then placement).
9. B5 boundary + build script; B7 naming sweep; shell acceptance;
   web tsc/lint; full pytest.
10. D1 Workspace seam refactor — lands ALONE, full existing self-edit
    suite green, before any AppBuildAgent code.
11. D2–D4 AppWorkspace (clone/pull, manifest, boundary) + tests.
12. D5–D7 sidecar slot, mcp_apps tools (`TOTAL_TOOLS` 55), prompts,
    profile env + tests.
13. App-build acceptance: one real small app built end-to-end by voice
    (scaffold → plan via planning pathway → app_build_start with
    plan_path → validate → confirm → PR).

Ordering rationale, locked: A and C are small and compounding — they
harden the delegation layer everything later is driven through. B before
D because the shell changes the daily surface everything is operated
from, and D (the largest part) then gets built and verified through the
hardened A+C machinery — Part D's own acceptance test doubles as the
system's first real autonomous-build exercise.

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
- [ ] C1: "review the recent developer runs and tell me why the last
      one failed" → developer answers from `runlog_list`/`runlog_detail`
      with real run data, no fabrication; `runlog_stats` shows per-model
      success rates.
- [ ] C2: a self-edit that breaks a unit test FAILS validation with the
      test output in the check result; repair/escalation proceed; CI
      pytest step is blocking.
- [ ] D refactor: full self-edit test suite green with UpgradeAgent on
      SelfEditWorkspace, zero behavior change, BEFORE AppBuildAgent
      lands.
- [ ] D end-to-end: one small real app — scaffold, plan, build from
      plan_path, manifest checks pass, user-confirmed PR on the app
      repo; a manifest-less app's PR and spoken summary both flag "no
      checks defined"; deny-listed paths (`.git`, workflows) refused.
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
| Flaky unit test blocks all self-edits (C2) | Low | Suite is network-free/deterministic today; a flake is fixed or skipped as its own bug, not by weakening the gate |
| Workspace-seam refactor regresses self-edit (D1) | High | Lands alone with the full existing suite green before any new code; behavior-identical is the acceptance bar |
| App build damages a foreign repo | Medium | Work confined to `data/app_workspaces/`; PR-only delivery (never direct push to main); deny list on `.git`/workflows/secrets; human merges |
| 40-iteration app builds run up cost | Medium | Explicit start confirmation names the profile; bounds in `config/upgrade_agent.yaml`; run log records model + tokens |

---

## §6 Rollback

A1/A3: remove the YAML fields — construction falls back to today's
behavior; `docs/REPO_MAP.md` inert when unreferenced. A2: delete the
guard block + prompt rule. B: the shell is additive — deleting
`macos/` and the two web-side branches restores the browser-only
console; `web/src` never depends on the shell's presence (every branch
is feature-detected). C1: unregister the server (tool count reverts).
C2: remove the check + revert the CI flip. D: `AppBuildAgent`, the
sidecar slot, and the mcp_apps tools are additive and revert
file-by-file; the D1 refactor is NOT rolled back once landed (it is
behavior-identical by its own acceptance bar — rolling it back buys
nothing); `data/app_workspaces/` is disposable. No migrations, no
data-shape changes anywhere in this plan.

---

## §7 Approval

- [ ] Larry approves.
- [ ] Implementation may begin.
