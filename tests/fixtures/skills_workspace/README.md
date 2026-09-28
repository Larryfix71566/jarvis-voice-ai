# Skills workspace contract fixtures

All content here is synthetic. These files pin wire/data shapes; they do not
assert that a package was activated or that an example executed.

- `catalog-response.json`: bounded library card and separate readiness states.
- `skill-detail.json`: reviewed intended process, with no instruction body.
- `package-metadata.json` and `schema/skill-metadata.schema.json`: sample
  companion metadata and its structural v1 contract. Runtime validation still
  performs the documented semantic checks beyond JSON Schema.
- `schema/workspace-contract.schema.json`: strict structural v1 contracts for
  the catalog response, skill detail, creator request, and activity events.
  Fixture tests also check operation-specific request fields, catalog/detail
  revision and example agreement, process graph invariants, and event sequence,
  process-step references, and truthful status/evidence combinations.
- `creator-request.json`: authenticated version-1 draft API payload after the
  native preview step; the local preview UUID is not sent as an API field.
- `activity-events.json`: illustrative sequence of trusted evidence events.
  Its successful step event uses a synthetic `check_receipt_id` to exercise the
  contract; it is not a receipt from a real execution.
- `voice-actions.json`: synthetic utterances mapped to the bounded navigation
  actions shared by voice, keyboard, and pointer.
- `../skills_authoring/<skill>/matcher-cases.json`: synthetic
  positive/negative matching cases declared by each reviewed package. The
  read-only example preview shows one case; it does not run a model or skill.

The step start/finish records in `activity-events.json` define the event shape;
they are not evidence that production currently emits trusted process-step
events. Current runtime instrumentation must be checked in the acceptance
status.

Update fixtures with the owning protocol/API change and add validation tests.
Do not put user transcripts, credentials, or real task artifacts here.
