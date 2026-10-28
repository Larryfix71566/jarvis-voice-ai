# Mortimer mail delivery and private reader — proposal for review

**Prepared:** 2026-10-28 with GPT-6 Luna, at Larry’s request

**Base:** freshly fetched `origin/main` `233995cb9fb0f9a5e1f2fd35611b4cfa1b5e0af8`, merge commit time `2026-10-27T20:32:49-04:00` (`2026-10-28T00:32:49Z`); PR #280 merged Kimi’s bounded WS-23 review and WS-31 NR1 handoff

**State:** proposed for a draft PR and WS-13 owner review. It does not change the canonical plan, roadmap row, source or config, activate a claim, or authorize credential access, live tests or release.

## Goal and evidence boundary

Restore dependable Gmail headlines in the daily report, then complete an explicitly read-only mail search/read/summary experience whose private message processing stays local. Sending, deleting, archiving, changing labels, and saving drafts are excluded and require a separate future decision and claim.

The report that says “Gmail unavailable” is user-confirmed, but its producer, date, exact status/error and account state are still unknown. Source code does not use `unavailable` as a mail status; `mcp_servers/mcp_mail/logic.py:128–134` says that status belongs to calendar. The existing `mail_headlines` account result returns `ok`, `partial`, `failed`, `timeout`, or `not_configured`, with a reason in `error` where available (`logic.py:942–950`). Mail disabled is a top-level `mail_disabled` result (`logic.py:823–825, 858–859`). A report may be translating one of these or may come from another producer; do not infer the mapping.

The installed development bundle’s source revision and checked clean checkout HEAD identify as `c63ecce97108787c55ef55fad73d32236694cc65`; the relevant P1 files are unchanged through current main. Launchd reports the Mortimer services disabled and unregistered. Process inventory was denied, so whether an app process is open is unknown. An earlier accepted M1-2/M1-3 record reports successful read-only Gmail and AT&T headline reads on deployed `575cc7b`; it does not establish present credentials or availability. M1-1’s formal repeat remains open. The inspected `data/status/daily-*.json` files are the model/provider status job’s outputs, with no mail fields; its disabled `com.mortimer.status-daily` label is not evidence about the separate mail report. A bounded scan found no Gmail mail-account event in that job log.

Fresh main contains P1’s Gmail-capable IMAP source (`logic.py:67–73`), but no P3 report implementation (`jarvis/brief.py`, `brief_tool.py`, `brief_watcher.py` are absent). Main documents that P2 calendar is a prerequisite for P3’s combined scheduled brief. The tracked Python, Swift and config scan found no other mailbox-report producer. This does not challenge Larry’s report that a daily report with mail exists, and does not establish whether its producer is in Mortimer or elsewhere. The first delivery step is to identify that producer and inspect its status metadata; if it is a different product or external job, Mortimer source alone cannot repair it.

## Existing WS-13 scope and disposition

The canonical source is `docs/plans/MORTIMER_MAIL_CALENDAR_BRIEF_PLAN.md`; §R, especially R.4–R.13, is authoritative over the August draft.

| Increment | Existing design/status on `233995c` | Proposed treatment |
|---|---|---|
| P1 mail headlines | Implemented: bounded TLS IMAP, read-only `EXAMINE`/`UID SEARCH`/`BODY.PEEK` headers, source policy and names-only preflight. Historical M1-2/M1-3 passed; current formal M1-1 and present account status remain unverified. | Diagnose current report and repeat P1 acceptance at an eligible build before changing source. Fix only an evidence-backed defect. |
| P2 calendar | Not claimed; requires the approved EventKit path, session eligibility, Google calendar setup for parity, and WS-17 coordination. | Keep out of a mail-only restoration. If the identified report is the canonical combined brief, register/complete P2 first as R.6 requires. |
| P3 deterministic scheduled/on-request brief | Not implemented in current main; depends on P2 eligibility and includes protected delivery/history, migration `0035_brief`, reminders and release checks. | Do not call P1 “the daily report” or bypass P2. Any new mail-only report adapter needs its own explicit scope decision. |
| P4 model-written brief | Optional and gated by R.11.1, 2, 6, 7 and a claim-time workload/policy review. | Defer. No cloud model gets message bodies or mail-derived private text. |
| P5 mail question agent | Not implemented. R.11.2–5 are prerequisites. Existing design has `mail_read(message_ref)` and explicitly says “There is no search” (R.11.5). | Reuse its security and reference design, then add bounded header search as a new reviewed capability. Local-only summaries by default; fail closed if no eligible local route or sink. |

P1’s secret isolation, source envelopes, read-only IMAP command set, bounded responses, honest exact/lower-bound/unknown counts and content-free logging remain binding contracts (R.10 and S1-1–9). P5 cannot relax them. Larry’s D1–D9 decisions are already recorded in R.5: P1–P3 precede optional P4/P5; default mail policy is confidential; the default spoken acknowledgement is fixed; and writes remain outside scope. Revisit a decision only through an explicit user decision, not implementation convenience.

## Staged delivery and gates

### 0. Pin down the unavailable report

1. Treat the daily mail report as the existing user-reported feature. Record its title/source, date and the exact user-visible status phrase. Identify the executable or service that produced it from its own non-content status panel or configuration metadata.
2. Trace that producer’s Gmail status mapping back to `mail_headlines` or to the external source. The desired diagnostic record is only: report/run id and time; source/build revision; account key (`gmail`); status; error/abort code; phase; duration. Do not collect sender, subject, body, address, credential, auth response text or session transcript.
3. Compare the report event to the supported source states. `not_configured` means one or both Gmail credential names are missing/unresolved in the child (`logic.py:836–841, 877–880`); `login_rejected` is an explicit failed LOGIN (`logic.py:612–619`); TLS, network, protocol, server abort and deadline have separate reason codes (`logic.py:746–764`). Preserve the distinction in report text.
4. No current report event was available in the already inspected safe artifacts. The existing `scripts/check_mail_env.py` can report names-set/forwarding/switch/account readiness without printing values or opening a socket, but internally sources `.env` and calls vault injection (`script:10–16, 29–31`). It is pending a narrow explicit authorization and is not run as part of this plan.

**Gate 0 exit:** name the actual report producer and provide its status/error metadata, or record “producer outside Mortimer repository; no Mortimer change assigned.” Do not start provider access to compensate for missing diagnosis.

### 1. Restore and prove Gmail headline delivery

Use the current P1 implementation; do not recreate it. Once Gate 0 identifies the producing path, check exact source/app identity, environment forwarding and kill switch. If preflight is approved, run only the existing names-only check on the identified eligible build. It distinguishes credentials visible to `mcp-mail` from missing/unforwarded names without connecting to Gmail; it cannot prove authentication.

If the source path is correct but the actual status is `login_rejected`, `network`, `tls`, `server_abort`, `deadline` or another explicit result, retain the code’s reason and show a clear per-account result in the identified report. Correct only a demonstrated report translation, configuration-forwarding defect, startup mismatch or bounded source bug. Do not label login rejection “unavailable”; do not conceal a partial result; never turn unknown/incomplete enumeration into zero. Keep a working other account usable when Gmail is unconfigured or fails.

Offline regression cases use the existing fake IMAP server: missing Gmail names → `not_configured`; kill switch → `mail_disabled`; Gmail login rejection distinct from a BYE/server abort; TLS/network/protocol/deadline each mapped to its safe reason; one account failure leaves the other’s result intact; partial enumeration reports lower-bound/unknown honestly; no header read marks a message read; and all errors/logs exclude credential values, server text, addresses, headers and body. Extend the existing content-free `mail_account_done` fields only if a concrete missing field is shown; log status/reason/phase/duration, not account identifiers beyond the fixed account key.

**Gate 1 acceptance:** all P1 source tests S1-1–9 pass; report-level mapping tests cover every status above and an account-isolation case; then, with separate explicit authorization, Larry performs M1-1 (names-only scoping on the eligible installed build), M1-2 (unread preservation) and M1-3 (Gmail returns `ok` or a specific status). Live M1-3 uses bounded header-only IMAP calls; no body fetch. Record exact build and outcome. A previous pass on `575cc7b` is historical, not a substitute.

### 2. Add a local-only read/search/summarize path

Only after Stage 1 is accepted and the P5 prerequisites are reviewed, use P5’s ephemeral message reference and body parser as the foundation (`R.11.5`). Existing P5 is read-only and explicitly has no search. Design one additional bounded search interface before implementation: user-level filters over account, date window, unread state and sender/subject; server query is built from validated fields, never model-supplied raw IMAP commands. Return a capped list of stable ephemeral references and safe headline fields. A selected reference may be read once under the existing byte, MIME, attachment, age and expiry limits. Do not cache message bodies persistently unless separately approved.

Private email bodies remain on the machine after retrieval. Default summary is deterministic/local. If an on-device model is considered, resolve only an explicitly approved local-only route; fail closed when unavailable. No cloud route or fallback may receive a body or private email-derived text. Do not change the global model, route registry or Mortimer harness-controller model under this proposal. Do not let message text trigger tools or enter the Supervisor conversation, notices, memory, run logs, or outbound arguments. Keep P5’s eligible local result sink, typed literal rendering and strict privacy label. If there is no eligible local sink, refuse before acquiring a body.

Offline tests add malformed/injection search filters, query caps, account/ref isolation, expiry/UIDVALIDITY change, expunged messages, MIME/attachment-first structures, attachment and oversized body refusal, hostile body instruction (zero follow-on calls), missing sink (zero acquisition), cloud route (zero model/body transmission), and content canaries absent from logs, history, notices, Supervisor context and persisted files. Preserve the existing P5 routing/injection checks and update them only after an independent source/contract review. Larry’s live checks use an explicitly approved test message and confirm unchanged unread state.

**Gate 2 acceptance:** R.11.1–5 findings resolved; security/source review and CI bind to exact source; local-only/no-cloud properties demonstrated with offline stubs and canaries; M-level user/device tests explicitly approved and recorded. P4 is unnecessary for this stage.

### 3. Future third-party actions are a separate proposal

No send, reply, draft, delete, archive, move, label, mark-read, forwarding or calendar write API. Any such request needs a new decision, threat review, human confirmation design, a separate main-roadmap claim and new authorization. It must not inherit this read-only approval.

## Acceptance and regression matrix

| Stage | Offline/source evidence | User/device evidence and release gate |
|---|---|---|
| 0 — diagnosis | Status-state mapping test; no content in diagnostic projection. | Identify report producer and run id/build/status/error. No credentials, sockets, messages or service start. |
| 1 — P1 | S1-1–9; report renderer cases for `ok`, `partial`, `failed` with each reason, `timeout`, `not_configured`, top-level `mail_disabled` (shown as disabled in the report); both-account independence; missing/expired config; no false zero; no `\\Seen`; content-free logs. | M1-1 approved names-only preflight; M1-2 unread preserved; M1-3 bounded Gmail connection/headline read returns `ok` or explicit code. Record installed source revision. |
| 2 — P5 read/search | R.11.1–5; search grammar and limits; ephemeral reference integrity; body/MIME bounds; injection, sink, route and storage canaries; zero external model calls with bodies. | On-device eligibility, requested read on explicit test message, unread remains unread; local route and output policy demonstrated. Only with separate M3/P5 approval. |
| 3 — actions | No tests or source in this plan. | New authorization, roadmap row, design and independent review required. |

## Owners and non-overlap proposal

| Work | Proposed accountable/author | Reviewer or human gate |
|---|---|---|
| This plan and assignment proposal | Codex using the user-selected GPT-6 Luna; complete in this task. | Parent reviews before publication. |
| WS-13 design and implementation | Claude remains the accountable WS-13 owner and proposed author for the future P1 reliability and P5 search/read claims. This draft hands the plan to Claude for review; no implementation claim is active. | Codex prepared this proposal with GPT-6 Luna and will review claim-specific source changes; WS-05 owner reviews any `registry.py` source-classification or `config/model_access.yaml` workload changes. Larry owns acceptance and release. |
| Stage 0 — report diagnosis | Claude, as current WS-13 owner, acknowledges the plan and identifies the reported daily producer/status from non-content metadata before creating a source claim. | Codex can review the status mapping. No credential preflight or provider access is part of this handoff. |
| Stage 1 — P1 headlines/report | Claude proposes a separate exact-scope claim only after Gate 0 identifies the report path; use the existing P1 source and add only evidence-backed corrections. | Codex reviews the source/status contract; WS-05 reviews registry classification if touched; Larry records M1 acceptance. |
| Stage 2 — P5 search/read | Claude proposes a separate claim after Stage 1 and R.11.1–5 review; this adds new bounded header-search scope because existing R.11.5 says there is no search. | Codex reviews privacy and source handling; WS-05 reviews any model/source policy; Larry decides local route and acceptance. |
| Kimi #280 assignments | No mail work assigned. PR #280 (`233995c`) records Kimi’s bounded WS-23 review and WS-31 NR1 implementation. Their documented scopes are limited to acceptance verifier / REA docs and WS-31 pure admission contract files, respectively; no overlap with mail source or this local artifact. | Preserve those exact Kimi scopes. Any later mail reassignment requires parent/Larry clarification and a matching main-roadmap handoff. |

This handoff preserves Claude as WS-13 owner; GPT-6 Luna is the requested authoring model for this plan. It does not activate source implementation, change a model route, or claim acceptance. P2 and P3 retain their existing R.6 dependencies; any P3 attempt touching WS-17’s locked arrival, history, display, or `pipeline.py` portions requires a fresh §4 agreement. The `0035_brief` reservation remains solely for canonical P3; do not use it for a P1 repair or invent another shared identifier. The separate WS-30 phone-access work and its parent ownership remain untouched.

## Proposed roadmap/assignment delta (for parent review; not applied)

Keep WS-13’s owner (`claude`), canonical plan path, migration reservation, status history and acceptance gates intact. This PR publishes a proposed handoff only; it does not edit the Claude-owned roadmap row or activate a claim. After Claude acknowledges the coordination and the report producer is identified, Claude can record a dated next-step/claim in the existing WS-13 row under the repository protocol:

> **Proposed next step:** Claude remains WS-13 owner. Claude acknowledges this plan and identifies the source/status of Larry’s existing daily mail report from non-content metadata. If source changes are needed, Claude proposes separate Stage 1 P1 and Stage 2 P5 claims with exact paths on then-current main; GPT-6 Luna is the requested plan-authoring model, not a change to WS-13 ownership or an active source claim. Codex reviews the source/status and privacy boundaries; WS-05 reviews registry/model-policy portions where applicable; Larry records the existing M1 acceptance and release outcomes. Stage 2 adds bounded header search because canonical R.11.5 currently states there is no search. Kimi’s #280 WS-23/31 and WS-30 phone-access ownership remain unchanged. No P2/P3, model-route, provider-write, service-start or release authority is implied.
>

Before any implementation, Larry registers the precise owner, branch and file scope on then-current `origin/main`; each increment gets a separate claim as R.6 requires. Update the canonical plan and roadmap only in the agreed owner’s branch, include any §4 overlaps (especially WS-05 registry/model policy and WS-17 brief/session/display portions), obtain cross-review and CI, and wait for Larry’s release authorization.

## Scope boundaries and recovery gates

1. **Present config readiness:** the existing `scripts/check_mail_env.py` is the canonical names-only M1-1 check. It can run during a separately authorized acceptance step against the named installed development build. It reads `.env` in its startup shell and invokes vault injection in process; its contract prints only set/unset names, forwarding, scoping, kill-switch and per-account readiness, and opens no provider socket. If this scope is not approved, use only already-persisted status metadata.
2. **Gmail reachability:** M1-3 is the canonical user/device acceptance check on the named deployed revision, with the configured account and bounded read-only IMAP/header behavior. It performs a provider login and query. A denied login is reported as a code; no password is displayed or changed. No body or write command.
3. **Release and recovery:** any deployment or service start is outside this planning PR and must follow the canonical `scripts/deploy_main.sh` process after Larry authorizes the exact target revision. The installed development services are recorded held; this plan does not enable or start them. Record pre/post identities and rollback receipt. If the health gate fails, restore the prior source/app through the approved deploy recovery path and leave services held pending review.
4. **To stage P5 live checks:** separate authorization for explicit local-app read of a test message and user-observed unread preservation. No cloud model call is part of acceptance.

This PR requests Claude’s review/acknowledgement of the WS-13 plan and proposed next steps. The draft authorizes no credential loading, provider call, service start or deployment.

## Source pointers

- `AGENTS.md`: repository work requires a matching main workstream row, main-first coordination, scope locks and existing-plan reuse. The proposal avoids editing the WS-13 row or canonical Claude-owned plan.
- `ROADMAP.md:350–388`: joint rules and approval/acceptance gates; `:623–661`: WS-13 current owner/status/scope; `:1554` shared mail credential-name and migration reservations; `:1612–1618` WS-17/WS-05 conflict boundaries.
- `docs/plans/MORTIMER_MAIL_CALENDAR_BRIEF_PLAN.md:R.4–R.6`: P1–P5 architecture, policy and incremental dependencies; `R.10`: P1–P3 contracts; `R.11.1–5`: P5 prerequisites; `R.11.5`: bounded body read and explicit no-search limitation; `R.12`: S1/M1 acceptance; `R.13`: WS-17, WS-21 and WS-05 coordination.
- `mcp_servers/mcp_mail/logic.py:67–83, 128–134, 575–595, 612–619, 735–778, 823–881, 938–950`: Gmail endpoint/name references; statuses; abort mapping; mail switch and credential gate; per-account output and diagnostic event.
- `mcp_servers/mcp_mail/server.py:15–23`, `mcp_servers/mcp_mail/skill.yaml:1–18`, `config/mcp_servers.yaml:100–107`: current headlines-only capability and scoped child configuration.
- `scripts/check_mail_env.py:1–31`: names-only output contract and its environment/vault loading behavior.
- PR #280 merge `233995c`: Kimi handoff is WS-23 review and WS-31 NR1 implementation, not a mail assignment.
