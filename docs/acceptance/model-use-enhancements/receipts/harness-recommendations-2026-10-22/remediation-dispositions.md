# Bounded PR #253 remediation — source candidate

Claim #257 landed as `29440804baf40292d84acbb0798646e67d0c510a`.
Isolated branch: `codex/ws05-harness-remediation-20261022`.
Dependency reconciliation commit: `a3b4107f07e2d8a581cdf304bf172a8fb379eaf0`.
Frozen #242 `d476905057fc29207338721ce9ec2a452cb2085d` and #253
`a568f7dc282fff7436a4527feb7d162a2b021c81` remain unchanged inputs. This
candidate does not authorize landing the broader foundation, installation,
model changes, new provider tests or source transmission to a reviewer.

| Finding | Narrow disposition | Offline evidence |
|---|---|---|
| F1 matching | Add relevant Claude/Codex family names to the harness description; preserve the global matcher and WS-03 implementation. Extend only package examples/fixtures and its revision pin. | Complete enabled-roster matching table includes the two reported requests, Astra, generic briefs, availability, unrelated switching/comparison and combined display switching/comparison. |
| F2 recognition | Recognize supported short numeric Claude IDs; preserve finite families and strict boundaries, including refusal to truncate dotted versions or suffixes into another ID. | Positive/negative ID tables retain unverified eligibility and blocked switching. No live documentation/account check. |
| F3 lost update | Stable process-shared file lock surrounds report read/modify/write; fetch/notice callbacks run outside it. UUID generation binds late notice acknowledgement to its own evidence. No timestamp compare-and-swap. | Separate-process barriers exercise both passive race windows, same timestamps, overlap, failed notice retry and atomic reader visibility. |
| Synthetic fixture isolation | Preserve the real default daily access-status collector while supplying synthetic layers/access/environment/health metadata; deny network, SQLite and subprocess use in the new fixture. | Two identical days remain quiet with no harness cache reads/writes through the legacy daily collector. Existing health checks remain unchanged. |
| A28 cancellation wording | Client timeout/window close does not cancel the synchronous refresh handler. A complete report may publish after the client stops waiting. | No cancellation propagation implemented or claimed; explicit slow-fetch barrier proves another refresh can finish while retrieval waits. |

The F1 matrix explanation is corrected: 0.333 exceeds the 0.30 score
threshold but fails the separate minimum of two shared tokens. The comparative
request fails both gates. Historical PR #253 evidence remains unchanged.

Cache semantics: concurrent refreshes publish in completion order; original
retrieval dates determine freshness. Readers see whole old/new JSON. Existing
schema-2 caches remain readable and gain internal generation metadata on their
first mutation without laundering source dates. A symlink lock is refused.
No-op passive processing retains its generation. Failed notice delivery stays
pending for retry. Delivery is at-least-once: crashes/overlapping workers may
duplicate a notice; no exactly-once guarantee or new notification authority is
claimed. A late acknowledgement cannot replace another generation's evidence.
The lock file stays in the existing status directory and is never unlinked by
normal operation; no migration, config key, endpoint or privilege is added.

Validation uses synthetic documents, selections and notices, temporary files,
an empty inherited environment, disabled dotenv/live tests, and a runner that
rejects external sockets/subprocesses. Spawned workers apply their own I/O
guards. Three negative controls on the unchanged dependency fail for the
intended lost-source, missed-ID and missed-skill assertions. The first runner
attempt produced setup errors because its subprocess denial function was not
compatible with a dependency's type annotation; a class-preserving denial
guard corrected the runner without changing application source.

The final focused run passed 147 tests in 3.81 seconds across
`test_harness_brief`, `test_harness_daily_offline`,
`test_harness_cache_concurrency`, `test_status_daily`,
`test_harness_confirmation`, `test_model_route_contracts` and
`test_status_models`. This includes nine cache concurrency/compatibility
checks. Native skill metadata/pins, the skill-creator structural validator,
diff whitespace and the roadmap checker also passed (zero roadmap errors or
warnings). The three negative controls failed for their intended assertions.
Final independent review identity is recorded with candidate publication.
Prior all-green #242/#257 CI is not CI for this repair. No full
suite, live inference, CLI review, installed service operation or acceptance
checkbox closure occurred. Claude contribution remains unused because the
landed claim explicitly excludes new source transmission. Further source
review, exact-head CI and any later feature merge remain distinct gates.
