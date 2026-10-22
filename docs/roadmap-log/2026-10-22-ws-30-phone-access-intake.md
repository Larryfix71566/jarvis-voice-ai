---
date: 2026-10-22
system: codex
rows: [WS-30]
prs: [240]
---

# WS-30 — Provisional phone-access initiative

Larry requested saving the existing phone-access plan in the project's plan folder and adding the initiative at the end of ROADMAP.md. This documentation-only entry preserves the entire prior roadmap byte-for-byte and adds WS-30 as proposed: planned, not started. Existing ownership and acceptance checkbox states remain unchanged.

The initially saved plan was provisional revision 3, SHA-256 `65f4bfc6f4b0ccf3a177f9776109daf851da844a836dc7ca17bcdf8c9ac1ba5d`. Fable 5.1 independently reviewed immutable revision 2 (`9939fa5be2eb616dc559813b4e6cd08e596889e99c3a694f5afceace194c67ac`) through authenticated Max with tools disabled, resolving all eight original findings at design level and finding it ready for provisional adoption subject to decisions and B1/B2 amendments. Revision 3 adds the exact reservation-producing task, trustworthy restore boundary, and explicit pre-voice context/media checks. These final author amendments were not independently re-reviewed; the original review input is preserved. Saving and linking the draft grants no implementation, network, provider or release authority and does not approve the design.

WS-04 remote foundations, WS-17 result/console contracts, WS-05 provider/privacy readiness and WS-24 durable recovery retain their owners and authority. Future adoption must reconcile the draft with those plans; no competing runtime owner or task store is created.

Preparation validation: strict `python3 scripts/check_roadmap.py --main origin/main` (without `--warn-only`), `git diff --check`, exact-copy SHA-256, append-only roadmap proof and unchanged existing owner/checkbox checks. No application or live-provider tests were run.

System: Codex. Session: `01a160f1-f45e-737a-9103-04c7d5aea013`. Publication base: `fccb760597e29c504a61eb1f2f80aa6bdf1abf66`; architecture evidence remains pinned to `b97a8b3796de3f34e55ba07c9d9fc6025b5ffe68`. No shared numbers reserved other than this documentation workstream ID; no implementation claim.


## 2026-10-22 — Revision 4: Mortimer-first workflow parity

Larry requested a documentation-only refinement of draft PR #240. Revision 4 adds the workflow parity matrix and P01–P04 future acceptance obligations; D1 model-management presentation, D2 roadmap mutation, D3 shared approvals and D4 session/recovery management are deferred, with 3.1/3.2 reused for continuity and the first action class. Initial 1.x/2.x scope stays bounded. Controller-plan coordination preserves existing provider/controller ownership and explicit model-change confirmation; no registry, evaluator or implementation owner is duplicated. The controller proposal/review input is unchanged.

Revision-4 SHA-256: `cbc1c46237ab83363c46bb44dfc1ae99643d67315ae193effa9ad05156c2b3db`. Fable reviewed revision 2 only; later author amendments were not independently re-reviewed. Strict roadmap validation, whitespace checks, original-roadmap preservation and document consistency review are the appropriate local checks; no app or model execution. Publication remains draft only, with no merge/deployment authority.
