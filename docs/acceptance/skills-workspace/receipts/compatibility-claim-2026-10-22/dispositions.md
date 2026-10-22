# Author dispositions — bounded WS-03 claim review

The exact excerpt review returned **REVISE** through Claude Max, with returned
model `claude-opus-5-5`. This is a review of a claim and partial source excerpts,
not a full-source review, implementation review or acceptance. The final author
amendments below have not been independently re-reviewed. No code changed.

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
