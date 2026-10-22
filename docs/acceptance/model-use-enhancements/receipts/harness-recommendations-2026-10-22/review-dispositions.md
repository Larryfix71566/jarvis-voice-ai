# Independent code review dispositions

Final exact R3 patch SHA256: `32ccb1f8971ff3e8f11030ec502432cb80dae48bbcf8f45e8f3789b31517c2e4`.

| Finding | Disposition and evidence |
|---|---|
| R1 P1 voice tool bypassed exact native preview and directly confirmed | Removed the voice confirmation sink; always refuses LLM-generated approval. Nonvoice previews include exact identities but no token. Backend/native tests verify no persistence. |
| R1 P1 routed metadata falsely represented actual voice baseline | Separate `configured_selection`; baseline/active_model unknown. Legacy Settings path explicitly disclosed. No runtime claim. |
| R1 P1 no durable identity across mutable config writers | Contained, not implemented: backend stage/confirm block voice_supervisor, including old drafts; native disables it. Nonvoice save is labeled mutable selection snapshot. Universal guard, runtime ACK and rollback remain a pending provider/runtime scope blocker. |
| R1 P1 scheduled health checks removed | Restored original health job. Independently caught passive cache/metadata hook adds no network/inference. Tests cover old job success and failure. |
| R1 P2 cached evidence loses selection/freshness | Recheck current selection digest and original source timestamps; show freshness in UI; stale/changed/malformed/unknown evidence cannot support an upgrade claim. |
| R2 P2 new status endpoints bypassed disable switch | Both use existing `_status_call`; four falsy spellings tested with fail-on-call dependencies. Independent actual-handler AST probe verified zero effect calls and working enabled paths. |
| R2 nonblocking wording/parser coverage | MCP text now says selection-only, active unknown, switching blocked; no parsed IDs => incomplete coverage. |

Independent R3 verdict: merge / human_review_required for the narrowed foundation; no remaining blocking finding within that scope. No author code edits after the exact R3 review. This is not authorization to publish/install or certification of usable harness switching. Full reviewer MD/JSON and frozen hashes are preserved.

238 final backend tests passed;16 native tests passed with native sources unchanged in R3;5 synthetic skill matcher cases and native structural validation passed. No live inference or installed acceptance. Full CI, shared-owner rebase/review, deployment and broader switching work remain pending.
