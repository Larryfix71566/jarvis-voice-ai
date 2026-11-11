---
date: 2026-11-11
system: kimi
rows: [WS-36]
prs: [332]
---

# WS-36 independent review: C0 and C0b interface contracts

- **System:** Kimi
- **Session:** `20-34-29-68cd6dae`
- **Workstream / item:** WS-36, review of C0 and C0b
- **Reviewed PR:** #332, `docs(contracts): C0 and C0b interface contracts (draft)`
- **Reviewed head:** `1f8aca7ee086912d1c9ffddcedbd65af738ca38b`
- **PR base reviewed:** `next` at `a1369e223e51cc499c8f942fae95133994a4facb`
- **Frozen source:** `5777e98cf1cdbaa65eb13079044693794c071927`
- **Verdict:** **CHANGES REQUESTED**
- **Review type:** static contract and source review. This is not a live approval test, UI acceptance pass, deployment, or merge authorization.

Kimi reviewed §0, §2, §3, §5, §6 and §7 in full, and read §1 and §4 for cross-section effects. Codex remains the lead for the detailed §1 layout and §4 box-828 citations; this verdict does not claim an independent audit of every source citation in those two sections. The reviewed PR head did not change during the review. Its allowlist, policy-tests, controller-tests, knowledge-base and validate checks all passed; those checks do not settle the behavioral findings below.

## Blocking findings

### B1 — Approval confirmation does not identify a self-contained operation when the preview has no recognized ref

§3.8 injects only `Confirmed. Go ahead with the pending {tool} from {agent}.`, with an optional ref. §3.3 recognizes only `staging_id`, `preview_id`, `draft_id` and `action_id`. It does not put the recorded summary, run id, origin request id, or original arguments into the confirmation (`docs/contracts/MORTIMER_INTERFACE_CONTRACTS.md:364-369`, `:454-462`).

That leaves the exact operation ambiguous, especially when more than one preview is open for the same specialist and tool. The delegation contract requires a fully self-contained task because a subagent cannot see the Supervisor conversation (`jarvis/agents/delegate.py:413-427`; `jarvis/agents/base.py:3-5`). The following preview results have no ref recognized by §3.3:

- `app_create` returns `proposed_name`, `template` and `files` (`mcp_servers/mcp_apps/logic.py:192-205`).
- `app_build_start` returns `app`, `goal` and `profile` (`mcp_servers/mcp_apps/logic.py:311-323`).
- `research_compare_start` returns `urls` and `focus` (`mcp_servers/mcp_web/logic.py:600-611`).
- `plan_start` returns `goal`, `mode`, `profile` and `review_path` (`mcp_servers/mcp_selfedit/logic.py:728-732`).

A routing-eval case proving only that the fixed sentence reaches the same agent does not prove that the specialist reissues the intended tool with the intended arguments.

**Required correction:** record and inject enough bounded original operation data to make the specialist task self-contained and uniquely identify the preview, or introduce a real resumable operation identifier accepted by the tool on confirmation. Preserve the rule that the approval handler itself never calls a tool. Add execution-level tests for every no-ref preview shape above, including two previews from the same agent/tool, asserting the exact confirmed tool and arguments rather than only the delegate destination.

### B2 — Pending resolution and supersession can settle the wrong operation

§3.3 resolves an entry on any later non-preview result with the same `agent` and `tool`, and supersedes an older preview whenever a newer preview has that same pair (`docs/contracts/MORTIMER_INTERFACE_CONTRACTS.md:371-379`). It ignores the already-recorded `run_id`, `origin_request_id`, ref and logical operation.

Two concurrent requests can legitimately use the same specialist and tool. Under the written rule, an unrelated result or preview can therefore remove a different pending approval. That breaks the multiple-open-approval decision in §3.10 and can make the remaining UI item refer to an operation other than the one the user expects.

**Required correction:** define deterministic correlation to the exact operation for resolution and supersession, using run/request identity plus a ref or bounded argument identity as needed. Do not use only agent/tool. Add tests with two same-agent/same-tool previews and with an unrelated non-preview result; the unrelated entry must remain pending and no incorrect `approval/settled` may be emitted.

### B3 — “Decline never runs anything” contradicts sending decline through an LLM turn

§3.2 rule 6 says decline never runs anything. §3.8 nevertheless builds `Declined. Do not run...` and delivers it through the accepted typed-request path, whose rule 1 starts exactly one model run (`docs/contracts/MORTIMER_INTERFACE_CONTRACTS.md:350-358`, `:454-462`; `:302-316`). A model turn cannot provide a hard guarantee that nothing runs.

**Required correction:** settle a decline locally, emit the decision/result without creating an LLM turn, and leave any necessary user-visible acknowledgement deterministic. Add a test proving decline creates no context message, model run, delegation or tool call while still settling only the selected approval.

### B4 — Approval is settled before the replacement turn is known to have started

§3.8 first settles the entry and sends `approval/settled`, then builds and delivers the typed turn (`docs/contracts/MORTIMER_INTERFACE_CONTRACTS.md:454-462`). The typed path can refuse when `runtime.alive` is false, and the existing context-injection path can fail before enqueueing (`:313`; `jarvis/bot/pipeline.py:2444-2454`). The UI can therefore remove the pending approval even though no confirmation turn started.

**Required correction:** make `accepted`/`approved` contingent on successful enqueue of the confirmation turn. Define the failure response and whether the entry remains open or expires, and make the UI state agree. Test dead-runtime and injection-failure cases, asserting that no premature `approval/settled` is sent and no silent loss of the pending operation occurs.

### B5 — Sensitive-turn suppression is not specified at the approval hook or decision handler

§3.2 rule 5 requires that no approval be published or accepted on a sensitive turn. §3.3 instead relies on protected-route event stripping and says that this satisfies the rule by construction (`docs/contracts/MORTIMER_INTERFACE_CONTRACTS.md:350-358`, `:360-383`). Protected-route stripping removes result payloads (`jarvis/agents/base.py:324-335`), but it is not equivalent to `is_sensitive()` for ordinary sensitive turns. `is_sensitive()` is the required fail-closed check and treats an unset context as sensitive (`jarvis/bot/sensitive_turn.py:79-93`).

**Required correction:** explicitly guard recording/publication and decisions with `is_sensitive()` at the approval boundary, while preserving protected-route stripping as a separate control. Add ordinary-sensitive and unset-context tests for both preview ingestion and `approval/decide`, with no pending message and no injected turn.

## Should-fix findings

### S1 — `origin_request_id` has no specified provenance at the approval hook

§3.3 requires each pending entry to store `origin_request_id`, and §3.9 uses it to place the approval under the owning request (`docs/contracts/MORTIMER_INTERFACE_CONTRACTS.md:364-369`, `:464-473`). The emitted `agent_tool_result` event carries agent, tool, arguments, result, run id, status and latency, but no origin request id (`jarvis/agents/base.py:1800-1809`; the parallel emit at `:1851-1860`). The current `on_agent_event` hook does not add one (`jarvis/bot/pipeline.py:970-1040`).

**Required correction:** name the trusted mapping from the delegated run/tool call to its foreground request and define null behavior when that mapping is absent. Add a test proving an approval is attached to the correct request when two foreground requests have concurrent delegations.

### S2 — The typed-request stale-session response is unreachable under the validation wording

§2.2 says failures of rules 1–4 receive no reply, but rule 3 includes a well-formed request whose session or generation does not match. §2.3 defines a `stale_session` reply (`docs/contracts/MORTIMER_INTERFACE_CONTRACTS.md:272-300`). §3.6 and §3.7 should make the same distinction explicit for approval decisions.

**Required correction:** state that malformed or untrustworthy identity receives no reply, while a well-formed request with a parseable request id and stale session/generation receives `stale_session`. Add separate malformed-identity and stale-session tests.

### S3 — Approval replay needs the same explicit bound as typed-request replay

§2.3 bounds typed replies at 128 entries for 300 seconds. §3.7 requires replay of the first approval result but gives no cache bound or TTL (`docs/contracts/MORTIMER_INTERFACE_CONTRACTS.md:298-300`, `:437-452`). The existing `ConsoleSession` precedent uses 128 responses for 300 seconds (`jarvis/bot/console_session.py:23-32`, `:54-63`).

**Required correction:** state the approval replay bound and eviction behavior and test duplicate, expiry and oldest-entry eviction cases.

### S4 — Zero-open bare-yes behavior conflicts with the exactly-one-open rule

§3.2 rule 7 and §3.10 say a bare yes approves only when exactly one approval is open. §3.10 rule 2 nevertheless sends a zero-open bare yes to the Supervisor unchanged, where the existing rule 9 can still confirm a preview (`docs/contracts/MORTIMER_INTERFACE_CONTRACTS.md:356-358`, `:475-487`). This also needs an explicit interaction with §3.2 rule 5, which says a sensitive-turn user answers by voice even though no approval is published.

**Required correction:** define whether zero-open voice confirmation is an intentional legacy/sensitive exception or is forbidden, then make the hard rule and algorithm agree. Test zero, one and multiple open entries for typed and spoken yes, including the sensitive-turn exception if retained.

## C0b and source checks with no additional finding

- The six WCAG contrast ratios in §5.1 independently recompute against `#15191D` as follows: listening `4.5944`, user `9.4906`, Mortimer `5.4750`, OK `14.8866`, approval `12.7648`, error `5.9341`; these round to the contract's figures. They remain calculations on the app background, not glass acceptance.
- The cited existing tokens remain `amber #FFB454`, `green #3DDC97`, `red #FF5F56` and `attn = amber` (`macos/MortimerHost/Sources/MortimerHost/App/AppTheme.swift:23-27`). The existing user/assistant RGB values are `#2DD4BF` and `#E07020`, and the stale Mortimer comment is present (`App/AppTuning.swift:122-127`).
- The cited mockup type sizes, palette figures, muted arc and white-core gradient support §5.1 through §5.3. C2 must still check actual glass, Reduce Transparency and Increase Contrast fallbacks; this static review did not run the UI.
- `prepare_commit`, `commit`, `prepare_push`, `push`, `repo_write_file` and `repo_commit_write` return the retired sandbox response, and migration 0026 expires legacy pending actions (`mcp_servers/mcp_git/logic.py:241-258`; `mcp_servers/mcp_repo/logic.py:468-475`; `jarvis/db.py:662-674`).
- Independent AST counting confirms 99 `ALLOWED_ACTIONS` entries at the freeze. The hello truncation and 100-action validation limit are at `jarvis/bot/console_protocol.py:302-335`.
- The current `DisplayResultStore` draft-tool set and failed-result display suppression support §0 item 2; no live behavior claim is made here.

## Required test-list update and next action

§6 currently covers the happy-path preview, same-agent/tool resolution, ref injection and ambiguous yes cases, but does not cover the blocking identities, failure ordering, no-model decline, sensitive approval boundary, concurrent request attribution, or replay bounds above (`docs/contracts/MORTIMER_INTERFACE_CONTRACTS.md:610-637`). Add the required cases beside the relevant corrected rules before C3, C7-py and C7a treat the contract as settled.

Claude should revise C0/C0b on a successor PR head for independent re-review. Kimi's next authorized item is A3; C2 waits for the corrected C0b contract on `next`.
