# Plan-author brief — Mortimer/Jarvis platform roadmap, wave plans

You are writing ONE implementation plan for the repository snapshot at
`/home/claude/repo` (a copy of Larry's `jarvis-voice-ai-clean` as of
2026-08-26). Read `/home/claude/repo/CLAUDE.md` first (all of it), then
`/home/claude/repo/docs/plans/MORTIMER_PLATFORM_ROADMAP.md` (the approved
roadmap — your plan implements one of its tracks and MUST obey its §0
constraints C1–C10 and §6 invariants). Pipecat 1.4.0 source is installed at
`/usr/local/lib/python3.11/dist-packages/pipecat` — read it when a plan
touches the runner, transports, or services; never guess a Pipecat API.

## The bar (non-negotiable)

Larry hands these plans to a DIFFERENT, weaker model (Claude Sonnet) to
implement, with no access to any conversation. The plan must be executable
end to end **without the implementer making a single design decision**.
The three shapes that reveal an unfinished section, and what to do instead:

- "requires judgment" / "use your judgment" → a deterministic rule the
  implementer executes (exact threshold, exact algorithm, exact copy).
- "investigate first" → a decision tree: check X; if A do this; if B do
  that; if neither, report and stop.
- "be careful" / "security-sensitive" → the complete implementation as
  literal code in the plan PLUS the adversarial cases it must reject, as
  test cases.

Self-audit taxonomy (all have actually happened in this project; check
each before you finish):
1. Multi-consumer contracts named but not typed — every API/format read by
   more than one consumer is specified member-by-member (signatures,
   return types, whether subscribe returns an unsubscribe).
2. Lifecycle left implicit (unmounted vs hidden; does state survive).
3. How a value is applied (which property, which transition).
4. Two sections describing the same behaviour differently.
5. Copy and visual states named but unspecified.
6. Initialization timing.
7. Signatures agreeing across sections; every schema column populated by
   some step; every value a step needs actually derivable.
8. Judgment left to the implementer (see the three shapes above).
9. Plan drift — files created but absent from the files manifest; a
   decision saying "write X" while a later section says "X exists".

Verify every claim against source before it goes in the plan — including
claims copied from the roadmap or an earlier plan. Cite `path:line` for
every "today X does Y" statement. If you find the roadmap is wrong about
something, say so in a **"Corrections to the roadmap"** subsection at the
top of your plan and proceed with the truth.

## Structure (match the house style)

Read two exemplars for tone and structure before writing:
`docs/plans/implemented/MORTIMER_CREDENTIAL_VAULT_PLAN.md` (security plan,
literal code, adversarial tests) and
`docs/plans/MORTIMER_SITE_RESEARCH_AND_COMPARISON_PLAN.md` (feature plan,
locked decisions, acceptance Larry runs). Use this skeleton:

```
# Title
**Status:** DRAFT for Larry's approval, 2026-08-26. Implements roadmap track Tn.
**Author / origin:** (Larry's quoted words that motivated it, from the roadmap)
**Roadmap constraints this plan is bound by:** list the C-numbers and say how each is honoured.
**Contracts this plan INTRODUCES (consumed by later plans):** ...
**Contracts this plan CONSUMES (by doc + section):** ...
**Corrections to the roadmap:** (or "none")
## §0 Binding constraints for the implementing model
## §1 What exists today (verified, path:line) and the gap
## §2 Non-goals
## §3 Decisions — lettered (use the letter prefix assigned to you), each with a *why*
## §4 Files (create / modify / delete — complete manifest; every file touched in §5 appears here)
## §5 Implementation steps, in order, each with: files, exact change, test that proves it
## §6 Tuning knobs — where every number lives (one place each), with its default and env override
## §7 Tests — enumerated by file and function name, with the inputs and expected outputs
## §8 Verification Larry runs on his hardware (the sandbox lacks Keychain/network/Xcode/mic)
## §9 Rollback (kill switch env var, and how to revert data changes)
## §10 Risks (table)
## §11 Self-audit (walk the 9-item taxonomy explicitly, item by item, say what you checked)
## §12 Approval checklist
```

Conventions the repo enforces (from CLAUDE.md — verify there):
- New MCP servers: `mcp_servers/<name>/logic.py` (pure, clients injected)
  + `server.py` (FastMCP over stdio) + `skill.yaml` with `requires_env`;
  tool descriptions state which system they touch; add to
  `config/mcp_servers.yaml`, `config/agents.yaml`, `TOTAL_TOOLS`, and the
  routing-eval fixture in the same PR.
- Every mutation is draft → confirm (the `actions`-table pattern).
- Kill switches are env vars read in ONE place, `JARVIS_<FEATURE>_ENABLED`.
- Tests: `tests/unit/` pytest; live things go in `tests/integration/` or
  `tests/evals/`; the routing eval must stay ≥ 90 %.
- Sandbox git is forbidden for the implementer (leaves index.lock) — plans
  say "Larry commits" and give the branch name.
- Secrets in the vault only (`jarvis/vault.py`, `set_secret()`); never
  `.env`, never `config/`.

## Cross-plan contracts (BINDING — all plans must agree on these exactly)

These are fixed here so six plans written in parallel cannot drift. The
plan that INTRODUCES a contract specifies it fully (code, schema, tests);
plans that CONSUME it cite "MORTIMER_<X>_PLAN.md §n" and do not restate.

### K1 — Client bearer tokens (introduced by REMOTE_ACCESS; consumed by NATIVE_CLIENT_CORE, LOCAL_VOICE_AND_MINI, MAIL_CALENDAR_BRIEF)
- Header: `Authorization: Bearer <token>` on every sidecar `/api/*` route
  and on the bot's WebRTC signalling route(s) served by the Pipecat runner
  (read `pipecat/runner/run.py` for the exact routes; do not guess).
- Token plaintext: 32 random bytes, base64url, no padding, prefixed
  `jvt_`. Shown ONCE at mint; never stored server-side.
- Server stores SHA-256 hex of the token in table
  `client_tokens(id INTEGER PK, user_id TEXT NOT NULL DEFAULT 'larry',
  name TEXT NOT NULL UNIQUE, token_hash TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL, last_used_at TEXT, revoked_at TEXT)` in the
  existing `data/jarvis.db` via `jarvis/db.py`'s migration mechanism.
- CLI: `python -m jarvis.auth add <name>` / `list` / `revoke <name>`.
  (Roadmap said `python -m jarvis.vault client-token …`; corrected here —
  hashes are not secrets and belong in the DB, and `jarvis/vault.py` must
  stay import-light and untouched.)
- Verification helper (single implementation, `jarvis/auth.py`):
  `def verify_bearer(header_value: str | None, conn=None) -> ClientIdentity | None`
  where `ClientIdentity = dataclass(name: str, user_id: str)`. Constant-time
  compare of hashes (`hmac.compare_digest`). Returns None for missing,
  malformed, unknown, or revoked tokens. Updates `last_used_at` on success.
- Loopback is NOT exempt. Bootstrap: the bot process and the sidecar's own
  internal callers (`mcp_selfedit.logic.AdminClient`, `mcp_apps` app-build
  client, watchers that call the sidecar) use a SERVICE token minted as
  `python -m jarvis.auth add service-bot` and stored in the vault under
  `JARVIS_SERVICE_TOKEN`; it reaches MCP children only via `requires_env`
  (K2).
- Kill switch: `JARVIS_AUTH_ENABLED` (default `true`). When `false`, all
  routes accept unauthenticated calls AND the bind host is forced to
  127.0.0.1 regardless of `JARVIS_BIND_HOST` (fail closed).
- Bind: `JARVIS_BIND_HOST` (default `127.0.0.1`) for both sidecar and bot.
  Startup refuses a non-loopback bind unless `JARVIS_AUTH_ENABLED=true`
  AND at least one unrevoked token exists; refusal is a logged error and
  exit code 2.
- The web console (alive until the native client replaces it) stores its
  token in `localStorage['jarvis_token']`, entered once in the Dev tab of
  the side drawer; a 401 anywhere shows a single toast "Token required —
  Dev tab" and does not retry. (Minimal web work; the console is being
  retired.)

### K2 — Per-server environment scoping (introduced by SECURITY_HARDENING; consumed by every plan that adds an MCP server)
- `SkillRegistry` (`jarvis/skills/registry.py:192` today does
  `env = dict(os.environ)`) builds each child's env as:
  `BASE_ENV_KEYS = ("PATH","HOME","PYTHONPATH","VIRTUAL_ENV","LANG","LC_ALL","TMPDIR","TZ","JARVIS_DB_PATH","JARVIS_TIMEZONE","JARVIS_ADMIN_URL","JARVIS_LOG_LEVEL")`
  copied when present, PLUS the names listed in that server's
  `skill.yaml` `requires_env`, PLUS the server's explicit `env:` map from
  `config/mcp_servers.yaml` (expanded as today). Nothing else.
- A server whose `requires_env` names a variable that is unset at spawn
  time: spawn proceeds, a WARNING names the server and the variable
  (today's behaviour for missing keys is preserved — verify what happens
  today and keep it).
- Kill switch: `JARVIS_ENV_SCOPING_ENABLED` (default `true`); `false`
  restores full inheritance.
- Any plan adding a server lists its `requires_env` explicitly.

### K3 — Sensitive turn flag (introduced by SECURITY_HARDENING; consumed later by the SENSITIVE_TIER plan, not written yet)
- Module `jarvis/sensitive.py`: `detect_financial(text: str) -> FinancialMatch | None`
  with `FinancialMatch = dataclass(kind: Literal["card","account","routing","iban","balance"], span: tuple[int,int])`.
  Patterns are literal in the plan with their positive/negative cases.
- Per-session flag: `SensitiveTurn` (in `jarvis/bot/`), set when
  `detect_financial(user_transcript)` matches, cleared on bot end-of-turn.
  While set: no INSERT into `conversations` for either role
  (`jarvis/bot/transcript_log.py:150`, `jarvis/agents/supervisor.py:194`),
  run-log payloads reduced to tool names, `bot.log` lines carry the turn
  id only. Memory gate (`jarvis/memory.py:301 scan_memory_content`) refuses
  with reason `"financial detail — not stored (sensitive tier not yet enabled)"`.
- Kill switch: `JARVIS_SENSITIVE_GUARD_ENABLED` (default `true`).

### K4 — Agent isolation sets (introduced by SECURITY_HARDENING; consumed by MAIL_CALENDAR_BRIEF)
- In `tests/unit/test_agent_isolation.py`:
  `OUTBOUND = {"mcp-web","mcp-git","mcp-apps","mcp-repo","mcp-selfedit"}`,
  `UNTRUSTED_INPUT = {"mcp-mail"}`. Test: no agent in `config/agents.yaml`
  has a non-empty intersection with both sets. Passes trivially today
  (no `mcp-mail`), fails the day someone wires mail to the developer.

### K5 — Host/URL configuration (introduced by REMOTE_ACCESS; consumed by LOCAL_VOICE_AND_MINI, NATIVE_CLIENT_CORE)
- Clients discover the server by ONE base URL each: `JARVIS_ADMIN_URL`
  (exists today — verify where it is read) and `JARVIS_BOT_URL` (new;
  default `http://127.0.0.1:7860`). No code names a host.

### K6 — Sixth agent name (introduced by MAIL_CALENDAR_BRIEF)
- `name: secretary`, `display_name: Secretary`, servers
  `[mcp-mail, mcp-calendar, mcp-reminders, mcp-screen]`. Routing-eval
  fixture gains ≥ 12 utterances for it (6 mail, 6 calendar/brief) and ≥ 6
  negatives that must still route to scheduler.

### K7 — Local voice service switches (introduced by LOCAL_VOICE_AND_MINI)
- `JARVIS_STT_PROVIDER` ∈ {`deepgram`,`whisper_mlx`} default `deepgram`;
  `JARVIS_TURN_DETECTOR` ∈ {`stt`,`smart_turn_v3`,`smart_turn_coreml`}
  default `stt`; `JARVIS_TTS_PROVIDER` ∈ {`elevenlabs`,`kokoro`} default
  `elevenlabs`; Supervisor LLM base URL/key already come from settings —
  verify and reuse, do not add a parallel knob.

### K8 — JarvisKit public surface (introduced by NATIVE_CLIENT_CORE)
- Swift package `macos/JarvisKit` (platforms macOS 26, iOS 26). Public
  types, minimum: `JarvisClient` (connect/disconnect, `@Published state`),
  `JarvisConfig(botURL: URL, adminURL: URL, token: String)`,
  `AppMessage` enum decoding the existing RTVI app-message payloads
  (enumerate them from `web/src` — `agentRuns.ts`, `displayResults.ts`,
  `conversationFeed.ts`, `uiCommands.ts`, `voiceState.ts`; specify each
  case's fields from the TypeScript source), `AdminAPI` (typed wrappers over
  the sidecar routes the drawer tabs use). Token from Keychain via
  `KeychainStore.token(for: botURL)`.

## Output — WRITE INCREMENTALLY (mandatory)

A previous run of this task was killed mid-research and produced nothing,
because the plan was written in one call at the end. Do not repeat that.

1. **Within your first 5 tool calls**, create
   `/home/claude/plans/out/<FILENAME>.md` containing the full section
   skeleton (all headings from the structure below) with `TODO` under each.
2. After each research burst, **Edit that file** to fill in the section you
   just have the evidence for. Never hold more than one section's worth of
   findings in your head unwritten.
3. Budget your reading: prefer targeted `grep -n` over reading whole large
   files; read a file in full only when the plan must quote or modify it.
   Aim to finish research in under 40 tool calls.

Write your plan to `/home/claude/plans/out/<FILENAME>.md`. Aim for the
length the content needs (the exemplars run 250–600 lines; security plans
carry literal code and run long). Return, as your final message, ONLY:
the file path, a 5-line summary, any roadmap corrections you made, and any
contract (K1–K8) you had to deviate from and why. No other prose.
