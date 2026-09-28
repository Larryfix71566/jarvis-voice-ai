#!/usr/bin/env python3
"""Apply a human-only proposal Larry approved (MORTIMER_VOICE_WORKFLOWS_PLAN.md W8).

Usage, from the production checkout (Mortimer hands Larry this exact line
after he says yes):

    .venv/bin/python scripts/apply_proposal.py <pull request number> <digest>

Mortimer never writes a human-only (Tier 0) file. Its draft pull request
carries the change as docs/proposals/*.patch instead. This script, run by
Larry under his own git and gh identity:

1. checks the pull request is an open Mortimer self-edit, fetches its head
   at exactly the commit GitHub reports, and checks that everything else
   the pull request changes is a file Mortimer may write (this branch is
   about to leave CI's self-edit allowlist gate behind);
   the proposal files must be exactly the ones Mortimer's edit API wrote:
   <digest> names their paths and contents, so a file a program added or
   changed during validation stops the apply;
2. applies every proposal in a throwaway worktree of that commit;
3. checks the NET result, not the patch text: the only files changed are
   the declared targets, each a regular file whose blob is the one its
   proposal recorded, plus the removed proposal files. Anything else a
   patch might smuggle in (a second diff in a form the header check does
   not see, a rename, a symlink, a mode change) stops it;
4. shows Larry the exact diff of every human-only file and waits for "y"
   (his voice "yes" got him this command; this "y" is the approval, made
   after reading the change: CI runs the moment the pull request opens,
   with the repository's secrets, and for a .github/ or dependency change
   that means running the proposed content);
5. commits under Larry's name, pushes larry/proposal-<N> (validate.yml
   gate 1 fails a self-edit branch that touches a human-only file, so the
   change needs a branch of his own), opens that pull request for CI and
   closes Mortimer's as superseded.

Nothing is pushed unless every check passed. The checkout it runs from is
never modified; the worktree is removed on exit.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from sandbox.artifacts import SECRET, source_path_allowed  # noqa: E402  (stdlib only)

SELF_EDIT_PREFIXES = ("jarvis/self-edit", "mortimer/selfedit/")   # == scripts/check_allowlist.py
BRANCH_PREFIX = "larry/proposal-"
REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,200}")
# The worktree holds Mortimer's branch: nothing in it may run. A hooks path
# of /dev/null means no hook fires for worktree add, apply, commit or push,
# even if a repo ever sets core.hooksPath to a directory inside the tree.
NO_HOOKS = ["-c", "core.hooksPath=/dev/null"]
# Terminal control characters and Unicode direction overrides in the diff
# are shown as escapes, so the change on screen is the change in the file.
_HIDDEN = re.compile("[\x00-\x08\x0b-\x1f\x7f-\x9f\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]")


def visible(text: str) -> str:
    return _HIDDEN.sub(lambda m: f"\\u{ord(m.group()):04x}" if ord(m.group()) > 0xff
                       else f"\\x{ord(m.group()):02x}", text)


def _load(name: str, relative: str):
    # By path, not `import jarvis.selfedit...`: the package __init__ pulls in
    # the whole self-edit service; these two modules are stdlib only.
    spec = importlib.util.spec_from_file_location(name, REPO / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


proposals = _load("_w8_proposals", "jarvis/selfedit/proposals.py")
allowlist_mod = _load("_w8_allowlist", "jarvis/selfedit/allowlist.py")
ALLOWLIST = allowlist_mod.Allowlist.load(REPO / "config" / "self_edit_allowlist.json")


class Stop(Exception):
    """A refusal; the message is printed after STOPPED:."""


def run(argv: list[str], cwd: Path, *, check: bool = True) -> str:
    proc = subprocess.run(argv, cwd=cwd, capture_output=True, text=True)
    if check and proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip().splitlines()
        raise Stop(f"`{' '.join(argv[:3])}` failed: {detail[-1] if detail else 'exit ' + str(proc.returncode)}")
    return proc.stdout


def pull_request(number: int, repo: Path) -> dict:
    fields = "number,state,headRefName,headRefOid,baseRefName,title,url"
    data = json.loads(run(["gh", "pr", "view", str(number), "--json", fields], repo))
    if data.get("state") != "OPEN":
        raise Stop(f"pull request {number} is {str(data.get('state')).lower()}, not open")
    head = data.get("headRefName") or ""
    if not head.startswith(SELF_EDIT_PREFIXES):
        raise Stop(f"pull request {number} comes from {head!r}, not a Mortimer self-edit branch")
    return data


def fetch(repo: Path, ref: str) -> str:
    if not REF.fullmatch(ref) or ".." in ref:
        raise Stop(f"{ref!r} is not a branch name this script will fetch")
    run(["git", "fetch", "-q", "--no-tags", "origin", ref], repo)
    return run(["git", "rev-parse", "FETCH_HEAD^{commit}"], repo).strip()


def changed_files(repo: Path, base: str, head: str) -> list[str]:
    merge_base = run(["git", "merge-base", base, head], repo).strip()
    out = run(["git", "diff", "--name-only", "--no-renames", "-z", merge_base, head], repo)
    return [p for p in out.split("\0") if p]


def check_target(target: str) -> None:
    parts = target.split("/")
    if (not source_path_allowed(target) or target.startswith("/") or ".." in parts
            or proposals.is_proposal_path(target)):
        raise Stop(f"{target} is not something a proposal may change (secrets, runtime data, or not a repo path)")
    if ALLOWLIST.tier(target) != allowlist_mod.DENIED and not target.startswith("tests/"):
        raise Stop(f"{target} is not human-only: Mortimer writes it directly, not as a proposal")


def read_proposals(tree: Path, patches: list[str], expect: str) -> dict[str, dict]:
    """Every proposal, checked against the untouched commit before any is applied."""
    found: dict[str, dict] = {}
    raws: dict[str, bytes] = {}
    for patch in patches:
        path = tree / patch
        if path.is_symlink() or not path.is_file():
            raise Stop(f"{patch} is not a regular file on the pull request's branch")
        raws[patch] = path.read_bytes()
    try:
        actual = proposals.set_digest({p: proposals.content_digest(raw.decode("utf-8")) for p, raw in raws.items()})
    except UnicodeError:
        raise Stop("a proposal file is not text") from None
    if actual != expect:
        raise Stop(f"the proposal files on this pull request are not the ones Mortimer wrote "
                   f"(digest {actual}, approved {expect}); do not apply it -- ask Mortimer to redo the change")
    for patch, raw in raws.items():
        if SECRET.search(raw):
            raise Stop(f"{patch} contains something that looks like a credential")
        try:
            info = proposals.parse(raw.decode("utf-8"))
        except (UnicodeError, ValueError) as exc:
            raise Stop(f"{patch}: {exc}") from None
        target = info["target"]
        check_target(target)
        if target in found:
            raise Stop(f"two proposals change {target}")
        at_head = run(["git", "rev-parse", "-q", "--verify", f"HEAD:{target}"], tree, check=False).strip()
        if info["base"] == proposals.NEW_FILE:
            if at_head:
                raise Stop(f"{patch} creates {target}, which already exists")
        elif at_head != info["base"]:
            raise Stop(f"{target} is not the file {patch} was written against")
        found[target] = {**info, "patch": patch}
    return found


def check_net_change(tree: Path, found: dict[str, dict]) -> None:
    """The staged result against HEAD must be exactly: each target changed to
    its Result blob as a regular file, and each proposal file deleted."""
    out = run(["git", "diff", "--cached", "--raw", "--no-renames", "--no-abbrev", "-z", "HEAD"], tree)
    fields = out.split("\0")
    seen: set[str] = set()
    removed: set[str] = set()
    patches = {info["patch"] for info in found.values()}
    for meta, path in zip(fields[0::2], fields[1::2]):
        if not meta:
            continue
        old_mode, new_mode, _old_sha, new_sha, status = meta.lstrip(":").split(" ")
        if path in patches and status == "D":
            removed.add(path)
            continue
        if path not in found:
            raise Stop(f"applying the proposals would also change {path}, which no proposal declares")
        # A changed file keeps its mode; a new one is a plain file (the
        # service never proposes anything else).
        allowed_mode = old_mode if status == "M" else "100644"
        if status not in ("A", "M") or new_mode != allowed_mode:
            raise Stop(f"{path} would become mode {new_mode} ({status}), not the {allowed_mode} it may have")
        if new_sha != found[path]["result"]:
            raise Stop(f"{path} after applying {found[path]['patch']} does not match its Result blob")
        seen.add(path)
    if seen != set(found):
        raise Stop(f"the proposals did not change {', '.join(sorted(set(found) - seen))}")
    if removed != patches:
        raise Stop("a proposal file was not removed")


def confirm(tree: Path, targets: list[str], others: list[str], branch: str) -> None:
    diff = run(["git", "--no-pager", "diff", "--cached", "--no-color", "--no-ext-diff",
                "--no-textconv", "HEAD", "--", *targets], tree)
    print("\nThe human-only change, exactly as it will be pushed:\n")
    print(visible(diff))
    if others:
        print(f"Also in the pull request (files Mortimer may write, validated in its sandbox): {', '.join(others)}")
    try:
        answer = input(f"\nPush this as {branch} and open the pull request? Type y to approve: ")
    except EOFError:
        answer = ""
    if answer.strip().lower() not in ("y", "yes"):
        raise Stop("not approved; nothing was pushed")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("number", type=int, help="Mortimer's pull request number")
    parser.add_argument("digest", help="the proposal set digest from Mortimer's command (12 hex)")
    args = parser.parse_args(argv)
    number, expect = args.number, args.digest.strip().lower()
    repo = Path(run(["git", "rev-parse", "--show-toplevel"], Path.cwd()).strip())
    branch = f"{BRANCH_PREFIX}{number}"
    tree = None
    try:
        pr = pull_request(number, repo)
        print(f"pull request {number}: {pr['title']}")
        if run(["git", "ls-remote", "origin", f"refs/heads/{branch}"], repo).strip():
            raise Stop(f"{branch} already exists on GitHub: this proposal was applied before")
        head = fetch(repo, pr["headRefName"])
        if head != pr["headRefOid"]:
            raise Stop(f"{pr['headRefName']} is at {head[:7]}, not {pr['headRefOid'][:7]} as GitHub reports; run it again")
        base = fetch(repo, pr["baseRefName"])
        changed = changed_files(repo, base, head)
        patches = sorted(p for p in changed if proposals.is_proposal_path(p))
        if not patches:
            raise Stop(f"pull request {number} carries no human-only proposal ({proposals.PROPOSAL_DIR}/*.patch)")
        direct = [p for p in changed if p not in patches and not ALLOWLIST.is_allowed(p)]
        if direct:
            raise Stop(f"pull request {number} itself changes {', '.join(direct)}, which Mortimer may not write")
        print(f"  proposals: {', '.join(patches)}")
        tree = Path(tempfile.mkdtemp(prefix="apply-proposal-"))
        run(["git", *NO_HOOKS, "worktree", "add", "-q", "--detach", str(tree), head], repo)
        found = read_proposals(tree, patches, expect)
        for info in found.values():
            run(["git", *NO_HOOKS, "apply", "--index", "--whitespace=nowarn", str(tree / info["patch"])], tree)
        run(["git", *NO_HOOKS, "rm", "-q", "--", *patches], tree)
        check_net_change(tree, found)
        targets = sorted(found)
        confirm(tree, targets, [p for p in changed if p not in patches], branch)
        title = pr["title"].removeprefix("self-edit: ").strip() or "human-only change"
        subject = f"{title[:80]} (human-only proposal from #{number})"
        body = (f"Applies the human-only proposal Larry approved in #{number} ({pr['url']}).\n\n"
                f"Changed by the proposal: {', '.join(targets)}.\n"
                f"Each file matches the Result blob recorded in its proposal, nothing else "
                f"changed, and the proposal files are removed.")
        run(["git", *NO_HOOKS, "commit", "-q", "-m", subject, "-m", body], tree)
        run(["git", *NO_HOOKS, "push", "-q", "origin", f"HEAD:refs/heads/{branch}"], tree)
        print(f"  pushed {branch}")
        try:
            url = run(["gh", "pr", "create", "--base", pr["baseRefName"], "--head", branch,
                       "--title", subject, "--body", body], repo).strip().splitlines()[-1]
        except Stop as exc:
            raise Stop(f"pushed {branch}, but the pull request did not open ({exc}); open it on GitHub from that branch") from None
        try:
            run(["gh", "pr", "close", str(number), "--comment",
                 f"Superseded by {url}: Larry approved the human-only proposal and applied it on his own branch."], repo)
        except Stop as exc:
            raise Stop(f"opened {url}, but #{number} did not close ({exc}); close it on GitHub") from None
        print(f"APPLIED: {url}")
        print(f"Closed #{number} as superseded. CI runs on the new pull request; merge it when it is green.")
        return 0
    except Stop as exc:
        print(f"STOPPED: {exc}")
        return 1
    finally:
        if tree is not None:
            subprocess.run(["git", "worktree", "remove", "--force", str(tree)], cwd=repo, capture_output=True)
            shutil.rmtree(tree, ignore_errors=True)
            subprocess.run(["git", "worktree", "prune"], cwd=repo, capture_output=True)


if __name__ == "__main__":
    sys.exit(main())
