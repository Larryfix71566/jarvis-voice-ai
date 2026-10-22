# Model Use Enhancements

**Status:** Recommendation-only R3 source will be landed via its separate implementation PR after claim #241 and required review/CI; this draft itself grants no merge or installation.25 reviewed source files are byte-identical on636880e. Universal harness switching remains unavailable. Earlier claim/provider status follows: Recommendation-only harness publication claim staged 2026-10-22; after this claim merges, the bounded R3 artifact may proceed through its separate draft review/CI. No implementation/acceptance is marked landed by the claim. Existing provider status follows: Revised combined implementation is staged for paired #232/#233 integration; after merge its implementation is landed while release/live acceptance remains open. Frozen `e74e4b8` passes all twelve original independent checks; [revised evidence](../acceptance/command-console/receipts/ws05-ws17-selective-integration-2026-10-21.md). Required exact-source cross-system review is not completed; publication CI remains separate. Historical status follows: SUBSCRIPTION RETIREMENT STAGED 2026-10-21 — draft #232 contains opt-in runtime guards and a buffered native voice/tool adapter; activation and incremental-streaming acceptance remain blocked. Claim #230 is merged and all five claim CI checks passed. No deployment or runtime activation. Historical LANDED FOUNDATION AND BOUNDED CAPABILITY FIXTURE REPAIRS — #177, #200 and #201, merged as `83d90e8` on 2026-10-10 (source `08c0635`, final head `de4381c`; all five CI checks passed). Larry approved revised `08c0635` for offline WS-17 verification only on 10-10; its comparison against frozen `59d57ea` is running, without a pass claim. The earlier approved a5b6f88→ce6cde8 twelve-check pass and subsequent dry-child CI failure remain separate history. Live model acceptance and rollout remain gated.
**Recorded:** 2026-09-20.
**Origin:** Larry's model-access, subscription, SAYGM, orchestrator, and latency discussions; implementation plan preserved from the conversation at Larry's request.
**Scope:** Manual subscription/API selection, SAYGM integration, privacy-aware routing, and preservation of Mortimer's existing behavior. Voice-provider replacement is a separate decision requiring testing.
**Authorization:** Saving this document does not itself authorize implementation, deployment, account changes, or live provider calls.

**Current implementation evidence (2026-09-20):** `jarvis/model_routing.py`,
`jarvis/saygm.py`, `jarvis/privacy_policy.py`, and
`jarvis/model_execution.py`, and `jarvis/model_preferences.py` provide the
policy, catalog, privacy, provider-neutral execution, and draft-confirmed
preference foundations. The admin sidecar exposes `GET /api/model-routes` plus
the stage/confirm preference endpoints. Existing runtime behavior remains unchanged until
`JARVIS_MODEL_ROUTING_ENABLED=1`; Claude and Codex subscription adapters are
text-only and explicitly gated, reject Mortimer tools, and strip inherited API
credentials/endpoint overrides before launch, so tool-bearing subscription
workloads fail closed until a sandbox-preserving bridge is validated. Focused verification:
the full unit suite passes (2,644 tests, 2026-09-20) using the repository's installed test
environment. `JarvisKit.AdminAPI` now has typed route-status and
draft-confirm methods, and the native Repo sidecar presents those controls
plus selected-route capabilities/privacy/billing metadata; the JarvisKit suite
passes 195 tests. MortimerHost builds successfully, while its full 250-test
run has 3 display-dependent skips and 8 failures in `WindowVisibilityTests`
when run without a visibly unoccluded GUI window; re-run those tests in an
active GUI session before release sign-off. The gated `model_route` voice tool uses
the same preference store and confirmation boundary; live voice acceptance is
still required. Background memory factories retain the resolved route object,
so enabled-mode subscription/SAYGM adapters do not assume an API credential.
The preserved `claude-haiku-4-5` voice supervisor is resolved through a
voice-only built-in profile, so readiness checks validate the unchanged voice
route while the general model registry continues to reject Haiku for
non-voice workloads.

**Current merged status (2026-10-06):** [PR #177](https://github.com/Larryfix71566/jarvis-voice-ai/pull/177) merged as `c38d895`, including final head `06a7ad5` and code head `408bc6f`; both heads passed all five CI checks. The merge does not establish live acceptance or deployment. The isolated branch
`codex/ws05-execution-20261005` is claimed on main through #175, #176, #178,
#179 (`fb3e1aa`), #180 (`4a2d4aa`) and #181 (`ac8eb7a`) before their bounded source/council/advisory edits.
Production checkout, installed bundle and deployment receipt agree on
`bde22bb`; the 10-05 aggregate-only baseline records 26 provider calls (12 LLM)
since deployment, with no populated historical route, billing-source or
model-duration fields. Those missing measurements cannot be recovered.
Running-process activation and representative workload quality remain open.

The candidate adds exact catalog/model/capability binding and pinned credential
contracts, workload quality floors, saved native preference and stale-draft
repairs, confidential replay/settlement execution, content-safe continuation
logs, and prospective non-streaming API accounting metadata. These are local
implementation results, not deployed acceptance.

The 10-06 integration also refreshes saved selections for each SubAgent run,
preserves concurrent snapshots and refuses unreadable preferences instead of
using an old model. Native owners retain cleanup quarantine across ordinary
runs and named-model preflight. Sealed host tool results are validated before
agent/log/event/continuation sinks; unknown sources stay confidential, verified
public failures are reduced to fixed categories, and repository source scopes
are pinned to actual guarded paths and bytes. Optional output/deadline and
configured-price task admission retain stricter parent bounds without writing
observed usage or silently selecting another route. The legacy registry and
council now reject canonical and wire aliases before key lookup. No production
limit values are assigned.

Claude 2.1.290 has a separately gated native MCP bridge. Only Mortimer's existing
validated agent tool loop executes operations; request-bound IPC returns its
results and mandatory system constraints to the provider runtime. Passing
public-fixture receipts cover exact runtime/schema/protocol identities,
isolation, unadvertised-tool refusal and cleanup. They do not enable the actual
Developer registry. Codex 0.160.0 has a matching text-only no-tools proof; a
three-case public research diagnostic passed all scored cases (median 3.9 s,
three samples, no stable-p95 claim). Previous direct-API and Claude diagnostics
failed the strict JSON-format gate, leaving their content unscored. Those
receipts cannot establish a quality comparison with the newer Codex harness.

**Latest prerequisite gates, 2026-10-06:** Code head `408bc6f` passes all five GitHub checks: 6,214 unit passes plus two subtests / 11 skips, 196 integration passes / four skips and 13 eval passes. The reviewed diagnostic repair also passes 146 focused, 386 affected (three existing skips) and 31 independent cases. Actual synthetic localhost-only validation passes all 40 schemas, one guarded reference read, mutation/Bash refusals and all four cleanup owners. This remains partial evidence, with every full provider/quality/billing/rollout acceptance flag false. Default CLI `2.1.291` is unverified; the local proof uses SHA-matching `2.1.290`. Exact REPO_MAP→Claude approval, operator-issued identity, manual-source authority, native-readiness scope/main claim, compliant confidential route, Claude cross-review and account/deployed acceptance remain open. Standard all12 is terminal 11/1 at `a653289`; VMs stopped and production unchanged. See [wire/local/CI evidence](../acceptance/model-use-enhancements/receipts/mar-native-api-wire-order-2026-10-06.json).

**Frozen CI and unit evidence, 2026-10-06:** Published `963ed85` passes all five GitHub checks; later candidate heads require their own checks. Its frozen Mac unit run records **5,916 passes plus two subtests / three skips / one previously reproduced audio-default failure** (101.69 seconds); this does not establish a green deployment gate. The storage/admission repair is independently reviewed, and its [receipt](../acceptance/model-use-enhancements/receipts/mar-storage-admission-lifecycle-2026-10-06.json) preserves earlier failures and the new exact-head result.

The standard immutable-image preparation and registration now succeed from `fd41f30`, producing image `9e71cb3f07c046fb9d0e84c3980134bfbf0372b8628c4b15e271cd15c7aa4c6a` without changing the production profile pointer. Bounded offline checks prove shared-input write refusal and read-only synthetic DB integrity; the task and template are stopped. Normal clone/hydration worker and desktop preflight now pass ([receipt](../acceptance/model-use-enhancements/receipts/mar-standard-worker-isolation-2026-10-06.json)). All 12 development checks completed on frozen `4e225f3`: ten passed, while both Python suites failed on the same three missing-English-tokenizer observer cases. Baseline and candidate were identical; this is a failed pre-edit baseline, not model quality or acceptance. Both owned tasks are stopped ([terminal receipt](../acceptance/model-use-enhancements/receipts/mar-full-sandbox-baseline-2026-10-06.json)). Observed guest IPv6 unreachability is not a general network-policy proof. [Image receipt](../acceptance/model-use-enhancements/receipts/mar-immutable-image-readiness-2026-10-06.json).

The four-operation Upgrade pilot driver is independently repaired with source-bound oracle/cleanup/route receipts; it remains a preliminary subgate with no live Developer acceptance. The new full40 managed harness now reaches the actual SDK through all40 real MCP schemas, and complete parent success-proof validation is now independently repaired; actual native/VM quality acceptance remains open. The shared boundary's32-schema rejection is repaired to the existing40-tool registry without altering tool permissions or native call limits. A four-operation pass cannot close MAR-I.

**Development/source candidate, 2026-10-06:** UpgradeAgent/AppBuildAgent now snapshot saved choices per run, enforce shared limits from host entry, bind each operation to its actual sandbox owner, and forbid enabled-mode implicit failover. Host issuers authenticate exact snapshot/admitted-write bytes; generated local-only restrictions persist before guest ingress, including lost acknowledgements and unverified derivatives. Creator HTTP results have process-memory Ed25519 receipts tied to the live run/revision/owner/job and one-use challenge; the bot re-seals them before any result sink. The focused committed-code gate passes 572 tests plus 45 subtests. See [the source-bound receipt](../acceptance/model-use-enhancements/receipts/mar-development-source-bridge-2026-10-06.json). These are inert host/transport regression tests, not real VM or native Developer acceptance.

**Open rollout gates:** complete manual advisory/public-crawl proof and representative research
and real sandbox Developer quality; confidential memory pilot; full workload
acceptance of optional limits; exact
running-service capabilities and activation; billing/allowance/paid-overage
settings; voice route-control and deployed rollback acceptance. SAYGM's [10-06 authenticated catalog](../acceptance/model-use-enhancements/receipts/model-access-catalog-readiness-2026-10-06.json) still contains 64 models and zero advertised confidential models. Local runtime is still a placeholder. Direct OpenAI API access is not
configured in the authoritative endpoint registry. Production global routing
must remain unchanged while its private workloads lack compliant routes.

**Historical reconciliation, 2026-09-22 at main `88b206f`.** At that ref, this header and
[the status file](../acceptance/model-use-enhancements/STATUS.md) agreed
on the then-committed receipts. Later dated evidence above supersedes these readiness results. MAR-E and MAR-F remain **open**. The
then-only committed SAYGM receipt (`saygm-readiness-2026-09-20.json`) failed
closed with `SAYGM_API_KEY is not set`. The only committed subscription
probe receipts (`subscription-probes-2026-09-20.md`,
`subscription-readiness-2026-09-20.json`) record Codex returning
`SUBSCRIPTION_PROBE_OK` and Claude `Not logged in`. The status file also
describes a Claude login and successful probe on 2026-09-21 and a SAYGM
catalog with 56 models on 2026-09-22. Those are user-reported, not in a
committed receipt, and unverified. The "195" JarvisKit and "250-test"
MortimerHost figures above are the static `func test` counts at `88b206f`.
No committed receipt records those runs; the newest committed JarvisKit logs
(2026-09-18) record 190/190. Likewise, no committed receipt records the
2,644-test Python run.

The implementation must follow the decisions below. Missing credentials,
unavailable models, or unsupported provider features must produce a documented
blocker—not an improvised architectural change.

Related documents:

- [Roadmap](../../ROADMAP.md)
- [Architecture](../ARCHITECTURE.md)
- [Platform roadmap](MORTIMER_PLATFORM_ROADMAP.md)
- [Gap-closure plan](MORTIMER_GAP_CLOSURE_PLAN.md)
- [Implementation status](../acceptance/IMPLEMENTATION_STATUS.md)
- [Model-use status](../acceptance/model-use-enhancements/STATUS.md)
- [Command Console and Knowledge Atlas plan](MORTIMER_COMMAND_CONSOLE_ATLAS_PLAN.md)
- [Automated-memory plan](MORTIMER_MEMORY_AUTOCONSOLIDATION_PLAN.md)

## Progress

- 2026-10-06 (Codex, terminal current-code CI and remaining-gate audit): Published `408bc6f` passes all five checks; exact logs record 6,214 unit passes plus two subtests / 11 skips, 196 integration passes / four skips and 13 eval passes. The independent remaining-gate audit finds no further in-scope autonomous implementation prerequisite after CI/status reconciliation. Default CLI2.1.291 requires revalidation before use, not automatic allowlist expansion. Required provider/source/identity/native-scope/account/cross-review/deployed acceptance still depend on their named actors; no model, permission, profile, production flag or acceptance gate was changed. [Receipt](../acceptance/model-use-enhancements/receipts/mar-native-api-wire-order-2026-10-06.json).

- 2026-10-06 (Codex, actual sorted API wire and bounded negative proof): Real `2.1.290` traffic advertises the exact 40 unique names and exact schemas in lexical order, while Registry/argv order stays distinct. The diagnostic now binds the sorted wire menu by exact name; its negative fixture emits Bash once, allows one terminal DONE continuation and refuses a third request. Parent proof additionally binds the negative model, canonical distinct session and origin; the preserved original accepts eight invalid bindings, while the repair refuses them and accepts the honest case. All 41 previous test functions and 74 assertions remain. Author 146 focused / 386 affected (three existing skips) and independent 31 cases pass. The actual synthetic localhost-only run passes, publishes an owner-600 partial artifact and verifies all four cleanup owners. All full acceptance flags remain false. Previous code head `60cc5c5` is all-five green; this new slice needs fresh CI. Default CLI `2.1.291`, external authorization, service identity, standard all12 native repair and other human/quality/rollout gates remain open. [Receipt](../acceptance/model-use-enhancements/receipts/mar-native-api-wire-order-2026-10-06.json).

- 2026-10-06 (Codex, Mac diagnostic environment): An actual fresh child added `__CF_USER_TEXT_ENCODING`, which the prior strict boundary rejected. Both diagnostic environments now derive only the exact current-UID Darwin marker; Linux adds none and foreign/malformed values or extra authority still refuse. All 38 previous test functions and 68 assertions are preserved. Author 174 focused / 373 affected cases pass with three existing skips; independent nine repository / eight temporary cases pass. The approved localhost-only retry ends with refusal and no protocol receipt; its child boundary and imports pass, so remaining metadata diagnosis is separate from native compatibility. No external inference or private-document transmission is authorized by these tests. Prior head `8668060` is all-five green; new-head CI and existing live/identity/native-scope/account/rollout gates remain open. [Receipt](../acceptance/model-use-enhancements/receipts/mar-native-diagnostic-macos-environment-2026-10-06.json).

- 2026-10-06 (Codex, diagnostic CI portability/loader repair): Exact Ubuntu CI at `aaedc37` records 6,160 passes/4 failures/8 setup errors/11 skips plus2 subtests. Three failures/eight errors originate before native worker creation because Mac `/private/tmp` is absent; the fourth is the central registry-loader architecture assertion. The default Mac capture parent and every UID/mode/cwd/environment/prefix/resolution guard remain unchanged. Tests use an owned project-receipts anchor and the unchanged atomic publication guard; no global directory, sudo or skip. Actual default/override model source hashes now come from loader metadata, with no filename authority duplicated. Author 364/3 existing migration skips, independent165/3 same skips, and independent absent-parent106/0 skips pass. All36 original test functions preserve65 exact assertions; endpoint-only bytes change the frozen contract. Fresh Ubuntu CI remains required. External document approval/native-readiness scope assignment and other rollout gates remain pending; local-only harness is unexecuted and under review. [Receipt](../acceptance/model-use-enhancements/receipts/mar-native-diagnostic-ci-portability-2026-10-06.json).

- 2026-10-06 (Codex, terminal sandbox stability and permission gates): Standard all12 at `a653289` on pinned `c43cc422…` finishes **11 passed / one failed baseline-native-library check**. Both actual different-UID Python suites pass6,068 plus2 subtests/11 skips; both MortimerHost suites pass493/7 skips/0 failures, and candidate JarvisKit passes226/0. Baseline JarvisKit fails only NativeAudioTransportTests line530 (five pings where more than five is required). Unchanged host code passes normally, fails only that assertion with a controlled650ms scheduler pause, then passes the immediate unpaused inverse; scheduling sensitivity is demonstrated, exact guest delay/runtime regression is unproven. All owned VMs stopped/settings/image unchanged; no test/timing waiver or acceptance. A bounded repair needs Larry main-row/scope assignment before edits. Reviewed native diagnostic `ddfacfa` is pushed; its live action was rejected **before process start** by automatic approval review because private `docs/REPO_MAP.md` lacked exact authorization to send to Claude. Specific approval is pending; no payload was sent and no runtime failure is inferred. Existing service identity/private-memory/billing/cross-review/rollout gates remain. [Receipt](../acceptance/model-use-enhancements/receipts/mar-sandbox-full-profile-stability-2026-10-06.json).

- 2026-10-06 (Codex, exact full-menu native diagnostic): New dry-default script acquires only the pinned named-reference protocol through all40 actual six-MCP schemas, leaving normal tools refusal intact. Actual effective policy/registry/quality/privacy and unsupported provider caps are checked before ingress. Independent review reproduced four original defects in durable bounds, authentic child helpers, cleanup ownership and parent evidence; all four are repaired with unchanged original witnesses/test bodies. Author104 focused/303 affected and independent104 cases pass, no skips. Actual held inert worker proves retained process/readers/lifetime and private quarantine until recovery; no native cleanup is inferred from process wait. Parent checks exact source/schema/native/hook/final-constraint and finite host-bound evidence. Root dry run passes without inference. Exact public live capture remains open; this is no route activation, Developer quality, billing or MAR-I acceptance. Published previous `a653289` now passes all five CI checks; actual all12 rerun has passed both Python suites (6,068 plus2 subtests/11 skips each) but remaining checks are still running. Later heads need fresh CI. [Receipt](../acceptance/model-use-enhancements/receipts/mar-native-full-menu-bootstrap-2026-10-06.json).

- 2026-10-06 (Codex, terminal sandbox and phase/ownership regressions): The actual standard all12 run at `4fd8228` on pinned image `c43cc422…` finished **11 passed checks / one failed baseline-backend check**; candidate Python passed6,058 plus2 subtests/10 skips, while baseline recorded5,999 passes/36 failures/27 errors/6 skips because host-only fixtures entered the unchanged strict reader with admin-owned baseline files. All owned VMs stopped; settings/image unchanged. Test-only private snapshots now preserve original source bytes/scanner checks and all71 prior pilot test bodies; real local Git, foreign-owner and unsafe-mode inverses remain. Author144 and root combined200 cases pass. The two CI deadline cases now expire the real request timeout after confirmed phase entry, retaining separate natural50ms early-expiry coverage and original late-output/spend assertions; independent56 plus2 natural-deadline probes pass. No production guard, timeout, SDK behavior or verification profile changed. Fresh exact-head CI and actual cross-UID all12 rerun remain open. [Terminal receipt](../acceptance/model-use-enhancements/receipts/mar-tokenizer-full-profile-terminal-2026-10-06.json), [fixture receipt](../acceptance/model-use-enhancements/receipts/mar-pilot-fixture-ownership-2026-10-06.json), [deadline receipt](../acceptance/model-use-enhancements/receipts/mar-deadline-confirmed-phases-2026-10-06.json).

- 2026-10-06 (Codex, portable atomic-receipt regression): Actual Ubuntu CI at `7ff27d5` failed the atomic-race fixture before the race because `/private/tmp` was absent. The test now uses pytest-owned temporary ROOT within the existing permitted receipt anchor; the production guard is unchanged. Original body remains byte-identical as an inert witness, with a missing-Mac-directory inverse. Real os.link, competing receipt inode/content/private modes, refusal2 and no-temp-leak assertions remain. Local54 cases pass (7.22s); new Ubuntu CI is not inferred. The same CI has two deadline-phase failures under diagnosis, and actual full12 has a distinct readonly-baseline host-fixture ownership failure; those gates remain open. [Receipt](../acceptance/model-use-enhancements/receipts/mar-receipt-race-portability-2026-10-06.json).

- 2026-10-06 (Codex, exact native menu order): Actual six-MCP discovery reproduces40 identical names with deterministic config/request order differing from manifest membership order. The old full-pilot preflight accepted an inert manifest-name receipt which the actual native client refused. Preflight, runtime recheck and parent native names/argv now bind the exact frozen schema/reference order; manifest remains declaration/set authority and strict receipt validation is unchanged. Author88 and independent121 overlapping cases pass, including actual native-client positives and names/schema-digest/invocation-digest inverses, with original diagnostics retained. No CLI or provider was invoked and no live-looking proof was created. Normal subscription tools remain unapproved; separate pinned named-reference capability acquisition is being implemented under the existing script scope, with developer quality/privacy floors and current static route refusal preserved. [Receipt](../acceptance/model-use-enhancements/receipts/mar-full-native-order-2026-10-06.json).

- 2026-10-06 (Codex, actual tokenizer image and worker): Normal fresh preparation/register at `8042722` produces immutable image `c43cc422…` with recipe SHA `56e71231…`, preserving settings/profile pointers. Normal offline clone/hydration at `4fd8228` proves worker UID502, cold default NLTK3.10.2 lookup in the protected Python prefix, all four official English hashes, actual worker write refusal and the Pipecat sentence helper. The three original RTVI assertions pass unchanged (3.52s); actual worker desktop/Keychain probe passes, then owned task stops. Initial caller pre-allocation path error is retained; no VM or runtime change resulted from that error. Actual unchanged all12 verifier is separately confirmed live (exec8389, primary `f6ccb30d4441`, verification `c11a71ad1cb3`) on frozen `4fd8228`, with identical baseline/candidate; no completion or model quality is inferred. A distinct actual six-MCP audit finds a deterministic manifest/request order mismatch in native40 receipt preflight; its bounded two-file repair and capability capture remain under review. [Receipt](../acceptance/model-use-enhancements/receipts/mar-tokenizer-image-worker-2026-10-06.json).

- 2026-10-06 (Codex, full Developer harness reviewed): The actual six-MCP/40-tool managed pilot driver is independently reviewed at driver SHA `10c26f43…` and test SHA `8f9e4f17…`. Author82 and independent111 overlapping checks pass. Parent success requires exact boolean/status/exit agreement plus backed registry/model/run/principal/session/source/candidate/all12/oracle/holdout/cleanup artifacts. Original public-entry witnesses remain unchanged; their exact inverses now refuse markerless desktop logs, baseline-as-edited verification allocations and unresolved tool-call IDs, while honest backed evidence still passes. This is structural offline/SDK-MockTransport evidence, not actual provider/VM quality. Exact native40 protocol capture, operator-issued identity, real nonempty edit, full12 and independent holdout/rollback remain open. [Receipt](../acceptance/model-use-enhancements/receipts/mar-full-developer-harness-2026-10-06.json).

- 2026-10-06 (Codex, pinned tokenizer recipe): Scope #183 merged green as `4d2a3ce` and was integrated at `24ce2f4` before edits. Fresh image preparation now downloads the official size/SHA-pinned archive, verifies all four English resource hashes, writes only fixed filenames under `.venv/share/nltk_data`, refuses redirects/proxy overrides and proves cold default tokenization before completion. Independent exact-block probes pass17 cases; root hydration/image gates pass11 plus6 subtests, with original assertions retained. No hydration, profile, runtime or voice assertion changed. These are offline recipe/dependency checks; actual fresh image, different-UID worker refusal, unchanged RTVI/full12 checks and Developer quality remain open. Reconciled only stale WS-05 ownership and already-implemented publication/descendant/review wording against source-bound receipts. [Receipt](../acceptance/model-use-enhancements/receipts/mar-tokenizer-recipe-2026-10-06.json).

- 2026-10-06 (Codex, tokenizer scope integrated): Docs-only claim #183 passed all five checks and merged as `4d2a3ce`. Its protected-prefix tokenizer recipe scope is integrated on the WS-05 candidate before code edits. The merge preserves both the main scope restriction and candidate terminal baseline evidence; fresh image preparation and unchanged offline/all12 acceptance remain required.

- 2026-10-06 (Codex, tokenizer-data prerequisite claim): The actual unchanged all12 sandbox baseline on frozen candidate `4e225f3` reproduces three RTVI observer failures. The locked NLTK package is present but English `punkt_tab` data is absent; actual observer tokenization raises LookupError and its worker stops while speech continues. Seven independent offline probes reproduce all three original assertions without data and pass them unchanged with read-only data present, with downloads disabled. Official NLTK index/archive SHA `e57f6418…` independently confirms the four English file hashes. This docs-only claim reserves `sandbox/guest/prepare.sh` before code to install pinned data in the protected Python prefix during fresh image preparation, preserving current hydration and all twelve checks. No voice/RTVI assertions, timing waiver, profile, network/helper, source exclusion, operator authority or production setting changes. A fresh immutable image and actual offline worker/full-profile evidence remain required; the unchanged-source verification is terminal and failed, not accepted.

- 2026-10-06 (Codex, terminal unchanged-source sandbox baseline): The actual standard verifier completed all twelve unmodified checks at `4e225f3` against immutable image `9e71cb3f…`. Ten passed; baseline and candidate Python suites each recorded 5,923 passes plus two subtests / three skips / the same three failing RTVI observer tests. Native, web, knowledge-base, scripted and latency checks passed. Independent seven-case causal/inverse evidence identifies missing English `punkt_tab` data; no observer assertion or code was weakened. Main recipe claim #183 is still open before any recipe edit. Both owned tasks are stopped; settings and image record are unchanged. The receipt remains failed, with no nonempty edit, model pilot or MAR-I acceptance. [Receipt](../acceptance/model-use-enhancements/receipts/mar-full-sandbox-baseline-2026-10-06.json).

- 2026-10-06 (Codex, bounded Developer substrate and full-tool boundary): The actual four-operation Upgrade driver/corpus/oracle are independently repaired, including private-store/SDK lifetime, exact merged parent/child policy, source allocation cleanup, oracle completeness and atomic output/parent identity. Author113 and independent132 overlapping affected cases pass. Shared execution now accepts the installed Developer's40 registered schemas while retaining native call-count, per-schema/argument quotas, permissions, source and budget gates; root229 passes and an independent53-case run exercises actual managed SubAgent/six MCP servers/SDK MockTransport. The new full40 harness remains unaccepted while its parent success-proof validation is repaired. A36-case independent public holdout is frozen outside Git before any model. The subsequent terminal all12 baseline on4e records ten passes and two failed Python checks with the same three observer failures causally tied to missing tokenizer data; recipe scope claim #183 precedes any fix. No live model pilot, publication, production activation or whole MAR-I acceptance. [Receipt](../acceptance/model-use-enhancements/receipts/mar-development-pilot-substrate-2026-10-06.json).

- 2026-10-06 (Codex, actual worker and desktop): Normal `Images.create`/hydration on owned task `fab0158b99aa` proves UID502 `mortimer-dev` and noninteractive sudo refusal. After a restart, the actual worker desktop and disposable Keychain probe passes; owned task is stopped, settings/image unchanged. The first diagnostic invocation omitted its host evidence directory and is retained as a failed observation; correcting the caller directory required no sandbox code/gate change. [Receipt](../acceptance/model-use-enhancements/receipts/mar-standard-worker-isolation-2026-10-06.json). The unchanged all12 verifier ran separately against frozen committed `4e225f3` with identical baseline/candidate, primary `de3a99ae63d2`, actual retained verification child `678b8671a334`, operation55428 / exec27828. Its terminal receipt records ten passed checks and two failed Python checks; both tasks are stopped. This is a pre-edit baseline, not Developer quality or acceptance. Independent36-case public synthetic holdout is frozen outside Git before model execution. Read-only operator readiness finds no existing service-bot credential/principal; A13 human-only minting is preserved and live full40 HTTP/source acceptance remains gated on an operator-issued identity.

- 2026-10-06 (Codex, crawler transport and catalog): Actual inert httpx reproduction proves a response cookie reaches the next site's API request. Each crawl now owns a fresh closed client, pins the endpoint, refuses redirects and ignores process proxy/TLS overrides. Root44 and independent44 overlapping cases pass, preserving existing research bounds/order/digests/scorer, API-off behavior, error taxonomy and confidential unknown pages. This is transport isolation, not public-origin approval or research quality acceptance. Today's authenticated SAYGM catalog read still reports64 models and zero confidential models; no model/subscription call or production change occurred. [Transport receipt](../acceptance/model-use-enhancements/receipts/mar-crawl-transport-isolation-2026-10-06.json); [catalog receipt](../acceptance/model-use-enhancements/receipts/model-access-catalog-readiness-2026-10-06.json).

- 2026-10-06 (Codex, exact-head CI and immutable image): `963ed85` passes all five GitHub checks; frozen Mac unit is 5,916 passes plus two subtests / three skips / the previously reproduced audio-default failure. Standard preparation/register succeeds for immutable image `9e71cb3f…` from `fd41f30`, with settings and both profile pointers unchanged. Actual guest agent works via `/usr/bin/true`; earlier `/bin/true` refusal was a probe-path error. Bounded offline input create refuses with EPERM, synthetic DB quick_check is ok, and both owned VMs are stopped. Standard worker hydration, all 12 checks and full40 Developer acceptance remain open. Four initial pilot defects are repaired; two subsequent model/output receipt defects remain under repair. [Image evidence](../acceptance/model-use-enhancements/receipts/mar-immutable-image-readiness-2026-10-06.json). Roadmap checker reports two pre-existing lifecycle-word errors in Larry-owned WS-10/WS-11; those rows are unchanged.

- 2026-10-06 (Codex, private pilot stores and admission lease): Main claim #182 preceded context-local DB/ledger/preference authority. Owned daemon futures retain full caller context and drain before private cleanup; finite failure retires/quarantines stores and refuses receipt/CLI/comparison success. Original spend assertions pass with a real foreign SQLite writer. Independent45 is clean. Published4dc3dfb CI failed17 deadline/admission cases over1,802s; separate causal probes prove a real double-cancel/loop-shutdown lease leak, with original test bodies copied unchanged. A synchronized worker/caller handoff now compensates late abandoned grants exactly once; independent38/7 and root395 overlapping cases pass. This repairs the reproduced leak, not a claim of the exact historical CI origin or green latest-head CI. Source packaging/clone atfd41f30 now succeeds (1,738 files); preparation remains open after guest-readiness refusal, with settings unchanged. Four independently reproduced Developer prototype defects are being repaired before any live pilot. [Receipt](../acceptance/model-use-enhancements/receipts/mar-storage-admission-lifecycle-2026-10-06.json).

- 2026-10-06 (Codex, exact synthetic-fixture hash repair): Main prerequisite claim #182 merged green as `d5d8cae` and was integrated as `d052314` before edits. Two current reviewed hash pins are refreshed and eight independently reviewed exact path/whole-file SHA pins added. Scanner/source-exclusion AST, historical baseline pins and fixture bodies are unchanged. Actual Candidate/snapshot mutation gates pass48 tests plus48 subtests; changed/moved bytes still refuse and partial output is deleted. The compatible-image retry and actual Developer acceptance remain separate. Pilot context-local storage repair is in progress; the published candidate CI remains live. [Receipt](../acceptance/model-use-enhancements/receipts/mar-reviewed-fixture-hashes-2026-10-06.json).

- 2026-10-06 (Codex, pilot storage authority claim): The published cleanup failure is causally reproduced with actual `jarvis.db.get_conn`: a foreign worker captures the process-global temporary pilot path, then writes after the cleanup directory scan. A fixed sleep, ignored cleanup error or joining only catalog work cannot repair that authority leak. This docs-only scope also claims host-only immutable storage context and the default DB path resolver before edits. Database/ledger/preference selection must be context-local, propagate to owned async workers, retain real worker completion before cleanup, and leave unrelated threads and all legacy/explicit-path behavior unchanged. No DDL, migration, production storage or provider/VM acceptance is introduced. The actual original spend assertions remain required.

- 2026-10-06 (Codex, immutable image source prerequisite claim): Actual image preparation at frozen `9f1e7d5` failed before VM boot on a source scanner refusal. A complete inventory of1,729 source-permitted Git blobs found13 matches in10 files; independent purpose/history review identified only synthetic redaction/scanner fixtures. Three inert probes reproduce the unchanged snapshot/Candidate refusals and partial-archive cleanup. This docs-only main claim covers exact reviewed path/SHA-256 fixture pins in `sandbox/artifacts.py` before code. Preserve the scanner, exclusions, historical baseline hashes, fixture bodies and all sandbox gates; no VM/provider/production acceptance is inferred. Candidate #177 remains draft; the real pilot still requires its own immutable image and exact runtime/schema/behavioral evidence.

- 2026-10-06 (Codex, causal planner cancellation test): Published `9f1e7d5` CI cancelled before the request started because a20ms fixture timer raced bootstrap. A frozen original-test probe reproduces that phase mismatch; the implementation correctly returned before-session cancellation. The test now schedules cancellation after the actual fake request yields, retaining every original started/structured-result/no-submit assertion and adding a cleanup witness. Three related cancellation tests pass. Pilot directory cleanup remains under diagnosis and new-head CI must rerun; no provider or VM acceptance. [Receipt](../acceptance/model-use-enhancements/receipts/mar-planner-cancellation-phase-2026-10-06.json).

- 2026-10-06 (Codex, crawler input egress): Reproduced protected URL/focus input entering the actual inert Tavily HTTP boundary before model privacy checks. Host input policy now gates client construction and every request; fresh caller restrictions stop later sites, while acquired unknown pages remain confidential before publication, digest or model use. Root62 and independent61 overlapping cases pass at the recorded source hashes. Published `9f1e7d5` CI has two failures (pilot directory cleanup and planner cancellation phase), being repaired without waivers. Compatible-image preparation task `03d46ae90796` failed at source scanning before VM boot: all13 matches in10 files are synthetic fixtures with stale/missing exact reviewed hashes. Core scanner changes require a separate main scope claim; no exclusions are loosened. Manual approval, public-crawl provenance, representative pilots and rollout remain open. [Receipt](../acceptance/model-use-enhancements/receipts/mar-research-input-egress-2026-10-06.json).

- 2026-10-06 (Codex, full-suite reservation-order repair): Frozen `58b4e21` exposed an actual retry-proof regression: an unsupported retrying SDK consumed an estimated reservation. The original no-reservation assertion remains. Repair `7d74226` shares authoritative dry/atomic admission: read-only preflight checks all inherited pools before construction without schema, UUID, clock or accounting writes; actual retry proof then precedes atomic reservation and its concurrency recheck. Independent223 and root105 overlapping cases pass. Repaired frozen full unit: 5,893 plus two subtests passed / three skips / only the previously reproduced audio-default failure. Final frozen source review passes 90 cases. These results close this bounded regression, not the Mac deployment or rollout gates; new-head CI remains pending. [Receipt](../acceptance/model-use-enhancements/receipts/mar-descendant-review-2026-10-06.json).

- 2026-10-06 (Codex, descendant budgets and acquired review documents): `cc420bf` retains D→planning P→council C and restart-safe complete ancestry. `df80223` coalesces authors into P, keeps council/economy reviewers eligible, checks every inherited bound before client construction and places locked-database validation inside the request timeout. `58b4e21` retains the exact coordinator/cancellation owner and sealed acquired review bytes. Budget independent192, root focused97 / independent27, source422 and installed-MCP2 overlapping cases pass. Thirty-two budget, eight root and ten review cases are new. Corrected causal SQLite and context-mutation probes are preserved unchanged; a prior-placement control reproduces the deadline defect. Frozen full-unit records 5,851 passes plus two subtests / three skips / the prior audio failure and a new retry-proof reservation regression; its bounded repair is in progress with the existing assertion retained. Bounded final source review passes 90 cases; new-head CI remains pending; no acceptance is borrowed from earlier refs. Manual/public-crawl source proof, representative pilots and rollout remain open. [Receipt](../acceptance/model-use-enhancements/receipts/mar-descendant-review-2026-10-06.json).

- 2026-10-06 (Codex, authenticated advisory source/budget transport): Main claim #181 (`ac8eb7a`) is integrated as `cc37241` before edits. Budget `6007479`, source `c091d7e` and Base/Registry/stdio `5da9b47` implement the frozen host-only APIs and separate advisory protocol. Signed preparation protects the accepted floor before execution, exact original root/child locators recover durable authority across processes, and real Developer/Analyst roles remain distinct. Single-mode authoring preserves its planning/frontier floor; original cancellation/event/generation ownership suppresses old publication after replacement and acknowledges even a pending start. Status/choose/save retains exact content and real target ownership; unknown crawl bytes stay confidential. Source501, independent265, budget177, Base/Registry9 and installed-MCP2 groups pass (overlapping counts). All18 registered schemas, including7 advisory tools, are unchanged; all86 sidecar routes retain authentication. Frozen full unit: 5,803 plus2 subtests passed, three skips and only the previously reproduced audio-default failure. Prior published `cc37241` passes all five CI checks; the new head needs its own rerun. Nested council/review planning remains explicitly refused until safe descendant sponsorship is implemented; no silent rewrite or public-data grant. [Receipt](../acceptance/model-use-enhancements/receipts/mar-advisory-source-budget-2026-10-06.json).

- 2026-10-06 (Codex, ordinary source admission/lifecycle repair): Code `50daa8b` closes all six reproduced source-floor/lifecycle counterexamples without altering their test bodies. Host floors refresh at actual file admission and persist to retained jobs; worker/cleanup capabilities pin the real session and refuse foreign replacement before VM work. Actual App Builder caller/parent identity and same-owner fresh-start positives pass. Saved host PR metadata retains its exact repository/commit/candidate, private floor and human-only notice. The frozen affected gate passes 476 tests plus two actual installed-MCP synthetic stdio transports; independent exact-six and targeted-11 reruns also pass (overlapping groups). The auth inventory now covers all 82 routes and explicitly checks all three new POST paths with the original bearer assertion. The frozen full unit run passes 5,738 plus two subtests, with three skips and only the previously reproduced audio-default failure; the auth inventory failure is closed. Latest-head CI still needs publication/rerun. Manual advisory/research source proof and actual VM/provider/deployment acceptance remain open. The checker still reports other-owned WS-10/WS-11 lifecycle wording, which this slice does not edit. [Receipt](../acceptance/model-use-enhancements/receipts/mar-ordinary-workspace-sources-2026-10-06.json).

- 2026-10-06 (Codex, ordinary authenticated workspace sources): Candidate `3a2fb5d` adds the reserved separate workspace protocol and hidden MCP metadata through installed self-edit/app modules. Authenticated host association, exact live/retained owner/session/run, pinned signer, one-use preparation/challenge and byte-bound receipts precede result sinks; provider arguments cannot supply approval. Restriction-only journals protect no-write private goals across later turns, and a reproduced dangling-ancestor bypass is fixed with the independent test body preserved. Existing handlers thread the policy of their actual acquired plan bytes. The frozen focused source/creator/legacy/advisory group passes 434 cases plus two actual MCP stdio/loopback synthetic transports. A frozen full unit run passes 5,721 plus two subtests, with three skips and two failures: the previously reproduced audio-default issue and the new three-route inventory count (79 versus 82), which is being corrected with its auth assertion intact. Manual advisory/research source proof, stored publication URL parity, full CI and live provider/VM/deployment remain separate gates. [Receipt](../acceptance/model-use-enhancements/receipts/mar-ordinary-workspace-sources-2026-10-06.json).

- 2026-10-06 (Codex, council ownership and deadline CI repairs): Budget `8d73966`, common execution/Upgrade `db3b19e` and council/replay/test integration `e13fbf1` implement sealed host-only sponsorship under the existing reserved costs schema. Atomic membership debits one estimated attempt against both scopes without duplicating observed usage; failed/cancelled reservations, earlier absolute expiry and stricter resumed bounds remain authoritative. Planning authors retain the planning floor, advisers retain council tiers, sponsored shadow work stays inline and detached standalone work preserves tenant context. Enabled replay protects unknown stored bytes and checks owner before reading payloads; JSON cannot make private source public. Association now preflights expiry before creating a coroutine, and the five failing CI cases use causal phase/expiry tests. The frozen suite passes 317 cases. Current full CI must rerun; no real provider/VM/account/production action or complete rollout claim is made. Manual admin input and crawled research provenance remain an explicit integration gate. [Receipt](../acceptance/model-use-enhancements/receipts/mar-council-child-budgets-2026-10-06.json).

- 2026-10-06 (Codex, full-file parity and proposal sources): Candidate `7baa962` replaces the generic 16 KiB edit limit with per-tool canonical transport bounds covering the existing editor ceilings, Unicode/control escaping, diffs and bounded rationale metadata. Current schemas still gate history and new/streamed calls before provider/tool events; unrelated tool quotas stay unchanged. The focused execution/source/native-gateway gate passes 170 tests with inert transports. Proposal source repair `c69edc4` authenticates the exact host-generated patch and approval-required notice, observes private baselines before guest write admission, and preserves that floor through copied derivatives and later reads; its related group passes 95 tests plus one separately permitted Unix transport. These overlapping groups are not a combined total and make no provider/VM/deployment claim. Scope #180 merged as `4a2d4aa` and is integrated before council/MCP execution edits. Latest #177 CI at `f6422a0` reports five deadline cases failing with 5,575 passes and three skips; those failures are being corrected, so the candidate is not CI-green. [Large-edit receipt](../acceptance/model-use-enhancements/receipts/mar-large-edit-parity-2026-10-06.json).

- 2026-10-06 (Codex, concurrent stateless native cleanup): Independent actual SubAgent/execute_chat/admission probes showed that a queued or active call could reuse a real text client after its other call failed cleanup. Candidate `5c50385` retains the completion owner's quarantine, rechecks the client after admission, blocks launch after a Codex capability-worker wait, and suppresses late active output before usage/message/event publication. The four independent probes are copied unchanged into the repo; seven additional wrapper/worker regressions keep normal authentication failures separate. The frozen focused suite passes 282 tests with two deprecation warnings. Initial local Unix-socket denial was environmental; all three transports and the complete rerun pass with socket permission. This makes no provider, VM, account or production acceptance claim. [Receipt](../acceptance/model-use-enhancements/receipts/mar-native-text-quarantine-2026-10-06.json).

- 2026-10-06 (Codex, development and authenticated creator sources): Scope #179 merged as `fb3e1aa` before edits. Candidate code `8902693` includes per-run Upgrade/AppBuild preferences, shared limits with host-entry deadlines and no enabled implicit failover; actual Runtime/Session/File proofs preserve registered project code and named architecture files without approving unknown/foreign baselines or logs. Source policy is saved before write ingress and stays monotonic through lost acknowledgements and copied derivatives. Owner/task/ref and baseline checks now run before guest RPC, as well as after it. Creator receipts bind authenticated owner/session/request/run/revision/job, exact tool/args/content and one-use challenge to a process-memory Ed25519 signer and host-pinned public anchor. Actual native parent cleanup and stateless typed cleanup failures retain quarantine. The frozen focused gate passes 572 tests and 45 subtests with three existing deprecation warnings. Independent inert source probes found no remaining blocker in these facets. No provider, VM or production action was performed. Capped council child budgets, ordinary MCP source integration, 16 KiB typed argument versus larger legacy edit parity, exact real Developer capability and live rollout remain open. [Receipt](../acceptance/model-use-enhancements/receipts/mar-development-source-bridge-2026-10-06.json).

- 2026-10-06 (Codex, Linux cancellation-test scheduling): PR #177 at `40958a7` passed four checks but Ubuntu validation exposed the caller-cancellation test’s 50 zero-delay tick assumption while admission performs worker-thread work. It now waits up to two seconds for the actual outbound phase with 1 ms polling; provider cancellation, one terminal event and released capacity assertions are unchanged. All 56 execution/limit tests and 20 repeated cancellation runs pass. This changes the test’s synchronization, not provider timing or production limits. The broader candidate gates and development-source work remain open.

- 2026-10-06 (Codex, per-run agent and execution integration): Reproduced ignored saved selections, stale credential reuse and startup refusal that survived repair; per-run route snapshots now honor confirmed choices without mutating concurrent model state, rebuild API clients for rotated keys, and retain native owners/quarantine through named preflight. Unreadable preferences and a disabled routed agent refuse instead of selecting a fallback. Host source envelopes are checked before all agent result sinks; raw/custom results cannot approve themselves. Parent deadlines cover queueing, run association and tools; optional output and configured-price spend bounds are enforced before outbound calls, including failed/cancelled reservation retention, unknown-price refusal and supported-SDK zero-retry proof. The focused agent/execution/delegate suite passes 260 cases. Source handling separately passes 176 tests; legacy identity handling passes 298 with three unchanged historical skips. These are candidate results, not deployment or real Developer acceptance. The wider unit audit reports 5,405 passes, three skips and the same pre-existing audio-default failure; the final independent boundary suite passes 115 cases. Integration/evals finish at 173 passes, four skips and the same four baseline inventory failures after 50 council integration tests pass with distinct synthetic model IDs. See [the source-bound receipt](../acceptance/model-use-enhancements/receipts/mar-bdg-runtime-integration-2026-10-06.json).

- 2026-10-06 (Codex, host-result and workload-limit contracts): Added frozen host execution scopes and HMAC-bound result envelopes that authenticate parent/task/tool-call/arguments/content/source policy, while keeping scope keys and provenance out of provider messages. Tampering, replay, forged JSON labels and repr-hook objects are refused; unknown primitive results inherit confidential policy. New and existing privacy/execution tests pass 115 cases. Optional immutable workload limits validate and snapshot nullable output/deadline/estimated-spend fields; related route tests pass 72 cases. These are contract pieces, not completed registry/execution enforcement or rollout acceptance; no production values are set.

- 2026-10-06 (Codex, next independent slice): Candidate #177 at `2992183` now passes all five CI checks. Docs claim #178 reserves optional output/deadline/configured-price task-spend keys and extends the bounded host source, early MCP log and legacy canonical-identity paths; those new paths stay untouched until the claim merges on main. A no-provider source audit proves nonfinancial unknown content reaches early registry error logging and subsequent agent/model sinks. Existing source-policy helpers and workload-limit contract paths are already claimed; no production values are assigned.

- 2026-10-06 (Codex, final candidate review): Independent regressions corrected ambiguous duplicate native calls, altered argument/history bindings, required PostToolUse system constraints, Unicode packet framing and invalid-UTF8 child cleanup. Unverified native cleanup now retains the owner and quarantines that client; active/queued or receipt-validation-wait requests cannot publish or start a new session after quarantine. The final focused subscription/agent/execution suite passes 243 tests. Broad Mac runs report 5,076 unit passes with one audio-default failure and 186 integration/eval passes with four function-inventory failures; unchanged main reproduces the same one/four failures. Nine detached-checkout policy tests, 226 JarvisKit tests and ten native route-control tests pass. The broader native capture failure also reproduces on unchanged main. These results do not claim a green full Mac deployment gate or complete WS-05 rollout.

- 2026-10-05 (Codex, MAR-B/D/E/F/H/I candidate): Route configuration cannot redefine native/local privacy or redirect authoritative API credentials; SAYGM catalog calls refuse redirects and use the exact catalog model, tier and advertised capabilities. Saved choices retain the static workload privacy/quality floors. Native controls preserve unavailable saved selections and bind confirmation to the exact current draft. Enabled historical-memory replay and review settlement now cross the shared confidential execution boundary, and late-delivery/settlement logs omit exception content and memory keys. Native subscription receipts and the bounded pilot harness are committed as scoped evidence, with account billing, complete source-policy coverage and representative Developer/private-memory acceptance explicitly open. No production activation or paid fallback was added. The ten native route-control tests pass; a protected-window capture failure also reproduces against unchanged main, so the deployment gate is not claimed green.

- 2026-10-05 (Codex, prospective MAR-A API metadata): On the isolated WS-05 branch claimed through #175 (`66198c5`) and audit extension #176 (`0b6723c`), the existing API factory now measures completed non-streaming calls while preserving client/response identity and arguments. Existing accounting remains its single owner; trusted local metadata supplies adapter route/billing and duration without saving content or relabeling old rows. Forty-one factory/ledger regressions pass, including actual one-row persistence, cache-control, cancellation and provider-extra spoof refusal. See [the offline receipt](../acceptance/model-use-enhancements/receipts/mar-a-prospective-api-attribution-2026-10-05.json). This is candidate code, not deployed evidence. Streaming/voice measurements, actual account billing and representative quality remain open; no production route or provider credential changed.


- 2026-10-02 (Codex, MAR-F Claude recheck): After Larry's sign-in, `/opt/homebrew/bin/claude` 2.1.278 reported Claude Max and completed a fixed public `claude-sonnet-5` prompt; the isolated Mortimer adapter returned the expected token as well. The older `~/.local/bin/claude` remained signed out. Installed bot/admin launch-agent `PATH` resolves Homebrew Claude and `.env` defines no override, but running process environment was not inspected. See the [recheck receipt](../acceptance/model-use-enhancements/receipts/mar-f-claude-subscription-recheck-2026-10-02.json). This clears the candidate text-authentication probe only; routing remains disabled and capability, billing, representative workload, privacy, and rollback gates remain open.

- 2026-10-02 (Codex, merged evidence handoff): MAR-A baseline PR #165 merged as `ecdf3a3` with all five checks passing, and MAR-E/F live-readiness PR #166 merged as `1ada011` after all five checks passed. The workstream remains in progress but has no active unmerged Codex branch; the next scoped slice must be claimed on main before implementation. Claude CLI reauthentication is a live user step; route activation remains gated.

- 2026-10-02 (Codex, MAR-E/F live readiness): On merged main `ecdf3a3`, the Mac vault-backed SAYGM catalog request succeeded with 64 models and zero advertised confidential models. Claude CLI 2.1.278 reported a signed-in Max account but both the isolated Mortimer adapter probe and a direct public-prompt CLI probe failed authentication (HTTP 401 on the direct call). Codex CLI 0.158.0-alpha.2.1 reported ChatGPT sign-in; its Mortimer adapter deliberately returned `gated` because no-tools runtime capability is not yet verified. See the [secret-free receipt](../acceptance/model-use-enhancements/receipts/model-access-live-readiness-2026-10-02.json). No route was enabled or production configuration changed.

- 2026-10-02 (Codex, MAR-A baseline refresh): The installed Mac remains on deployed `ae70f2c` while main is `bd41b5e`. Current launchd bot/admin/extractor/costs/vault PIDs match the clean deployment receipt; a read-only `ps` executable-name check confirms the production venv processes. The production checkout has zero tracked edits and five untracked entries. The routing flag and model-access override are absent from the sourced `.env` and launch-agent environment, but the running process environment itself was not inspected. Production and merged candidate each pass the Python 3.12 call-site audit at 28/28. The read-only ledger window since deployment contains 15 provider calls (8 LLM), with zero populated route, billing-source, or model-duration fields; one completed supervisor run is not a quality score. No provider call or production write was made during this aggregate baseline capture. See [`mar-a-baseline-refresh-2026-10-02.json`](../acceptance/model-use-enhancements/receipts/mar-a-baseline-refresh-2026-10-02.json). MAR-A remains open for representative quality/latency evidence, effective-routing verification, and production route/billing attribution.

- 2026-10-02 (Codex, MAR-A synthetic direct-API smoke): Ten public, tool-free, capped calls through the provider-neutral execution boundary produced exact expected outputs in five Haiku voice-supervisor and five Sonnet analyst fixtures. Median call durations were 508.3 ms and 994.0 ms; nearest-rank p95 is the sample maximum (617.0 ms and 1184.3 ms) with only five calls per model. The [receipt](../acceptance/model-use-enhancements/receipts/mar-a-synthetic-direct-api-2026-10-02.json) records route/billing metadata and token counts but no response text or credential. This is a narrow instruction-following and latency smoke, not representative workload quality or production route/billing attribution. MAR-A remains open.

- 2026-10-02 (Codex, bounded test-stability fix, PR #162 merged as `30ac2c7`): The model-admission priority test now waits up to two seconds for the interactive waiter registered on a worker thread, polling at 1 ms intervals instead of assuming 20 zero-delay event-loop turns suffice. Its existing capacity and priority assertions remain. Thirty focused iterations and all 38 tests in `tests/unit/test_model_execution.py` passed locally; all five PR checks passed. This is a test-only change; MAR-A live route/capability evidence and rollout remain open.

- 2026-10-02 (Codex, bounded test stability claim): Larry reported an intermittent failure in `test_background_admission_reserves_capacity_and_prioritizes_interactive`. The test waits at most 20 `asyncio.sleep(0)` turns for an interactive waiter registered by `_acquire` on a worker thread. Codex will replace that scheduling assumption with a deadline-based wait in `tests/unit/test_model_execution.py`, without changing `ModelAdmissionController` or route policy. The 10-02 baseline test passed eight local repeats, which does not disprove the reported approximately one-in-four failure. This is separate from MAR-A rollout and makes no live acceptance claim.

### Bounded contracts and remaining acceptance — 2026-10-06

The implemented contracts below retain their stated invariants. Passing candidate tests do not waive the remaining live acceptance gates:

- **Research input egress (frozen, 2026-10-06):** Reproduced actual authenticated advisory input marked `local_only` or `confidential` constructing the real Tavily client and sending its original URL/focus before the model privacy refusal. In enabled mode, the trusted host input floor must permit the fixed external crawler route before credential/client creation and again before each HTTP request. Freeze the original input packet; current caller restrictions, budget, cancellation and generation still apply. Acquired-page restrictions must precede every output/model sink, but must not be confused with the distinct original input packet for the second site's independent crawl. No unknown page becomes public from HTTPS, Tavily success, response JSON or bearer authentication. Preserve two-site order, bounds, digests/scorer, API-off behavior and actual privacy refusals. The private reproduction uses SDK `MockTransport`, not a real network or model. Manual request-input authority remains a separate pending decision.

- **Typed source policies (MAR-D/G):** Installed Upgrade/AppBuild and authenticated creator callbacks issue source-bound envelopes before sinks. Ordinary self-edit/app MCP transport and the `50daa8b` admission/lifecycle repairs preserve exact saved repository/PR/commit/candidate metadata, human-only approval notices and private source floors. The frozen ordinary-source gate passes 476 focused cases and two installed-MCP transports; [its receipt](../acceptance/model-use-enhancements/receipts/mar-ordinary-workspace-sources-2026-10-06.json) records the bounded independent ownership/publication checks. Unknown outputs remain confidential. Complete manual/public-crawl source approval and real Developer/lifecycle acceptance remain open. Preserve standing project-code and named-reference grants, foreign/unknown baseline restrictions, source exclusions and routing-off behavior. Access permission and result JSON cannot grant source approval.
- **Council identity (MAR-B/G):** Enabled and legacy loaders/member selection now reject duplicate canonical and physical identities before credential lookup. Review the guard with the actual registry and retain representative enabled-mode council acceptance; judge/proposer independence uses identity, never profile name.
- **Workload limits (MAR-B/C/J):** Execution, SubAgent and Upgrade/AppBuild share optional task bounds, with host-entry deadlines and retained failed/cancelled reservations. Absent/null settings introduce no production ceiling. Candidate `e13fbf1` implements sealed coordinator/child ownership, atomic root-plus-child admission and restart-safe sponsor recovery; the frozen focused/integration suite passes 317 tests. Manual admin plan/research paths still lack trusted input/crawl source proof and must refuse unverified content rather than infer approval from JSON. Estimated prices are not account charge guarantees; no paid fallback on exhaustion.
- **Remaining owned execution loops (MAR-G):** The raw-source, stale-default and implicit-failover defects in UpgradeAgent/AppBuildAgent are corrected in the candidate and tested against actual inert host sandbox facets. Verify the remaining MCP tool loop and cross-family provenance in the real Developer pilot. The bounded large-edit repair at `7baa962` passes 170 focused tests, including actual inert SelfEditService/AppWorkspace boundaries and a Unix transport. Real native Developer acceptance remains separate.
- **Real Developer pilot (MAR-F/I):** Configured Tart 2.37.0 and Softnet pass doctor; cached `mortimer-base` exists. Standard preparation/register produced immutable image `9e71cb3f…` from frozen `fd41f30` with dependency key `c713fb90…`, preserving `settings.json` and both installed profile pointers. Bounded offline probes end with no running VM. The independently repaired four-operation Upgrade driver accepts the image ID explicitly; publication and private screen/runlog/status reads stay excluded. Normal clone/hydration worker and desktop preflight pass; all 12 baseline/candidate profile checks remain required on the actual edited candidate. The unchanged-source all12 baseline has finished with ten passes and two Python failures caused by the same missing-tokenizer prerequisite. The complete 40-tool Developer driver is independently reviewed for parent evidence; its own exact live runtime/schema capability receipt remains missing. A narrower fixture or four-operation receipt cannot authorize the full registry. Use the actual isolated sandbox/MCP driver through the existing permission/draft loop; verify source policy, required constraints, cancellation, cleanup, parent ownership, a nonempty edit, independent holdout quality and rollback. Text-only or no-op mocks cannot establish Developer acceptance.
- **Research and private-memory acceptance (MAR-E/I/J):** Pin the same source/scorer/framework before and after measurements, compare equivalent baseline/candidate cases, and report schema failure separately from factual quality. Source-packet synthesis does not establish full research retrieval. Use a catalog-confirmed compliant route for confidential synthetic memory; current SAYGM catalog offers none. Account allowance/paid-overage and physical/spoken checks remain Larry's gates.
- **Initial advisory audit (historical; implemented by `5da9b47` and the later descendant/review slice below):** Real Developer `plan_start` and Analyst `research_compare_start` calls already have a typed `ToolExecutionScope` in Base/Registry, but their MCP wrappers forward only GL9 `run_id`. Admin records establish owner/session/role; sensitivity can tighten policy but cannot reconstruct an exact `local_only` floor. The minimum next slice is voice author-only planning with an authenticated advisory issuer bound to actual owner/session/run/agent/tool/call/arguments and the original host budget. A preparation must expose a verifiable accepted input floor before any operation, and status must bind the retained action. The workspace/creator contexts must not invent a Developer role for Analyst or grant source authority from a bearer, route, or JSON label. Caller budget sponsorship across processes needs actual retained authority; serialized policy fields are not an allowance. Research crawler transport currently discards effective origin/redirect/credential evidence and trusts returned URL/content; HTTPS or Tavily success alone cannot make acquired bytes public. Unknown crawl data stays confidential. Reserve `mcp_servers/mcp_web/server.py`, `mcp_servers/mcp_web/logic.py`, `jarvis/research/crawl.py` and any new advisory protocol contract on main before edits. No UI, permission or model-pin change is part of that bounded follow-on. Read-only inert audit: 64 passed (advisory10, crawler10, registry44); no provider/VM/production action. The bounded actual-worker cancellation probe also reproduces a cancelled plan overwriting a replacement action when its old completion arrives. Repair with an owning cancellation event and exact owner/session/origin-run/action/generation guard before every state publication, preserving the existing permission/draft workflow. Save/choose/status/adopt must retain the job policy and exact content identity; a raw sandbox write cannot relabel a private derivative.
  - Frozen host-budget entry points: `bind_model_task_budget_for_transport(owner, child_workload, child_limits, *, started_at, now=None) -> ChildTaskBudget` validates the authentic local owner, explicitly persists its root and child link even for all-null limits, and keeps ordinary no-transport defaults unchanged. `recover_model_task_budget_for_transport(workload, parent_request_id, *, scope_id) -> TaskBudget` requires the current tenant, exact durable root and origin, and no incoming parent link. Hidden scope IDs locate existing authority; JSON caps/null flags cannot replace it. Admin recovers the actual Developer/Analyst owner, then resolves the recorded planning/council child against local config. Missing/replaced/foreign authority refuses before execution; stricter resumed bounds and the original execution-entry clock remain authoritative.
  - Implemented at `5da9b47`: signed advisory prepare/execute/cancel, original parent budget, actual-role status/choose/adopt/save and unknown-confidential research transport. The later `cc420bf` / `df80223` / `58b4e21` descendant/review slice supports requested council mode and nonempty review paths with the original Developer→planning→council budget chain, exact acquired-document proof and owning cancellation event. Planning authors reuse the coordinator; reviewers retain council eligibility. Unknown documents remain confidential, and changed source/context or foreign ownership refuses before client creation. The causal cancelled-worker regression joins the actual old worker before checking replacement state. Manual/public-crawl approval, full research/private-memory and real workload acceptance remain separate. [Descendant/review receipt](../acceptance/model-use-enhancements/receipts/mar-descendant-review-2026-10-06.json).
  - Implemented descendant contract at `cc420bf`: `begin_model_descendant_budget(parent: ChildTaskBudget, workload, limits, *, started_at=None, now=None) -> ChildTaskBudget` accepts only an authentic sealed coordinator. The contract retains private HMAC-covered `_ancestors: tuple[TaskBudget, ...] = ()`; keep `.owner` as original Developer D and `.child` as execution leaf. It retains actual sealed D→planning P in the advisory action and passes host-only `coordinator_budget` to `_run_plan_single`/`_run_plan_council` and council helpers. Adviser C links to P, P to D in the existing tables; authors reuse/refine D/P, advisers remain council. Resolve/remaining/reserve validates every unique scope, inherits the earliest deadline and strictest output/spend, and charges one attempt UUID to D/P/C without duplicating observed usage. Omitted/null sponsorship recovers the complete durable chain; cycles, missing/foreign ancestors and conflicting existing D→C refuse without reparenting or fallback. No public context/schema, ledger DDL, model membership/tier/seed/effort or production limit change. The frozen tests cover independent D/P/C ceilings, adviser exhaustion of P, one reservation/three memberships/one observation, retained failed/cancelled reservations, fresh-process omitted/null recovery, ancestry forgery/cycle/replacement refusal, author coalescing and unchanged planning/frontier versus council adviser floors. Review-document approval remains a separate real-source proof; unknown bytes stay confidential.
  - Frozen review-context boundary: host-only `context_source=AdvisorySourceContext` verifies a sealed local acquired-document proof, the exact whole model-visible context, registered repository/file identity and raw byte digest. Council snapshots primitive context before verification and before awaits, and binds that source to the original coordinator budget and cancellation event. Plain `DataPolicy`, JSON privacy labels or path strings cannot approve a review document. Static workload/caller/private floors still join; unverified documents are confidential in enabled mode, while routing-off compatibility remains. The real acquired public review case must retain explicit council/economy reviewer eligibility rather than rewriting it to planning/frontier. No public tool, wire context or permission change.
  - Required bounded tests: two-process all-null/output-only recovery and null-clearing refusal; tenant/root/child identity and replacement; one estimated reservation across processes; actual SDK cancellation before/after admission; cancelled-generation replacement; typed policy retention through choose/status/adopt/save. The temporary cancellation probe passed once while intentionally asserting the earlier defect; the later causal regression closes it. The old probe is reproduction evidence, not acceptance.


## 1. Lock the scope and intended outcome

Mortimer will support three model-access routes:

- **Subscription:** Official Claude and Codex runtimes authenticated through Larry's accounts.
- **Direct/provider API:** Existing Anthropic, OpenRouter, Moonshot, and other configured API routes.
- **SAYGM API:** Confidential inference or upstream-provider routing, explicitly distinguished.

The user will be able to configure the route for each model and override it for
particular workloads.

SAYGM confidential inference will be preferred for sensitive sub-agent work when
the selected model meets quality and capability requirements. Subscriptions will
be preferred for eligible work where their privacy characteristics are acceptable.

**The current Haiku voice supervisor, Deepgram transcription, and ElevenLabs
voice generation remain on their existing routes.** Replacing them is outside
this implementation.

The existing Mac remains the control center. No additional hardware or locally
hosted language model is required.

## 2. Establish the actual deployment baseline before changing routing

The running backend inspected on 2026-09-20 used the installed checkout, while
the release candidate contained newer memory-routing code. Resolve that
discrepancy first. This is a dated observation, not a permanent description of
the deployment.

The implementation must:

- Record the running backend paths, revisions, launch-service configuration, and interface build.
- Inventory every model call site, including background jobs and synchronous clients.
- Identify the release containing the accepted interface and automated-memory changes.
- Consolidate the intended backend changes through the existing release process.
- Confirm that background memory work uses its dedicated profile rather than inheriting the Haiku supervisor setting.
- Capture baseline quality, latency, errors, and usage before introducing new routes.

Do not overwrite local patches or assume the newest-looking interface proves
that the backend is current.

**Completion evidence:** One documented release identity, verified running
service paths, and an inventory mapping every workload to its effective model
and route.

## 3. Separate model identity, access route, and workload policy

Extend the existing model registry rather than creating a competing model list.

A **model record** must contain:

- Stable canonical identity.
- Display name and provider-specific model identifiers.
- Required quality tier.
- Verified capabilities: text, images, tool use, structured output, streaming, and cancellation.
- Available access routes.

An **access-route record** must contain:

- Unique route identifier.
- Adapter type: direct API, SAYGM, Claude subscription, or Codex subscription.
- Authentication reference; never the credential itself.
- Billing source.
- Availability and authentication status.
- For SAYGM, catalog tier and upstream provider.
- Capability-validation results and their date.

A **workload policy** must contain:

- Selected model and route.
- Minimum quality and required capabilities.
- Permitted data destinations and required privacy level.
- Priority, deadline, and queue behavior.
- Explicitly allowed fallback routes.
- Spending limit where applicable.

A model reached through two routes remains **one model identity**, particularly
for council independence.

Existing configured model names must not be silently replaced with whatever a
subscription happens to expose.

## 4. Make route selection deterministic

Use this fixed selection order:

1. Resolve the workload and its policy.
2. Apply an explicit per-task selection, if present.
3. Otherwise apply the workload override, then the model's configured default route.
4. Check privacy, allowed destinations, quality, and capabilities.
5. Check authentication, capacity, and spending limits.
6. Execute, queue, or return a specific unavailable-route status.

An explicit selection that fails validation must remain visible as unavailable.
Do not substitute a different model.

Automatic fallback is disabled by default. An enabled fallback must meet the
same privacy and quality requirements and be explicitly listed in the workload
policy.

**Subscription exhaustion must never silently trigger paid API usage.**

## 5. Implement one execution boundary for all model routes

Introduce a shared execution layer between workloads and provider adapters.
Retain the existing API client behavior behind the direct-API adapter.

The execution layer must accept a standard task containing:

- Workload, task, and parent-request identifiers.
- Selected model and route.
- Instructions, context, attachments, and output requirements.
- Permitted tools.
- Data-policy labels.
- Deadline and cancellation signal.

It must return normalized events for:

- Queued and started.
- Progress and text output.
- Tool requests and results.
- Artifacts.
- Completion, cancellation, and failure.
- Usage, billing source, and timing.

Existing result grouping must use the parent-request identifier so one
development request continues to produce one consolidated result area.

Provider differences belong inside adapters. Agent implementations must not
acquire provider-specific authentication or fallback logic.

Subscription runtimes may manage their own internal reasoning/tool loop, but
**every tool operation must pass through Mortimer's existing permission and
sandbox boundary**. Unrestricted built-in shell, filesystem, network, or
delegation tools must not create an alternate execution path.

If a runtime cannot enforce that boundary for a workload, mark that combination
unsupported.

## 6. Integrate SAYGM with explicit privacy distinctions

Add a SAYGM adapter using its documented interfaces. Discover supported models
and metadata from its catalog.

Store the SAYGM credential in the existing Mac vault. Use separate keys where
different guardrail policies are required.

Expose three distinct route descriptions:

- **SAYGM confidential inference**
- **SAYGM gateway → named upstream provider**
- **SAYGM open-model route → named upstream provider**

Only a catalog-confirmed confidential route may satisfy a confidential-inference
requirement. A `-TEE` suffix alone is insufficient evidence.

Enable and test applicable SAYGM redaction controls; they are documented as off
by default. Redaction is an additional safeguard, not proof that sensitive
content cannot escape. See the [SAYGM privacy model](https://docs.saygm.com/security/privacy/)
and [guardrails](https://docs.saygm.com/platform/guardrails/).

Keep these verification states separate:

- Provider-documented protection.
- Catalog metadata checked.
- Compatibility tested.
- Attestation independently verified.

Never display "attestation verified" unless verification actually occurred.
At the time of this plan, the documented buyer-facing verification interface
was not yet generally available; record that limitation without inventing a
substitute. Recheck the [SAYGM attestation documentation](https://docs.saygm.com/security/attestation/)
during implementation.

SAYGM usage must be recorded as paid API usage against its own credits,
separate from subscription consumption. See [SAYGM billing](https://docs.saygm.com/platform/billing/).

## 7. Integrate subscriptions through official runtimes

Use the official Claude runtime/Agent SDK and Codex SDK or app-server
interfaces. Pin tested versions.

Authentication must use the provider's own sign-in flow. Mortimer must not
collect browser cookies or copy subscription tokens into the project vault.

Subscription processes must have isolated environments so inherited API keys,
endpoint overrides, or provider configuration cannot unintentionally select
paid API access.

For each subscription route:

- Verify the authenticated account and access mode using supported mechanisms.
- Discover or validate available models.
- Confirm tool, image, structured-output, and cancellation support before enabling dependent workloads.
- Surface expired authentication and exhausted allowance distinctly.
- Record unavailable usage-limit information as unknown.
- Disable paid overage where supported and verify the relevant setting before claiming subscription-only operation.

Unavailable exact models remain unavailable. A replacement requires a recorded
model-selection change.

The supported mechanisms and account restrictions must be rechecked during
implementation against the official [Claude guidance](https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan),
[Claude authentication restrictions](https://code.claude.com/docs/en/legal-and-compliance),
and [Codex integration documentation](https://learn.chatgpt.com/docs/codex-sdk).

## 8. Enforce privacy before transmission and on results

Place policy enforcement locally, before every outbound model request and
external tool call.

Use three requirements:

- **Local only:** Content cannot leave the Mac.
- **Confidential inference required:** Content may reach approved confidential inference routes.
- **Approved external processing:** Content may reach specifically permitted external providers.

Determine requirements from workload policy and source metadata. Newly
introduced, unlabeled private documents, memory records, and attachments
default to confidential processing. Public sources can be marked for approved
external processing.

Do not send content to an external model merely to decide whether it is
sensitive. Automated content detection may tighten policy but must not
downgrade it.

When context is combined, retain the strictest applicable restrictions. Tool
results and model outputs inherit the restrictions of their inputs unless an
explicit, tested transformation permits a narrower release.

Apply this to:

- Prompts and conversation history.
- Retrieved memories and documents.
- Images and screenshots.
- Tool arguments and results.
- Council proposals and evaluations.
- Provider-side session history.
- Logs, telemetry, and error reports.

Check new tool results **before** they are fed back into a model. If a tool
retrieves content that the current route cannot receive, stop that continuation
and use only an explicitly permitted route or queue the task.

Secrets remain available only to the tools that need them; they must not enter
model context.

## 9. Preserve the voice supervisor while controlling confidential handoffs

Haiku continues to manage ordinary conversation and delegation.

For confidential sub-agent work:

- Pass an opaque task or document reference where possible.
- Let the authorized sub-agent retrieve the sensitive material directly.
- Return the full result to Mortimer's existing local response/results area.
- Give Haiku a fixed status message such as "The private result is ready," without the protected content.
- Keep that protected result out of subsequent supervisor context and ElevenLabs input unless its policy explicitly permits those destinations.

Existing memory context supplied to the supervisor must be audited and labeled.
Do not silently erase all personalization, and do not claim confidentiality
while restricted memories are still injected into Haiku's prompt.

The UI must distinguish **confidential delegated processing** from **an entirely
private conversation**. Existing speech may already have been processed by
Deepgram and Haiku; the new routing cannot undo that exposure.

This phase changes data handling where required, but does not replace the voice
providers or redesign the voice interaction.

## 10. Apply workload defaults without reducing quality

Configure the initial rollout as follows:

- **Voice supervisor:** Existing Haiku API route.
- **Memory extraction, consolidation, private-document analysis:** Prefer qualified SAYGM confidential models.
- **Librarian and other agents handling private records:** SAYGM confidential routes when their inputs require them.
- **General research and synthesis:** Subscription route where the data policy permits it.
- **Development and application building:** Subscription route for approved project content; confidential route where the project's policy requires it.
- **Scheduler and Systems:** Select by the information involved, not merely the agent's name.
- **Council:** Eligible subscription, SAYGM, and existing API members; each member must satisfy the task's data policy.
- **Vision:** Enable each route only after image-input tests.
- **Deepgram, ElevenLabs, Tavily, and unrelated integrations:** Existing routes remain.

No agent may fall below its existing quality floor.

If a confidential model cannot meet the required quality or capability, report
the workload as unavailable under its current policy. Do not silently send it
to a frontier provider or a weaker model.

## 11. Treat latency as a task-level acceptance criterion

Approximately one additional second for a delegated task is acceptable if
quality and privacy requirements are met. It is not permission to add one
second to every sequential model call without measuring the cumulative effect.

Measure:

- Queue time.
- Time to first useful output.
- Total task completion time.
- Per-call time and number of sequential calls.
- Tool execution time.
- Cancellation time.
- Median and 95th-percentile results.

Initial acceptance targets:

- Show a local acknowledgment or working state within **250 ms** under normal load.
- For short interactive sub-agent tasks, target **no more than one second additional median completion time** against the baseline.
- Flag **more than two seconds additional 95th-percentile delay** for review before changing defaults.
- Evaluate research and development using total completion time and quality, not a universal one-second threshold.
- Queue background memory maintenance behind interactive work without losing pending exchanges.

Benchmark cold starts and warm sessions separately. Do not reuse sessions
across unrelated privacy boundaries to improve timing.

Reserve execution capacity for interactive work. Background jobs must not
exhaust all subscription concurrency or interfere with audio processing on the
16 GB Mac.

## 12. Add controls within the existing console

Extend the current model/settings area. Do not create a replacement console or
remove existing sidecar content.

Provide:

- Model and route selection.
- Workload overrides.
- Privacy requirement and permitted destinations.
- Explicit fallback configuration.
- Authentication, capacity, and route-health status.
- SAYGM credit/cost information and subscription limits when available.
- A connection test using synthetic content.

Show each task's effective model, route, billing source, and privacy status in
its existing result details.

Preserve voice control for selecting configured routes and requesting status.
Route changes made by voice must use the same validation as changes made
visually.

Reuse the existing response window, parent-request grouping, multi-monitor
routing, typography, and Liquid Glass settings. Preserve the orb and its
speaker-state behavior.

## 13. Preserve execution, memory, and failure behavior

The implementation must retain:

- Sandbox isolation and existing tool permissions.
- Current self-edit behavior: work may start after the spoken preview, with the established PR approval boundary.
- Existing automated-memory admission, deduplication, and recovery behavior.
- Persistent pending work across restarts.
- Cancellation and visible progress.
- Existing council identity and self-judging restrictions.

Normalize failures into actionable categories: authentication required,
allowance exhausted, insufficient credit, unsupported model/capability,
privacy-policy mismatch, timeout, provider failure, and cancellation.

Failed or interrupted model calls must not blindly replay tools that may have
already changed state. Reconcile recorded tool execution before resuming.

Sensitive payloads must not be included in ordinary usage logs. Record
identifiers, route decisions, timings, and error categories sufficient to
diagnose problems.

## 14. Implement in gated stages

Each stage should be independently reviewable and reversible. All stages are
open when this plan is recorded; saving the document closes no implementation
or acceptance requirement. Use the `MAR-` identifiers below consistently in
future status updates.

- [ ] **MAR-A — Baseline:** Reconcile deployment, inventory call sites, capture measurements.
- [ ] **MAR-B — Contracts:** Add model/route/workload records and validation. Existing routes retain their behavior.
- [ ] **MAR-C — Execution boundary:** Wrap existing API execution and prove behavioral parity.
- [ ] **MAR-D — Privacy enforcement:** Add input, tool-result, output, and logging controls.
- [ ] **MAR-E — SAYGM:** Add catalog discovery, credentials, compatibility checks, and synthetic tests.
- [ ] **MAR-F — Subscriptions:** Add official runtime adapters and authentication isolation.
- [ ] **MAR-G — Workload integration:** Migrate all non-voice model call sites, including memory and council paths.
- [ ] **MAR-H — Console:** Add configuration, status, and voice-accessible controls.
- [ ] **MAR-I — Pilot:** Enable one research workload, one development workload, and one synthetic confidential-memory workload.
- [ ] **MAR-J — Rollout:** Expand defaults only after the quality, privacy, and latency gates pass.

Do not test production confidential data on an unvalidated route. Do not add
automatic production shadow calls that duplicate private content or charges.

Rollback must preserve privacy restrictions. If the previous software cannot
enforce an active restriction, pause that workload instead of routing it
through an older unrestricted path.

## 15. Require evidence before closing the work

Automated and live acceptance must demonstrate:

- Manual route selection is honored.
- Unavailable models are not silently substituted.
- Subscription calls do not inherit API authentication.
- Exhaustion causes the configured queue/failure behavior without paid fallback.
- Confidential content cannot reach disallowed models through prompts, tools, results, council calls, or logs.
- SAYGM frontier routes are never labeled confidential inference.
- Cancellation, restart recovery, and tool execution remain correct.
- Council members remain independent by canonical model identity.
- Memory work does not fall back to the voice model.
- Existing interface, orb, result grouping, and monitor behavior remain intact.
- Latency and quality meet the workload-specific acceptance criteria.
- The deployed build and effective configuration match the tested release.

Update the existing architecture documentation, roadmap, gap-closure plan, and
implementation status documents with one shared set of item identifiers.
Keep open items at the top and completed items below, with evidence links.

Mortimer's self-edit context and the user-visible architecture view must expose
the same routing rules, configuration ownership, and limitations.

**Completion means the routes are configurable, policy-enforced, tested,
deployed, and documented. An adapter existing in the repository alone does not
close the item.**


## 16. Progress log

### 2026-09-29 — WS-05 MAR-A baseline reconciliation

- Confirmed production deployment receipt and app bundle revision match production checkout `eb24e81`; launch agents report loaded, but current process identity was not independently verifiable.
- Ran the production Python 3.12 model-call-site audit: 28 covered, zero review-required.
- Captured aggregate-only usage/cost totals and workload counts. The ledger has no duration, quality score, or route/billing attribution.
- Added the evidence and limitations to [`mar-a-baseline-2026-09-29.json`](../acceptance/model-use-enhancements/receipts/mar-a-baseline-2026-09-29.json). MAR-A stays open pending a safe, approved measurement method and the missing metrics.
- No provider calls, feature activation, credential changes, prompt/response reads, or production writes.

### 2026-10-06 — Post-merge roadmap reconciliation (Codex)

GitHub and fetched main confirm #177 merged as `c38d895`. The roadmap now places WS-05 with built work whose acceptance remains open. Existing scoped diagnostics and CI evidence retain their exact revisions. The latest recorded production receipt is `bde22bb`, deployed 10-03 16:34 EDT; no deployment was performed. Exact external-payload authorization, operator-issued identity, native-test assignment, manual-source policy, cross-system review recording, runtime capability/workload, account and rollout gates remain open. No full acceptance flag was changed.

### 2026-10-07 — Bounded capability host-fixture repair claim (Codex)

Larry assigned the bounded repair to `test_claude_developer_capability.py` to unblock WS-17 independent verification. The existing `owned_pilot_source` fixture copies the exact frozen test source into new worker-owned, single-link, read-only files through the unchanged source scanner; it does not adopt the administrator-owned baseline. The capability module has not bound this fixture, and the independent `b2e17b4`→`fee4ac0` comparison failed on its baseline (7 failures and 84 setup errors), although every candidate check passed.

The isolated branch is `codex/ws05-capability-fixture-20261007`. Scope is test-fixture binding and directly related regressions only, with the existing fixture helper changed only if necessary. Every production owner/read/link/mode guard, scanner/pin, source byte, baseline snapshot and all twelve profile checks stays intact. No provider call, baseline adoption, account change, production activation or deployment is authorized by this claim. A corrected baseline/reference must be separately reviewed and approved before a new independent comparison; this claim closes no acceptance gate.

### 2026-10-07 — Exact frozen-source capability fixture repair (Codex)

Claim #199 passed all five CI checks and merged as `99993eb`; it was integrated before edits. Frozen repair `a5b6f88` changes two test files only: the existing bounded source fixture adds the named, scanner-approved `docs/REPO_MAP.md`, and capability tests bind both parent and fresh child imports to that exact worker-owned read-only source. All 57 original capability functions/classes are AST-identical, and the helper's sole body change is the named reference. Runtime readers, owner/link/mode guards, source scanners/pins, source bytes, protected baseline and all12 runner/profile fingerprints are unchanged.

The existing local capability suite passed146 before edits. On an exact scratch copy with the repair withheld, the two source/CLI regressions fail and the foreign-owner guard inverse passes; after repair all three pass. The affected capability/development/full-development suites pass293. The full offline Python gate passes6,461 plus2 subtests /7 existing skips /zero failures (230.97s;13 warnings retained). The independent Codex fixture reviewer approves the two-file repair. Fixture teardown verifies exact source fingerprints and no added source files. [Evidence](../acceptance/model-use-enhancements/receipts/mar-capability-owned-fixture-2026-10-07.json).

These are local test results, not an actual different-UID VM retest, provider/runtime acceptance or deployment. The original `b2e17b4`→`fee4ac0` failed comparison remains failed. Before repeating WS-17 verification, review and approve a corrected reference, integrate this repair into the frozen candidate, and use the unchanged all12 verifier. WS-17's required exact-source Claude review remains separate and pending; no new source was sent to Claude in this repair. All broader source/identity/account/activation decisions remain unchanged.

Publication: draft [PR #200](https://github.com/Larryfix71566/jarvis-voice-ai/pull/200) contains the exact reviewed `a5b6f88` test source plus evidence/status only. It is not merged or deployed at publication; CI and corrected-reference approval remain open.


### 2026-10-09 — Parent notifier interference in the dry-child fixture (Codex)

Continuing Larry’s existing bounded assignment on the same claimed
`codex/ws05-capability-fixture-20261007` branch, integrated main `27fd356`
before edits. Larry approved `a5b6f88` for WS-17’s offline comparison and exact
`065d500`/`748b1e5` Claude reviews. Both separate static reviews completed, and
that comparison passed all twelve checks with actual UID 502 and clean owned-VM
shutdown. [Frozen WS-17 evidence](https://github.com/Larryfix71566/jarvis-voice-ai/blob/287b96dde2804682dcf81d74af05d58d37c6fb47/docs/acceptance/command-console/CC7A_REVIEW_AND_VERIFICATION_2026-10-09.md)
retains its source and limitations; it does not turn broader WS-05 live gates
into passes.

Final GitHub CI on WS-17 head `287b96d` failed only the new dry-child test:
6,365 passed / 11 skips / two subtests, but the empty-directory assertion found
unit.db and its SQLite companions. The parent autouse fixture owns unit.db;
the actual child environment uses probe.db. Parent pytest logs show a notifier
poll error, while child exit/exact dry JSON passed. A controlled actual
ReminderNotifier.tick_once reproduced the original failure deterministically
(1 failed in 2.22s). Missing reminders schema is an inference from the source;
CI records only OperationalError.

Frozen follow-up `08c06357267ef1348ec4b64dfdd12b26d4710a50` changes one test
function only. A fresh factory-created sibling directory holds the child cwd
and worker environment. The test forces an actual parent notifier poll under
pytest-owned paths, with fake post=False and no thread or desktop notification,
then keeps the complete original body as an unchanged suffix. Exact dry JSON,
empty child directory, argv and five-second timeout remain. No child file is
ignored; no runtime reader, source scanner/pin, fixture source/helper, protected
baseline, profile check or timeout changed. All other 60 top-level function/class
ASTs and file mode are unchanged.

The same forced poll passes after isolation (1 in 1.66s). Injecting probe.db
inside the actual child directory still fails the original empty-directory
assertion (1 in 3.86s), proving that child writes remain detectable. The focused
capability/development suite initially passed 203 and failed only the existing
restricted socket-bind prerequisite; with local loopback allowed, all 204 pass
in 14.92s. Independent Codex static review approves this bounded fixture change,
without approving a new baseline or executing the reported tests.

[Exact receipt](../acceptance/model-use-enhancements/receipts/mar-capability-notifier-isolation-2026-10-09.json).
Published as separate reviewable [PR #201](https://github.com/Larryfix71566/jarvis-voice-ai/pull/201). Larry’s new baseline/reference
approval remains required before another independent comparison. No new source
was sent to Claude; narrow `065d500`/`748b1e5` authorization excludes this follow-up.
The prior successful VM comparison and failed CI remain separate evidence.
No production/model/account activation or live acceptance changed.


### 2026-10-10 — Merged fixture repair and revised-reference approval (Codex)

[PR #201](https://github.com/Larryfix71566/jarvis-voice-ai/pull/201) merged as
`83d90e86780c726684a295557057741ab7266397` on 2026-10-10 at 18:51:24 EDT.
Its source is `08c06357267ef1348ec4b64dfdd12b26d4710a50`; final head
`de4381c9b4919fc7f6b203692b3ad8a10fcdc4cb` passed all five GitHub checks.
The exact validate run records 6,280 unit passes, 11 skips and two passing
subtests (400.11 seconds), plus 196 integration passes and four skips
(159.04 seconds); eval, latency and frontend gates also passed.

Larry explicitly approved `08c06357267ef1348ec4b64dfdd12b26d4710a50` for
**offline WS-17 verification only** on 10-10. This closes this particular
revised-reference approval prerequisite, not any model/runtime acceptance.
It does not grant a new Claude payload, private-source transfer, provider call,
release, deployment, account setting or production activation. The repaired
reference remains immutable. Relative to its parent `27fd356`, the repair is
one test function only; relative to old `a5b6f88`, the reference also includes
already merged #197, whose six source/test paths match reviewed `065d500`
exactly. No runtime change is introduced by #201.

The WS-17 owner integrated main and froze candidate
`59d57ea3f7eb007a02a17f425accf186a38108c2`; the unchanged twelve-check offline
comparison against approved `08c0635` is **running at this record**, with no
pass or cleanup result yet claimed. WS-17 owns the terminal receipt and its
release/live UI gates. The original all-twelve-check `a5b6f88`→`ce6cde8` pass,
subsequent failing CI and October 9 prerequisite snapshot remain unchanged
in their receipts. [Notifier repair and dated follow-up](../acceptance/model-use-enhancements/receipts/mar-capability-notifier-isolation-2026-10-09.json).

All broader source/identity/native-readiness/account/workload/rollout gates and
acceptance flags retain their prior state; no deployment or live acceptance.

Publication: documentation-only [PR #202](https://github.com/Larryfix71566/jarvis-voice-ai/pull/202) records this dated merged/CI/approval snapshot; it adds no runtime change or terminal WS-17 result.


## 2026-10-20 — Direct-provider retirement dispatch (WS-05)

Larry instructed Codex to proceed with retiring direct OpenAI and Anthropic API usage and migrating to his subscriptions. This extends the existing workstream; it does not create a separate plan or claim that the earlier live gates passed. Source: conversation `01a1573e-ae10-7388-b7c4-e36ff49120e0`.

Implementation sequence: central fail-closed access policy and complete direct-call inventory; explicit subscription workload defaults and truthful aliases; verified Claude/Codex runtime capability integration, including voice/tool handling; offline regression coverage for missing runtime, expiration/quota, cancellation and no API fallback; staged operator readiness and activation only when supported. Deepgram/ElevenLabs speech services remain separate. OpenRouter is separately billed and cannot silently replace a subscription. Private-source and local-only policies remain binding. Do not copy subscription credentials into API clients.

The audit of deployed `b136a2a` observed direct Anthropic voice, developer, analyst and maintenance calls; no direct OpenAI ledger entries. Legacy OpenAI defaults and automatic executor API failover remain to retire. Claude's saved subscription probe succeeds; Codex is absent from the service PATH. These are routing/readiness findings, not invoice or current authentication proof.

Main `fd56e98` roadmap checker reports one unrelated stale WS-17 status (review despite merged #226). Preserve that owner's row; this dispatch does not close its acceptance. Claim branch: `codex/ws05-subscription-retirement-20261020`. Claim-only registration edits ROADMAP and this existing plan; runtime implementation must follow the merged claim.

### 2026-10-20 implementation checkpoint — staged guards, not migration acceptance

Claim #230 merged as `005e2a4`. The candidate adds an opt-in central `JARVIS_LLM_ACCESS_MODE=subscription_only` policy, refusing application-runtime LLM API client construction and legacy paid fallback, including retained/injected API clients at the shared execution boundary. It uses staged subscription workload selections without changing privacy/capability floors, makes the bare Codex alias select the subscription profile, and removes the requirement for an OpenAI-shaped API credential in subscription-only Settings. Screen MCP explicitly inherits the nonsecret billing-policy setting; no skill permission is added. Legacy mode remains the deployed default.

This is NOT a ready production migration: voice construction deliberately refuses in retirement mode until subscription streaming/tools have been implemented and verified. Tool workloads retain existing exact-runtime/receipt checks; protected memory and local-only workloads retain their private-route requirements. No authentication, native capability, quota/overage, or integrated release acceptance is claimed. Installed Claude `2.1.291` and the bundled ChatGPT Codex `0.163.0-alpha.10.2` differ from the pinned verified tool/text runtime versions. The bundled binary is present but absent from Mortimer's service PATH; no path, credential, account or production setting was changed. `scripts/check_subscription_retirement.py` invokes only version inspection and reports activation blocked, never a successful login or model call.

Focused verification: client/configuration/Anthropic protocol group 166 passed; routing/execution/executor/screen/orchestrator group 216 passed (overlapping groups, do not sum). Manifest validation passes for all 15 skills using synthetic placeholder environment values; no credentials were loaded. The initial full unit run had sandbox-local-socket failures and integration failures; see the 10-21 follow-up below for the corrected run. An initial new-test failure was a mock's fabricated instrumentation marker; the corrected fixture exercises the original no-provider-call assertion.

Coordination: acceptance task `01a15094-cfcd-729f-83f0-0301d1c7001c` owns the final integrated release. WS-05's only pipeline edit is the early LLM readiness guard immediately after `settings = runtime.settings` in `build_pipeline`; no delegate/Base/Registry code is changed, and weather, result selection, cancellation/foreground ownership remain untouched. No deployment is underway. Current WS-05 checker ambiguity was corrected by moving the old merged fixture branch from the current `Where` field to historical evidence; only the unrelated WS-17 stale merged-review finding remains on the inspected main.


### 2026-10-21 — Draft #232 repair and bounded integration handoff

The endpoint-contract check now rejects forged routes before reading any environment value, while the billing guard still precedes credential lookup and SDK construction. The screen child receives the nonsecret denial setting through its explicit optional-env declaration; its frozen environment snapshot is updated without adding a credential or tool permission. The policy's environment read is statically traceable. The owned-source test fixture correctly includes the new policy module after it is committed; no fixture inclusion rule, ownership guard or source scanner was weakened.

Offline validation with local test sockets permitted: **6,638 passed, 11 skipped, 2 failed, 2 subtests passed**. One failure was the new retained-route test lacking a synthetic credential before switching modes; that fixture is corrected. The other was the host's inherited `JARVIS_NS_ENABLED` affecting a default-disabled audio test. With that variable removed only in the test process, the complete audio group passes (14 tests). The repaired subscription/endpoint-contract/env-scope/snapshot/audio group then passes **135 tests**. These are follow-up results, not a claim that the full suite was rerun to green. No provider inference or real account credential is needed by these tests. The original sandbox run's socket denials do not represent application regressions. Claim #230 has all five CI checks green; runtime #232 still requires its final-head CI and review.

Read-only runtime identity checks confirm the still-installed Claude Code 2.1.290 binary matches the existing version contract (SHA-256 `b8412a3826b2dc8ecb1c0605970c28dea28355de5faa740407dd881acdd40237`). This was a process-local command override and `--version` only, not a service change, login or capability receipt. Default Claude remains 2.1.291 and unverified. The bundled Codex binary is present but its 0.163.0-alpha.10.2 version remains outside the pinned 0.160.0 contract. Authentication, subscription billing and overage settings remain unverified.

**Handoff boundaries:** WS-05 owns `provider_access`, client factories/shims, routing/execution, subscription readiness, related configuration and tests. In `jarvis/bot/pipeline.py`, only the four-line readiness guard immediately following `settings = runtime.settings` in `build_pipeline` is changed. Acceptance may edit `jarvis/agents/delegate.py`, `jarvis/agents/base.py`, and `jarvis/skills/registry.py`; WS-05 has no edits planned there. Preserve both streams' intent on integration. The WS-05 roadmap checker ambiguity is fixed by moving the historical branch out of `Where`. The checker still reports the separate stale WS-17 #226 review status on this main baseline; acceptance owns its correction.

**Remaining implementation/acceptance:** subscription voice streaming, tool continuation, interruption/cancellation and latency; exact-runtime/model/tool-schema receipts for each workload; verified Codex text runtime and capability contract (Codex native tools remain unsupported); account subscription/paid-overage evidence; and an eligible route for confidential/local-only work without weakening source policy. Standalone operator utilities `scripts/check_env.py:model_key_probe`, `scripts/check_keys.py:probe`, `scripts/probe_planner.py:main`, and `scripts/voice_model_bench.py:bench_candidate` now apply the same retirement guard, including when the policy exists only in .env. Key/planner/bench entry points refuse before vault/source reads; check_env suppresses LLM API probes without declaring subscription readiness. Their provider operations were not invoked. The diagnostic-retirement/check-env group passes **50 tests**, including refusal-before-HTTP/SDK/vault and .env-only policy coverage. Legacy diagnostic behavior remains available in legacy mode. Speech stays on separately billed Deepgram/ElevenLabs. OpenRouter is separately billed and is denied as an implicit fallback in subscription-only mode.

Production remains on its existing legacy routing. Do not enable the new mode yet: it intentionally refuses voice startup and unsupported/private workloads. Acceptance task `01a15094-cfcd-729f-83f0-0301d1c7001c` owns the eventual integrated release; WS-05 has no separate deployment in progress or planned. Migration is blocked, not completed. No action was denied by automatic approval review; provider/account/source acceptance has not been attempted under the current no-provider/no-credential-change constraints.


### 2026-10-21 — Buffered subscription voice implementation (continuation)

Integrated current main `3061408` (#231 claim/metadata). The roadmap checker now passes with zero errors/warnings. Added `jarvis/bot/subscription_llm.py`: a Pipecat LLMService over Mortimer's existing Claude native-tool gateway, using the shared model execution/privacy boundary. It publishes complete assistant messages as speech frames; this is **buffered delivery, not verified incremental token streaming**. The pinned gateway explicitly refuses stream=True and its validated invocation/receipt does not include partial-message output. Do not silently broaden that contract or advertise streaming from a buffered response.

The adapter retains exact parent/task tool bindings across Pipecat results, rejects mutated/foreign/incomplete continuations, represents only validated completed tool history as retrospective text for a later native session, and runs tools through the existing Pipecat/Mortimer registered handlers. It drains inference and native sessions on interruption, stop, cancellation and cleanup, retaining failed cleanup as a reuse blocker. It records normalized subscription route/billing once, without emitting duplicate API-attributed usage frames. Unknown token counts remain unknown. Fourteen synthetic tests pass, including real Pipecat dispatcher execution; no provider process is started by those tests.

The service requires a host-owned policy for the **entire** context, including retained memory and tool results. An ordinary current-turn sensitivity boolean is not sufficient. Its default is confidential/refused, and the pipeline supplies no blanket external approval. Voice activation stays blocked until trustworthy per-source voice classification and an eligible private/local route exist. This preserves restrictions rather than relabeling private content. Images and unsupported tool contexts refuse. The pipeline candidate branch now selects this adapter, behind the unchanged unconditional retirement-readiness guard.

**Updated bounded handoff:** in `jarvis/bot/pipeline.py`, WS-05 changes only the early guard in `build_pipeline` and the adjacent-to-existing LLM provider-selection branch around the Google/Anthropic/OpenAI constructors. Acceptance retains all weather, result, interruption/foreground logic plus delegate/Base/Registry files; those three files remain unchanged by WS-05. Final integrated release remains acceptance-owned. No separate deployment.

Codex command discovery now checks an explicit override first, then PATH, then the already-installed ChatGPT app's bundled executable. An explicit unavailable override never falls back. This changes no installed file, credential or service setting and does not relax the pinned version/capability receipt. Read-only status commands with a credential-stripped environment report Codex `logged in using ChatGPT`. The first sandboxed Claude check returned `loggedIn=false`; a status-only repeat outside the sandbox confirms both installed Claude 2.1.290 and 2.1.291 report `loggedIn=true`, `authMethod=claude.ai`, `subscriptionType=max`. This corrects a sandbox Keychain-access artifact, not an account change. No new sign-in is indicated. These checks do not verify allowance, invoice cost or paid-overage settings. No identity/email/token fields were retained. The current bundled Codex version remains unverified for the pinned no-tool contract.

The minimum **future** live-test approval is specific: authorize bounded synthetic-only requests through official Claude Code (voice/tool model and exact synthetic schema) and Codex (gpt-6-astra text-only), consuming subscription quota with possible account overage exposure if enabled; direct API/OpenRouter fallback remains prohibited. Claude Max and Codex ChatGPT login metadata are confirmed; account allowance/overage must be confirmed separately. Do not ask for a redundant sign-in based on the sandbox-only result. No real conversation, repo, memory, file, clipboard or private tool result is included in that proposed proof. Production voice context/private-source routing and latency acceptance remain separate gates; synthetic approval cannot authorize those payloads. Current restrictions still prohibit provider inference, so none has been attempted.

The alternative implemented here is buffered Claude subscription speech plus host-executed tools, subject to latency acceptance. A later incremental-streaming contract needs exact-runtime evidence and matching receipts. Codex remains a text-role option; no unsupported Codex tool/voice capability is claimed. Full clean offline validation and final-head CI are next.


Compatibility follow-up: controller CI on `544bf7f` correctly rejected a changed
hash-pinned historical status test. Restored that test byte-for-byte; no pin,
scanner exemption or fixture hash was changed. Kept `provider_command`'s
configured-name contract and added `resolve_provider_executable` for PATH/bundle
selection, used by runtime identity, status installation checks and readiness.
The status response schema is unchanged. All 160 controller tests pass locally.
The focused status/retirement/voice/runtime group passes 127 tests. A fresh
complete offline suite and final-head CI follow.


The intermediate full-suite run exposed the new voice execution site's missing
static ownership-map entry; it is now explicitly classified as a gated native
voice candidate in `scripts/audit_model_call_sites.py`, without weakening the
inventory assertion. That run also inherited audio enablement during collection
and overlapped the resolver repair, so it is not final-head evidence. The clean
rerun explicitly sets `JARVIS_NS_ENABLED=false` for the test process (tests may
still override it), disables live tests, and freezes the committed candidate.


### 2026-10-21 — Frozen-source verification and exact remaining acceptance

Runtime candidate `763bfe1926e2b9f0ed0279db9a3b0d81b0eadc15` passes the full
clean unit suite: **6,661 passed, 11 skipped, 2 subtests passed** in 206.13 s.
The run used a minimal environment containing only host execution essentials,
`RUN_LIVE=0`, and explicit default-disabled audio/console flags. Test vault and
ledger isolation remained active. Earlier local wiring failures were caused by
inherited production console enablement; a 5 ms deadline test also once expired
before reaching its mock under concurrent suite load. No assertion, deadline,
source scanner, fixture pin or production setting was weakened. The integration
and scripted eval gates are running sequentially; final PR evidence will record
their terminal results and all five final-head CI outcomes.

The minimum proposed human confirmation for later live proof is: authorize one
bounded Claude Code 2.1.290 / Haiku 4.5 synthetic voice-tool session and one Codex
/ gpt-6-astra synthetic text session, each at most 120 seconds with no retries,
only after the applicable runtime capability gates pass. Claude would receive
explicitly reviewed tool schemas with synthetic stub results, plus a synthetic
prompt; Codex receives synthetic text only. No real conversation, memory,
repository file content, clipboard, screen image or private result may be sent.
Subscription quota will be consumed; **paid overage must be confirmed disabled,
or separately approved with an enforceable limit before any request**. Direct
API and OpenRouter fallback remain forbidden. This is the exact future request,
not authorization supplied by this document, and does not establish production
privacy or latency acceptance.

Remaining technical/source gates are concrete: the current Codex binary still
needs its own verified no-tools contract; the native Claude receipt must match
the actual voice model/tool schema and executable; buffered response latency and
interruption need live confirmation. The full voice context contains retained
memory/tool material without comprehensive trusted source labels, so it is
confidential by default. Subscription routes are `approved_external`, and no
eligible local runtime or attested confidential route is configured. A blanket
ordinary-turn approval or an API-compatible URL cannot solve that mismatch.
The implemented alternative is buffered Claude speech with Mortimer-owned tools
for appropriately classified workloads. Protected work must remain unavailable
until an eligible private/local route exists or Larry explicitly approves a
narrow source-policy change. Existing restrictions have not been relaxed.


### 2026-10-21 — Offline runtime proof and voice provenance integration boundary

The final `c8f2e56` candidate passed all five CI checks (validation run
39538458818), with local 6,661 unit / 197 integration / 13 eval passes on its
runtime source `763bfe1`. The following bounded continuation supersedes only
the earlier installed-Codex compatibility blocker, not live/account acceptance.

The existing installed-CLI localhost diagnostic now has a candidate-only mode
that can inspect an unverified version without changing the production gate.
Actual Codex `0.163.0-alpha.10.2` passed both positive and hostile-tool fixtures:
one credential-free request with an empty tool menu completed successfully;
the negative fixture made two requests, explicitly refused the injected
`exec_command`, and left its canary absent. External networking and reads of
the existing Codex/Keychain credential directories were denied by an additional
macOS sandbox, and HOME was an empty temporary directory. No inference or
account request occurred. The exact binary/model/catalog/invocation evidence is
[codex-0163-loopback-capability-2026-10-21.json](../acceptance/model-use-enhancements/receipts/codex-0163-loopback-capability-2026-10-21.json).
This evidence supports adding that exact version to the verified text-runtime
set. Matching receipt and operator gates still apply; no production variable,
route, credential, tool permission, model identity or old fixture was changed.
A future release may change the binary and invalidate this receipt.

Full voice source classification is **unfinished implementation**, not a user
consent switch. The agreed WS-05/WS-17 handoff currently covers only the early
readiness guard and LLM selection. The missing source bindings occur outside
those regions:

- `jarvis/memory.py:render_memory_context` returns one string with facts and
  summary; `pipeline.py` inserts it directly into the system prompt. The
  renderer must return host-owned policy/source metadata alongside the exact
  rendered bytes; historical/unclassified memory remains confidential.
- The accepted user-aggregator boundary and every assistant append need
  immutable source bindings. `SensitiveTurn.clear()` resets the current flag;
  that flag cannot authorize older retained history. Outputs inherit the
  complete input's strictest policy, including local-only restrictions.
- `pipeline.py:adapt_to_pipecat` passes plain results to `result_callback`.
  Trusted tool scope/result policies must survive this boundary before JSON
  conversion and be bound to exact call IDs and result bytes. Model-supplied
  labels are never authority. Delegate/Base/Registry metadata transport needs
  a bounded handoff coordinated with the acceptance owner.
- Clipboard injection, `inject_context`, `inject_late_result`, deferred
  injection and history rewriting/minimization must carry those same bindings.
  A copied, mutated, unbound or stale message must fail closed; compaction must
  preserve the strictest source floor rather than infer approval from text.

The smallest integration dependency is an explicit expanded handoff for those
source-policy-only boundaries (plus directly related regression tests), with
WS-17 retaining weather, foreground/request identity and cancellation behavior.
No such regions were edited in this continuation. This can be implemented
without inference or user declassification once ownership is coordinated.
It would still correctly block memory/private/local-only contexts from the
approved-external subscription route. Supporting those contexts requires an
eligible private/local runtime, a separate product/route decision; removing or
relabeling memory is not assumed. Live synthetic consent, account overage and
external source-review consent remain pending. No generic privacy approval
can substitute for this implementation.


### 2026-10-21 — Confirmed source handoff and implemented context bindings

The parent/acceptance owner confirmed the source-policy-only CX-27 handoff.
The preceding `49033ee` source passed all five CI checks, plus clean local
6,663 unit and 197 integration tests. Its installed-Codex receipt remains
valid; no inference, source review, account setting or activation was performed.

The new `jarvis/voice_sources.py` implements host-only, per-context exact-byte
and object bindings, per-run ContextVar accumulation, immutable classified
text for immediate/late transport, and a monotonic session privacy floor.
Plain JSON labels and copied/unbound/mutated messages cannot authorize egress.
Nested scopes cannot lower their parent's restrictions. Whole-history privacy
survives turn resets, removal, weather minimization and late-result rewriting.
The floor is deliberately conservative until a new session is created.

Pipeline context creation, memory snapshot binding, tool-result delivery,
clipboard/silent/correction/greeting/late injection and neutralizers now retain
source policy. Pipecat's actual assistant/tool materialization is recognized
only against host-retained model/tool identities and exact result bytes.
Base exports configured/acquired source floors through a per-run scope;
Delegate keeps them through immediate and interrupted late returns, preserving
ordinary string-return compatibility outside a tracking scope. Registry is
unchanged. Persisted notices lack authenticated source metadata and receive a
local-only floor on greeting, so persistence cannot silently lower a known
local-only result; no DB schema or existing memory classification was changed.

Real Pipecat projection testing exposed a buffered-adapter continuation defect:
spoken text and per-tool assistant/result pairs are separate messages, unlike
the earlier combined mock. The adapter now validates both exact projections,
then restores only host-retained native metadata. A synthetic full native
continuation plus subsequent turn passes without any provider subprocess.

The focused source/voice/Base/Delegate/weather/foreground/readiness group passes
248 tests. This includes actual SDK materialization, exact result mutation
rejection, acquired local-only Base output, context copying, nested/cancelled
scope isolation, and cancellation followed by typed late delivery. Full frozen
source checks and a separate preview with acceptance `d242ba4` are next; their
terminal results will be recorded on PR #232. No acceptance candidate was
modified. The newly implemented bindings are not permission to send memory,
clipboard, unclassified voice input or protected tool content to subscriptions.
Those inputs still block the approved-external route. Remaining decisions are
eligible private/local routing and bounded synthetic/live account acceptance;
ordinary whole-context approval is not assumed. Production guard remains.


The first full provenance run at `d0f18c3` finished 6,675 passed / one failed:
the clipboard contract requires an explicit `add_messages` in its injector.
The helper had preserved silent-append behavior, but moved that call out of
the checked region. Restored the explicit append with source binding directly
before it, without editing the test. The combined preview `df75f80` of
`d0f18c3` + acceptance `d242ba4` passes 327 focused tests; its one runtime
merge conflict preserves the stop-turn refusal inside the source/runlog scope
before invoking any handler. Two roadmap conflicts preserve WS-05 history and
both handoffs. Acceptance's candidate remains unchanged. Final repaired-head
full local/CI results will be recorded on PR #232.


Repaired source `336c5ca` passes 6,676 clean unit tests. Integration exposed a
separate lifecycle defect: rebuilding a pipeline with the same Runtime tried
to reuse its already-bound context source store. Rebuilds now create fresh
message/call identities while inheriting the original privacy floor; the
single-context ownership check stays enforced. The existing three bot-wiring
assertions are unchanged, and a new regression proves rebuilding cannot erase
a local-only floor or reuse another context's authority.

The pinned Claude Code 2.1.290 also completed a synthetic localhost roundtrip
with all 16 voice tools enabled. Both HTTP requests matched the exact tool
schemas and Haiku 4.5 model; the cost_summary call received a synthetic stub
result only, terminal text matched, and native cleanup was verified. A macOS
sandbox denied external networking and existing credential-file reads, with a
temporary empty HOME and a dummy localhost-only credential. No actual handler,
provider inference or account request ran. See
[claude-voice16-loopback-2026-10-21.json](../acceptance/model-use-enhancements/receipts/claude-voice16-loopback-2026-10-21.json).
This is full-menu protocol evidence, not actual model tool choice, live
latency/quality, billing or an exact production feature-switch receipt. The
first diagnostic attempt stopped at executable lookup because its temporary
selector variable was misspelled; correcting only that variable enabled the
localhost probe. No sign-in, credential change or gate bypass was applied to
production. Runtime/workload live acceptance still requires later consent.


Frozen source `acc0bd1` completed 6,677 unit tests, 197 integration tests and
13 scripted evals successfully. Before finalizing, a separate preview regression
reproduced a materialized-payload gap: modifying adapter output after the first
context classification was not rejected. The adapter now compares its owned
message snapshot against the exact host bindings immediately before execution;
a mismatch refuses before native client construction. The regression fails
without this check and passes with it, alongside the actual public Pipecat
continuation. Original full-run evidence was kept frozen until completion;
only then was this bounded repair applied. Source schemas remain bound by the
existing exact-workload native receipt gate. No source authorization, private
label, runtime/credential gate or production activation was relaxed.

## 2026-10-21 — Selective direct-provider shutdown; preserve explicit OpenRouter

Larry corrected the rollout priority: stop direct OpenAI/Anthropic immediately,
keep OpenRouter available, and continue implementation/merge with existing
checks. At 11:27:52 UTC the bot, extractor, admin, costs, daily-status and vault
launch agents were reversibly disabled and unloaded. All former processes
exited; aggregate-only local ledger verification at 11:29:13 found zero new
calls since shutdown. Native UI remained open. No credential, OpenRouter
configuration or production source changed. This broad temporary stop also
makes OpenRouter unavailable through the stopped services; it is not the final
selective restoration. Detailed process metadata/rollback state stays local.

The original `subscription_only` meaning is retained. New reserved value
`direct_apis_disabled` denies direct/unknown API endpoints and implicit fallback,
while permitting explicitly configured canonical `https://openrouter.ai/api/v1`
requests through the existing validated execution boundary. Endpoint and
provider-label checks precede construction; retained clients recheck their
actual endpoint on every completion. SDK protocol/model branding cannot make a
direct OpenAI/Anthropic request eligible. No workload/profile/default is silently
rewritten to OpenRouter or subscriptions.

OpenRouter completion admission is scoped to the exact already validated
payload and approved-external source policy. The scope is reset after success,
error or cancellation; legacy unclassified clients cannot use it. Existing
private/local-only history checks still refuse before client creation. Native
subscription/local routes retain their existing runtime/source/receipt/operator
gates, and no new account inference is authorized by this mode. Voice stays
blocked until its whole protected context has an eligible route; no memory
removal, redaction-by-assumption or blanket declassification is introduced.
Standalone diagnostics still refuse paid probes. Speech billing is separate.

First focused gate: 119 tests pass, including a real OpenAI SDK with offline
HTTP mock transport, public OpenRouter success, confidential/local-only refusal,
exact-payload binding, endpoint spoof/retarget rejection, retained direct-client
refusal and direct-route refusal with injected clients. Expanded and full gates
are recorded on the revised PR. Prior b1f07a2/794a298 receipts remain historical;
they do not validate this policy change. Acceptance #233 has advanced with
additional host evidence; its owner retains combined verification, merge order
and guarded release/restoration. No service should be enabled before this exact
policy source is deployed and its effective setting verified. Non-inference
services may then be restored independently; protected voice/background work
must remain unavailable rather than buying direct inference or leaking private
data to OpenRouter. External review and bounded synthetic subscription tests
are now approved, but no inference (including review) may run until paid-overage
disabled confirmation is obtained. Login metadata does not establish that gate.

### 2026-10-22 — Other-provider selective-policy correction (WS-05)

Larry clarified that only direct Anthropic and OpenAI APIs are retired. Correct
the OpenRouter-only allow rule using the protected endpoint registry plus the
existing SAYGM endpoint contract. Unknown identities remain refused. Preserve
SAYGM catalog-derived privacy, source floors, exact-payload admission, explicit
routing, authentication and task budget gates. No endpoint/configuration edits,
new calls, fallback, service operations or native/installer changes. WS-17 owns
release integration. Both extra-usage confirmations are recorded and both
bounded live-test allowances are used; this slice is synthetic/offline only.

Implementation: API identity is matched against the fixed protected endpoint
registry, with direct OpenAI/Anthropic labels/domains refused even if relabeled.
SAYGM retains its existing pinned endpoint validator and catalog-derived
confidential route; local-only sources remain refused. Exact request admission
and no implicit fallback remain enforced. Selective SDK transports refuse
redirects, including retained clients whose redirect setting becomes unsafe.
Five new regression cases failed before the repair; the expanded focused
suite passes 243 tests (including existing localhost-only redirect tests).
Full offline gates and final publication CI remain pending. No live provider
requests, account/configuration changes, service restart or installation.

Follow-up verification: the first full run was interrupted after inherited
Pipecat dotenv state blocked synthetic providers (175 failed / 3,699 passed /
11 skipped). `pipecat/runner/run.py:140` was confirmed as the import-time
dotenv caller without loading credentials in that diagnostic. Test-only
`PYTHON_DOTENV_DISABLED=1 RUN_LIVE=0` isolates the installed environment;
76 tests in sampled failing groups then passed. The isolated full run
completed with 6,857 passes, 11 skips, two passing subtests and one genuine
registry single-loader contract failure. Repaired by using the existing
`load_registry_layers(DEFAULT_PROFILES_PATH)` explicitly, preserving protected
path precedence and its validation without a second parser. Expanded focused
verification: 302 passed / three existing prerequisite skips. Final frozen
full verification and publication results are maintained in PR #239. This
is source evidence only; WS-17 retains review/integration/installation and
all runtime/private-route gates. The old interrupted run is not a pass.


## 2026-10-22 — recommendation-only foundation publication claim

Larry authorized publishing the independently reviewed isolated R3 patch as a draft and checking CI, not merging or installing it. Branch `codex/ws05-harness-recommendations-20261022`; claim branch `docs/claim-ws05-harness-20261022`. CX-28 preserves other owners. The native skill, passive status notice, explicit fixed-public-document refresh and safe admission refusal reuse current infrastructure. Exact source artifact SHA256 `32ccb1f8971ff3e8f11030ec502432cb80dae48bbcf8f45e8f3789b31517c2e4`, originally against `574282e5b036a3e4a9e6f76e82c4dc92f61c309a`, will be checked for byte identity after integration with current main.

Plan Library `libfile_502deeb949688191a3c41f02eafadb4c` version2; full isolated handoff `libfile_cd1e8c0339508191b0dd013bba2b0cc9` version1. Three exact Opus Max document reviews completed; final textual amendments self-checked, not fourth-reviewed. Independent code review found no blockers only within the narrowed foundation, human review required. Current evidence238 backend/16 native tests plus five skill matcher cases is source-specific, not live acceptance. Cross-system source review required before merge remains separate.

Universal approval across config writers, durable model identity, runtime ACK and rollback are unimplemented. Harness switching must remain unavailable; selected metadata never proves actual active voice identity. Benchmark, model selection, provider permissions, installation and any later merge remain separate decisions. Existing current-release installation must not wait for this feature. No new plan/row or duplicate skill importer is introduced.


### R3 immutable publication evidence — 2026-10-22

[Source/review receipt](../acceptance/model-use-enhancements/receipts/harness-recommendations-2026-10-22/README.md) records the exact reviewed25-file identity, independent review/dispositions,238 backend/16 native tests and limitations. New main636880e changes no reviewed source. The claim and reviewed implementation are separate drafts; publication is authorized, merging is not. All original provider/acceptance history and checkboxes remain unchanged.


### 2026-10-22 — R4 draft CI correction

Draft #242's initial R3 CI caught frozen Developer menu and skill/auth inventory integration failures. The independently reviewed R4 correction restores exact existing MCP schemas and uses passive `status_models.harness_brief` from `jarvis/status/models.py`. No new MCP tool or permission grant remains; native explicit refresh stays authenticated. Existing capability labels and exact six-skill/88-route assertions are preserved. R4 source SHA256 `d0a42d8adb59e5501d6c108e06ada0b9b6f4632b7f06f2ef5b7c5c5abf680339`; 415 focused tests passed with eight skips, five matcher cases passed. Native source/tests unchanged; prior16 results reused. Independent source review accepts draft correction with merge held for amended-head CI and required cross-system review. Claim #241 is green but unmerged; both drafts stay unmerged. No activation, install, benchmark, model switch or claim of complete approval/runtime enforcement.
