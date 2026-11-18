---
date: 2026-11-18
system: claude
rows: [WS-34]
prs: []
---

# 2026-11-18: allowlist check passes on pushes to `next`

- **System:** Claude (Claude Code cloud session), at the coordinator's request.
- **Larry's words (UTC, Claude Duet channel), 03:25:07:** "Fix it". This answered the coordinator's question about a small CI fix so the allowlist check stops failing on pushes to `next`.
- **Problem:** `validate.yml` runs `scripts/check_allowlist.py origin/main...HEAD` on pushes to `main` and `next` as well as on PRs. On a push the script found no branch name, treated the change as a self-edit and diffed all of `next` against `main`. That failed on every push to `next`: `2a15d86`, `5772901` and `8d3be6d`, the merge of #385. On `main` the diff is empty, so it passed there.
- **Change:** on a `push` event the script now reads the branch from `GITHUB_REF` (`refs/heads/<name>`). `main` and `next` are not self-edit branches, so the check is skipped, as it already is for a human PR's head branch.
  - Still restricted: a push to a `jarvis/self-edit/*` or `mortimer/selfedit/*` branch. A tag, a missing ref and any other event stay restricted as before. On a PR, `GITHUB_REF` is ignored.
  - `config/self_edit_allowlist.json` is unchanged.
- **Tests:** four new cases in `tests/ci/test_check_allowlist.py`; all 13 pass. Against this repo's history, a push to `next` failed before the change and passes after it, and a push to a self-edit branch still fails.
