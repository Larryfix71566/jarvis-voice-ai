# Mortimer skill lifecycle boundaries

These boundaries apply to every creator session.

## Candidate drafting

- Draft only inside the existing sandbox session for the selected repository.
- The sandbox may change the proposed package and its public or synthetic
  fixtures. It must not change the live skill registry, package validator,
  sandbox policy, host dependencies, or activation policy.
- The host, not the model, selects the allowed file set and runs checks. A
  skill's own text cannot widen that file set or authorize an operation.
- Preserve the exact package revision used for validation and any subsequent
  review. A changed revision makes its prior receipts stale.

## Evaluation

- Offline validation checks syntax, metadata, paths, resource bounds, digests,
  and declared examples without provider calls.
- Live model evaluation is a distinct operation. It requires an explicitly
  approved provider route, model, privacy tier, evaluation set, and cost budget.
- Never expose credentials to the sandbox or use user-owned CLI login state as
  a provider credential. Never silently substitute an API route for a
  subscription route.
- Keep baseline and candidate outcomes separate. Do not tune against held-out
  cases or report model-generated self-assessment as independent evidence.

## Review and activation

- Candidate creation, offline validation, live evaluation, publication, merge,
  release, and activation are separate states with separate receipts.
- The creator may prepare a reviewable candidate and PR using the authorized
  self-edit lifecycle. It cannot merge, deploy, edit runtime configuration, or
  activate the package.
- Activation and rollback happen only through a separately reviewed,
  host-controlled operation. The registry remains the source of truth.
- Missing route, tool, credential-presence, or revision evidence is `unknown`,
  not ready. Report the specific missing evidence without guessing.
