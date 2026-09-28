# Skill authoring quality

Use this checklist as guidance, not a rigid template. Keep the package small,
specific, and useful to another model.

## Trigger and scope

- State what the skill does and the situations where it should be selected.
- Make the description specific enough to separate it from neighboring skills.
- Define the intended user, expected result, and important exclusions.
- Prefer a small reusable capability over a collection of unrelated procedures.

## Instructions

- Write direct, ordered steps; explain why a constraint matters when that helps
  the model make a safe decision.
- Put detailed or rarely needed material in declared references and identify
  exactly when to read each one.
- State input, output, tool, approval, and failure expectations explicitly.
- Do not claim a tool exists until its current Mortimer manifest and runtime
  evidence support that claim.
- Separate guidance from code-enforced behavior. Never imply that an
  instruction alone enforces a gate.

## Examples and checks

- Use representative, synthetic or public examples that do not expose private
  prompts, project secrets, or personal history.
- Include both in-scope and near-boundary requests to test when the skill should
  and should not be selected.
- Prefer checks with observable outcomes. Use offline package validation first.
- Keep expected results independent from the implementation so evaluation can
  reveal omissions instead of merely repeating the skill's instructions.
- Record which checks actually ran, their receipts, and what remains unknown.

## Revision

- Preserve the existing skill name when revising a skill.
- Compare the new revision with the prior one and explain behavior changes.
- A content or dependency change invalidates earlier readiness and evaluation
  evidence until the applicable checks are repeated.
