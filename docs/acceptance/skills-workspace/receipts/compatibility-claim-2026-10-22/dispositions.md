# Author dispositions — bounded WS-03 claim review

The exact excerpt review returned **REVISE** through Claude Max, with returned
model `claude-opus-5-5`. This is a review of a claim and partial source excerpts,
not a full-source review, implementation review or acceptance. At the time of this first disposition, the author
amendments below had not been independently re-reviewed. No code changed.

| Finding | Disposition |
|---|---|
| F1 enforcement seam | Adopted: require `parse_skill` refusal and closed catalog reason propagation; test existing final re-parse in both modes. Nuance: the V2 selector already rejects catalog blockers; the review's blanket statement about all V2 paths is broader than the supplied selection evidence. Final re-parse remains essential. No Base/selector source edit is claimed. Refusal-trace UX remains separate SW-D work. Isolation testing means other valid packages/runs remain usable, not that an explicitly refused request secretly substitutes another skill. |
| F2 strictness | Adopted: unique keys, bounded reads/frontmatter, no anchors/aliases/custom tags, strict types and closed descriptive-field schemas. The exact schema will be reviewed implementation work; #246 is a pinned design contract, not an executable allowlist oracle. |
| F3 safe diagnostics | Adopted: closed reason codes/trusted labels/counts, never attacker-controlled values/keys, paths, snippets or exception text; source-to-sink canaries include tool dependency names. |
| F4 scripts | Partially adopted: perform and preserve offline inventory before code. Six current packages, five generally enabled, have no scripts directory. Do not adopt the suggestion to preserve warning-only admission for unresolved script-dependent imports: that conflicts with Larry's no-silent-omission contract. Unknown required dependencies must block. No current package admission change is authorized without explicit review. |
| F5 gate framing | Adopted: retitled inventory as of recorded main; only P0 regression/diagnostic portions are authorized source work. Any frozen SW-B/C fixture outcome change blocks merge and is reported, not silently re-scoped. |
| F6 boundaries | Adopted: preserve #242, pin #246 at028b44e, leave selector source unchanged, require separate path coordination if necessary, and label this partial advisory review honestly. Source hashes were captured externally but not included in the model's excerpts; receipt links the exact input to that manifest. |

No acceptance gate advanced; SW-B/C remain the only two accepted full gates.
Repository-main claim remains the source-edit prerequisite. Current provider,
acceptance installation, WS-20 and publication #246 work remain isolated.

## Second review of 9413b5e — corrections for fresh review

The second independent verdict is preserved unmodified in
`rereview-9413b5e/CLAUDE_REVIEW.md`. All five CI checks passed on that exact head.
This correction changes documentation only:

- Script admission is now deterministic for all packages: any package-root
  `scripts` entry refuses without following links or reading script contents.
  The two existing admission tests and their intentional new refusal expectation
  are named in the plan. Script non-execution and historical evidence remain.
  Harmless instruction/code examples and supported text references remain usable.
- The plan fixes the initial frontmatter/metadata allowlist and observed types.
  Unknown fields cannot become implicitly supported; reviewed additions remain
  possible for known harmless metadata. Full package compatibility is not claimed.
- The original evidence files were already committed. They were omitted from the
  second review packet, not missing from the repository. Decoded input and source
  hashes verify. The next packet includes the original receipt/manifest/input and
  the second review artifacts, plus the corrected claim and relevant source.
- ROADMAP retains the historical bde22bb Versions subcheck pointer. No checkbox
  or gate changes. Source work still waits for the claim on main.

The parent expressly requested these recoverable claim corrections and fresh
review/CI. No source implementation or merge permission is inferred.
