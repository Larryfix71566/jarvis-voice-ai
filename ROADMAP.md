# Mortimer master roadmap

This file is the single record of **who is doing what** in this repository, for every system that writes code here. Plans (`docs/plans/`) hold design. Receipts (`docs/acceptance/`) hold evidence. **This file holds ownership and state.**

**Last reconciled:** 2026-09-27 17:00 EDT, against main `0b76f49` and Codex's worktree `codex/isolated-20260924`. Details: [cross-system evaluation](docs/reviews/CROSS_SYSTEM_PLAN_EVAL_2026-09-27.md).

---

## 0. Protocol (binding for every system)

Systems: **`claude`** (Cowork or Claude Code), **`codex`**, **`larry`** (steps only a human can do).

1. **Read this file on `origin/main` before any work.** If your branch is behind `origin/main`, merge main first. Never trust a plan's own "baseline" line over current main.
2. **No row, no work.** Every change belongs to exactly one row in §2. If no row fits, stop and ask Larry. Add a row yourself only when Larry's task tells you to.
3. **Claim before code.** A row counts as claimed once it is on main with your system as `Owner`, your branch in `Where`, and status `claimed`. Larry sets this when he dispatches the work, by editing the file on GitHub or with a docs-only PR.
4. **Scope is a lock.** While a row is `claimed`, `in-progress` or `review`, the paths in its `Scope` belong to that row. Do not edit them from any other row. If you have to, stop, add an entry to §4, and ask Larry.
5. **One plan per row.** Add dated progress entries to the row's plan. Do not write a new plan file for the same work. A new plan file needs a new row, and Larry approves it.
6. **Shared numbers are reserved in §3 first:** DB migration ids, allow-list rows, launchd labels, ports, new config keys. Take the next free number and record it in §3 in your branch's first commit.
7. **Production is deploy-only.** Nobody edits `~/jarvis-voice-ai-clean`. Work in your own worktree or clone. Production changes only through `scripts/deploy_main.sh` (see its note on the 24 Sep incident).
8. **Stay current and visible.** Merge `origin/main` into your branch at the start of every session and before any PR. Commit at the end of every slice. Work that exists only as uncommitted changes can't be seen or merged.
9. **Stay out of the other system's workspace.** Do not read from or write to another system's checkout or worktree. Handoffs go through this file and a PR.
10. **Update your row when its state changes.** Do this on your branch; it lands with your PR. On merge the row becomes `landed`, with the PR number and merge commit, and the plan's status header is updated to match.
11. **Status hierarchy:** this file (owner, state) > plan status header (design status) > receipts (evidence). When they disagree, correct the plan header, unless this file is the one that's wrong.
12. **Attribution:** every PR body names the system and its session link.

Claude has one extra rule: it never runs `git` against the Mac repo (see `CLAUDE.md`). Larry commits.

**Status values:** `proposed` → `claimed` → `in-progress` → `review` (PR open) → `landed` (on main) → `accepted` (Mac/live acceptance done). Also `blocked` and `parked`.

**Dispatching work (Larry):**
1. Add or edit the row on main.
2. Tell the system: *"Take WS-xx per ROADMAP.md."*
3. The system confirms that the row, branch and scope match, merges main, and starts.

---

## 1. Systems and workspaces

| System | Where it works | How work reaches main | Reads |
|---|---|---|---|
| `codex` | Worktrees of `~/Documents/Codex/2026-09-09/can/work/active-repo`. Current: `codex-isolated-20260924`, branch `codex/isolated-20260924`. | Larry pushes the branch and opens the PR | `AGENTS.md` |
| `claude` | Cowork: Linux VM plus a bridge to the Mac, never runs git on the Mac. Claude Code: a GitHub clone. | A branch or patch plus a commit-message file; Larry commits and pushes unless the session has GitHub access | `CLAUDE.md` |
| `larry` | The Mac, production, the vault, GitHub | Merges PRs; deploys with `scripts/deploy_main.sh` | — |

---

## 2. Workstreams

- Scope locks only while status is `claimed`, `in-progress` or `review`.
- "(proposed)" next to an owner means Larry has not yet confirmed who owns the row.
- † marks a plan that exists only on the owner's branch until that branch merges.

| ID | Workstream | Owner | Status | Where | Plan (one) | Scope (locked while active) | Next step | Updated |
|---|---|---|---|---|---|---|---|---|
| WS-01 | Verified gap closure GC24-00…06: execution lifecycle, privacy log redaction, memory admission, Atlas | `codex` | in-progress: main `2e6f769` integrated locally; acceptance open | `codex/isolated-20260924` | `docs/plans/MORTIMER_VERIFIED_GAP_CLOSURE_PLAN.md`†. The 12 gap-index plans fold into it (CX-05). | `jarvis/model_execution.py`, `jarvis/memory_admission.py`, `jarvis/runlog/`, `jarvis/agents/`, execution routes in `jarvis/admin/server.py`. GC24-03 logging edits touch the whole repo and resume only after CX-01. | All 31 conflict files resolved; merged native suites pass; Python has only two pending human deny-list failures | 09-28 |
| WS-02 | Subscription runtime isolation (GC24-04) | `codex` | in-progress: offline done, live gates open | `codex/isolated-20260924` | `docs/plans/MORTIMER_SUBSCRIPTION_RUNTIME_ISOLATION_PLAN_2026-09-25.md`† | `jarvis/subscription.py` | Land with WS-01; run status/subscription tests on the merged tree | 09-25 |
| WS-03 | Skills Workspace and skill creation (T6; supersedes `MORTIMER_SKILL_AUTHORING_PLAN.md`). **Its own view, separate from the Workflow Viewer** (Larry, 09-27) | `codex` | in-progress | `codex/isolated-20260924` | `docs/plans/MORTIMER_SKILLS_WORKSPACE_IMPLEMENTATION_PLAN.md`† | `jarvis/skill_*.py`, `jarvis/agent_skills.py`, `jarvis/selfedit/skill_policy.py`, `/api/skills*` in `jarvis/admin/server.py`. The five console view-mode Swift files are **shared with WS-07's landed Workflow Viewer**: add a new `skills` mode beside `workflows`; do not replace or restyle the viewer. | Larry approved 09-28: top-level Skills beside Workflows, Display menu, “open skills” and related-workflow links. Resolve Swift merge preserving both views | 09-27 |
| WS-04 | Remote access T2: bearer tokens, fail-closed bind, Tailscale | `codex` (Larry, 09-27) | in-progress **on Codex's branch only**; turning it on is an undecided roadmap item | `codex/isolated-20260924` | `docs/plans/MORTIMER_REMOTE_ACCESS_PLAN.md` (DRAFT) + **Addendum R1** (dormant-merge fixes, approved 09-27) | `jarvis/auth.py`, `jarvis/authmw.py`, `jarvis/bind.py`, `jarvis/urls.py`, `jarvis/bot/server.py`, auth middleware and bind in `jarvis/admin/server.py`. Plus the integration points in CX-11: `jarvis/bot/status_tool.py`, `scripts/deploy_main.sh` health checks, `mcp_servers/mcp_selfedit/logic.py` headers | Implement Addendum R1 (R1.2–R1.8) on the merged tree; done-when in R1.10. Turning T2 on and token setup (R1.9) wait for Larry | 09-27 |
| WS-05 | Model Use Enhancements MAR-A…J (checklist in §7) | `codex` (proposed) | proposed: foundation landed, live gates open | none yet | `docs/plans/MORTIMER_MODEL_USE_ENHANCEMENTS_PLAN.md` | `jarvis/model_routing.py`, `jarvis/model_preferences.py`, `config/model_access.yaml` | Larry confirms owner; MAR-A first | 09-22 |
| WS-06 | Self-service access and recovery P1–P7, plus registry split P5 (#86's files; merged in the 09-25 landing) | `claude` | landed; Mac checks open | main | Spec not on main (CX-09). Registry half: `docs/plans/MORTIMER_MODEL_REGISTRY_SPLIT_PLAN.md` | — | `larry`: 11 Mac checks from the handoff §4; decide the tier of `config/model_access.yaml` | 09-25 |
| WS-07 | Voice workflows phases 1–4, Workflow Viewer, #80 privacy fix, DEPLOY-MAIN | `claude` | landed (main `0b76f49`) | main | `docs/plans/MORTIMER_VOICE_WORKFLOWS_PLAN.md`, `docs/plans/MORTIMER_WORKFLOW_VIEWER_PLAN.md` | — | Correct the plan's status header (it still says "READY FOR HANDOFF") | 09-25 |
| WS-08 | Orb crystal glass (#90) | `claude` | landed; step 9 open | main | `docs/plans/MORTIMER_ORB_CRYSTAL_GLASS_PLAN.md` | — | `larry`: placement, Reduce Motion and rollback checks | 09-24 |
| WS-09 | Command Console and Atlas release acceptance | `larry` | open (Mac only) | — | `docs/plans/MORTIMER_COMMAND_CONSOLE_ATLAS_PLAN.md` | — | Follow `docs/acceptance/ACCEPTANCE_RUNBOOK.md` | 09-22 |
| WS-10 | Memory automation: staged enablement on the Mac | `larry` | pending merged-pipeline acceptance | — | `docs/plans/MORTIMER_MEMORY_AUTOCONSOLIDATION_PLAN.md` | — | CX-07 integrated locally; validate and choose staged Mac enablement before rollout | 09-27 |
| WS-11 | Adaptive interface C8 acceptance | `larry` | open (Mac only) | — | `docs/plans/MORTIMER_ADAPTIVE_INTERFACE_PLAN.md` | — | `docs/acceptance/adaptive-interface/RELEASE_READINESS.md` | 09-22 |

---

## 3. Reserved shared numbers

**DB migrations** (`jarvis/db.py`, `MIGRATIONS`). Migrations are tracked by id string and applied in list order. Never rename an id that may already be applied in production.

| Id | Name | Owner | State |
|---|---|---|---|
| 0001–0027 | … `0025_notices`, `0026_expire_retired_actions`, `0027_notice_memory_review` | — | on main; treat as applied in production |
| 0028 | `memory_admission_jobs` (was Codex `0025`) | WS-01 | reserved: renumber on merge |
| 0029 | `memory_classification_budget` (was Codex `0026`) | WS-01 | reserved: renumber on merge |
| 0030 | `memory_admission_shadow` (was Codex `0027`) | WS-01 | reserved: renumber on merge |
| 0031 | `agent_event_tool_call_identity` (was Codex `0028`) | WS-01 | reserved: renumber on merge |
| 0032 | `execution_action_claims` (was Codex `0029`) | WS-01 | reserved: renumber on merge |
| 0033 | `skill_events` (was Codex `0030`) | WS-03 | reserved: renumber on merge |
| 0034 | `client_tokens` (was Codex `0031`) | WS-04 | reserved: renumber on merge. The table is harmless while auth is dormant. Also update the Remote Access plan's cross-plan guard |
| 0035 | (T5 mail/calendar) | backlog | reserved |
| 0036 | `skill_step_check_receipts` (was Codex `0032`) | WS-03 | reserved 09-28; production read-only check confirms no Codex ids applied |
| 0037+ | free | — | take the next one and write it here |

Before renumbering, confirm on the production database that none of Codex's seven ids was ever applied: `SELECT id FROM migrations ORDER BY id;`

**Self-edit allow-list rows:** owned by `docs/plans/ALLOWLIST_SEQUENCE.md`. That rule is unchanged: every allow-list change is a human commit.

---

## 4. Conflict register

Open means not yet resolved. Each entry names who resolves it.

| ID | Conflict | Resolves | State |
|---|---|---|---|
| CX-01 | Codex's worktree is based on `977f50b` and lacks #86 and the voice-workflows landing (`jarvis/status/`, `notices.py`, `voice_workflows.py`, …). 24 `jarvis/` files changed on both sides. | `codex`: commit, then merge `origin/main` | resolved locally 09-28; all conflicts reconciled |
| CX-02 | Migration ids `0025`–`0027` collide between main and Codex's tree. | `codex`: renumber per §3 | resolved locally 09-28; upgrade/idempotency tests pass |
| CX-03 | `jarvis/workflows.py`: main has triggers, priority and draft; Codex has redacted parse-failure logs. Keep both. Same care applies to all 24 files in CX-01. | `codex` during the merge | resolved locally 09-28; workflow and privacy tests pass |
| CX-04 | Workflow Viewer (landed) and Skills Workspace (in progress) both add a console view through the same five Swift files. | `larry`: **two separate views** (09-27). `codex` adds `skills` as its own mode in WS-03 | decided |
| CX-05 | 12 gap-index plans in Codex's tree that overlap `MORTIMER_VERIFIED_GAP_CLOSURE_PLAN.md` and each other. Fold them into `MORTIMER_VERIFIED_GAP_CLOSURE_PLAN.md`, or archive them with a pointer. | `codex` | resolved locally 09-28: 12 originals archived with redirects and canonical topic index; merge pending |
| CX-06 | T2 code was being written while `MORTIMER_REMOTE_ACCESS_PLAN.md` still says DRAFT. | `larry` (09-27): Codex keeps owning T2; turning it on stays undecided | decided |
| CX-07 | Memory admission is designed in two places that do not know about each other. On main (Claude): the echo guard at extraction, and auto-settle of contradictions in the sweep, with a model call, notices and `memory_restore`. In Codex's worktree (GC24-05): a durable admission queue (extract → classify → apply) with a model classifier on a confidential route. Codex's `memory_extraction.py` lacks the echo guard, and its `memory_sweep.py` lacks auto-settle. See the evaluation's addendum. | `codex`: approved echo guard → durable classification/admission → saved memory → automatic contradiction settlement | decided by Larry 09-28; integration implemented, 333 targeted tests pass |
| CX-08 | Status files have forked: `docs/acceptance/IMPLEMENTATION_STATUS.md` is 7 KB on main and 50 KB in Codex's tree. | whoever merges WS-01 | resolved locally 09-28: concise current status; both original histories archived; merge pending |
| CX-09 | #86 cites `docs/plans/MORTIMER_SELF_SERVICE_ACCESS_IMPLEMENTATION_SPEC.md`, which is not in main's `docs/plans/` or `docs/archive/`. | `claude` or `larry`: add it, or record where it lives | open |
| CX-10 | #86's branches were built inside Codex's checkout, and the voice-workflows plan calls #86 "Codex's". | Protocol rules 9 and 12 | closed by protocol |
| CX-11 | Codex's T2 code against what Claude landed on main. (1) `JARVIS_AUTH_ENABLED` **defaults to true**, with no exempt routes, loopback included, so merging it turns auth on. (2) Main callers that send no token would then get 401: `jarvis/bot/status_tool.py` (the `system_status` tool from #86) and `scripts/deploy_main.sh` phase D, whose health checks expect 200 from `/api/health` and 200/307 from the bot, so the deploy would stop. (3) The route inventory in Codex's tree has 64 sidecar routes; main has 68 decorators, including 10 Codex's copy lacks: `/api/status/*` (9) and `/api/workflows`. (4) `mcp_servers/mcp_selfedit/logic.py`: Codex added service headers; main's copy also changed, so keep both. (5) Token setup is by CLI only (`python -m jarvis.auth add`), which conflicts with the no-shell-commands principle behind Claude's voice workflows (D-L2/D-L5). The native app already sends a Keychain token on every request (`JarvisHTTP.swift`), so it needs no code change, only a stored token. | `codex`: Addendum R1 fixes (1)–(4); `larry` decides (5) when T2 is decided (options in R1.9) | plan approved; implementation open |

| CX-12 | Merge reconciliation must carry the three streaming flags from Codex's former live registry into the split live profiles, while preserving main's historical migration fixtures unchanged. Earlier source attribution to main was incorrect: Git rename merging had carried the flags into the historical YAML. | `codex` under WS-01, approved by Larry | resolved locally 09-28: three live flags restored; original fixtures preserved; explicit overlay regression passes |

---

## 5. Backlog (unclaimed)

Nobody works on these until Larry turns one into a §2 row.

- **T2 remote access: switching it on** (undecided). Codex builds it dormant under WS-04; turning it on, and how you get tokens without shell commands (CX-11 item 5), is a later decision.
- **T1.3 native client hardware verification** V3–V9: `MORTIMER_NATIVE_CLIENT_APP_PLAN.md` §8.
- **T1.4 web retirement:** `MORTIMER_WEB_RETIREMENT_PLAN.md` (DRAFT).
- **T3 local voice and Mac mini:** `MORTIMER_LOCAL_VOICE_AND_MINI_PLAN.md` (DRAFT; needs the hardware).
- **T4b sensitive tier:** gated on G3. Larry's rule: no financial piece until models run locally on the mini.
- **T5 mail, calendar and daily brief:** `MORTIMER_MAIL_CALENDAR_BRIEF_PLAN.md` (DRAFT). Codex edited the plan document on 09-26; no mail code was found. Migration `0035` is reserved.
- **Personal VAD / speaker gate:** built and switched off pending the §6 effectiveness protocol (see §7 below).
- **Optimization plan Rev 3.6:** remaining phases not reconciled in this pass.

---

## 6. Recently landed

- 09-25: voice workflows phases 1–4, Workflow Viewer, #80 privacy fix, `scripts/deploy_main.sh` (WS-07). Main is now `0b76f49`.
- 09-25: self-service access and recovery (#86's files, merged as-is in the same landing, WS-06).
- 09-24: orb crystal glass (#90, WS-08).
- Earlier: see `docs/plans/implemented/` and `docs/archive/README.md`.

---

## 7. Deferred features with revisit criteria

*Carried over unchanged from the previous `ROADMAP.md` (headings demoted one level). Each item still needs its own plan and a §2 row before anyone builds it.*

### Mortimer roadmap — deferred features with revisit criteria

Standing list of decided-but-not-yet-built directions. Each entry names
its trigger — the observable condition that says "build this now" —
per the discipline in MORTIMER_VOICE_UI_PLAN.md §7. Items here have had
their *direction* decided in discussion with Larry; each still gets its
own plan doc before implementation.

#### Model Use Enhancements (added 2026-09-20)

- [ ] **MAR-A** — Reconcile the deployed Mac checkout and capture live
  baseline evidence.
- [ ] **MAR-D** — Finish the broader tool-result/continuation privacy audit.
- [ ] **MAR-E** — Validate SAYGM credentials, catalog, and confidential
  synthetic inference.
- [ ] **MAR-F** — Re-authenticate Claude and validate subscription capabilities
  and account isolation.
- [ ] **MAR-G** — Produce enabled-mode runtime evidence across all routed
  non-voice call sites.
- [ ] **MAR-H** — Complete live voice route-control acceptance.
- [ ] **MAR-I** — Run the research, development, and confidential-memory pilot.
- [ ] **MAR-J** — Complete latency, quality, privacy, rollback, and deployed
  release evidence.

- [x] **MAR-B/C foundation** — Model/route/workload contracts and the
  provider-neutral execution boundary are implemented and covered by tests.
- [x] **MAR-D foundation** — Policy-aware run-log/council redaction and
  protected delegation activity-event handling are implemented.
- [x] **MAR-F foundation** — Gated Claude/Codex text adapters isolate
  subscription subprocesses from inherited API credentials and endpoints.
- [x] **MAR-H foundation** — Sidecar, native Repo controls, route metadata,
  and the gated voice preference tool share the same draft/confirm store.

See the detailed [Model Use Enhancements plan](docs/plans/MORTIMER_MODEL_USE_ENHANCEMENTS_PLAN.md)
and [acceptance status](docs/acceptance/model-use-enhancements/STATUS.md) for
evidence, test counts, and exact handoff commands.

**Status:** In progress. The routing foundation, SAYGM catalog parser,
privacy checks, provider-neutral execution contract, and read-only route
status are implemented behind `JARVIS_MODEL_ROUTING_ENABLED=1`; the sidecar
and native API now expose draft-confirmed persistent route controls. Live
provider credentials, subscription capability validation, runtime-enabled
evidence, and release deployment remain open.
The document records manual per-model and per-workload subscription/API
selection, separate Claude/Codex subscription adapters, SAYGM confidential
inference, privacy enforcement, and quality/latency acceptance.
Haiku voice orchestration, Deepgram, and ElevenLabs retain their existing
routes. No silent paid fallback or downgrade in privacy or model quality.

**Trigger to build:** Implementation is requested after the saved plan is
reviewed. Begin with MAR-A's deployed-backend reconciliation and baseline;
model availability and provider limitations are explicit validation gates.

#### Personal VAD — speaker-gated turn-taking (added 2026-08-16)

**Status (2026-09-22): BUILT, gated OFF.** Shipped 2026-08-22 (`88d58bc`)
as the Tier-2 speaker gate of `docs/plans/MORTIMER_VOICE_ISOLATION_TIER12_PLAN.md`,
with windowed scoring added by `MORTIMER_GATE_V2_AND_MODEL_REQUEST_PLAN.md`:
`jarvis/speaker.py` (local SpeechBrain ECAPA-TDNN embeddings, CPU, file-based
`python -m jarvis.speaker enroll|verify|status`) and
`jarvis/bot/speaker_gate.py` (`SpeakerTap`, `TranscriptGate`, and
`SpeakerVerifiedMinWordsTurnStartStrategy`, which makes barge-in while the
bot is speaking require a passing speaker score). `JARVIS_SPEAKER_GATE_ENABLED`
defaults to false and stays off until the plan's §6 effectiveness protocol
is run (`docs/acceptance/adaptive-interface/RELEASE_READINESS.md`). Still
unbuilt from the scope below: wake-word follow-up gating (nothing in
`jarvis/wakeword/` or `WakeWordListener.swift` consults the speaker
profile); turn-END gating as such (an unknown voice can still open and close
a turn while the bot is quiet — its transcript is dropped instead); and a
calibration command — the threshold is a fixed default
(`JARVIS_SPEAKER_THRESHOLD`, 0.40), with `JARVIS_SPEAKER_CAPTURE` recording
turn audio only as a calibration aid. The text below is the original
decision record.

**What:** local speaker recognition (enroll ~30s of Larry's voice once;
ECAPA-TDNN/resemblyzer-class embeddings, CPU, no cloud — same
local-first pattern as openwakeword) used to GATE turn-taking
decisions: only the enrolled speaker's voice may barge in, end a turn,
or follow a wake-word activation. It gates ACTIONS, not audio — STT
still runs on everything (no added first-word latency); interruption
and turn-end signals are suppressed unless the active speech segment
matches the enrolled profile.

**Why:** noise suppression (Workstream A) removes non-speech and the
VAD detects any speech — neither can reject the wrong HUMAN (TV,
another person, playback). Observed symptom: four consecutive
"[system] Your previous reply was interrupted" notices in one session
(logs/bot.log, 2026-08-16 19:41) — spurious barge-ins are the concrete
problem this solves.

**Boundaries decided in advance:** this is a UX filter, never
authentication — spoofable by recordings and degraded by illness or
distance, so it must never gate confirmation actions (commits, pushes,
submits). Threshold must be calibrated from logged data, not
hand-tuned (the PROCEDURE_MATCH_THRESHOLD `--calibrate` discipline),
with false-rejection (ignoring Larry from across the room) weighted as
the worse failure. Sequenced after or alongside the noise-suppression
workstream — NS cleans the signal, which makes the embeddings more
reliable.

**Trigger to build:** spurious barge-ins recur in normal use after the
VAD stop_secs tuning and (if enabled) noise suppression are in place —
i.e. this is the fix for the wrong-voice case specifically, not the
first lever to pull.

#### Other standing deferrals (pointers)

- **Native macOS client:** SUPERSEDED 2026-08-25 by the full-Swift
  decision (`docs/plans/MORTIMER_PLATFORM_ROADMAP.md` T1,
  `docs/plans/MORTIMER_NATIVE_CLIENT_CORE_PLAN.md`).
- **Voice UI deferrals:** local fast-path grammar, Window Management
  API auto-detect, named multi-windows, voice help tour, auto-hide
  chrome, speech-reactive overlay opacity — MORTIMER_VOICE_UI_PLAN.md
  §7 (revisit criteria there).
- **Council for app-scaffolding:** no trigger exists yet by design —
  CLAUDE.md's council section, "do not invent a trigger for it."


---

## 8. Change log

- 2026-09-27: Claude (Cowork) turned this file into the master tracker: protocol, workstreams WS-01…11, migration reservations, conflict register CX-01…10. Reconciled against main `0b76f49` and Codex's worktree `codex/isolated-20260924`. The previous content (deferred features) is §7, unchanged. Owners marked "proposed" await Larry's confirmation.
- 2026-09-27 (later): Larry's decisions. **CX-04:** workflows and skills are different objects, so they get separate views; WS-03 adds its own `skills` mode, with layout options shown before any Swift UI is built. **CX-06:** remote access (T2) is an undecided roadmap item; WS-04 is parked and Codex's T2 code moves to a parked branch; migration `0034` is held. CX-07 rewritten with the verified details.
- 2026-09-27 (later still): Larry: T2 stays with Codex. WS-04 is back to `codex`, in-progress on its branch, and will merge only dormant (auth off by default) until Larry decides to turn it on. The parked-branch step is removed. CX-11 lists the conflicts between T2 and Claude's landed work.
- 2026-09-27 (evening): Larry approved the recommended fixes. Addendum R1 is appended to `MORTIMER_REMOTE_ACCESS_PLAN.md`: auth off unless set to "true"; a service token for `system_status`; both sides kept in the watchers and `mcp_selfedit`; a guard test for unauthenticated internal callers; authenticated DEPLOY-MAIN health checks (`scripts/service_health.py`); migration `0034`; the route inventory recounted. WS-04 and CX-11 point to it.

- 2026-09-28: Codex WS-01/03/04 integration on `codex/isolated-20260924`: 22 of 31 conflicted files resolved; remaining nine are memory/CX-07 and Swift/navigation. Main remains `2e6f769`. Architecture and repo map now fit injected prompt caps. Targeted workflow, validation, auth, subscription, web and bundle checks pass; full suites await a coherent merged tree. R1 synthetic health/caller/token checks: 14 pass, human deny-list gate still fails as expected pending W1-REMOTE-HEALTH. No deployment or activation.

- 2026-09-28: Codex CX-08 reconciled the implementation-status fork: one current 5.8 KB status linked to ROADMAP and per-workstream evidence, with both the main and isolated-branch originals preserved in docs/archive. Historical full-suite counts and failed verifier evidence are explicitly separated from current targeted checks.

- 2026-09-28: Codex CX-05 archived the twelve overlapping F7 gap indexes with lossless body/link verification and redirects. Root independently verified all twelve normalized bodies against HEAD and 217 archive/stub links. Canonical index links were also checked by the docs agent (269 links total). Documentation regression checks: 16 pass; the endpoint integration check remains blocked by unresolved memory imports. Architecture (10,387 chars) and repo map (6,190 chars) retain required references within their prompt caps.

- 2026-09-28: Larry confirmed CX-07 ordering and Codex ownership, WS-03 separate top-level navigation, and CX-12 restoration of the three original Anthropic streaming flags. Implementation resumed in the isolated merge worktree; these approvals do not enable production features or authorize paid evaluations.

- 2026-09-28: Codex completed all merge resolutions. Final broad Python run: 4,851 passed, 2 expected pending human deny-list failures, 4 skipped. Subsequent historical-fixture correction/streaming-overlay regression: 59 passed, 3 legitimate migration-snapshot skips. JarvisKit: 219/0 failures. MortimerHost: 372 executed, 7 skipped, 0 failures. Evidence is in `docs/acceptance/skills-workspace/receipts/main-integration-2026-09-28/`; no deployment/activation, paid evaluation, physical-display acceptance or full release claimed.
