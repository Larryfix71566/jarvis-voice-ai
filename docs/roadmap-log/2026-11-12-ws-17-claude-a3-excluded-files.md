---
date: 2026-11-12
system: claude
rows: [WS-17]
prs: [275, 313, 315]
---

# WS-17 A3 — Claude's review of the Kimi-authored files excluded from the combined-source review, Claude, 2026-11-12

System: Claude (Claude Code cloud session, Larry's Claude Duet channel). This is release closure plan item A3, part "Claude for the excluded files". Under §0 rule 14, Kimi's combined-source review of production `b136a2a` to freeze `5777e98` excludes the code Kimi wrote: WS-31 NR1 and WS-32 reader repair #275. Claude wrote neither. Documentation only: this entry. It does not change the WS-17 block or Kimi's review subsection.

## Verdict

**APPROVE. No release-risk finding in the excluded code at the freeze.** Both pieces had earlier nonauthor reviews by Claude. This entry checks that the reviewed bytes are the bytes in the freeze, and reruns their tests at the freeze.

## WS-31 NR1 (no-reference draft contract)

All three files at `5777e98` are the exact blobs Claude approved at head `c43fdbf` ([approval log](2026-11-10-ws-31-claude-nr1-fix-approval.md), #313, #315):

| Path | Blob at `5777e98` |
| --- | --- |
| `jarvis/app_build_contract.py` | `40309e3b393b789df12b49c11867163990d674c9` |
| `tests/unit/test_app_build_contract.py` | `3cfa157ab50efafee9198acf7a66205424dd666f` |
| `tests/fixtures/app_build_contract/new_idea_v1.json` | `3ff48199350544733f51430a5cc8dc74747ca3ea` |

None of the three exists at `b136a2a`, so the entire delta is the approved code. NR1 remains unwired, and `build_authorized` is always false.

## WS-32 reader repair #275

#275's only code commit is `5c5cb2e`. Claude reviewed it on 2026-11-03 ([review log](2026-11-03-ws-32-claude-independent-review.md)). The verdict was that the reader change was "correct within its own file". The one blocking finding was in the host verifier (`jarvis/skills/registry.py`), not in Kimi's code. Claude's #296 and #322 fixed it, and Codex reviewed both (#324 and the 11-10 host-verifier review). #275's three later commits are docs only. The merged blobs of `mcp_servers/mcp_repo/logic.py` (`7beb350`) and `tests/unit/test_roadmap_reader.py` (`32ee189`) at `51a3f56` equal the reviewed `5c5cb2e`.

After #275, Codex's #312 and Claude's #322 changed both files again. Those changes are not Kimi-authored and stay in Kimi's review scope. At the freeze, `git blame` attributes these lines to `5c5cb2e`:

- 6 lines of `mcp_servers/mcp_repo/logic.py` (blob `5fd00243183298c5c74695ae8a20033729505e13`):
  - line 15, a comment;
  - lines 149–150, the `ROADMAP.md`-only cap choice;
  - lines 155 and 157, the size check, made before reading, and its message;
  - line 169, the post-read byte check.
- 41 lines of `tests/unit/test_roadmap_reader.py` (blob `8f316c8643c99dc7241b5cebff4030aaabf3bd51`).

Re-read at the freeze, the surviving logic does what it did when reviewed:

- Only the canonical `ROADMAP.md` gets the separate `ROADMAP_READ_MAX_BYTES` (1 MiB after #322). Every other file keeps `REPO_READ_MAX_BYTES` (256,000).
- An oversize file is refused from `stat()` before it is read, with a "NOT truncated" message.
- A roadmap that grows past the cap between `stat()` and `read_bytes()` is refused, not truncated.

The freeze roadmap is 315,959 bytes, inside the 1 MiB cap.

Not a finding: the cap choice compares the resolved relative path to the exact string `ROADMAP.md`. On a case-insensitive file system, a request for `roadmap.md` would probably get the generic 256,000-byte cap and an honest refusal, not a truncated read. This is untested here. A read of `roadmap.md` through `repo_read_file` on the Mac would settle it. Either way it fails closed.

## Tests at the freeze

Detached worktree at `5777e98`, Python 3.13 venv without the `openai` package:

- `pytest --noconftest tests/unit/test_app_build_contract.py tests/unit/test_roadmap_reader.py -q`: **105 passed** (85 NR1 and 20 reader).
- `--noconftest` was needed because an autouse fixture in the shared `tests/conftest.py` patches `jarvis.agents.delegate` (line 107), and that import reaches `jarvis/llm_client.py`, which needs `openai`. Neither suite references the database, delegation, the notice outbox or the vault and costs paths that conftest redirects. The full suite was not run here. CI's blocking `pytest tests/unit` on the freeze commit covers it.

## Unchanged

No source, test, fixture, configuration, ROADMAP block, plan or acceptance checkbox was changed. This entry does not lift the operational hold. Larry decides recovery and deployment.
