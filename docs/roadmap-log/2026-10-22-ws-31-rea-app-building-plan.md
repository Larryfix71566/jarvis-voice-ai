---
date: 2026-10-22
system: codex
rows: [WS-31]
prs: []
---

# WS-31 — REA-assisted app building through Mortimer

Larry requested preserving the REA research in the existing documentation folder, a phased implementation plan, and then appending that plan to the end of the roadmap. He clarified and confirmed the use case: building new apps and recreating authorized features of reference apps through Mortimer, rather than Mortimer self-improvement. This entry records planned work, not implementation approval.

The [plan](../plans/MORTIMER_REA_INTEGRATION_PLAN.md) covers the no-reference new-app branch, optional static-first REA investigation, evidence/unknowns, behavior specification, existing App Builder/sandbox reuse, independent implementation, behavioral acceptance and separate release approval. It defines typed artifact handoffs, nine ordered work packages, resource/privacy/licensing controls and go/no-go gates. Portable Skill instruction reuse is grounded in the architecture owner's 19-check verification; exact package adaptation, executable adapters and activation remain gated. The controller, Skills, provider, release and investigation owners retain authority.

The [research Markdown](../interface-research/REA_INTEGRATION_RESEARCH_2026-10-22.md) preserves all 82 body paragraphs and 30 hyperlinks from the original research document. The [original DOCX](../interface-research/REA_INTEGRATION_RESEARCH_2026-10-22.docx) is byte-identical, SHA-256 `d57310f50fecaf1ebec459ca3828265b999d05b252b73bc8532fbd6ecd424882`. Its original Mortimer-enhancement framing is preserved as research history; the new plan reflects Larry's subsequent app-building clarification.

Source inspection baseline: main `f88f5f56d4b34bd35007f964dcc4047318144478`. To preserve pending WS-30 and its established end position, the isolated local branch `docs/rea-integration-20261022` is based on phone PR #240 head `87f163a7619596104e27af0bf50a3b6b88d28809`, which contains that main revision. All three phone documentation files are inherited without modification, and WS-31 is appended after WS-30. PR #240 remains pending; no merge was performed. If later publication is requested, refresh main/PR status and reconcile this dependency without duplicating WS-30 or overwriting other owners' changes.

Validation: strict `python3 scripts/check_roadmap.py --main origin/main`, `git diff --check`, original-document/text/hyperlink preservation, local/source-link existence, append-only roadmap proof and unchanged inherited phone documents/previous owner/checkbox state. No integration test, live provider request, REA run, benchmark, installation or activation. No independent review of the REA plan is claimed.

System: Codex. Parent task: the originating documentation task. Documentation-only workstream ID WS-31; no runtime identifiers or implementation paths reserved. Local commit only; no push, PR, merge or deployment authorized.

## Shared compatibility contract handoff

Bound the REA plan to completed `mortimer.skill-compatibility.v1`, original version 0. The canonical adoption target remains the existing WS-03 Skills Workspace plan; the proposed append-only patch is unapplied. Reuse its 22-row gap matrix and 25 proposed acceptance cases. Manual-only invocation requires trusted user origin; translated restrictions apply to schemas and dispatch/delegation/support; exact source/candidate/evidence/policy binding and runtime readback are required. This consumes shared planning work without another importer, code changes or an activation claim. Original research and roadmap append remain unchanged.

## Sanitized publication

System: Codex. WS-31 documentation publication on `docs/rea-integration-publish-20261022`; original local document source `dd8e4f9`, dependency phone #240 at `87f163a7619596104e27af0bf50a3b6b88d28809`, current main `636880eabbe9dc756c30df7128d0a90c02d222bd`. Only provenance and handoff references changed. No implementation, activation, merge or deployment. Next: larry reviews the draft/dependencies; future implementation needs its own claim.
