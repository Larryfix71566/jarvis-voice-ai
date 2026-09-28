"""Human-only proposals (MORTIMER_VOICE_WORKFLOWS_PLAN.md W8, Larry 2026-09-25: option A).

Mortimer never writes a human-only (Tier 0) file. A self-edit write to one
is saved instead as a patch under ``docs/proposals/`` (routine tier), which
the draft pull request carries. Larry answers "approve?"; on yes he runs
``scripts/apply_proposal.py <pull request> <digest>`` under his own
identity. That script applies the patch in a throwaway worktree, checks the
result against the ``Result:`` blob recorded here, shows him the diff and
pushes nothing until he types y, then opens it as his own pull request for
CI and closes Mortimer's as superseded. A self-edit branch may only touch allowlisted
paths (validate.yml gate 1), so the applied change cannot live on
Mortimer's branch.

Stdlib only: scripts/apply_proposal.py imports this module to parse what it
applies, so the writer and the applier share one format.
"""
from __future__ import annotations

import difflib
import hashlib
import re
import shlex

PROPOSAL_DIR = "docs/proposals"
MARKER = "HUMAN-ONLY PROPOSAL"
APPLY_SCRIPT = "scripts/apply_proposal.py"
NEW_FILE = "new file"
RATIONALE_PREFIX = "human-only proposal for "

_RATIONALE_RE = re.compile(r"^human-only proposal for (\S+) \(sha256 ([0-9a-f]{16})\): ")
_HEADER_RE = re.compile(r"^(Target|Base|Result|Why): ?(.*)$")
_DIFF_RE = re.compile(r"^diff --git a/(\S+) b/(\S+)$")
_BLOB_RE = re.compile(r"[0-9a-f]{40}")


def proposal_path(target: str) -> str:
    """The one patch file for `target`: readable, and unique per target
    (a second write to the same target replaces its proposal)."""
    slug = re.sub(r"[^a-z0-9]+", "-", target.lower()).strip("-")[:60].strip("-") or "file"
    digest = hashlib.sha1(target.encode("utf-8")).hexdigest()[:8]
    return f"{PROPOSAL_DIR}/{slug}-{digest}.patch"


def is_proposal_path(path: str) -> bool:
    return path.startswith(PROPOSAL_DIR + "/") and path.endswith(".patch")


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def content_digest(text: str) -> str:
    """Names one proposal file's exact content."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def rationale_for(target: str, why: str, digest: str) -> str:
    """The session's record of a proposal the edit API wrote: its target
    and the digest of the exact file (shown in the pull request too)."""
    return f"{RATIONALE_PREFIX}{target} (sha256 {digest}): " + " ".join((why or "").split())


def target_of(rationale: str) -> str | None:
    """The target a proposal file's rationale names, or None for an
    ordinary edit."""
    match = _RATIONALE_RE.match(rationale or "")
    return match.group(1) if match else None


def digest_of(rationale: str) -> str | None:
    match = _RATIONALE_RE.match(rationale or "")
    return match.group(2) if match else None


def set_digest(files: dict[str, str]) -> str:
    """One short digest for a pull request's whole set of proposal files,
    {patch path: content_digest}. The apply command carries the set the
    edit API wrote, so a proposal file that appeared or changed any other
    way (a program run during validation can write under docs/) stops the
    apply instead of riding along with the one Larry approved."""
    lines = "\n".join(f"{path} {files[path]}" for path in sorted(files))
    return hashlib.sha256(lines.encode("utf-8")).hexdigest()[:12]


def _git_lines(text: str) -> list[str]:
    """Lines as git counts them: split on \\n only. str.splitlines also
    splits on \\r, form feeds and Unicode separators, which would make a
    hunk git cannot apply."""
    parts = text.split("\n")
    return [part + "\n" for part in parts[:-1]] + ([parts[-1]] if parts[-1] else [])


def _diff_lines(target: str, before: str | None, after: str, mode: int) -> list[str]:
    old = _git_lines(before or "")
    new = _git_lines(after)
    lines = [f"diff --git a/{target} b/{target}\n"]
    mode = 0o100000 | mode          # git's regular-file mode: 100644 / 100755
    new_sha = git_blob_sha(after.encode("utf-8"))
    if before is None:
        lines += [f"new file mode {mode:o}\n", f"index {'0' * 40}..{new_sha}\n",
                  "--- /dev/null\n", f"+++ b/{target}\n"]
    else:
        old_sha = git_blob_sha(before.encode("utf-8"))
        lines += [f"index {old_sha}..{new_sha} {mode:o}\n",
                  f"--- a/{target}\n", f"+++ b/{target}\n"]
    body = list(difflib.unified_diff(old, new, n=3))[2:]   # drop difflib's own ---/+++
    for line in body:
        # git marks a last line without a newline; difflib does not.
        lines.append(line if line.endswith("\n") else line + "\n\\ No newline at end of file\n")
    return lines


def render(target: str, before: str | None, after: str, why: str, mode: int = 0o644) -> str:
    """The proposal file: a short header git ignores, then a git patch.

    `before` is the file at the session's base revision (None when the
    proposal creates it). Deleting a file is not a proposal."""
    if before == after:
        raise ValueError(f"the proposal would not change {target}")
    base = NEW_FILE if before is None else git_blob_sha(before.encode("utf-8"))
    header = [
        f"{MARKER} (MORTIMER_VOICE_WORKFLOWS_PLAN.md W8)\n",
        f"Target: {target}\n",
        f"Base: {base}\n",
        f"Result: {git_blob_sha(after.encode('utf-8'))}\n",
        f"Why: {' '.join((why or '').split())}\n",
        "\n",
        f"Mortimer did not change {target}. It changes only when Larry approves\n",
        f"this proposal and runs {APPLY_SCRIPT}, which applies it on his own\n",
        "branch and checks the file against Result above.\n",
        "\n",
    ]
    return "".join(header + _diff_lines(target, before, after, mode))


def parse(text: str) -> dict:
    """Header fields and the paths the patch touches. Raises ValueError
    for anything that is not exactly one well-formed proposal."""
    lines = text.split("\n")
    if not lines or not lines[0].startswith(MARKER):
        raise ValueError("not a human-only proposal")
    fields: dict[str, str] = {}
    diff_paths: list[str] = []
    in_diff = False
    for line in lines[1:]:
        diff = _DIFF_RE.match(line)
        if diff:
            in_diff = True
            if diff.group(1) != diff.group(2):
                raise ValueError("a proposal may not rename a file")
            diff_paths.append(diff.group(1))
            continue
        if not in_diff:
            field = _HEADER_RE.match(line)
            if field and field.group(1) not in fields:
                fields[field.group(1)] = field.group(2).strip()
    missing = [name for name in ("Target", "Base", "Result") if not fields.get(name)]
    if missing:
        raise ValueError("proposal header lacks " + ", ".join(missing))
    if diff_paths != [fields["Target"]]:
        raise ValueError(f"the patch must change exactly {fields['Target']}, not {diff_paths or 'nothing'}")
    if not _BLOB_RE.fullmatch(fields["Result"]) or not (
            fields["Base"] == NEW_FILE or _BLOB_RE.fullmatch(fields["Base"])):
        raise ValueError("proposal header has a malformed blob id")
    if fields["Result"] == fields["Base"]:
        raise ValueError("the proposal would not change its target")
    return {"target": fields["Target"], "base": fields["Base"], "result": fields["Result"],
            "why": fields.get("Why", ""), "diff_paths": diff_paths}


def apply_command(repo_root, number: int, digest: str) -> str:
    """The one command Larry runs after he approves, from the checkout the
    admin sidecar runs in, with its virtualenv's Python."""
    if not re.fullmatch(r"[0-9a-f]{12}", digest or ""):
        raise ValueError("a proposal set digest is 12 hex characters")
    return f"cd {shlex.quote(str(repo_root))} && .venv/bin/python {APPLY_SCRIPT} {int(number)} {digest}"
