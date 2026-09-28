# Mortimer architecture reference

**Reference status:** source map, added 2026-09-18. **Last source audit:**
2026-09-22 against `main` `88b206f`; the runtime-checkout observations under
"Configuration and deployment paths" (2026-09-17/18) were not re-observed.
A navigation aid; track plans stay authoritative for requirements and gates.

**Skills workspace candidate supplement, refreshed 2026-09-28:** the current
isolated worktree adds read-only skills catalog/detail/version APIs, typed
privacy-safe selection/body-read traces, user-scoped run/event APIs and native
Activity and Versions views alongside the native Skills view. The Versions view
distinguishes human manifest version, package SHA-256, enabled registry pin and
caller-owned candidate requests; it does not claim activation or historical
installed revisions. A versioned `SkillStepCheckReceipt` contract now uses a
process-local HMAC, exact run/request/skill-revision/step/attempt identity,
two-minute expiry, a host-owned check registry/map, and durable one-shot
replay protection. The checker registry maps exact weather-condition,
repository-status, repository-history, and creator offline-validation steps to
host checks. Other steps remain unknown until independent host evidence is
implemented and bound to the owning attempt. Successful tool
calls alone are observations. The opt-in deterministic selector
requires both rollout flags and verified route, tool, capability, package-pin,
readiness and privacy evidence; explicit skill IDs skip lexical scoring only.
It selects one primary and at most one support, and only when both packages
mutually declare compatibility and their combined body fits the fixed prompt
budget. Current packages declare no mutual skill-pair compatibility, so they
remain single-skill. Public dry-run evidence covers five positive, five no-skill
and four overlapping cases with no provider calls. The package snapshot is cached
for 60 seconds; measured warm selector p95 is 4.39/4.37 ms across 100 synthetic
skills. Same-pin expiry refresh runs in a background worker while package pins
are rechecked before injection; registry changes rebuild synchronously.
Declared matcher examples return
only bounded synthetic request/expected-selection previews after declaration,
fixture-schema and package-pin checks; they never execute a skill or model.
Voice can open a declared process step or example and hand a bounded draft to
the native creator review, but cannot publish or activate. Version API evidence
is limited to the current package/config and owner-scoped request receipts; no
previous installed package/Git history is returned. Activation and rollback
still require evaluation evidence and a maintainer-reviewed config change.
Trusted step evidence, live creator evaluation, readiness evaluation, activation
and rollback remain open. It is not yet merged or deployed; see the [implementation
plan](plans/MORTIMER_SKILLS_WORKSPACE_IMPLEMENTATION_PLAN.md) and [acceptance
status](acceptance/skills-workspace/STATUS.md).

Creator drafts use the owner-scoped job receipts in `jarvis/skill_requests.py`.
The admin service prepares the disposable sandbox, then uses the authenticated
internal endpoint in `jarvis/bot/server.py` to reach the live Developer through
`jarvis/bot/skill_creator_dispatch.py`. That registry carries the actual user's
identity and session privacy holder. The Developer's RunLogger generates the
run ID; an atomic admin association binds it to the creator request, pinned
creator revision and separate sandbox job before tool execution. The run has
only the four creator tools; the authoring service checks the expected job at
session resolution. Scrubbed lifecycle messages retain this run ID through
JarvisKit and the native AgentRunStore, so a completed creator run cannot settle
another concurrent Developer card. Late validation uses `jarvis/skill_validation_activity.py` to append to the
originating run without changing its terminal row. The worker records an
attempt before validation, and the saved host receipt binds the request,
attempt and sandbox job. Recovery never invents a missing started event. An
exact pinned host check rechecks complete candidate evidence before a signed
receipt is accepted; job locking, owner/privacy checks, transactional event
ordering and one-shot receipt storage cover cancellation and duplicate delivery.
This path has local fake-VM integration coverage; live acceptance remains open.

## Runtime shape

```mermaid
flowchart LR
  MIC[Microphone / PTT / wake word] --> BOT[Pipecat bot :7860]
  BOT --> SUP[Supervisor / orchestrator]
  SUP --> AGENTS[Specialists and developer]
  AGENTS --> MCP[MCP skill subprocesses]
  BOT --> MEM[Admission, extraction, automation]
  MEM --> DB[(data/jarvis.db)]
  BOT --> TTS[ElevenLabs or configured TTS]
  BOT --> UI[RTVI over /ws-client WebSocket or WebRTC]
  UI --> HOST[MortimerHost native Command Console]
  HOST --> ATLAS[Knowledge Atlas, graph, sidecar, content panels]
  HOST --> SKILLS[Skills library and intended process view]
  HOST --> SHARE[Text/image staging and OS share]
  HOST --> DISPLAY[NSScreen placement]
  HOST --> SIDE[Admin sidecar :7861]
  SIDE --> EDIT[Sandbox/self-edit and planning]
  SIDE --> SKCAT[Read-only skill catalog/detail/version evidence]
  SIDE --> DB
  VAULT[Mac Keychain + data/secrets.vault] -. injects process env .-> BOT
  VAULT -.-> SIDE
  KB[Separate mortimer-vault :8484] --> AGENTS
```

Transport: `jarvis/bot/bot.py` serves `/ws-client` (WebSocket,
`ws_transport.py`) and `/api/offer` (SmallWebRTC). For a loopback bot
`JarvisClient` defaults to `NativeAudioTransport` over `/ws-client`;
`JARVIS_FORCE_WEBRTC` is the rollback, and a remote bot uses WebRTC.

The bot owns the voice session, Supervisor turn, tool registration, memory
session lifecycle and speech output. `MortimerHost` owns native windows,
layout, drawer tabs, Atlas/graph state, display placement and content
sharing. The admin sidecar owns self-edit, planning, run status and
HTTP inspection. The Skills view reads validated package metadata, process
maps, version pins and owner-scoped candidate receipts from the sidecar;
synthetic examples preview expected selection without
running a skill, and intended steps do not prove that a run completed them.
Trusted pass receipts are persisted in the `skill_step_check_receipts` table
under migration 0032 and are erased with protected-run transitions or run
retention pruning. Receipt infrastructure does not turn tool results or
model-authored activity into verified step success.
MCP servers are subprocesses with declared credentials and
no UI state. SQLite durably owns conversations, memories, jobs, receipts and
run metadata.

Layout 2 (`CommandConsoleView`) is the default. Layouts 0/1 and the frozen
web console (`scripts/run_web.sh`) stay as rollback until the Command Console
physical and daily-driver gates close.

The self-edit planner and `inject_repo_map` sub-agents receive this file,
capped at 12,000 chars, with `docs/REPO_MAP.md`. `GET /api/architecture`
serves it and the Repo sidecar renders it with its SHA-256; both read on
demand, keep no copy and grant no edit authority.

## Trust and data boundaries

- The bot and sidecar bind to localhost; remote access is a separate track.
- User speech is transient audio, transcript input and (when enabled) a local
  conversation row. Memory admission is bounded, redacts credential patterns,
  and applies source-role and evidence policy before durable promotion.
- Memory classification gets bounded redacted candidates and returns metadata
  only; it cannot grant permissions, write content or override a user
  correction. Shadow receipts hold a digest and metrics, not candidate text.
- Inbound text/image is staged locally and needs an explicit approval
  manifest before provider delivery; imported content and derived results are
  ephemeral.
- Outward sharing freezes the selected result before opening the OS picker;
  opening a picker is not reported as delivery.
- `jarvis.vault.inject_env()` loads secrets from `data/secrets.vault` and the
  macOS Keychain. A running checkout may set `JARVIS_VAULT_PATH`; secrets are
  never copied into candidate worktrees or committed to `.env`.

## Model routes

No single project-wide model setting exists. `OPENAI_MODEL`/`OPENAI_BASE_URL`
(`jarvis/config.py`) configure only the voice Supervisor.

- `config/model_access.yaml` + `jarvis/model_routing.py` separate model
  identity from access route (`direct_api`, `subscription`,
  `codex_subscription`, `saygm`, `local`) and workload privacy.
  `JARVIS_MODEL_ROUTING_ENABLED` defaults to false while adapters are
  qualified; overrides are `JARVIS_MODEL_ROUTE_<WORKLOAD>` and
  `JARVIS_MODEL_PROFILE_<WORKLOAD>`.
- `jarvis/saygm.py`: a SAYGM route is confidential only when the catalog
  confirms `tier: confidential` and the `-TEE` suffix; other SAYGM routes are
  external processing. `GET /api/model-routes` shows status without secrets.
- `scripts/verify_model_access.py` checks key presence without printing
  secrets (contacts providers only with `--saygm`/`--probe-subscriptions`);
  `scripts/audit_model_call_sites.py --require-covered` fails on an
  unclassified production completion call site.
- `jarvis/privacy_policy.py` enforces local-only/confidential/approved-external
  before a request; `jarvis/model_execution.py` is the provider-neutral
  contract; tool permissions stay with agent and sandbox layers.
  `jarvis/model_preferences.py` holds drafts and confirmed choices for the
  Repo sidecar and gated `model_route` voice tool. Council, planning and
  shadow calls reject a route that fails a stricter `data_policy`; enabled
  confidential/local-only policies also redact the run log.
- Skill evaluation is an isolated `skill_eval` background workload: it requires
  both an enabled `skill_evaluation` budget block and
  `JARVIS_SKILL_EVAL_ENABLED=1`, ignores model preferences, rejects route
  overrides, and has no fallback. No such block is configured in the current
  access policy, so the workload remains unavailable. Paid calls require a
  numeric spend ceiling and a known price at per-call reservation.
- `claude-haiku-4-5` is a voice-only built-in route, absent from the registry.
- Claude/Codex subscription adapters are text-only (tool calls rejected);
  `jarvis/subscription.py` strips inherited API keys and endpoints before the
  CLI launches, so subscription traffic cannot become paid API traffic.
  Protected delegation text is masked in activity events and native UI.
- With the per-turn sensitive latch armed, the MCP registry refuses external
  web, app, screen-vision and self-edit servers; local tools stay usable.

| Workload | Source of selection | Current policy | Credential/endpoint behavior |
| --- | --- | --- | --- |
| Voice Supervisor/orchestrator | `OPENAI_MODEL`, `OPENAI_BASE_URL`, `jarvis/bot/pipeline.py` | Haiku dispatcher; delegates, never builds | Voice configuration and its provider key |
| Scheduler, Librarian, Analyst, Systems | `config/agents.yaml` → `claude-sonnet-5` | Refuse on missing profile/key; no Supervisor fallback | `config/upgrade_models.yaml` profile route |
| Developer, App Builder | `config/agents.yaml` → `claude-opus` | Refuse on missing profile/key; build-grade model | Registry profile route |
| Optional Codex subscription workload | explicit `codex-subscription` profile + `codex_subscription` route | Text-only until tools are validated; no API-key fallback | Authenticated Codex CLI subscription |
| Planner/self-edit executor | `JARVIS_UPGRADE_PROFILE` / `JARVIS_APPBUILD_PROFILE`, registry default per plan | Profile and refusal/fallback recorded in the sidecar | Registry profile route |
| Research comparison writer | `JARVIS_PLANNING_PROFILE` → registry default | Never the voice Supervisor; profile recorded with the result | Registry profile route plus Tavily crawl |
| Council | `jarvis/council/config.py` plus registry pool | Council exclusion and tier rules | Per-profile registry route |
| Vision | `vision` workload in `config/model_access.yaml` if routing is on, else `JARVIS_VISION_PROFILE` | Image-capable profile required; else fails closed | Validated registry profile route |
| Background extraction and maintenance sweep | `jarvis/memory_extraction.py`, `jarvis/memory_sweep.py` | `JARVIS_MEMORY_PROFILE` route, default registry `claude-sonnet-5`; fails closed without its credential | Profile route via `jarvis/memory_model.py` |
| Knowledge-base digest and procedure description | `jarvis/kb_digest.py`, `jarvis/procedures.py` | `JARVIS_BACKGROUND_PROFILE` route, default registry `claude-sonnet-5`; never inherits the Supervisor route | Profile route via `jarvis/memory_model.py` |
| New memory classifier shadow and staged rollout | Live bot: `heuristic_classifier` in `jarvis/memory_automation.py` (no model). Model classifier only in `scripts/run_memory_provider_shadow.py --profile NAME` | Admission ordered by `JARVIS_MEMORY_AUTOMATION_STAGE` (`shadow` → `explicit_preferences` → `corroborated_inferences`); unknown fails closed | Shadow profile supplies model, provider, endpoint, key, temperature |

Haiku is reserved for the voice Supervisor; no profile in a background row
may resolve to it. Each background family is independently selectable. Provider
shadow receipt: `docs/acceptance/memory-automation/provider-shadow-receipt.json`
(2026-09-18, profile `claude-sonnet-5`, 8/8 cases, no regression, live
database untouched, production automation disabled). To re-run it, dry-run
first (no credentials read, no provider call):

```sh
UV_CACHE_DIR=/private/tmp/jarvis-uv-cache uv run \
  --with-requirements requirements-lock.txt \
  python scripts/run_memory_provider_shadow.py --profile kimi-k3 --dry-run
```

A live run drops `--dry-run`, from the runtime checkout or with its vault
passed explicitly; never copy the vault into the release-review checkout.

## Configuration and deployment paths

Source verification normally uses the candidate worktree
`/Users/larryfix/Documents/Codex/2026-09-09/can/work/release-review`. The
runtime checkout inspected 2026-09-18 is `/Users/larryfix/jarvis-voice-ai-clean`
(vault `data/secrets.vault`; `.env` voice route `https://api.anthropic.com/v1`,
`claude-haiku-4-5`). Keep them separate; `JARVIS_VAULT_PATH` bridges a
candidate command to the runtime vault.

Candidate work is isolated and verified in `sandbox/runtime.py`/`session.py`
before a draft PR. The release checklist records candidate
revision, deployment fingerprint, test receipt and rollback target; a passing
source test does not prove the Mac runs that candidate. The observed launchd
bot ran from the runtime checkout with its own database and vault; its
2026-09-17 log shows the live Supervisor is `claude-haiku-4-5` but not that the
candidate's Command Console or memory route is loaded. A Codex-shell display
probe saw zero `NSScreen`s (headless, not a physical result). Deployment and
loaded-version evidence remain open gates.

## Where to verify each surface

| Surface | Implementation | Acceptance evidence |
| --- | --- | --- |
| Native Command Console / Atlas | `macos/MortimerHost/`, `macos/JarvisKit/` | `docs/acceptance/command-console/STATUS.md`, physical Mac gates |
| Skills workspace (candidate) | `jarvis/skill_catalog.py`, `/api/skills`, `MortimerHost/Console/SkillsWorkspaceView.swift` | `docs/acceptance/skills-workspace/STATUS.md`; activity, creator and live release gates open |
| Voice and shared actions | `jarvis/bot/`, `ConsoleProtocol` | `docs/acceptance/command-console/VOICE.md` |
| Memory admission and automation | `jarvis/memory.py`, `jarvis/memory_automation.py`, `jarvis/memory_sweep.py` | `docs/acceptance/memory-automation/STATUS.md` |
| Provider shadow | `scripts/run_memory_provider_shadow.py`, registry | `provider-shadow-receipt.json`, `rollout-monitoring-receipt.json` (same directory) |
| Self-edit sandbox | `sandbox/`, `jarvis/selfedit/`, admin sidecar | adaptive-interface release readiness |
| Secrets | `jarvis/vault.py` | vault unit/integration tests and Mac status check |
| Display topology | `ScreenPlacement`, `run_display_topology_probe.sh` | physical display receipt; Spaces are not `NSScreen`s |
| Plan artifact integrity | `tests/unit/test_plan_manifests.py` | required plan artifacts exist (rendering-suite filename alias documented) |

Superseded plans and snapshots (e.g. the 2026-09-04 architecture snapshot)
are history in `docs/archive/`.

## Known open gates

Documentation closes no acceptance work. Memory automation has passing
provider-shadow and offline rollout receipts but still needs gradual Mac
enablement with redacted live benefit/cost evidence. The Command Console needs
physical display recovery, system sharing, VoiceOver/accessibility, deployment
identity and daily-driver evidence. These stay in the release-readiness
checklist; unit tests alone never check them off.
