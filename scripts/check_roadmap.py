#!/usr/bin/env python3
"""Roadmap drift check (WS-20 B4, docs/plans/ROADMAP_JOINT_WORKING_PLAN.md §3).

Compares ROADMAP.md with things a script can check, so a stale row is found
when it goes stale instead of at the next full reconciliation:

  fields      every §2 block has the shared fields; Status starts with a
              lifecycle word
  merged      a claimed / in-progress / review row whose `Where` branch is
              already merged into main (the WS-18 and WS-04 drift of 09-30)
  production  a row states current production ("present in production",
              "not deployed in production", ...) instead of recording events
              (plan B2); an error once ROADMAP.md has a **Production:** line
  receipt     --receipts DIR: the **Production:** line, or a row's current-
              production claim, disagrees with the newest deployment receipt
  pr-age      --github: an open PR older than 2 days that no row's Next step
              names (needs `gh`)
  changelog   once §8 holds the marker <!-- changelog: docs/roadmap-log/ -->:
              no entries left in §8, and
              every log file has its front matter and names existing rows
  ids         WS ids are unique; every WS id mentioned is defined

Standard library only. Prints one finding per line, `WS-xx: problem
(evidence)`, plus GitHub annotations under Actions. Exit 1 when an error is
found, unless --warn-only (the first week in CI, Larry 10-02).

Usage: python scripts/check_roadmap.py [--main REF] [--receipts DIR]
                                       [--github] [--warn-only]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FIELDS = (
    "Owner", "Status", "Implemented by", "Remaining work / acceptance",
    "Model version", "Where", "Plan", "Scope", "Next step", "Updated",
)
LIFECYCLE = ("proposed", "claimed", "in-progress", "review", "landed", "accepted", "blocked", "parked")
OPEN_STATES = ("claimed", "in-progress", "review")
# Present-tense claims about production. Event wording ("deployed in `x` on
# 09-30", "accepted on production `x`") stays true and is not matched.
PRODUCTION_PHRASES = re.compile(
    r"(still in production|present in production|not in (?:verified )?production|"
    r"not deployed in production|not yet deployed|production remains|production is `|"
    r"in verified production|verified production `)",
    re.IGNORECASE,
)
BRANCH_RE = re.compile(r"`((?:codex|claude|docs|fix|feat|ws\d+|plan|sandbox|closure)/[A-Za-z0-9._/-]+)`")
SHA_RE = re.compile(r"`([0-9a-f]{7,40})`")
WS_RE = re.compile(r"\bWS-(\d{2})\b")
LOG_DIR = "docs/roadmap-log"
# B1 puts this marker in §8 when the entries move out; the §8 checks start then.
LOG_MARKER = "<!-- changelog: docs/roadmap-log/ -->"


@dataclass
class Finding:
    level: str  # "error" or "warning"
    where: str
    message: str
    line: int = 0

    def text(self) -> str:
        return f"{self.where}: {self.message}"


@dataclass
class Block:
    ws: str  # "WS-07"
    line: int
    fields: dict[str, str]
    field_lines: dict[str, int]

    @property
    def status_word(self) -> str:
        status = self.fields.get("Status", "").strip()
        m = re.match(r"[A-Za-z-]+", status)
        return m.group(0).lower() if m else ""


def parse_blocks(text: str) -> list[Block]:
    blocks = []
    for m in re.finditer(r'<details id="ws-(\d+)">(.*?)</details>', text, re.S):
        start_line = text.count("\n", 0, m.start()) + 1
        fields, lines = {}, {}
        body_start = m.start(2)
        for fm in re.finditer(r"^- \*\*([^:*]+):\*\* ?(.*)$", m.group(2), re.M):
            name = fm.group(1).strip()
            if name not in fields:
                fields[name] = fm.group(2)
                lines[name] = text.count("\n", 0, body_start + fm.start()) + 1
        blocks.append(Block(f"WS-{m.group(1)}", start_line, fields, lines))
    return blocks


def section(text: str, heading_prefix: str) -> tuple[str, int]:
    """Body of the `## ` section whose heading starts with heading_prefix."""
    m = re.search(rf"^## {re.escape(heading_prefix)}[^\n]*\n", text, re.M)
    if not m:
        return "", 0
    nxt = re.search(r"^## ", text[m.end():], re.M)
    end = m.end() + nxt.start() if nxt else len(text)
    return text[m.end():end], text.count("\n", 0, m.end()) + 1


def production_line(text: str) -> str | None:
    m = re.search(r"^\*\*Production:\*\* ?(.*)$", text[:4000], re.M)
    return m.group(1) if m else None


# --------------------------------------------------------------- git helpers

def git(*args: str, cwd: Path = REPO_ROOT) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def resolve_main(ref: str | None, cwd: Path) -> str | None:
    for cand in ([ref] if ref else ["origin/main", "main", "HEAD"]):
        if git("rev-parse", "--verify", "-q", f"{cand}^{{commit}}", cwd=cwd).returncode == 0:
            return cand
    return None


def merged_pr_for_branch(branch: str, main: str, cwd: Path) -> str | None:
    """PR number whose merge commit on main came from this branch."""
    out = git("log", "--first-parent", "--merges", "--format=%s", main, cwd=cwd).stdout
    for line in out.splitlines():
        m = re.match(r"Merge pull request #(\d+) from [^/\s]+/(\S+)$", line.strip())
        if m and m.group(2) == branch:
            return m.group(1)
    return None


def branch_state(branch: str, main: str, cwd: Path) -> tuple[str, str]:
    """('merged'|'open'|'maybe'|'unknown', evidence)."""
    for ref in (f"origin/{branch}", branch):
        rp = git("rev-parse", "--verify", "-q", f"{ref}^{{commit}}", cwd=cwd)
        if rp.returncode == 0:
            sha = rp.stdout.strip()
            if git("merge-base", "--is-ancestor", sha, main, cwd=cwd).returncode == 0:
                pr = merged_pr_for_branch(branch, main, cwd)
                return "merged", f"{ref} {sha[:7]} is in {main}" + (f" (PR #{pr})" if pr else "")
            return "open", ""
    pr = merged_pr_for_branch(branch, main, cwd)
    if pr:
        # Without the ref we cannot tell whether newer commits sit on the
        # branch (a long-lived branch merged once, e.g. #103), so this is a
        # question, not a verdict.
        return "maybe", f"no ref for {branch} here; PR #{pr} from it was merged into {main}"
    return "unknown", ""


# ------------------------------------------------------------------- checks

def check_fields(blocks: list[Block]) -> list[Finding]:
    out = []
    for b in blocks:
        missing = [f for f in REQUIRED_FIELDS if f not in b.fields]
        if missing:
            out.append(Finding("error", b.ws, f"missing fields: {', '.join(missing)}", b.line))
        if "Status" in b.fields and b.status_word not in LIFECYCLE:
            out.append(Finding("warning", b.ws,
                               f"Status starts with {b.status_word!r}, not a lifecycle word "
                               f"({', '.join(LIFECYCLE)})", b.field_lines.get("Status", b.line)))
    return out


def check_merged_branches(blocks: list[Block], main: str | None, cwd: Path) -> list[Finding]:
    if not main:
        return [Finding("warning", "ROADMAP", "no main ref found; branch checks skipped")]
    out = []
    for b in blocks:
        if b.status_word not in OPEN_STATES:
            continue
        for branch in BRANCH_RE.findall(b.fields.get("Where", "")):
            state, evidence = branch_state(branch, main, cwd)
            if state == "merged":
                out.append(Finding("error", b.ws,
                                   f"status is {b.status_word!r} but branch {branch} is already merged ({evidence})",
                                   b.field_lines.get("Where", b.line)))
            elif state == "maybe":
                out.append(Finding("warning", b.ws,
                                   f"status is {b.status_word!r}; is branch {branch} still in use? ({evidence})",
                                   b.field_lines.get("Where", b.line)))
    return out


def check_production_phrases(blocks: list[Block], has_line: bool) -> list[Finding]:
    out = []
    level = "error" if has_line else "warning"
    for b in blocks:
        for name in ("Status", "Where", "Next step", "Remaining work / acceptance"):
            value = b.fields.get(name, "")
            hits = sorted({m.group(0).lower() for m in PRODUCTION_PHRASES.finditer(value)})
            if hits:
                out.append(Finding(level, b.ws,
                                   f"{name} states current production ({'; '.join(hits)}); record events instead (plan B2)",
                                   b.field_lines.get(name, b.line)))
    return out


def newest_receipt(directory: Path) -> tuple[str, str, Path] | None:
    """Newest *deployed* receipt by its own deployed_at (file times change when copied)."""
    best = None
    for path in directory.glob("deployment-receipt-*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            when = datetime.fromisoformat(str(data.get("deployed_at", "")))
        except (OSError, ValueError):
            continue
        if data.get("status") != "deployed" or not data.get("main_revision"):
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        if best is None or when > best[0]:
            best = (when, data["main_revision"], str(data["deployed_at"]), path)
    return best[1:] if best else None


def check_receipt(text: str, blocks: list[Block], directory: Path) -> list[Finding]:
    found = newest_receipt(directory)
    if not found:
        return [Finding("warning", "Production", f"no deployed receipt in {directory}")]
    sha, when, path = found
    out = []
    line = production_line(text)
    if line is not None:
        shas = SHA_RE.findall(line) or re.findall(r"\b[0-9a-f]{7,40}\b", line)
        if not shas or (not sha.startswith(shas[0]) and not shas[0].startswith(sha[:7])):
            out.append(Finding("error", "Production",
                               f"line says {shas[0] if shas else '(no sha)'}; newest receipt is {sha[:7]} "
                               f"deployed {when} ({path.name})"))
    for b in blocks:
        for name in ("Status", "Where", "Next step"):
            value = b.fields.get(name, "")
            for m in PRODUCTION_PHRASES.finditer(value):
                tail = value[m.end():m.end() + 30]
                sm = SHA_RE.search(tail) or SHA_RE.search(m.group(0) + tail)
                if sm and not sha.startswith(sm.group(1)):
                    out.append(Finding("error", b.ws,
                                       f"{name} names production `{sm.group(1)}`; newest receipt is {sha[:7]} "
                                       f"deployed {when}", b.field_lines.get(name, b.line)))
    return out


def check_pr_age(blocks: list[Block], now: datetime, days: int = 2) -> list[Finding]:
    proc = subprocess.run(
        ["gh", "pr", "list", "--state", "open", "--json", "number,title,createdAt", "--limit", "100"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        return [Finding("warning", "PRs", "gh pr list failed; PR age check skipped")]
    return pr_age_findings(json.loads(proc.stdout or "[]"), blocks, now, days)


def pr_age_findings(prs: list[dict], blocks: list[Block], now: datetime, days: int = 2) -> list[Finding]:
    next_steps = " ".join(b.fields.get("Next step", "") for b in blocks)
    out = []
    for pr in prs:
        created = datetime.fromisoformat(pr["createdAt"].replace("Z", "+00:00"))
        age = now - created
        if age > timedelta(days=days) and not re.search(rf"#{pr['number']}\b", next_steps):
            out.append(Finding("warning", f"PR #{pr['number']}",
                               f"open {age.days} days and no row's Next step names it ({pr.get('title', '')})"))
    return out


def check_changelog(text: str, root: Path) -> list[Finding]:
    body, line = section(text, "8. Change log")
    if LOG_MARKER not in body:
        return []  # B1 not landed yet: §8 still holds the entries
    out = []
    entries = re.findall(r"^- \d{4}-\d{2}-\d{2}", body, re.M)
    if entries:
        out.append(Finding("error", "§8", f"{len(entries)} entries in ROADMAP.md §8; add a file under {LOG_DIR}/ instead", line))
    defined = {b.ws for b in parse_blocks(text)}
    for path in sorted((root / LOG_DIR).glob("*.md")):
        content = path.read_text(encoding="utf-8")
        head = content.split("\n---", 1)[0] if content.startswith("---") else ""
        if not head:
            out.append(Finding("error", f"{LOG_DIR}/{path.name}", "no front matter"))
            continue
        meta = dict(re.findall(r"^(\w+):\s*(.*)$", head, re.M))
        missing = [k for k in ("date", "system", "rows") if not meta.get(k)]
        if missing:
            out.append(Finding("error", f"{LOG_DIR}/{path.name}", f"front matter lacks {', '.join(missing)}"))
        for ws in WS_RE.findall(meta.get("rows", "")):
            if f"WS-{ws}" not in defined:
                out.append(Finding("error", f"{LOG_DIR}/{path.name}", f"names WS-{ws}, which ROADMAP.md does not define"))
    return out


def check_ids(text: str, blocks: list[Block]) -> list[Finding]:
    out = []
    seen: dict[str, int] = {}
    for b in blocks:
        if b.ws in seen:
            out.append(Finding("error", b.ws, f"defined twice (lines {seen[b.ws]} and {b.line})", b.line))
        seen[b.ws] = b.line
    for n in sorted(set(WS_RE.findall(text))):
        if f"WS-{n}" not in seen:
            first = text.count("\n", 0, re.search(rf"\bWS-{n}\b", text).start()) + 1
            out.append(Finding("warning", f"WS-{n}", "mentioned but not defined as a block", first))
    return out


# --------------------------------------------------------------------- main

def run(root: Path, main_ref: str | None, receipts: Path | None, github: bool,
        now: datetime | None = None) -> list[Finding]:
    text = (root / "ROADMAP.md").read_text(encoding="utf-8")
    blocks = parse_blocks(text)
    main = resolve_main(main_ref, root)
    findings = check_fields(blocks)
    findings += check_ids(text, blocks)
    findings += check_merged_branches(blocks, main, root)
    findings += check_production_phrases(blocks, production_line(text) is not None)
    findings += check_changelog(text, root)
    if receipts:
        findings += check_receipt(text, blocks, receipts)
    if github:
        findings += check_pr_age(blocks, now or datetime.now(timezone.utc))
    return findings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", type=Path, default=REPO_ROOT)
    ap.add_argument("--main", dest="main_ref", help="ref that counts as main (default origin/main, main, HEAD)")
    ap.add_argument("--receipts", type=Path, help="folder with deployment-receipt-*.json (the Mac's ~/MortimerRollback/logs)")
    ap.add_argument("--github", action="store_true", help="also check open PR age with gh")
    ap.add_argument("--warn-only", action="store_true", help="report errors but exit 0")
    args = ap.parse_args(argv)

    findings = run(args.root, args.main_ref, args.receipts, args.github)
    annotate = os.environ.get("GITHUB_ACTIONS") == "true"
    for f in findings:
        print(f"{f.level.upper():7} {f.text()}")
        if annotate:
            kind = "warning" if args.warn_only or f.level == "warning" else "error"
            loc = f" file=ROADMAP.md,line={f.line}" if f.line else ""
            print(f"::{kind}{loc}::{f.text()}")
    errors = sum(f.level == "error" for f in findings)
    warnings = len(findings) - errors
    print(f"roadmap check: {errors} errors, {warnings} warnings" + (" (warn-only)" if args.warn_only else ""))
    return 1 if errors and not args.warn_only else 0


if __name__ == "__main__":
    sys.exit(main())
