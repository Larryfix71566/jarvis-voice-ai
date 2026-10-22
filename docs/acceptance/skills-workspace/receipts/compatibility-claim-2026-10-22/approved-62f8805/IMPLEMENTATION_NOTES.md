# WS-03 post-claim implementation notes

Preparation only; no source edits before the matching main claim. The approved
claim at 62f8805 remains the authority. These notes record the independent
reviewer's non-blocking follow-ups and source observations.

- Use stable ordinal labels for invalid-package CLI diagnostics. Preserve the
  catalog's existing slug-validated skill identity; do not turn catalog display
  metadata into arbitrary error text. CLI inventory deduplication needs a focused
  regression case when compatibility codes replace generic errors.
- Validate all writer fields and serialize the candidate completely before
  creating its directory. Refused authoring must leave no partial directory/file.
- Distinguish frontmatter compatibility controls from existing companion-manifest
  fields. Do not silently change manifest readiness semantics. Report any required
  diagnostic assertion changes by test ID before editing them.
- Preserve catalog digest ordering and integrity reason precedence. The pure
  compatibility parser must not read scripts; the existing digest may hash bytes.
- Refuse package-root scripts entries by casefolded entry-name matching, including
  empty/file/symlink cases. Keep harmless reference directories and code examples.
- Strict YAML should reject duplicate keys, anchors, aliases and explicit tags
  before construction, with bounded bytes and nesting. Avoid exceptions containing
  package-controlled text. Validate types before all normalization or coercion.
- Keep the 20,000-character body guidance a warning for otherwise valid content;
  hard resource limits need boundary tests and cannot truncate instructions.
- Preserve both disclosed script-admission test identities with stronger refusal
  assertions. List any other changed assertion before modification. Frozen SW-B/C
  outcome changes beyond the disclosed script cases require coordination.
- Exercise real admission seams under legacy, workspace pins, V2 and explicit
  request flags using in-memory synthetic providers only. Selected-body drift
  after selection must still fail at the final re-parse.
- Test execution must use the isolated checkout, synthetic temporary state and a
  sanitized environment. No credentials, live provider calls, runtime services,
  installed checkout writes or third-party scripts are authorized.

The third review input digest was separately verified after the fourth review:
c973b3ca793555f017afd0d87f0c866df274c0c4126d1f9df098de437fa1f362.
The fourth reviewer did not independently recompute hashes; author verification
must stay separately attributed.
