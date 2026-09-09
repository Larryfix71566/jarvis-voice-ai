"""Self-edit service: the sandboxed "hands" of the self-development loop (plan section 3).

Implements exactly four write operations plus status/revert. The Upgrade
Agent (jarvis/agents/upgrade_agent.py) is the only intended client; the LLM
behind it never gets shell or raw git access.

Locked invariants (plan section 1):
- main is never touched: every operation works on a session branch named
  jarvis/self-edit/<yyyymmdd>-<slug> created from the configured base ref
  (JARVIS_SELFEDIT_BASE_REF, default origin/main); its PR targets that
  same branch.
- Only allowlisted paths (config/self_edit_allowlist.json) can be written.
- submit() refuses unless validate() passed earlier in the same session.
- A rollback tag pre-selfedit-<ts> is created before anything changes.
- No force-push, no branch deletion of anything but the session branch,
  no user-supplied branch names.
- **The user's checkout is never touched** (Larry 2026-08-30: "every time
  we do a self edit we break git"). A session lives in its OWN git
  worktree under data/selfedit_worktrees/<slug>/ — `git worktree add`
  from the shared .git — and every read, edit, validation gate, commit and
  push happens there. The branch the user has checked out, their working
  tree, and the code the running bot imported from disk are never
  involved. Before this, start_session ran `git checkout -b` IN the live
  tree and submit/revert ended with `git checkout main`: a session yanked
  the user's feature branch out from under them (2026-08-30 the entire
  native-client tree vanished mid-build), demanded a clean tree first,
  left the bot running code that no longer matched disk, and made every
  other git action taken mid-session land on the sandbox branch.

Git is invoked via subprocess with an argument list (never shell), a fixed
timeout, and cwd pinned to the repo root or the session worktree — same
discipline as mcp_git.logic.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
import time
import urllib.request
import json
from pathlib import Path

from jarvis.selfedit.allowlist import Allowlist, extract_paths

logger = logging.getLogger(__name__)

GIT_TIMEOUT_S = 60
VALIDATE_PYTEST_TIMEOUT_S = 900  # 2026-09-04: 2,150+ tests; the self-edit
# run that convened council round e48cfbe1 timed out here at 300 s
# (gap-closure plan GC1b). CI runs the same command with no timeout.
# SE5 (MORTIMER_SELFEDIT_AUTHORING_PLAN.md) — the Swift gate. Generous and
# LOGGED, not tuned: these are hang guards, not budgets. Measured 2026-09-07
# in a fresh detached worktree with a warm SwiftPM cache (plan §8 V0b/V0c):
# `swift build` 10.2 s, `swift test` 11.5 s (JarvisKit) / 13.1 s
# (MortimerHost). The only slow path is a cache MISS — a WebRTC XCFramework
# fetch from GitHub after a version bump — which is a download, not a
# compile. Tighten only from logged `seconds`.
VALIDATE_SWIFT_BUILD_TIMEOUT_S = 1800
VALIDATE_SWIFT_TEST_TIMEOUT_S = 900
# Package dependency closure: a JarvisKit change must also build the app
# that consumes it (macos/MortimerHost/Package.swift declares
# .package(path: "../JarvisKit")). Order is build order.
SWIFT_PACKAGES: dict[str, tuple[str, ...]] = {
    "JarvisKit": ("JarvisKit", "MortimerHost"),
    "MortimerHost": ("MortimerHost",),
}

SESSION_BRANCH_PREFIX = "jarvis/self-edit"
ROLLBACK_TAG_PREFIX = "pre-selfedit"
DEFAULT_BASE_REF = "origin/main"
# 2026-09-07: the base a session is cut from (and the branch its PR targets)
# is configuration, not a constant. Every session to date branched from
# origin/main while the running code lived on an unmerged feature branch, so
# the loop validated a tree in which the files it was asked to touch did not
# exist. Set JARVIS_SELFEDIT_BASE_REF to the branch actually being run
# (e.g. feat/graph-layer). A ref that starts with "origin/" is fetched
# before the session; a local ref is used as-is. The PR base is the same
# value with any "origin/" prefix removed, so the two can never diverge.
BASE_REF_ENV = "JARVIS_SELFEDIT_BASE_REF"
# Session worktrees live under data/ — already self-edit-denied and
# gitignored (data/selfedit_worktrees/ joins .gitignore explicitly), the
# same home AppWorkspace uses for foreign repos (data/app_workspaces/).
WORKTREES_DIR = Path("data") / "selfedit_worktrees"

MAX_FILE_BYTES = 200_000  # refuse oversized writes

# Validation subprocesses (the import gates and pytest) get a WHITELISTED
# environment, never this process's. scripts/run_admin.sh exports every
# .env key (`set -a; . ./.env`) and jarvis/admin/server.py calls
# inject_env() at import, so the sidecar's os.environ carries every config
# flag and every vault secret. 2026-09-07: two unit tests that are green in
# a plain shell failed inside validate() on exactly JARVIS_NS_ENABLED=true
# and the vault's JARVIS_GITHUB_TOKEN -- the suite was being run in an
# environment no human ever runs it in, and vault secrets were in the
# environment of an LLM-driven subprocess. A whitelist (not a blacklist of
# known names) is what keeps the next new key from leaking by default; the
# gates then run the way `uv run pytest tests/unit -q` runs for a person.
# Git (self._git) is deliberately NOT covered: push/fetch need HOME, the
# credential helper and whatever the launchd environment provides.
CHILD_ENV_KEEP = (
    "PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "TERM",
    "USER", "LOGNAME", "SHELL",
)


def child_env() -> dict[str, str]:
    """The environment handed to every validation gate subprocess."""
    return {k: v for k, v in os.environ.items() if k in CHILD_ENV_KEEP}

# Tier B gate: import-only, no network, no keys read — pipeline.py and the
# agent modules resolve their clients at build time, not import time.
CORE_IMPORT_SMOKE = (
    "import jarvis.bot.pipeline, jarvis.bot.display, jarvis.agents.base, "
    "jarvis.agents.delegate, jarvis.agents.supervisor, jarvis.skills.registry"
)

_MERGE_NOTE = (
    "Review and merge on GitHub — this PR was opened by the Jarvis "
    "self-development loop. Merge is manual-only; Jarvis cannot merge it."
)


def _repo_root() -> Path:
    return Path(
        os.environ.get("JARVIS_REPO_ROOT", Path(__file__).resolve().parents[2])
    )


def _slugify(text: str, max_len: int = 32) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (slug[:max_len].strip("-") or "change")


# B1/B3 — paths whose change is VISIBLE and therefore unverifiable by any of
# the four validation gates. web/src is the primary self-edit target by
# design (the Edit panel grew out of it), which is precisely why this needs
# saying out loud.
VISUAL_PATH_PREFIXES = ("web/src/", "web/public/",
                        "macos/MortimerHost/Sources/MortimerHost/")


def is_visual_path(path: str) -> bool:
    return str(path).replace("\\", "/").startswith(VISUAL_PATH_PREFIXES)


# SE6 — Swift sources. Package manifests, plists, entitlements and scripts
# are NOT here: they are denied by the allowlist (a manifest change is a
# dependency change, which is a human PR).
SWIFT_PATH_PREFIXES = ("macos/JarvisKit/Sources/", "macos/MortimerHost/Sources/")


def is_swift_path(path: str) -> bool:
    return str(path).replace("\\", "/").startswith(SWIFT_PATH_PREFIXES)


def swift_packages_for(changed: list[str]) -> list[str]:
    """Ordered, de-duplicated packages to build for these changed paths —
    JarvisKit before MortimerHost, because MortimerHost consumes it.

    A path outside macos/, or under a macos/ directory that is not a
    package (macos/README.md), contributes nothing."""
    out: list[str] = []
    for p in changed:
        parts = str(p).replace("\\", "/").split("/")
        if len(parts) >= 2 and parts[0] == "macos" and parts[1] in SWIFT_PACKAGES:
            for pkg in SWIFT_PACKAGES[parts[1]]:
                if pkg not in out:
                    out.append(pkg)
    order = list(SWIFT_PACKAGES)
    return sorted(out, key=order.index)


def is_swift_only(changed: list[str]) -> bool:
    """True when EVERY changed path is under macos/ — the diff contains no
    Python for pytest to exercise. Named for the common case; a macos-only
    diff of docs qualifies too (and gets no Swift gate either, since
    swift_packages_for ignores non-package paths)."""
    return bool(changed) and all(
        str(p).replace("\\", "/").startswith("macos/") for p in changed
    )


# Larry 2026-08-21 ("when those self change edits are present they have to
# be highlighted so they can't go thru quietly"): paths whose change GRANTS
# OR REWIRES AGENT CAPABILITIES. These joined the allowlist the same day so
# a missing tool can be fixed by voice — which deliberately moved the
# privilege-escalation gate to the human merging the PR. That only works if
# the PR announces itself: a capability grant buried in a routine-looking
# diff is the quiet pass-through this flag exists to prevent.
CAPABILITY_PATHS = ("config/agents.yaml", "config/mcp_servers.yaml")
CAPABILITY_PATH_PREFIXES = ("mcp_servers/",)


def is_capability_path(path: str) -> bool:
    p = str(path).replace("\\", "/")
    return p in CAPABILITY_PATHS or p.startswith(CAPABILITY_PATH_PREFIXES)


class SelfEditError(Exception):
    """Raised for refused operations; the service API converts to dicts."""


class SelfEditService:
    """One active self-edit session at a time per service instance."""

    def __init__(
        self,
        repo_root: str | Path | None = None,
        allowlist_path: str | Path | None = None,
        github_token: str | None = None,
        github_repo: str | None = None,
        base_ref: str | None = None,
    ):
        self.repo_root = Path(repo_root) if repo_root else _repo_root()
        al_path = Path(allowlist_path) if allowlist_path else (
            self.repo_root / "config" / "self_edit_allowlist.json"
        )
        self.allowlist = Allowlist.load(al_path)
        self.base_ref = base_ref or os.environ.get(BASE_REF_ENV) or DEFAULT_BASE_REF
        self._github_token = github_token or os.environ.get("JARVIS_GITHUB_TOKEN")
        self._github_repo = github_repo or os.environ.get(
            "JARVIS_GITHUB_REPO", "Larryfix71566/jarvis-voice-ai"
        )
        # Active session state (None when no session).
        self.branch: str | None = None
        self.rollback_tag: str | None = None
        self.goal: str | None = None
        self.proposals: list[dict] = []
        # SE8 — the delegating run's id, threaded from the staging record
        # through start_session so every selfedit_* log line, the status
        # payload and the finish job share ONE id. Set in step 3; declared
        # here so the gate log lines below never see an unset attribute.
        self.run_id: str | None = None
        self._validated_ok = False
        # SE6 — the checks from the LAST validate(), for the PR body.
        self._last_checks: list[dict] = []
        # The session's isolated worktree (None when no session). Every
        # file read/write and every git command that concerns the SESSION
        # runs here; the user's checkout (repo_root) is only ever used for
        # shared-repo operations (fetch, tag, worktree add/remove, branch
        # -D) and for verify_appearance's "what is the human running"
        # question.
        self.work_root: Path | None = None

    @property
    def pr_base(self) -> str:
        """The GitHub branch a session's PR targets: base_ref minus any
        "origin/" prefix. One value drives both `worktree add` and the PR,
        so a session can never be cut from one branch and opened against
        another."""
        ref = self.base_ref
        return ref[len("origin/"):] if ref.startswith("origin/") else ref

    @property
    def tree(self) -> Path:
        """Where the session's files live: the worktree while a session is
        active, else the repo root (read-only uses such as
        describe_boundary)."""
        return self.work_root if self.work_root is not None else self.repo_root

    # ------------------------------------------------------------- git

    def _git(self, *args: str, timeout: int = GIT_TIMEOUT_S,
             cwd: Path | None = None) -> tuple[int, str]:
        """Run git. Default cwd is the session worktree when one is active
        (so diff/add/commit/push act on the SESSION), else the repo root.
        Pass cwd=self.repo_root explicitly for shared-repo operations."""
        proc = subprocess.run(
            ["git", *args],
            cwd=cwd if cwd is not None else self.tree,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return proc.returncode, (proc.stdout + proc.stderr).strip()

    def _git_ok(self, *args: str, timeout: int = GIT_TIMEOUT_S,
                cwd: Path | None = None) -> str:
        code, out = self._git(*args, timeout=timeout, cwd=cwd)
        if code != 0:
            raise SelfEditError(f"git {' '.join(args[:2])} failed: {out}")
        return out

    def _worktree_path(self, branch: str) -> Path:
        return self.repo_root / WORKTREES_DIR / branch.rsplit("/", 1)[-1]

    def _remove_worktree(self, branch: str | None) -> None:
        """Best-effort teardown of the session worktree + local branch.
        Shared-repo operations, so cwd is the repo root. Never touches the
        user's checkout; never deletes any branch but the session's."""
        self.work_root = None
        if branch is None:
            return
        path = self._worktree_path(branch)
        if path.exists():
            self._git("worktree", "remove", "--force", str(path), cwd=self.repo_root)
        self._git("worktree", "prune", cwd=self.repo_root)
        self._git("branch", "-D", branch, cwd=self.repo_root)

    def _run(self, argv: list[str], cwd: Path, timeout: int) -> tuple[int, str]:
        try:
            proc = subprocess.run(
                argv, cwd=cwd, capture_output=True, text=True, timeout=timeout,
                env=child_env(),
            )
            return proc.returncode, (proc.stdout + proc.stderr).strip()[-4000:]
        except FileNotFoundError as exc:
            return 127, str(exc)
        except subprocess.TimeoutExpired:
            return 124, f"timed out after {timeout}s"

    # ---------------------------------------------------------- session

    def start_session(self, goal: str, run_id: str | None = None) -> dict:
        """Open a session. `run_id` (SE8) is the delegating run's id, from
        the staging record — carried on the session so the developer run,
        the sidecar job, the gate log lines and the ledger share ONE id.
        Reconstructing the 2026-09-07 history needed two logs and four
        tables joined by timestamp because nothing did."""
        if not goal or not goal.strip():
            return {"ok": False, "error": "goal is empty"}
        if self.branch is not None:
            return {
                "ok": False,
                "error": f"a self-edit session is already active on {self.branch} — "
                         "submit or revert it first",
            }
        # NO clean-tree requirement on the user's checkout any more: the
        # session gets its own worktree, which is clean by construction.
        # The old check forced the developer to "clean up" the user's tree
        # first (2026-08-30 it deleted a directory to satisfy it).
        try:
            root = self.repo_root
            if self.base_ref.startswith("origin/"):
                self._git_ok("fetch", "origin", self.pr_base, cwd=root)
            ts = time.strftime("%Y%m%d-%H%M%S")
            tag = f"{ROLLBACK_TAG_PREFIX}-{ts}"
            # Two sessions inside one second (a retry right after a
            # revert) must not collide on the tag — suffix, never -f.
            n = 2
            while self._git("rev-parse", "--verify", "-q", f"refs/tags/{tag}", cwd=root)[0] == 0:
                tag = f"{ROLLBACK_TAG_PREFIX}-{ts}-{n}"
                n += 1
            branch = f"{SESSION_BRANCH_PREFIX}/{time.strftime('%Y%m%d')}-{_slugify(goal)}"
            path = self._worktree_path(branch)
            # A previous session that crashed mid-way may have left a
            # registered-but-gone worktree or a stale directory; prune
            # first so `worktree add` sees a clean slate.
            self._git("worktree", "prune", cwd=root)
            if path.exists():
                raise SelfEditError(
                    f"a stale session worktree exists at {path} — remove it "
                    "(git worktree remove --force) before starting a new session"
                )
            self._git_ok("tag", tag, self.base_ref, cwd=root)
            path.parent.mkdir(parents=True, exist_ok=True)
            self._git_ok("worktree", "add", str(path), "-b", branch, self.base_ref, cwd=root)
        except SelfEditError as exc:
            return {"ok": False, "error": str(exc)}
        self.branch = branch
        self.rollback_tag = tag
        self.work_root = path
        self.goal = goal.strip()
        self.run_id = (run_id or "").strip() or None
        self.proposals = []
        self._validated_ok = False
        self._last_checks = []
        logger.info("selfedit_session_start branch=%s tag=%s worktree=%s run_id=%s",
                    branch, tag, path, self.run_id)
        return {"ok": True, "branch": branch, "rollback_tag": tag, "worktree": str(path)}

    # ----------------------------------------------------------- edits

    def read_file(self, path: str) -> dict:
        """Read an allowlisted file (the agent's window into the codebase)."""
        try:
            rel = self._check_path(path)
        except SelfEditError as exc:
            return {"ok": False, "error": str(exc)}
        full = self.tree / rel
        if not full.is_file():
            return {"ok": False, "error": f"no such file: {rel}"}
        if full.stat().st_size > MAX_FILE_BYTES:
            return {"ok": False, "error": f"file too large to read: {rel}"}
        return {"ok": True, "path": rel, "content": full.read_text(encoding="utf-8")}

    def propose_edit(self, path: str, new_content: str, rationale: str,
                     visual_intent: str = "") -> dict:
        """Stage one allowlisted edit; returns the resulting diff.

        `visual_intent` (MORTIMER_DEVELOPER_SECTIONS_AND_VISUAL_VERIFY_PLAN.md
        B1) — ONE sentence saying what should look different, recorded only
        for edits under web/src or web/public.

        It exists because a vision model asked "does this look right?" has no
        reference and will produce agreeable prose. Asked "is the side drawer
        translucent, with the desktop visible through it?" it can be wrong in
        a way that is DETECTABLE. Absent is a legal state and is reported as
        such — never a fabricated question, the same discipline AppWorkspace
        applies to a missing `mortimer.app.yaml`.
        """
        if self.branch is None:
            return {"ok": False, "error": "no active session — call start_session first"}
        try:
            rel = self._check_path(path, must_exist=False)
        except SelfEditError as exc:
            return {"ok": False, "error": str(exc)}
        if len(new_content.encode("utf-8")) > MAX_FILE_BYTES:
            return {"ok": False, "error": f"edit too large for {rel}"}
        full = self.tree / rel
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(new_content, encoding="utf-8")
        self._validated_ok = False  # any new edit invalidates prior validation
        self._last_checks = []
        _c, diff = self._git("diff", "--", rel)
        proposal = {"path": rel, "rationale": rationale, "diff": diff}
        if is_visual_path(rel):
            proposal["visual_intent"] = visual_intent.strip()
        self.proposals = [p for p in self.proposals if p["path"] != rel]
        self.proposals.append(proposal)
        logger.info("selfedit_propose path=%s", rel)
        return {"ok": True, "path": rel, "diff": diff}

    def verify_appearance(self, *, branch_override: bool = False,
                          display: int = 1, view=None) -> dict:
        """B2 — look at the running console and say whether the recorded
        `visual_intent` is actually true.

        THIS IS A CHECK, NEVER A GATE. It cannot be called from validate()
        and must never join the checks list: a screenshot taken during
        validation photographs whatever console happens to be running —
        almost always the PRE-change one — and would hand back a green tick
        that means nothing. It is only meaningful once the branch is on
        screen, which is after a human has pulled and run it.

        Order matters and each step can refuse:
          1. Confirm what is checked out. A pass claimed against the wrong
             code is exactly the failure this exists to prevent.
          2. State the residual assumption every time — the branch is
             confirmed, a browser RELOAD is not. Under `npm run dev` Vite
             hot-reloads so the two coincide; against a stale production
             build they do not.
          3. Refuse when no visual_intent was recorded, naming that as the
             reason rather than inventing a question.
        """
        visual = [p for p in self.proposals if is_visual_path(p["path"])]
        if not visual:
            return {"ok": False,
                    "error": "this session changed nothing visible "
                             "(no web/src or web/public edits)"}

        # The USER's checkout, explicitly — the session worktree is always
        # on the session branch and would trivially "match".
        code, current = self._git("rev-parse", "--abbrev-ref", "HEAD", cwd=self.repo_root)
        current = current.strip() if code == 0 else "<unknown>"
        matched = self.branch is not None and current == self.branch
        if not matched and not branch_override:
            return {
                "ok": False,
                "branch": current,
                "expected_branch": self.branch,
                "error": (
                    f"the checked-out branch is {current!r}, not this "
                    f"session's {self.branch!r}. Looking at the screen now "
                    f"would judge different code. Check out the branch, or "
                    f"pass branch_override if these changes are already "
                    f"merged into what is running."
                ),
            }

        intent = next((p.get("visual_intent", "") for p in visual
                       if p.get("visual_intent")), "")
        if not intent:
            return {
                "ok": False,
                "branch": current,
                "error": "no intended appearance was recorded for this "
                         "session, so there is nothing specific to check "
                         "for. Say what should look different and retry.",
            }

        question = (
            f"{intent}\n\nAnswer only from what is on screen. Also report "
            f"anything unreadable, clipped, or overlapping, and say plainly "
            f"if you cannot tell."
        )
        if view is None:
            from mcp_servers.mcp_screen.logic import screen_view as view
        result = view(question, display=display)
        if result.get("error"):
            return {"ok": False, "branch": current, "error": result["error"]}
        return {
            "ok": True,
            "branch": current,
            "branch_matched": matched,
            "intent": intent,
            "answer": result.get("answer", ""),
            "low_confidence": bool(result.get("low_confidence")),
            # Stated EVERY time, not only on the override path: confirming
            # the branch is not confirming that the browser reloaded.
            "assumption": ("the branch is confirmed; a browser reload is "
                           "not. Under `npm run dev` Vite hot-reloads, so "
                           "these coincide; against a stale production "
                           "build they do not."),
        }

    def _visual_change_block(self) -> list[str]:
        """B3 — the PR body flags a change the four validation gates cannot
        see.

        allowlist/backend-import/frontend-build/pytest prove the code
        compiles, imports and passes tests. NONE of them can tell whether the
        console still looks right: every glass change made 2026-08-18 would
        have sailed through all four while rendering as anything at all. The
        only thing between a self-edit and an unusable console is a human
        running the branch, so the PR says so.
        """
        visual = [p for p in self.proposals if is_visual_path(p["path"])]
        if not visual:
            return []
        stated = [p.get("visual_intent", "") for p in visual]
        intent = next((s for s in stated if s), "")
        lines = ["", "### Visual change — run the branch before merging", ""]
        if intent:
            lines.append(f"Intended appearance: {intent}")
        else:
            # The warning is the useful half. Omitting the block because the
            # agent failed to author a sentence would hide a visual change
            # exactly when the agent was least careful about it.
            lines.append("_No intended appearance was stated — describe what "
                         "should look different before verifying._")
        lines += [
            "",
            "The four validation checks cannot see the screen. Run this "
            "branch and say \"check your appearance\" to have Mortimer look "
            "at the result.",
        ]
        return lines

    def _swift_change_block(self) -> list[str]:
        """SE6 — the PR body flags a change that needs a REBUILD.

        Every other gate proves the branch is correct. None of them changes
        the binary the human is running: MortimerHost is a compiled app,
        and a merged Swift change does nothing at all until
        macos/MortimerHost/scripts/bundle.sh runs. That one manual step is
        the only thing left in the loop, so it is stated in the PR, in the
        spoken submit notice, and nowhere else does it need saying."""
        swift = [p["path"] for p in self.proposals if is_swift_path(p["path"])]
        if not swift:
            return []
        lines = ["", "### ⚠ SWIFT CHANGE — rebuild the app before using it", ""]
        lines += [f"- `{p}`" for p in swift]
        lines += [
            "",
            "The gates ran `swift build` and `swift test` in the session "
            "worktree, so this branch compiles. The MortimerHost you are "
            "running is still the binary from the last rebuild. After "
            "merging and pulling:",
            "",
            "    cd macos/MortimerHost && scripts/bundle.sh",
            "",
            "Then say \"check your appearance\" to have Mortimer look at the "
            "result.",
        ]
        return lines

    def _validation_block(self) -> list[str]:
        """SE6 — what the gates actually did, in the PR body.

        `.github/workflows/validate.yml` runs on pull requests to `main`
        only. While JARVIS_SELFEDIT_BASE_REF points at a feature branch,
        GitHub runs NO checks on a self-edit PR, and this table is the only
        record that anything was validated at all."""
        if not self._last_checks:
            return []
        lines = ["", "### Validation (sidecar gates)", "",
                 "| gate | ok | seconds |", "|---|---|---|"]
        for check in self._last_checks:
            seconds = check.get("seconds")
            shown = "—" if seconds is None or check.get("selected") is False \
                else f"{seconds:.1f}"
            lines.append(f"| {check['name']} | {'✓' if check['ok'] else '✗'} | {shown} |")
        lines += [
            "",
            "`.github/workflows/validate.yml` runs only on pull requests to "
            "`main`; when the base is a feature branch this table is the "
            "only record of what ran.",
        ]
        return lines

    def _capability_change_block(self) -> list[str]:
        """The PR body flags a change that grants or rewires agent tools.

        Unlike the visual block (which flags what validation cannot SEE),
        this flags what validation cannot JUDGE: all four gates can pass
        on a diff that hands an agent a capability it should not have.
        The human merging on GitHub is the enforcement point for that
        class, so the PR must make the class unmissable.
        """
        cap = [p for p in self.proposals if is_capability_path(p["path"])]
        if not cap:
            return []
        lines = [
            "",
            "### ⚠ CAPABILITY CHANGE — this PR grants or rewires agent tools",
            "",
            "Files that define what agents can do:",
        ]
        for p in cap:
            lines.append(f"- `{p['path']}`")
        lines += [
            "",
            "Review the `config/agents.yaml` and `config/mcp_servers.yaml` "
            "diffs line by line before merging: every added server or tool "
            "is a standing grant to that agent, not a one-off. Validation "
            "gates verify the code works — only this review verifies the "
            "grant is intended.",
        ]
        return lines

    def _core_change_block(self) -> list[str]:
        """Tier B — the PR body flags a change to the product core
        (MORTIMER_SELFEDIT_TIERS_PLAN.md). The gates prove it imports and
        passes tests; only a human RUNNING the branch proves voice still
        works. Same mechanism as the visual/capability blocks: keyed on
        WHICH paths changed, never on what the agent wrote about them."""
        core = [p["path"] for p in self.proposals if self.allowlist.is_core(p["path"])]
        if not core:
            return []
        lines = [
            "",
            "### ⚠ CORE CHANGE — this PR edits the voice pipeline / agent core",
            "",
            "Tier B files changed:",
        ]
        for path in core:
            lines.append(f"- `{path}`")
        lines += [
            "",
            "All validation gates passed (allowlist, backend imports, core "
            "imports, frontend build, pytest), but none of them can hear "
            "Mortimer talk. Run this branch — `./scripts/mortimer.sh` from a "
            "checkout of it — and hold a real conversation before merging.",
        ]
        return lines

    def _check_path(self, path: str, must_exist: bool = False) -> str:
        if not self.allowlist.is_allowed(path):
            raise SelfEditError(
                f"path is not on the self-edit allowlist: {path!r}. "
                "Off-allowlist changes require human development."
            )
        rel = Allowlist._normalize(path)
        if must_exist and not (self.tree / rel).is_file():
            raise SelfEditError(f"no such file: {rel}")
        return rel

    # ------------------------------------------------------- validation

    def validate(self) -> dict:
        """Run the same gates as CI (plan section 2.2). Read-only; never commits."""
        if self.branch is None:
            return {"ok": False, "error": "no active session"}
        checks: list[dict] = []

        # 1. Allowlist enforcement on the full diff vs origin/main.
        t_gate = time.monotonic()
        _c, names = self._git("diff", "--name-only", self.base_ref, "--", ".")
        changed = [n for n in names.splitlines() if n.strip()]
        # `git diff` lists TRACKED changes only. propose_edit writes a file
        # but never stages it (submit() is what runs `git add`), so a
        # self-edit that CREATES a file was invisible to every gate below:
        # the allowlist check that exists to be independent of
        # propose_edit's own check saw nothing, and SE5's gate selection
        # would read a mixed diff as Swift-only. Untracked, non-ignored
        # files are part of the diff this session will submit, so they are
        # part of what the gates see. (Found 2026-09-07 writing SE5's
        # tests; .pytest_cache and __pycache__ are ignored, so gate output
        # cannot pollute this list.)
        _c, untracked = self._git("ls-files", "--others", "--exclude-standard")
        for name in untracked.splitlines():
            if name.strip() and name not in changed:
                changed.append(name)
        violations = self.allowlist.filter_violations(changed)
        core_changed = self.allowlist.core_paths(changed)
        checks.append({
            "name": "allowlist",
            "ok": not violations,
            "output": ("all changed files allowed"
                       if not violations else "forbidden: " + ", ".join(violations))
                      + (f" · core (Tier B): {', '.join(core_changed)}" if core_changed else ""),
            "seconds": round(time.monotonic() - t_gate, 1),
        })
        logger.info("selfedit_gate name=allowlist ok=%s seconds=%.1f run_id=%s",
                    not violations, time.monotonic() - t_gate, self.run_id)

        # 2. Backend import smoke.
        # sys.executable, not a bare "python"/"python3" resolved off PATH
        # (2026-09-02 fix): this venv is uv-managed and has no `python`
        # binary at all in some environments (only `python3`), and
        # subprocess.run here does not go through a shell -- a hardcoded
        # "python" 127'd with "No such file or directory" the moment PATH
        # didn't happen to resolve it, silently failing every validate()
        # call's import/pytest gates. sys.executable is also more correct
        # on its own terms: it pins the gate to the SAME interpreter (and
        # therefore the same installed deps) the running bot uses, rather
        # than whatever "python" happens to mean in the ambient PATH.
        t_gate = time.monotonic()
        code, out = self._run(
            [sys.executable, "-c", "import jarvis, jarvis.config, jarvis.cli"],
            cwd=self.tree, timeout=120,
        )
        seconds = time.monotonic() - t_gate
        logger.info("selfedit_gate name=backend_imports ok=%s seconds=%.1f run_id=%s",
                    code == 0, seconds, self.run_id)
        checks.append({"name": "backend_imports", "ok": code == 0,
                       "output": out or "imports ok", "seconds": round(seconds, 1)})

        # 2b. Tier B (core) — the fifth gate, only when a core path changed
        # (MORTIMER_SELFEDIT_TIERS_PLAN.md): the voice pipeline and the agent
        # roster must still IMPORT. A broken pipeline construct is the one
        # failure the plain `import jarvis` smoke never sees, and it is
        # exactly what a jarvis/bot or jarvis/agents edit can break.
        if core_changed:
            t_gate = time.monotonic()
            code, out = self._run(
                [sys.executable, "-c", CORE_IMPORT_SMOKE],
                cwd=self.tree, timeout=180,
            )
            seconds = time.monotonic() - t_gate
            logger.info("selfedit_gate name=core_imports ok=%s seconds=%.1f run_id=%s",
                        code == 0, seconds, self.run_id)
            checks.append({"name": "core_imports", "ok": code == 0,
                           "output": out[-2000:] or "core imports ok",
                           "paths": core_changed, "seconds": round(seconds, 1)})

        # There is no frontend build step any more (removed 2026-09-05). web/
        # is frozen and no goal can reach it, so building it validated nothing
        # while costing up to 600 s twice per run in a fresh worktree
        # with no node_modules — and an npm failure for ANY environmental
        # reason (registry blip, node drift, yanked transitive dep) failed
        # validation, exhausted the single auto-repair, and convened an E1
        # council over a component nobody runs.
        # 3a. Swift gate (SE5) — only when a Swift PACKAGE changed. Runs
        # BEFORE pytest: it is the cheaper of the two (measured ~10 s per
        # package against ~330 s for the suite), so a Swift break is
        # reported in seconds instead of six minutes.
        #
        # The gate keys on `_run`'s EXIT CODE, never on output text: a
        # `swift test` run prints the Swift Testing runner's "Test run with
        # 0 tests ... passed" line AFTER an XCTest failure in the same
        # output (2026-09-07, plan §8 V0c), so the last line lies.
        for pkg in swift_packages_for(changed):
            pkg_dir = self.tree / "macos" / pkg
            for verb, timeout in (("build", VALIDATE_SWIFT_BUILD_TIMEOUT_S),
                                  ("test", VALIDATE_SWIFT_TEST_TIMEOUT_S)):
                t_gate = time.monotonic()
                code, out = self._run(["swift", verb], cwd=pkg_dir, timeout=timeout)
                seconds = time.monotonic() - t_gate
                name = f"swift_{verb}:{pkg}"
                logger.info("selfedit_gate name=%s ok=%s seconds=%.1f run_id=%s",
                            name, code == 0, seconds, self.run_id)
                checks.append({"name": name, "ok": code == 0,
                               "output": out[-2000:] or f"swift {verb} ok",
                               "seconds": round(seconds, 1)})
                if code != 0:
                    # A package that does not build cannot be meaningfully
                    # tested. The next package is still attempted: whether a
                    # JarvisKit break also breaks MortimerHost is something
                    # to READ in the checks, not assume.
                    break

        # 4. Backend unit tests (C2, MORTIMER_MODEL_DISCIPLINE_AND_MAC_SHELL_PLAN.md).
        # CI's own pytest step is a hard gate now for the same reason — a
        # self-edit that imports cleanly can still break backend behavior;
        # only the test suite catches that.
        #
        # SE5 gate SELECTION: a diff entirely under macos/ contains no
        # Python, and no test under tests/ reads macos/ (verified by grep,
        # 2026-09-07). Running the suite on it validates nothing and costs
        # ~330 s. This is a selection rule inside the gate, never a skipped
        # test: the check is recorded with selected=False so the PR body
        # and the console both say the suite did not run, and any diff
        # touching a single Python file runs it in full.
        if is_swift_only(changed):
            checks.append({
                "name": "pytest", "ok": True, "selected": False, "seconds": 0.0,
                "output": "not run — every changed path is under macos/, so the "
                          "diff contains no Python; no test under tests/ reads "
                          "macos/ (verified 2026-09-07)",
            })
            logger.info("selfedit_gate name=pytest ok=True seconds=0.0 selected=False "
                        "run_id=%s", self.run_id)
        else:
            t_gate = time.monotonic()
            code, out = self._run(
                [sys.executable, "-m", "pytest", "tests/unit", "-q"],
                cwd=self.tree, timeout=VALIDATE_PYTEST_TIMEOUT_S,
            )
            seconds = time.monotonic() - t_gate
            logger.info("selfedit_gate name=pytest ok=%s seconds=%.1f run_id=%s",
                        code == 0, seconds, self.run_id)
            checks.append({"name": "pytest", "ok": code == 0,
                           "output": out[-2000:] or "tests ok",
                           "seconds": round(seconds, 1)})

        ok = all(c["ok"] for c in checks)
        self._validated_ok = ok
        # SE6 — the PR body reports what actually ran (step 3). CI runs only
        # on pull requests to main, so when the base is a feature branch
        # these checks are the ONLY record of validation.
        self._last_checks = checks
        logger.info("selfedit_validate ok=%s run_id=%s", ok, self.run_id)
        return {"ok": ok, "checks": checks}

    # ---------------------------------------------------------- submit

    def submit(self) -> dict:
        """Commit, push the session branch, and open a PR. Never merges."""
        if self.branch is None:
            return {"ok": False, "error": "no active session"}
        if not self.proposals:
            return {"ok": False, "error": "no proposed edits in this session"}
        if not self._validated_ok:
            return {
                "ok": False,
                "error": "validation has not passed since the last edit — "
                         "run validate() and fix any failures first",
            }
        if not self._github_token:
            return {"ok": False, "error": "JARVIS_GITHUB_TOKEN is not set"}
        try:
            paths = [p["path"] for p in self.proposals]
            self._git_ok("add", "--", *paths)
            msg = f"self-edit: {_slugify(self.goal or 'change', 48)}"
            self._git_ok(
                "commit", "-m",
                msg + "\n\n" + (self.goal or "") + "\n\n" + _MERGE_NOTE,
            )
            self._git_ok("push", "-u", "origin", self.branch)
            self._git_ok("push", "origin", self.rollback_tag)
            pr = self._open_pr(msg)
        except SelfEditError as exc:
            return {"ok": False, "error": str(exc)}
        logger.info("selfedit_submit branch=%s pr=%s run_id=%s",
                    self.branch, pr.get("html_url"), self.run_id)
        capability = [p["path"] for p in self.proposals
                      if is_capability_path(p["path"])]
        core = [p["path"] for p in self.proposals if self.allowlist.is_core(p["path"])]
        result = {
            "ok": True,
            "branch": self.branch,
            "pr_url": pr.get("html_url"),
            "notice": _MERGE_NOTE,
        }
        if core:
            # Spoken by the developer when it reports the submit: the human
            # must HEAR that this PR touches the voice core and needs a
            # real run before merging.
            result["core_change"] = True
            result["core_paths"] = core
            result["notice"] = (
                "CORE CHANGE: this PR edits the voice pipeline or agent core ("
                + ", ".join(core)
                + ") — run the branch and hold a real conversation before "
                  "merging. " + _MERGE_NOTE
            )
        swift = [p["path"] for p in self.proposals if is_swift_path(p["path"])]
        if capability:
            # Spoken by the developer when it reports the submit — the
            # human must HEAR that this PR changes what agents can do, not
            # just find the block later on GitHub. Prepended so a PR that
            # is both core and capability announces both.
            result["capability_change"] = True
            result["notice"] = (
                "CAPABILITY CHANGE: this PR grants or rewires agent tools ("
                + ", ".join(capability)
                + ") — review those diffs line by line before merging. "
                + result["notice"]
            )
        if swift:
            # SE6 — the ONE manual step left in the loop. Prepended last so
            # it is the first thing spoken: a merged Swift change is inert
            # until the app is rebuilt, and a human who does not hear this
            # will report the self-edit as having done nothing.
            result["swift_change"] = True
            result["swift_paths"] = swift
            result["notice"] = (
                "SWIFT CHANGE: after merging, rebuild the app — cd "
                "macos/MortimerHost && scripts/bundle.sh — the running "
                "MortimerHost is the old binary until then. "
                + result["notice"]
            )
        # Session is complete: tear down the worktree + local branch. The
        # user's checkout is untouched — there is no `checkout main` here
        # any more, by design (module docstring).
        branch, tag = self.branch, self.rollback_tag
        self._remove_worktree(branch)
        self.branch = None
        self.rollback_tag = None
        self.run_id = None
        self.proposals = []
        self._validated_ok = False
        self._last_checks = []
        result["rollback_tag"] = tag
        return result

    def _open_pr(self, title: str) -> dict:
        body_lines = [
            f"**Goal:** {self.goal}",
            "",
            "**Proposed edits:**",
        ]
        for p in self.proposals:
            body_lines.append(f"- `{p['path']}` — {p['rationale']}")
        # Loudest first: core, then capability, then visual.
        # Loudest first: swift (needs an action), core, capability, visual.
        body_lines += self._swift_change_block()
        body_lines += self._core_change_block()
        body_lines += self._capability_change_block()
        body_lines += self._visual_change_block()
        body_lines += self._validation_block()
        body_lines += ["", "---", _MERGE_NOTE]
        req = urllib.request.Request(
            f"https://api.github.com/repos/{self._github_repo}/pulls",
            data=json.dumps({
                "title": title,
                "head": self.branch,
                "base": self.pr_base,
                "body": "\n".join(body_lines),
            }).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._github_token}",
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            raise SelfEditError(f"failed to open pull request: {exc}") from exc

    # ---------------------------------------------------------- revert

    def revert(self) -> dict:
        """Drop the session: remove its worktree and delete its branch.

        There is nothing to "restore" in the user's checkout because the
        session never touched it — the old `checkout main` + `reset --hard
        <tag>` is gone (it was what moved the user off their branch). The
        rollback tag stays as the record of the base the session was cut
        from."""
        if self.branch is None:
            return {"ok": False, "error": "no active session"}
        branch, tag = self.branch, self.rollback_tag
        self._remove_worktree(branch)
        logger.info("selfedit_revert branch=%s tag=%s run_id=%s", branch, tag, self.run_id)
        self.branch = None
        self.rollback_tag = None
        self.goal = None
        self.run_id = None
        self.proposals = []
        self._validated_ok = False
        self._last_checks = []
        return {"ok": True, "reverted_to": tag}

    def preflight(self, goal: str, has_plan: bool,
                  target_paths: list[str] | None = None) -> dict:
        """Tier pre-flight for a goal BEFORE it is staged
        (MORTIMER_SELFEDIT_TIERS_PLAN.md). Classifies the repo paths the
        edit will TOUCH — `target_paths` when the caller supplies them,
        otherwise the paths the goal text names; refuses a Tier-0 (denied)
        path outright and a Tier-B (core) path with no plan. Best-effort on
        extraction — a goal that names no files passes through (the
        planner's own allowlist check still governs every write). The
        point is to fail at the preview, in one sentence, instead of after
        confirm + staging + a planner run that discovers the same wall
        (2026-08-30: three runs).

        `target_paths` (2026-09-07 review, F5): prose cannot tell "edit
        jarvis/model_catalog.py" from "add a line ABOUT
        jarvis/model_catalog.py" — four previews were refused that day as
        Tier B for a docs-only edit that merely mentioned a core file, and
        a goal that named no path at all ("the macOS host console view
        script") walked a Tier-0 target straight past this gate. When the
        developer states the files the edit will change, those are what
        is classified and the prose is not consulted."""
        targets = [t.strip() for t in (target_paths or []) if t and t.strip()]
        paths = targets or extract_paths(goal)
        tiers = self.allowlist.classify(paths)
        result: dict = {"ok": True, "paths": paths, "tiers": tiers}
        # GC4 (gap-closure plan, 2026-09-04), WIDENED 2026-09-05: web/ is
        # frozen -- interface work goes to macos/MortimerHost now. Originally
        # this refused only a goal whose paths were ALL under web/, so a mixed
        # goal could still edit the deprecated client by naming one other file.
        # "Frozen except when bundled with other changes" is not frozen, and it
        # was the only reason validation still had to build web/ at all.
        # `any` over an empty list is False, so a goal naming no files still
        # passes through (test_goal_naming_no_files_passes_through); `result`
        # still carries `tiers` because jarvis/admin/server.py:795 reads
        # flight["tiers"] on refusal.
        if any(p == "web" or p.startswith("web/") for p in paths):
            result.update(ok=False, error=(
                "web/ is frozen (2026-09-04): interface work goes to "
                "macos/MortimerHost, which self-edit can change — name the "
                "Swift file in target_paths."
            ))
            return result
        if tiers["denied"]:
            result.update(ok=False, error=(
                "these files are human-only (Tier 0 — the self-edit loop's own "
                "machinery, secrets, dependencies or CI) and cannot be self-edited: "
                + ", ".join(tiers["denied"])
                + ". Ask Larry to make that change directly, or re-scope the "
                  "goal to the other files."
            ))
            return result
        if tiers["core"] and not has_plan:
            result.update(ok=False, error=(
                "this goal touches the voice/agent core (Tier B: "
                + ", ".join(tiers["core"])
                + "). Core edits need a plan document — draft one with "
                  "plan_start (or point at an existing docs/plans/ file) and "
                  "pass it as plan_path."
            ))
        return result

    def describe_boundary(self) -> str:
        """A human-readable statement of what this workspace will and
        won't let an edit touch — surfaced to a scope-advisor council
        round when the agent declines a goal
        (jarvis/agents/upgrade_agent.py's session_decline handling).
        Self-edit's boundary is its allowlist file, verbatim."""
        try:
            return (
                self.repo_root / "config" / "self_edit_allowlist.json"
            ).read_text(encoding="utf-8")
        except OSError:
            return "(allowlist file unavailable)"

    def status(self) -> dict:
        return {
            "active": self.branch is not None,
            "branch": self.branch,
            "rollback_tag": self.rollback_tag,
            "worktree": str(self.work_root) if self.work_root else None,
            "goal": self.goal,
            "run_id": self.run_id,
            "proposals": [
                {"path": p["path"], "rationale": p["rationale"], "diff": p["diff"]}
                for p in self.proposals
            ],
            "validated_ok": self._validated_ok,
        }
