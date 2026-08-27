# Mortimer Web Retirement Plan (T1.4)

**Status:** DRAFT for Larry's approval, 2026-08-26. Implements roadmap track **T1.4** (`docs/plans/MORTIMER_PLATFORM_ROADMAP.md` §2.1: *"T1.4 Deletion: `web/` and `macos/MortimerShell/` removed once T1.3 has passed gate G1 and run as daily driver for the period G1 names."*).

**Author / origin:** Roadmap §2.1 T1.4 and §4 G1(e); `CROSS_PLAN_RESOLUTION.md` §C **F12** (*"`web/`'s retirement (T1.3/T1.4) is unowned though three plans discharge obligations onto T1.4… T1.4 is where CORS removal and the parity test land"*). This plan is the third of the three native-track plans named in F12: `MORTIMER_NATIVE_CLIENT_CORE_PLAN.md` (T1.1/T1.2, written), `MORTIMER_NATIVE_CLIENT_APP_PLAN.md` (T1.3, written in parallel), and this one (T1.4).

**Roadmap constraints this plan is bound by:**
- **C1** (backend contract unchanged for the client migration) — honoured: this plan removes only code that existed *for the web client* (CORS allow-list to `:5173`, the `npm run build` self-edit gate, the web launcher). It adds no client-specific endpoint and changes no RTVI app-message or sidecar JSON contract. The bot (`jarvis/bot/`) is not touched at all.
- **C2** (localhost is the trust boundary until T2) — honoured trivially; this plan opens no port. Removing the sidecar `CORSMiddleware` *narrows* browser surface (no origin is allowed), it does not widen it.
- **C7** (routing eval ≥ 90 %) — honoured: no agent, Supervisor model, or Supervisor prompt changes. §8 re-runs the eval anyway (roadmap G1(d) discipline) and records the score.
- **C8** (self-edit allow/deny changes are human commits) — honoured: this plan makes **no** edit to `config/self_edit_allowlist.json` (decision **W8**), and the whole deletion is a single Larry hand-commit (it touches deny-listed files `jarvis/admin/**`, `jarvis/selfedit/**`, `macos/**`).
- **C10** (degradation-proof) — honoured: every removal is specified by text-anchored edit, every "X references web/" claim is grep-verified in §1, and §0 is a hard stop with three mechanical gates.

**Contracts this plan INTRODUCES (consumed by later plans):** none. This is a terminal deletion plan.

**Contracts this plan CONSUMES (by doc + section):**
- `MORTIMER_REMOTE_ACCESS_PLAN.md` **R-A2 / §5 Step 4 / A6-A7 / §5 "Nothing is deleted"** — REMOTE explicitly *defers* deletion of the sidecar `CORSMiddleware` to this plan and builds its `BearerAuthMiddleware` `OPTIONS` pass-through branch (A6, F16) so that *"removing `CORSMiddleware` at T1.4 cannot silently break preflight."* This plan discharges that deferral (decision **W3**).
- `MORTIMER_REMOTE_ACCESS_PLAN.md` **A12 / §5 Step 8** — the console's `localStorage['jarvis_token']` at-rest bearer token (XSS-readable in a browser). `CROSS_PLAN_RESOLUTION.md` §C F12 calls this **R9**; it disappears the moment `web/` is deleted (decision **W2**, risk table §10).
- `MORTIMER_MAIL_CALENDAR_BRIEF_PLAN.md` — MAIL's obligation to keep `web/src/agentLayout.ts` and `tests/unit/test_agents_yaml_frontend_parity.py` in sync when the sixth agent lands becomes moot once `web/` is gone; F12 assigns their retirement here (decision **W7**).
- `MORTIMER_NATIVE_CLIENT_APP_PLAN.md` (T1.3) and `MORTIMER_NATIVE_CLIENT_CORE_PLAN.md` (T1.1/T1.2) — the native replacement whose landing + daily-driver period is this plan's precondition (§0).

**Corrections to the roadmap:** none. (One clarification, not a correction: roadmap §7 O7 leaves the daily-driver window open — *"5 daily-driver days (G1e) or longer?"* — while §4 G1(e) states the concrete number, *"5 consecutive days."* This plan uses the G1(e) number, 5, as the binding value and flags O7 in §12 for Larry to raise if he wants longer. It does not invent a different number.)

---

## §0 Binding constraints for the implementing model

**This plan is a large, irreversible-feeling deletion. It MUST NOT run before the native app is proven. The following is a hard stop.**

**B0.1 — Three mechanical precondition gates. Run all three FIRST. If any fails, STOP and report; delete nothing.**

1. **The T1.2 core package exists.**
   `test -d macos/JarvisKit` (created by `MORTIMER_NATIVE_CLIENT_CORE_PLAN.md`). If absent → STOP: *"JarvisKit not present; native core (T1.2) has not landed."*
2. **The T1.3 macOS app exists.**
   `test -d macos/MortimerHost` (the native app target created by `MORTIMER_NATIVE_CLIENT_APP_PLAN.md`; the roadmap §5 W4/F16 note names `macos/MortimerHost` as the app rebuilt by T6). If absent → STOP: *"MortimerHost not present; native app (T1.3) has not landed."*
3. **The T1.3 plan has been marked implemented.**
   `test -f docs/plans/implemented/MORTIMER_NATIVE_CLIENT_APP_PLAN.md`. If absent → STOP: *"T1.3 plan is not in docs/plans/implemented/; gate G1 has not been signed off."*

   Rationale: moving a plan into `docs/plans/implemented/` is the repo's existing "this shipped" marker (see the many files already there, e.g. `MORTIMER_SIDE_DRAWER_PLAN.md`). Larry performs this move only after G1(a)–(e) pass.

**B0.2 — G1(e) is a human attestation the implementer cannot compute.** Gate G1(e) is *"Native app used as daily driver for 5 consecutive days with no fallback to the web console"* (roadmap §4). No file or command proves five days of human usage. The gate is therefore **Larry's**, expressed by the two markers B0.1.2 and B0.1.3 (the app exists AND its plan is in `implemented/`), plus his explicit sign-off recorded in the branch's PR description. The implementer treats B0.1's three checks as the operational proxy and does not attempt to verify the five days itself.

**B0.3 — Text-anchored edits only, never line numbers.** By the time this plan runs, `MORTIMER_REMOTE_ACCESS_PLAN.md` (W1) has already edited `jarvis/admin/server.py` (added `BearerAuthMiddleware`, added `Authorization` to `allow_headers`, reordered middleware so CORS is outermost). Every edit site in §5 is located by the exact quoted code string given there. If a quoted string is not found verbatim, STOP and report — do not guess a replacement.

**B0.4 — This is one commit, and it is Larry's.** The deletion touches deny-listed paths (`jarvis/admin/**`, `jarvis/selfedit/**`, `macos/**` — see `config/self_edit_allowlist.json`), so it can never be a self-edit branch. The implementer prepares the working tree; **Larry commits** on branch `t1.4-web-retirement`. The plan does not run `git`.

**B0.5 — Do not touch `config/self_edit_allowlist.json`.** Its `macos/**` deny entry is still LIVE — `macos/JarvisKit` and `macos/MortimerHost` exist and must stay assistant-unwritable. Its `web/**` allow/deny entries become dead but are inert (nothing self-edits a deleted path). Allow-list edits are owned and sequenced by `docs/plans/ALLOWLIST_SEQUENCE.md` (`CROSS_PLAN_RESOLUTION.md` §A); this plan stays out of that file (decision **W8**).

---

## §1 What exists today (verified, path:line) and the gap

Everything below was grep-verified in the snapshot at `/home/claude/repo` on 2026-08-26.

**The two deletable trees**

| Tree | Fact | Verified |
|---|---|---|
| `web/` | Vite React-TS console. **52 files under `web/src/`**, 67 files total excluding `node_modules/` and the three `dist_*` build outputs. `package.json`, `vite.config.ts`, `index.html`/`drawer.html`/`display.html` entrypoints. | `find web/src -type f` = 52; `find web -type f -not -path '*/node_modules/*' -not -path '*/dist_*/*'` = 67 |
| `macos/MortimerShell/` | Old WKWebView shell, SPM executable. **11 `.swift` files** under `Sources/MortimerShell/` + `Package.swift`, plus a stub `.xcodeproj`, `Assets.xcassets`, `templates/`, `README.md`. `ShellWebView.swift` loads `http://127.0.0.1:5173`. Superseded by `macos/MortimerHost` (T1.3). | `find macos/MortimerShell -name '*.swift'` = 11; `macos/MortimerShell/README.md:27`, `.../mac-shell.md:17` (loads `:5173`) |

**Every backend / tooling reference to them (grep-verified — this is the complete set)**

| # | Reference | Location | What it is | Removal |
|---|---|---|---|---|
| R1 | Sidecar CORS allow-list to `:5173` | `jarvis/admin/server.py:65` (import) and the `app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173","http://127.0.0.1:5173"], …)` block (`:107`–`:112` today; REMOTE W1 adds `Authorization` to `allow_headers` and moves it) | The ONLY reason the sidecar has CORS at all is the browser console. | **W3** — remove the middleware + import. |
| R2 | `mortimer.sh` launches web | `scripts/mortimer.sh:26` `WEB_PORT=5173`; `:39` `pkill -f "vite"`; the `nohup ./scripts/run_web.sh …` line; `rotate_log web`; `:103` `check web …`; `:106` `echo "Open http://localhost:$WEB_PORT…"` | One-command stack starter runs bot+admin+**web**. | **W4** — stop starting/stopping/logging/echoing web. |
| R3 | `run_web.sh` | `scripts/run_web.sh` (whole file) | Starts `npm run dev` on `:5173`. | **W2** — delete. |
| R4 | `build_shell.sh` | `scripts/build_shell.sh` (whole file) | Builds `macos/MortimerShell` via `swift build`. | **W2** — delete. |
| R5 | Self-edit `frontend_build` gate | `jarvis/selfedit/service.py:65` `VISUAL_PATH_PREFIXES`, `:391` `validate()`, `:417`–`:422` the `npm ci` + `npm run build` check in `web_dir`, `:36` `BUILD_TIMEOUT_S=600` | Validation gate 3 runs `npm ci && npm run build` in `web/`. With `web/` gone, `npm ci` fails in a missing dir → self-edit validation would **always fail**. | **W5** — remove the gate + now-unused `BUILD_TIMEOUT_S`; leave `is_visual_path`/`VISUAL_PATH_PREFIXES` dormant (documented). |
| R6 | CI frontend build | `.github/workflows/validate.yml:44`–`:49` and its mirror `scripts/validate.yml:47`–`:52` (`setup-node` + `cd web; npm ci; npm run build`) | CI Gate 5 compiles the frontend. | **W6** — remove Gate 5 from both files. |
| R7 | Frontend-parity unit test | `tests/unit/test_agents_yaml_frontend_parity.py` (whole file) — regexes `web/src/agentLayout.ts` against `config/agents.yaml` | Guards `agentLayout.ts` against the agent roster drifting. Subject file is being deleted. | **W7** — delete the test. |
| R8 | `session_validate` tool blurb | `jarvis/agents/upgrade_agent.py:145` `"…imports, frontend build)."` | Cosmetic: describes the validation gate to the upgrade agent. | **W9** — drop the `, frontend build` clause. |
| R9 | Self-development prompt example | `jarvis/prompts.py:296` — example path `web/src/components/ClockPanel.tsx` | Cosmetic: illustrates naming files in a self-edit goal. | **W9** — replace with a still-live example path. |
| R10 | CLAUDE.md run/test docs | `CLAUDE.md:21`,`:26`,`:57`–`:61`,`:69`,`:74`,`:102`… (the `run_web.sh`, `cd web && npm …`, "bot + admin + web", CI Gate list) | Developer docs. | **W9** — prune web lines. |
| R11 | README docs | `README.md:38` (arch diagram),`:102`–`:105`,`:270`,`:272`,`:285`,`:325`,`:345`,`:349`,`:356` | User-facing setup/troubleshooting. | **W9** — prune web lines. |
| R12 | Acceptance checklists | `tests/acceptance/phase-6.md` (web console phase), `tests/acceptance/mac-shell.md` (WKWebView shell) | Manual per-phase checklists for the deleted UIs. | **W2** — delete both. |

**Things that look like references but are NOT (verified — do NOT touch):**
- `jarvis/bot/bot.py:4` `"Then open http://localhost:7860/client…"` — the Pipecat **runner's own** built-in client on the *bot* port `:7860`, not `web/`. Out of scope (C1: bot untouched).
- Bot-side CORS: `pipecat/runner/run.py` defaults `allow_origins=["*"]` (REMOTE R-A2). Not our code; nothing to delete.
- `config/self_edit_allowlist.json` `web/**` and `macos/**` entries — see W8/B0.5.
- `tests/unit/test_selfedit_service.py`, `tests/unit/test_selfedit_allowlist.py` — reference `web/src/App.tsx` etc. as **synthetic string fixtures inside `tmp_path`**, never the real tree; they pass unchanged after deletion (verified: they build their own temp `web/src`). No edit (see §7).
- `docs/plans/**` (roadmap, other plans, `implemented/*`) mentioning `5173`/`web` — historical record; not edited here (the roadmap is SEC-owned per `CROSS_PLAN_RESOLUTION.md` §C F14).

**The gap:** T1.3 has shipped the native app and (per §0) it has been the daily driver for G1(e)'s five days. The web console and old shell are now dead weight carrying live cost: a CORS surface on the sidecar, a `npm` build gate on every self-edit and every CI run, and a launcher that starts a Vite process nobody uses.

---

## §2 Non-goals

- **N1 — No backend behaviour change (C1).** The bot pipeline, RTVI app-messages, and sidecar JSON routes are untouched except for removing the now-clientless CORS middleware.
- **N2 — Not `jarvis/config.py`'s `jarvis_webrtc_endpoint`.** REMOTE R-A4 already established it is dead configuration unrelated to the console; leave it.
- **N3 — Not the `BearerAuthMiddleware` `OPTIONS` pass-through branch** REMOTE added (A6/F16). It becomes permanently unreachable once no browser exists, but it is inert defence in a deny-listed file; removing it is out of scope (§10 RM-2).
- **N4 — Not `config/self_edit_allowlist.json`** (W8/B0.5).
- **N5 — Not `docs/plans/**`** history, and not the roadmap (SEC-owned, F14).
- **N6 — No new native code.** That is T1.3's plan, not this one.
- **N7 — Not `macos/JarvisKit` or `macos/MortimerHost`.** Only `macos/MortimerShell/` goes.

---

## §3 Decisions — lettered (W-prefix), each with a *why*

- **W1 — Run only behind the §0 hard stop (T1.2+T1.3 present, T1.3 plan in `implemented/`).** *Why:* the roadmap makes G1(e) the sole precondition for T1.4 (§4: *"Only after (e) does T1.4 delete `web/`."*). A deletion that outran the native app would leave Larry with no working UI. The three mechanical checks are the closest deterministic proxy for a five-day human attestation the implementer cannot compute (B0.2).

- **W2 — Delete `web/` whole, `macos/MortimerShell/` whole, `scripts/run_web.sh`, `scripts/build_shell.sh`, `tests/acceptance/phase-6.md`, `tests/acceptance/mac-shell.md`, and `tests/unit/test_agents_yaml_frontend_parity.py`.** *Why:* these are the artefacts whose entire reason to exist is the retired web UI / old shell. The roadmap names `web/` and `macos/MortimerShell/` explicitly; the two scripts and two acceptance docs are their launch/verify surface; the parity test's subject is inside `web/`.

- **W3 — Remove the sidecar `CORSMiddleware` (and its import).** *Why:* REMOTE deferred exactly this to T1.4 (R-A2: *"deletes it when `web/` is deleted at T1.4 — not here"*) and pre-built its `OPTIONS` branch so removal cannot break preflight. With no browser origin left, CORS allows nothing useful and only widens attack surface if ever misconfigured. Discharges F12's *"T1.4 is where CORS removal … land[s]."*

- **W4 — `mortimer.sh` stops starting, stopping, rotating, health-checking, and advertising web.** *Why:* F12 / roadmap — the one-command stack must no longer launch a Vite process. Bot + admin remain; the native app is launched by Larry from Xcode/Finder, outside this script (it is a GUI app, not a `nohup` background service).

- **W5 — Remove the `frontend_build` validation gate (and now-unused `BUILD_TIMEOUT_S`); leave `is_visual_path`/`VISUAL_PATH_PREFIXES` in place but dormant.** *Why:* the gate runs `npm ci` in `web/`; after deletion that directory is gone and the gate would fail every self-edit validation (a correctness break, not cosmetics). The visual-path helpers are pure string predicates that now match nothing (no `web/src/` path can exist), so they are harmless; ripping them out would churn a deny-listed security file and delete scaffolding a future *native* visual-verify step could repopulate. Minimal, reversible.

- **W6 — Remove CI Gate 5 (frontend build) from both `.github/workflows/validate.yml` and `scripts/validate.yml`.** *Why:* the gate compiles a deleted app; left in, CI fails on `cd web`. Removing it drops the `setup-node` step too (nothing else uses Node).

- **W7 — Delete the frontend-parity test rather than repurpose it.** *Why:* F12 offers "deleted or repurposed"; the test's whole mechanism is a regex over `web/src/agentLayout.ts`, which no longer exists. A native equivalent (assert every `config/agents.yaml` agent appears in the SwiftUI layout) belongs to the T1.3 plan against its own Swift source, not here — inventing one here would test code this plan does not own. So: delete. MAIL's obligation to edit `agentLayout.ts` + this test when the sixth agent lands is thereby retired (its subject and its guard both gone).

- **W8 — Do not edit `config/self_edit_allowlist.json`.** *Why:* B0.5 — `macos/**` deny is still live for JarvisKit/MortimerHost; the `web/**` entries are inert once the paths vanish; and the file is C8/`ALLOWLIST_SEQUENCE.md`-owned. Touching it risks colliding with the four sequenced rows other plans append. Dead allow entries pointing at absent paths never match anything (`check_allowlist.py` only ever tests paths that appear in a diff).

- **W9 — Prune stale docs/prompt/tool text.** *Why:* `CLAUDE.md`, `README.md`, `jarvis/prompts.py:296`, and `jarvis/agents/upgrade_agent.py:145` describe a web run/build flow that no longer exists; leaving them misleads the next reader (human or model). These are small, mechanical text edits in the same commit.

- **W10 — Land as ONE revertable commit; rely on git history for restore.** *Why:* this is a large deletion with no runtime kill switch to flip. The safe rollback for a deletion is `git revert` of a single commit (§9); bundling every removal into one commit makes that one command sufficient, and `web/` + `macos/MortimerShell/` remain fully recoverable from history.

---

## §4 Files (create / modify / delete — complete manifest)

Every file touched in §5 appears here. No file is created.

**DELETE (whole path):**
| Path | Note |
|---|---|
| `web/` | entire tree (52 `src` files, 67 total incl. entrypoints, config, `public/`, `dist_*`, `README.md`) |
| `macos/MortimerShell/` | entire tree (11 `.swift`, `Package.swift`, stub `.xcodeproj`, `Assets.xcassets`, `templates/`, `README.md`, `.DS_Store` if present) |
| `scripts/run_web.sh` | R3 |
| `scripts/build_shell.sh` | R4 |
| `tests/acceptance/phase-6.md` | R12 |
| `tests/acceptance/mac-shell.md` | R12 |
| `tests/unit/test_agents_yaml_frontend_parity.py` | R7 / W7 |

**MODIFY:**
| Path | Change | Ref |
|---|---|---|
| `jarvis/admin/server.py` | remove `CORSMiddleware` import and the `app.add_middleware(CORSMiddleware, …)` call | W3 / R1 |
| `scripts/mortimer.sh` | remove all web start/stop/rotate/check/echo | W4 / R2 |
| `jarvis/selfedit/service.py` | remove the `frontend_build` check block and `BUILD_TIMEOUT_S`; add a one-line comment where the gate was | W5 / R5 |
| `.github/workflows/validate.yml` | remove Gate 5 (frontend build) + its `setup-node` step | W6 / R6 |
| `scripts/validate.yml` | same removal (mirror copy) | W6 / R6 |
| `jarvis/agents/upgrade_agent.py` | drop `, frontend build` from the `session_validate` description | W9 / R8 |
| `jarvis/prompts.py` | replace the `web/src/components/ClockPanel.tsx` example with a live path | W9 / R9 |
| `CLAUDE.md` | prune web run/build/CI lines | W9 / R10 |
| `README.md` | prune web setup/troubleshooting/diagram lines | W9 / R11 |

**NOT touched (called out to prevent drift):** `config/self_edit_allowlist.json` (W8), `jarvis/config.py` (N2), `jarvis/bot/**` (C1/N1), `tests/unit/test_selfedit_service.py`, `tests/unit/test_selfedit_allowlist.py` (§1, §7), the roadmap and other `docs/plans/**` (N5).

---

## §5 Implementation steps, in order, each with: files, exact change, test that proves it

> Run **§0 B0.1's three gates first.** If any fails, STOP. Do nothing below.

### Step 1 — Delete the two trees and their satellites (W2)
**Files:** the seven DELETE rows in §4.
**Change:** remove each path recursively:
```
rm -rf web
rm -rf macos/MortimerShell
rm -f  scripts/run_web.sh scripts/build_shell.sh
rm -f  tests/acceptance/phase-6.md tests/acceptance/mac-shell.md
rm -f  tests/unit/test_agents_yaml_frontend_parity.py
```
**Test that proves it:** `test ! -e web && test ! -e macos/MortimerShell && test -d macos/JarvisKit && test -d macos/MortimerHost` exits 0 (the two deletions gone, the two native trees intact). `pytest tests/unit -q` collects with **no** `test_agents_yaml_frontend_parity` and no collection error.

### Step 2 — Remove the sidecar CORS middleware (W3 / R1)
**File:** `jarvis/admin/server.py`.
**Change A — remove the import.** Delete the line whose exact text is:
```python
from fastapi.middleware.cors import CORSMiddleware
```
**Change B — remove the middleware registration.** Delete the entire `app.add_middleware(CORSMiddleware, …)` call. Locate it by the anchor string `CORSMiddleware,` inside an `app.add_middleware(` call and remove from `app.add_middleware(` through its closing `)`. In today's tree that block is:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
```
After REMOTE (W1) lands, `allow_headers` will additionally contain `"Authorization"` and the block may sit at a different line and in a different order relative to `BearerAuthMiddleware`. **Remove only the `CORSMiddleware` `add_middleware` call.** Do NOT remove the `BearerAuthMiddleware` registration, and do NOT remove its `OPTIONS` pass-through branch (N3).
**If the anchor `CORSMiddleware,` is not found:** REMOTE may have already renamed or removed it — STOP and report; do not invent an edit.
**Test that proves it:** `python -c "import jarvis.admin.server"` succeeds (no `NameError` for `CORSMiddleware`). `grep -rn "CORSMiddleware\|5173" jarvis/` returns nothing. The REMOTE auth tests (`tests/unit/test_authmw.py` or equivalent) still pass — an unauthenticated `/api/*` call is still 401 (auth is REMOTE's `BearerAuthMiddleware`, unaffected by CORS removal).

### Step 3 — Stop `mortimer.sh` launching web (W4 / R2)
**File:** `scripts/mortimer.sh`.
**Changes (each located by its exact current text):**
1. Delete the line `WEB_PORT=5173`.
2. In `stop_all()`, delete the line `  pkill -f "vite"                  2>/dev/null`.
3. Delete the `nohup ./scripts/run_web.sh   >> logs/web.log   2>&1 &` line and the following `WEB_PID=$!` line.
4. Delete the `rotate_log web` line.
5. Delete the health-check line `check web   "$WEB_PID" "http://localhost:$WEB_PORT"`.
6. In the `logs)` case, change `exec tail -f logs/bot.log logs/admin.log logs/web.log` to `exec tail -f logs/bot.log logs/admin.log` (drop `logs/web.log`).
7. Replace the two trailing echo lines
   ```
   echo
   echo "Open http://localhost:$WEB_PORT and click Connect."
   ```
   with
   ```
   echo
   echo "Bot + admin running. Launch the Mortimer app (macos/MortimerHost) to connect."
   ```
   Update the usage comment at the top of the file: change the two occurrences of `bot + admin + web` / `bot+admin+web` to `bot + admin`.
**Test that proves it:** `bash -n scripts/mortimer.sh` (syntax OK). `grep -c "5173\|vite\|run_web\|WEB_PID\|WEB_PORT\|web.log" scripts/mortimer.sh` returns `0`. Manual (§8): `./scripts/mortimer.sh` starts exactly two processes; `./scripts/mortimer.sh logs` tails two files; no `logs/web.log` is created.

### Step 4 — Remove the self-edit `frontend_build` gate (W5 / R5)
**File:** `jarvis/selfedit/service.py`.
**Change A — delete the gate block.** Locate by the anchor comment `# 3. Frontend build.` and remove from that comment through the `checks.append({"name": "frontend_build", …})` call inclusive. Today that is:
```python
        # 3. Frontend build.
        web_dir = self.repo_root / "web"
        code, out = self._run(["npm", "ci"], cwd=web_dir, timeout=BUILD_TIMEOUT_S)
        if code == 0:
            code, out = self._run(["npm", "run", "build"], cwd=web_dir,
                                  timeout=BUILD_TIMEOUT_S)
        checks.append({"name": "frontend_build", "ok": code == 0,
                       "output": out[-2000:] or "build ok"})
```
Replace the whole block with a single comment so the gate numbering reads honestly:
```python
        # (Former gate 3 "frontend build" removed at T1.4 with web/ —
        #  MORTIMER_WEB_RETIREMENT_PLAN.md W5. Validation is now
        #  allowlist -> backend imports -> pytest.)
```
**Change B — remove the now-unused constant.** Delete the line `BUILD_TIMEOUT_S = 600` (grep first: `grep -n BUILD_TIMEOUT_S jarvis/selfedit/service.py` must show only the definition once Change A lands; if any other use remains, keep the constant and report).
**Change C — leave `VISUAL_PATH_PREFIXES`, `is_visual_path`, and `_visual_change_block` in place** (W5 rationale). No edit.
**Test that proves it:** `python -c "import jarvis.selfedit.service"` succeeds. `grep -n "npm\|frontend_build\|BUILD_TIMEOUT_S" jarvis/selfedit/service.py` returns nothing. `pytest tests/unit/test_selfedit_service.py -q` passes (these tests use synthetic `tmp_path/web/src` fixtures and mock `_run`; none asserts a `frontend_build` check — verified: `grep -rn frontend_build tests/` is empty).

### Step 5 — Remove CI Gate 5 (W6 / R6)
**Files:** `.github/workflows/validate.yml` AND `scripts/validate.yml` (identical mirror).
**Change (in each file):** delete the frontend section — the `# Gate 5: frontend still compiles.` comment, the `- uses: actions/setup-node@v4` step with its `with: node-version: "20"`, and the `- name: Frontend build` step with its `run: | / cd web / npm ci / npm run build` body. Nothing else references Node, so `setup-node` goes too.
**Test that proves it:** `grep -rn "web\|npm\|node\|vite\|5173" .github/workflows/validate.yml scripts/validate.yml` returns nothing. Both files still parse as YAML (`python -c "import yaml,sys; [yaml.safe_load(open(p)) for p in ('.github/workflows/validate.yml','scripts/validate.yml')]"`).

### Step 6 — Prune stale prompt / tool / docs text (W9 / R8–R11)
**File `jarvis/agents/upgrade_agent.py`:** in the `session_validate` description, change `"Run the validation gate (allowlist, backend imports, frontend build)."` to `"Run the validation gate (allowlist, backend imports, tests)."` (anchor: `frontend build).`).
**File `jarvis/prompts.py`:** in the `self_development` prompt, replace the parenthetical example `(e.g. "add a clock panel: web/src/components/ClockPanel.tsx and its wiring in App.tsx")` with a live-path example `(e.g. "add a settings knob: jarvis/config.py and its reader in jarvis/bot/pipeline.py")`. Anchor: `web/src/components/ClockPanel.tsx`.
**File `CLAUDE.md`:** remove the web-specific lines — the `./scripts/run_web.sh …` command line; the `# Web client` block (`cd web && npm run build|lint|dev`); the `./scripts/mortimer.sh` comment's `bot + admin + web` → `bot + admin`; the CI description's trailing `→ web/npm run build` in the Gate list; the architecture diagram line `Browser (React/Vite) --WebRTC--> …` → `Native app (JarvisKit) --WebRTC--> Python bot (Pipecat pipeline) --MCP/stdio--> MCP skill servers`.
**File `README.md`:** remove the web setup step ("Start the web console" / `run_web.sh`), the `cd web && npm run build` reference, the `web/` line in the repo tree, the `run_web.sh` tree line, and the `:5173` rows in the troubleshooting table; in the arch diagram/prose replace "Vite React-TS console" phrasing with the native app; keep everything about bot/admin/wakeword.
**Test that proves it:** `grep -rn "5173\|run_web\|MortimerShell\|build_shell\|cd web\|npm run" CLAUDE.md README.md jarvis/prompts.py jarvis/agents/upgrade_agent.py` returns nothing. `python -c "import jarvis.prompts, jarvis.agents.upgrade_agent"` succeeds.

### Step 7 — Full repo grep sweep (proves completeness)
**Change:** none — verification gate before commit.
```
grep -rn "web/src\|web/dist\|run_web\|build_shell\|MortimerShell\|:5173\|localhost:5173\|127.0.0.1:5173\|CORSMiddleware\|npm run build\|npm ci" \
  --include="*.py" --include="*.sh" --include="*.yml" --include="*.yaml" \
  --include="*.json" --include="*.md" . \
  | grep -v "^./docs/plans/"
```
**Expected:** empty **except** `config/self_edit_allowlist.json` (its inert `web/**` allow/deny entries, deliberately left — W8) and possibly `jarvis/config.py`'s `jarvis_webrtc_endpoint` if it matches (it does not contain `5173`; N2). Any *other* hit is an unremoved reference — investigate: if it is a code/script/CI path, remove it following the nearest matching decision; if it is under `docs/plans/`, leave it (N5). If unsure, STOP and report.

### Step 8 — Larry commits (B0.4)
Larry commits the whole working tree as one commit on branch `t1.4-web-retirement`, message summarising "T1.4: delete web/ and macos/MortimerShell; remove sidecar CORS, self-edit frontend gate, CI frontend build, web launcher." The implementer does not run `git`.

---

## §6 Tuning knobs — where every number lives, with its default and env override

This plan introduces **no** tuning knobs, thresholds, or env vars. It *removes* one hardcoded constant (`BUILD_TIMEOUT_S = 600`, Step 4B). The only number in the plan is the daily-driver window **5**, which is not a knob this plan owns — it is roadmap **G1(e)** (`docs/plans/MORTIMER_PLATFORM_ROADMAP.md` §4), and roadmap §7 **O7** is the one place a change to it would be decided (§12).

---

## §7 Tests — enumerated by file and function, with inputs and expected outputs

No new test files. The changes are verified by deletions, existing suites, and grep gates.

| # | Test | Input | Expected |
|---|---|---|---|
| T1 | `pytest tests/unit -q` collection | after Step 1 | collects with **no** `test_agents_yaml_frontend_parity`; **no** collection error; green. |
| T2 | `tests/unit/test_selfedit_service.py` (unchanged) | after Step 4 | passes — uses `tmp_path/web/src` synthetic fixtures + mocked `_run`; no assertion names `frontend_build` (verified `grep -rn frontend_build tests/` = ∅). |
| T3 | `tests/unit/test_selfedit_allowlist.py` (unchanged) | after Step 1/8 | passes — asserts allow/deny *string* logic against literal paths like `web/src/App.tsx`; the allow-list JSON is unchanged (W8), so every assertion holds. |
| T4 | REMOTE auth suite (`tests/unit/test_authmw.py` / `test_auth.py`, whichever REMOTE created) | after Step 2 | passes — 401 on missing/invalid token unchanged; CORS removal does not touch `BearerAuthMiddleware`. |
| T5 | Import smoke `python -c "import jarvis, jarvis.config, jarvis.cli, jarvis.runlog, jarvis.admin.server, jarvis.selfedit.service, jarvis.prompts, jarvis.agents.upgrade_agent"` | after Steps 2,4,6 | exits 0. |
| T6 | `bash -n scripts/mortimer.sh` | after Step 3 | exits 0; `grep -c "5173\|vite\|run_web\|WEB_PID\|web.log" scripts/mortimer.sh` = 0. |
| T7 | CI YAML parse | after Step 5 | both `validate.yml` load as YAML; no `web`/`npm`/`node` token remains. |
| T8 | Grep sweep (Step 7) | after all steps | empty except the two documented allowances. |
| T9 | Routing eval `RUN_LIVE=1 python -m tests.evals.routing_eval` | after all steps (§8, Larry's hardware) | ≥ 90 % — recorded (C7/G1(d)); no agent/prompt/model change means it is unchanged from the pre-deletion baseline. |

---

## §8 Verification Larry runs on his hardware (sandbox lacks Keychain/network/Xcode/mic)

1. **Precondition attestation (G1(e)).** Confirm the native app was daily driver 5 consecutive days with zero web-console fallback; that `docs/plans/implemented/MORTIMER_NATIVE_CLIENT_APP_PLAN.md` exists; that `macos/JarvisKit` and `macos/MortimerHost` exist. (These are §0 B0.1's gates; Larry is the human witness for the five days.)
2. **Stack starts clean.** `./scripts/mortimer.sh` → exactly bot + admin come up; `logs/` gains `bot.log` + `admin.log` only, no `web.log`; the closing message names the native app, not `:5173`. `./scripts/mortimer.sh logs` tails two files. `./scripts/mortimer.sh stop` kills both; `pgrep -f vite` finds nothing.
3. **Native app still connects** to the unchanged bot + sidecar (voice session, drawer Runs-tab fetch) with a valid token — proving CORS removal broke nothing (browser-only concern).
4. **Self-edit validation.** Trigger a small self-edit (`selfedit_start` on a `docs/**` file, then `selfedit_validate`): validation returns `allowlist → backend_imports → pytest`, **no** `frontend_build` check, and passes without `npm` installed.
5. **CI is green** on the `t1.4-web-retirement` PR with no Node/frontend step in the run log.
6. **Routing eval** `RUN_LIVE=1 python -m tests.evals.routing_eval` ≥ 90 % — record the score in the PR (C7/G1(d)).
7. **Rollback rehearsal (recommended before merge):** on a throwaway branch, `git revert` the (soon-to-exist) commit and confirm `web/` and `macos/MortimerShell/` return and `./scripts/mortimer.sh` starts web again — proving §9 works.

---

## §9 Rollback

There is **no runtime kill switch** — nothing here is feature-flagged; it is a deletion. Rollback is source-level.

- **Single-commit revert.** The entire change lands as one commit on `t1.4-web-retirement` (W10 / Step 8). To restore everything — the two trees, the CORS middleware, the self-edit gate, the CI step, the launcher lines, the docs — Larry runs `git revert <commit-sha>` (or `git checkout <parent-sha> -- web macos/MortimerShell scripts/run_web.sh scripts/build_shell.sh` for a partial file-level restore). Because `web/` and `macos/MortimerShell/` are only *deleted*, never rewritten, they are byte-for-byte recoverable from history: `git show <parent-sha>:web/package.json` etc.
- **Why one commit.** A revert of a single commit is one deterministic command; splitting the deletion across commits would force a multi-revert with ordering risk.
- **No data changes.** This plan writes to no database, vault, or `data/**` path, so there is nothing to un-migrate. `data/jarvis.db`, `logs/`, and the vault are untouched.
- **Partial regressions.** If only the launcher or CORS change misbehaves, revert just that file from the parent SHA rather than the whole commit; the trees can stay deleted.
- **Guard against premature run.** The §0 gates are the *forward* guard; this section is the *backward* one. If, after merge, the native app regresses badly enough that Larry needs the web console back, the revert above returns a working `web/` because the tree was preserved in history — but note the console's `web/src/api.ts` bearer-token flow (REMOTE A12) and the RTVI app-messages it decodes are unchanged by this plan, so a revert yields a *functional* console, not a stale one.

---

## §10 Risks (table)

| ID | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| RM-1 | T1.4 runs before the native app is truly the daily driver; Larry is left with no UI. | low | high | §0 hard stop: three mechanical gates (JarvisKit + MortimerHost present, T1.3 plan in `implemented/`) plus Larry's G1(e) attestation. Delete nothing if any gate fails. |
| RM-2 | Removing `CORSMiddleware` breaks REMOTE's preflight handling. | very low | med | REMOTE pre-built the `BearerAuthMiddleware` `OPTIONS` pass-through (A6/F16) *specifically* so removal is safe; it is left in place (N3). With no browser, no preflight is ever issued anyway. T4 (auth suite) + step-2 test prove 401 behaviour intact. |
| RM-3 | REMOTE (W1) reshaped `jarvis/admin/server.py` and the CORS anchor moved; a line-based edit deletes the wrong block. | med | high | B0.3 / Step 2 use text anchors only; if `CORSMiddleware,` is not found verbatim, STOP and report. |
| RM-4 | A live reference to `web/`/`5173` is missed and something breaks at runtime. | low | med | Step 7 full-repo grep sweep with an explicit allow-list of the two expected residual hits; any other hit blocks the commit. |
| RM-5 | A unit test secretly depended on the real `web/` tree or the `frontend_build` check. | low | med | Verified: `test_selfedit_service.py`/`test_selfedit_allowlist.py` use synthetic `tmp_path` fixtures and string literals; `grep -rn frontend_build tests/` is empty. T1/T2/T3 re-prove after deletion. |
| RM-6 | `macos/**` allow-list deny mistakenly assumed dead and removed, exposing JarvisKit/MortimerHost to self-edit. | low | high | W8/B0.5: `config/self_edit_allowlist.json` is not touched at all; `macos/**` deny stays. |
| RM-7 | The retired browser token (`localStorage['jarvis_token']`, XSS-readable — REMOTE A12 / F12 "R9") is thought to persist. | n/a | n/a (positive) | This is a *risk that closes*: deleting `web/` removes the only writer/reader of that key; no browser storage of a bearer token remains anywhere in the repo (grep for `localStorage` returns nothing after Step 1). |

---

## §11 Self-audit (9-item taxonomy)

1. **Multi-consumer contracts named but not typed.** This plan introduces no contract and consumes four (REMOTE R-A2/A6/A12, MAIL parity, the two NATIVE plans, roadmap G1(e)) — each cited by doc + section in the header and §1, not restated. The one API it *changes* (sidecar middleware stack) is specified by exact anchor text and its sole cross-consumer, REMOTE's auth middleware, is explicitly left intact with a test (T4). ✓
2. **Lifecycle left implicit.** The only lifecycle question is "what launches the UI now" — answered in Step 3/W4: `mortimer.sh` runs bot+admin only; the native GUI app is launched by Larry outside the script (stated, not implied). Deleted files have no lifecycle. ✓
3. **How a value is applied.** No values applied; removals only. The one near-value (the `mortimer.sh` closing message) has its exact replacement string given. ✓
4. **Two sections describing the same behaviour differently.** CORS removal is stated once as a decision (W3) and once as a step (Step 2) with the same anchor and the same "leave `BearerAuthMiddleware`/OPTIONS alone" caveat; the self-edit gate the same (W5/Step 4). Cross-checked. ✓
5. **Copy and visual states named but unspecified.** The three user-visible strings changed (`mortimer.sh` echo, `session_validate` description, prompt example) are given verbatim before and after. No visual states (no UI is authored). ✓
6. **Initialization timing.** N/A — nothing initializes. The only ordering that matters (this plan runs *after* REMOTE W1 reshaped `server.py`) is stated in B0.3 and handled by text anchors + a STOP. ✓
7. **Signatures agree; every schema column populated; every value derivable.** No signatures/schemas introduced. `validate()`'s return shape *loses* the `frontend_build` entry — checked against tests (no test reads it, T2). Every grep claim in §1 was run; every anchor string in §5 is quoted from the current source. ✓
8. **Judgment left to the implementer.** The two judgment points are gated deterministically: (a) the precondition — three `test`/`grep` checks with STOP conditions (§0); (b) the grep-sweep residuals — an explicit allow-list of two expected hits and "any other hit STOP/investigate with the matching decision" (Step 7). No "use judgment" remains. ✓
9. **Plan drift — files created but absent from manifest; "write X" vs "X exists".** No files created. Every path in §5 appears in §4's manifest; every DELETE/MODIFY row maps to a numbered step. §1's "NOT references" list pre-empts the "touch X" / "leave X" contradiction for `config.py`, the allow-list, the two selfedit tests, and `bot.py:4`. ✓

---

## §12 Approval checklist

- [ ] **G1(e) confirmed:** native app was daily driver 5 consecutive days, zero web-console fallback (roadmap §4). *(Larry: is 5 the right window, or does O7 want longer? If longer, say so before merge — this plan uses 5 per G1(e).)*
- [ ] `macos/JarvisKit` and `macos/MortimerHost` exist; `docs/plans/implemented/MORTIMER_NATIVE_CLIENT_APP_PLAN.md` exists (§0 B0.1).
- [ ] Deletion approved for: `web/`, `macos/MortimerShell/`, `scripts/run_web.sh`, `scripts/build_shell.sh`, `tests/acceptance/phase-6.md`, `tests/acceptance/mac-shell.md`, `tests/unit/test_agents_yaml_frontend_parity.py`.
- [ ] Sidecar `CORSMiddleware` removal approved (discharges REMOTE R-A2 deferral).
- [ ] `mortimer.sh` no longer launches web; self-edit `frontend_build` gate and CI Gate 5 removed.
- [ ] `config/self_edit_allowlist.json` left untouched (`macos/**` deny stays; web entries inert) — confirmed intentional (W8).
- [ ] Lands as ONE commit on `t1.4-web-retirement`; rollback = `git revert <sha>` (§9); rollback rehearsal (§8.7) passed.
- [ ] Routing eval ≥ 90 % recorded in the PR (C7 / G1(d)); CI green with no frontend step.
