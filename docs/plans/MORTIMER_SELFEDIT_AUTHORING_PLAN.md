# Mortimer — Self-Edit Authoring Plan (the developer writes; the sidecar validates; Larry reviews, merges, rebuilds)

**Status:** DRAFT for Larry's approval, 2026-09-07. Implements the architecture verdict in `Claude outputs/selfedit_architecture_review_2026-09-07.md` (options C, A, B) against roadmap track T1.3's live interface (`macos/MortimerHost`).

**Author / origin.** Larry, 2026-09-07, verbatim:

- *"I want to start a self-edit in the interface and take it all the way thru to having swift rebuild. I will have to do the rebuild but nothing before that manually."*
- *"we dont even get close to there today. maybe our architecture for self-edit is flawed."*
- *"i suggest a self-edit and you give me finished changes to review and commit and to rebuild in swift."*

**Roadmap constraints this plan is bound by.**

| C | How this plan honours it |
|---|---|
| **C1** — backend contract unchanged for the client migration | No RTVI shape changes. The console's existing `/api/selfedit/run`, `/validate`, `/submit`, `/revert` keep their signatures and synchronous behaviour (SE10); three routes are ADDED. |
| **C2** — localhost is the trust boundary | Nothing binds or opens a port. |
| **C4** — every mutation is draft → confirm | The self-edit keeps its two-phase start (preview → `staging_id` → confirm). SE1 makes `prepare_commit` narrower, not looser. Auto-submit-on-green (SE4) is the confirm the user already gave, stated in the preview text — see the decision. |
| **C7** — routing eval ≥ 90 % | No agent, description, or tool-name the router sees changes (`tests/evals/cases.yaml` names no `selfedit_*` tool — verified `grep -c` = 0). New MCP tools are inside the developer's server. Eval re-run is §8 V6 anyway. |
| **C8** — allow/deny changes are human commits | SE5 is Larry's commit, as a row in `ALLOWLIST_SEQUENCE.md`. |
| **C9** — secrets in the vault only | No new secret. `JARVIS_SELFEDIT_AUTHORING_ENABLED` is configuration. |
| **C10** — degradation-proof | Kill switch restores today's planner path exactly (§9). Swift gate absent (no toolchain) fails the gate loudly with the command output, never silently passes. |

**Contracts this plan INTRODUCES:** SE-A — the sidecar "finish" job (`POST /api/selfedit/finish`, `GET /api/selfedit/run` `finish` member), consumed by `mcp_selfedit`, `jarvis/bot/progress_watcher.py`, and (optionally later) the MortimerHost Edit tab.
**Contracts this plan CONSUMES:** G2 staging handshake (`MORTIMER_SESSION_GAPS_AND_SELFEDIT_CONVERGENCE_PLAN.md`); GL9 `run_id` threading (`MORTIMER_GRAPH_LAYER_PLAN.md`); K2 child-env whitelist (`MORTIMER_SECURITY_HARDENING_PLAN.md` — and the 2026-09-07 `CHILD_ENV_KEEP` in `jarvis/selfedit/service.py:87`); tiers (`MORTIMER_SELFEDIT_TIERS_PLAN.md`); B1/B2 visual intent (`MORTIMER_DEVELOPER_SECTIONS_AND_VISUAL_VERIFY_PLAN.md`).
**Corrections to the roadmap:** none. Corrections to `macos/README.md` and the tiers plan's "no Swift gate exists" premise are made by this plan (SE5/SE6) rather than argued with.

---

## §0 Binding constraints for the implementing model

0.1 Every decision in §3 is LOCKED. If a step is impossible as written, STOP and report; do not substitute.
0.2 FIND/REPLACE anchors must be verified unique (`grep -c` = 1) before editing. Missing or ambiguous → stop and report.
0.3 The approved test command is `uv run pytest tests/unit -q` on Larry's Mac. Never bare `pytest`. The implementer runs nothing in a sandbox that lacks the venv; it hands Larry the command.
0.4 Never `xfail`, never `skip`, never `try/except` around an assertion. SE5's "no pytest for a Swift-only diff" is a **gate-selection rule inside `validate()`**, not a test skip, and §7 pins that it fires only for macos-only diffs.
0.5 Human-only files: `config/self_edit_allowlist.json`, `config/upgrade_models.yaml`, `config/upgrade_agent.yaml`, `.env`. The implementer never writes them; the plan says "Larry commits" and gives the exact content.
0.6 No secrets in `.env`; the vault is the only secret store.
0.7 `VALIDATE_PYTEST_TIMEOUT_S` stays 900 (Larry, 09-05). New Swift timeouts start generous and every gate logs its wall-clock so the numbers get data before anyone tightens them.
0.8 The implementer does not run git. Branch for this work: `feat/selfedit-authoring`, cut from `feat/graph-layer`; Larry commits after each step's green suite.
0.9 Read `CLAUDE.md` in full before step 1.

---

## §1 What exists today (verified, path:line) and the gap

**The loop as built.** Voice → Supervisor (Haiku) → `delegate_task` → developer sub-agent (Opus, `config/agents.yaml`: `timeout_s: 300`, `max_iterations: 25`) → `selfedit_start` (`mcp_servers/mcp_selfedit/logic.py:64`) → `POST /api/selfedit/stage` → `staging_id` → user "yes" → `selfedit_start(confirm=true, staging_id)` → `POST /api/selfedit/run` (`jarvis/admin/server.py`, `selfedit_run`) → a **second LLM loop**, `UpgradeAgent` (`jarvis/agents/upgrade_agent.py`), in a fresh worktree with five tools (`file_read`, `edit_propose`, `session_validate`, `session_submit`, `session_decline`) → `SelfEditService.validate()` → `submit()` → PR.

**Fixed 2026-09-07 (2c0ff5a), in the tree:** whitelisted gate env (`service.py:87` `CHILD_ENV_KEEP`, `:93` `child_env()`); configurable base ref (`service.py:66` `BASE_REF_ENV`, `pr_base` property; `.env` carries `JARVIS_SELFEDIT_BASE_REF=feat/graph-layer`, pushed); staging-id resolution and busy-before-pop (`server.py` `_take_staging`); `submitted`/`pr_url` on the job; stale-session revert; `target_paths` on `preflight` / `stage` / `selfedit_start`. None has been exercised by voice.

**The gap this plan closes — the review's three findings, each with its evidence.**

1. *The unvalidated path shipped; the validated one never did.* `mcp_servers/mcp_git/logic.py:197-217` `prepare_commit(message)` runs **`git add -A`** (`:204`) and drafts a commit of every changed file; `actions` table rows #22 and #26 are 61- and 62-file commits to `main` by voice, pushed. `selfedit_start` has been called 46 times; PRs opened: 0.
2. *Containment is inverted.* `upgrade_agent.py:4-5` / `service.py:4-5`: the sandboxed planner "never gets shell or raw git access"; the developer, which can reach `main`, has `repo_write_file`/`repo_commit_write` (`mcp_servers/mcp_repo/logic.py:366,392`) and `prepare_commit`/`commit`/`push` (`mcp_git/skill.yaml:5`).
3. *The split blinds the editor.* 42 developer runs led to a `selfedit_start`; 106 read/search calls preceded staging whose results the planner never sees — the planner has `file_read` and the goal text, no search, and `docs/REPO_MAP.md` names `macos/` zero times.

**Three more facts that shape the design.**

- `jarvis/skills/registry.py:39` `CALL_TIMEOUT = 30.0` — every MCP tool call is bounded at 30 s. `POST /api/selfedit/validate` and `/submit` are **synchronous** (`server.py` `selfedit_validate` calls `_selfedit_service.validate()` inline; the suite alone took 328 s today). So the developer's existing `selfedit_validate`/`selfedit_submit` tools have never been usable against the real suite: they time out at 30 s. Any developer-driven validation MUST be a background job.
- `macos/**` is `deny` in `config/self_edit_allowlist.json`; `upgrade_agent.py:104` lists `macos/` as Tier 0 in the planner prompt; `service.py:786` tells the developer interface work "is a human PR"; `macos/README.md` says the same. Two voice attempts (09-05 drawer handle, 09-07 graph zoom) were refused here — correctly.
- Swift layout: `macos/MortimerHost/Package.swift` depends on `.package(path: "../JarvisKit")`; `macos/JarvisKit/Package.swift` depends on `https://github.com/stasel/WebRTC.git` (binary XCFramework). `.gitignore:51-53` ignores `macos/**/.build/`, `.swiftpm/`, `xcuserdata/`. `macos/MortimerHost/scripts/bundle.sh` wraps the SPM binary into `.build/MortimerHost.app` and opens it — **Larry's rebuild step, unchanged by this plan.** `GlassSpike/` is a throwaway spike and `MortimerShell/` the outgoing WKWebView shell (`macos/README.md`). No Python test reads any file under `macos/` (verified: the two mentions in `tests/` are a string in a forbidden-paths list and a docstring).

---

## §2 Non-goals

- The Upgrade Agent is **not deleted**. It stays for `app_build` (its own repo, no explorer) and for `plan_path`-seeded self-edits started from the console or by voice (SE3). Its tests stay.
- No change to the console's synchronous endpoints (C1). The MortimerHost Edit tab keeps working as today; wiring it to the finish job is a later, optional change.
- No Swift-side visual verification beyond B2's existing `selfedit_verify_appearance` after Larry's rebuild.
- No council changes. E1 escalation is not wired into the authored path (SE4's repair is the developer, by voice); E2 scope council is unchanged for planner declines.
- No baseline-diff pytest gate (review option D) — a separate, later decision once Swift runs have produced timing data.
- `web/**` stays frozen; the `web/src/**` allow entries are not touched (human-only file; not this plan's row).

---

## §3 Decisions — SE-lettered, each with a *why*

| # | Decision | Why |
|---|---|---|
| **SE1** | `prepare_commit(message, paths: list[str])` — `paths` is **required**, `git add -- <paths>` only, no `-A`; the draft summary names every file; `commit()` re-verifies the staged set equals the drafted set and refuses otherwise. The developer prompt: commit only files it wrote this session, never "everything". | Review finding 1: a 61-file sweep to `main` under a one-line message. A commit tool that stages the whole tree is a defect regardless of architecture. |
| **SE2** | **The developer authors self-edits in the sandbox.** Three new `mcp_selfedit` tools backed by three new sidecar routes over the EXISTING `SelfEditService` methods: `selfedit_read(path)` → `GET /api/selfedit/file` → `read_file`; `selfedit_write(path, content, rationale, visual_intent="")` → `POST /api/selfedit/write` → `propose_edit` (same allowlist check, same worktree, returns the diff); `selfedit_finish()` → `POST /api/selfedit/finish` → the background job in SE4. `selfedit_validate` and `selfedit_submit` tools are **retired** (endpoints stay, SE10). | Review findings 2 and 3: the agent that explores is the agent that edits; the sandbox contains the agent that has git reach; the 106 duplicated reads disappear; no goal-as-prose handoff for the common case. `propose_edit`/`read_file` already exist and are already tested — nothing about *what* an edit may touch changes. |
| **SE3** | `selfedit_start(confirm=true)`: if the staged record has a **`plan_path`** → launch the Upgrade Agent run exactly as today (`_run_agent`); otherwise → `start_session()` synchronously and return `{"ok": true, "session": {"branch", "goal", "target_paths", "run_id"}}` so the developer authors in the same delegation. Deterministic on one field. | Plan-driven, multi-file work is what the planner loop is for and what a 300 s / 25-iteration delegation cannot hold; a stated single goal is what the developer can author in 4–8 tool calls (measured exploring runs: 15–72 s). One rule, no judgment. |
| **SE4** | **The finish job.** `POST /api/selfedit/finish` starts a daemon thread: `validate()`; if every check passes → `submit()`; state machine `validating → submitting → done(pr_url) | failed(checks) | error`, mirrored on `GET /api/selfedit/run` as `finish: {state, checks, pr_url, started_at, finished_at, run_id}`. **Auto-submit on green is covered by the start confirmation:** the preview sentence becomes *"…validate it, and if every check passes open the pull request. Say yes to start (staging_id …)."* On `failed`, the session stays open with the check output; repair is the developer on the next turn (`selfedit_read` → `selfedit_write` → `selfedit_finish` again). No E1 council on this path. | Today's planner already calls `session_submit` with no per-submit user turn (`upgrade_agent.py` rule 4) — this is parity, made explicit in the words the user hears. Validation cannot be synchronous under `CALL_TIMEOUT = 30`. Repair by the developer keeps a human in the loop at the exact point the review found value (the council's correct diagnosis today led nowhere because the loop had no legal move). |
| **SE5** | **Swift gate + gate selection in `validate()`.** Changed paths under `macos/<Pkg>/…` → `PKGS = {"JarvisKit": ["JarvisKit", "MortimerHost"], "MortimerHost": ["MortimerHost"]}` union, JarvisKit first; for each package run `swift build` then `swift test` with `cwd=<worktree>/macos/<Pkg>` through `_run` (whitelisted env), timeouts `VALIDATE_SWIFT_BUILD_TIMEOUT_S = 1800`, `VALIDATE_SWIFT_TEST_TIMEOUT_S = 900`, checks named `swift_build:<Pkg>`, `swift_test:<Pkg>`. **When every changed path is under `macos/`, the pytest gate is not run** and the checks list carries `{"name": "pytest", "ok": true, "output": "not run — Swift-only diff; no Python test reads macos/ (verified 2026-09-07)", "selected": false}`. Backend/core import gates run regardless. Every gate logs `selfedit_gate name=%s ok=%s seconds=%.1f run_id=%s`. | The tiers plan denied `macos/**` because "no Swift gate exists, so a self-edit here would be unvalidated." This is the gate. Not running pytest on a diff it cannot observe is the same reasoning that removed the frontend build on 09-05; the selection rule is pinned by tests both ways. Timeouts are generous and logged because we have zero cold-worktree measurements (0.7). |
| **SE6** | **Swift change is loud.** `SWIFT_PATH_PREFIXES = ("macos/JarvisKit/Sources/", "macos/MortimerHost/Sources/")`; `VISUAL_PATH_PREFIXES` gains the `MortimerHost/Sources/` prefix so B1's `visual_intent` is recorded and B2's `selfedit_verify_appearance` works after the rebuild. PR body gains a `### SWIFT CHANGE — rebuild the app before using it` block naming `macos/MortimerHost/scripts/bundle.sh`, and a `### Validation (sidecar gates)` block listing every check with its `ok` and `seconds` (`validate()` keeps its last `checks` list on `self._last_checks`, next to the existing `_validated_ok`; cleared where that flag is cleared); `submit()`'s result gains `swift_change: true` and prepends the spoken notice `"SWIFT CHANGE: after merging, rebuild the app — cd macos/MortimerHost && scripts/bundle.sh — the running MortimerHost is the old binary until then."` | Larry keeps exactly one manual step and must hear it. Same mechanism as the CORE/CAPABILITY blocks: keyed on which paths changed, never on what the agent wrote. |
| **SE7** | **Prompts and maps.** `upgrade_agent.py` SYSTEM_PROMPT rule 2 drops `macos/` from Tier 0 and names the Swift gate. `jarvis/prompts.py` `self_development` section rewritten for the authored flow (literal text in §5 step 7). `service.py:786` freeze message: "…interface work goes to `macos/MortimerHost`, which self-edit can now change." `docs/REPO_MAP.md` gains a `macos/` section (literal text in §5 step 8). `macos/README.md` deny sentence replaced. `CLAUDE.md` self-edit paragraph updated. | The planner and developer both refuse macos on prompt text today; the planner has no map of the Swift tree. |
| **SE8** | **One attempt id.** The `run_id` GL9 already places in the staging record is stored on the session (`SelfEditService.run_id`), included in every `selfedit_*` log line, in `status()`, in the finish job, and passed as `session_id` to `record_completion` for sidecar-side LLM calls (planner path). | Reconstructing today's history needed two logs and four tables joined by timestamps. |
| **SE9** | **End-to-end integration test** `tests/integration/test_selfedit_end_to_end.py`: `TestClient(app)`, a temp bare origin + clone as `_selfedit_service.repo_root` with `base_ref` a local branch, `_open_pr` faked and captured, **real** allowlist/import/pytest gates on the temp repo's own one-test suite, Swift gate not triggered (no `macos/` in the temp repo); drives stage → confirm (session opens) → write → finish → asserts `done`, `pr_url`, `head`/`base` in the captured PR body, and the branch present in the bare origin. | No test has ever driven developer → sidecar → gates → git. Every attempt was a production run. |
| **SE10** | **Console endpoints unchanged.** `/api/selfedit/run`, `/validate`, `/submit`, `/revert`, `/cancel`, `/reject` keep signatures and synchronous behaviour. `/finish` is additive. `_busy()` covers both the run job and the finish job. | C1; the MortimerHost Edit tab calls these. |
| **SE11** | **Kill switch** `JARVIS_SELFEDIT_AUTHORING_ENABLED` (default on), read in ONE place, `server.py` `authoring_enabled()`. Off → `confirm=true` launches the Upgrade Agent for every staging, exactly today's behaviour; the three new tools return `{"ok": false, "error": "developer authoring is disabled (JARVIS_SELFEDIT_AUTHORING_ENABLED=false) — the planner path is active"}`. | C10. |

---

## §4 Files (create / modify / delete — complete manifest)

### Create (2)

| Path | What | Step |
|---|---|---|
| `tests/integration/test_selfedit_end_to_end.py` | SE9 | 9 |
| `docs/plans/MORTIMER_SELFEDIT_AUTHORING_PLAN.md` | this plan | 0 |

### Modify (19)

| Path | Change | Step |
|---|---|---|
| `mcp_servers/mcp_git/logic.py` | SE1 `prepare_commit(message, paths)`; `commit()` staged-set check | 1 |
| `mcp_servers/mcp_git/server.py` | `prepare_commit` tool signature + description | 1 |
| `tests/unit/test_mcp_git_logic.py` | SE1 tests | 1 |
| `jarvis/selfedit/service.py` | SE5 gate + selection + timing; SE6 prefixes/block/notice; SE7 freeze text; SE8 `run_id` on session/status/logs | 2, 3 |
| `tests/unit/test_selfedit_service.py` | SE5/SE6/SE8 tests | 2, 3 |
| `jarvis/admin/server.py` | SE3 confirm branch; SE2 `/file`, `/write`; SE4 `/finish` job + `GET /run` `finish`; SE8; SE11; `_busy()` | 4 |
| `tests/unit/test_admin_selfedit.py` | SE3/SE4/SE11 tests | 4 |
| `mcp_servers/mcp_selfedit/logic.py` | SE2 tools; retire validate/submit; SE4 preview sentence; `selfedit_status` speaks the finish job | 5 |
| `mcp_servers/mcp_selfedit/server.py` | tool registrations | 5 |
| `mcp_servers/mcp_selfedit/skill.yaml` | tools list | 5 |
| `tests/unit/test_mcp_selfedit_logic.py` | SE2/SE4 tests; retired-tool tests removed | 5 |
| `tests/integration/test_registry.py` | `TOTAL_TOOLS` 69 → **70** (−2 +3) | 5 |
| `jarvis/bot/progress_watcher.py` | poll `finish` too; line "Self-edit validating…" | 6 |
| `tests/unit/test_progress_watcher.py` | the new line | 6 |
| `jarvis/agents/upgrade_agent.py` | SE7 SYSTEM_PROMPT rule 2 | 7 |
| `jarvis/prompts.py` | SE7 `self_development` section | 7 |
| `tests/unit/test_prompts.py` | if any assertion pins the old wording (check with `grep -n "human PR\|selfedit_validate\|selfedit_submit"`) | 7 |
| `docs/REPO_MAP.md`, `macos/README.md`, `CLAUDE.md`, `docs/plans/ALLOWLIST_SEQUENCE.md` | SE7 text; SE5 row W0-SWIFT | 8 |
| `config/self_edit_allowlist.json` | **Larry's commit** (SE5, row W0-SWIFT) | 8 |

### Delete (0)

### Explicitly NOT touched
`jarvis/agents/upgrade_agent.py` loop body and `TOOL_SPECS`; `AppBuildAgent`; `jarvis/council/**`; `config/agents.yaml` roster; `tests/evals/cases.yaml`; `macos/**` Swift sources (this plan enables editing them; it does not edit them); `.github/workflows/validate.yml` (runs on PRs to `main` on ubuntu — no Swift there; the sidecar gate is the Swift validation, stated in §10).

---

## §5 Implementation steps, in order

Each step ends with `uv run pytest tests/unit -q` green and a Larry commit on `feat/selfedit-authoring`.

### Step 1 — SE1, `prepare_commit` takes paths

`mcp_servers/mcp_git/logic.py:197-217`. Replace the body:

```python
def prepare_commit(message: str, paths: list[str]) -> dict:
    """Stage ONLY `paths` and draft a commit. Does not commit.

    2026-09-07: this used to run `git add -A` and drafted whatever was
    dirty — actions #22 and #26 committed 61 and 62 files to main by voice
    under one-line messages (#3: 69 files, #11: 27 files, same way). A commit tool that stages the whole tree is a
    defect; the developer names what it wrote."""
    if not message or not message.strip():
        return {"ok": False, "error": "commit message is empty"}
    clean = [p.strip() for p in (paths or []) if p and p.strip()]
    if not clean:
        return {"ok": False, "error": "prepare_commit needs the list of files to commit — name the files you changed"}
    st = git_status()
    if st["clean"]:
        return {"ok": False, "error": "working tree is clean — nothing to commit"}
    unknown = [p for p in clean if p not in st["changed_files"]]
    if unknown:
        return {"ok": False, "error": "not changed in the working tree: " + ", ".join(unknown)}
    code, out = _git("add", "--", *clean)
    if code != 0:
        return {"ok": False, "error": f"git add failed: {out}"}
    summary = (
        f"Commit {len(clean)} file(s) on branch '{st['branch']}' "
        f"with message: \"{message}\". Files: {', '.join(clean)}"
    )
    action_id = _insert_action(
        "git_commit", {"message": message, "files": clean, "branch": st["branch"]}, summary
    )
    return {"ok": True, "action_id": action_id, "summary": summary}
```

In `commit(action_id)`, before `git commit`: read `git diff --cached --name-only`; if the set differs from `payload["files"]`, resolve the action `failed` with `"staged set drifted since the draft: ..."` and return that error. Update `server.py`'s `prepare_commit` tool signature `(message: str, paths: list[str])` and its description: *"Stage ONLY the named files and draft a commit… Name every file you changed; nothing else is staged."* `git_status`'s `changed_files` (`logic.py:138`) is the source of truth for the membership check — it already strips the two-column status prefix.

Tests (`tests/unit/test_mcp_git_logic.py`): `test_prepare_commit_requires_paths`; `test_prepare_commit_stages_only_named_paths` (dirty two files, name one, assert `git diff --cached --name-only` is exactly that one); `test_prepare_commit_refuses_an_unchanged_path`; `test_commit_refuses_when_staged_set_drifted`.

### Step 2 — SE5 Swift gate and gate selection

`jarvis/selfedit/service.py`. Add constants beside `VALIDATE_PYTEST_TIMEOUT_S`:

```python
# Swift gate (MORTIMER_SELFEDIT_AUTHORING_PLAN.md SE5). Generous and LOGGED,
# not tuned: a cold worktree resolves JarvisKit's WebRTC XCFramework from
# SwiftPM's cache under $HOME (or GitHub) and compiles from nothing — no
# measurement of that exists yet. Tighten only from logged seconds.
VALIDATE_SWIFT_BUILD_TIMEOUT_S = 1800
VALIDATE_SWIFT_TEST_TIMEOUT_S = 900
# Package dependency closure: a JarvisKit change must also build the app
# that consumes it (macos/MortimerHost/Package.swift: .package(path: "../JarvisKit")).
SWIFT_PACKAGES: dict[str, tuple[str, ...]] = {
    "JarvisKit": ("JarvisKit", "MortimerHost"),
    "MortimerHost": ("MortimerHost",),
}
SWIFT_PATH_PREFIXES = ("macos/JarvisKit/Sources/", "macos/MortimerHost/Sources/")
```

Add module functions:

```python
def swift_packages_for(changed: list[str]) -> list[str]:
    """Ordered, de-duplicated packages to build for these changed paths
    (JarvisKit before MortimerHost). Paths not under macos/<Pkg>/ contribute
    nothing; a macos path outside SWIFT_PACKAGES contributes nothing."""
    out: list[str] = []
    for p in changed:
        parts = p.replace("\\", "/").split("/")
        if len(parts) >= 2 and parts[0] == "macos" and parts[1] in SWIFT_PACKAGES:
            for pkg in SWIFT_PACKAGES[parts[1]]:
                if pkg not in out:
                    out.append(pkg)
    order = list(SWIFT_PACKAGES)  # JarvisKit, MortimerHost
    return sorted(out, key=order.index)


def is_swift_only(changed: list[str]) -> bool:
    return bool(changed) and all(p.replace("\\", "/").startswith("macos/") for p in changed)
```

In `validate()`, after the core-imports gate and BEFORE pytest, insert:

```python
        # SE5 — Swift gate, only when a Swift package changed.
        for pkg in swift_packages_for(changed):
            pkg_dir = self.tree / "macos" / pkg
            for verb, timeout in (("build", VALIDATE_SWIFT_BUILD_TIMEOUT_S),
                                  ("test", VALIDATE_SWIFT_TEST_TIMEOUT_S)):
                t0 = time.monotonic()
                code, out = self._run(["swift", verb], cwd=pkg_dir, timeout=timeout)
                seconds = time.monotonic() - t0
                name = f"swift_{verb}:{pkg}"
                logger.info("selfedit_gate name=%s ok=%s seconds=%.1f run_id=%s",
                            name, code == 0, seconds, self.run_id)
                checks.append({"name": name, "ok": code == 0,
                               "output": out[-2000:] or f"swift {verb} ok", "seconds": round(seconds, 1)})
                if code != 0:
                    break  # a failed build makes the test result meaningless
```

Replace the pytest block with the selection rule:

```python
        if is_swift_only(changed):
            checks.append({"name": "pytest", "ok": True, "selected": False,
                           "output": "not run — Swift-only diff; no Python test reads macos/ (verified 2026-09-07)"})
        else:
            t0 = time.monotonic()
            code, out = self._run([sys.executable, "-m", "pytest", "tests/unit", "-q"],
                                  cwd=self.tree, timeout=VALIDATE_PYTEST_TIMEOUT_S)
            seconds = time.monotonic() - t0
            logger.info("selfedit_gate name=pytest ok=%s seconds=%.1f run_id=%s",
                        code == 0, seconds, self.run_id)
            checks.append({"name": "pytest", "ok": code == 0,
                           "output": out[-2000:] or "tests ok", "seconds": round(seconds, 1)})
```

At the end of `validate()`, beside `self._validated_ok = ok` (line 613), add `self._last_checks = checks` (consumed by step 3's Validation table).

Also log and record `seconds` for the allowlist/import gates the same way (three more `logger.info` lines, `"seconds"` on each check dict). `swift` is resolved off `PATH` in the whitelisted env (`/usr/bin/swift` on macOS); a missing toolchain returns code 127 from `_run` and fails the gate with `"[Errno 2] No such file or directory: 'swift'"` — loud, never a pass.

Tests (`tests/unit/test_selfedit_service.py`, new class `TestSwiftGate`), all with `monkeypatch.setattr(service, "_run", fake)` recording `(argv, cwd)`: `test_no_swift_gate_without_macos_change`; `test_jarviskit_change_builds_and_tests_both_packages_in_order`; `test_mortimerhost_change_builds_only_mortimerhost`; `test_failed_swift_build_skips_swift_test_for_that_package`; `test_swift_only_diff_does_not_run_pytest` (assert no argv contains `"pytest"` and the pytest check has `selected: False`, `ok: True`); `test_mixed_diff_runs_pytest`; `test_swift_packages_for_ignores_non_package_macos_paths` (`macos/README.md` → `[]`); `test_gates_log_seconds` (caplog contains `selfedit_gate name=pytest`).

### Step 3 — SE6 Swift change block and notice; SE8 `run_id`; SE7 freeze text

`service.py`: extend `VISUAL_PATH_PREFIXES` to `("web/src/", "web/public/", "macos/MortimerHost/Sources/")`. Add `is_swift_path(path)` over `SWIFT_PATH_PREFIXES`. Add `_swift_change_block()` shaped like `_core_change_block()`:

```
### ⚠ SWIFT CHANGE — rebuild the app before using it

Files under the native client changed:
- `<path>` …

The gates ran `swift build` and `swift test` in the session worktree, but the
MortimerHost you are running is the binary from the last rebuild. After
merging and pulling: `cd macos/MortimerHost && scripts/bundle.sh`. Then say
"check your appearance" to have Mortimer look at the result.
```

Insert it in `_open_pr` after the core block. Add `_validation_block()` after the visual block — `validate()` (line 542) sets `self._last_checks = checks` beside `self._validated_ok` at line 613, and every line that resets `_validated_ok = False` (178, 302, 347, 688, 745) also sets `_last_checks = []`:

```
### Validation (sidecar gates)

| gate | ok | seconds |
|---|---|---|
| allowlist | ✓ | 0.1 |
| import:backend | ✓ | 2.3 |
| pytest | ✓ | 328.4 |
| swift_build:MortimerHost | ✓ | 412.0 |

`.github/workflows/validate.yml` runs only on pull requests to `main`; when the base is a feature branch this table is the only record of what ran.
```

One row per entry in `_last_checks` (`name`, `ok` as ✓/✗, `seconds`; a check without `seconds` — the pytest `selected: false` marker — shows `—`). In `submit()`, compute `swift = [p["path"] for p in self.proposals if is_swift_path(p["path"])]`; when non-empty set `result["swift_change"] = True`, `result["swift_paths"] = swift`, and prepend to `result["notice"]`: `"SWIFT CHANGE: after merging, rebuild the app — cd macos/MortimerHost && scripts/bundle.sh — the running MortimerHost is the old binary until then. "`.

`start_session(goal, run_id: str | None = None)` stores `self.run_id`; `status()` returns it; `revert()`/`submit()` clear it; every `logger.info("selfedit_…")` in the module gains `run_id=%s`. `service.py:786`: replace `"macos/MortimerHost, which is a human PR."` with `"macos/MortimerHost, which self-edit can change (name the Swift file in target_paths)."`. `tests/unit/test_web_freeze_preflight.py` mentions the old sentence only in its module docstring (lines 3-4), no assertion pins it — update the docstring.

Tests: `TestSwiftChangeFlag`: `test_is_swift_path`; `test_pr_body_flags_a_swift_change` (block present, names bundle.sh); `test_submit_notice_starts_with_swift_change` (token set, `_open_pr` faked, `_run` faked green, real git against the fixture's bare origin — the same shape as `test_run_reports_the_pull_request_it_submitted`); `test_a_python_change_gets_no_swift_block`; `test_pr_body_lists_every_gate_with_seconds`; `test_last_checks_cleared_by_a_new_edit`; `test_visual_intent_is_recorded_for_mortimerhost_sources`; `test_session_carries_run_id_into_status_and_logs`.

### Step 4 — SE3 confirm branch, SE2 routes, SE4 finish job, SE11 switch

`jarvis/admin/server.py`.

Kill switch (one place):

```python
SELFEDIT_AUTHORING_ENABLED_ENV = "JARVIS_SELFEDIT_AUTHORING_ENABLED"

def authoring_enabled() -> bool:
    """True unless JARVIS_SELFEDIT_AUTHORING_ENABLED is an explicit false value (SE11)."""
    return os.environ.get(SELFEDIT_AUTHORING_ENABLED_ENV, "").strip().lower() not in ("0", "false", "no", "off")
```

Finish job state beside `_run_job`:

```python
_finish_job: dict[str, Any] = {
    "state": "idle",   # idle | validating | submitting | done | failed | error
    "checks": None, "pr_url": None, "notice": None, "run_id": None,
    "started_at": None, "finished_at": None,
}
_finish_lock = threading.Lock()
```

`_busy()` becomes `_run_job["state"] == "running" or _finish_job["state"] in ("validating", "submitting")`.

In `selfedit_run`, after the staged record is resolved and the plan text loaded, replace the unconditional `_make_agent`/thread launch with:

```python
    if authoring_enabled() and not plan_path and body.plan is None:
        # SE3 — developer-authored: open the session now, return it.
        if _selfedit_service.branch and (_selfedit_service.goal or "") != goal:
            logger.info("selfedit_stale_session_reverted branch=%s ...", ...)  # existing lines
            _selfedit_service.revert()
        if not _selfedit_service.branch:
            res = _selfedit_service.start_session(goal, run_id=run_id)
            if not res.get("ok"):
                return {"ok": False, "error": res.get("error")}
        logger.info("selfedit_state_transition state=session_open goal=%r run_id=%s", goal, run_id)
        return {"ok": True, "started": False, "session": {
            "branch": _selfedit_service.branch, "goal": goal,
            "target_paths": rec_target_paths, "run_id": run_id,
            "worktree": str(_selfedit_service.work_root),
        }}
    # planner path (plan_path present, or authoring disabled): unchanged below
```

(`rec_target_paths` = `rec.get("target_paths") or []` on the staged branch and `[]` on the deprecated bare-goal branch — `GoalIn` has no `target_paths` field and gains none. Store `target_paths` in the staging record in `selfedit_stage` (server.py `_selfedit_stagings[staging_id] = {...}`, which today keeps `goal`, `profile`, `plan_path`, `run_id`, `created_at` — `target_paths` is classified by `preflight` and then dropped). `_busy()` today is `_run_job["state"] == "running"` under `_run_lock`; the finish-job clause reads `_finish_job` under `_finish_lock`.)

Routes:

```python
class SelfEditFileQuery(BaseModel):
    path: str

@app.get("/api/selfedit/file")
def selfedit_file(path: str) -> dict:
    if not authoring_enabled():
        return _AUTHORING_OFF
    return _selfedit_service.read_file(path)

class SelfEditWriteIn(BaseModel):
    path: str
    content: str
    rationale: str = ""
    visual_intent: str = ""

@app.post("/api/selfedit/write")
def selfedit_write(body: SelfEditWriteIn) -> dict:
    if not authoring_enabled():
        return _AUTHORING_OFF
    if _busy():
        return {"ok": False, "error": "validation is running — wait for it to finish, then edit"}
    return _selfedit_service.propose_edit(body.path, body.content, body.rationale, body.visual_intent)

@app.post("/api/selfedit/finish")
def selfedit_finish() -> dict:
    if not authoring_enabled():
        return _AUTHORING_OFF
    if not _selfedit_service.branch:
        return {"ok": False, "error": "no open self-edit session"}
    if not _selfedit_service.proposals:
        return {"ok": False, "error": "nothing has been written yet"}
    with _finish_lock:
        if _busy():
            return {"ok": False, "error": "a run is already in progress — ask for status instead"}
        _finish_job.update(state="validating", checks=None, pr_url=None, notice=None,
                           run_id=_selfedit_service.run_id, started_at=time.time(), finished_at=None)
    threading.Thread(target=_run_finish, daemon=True).start()
    return {"ok": True, "started": True, "state": "validating"}
```

`_AUTHORING_OFF = {"ok": False, "error": "developer authoring is disabled (JARVIS_SELFEDIT_AUTHORING_ENABLED=false) — the planner path is active"}`.

The worker:

```python
def _run_finish() -> None:
    try:
        result = _selfedit_service.validate()
        with _finish_lock:
            _finish_job["checks"] = result.get("checks")
        if not result.get("ok"):
            with _finish_lock:
                _finish_job.update(state="failed", finished_at=time.time())
            logger.info("selfedit_state_transition state=finish_failed run_id=%s", _finish_job["run_id"])
            return
        with _finish_lock:
            _finish_job["state"] = "submitting"
        sub = _selfedit_service.submit()
        with _finish_lock:
            if sub.get("ok"):
                _finish_job.update(state="done", pr_url=sub.get("pr_url"), notice=sub.get("notice"), finished_at=time.time())
            else:
                _finish_job.update(state="error", notice=sub.get("error"), finished_at=time.time())
        logger.info("selfedit_state_transition state=finish_%s pr=%s run_id=%s",
                    _finish_job["state"], _finish_job["pr_url"], _finish_job["run_id"])
    except Exception as exc:  # noqa: BLE001 — a crash must still settle the job
        logger.exception("finish job crashed")
        with _finish_lock:
            _finish_job.update(state="error", notice=f"finish crashed: {type(exc).__name__}: {exc}", finished_at=time.time())
```

`selfedit_run_status` returns `"finish": dict(_finish_job)` alongside `job`. A `failed` finish leaves the session open (validate() never commits); `validated_ok` stays false until a later finish passes.

Tests (`tests/unit/test_admin_selfedit.py`): `test_confirm_without_plan_opens_a_session_and_does_not_launch_the_planner` (`_make_agent` patched to raise; `_selfedit_service` swapped for a temp-repo service; assert `session.branch`, `started is False`); `test_confirm_with_plan_path_still_launches_the_planner`; `test_authoring_kill_switch_restores_planner_path` (`monkeypatch.setenv(..., "false")`); `test_write_then_finish_reaches_done_with_pr_url` (`validate` and `submit` patched on the service to return green / `{"ok": True, "pr_url": …}`; poll `finish.state == "done"`); `test_finish_failed_leaves_session_open_with_checks`; `test_finish_refused_while_busy`; `test_write_refused_while_validating`; `test_file_route_honours_allowlist`; `test_run_status_carries_finish_and_run_id`.

### Step 5 — SE2 tools in `mcp_selfedit`

`logic.py`: add

```python
def selfedit_read(client, path: str) -> dict[str, Any]:
    return _call(lambda: client.get("/api/selfedit/file", params={"path": path}))

def selfedit_write(client, path: str, content: str, rationale: str = "", visual_intent: str = "") -> dict[str, Any]:
    resp = _call(lambda: client.post("/api/selfedit/write", json={
        "path": path, "content": content, "rationale": rationale, "visual_intent": visual_intent}))
    if not resp.get("ok"):
        return resp
    return {"ok": True, "path": resp.get("path"), "diff": resp.get("diff", ""),
            "summary": f"Wrote {resp.get('path')} in the session worktree."}

def selfedit_finish(client) -> dict[str, Any]:
    resp = _call(lambda: client.post("/api/selfedit/finish"))
    if not resp.get("ok"):
        return resp
    return {"ok": True, "started": True,
            "summary": ("Validating now — allowlist, imports, the Swift build and tests when a Swift "
                        "file changed, and the Python suite when one is affected. If every check passes "
                        "the pull request opens automatically; ask me how it is coming along anytime.")}
```

(`AdminClient.get(path)` at `logic.py:40` takes no `params` — add `params: dict | None = None` and pass it through to `httpx.Client.get`; the fake clients in `test_mcp_selfedit_logic.py` gain the same keyword. `AdminClient`'s timeout is 10 s: the synchronous `start_session` inside `confirm=true` took 0.9 s on 2026-09-07 14:14:33→34 (`admin.launchd.log`, `state=running` → `selfedit_session_start`) with a local base ref; an `origin/` base adds one `git fetch` — keep the base local until that is measured.) In `selfedit_start`'s `confirm=true` branch, when the response carries `session` (not `started`), return `{"ok": True, "session": …, "summary": "Session open on <branch>. Read the target files with selfedit_read, write the change with selfedit_write, then call selfedit_finish."}` — the developer acts on that in the same delegation. Preview sentence (SE4) replaces the current *"Planning runs in the background and can take several minutes; I can check progress anytime. Say yes to start (staging_id …)."* with *"I will write the change, validate it, and if every check passes open the pull request. Say yes to start (staging_id …)."* — the `core_note` sentence stays. `selfedit_status`: when `finish.state` is `validating`/`submitting` say so; when `done` speak `pr_url` and the notice (the SWIFT CHANGE sentence rides in it); when `failed` speak the first failing check's name and the first 200 chars of its output and offer to fix it. Remove `selfedit_validate` and `selfedit_submit` from `logic.py`, `server.py`, `skill.yaml`; add the three. `test_registry.py` `TOTAL_TOOLS` 69 → 70 with a comment line in the existing style.

Tests (`test_mcp_selfedit_logic.py`): replace the validate/submit tests with `test_read_posts_path`; `test_write_returns_diff_and_summary`; `test_finish_posts_and_speaks_the_contract`; `test_confirm_with_session_response_tells_the_developer_what_to_do_next`; `test_preview_sentence_states_validate_and_open_pr`; `test_status_speaks_finish_states` (three cases: validating, done with pr_url + notice, failed with the failing check).

### Step 6 — progress watcher

`jarvis/bot/progress_watcher.py:156-165` `_default_fetch_selfedit_job`: also return the job when `data["finish"]["state"] in ("validating", "submitting")`, with a `kind` key; `_fmt_selfedit_line`: `"Self-edit validating…"` / `"Self-edit submitting the pull request…"` for those kinds, existing text otherwise. Test: `test_progress_watcher.py::test_finish_job_is_announced`.

### Step 7 — SE7 prompts

`jarvis/agents/upgrade_agent.py:104`: in rule 2 delete `, macos/` from the Tier-0 list and append to the Routine sentence: *"Swift sources under macos/JarvisKit and macos/MortimerHost are routine and are validated by swift build and swift test."* (`TOOL_SPECS` unchanged.)

`jarvis/prompts.py` `DEVELOPER_SECTIONS["self_development"]` — replace the two-phase sentences (*"Same two-phase discipline: … staging_id the preview returned."*) with:

> Same two-phase discipline: call selfedit_start with confirm set to false, pass target_paths — the files the edit will CHANGE — speak the returned summary and STOP; only after explicit confirmation in a new turn call again with confirm set to true AND the staging_id. When that call returns a session (no plan_path), YOU write the change in the same turn: selfedit_read each target file, selfedit_write the complete new content with a one-line rationale (and, for a file under macos/MortimerHost/Sources, one sentence of visual_intent saying what should look different), then selfedit_finish — validation and the pull request happen in the background, so end your turn by saying so. If a later status reports a failed check, read the output, fix it with selfedit_write, and call selfedit_finish again. When the goal names a plan document, pass plan_path and the planner does the writing instead. Interface work goes to the macOS host under macos/MortimerHost/Sources — never web/, which is frozen.

Delete the sentences that reference `selfedit_validate` and `selfedit_submit`. Keep the length under what `test_prompts.py` enforces (check with `grep -n "1250\|1200" tests/unit/test_prompts.py` — the developer core has its own ceiling; this section is not in the core). Add to the git guidance: *"prepare_commit takes the list of files to commit; name exactly the files you changed, never everything that is dirty."*

### Step 8 — SE5 allowlist row (Larry) and docs

`docs/plans/ALLOWLIST_SEQUENCE.md`: add row **W0-SWIFT**, owner this plan: *Remove `"macos/**"` from `deny`. Add to `allow`: `"macos/JarvisKit/**"`, `"macos/MortimerHost/**"`. Add to `deny`: `"macos/**/Package.swift"`, `"macos/**/Package.resolved"`, `"macos/**/*.plist"`, `"macos/**/*.entitlements"`, `"macos/**/scripts/**"`, `"macos/GlassSpike/**"`, `"macos/MortimerShell/**"`.* Verify command: `uv run pytest tests/unit/test_selfedit_allowlist.py -q`.

`tests/unit/test_selfedit_allowlist.py`: `test_allowed_paths` gains `"macos/MortimerHost/Sources/MortimerHost/Display/GraphImageView.swift"` and `"macos/JarvisKit/Tests/JarvisKitTests/AppMessageTests.swift"`; `test_forbidden_paths` keeps `"macos/MortimerHost/Package.swift"` and gains `"macos/MortimerHost/Sources/MortimerHost/Info.plist"`, `"macos/MortimerHost/scripts/bundle.sh"`, `"macos/MortimerShell/Package.swift"`. These tests are RED until Larry's commit lands — that is the intended order (the tests describe the allowlist the row produces); Larry applies the row in the same push.

`docs/REPO_MAP.md`: add under the top-level tree:

> - `macos/` — the native client (Swift). `JarvisKit/` is the shared package (voice session, admin API client, wake word); `MortimerHost/` is the app: `Sources/MortimerHost/Display/` (display panels, `GraphImageView.swift` renders graph PNGs at panel size), `Drawer/` (side drawer tabs incl. `EditTab.swift`), `Stores/` (`AgentRunStore.swift`), `Support/` (`AppTuning.swift` constants). `GlassSpike/` is a throwaway spike; `MortimerShell/` is the outgoing WKWebView shell. Build: `swift build` / `swift test` per package; the app bundle is `MortimerHost/scripts/bundle.sh`.

`macos/README.md`: replace the deny paragraph with: *"`macos/JarvisKit/**` and `macos/MortimerHost/**` are self-editable (MORTIMER_SELFEDIT_AUTHORING_PLAN.md); manifests, plists, entitlements, `scripts/`, `GlassSpike/` and `MortimerShell/` are not. A self-edit is validated by `swift build` + `swift test` in its worktree; the running app is rebuilt by a human with `scripts/bundle.sh`."* `CLAUDE.md`: the self-edit paragraph gains one sentence naming the authored flow and the Swift gate.

### Step 9 — SE9 end-to-end test

`tests/integration/test_selfedit_end_to_end.py` (runs in Larry's integration suite; needs git and the venv, no network):

```python
"""The test that never existed: developer tool -> sidecar -> gates -> git -> PR."""
import json, subprocess, time
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
import jarvis.admin.server as srv
from jarvis.admin.server import app
from jarvis.selfedit.service import SelfEditService

ALLOWLIST = {"allow": ["docs/**", "tests/**"], "deny": ["jarvis/**"], "core": []}

def _git(cwd, *a): subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True, text=True)

@pytest.fixture
def temp_repo(tmp_path):
    origin = tmp_path / "origin.git"; _git(tmp_path, "init", "--bare", str(origin))
    work = tmp_path / "work"; _git(tmp_path, "clone", str(origin), str(work))
    _git(work, "config", "user.email", "t@e.com"); _git(work, "config", "user.name", "T")
    _git(work, "checkout", "-b", "main")
    (work / "jarvis").mkdir(); (work / "jarvis/__init__.py").write_text("")
    (work / "jarvis/config.py").write_text(""); (work / "jarvis/cli.py").write_text("")
    (work / "tests/unit").mkdir(parents=True); (work / "tests/unit/test_ok.py").write_text("def test_ok():\n    assert True\n")
    (work / "docs").mkdir(); (work / "docs/NOTE.md").write_text("hello\n")
    (work / "config").mkdir(); (work / "config/self_edit_allowlist.json").write_text(json.dumps(ALLOWLIST))
    _git(work, "add", "-A"); _git(work, "commit", "-m", "init"); _git(work, "push", "-u", "origin", "main")
    return origin, work

def _wait(c, state, timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        f = c.get("/api/selfedit/run").json()["finish"]
        if f["state"] == state: return f
        time.sleep(0.2)
    raise AssertionError(f"finish never reached {state}: {f}")

def test_stage_confirm_write_finish_opens_a_pull_request(temp_repo, monkeypatch):
    origin, work = temp_repo
    svc = SelfEditService(repo_root=work, github_token="t", github_repo="o/r", base_ref="origin/main")
    captured = {}
    monkeypatch.setattr(svc, "_open_pr", lambda title: captured.update(title=title) or {"html_url": "https://example.invalid/pr/1"})
    monkeypatch.setattr(srv, "_selfedit_service", svc)
    monkeypatch.setattr(srv, "_make_agent", lambda *a, **k: (_ for _ in ()).throw(AssertionError("planner must not launch")))
    c = TestClient(app)
    sid = c.post("/api/selfedit/stage", json={"goal": "add a line to docs/NOTE.md", "target_paths": ["docs/NOTE.md"]}).json()["staging_id"]
    opened = c.post("/api/selfedit/run", json={"staging_id": sid}).json()
    assert opened["ok"] and opened["session"]["branch"].startswith("jarvis/self-edit/")
    assert c.get("/api/selfedit/file", params={"path": "docs/NOTE.md"}).json()["content"] == "hello\n"
    w = c.post("/api/selfedit/write", json={"path": "docs/NOTE.md", "content": "hello\nworld\n", "rationale": "e2e"}).json()
    assert w["ok"] and "+world" in w["diff"]
    assert c.post("/api/selfedit/finish").json()["started"]
    fin = _wait(c, "done")
    assert fin["pr_url"] == "https://example.invalid/pr/1"
    names = {ch["name"]: ch["ok"] for ch in fin["checks"]}
    assert names == {"allowlist": True, "backend_imports": True, "pytest": True}
    branch = opened["session"]["branch"]
    out = subprocess.run(["git", "rev-parse", f"refs/heads/{branch}"], cwd=origin, capture_output=True, text=True)
    assert out.returncode == 0, "session branch was not pushed to origin"
    assert svc.branch is None  # torn down after submit
```

The `backend_imports` gate passes because the temp repo carries stub `jarvis/config.py` and `jarvis/cli.py` and the child's cwd is the worktree (sys.path[0] = cwd for `-c`). A second test, `test_finish_failed_keeps_the_session_open`, writes `tests/unit/test_bad.py` with a failing test and asserts `state == "failed"`, `checks["pytest"] is False`, `svc.branch` still set.

### Step 10 — the first Swift run (Larry, §8)

---

## §6 Tuning knobs — where every number lives

| Knob | Where | Default | Override |
|---|---|---|---|
| `VALIDATE_SWIFT_BUILD_TIMEOUT_S` | `jarvis/selfedit/service.py` | 1800 | none — edit the constant after reading logged `seconds` |
| `VALIDATE_SWIFT_TEST_TIMEOUT_S` | same | 900 | same |
| `VALIDATE_PYTEST_TIMEOUT_S` | same | 900 | unchanged (0.7) |
| `SWIFT_PACKAGES` | same | JarvisKit→(JarvisKit, MortimerHost); MortimerHost→(MortimerHost,) | edit when a package is added |
| `SWIFT_PATH_PREFIXES`, `VISUAL_PATH_PREFIXES` | same | as SE6 | — |
| `JARVIS_SELFEDIT_AUTHORING_ENABLED` | `jarvis/admin/server.py` `authoring_enabled()` — the only read | on | `.env` (configuration) |
| `JARVIS_SELFEDIT_BASE_REF` | `service.py:66` (existing) | `origin/main` | `.env` — already `feat/graph-layer` |

### Not knobs (deliberately)
The developer's `timeout_s: 300` / `max_iterations: 25` (`config/agents.yaml`) — authoring must fit them; if a goal cannot, it gets a `plan_path` and the planner (SE3). `CALL_TIMEOUT = 30` in the registry — the reason every long operation is a job.

---

## §7 Tests — enumerated

| File | Test | Pins |
|---|---|---|
| `tests/unit/test_mcp_git_logic.py` | `test_prepare_commit_requires_paths` | SE1 |
| | `test_prepare_commit_stages_only_named_paths` | SE1: `git diff --cached --name-only` == the named file |
| | `test_prepare_commit_refuses_an_unchanged_path` | SE1 |
| | `test_commit_refuses_when_staged_set_drifted` | SE1 |
| `tests/unit/test_selfedit_service.py::TestSwiftGate` | 8 tests listed in step 2 | SE5, incl. both directions of the pytest selection rule |
| `::TestSwiftChangeFlag` | 8 tests listed in step 3 | SE6, SE8 |
| existing `test_validate_runs_pytest_gate_and_passes` etc. | unchanged (no macos paths → pytest runs) | selection rule default |
| `tests/unit/test_admin_selfedit.py` | 9 tests listed in step 4 | SE3, SE4, SE10, SE11 |
| `tests/unit/test_mcp_selfedit_logic.py` | 6 tests listed in step 5 | SE2, SE4 |
| `tests/unit/test_progress_watcher.py` | `test_finish_job_is_announced` | step 6 |
| `tests/unit/test_selfedit_allowlist.py` | allowed/forbidden additions in step 8 | SE5 (red until Larry's row) |
| `tests/integration/test_registry.py` | `TOTAL_TOOLS == 70` | SE2 |
| `tests/integration/test_selfedit_end_to_end.py` | 2 tests in step 9 | SE9 — the chain |
| `tests/evals/routing_eval.py` | unchanged; re-run in §8 V6 | C7 |

Full-suite gate after every step: `uv run pytest tests/unit -q` green; after step 9: `uv run pytest tests/integration -q` green.

---

## §8 Verification Larry runs on his hardware

**V0 — before any code: the toolchain from a PATH-only environment** (what the sidecar's child gets):
```
cd ~/jarvis-voice-ai-clean/macos/MortimerHost && time env -i PATH=/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin HOME="$HOME" swift build 2>&1 | tail -5
```
Expect a build. If `swift` is not found, `xcode-select -p` must point at Xcode or the CLT before step 2 is worth writing; report and stop.

**V1 — the suite.** `uv run pytest tests/unit -q` green at every step; `uv run pytest tests/integration -q` green after step 9 (the e2e test is the one that has never existed).

**V2 — restart.** `./scripts/mortimer.sh` after the final commit (sidecar and bot both carry changed code).

**V3 — the run that has never happened, by voice.** Say: *"Start a self-edit: add zoom in and zoom out to the memory graph window in the macOS host — mouse wheel and plus/minus keys, keep pan working. Only change GraphImageView.swift."* Expect the preview naming `target_paths` `macos/MortimerHost/Sources/MortimerHost/Display/GraphImageView.swift` and the sentence *"…validate it, and if every check passes open the pull request."* Say *yes*. Expect: *"Session open… written GraphImageView.swift… validating now."* Wait — the first cold `swift build` is unmeasured; the progress watcher says *"Self-edit validating…"* every tick. Ask *"how is the self-edit coming along?"* Expect the PR link and the SWIFT CHANGE sentence. If `failed`: expect the failing check named with its output, and *"want me to fix it?"* — say yes and the repair loop runs once more.

**V4 — the gates' own numbers.** `grep selfedit_gate logs/admin.launchd.log` — one line per gate with `seconds=`. Record `swift_build:MortimerHost` cold; that number is what tightens `VALIDATE_SWIFT_BUILD_TIMEOUT_S` later, and nothing else does.

**V5 — review, merge, rebuild (the one manual step).** Review the PR on GitHub (base `feat/graph-layer`; body carries the SWIFT CHANGE block and the intended-appearance sentence). Merge. Then:
```
cd ~/jarvis-voice-ai-clean && git pull && cd macos/MortimerHost && scripts/bundle.sh
```
Zoom the graph. Optionally: *"check your appearance"* → `selfedit_verify_appearance` (`branch_override` since the change is merged).

**V6 — routing eval** (C7): `RUN_LIVE=1 uv run python tests/evals/routing_eval.py` ≥ 90 %.

**V7 — SE1 in the wild.** *"Commit the two files you just changed"* → the draft names exactly those files; `git log --stat -1` after confirm shows only them.

Results are appended here.

---

## §9 Rollback

- `JARVIS_SELFEDIT_AUTHORING_ENABLED=false` in `.env` + restart: `confirm=true` launches the planner for every staging, the three tools refuse with a named reason, the finish route refuses. Today's behaviour exactly.
- Swift gate: no switch. It runs only when `macos/**` changed; reverting Larry's allowlist row makes that impossible again (`test_selfedit_allowlist.py`'s new allowed-paths tests go red — intended).
- SE1: no data change; reverting the commit restores `git add -A`.
- Data: worktrees and session branches are removed by `submit()`/`revert()` as today; a finish job that dies mid-way leaves the session open — `POST /api/selfedit/revert` (or *"revert the self-edit"*) drops it.

---

## §10 Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Cold `swift build` in a fresh worktree exceeds 1800 s (WebRTC XCFramework fetched from GitHub rather than SwiftPM's cache) | unknown — no measurement exists | V0 measures warm; V4 measures cold; the timeout starts generous; `HOME` is in `CHILD_ENV_KEEP` so the cache is reachable |
| `swift` not resolvable from the launchd child (`xcode-select` not set) | low; V0 settles it before code | gate fails loudly with code 127 and the error text |
| A barge-in orphans the developer's authoring run mid-write | medium | writes land in the worktree as they happen; the session stays open; the next turn's `selfedit_status` shows `proposals` and the developer continues |
| Developer exceeds 25 iterations / 300 s while authoring | low for single-file goals | the session survives; multi-file goals use `plan_path` (SE3) |
| Push from the launchd process cannot authenticate (never run) | unknown | first surfaced by V3; `finish.state == "error"` with the git error text; fix is a credential-helper question, not this plan |
| `_busy()` now blocks console `/validate` while a finish job runs | certain, by design | the console reports "a run is in progress"; SE10 keeps its endpoints |
| The PR opens against `feat/graph-layer` (`.env` `JARVIS_SELFEDIT_BASE_REF`), and `.github/workflows/validate.yml` runs only on `pull_request` to `main` — so GitHub runs no checks on the self-edit PR | certain, read from the workflow | the sidecar gates ARE the checks (allowlist, import, pytest, Swift); the PR body's Validation table (SE6, step 3) records which ran and their seconds. When the base returns to `origin/main`, CI runs again, without Swift |
| A Swift-only diff skips pytest and a Python test later starts reading `macos/` | low | `is_swift_only` is one function with both-direction tests; the day a test reads `macos/`, remove the rule |

---

## §11 Self-audit — the nine-item taxonomy

1. *Multi-consumer contracts typed:* the finish job dict is specified member-by-member (SE4) and read by `mcp_selfedit`, `progress_watcher`, and `GET /api/selfedit/run`; `selfedit_start`'s `session` response is specified with all five keys.
2. *Lifecycle:* session survives a failed finish and a barge-in; torn down by `submit()`/`revert()` only; finish job is process state, reset on restart like `_run_job` (documented as such in G2).
3. *How a value is applied:* `target_paths` is stored in the staging record (new) and returned in `session`; `run_id` flows staging → session → logs/status/ledger.
4. *Two sections, one behaviour:* auto-submit-on-green is stated once (SE4) and the preview sentence is given once (step 5); §3 and §5 agree on tool names and route names.
5. *Copy specified:* preview sentence, finish summary, status sentences, SWIFT CHANGE block and notice, `_AUTHORING_OFF` — all literal.
6. *Initialization timing:* `_finish_job` is module state initialized `idle`; `authoring_enabled()` is read per call, never cached.
7. *Signatures agree:* `prepare_commit(message, paths)` in logic and server; `selfedit_write(path, content, rationale, visual_intent)` in logic, server, and route model; `start_session(goal, run_id=None)`; `validate()` unchanged signature.
8. *No judgment left:* tier (routine), deny set, timeouts, package closure, pytest selection, planner-vs-author rule (`plan_path` present) are all literal.
9. *Drift:* every file in §5 appears in §4; `test_web_freeze_preflight.py`'s docstring is named in step 3; `TOTAL_TOOLS` change is in both §4 and §5. Every `path:line` above was re-read against the tree on 2026-09-07 before this draft was delivered.

---

## §12 Approval checklist (Larry)

- [ ] **Tier for Swift sources is routine** (SE5), not core — no `plan_path` for a single-file Swift change.
- [ ] **The deny set under `macos/`** (step 8 row W0-SWIFT): manifests, plists, entitlements, `scripts/`, the spike, the shell.
- [ ] **Auto-submit on green is covered by the start confirmation**, stated in the preview sentence (SE4).
- [ ] **`plan_path` present → planner; absent → developer authors** (SE3).
- [ ] **No pytest on a Swift-only diff** (SE5).
- [ ] **Swift timeouts start at 1800 / 900 and are tightened only from logged seconds** (0.7).
- [ ] **`prepare_commit` requires the file list** (SE1) — this changes what "commit my changes" does by voice: the developer must name files.
- [ ] Branch `feat/selfedit-authoring` from `feat/graph-layer`; Larry commits per step; V0 runs before step 2.
