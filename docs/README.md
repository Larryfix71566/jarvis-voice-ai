# Documentation map

- [Master roadmap](../ROADMAP.md) — who owns what across Claude and Codex; read before any work (protocol in §0).
- [Architecture reference](ARCHITECTURE.md) — current runtime ownership,
  trust boundaries, model routes, deployment paths and verification pointers.
- [Repository map](REPO_MAP.md) — source tree navigation for agents and
  developers.
- [Plans](plans/) — normative implementation plans and specifications,
  including those authored through the planning pathway (adopt default).
  One document per plan; never create documentation directories anywhere
  else in the repo (`jarvis/docs/` in particular must not be recreated).
- [Verified gap closure](plans/MORTIMER_VERIFIED_GAP_CLOSURE_PLAN.md) — the
  2026-09-24 execution addendum for remaining interface, memory, model-access
  and release-evidence gaps; includes locked decisions and model handoff rules.
- [Implemented plans](plans/implemented/) — completed implementation plans,
  kept for the decision history they carry. CLAUDE.md links here.
- [Reviews](reviews/) — model-authored reviews of plans/specs, adopted
  through the planning pathway's review mode. Each ends with an attribution
  footer naming its reviewer.
- [Acceptance](acceptance/) — dated evidence and remaining release gates.
- [Interface research](interface-research/) — research findings and design feedback;
  includes [Jev use cases and Mortimer feedback (2026-09-22)](interface-research/JEV_USE_CASES_AND_MORTIMER_FEEDBACK_2026-09-22.md).
- [Archive](archive/) — superseded or completed documents kept for history
  (archived 2026-09-22); not a source of truth. Its README maps each file to
  its current source.
