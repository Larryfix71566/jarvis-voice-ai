"""Self-edit service: the sandboxed "hands" of the self-development loop (plan section 3).

Implements exactly four write operations plus status/revert. The Upgrade
Agent (jarvis/agents/upgrade_agent.py) is the only intended client; the LLM
behind it never gets shell or raw git access.

Locked invariants (plan section 1):
- main is never touched: every operation works on a session branch named
  jarvis/self-edit/<yyyymmdd>-<slug> created from origin/main.
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
BUILD_TIMEOUT_S = 600
VALIDATE_PYTEST_TIMEOUT_S = 900  # 2026-09-04: 2,150+ tests; the self-edit
# run that convened council round e48cfbe1 timed out here at 300 s
# (gap-closure plan GC1b). CI runs the same command with no timeout.
SESSION_BRANCH_PREFIX = "jarvis/self-edit"
ROLLBACK_TAG_PREFIX = "pre-selfedit"
DEFAULT_BASE_REF = "origin/main"
# Session worktrees live under data/ — already self-edit-denied and
# gitignored (data/selfedit_worktrees/ joins .gitignore explicitly), the
# same home AppWorkspace uses for foreign repos (data/app_workspaces/).
WORKTREES_DIR = Path("data") / "selfedit_worktrees"

MAX_FILE_BYTES = 200_000  # refuse oversized writes

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
VISUAL_PATH_PREFIXES = ("web/src/", "web/public/")


def is_visual_path(path: str) -> bool:
    return str(path).replace("\\", "/").startswith(VISUAL_PATH_PREFIXES)


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
        base_ref: str = DEFAULT_BASE_REF,
    ):
        self.repo_root = Path(repo_root) if repo_root else _repo_root()
        al_path = Path(allowlist_path) if allowlist_path else (
            self.repo_root / "config" / "self_edit_allowlist.json"
        )
        self.allowlist = Allowlist.load(al_path)
        self.base_ref = base_ref
        self._github_token = github_token or os.environ.get("JARVIS_GITHUB_TOKEN")
        self._github_repo = github_repo or os.environ.get(
            "JARVIS_GITHUB_REPO", "Larryfix71566/jarvis-voice-ai"
        )
        # Active session state (None when no session).
        self.branch: str | None = None
        self.rollback_tag: str | None = None
        self.goal: str | None = None
        self.proposals: list[dict] = []
        self._validated_ok = False
        # The session's isolated worktree (None when no session). Every
        # file read/write and every git command that concerns the SESSION
        # runs here; the user's checkout (repo_root) is only ever used for
        # shared-repo operations (fetch, tag, worktree add/remove, branch
        # -D) and for verify_appearance's "what is the human running"
        # question.
        self.work_root: Path | None = None

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
                argv, cwd=cwd, capture_output=True, text=True, timeout=timeout
            )
            return proc.returncode, (proc.stdout + proc.stderr).strip()[-4000:]
        except FileNotFoundError as exc:
            return 127, str(exc)
        except subprocess.TimeoutExpired:
            return 124, f"timed out after {timeout}s"

    # ---------------------------------------------------------- session

    def start_session(self, goal: str) -> dict:
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
            self._git_ok("fetch", "origin", "main", cwd=root)
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
        self.proposals = []
        self._validated_ok = False
        logger.info("selfedit_session_start branch=%s tag=%s worktree=%s", branch, tag, path)
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
        _c, names = self._git("diff", "--name-only", self.base_ref, "--", ".")
        changed = [n for n in names.splitlines() if n.strip()]
        violations = self.allowlist.filter_violations(changed)
        core_changed = self.allowlist.core_paths(changed)
        checks.append({
            "name": "allowlist",
            "ok": not violations,
            "output": ("all changed files allowed"
                       if not violations else "forbidden: " + ", ".join(violations))
                      + (f" · core (Tier B): {', '.join(core_changed)}" if core_changed else ""),
        })

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
        code, out = self._run(
            [sys.executable, "-c", "import jarvis, jarvis.config, jarvis.cli"],
            cwd=self.tree, timeout=120,
        )
        checks.append({"name": "backend_imports", "ok": code == 0,
                       "output": out or "imports ok"})

        # 2b. Tier B (core) — the fifth gate, only when a core path changed
        # (MORTIMER_SELFEDIT_TIERS_PLAN.md): the voice pipeline and the agent
        # roster must still IMPORT. A broken pipeline construct is the one
        # failure the plain `import jarvis` smoke never sees, and it is
        # exactly what a jarvis/bot or jarvis/agents edit can break.
        if core_changed:
            code, out = self._run(
                [sys.executable, "-c", CORE_IMPORT_SMOKE],
                cwd=self.tree, timeout=180,
            )
            checks.append({"name": "core_imports", "ok": code == 0,
                           "output": out[-2000:] or "core imports ok",
                           "paths": core_changed})

        # 3. Frontend build.
        web_dir = self.tree / "web"
        code, out = self._run(["npm", "ci"], cwd=web_dir, timeout=BUILD_TIMEOUT_S)
        if code == 0:
            code, out = self._run(["npm", "run", "build"], cwd=web_dir,
                                  timeout=BUILD_TIMEOUT_S)
        checks.append({"name": "frontend_build", "ok": code == 0,
                       "output": out[-2000:] or "build ok"})

        # 4. Backend unit tests (C2, MORTIMER_MODEL_DISCIPLINE_AND_MAC_SHELL_PLAN.md).
        # CI's own pytest step is a hard gate now for the same reason — a
        # self-edit that imports cleanly and builds the frontend can still
        # break backend behavior; only the test suite catches that.
        code, out = self._run(
            [sys.executable, "-m", "pytest", "tests/unit", "-q"],
            cwd=self.tree, timeout=VALIDATE_PYTEST_TIMEOUT_S,
        )
        checks.append({"name": "pytest", "ok": code == 0,
                       "output": out[-2000:] or "tests ok"})

        ok = all(c["ok"] for c in checks)
        self._validated_ok = ok
        logger.info("selfedit_validate ok=%s", ok)
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
        logger.info("selfedit_submit branch=%s pr=%s", self.branch, pr.get("html_url"))
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
        # Session is complete: tear down the worktree + local branch. The
        # user's checkout is untouched — there is no `checkout main` here
        # any more, by design (module docstring).
        branch, tag = self.branch, self.rollback_tag
        self._remove_worktree(branch)
        self.branch = None
        self.rollback_tag = None
        self.proposals = []
        self._validated_ok = False
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
        body_lines += self._core_change_block()
        body_lines += self._capability_change_block()
        body_lines += self._visual_change_block()
        body_lines += ["", "---", _MERGE_NOTE]
        req = urllib.request.Request(
            f"https://api.github.com/repos/{self._github_repo}/pulls",
            data=json.dumps({
                "title": title,
                "head": self.branch,
                "base": "main",
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
        logger.info("selfedit_revert branch=%s tag=%s", branch, tag)
        self.branch = None
        self.rollback_tag = None
        self.goal = None
        self.proposals = []
        self._validated_ok = False
        return {"ok": True, "reverted_to": tag}

    def preflight(self, goal: str, has_plan: bool) -> dict:
        """Tier pre-flight for a goal BEFORE it is staged
        (MORTIMER_SELFEDIT_TIERS_PLAN.md). Classifies the repo paths the
        goal text names; refuses a Tier-0 (denied) path outright and a
        Tier-B (core) path with no plan. Best-effort on extraction — a goal
        that names no files passes through (the planner's own allowlist
        check still governs every write). The point is to fail at the
        preview, in one sentence, instead of after confirm + staging + a
        planner run that discovers the same wall (2026-08-30: three runs)."""
        paths = extract_paths(goal)
        tiers = self.allowlist.classify(paths)
        result: dict = {"ok": True, "paths": paths, "tiers": tiers}
        # GC4 (gap-closure plan, 2026-09-04): web/ is frozen -- interface work
        # goes to macos/MortimerHost now. `paths and` keeps a goal naming no
        # files passing through (test_goal_naming_no_files_passes_through);
        # `result` still carries `tiers` because jarvis/admin/server.py:795
        # reads flight["tiers"] on refusal.
        if paths and all(p == "web" or p.startswith("web/") for p in paths):
            result.update(ok=False, error=(
                "web/ is frozen (2026-09-04): interface work goes to "
                "macos/MortimerHost, which is a human PR."
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
            "proposals": [
                {"path": p["path"], "rationale": p["rationale"], "diff": p["diff"]}
                for p in self.proposals
            ],
            "validated_ok": self._validated_ok,
        }
