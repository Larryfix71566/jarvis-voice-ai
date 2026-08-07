# Jarvis Upgrade Plan — Self-Extending Agent Framework

Status: LOCKED (v1.0) · Date: 2026-08-07 · Supersedes: none (extends `Jarvis_Voice_AI_Agent_Implementation_Plan.md`)

## §0 Governance (inherited)

Same rules as the base implementation plan:

1. Phases execute in order; each phase has explicit exit gates.
2. Commit only after all gates for the phase pass.
3. Deviations from this plan must be wiring-level, recorded in `DEVIATIONS.md` before commit.
4. Secrets live only in `.env` / macOS Keychain — never committed, never echoed to logs.
5. Every externally visible action Jarvis takes is auditable after the fact.

---

## §1 Current-state seams (what we build on)

The base system already provides, verified in acceptance:

- **Declarative roster** — `config/agents.yaml` (`sub_agents:` name, display_name, mcp_servers, description). `build_delegate_tool` generates delegation from this roster.
- **Per-session SkillRegistry** — stdio MCP children spawn on WebRTC connect, reaped on disconnect. Consequence: a newly registered skill becomes available **on next reconnect** with no bot restart. (Verify in U1-G3; believed free.)
- **One-folder skills** — `mcp_servers/mcp_<name>/{logic.py, server.py}`; pure logic separated from transport.
- **Config-only provider switch** — `OPENAI_BASE_URL` / `OPENAI_MODEL` (proven: Kimi → Claude Haiku with zero code change).
- **Env validation** — `scripts/check_env.py`; **persistent store** — `spoken.db` with migrations.
- **Web console** — Vite/React on 5173, Pipecat WebRTC to bot on 7860.

---

## §2 Skill classes

Two classes of skill, distinguished by failure mode:

| | **Standard** (existing 5) | **Privileged** (new) |
|---|---|---|
| Blast radius | Local, reversible | External / system-visible |
| Examples | time, notes, web search | Gmail send, calendar write, shell/system changes |
| Credentials | API keys in `.env` | OAuth tokens in **macOS Keychain** |
| Execution | Single tool call | **Draft → confirm → commit** (§5.2) |
| Audit | Logs | `actions` table, mandatory (§5.3) |
| AuthZ policy | `none` | `confirm` default, stiffenable (§5.4) |

A skill's class is declared in its manifest (§3.1) and enforced by the registry, not by convention.

---

## §3 Layer 1 — Formalize the framework

### 3.1 Skill manifest

Every `mcp_servers/mcp_<name>/` gains `skill.yaml`:

```yaml
name: mcp-gmail
version: 0.1.0
class: privileged            # standard | privileged
tools: [gmail_search, gmail_read_thread, gmail_draft_send, gmail_commit]
requires_env: []             # checked by check_env.py
requires_keychain: [google-oauth-jarvis]
scopes: [gmail.readonly]     # declared, verified at auth time
test: "python3 -m pytest mcp_servers/mcp_gmail/tests -q"
```

### 3.2 Registry validation

New `scripts/check_skills.py`: every `mcp_servers` reference in `agents.yaml` resolves; every skill has a manifest; every manifest's `requires_env`/`requires_keychain` is satisfiable; every skill's smoke test passes. Runs in CI-style gate and on `jarvis doctor`.

### 3.3 Agent additions

Adding a sub-agent = `agents.yaml` entry + description only. Validator confirms delegation schema still generates. No code changes permitted for roster-only additions.

---

## §4 Layer 2 — Workflows

### 4.1 Phase A: scheduled prompts (build first)

Reminders already have `delivered` state and DB persistence. Extend: a reminder whose payload is a **prompt** injected as a user turn on delivery.

- Voice: "Every weekday at 7am, brief me on today" → recurring reminder → fires → injects "brief me" → supervisor delegates (Scheduler + Analyst) → speaks result.
- Delivered-when-disconnected behavior matches run24 precedent: deliver on next connect, merged into greeting.

### 4.2 Phase B: workflow graphs (only when 4.1's limits bite)

`config/workflows.yaml`: triggers (cron / voice phrase / event) → step graphs with agent routing. Deferred until a concrete need exists that scheduled prompts cannot express.

---

## §5 Layer 3 — Privileged skills & authorization

### 5.1 Credential brokering

- One-time OAuth via CLI: `python3 -m jarvis.cli auth google` → opens browser → refresh token stored in **macOS Keychain** (service `jarvis`, account `google-oauth-jarvis`).
- Skills read tokens from Keychain at call time; tokens never in `.env`, DB, logs, or repo.
- Revocation = Keychain delete; rotation = re-run auth command.
- Scopes requested minimally per skill version (§7).

### 5.2 Draft → confirm → commit (structural, not prompt-level)

Every privileged write tool splits in two:

1. `*_draft_*(...)` → validates + prepares the action, stores pending action in DB, returns an action_id and a human-readable summary. Jarvis speaks the summary ("Send email to X, subject Y, body reads: …").
2. `*_commit(action_id)` → executes. **Preconditions enforced in code:** (a) action_id exists and is pending; (b) a new user turn has occurred since the draft; (c) policy level for that action class is satisfied (§5.4).

No privileged effect is reachable within a single user utterance. This is also the prompt-injection defense: attacker text inside an email/webpage can at most cause a draft to be read aloud — never a commit, because the user never speaks the confirmation.

### 5.3 Audit log

`actions` table (new migration): id, tool, class, draft payload (JSON), spoken summary, commit timestamp, authorizing transcript excerpt, result/status. Queryable by voice ("Jarvis, what did you send today?") and by CLI.

### 5.4 Authorization policy ladder (stiffening mechanism)

Per-action-class policy in `config/policy.yaml`, default shown:

```yaml
policy:
  default: confirm          # applies to all privileged actions
  overrides:
    gmail.send: confirm
    calendar.write: confirm
    system.shell: phrase    # example of a stiffer default we ship with
```

Levels, in increasing strength:

| Level | Name | Requirement at commit |
|---|---|---|
| 0 | `readonly` | Action class disabled for writes (draft rejected) |
| 1 | `confirm` | Spoken confirmation in a new user turn (**current default**) |
| 2 | `phrase` | Spoken unlock phrase (e.g. "Jarvis, authorized") within N seconds; phrase set via CLI, hashed in config |
| 3 | `console` | Click confirm in web console (out-of-band from voice channel) |

Stiffening = edit `policy.yaml` + reconnect. No code changes. Tightening applies immediately to new drafts; pending drafts are invalidated on policy change.

The enforcement point is the commit precondition check in the registry — one choke point all privileged commits pass through, so policy changes cannot be bypassed by an individual skill.

### 5.5 Autonomy boundary (locked)

Jarvis never initiates privileged actions. Drafts arise only from an explicit user request in the current session (or a user-created scheduled prompt, §4.1). No background/agent-initiated commits, ever.

---

## §6 Layer 4 — Foundry (build skills/agents by voice)

Fifth sub-agent, `foundry`, backed by `mcp_servers/mcp_forge/`:

- `scaffold_skill(name, description)` → generates `mcp_<name>/` from template + draft `skill.yaml`
- `scaffold_agent(name, skills, description)` → appends draft `agents.yaml` entry
- `run_skill_tests(name)` → executes manifest `test` command in isolation
- `promote_skill(name)` → draft → active **only if** tests pass; promotion is a git commit
- `retire_skill(name)` → deactivates (kept in git history)

**Locked rules:**
1. Generated code is always draft. Nothing activates without its manifest tests passing.
2. Every promote/retire is a commit — capability changes are auditable in git.
3. Foundry can scaffold privileged skills, but the scaffold ships with `class: privileged` + policy `confirm` minimum; it cannot lower policy.
4. Foundry is itself standard-class: it writes files in the repo, never executes generated code except via `run_skill_tests` in a subprocess sandbox.

**Deferred decision:** LLM-written skill logic vs template-only. Default: template + user-edited logic initially; LLM codegen only after U4 proves the test gates hold.

---

## §7 Gmail / Calendar roadmap (first privileged skills)

| Step | Scope | Capability |
|---|---|---|
| G1 | `gmail.readonly` | search, list unread, read thread, summarize |
| G2 | `calendar.readonly` | today's events, next N days (merges with Scheduler agent) |
| G3 | `+ gmail.send` | draft+commit send, reply |
| G4 | `+ calendar.events` | create / move / cancel events |

- Each step is separately gated; scopes added only when that step ships.
- Injection posture: email bodies and event descriptions are *data*, surfaced via summarization; they never enter the supervisor prompt as instructions; commit gate is the backstop (§5.2).

---

## §8 Layer 5 — External project orchestration

Jarvis orchestrates external projects; it does not voice-author arbitrary code.

- GitHub integration (issues, PRs, clone, status) via MCP; code lives in the target project's own repo with its own CI as the quality gate.
- Voice role: "open an issue on X", "what's CI status on Y", "summarize PR #12".
- Locked boundary: Foundry scaffolds **inside** the Jarvis framework only; external repos are interacted with through their own tooling, never self-modified into Jarvis.

---

## §9 Phases & exit gates

### U1 — Framework formalization
- G1: `skill.yaml` manifests for all 5 existing skills; `check_skills.py` passes.
- G2: Roster-only test agent added via `agents.yaml` alone; delegation schema validates.
- G3: New standard skill (e.g. `mcp_stocks` read-only) added; available after reconnect with **no bot restart**.

### U2 — Scheduled-prompt workflows
- G1: Recurring prompt-reminder fires and injects on schedule; delivered-state correct when disconnected.
- G2: Briefing workflow (calendar-read stub + time + notes) completes end-to-end by voice.

### U3 — Privileged-skill substrate
- G1: Keychain broker + `jarvis auth google` flow stores/reads/revokes token.
- G2: Draft/commit enforced: commit without new user turn rejected; commit with policy `phrase` requires phrase; policy change invalidates pending drafts.
- G3: `actions` audit table records draft+commit+transcript excerpt; queryable.

### U4 — Foundry
- G1: Scaffold a standard skill by voice → tests run → promote → usable after reconnect.
- G2: Scaffolded privileged skill refuses `policy < confirm`; promote blocked on failing tests.
- G3: Full cycle leaves clean git history (one commit per promote).

### U5 — Gmail/Calendar G1–G4
- G1: read inbox + summarize by voice, 10 consecutive trials, 0 errors.
- G2: calendar read merges into Scheduler answers.
- G3: send flow: draft read-back → spoken confirm → commit → appears in Sent; audit row present.
- G4: event create/move/cancel with confirm; read-back correct in user's timezone.

---

## §10 Open decisions

1. LLM codegen for skill logic (fast/strict-tests) vs template-only (safe/limited) — default template-only, revisit after U4.
2. `system.shell` action class: exact command allowlist vs open shell behind `phrase` policy. Lean: allowlist.
3. Web-console confirm UI (policy level 3) — build only if a `console`-policy action is actually configured.
