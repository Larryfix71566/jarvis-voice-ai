# REA research provenance and preservation

Research date: 2026-10-22
Status: Preserved research; recommendations only. No installation, activation, model change or integration is approved.

This file reproduces the complete body of **REA integration options for Mortimer.docx** (46,457 bytes; retrieved 2026-10-22). All 82 original body paragraphs and 30 hyperlink occurrences are retained. Heading markup and pagination differ; no findings were replaced with a summary. The [original DOCX](REA_INTEGRATION_RESEARCH_2026-10-22.docx) is preserved byte-for-byte, SHA-256 `d57310f50fecaf1ebec459ca3828265b999d05b252b73bc8532fbd6ecd424882`. Its author and last-modifier metadata are blank; private storage identifiers are omitted from this publication.

The [phased Mortimer integration plan](../plans/MORTIMER_REA_INTEGRATION_PLAN.md) adds repository-specific design, gates and ownership boundaries. Research versions and upstream `main` links below are observations from the research date, not installed versions, immutable source pins or proof of compatibility. Exact upstream release/package verification remains a pre-pilot gate. This documentation pass did not execute REA or reproduce upstream benchmarks; no independent review of this plan is claimed.

This location follows `docs/README.md`, which assigns research findings and design feedback to `docs/interface-research/`. Repository inspection used main `f88f5f56d4b34bd35007f964dcc4047318144478`. Runtime configuration and other owners' work were left unchanged. Larry subsequently clarified the intended use as new-app building and authorized feature recreation through Mortimer, and requested an end-of-roadmap plan entry. The linked plan and WS-31 reflect that later direction; the original research below remains unchanged.

---

# REA integration options for Mortimer

Research checked 22 October 2026

## Recommendation

Add no broad REA access to Mortimer's controller now. The best next step, if implementation is later approved, is a narrowly scoped, read-only investigation skill. Use existing source tools first; add a pinned REA static-analysis worker only for questions those tools cannot answer. Graduate to an isolated specialist for authorized binary or runtime investigations after a measured pilot. Keep improvement proposals, code edits, review, approval and deployment in Mortimer's existing supervised development workflow.

The likely project is morluto/rea, formally named Reverse Engineer Anything, published as rea-agents and linked from rea.tools. That is a strong match to “rea reverse engineer anything,” but no specific repository URL was supplied, so identity remains provisional. A surprisingly relevant separate project is dav1dngy/era-agent, which adds a supervised improvement lab around REA. It is useful design research, not sufficiently verified to recommend replacing Mortimer's harness.

## Repository identity and nearby projects

### morluto rea strongest exact match

[morluto/rea](https://github.com/morluto/rea)

[rea.tools/](https://rea.tools/)

The official project connects coding agents to reverse-engineering capabilities through MCP and a CLI. It analyzes native software, JavaScript/Electron, managed code and websites. The agent interprets evidence and can separately implement a feature. REA is not itself a foundation model, a recovered-source guarantee, or a complete application cloner. Its README explicitly warns against treating a similarly named repository or copied README as an official download. Search results contain multiple forks with nearly identical names. Use the official owner, package identity and pinned release, not search ranking.

Sources: [morluto/rea / README.md](https://github.com/morluto/rea/blob/main/README.md)

### ShadowSwaps REA Reconstruction Companion planning and validation skill

[ShadowSwaps/REA-Reconstruction-Companion](https://github.com/ShadowSwaps/REA-Reconstruction-Companion)

A model-independent skill that turns evidence into behavior contracts, requirements, implementation stages and acceptance checks. It can work with supplied evidence rather than automatically acquiring a target. Its portable core does not require a model SDK or paid API. It is MIT licensed. Useful ideas include separating observations from proposed improvements, recording unknowns, and testing one feature slice. Do not auto-install its optional REA integration: the maintainer reported that modifying REA's canonical skill can fail validation and be overwritten by REA setup. Prefer an independent Mortimer-owned skill and reviewed attribution, not patching upstream skill files.

Sources: [ShadowSwaps/REA-Reconstruction-Companion / README.md](https://github.com/ShadowSwaps/REA-Reconstruction-Companion/blob/main/README.md) | [ShadowSwaps/REA-Reconstruction-Companion / LICENSE](https://github.com/ShadowSwaps/REA-Reconstruction-Companion/blob/main/LICENSE) | [morluto/rea/issues/4718](https://github.com/morluto/rea/issues/4718)

### dav1dngy era agent workflow and supervised improvement wrapper

[dav1dngy/era-agent](https://github.com/dav1dngy/era-agent)

ERA means Evolve & Reverse Engineer Anything. It wraps REA with analysis reports, an Electron/browser workbench, review/modify/rebuild workflows, approval and rollback, multiple coding-agent roles, and an Improvement Lab. The project is independent of upstream REA, uses REA 6.4.0, and is MIT licensed. Version 0.2.0 is an unsigned macOS-arm64 development build, not a signed production desktop download. Its README says audit fixes have not received independent re-review.

Its validation matrix is unusually explicit: Claude Code integration is unverified against the real CLI; multi-agent roles use mocked agents; Codex has historical real runs rather than new generation on that revision. Native decompilation quality is unverified despite provider health checks. Improvement Lab ran in a throwaway clone but cannot evaluate apps/studio and has significant run limits. These are reasons to study its isolation, evidence and approval design, not import its control plane wholesale. The small authored benchmarks do not establish performance on arbitrary software.

Sources: [dav1dngy/era-agent](https://github.com/dav1dngy/era-agent) | [dav1dngy/era-agent / docs/SUPPORT_AND_VALIDATION.md](https://github.com/dav1dngy/era-agent/blob/main/docs/SUPPORT_AND_VALIDATION.md)

### mytechnotalent rea a different REA

[mytechnotalent/rea](https://github.com/mytechnotalent/rea)

This is Reverse Engineering Assistant, a Rust-based offline analysis engine with optional API-backed autonomous analysis and an MCP interface. It is not morluto's Node/MCP orchestration project. Its README advertises v7.1.0, many binary/artifact formats, deterministic offline reports, and a 90-turn API-driven analyst mode. The latter does not match a subscription-only default. Its claim that forbidding unsafe Rust makes hostile inputs unable to compromise the host is not a security guarantee; dependency behavior, logic bugs, resource exhaustion and output handling still require review. Treat it as an alternative static-triage candidate only if a fixture comparison demonstrates value.

Sources: [mytechnotalent/rea / README.md](https://github.com/mytechnotalent/rea/blob/main/README.md)

### LaurieWired GhidraMCP narrower alternative

[LaurieWired/GhidraMCP](https://github.com/LaurieWired/GhidraMCP)

An Apache-2.0 Ghidra plugin and Python MCP bridge for decompilation, inventories and analyst annotations. Suitable if the only requirement is existing Ghidra work, not cross-layer web/Electron analysis. The current README describes Ghidra 12.1.4 and a headless route; the releases page still lists older compatibility information. Pin and verify a matching extension/client/engine combination instead of assuming README main equals packaged release. Renaming and annotation features are mutations, so this is not inherently a read-only option.

Sources: [LaurieWired/GhidraMCP / README.md](https://github.com/LaurieWired/GhidraMCP/blob/main/README.md) | [LaurieWired/GhidraMCP/releases](https://github.com/LaurieWired/GhidraMCP/releases)

Other exact-name search results include Noisyxl/REA, a separate workflow repo presenting broad reconstruction claims. Its small repository and prose claims were not enough to establish comparable implementation or validation. It is not a reason to replace the strongest official match. No independent performance ranking of these projects was established.

## What REA can usefully do

Source understanding: When Mortimer's source is available, direct search, language-server/AST tools, tests, dependency graphs and runtime traces should remain the baseline. Decompiling Mortimer's own code would usually throw away useful information. REA becomes relevant for bundled JavaScript/Electron boundaries, source-to-bundle correspondence, packaged artifacts and missing-source components. Its application workflows consume retained graphs, trace selected features and compare versions while preserving unknowns. These are bounded structural observations, not proof of full runtime equivalence.

Sources: [morluto/rea / docs/javascript-application-workflows.md](https://github.com/morluto/rea/blob/main/docs/javascript-application-workflows.md)

Native binaries: REA orchestrates existing engines such as Hopper, Ghidra and IDA for function inventories, disassembly, pseudocode and references. Results depend on the selected provider, target architecture, symbols, compiler and available evidence. It can support understanding an authorized feature or file format; it cannot promise original source recovery or accurate whole-product reconstruction.

Sources: [morluto/rea / docs/native-investigation.md](https://github.com/morluto/rea/blob/main/docs/native-investigation.md)

Web and UI: Passive CDP observation can capture page structure, accessibility information, scripts, resource and event metadata. Static bundle analysis can identify route/endpoint candidates. This reveals client-side behavior, not private backend implementation or business logic that never reaches the client. A screenshot is evidence of one appearance, not an implementation specification. Keep ordinary browser automation in Mortimer's established browser tools; use REA only for a specific investigation.

Sources: [morluto/rea / docs/browser-observation.md](https://github.com/morluto/rea/blob/main/docs/browser-observation.md)

Protocols: Offline HAR/SAZ and supported capture formats can expose recorded requests, responses and payload evidence. The documented offline capture operation does not fetch recorded URLs or start a proxy. This is a useful low-risk first step for debugging Mortimer-owned integrations with sanitized fixtures. It does not authorize intercepting unrelated traffic, installing a root certificate, exposing credentials or defeating TLS protections.

Sources: [morluto/rea / docs/web-network-captures.md](https://github.com/morluto/rea/blob/main/docs/web-network-captures.md)

Self-improvement: REA can supply evidence to a development proposal. It should not own model selection, tool privileges, credential handling, approval decisions or production deployment. Nothing found makes REA a general-purpose self-improvement algorithm. ERA's lab changes its own application code; it does not retrain a foundation model.

## Architecture and operational reality

REA has TypeScript CLI and MCP adapters sharing application workflows, provider/session composition, schema contracts, evidence records and snapshot logic. Native bridges adapt provider APIs; browser and JavaScript layers gather and relate observations. The architecture includes owned-process supervision and bounded resource handling. For Mortimer, use the public CLI/MCP boundary rather than importing internal modules or forking the engine. Internal code and schemas change too rapidly to assume a stable library API.

Sources: [morluto/rea / docs/architecture.mermaid](https://github.com/morluto/rea/blob/main/docs/architecture.mermaid)

The source package manifest currently says 6.7.0, requires Node ^22.19.0, ^24.11.0 or >=26, and lists a substantial dependency graph: Babel parsing, ASAR, MCP client/server, Playwright core, archive/XML/JSON parsers, cryptographic and process utilities, and optional Frida. Native analysis engines are separate prerequisites. Existing compatible Node and static JavaScript analysis are the least complicated starting point; do not install a complete native toolbox preemptively.

Sources: [morluto/rea / package.json](https://github.com/morluto/rea/blob/main/package.json)

GitHub lists 6.7.0 released 18 October 2026. Its notes state 6.6.0 was tagged but not published to npm, illustrating why tags, repository main and installed packages must be distinguished. Recent fixes include configuration-edit semantics and lifecycle/evidence behavior. This is active maintenance, but also integration churn. Popularity and commit volume do not establish correctness. No independent security audit of REA was established in this research.

Sources: [morluto/rea/releases](https://github.com/morluto/rea/releases)

Test infrastructure includes deterministic fixtures and real-toolchain lanes. The client-verification guide explicitly separates native-client tests with a loopback model from real model-service compatibility. A successful MCP initialization or provider doctor result is not an end-to-end acceptance test. Mortimer needs its own pinned fixtures and live, authorized provider trial before relying on a workflow.

Sources: [morluto/rea / docs/testing.md](https://github.com/morluto/rea/blob/main/docs/testing.md) | [morluto/rea / docs/client-verification.md](https://github.com/morluto/rea/blob/main/docs/client-verification.md)

## Security privacy licensing and cost

REA's security policy explicitly states that it is not a sandbox. Its authenticated bridges and private runtime files limit some local exposure but do not protect against malicious processes under the same OS account. Parsing an untrusted binary gives the selected provider that user's privileges. Temporary projects and cleanup controls are useful hygiene, not isolation. Run hostile samples only in an appropriately isolated disposable environment, not your primary Mac account.

Sources: [morluto/rea / SECURITY.md](https://github.com/morluto/rea/blob/main/SECURITY.md)

REA directly executes declared tool requests and does not impose per-call permission grants. Tool annotations describe effects but are not authorization controls. Static JavaScript analysis may launch a parser worker and write temporary files without executing the target app; other tools may execute foreign code or mutate devices/files. Its optional HTTP transport lacks TLS and client authentication. Recommendation: dedicated stdio child process per task, with a Mortimer-owned allowlist and independent OS restrictions; do not expose the HTTP listener to a LAN or the internet.

Sources: [morluto/rea / docs/mcp-contracts.md](https://github.com/morluto/rea/blob/main/docs/mcp-contracts.md)

Treat source, strings, comments, DOM text and analysis output as untrusted evidence, never instructions. Prevent a target from requesting new tools, reading credentials, changing configuration or authorizing a patch. Retain original evidence locally with restrictive permissions; send only relevant, scrubbed excerpts to the chosen coding agent. A local analyzer does not make model reasoning local. Authenticated browser profiles, cookies, capture bodies, logs and source can all contain sensitive data. Redaction requires explicit checking rather than relying on a tool's defaults.

REA-authored code is MIT, but dependencies, derived parsers, native components and external commercial engines retain their terms. Hopper/IDA/JEB access requires legitimate licenses. REA's license grants no rights to proprietary target code or assets. Use targets you own or are authorized to inspect; separate understanding/interoperability work from copying protected implementation or bypassing licensing/authentication. For a reconstruction, define a behavior specification and independently implement it; a separate model session alone is not a clean-room legal or technical boundary.

Sources: [morluto/rea / THIRD_PARTY_NOTICES.md](https://github.com/morluto/rea/blob/main/THIRD_PARTY_NOTICES.md)

REA need not introduce a paid model API. Official Codex and Claude Code support account-based authentication, with plan and usage constraints. Use supported signed-in clients rather than extracting subscription credentials into a custom SDK or assuming subscription access is a general API entitlement. Verify the actual account/authentication mode and disable unapproved paid fallbacks. A subscription still has quotas and possible separately enabled extra usage; do not promise unlimited or zero marginal cost. Native commercial tools and compute/storage can add costs independently.

Sources: [learn.chatgpt.com/docs/auth](https://learn.chatgpt.com/docs/auth) | [code.claude.com/docs/en/authentication](https://code.claude.com/docs/en/authentication)

## Ranked implementation options

### First choice a Mortimer-owned read-only investigation skill

Scope: Answer one question about an approved source tree, packaged app or sanitized capture. Begin with existing source analysis; optionally call a pinned REA static CLI operation. Return an evidence-backed answer and a separate proposed change, never an automatic implementation.

Implementation shape: Mortimer validates target and permission; a restricted adapter accepts a small typed request; the analyzer writes to a dedicated job directory; an output reducer returns selected facts; the normal reviewer evaluates the proposal. Do not install upstream setup globally or give the controller the entire tool catalog. A plain skill without enforced controls is guidance, not a sandbox.

Benefit: Lowest incremental complexity, preserves the existing controller and fits subscription-backed coding clients. Limitation: Does not answer runtime-only questions. Prerequisites: confirm intended repo, one useful owned fixture, exact pinned package, scoped installation approval, evidence retention policy and a measured baseline.

### Second choice no REA integration

Use ordinary repository search, AST/LSP, tests and existing instrumentation. Choose this if the actual need is improving Mortimer's available source or day-to-day personal-assistant reliability. REA adds no clear value until there is a recurring artifact/runtime question. This is the correct fallback if the pilot fails to improve accuracy or effort. Keep the evidence/unknowns discipline without adding a new dependency.

### Third choice a sandboxed specialist worker

Scope: Repeated native binary, packaged app, browser or runtime investigations that passed the static pilot's value test. Keep Mortimer as the only user-facing workflow; REA is an implementation detail behind a job queue.

Implementation shape: separate analysis identity/environment, copied read-only input, isolated writable output, no personal browser profile, no SSH/cloud/account credentials, network denied by default, CPU/memory/disk/time limits, independent approval for target execution or attach, cancellation and cleanup verification. A dedicated Mac VM may be needed for macOS GUI/native behavior; a generic container is not equivalent. Let approved coding-agent clients reason outside the sample sandbox over scrubbed evidence so model credentials are never exposed to target code.

Benefit: Broad capability with a defensible boundary. Cost: macOS permissions, GUI lifecycle, provider setup, storage and maintenance. Prerequisites: source-review-approved adapter, host isolation validation, real target-specific tests and a separate runtime authorization path.

### Fourth choice deeper integration or a fork

Only justified after repeated evidence that public CLI/MCP boundaries are insufficient. Possible later work: normalized evidence storage, cross-version comparisons and a reconstruction planner that produces testable proposals. Avoid embedding REA internals or adopting ERA's entire workbench/control plane now; both increase coupling and duplicate Mortimer's orchestration. Do not allow self-generated analyses to approve their own patches or modify approval machinery. Controller model changes remain a separate user approval decision.

## Proposed pilot and acceptance gates

This is a proposed plan requiring implementation approval, not work already performed.

Pilot A: a tiny owned JavaScript/Electron fixture with known UI-to-IPC-to-handler behavior. Compare existing source tools against REA on the same three questions. Require exact source locations, explicit unknowns and no execution of target application code.

Pilot B: an owned build plus its source. Check a selected source-to-bundle relationship and one intentional version change. Verify reported coverage, distinguish absence from unobserved data, and independently confirm the result from the fixture.

Pilot C, only if justified: a sanitized captured request/response sequence from an owned integration. Require no network egress, no secrets in the model-visible summary and correct identification of the tested behavior. Native decompilation is a later pilot, not a prerequisite for A or B.

Record: package/commit identity, provider and host versions, target digest, question, approved scope, operation names, observed effects, evidence references, uncertainty, elapsed time, model usage, disk usage and cleanup outcome. Keep complete evidence local and page/project only the needed portions; REA's CLI documentation warns that full application evidence can be hundreds of megabytes.

Sources: [morluto/rea / docs/cli.md](https://github.com/morluto/rea/blob/main/docs/cli.md)

Go/no-go gates: answers improve over the baseline; all material claims have inspectable evidence; unsupported cases fail clearly; denied filesystem/network access is tested; prompt-injection fixtures cannot expand privileges; target and evidence retention rules hold; cancellation leaves no owned processes or unexplained files; reinstall/removal is scoped and reversible; the operator can review a proposed patch before changes reach Mortimer. Any unresolved containment or cost issue blocks expansion.

Suggested Mortimer adapter request fields: target reference, target digest, question, analysis mode, approved operation set, data classification, output destination and resource budget. Suggested response fields: facts with locations, inferences, unknowns, evidence references, effects and cleanup status. This is a proposed Mortimer contract, not an assertion that these fields match upstream REA.

## Final decision

Proceed with design only until the intended repository and first practical use case are confirmed. If the goal is understanding another app's feature or a packaged component, a static-only pilot is worthwhile. If the goal is making Mortimer improve its own available code, prioritize the supervised source-development architecture and borrow evidence/validation patterns rather than adding a reverse-engineering platform. ERA merits a focused design comparison, but its disclosed verification gaps rule out treating it as production-ready replacement infrastructure.
