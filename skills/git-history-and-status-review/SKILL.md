---
name: git-history-and-status-review
description: Report what has recently changed in a local git repository — recent commits with hashes, messages and dates; current branch and its position relative to origin; uncommitted and untracked files; and which files a given commit touched. Use when asked what has shipped, what is in flight, or what state the working tree is in.
metadata:
  source: procedure:15
  agent: developer
  promoted_successes: 20
  promoted_failures: 6
---

# Repository history and status review

## When to use this

Any question of the form "what have we shipped", "what's uncommitted",
"what changed in that commit", or "what branch am I on". This is the
most-exercised procedure in the run log (20 successes, 6 failures) and
the failures were all shape problems — reporting history when status was
asked, or the reverse — so read the question for which of the three it
wants before running anything.

## The three questions, and the command for each

**What has shipped** — commit history:

```
git log --oneline -10
git log -5 --pretty=format:'%h %ad %s' --date=short
```

**What is in flight** — working tree state:

```
git status --short --branch
```

The `--branch` line is the part that answers "am I ahead of origin", and
it is the part most often left out.

**What did that change touch** — a specific commit or the working tree:

```
git show --stat <hash>
git diff --stat            # unstaged
git diff --cached --stat   # staged
```

## Reporting rules

- Answer the question that was asked. History and status are different
  questions; giving both when one was asked buries the answer.
- Prefer `--stat` over full diffs when summarising. A file list with
  line counts is readable by voice; a diff is not.
- Give counts, not adjectives: "9 modified, 3 untracked", never "a few
  changes".
- Never state a branch's position relative to origin without having seen
  it in `git status --branch` output — a stale `git log` cannot tell you
  whether it has been pushed.
- If a command fails, say what failed. An index lock, a detached HEAD or
  a missing remote are all specific and all worth naming.

## Do not store the answer

Repository state is transient. `jarvis/memory.py`'s volatile-state
firewall rejects "19 commits ahead of main" at write time for exactly
this reason: asking git is always correct, and a stored snapshot can
only become wrong. Report it; do not remember it.
