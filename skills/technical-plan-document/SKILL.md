---
name: technical-plan-document
description: Write an implementation plan or technical specification that another model can build from without making design decisions — required sections, explicit decisions with their rationale, acceptance criteria, and a self-audit for contradictions. Use when asked for a plan, spec, design document or phased implementation write-up.
metadata:
  source: procedure:18+22
  agent: developer
  promoted_successes: 22
  promoted_failures: 4
---

# Technical plan and specification documents

## When to use this

Any request for a plan, spec, design document, or phased implementation
write-up. Two learned procedures covered this ground separately
(#18 "technical specification document", #22 "technical integration
plan"); they are one skill, because a spec and a plan differ in emphasis
and not in what makes either usable.

## The standard the document has to meet

**Degradation-proof.** Any model must be able to build from it without
making a design decision. Every choice the author made is written down
along with why; every choice deliberately left open is labelled as open,
not left silent. A reader who has to guess has found a defect.

## Required sections

1. **Evidence** — what is measurably true today. Numbers, file paths,
   run IDs, quoted output. A plan that opens with a proposal instead of
   a measurement is arguing from assumption.
2. **The decision(s)**, each with the alternative considered and the
   specific downside of the alternative.
3. **Design constraints** — the properties that must hold, and for each
   one whether it holds *by construction* or only by discipline.
4. **Numbered work items**, each small enough to verify on its own.
5. **Acceptance criteria** — what makes each item done. Not "it works":
   a command, a test name, an observable output.
6. **Out of scope**, explicitly. The things a reader would reasonably
   assume are included, named and excluded.
7. **Open decisions**, numbered, each with options and a recommendation.

## Rules that came from real failures

- **Name the mechanical backstop for every rule.** A rule without one is
  a wish. If the plan says an agent "should not" do something, say what
  in the code makes it not happen.
- **Self-audit before calling it ready.** Read the whole document
  looking for two sections that contradict each other. This has caught
  real defects — a tier table in one section disagreeing with the
  implementation note in another.
- **State what is unverified.** If a plan was written without access to
  the hardware, API or build tool it targets, say so at the top. An
  unverified section that reads like a verified one is worse than a gap.
- **Do not invent a trigger.** If a mechanism has no natural place to
  fire yet, say so and leave it unwired rather than inventing a caller.

## Where the document goes

Adopted plans land under `docs/plans/`; completed ones move to
`docs/plans/implemented/`; reviews go to `docs/reviews/`. Adoption is
the one place an authorship footer is stamped — candidates on a ballot
stay footer-free so they remain byte-comparable.

## Routing

Real plan authoring runs through the planning pathway (`plan_start`),
not inline in the voice loop. A full document does not fit in a
five-round tool budget, and attempting it there is what produced the
timeouts that created the pathway.
