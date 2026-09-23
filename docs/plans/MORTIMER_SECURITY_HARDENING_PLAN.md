# Mortimer Security Hardening Plan (roadmap track T4a)

**Status:** **IMPLEMENTED (code), on `main` by 2026-09-04 — §8 VERIFICATION
PARTIAL: V1 has historical passing evidence; V2–V6 remain unverified.
V7's three deny entries ARE APPLIED on main, checked 2026-09-17.**
*Reconciled 2026-09-22 against main `88b206f`:* the V7 deny entries were added
by `e6f6f33` (2026-09-07, "T4a V7 … row W0-SEC") and are present at
`88b206f`. The previously cited `25ab904d` (#74, 2026-09-15) has an empty diff
against its parent `7c23de1` and is not the source. The merge-base check noted
as "Not run" below now passes: `git merge-base --is-ancestor
origin/feat/t4a-security-hardening main` exits 0 (branch tip `60e9f42`), so the
T4a branch is fully contained in `main`. V2–V6 status is unchanged.
The implementation inventory below was originally audited against
`feat/graph-layer` (2c0ff5a), 2026-09-07. Implements roadmap
track **T4a** (`docs/plans/MORTIMER_PLATFORM_ROADMAP.md` §2.4, "T4a — hardening,
not gated").

**What is in the tree (path:line).** D-H1/K2: `jarvis/skills/registry.py:50`
`BASE_ENV_KEYS`, `:76` `env_scoping_enabled`, `:88` `load_requires_env`, `:113`
`_resolve_dynamic_env`, `:166` `build_child_env`; the only `dict(os.environ)`
left is the kill-switch fallback at `:181`. D-H2: all six `skill.yaml`
corrections (`mcp_web` `TAVILY_API_KEY`+`JARVIS_UNITS`, `mcp_git`/`mcp_repo`
`JARVIS_REPO_ROOT`, `mcp_apps` requires+optional, `mcp_selfedit` optional,
`mcp_screen` requires+optional+`requires_env_dynamic`); zero "inherits the full
parent environment" comments left in `config/mcp_servers.yaml`;
`scripts/check_skills.py` knows `optional_env` and `requires_env_dynamic`;
`CLAUDE.md:93` carries the allowlist clause. D-H3 `jarvis/sensitive.py`; D-H4
`jarvis/bot/sensitive_turn.py`; D-H5 constants in `sensitive.py` only; D-H6
sites: `jarvis/bot/transcript_log.py` (arm/is_sensitive), `jarvis/agents/
supervisor.py:38,166`, `jarvis/cli.py:17`, `jarvis/bot/pipeline.py:58,158`;
D-H7 `jarvis/runlog/store.py:74` `SENSITIVE_SENTINEL`, `:155` `_redact`,
snapshot passed at `jarvis/agents/base.py:467`; D-H8 `jarvis/memory.py:34,391`;
P14/P15 gates `mcp_servers/mcp_notes/logic.py:16`, `mcp_servers/mcp_reminders/
logic.py:23`; D-H10 both kill switches read in exactly one place
(`registry.py:57/77`, `sensitive.py:47/51`), documented at `.env.example:303,305`,
and neither is set in `.env`, so both mechanisms are ON. Tests: 5 of the §4
unit files exist with 12+16+15+4+2 = 49 tests plus the `test_memory.py`
additions; all green inside the 2,329-test suite run 2026-09-07. Roadmap edits
RE-1–RE-5 are applied (`ROADMAP.md:223` T3.6, `:463` KeychainStore clause,
`:247` §2.4). **One §4 create item is absent:** `tests/integration/
test_env_scoping_live.py` was never written; its stated acceptance (spawn the
real registry, call `get_current_time`, get a time back) is what
`tests/integration/test_registry.py::test_call_real_tool_round_trip` already
does, ungated, and it passed in the 102-test integration run of 2026-09-05.

**How it reached `main`.** `.git` reflogs: HEAD left `feat/t4a-security-
hardening` at its tip `60e9f42` for `main` on 2026-09-04 13:39Z; `main` then
fast-forwarded twice that day (`47f674c → a0cece1 → e101758`) and
`feat/graph-layer` was created from `main` at `e101758` at 15:53Z. Every file
above is on `feat/graph-layer` and none of it was authored there, so the T4a
work is on `main`. Not run: `git merge-base --is-ancestor
origin/feat/t4a-security-hardening main` — the one command that makes that
certain. The 09-04 snapshot's "49 commits sit on feat/t4a-security-hardening"
describes the branch before that pull.

**Current verification status (2026-09-17).** V7's policy edit is present:
`jarvis/skills/registry.py`, `tests/unit/test_agent_isolation.py` and
`tests/unit/test_requires_env_snapshot.py` are all denied in
`config/self_edit_allowlist.json` on main and candidate `5faa2e6`. Do not
repeat the allowlist edit. The original claim that these files were
self-editable is superseded by that source check; current release test
evidence belongs in `docs/acceptance/adaptive-interface/RELEASE_READINESS.md`.
**Still open: V2–V6 — no recorded acceptance run found.** The
mechanisms deliberately log nothing when they arm (logging the event would be
a persistence site), so the absence of log lines is expected and is evidence
of nothing; V2's `ps eww` on a live `mcp_time` child and V4's spoken account
number are the only proofs and both need Larry's hardware. (3) **Drift since
08-27, not a hole:** `MORTIMER_SELFEDIT_TIERS_PLAN.md` (08-31) made
`jarvis/**` Tier B (`core`), so D-H9's statement that `jarvis/sensitive.py`,
`jarvis/memory.py`, `jarvis/bot/sensitive_turn.py` and `jarvis/runlog/store.py`
"match no allow pattern" now reads "match the core pattern": editable with a
`plan_path`, a CORE CHANGE block on the PR, and the human merge. Deny > allow >
core precedence is unchanged.

*Original header, kept for provenance:* DRAFT for Larry's approval,
2026-08-26.

**Author / origin.** Larry, 2026-08-25/26, quoted in the roadmap's origin
section:

- *"ensure we have the security portion right to include sensitive info like
  financial info"*
- *"I want this data available to the AI and myself but secured from any
  intruder."*
- Sequencing rule, verbatim: *"we will not implement the financial piece until
  the issues are resolved like moving to the mini so that we can process the
  models locally."*

That last sentence is why this plan exists as a separate track from T4b. T4a is
everything that makes the system **stop leaking** and **stop storing** — it adds
no store, no key, no decryption path, and no new place for a financial value to
land. It is explicitly **not gated** on G3 (roadmap C3). T4b (the encrypted
sensitive tier) is gated and is not in this plan.

**Roadmap constraints this plan is bound by.**

| C | How this plan honours it |
|---|---|
| **C1** — backend contract does not change for the client migration | No RTVI app-message shape changes, no new sidecar route, no client-specific endpoint. The only wire-visible change is that a `sensitive` turn produces *fewer* rows/lines, never a different shape. |
| **C2** — localhost is the trust boundary until T2 | This plan binds nothing, opens no port, and changes no bind host. `JARVIS_BIND_HOST` belongs to T2/K1 and is not touched here. |
| **C3** — the sensitive tier (T4b) does not start until G3 | **This is T4a.** Nothing here stores a financial value anywhere. The memory gate *refuses*; the sensitive-turn flag *suppresses*. There is no encrypted store, no Keychain access-control item, no key. The plan adds a hard test (§7, `test_no_sensitive_store_exists`) that fails if a future edit introduces one under this track. |
| **C4** — every mutation stays draft → confirm | This plan introduces no mutating tool. Its only user-visible behaviour is refusal text. |
| **C5** — sub-agents act on data, never on the user's windows | Untouched. No new Supervisor tool, no `ui` app-message. |
| **C6** — untrusted content never shares an agent with an outbound channel | **Enforced here**, as K4: `tests/unit/test_agent_isolation.py` (§7). Passes today; fails the day a mail server joins an agent that holds any of `OUTBOUND` = `mcp-web`/`mcp-git`/`mcp-apps`/`mcp-repo`/`mcp-selfedit`/`mcp-screen`/`mcp-calendar` (the last two added per resolution §B). |
| **C7** — routing eval stays ≥ 90 % | This plan adds no agent, does not change the Supervisor model, and does not change the Supervisor prompt. **One prompt-adjacent risk exists and is neutralised**: the memory-gate refusal string is returned by `upsert_fact`'s logger, not into the LLM context (see §1.5 and D-H8). Larry still re-runs the eval once (§8 V6) because `SkillRegistry` env scoping changes what every MCP child sees, and a child that silently loses a variable would show up as a routing/tool failure. |
| **C8** — self-edit allow/deny changes are human commits | `config/self_edit_allowlist.json` is not edited by this plan. `jarvis/sensitive.py` and `jarvis/bot/sensitive_turn.py` match no allow pattern, so they need no deny entry (§1.6, R-4). D-H9 (resolution §A) denies `jarvis/skills/registry.py` and the two test files instead — **that edit is Larry's commit via ALLOWLIST_SEQUENCE.md row W0, not the implementer's** (§8 V7). |
| **C9** — secrets go in the vault | This plan adds no secret. It *reduces* secret exposure: after K2, `GITHUB_TOKEN` no longer reaches `mcp_time`. |
| **C10** — degradation-proof | Every pattern is literal code in §5. Every threshold is a named constant in §6. Every adversarial case is an enumerated test in §7 with its expected output. No "use judgment", no "investigate first". |

**Contracts this plan INTRODUCES (consumed by later plans).**

- **K2 — per-server environment scoping.** `jarvis/skills/registry.py`. Fully
  specified in §3 D-H1/D-H2 and §5 Step 2. Every plan that adds an MCP server
  must list that server's `requires_env`.
- **K3 — sensitive turn flag + financial-pattern gate.** `jarvis/sensitive.py`
  (`detect_financial`, `FinancialMatch`) and `jarvis/bot/sensitive_turn.py`
  (`SensitiveTurn`). Fully specified in §3 D-H3…D-H8 and §5 Steps 3–8 (Step 8
  adds the notes/reminders gates, review F14). Consumed by the future
  SENSITIVE_TIER (T4b) plan, which replaces the refusal with a route-to-tier.
- **K4 — agent isolation sets.** `tests/unit/test_agent_isolation.py`,
  `OUTBOUND` / `UNTRUSTED_INPUT`. Fully specified in §5 Step 9 and §7.4.
  `OUTBOUND` includes `mcp-screen` and `mcp-calendar` per resolution §B.
  Consumed by MAIL_CALENDAR_BRIEF (T5), which adds `mcp-mail` to
  `UNTRUSTED_INPUT`'s live meaning by creating the server and must keep
  `mcp-screen` off its `secretary` agent.

**Contracts this plan CONSUMES (by doc + section).**

- None. T4a depends on nothing (roadmap §2.4, "Depends on. T4a: nothing.").
- **Forward compatibility note, not a dependency:** K1 (bearer tokens,
  introduced by `MORTIMER_REMOTE_ACCESS_PLAN.md`) states that the service token
  reaches MCP children *only* via `requires_env` (K2). This plan makes that
  possible by building the allowlist mechanism; it does **not** add
  `JARVIS_SERVICE_TOKEN` to any `requires_env` (no server needs it yet). The
  REMOTE_ACCESS plan adds that name to `mcp_selfedit/skill.yaml`'s
  `requires_env` itself.

---

## Revision table (review findings closed, 2026-08-27)

This revision closes the per-plan adversarial review
(`review-opus/MORTIMER_SECURITY_HARDENING_PLAN.review.md`, 6 BLOCKER / 11
MAJOR / 6 MINOR) and applies the cross-plan resolution
(`CROSS_PLAN_RESOLUTION.md` §A, §B, §C-F6/F11) items assigned to this plan.
Where the resolution and the review differ, the resolution wins (it is
binding); the one such case is D-H9, noted below. Every regex change was
re-extracted and **re-measured** against the review's own breaking inputs
plus this repo's routing-eval fixture — see §7.1's measurement note.

| Finding | Sev | Section(s) changed | What changed |
|---|---|---|---|
| F1 | BLOCKER | D-H4, §5 Step 6, §7.3 | Flag no longer cleared on `UserStoppedSpeakingFrame` (which fires *before* the consumers). Cleared on `UserStartedSpeakingFrame` (true start-of-turn) and on `InterruptionFrame` after discarding the assistant buffer. Frame order stated in D-H4. |
| F2 | BLOCKER | D-H4, D-H6 (P2/P7), §5 Step 6b/6f, §7.1 | The **assistant reply is now scanned** (`arm_from_text` on the reply text) in both `TranscriptLogger` and `Orchestrator.chat`, so "what's my balance" → reply "$2,431.18" is suppressed. Measured positive added. |
| F3 | BLOCKER | D-H5, §5 Step 3, §7.1 | `_FIN_WORD_RE` given `\b` boundaries (no more `owe`⊂`borrowed`); `_ACCOUNT_RE` rewritten to a connector-chain (drops bare-verb `checking`/`savings`, rejects `account, the order number is …`). Re-measured 0-FP/0-FN over 160 inputs. |
| F4 | BLOCKER | §4, §5 Step 5e, D-H6 | `jarvis/cli.py` added to the manifest; it now constructs a `SensitiveTurn` and `set()`s the ContextVar, so P4/P5 are actually wired on the text path. Class corrected to `Orchestrator`. |
| F5 | BLOCKER | §1.3, D-H6 (P12/P13), §5 Step 7 | `RunLogger.start()`'s `task` field (P12) and `mcp_call`'s `error` (P13) are the 12th/13th persistence sites; both now redacted. "Eleven sites" wording corrected throughout. |
| F6 | BLOCKER | D-H4, D-H6, D-H7, §5 Step 7 | Delegated sub-agents run in **detached tasks that outlive the turn**. The flag is now **snapshotted into `RunLogger` at construction** (`sensitive=`); run-log sites read `self._sensitive`, not the live ContextVar. Reply-derived values are additionally caught by a content scan at each payload site. |
| F7 | MAJOR | §4, §5 Step 1, §6 | Optional-with-default vars go in a new `optional_env:` key so `scripts/check_skills.py` (which enforces `requires_env` presence) does not print `SKILLS FAIL`. `check_skills.py` added to the manifest and taught `optional_env`. |
| F8 | MAJOR | §7.2 | `_read_in_source` now resolves module-level `NAME = "ENV_VAR"` constants (the repo's dominant style) before matching, so it catches all four of `mcp-screen`'s reads instead of zero. |
| F9 | MAJOR | §4, §5 Step 2c/5d, §6 | `.env.example` does not exist; steps changed to "create if absent, else append", full content given. The false `check_env.py` rationale dropped. |
| F10 | MAJOR | §7.1, §7 note, §8 V1 | Counts corrected to the **re-measured** set: 29 positives + 65 negatives = 94 enumerated (162 with the routing fixture); the redacted line carries `28 chars withheld`, not 27. |
| F11 | MAJOR | §1.2, D-H2, §7.2, §10 R-H1 | Transitive audit added: `mcp-screen` imports `upgrade_agent`, which reads `JARVIS_UPGRADE_MODELS`; that name is now in `mcp-screen`'s `requires_env`. §7.2 test follows `from jarvis.…` one level. |
| F12 | MAJOR | D-H9, §7.6, §10 R-H11 | Resolution §A keeps `config/agents.yaml`/`skill.yaml` editable and guards `requires_env` with a frozen snapshot test. That test now **also freezes each server's `config/mcp_servers.yaml` `env:` map**, closing the review's `env:`-map re-grant bypass without a new deny entry. Residual noted. |
| F13 | MAJOR | D-H4, §5 Step 6, §7.3 | Deepgram Flux splits one utterance across several finalized transcripts. A per-turn accumulator now runs detection on the **accumulated** text, and the USER print/persist is **buffered to turn close**, so a split "routing number is" / "021000021" still arms. |
| F14 | MAJOR | §1.3 (P14/P15), D-H6, §4, §5 Step 8 | `mcp_notes.create_note`/`update_note` and `mcp_reminders.set_reminder` were unenumerated plaintext sinks; each now runs the memory-gate financial scan and refuses. |
| F15 | MAJOR | §1.4, D-H4, §11 item 1 | The false "the observer's task is not a child of the turn" premise removed. Correct rationale: the observer task **is** created after `set()`, so it inherits the ContextVar; `Runtime.sensitive_turn` owns the object's lifetime and the ContextVar publishes that same reference. One mechanism, not two. |
| F16 | MAJOR | D-H2, §5 Step 2a, §5 Step 1 | An unknown `requires_env_dynamic` source no longer raises inside `build_child_env` (which would brick startup); it logs at ERROR and degrades. The hard error moves to a startup validation pass in `check_skills.py`. |
| F17 | MAJOR | D-H4, §5 Step 4 | `arm_from_text` now actually consults `jarvis.runlog.get_run_id()` (lazily) for `turn_id`, delivering the correlation property D-H4 promised. |
| F18 | MINOR | §8 V4 | V4 gains a step 0 (`grep "USER:" logs/bot.log`) confirming Flux numeralised the digits; absent digits ⇒ **inconclusive**, not failed. |
| F19 | MINOR | §1.3, D-H6, §5 Step 6f | `Supervisor` → `Orchestrator` throughout. |
| F20 | MINOR | §5 Step 4 | `redacted(text)` drops the unused `role` parameter. |
| F21 | MINOR | D-H2, §5 Step 1 | `mcp-apps`/`mcp-selfedit`/`mcp-screen` optional-with-default vars moved to `optional_env:` — no permanent WARNING per spawn. |
| F22 | MINOR | R-5, D-H5, §6, §12 | `BALANCE_MIN_AMOUNT` **re-measured after the F3 boundary fix**: `100.0` → **`25.0`**, which catches a $50 (and $47.32) balance while still rejecting "$20 for lunch". |
| F23 | MINOR | §7.3 | The `RunLogger` example uses the real signature (`display_name` positional, `root=tmp_path`, `sensitive=`). |
| Res §A | — | D-H9, §8 V7, `ALLOWLIST_SEQUENCE.md` | D-H9 rewritten: deny only `jarvis/skills/registry.py`, `tests/unit/test_agent_isolation.py`, `tests/unit/test_requires_env_snapshot.py`; **keep `config/agents.yaml` and `mcp_servers/*/skill.yaml` editable** (Larry's 2026-08-21 decision), guarded by the new frozen snapshot test. §8 Larry-step now cites `docs/plans/ALLOWLIST_SEQUENCE.md` row W0. |
| Res §B | — | §7.4 `OUTBOUND`, Roadmap edits | K4 `OUTBOUND` gains `mcp-screen` and `mcp-calendar`. Roadmap T3.6 local-vision item requested. |
| Res §C (F6) | — | §9 kill-switch row | Env-scoping kill switch note: after REMOTE lands, `false` also hands `JARVIS_SERVICE_TOKEN` to all children — revoke first. |
| Res §C (F11) | — | citations | `registry.py:191` → cited by code text (`env = dict(os.environ)`; the assignment is at line 192). |

---

## Corrections to the roadmap

Five. All verified against source; the plan proceeds on the corrected facts.

**R-1 — "Every `mcp_servers/*/skill.yaml` has `requires_env: [...]` … the data
for env scoping already exists" (roadmap §1, "Per-server declared needs") is
WRONG as a basis for scoping.** The *field* exists on all twelve servers, but
its contents are incomplete on **six of twelve**. Six servers read environment
variables at runtime that they do not declare, and would break the moment
scoping turned on if the declarations were trusted as written. The full
audit is §1.2; the corrected declarations are D-H2 and §5 Step 1. Notably
`mcp_apps` declares `[GITHUB_TOKEN]` but also reads `GITHUB_OWNER`
(`mcp_servers/mcp_apps/github.py:30`), and `mcp_screen` declares `[]` while
reading four variables plus a *dynamically-named* API key
(`mcp_servers/mcp_screen/logic.py:282`) — that last one cannot be expressed as
a static list and is handled by D-H2's `requires_env_dynamic` rule.

**R-2 — the roadmap's T4a bullet says the bridge variables are
"(`JARVIS_DB_PATH`, `JARVIS_TIMEZONE`)".** `bridge_settings_to_env`
(`jarvis/config.py:229`) actually bridges **four** names: `JARVIS_DB_PATH`
(L259), `JARVIS_TIMEZONE` (L260), `JARVIS_UNITS` (L265) and `TAVILY_API_KEY`
(L268–269), and `jarvis/config.py:282` already names all four in a list. A
base-env allowlist of two would silently break `mcp_web.get_weather`'s unit
selection (`mcp_servers/mcp_web/logic.py:71`). K2's `BASE_ENV_KEYS` in the
brief is also not a superset of that set — it omits `JARVIS_UNITS` and
`TAVILY_API_KEY`. Resolution: `BASE_ENV_KEYS` is used **exactly as K2 spells
it** (it is a binding cross-plan contract), and the two missing names are
supplied where they belong — through `requires_env` on the servers that read
them (`mcp-web`: `JARVIS_UNITS`, `TAVILY_API_KEY`). See D-H2. No deviation
from K2 results.

**R-3 — the roadmap's memory-gate refusal wording differs from K3's.** Roadmap
§2.4 says the reply is *"I'm not storing financial details yet"*. K3 fixes the
`scan_memory_content` return value as
`"financial detail — not stored (sensitive tier not yet enabled)"`. These are
two different strings for two different audiences and both are kept, with the

boundary made explicit: the **K3 string is the `scan_memory_content` return
value** (a log/diagnostic reason, matching the existing style of that
function's returns — `"possible API key literal"` etc., `jarvis/memory.py:185`),
and the **roadmap string is spoken copy** that this plan does *not* wire,
because wiring it would put a refusal reason into the Supervisor's context and
`jarvis/bot/remember_tool.py:19–22` (D8) deliberately forbids exactly that
("The rejection reason is never surfaced back to the LLM, which could otherwise
try to 'fix' and resubmit flagged content"). See D-H8.

**R-4 — the roadmap's deny-list row is accurate but tells only half the story;
the *allow* list is what matters for this track, and it covers four of the five
things this plan hardens.** The roadmap §1 table lists the deny list as
covering `skills/**`, `config/skills.yaml`, `macos/**`, `jarvis/bot/**`,
`jarvis/admin/**`, `data/**`, `*.vault` — verified accurate (§1.6). Matching is
deny-wins-then-must-match-allow (`jarvis/selfedit/allowlist.py:77–79`), so the
allow list is a hard requirement, not a hint. The allow list is
`web/src/**`, `web/public/**`, `config/**`, `jarvis/prompts.py`,
`jarvis/skills/**`, `jarvis/services/**`, `mcp_servers/**`, `tests/**`,
`docs/**`, `*.md`. Consequences this plan must reckon with:

- `jarvis/sensitive.py` and `jarvis/memory.py` are **not** self-editable —
  they match no allow pattern. Good news, and it means D-H9 does *not* need to
  add them. (An earlier reading of this plan asserted the opposite; corrected.)
- `jarvis/skills/**` is allowed, so **`jarvis/skills/registry.py` — the single
  enforcement point for K2 — is self-editable.**
- `mcp_servers/**` is allowed, so **every `skill.yaml` `requires_env` — the
  data K2 scopes from — is self-editable.**
- `config/**` is allowed (only `self_edit_allowlist.json`, `upgrade_agent.yaml`,
  `upgrade_models.yaml`, `skills.yaml` are denied), so **`config/agents.yaml` —
  the subject of the C6/K4 test — is self-editable.**
- `tests/**` is allowed, so **`tests/unit/test_agent_isolation.py` — the K4
  test itself — is self-editable.**

An assistant that can widen its own `requires_env`, rewrite the scoping code,
add `mcp-web` to a mail agent, and delete the test that would catch it, is not
constrained by any of the three mechanisms in this plan.

**How this is guarded — Larry's binding decision (`CROSS_PLAN_RESOLUTION.md`
§A, 2026-08-26), which overrides this plan's first draft.** An earlier draft of
D-H9 denied `config/agents.yaml` and `mcp_servers/*/skill.yaml` outright. Larry
**kept** the 2026-08-21 rule that a self-edit may *propose* granting an agent
new tools (gate = validation + Larry merging the PR), because denying those
files also kills the voice self-repair path. So the *proposal* stays possible;
the *enforcement* moves into files the assistant cannot edit. D-H9 therefore
denies only three paths — `jarvis/skills/registry.py` (the scoping code),
`tests/unit/test_agent_isolation.py` (the K4 test) and the new
`tests/unit/test_requires_env_snapshot.py` (the frozen privilege snapshot) —
and the snapshot test is what catches a self-edit that widens a
`requires_env` or re-grants a secret through a `config/mcp_servers.yaml`
`env:` map. Those three deny entries and the snapshot test are Larry's W0
commit, applied via **`docs/plans/ALLOWLIST_SEQUENCE.md` row W0** (§8 V7), not
§5. See D-H9 for the full rewrite and the "Corrections to the roadmap" note.

**R-5 — the roadmap's balance regex, used literally, fires on ordinary English
near small amounts, and the FIRST draft of this plan masked that with a floor
that was too high.** Roadmap §2.4 prescribes `\$\s?\d[\d,]*(\.\d{2})?` adjacent
to `balance|account|owe|owed|savings|checking|401k|IRA|brokerage`. Executed
verbatim in the sandbox, `"I owe you $20 for lunch"` and
`"the invoice showed $1,299"` both match — the keyword list has **no word
boundaries**, so `owe` matches inside `borrowed`/`however`/`allowed`, and
`showed`/`lowered`/`followed`/`flowers`/`tower`/`vowel` all contain `owe`
(review F3, 11 measured false positives). The first draft of this plan
"fixed" that with `BALANCE_MIN_AMOUNT = 100.0` — but that is the wrong lever
(review F22): it throws away *real* small balances ("$47.32 checking balance")
to suppress a false positive whose real cause is the missing boundary.

**Resolution (re-measured 2026-08-27).** (1) The keyword pattern gets `\b`
boundaries (D-H5): `owe` no longer matches inside `borrowed`, and the money
shape stays exactly as the roadmap gives it. (2) With boundaries in place the
corpus is clean *at any floor down to 0* — the floor was doing no work; the
adjacency of a genuine financial **noun** is the discriminator, not the amount.
(3) The one residual the floor still earns is the trivial-IOU shape
("owe you $20 for lunch"), where the verb `owe` is genuinely present but the
sum is not a balance. So the floor is **re-measured, not removed**:
`BALANCE_MIN_AMOUNT = 25.0`. Measured (§7.1): "$50 savings balance", "$47.32
checking balance" and "$30 balance" are caught (per Larry's *"a $50 balance is
financial"*); "owe you $20 for lunch", "owe me $15" are not; all 68
routing-eval utterances stay negative. `0.0` restores the roadmap's literal
"any amount beside a financial noun" behaviour.

---

## §0 Binding constraints for the implementing model

You are implementing this plan with no access to the conversation that produced
it. These are not suggestions.

1. **Sandbox git is forbidden.** Do not run `git add`, `git commit`,
   `git checkout`, `git stash`, or any other git command that writes. It leaves
   `index.lock` behind and breaks Larry's working tree. Larry commits. Branch
   name for this work: **`security-hardening-t4a`**.
2. **Do not edit `config/self_edit_allowlist.json`.** Roadmap C8. D-H9
   describes the change; §8 V7 is Larry running it. If you find yourself
   opening that file, stop.
3. **Do not create an encrypted store, a Keychain item, a new table, or any
   column named `sensitive` on an existing table.** Roadmap C3. T4a stores
   nothing. If a step seems to require persistence of a financial value,
   you have misread the step — re-read §2.
4. **Every regex in this plan is copied verbatim.** Do not "improve",
   re-order, or re-flag them. They were re-extracted and executed on
   2026-08-27 against all 92 enumerated cases in §7.1 (28 positive, 64
   negative) **plus** this repo's 68-utterance routing-eval fixture — 160
   inputs, 0 false positives, 0 false negatives. The measured results and the
   exact command are in §7.1's measurement note. A changed pattern invalidates
   the measurement; if you must change one, re-run that command and record the
   new result in the same edit.
5. **`jarvis/sensitive.py` imports only the standard library** (`re`,
   `dataclasses`, `typing`). No `jarvis.*` import, no third-party import. It is
   imported by `jarvis/memory.py`, which is imported by the MCP memory server,
   the bot, the CLI and the sidecar; a heavy import here costs every one of
   them. `jarvis/vault.py`'s import-light rule is the precedent.
6. **Do not change the locked 9-processor pipeline order**
   (`jarvis/bot/pipeline.py:669–698`). The sensitive-turn flag is set and read
   by existing processors/observers; it adds no processor.
7. **Kill switches are read in exactly one place each.** `JARVIS_ENV_SCOPING_ENABLED`
   in `jarvis/skills/registry.py` only; `JARVIS_SENSITIVE_GUARD_ENABLED` in
   `jarvis/sensitive.py` only. Every other module asks those modules. See §6.
8. **If a step's precondition is not what this plan says it is** (a line number
   has moved by more than ±15 lines, or the quoted code differs), do not guess.
   Search for the quoted code string, use the line you find, and note the drift
   in your final report. If the quoted code is absent entirely, **stop and
   report** — do not invent a replacement.
9. **Run the tests named in §7 after each step, not once at the end.** Each
   step in §5 names the exact command.
10. **No new dependency.** `requirements.txt` and `requirements-lock.txt` are
    not touched by this plan.

---

## §1 What exists today (verified, path:line) and the gap

### 1.1 Environment inheritance — every MCP child gets everything

`_start_server`'s `env = dict(os.environ)` (at `jarvis/skills/registry.py:192`
in the snapshot — the review and brief both say 192; anchor by the code text)
is the whole of the isolation story today:

```python
    async def _start_server(self, entry: dict[str, Any]) -> None:
        name = entry["name"]
        env = dict(os.environ)                     # ← registry.py:192
        for key, value in (entry.get("env") or {}).items():
            expanded = expand_env_vars(str(value))
            ...
            env[key] = expanded
        env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
```

`dict(os.environ)` is a full copy. Combined with `jarvis/vault.py`'s
`inject_env()`, which copies **every** vault secret into `os.environ` of the
parent process (roadmap §1, "Vault" row), the consequence is exact and
demonstrable: `mcp_time` — a server whose entire job is calling
`ZoneInfo(os.environ.get("JARVIS_TIMEZONE", "UTC"))`
(`mcp_servers/mcp_time/logic.py:38`) — is handed `GITHUB_TOKEN`,
`ELEVENLABS_API_KEY`, `OPENAI_API_KEY`, `TAVILY_API_KEY` and everything else in
the vault. Twelve servers, twelve full copies of every credential.

The existing per-server `env:` map in `config/mcp_servers.yaml` is an
**addition**, not a restriction — it overwrites named keys in the full copy
(`registry.py:206`). Three servers (`mcp-repo`, `mcp-runlog`, `mcp-screen`)
carry comments in `config/mcp_servers.yaml` that *rely on* full inheritance in
so many words ("the child inherits the full parent environment"). Those
comments become false the moment scoping lands and are rewritten in §5 Step 1.

`expand_env_vars` (`jarvis/config.py:33–43`) leaves an unresolved `${VAR}` as
the literal seven-character string by design; `registry.py:200–205` already
logs `mcp_server_env_unresolved` as a **warning, not a refusal**, with the
server and variable named. K2's rule for a missing `requires_env` variable
("spawn proceeds, a WARNING names the server and the variable") is therefore
already this codebase's established behaviour, and D-H1 preserves it exactly.

### 1.2 Per-server `requires_env` as it is TODAY, versus what each server reads

Declarations read from `mcp_servers/*/skill.yaml`; runtime reads from
`grep -rn "os\.environ\|getenv" mcp_servers/`.

| Server | `requires_env` TODAY | Env actually read (path:line) | Verdict |
|---|---|---|---|
| `mcp-time` | `[]` (`mcp_time/skill.yaml:6`) | `JARVIS_TIMEZONE` — `mcp_time/logic.py:38` | **OK by base env** — `JARVIS_TIMEZONE` ∈ `BASE_ENV_KEYS` |
| `mcp-notes` | `[]` (`mcp_notes/skill.yaml:6`) | `JARVIS_DB_PATH` via `jarvis/db.py:456` | **OK by base env** — `JARVIS_DB_PATH` ∈ `BASE_ENV_KEYS`; also in its `env:` map |
| `mcp-memory` | `[]` (`mcp_memory/skill.yaml:6`) | `JARVIS_DB_PATH` via `jarvis/db.py:456` | **OK by base env** |
| `mcp-reminders` | `[]` (`mcp_reminders/skill.yaml:6`) | `JARVIS_TIMEZONE` — `mcp_reminders/logic.py:59`; `JARVIS_DB_PATH` via `jarvis/db.py:456` | **OK by base env** (both in `BASE_ENV_KEYS` and in its `env:` map) |
| `mcp-system` | `[]` (`mcp_system/skill.yaml:6`) | none | **OK** |
| `mcp-runlog` | `[]` (`mcp_runlog/skill.yaml:6`) | `JARVIS_DB_PATH` via `jarvis/db.py:456` | **OK by base env** |
| `mcp-web` | `[TAVILY_API_KEY]` (`mcp_web/skill.yaml:6–7`) | `TAVILY_API_KEY` — `mcp_web/logic.py:173`; **`JARVIS_UNITS` — `mcp_web/logic.py:71`** | **UNDECLARED: `JARVIS_UNITS`** |
| `mcp-git` | `[]` (`mcp_git/skill.yaml:6`) | **`JARVIS_REPO_ROOT` — `mcp_git/logic.py:44`**; `JARVIS_DB_PATH` via `jarvis/db.py:456` | **UNDECLARED: `JARVIS_REPO_ROOT`** |
| `mcp-repo` | `[]` (`mcp_repo/skill.yaml:6`) | **`JARVIS_REPO_ROOT` — `mcp_repo/logic.py:98`** | **UNDECLARED: `JARVIS_REPO_ROOT`** |
| `mcp-apps` | `[GITHUB_TOKEN]` (`mcp_apps/skill.yaml:7`) | `GITHUB_TOKEN` — `mcp_apps/github.py:29`; **`GITHUB_OWNER` — `mcp_apps/github.py:30`**; **`JARVIS_REGISTRY_REPO` — `mcp_apps/logic.py:33`**; **`JARVIS_REGISTRY_BRANCH` — `mcp_apps/logic.py:37`** | **UNDECLARED: `GITHUB_OWNER`, `JARVIS_REGISTRY_REPO`, `JARVIS_REGISTRY_BRANCH`** |
| `mcp-selfedit` | `[]` (`mcp_selfedit/skill.yaml:18`) | **`JARVIS_ADMIN_URL` — `mcp_selfedit/logic.py:36`** (const `ADMIN_URL_ENV`, L20); **`JARVIS_UPGRADE_PROFILE` — `mcp_selfedit/logic.py:127`** | **`JARVIS_ADMIN_URL` OK by base env; UNDECLARED: `JARVIS_UPGRADE_PROFILE`** |
| `mcp-screen` | `[]` (`mcp_screen/skill.yaml:6`) | **`JARVIS_SCREEN_ENABLED`** (const `SCREEN_ENABLED_ENV`, `logic.py:70`, read `:97`); **`JARVIS_SCREEN_RETENTION_HOURS`** (const `SCREEN_RETENTION_ENV`, `:72`, read `:108`); **`JARVIS_VISION_PROFILE`** (const `VISION_PROFILE_ENV`, `:71`, read `:274`); **`JARVIS_UPGRADE_MODELS` — read TRANSITIVELY** via `from jarvis.agents.upgrade_agent import load_model_registry` (`logic.py:66`), which reads `REGISTRY_PATH_ENV = "JARVIS_UPGRADE_MODELS"` (`upgrade_agent.py:60`, at `:218`); **a profile-dependent key name — `logic.py:283,294,314`**, `prof.get("api_key_env", "OPENAI_API_KEY")`, resolving to one of `OPENAI_API_KEY`, `MOONSHOT_API_KEY`, `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY` from `config/upgrade_models.yaml` | **UNDECLARED: all five, one read transitively (F11), one dynamic** |

**Transitive reads (review F11).** The `grep mcp_servers/` audit only sees
env names read *inside* a server's own package. Every MCP server also imports
`jarvis.*` modules, and those read the environment too. The one case that
matters here is `mcp-screen` → `jarvis.agents.upgrade_agent` →
`JARVIS_UPGRADE_MODELS`: after scoping, an operator who points that variable at
a non-default registry gets `mcp-screen` silently resolving the *default*
registry — a different profile set, possibly with an `api_key_env` the child
was never granted, surfacing as "vision is not configured". `JARVIS_UPGRADE_MODELS`
is therefore in `mcp-screen`'s `requires_env` (D-H2), and §7.2's
`test_no_server_reads_an_undeclared_var` now follows `from jarvis.…` imports one
level deep so the next such case is caught mechanically rather than by grep.
The remaining transitive-read risk (third-party libraries reading their own env,
a name built at runtime) is R-H1/R-H2, mitigated by warn-and-proceed.

Six of twelve servers are under-declared. `mcp-screen` is the hard case: the
name of the API key it needs is a *value* in `config/upgrade_models.yaml`
(`api_key_env:` at L66, L76, L86, L103, L140, …), chosen at call time by
`JARVIS_VISION_PROFILE`. `config/mcp_servers.yaml`'s own comment for `mcp-screen`
states this and concludes "an explicit list would be actively wrong". It is
right that a *static* list is wrong, and D-H2 resolves it with a declared
dynamic source rather than by exempting the server.

### 1.3 Where a spoken financial detail persists today, in plaintext

Every one of these fires on an ordinary turn. None of them can be suppressed
today, because there is no per-turn flag to suppress them with.

| # | Site | path:line | What lands |
|---|---|---|---|
| P1 | `TranscriptObserver._persist` call — the USER side | `jarvis/bot/transcript_log.py:143` | Row in `conversations` with the full user utterance |
| P2 | `TranscriptLogger._persist` call — the ASSISTANT side | `jarvis/bot/transcript_log.py:69` (→ `:81` → module `_persist` at `:146`) | Row in `conversations` with the full assistant reply |
| P3 | The shared writer both use | `jarvis/bot/transcript_log.py:146–155` | `INSERT INTO conversations (session_id, role, content, created_at)` |
| P4 | `Orchestrator._persist("user", …)` — the CLI / text path | `jarvis/agents/supervisor.py`, `self._persist("user", user_text)` (class `Orchestrator`, `:118` → `:191–196`) | Same table, same columns |
| P5 | `Orchestrator._persist("assistant", …)` | `jarvis/agents/supervisor.py`, `self._persist("assistant", reply)` (`:153` → `:191–196`) | Same |
| P6 | stdout USER line | `jarvis/bot/transcript_log.py:142` — `print(f"[{_ts()}] USER: {text}")` | Full utterance to stdout, redirected to `logs/bot.log` by `scripts/mortimer.sh:85` (`nohup ./scripts/run_bot.sh >> logs/bot.log 2>&1 &`) |
| P7 | stdout ASSISTANT line | `jarvis/bot/transcript_log.py:68` — `print(f"[{_ts()}] {ASSISTANT_LOG_PREFIX} {text}")` | Full reply to `logs/bot.log` |
| P8 | Run-log tool arguments | `jarvis/runlog/store.py:263–272` — `args_json = json.dumps(arguments)`, `_append(payload_key="arguments", …)` + `args_preview` column | Full tool arguments to `logs/agents/<date>/<run_id>.jsonl` **and** a 2000-char preview to SQLite `agent_events.args_preview` |
| P9 | Run-log tool results | `jarvis/runlog/store.py:285–296` — `_append(payload_key="result", …)` + `result_preview` column | Full result to JSONL, 2000-char preview to `agent_events.result_preview` |
| P10 | Run-log final reply | `jarvis/runlog/store.py:333–341` — `_append(payload_key="reply", …)`, `reply_preview=?`, `error=?` | Full sub-agent reply to JSONL, preview + error to `agent_runs` |
| P11 | Memory extraction | `jarvis/memory.py:542`, `:575`, `:606` — `scan_memory_content(key) or scan_memory_content(value)` | Facts/summaries into `memories`. The gate exists but has **no financial patterns** |
| P12 | Run-log **task** — the delegation text the Orchestrator composed from the user's utterance (review F5) | `jarvis/runlog/store.py`, `RunLogger.start()` — `"task": self.task` in the JSONL `run_start` record (`:247`) **and** the `agent_runs.task` column (`:254`). Constructed at `jarvis/agents/base.py:443` from the user's task | The field most certain to contain the user's words, written to two places |
| P13 | Run-log `mcp_call` **error** (review F5) | `jarvis/runlog/store.py`, `RunLogger.mcp_call()` — the `error` field of the `mcp_call` JSONL record; built from the failing tool's own message (`jarvis/skills/registry.py` formats `f"{tool_name} failed: {error}"`) | Tool error text, which can echo an argument |
| P14 | Notes store (review F14) | `mcp_servers/mcp_notes/logic.py:36` — `INSERT INTO notes (title, body, …)`; **no scan today** | `title`/`body` verbatim; the routing-eval fixture proves "save a note that …" is in-domain, and the note stays searchable |
| P15 | Reminders store (review F14) | `mcp_servers/mcp_reminders/logic.py`, `set_reminder`'s `INSERT INTO reminders (…)` | Reminder text verbatim |

`jarvis/logging_config.py` is 13 lines total and does nothing but
`logging.basicConfig(level=…, format=LOG_FORMAT, force=True)` (L12). There is
**no filter, no redactor, and no place to hang one** — and the two transcript
lines that matter (P6, P7) are `print()` calls that never pass through
`logging` at all. This is a correction to any assumption that `bot.log`
redaction can be done centrally in `logging_config.py`: it cannot. It is done
at P6/P7, which is where D-H6 puts it.

### 1.4 There is no per-turn flag today

`grep -rn "sensitive" jarvis/` returns nothing that is a per-turn flag.
`Runtime` (`jarvis/bot/pipeline.py:118–140`) holds `settings`, `registry`,
`session_id`, `late_delivery`, `speaker_gate` — no turn state. The only
per-turn correlation mechanism that exists is
`jarvis/runlog/context.py:32` — `current_run_logger: ContextVar[RunLogger|None]`
with `get_run_id()` (L41) and `run_logger_scope()` (L48), whose docstring
records that "contextvars propagate correctly across asyncio task boundaries,
so concurrent delegations … each see their own RunLogger with no additional
plumbing." That is the right mechanism and D-H4 copies its shape exactly.

**What the flag actually is, and why the ContextVar is the single mechanism
(corrected, review F15).** An earlier draft claimed the transcript sites
(P1/P2/P6/P7) "execute on a task whose context is not a child of the turn that
set the flag", and concluded a `Runtime`-owned object had to be read *directly*
alongside the ContextVar. **That premise is false and was never true in the
code:** `run_session` calls `current_sensitive_turn.set(...)` (§5 Step 5b)
*before* `build_pipeline` and *before* `TranscriptObserver`/`TranscriptLogger`
are constructed, and asyncio copies the current context into every task created
afterwards — so the observer's task and the processor's task both inherit the
ContextVar. Nothing in this plan reads `runtime.sensitive_turn` directly; every
site reads through `is_sensitive()` / `current_turn_id()` / `arm_from_text()`,
all of which resolve `current_sensitive_turn.get()`.

The `Runtime.sensitive_turn` field is therefore **not a second access path** —
it is the object's *lifetime owner*. Making it a `default_factory` dataclass
field means one `SensitiveTurn` is constructed with the `Runtime`, lives exactly
as long as the session, and dies with it; the ContextVar publishes a
**reference** to that same mutable object so any task can reach it and see its
mutations. The object must be mutable and shared (not a value copied per
context) precisely so that `arm()` on the main task is visible to a reader in a
child task with no synchronisation. One object, one access path (the
ContextVar), one lifetime owner (`Runtime`). D-H4.

The run-log sites are the exception, and are handled differently: a delegated
sub-agent runs in a **detached task that outlives the turn** (review F6,
`jarvis/agents/delegate.py`, `run_task = asyncio.create_task(_execute())`), so
reading the live flag at write time is unsafe — the turn may already have
cleared. Those sites read a **snapshot** taken when the `RunLogger` is
constructed (D-H6/D-H7), not the live ContextVar.

### 1.5 The existing memory gate, and the style the new patterns must match

`scan_memory_content` (`jarvis/memory.py:301–316`) is a pure, total function
returning `str | None` — a short lowercase reason on rejection, `None` on
accept. Its order today: dangerous Unicode (L305–306), then
`_CREDENTIAL_PATTERNS` (L309–311, matched against the **raw** text), then
`_INJECTION_PATTERNS` (L312–315, matched against `text.lower()`).
`_CREDENTIAL_PATTERNS` (`jarvis/memory.py:184–193`) is a
`list[tuple[re.Pattern, str]]` with reasons like `"possible API key literal"`.

Callers: `jarvis/memory.py:542` (`upsert_fact`), `:575` (summary), `:606`
(second fact path), and `tests/unit/test_memory.py`. The tool-facing caller is
`jarvis/bot/remember_tool.py`, whose module docstring (L19–22) locks the
behaviour on rejection: *"a content-scan rejection is silent to the user beyond
the generic confirmation sentence … The rejection reason is never surfaced back
to the LLM."* Its handler (`remember_tool.py:60–68`) returns
`f"Got it — I'll remember {key}."` **unconditionally**, whether or not the
write was gated. This plan does not change that, and R-3 explains why the
roadmap's spoken string is not wired.

### 1.6 Agent isolation today

`config/agents.yaml` has five agents. Their `mcp_servers` lists:

| Agent | `mcp_servers` | line |
|---|---|---|
| `scheduler` | `[mcp-time, mcp-reminders, mcp-screen]` | `config/agents.yaml:10` |
| `librarian` | `[mcp-notes, mcp-memory, mcp-screen]` | `:14` |
| `analyst` | `[mcp-web, mcp-screen]` | `:18` |
| `systems` | `[mcp-system, mcp-screen]` | `:40` |
| `developer` | `[mcp-git, mcp-apps, mcp-repo, mcp-selfedit, mcp-runlog, mcp-screen]` | `:45` |

`analyst` and `developer` hold outbound channels. No agent holds an untrusted
input channel, because `mcp-mail` does not exist. C6 is therefore satisfied
today **by accident**, and nothing detects the accident ending. That is the
gap K4 closes.

`config/self_edit_allowlist.json` (verified in full):

- **allow:** `web/src/**`, `web/public/**`, `config/**`, `jarvis/prompts.py`,
  `jarvis/skills/**`, `jarvis/services/**`, `mcp_servers/**`, `tests/**`,
  `docs/**`, `*.md`
- **deny:** `.github/**`, `jarvis/selfedit/**`, `jarvis/agents/**`,
  `jarvis/wakeword/**`, `jarvis/bot/**`, `jarvis/admin/**`,
  `config/self_edit_allowlist.json`, `config/upgrade_agent.yaml`,
  `config/upgrade_models.yaml`, `config/skills.yaml`, `skills/**`,
  `requirements*.txt`, `web/package.json`, `web/package-lock.json`,
  `DEVIATIONS.md`, `.env`, `.env.*`, `**/.env`, `**/.env.*`,
  `jarvis/vault.py`, `data/**`, `*.vault`, `**/*.vault`, `macos/**`
- matching rule: `jarvis/selfedit/allowlist.py:77–79` — any deny match rejects;
  otherwise the path must match some allow pattern.

`jarvis/skills/registry.py`, `mcp_servers/*/skill.yaml`, `config/agents.yaml`
and `tests/**` are all writable by the self-edit loop today. R-4 / D-H9.

### 1.7 The gap, stated in one paragraph

Twelve MCP subprocesses each hold a full copy of every credential in the vault;
six of them under-declare what they actually need (one of the six,
`mcp-screen`, reads a name *transitively*, review F11), so nobody can turn
scoping on safely without first fixing the declarations. A spoken account
number lands in **fifteen** distinct plaintext locations (P1–P15 in §1.3; the
first draft of this plan enumerated only eleven and missed the run-log `task`
and `mcp_call.error` fields it edits, and the `notes`/`reminders` stores, review
F5/F14) and there is no flag anywhere in the process that could be consulted to
stop it. The memory write gate rejects API
keys and credentialed URLs but accepts a routing number without comment. And
the one architectural rule that keeps a future mail reader away from the web
and the repo (C6) is enforced by nothing but the absence of the mail server.

---

## §2 Non-goals

Explicitly out of scope. If a step seems to need one of these, re-read §0.3.

1. **No encrypted sensitive store, no key, no Secure Enclave item, no
   Touch ID/Face ID prompt.** That is T4b, gated on G3 (C3). This plan's
   financial path terminates in *refusal* and *suppression*.
2. **No new column, table, or migration.** In particular no `sensitive`
   column on `conversations` — a suppressed turn writes **no row at all**, so
   there is nothing to mark. (`jarvis/db.py`'s migration mechanism is not
   touched.)
3. **No authentication, no bearer tokens, no bind-host change.** K1/K5, T2,
   `MORTIMER_REMOTE_ACCESS_PLAN.md`. C2 keeps localhost as the boundary until
   then.
4. **No mail server, no calendar server, no sixth agent.** T5/K6. K4 ships the
   *test*; T5 ships the thing it constrains.
5. **No redaction of already-written data.** This plan changes what is written
   from now on. Purging `data/jarvis.db`, `logs/agents/` and `logs/bot.log` of
   history is a one-time operator action, given as an optional command in §8
   V8 for Larry to run or not run. No code does it.
6. **No PII detection beyond the five financial kinds** in K3 (`card`,
   `account`, `routing`, `iban`, `balance`). No SSN, no address, no medical, no
   name detection. Scope creep here is how a detector becomes unusable: every
   added kind adds false positives to ordinary speech, and §7.1's negative set
   is the budget.
7. **No STT/TTS vendor change.** Deepgram still hears every word and ElevenLabs
   still speaks every reply; suppressing *storage* does not suppress
   *transmission*. This is an accepted residual, stated in §10 R-H5, and it is
   T4b/T3's problem to fix (local STT).
8. **No change to the locked pipeline order, no new processor.** §0.6.
9. **No Supervisor prompt change and no new Supervisor tool.** C7. The
   Supervisor is not asked to classify anything; detection is mechanical.
10. **No `logging_config.py` filter framework.** §1.3 established that the two
    transcript lines are `print()` calls that never reach `logging`. Building a
    filter that cannot see them would be theatre.

---

## §3 Decisions — H-lettered

### D-H1 — `SkillRegistry` builds each child's env from an allowlist, not `dict(os.environ)` (K2)

The line `env = dict(os.environ)` in `_start_server` (at `registry.py:192` in the
snapshot — cite by that text, review F11) becomes a call to a new module-level
function `build_child_env(entry)`. The env a child receives is exactly, in this
order:

1. Each name in `BASE_ENV_KEYS`, **copied only if present** in `os.environ`.
2. Each name in that server's `skill.yaml` `requires_env`, copied if present;
   if absent, a `WARNING` naming server and variable, and the spawn proceeds.
3. Each name in that server's `optional_env` (review F7/F21), copied if present,
   **silent if absent** — these have a code default, so a permanently-unset one
   is normal and must not warn.
4. Each name in that server's `requires_env_dynamic` sources (D-H2), resolved
   at spawn time, copied if present, **silent if absent** — a dynamic source
   means "whichever of these exists", so absence is normal (see the note in
   §5 Step 2a; measured, this removed 6 spurious WARNING lines per
   `mcp-screen` spawn). An unrecognised source is caught and logged at ERROR,
   never raised out of the spawn path (review F16).
5. Each key in the server's `env:` map from `config/mcp_servers.yaml`, expanded
   through `expand_env_vars` exactly as today (the lines from
   `for key, value in (entry.get("env") or {}).items():` onward, including the
   existing `mcp_server_env_unresolved` warning, unchanged).
6. `PYTHONPATH` prepended with `REPO_ROOT`, exactly as today.

Nothing else. `BASE_ENV_KEYS` is K2's tuple verbatim:

```python
BASE_ENV_KEYS = (
    "PATH", "HOME", "PYTHONPATH", "VIRTUAL_ENV", "LANG", "LC_ALL",
    "TMPDIR", "TZ", "JARVIS_DB_PATH", "JARVIS_TIMEZONE",
    "JARVIS_ADMIN_URL", "JARVIS_LOG_LEVEL",
)
```

*Why an allowlist and not a denylist of secret-looking names.* A denylist has
to be right about every future secret; an allowlist has to be right about
twelve known servers, and it is wrong loudly (a warning naming the variable)
rather than silently. The vault's `inject_env()` puts every secret into
`os.environ` by design, so "what is a secret" is not a question this layer can
answer — "what does this server declare" is.

*Why `requires_env` from `skill.yaml` and not a new field in
`config/mcp_servers.yaml`.* The data already exists per-server in the file the
server owns, CLAUDE.md already requires new servers to carry it, and
`config/mcp_servers.yaml`'s `env:` map is an *expansion* mechanism with
different semantics (it can rename and it can supply literals). Two mechanisms,
two jobs, no merge conflict between them.

### D-H2 — the six under-declared servers get corrected `requires_env`, and `mcp-screen` gets `requires_env_dynamic`

Corrected declarations (the full target state; §1.2 has today's state and the
evidence line for every name):

| `skill.yaml` | `requires_env` AFTER this plan | Why |
|---|---|---|
| `mcp_servers/mcp_time/skill.yaml` | `[]` (unchanged) | `JARVIS_TIMEZONE` ∈ `BASE_ENV_KEYS` |
| `mcp_servers/mcp_notes/skill.yaml` | `[]` (unchanged) | `JARVIS_DB_PATH` ∈ `BASE_ENV_KEYS` |
| `mcp_servers/mcp_memory/skill.yaml` | `[]` (unchanged) | same |
| `mcp_servers/mcp_reminders/skill.yaml` | `[]` (unchanged) | both names ∈ `BASE_ENV_KEYS` |
| `mcp_servers/mcp_system/skill.yaml` | `[]` (unchanged) | reads no env |
| `mcp_servers/mcp_runlog/skill.yaml` | `[]` (unchanged) | `JARVIS_DB_PATH` ∈ `BASE_ENV_KEYS` |
| `mcp_servers/mcp_web/skill.yaml` | `[TAVILY_API_KEY, JARVIS_UNITS]` | `logic.py:71` reads `JARVIS_UNITS`; R-2 |
| `mcp_servers/mcp_git/skill.yaml` | `[JARVIS_REPO_ROOT]` | `logic.py:44` |
| `mcp_servers/mcp_repo/skill.yaml` | `[JARVIS_REPO_ROOT]` | `logic.py:98` |
| `mcp_servers/mcp_apps/skill.yaml` | `[GITHUB_TOKEN, GITHUB_OWNER, JARVIS_REGISTRY_REPO, JARVIS_REGISTRY_BRANCH]` | `github.py:29,30`; `logic.py:33,37` |
| `mcp_servers/mcp_selfedit/skill.yaml` | `[JARVIS_UPGRADE_PROFILE]` | `logic.py:127`. `JARVIS_ADMIN_URL` (`logic.py:36`) is already in `BASE_ENV_KEYS`, so it is **not** repeated here |
| `mcp_servers/mcp_screen/skill.yaml` | `[JARVIS_SCREEN_ENABLED, JARVIS_SCREEN_RETENTION_HOURS, JARVIS_VISION_PROFILE]` **plus** `requires_env_dynamic: [{source: upgrade_models_api_keys}]` | `logic.py:97,108,274`; the API key name is a *value* in `config/upgrade_models.yaml` |

**`requires_env_dynamic` — the complete specification.** A new, optional
`skill.yaml` key. Its value is a list of objects each having exactly one key,
`source`, whose value is one of a **closed set of two** recognised source names.
Any other value is a hard error at registry start (`ValueError`), because a
typo silently granting nothing is the failure mode this whole track exists to
prevent.

| `source` | Resolves to | Implementation |
|---|---|---|
| `upgrade_models_api_keys` | Every distinct `api_key_env:` value appearing anywhere in `config/upgrade_models.yaml` | `yaml.safe_load`, walk all profiles, collect `p.get("api_key_env")`, plus the literal fallback `"OPENAI_API_KEY"` (which `mcp_screen/logic.py:282` uses as its default), sorted, de-duplicated |
| `vault_names` | Reserved for T4b; resolving it in T4a raises `ValueError("requires_env_dynamic source 'vault_names' is not available before T4b")` | — |

Today `config/upgrade_models.yaml` yields
`{ANTHROPIC_API_KEY, MOONSHOT_API_KEY, OPENAI_API_KEY, OPENROUTER_API_KEY}`
(verified at `config/upgrade_models.yaml:66,76,86,103,140,150,160,170,180,190,206,216,226`).
`mcp-screen` is the only server using it.

*Why not just hard-code those four names into `mcp_screen`'s `requires_env`.*
Because `config/upgrade_models.yaml` is a registry Larry edits — the day he
adds a Groq profile, a hard-coded list makes vision fail with "vision is not
configured" and nothing in the error names the real cause. The `config/**`
allow rule (§1.6) also means the assistant can add a profile itself.

*Why `mcp-screen` still does not get a blanket exemption.* It gets four
specific credential names it might need, not `GITHUB_TOKEN`, not
`DEEPGRAM_API_KEY`, not `ELEVENLABS_API_KEY`, not the vault's future
`JARVIS_SERVICE_TOKEN`. That is the whole win.

### D-H3 — `jarvis/sensitive.py` is a new stdlib-only module; §5 Step 3 has its complete source

Detection is **mechanical, not model-driven**. The Supervisor is never asked
"is this sensitive?" — that would be a prompt change (C7), it would be
non-deterministic, and a hijacked Supervisor could answer "no". Five kinds,
fixed evaluation order `card → routing → account → iban → balance`, first match
wins. `detect_financial` is pure and total: it never raises, never logs, and
never returns the matched text — only its `kind` and `span`, so a caller that
logs a `FinancialMatch` still leaks nothing.

**`span` is defined as the span of the sensitive token itself** (the digit run,
the IBAN, the money amount), **not** the span of the keyword context that
qualified it. This matters because T4b will use `span` to excerpt a value for
the encrypted tier; a span that included "my routing number is " would store
the words too. Verified against the implementation: every `return` uses
`m.span(1)` or a group-0 span that contains only the token.

### D-H4 — `SensitiveTurn`: one mutable object, published on a ContextVar, snapshotted into detached tasks

`jarvis/bot/sensitive_turn.py` (new). §1.4 corrected the mechanism (review F15):
the ContextVar is the **single** access path for the live sites, because the
observer and processor tasks are created *after* `run_session` sets it and so
inherit it. The run-log is the one exception — it runs in a detached task that
outlives the turn (review F6) and reads a **snapshot** instead.

- `SensitiveTurn` — a small class with `armed: bool`, `turn_id: str | None`,
  `kind: str | None`, and methods `arm(kind, turn_id=None)`, `clear()`,
  `is_armed()`. It is **not** a dataclass and **not** frozen; it is deliberately
  mutable so every holder of the reference sees the same state.
- `Runtime.sensitive_turn: SensitiveTurn` — a `field(default_factory=SensitiveTurn)`
  on `jarvis/bot/pipeline.py`'s `Runtime` dataclass. It **owns the object's
  lifetime** (constructed with the `Runtime`, dies with the session); it is not
  read directly by any suppression site.
- `current_sensitive_turn: ContextVar[SensitiveTurn | None]` in the same
  module, holding a **reference to that same object**, `set()` once per session
  before the pipeline is built. Every live site reads through it.
- Free function `is_sensitive() -> bool`, the only thing the live suppression
  sites call. `return holder.is_armed() if holder is not None else True`.
  **Fail-CLOSED, and this is the one place that choice is made (review F1/F6):**
  an unset ContextVar means "treat as sensitive → suppress". This is safe
  because the ContextVar is *always* set at every live read site (the bot wires
  it in `run_session` before the observer exists, §5 Step 5b; the CLI wires it
  in `main()`, §5 Step 5e — both before any turn), so the `None` branch is
  reached only on a genuine wiring regression — and then the failure is **loud**
  (transcripts stop appearing, caught immediately by V4) instead of a silent
  leak. An ordinary turn still logs normally, because on it the holder is set
  and `is_armed()` is `False`.
- Free function `arm_from_text(text, turn_id=None) -> bool` — runs
  `detect_financial(text)`; on a match, arms the holder and returns `True`.
  Total: a missing holder is a no-op. Called on **both** the user text (Step 6)
  and the assistant reply text (review F2) — the reply is the most likely way a
  value enters the system ("what's my balance?" → "$2,431.18").

**Frame order (stated so the implementer does not infer it, review F1).** Per
turn, the observer and processor see:
`UserStartedSpeakingFrame` → one or more finalized `TranscriptionFrame`
(they accumulate mid-turn — Deepgram Flux, D-010) → `UserStoppedSpeakingFrame`
→ the LLM runs, possibly delegating into detached tasks → `LLMTextFrame`s →
`LLMFullResponseEndFrame`. A barge-in raises `UserStartedSpeakingFrame` and
`InterruptionFrame` first, and `LLMFullResponseEndFrame` may never arrive.

**Lifecycle, stated completely** (taxonomy item 2):

| Event | What happens | Where |
|---|---|---|
| Session start (`run_session`) / CLI start (`main`) | `Runtime.sensitive_turn` is constructed by `default_factory` (bot) or `SensitiveTurn()` (CLI); `current_sensitive_turn.set(...)` is called once, **before** the observer/processor exist | pipeline §5 Step 5b; cli §5 Step 5e |
| **Start of a user turn** (`UserStartedSpeakingFrame`) | `clear()` the flag and **reset the per-turn user-transcript accumulator**. This is the true start-of-turn boundary and the first frame a barge-in raises, so the previous turn's flag never leaks into this one (review F1) | `TranscriptObserver`, §5 Step 6c |
| Finalized user transcription arrives (may be several — Flux splits utterances, review F13) | text is **appended to the accumulator**; `arm_from_text(accumulated)` runs on the *joined* text; **nothing is printed or persisted yet** | `TranscriptObserver`, §5 Step 6d |
| End of user speech (`UserStoppedSpeakingFrame`) | the accumulated user text is flushed once: redacted print + **no** persist if armed, else raw print + persist. Latency baseline set here | `TranscriptObserver`, §5 Step 6d |
| Delegation starts (Orchestrator calls a sub-agent tool) | `RunLogger` is constructed with `sensitive=is_sensitive()` **snapshotted** at that moment (review F6); the detached task reads that snapshot, never the live flag | `jarvis/agents/base.py`, §5 Step 7 |
| Assistant reply completes (`LLMFullResponseEndFrame`) | `arm_from_text(reply)` runs on the assistant text (review F2), then redacted print + no persist if armed, else raw print + persist. The flag is **not** cleared here — it stays armed until the next `UserStartedSpeakingFrame`, so a late-constructed run-log still snapshots the right value | `TranscriptLogger`, §5 Step 6b |
| User interrupts mid-turn (`InterruptionFrame`) | `TranscriptLogger` **discards** `self._assistant_buffer` (so a partial sensitive reply is not flushed by the next end-frame with a stale flag) and `clear()`s the flag | `TranscriptLogger`, §5 Step 6b |
| Session end / bot restart | The object dies with the `Runtime`/process. **A sensitive turn does not survive a restart** — nothing persists (C3: T4a stores nothing) | — |
| Guard disabled (`JARVIS_SENSITIVE_GUARD_ENABLED=false`) | `detect_financial` returns `None` unconditionally ⇒ `arm_from_text` never arms ⇒ the holder stays `armed=False` ⇒ `is_sensitive()` is `False`. Every site is inert. One kill switch, one read site | `jarvis/sensitive.py` |

`turn_id` is `jarvis.runlog.get_run_id()` at arm time when inside a run, else a
fresh `uuid.uuid4().hex[:8]`. `arm_from_text` resolves it with a **lazy** import
(review F17 — the source in §5 Step 4 now actually calls it):

```python
if turn_id is None:
    try:
        from jarvis.runlog import get_run_id
        turn_id = get_run_id() or None
    except Exception:
        turn_id = None
```

It exists so the redacted log lines (D-H6) are correlatable without carrying
content.

### D-H5 — the detector's numbers and why each is what it is

Every threshold is a named constant in `jarvis/sensitive.py` and appears in §6.

| Constant | Value | Why this value |
|---|---|---|
| `CARD_MIN_DIGITS` / `CARD_MAX_DIGITS` | `13` / `19` | ISO/IEC 7812 PAN length. 13 excludes 10-digit phone numbers and 12-digit run ids; 19 excludes the 20-digit-and-longer opaque ids seen in `logs/agents/` |
| `ACCOUNT_MIN_DIGITS` / `ACCOUNT_MAX_DIGITS` | `6` / `17` | 6 excludes 5-digit US zips and 4-digit "ending in" fragments (which are deliberately *not* sensitive); 17 is the longest US bank account number in practice |
| `CONTEXT_WINDOW_CHARS` | `40` | Measured: "the routing number for the joint account is 021000021" puts 9 chars between keyword and digits; 40 covers every phrasing in §7.1's positive set with margin, and is short enough that the keyword and the number are in the same clause. Used by `routing` and `balance` |
| `IBAN_MIN_TOTAL` / `IBAN_MAX_TOTAL` | `15` / `34` | ISO 13616 |
| `BALANCE_MIN_AMOUNT` | `25.0` | R-5, **re-measured after the F3 boundary fix**. With `\b` boundaries the corpus is 0-FP down to `0.0`; the floor's only remaining job is the trivial-IOU shape ("owe you $20 for lunch"). `25.0` catches a $50 and a $47.32 balance (per Larry's *"a $50 balance is financial"*) while rejecting sub-$25 IOUs. Set to `0.0` for the roadmap's literal rule. (The first draft's `100.0`, and the now-removed `ACCOUNT_WINDOW_CHARS = 24`, were both artefacts of the missing word boundaries — review F22) |

Structural choices that are not numbers but are equally load-bearing:

- **Card grouping floor of 4.** `\d{4,6}(?:[ -]\d{4,6}){2,4}` — every
  separator-delimited group must be 4–6 digits. This single choice is what
  rejects dates (`2026-08-27` → 4,2,2), zip+4 (`35242-1234` → only one
  separator, needs ≥2), phone numbers (`555-123-4567` → 3,3,4), and SSN shapes
  (`123-45-6789` → 3,2,4). Measured in §7.1.
- **Word boundaries on the balance keyword (review F3).** `_FIN_WORD_RE` is
  `(?:\b(?i:balance|accounts?|owed?|savings|checking|401\s?k|brokerage)\b|\bIRA\b)`.
  The `\b`s are what keep `owe` from matching inside `borrowed`, `however`,
  `allowed`, `followed`, `flowers`, `tower`, `vowel`, `lowered`, `slowed`,
  `showed`, and `account` from matching inside `accounting`. Without them, 11 of
  §7.1's negatives (all measured) fired. This is the defect the `BALANCE_MIN_AMOUNT`
  floor was papering over.
- **The account rule is a connector-chain, not a window (review F3).**
  `_ACCOUNT_RE` requires an account **noun** (`account`/`acct`/`checking account`/
  `savings account`/`bank account`) followed by only connective tokens
  (`number`/`num`/`no`/`is`/`ending`/`in` and punctuation) before a solid 6–17
  digit run. A *competing* noun between the keyword and the digits breaks the
  chain, so `"my account, the order number is 8675309"` and
  `"log in to my account, my member id is 998877"` do **not** match, while
  `"account number is 000123456789"` and `"Account: 100200300400"` do. The
  earlier bare-verb `checking`/`savings` alternatives (which matched
  `"checking build 1049322"`) are gone.
- **IBAN is matched case-SENSITIVELY.** No `re.IGNORECASE`. That is what keeps
  `gpt-5.1`, `462da350`, `97d5cecc` and `eleven_flash_v2_5` out before the
  mod-97 check is even reached.
- **`IRA` is case-sensitive; every other balance keyword is not.** Written as
  `…|\bIRA\b` outside the `(?i:…)` group. Without this, the given name "Ira" is
  a financial keyword. Measured: §7.1 negative `"Ira paid me $500 back"`.

### D-H6 — the fifteen persistence sites, and exactly what each does when armed

Taxonomy item 3 (how a value is applied) and item 1 (multi-consumer contract).
This table is the contract. Every row is implemented in §5 Steps 6–8. Sites are
anchored by code text, not line number, because sibling plans edit
`transcript_log.py`, `store.py` and `supervisor.py` (brief rule).

The **live** sites (P1–P7, P11, P14, P15) read `is_sensitive()` /
`detect_financial` directly. The **run-log** sites (P8–P10, P12, P13) run in a
detached task that outlives the turn (review F6), so they read the boolean
`RunLogger._sensitive` **snapshotted at construction** (`sensitive=is_sensitive()`
in `jarvis/agents/base.py`), OR — as defence for a reply-derived value the user
turn did not telegraph — `detect_financial(<the payload value>) is not None`.
"armed" below means either of those is true.

| # | Site (anchor) | Behaviour when armed | Behaviour when not |
|---|---|---|---|
| P1 | `transcript_log.py`, `TranscriptObserver` — `_persist(self._session_id, "user", text)` | **not called** — no row (user text buffered to turn close, then skipped) | unchanged |
| P2 | `transcript_log.py`, `TranscriptLogger` — `self._persist("assistant", text)`. **The reply is scanned first** (`arm_from_text(text)`, review F2) | **not called** — no row | unchanged |
| P3 | `transcript_log.py`, module `def _persist(session_id, role, content)` | a defence-in-depth `if is_sensitive(): return` as the first statement, so a future caller cannot bypass P1/P2 | unchanged |
| P4 | `supervisor.py`, `Orchestrator.chat` — `self._persist("user", user_text)` | **not called** | unchanged |
| P5 | `supervisor.py`, `Orchestrator.chat` — `self._persist("assistant", reply)`. **The reply is scanned first** (`arm_from_text(reply)`, review F2) | **not called** | unchanged |
| P6 | `transcript_log.py`, `print(f"[{_ts()}] USER: {text}")` | prints `[hh:mm:ss] USER: <sensitive turn {turn_id}: {n} chars withheld>` | unchanged |
| P7 | `transcript_log.py`, `print(f"[{_ts()}] {ASSISTANT_LOG_PREFIX} {text}")` | prints `[hh:mm:ss] MORTIMER: <sensitive turn {turn_id}: {n} chars withheld>` | unchanged |
| P8 | `store.py`, `RunLogger.tool_call` | `arguments` in the JSONL payload → `"<sensitive>"`; `args_preview` column → `"<sensitive>"`. **`tool` and `seq` still written** — K3: "run-log payloads reduced to tool names" | unchanged |
| P9 | `store.py`, `RunLogger.tool_result` | `result` in payload → `"<sensitive>"`; `result_preview` column → `"<sensitive>"`. `tool`, `ok`, `latency_ms` still written | unchanged |
| P10 | `store.py`, `RunLogger.finish` | `reply` in payload → `"<sensitive>"`; `reply_preview` → `"<sensitive>"`; `error` → `"<sensitive>"` when status != ok. `status`, `latency_ms`, `tool_count`, `tools_ok`, `tools_failed` still written | unchanged |
| P11 | `memory.py`, `scan_memory_content` | returns `"financial detail — not stored (sensitive tier not yet enabled)"` (D-H8). **Independent of the turn flag** — inspects its own argument | unchanged |
| P12 | `store.py`, `RunLogger.start` — `task` (review F5) | `task` in the `run_start` JSONL record → `"<sensitive>"`; `agent_runs.task` column → `"<sensitive>"`. `agent`, `display_name`, `session_id`, `started_at` still written. Uses the **snapshot** (the task text *is* the user's words, known at construction) | unchanged |
| P13 | `store.py`, `RunLogger.mcp_call` — `error` (review F5) | `error` in the `mcp_call` JSONL record → `"<sensitive>"`. `tool`, `server`, `ok`, `latency_ms` still written | unchanged |
| P14 | `mcp_notes/logic.py`, `create_note`/`update_note` (review F14) | `scan_memory_content(title)`/`(body)` runs; on a financial hit the write is **refused** — no row lands. Unlike the memory gate (which returns a cheerful confirmation, D-H8), a note that failed to save must report failure, so a fixed refusal string IS returned to the agent — it names the *category* ("financial detail"), never a character of the content | unchanged |
| P15 | `mcp_reminders/logic.py`, `set_reminder` (review F14) | `scan_memory_content(message)` runs; on a financial hit the write is **refused**, same contract as P14 | unchanged |

Three properties of this table that must not be lost:

- **P11/P14/P15 are not gated on the turn flag.** They call `detect_financial`
  (via `scan_memory_content`) on their own argument and run in MCP subprocesses
  that never had a `Runtime`. That is why the plan has both a flag and gates,
  and they do not talk to each other.
- **The run-log keeps its shape.** `mcp_servers/mcp_runlog/logic.py` and the
  Runs drawer tab read these records; replacing a value with `"<sensitive>"`
  keeps every key present and every type a string, so no reader changes. This
  is why the sentinel is a string and not `null` or a removed key.
- **`jarvis/procedures.py`'s `learn_from_run`** derives a procedure
  label/description from the same `task` P12 redacts. It is out of this plan's
  edit set, but noted in §10 R-H7 as a site T4b must revisit; under a snapshot
  turn its input `task` is already `"<sensitive>"`, so it cannot echo the value
  through the run-log, only through its own LLM call, which is the residual.

The sentinel is the module constant `SENSITIVE_SENTINEL = "<sensitive>"` in
`jarvis/runlog/store.py`, beside the existing `_DROPPED` sentinel
(`store.py:66`), which it deliberately mirrors.

### D-H7 — the run-log reads a SNAPSHOT taken at construction, plus a content scan

The first draft read the live flag through a lazy accessor. That is wrong for
the run-log (review F6): a delegated sub-agent runs in a **detached task that
outlives the turn** (`jarvis/agents/delegate.py`, `run_task =
asyncio.create_task(_execute())`), and the Orchestrator's turn — and its
`LLMFullResponseEndFrame` — has often already passed by the time the
sub-agent's `tool_call`/`tool_result`/`finish` land. Reading the live flag then
would see it cleared. So:

- **The flag is snapshotted at `RunLogger` construction.** `RunLogger` gains a
  keyword `sensitive: bool = False`, stored as `self._sensitive`. The **caller**
  passes it — `jarvis/agents/base.py`'s `run()` constructs `RunLogger(...,
  sensitive=is_sensitive())` beside its existing `model=run_model` argument
  (that call site runs on the delegating task, which *does* inherit the
  ContextVar, so `is_sensitive()` reads the real armed state). This mirrors the
  `model=` precedent: a value the run must record, captured once at the one site
  that has it in hand.
- **`store.py` no longer imports `jarvis.bot` at all** — the cycle D-H4's first
  draft worried about is gone, because the boolean is passed in. `store.py` does
  import `detect_financial` from `jarvis.sensitive` (stdlib-only, no cycle:
  `jarvis/runlog/context.py`'s note is about `jarvis.bot`, not `jarvis.sensitive`).
- **Each run-log payload site redacts when `self._sensitive` OR
  `detect_financial(value)` fires.** The content scan is the defence for the
  reply-derived case (review F2/F6): a value the user turn did not telegraph but
  a tool *result* contains still gets redacted, regardless of the snapshot. Over-
  redaction of a diagnostic run-log is the safe direction. The helper:

```python
def _redact(self, value: str) -> bool:
    """True if this run-log value must be replaced with the sentinel.

    Snapshot (the turn was sensitive at delegation time) OR the value itself
    contains a financial detail (a reply-derived value the user turn did not
    telegraph). detect_financial is stdlib-only and total — it never raises.
    """
    if self._sensitive:
        return True
    try:
        return detect_financial(value) is not None
    except Exception:  # noqa: BLE001 — logging must never break the run
        return False
```

Total and safe, consistent with `RunLogger._safe`'s existing "logging must
never break the run" posture (`store.py:195`).

### D-H8 — the memory gate's new financial branch, its position, and its wording

`scan_memory_content` gains one branch, placed **after** the Unicode check and
`_CREDENTIAL_PATTERNS` and **before** `_INJECTION_PATTERNS`. Position is
specified because the function returns the *first* reason and the reason is
logged: a string containing both an API key and a balance should report the API
key (the more urgent leak), and a prompt-injection attempt containing a dollar
amount should report the financial detail (the thing we must not store) rather
than the injection.

The returned reason is exactly, byte for byte:

```
financial detail — not stored (sensitive tier not yet enabled)
```

(that is U+2014 EM DASH, matching K3.) It is a **log/diagnostic reason** in the
style of the function's existing returns (`"possible API key literal"`,
`jarvis/memory.py:185`), not spoken copy. Per R-3 and
`jarvis/bot/remember_tool.py:19–22` D8, it is **never** surfaced to the LLM or
the user: `remember`'s handler keeps returning
`f"Got it — I'll remember {key}."` unchanged (`remember_tool.py:67`), and
`upsert_fact` keeps logging the reason and dropping the write. The roadmap's
spoken sentence "I'm not storing financial details yet" is **not wired by this
plan**; T4b wires user-facing copy when there is somewhere to route to.

*Why not tell the user.* Because `remember_tool.py:19–22` already decided this
question for the credential case and gave the reason: a model told *why* its
write was refused will rewrite the content to evade the filter. Making an
exception for financial content would be the same mistake with higher stakes.

### D-H9 — three deny-list entries + a frozen privilege snapshot protect the mechanisms from self-edit (Larry's commit)

Per `CROSS_PLAN_RESOLUTION.md` §A (Larry's binding decision, 2026-08-26), which
**overrides this plan's first draft**. Add exactly these to
`config/self_edit_allowlist.json`'s `deny` array:

```json
    "jarvis/skills/registry.py",
    "tests/unit/test_agent_isolation.py",
    "tests/unit/test_requires_env_snapshot.py",
```

**`config/agents.yaml` and `mcp_servers/*/skill.yaml` stay editable** — Larry
kept the 2026-08-21 rule that a self-edit may *propose* granting an agent new
tools (the gate is validation + Larry merging the PR). Denying those files
would kill the voice self-repair path. The *enforcement* moves instead into a
frozen snapshot the proposal cannot silently alter:

**New test `tests/unit/test_requires_env_snapshot.py` (this plan owns it; W0;
denied above).** It freezes each server's privilege surface as a dict literal
inside the test file and fails CI if any `skill.yaml` `requires_env` **or** any
`config/mcp_servers.yaml` `env:` map diverges from it. Freezing the `env:` map
as well is what closes review F12 — the `env:`-map re-grant bypass
(`config/mcp_servers.yaml` is allow-listed, and its `env:` map is applied last
and overrides `build_child_env`) — without adding a deny entry for a file the
self-repair path legitimately edits. A self-edit that widens a `requires_env` or
adds `GITHUB_TOKEN: "${GITHUB_TOKEN}"` to `mcp-time`'s `env:` map now turns CI
red until Larry edits the denied snapshot by hand. Deny takes precedence over
the `tests/**` allow — the same precedence the current file already relies on
(`config/**` allowed, `config/skills.yaml` denied). The complete file is in
§7.6.

`jarvis/sensitive.py`, `jarvis/memory.py`, `jarvis/bot/sensitive_turn.py` and
`jarvis/runlog/store.py` need no entry — they match no allow pattern (§1.6,
verified by the review). **The implementing model does not make the
allowlist edit**; §8 V7 is Larry applying **row W0 of
`docs/plans/ALLOWLIST_SEQUENCE.md`** (the single owner of the reconciled
allow-list). §5 Step 9 adds a test that *reports* the current exposure rather
than asserting it, so the plan can be merged before Larry's commit.

**Corrections to the roadmap (D-H9).** The roadmap §1 deny-list row and R-4
above reason toward denying `config/agents.yaml` and `mcp_servers/*/skill.yaml`
outright — and this plan's *first draft of D-H9 did exactly that*. That would
have **reversed Larry's 2026-08-21 decision** to allow self-edits to propose
tool grants. It is corrected here per resolution §A: the proposal stays
possible; the guard is the frozen snapshot, not a deny wall. Any reader of the
roadmap who infers "T4a denies `skill.yaml`" is reading the superseded draft.

### D-H10 — one new env var per mechanism, both defaulting to on

`JARVIS_ENV_SCOPING_ENABLED` and `JARVIS_SENSITIVE_GUARD_ENABLED`, both
`true` by default, both read in exactly one place (§6). `false` restores
today's behaviour exactly — full env inheritance, no detection, no suppression.
Both are documented in `.env.example` as **commented-out** lines (so no default
value is committed and nothing starts requiring them). **Note (review F9):**
`.env.example` does **not** exist in the snapshot (`.gitignore` un-ignores it,
`scripts/mortimer.sh` tells the user to copy it, but the file is absent), so
§5 Steps 2c/5d *create it if absent, else append*. The first draft's claim that
this keeps `scripts/check_env.py` from "requiring" them was wrong — `check_env.py`
reads a hardcoded `REQUIRED_VARS = ["OPENAI_API_KEY", "DEEPGRAM_API_KEY",
"ELEVENLABS_API_KEY"]` and never reads `.env.example`; that rationale is
dropped.

---

## §4 Files (create / modify / delete — complete manifest)

Every file touched by §5 appears here. Nothing else is touched.

### Create (9)

| Path | What it is | Step |
|---|---|---|
| `docs/plans/ALLOWLIST_SEQUENCE.md` | The single owner of the reconciled self-edit allow-list: the final JSON + the four ordered per-wave commit rows (W0-SKILL, W0-SEC, W1-REMOTE, W2-LOCAL), each with a verify command. Referenced by SKILL/REMOTE/LOCAL §8 steps and by SEC §8 V7. Complete content in §5 Step 8d. **A docs file — not code; it is not itself denied, but it *describes* Larry's W0 deny commit** | 8 |
| `jarvis/sensitive.py` | `detect_financial`, `FinancialMatch`, `guard_enabled`, the five patterns, the three checksums, the tuning constants | 3 |
| `jarvis/bot/sensitive_turn.py` | `SensitiveTurn`, `current_sensitive_turn`, `is_sensitive()` (fail-closed), `arm_from_text()`, `redacted()` | 4 |
| `tests/unit/test_sensitive.py` | 28 positive + 64 negative utterances, totality, kill switch, span contract | 3 |
| `tests/unit/test_sensitive_turn.py` | flag lifecycle (incl. the real frame sequence), and the fifteen suppression sites | 4, 6, 7 |
| `tests/unit/test_env_scoping.py` | `build_child_env` unit tests + the K2 acceptance ("spawn `mcp_time`, assert `GITHUB_TOKEN` absent") | 2 |
| `tests/unit/test_agent_isolation.py` | K4 + exposure report, verbatim in §7.4 | 9 |
| `tests/unit/test_requires_env_snapshot.py` | The frozen privilege snapshot (D-H9, resolution §A); verbatim in §7.6. **Denied by W0** so a self-edit cannot rewrite it | 8 |
| `tests/integration/test_env_scoping_live.py` | The one check that spawns real subprocesses; `@pytest.mark.skipif(not os.environ.get("RUN_LIVE"))` per CLAUDE.md's rule that live things live in `tests/integration/` | 2 |

### Modify (22)

| Path | Change | Step |
|---|---|---|
| `mcp_servers/mcp_web/skill.yaml` | `requires_env: [TAVILY_API_KEY, JARVIS_UNITS]` | 1 |
| `mcp_servers/mcp_git/skill.yaml` | `requires_env: [JARVIS_REPO_ROOT]` | 1 |
| `mcp_servers/mcp_repo/skill.yaml` | `requires_env: [JARVIS_REPO_ROOT]` | 1 |
| `mcp_servers/mcp_apps/skill.yaml` | `requires_env: [GITHUB_TOKEN, GITHUB_OWNER]` + `optional_env: [JARVIS_REGISTRY_REPO, JARVIS_REGISTRY_BRANCH]` (F7/F21) | 1 |
| `mcp_servers/mcp_selfedit/skill.yaml` | `optional_env: [JARVIS_UPGRADE_PROFILE]` (F21) | 1 |
| `mcp_servers/mcp_screen/skill.yaml` | `requires_env: [JARVIS_SCREEN_ENABLED, JARVIS_VISION_PROFILE]` + `optional_env: [JARVIS_SCREEN_RETENTION_HOURS, JARVIS_UPGRADE_MODELS]` (F11) + `requires_env_dynamic:` | 1 |
| `config/mcp_servers.yaml` | Rewrite the three stale "the child inherits the full parent environment" comments (`mcp-repo`, `mcp-runlog`, `mcp-screen`). **No `env:` map values change.** | 1 |
| `scripts/check_skills.py` | teach the validator `optional_env` (enforce only `requires_env` presence); add the startup-validation pass over `requires_env_dynamic` sources (F7/F16) | 1 |
| `CLAUDE.md` | the new-MCP-server convention gains the `requires_env`/`optional_env` allowlist clause | 1 |
| `jarvis/skills/registry.py` | `BASE_ENV_KEYS`, `build_child_env()`, `load_requires_env()`, `_resolve_dynamic_env()` (F16: catch `ValueError`, degrade), `env_scoping_enabled()`; `env = dict(os.environ)` (the line `env = dict(os.environ)` at ~L192) → `env = build_child_env(entry)` | 2 |
| `jarvis/memory.py` | import `detect_financial`; one branch in `scan_memory_content` | 5 |
| `jarvis/bot/pipeline.py` | `Runtime.sensitive_turn` field; one `current_sensitive_turn.set(...)` in `run_session` before the pipeline is built | 5 |
| `jarvis/cli.py` | construct a `SensitiveTurn` and `current_sensitive_turn.set(...)` in `main()` before the read loop (F4) | 5 |
| `jarvis/bot/transcript_log.py` | per-turn accumulator; arm on accumulated user text and on the assistant reply; clear on `UserStartedSpeakingFrame`/`InterruptionFrame`; suppress P1, P2, P3, P6, P7 (F1/F2/F13) | 6 |
| `jarvis/agents/supervisor.py` | scan+suppress P4, P5 (class is `Orchestrator`, F19) | 6 |
| `jarvis/agents/base.py` | pass `sensitive=is_sensitive()` to `RunLogger(...)` (F6 snapshot) | 7 |
| `jarvis/runlog/store.py` | `SENSITIVE_SENTINEL`, `sensitive=` ctor arg + `self._sensitive`, `_redact()`; suppress P8, P9, P10, **P12** (`start` task), **P13** (`mcp_call` error) (F5/F6) | 7 |
| `mcp_servers/mcp_notes/logic.py` | financial gate on `create_note`/`update_note` — P14 (F14) | 8 |
| `mcp_servers/mcp_reminders/logic.py` | financial gate on `set_reminder` — P15 (F14) | 8 |
| `.env.example` | **create if absent, else append** two commented-out kill-switch lines (F9) | 2, 5 |
| `docs/plans/MORTIMER_PLATFORM_ROADMAP.md` | see the "Roadmap edits" section at the end of this plan (SEC owns all roadmap edits) | 10 |
| `tests/unit/test_memory.py` | add the financial-gate cases to the existing `scan_memory_content` class | 5 |

### Delete (0)

Nothing is deleted.

### Explicitly NOT touched

`jarvis/vault.py` (import-light, C9), `jarvis/db.py` (no migration, §2.2),
`jarvis/logging_config.py` (§1.3 — nothing to hang a filter on),
`config/self_edit_allowlist.json` (C8 — Larry, §8 V7 / ALLOWLIST_SEQUENCE.md
row W0), `config/agents.yaml` (K4 tests it, does not change it; stays editable
per resolution §A), `jarvis/bot/remember_tool.py` (D-H8 — its behaviour is
already correct), `jarvis/procedures.py` (`learn_from_run` residual, §10 R-H7,
out of this plan's edit set), `requirements*.txt` (§0.10).

## §5 Implementation steps, in order

Do them in this order. Steps 1–2 (K2) and Steps 3–8 (K3 — Step 8 adds the
notes/reminders gates) are independent of each other; Step 9 (K4 + the exposure
report) is independent of both. Run each step's test before
starting the next.

---

### Step 1 — correct the six under-declared `requires_env` (no behaviour change yet)

**Files:** `mcp_servers/mcp_web/skill.yaml`, `mcp_servers/mcp_git/skill.yaml`,
`mcp_servers/mcp_repo/skill.yaml`, `mcp_servers/mcp_apps/skill.yaml`,
`mcp_servers/mcp_selfedit/skill.yaml`, `mcp_servers/mcp_screen/skill.yaml`,
`config/mcp_servers.yaml`, `CLAUDE.md`.

This step is first, but it is **not** inert (correcting the first draft, review
F7): `scripts/check_skills.py` already reads `requires_env` and **enforces
presence** — `for var in m["requires_env"]: if not env.get(var): errors.append(…)`
(`check_skills.py:102–104`), a gate CLAUDE.md lists. Several of the names below
are optional-with-a-code-default (`mcp_apps` defaults `JARVIS_REGISTRY_REPO` to
`"jarvis-voice-ai"`, `JARVIS_REGISTRY_BRANCH` to `"mortimer-dev"`; `mcp_screen`
treats `JARVIS_SCREEN_RETENTION_HOURS` absence as a default; `mcp_selfedit`'s
`JARVIS_UPGRADE_PROFILE` has a default), so listing them under `requires_env`
would print `SKILLS FAIL` for any unset one. They go under a new **`optional_env:`**
key instead — `build_child_env` forwards it identically (copy-if-present, silent
if absent) but `check_skills.py` does **not** enforce its presence (1d). This
also removes the four permanent per-spawn WARNINGs review F21 measured.

**1a.** Set each of the six files as follows (comments show the evidence line
per name; anchor by the `requires_env:` text, not a line number):

`mcp_servers/mcp_web/skill.yaml`
```yaml
requires_env:
  - TAVILY_API_KEY
  # mcp_web/logic.py:71 reads this to choose imperial vs metric for
  # get_weather. Bridged from Settings by jarvis/config.py:265.
  - JARVIS_UNITS
```

`mcp_servers/mcp_git/skill.yaml`
```yaml
# mcp_git/logic.py:44 reads JARVIS_REPO_ROOT. JARVIS_DB_PATH is not listed:
# it is in registry.BASE_ENV_KEYS.
requires_env: [JARVIS_REPO_ROOT]
```

`mcp_servers/mcp_repo/skill.yaml`
```yaml
# mcp_repo/logic.py:98 reads JARVIS_REPO_ROOT.
requires_env: [JARVIS_REPO_ROOT]
```

`mcp_servers/mcp_apps/skill.yaml` (review F7/F21 — the two registry names are
optional-with-default, so `optional_env`, not `requires_env`)
```yaml
# github.py:29 GITHUB_TOKEN, github.py:30 GITHUB_OWNER (both required).
requires_env: [GITHUB_TOKEN, GITHUB_OWNER]
# logic.py:33 JARVIS_REGISTRY_REPO (default "jarvis-voice-ai"),
# logic.py:37 JARVIS_REGISTRY_BRANCH (default "mortimer-dev") — forwarded if
# present, never required (they have code defaults).
optional_env: [JARVIS_REGISTRY_REPO, JARVIS_REGISTRY_BRANCH]
```

`mcp_servers/mcp_selfedit/skill.yaml` (JARVIS_UPGRADE_PROFILE has a default —
`optional_env`; JARVIS_ADMIN_URL is in BASE_ENV_KEYS)
```yaml
# logic.py:127 reads JARVIS_UPGRADE_PROFILE (has a code default).
# JARVIS_ADMIN_URL (logic.py:36) is NOT listed — it is in BASE_ENV_KEYS (K2/K5).
optional_env: [JARVIS_UPGRADE_PROFILE]
```

`mcp_servers/mcp_screen/skill.yaml` (review F11 adds JARVIS_UPGRADE_MODELS, read
transitively via `jarvis.agents.upgrade_agent`; it and JARVIS_SCREEN_RETENTION_HOURS
are optional-with-default)
```yaml
# logic.py:97 JARVIS_SCREEN_ENABLED, logic.py:274 JARVIS_VISION_PROFILE (both
# gate whether vision runs at all).
requires_env: [JARVIS_SCREEN_ENABLED, JARVIS_VISION_PROFILE]
# JARVIS_SCREEN_RETENTION_HOURS (logic.py:108) has a code default.
# JARVIS_UPGRADE_MODELS is read TRANSITIVELY: logic.py:66 imports
# jarvis.agents.upgrade_agent, which reads it (upgrade_agent.py:218) to locate
# config/upgrade_models.yaml — it too has a default path, but if scoping stripped
# it a custom-registry operator would silently load the WRONG registry (review
# F11). optional_env forwards it when the operator has set it; default installs
# (unset) stay green under check_skills.py.
optional_env: [JARVIS_SCREEN_RETENTION_HOURS, JARVIS_UPGRADE_MODELS]
# The vision API key's NAME is a value in config/upgrade_models.yaml
# (api_key_env:), chosen at call time by JARVIS_VISION_PROFILE — see
# mcp_screen/logic.py:283. A static list would go stale the day a profile
# is added, so the registry resolves it from that file at spawn time.
requires_env_dynamic:
  - source: upgrade_models_api_keys
```

**1b.** In `config/mcp_servers.yaml`, three comment blocks now state something
that will be false after Step 2. Replace the phrase "the child inherits the
full parent environment" wherever it appears (the `mcp-repo`, `mcp-runlog` and
`mcp-screen` entries) with:

> "the child's environment is built by SkillRegistry from BASE_ENV_KEYS +
> this server's skill.yaml requires_env (MORTIMER_SECURITY_HARDENING_PLAN.md
> K2); no `env:` entry is needed here."

Keep the rest of each comment — in particular `mcp-repo`'s explanation of why
a literal `${JARVIS_REPO_ROOT}` was harmful is still true and still valuable.
**Do not change any `env:` map value.**

**1c.** In `CLAUDE.md`, in the MCP-server conventions list, after the
`skill.yaml` with `requires_env` clause, add:

> `requires_env` / `optional_env` together must name **every** environment
> variable the server reads (directly or through a `jarvis.*` import) that is
> not in `jarvis/skills/registry.py`'s `BASE_ENV_KEYS`. They are an allowlist,
> not documentation: after `MORTIMER_SECURITY_HARDENING_PLAN.md` K2, an
> undeclared variable does not reach the child. Use `requires_env` for a
> variable with no code default (`check_skills.py` fails if it is unset) and
> `optional_env` for one that has a default (forwarded if present, never
> required). `requires_env_dynamic` is for a variable whose *name* is chosen at
> runtime (only `mcp-screen` today).

**1d.** In `scripts/check_skills.py` (review F7/F16):

- Teach the manifest loader the two new keys: `optional_env` (a list, default
  `[]`) and `requires_env_dynamic` (a list, default `[]`). The presence check
  stays on `requires_env` **only** — `optional_env` names are never asserted
  present.
- Add a **startup-validation pass** that is the *right* home for D-H2's hard
  error (F16): for every server, if `requires_env_dynamic` names a `source`
  not in `registry._DYNAMIC_SOURCES`, append an error. This makes a typo a
  loud check-time failure instead of the `build_child_env` crash the first
  draft would have caused (F16 moves the raise out of the spawn path).

**Test that proves it** — a new test in `tests/unit/test_env_scoping.py`
(`test_every_declared_var_is_actually_read`, §7.2) greps each server package
for each declared name and fails on a declaration nothing reads; and
`test_no_server_reads_an_undeclared_var`, its inverse (now resolving
constant-style reads and one level of `jarvis.*` import, F8/F11). Run:
```
pytest tests/unit/test_env_scoping.py -q
python scripts/check_skills.py     # must print SKILLS OK on a default install
```
(At this point the scoping tests that need Step 2 will fail; that is expected.
The declaration tests and `check_skills.py` must pass.)

---

### Step 2 — `SkillRegistry` builds a scoped env (K2)

**File:** `jarvis/skills/registry.py`, plus `.env.example`.

**2a.** Add near the top of the module, after the existing imports:

```python
# ⚙ TUNING KNOB (plan §6, D-H1) — the ONLY variables every MCP child
# receives regardless of what it declares. This tuple is contract K2 and is
# copied verbatim from MORTIMER_PLATFORM_ROADMAP.md's cross-plan contracts;
# do not reorder or extend it without amending K2, because six plans agree
# on it. Names are copied only when PRESENT in os.environ.
BASE_ENV_KEYS = (
    "PATH", "HOME", "PYTHONPATH", "VIRTUAL_ENV", "LANG", "LC_ALL",
    "TMPDIR", "TZ", "JARVIS_DB_PATH", "JARVIS_TIMEZONE",
    "JARVIS_ADMIN_URL", "JARVIS_LOG_LEVEL",
)

# Kill switch (plan §6, D-H10). Read HERE and nowhere else in the codebase.
ENV_SCOPING_ENABLED_ENV = "JARVIS_ENV_SCOPING_ENABLED"

#: skill.yaml requires_env_dynamic sources. Closed set — an unrecognised
#: source is a hard error, because a typo that silently grants nothing is
#: exactly the failure this track exists to prevent.
_DYNAMIC_SOURCES = ("upgrade_models_api_keys", "vault_names")


def env_scoping_enabled() -> bool:
    """True unless JARVIS_ENV_SCOPING_ENABLED is an explicit false value."""
    return os.environ.get(ENV_SCOPING_ENABLED_ENV, "").strip().lower() not in (
        "0", "false", "no", "off",
    )


def _skill_yaml_path(server_name: str) -> Path:
    """config server name 'mcp-web' -> mcp_servers/mcp_web/skill.yaml."""
    return REPO_ROOT / "mcp_servers" / server_name.replace("-", "_") / "skill.yaml"


def load_requires_env(server_name: str) -> tuple[list[str], list[str], list[dict]]:
    """Return (requires_env, optional_env, requires_env_dynamic) for one server.

    A missing skill.yaml, an unreadable one, or a missing key yields
    ([], [], []) plus a WARNING — a server with no declaration gets
    BASE_ENV_KEYS only, which is the safe direction. Never raises.
    """
    path = _skill_yaml_path(server_name)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except FileNotFoundError:
        logger.warning("skill_yaml_missing server=%s path=%s "
                       "(child gets BASE_ENV_KEYS only)", server_name, path)
        return [], [], []
    except Exception as exc:  # noqa: BLE001
        logger.warning("skill_yaml_unreadable server=%s error=%s "
                       "(child gets BASE_ENV_KEYS only)", server_name, exc)
        return [], [], []
    required = [str(n) for n in (data.get("requires_env") or [])]
    optional = [str(n) for n in (data.get("optional_env") or [])]
    dynamic = list(data.get("requires_env_dynamic") or [])
    return required, optional, dynamic


def _resolve_dynamic_env(server_name: str, dynamic: list[dict]) -> list[str]:
    """Expand requires_env_dynamic entries into concrete variable names.

    Raises ValueError on an unrecognised source (D-H2). The raise is CAUGHT by
    build_child_env (review F16) so a typo cannot brick the voice loop; the
    same validation runs at check-time in scripts/check_skills.py (Step 1d),
    which is where a manifest error belongs.
    """
    names: set[str] = set()
    for entry in dynamic:
        source = (entry or {}).get("source")
        if source not in _DYNAMIC_SOURCES:
            raise ValueError(
                f"{_skill_yaml_path(server_name)}: requires_env_dynamic "
                f"source {source!r} is not one of {_DYNAMIC_SOURCES}"
            )
        if source == "vault_names":
            raise ValueError(
                "requires_env_dynamic source 'vault_names' is not available "
                "before T4b (MORTIMER_SECURITY_HARDENING_PLAN.md D-H2)"
            )
        # upgrade_models_api_keys
        names.add("OPENAI_API_KEY")  # mcp_screen/logic.py:282 default
        try:
            with open(REPO_ROOT / "config" / "upgrade_models.yaml", "r",
                      encoding="utf-8") as fh:
                registry = yaml.safe_load(fh) or {}
        except Exception as exc:  # noqa: BLE001 — degrade to the default only
            logger.warning("upgrade_models_unreadable server=%s error=%s",
                           server_name, exc)
            continue
        for value in _walk_api_key_envs(registry):
            names.add(value)
    return sorted(names)


def _walk_api_key_envs(node: Any) -> Iterator[str]:
    """Yield every `api_key_env` value anywhere in a parsed YAML tree.

    Walks rather than assuming a shape, because config/upgrade_models.yaml
    groups profiles under keys this module has no business knowing about.
    """
    if isinstance(node, dict):
        value = node.get("api_key_env")
        if isinstance(value, str) and value:
            yield value
        for child in node.values():
            yield from _walk_api_key_envs(child)
    elif isinstance(node, list):
        for child in node:
            yield from _walk_api_key_envs(child)


def build_child_env(entry: dict[str, Any]) -> dict[str, str]:
    """Build the environment for one MCP child (K2, plan D-H1).

    BASE_ENV_KEYS (when present) + the server's requires_env (+ dynamic)
    + the server's explicit `env:` map, expanded. Nothing else.

    JARVIS_ENV_SCOPING_ENABLED=false restores full inheritance, and says so
    once at WARNING level so a machine running unscoped is never quiet
    about it.
    """
    name = entry["name"]
    if not env_scoping_enabled():
        logger.warning("mcp_env_scoping_disabled server=%s "
                       "(JARVIS_ENV_SCOPING_ENABLED=false — child inherits "
                       "the FULL parent environment)", name)
        return dict(os.environ)

    env: dict[str, str] = {}
    for key in BASE_ENV_KEYS:
        value = os.environ.get(key)
        if value is not None:
            env[key] = value

    required, optional, dynamic = load_requires_env(name)
    for key in required:
        if key in BASE_ENV_KEYS:
            continue
        value = os.environ.get(key)
        if value is None:
            # K2: spawn proceeds; a WARNING names the server and the
            # variable. Same posture as the existing
            # mcp_server_env_unresolved warning below — a degraded server
            # beats a dead voice loop. Deduplicated per process so a
            # permanently-unset var does not reprint on every restart.
            if (name, key) not in _WARNED_MISSING:
                _WARNED_MISSING.add((name, key))
                logger.warning(
                    "mcp_server_env_missing server=%s var=%s "
                    "(declared in skill.yaml requires_env but not set in "
                    "this process — the child will not receive it)",
                    name, key)
            continue
        env[key] = value

    # optional_env (plan Step 1, review F7/F21): forwarded when present,
    # SILENT when absent — these names have a code default in the server, so
    # a permanently-unset one is normal and must not warn.
    for key in optional:
        if key in BASE_ENV_KEYS or key in env:
            continue
        value = os.environ.get(key)
        if value is not None:
            env[key] = value

    # Dynamic names are "whichever of these exists", not "all of these" —
    # mcp-screen needs ONE vision key and the source yields four. Absence
    # is therefore normal and silent here; mcp_screen/logic.py already
    # produces a precise user-facing error naming the key it wanted.
    #
    # review F16: an unrecognised source raises inside _resolve_dynamic_env;
    # SkillRegistry.start() wraps _start_server in `except: stop(); raise`,
    # so an unguarded raise here would bring the whole voice loop down for a
    # single skill.yaml typo. Catch it, log at ERROR, and degrade to
    # base+required+optional — the same "degraded server beats a dead voice
    # loop" posture as the missing-variable case. The typo is still caught
    # loudly at check-time by scripts/check_skills.py (Step 1d).
    try:
        resolved = _resolve_dynamic_env(name, dynamic)
    except ValueError as exc:
        logger.error("mcp_requires_env_dynamic_invalid server=%s error=%s "
                     "(child gets base+requires_env+optional_env only)",
                     name, exc)
        resolved = []
    for key in resolved:
        if key in BASE_ENV_KEYS or key in env:
            continue
        value = os.environ.get(key)
        if value is not None:
            env[key] = value
    return env
```

and beside `_DYNAMIC_SOURCES`:
```python
#: (server, var) pairs already warned about, so a permanently-unset
#: optional variable warns once per process rather than once per spawn.
_WARNED_MISSING: set[tuple[str, str]] = set()
```

**Imports.** Verified against `jarvis/skills/registry.py:17–33`: `os` (L20),
`logging` (L19), `yaml` (L27), `Path` (L24, from `pathlib`) and `Any` (L25) are
**already imported**; `REPO_ROOT` is already defined at L37. The **only** new
import needed is `Iterator`, which joins the existing
`from typing import Any` line:
```python
from typing import Any, Iterator
```

**2b.** In `_start_server`, replace the line

```python
        env = dict(os.environ)
```
(anchor by that exact text — it is at `jarvis/skills/registry.py:192` in the
snapshot; the review and the brief both cite 192, correcting the first draft's
"191") with
```python
        env = build_child_env(entry)
```

Everything from the next line (`for key, value in (entry.get("env") or {}).items():`)
through `env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")`
is **unchanged**, including the `mcp_server_env_unresolved` warning. That
preserves two properties: the `env:` map still wins over everything (it is
applied last — this is also why the D-H9 snapshot test freezes the `env:` maps,
review F12), and `PYTHONPATH` is still prefixed with `REPO_ROOT` — which matters
more now, since `PYTHONPATH` may be absent from a scoped env and
`env.get("PYTHONPATH", "")` already handles that. **`${VAR}` expansion is
unaffected:** `expand_env_vars` reads the *parent's* `os.environ` (which scoping
never touches; only the child's env is restricted), so every `${...}` in an
`env:` map still resolves, and an unresolved one still stays the literal
seven-char string with the existing warning. Re-verified in the sandbox
(2026-08-27): `${JARVIS_REPO_ROOT}` → `/repo`, `${NOPE}` → `${NOPE}`.

**2c.** In `.env.example`, add under a `# --- security (T4a) ---` heading:

```
# Kill switch: false restores full environment inheritance for MCP children.
# JARVIS_ENV_SCOPING_ENABLED=true
```

**Test that proves it:**
```
pytest tests/unit/test_env_scoping.py -q
```
including K2's own acceptance from the roadmap — spawn `mcp_time`, assert
`GITHUB_TOKEN` is absent (§7.2 `test_mcp_time_gets_no_github_token`).

**Re-measured in the sandbox against the real repo (2026-08-27)**, with the
Step 1 declarations (incl. `optional_env`) applied and `GITHUB_TOKEN`,
`GITHUB_OWNER`, `TAVILY_API_KEY`, `ELEVENLABS_API_KEY`, `DEEPGRAM_API_KEY`,
`OPENROUTER_API_KEY`, `OPENAI_API_KEY`, `JARVIS_TIMEZONE`, `JARVIS_UNITS`,
`JARVIS_REPO_ROOT`, `JARVIS_DB_PATH`, `JARVIS_UPGRADE_MODELS`,
`JARVIS_SCREEN_ENABLED`, `JARVIS_VISION_PROFILE` all set and
`JARVIS_REGISTRY_REPO` **unset** — the env each child receives:

| Server | Keys received |
|---|---|
| `mcp-time` | `HOME`, `JARVIS_DB_PATH`, `JARVIS_TIMEZONE`, `PATH` |
| `mcp-web` | `HOME`, `JARVIS_DB_PATH`, `JARVIS_TIMEZONE`, `JARVIS_UNITS`, `PATH`, `TAVILY_API_KEY` |
| `mcp-apps` | `GITHUB_OWNER`, `GITHUB_TOKEN`, `HOME`, `JARVIS_DB_PATH`, `JARVIS_TIMEZONE`, `PATH` |
| `mcp-screen` | `HOME`, `JARVIS_DB_PATH`, `JARVIS_SCREEN_ENABLED`, `JARVIS_TIMEZONE`, `JARVIS_UPGRADE_MODELS`, `JARVIS_VISION_PROFILE`, `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, `PATH` |
| `mcp-selfedit` | `HOME`, `JARVIS_DB_PATH`, `JARVIS_TIMEZONE`, `PATH` |

`ELEVENLABS_API_KEY` and `DEEPGRAM_API_KEY` reached **no** child;
`GITHUB_TOKEN` reached only `mcp-apps`; `JARVIS_UPGRADE_MODELS` (optional_env)
reached only `mcp-screen` and only because it was set; `JARVIS_REGISTRY_REPO`
(optional_env, unset) reached nobody and printed **no** WARNING (review F21).
`upgrade_models_api_keys` resolved to `['ANTHROPIC_API_KEY', 'MOONSHOT_API_KEY',
'OPENAI_API_KEY', 'OPENROUTER_API_KEY']`; only the two of those present in the
env (`OPENAI_API_KEY`, `OPENROUTER_API_KEY`) reached `mcp-screen`. The invalid
`requires_env_dynamic` source raised `ValueError` and was **caught** inside
`build_child_env` (review F16), the child degrading to base+required+optional.
The missing-`skill.yaml` path returned `([], [], [])` with a WARNING.

---

### Step 3 — `jarvis/sensitive.py` (K3, detection)

**File:** `jarvis/sensitive.py` (new). This is the complete file. Copy it
verbatim — §0.4.

```python
"""Financial-detail detection for the sensitive-turn guard (T4a, contract K3).

Stdlib only, by rule (MORTIMER_SECURITY_HARDENING_PLAN.md §0.5): this module
is imported by jarvis/memory.py, which the bot, the CLI, the admin sidecar and
the MCP memory server all import. A heavy import here costs every one of them.

Nothing in this module stores, encrypts, logs or transmits anything. It
answers one question — "does this text contain a financial detail we must not
persist yet?" — and returns only a KIND and a SPAN, never the matched text, so
a caller that logs a FinancialMatch still leaks nothing.

Every pattern below was re-extracted and executed on 2026-08-27 against the 92
utterances in MORTIMER_SECURITY_HARDENING_PLAN.md §7.1 (28 positive, 64
negative) PLUS this repo's 68-utterance routing-eval fixture
(tests/evals/cases.yaml) — 160 inputs, 0 false positives, 0 false negatives.
The negatives include the 18 shapes that broke the first draft (review F3:
owe⊂borrowed, checking-the-build, account-then-order-number). Changing a
pattern invalidates that measurement — change the tests in the same edit and
re-run.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Literal

Kind = Literal["card", "account", "routing", "iban", "balance"]


@dataclass(frozen=True)
class FinancialMatch:
    """kind: which detector fired. span: the span of the SENSITIVE TOKEN
    itself (the digit run, the IBAN, the money amount) in the input string —
    NOT the span of the keyword context that qualified it. T4b excerpts by
    this span, so widening it would store the surrounding words too."""

    kind: Kind
    span: tuple[int, int]


# --------------------------------------------------------------------------
# Kill switch (plan §6, D-H10). Read HERE and nowhere else in the codebase.
# --------------------------------------------------------------------------

SENSITIVE_GUARD_ENABLED_ENV = "JARVIS_SENSITIVE_GUARD_ENABLED"


def guard_enabled() -> bool:
    """True unless JARVIS_SENSITIVE_GUARD_ENABLED is an explicit false value."""
    return os.environ.get(SENSITIVE_GUARD_ENABLED_ENV, "").strip().lower() not in (
        "0", "false", "no", "off",
    )


# --------------------------------------------------------------------------
# ⚙ TUNING KNOBS (plan §6, D-H5). Each number lives here and nowhere else.
# --------------------------------------------------------------------------

#: ISO/IEC 7812 PAN length, after separators are removed.
CARD_MIN_DIGITS = 13
CARD_MAX_DIGITS = 19
#: A solid digit run this long, after an account keyword, is an account number.
#: 6 excludes 5-digit US zips and 4-digit "ending in" fragments.
ACCOUNT_MIN_DIGITS = 6
ACCOUNT_MAX_DIGITS = 17
#: How far a financial keyword may sit from its digits / money amount
#: (routing and balance only; account uses a connector-chain, not a window).
CONTEXT_WINDOW_CHARS = 40
#: ISO 13616.
IBAN_MIN_TOTAL = 15
IBAN_MAX_TOTAL = 34
#: Below this, an amount beside a financial noun is a trivial IOU, not a
#: balance (plan R-5, re-measured after the word-boundary fix). 25.0 catches a
#: $50/$47.32 balance and rejects "owe you $20 for lunch". Set to 0.0 for the
#: roadmap's literal "any amount beside a financial noun" behaviour.
BALANCE_MIN_AMOUNT = 25.0


# --------------------------------------------------------------------------
# Patterns
# --------------------------------------------------------------------------

# card — an unseparated 13-19 digit run, OR 3-5 groups of 4-6 digits joined by
# single spaces or hyphens. The group FLOOR OF 4 is the load-bearing part: it
# is what rejects dates (2026-08-27 -> 4,2,2), zip+4 (35242-1234 -> only one
# separator, needs >=2), phone numbers (555-123-4567 -> 3,3,4) and SSN shapes
# (123-45-6789 -> 3,2,4) without a single special case.
_CARD_RE = re.compile(
    r"(?<![\w-])(?:\d{13,19}|\d{4,6}(?:[ -]\d{4,6}){2,4})(?![\w-])"
)

# routing — exactly 9 digits AND the ABA checksum AND a routing keyword within
# CONTEXT_WINDOW_CHARS, in either order. All three, because nine bare digits
# is also a zip+4 with the hyphen eaten and a dozen other things.
_ROUTING_RE = re.compile(
    rf"(?i)\b(?:routing|aba|rtn|transit)\b"
    rf"[^\n]{{0,{CONTEXT_WINDOW_CHARS}}}?(?<![\w-])(\d{{9}})(?![\w-])"
    rf"|(?<![\w-])(\d{{9}})(?![\w-])"
    rf"[^\n]{{0,{CONTEXT_WINDOW_CHARS}}}?\b(?:routing|aba|rtn|transit)\b"
)

# account — a connector-chain, NOT a proximity window (review F3). An account
# NOUN (account/acct/checking account/savings account/bank account), then only
# connective tokens (number/num/no/is/ending/in and punctuation) before a SOLID
# 6-17 digit run. A COMPETING noun between the keyword and the digits breaks the
# chain, so "my account, the order number is 8675309" and "log in to my
# account, my member id is 998877" do NOT match (both were false positives in
# the first draft's window rule), while "account number is 000123456789" and
# "Account: 100200300400" do. The bare-verb "checking"/"savings" alternatives
# are gone — they matched "checking build 1049322". Solid (no internal
# separators) still costs a grouped account number ("account 0001 2345 6789");
# see plan §10 R-H3.
_ACCOUNT_RE = re.compile(
    r"(?i)\b(?:(?:checking|savings|bank)\s+account|account|acct)\b"
    r"(?:[\s:#.,\-]*\b(?:number|num|no|is|ending|in)\b)*"
    r"[\s:#.,\-]*"
    rf"(?<![\w-])(\d{{{ACCOUNT_MIN_DIGITS},{ACCOUNT_MAX_DIGITS}}})(?![\w-])"
)

# iban — CC dd + 11..30 alphanumerics, then mod-97. UPPERCASE ONLY: there is
# deliberately no re.IGNORECASE here, and that is what keeps "gpt-5.1",
# "462da350", "97d5cecc" and "eleven_flash_v2_5" out before mod-97 is
# even reached.
_IBAN_RE = re.compile(r"(?<![\w-])([A-Z]{2}\d{2}[A-Z0-9]{11,30})(?![\w-])")

# balance — the roadmap's money shape, plus BALANCE_MIN_AMOUNT (plan R-5),
# adjacent to a financial noun. WORD BOUNDARIES (review F3) are load-bearing:
# without them "owe" matched inside borrowed/however/allowed/followed/flowers/
# tower/vowel/lowered/slowed/showed and "account" inside "accounting". IRA is
# case-SENSITIVE (outside the (?i:...) group) so the given name "Ira" is not a
# financial keyword; everything else is case-insensitive.
_MONEY_RE = re.compile(r"\$\s?(\d{1,3}(?:,\d{3})+(?:\.\d{2})?|\d+(?:\.\d{2})?)")
_FIN_WORD_RE = re.compile(
    r"(?:\b(?i:balance|accounts?|owed?|savings|checking|401\s?k|brokerage)\b|\bIRA\b)"
)


# --------------------------------------------------------------------------
# Checksums
# --------------------------------------------------------------------------

def _luhn_ok(digits: str) -> bool:
    """ISO/IEC 7812 check digit."""
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = ord(ch) - 48
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _aba_ok(digits: str) -> bool:
    """US ABA routing transit number check digit."""
    if len(digits) != 9:
        return False
    d = [ord(c) - 48 for c in digits]
    checksum = (3 * (d[0] + d[3] + d[6])
                + 7 * (d[1] + d[4] + d[7])
                + 1 * (d[2] + d[5] + d[8]))
    return checksum % 10 == 0


def _iban_ok(token: str) -> bool:
    """ISO 13616 mod-97-10."""
    if not (IBAN_MIN_TOTAL <= len(token) <= IBAN_MAX_TOTAL):
        return False
    buf = []
    for ch in token[4:] + token[:4]:
        buf.append(str(ord(ch) - 55) if ch.isalpha() else ch)
    try:
        return int("".join(buf)) % 97 == 1
    except ValueError:
        return False


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def detect_financial(text: str) -> FinancialMatch | None:
    """Return the FIRST financial detail found in `text`, else None.

    Evaluation order is fixed and is part of contract K3:
    card -> routing -> account -> iban -> balance. Ordered most-specific
    first, so "routing 021000021 and account 000123456789" reports the
    routing number rather than the account.

    Pure and total: never raises, never logs, never returns the matched text.
    Returns None unconditionally when the guard is disabled.
    """
    if not text or not isinstance(text, str) or not guard_enabled():
        return None
    try:
        for m in _CARD_RE.finditer(text):
            digits = m.group(0).replace(" ", "").replace("-", "")
            if CARD_MIN_DIGITS <= len(digits) <= CARD_MAX_DIGITS and _luhn_ok(digits):
                return FinancialMatch("card", m.span())

        for m in _ROUTING_RE.finditer(text):
            digits = m.group(1) or m.group(2)
            if digits and _aba_ok(digits):
                return FinancialMatch(
                    "routing", m.span(1) if m.group(1) else m.span(2))

        m = _ACCOUNT_RE.search(text)
        if m is not None:
            return FinancialMatch("account", m.span(1))

        for m in _IBAN_RE.finditer(text):
            if _iban_ok(m.group(1)):
                return FinancialMatch("iban", m.span(1))

        for m in _MONEY_RE.finditer(text):
            try:
                amount = float(m.group(1).replace(",", ""))
            except ValueError:
                continue
            if amount < BALANCE_MIN_AMOUNT:
                continue
            lo = max(0, m.start() - CONTEXT_WINDOW_CHARS)
            hi = min(len(text), m.end() + CONTEXT_WINDOW_CHARS)
            if _FIN_WORD_RE.search(text[lo:hi]):
                return FinancialMatch("balance", m.span())
    except Exception:  # noqa: BLE001 — total by contract; a detector that
        # raises inside the voice loop is worse than one that misses.
        return None
    return None
```

**Test that proves it:** `tests/unit/test_sensitive.py`, §7.1, all 60
enumerated utterances.
```
pytest tests/unit/test_sensitive.py -q
```

---

### Step 4 — `jarvis/bot/sensitive_turn.py` (K3, the flag)

**File:** `jarvis/bot/sensitive_turn.py` (new). Complete file:

```python
"""Per-turn sensitive flag (T4a, contract K3).

The ContextVar is the SINGLE access path (plan D-H4, review F15). run_session
(and the CLI's main) call current_sensitive_turn.set(...) BEFORE the observer,
processor and any turn exist, so every task created afterwards — including the
Pipecat observer's and processor's tasks — inherits the reference and sees its
mutations. The earlier claim that the transcript sites run on tasks "not
children of the turn" was false: they run on tasks created after set().

Runtime.sensitive_turn is the object's LIFETIME OWNER, not a second access path:
a default_factory dataclass field, so one SensitiveTurn is constructed with the
Runtime, published on the ContextVar, and dies with the session. The object is
mutable and shared precisely so a reference copied into a child context stays
live — arm() on the main task is visible to a reader in a child task with no
synchronisation.

The run-log is the ONE exception: it runs in a detached task that outlives the
turn (jarvis/agents/delegate.py), so it reads a boolean SNAPSHOT taken when the
RunLogger is constructed (plan D-H7), never the live flag.

This module stores nothing and persists nothing. The flag dies with the
session; a sensitive turn deliberately does not survive a restart, because
T4a has nowhere to survive to (roadmap C3).
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar

from jarvis.sensitive import detect_financial


class SensitiveTurn:
    """Mutable per-session holder for the current turn's sensitivity.

    Deliberately not a dataclass and not frozen: every suppression site holds
    the SAME instance and must see mutations.
    """

    __slots__ = ("armed", "turn_id", "kind")

    def __init__(self) -> None:
        self.armed: bool = False
        self.turn_id: str | None = None
        self.kind: str | None = None

    def arm(self, kind: str, turn_id: str | None = None) -> None:
        """Mark the current turn sensitive. Idempotent within a turn."""
        self.armed = True
        self.kind = kind
        if self.turn_id is None:
            self.turn_id = turn_id or uuid.uuid4().hex[:8]

    def clear(self) -> None:
        """End of turn. Always safe to call, armed or not."""
        self.armed = False
        self.turn_id = None
        self.kind = None

    def is_armed(self) -> bool:
        return self.armed


current_sensitive_turn: ContextVar[SensitiveTurn | None] = ContextVar(
    "current_sensitive_turn", default=None
)


def is_sensitive() -> bool:
    """True when the current turn is flagged sensitive.

    FAIL-CLOSED, and this is the ONE place that choice is made (review F1/F6):
    an UNSET ContextVar returns True — "treat as sensitive → suppress". The
    ContextVar is always set at every live read site (run_session and the CLI's
    main wire it before any turn), so the None branch is reached only on a
    genuine wiring regression — and then the failure is LOUD (transcripts stop
    appearing, caught immediately by V4) instead of a silent leak. An ordinary
    turn logs normally: its holder is set and is_armed() is False.
    """
    holder = current_sensitive_turn.get()
    if holder is None:
        return True  # fail-closed
    return holder.is_armed()


def current_turn_id() -> str:
    """The armed turn's id, for redacted log lines. '-' when not armed/unset."""
    holder = current_sensitive_turn.get()
    if holder is None or holder.turn_id is None:
        return "-"
    return holder.turn_id


def arm_from_text(text: str, turn_id: str | None = None) -> bool:
    """Run detection on `text` and arm the current turn if it matches.

    Called on BOTH the user text and the assistant reply (review F2). Returns
    True when it armed. Total: a missing holder is a no-op, not a crash — this
    runs inside the voice loop.
    """
    match = detect_financial(text)
    if match is None:
        return False
    holder = current_sensitive_turn.get()
    if holder is None:
        return False
    if turn_id is None:
        # Correlate the redacted log line with the run, when inside one
        # (review F17). Lazy import: jarvis.runlog must not be imported at this
        # module's top (it would pull jarvis.agents, a heavier graph); this is
        # the only place we need it.
        try:
            from jarvis.runlog import get_run_id
            turn_id = get_run_id() or None
        except Exception:  # noqa: BLE001
            turn_id = None
    holder.arm(match.kind, turn_id)
    return True


def redacted(text: str) -> str:
    """The line that replaces a transcript print on a sensitive turn.

    Carries the turn id and a length ONLY — never a character of content,
    never the detected kind (the kind is itself a hint about the value).
    (review F20: no `role` parameter — the caller supplies the USER:/MORTIMER:
    prefix itself.)
    """
    return f"<sensitive turn {current_turn_id()}: {len(text)} chars withheld>"
```

**Test that proves it:** `tests/unit/test_sensitive_turn.py` §7.3, lifecycle
group.

---

### Step 5 — wire the flag into `Runtime` and the memory gate

**Files:** `jarvis/bot/pipeline.py`, `jarvis/memory.py`, `.env.example`,
`tests/unit/test_memory.py`.

**5a.** `jarvis/bot/pipeline.py` — add the import beside the other
`jarvis.bot.*` imports (they run to line 68):
```python
from jarvis.bot.sensitive_turn import SensitiveTurn, current_sensitive_turn
```
and add a field to the `Runtime` dataclass, after `speaker_gate` (anchor:
the `speaker_gate: Any = None` field):
```python
    # T4a K3 — per-turn sensitive flag. Runtime OWNS the object's lifetime
    # (constructed per session, dies with it); the ContextVar in
    # jarvis/bot/sensitive_turn.py publishes a reference to THIS object and is
    # the single access path (review F15). Never persisted.
    sensitive_turn: SensitiveTurn = field(default_factory=SensitiveTurn)
```

**5b.** In `run_session`, immediately after the `Runtime` is constructed and
**before** `build_pipeline` is called, add:
```python
    # T4a K3 — publish the session's flag object into the context so
    # delegated sub-agent tasks (jarvis/runlog/store.py) can read it. Set
    # once per session; the object is mutated, never replaced.
    current_sensitive_turn.set(runtime.sensitive_turn)
```
Locate the construction by searching for `Runtime(` in `jarvis/bot/pipeline.py`.
If `run_session` receives an already-built `Runtime`, put the `set()` call as
the first statement of `run_session`. **Initialization timing is load-bearing**
(taxonomy item 6): the `set()` must happen before `TranscriptObserver` and
`TranscriptLogger` are constructed, or the first turn reads an unset var.

**5c.** `jarvis/memory.py` — add to the imports:
```python
from jarvis.sensitive import detect_financial
```
Add a module constant beside `_CREDENTIAL_PATTERNS` (L184):
```python
# T4a K3 — the memory gate's financial refusal. This is a LOG/DIAGNOSTIC
# reason in the style of the _CREDENTIAL_PATTERNS reasons above, not spoken
# copy: jarvis/bot/remember_tool.py:19-22 (D8) forbids surfacing a scan
# rejection reason to the LLM, which would otherwise rewrite the content to
# evade the filter. T4b replaces the refusal with a route to the tier.
FINANCIAL_REJECTION = "financial detail — not stored (sensitive tier not yet enabled)"
```
Then insert the branch into `scan_memory_content`, between the
`_CREDENTIAL_PATTERNS` loop (ends L311) and the `lowered = text.lower()` line
(L312):
```python
    if detect_financial(text) is not None:
        return FINANCIAL_REJECTION
```
The final function reads:
```python
def scan_memory_content(text: str) -> str | None:
    """Return a short rejection reason if `text` is unsafe to persist as
    memory (prompt injection, credential/exfiltration pattern, financial
    detail, or invisible Unicode), else None. Pure and total — never raises."""
    if not text:
        return None
    if any(ch in _DANGEROUS_UNICODE for ch in text):
        return "invisible or bidirectional unicode detected"
    for pattern, reason in _CREDENTIAL_PATTERNS:
        if pattern.search(text):
            return reason
    if detect_financial(text) is not None:
        return FINANCIAL_REJECTION
    lowered = text.lower()
    for pattern, reason in _INJECTION_PATTERNS:
        if pattern.search(lowered):
            return reason
    return None
```
**Order is specified, not incidental** (D-H8): credentials outrank financial
details (the more urgent leak), and financial details outrank injection
phrasing (a jailbreak carrying a balance must be refused as financial, because
that is the thing we must not store).

All three existing call sites (`memory.py:542`, `:575`, `:606`) already handle
a non-`None` return by refusing the write and logging — no change needed there,
and none is made. `remember_tool.py` is unchanged (D-H8).

**5d.** `.env.example` — under the `# --- security (T4a) ---` heading (created
in Step 2c if the file is absent, review F9):
```
# Kill switch: false disables financial detection and all turn suppression.
# JARVIS_SENSITIVE_GUARD_ENABLED=true
```

**5e.** `jarvis/cli.py` — the text/CLI path (P4, P5) needs its own
`SensitiveTurn`, because it has no `run_session` and no `TranscriptObserver`
(review F4). `jarvis/cli.py:16` imports `Orchestrator` and `:97` calls
`orchestrator.chat(line)`. Add the import and, in `main()`, **after**
`bridge_settings_to_env()` and **before** the read loop:
```python
from jarvis.bot.sensitive_turn import SensitiveTurn, current_sensitive_turn
...
    # T4a K3 — the text path has no pipeline; wire the flag here so
    # Orchestrator.chat's P4/P5 guards (and any delegated RunLogger snapshot)
    # see a real holder. Set once, before the read loop (review F4).
    current_sensitive_turn.set(SensitiveTurn())
```
Without this, `is_sensitive()` fails **closed** (Step 4) and the CLI would
suppress *every* turn — which is the loud failure, but not the behaviour we
want; the `set()` makes ordinary CLI turns log normally and sensitive ones
suppress. `jarvis/agents/supervisor.py`'s class is `Orchestrator`, not
`Supervisor` (review F19).

**Test that proves it:**
```
pytest tests/unit/test_memory.py -q tests/unit/test_sensitive_turn.py -q
```

---

### Step 6 — suppress the transcript sites P1–P7

**Files:** `jarvis/bot/transcript_log.py`, `jarvis/agents/supervisor.py`.

The frame order this step relies on is stated in D-H4. In summary, per turn the
observer/processor see: `UserStartedSpeakingFrame` (clear + reset accumulator)
→ one or more finalized `TranscriptionFrame` (accumulate + arm, buffer) →
`UserStoppedSpeakingFrame` (flush the user side once) → LLM → `LLMTextFrame`s →
`LLMFullResponseEndFrame` (scan reply, flush assistant side); a barge-in raises
`UserStartedSpeakingFrame`/`InterruptionFrame` first.

**6a.** `jarvis/bot/transcript_log.py` — add the frames and the helper import.
Add `UserStartedSpeakingFrame` and `InterruptionFrame` to the existing
`from pipecat.frames.frames import (...)` block (verified in pipecat 1.4:
`InterruptionFrame` at `frames.py:1018`, `UserStartedSpeakingFrame` at
`:1030` — note the class is `InterruptionFrame`, **not** `StartInterruptionFrame`;
the review's F1 named the latter, which does not exist in this pipecat), and:
```python
from jarvis.bot.sensitive_turn import (
    arm_from_text, current_sensitive_turn, is_sensitive, redacted,
)
```

**6b — `TranscriptLogger.process_frame` (the ASSISTANT side, P2/P7, reply
scan).** Two changes. First, add a `InterruptionFrame` branch that
**discards** the partial assistant buffer and clears the flag on a barge-in
(review F1 — there is no such branch today, so a partial sensitive reply
survives into the next turn and is flushed after the flag was cleared):
```python
        if isinstance(frame, InterruptionFrame):
            # Barge-in: drop the half-built reply so it is never flushed, and
            # clear the flag (plan D-H4). Do this BEFORE super()/push.
            self._assistant_buffer = []
            holder = current_sensitive_turn.get()
            if holder is not None:
                holder.clear()
```
Second, replace the `LLMFullResponseEndFrame` branch (anchor: the
`elif isinstance(frame, LLMFullResponseEndFrame):` block that joins
`self._assistant_buffer`) with — note it **scans the reply** before deciding
(review F2), and does **not** clear the flag (clearing is on the next
`UserStartedSpeakingFrame`/`InterruptionFrame`, so a late-constructed
run-log still snapshots the right value, review F6):
```python
        elif isinstance(frame, LLMFullResponseEndFrame):
            text = "".join(self._assistant_buffer).strip()
            self._assistant_buffer = []
            if text:
                # P2/P7 (plan D-H6, review F2): the reply itself may be the
                # only place the value appears ("what's my balance?" ->
                # "$2,431.18"). Scan it before printing/persisting.
                arm_from_text(text)
                if is_sensitive():
                    print(f"[{_ts()}] {ASSISTANT_LOG_PREFIX} "
                          f"{redacted(text)}", flush=True)
                else:
                    print(f"[{_ts()}] {ASSISTANT_LOG_PREFIX} {text}", flush=True)
                    self._persist("assistant", text)
            self._log_turn("llm_done")
```

**6c — `TranscriptObserver`, start-of-turn boundary (review F1/F13).** Give the
observer a per-turn accumulator in `__init__`: `self._user_buffer: list[str] = []`.
Replace the `UserStartedSpeakingFrame` handling (add a branch — today the
observer has none) so the flag is cleared and the accumulator reset at the
**true start of the turn** (this is also the first frame a barge-in raises, so
the previous turn's flag never leaks into this one):
```python
        if isinstance(frame, UserStartedSpeakingFrame):
            holder = current_sensitive_turn.get()
            if holder is not None:
                holder.clear()
            self._user_buffer = []
            return
```
The existing `UserStoppedSpeakingFrame` branch keeps setting the latency
baseline, and now **flushes the accumulated user text once** (review F13 — a
Flux-split "my routing number is" / "021000021" is only detectable on the
joined text, and must not be printed/persisted per segment):
```python
        if isinstance(frame, UserStoppedSpeakingFrame):
            self._turn_start = time.perf_counter()
            self._audio_logged_for_turn = False
            text = " ".join(self._user_buffer).strip()
            self._user_buffer = []
            if text:
                arm_from_text(text)          # arm on the FULL turn text
                if is_sensitive():
                    # P6 (plan D-H6): no content to bot.log, no conversations row
                    print(f"[{_ts()}] USER: {redacted(text)}", flush=True)
                else:
                    print(f"[{_ts()}] USER: {text}", flush=True)
                    _persist(self._session_id, "user", text)  # P1
            return
```

**6d — `TranscriptObserver`, finalized transcript (accumulate, do NOT emit).**
Replace the tail of `on_push_frame` (anchor: the `text = frame.text.strip()`
block that today prints and `_persist`s each finalized frame) with an
accumulate-only body — the print/persist moved to 6c's flush:
```python
        text = frame.text.strip()
        if not text:
            return
        # review F13: accumulate; detection and emit happen once at turn close
        # (6c). Arm incrementally too, so a single-segment turn is armed as
        # early as possible; arm_from_text is idempotent and total.
        self._user_buffer.append(text)
        arm_from_text(" ".join(self._user_buffer))
```
(The speaker-gate `only_from` filter and the `finalized` check above this block
are unchanged — a gated/non-final frame is still skipped before it reaches the
accumulator.)

**6e.** Add the defence-in-depth guard as the first statement of the module
`_persist` (anchor: `def _persist(session_id: str, role: str, content: str)`):
```python
def _persist(session_id: str, role: str, content: str) -> None:
    # P3 (plan D-H6) — defence in depth. P1/P2 already avoid calling this on a
    # sensitive turn; this makes a future caller that forgets harmless. Note
    # is_sensitive() is fail-closed, so an unwired context suppresses here too.
    if is_sensitive():
        return
    try:
        with get_conn() as conn:
            ...
```
(the rest of the function is unchanged.)

**6f.** `jarvis/agents/supervisor.py` — the CLI/text path (P4, P5), class
`Orchestrator` (review F19). Add:
```python
from jarvis.bot.sensitive_turn import arm_from_text, is_sensitive
```
Replace the `self._persist("user", user_text)` line (anchor that text) with —
the text path scans the user turn itself (there is no `TranscriptObserver`
here; `jarvis/cli.py` sets a `SensitiveTurn`, §5 Step 5e):
```python
        arm_from_text(user_text)               # T4a K3 (P4)
        if not is_sensitive():
            self._persist("user", user_text)
```
Replace the `self._persist("assistant", reply)` line with — scan the reply too
(review F2), for exactly the "what's my balance" case:
```python
        arm_from_text(reply)                    # T4a K3 (P5), review F2
        if not is_sensitive():
            self._persist("assistant", reply)
```

*On the import cycle.* Verified safe: `jarvis/bot/__init__.py` is **empty**,
and `jarvis/bot/sensitive_turn.py` imports only `jarvis.sensitive` (stdlib) and
lazily `jarvis.runlog`, so `jarvis.agents.supervisor` → `jarvis.bot.sensitive_turn`
terminates. A top-level import is correct here. *Decision tree if it
nevertheless fails:* run `python3 -c "import jarvis.agents.supervisor"`. If it
raises `ImportError`, move both names into a local import inside `chat()`, note
it in your final report, and do **not** duplicate the flag into a second module.
If it raises anything else, stop and report (§0.8).

**Test that proves it:**
```
pytest tests/unit/test_sensitive_turn.py -q
```

---

### Step 7 — suppress the run-log sites P8–P10, P12, P13

**Files:** `jarvis/runlog/store.py`, `jarvis/agents/base.py`.

**7a — the sentinel, the snapshot, the redactor.** In `jarvis/runlog/store.py`,
add beside `_DROPPED` (`store.py:66`):
```python
from jarvis.sensitive import detect_financial  # stdlib-only; no jarvis.bot cycle

# T4a K3 — replaces a payload value on a sensitive turn. A STRING, and
# deliberately shaped like the _DROPPED sentinel above, so every reader
# (mcp_runlog/logic.py, the Runs drawer tab, tests) still finds every key
# present with the type it expects. K3: "run-log payloads reduced to tool
# names" — the tool name, seq, ok and latency are always kept.
SENSITIVE_SENTINEL = "<sensitive>"
```
Add a `sensitive: bool = False` keyword to `RunLogger.__init__` (beside
`model`) and store it (review F6 — the snapshot):
```python
        model: str | None = None,
        sensitive: bool = False,
    ) -> None:
        ...
        self.model = model
        # T4a K3 (plan D-H7). Snapshotted at construction because a delegation
        # runs in a DETACHED task that outlives the turn — reading the live
        # flag at write time would see it cleared (review F6).
        self._sensitive = sensitive
```
Add the redactor method (plan D-H7 — snapshot OR content scan; the content scan
catches a reply-derived value the user turn did not telegraph, review F2/F6):
```python
    def _redact(self, value: str) -> bool:
        if self._sensitive:
            return True
        try:
            return detect_financial(value) is not None
        except Exception:  # noqa: BLE001 — logging must never break the run
            return False
```

**7a-bis — the caller passes the snapshot.** In `jarvis/agents/base.py`'s
`run()`, where `RunLogger(...)` is constructed with `model=run_model`, add:
```python
from jarvis.bot.sensitive_turn import is_sensitive   # top of module
...
        runlog = RunLogger(
            resolved_run_id, self.name, self.display_name, task,
            session_id=session_id,
            enabled=self._settings.jarvis_runlog_enabled,
            model=run_model,
            sensitive=is_sensitive(),   # T4a K3 snapshot (review F6)
        )
```
This call runs on the delegating task, which inherits the ContextVar, so
`is_sensitive()` reads the real armed state. (Import note: `jarvis.agents.base`
→ `jarvis.bot.sensitive_turn` → `jarvis.sensitive` (+ lazy `jarvis.runlog`);
`jarvis/bot/__init__.py` is empty, so no cycle. If a cycle nevertheless
surfaces, use a lazy import at the call site and report it, §0.8.)

**7b — `tool_call` (P8).** Redact `arguments` when `self._redact(args_json)`:
```python
            args_json = json.dumps(arguments, default=str)
            redact = self._redact(args_json)
            stored_args = SENSITIVE_SENTINEL if redact else arguments
            args_json = SENSITIVE_SENTINEL if redact else args_json
            self._append(
                {"type": "tool_call", "seq": seq, "tool": tool, "at": now_iso()},
                payload_key="arguments", payload_value=stored_args,
                size_str=args_json,
            )
            self._execute(
                "INSERT INTO agent_events (run_id, seq, type, tool, "
                "args_preview, created_at) VALUES (?, ?, 'tool_call', ?, ?, ?)",
                (self.run_id, seq, tool, _truncate(args_json), now_iso()),
            )
```

**7c — `tool_result` (P9).** `self._tools_ok/_tools_failed` counters above are
**unchanged** (counts are not content):
```python
            stored = SENSITIVE_SENTINEL if self._redact(result) else result
            self._append(
                {"type": "tool_result", "seq": seq, "tool": tool, "ok": bool(ok),
                 "latency_ms": latency_ms, "at": now_iso()},
                payload_key="result", payload_value=stored, size_str=stored,
            )
            self._execute(
                "INSERT INTO agent_events (run_id, seq, type, tool, ok, "
                "latency_ms, result_preview, created_at) "
                "VALUES (?, ?, 'tool_result', ?, ?, ?, ?, ?)",
                (self.run_id, seq, tool, 1 if ok else 0, latency_ms,
                 _truncate(stored), now_iso()),
            )
```

**7d — `finish` (P10).** After `status = self._derive_status(reply)` and
`error = _truncate(reply) if status != "ok" else None` and
`reply_preview = _truncate(reply)` (so status is still derived from the real
reply), insert:
```python
            if self._redact(reply):
                reply = SENSITIVE_SENTINEL
                reply_preview = SENSITIVE_SENTINEL
                if error is not None:
                    error = SENSITIVE_SENTINEL
```

**7e — `start` task (P12, review F5).** `task` is the delegation text composed
from the user's utterance and is written to both the `run_start` JSONL record
and the `agent_runs.task` column. It is known at construction, so the snapshot
alone suffices; use `self._redact(self.task)`:
```python
        def _do() -> None:
            self._started_at = now_iso()
            date = self._started_at[:10]
            self.payload_path = RUNLOG_DIR / date / f"{self.run_id}.jsonl"
            task = SENSITIVE_SENTINEL if self._redact(self.task) else self.task
            self._buffer.append({
                "type": "run_start", "seq": self._next_seq(),
                "run_id": self.run_id, "agent": self.agent,
                "display_name": self.display_name,
                "session_id": self.session_id, "task": task,
                "started_at": self._started_at,
            })
            self._execute(
                "INSERT INTO agent_runs (run_id, session_id, agent, "
                "display_name, task, status, started_at, tool_count, model) "
                "VALUES (?, ?, ?, ?, ?, 'running', ?, 0, ?)",
                (self.run_id, self.session_id, self.agent, self.display_name,
                 task, self._started_at, self.model),
            )
        self._safe("start", _do)
```

**7f — `mcp_call` error (P13, review F5).** The `error` field is built from the
failing tool's own message, which can echo an argument:
```python
            err = (SENSITIVE_SENTINEL
                   if (error is not None and self._redact(error)) else error)
            self._buffer.append({
                "type": "mcp_call", "seq": seq, "tool": tool, "server": server,
                "ok": bool(ok), "latency_ms": latency_ms, "error": err,
                "at": now_iso(),
            })
```
(the `INSERT INTO agent_events (... 'mcp_call' ...)` below it does not store
`error`, so it is unchanged.)

**Test that proves it:**
```
pytest tests/unit/test_sensitive_turn.py tests/unit/test_runlog_store.py -q
```

---

### Step 8 — the notes and reminders financial gates (P14, P15) + the requires_env snapshot test

**Files:** `mcp_servers/mcp_notes/logic.py`, `mcp_servers/mcp_reminders/logic.py`,
`tests/unit/test_requires_env_snapshot.py` (new).

**8a — notes gate (P14, review F14).** `mcp_notes.create_note(title, body, tags)`
(`logic.py:26`) and `update_note` INSERT their arguments verbatim
(`logic.py:36`) with no scan today; the routing-eval fixture proves "save a note
that …" is squarely in-domain. Import the gate and refuse a financial write:
```python
from jarvis.memory import scan_memory_content   # already imports detect_financial

def create_note(title: str, body: str, tags: str = "") -> dict:
    reason = scan_memory_content(title) or scan_memory_content(body)
    if reason is not None:
        # A note that failed to save MUST report failure (unlike the memory
        # gate, which confirms cheerfully — a note is an explicit user request
        # to store something). The refusal names the CATEGORY only, never the
        # content, and is a FIXED string (not `reason`, which could carry more
        # detail). T4b routes this to the encrypted tier instead of refusing.
        return {"error": "not saved: financial detail (sensitive tier not yet enabled)"}
    ... # existing INSERT unchanged
```
Apply the same guard to `update_note`. `mcp_notes` runs as a subprocess that
imports `jarvis.memory` today (verify with `python -c "import
mcp_servers.mcp_notes.logic"`); if that import is not already present, import
`jarvis.sensitive.detect_financial` directly instead (stdlib-only, §0.5) and
inline the one-line check.

**8b — reminders gate (P15, review F14).** Same shape on
`mcp_reminders.set_reminder(message, due_expression)` (`logic.py:169`, INSERT at
`:181`): refuse when `scan_memory_content(message)` is non-`None`.

**8c — the requires_env snapshot test (D-H9, resolution §A).** Create
`tests/unit/test_requires_env_snapshot.py` — the complete file is in §7.6. It
freezes each server's `requires_env`/`optional_env` (from `skill.yaml`) **and**
`env:` map (from `config/mcp_servers.yaml`) as dict literals and fails if any
diverges. This is the guard that replaces D-H9's dropped `skill.yaml` deny
(resolution §A); it is denied by W0 so a self-edit cannot rewrite it.

**8d — author `docs/plans/ALLOWLIST_SEQUENCE.md` (the single owner of the
allow-list, resolution §A/§D).** This is a **docs file SEC owns**; SKILL (row
W0-SKILL), REMOTE (W1), LOCAL (W2) and SEC's own §8 V7 (W0-SEC) all point their
§8 Larry-steps at it, so it must exist as a standalone file, not only inlined
here. Create it verbatim with the content below — the reconciled final JSON
plus all four ordered rows, each with its verify command. (This is the same
content SEC references from §8 V7 and R-4/D-H9; authoring it here is what makes
the sibling plans' "apply row N of ALLOWLIST_SEQUENCE.md" instruction resolvable.)

````markdown
# Self-edit allow-list — reconciled final state and ordered commits

**Status:** binding, 2026-08-27. Owner: `MORTIMER_SECURITY_HARDENING_PLAN.md`
(SEC) per `CROSS_PLAN_RESOLUTION.md` §A/§D. This document is the **single owner**
of `config/self_edit_allowlist.json` across the Mortimer track plans. Each
plan's §8 allow-list step is: *"apply row N of this file and run its verify
command."* No plan edits the allow-list directly; every change is a **human
commit** (roadmap C8). `config/agents.yaml` and `mcp_servers/*/skill.yaml` stay
editable (resolution §A); the privilege guard is `jarvis/skills/registry.py`
(denied) + the frozen `tests/unit/test_requires_env_snapshot.py` (denied).

## Reconciled final `config/self_edit_allowlist.json`

Deny wins over allow (`jarvis/selfedit/allowlist.py` — any deny match rejects;
otherwise the path must match some allow pattern), so a denied `tests/unit/…`
file stays denied even though `tests/**` is allowed.

```json
{
  "allow": [
    "web/src/**", "web/public/**", "config/**", "jarvis/prompts.py",
    "jarvis/skills/**", "jarvis/services/**", "mcp_servers/**",
    "skills/**", "tests/**", "docs/**", "*.md"
  ],
  "deny": [
    ".github/**", "jarvis/selfedit/**", "jarvis/agents/**",
    "jarvis/wakeword/**", "jarvis/bot/**", "jarvis/admin/**",
    "config/self_edit_allowlist.json", "config/upgrade_agent.yaml",
    "config/upgrade_models.yaml", "config/skills.yaml",
    "requirements*.txt", "web/package.json", "web/package-lock.json",
    "DEVIATIONS.md", ".env", ".env.*", "**/.env", "**/.env.*",
    "jarvis/vault.py", "data/**", "*.vault", "**/*.vault", "macos/**",

    "jarvis/skills/registry.py",
    "tests/unit/test_agent_isolation.py",
    "tests/unit/test_requires_env_snapshot.py",
    "jarvis/auth.py", "jarvis/authmw.py", "jarvis/bind.py",
    "docs/runbooks/**"
  ]
}
```

## Ordered commits (apply in wave order W0 → W2; within W0, SKILL then SEC)

| # | Wave | Plan | Change to `config/self_edit_allowlist.json` | Verify command |
|---|---|---|---|---|
| **W0-SKILL** | W0 | `MORTIMER_SKILL_AUTHORING_PLAN.md` | Move `"skills/**"` from `deny` to `allow` (add/remove these exact strings — do **not** apply a stored unified diff; SEC's W0-SEC entries change surrounding lines). `config/skills.yaml` **stays in `deny`** (the one-at-a-time enable rule); `config/agents.yaml` is **not** touched (it stays editable per resolution §A). | `python -c "import json,sys; a=json.load(open('config/self_edit_allowlist.json')); ok = ('skills/**' in a['allow'] and 'skills/**' not in a['deny'] and 'config/skills.yaml' in a['deny'] and 'config/agents.yaml' not in a['deny']); sys.exit(0 if ok else 1)"` — exit 0. Then `pytest tests/unit -q` stays green. |
| **W0-SEC** | W0 | `MORTIMER_SECURITY_HARDENING_PLAN.md` | Add to `deny`: `"jarvis/skills/registry.py"`, `"tests/unit/test_agent_isolation.py"`, `"tests/unit/test_requires_env_snapshot.py"`. **Do NOT** add `config/agents.yaml` or `mcp_servers/*/skill.yaml`. | `pytest tests/unit/test_agent_isolation.py -q -s` → exposure line reads `none — V7 commit is in`; `pytest tests/unit/test_requires_env_snapshot.py -q` passes. |
| **W1-REMOTE** | W1 | `MORTIMER_REMOTE_ACCESS_PLAN.md` | Add to `deny`: `"jarvis/auth.py"`, `"jarvis/authmw.py"`, `"jarvis/bind.py"`. | `python -c "import json,sys; d=json.load(open('config/self_edit_allowlist.json'))['deny']; sys.exit(0 if all(x in d for x in ['jarvis/auth.py','jarvis/authmw.py','jarvis/bind.py']) else 1)"` — exit 0; plus REMOTE's `tests/unit/test_service_token.py` passes. |
| **W2-LOCAL** | W2 | `MORTIMER_LOCAL_VOICE_AND_MINI_PLAN.md` | Add to `deny`: `"docs/runbooks/**"`. | `python -c "import json,sys; sys.exit(0 if 'docs/runbooks/**' in json.load(open('config/self_edit_allowlist.json'))['deny'] else 1)"` — exit 0. |

General verify at every row (if present): `python3 scripts/check_allowlist.py origin/main...HEAD`.
````

**Test that proves it:**
```
pytest tests/unit/test_requires_env_snapshot.py -q
python -c "import mcp_servers.mcp_notes.logic, mcp_servers.mcp_reminders.logic"
test -f docs/plans/ALLOWLIST_SEQUENCE.md    # the sibling plans' §8 steps resolve
```

---

### Step 9 — the agent isolation test (K4) + the self-edit exposure report

**File:** `tests/unit/test_agent_isolation.py` (new). Complete file in §7.4.
No production file changes. It must pass on today's `config/agents.yaml`.
`OUTBOUND` includes `mcp-screen` and `mcp-calendar` per resolution §B.

The same file carries `test_report_self_edit_exposure` (§7.4). It **does not
assert**; it prints which of the D-H9 guarded paths are currently writable by
the self-edit loop, so the suite can be merged before Larry's commit and the
state is visible in CI either way. When Larry applies **ALLOWLIST_SEQUENCE.md
row W0** (§8 V7), the printed list becomes empty. Per taxonomy item 9 — the plan
must not claim a file is protected while §8 says Larry has yet to protect it.

```
pytest tests/unit/test_agent_isolation.py -q -s
```

---

### Step 10 — roadmap and docs housekeeping

**File:** all roadmap edits are collected in the **"Roadmap edits"** section at
the end of this plan (SEC owns every `docs/plans/MORTIMER_PLATFORM_ROADMAP.md`
edit per the brief and resolution §D). The implementer applies that section's
literal before/after blocks; Larry commits. This step no longer edits the
roadmap inline — it is a pointer, so the single owner of the roadmap deltas is
one place.

## §6 Tuning knobs — where every number lives (one place each)

Every value below is defined in exactly one module. No duplicate literal
appears anywhere else in the codebase, including in tests: tests import the
constant.

### Kill switches (env vars, read in ONE place each)

| Env var | Default | Read at | Effect when `false`/`0`/`no`/`off` |
|---|---|---|---|
| `JARVIS_ENV_SCOPING_ENABLED` | `true` | `jarvis/skills/registry.py`, `env_scoping_enabled()` — the only `os.environ.get` for this name in the repo | `build_child_env` returns `dict(os.environ)`, i.e. today's behaviour exactly, and logs `mcp_env_scoping_disabled` once per server spawn |
| `JARVIS_SENSITIVE_GUARD_ENABLED` | `true` | `jarvis/sensitive.py`, `guard_enabled()` — the only `os.environ.get` for this name in the repo | `detect_financial` returns `None` unconditionally ⇒ `arm_from_text` never arms ⇒ `is_sensitive()` returns `False` (the holder stays `armed=False`) ⇒ every one of the fifteen sites in D-H6 behaves exactly as today, including the gates |

Both are documented in `.env.example` (created if absent, review F9) as
**commented-out** lines — no committed default value. (There is no
`check_env.py` interaction; that first-draft rationale was wrong, D-H10.)

**Fail-closed choice.** `is_sensitive()` returns `True` on an **unset**
ContextVar (Step 4, review F1/F6). This is not a knob — it is the one place the
fail-open/closed choice is made, and it is fail-CLOSED so a wiring regression is
loud (transcripts stop) rather than a silent leak. It never fires in normal
operation because the ContextVar is set at session/CLI start before any turn.
The kill switch above is the intended way to disable the guard; unsetting the
ContextVar is not.

### Constants

| Constant | Value | Module | What it governs |
|---|---|---|---|
| `BASE_ENV_KEYS` | 12-name tuple (D-H1) | `jarvis/skills/registry.py` | The only variables every MCP child gets. **Contract K2 — six plans agree on it; amend K2 before changing.** |
| `_DYNAMIC_SOURCES` | `("upgrade_models_api_keys", "vault_names")` | `jarvis/skills/registry.py` | Closed set of `requires_env_dynamic` sources |
| `CARD_MIN_DIGITS` / `CARD_MAX_DIGITS` | `13` / `19` | `jarvis/sensitive.py` | PAN length after separators removed |
| `ACCOUNT_MIN_DIGITS` / `ACCOUNT_MAX_DIGITS` | `6` / `17` | `jarvis/sensitive.py` | Solid digit-run length for an account number |
| `CONTEXT_WINDOW_CHARS` | `40` | `jarvis/sensitive.py` | Keyword↔token distance for routing and balance (account uses a connector-chain, not a window — review F3) |
| `IBAN_MIN_TOTAL` / `IBAN_MAX_TOTAL` | `15` / `34` | `jarvis/sensitive.py` | ISO 13616 length bounds |
| `BALANCE_MIN_AMOUNT` | `25.0` | `jarvis/sensitive.py` | Floor below which an amount beside a financial noun is a trivial IOU (R-5, re-measured after the F3 boundary fix). Catches a $50/$47.32 balance; rejects "owe you $20 for lunch". `0.0` restores the roadmap's literal rule |
| `FINANCIAL_REJECTION` | the K3 string | `jarvis/memory.py` | The memory gate's refusal reason |
| `SENSITIVE_SENTINEL` | `"<sensitive>"` | `jarvis/runlog/store.py` | Replaces a run-log payload value |
| `OUTBOUND` / `UNTRUSTED_INPUT` | K4's two sets (`OUTBOUND` gains `mcp-screen`, `mcp-calendar` — resolution §B) | `tests/unit/test_agent_isolation.py` | **Contract K4** — MAIL_CALENDAR_BRIEF adds to `UNTRUSTED_INPUT` |

### Not knobs (deliberately)

`PREVIEW_CHARS`, `MAX_BUFFERED_EVENTS`, `MAX_PAYLOAD_BYTES`, `ORPHAN_AFTER_S`,
`RUN_ORPHAN_AFTER_S` in `jarvis/runlog/store.py:38–63` are untouched by this
plan. `_truncate(SENSITIVE_SENTINEL)` is a no-op at any sane `PREVIEW_CHARS`,
so the two do not interact.

---

## §7 Tests — enumerated by file and function, with inputs and expected outputs

**Measurement note (re-measured 2026-08-27, after the review's F3/F22 fixes).**
The §5 Step 3 detector was re-extracted verbatim and executed against the §7.1
set (**29 positives + 65 negatives = 94**) **plus** this repo's 68-utterance
routing-eval fixture (`tests/evals/cases.yaml`, all must be negative) — **162
inputs, 0 false positives, 0 false negatives** at `BALANCE_MIN_AMOUNT = 25.0`.
Detection cost **5.0 ms on a 23,850-character input**. The command:

```
$ python3 harness.py     # extracted detector + the three corpora
POS 29 NEG 65 ROUTING 68 TOTAL 162
false negatives: []   wrong kind: []   false positives: []
```

Additionally scanned (0 false positives on each): the review's 18 breaking
inputs (all now in NEGATIVES), and **49 digit-bearing phrasings harvested from
`skills/*/SKILL.md`** ("19 commits ahead of main", "9 modified, 3 untracked",
"72°F", "401", etc.) — the detector fired on none, so the skill corpus adds no
false-positive pressure.

The 64 negatives now include the **18 shapes that broke the first draft** (review
F3): `owe`⊂`borrowed`/`however`/`allowed`/`followed`/`flowers`/`tower`/`vowel`/
`lowered`/`slowed`, `checking build 1049322`, `account, the order number is
8675309`, and the trivial IOUs `owe you $20 for lunch`. The floor was re-measured,
not asserted: with the word boundaries in place the corpus is clean at any floor
≥ 0; `25.0` is the value that additionally catches a $50/$47.32 balance (per
Larry's *"a $50 balance is financial"*) while rejecting sub-$25 IOUs (review
F22). Do not alter a pattern without re-running the harness and updating this
note in the same edit.

### 7.1 `tests/unit/test_sensitive.py`

```python
"""K3 detection cases (MORTIMER_SECURITY_HARDENING_PLAN.md §7.1).

Re-measured 2026-08-27 against jarvis/sensitive.py: 29 positives, 65 negatives,
0 failures, plus this repo's 68-utterance routing-eval fixture (all negative,
asserted in test_routing_eval_fixture_is_all_negative below). The negatives are
not filler — each is a shape a naive financial regex gets wrong, including the
18 that broke the first draft (owe-inside-borrowed, checking-the-build,
account-then-order-number) and this repo's own run ids, model names and tuning
constants.
"""

import pytest
import yaml

from jarvis.sensitive import (
    BALANCE_MIN_AMOUNT, FinancialMatch, detect_financial,
)
from jarvis.skills.registry import REPO_ROOT

POSITIVES = [
    # --- card (Luhn-valid test PANs) ---
    ("My Visa is 4111 1111 1111 1111", "card"),
    ("card number 4111111111111111", "card"),
    ("Amex 3782 822463 10005", "card"),
    ("put it on 5555555555554444", "card"),
    ("6011 1111 1111 1117 is the Discover", "card"),
    ("4012-8888-8888-1881", "card"),
    # --- routing (ABA-checksum-valid) ---
    ("the routing number is 021000021", "routing"),
    ("121000248 is my routing number", "routing"),
    ("ABA 011401533", "routing"),
    ("transit number 026009593", "routing"),
    # --- account (connector-chain) ---
    ("my account number is 000123456789", "account"),
    ("checking account 4829173", "account"),
    ("savings acct 88811223344", "account"),
    ("Account: 100200300400", "account"),
    # --- iban (mod-97-valid) ---
    ("IBAN GB82WEST12345698765432", "iban"),
    ("wire it to DE89370400440532013000", "iban"),
    ("FR1420041010050500013M02606", "iban"),
    # --- balance ---
    ("my balance is $2,431.09", "balance"),
    ("the checking balance dropped to $812.44", "balance"),
    ("I owe $1,250 on that one", "balance"),
    ("401k is at $118,000", "balance"),
    ("brokerage account holding $45,000", "balance"),
    ("savings has $3,000 in it", "balance"),
    ("my IRA is worth $220,400", "balance"),
    ("account balance $105.00", "balance"),
    # small real balances — review F22 (a $50 balance IS financial) ---
    ("my checking account balance is $47.32", "balance"),
    ("my savings balance is $50", "balance"),
    ("the account balance is $88.10", "balance"),
    # assistant-shaped reply — review F2 (the reply is now scanned) ---
    ("Your checking account balance is $2,431.18 as of today.", "balance"),
]

NEGATIVES = [
    # phone numbers — 4 shapes
    "call me at 555-123-4567",
    "(205) 555-0134",
    "1-800-555-0199",
    "my phone is 205 555 0134",
    # zip codes
    "my zip is 35242",
    "ship it to zip 35242-1234",
    # dates and timestamps
    "the meeting is on 2026-08-27",
    "2026-08-27T14:32:00Z",
    # order / confirmation numbers
    "order number 10023344",
    "confirmation 8837-2210",
    "the PR is #1423 and the issue is #98",
    # this repo's own run ids and commits
    "run id 462da350",
    "run 97d5cecc failed",
    "analyst runs 462da350, 97d5cecc, 9bd877dc all failed",
    "the commit is 9ed79982e1",
    # model and version strings
    "the model is gpt-5.1",
    "we're on version 2.1.4",
    "pipecat 1.4.0",
    "elevenlabs eleven_flash_v2_5",
    # small money without a financial noun, and with a verb-y one
    "grab lunch, $20 for lunch on Friday",
    "it cost $8.50",
    "my account was charged $8.50",       # $8.50 < floor; account not a number
    "he owes me $20 for lunch",           # "owes" != owe/owed (boundary)
    # financial nouns with no value
    "my account is locked again",
    "check the savings on that deal",
    "route 280 is backed up",
    "the routing eval scored 92%",
    # the case-sensitivity trap for IRA
    "Ira paid me $500 back",
    # bare numbers in ordinary speech
    "remind me in 15 minutes",
    "set a timer for 90 seconds",
    "temperature is 91 degrees",
    "I have 1234 unread emails",
    # this repo's own constants and identifiers
    "MAX_PAYLOAD_BYTES = 5000000",
    "set max_iterations to 25 and timeout_s to 300",
    # checksum traps: right shape, wrong check digit
    "1234 5678 9012 3456",
    "GB82WEST12345698765433",
    # review F3 — "owe" as a substring, near an amount >= floor (was 11 FPs)
    "the invoice showed $1,299 for the laptop",
    "I lowered the offer to $250",
    "he borrowed $400 from his brother",
    "however, $250 is too much for a mouse",
    "the crowd allowed $150 tickets",
    "sales slowed after the $300 hike",
    "the flowers cost $120",
    "she followed up on the $900 invoice",
    "the tower repair was $2,000",
    "vowel training software is $150",
    # review F3 — repo prose substrings near money
    "the lowest price was $500",
    "she narrowed it to $300 options",
    "powers of ten like $1000",
    "the shadowed panel cost $200 to fix",
    "I swallowed the $150 fee",
    "windowed mode dropped to $99",
    "accounting for $5000 in scope",
    "lowering the bar to $250",
    # review F3 — bare-verb "checking"/"savings" + a long id (was 8 FPs)
    "checking the run at 1756254000 now",
    "I'm checking build 1049322 for errors",
    "checking on that, the PR is 1234567",
    "checking flight 1234567 status",
    "my account, the order number is 8675309",
    "my Amazon account, order 112233445 shipped",
    "log in to my account, my member id is 998877",
    "savings of 1500000 tokens per run",
    # review F22 — trivial IOUs with the verb "owe" (floor rejects sub-$25)
    "I owe you $20 for lunch",
    "you owe me $15",
    "owe Dave $20 for lunch",
]


@pytest.mark.parametrize("text,kind", POSITIVES)
def test_positive(text, kind):
    match = detect_financial(text)
    assert match is not None, f"missed: {text!r}"
    assert match.kind == kind, f"{text!r} -> {match.kind}, want {kind}"


@pytest.mark.parametrize("text", NEGATIVES)
def test_negative(text):
    assert detect_financial(text) is None, f"false positive: {text!r}"


def test_counts_match_the_plan():
    """Guards against a case being quietly deleted to make the suite pass."""
    assert len(POSITIVES) == 29
    assert len(NEGATIVES) == 65


def test_routing_eval_fixture_is_all_negative():
    """C7 / review corpus: every routing-eval utterance is a non-financial
    turn and must never arm the detector (0 false alarms on the real fixture)."""
    cases = yaml.safe_load((REPO_ROOT / "tests" / "evals" / "cases.yaml").read_text())
    fired = [c["input"] for c in cases if detect_financial(c["input"]) is not None]
    assert not fired, f"detector fired on routing-eval utterances: {fired}"


def test_span_covers_only_the_token():
    """span is the sensitive token, never the keyword context (D-H3)."""
    text = "the routing number is 021000021"
    match = detect_financial(text)
    assert text[match.span[0]:match.span[1]] == "021000021"

    text = "my balance is $2,431.09"
    match = detect_financial(text)
    assert text[match.span[0]:match.span[1]] == "$2,431.09"


def test_order_is_most_specific_first():
    """A string with both a routing number and an account number reports
    the routing number (D-H3 fixed order)."""
    match = detect_financial("routing 021000021 and account 000123456789")
    assert match.kind == "routing"


def test_total_never_raises():
    for value in (None, "", "a" * 20000, "\x00\x01\x02", "​", 12345, []):
        assert detect_financial(value) is None


def test_kill_switch(monkeypatch):
    card = "My Visa is 4111 1111 1111 1111"
    assert detect_financial(card) is not None
    monkeypatch.setenv("JARVIS_SENSITIVE_GUARD_ENABLED", "false")
    assert detect_financial(card) is None
    monkeypatch.setenv("JARVIS_SENSITIVE_GUARD_ENABLED", "0")
    assert detect_financial(card) is None
    monkeypatch.setenv("JARVIS_SENSITIVE_GUARD_ENABLED", "true")
    assert detect_financial(card) is not None


def test_balance_floor_is_the_knob(monkeypatch):
    """R-5/F22: the floor is what separates a trivial IOU from a balance.
    "owe" matches the keyword (boundary-safe), so only the $20 < 25 floor
    keeps this negative; at floor 0 the roadmap's literal rule returns it."""
    assert detect_financial("I owe you $20 for lunch") is None
    monkeypatch.setattr("jarvis.sensitive.BALANCE_MIN_AMOUNT", 0.0)
    assert detect_financial("I owe you $20 for lunch") is not None


def test_word_boundary_keeps_owe_out_of_borrowed():
    """review F3: the boundary fix, not the floor, is what rejects these."""
    for text in ("he borrowed $400 from his brother",
                 "the invoice showed $1,299 for the laptop",
                 "I lowered the offer to $250"):
        assert detect_financial(text) is None, text


def test_account_connector_chain_rejects_competing_nouns():
    """review F3: a competing noun between 'account' and the digits breaks
    the chain, so an order/member number near 'account' is not an account."""
    assert detect_financial("my account, the order number is 8675309") is None
    assert detect_financial("checking build 1049322 for errors") is None
    assert detect_financial("my account number is 000123456789").kind == "account"


def test_returns_a_frozen_dataclass():
    match = detect_financial("card number 4111111111111111")
    assert isinstance(match, FinancialMatch)
    with pytest.raises(Exception):
        match.kind = "balance"
```

### 7.2 `tests/unit/test_env_scoping.py` (K2)

```python
"""K2 per-server env scoping (MORTIMER_SECURITY_HARDENING_PLAN.md §7.2)."""

import os
import re
from pathlib import Path

import pytest
import yaml

from jarvis.skills.registry import (
    BASE_ENV_KEYS, REPO_ROOT, build_child_env, load_requires_env,
)

SERVERS = sorted(p.parent.name for p in (REPO_ROOT / "mcp_servers").glob("*/skill.yaml"))


def _declared(pkg: str) -> set[str]:
    """requires_env + optional_env — both are grants the server may receive."""
    data = yaml.safe_load((REPO_ROOT / "mcp_servers" / pkg / "skill.yaml").read_text())
    return set(data.get("requires_env") or []) | set(data.get("optional_env") or [])


_ENV_CALL = re.compile(
    r"""os\.(?:environ\.get|getenv|environ)\(?\s*\[?\s*(?:["']([A-Z][A-Z0-9_]+)["']"""
    r"""|([A-Z][A-Z0-9_]+))"""            # a bare NAME (a module constant)
)
_CONST = re.compile(r"""^([A-Z][A-Z0-9_]*)\s*=\s*["']([A-Z][A-Z0-9_]+)["']""", re.M)
_JARVIS_IMPORT = re.compile(r"^\s*from\s+(jarvis\.[\w.]+)\s+import\b", re.M)


def _module_path(dotted: str) -> Path | None:
    p = REPO_ROOT / (dotted.replace(".", "/") + ".py")
    return p if p.exists() else None


def _reads_of(src: str) -> set[str]:
    """Env names read in one source string, resolving module-level
    NAME = "ENV_VAR" constants (review F8, the repo's dominant style)."""
    names: set[str] = set()
    consts = dict(_CONST.findall(src))              # NAME -> ENV_VAR
    for lit, const in _ENV_CALL.findall(src):
        if lit:
            names.add(lit)
        elif const in consts:
            names.add(consts[const])
    return names


def _read_local(pkg: str) -> set[str]:
    """Env names read in the server package's OWN .py files (precise)."""
    names: set[str] = set()
    for path in (REPO_ROOT / "mcp_servers" / pkg).rglob("*.py"):
        names |= _reads_of(path.read_text())
    return names


def _read_transitive(pkg: str) -> set[str]:
    """_read_local plus env names read in any jarvis.* module the package
    imports, one level deep (review F11). Deliberately OVER-approximates — an
    imported module read for other reasons still counts — so it is used only
    to CONFIRM a declaration is justified, never to demand a new one."""
    names = _read_local(pkg)
    for path in (REPO_ROOT / "mcp_servers" / pkg).rglob("*.py"):
        for dotted in _JARVIS_IMPORT.findall(path.read_text()):
            mod = _module_path(dotted)
            if mod is not None:
                names |= _reads_of(mod.read_text())
    return names


@pytest.mark.parametrize("pkg", SERVERS)
def test_no_server_reads_an_undeclared_var(pkg):
    """Every env name a server reads in its OWN package — as a literal or via a
    module constant (review F8, the repo's dominant style) — is declared
    (requires_env/optional_env) or in BASE_ENV_KEYS. This is the test that
    would have caught all six under-declared servers in R-1, mcp-screen's
    constant-style reads included. Transitive reads (through a jarvis.* import)
    are out of this test's scope (R-H1) — following imports here would
    over-approximate and demand spurious declarations; the one known transitive
    read, mcp-screen's JARVIS_UPGRADE_MODELS, is declared by hand (Step 1)."""
    undeclared = _read_local(pkg) - _declared(pkg) - set(BASE_ENV_KEYS)
    assert not undeclared, (
        f"{pkg} reads {sorted(undeclared)} but declares neither them nor "
        f"BASE_ENV_KEYS coverage — add them to requires_env/optional_env in "
        f"mcp_servers/{pkg}/skill.yaml"
    )


@pytest.mark.parametrize("pkg", SERVERS)
def test_every_declared_var_is_actually_read(pkg):
    """The inverse: a declaration nothing reads is a grant nobody needs. A read
    may be transitive (mcp-screen's JARVIS_UPGRADE_MODELS is read through
    jarvis.agents.upgrade_agent), so this confirms against the OVER-approximating
    transitive set."""
    read = _read_transitive(pkg)
    for name in _declared(pkg):
        assert name in read, f"{pkg} declares {name} but nothing (resolved) reads it"


def test_mcp_time_gets_no_github_token(monkeypatch):
    """The roadmap's own T4a acceptance, as a unit test."""
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_" + "x" * 36)
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-secret")
    monkeypatch.setenv("JARVIS_TIMEZONE", "America/Chicago")
    env = build_child_env({"name": "mcp-time", "env": {}})
    assert "GITHUB_TOKEN" not in env
    assert "TAVILY_API_KEY" not in env
    assert env["JARVIS_TIMEZONE"] == "America/Chicago"


def test_declared_var_reaches_its_own_server(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_" + "x" * 36)
    monkeypatch.setenv("GITHUB_OWNER", "larry")
    env = build_child_env({"name": "mcp-apps", "env": {}})
    assert env["GITHUB_TOKEN"].startswith("ghp_")
    assert env["GITHUB_OWNER"] == "larry"


def test_base_env_keys_are_copied_only_when_present(monkeypatch):
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    env = build_child_env({"name": "mcp-time", "env": {}})
    assert "VIRTUAL_ENV" not in env
    assert "PATH" in env


def test_missing_declared_var_warns_and_does_not_crash(monkeypatch, caplog):
    """K2: spawn proceeds, a WARNING names the server and the variable."""
    from jarvis.skills.registry import _WARNED_MISSING
    _WARNED_MISSING.discard(("mcp-repo", "JARVIS_REPO_ROOT"))
    monkeypatch.delenv("JARVIS_REPO_ROOT", raising=False)
    with caplog.at_level("WARNING"):
        env = build_child_env({"name": "mcp-repo", "env": {}})
    assert "JARVIS_REPO_ROOT" not in env
    assert "mcp_server_env_missing" in caplog.text
    assert "mcp-repo" in caplog.text
    assert "JARVIS_REPO_ROOT" in caplog.text


def test_missing_var_warns_once_per_process(monkeypatch, caplog):
    """Measured: without dedupe, mcp-screen printed 6 WARNINGs per spawn."""
    from jarvis.skills.registry import _WARNED_MISSING
    _WARNED_MISSING.discard(("mcp-repo", "JARVIS_REPO_ROOT"))
    monkeypatch.delenv("JARVIS_REPO_ROOT", raising=False)
    with caplog.at_level("WARNING"):
        build_child_env({"name": "mcp-repo", "env": {}})
        caplog.clear()
        build_child_env({"name": "mcp-repo", "env": {}})
    assert "mcp_server_env_missing" not in caplog.text


def test_dynamic_source_resolves_vision_keys(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-secret")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_" + "x" * 36)
    env = build_child_env({"name": "mcp-screen", "env": {}})
    assert env["OPENROUTER_API_KEY"] == "or-secret"
    assert "GITHUB_TOKEN" not in env


def test_absent_dynamic_keys_are_silent(monkeypatch, caplog):
    """A dynamic source means "whichever of these exists" — mcp-screen needs
    ONE vision key and the source yields four, so three absences are normal
    and must not warn (D-H1 step 3)."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-secret")
    for name in ("ANTHROPIC_API_KEY", "MOONSHOT_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    with caplog.at_level("WARNING"):
        build_child_env({"name": "mcp-screen", "env": {}})
    assert "ANTHROPIC_API_KEY" not in caplog.text
    assert "OPENAI_API_KEY" not in caplog.text


def test_unknown_dynamic_source_is_a_hard_error(tmp_path, monkeypatch):
    from jarvis.skills.registry import _resolve_dynamic_env
    with pytest.raises(ValueError, match="is not one of"):
        _resolve_dynamic_env("mcp-fake", [{"source": "everything"}])


def test_vault_names_source_is_reserved_for_t4b():
    from jarvis.skills.registry import _resolve_dynamic_env
    with pytest.raises(ValueError, match="not available before T4b"):
        _resolve_dynamic_env("mcp-fake", [{"source": "vault_names"}])


def test_explicit_env_map_still_wins(monkeypatch):
    """The `env:` map in config/mcp_servers.yaml is applied by
    _start_server AFTER build_child_env (registry.py:193-206, unchanged by
    this plan), so it still overrides. Asserted against _start_server's
    real composition, not against build_child_env alone."""
    monkeypatch.setenv("JARVIS_DB_PATH", "/base/jarvis.db")
    env = build_child_env({"name": "mcp-notes", "env": {}})
    assert env["JARVIS_DB_PATH"] == "/base/jarvis.db"
    # Replicate _start_server's next lines to prove ordering:
    from jarvis.config import expand_env_vars
    for key, value in {"JARVIS_DB_PATH": "/override/x.db"}.items():
        env[key] = expand_env_vars(str(value))
    assert env["JARVIS_DB_PATH"] == "/override/x.db"


def test_pythonpath_is_still_prefixed_when_absent(monkeypatch):
    """build_child_env may omit PYTHONPATH entirely; registry.py:207's
    env.get("PYTHONPATH", "") already handles that, and must keep doing so."""
    monkeypatch.delenv("PYTHONPATH", raising=False)
    env = build_child_env({"name": "mcp-time", "env": {}})
    assert "PYTHONPATH" not in env
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    assert env["PYTHONPATH"].startswith(str(REPO_ROOT))


def test_kill_switch_restores_full_inheritance(monkeypatch):
    monkeypatch.setenv("JARVIS_ENV_SCOPING_ENABLED", "false")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_" + "x" * 36)
    env = build_child_env({"name": "mcp-time", "env": {}})
    assert env["GITHUB_TOKEN"].startswith("ghp_")


def test_missing_skill_yaml_degrades_to_base_only(caplog):
    with caplog.at_level("WARNING"):
        required, dynamic = load_requires_env("mcp-does-not-exist")
    assert required == [] and dynamic == []
    assert "skill_yaml_missing" in caplog.text
```

**Integration check (`tests/integration/test_env_scoping_live.py`), the
roadmap's literal acceptance:** start a `SkillRegistry` with the real
`config/mcp_servers.yaml`, call `get_current_time`, assert it returns a time in
`JARVIS_TIMEZONE` — i.e. scoping did not break the server it scoped hardest.
Marked `@pytest.mark.skipif(not os.environ.get("RUN_LIVE"))` because it spawns
subprocesses.

### 7.3 `tests/unit/test_sensitive_turn.py` (K3, the flag and the 11 sites)

```python
"""K3 flag lifecycle and the fifteen suppression sites (plan §7.3, D-H6)."""

import json

import pytest

from jarvis.bot.sensitive_turn import (
    SensitiveTurn, arm_from_text, current_sensitive_turn, current_turn_id,
    is_sensitive, redacted,
)
from jarvis.skills.registry import REPO_ROOT


@pytest.fixture
def holder():
    obj = SensitiveTurn()
    token = current_sensitive_turn.set(obj)
    yield obj
    current_sensitive_turn.reset(token)


# --- lifecycle -----------------------------------------------------------

def test_unset_contextvar_is_fail_closed():
    """FAIL-CLOSED (D-H4, review F1/F6): a missing holder means "suppress".
    In production the ContextVar is always set (run_session / cli.main wire it
    before any turn), so this branch is a loud wiring-regression signal, not a
    normal state. current_turn_id stays '-' (no armed turn to correlate)."""
    assert is_sensitive() is True
    assert current_turn_id() == "-"


def test_arm_and_clear(holder):
    assert is_sensitive() is False
    assert arm_from_text("my account number is 000123456789") is True
    assert is_sensitive() is True
    assert holder.kind == "account"
    assert holder.turn_id is not None
    holder.clear()
    assert is_sensitive() is False
    assert holder.turn_id is None


def test_arm_is_idempotent_within_a_turn(holder):
    arm_from_text("card number 4111111111111111")
    first = holder.turn_id
    arm_from_text("and my routing is 021000021")
    assert holder.turn_id == first


def test_clear_is_safe_when_never_armed(holder):
    holder.clear()
    assert is_sensitive() is False


def test_ordinary_turn_never_arms(holder):
    assert arm_from_text("what's the weather in Birmingham") is False
    assert is_sensitive() is False


def test_kill_switch_prevents_arming(holder, monkeypatch):
    monkeypatch.setenv("JARVIS_SENSITIVE_GUARD_ENABLED", "false")
    assert arm_from_text("card number 4111111111111111") is False
    assert is_sensitive() is False


def test_redacted_line_carries_no_content(holder):
    arm_from_text("card number 4111111111111111")
    line = redacted("card number 4111111111111111")   # no `role` arg (F20)
    assert "4111" not in line
    assert "card" not in line          # the KIND is a hint too
    assert holder.turn_id in line
    assert "28 chars withheld" in line  # len("card number 4111111111111111") == 28


def test_the_flag_reaches_a_child_task(holder):
    """The ContextVar holds a REFERENCE, so a task started before arming
    still sees the armed state (D-H4)."""
    import asyncio

    async def child():
        return is_sensitive()

    async def main():
        arm_from_text("card number 4111111111111111")
        return await asyncio.create_task(child())

    assert asyncio.run(main()) is True


# --- P1/P2/P3: the conversations table -----------------------------------

def test_p1_p2_no_conversations_row_when_armed(holder, tmp_path, monkeypatch):
    from jarvis.bot import transcript_log
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "t.db"))
    from jarvis.db import get_conn, run_migrations
    run_migrations()

    transcript_log._persist("s1", "user", "ordinary line")
    arm_from_text("card number 4111111111111111")
    transcript_log._persist("s1", "user", "card number 4111111111111111")
    holder.clear()

    with get_conn() as conn:
        rows = conn.execute("SELECT content FROM conversations").fetchall()
    assert [r[0] for r in rows] == ["ordinary line"]


def test_p4_p5_supervisor_does_not_persist_when_armed(holder, tmp_path, monkeypatch):
    """Same assertion for the CLI/text path (jarvis/agents/supervisor.py)."""
    # Constructed with a stub client; only _persist behaviour is exercised.
    ...


# --- F1: the real frame sequence suppresses the assistant row ------------

def test_real_frame_sequence_suppresses_assistant_row(holder, tmp_path, monkeypatch):
    """review F1 — drive the ACTUAL order the observer/processor see:
    UserStartedSpeakingFrame -> TranscriptionFrame(s) -> UserStoppedSpeakingFrame
    -> LLMTextFrame(s) -> LLMFullResponseEndFrame. The user turn carries no
    value; the ASSISTANT reply does (review F2). Both rows must be suppressed,
    and the flag must NOT have been cleared before the reply was scanned."""
    import asyncio
    from pipecat.frames.frames import (
        UserStartedSpeakingFrame, UserStoppedSpeakingFrame,
        TranscriptionFrame, LLMTextFrame, LLMFullResponseEndFrame,
    )
    from pipecat.processors.frame_processor import FrameDirection
    from pipecat.observers.base_observer import FramePushed
    from jarvis.bot.transcript_log import TranscriptObserver, TranscriptLogger
    from jarvis.db import get_conn, run_migrations
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "t.db"))
    run_migrations()

    obs = TranscriptObserver("s1")
    log = TranscriptLogger(session_id="s1")

    async def push_obs(frame):
        await obs.on_push_frame(FramePushed(
            source=None, frame=frame, direction=FrameDirection.DOWNSTREAM,
            timestamp=0))
    async def push_log(frame):
        await log.process_frame(frame, FrameDirection.DOWNSTREAM)

    async def drive():
        await push_obs(UserStartedSpeakingFrame())
        # user asks a question with NO value in it
        await push_obs(TranscriptionFrame("what is my checking balance", "u", ""))
        await push_obs(UserStoppedSpeakingFrame())
        # assistant answers WITH the value
        await push_log(LLMTextFrame("Your checking account balance is $2,431.18."))
        await push_log(LLMFullResponseEndFrame())

    asyncio.run(drive())
    with get_conn() as conn:
        rows = conn.execute("SELECT role, content FROM conversations").fetchall()
    # the assistant row must be absent (reply scanned, flag still armed);
    # the user row is an ordinary question and MAY be present — assert the
    # figure never landed anywhere.
    assert all("2,431.18" not in c for _, c in rows)
    assert not any(role == "assistant" and "2,431" in c for role, c in rows)


# --- P8/P9/P10/P12/P13: the run log --------------------------------------

def test_run_log_redacts_on_the_snapshot(tmp_path, monkeypatch):
    """review F5/F6/F23 — the SNAPSHOT path: sensitive=True at construction
    redacts task (P12), tool_call args (P8), tool_result (P9), finish (P10)
    even for payloads that contain no financial detail of their own."""
    from jarvis.runlog.store import SENSITIVE_SENTINEL, RunLogger
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "t.db"))
    from jarvis.db import run_migrations
    run_migrations()

    # correct signature: display_name is a required positional; root redirects
    # the JSONL under tmp_path; sensitive= is the snapshot (review F23).
    log = RunLogger("t0000001", "analyst", "Analyst",
                    "look up my balance", root=tmp_path, model="m",
                    sensitive=True)
    log.start()
    log.tool_call("web_search", {"query": "weather"})     # no value in args
    log.tool_result("web_search", "sunny and mild", 12, True)
    log.finish("done")

    payload = [json.loads(line)
               for line in (tmp_path / log.payload_path).read_text().splitlines()]
    start = next(r for r in payload if r["type"] == "run_start")
    call = next(r for r in payload if r["type"] == "tool_call")
    result = next(r for r in payload if r["type"] == "tool_result")
    end = next(r for r in payload if r["type"] == "run_end")
    assert start["task"] == SENSITIVE_SENTINEL          # P12
    assert call["tool"] == "web_search"                 # name survives
    assert call["arguments"] == SENSITIVE_SENTINEL      # P8
    assert result["tool"] == "web_search" and result["ok"] is True
    assert result["latency_ms"] == 12                   # metrics survive
    assert result["result"] == SENSITIVE_SENTINEL       # P9
    assert end["reply"] == SENSITIVE_SENTINEL           # P10
    assert end["tool_count"] == 1


def test_run_log_redacts_a_reply_derived_value_via_content_scan(tmp_path, monkeypatch):
    """review F2/F6 — sensitive=False snapshot, but a tool RESULT contains a
    value the user turn did not telegraph: the content scan catches it."""
    from jarvis.runlog.store import SENSITIVE_SENTINEL, RunLogger
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "t.db"))
    from jarvis.db import run_migrations
    run_migrations()
    log = RunLogger("t0000002", "analyst", "Analyst", "look it up",
                    root=tmp_path, model="m", sensitive=False)
    log.start()
    log.tool_result("lookup", "your balance is $2,431.09", 5, True)
    log.finish("ok")
    payload = [json.loads(line)
               for line in (tmp_path / log.payload_path).read_text().splitlines()]
    result = next(r for r in payload if r["type"] == "tool_result")
    assert result["result"] == SENSITIVE_SENTINEL
    raw = (tmp_path / log.payload_path).read_text()
    assert "2,431" not in raw


def test_run_log_is_untouched_on_an_ordinary_turn(tmp_path, monkeypatch):
    """The regression that matters most: sensitive=False and no financial
    content — every payload round-trips verbatim."""
    from jarvis.runlog.store import RunLogger
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "t.db"))
    from jarvis.db import run_migrations
    run_migrations()
    log = RunLogger("t0000003", "analyst", "Analyst", "what's the weather",
                    root=tmp_path, model="m", sensitive=False)
    log.start()
    log.tool_call("web_search", {"query": "weather in Rome"})
    log.tool_result("web_search", "sunny, 24C", 7, True)
    log.finish("It's sunny in Rome.")
    raw = (tmp_path / log.payload_path).read_text()
    assert "weather in Rome" in raw and "sunny, 24C" in raw and "It's sunny" in raw


def test_runlog_never_imports_jarvis_bot_at_module_scope():
    """D-H7: store.py takes the snapshot as a ctor arg; it must not import
    jarvis.bot at all (jarvis.sensitive is fine — stdlib-only)."""
    source = (REPO_ROOT / "jarvis" / "runlog" / "store.py").read_text()
    assert "jarvis.bot" not in source


# --- P11: the memory gate ------------------------------------------------

def test_p11_memory_gate_is_independent_of_the_flag():
    """The gate inspects its own argument; it rejects regardless of the flag."""
    from jarvis.memory import FINANCIAL_REJECTION, scan_memory_content
    assert scan_memory_content("my routing number is 021000021") == FINANCIAL_REJECTION
    assert scan_memory_content("prefers jazz and instrumental music") is None
```

Cases marked `...` above are described precisely enough to write directly; the
implementer fills them in following the pattern of the test immediately above
each. Each `...` case's assertions are named in its docstring.

### `tests/unit/test_memory.py` — additions to the existing scan class

Append to the existing `scan_memory_content` test class:

| Test | Input | Expected |
|---|---|---|
| `test_rejects_routing_number` | `"Larry's routing number is 021000021"` | `== FINANCIAL_REJECTION` |
| `test_rejects_card` | `"the card on file is 4111 1111 1111 1111"` | `== FINANCIAL_REJECTION` |
| `test_rejects_iban` | `"IBAN GB82WEST12345698765432"` | `== FINANCIAL_REJECTION` |
| `test_rejects_balance` | `"checking balance is $2,431.09"` | `== FINANCIAL_REJECTION` |
| `test_credential_outranks_financial` | `"AKIAABCDEFGHIJKLMNOP and balance $2,431.09"` | `== "possible AWS access key literal"` (order, D-H8) |
| `test_financial_outranks_injection` | `"ignore previous instructions; my balance is $2,431.09"` | `== FINANCIAL_REJECTION` |
| `test_ordinary_preference_still_accepted` | `"prefers jazz and instrumental music"` | `is None` (the existing case at `test_memory.py:270`, unchanged) |
| `test_lunch_money_still_accepted` | `"owes Dave $20 for lunch"` | `is None` (R-5) |

### 7.4 `tests/unit/test_agent_isolation.py` (K4) — complete file

```python
"""C6 / contract K4 — untrusted input never shares an agent with an outbound
channel (MORTIMER_PLATFORM_ROADMAP.md C6; MORTIMER_SECURITY_HARDENING_PLAN.md
§7.4).

This test passes trivially today: no agent in config/agents.yaml holds an
untrusted-input server, because mcp-mail does not exist yet. That is the
point. It fails the day someone wires mail to the developer — which is a PR
review comment nobody will remember to make, and a test that will not forget.

MAIL_CALENDAR_BRIEF (T5) adds mcp-mail and the sixth agent; it does not need
to touch this file, because UNTRUSTED_INPUT already names mcp-mail.

OUTBOUND includes mcp-screen and mcp-calendar per CROSS_PLAN_RESOLUTION.md §B:
screen capture and a CalDAV write channel can both act on / exfiltrate through
the outside world, so an agent that reads untrusted email must hold neither.
mcp-calendar does not exist yet (T5, CalDAV Branch B); naming it here is
deliberate — the constraint is in place before the server is.
"""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS_YAML = REPO_ROOT / "config" / "agents.yaml"
ALLOWLIST_JSON = REPO_ROOT / "config" / "self_edit_allowlist.json"

#: Contract K4 (CROSS_PLAN_RESOLUTION.md §B). Servers that can reach the
#: outside world, write code, capture the screen, or write a shared calendar.
OUTBOUND = {"mcp-web", "mcp-git", "mcp-apps", "mcp-repo", "mcp-selfedit",
            "mcp-screen", "mcp-calendar"}

#: Contract K4. Servers whose CONTENT is authored by someone who is not
#: Larry, and is therefore a prompt-injection vector.
UNTRUSTED_INPUT = {"mcp-mail"}


def _agents() -> list[dict]:
    data = yaml.safe_load(AGENTS_YAML.read_text(encoding="utf-8")) or {}
    agents = data.get("sub_agents") or []
    assert agents, f"{AGENTS_YAML} declares no sub_agents"
    return agents


def test_no_agent_mixes_untrusted_input_with_an_outbound_channel():
    violations = []
    for agent in _agents():
        servers = set(agent.get("mcp_servers") or [])
        untrusted = servers & UNTRUSTED_INPUT
        outbound = servers & OUTBOUND
        if untrusted and outbound:
            violations.append(
                f"{agent.get('name')!r} holds untrusted input "
                f"{sorted(untrusted)} AND outbound {sorted(outbound)}"
            )
    assert not violations, (
        "roadmap C6 violated in config/agents.yaml — an agent that reads "
        "content Larry did not write must not also hold a channel that can "
        "act on the outside world:\n  " + "\n  ".join(violations)
    )


def test_the_sets_have_not_been_quietly_emptied():
    """A passing test with an empty set proves nothing. K4 fixes both sets;
    growing UNTRUSTED_INPUT is expected, shrinking either is not."""
    assert OUTBOUND == {"mcp-web", "mcp-git", "mcp-apps", "mcp-repo",
                        "mcp-selfedit", "mcp-screen", "mcp-calendar"}
    assert "mcp-mail" in UNTRUSTED_INPUT


def test_every_named_server_is_real_or_planned():
    """Catches a typo that would make the intersection silently empty.
    mcp-mail (T5) and mcp-calendar (T5 CalDAV) are named before they exist."""
    declared = {p.parent.name.replace("_", "-")
                for p in (REPO_ROOT / "mcp_servers").glob("*/skill.yaml")}
    unknown = (OUTBOUND | UNTRUSTED_INPUT) - declared - {"mcp-mail", "mcp-calendar"}
    assert not unknown, f"K4 names servers that do not exist: {sorted(unknown)}"


def test_report_self_edit_exposure(capsys):
    """INFORMATIONAL, asserts nothing (plan D-H9 / §5 Step 9).

    Reports which mechanisms of this plan the self-edit loop can still
    rewrite. Larry's §8 V7 commit empties this list. It does not assert,
    because the plan must be mergeable before that commit — asserting here
    would make the suite red for a change the implementing model is
    forbidden (C8) to make.
    """
    import json

    from jarvis.selfedit.allowlist import Allowlist

    allowlist = Allowlist.load(ALLOWLIST_JSON)
    # D-H9 / resolution §A — the three paths W0 denies. config/agents.yaml and
    # mcp_servers/*/skill.yaml are DELIBERATELY not here: they stay editable,
    # guarded by tests/unit/test_requires_env_snapshot.py instead.
    guarded = [
        "jarvis/skills/registry.py",
        "tests/unit/test_agent_isolation.py",
        "tests/unit/test_requires_env_snapshot.py",
    ]
    exposed = [p for p in guarded if allowlist.is_allowed(p)]
    print("\nT4a self-edit exposure (D-H9): "
          + (", ".join(exposed) if exposed else "none — V7 commit is in"))
```

*`Allowlist` signatures, verified:* `Allowlist.load(path) -> Allowlist`
(`jarvis/selfedit/allowlist.py:60–63`, a `@classmethod`) and
`is_allowed(self, path: str) -> bool` (`:74–79`, deny-first-then-allow, and it
raises `ValueError` on a traversal path — every path above is repo-relative, so
that branch is unreachable here). No `RunLogger`-style keyword arguments.

*`RunLogger.__init__` signature (review F23)* — after Step 7a it is
`RunLogger(run_id, agent, display_name, task, *, session_id=None,
enabled=True, db_path=None, root=None, model=None, sensitive=False)`. Note
**`display_name` is a required positional**, `root` (not `db_path`) redirects
the JSONL under `tmp_path`, and `sensitive=` is the new snapshot. The §7.3 tests
use it exactly: `RunLogger("t0000001", "analyst", "Analyst", "task",
root=tmp_path, model="m", sensitive=True)`.

### 7.5 Full-suite gate

```
pytest tests/unit tests/integration -q
```
must be green before Larry is asked to review. No test is deleted or skipped
by this plan.

### 7.6 `tests/unit/test_requires_env_snapshot.py` (D-H9, resolution §A) — complete file

The frozen privilege snapshot that replaces D-H9's dropped `skill.yaml` deny.
It freezes each server's `requires_env`/`optional_env` (from `skill.yaml`) AND
its `config/mcp_servers.yaml` `env:` map, and fails if any diverges — so a
self-edit that widens a grant, or re-grants a secret through an `env:` map
(review F12), turns CI red until Larry edits this **denied** file by hand.

```python
"""Frozen privilege snapshot (MORTIMER_SECURITY_HARDENING_PLAN.md D-H9,
CROSS_PLAN_RESOLUTION.md §A). This file is DENIED in
config/self_edit_allowlist.json (ALLOWLIST_SEQUENCE.md row W0), so the self-edit
loop cannot change what it asserts. Any legitimate change to a server's
privilege surface is a human commit that edits BOTH the manifest AND this
snapshot — which is exactly the review gate the resolution chose over an
outright deny of config/agents.yaml and mcp_servers/*/skill.yaml.
"""

import yaml

from jarvis.skills.registry import REPO_ROOT

# EXPECTED[server] = (requires_env, optional_env, env_map). Order-independent
# for the lists (sorted before compare); the env_map is compared exactly,
# key AND value — an `env:` value can rename or supply a literal.
EXPECTED = {
    "mcp-time":      ([], [], {}),
    "mcp-notes":     ([], [], {"JARVIS_DB_PATH": "${JARVIS_DB_PATH}"}),
    "mcp-memory":    ([], [], {"JARVIS_DB_PATH": "${JARVIS_DB_PATH}"}),
    "mcp-reminders": ([], [], {"JARVIS_DB_PATH": "${JARVIS_DB_PATH}",
                               "JARVIS_TIMEZONE": "${JARVIS_TIMEZONE}"}),
    "mcp-system":    ([], [], {}),
    "mcp-runlog":    ([], [], {}),
    "mcp-web":       (["TAVILY_API_KEY", "JARVIS_UNITS"], [],
                      {"TAVILY_API_KEY": "${TAVILY_API_KEY}"}),
    "mcp-git":       (["JARVIS_REPO_ROOT"], [], {"JARVIS_DB_PATH": "${JARVIS_DB_PATH}"}),
    "mcp-repo":      (["JARVIS_REPO_ROOT"], [], {}),
    "mcp-apps":      (["GITHUB_TOKEN", "GITHUB_OWNER"],
                      ["JARVIS_REGISTRY_REPO", "JARVIS_REGISTRY_BRANCH"],
                      {"GITHUB_TOKEN": "${GITHUB_TOKEN}",
                       "GITHUB_OWNER": "${GITHUB_OWNER}"}),
    "mcp-selfedit":  ([], ["JARVIS_UPGRADE_PROFILE"], {}),
    "mcp-screen":    (["JARVIS_SCREEN_ENABLED", "JARVIS_VISION_PROFILE"],
                      ["JARVIS_SCREEN_RETENTION_HOURS", "JARVIS_UPGRADE_MODELS"],
                      {}),
}


def _skill(server: str) -> dict:
    pkg = server.replace("-", "_")
    return yaml.safe_load(
        (REPO_ROOT / "mcp_servers" / pkg / "skill.yaml").read_text()) or {}


def _env_maps() -> dict:
    data = yaml.safe_load((REPO_ROOT / "config" / "mcp_servers.yaml").read_text())
    servers = data if isinstance(data, list) else (
        data.get("servers") or data.get("mcp_servers") or [])
    return {s["name"]: (s.get("env") or {}) for s in servers}


def test_privilege_surface_is_frozen():
    env_maps = _env_maps()
    drift = []
    for server, (req, opt, env) in EXPECTED.items():
        y = _skill(server)
        got_req = sorted(str(n) for n in (y.get("requires_env") or []))
        got_opt = sorted(str(n) for n in (y.get("optional_env") or []))
        got_env = env_maps.get(server, {})
        if got_req != sorted(req):
            drift.append(f"{server}.requires_env: {got_req} != {sorted(req)}")
        if got_opt != sorted(opt):
            drift.append(f"{server}.optional_env: {got_opt} != {sorted(opt)}")
        if got_env != env:
            drift.append(f"{server} env: map: {got_env} != {env}")
    assert not drift, (
        "A server's privilege surface changed. If this is an intended, "
        "human-reviewed grant, edit EXPECTED here (a DENIED file — a self-edit "
        "cannot) in the SAME commit:\n  " + "\n  ".join(drift))


def test_no_server_gained_an_unfrozen_env_map_key():
    """Defence for review F12: a re-grant via a NEW server's env: map, or a new
    key on an existing one, is caught even if EXPECTED was not updated."""
    for server, got in _env_maps().items():
        assert server in EXPECTED, f"unfrozen server {server} in config/mcp_servers.yaml"
        for key in got:
            assert key in EXPECTED[server][2], (
                f"{server} env: map gained key {key!r} — a secret re-grant "
                f"(review F12). Freeze it in EXPECTED (a human commit).")
```

*Frozen values verified against the repo snapshot (2026-08-27):* the `env:` maps
above are `config/mcp_servers.yaml`'s current maps verbatim; the
`requires_env`/`optional_env` are Step 1's target state. This test is RED until
Step 1 lands (the repo's `skill.yaml` files still say `[]`), which is correct —
it is the gate that proves Step 1 was applied exactly.

## §8 Verification Larry runs on his hardware

The sandbox has no Keychain, no network, no Xcode and no microphone, so the
implementing model cannot run V2–V6. Larry runs these on the Mac, in order.

**V1 — the suite (the model runs this too; Larry confirms).**
```bash
pytest tests/unit tests/integration -q
```
Expect green. Then specifically:
```bash
pytest tests/unit/test_sensitive.py -q  # 94 enumerated cases + property tests + routing fixture
pytest tests/unit/test_env_scoping.py -q
pytest tests/unit/test_requires_env_snapshot.py -q
pytest tests/unit/test_agent_isolation.py -q -s   # -s to see the D-H9 exposure line
```

**V2 — the scoping actually reaches the children (the roadmap's own T4a
acceptance).** With the vault unlocked so `inject_env()` has run:
```bash
./scripts/mortimer.sh
# in another shell, while the bot is up:
for pid in $(pgrep -f "mcp_servers.mcp_time.server"); do
  ps eww $pid | tr ' ' '\n' | grep -E '^(GITHUB_TOKEN|TAVILY_API_KEY|ELEVENLABS_API_KEY|OPENAI_API_KEY|DEEPGRAM_API_KEY)=' 
done
```
**Expect no output.** Then confirm the server still works — ask Mortimer
"what time is it?" and get a correct local time. Repeat for `mcp_apps`:
```bash
for pid in $(pgrep -f "mcp_servers.mcp_apps.server"); do
  ps eww $pid | tr ' ' '\n' | grep -E '^(GITHUB_TOKEN|GITHUB_OWNER)=' | sed 's/=.*/=<set>/'
done
```
**Expect exactly `GITHUB_TOKEN=<set>` and `GITHUB_OWNER=<set>`.**

*(`ps eww` shows a process's environment on macOS only for processes the
invoking user owns, which is the case here. If it prints nothing at all for a
running pid, the check is inconclusive, not passing — use
`sudo ps eww $pid` or read `/proc`-equivalent via `lsof` and say so.)*

**V3 — no server broke.** Exercise one tool per privileged server through
voice or `python3 -m jarvis.cli`:

| Say | Expect | Proves |
|---|---|---|
| "what time is it" | correct local time | `JARVIS_TIMEZONE` via `BASE_ENV_KEYS` |
| "what's the weather" | a forecast in **°F** | `TAVILY_API_KEY` + `JARVIS_UNITS` via `requires_env` (R-2) |
| "what's the git status" | a real branch summary | `JARVIS_REPO_ROOT` via `requires_env` |
| "read jarvis/config.py and tell me what bridge_settings_to_env does" | a real answer, not "does not exist" | `mcp-repo`'s `JARVIS_REPO_ROOT` — the exact failure mode `config/mcp_servers.yaml`'s comment records |
| "what's on my screen" | a description | `mcp-screen`'s four vars **and** the dynamic API key |
| "remind me to call Dave at 4" | a reminder set | `JARVIS_DB_PATH` + `JARVIS_TIMEZONE` |

Any "not configured" / "does not exist" answer here means a `requires_env`
declaration is still short. Fix the `skill.yaml`, do not disable scoping.

**V4 — the sensitive turn, end to end, with real speech.** With
`tail -f logs/bot.log` in another window, say out loud:

> "My checking account number is zero zero zero one two three four five six
> seven eight nine."

**Step 0 (review F18) — confirm Flux numeralised the digits.** The detector is
regex-only; if Deepgram Flux emitted the *words* ("zero zero zero…") rather than
`000123456789`, the turn will not arm and V4 is **inconclusive, not failed**
(R-H4 confirmed live), because this pipeline cannot force numerals —
`DeepgramFluxSTTSettings` exposes no `numerals`/`smart_format` knob (only
`eager_eot_threshold`, `eot_threshold`, `eot_timeout_ms`, `keyterm`,
`min_confidence`, `language_hints`). So first check what was transcribed **before
suppression** — but the USER line is already redacted, so instead type the same
utterance in `python3 -m jarvis.cli` (which shows the pre-suppression path is
also armed) OR say a phrasing you know Flux numeralises. If a subsequent check
shows the flag never armed, record V4 **inconclusive** and rely on the unit
tests + V5.

Then:
```bash
sqlite3 data/jarvis.db \
  "SELECT COUNT(*) FROM conversations WHERE content LIKE '%123456789%';"
grep -c "123456789" logs/bot.log
grep -rc "123456789" logs/agents/ 2>/dev/null | grep -v ':0$'
```
**Expect `0`, `0`, and no output.** In `logs/bot.log` expect instead a line of
the shape:
```
[14:32:07] USER: <sensitive turn a1b2c3d4: 61 chars withheld>
```
Then say "what's the weather" and confirm the **next** turn is logged
normally — the flag cleared at the next `UserStartedSpeakingFrame`.

*Note on what V4 does NOT prove:* Deepgram still received the audio and
transcribed it, and ElevenLabs still spoke the reply. §2.7 / R-H5. T4a stops
Mortimer from *keeping* the number; it does not stop the vendors from having
heard it. That is T3/T4b.

**V5 — the memory gate.** In `python3 -m jarvis.cli`:
> "Remember that my routing number is 021000021."

Expect Mortimer to reply with its ordinary confirmation
("Got it — I'll remember …"), and then:
```bash
sqlite3 data/jarvis.db "SELECT COUNT(*) FROM memories WHERE content LIKE '%021000021%';"
grep "memory_content_rejected\|financial detail" logs/*.log | tail -3
```
**Expect `0` and a log line naming the financial rejection.** The cheerful
confirmation with no stored fact is deliberate and is D-H8's decision (a model
told why its write was refused rewrites the content to evade the filter); if
Larry wants an honest "I'm not storing that yet", that is a T4b change with a
place to route to, and it goes in that plan.

Also confirm ordinary memory still works: "Remember that I prefer metric
units," then `sqlite3 data/jarvis.db "SELECT key, content FROM memories ORDER BY updated_at DESC LIMIT 1;"`

**V6 — the routing eval (C7).** This plan does not touch the Supervisor
prompt or model, but it changes what every MCP child can see, and a child that
lost a variable shows up here as a tool failure:
```bash
RUN_LIVE=1 python -m tests.evals.routing_eval
```
**Record the score in this section before merge. Must be ≥ 90 %.**
Score: `________` (Larry fills in).

**V7 — Larry's own commit: apply ALLOWLIST_SEQUENCE.md row W0 (C8, D-H9,
resolution §A).** The implementing model is forbidden from editing
`config/self_edit_allowlist.json` (§0.2). Larry applies **row W0 of
`docs/plans/ALLOWLIST_SEQUENCE.md`** — the single owner of the reconciled
allow-list — which adds exactly three entries to the `deny` array:
```json
    "jarvis/skills/registry.py",
    "tests/unit/test_agent_isolation.py",
    "tests/unit/test_requires_env_snapshot.py",
```
then runs that row's verify command (from ALLOWLIST_SEQUENCE.md):
```bash
pytest tests/unit/test_agent_isolation.py -q -s   # exposure line
pytest tests/unit/test_requires_env_snapshot.py -q
```
Expect the exposure line to read `none — V7 commit is in`.

*What this does and does NOT cost (resolution §A).* `config/agents.yaml` and
`mcp_servers/*/skill.yaml` **stay editable** — the self-edit loop can still
*propose* a tool grant or a new server's `skill.yaml`, which keeps the voice
self-repair path and T6 skill authoring alive. The enforcement is the frozen
snapshot (§7.6): a proposed change to a server's `requires_env` or a
`config/mcp_servers.yaml` `env:` map turns CI red until Larry edits the denied
`test_requires_env_snapshot.py` by hand, in the same commit that merges the
grant. That is the review gate Larry chose over an outright deny (which the
first draft of D-H9 would have imposed, reversing his 2026-08-21 decision).

**V8 — optional, one-time, destructive: purge history.** No code does this
(§2.5). Only if Larry wants the pre-T4a plaintext gone:
```bash
./scripts/mortimer.sh stop
cp data/jarvis.db data/jarvis.db.bak-$(date +%Y%m%d)
sqlite3 data/jarvis.db "DELETE FROM conversations WHERE created_at < date('now');"
rm -rf logs/agents/2026-0[1-8]*
: > logs/bot.log
```
Review the backup before deleting it.

**Branch:** `security-hardening-t4a`. Larry commits; the implementing model
never runs git (§0.1).

---

## §9 Rollback

Three independent mechanisms, three independent rollbacks. Nothing here writes
data, so **no data migration has to be reverted** — that is the main advantage
of T4a being a "stores nothing" track.

### Instant, no deploy — the kill switches

| Symptom | Set | Effect |
|---|---|---|
| An MCP server stopped working after this change ("not configured", "does not exist", a missing key) | `JARVIS_ENV_SCOPING_ENABLED=false` in `.env`, restart | Children inherit the full environment again — byte-identical to pre-plan behaviour. A `mcp_env_scoping_disabled` WARNING per spawn keeps it visible. **⚠ After REMOTE (T2) lands (`CROSS_PLAN_RESOLUTION.md` §C-F6): this switch also hands `JARVIS_SERVICE_TOKEN` to all twelve MCP children via `dict(os.environ)`. Before setting it, revoke the service token or set `JARVIS_AUTH_ENABLED=false` too; re-mint after re-enabling scoping.** |
| Detection is firing on ordinary speech, or transcripts stopped appearing | `JARVIS_SENSITIVE_GUARD_ENABLED=false` in `.env`, restart | `detect_financial` returns `None` unconditionally (the holder stays `armed=False`); all fifteen sites behave as before, including the gates. (This is the intended way to disable the guard — not unsetting the ContextVar, which fail-closes.) |
| Detection is *mostly* right but too eager on money | Do **not** disable the guard. Set `BALANCE_MIN_AMOUNT` higher in `jarvis/sensitive.py` (§6), or `0.0` for the roadmap's literal rule | Narrow fix, keeps card/routing/account/IBAN protection |

Neither switch requires a code change, and neither leaves anything behind.

### Partial revert — one mechanism at a time

The three mechanisms share no file, which is why they were sequenced this way:

- **K2 only:** revert `jarvis/skills/registry.py` and `config/mcp_servers.yaml`.
  Leave the corrected `skill.yaml` files — they are accurate documentation
  regardless of whether anything enforces them, and Step 1 was designed to be
  independently keepable.
- **K3 only:** revert `jarvis/sensitive.py`, `jarvis/bot/sensitive_turn.py`,
  and the edits to `jarvis/bot/transcript_log.py`,
  `jarvis/agents/supervisor.py`, `jarvis/runlog/store.py`,
  `jarvis/bot/pipeline.py`, `jarvis/memory.py`.
- **K4 only:** delete `tests/unit/test_agent_isolation.py`. It touches no
  production code. (Do not do this to make a red suite green — a red K4 means
  C6 is being violated, which is the whole point.)

### Data

**Nothing to revert.** No table, no column, no migration, no key, no file
format change. The one shape change is that run-log records for a sensitive
turn contain the literal string `"<sensitive>"` where a payload used to be;
every reader already handles arbitrary strings there (the `_DROPPED` sentinel
at `jarvis/runlog/store.py:66` has set that precedent since the run log
shipped), and rolling back simply stops producing them. Records already written
with `"<sensitive>"` stay that way and render correctly in the Runs tab.

### If V7 has to be undone

Larry removes the four `deny` entries. That is a human commit both ways (C8).

---

## §10 Risks

| # | Risk | Likelihood | Impact | Mitigation / accepted |
|---|---|---|---|---|
| **R-H1** | A server reads an env var through a name this plan's audit missed — one built at runtime, read **transitively** through a `jarvis.*` import, or read by a library | Medium | That server degrades or fails at spawn, possibly in a way that only shows under load | The §7.2 audit now resolves module-level `NAME = "ENV_VAR"` constants (review F8) and, for confirming a declaration is justified, follows one level of `jarvis.*` imports (review F11). It deliberately does **not** follow imports in the *undeclared-read* direction (over-approximation would demand spurious grants), so a **transitive read is out of that test's scope** — the one known case, `mcp-screen → upgrade_agent → JARVIS_UPGRADE_MODELS`, is declared by hand (Step 1). V3 exercises one tool per server on real hardware, and the missing-variable case **warns and proceeds** (D-H1) rather than refusing |
| **R-H2** | A **third-party library** inside an MCP child reads an env var nobody declared (`REQUESTS_CA_BUNDLE`, `SSL_CERT_FILE`, `HTTP_PROXY`, `NO_PROXY`, `OPENAI_BASE_URL`) | Medium | TLS or proxy failures on Larry's network that look like API outages | Not in `BASE_ENV_KEYS`, because K2 is a fixed cross-plan contract and this plan will not amend it unilaterally. **If V2/V3 surfaces this, the fix is a `requires_env` entry on the affected server, not a `BASE_ENV_KEYS` change** — and if it turns out to affect every server, that is a K2 amendment Larry approves in the roadmap, noted here so the next plan author does not have to rediscover it |
| **R-H3** | The account detector requires a *solid* 6–17 digit run, so a grouped account number ("account 0001 2345 6789") is missed | Medium | A real account number reaches `conversations` | Accepted and documented in the module docstring. The alternative (allowing separators) reintroduced `"account created 2026-08-27"` as a false positive in measurement. The card detector still catches grouped 13–19 digit runs if they are Luhn-valid. T4b can revisit with a proper tokenizer |
| **R-H4** | Detection is regex-only, so a **spoken-out** number ("four one one one, one one one one…") is not detected — and voice is the primary interface | **High** | The main path for a financial detail into this system is exactly the path detection is weakest on | **Accepted, and the most important limitation in this plan.** Deepgram Flux usually emits digit strings numerically for "my account number is …" phrasing, which is why V4 tests speech rather than typing, but it is not guaranteed. Written down rather than hidden, per C10. Mitigating it needs the Supervisor's judgment, which is a prompt change (C7) and belongs to T4b where there is somewhere to route a detected value |
| **R-H5** | Suppressing storage does not suppress **transmission**: Deepgram receives the audio, ElevenLabs speaks the reply, and the LLM provider sees the turn in context | Certain | A vendor holds a financial detail even on a fully-suppressed turn | **Accepted residual, stated in §2.7 and in V4.** This is precisely why Larry's sequencing rule puts the financial tier after local models (T3/G3). T4a's honest claim is "Mortimer does not keep it", not "nobody heard it" |
| **R-H6** | The **fail-CLOSED** default (D-H4, review F1/F6) means a wiring bug (the ContextVar never set at a live read site) produces **total suppression** — transcripts stop appearing | Low | Larry notices immediately (no transcript) and the guard's kill switch or a fix restores logging | Deliberate, and the direction reversed from the first draft (which was fail-open and made a wiring bug *silent*). The ContextVar is set at session/CLI start before any turn, so the `None` branch is a genuine regression, not a normal state; a loud failure is the correct posture for a security control. Countered by V4 (a normal-looking turn on real hardware proves wiring), `test_real_frame_sequence_suppresses_assistant_row`, and `test_the_flag_reaches_a_child_task` |
| **R-H7** | Sensitive text lingers where this plan does not reach: the Supervisor's in-memory `_history` (removed only by `MAX_HISTORY_MESSAGES` trimming, `jarvis/agents/supervisor.py`, anchor `self._history = self._history[-MAX_HISTORY_MESSAGES:]`), and `jarvis/procedures.py`'s `learn_from_run`, which derives a procedure label from the run's `task` | Certain | A later same-session turn can echo the value; a learned procedure can carry it | Accepted for T4a. Clearing history mid-session would break the conversation. P12 already redacts the run-log `task`, so `learn_from_run`'s run-log input is `"<sensitive>"` on a snapshot turn; its own LLM call is the residual. T4b's "decrypted for one turn, never into a sub-agent context" rule is the real fix — noted here as the two sites T4b's author must handle |
| **R-H8** | `mcp-screen`'s `requires_env_dynamic` grants **all four** vision API keys, not just the active profile's | Certain | `mcp-screen` holds three keys it will not use this run | Accepted: still a reduction from "every secret in the vault" to four, and resolving the active profile at spawn time would require the registry to duplicate `mcp_screen/logic.py:274–300`'s profile-selection logic — two implementations of one judgement, which is the failure this codebase's D1 comment already warns about |
| **R-H9** | ~~V7's deny rule blocks the assistant from authoring `skill.yaml`~~ **Resolved by resolution §A:** `skill.yaml`/`config/agents.yaml` stay editable; the guard is the frozen snapshot. So T6 skill authoring is **not** blocked | — | Superseded. The residual is that a self-edit which changes a server's privilege surface fails CI until Larry updates the denied snapshot in the same commit — that is the intended review gate, not friction |
| **R-H10** | `conversations` rows the memory sweep already folded into `memories` before this plan landed still hold plaintext | Certain | Historical exposure is unchanged by this plan | §2.5 — out of scope by design; V8 gives Larry a one-time purge he may run or ignore. This plan changes the future, not the past |
| **R-H11** | The `config/mcp_servers.yaml` `env:` map is applied last and overrides `build_child_env`, so an allowed edit could re-grant any secret to any server (review F12) | Low | A self-edit restores full credential access with no `skill.yaml`/`registry.py` change | **Closed by the frozen snapshot test** (§7.6, D-H9): `test_requires_env_snapshot.py` freezes every server's `env:` map key **and** value, and `test_no_server_gained_an_unfrozen_env_map_key` rejects a new key or a whole new server. The test file is denied (W0), so a self-edit cannot both re-grant and update the snapshot. Residual: the guard is CI-time, not merge-blocking on its own — it relies on CI being required, which it is (CLAUDE.md gate) |

---

## §11 Self-audit — the nine-item taxonomy, walked

**1. Multi-consumer contracts named but not typed.** Four contracts here are
read by more than one consumer, and each is typed member-by-member:

- `detect_financial(text: str) -> FinancialMatch | None`, with
  `FinancialMatch = frozen dataclass(kind: Literal[...], span: tuple[int,int])`
  — consumers: `jarvis/memory.py`, `jarvis/bot/sensitive_turn.py`, T4b.
  The **meaning of `span`** (the token, not the keyword context) is specified
  in D-H3 and tested in `test_span_covers_only_the_token`, because T4b will
  excerpt by it. The **evaluation order** is specified and tested
  (`test_order_is_most_specific_first`) because it determines which `kind` a
  mixed string reports.
- `is_sensitive() -> bool` — consumers: `transcript_log.py`, `supervisor.py`
  (the run-log reads a **snapshot** instead, D-H7). Its **fail-CLOSED**
  behaviour on an unset ContextVar is stated in D-H4 and tested
  (`test_unset_contextvar_is_fail_closed`), and is safe because every live read
  site has the ContextVar set before any turn (review F1/F6).
- `build_child_env(entry: dict) -> dict[str, str]` and
  `load_requires_env(name) -> tuple[list[str], list[str], list[dict]]`
  (requires_env, **optional_env**, requires_env_dynamic — review F7) — consumers:
  `_start_server`, every future MCP-server plan. Precedence order (base →
  requires_env → optional_env → dynamic → `env:` map → PYTHONPATH) is enumerated
  in D-H1 and tested (`test_explicit_env_map_still_wins`).
- `requires_env_dynamic` — a new **file format** read by the registry and
  written by every future server author. Its complete grammar (a list of
  one-key objects; `source` from a closed two-element set; unknown ⇒
  `ValueError`) is in D-H2 and tested twice.
- `SENSITIVE_SENTINEL` is a **string**, and D-H6 says why (every run-log reader
  expects a string in those keys; `null` or a removed key would change the
  format).
- **Subscribe/unsubscribe question:** `current_sensitive_turn` is a
  `ContextVar`, so the analogue is set/reset. §7.3's `holder` fixture uses
  `current_sensitive_turn.reset(token)`, mirroring
  `jarvis/runlog/context.py:48–58`'s `run_logger_scope`. Production sets it
  once per session and never resets (the session's exit disposes the context).

**2. Lifecycle left implicit.** D-H4 carries the full lifecycle table with the
**frame order stated explicitly** (review F1): start-of-turn
(`UserStartedSpeakingFrame`) clears the flag and resets the accumulator;
finalized transcripts accumulate and arm on the joined text (review F13);
end-of-user-speech flushes once; delegation snapshots the flag (review F6);
assistant-reply-complete scans the reply (review F2) and does **not** clear;
barge-in (`InterruptionFrame`) discards the partial reply and clears. The two
questions that bite: *does state survive a restart?* — no, by design (nothing
persists); *what happens on an interrupted turn?* — cleared at the next
`UserStartedSpeakingFrame` and on `InterruptionFrame`, both of which precede any
stale flush, with the reason written down. The first draft cleared on
`UserStoppedSpeakingFrame`, which fires *before* 9 of the consumers — the
BLOCKER F1 fixed here.

**3. How a value is applied.** D-H6's fifteen-row table names, for each site,
the exact expression that changes and what it becomes — `"<sensitive>"` for
run-log payload values and preview columns (P8–P10, P12, P13), a `redacted()`
line for the two `print`s (P6/P7), "not called" for the four transcript
`_persist` sites (P1/P2/P4/P5), and a returned reason/refusal string for the
memory/notes/reminders gates (P11/P14/P15). §5 gives the literal replacement
code for each.

**4. Two sections describing the same behaviour differently.** Checked
deliberately, and one conflict was found and resolved rather than papered
over: the roadmap's spoken refusal *"I'm not storing financial details yet"*
versus K3's `"financial detail — not stored (sensitive tier not yet enabled)"`.
R-3 assigns each to one audience (log reason vs. spoken copy) and D-H8 says
only the first is wired, with `remember_tool.py:19–22` as the reason. Also
checked: §6's constant table against §5's literal code (values match), §4's
manifest against every file mentioned in §5 (match), and D-H6's table against
§5 Steps 6–7 (match).

**5. Copy and visual states named but unspecified.** Three strings exist in
this plan and all three are given literally: the memory rejection
(`FINANCIAL_REJECTION`, exact, including the em dash), the redacted transcript
line (`<sensitive turn {turn_id}: {n} chars withheld>`, with a test asserting
it contains neither content nor the detected kind), and `SENSITIVE_SENTINEL`
(`"<sensitive>"`). No visual states: this plan touches no UI. The Runs drawer
tab renders `"<sensitive>"` as ordinary text, which is why the sentinel is a
string.

**6. Initialization timing.** Called out explicitly in §5 Step 5b: the
`current_sensitive_turn.set()` must run **before** `TranscriptObserver` and
`TranscriptLogger` are constructed, or the first turn of a session reads an
unset ContextVar. The `Runtime` field uses `default_factory` so the object
exists before any `set()` call can reference it. `BASE_ENV_KEYS` and the
detector patterns are module-level constants compiled at import — no ordering
hazard. `load_requires_env` reads `skill.yaml` at **spawn** time, not import
time, so a `skill.yaml` edited between runs takes effect on the next restart.

**7. Signatures agree; every schema column is populated; every value a step
needs is derivable.** Verified against source rather than assumed:
`RunLogger.__init__`'s real signature (`store.py:91–102`, `display_name` is a
required positional — §7.4's note corrects the §7.3 snippets),
`Allowlist.load`/`is_allowed` (`allowlist.py:60–79`), `registry.py`'s existing
imports (only `Iterator` is new — Step 2a), `scan_memory_content`'s
`str | None` contract (`memory.py:301`), and `jarvis/bot/__init__.py` being
empty (so the `supervisor.py` → `sensitive_turn` import cannot cycle).
Schema columns: the plan adds none. Every existing column a suppressed write
would have filled either keeps its real value (`tool`, `seq`, `ok`,
`latency_ms`, `status`, `tool_count`, `tools_ok`, `tools_failed`) or gets
`"<sensitive>"` (`args_preview`, `result_preview`, `reply_preview`, `error`) —
none is left NULL where it was previously NOT NULL. Derivability: `turn_id`
comes from `get_run_id()` or a fresh uuid, both available at arm time;
`redacted()` needs only `len(text)`.

**8. Judgment left to the implementer.** Searched for the three shapes. The
plan contains no "use your judgment" and no "investigate first". Four places
came close and each was converted into a rule:
(a) *which servers are under-declared* → the §1.2 table, from `grep`, with a
line number per name;
(b) *what to do when a `requires_env` variable is missing at spawn* → warn and
proceed, with the log format given;
(c) *whether `supervisor.py` may import `jarvis.bot`* → verified in the
sandbox (yes), **plus** a decision tree if it fails anyway;
(d) *`allowlist.is_allowed`'s name* → originally "verify before writing",
now replaced with the verified signature. §0.8 is the one remaining
open-ended instruction and it is a **stop-and-report** rule, not a
design decision.

**9. Plan drift.** §4's manifest lists **9 created + 22 modified + 0 deleted**
(this revision added `jarvis/cli.py`, `jarvis/agents/base.py`,
`scripts/check_skills.py`, `mcp_servers/mcp_notes/logic.py`,
`mcp_servers/mcp_reminders/logic.py` to Modify — reviews F4/F6/F7/F14 — and
`tests/unit/test_requires_env_snapshot.py` + `docs/plans/ALLOWLIST_SEQUENCE.md`
to Create — resolution §A/§D; the latter is authored by §5 Step 8d). Every
file named anywhere in §5 appears in it, and §4 carries an "explicitly NOT
touched" list so an implementer cannot drift into `vault.py` or
`self_edit_allowlist.json`. The create/modify split is consistent: nothing is
created in §5 that §4 lists as modified. Re-checked after this revision: the
manifest step numbers match the renumbered §5 (notes/reminders + snapshot test
= Step 8; K4 + exposure = Step 9; roadmap = Step 10).
`config/self_edit_allowlist.json` is the deliberate seam — D-H9 *describes* the
change, §4 lists it as NOT touched, §5 Step 9 ships a test that **reports
rather than asserts**, and §8 V7 is Larry making it. That is stated the same
way in all four places, which is exactly the "write X / X exists" drift this
item exists to catch. One drift was found and fixed during the audit: an
earlier draft of R-4 claimed `jarvis/memory.py` was self-editable and that
D-H9 must protect it; reading `jarvis/selfedit/allowlist.py:74–79` showed
matching is deny-first-**then-allow**, and `jarvis/memory.py` matches no allow
pattern. R-4 now says so, and D-H9 lists four paths instead of six.

---

## §12 Approval checklist

Larry ticks each before the implementing model starts.

- [ ] **The three mechanisms are the right three.** Per-server env scoping
      (K2), a sensitive-turn flag plus a financial memory gate (K3), and a C6
      isolation test (K4). Nothing stored, nothing encrypted, no key —
      consistent with *"we will not implement the financial piece until … the
      mini."*
- [ ] **R-1 accepted:** six of twelve servers under-declare `requires_env`
      today, and Step 1 corrects them before Step 2 turns enforcement on.
- [ ] **R-2 accepted:** `BASE_ENV_KEYS` is used exactly as K2 fixes it;
      `JARVIS_UNITS` and `TAVILY_API_KEY` reach `mcp-web` through
      `requires_env` instead. No K2 deviation.
- [ ] **R-3 accepted:** the K3 string is a log reason; the roadmap's spoken
      sentence is not wired, because `remember_tool.py` D8 forbids telling a
      model why its write was refused. **If Larry wants Mortimer to say it out
      loud, say so now** — it is a small change here and an awkward one later.
- [ ] **R-4 accepted:** `jarvis/skills/registry.py`, every `skill.yaml`,
      `config/agents.yaml` and `tests/**` are self-editable today; per
      resolution §A the first three of those stay editable except
      `registry.py` and the two denied test files (D-H9).
- [ ] **R-5 / F22 accepted:** `BALANCE_MIN_AMOUNT = 25.0`, **re-measured after
      the word-boundary fix**, not the first draft's `100.0`. It catches a $50
      and a $47.32 balance (*"a $50 balance is financial"*) while rejecting
      "owe you $20 for lunch". Set to `0.0` for the roadmap's literal rule. The
      floor now does only the trivial-IOU job; the boundaries do the rest.
- [ ] **The 94 test utterances (29 pos + 65 neg) are the right ones**, and the
      68-utterance routing fixture is asserted all-negative. §7.1 is the
      false-positive budget; it now includes the 18 shapes that broke the first
      draft (owe⊂borrowed, checking-the-build, account-then-order-number).
- [ ] **R-H4 accepted:** spoken-out digits ("four one one one…") are not
      detected. This is the highest-impact limitation in the plan and voice is
      the primary interface. V4 step 0 records "inconclusive" if Flux did not
      numeralise (F18).
- [ ] **R-H5 accepted:** Deepgram, ElevenLabs and the LLM provider still see a
      suppressed turn. T4a's claim is "Mortimer does not keep it".
- [ ] **R-H7 accepted:** the Supervisor's in-session history and
      `learn_from_run` still hold the text until trimming / are T4b sites.
- [ ] **Resolution §A accepted (D-H9):** deny only `registry.py` and the two
      test files; keep `config/agents.yaml` and `mcp_servers/*/skill.yaml`
      editable, guarded by the frozen snapshot (`test_requires_env_snapshot.py`).
      This keeps the 2026-08-21 decision — the first draft's broad deny would
      have reversed it. Larry applies **ALLOWLIST_SEQUENCE.md row W0**.
- [ ] **V8 decision made:** purge pre-T4a history, or leave it.
- [ ] **Branch name confirmed:** `security-hardening-t4a`. Larry commits;
      the implementing model never runs git.
- [ ] **V6 slot acknowledged:** the routing-eval score gets written into §8
      before merge (C7).

---

## Roadmap edits (apply to MORTIMER_PLATFORM_ROADMAP.md)

Per the brief and `CROSS_PLAN_RESOLUTION.md` §D, **SEC owns every edit to
`docs/plans/MORTIMER_PLATFORM_ROADMAP.md`.** The roadmap in the repo is the live
copy; the implementer applies these literal before/after blocks (Larry commits).
Each block anchors by quoted text, not line number. Several of these edits
discharge resolution items other fix-tasks reported needing (F12/F13/F14/F16,
and REMOTE's §2.2 pointer, RE-5); they are folded here so the roadmap has a
single editor.

### RE-1 — §8 plan queue: list all TEN plans and mark which are written (resolution §C-F12/F14/F16)

The native track is **three** plans, not one (resolution §C-F12): NATIVE core
is written; the T1.3 app plan and the T1.4 web-retirement plan are unwritten and
are where CORS removal, the `localStorage`-token risk, and the `agentLayout.ts`
parity test land.

**BEFORE** (§8, "Plan queue"):
```
1. `MORTIMER_SECURITY_HARDENING_PLAN.md` (T4a) — smallest, unblocks T5,
   closes the every-key-everywhere exposure now.
2. `MORTIMER_NATIVE_CLIENT_PLAN.md` (T1.0–T1.4) — after the design
   exploration has been reviewed, so the plan carries the chosen look.
3. `MORTIMER_REMOTE_ACCESS_PLAN.md` (T2).
4. `MORTIMER_SKILL_AUTHORING_PLAN.md` (T6 skill half).
5. `MORTIMER_LOCAL_VOICE_AND_MINI_PLAN.md` (T3).
6. `MORTIMER_MAIL_CALENDAR_BRIEF_PLAN.md` (T5).
7. `MORTIMER_SENSITIVE_TIER_PLAN.md` (T4b) — written only after G3 passes,
   so it is specified against the real local stack.
8. `MORTIMER_XCODE_REBUILD_PLAN.md` (T6 Xcode half) — after T1.3.
```

**AFTER**:
```
Ten track plans. "written" = the plan document exists and has been reviewed;
"unwritten" = queued, specified only by this roadmap so far.

1. `MORTIMER_SECURITY_HARDENING_PLAN.md` (T4a) — **written**. Smallest,
   unblocks T5, closes the every-key-everywhere exposure now.
2. `MORTIMER_NATIVE_CLIENT_CORE_PLAN.md` (T1.0–T1.2, T1.5) — **written**.
   JarvisKit + the RTVI client core; carries the chosen look from the T1.0
   design exploration. Sole consumer of K8's `AdminAPI` per-tab structs (those
   are deferred to T1.3).
3. `MORTIMER_NATIVE_CLIENT_APP_PLAN.md` (T1.3) — **unwritten**. The native app
   that hosts the client core (replaces `macos/MortimerHost` as the shipping
   shell). T6's Xcode-rebuild half depends on it (see §5 W4).
4. `MORTIMER_WEB_RETIREMENT_PLAN.md` (T1.4) — **unwritten**, small. Where CORS
   removal, the `localStorage`-token risk (REMOTE R9), and the `agentLayout.ts`
   + parity test land once the native app is the client.
5. `MORTIMER_REMOTE_ACCESS_PLAN.md` (T2) — **written**.
6. `MORTIMER_SKILL_AUTHORING_PLAN.md` (T6 skill half) — **written**.
7. `MORTIMER_LOCAL_VOICE_AND_MINI_PLAN.md` (T3) — **written**.
8. `MORTIMER_MAIL_CALENDAR_BRIEF_PLAN.md` (T5) — **written**.
9. `MORTIMER_SENSITIVE_TIER_PLAN.md` (T4b) — **unwritten**. Written only after
   G3 passes, so it is specified against the real local stack.
10. `MORTIMER_XCODE_REBUILD_PLAN.md` (T6 Xcode half) — **unwritten**. After T1.3.
```

### RE-2 — §5 W4 row: the KeychainStore/T4b-key clause (F13) and the Xcode-rebuilds-MortimerHost clause (F16)

**BEFORE** (§5 Sequence table, the W4 row):
```
| **W4** | T4b sensitive tier; T6 Xcode rebuild path + `macos/**` allow-list | T4b needs G3 (C3) and the native app (key holder). Rebuild path needs a Swift app to rebuild. |
```

**AFTER** (same row, plus two notes beneath the table):
```
| **W4** | T4b sensitive tier; T6 Xcode rebuild path + `macos/**` allow-list | T4b needs G3 (C3) and the native app (key holder). Rebuild path needs a Swift app to rebuild. See W4 notes F13/F16. |

- **W4 note (F13) — two different Keychain items, do not conflate.**
  NATIVE's `KeychainStore` holds the **K1 bearer token only**, with
  `kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly` (no user presence — the
  headless bot must read it). The **T4b tier key is a different Keychain item**
  with `SecAccessControl` user-presence (Touch ID / Face ID), introduced by the
  T4b plan and held by the *client*, never the bot (roadmap R-T4). A single item
  cannot serve both — the bearer token must be bot-readable, the tier key must
  not be.
- **W4 note (F16) — T6's Xcode half rebuilds `macos/MortimerHost`.** If T1.3
  (the native app plan) has not landed when the T6 Xcode-rebuild path is built,
  it rebuilds `macos/MortimerHost` (from NATIVE core), not the T1.3 app.
  `GlassSpike` is a throwaway spike and is out of scope for the rebuild path.
```

### RE-3 — §2.3 T3 gains item T3.6 (local vision), and "Local vision" leaves Out-of-scope (resolution §B)

**BEFORE** (§2.3, the T3.5 item and the Out-of-scope line):
```
- T3.5 *Sizing*: RAM = (chosen LLM weight footprint at its quantization)
  + Whisper large-v3-turbo + smart-turn + 8 GB OS/headroom; the plan records
  the arithmetic for the chosen model and rejects any configuration where
  the sum exceeds physical RAM.

**Out of scope.** Cloud hosting (the terminal state; T3 must not encode
"the mini" in anything but config — C1's provider seam). Local TTS as
default. Local vision.
```

**AFTER**:
```
- T3.5 *Sizing*: RAM = (chosen LLM weight footprint at its quantization)
  + Whisper large-v3-turbo + smart-turn + 8 GB OS/headroom; the plan records
  the arithmetic for the chosen model and rejects any configuration where
  the sum exceeds physical RAM. Add the vision model's footprint (T3.6) to
  this sum when T3.6 is enabled.
- T3.6 *Local vision* (CROSS_PLAN_RESOLUTION.md §B): a config-only profile in
  `config/upgrade_models.yaml` whose `base_url` points at the mini's local
  OpenAI-compatible server (the same one T3.3 stands up for the Supervisor LLM)
  running a vision model (Qwen2.5-VL / Llama 3.2 Vision), with `vision: true`
  and its key present; `JARVIS_VISION_PROFILE` is set to it. `screen_view`
  already calls `OpenAI(base_url=profile["base_url"])`, so **no code change** —
  the screenshot stops crossing the trust boundary for the five agents and the
  Supervisor's direct `view_screen`. Gated on T3 (needs the mini + local
  serving), exactly like the financial tier. Until it lands, screen vision
  remains cloud and `JARVIS_SCREEN_ENABLED=false` is the only full mitigation
  for the image-exfiltration path (the text-laundering path is closed
  separately by K4 keeping `mcp-screen` off the mail agent — §7.4 / resolution §B).

**Out of scope.** Cloud hosting (the terminal state; T3 must not encode
"the mini" in anything but config — C1's provider seam). Local TTS as
default. (Local vision is now T3.6, in scope.)
```

### RE-4 — §1 table rows corrected (was §5 Step 10, moved here so all roadmap edits are in one place)

**Per-server declared needs** row — replace its Fact cell with:
"Every `mcp_servers/*/skill.yaml` has `requires_env`, but six of twelve were
**under-declared** (one, `mcp-screen`, reads a name *transitively*; see
MORTIMER_SECURITY_HARDENING_PLAN.md R-1/F11); corrected by that plan's Step 1
(`requires_env` + the new `optional_env`) and enforced by the scoping allowlist."

**Vault** row — replace its last sentence ("MCP children inherit the full
environment") with: "MCP children receive `BASE_ENV_KEYS` + their own
`requires_env`/`optional_env` only (K2); no server sees a secret it did not
declare."

Also, under §2.4 "**T4a — hardening, not gated.**", add as the first line:
`Implemented by MORTIMER_SECURITY_HARDENING_PLAN.md (decisions H1–H10).`

### RE-5 — §2.2 pointer to REMOTE's roadmap corrections (delegated by REMOTE)

REMOTE's plan carries a "Corrections to the roadmap" block (R-A1…R-A4) against
the §2.2 (T2 — remote access) track, but SEC owns every roadmap edit
(resolution §D), so REMOTE delegated the pointer here. Add one line beside the
roadmap's §2.2 heading (anchor on the "### 2.2" / "T2 — remote access" text):

**AFTER** the §2.2 heading line, add:
```
> Corrections to this track's roadmap text (bearer-token flow, CORS/localStorage
> retirement, `mcp_selfedit` `requires_env` append order, the T4a precondition
> gate) are in MORTIMER_REMOTE_ACCESS_PLAN.md "Corrections to the roadmap"
> (R-A1…R-A4). Read them before implementing T2.
```

This is a pointer only — the corrections themselves stay in REMOTE, exactly as
this plan's own R-1…R-5 stay here; SEC just places the roadmap-side signpost so
a reader of §2.2 is sent to them.
