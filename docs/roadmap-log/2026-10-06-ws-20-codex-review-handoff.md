---
date: 2026-10-06
system: codex
rows: [WS-20, WS-13, WS-17]
prs: [172, 173, 174, 190]
---

# WS-13 draft review preparation — Codex, 2026-10-06

Read-only review of main `30dcb4e592316872b6675826c71f031310992839` in Codex's isolated checkout. This is a proposed reviewer handoff, not a new plan or implementation authorization. Authoritative plan: `docs/plans/MORTIMER_MAIL_CALENDAR_BRIEF_PLAN.md` (still DRAFT). WS-13 remains Claude-owned and proposed on this ref; its scope is that plan file only. No pending Codex edits exist in the reviewed checkout. No repo/runtime/production change, mailbox/calendar/provider call, credential access, or live acceptance occurred.

## Corrections required before this becomes an executable plan

1. **Secretary's literal roster violates the existing isolation gate.** Plan C6/K6/M9 (lines 21, 29–33, 895–925) grants `[mcp-mail, mcp-calendar, mcp-reminders]` while simultaneously claiming no outbound channel. `tests/unit/test_agent_isolation.py:30–35,45–59` puts `mcp-calendar` in OUTBOUND and `mcp-mail` in UNTRUSTED_INPUT. The proposed list therefore has both intersections and fails K4. This is an unresolved contract contradiction, not a passing historical finding. Preserve K4; do not remove `mcp-calendar` from its protected set to make the old plan pass. Claude must propose a compliant isolation correction for approval, not silently decide one during implementation.

2. **Read-only mail-agent behavior is only prompt-gated for reminders.** Plan M1/N2 say no reminder writes, but M9/§7.3 explicitly grant `set_reminder`, `complete_reminder`, `cancel_reminder`, and destructive `get_due_reminders`. Those are real tools in `mcp_servers/mcp_reminders/server.py:11–37`; mutations/destructive reads are real in `logic.py:173,231–277`. RM-11a already records this residual. Do not relabel it structurally read-only or treat a routing test as removing authority. Retain the residual decision for Larry or obtain an explicit revised contract before an implementation plan claims structural enforcement.

3. **Migration names are obsolete and occupied.** Plan F1/§0.11/§1.1/M16/Step 6/rollback repeatedly specify `0031_client_tokens` followed by `0032_brief`. Main `jarvis/db.py:908–913` already uses `0031_agent_event_tool_call_identity`, `0032_execution_action_claims`, `0033_skill_events`, `0034_client_tokens`, and `0036_skill_step_check_receipts`. `ROADMAP.md:725–730` reserves **0035 for MAIL** and forbids renumbering applied migrations. Correct every operative SQL constant/name/guard/test/rollback reference to the reservation; retain historical entries as history, not current instructions. Do not use generic `<n+1>` to consume 0037 or renumber existing entries.

4. **Secretary would be the seventh specialist, not the sixth.** Plan C7/K6/R-M2/§1.1/M9/Step 11 refers to five existing agents and `test_exactly_five_agents_today`. Current roster includes `app_builder`; `tests/unit/test_agents_yaml_frontend_parity.py:80–94` asserts six. The same module now has live Swift parity gates at `:107–141` against `macos/MortimerHost/Sources/MortimerHost/Console/OrbFieldView.swift`. Update roster arithmetic and the future file manifest/tests. Preserve web parity while web remains; the live native parity change cannot be omitted as “T1 handles it.”

5. **Do not overwrite Supervisor rule 13.** Plan M9/§7.7 append literal `13. Mail...` after rule 12. Main `jarvis/prompts.py:75` already owns rule 13 for delegated detail follow-up, and rule 11 refers to it. The amended mail rule must coexist with that behavior and its tests. Choose the new numbering in the approved revised plan rather than duplicate or replace rule 13 in implementation.

6. **The proposed model call no longer matches its API or workload semantics.** Plan M11 (`:1052–1059`) calls `council_mod._call_profile` without its now-required keyword-only `rung` (`jarvis/council/council.py:443–447`), which raises before inference. In managed mode that helper classifies non-PLAN_AUTHOR_PROMPT calls as workload `council` (`:467–498`); simply adding `rung` would not establish the intended brief workload/privacy/priority/budget. Secretary M9 lacks current required model-floor/default/refusal routing fields. `config/model_access.yaml` has no secretary/brief workload; `resolve_policy` rejects unknown workloads (`jarvis/model_routing.py:386–388`); `SubAgent` resolves by its agent name (`jarvis/agents/base.py:359–363`). Reconcile with the existing provider-neutral execution, model floor, saved manual subscription/API preferences, budget/deadline/usage, cancellation and no-fallback rules. Reserve any new workload/config keys in roadmap §3 before later implementation. This handoff does not pick a provider/model/privacy floor.

7. **Mail source policy and derived-result flow are missing from the old privacy description.** Plan C3/§0.10/M11/RM-14 assume ordinary tool logs and raw prose returned to the voice Supervisor, deferring redaction to T4b. For classified, policy-scoped results, main defaults unknown tool content to confidential (`jarvis/privacy_policy.py:321–326`), enforces route privacy before sending (`:47–55`), and arms sensitive handling from protected tool envelopes (`jarvis/skills/registry.py:704–715`). The registry returns raw content when `execution_scope` is absent (`:644–645`), and the proposed watcher uses plain `registry.call` (plan `:1273`). Its ingress must acquire/preserve host source policy and bind derived output explicitly; existing machinery does not automatically protect a new caller merely by name. Actual specialist continuation inherits acquired policy (`jarvis/agents/base.py:1386–1415`), and the existing protected result sink keeps protected prose off the voice Supervisor (`jarvis/bot/pipeline.py:601–627`). The revised plan must state how authorized mail/calendar sources, sanitised headlines, model summary, local UI, logs, memory and speech preserve the chosen policy end to end. Fences and short summaries do not declassify source data. Do not implicitly label mail approved_external, silently fall back to an API/subscription, or bypass existing policy checks. The correct permitted privacy/speech/logging contract is an approval prerequisite.

8. **Native rendering works generically, but ownership/arrival/privacy are not “free.”** Plan §0.10/M12/§7.11 assume adding a markdown pseudo-tool with surface window supplies all T1 behavior. Current native `DisplayPayload` has data policy/opaque references (`macos/JarvisKit/Sources/JarvisKit/AppMessage.swift:198–208`); protected results cannot export/copy/share/move to the supporting display. `AppMessageRouter.swift:235–292` applies conversation-first routing and arrival intent. `ConversationThreadView.swift:426–452` only exempts known `plan_ready`/`research_report` background tools: With layout 2/thread enabled, Conversation shown and the supporting display closed, a new no-run-ID scheduled `brief_report` within 120 seconds of unrelated user speech could be treated as that turn's answer and open. The draft emits such a payload (plan `:1291–1293`); this is a prospective plan incompatibility, not a reproduced runtime defect in the unimplemented T5 feature. The revised plan must preserve UUID identity and single renderer, differentiate on-request from scheduled/delayed arrival, retain focus/New-card behavior, and specify policy-compatible sharing/display behavior. Add corresponding native plan/test scope only through coordinated later implementation claim; this is not permission to expand the current docs-only row.

9. **Privilege manifest assumptions are stale.** Plan C8 says agents.yaml and every skill.yaml are denied; current `config/self_edit_allowlist.json:52–54` instead protects registry/isolation/privilege snapshot tests. `tests/unit/test_requires_env_snapshot.py:1–7,98–106` requires the new servers' env maps to be frozen through the existing human commit rule. Plan M15/Step 0 forces optional defaults into requires_env; `scripts/check_skills.py:118–124` and current frozen snapshot support explicit optional_env and use it for defaulted settings. Correct the plan to current K2 and human privilege-review semantics. Credentials stay required/scoped; do not widen BASE_ENV_KEYS or forward the whole vault. The future change manifest must include the frozen snapshot/human step rather than promise no protected privilege work.

10. **Tool counts, baseline and body-retention text are inconsistent.** Plan §1.1/Step 9/§11 claims 64 existing tools and 70 after adding six; `tests/integration/test_registry.py:11–27,62–64` currently declares 14 servers and 81 tools. Re-derive the final count from whichever approved tools survive the isolation correction. Header C3 (`:18`) says mail bodies are stored in digest_json, while M10/M16 (`:984,1410`) and tests say bodies never enter it. Fix that contradiction in favor of the already-stated headlines-only digest contract. Refresh old line-number/hard-coded baseline references and preserve prior measurement claims as historical, not new acceptance.

11. **Sandbox/operator instructions must match the actual coordination protocol.** Plan §0.2/§0.9 and final checklist assume one old Cowork sandbox, hard-code `feat/t5-mail-calendar-brief`, forbid all models' git, and forbid native/offline verification universally. Current AGENTS/ROADMAP permit Codex's isolated worktrees, require matching claimed owner/branch before edits, and apply Claude's Mac-git restriction only to Claude. Replace universal obsolete environment claims with system-specific handoff/verification constraints. Keep real mailbox permissions, account access, paid/live eval and human sign-offs as gates; source tests still do not prove Mac/provider acceptance.

## Binding intent to preserve in the review

- Read-only mail/calendar feature; no sending/replying/forwarding or event-writing surfaces.
- Secrets in the established secrets vault with per-child env scoping, not documents, model prompts, plists or a broad environment dump.
- Existing K4 isolation sets, human-protected privilege review, model floors, no silent paid/model/privacy fallback, current provider-neutral/manual access architecture, and protected-output constraints.
- Bodies do not enter stored/spoken digest or facts card; bounded retrieval, hostile-input fixtures, grounded deterministic fallback, once-per-day scheduling/dedup, kill switches, partial-source failure honesty and reversible release.
- Existing binding WS-17 arrival/focus/result-identity conventions and WS-21 confirmed supporting-display transfers; no new display window model.
- Routing quality floor ≥90% and V1–V10 remain evidence gates. No gate was tested or accepted by this read-only review.

## Decisions still for Larry, after Claude reconciles the draft

- Approve the revised plan/read-only scope and the explicit solution or accepted residual for calendar/reminder/injection isolation.
- Confirm Calendar.app visibility and EventKit versus CalDAV; any direct Google access is a separately specified branch, not an implementation guess.
- Approve Secretary and digest workload/profile/route/privacy; permitted speech/headlines/logging/retention/shared-display behavior under that privacy contract.
- Approve account/vault names and provide selected account access through vault/OS permission flow; no credential values enter plan/roadmap.
- Approve brief schedule/catch-up and permitted content; defaults are proposed, not answers.
- Complete live account/permission/routing/Mac acceptance and approve release/activation afterward.

Static contract corroboration embedded below derives the conflicting K4 intersections, occupied migration tail and missing required `rung` directly from current ASTs. It is not a test-suite or live acceptance receipt.


## Current WS-17/20 handoff

PR #173 remains open at `fb2e06f02544c26031bd293f2af0d81ac0a69b6f`, with the three Codex changes-requested findings still unresolved: observed-inventory numbered targets must never mutate a different UUID after renumbering; the actual callback must retain bounded choice IDs/labels; the open older result must retain Close without widening the Recents display bound or discarding Output history. The pre-existing `secondary_target` comparison transport also needs completion for the promised voice parity. Exact causal witnesses are already in the merged `2026-10-06-ws-20-codex-resumed-pr-reviews.md`; no manual file copy is needed. All five GitHub checks are green at this head, but the causal review findings are not resolved by that status. Claude remains implementer and Codex reviews each repaired head before merge. CC7a.4 subject/freshness reuse and live UI2-22…25 remain afterward.

PRs #172 (`33f5778fca287b39f892ba845b04b446fd752bbc`) and #174 (`011fdb99021be991c078ec01e0714d24c4834e07`) have roadmap conflicts. Their owner must integrate current main while keeping both sides' intent and the merged per-card acceptance checklists; rebase/merge must retain the production receipt and the already-published Versions wording/R2 guard evidence. Codex reviews changed heads; this handoff applies no branch mutation or implementation reassignment.

## Static contract proof

```json
{
  "ref": "30dcb4e592316872b6675826c71f031310992839",
  "proposed_secretary": [
    "mcp-calendar",
    "mcp-mail",
    "mcp-reminders"
  ],
  "untrusted_intersection": [
    "mcp-mail"
  ],
  "outbound_intersection": [
    "mcp-calendar"
  ],
  "migration_tail": [
    "0029_memory_classification_budget",
    "0030_memory_admission_shadow",
    "0031_agent_event_tool_call_identity",
    "0032_execution_action_claims",
    "0033_skill_events",
    "0034_client_tokens",
    "0036_skill_step_check_receipts"
  ],
  "call_profile_required_keyword_only": [
    "rung"
  ],
  "proof_type": "stdlib AST static contract check; no app/provider call, suite not rerun"
}
```
