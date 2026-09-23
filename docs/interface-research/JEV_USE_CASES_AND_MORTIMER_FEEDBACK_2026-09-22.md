# Jev use cases and Mortimer interface feedback

Research date: 2026-09-22  
Status: Research and recommendations only; no implementation or routing change approved by this document.

## Assessment

Jev merits evaluation for narrowly defined decisions in Mortimer's interface and memory workflows. Public community projects now demonstrate voice command interpretation, memory retrieval, browser navigation, home automation, and code-review screening. The available evidence is predominantly prototypes, research, and author-run benchmarks, rather than established production reliability.

This research reviewed published documentation and repository material. The projects and their benchmarks were not executed or independently reproduced for Mortimer. Reported measurements below belong to their authors; proposed Mortimer applications are recommendations, not existing capabilities or validated integration results.

Jev returns constrained decisions such as choices, scores, and probabilities. It should complement models that generate answers, explanations, and code. A valid output type does not establish that the decision is correct. See [TypeSafe's introduction](https://typesafe.ai/blog/introducing-system-one-models-and-jev).

## 1. Voice commands and contextual corrections

[Jev Voice Browser](https://github.com/moritzkremb/jev-voice-browser) interprets spoken commands, selects page elements, and handles corrections such as selecting a different previously referenced target. Ambiguous targets receive numbered overlays. Application code controls execution and cancellation. The author reports approximately 330 ms average Jev latency in a small integration test; this is not a Mortimer measurement or general latency guarantee.

**Potential Mortimer use:** resolve commands such as “expand that result,” “move the second card to the other screen,” and “show its sources” against known interface actions and visible cards. Highlight the intended target to provide immediate visual acknowledgment. Preserve existing speech capture and playback rather than adopting the demo's speech service.

**Feedback:** a strong interface fit for reversible actions. Ambiguous or consequential actions must continue through the existing decision and permission rules. Partial speech should not trigger premature execution.

## 2. Automatic memory organization and retrieval

[Jev-Mem](https://github.com/libingzheren/Jev-Mem) uses Jev to classify observations, judge relationships, choose retrieval paths, rank evidence, and assess whether enough information has been found. Its memory views include semantic, temporal, causal, and entity relationships, with provenance. This is a research implementation; its default retains all valid observations, and the repository describes evaluation limitations.

**Potential Mortimer use:** distinguish durable preferences from temporary circumstances, rank relevant history, and suggest useful Knowledge Atlas relationships without routinely asking the user to classify memories.

**Feedback:** closely aligned with the user's desire for memory that quietly adds value. Preserve Mortimer's retention, correction, provenance, and privacy policies. Evaluate suggested classifications and retrieval choices against the existing system before allowing them to change stored memory. Do not transplant the project's retain-all default.

## 3. Research citation support checks

TypeSafe's [citation-checking cookbook](https://docs.typesafe.ai/cookbooks/citation_check) combines exact quotation checks with Jev judgments about whether surrounding source text supports or contradicts a claim. The demonstration uses eight citations, so it does not establish broad accuracy.

**Potential Mortimer use:** display “support found,” “conflicting evidence,” or “needs review” on research result cards, with the relevant source passage available for inspection.

**Feedback:** a useful way to make research results more inspectable. Source support is different from factual truth. Neither an exact quote match nor a model judgment should produce an unconditional “verified fact” label.

## 4. Browser research and navigation

[Jev Browser](https://github.com/jkudish/jev-browser) uses Jev to choose browser actions and assess progress toward a goal. Application code retains action budgets, recovery, and stopping behavior. Difficult websites and ambiguous navigation remain limitations.

**Potential Mortimer use:** a research worker that locates relevant pages and returns evidence to the existing response card associated with the request.

**Feedback:** consistent with the preference for one consolidated result per request and controlled supporting-display behavior. Introducing a browser worker should not introduce additional result windows or bypass the existing action controls.

## 5. Home automation decisions

[Jev for Home Assistant](https://github.com/AboveColin/HA-Jev) is a community integration, not an official TypeSafe integration. It turns questions about household state into probability, choice, or score sensors that can drive automations. It also includes an Assist conversation integration.

**Potential Mortimer use:** identify household situations worth surfacing as reminders or recommendations, and assist with interpreting home-control requests.

**Feedback:** a concrete reference for the home-automation roadmap. Straightforward conditions should remain ordinary deterministic rules. The integration is not evidence that Jev can perform surveillance vision or reliably authorize security-critical actions.

## 6. Screening self-edit changes for review

[Jev Review](https://github.com/devagrawal09/jev-review) screens potential risks, selects relevant code evidence, scores severity, and routes further review. Its author describes findings as review prompts rather than proven defects. The experimental workflow does not replace compiler diagnostics or static analysis.

**Potential Mortimer use:** prioritize sandbox review and direct the existing coding models toward areas needing attention.

**Feedback:** potentially useful as an additional signal alongside tests, compiler checks, and model review. It should not become an independent authority to merge or deploy changes.

## Measured tradeoff: speed versus accuracy

An independent author's [Jev benchmark repository](https://github.com/GaNotchVFX/jev-benchmarks) reports three workloads: support-ticket triage, voice decisions, and bulk tagging. For its voice workload, the author reports approximately 150 ms for Jev versus 1,086 ms for the fastest tested LLM, with a loss of 3–6 percentage points in intent accuracy. These are author-reported results from a specific setup, not independently reproduced results or measurements of Mortimer.

The practical implication is that speed alone does not justify a model change. Measure wrong actions, missed or incorrectly recalled memories, uncertainty handling, end-to-end latency, and total cost. Include fallback calls in the comparison.

## Recommended direction for Mortimer

The strongest initial evaluation candidates are research-source support checks, reversible interface commands, and memory classification/retrieval. Retain the current voice supervisor while comparing these narrower roles. Route uncertain cases through the existing models and application policy.

The user considers approximately one second acceptable for much non-voice sub-agent work. Jev therefore needs to demonstrate better overall results or economics, not merely lower latency. Its API cost must also be compared with the existing subscription-based routes; lower API pricing does not automatically mean lower incremental cost than an already-paid subscription.

Preserve these product requirements in any later implementation proposal:

- Voice control remains available for interface actions.
- Visual feedback identifies the interpreted action or target.
- A request's findings remain consolidated in its response/results area.
- Existing single- and multi-monitor placement behavior remains authoritative.
- Memory classification should reduce user interruption while preserving correction and provenance.
- Sensitive context must pass the project's privacy policy before any external model call; classification itself is a disclosure if the classifier is hosted externally.
- No change to self-edit permissions, approval boundaries, or deployment authority follows from this research.

Before adoption, unresolved questions include Mortimer-specific accuracy, fallback frequency, real end-to-end latency, incremental cost, provider data handling, and how often Jev improves on ordinary rules. These are evaluation questions, not completed acceptance gates.

## Related repository documents

- [Model use enhancements](../plans/MORTIMER_MODEL_USE_ENHANCEMENTS_PLAN.md)
- [Command Console and Knowledge Atlas plan](../plans/MORTIMER_COMMAND_CONSOLE_ATLAS_PLAN.md)
- [Memory automation plan](../plans/MORTIMER_MEMORY_AUTOCONSOLIDATION_PLAN.md)

Research recorded by Codex from the online review discussed with the user on 2026-09-22. This document does not modify those plans or mark any implementation task complete.
