"""WS-20 B4: scripts/check_roadmap.py, built from the real drift cases of 09-30 and 10-02."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "check_roadmap", Path(__file__).resolve().parents[2] / "scripts" / "check_roadmap.py")
cr = importlib.util.module_from_spec(SPEC)
sys.modules["check_roadmap"] = cr
SPEC.loader.exec_module(cr)

FIELDS = {
    "Owner": "`claude`", "Status": "landed", "Implemented by": "Claude",
    "Remaining work / acceptance": "None", "Model version": "not recorded",
    "Where": "main", "Plan": "none", "Scope": "—", "Next step": "None", "Updated": "10-02",
}


def block(ws: str, **over: str) -> str:
    fields = {**FIELDS, **over}
    body = "\n".join(f"- **{k}:** {v}" for k, v in fields.items())
    return f'<details id="ws-{ws}">\n<summary>WS-{ws} — test</summary>\n\n{body}\n\n</details>\n'


def roadmap(*blocks: str, production: str | None = None, changelog: str = "- 2026-10-02: entry\n") -> str:
    head = "# Mortimer master roadmap\n\n"
    if production:
        head += f"**Production:** {production}\n\n"
    return (head + "## 2. Workstreams\n\n### Needs work\n\n" + "\n".join(blocks)
            + "\n## 8. Change log\n\n" + changelog + "\n## 6. Recently landed\n")


def git(cwd: Path, *args: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t"}
    return subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True).stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "f").write_text("0")
    git(tmp_path, "add", "f")
    git(tmp_path, "commit", "-qm", "base")
    return tmp_path


def write(root: Path, text: str) -> None:
    (root / "ROADMAP.md").write_text(text, encoding="utf-8")


def messages(findings, level=None):
    return [f.text() for f in findings if level is None or f.level == level]


# ------------------------------------------------------------------ fields

def test_a_complete_row_with_a_lifecycle_status_is_clean(repo):
    write(repo, roadmap(block("07")))
    assert cr.run(repo, "main", None, False) == []


def test_missing_fields_are_errors():
    blocks = cr.parse_blocks(roadmap(block("07").replace("- **Scope:** —\n", "")))
    assert messages(cr.check_fields(blocks), "error") == ["WS-07: missing fields: Scope"]


@pytest.mark.parametrize("status", ["pending merged-pipeline acceptance", "open (Mac only)"])
def test_non_lifecycle_status_words_are_errors(status):
    # WS-10 and WS-11 on 10-02. An error, so the contract holds once CI drops
    # --warn-only (Codex review of #156); --warn-only still exits 0.
    found = cr.check_fields(cr.parse_blocks(roadmap(block("10", Status=status))))
    assert [f.level for f in found] == ["error"] and "not a lifecycle word" in found[0].message


@pytest.mark.parametrize("status", ["in-progress: CC7a.1 landed", "landed: claim PR #150 merged", "accepted: Larry",
                                    "review", "proposed"])
def test_lifecycle_words_with_detail_pass(status):
    assert cr.check_fields(cr.parse_blocks(roadmap(block("17", Status=status)))) == []


# ------------------------------------------------------------ merged branches

def merged_branch(repo: Path, branch: str, pr: int) -> None:
    git(repo, "checkout", "-qb", branch)
    (repo / "g").write_text(branch)
    git(repo, "add", "g")
    git(repo, "commit", "-qm", "work")
    git(repo, "checkout", "-q", "main")
    git(repo, "merge", "-q", "--no-ff", "-m", f"Merge pull request #{pr} from owner/{branch}", branch)


def test_open_row_on_a_merged_branch_is_an_error(repo):
    # WS-18 on 09-30: "review" with branch ws18/audio-output-switch already merged as #144.
    merged_branch(repo, "ws18/audio-output-switch", 144)
    write(repo, roadmap(block("18", Status="review: fix in PR", Where="branch `ws18/audio-output-switch`")))
    found = cr.run(repo, "main", None, False)
    assert len(messages(found, "error")) == 1
    assert "ws18/audio-output-switch is already merged" in found[0].message and "PR #144" in found[0].message


def test_without_the_ref_a_merged_pr_is_a_question_not_a_verdict(repo):
    # codex/isolated-20260924 merged once as #103 and later got unmerged commits;
    # a checkout without branch refs cannot tell, so it warns instead of erring.
    merged_branch(repo, "codex/ws04-local-onboarding-20260930", 149)
    git(repo, "branch", "-q", "-D", "codex/ws04-local-onboarding-20260930")
    write(repo, roadmap(block("04", Status="in-progress: R2", Where="`codex/ws04-local-onboarding-20260930`")))
    found = cr.run(repo, "main", None, False)
    assert [f.level for f in found] == ["warning"]
    assert "still in use" in found[0].message and "PR #149" in found[0].message


def test_a_branch_merged_once_and_extended_since_is_open(repo):
    merged_branch(repo, "codex/isolated-20260924", 103)
    git(repo, "checkout", "-q", "codex/isolated-20260924")
    (repo / "later").write_text("MAR-A baseline")
    git(repo, "add", "later")
    git(repo, "commit", "-qm", "addf278 stand-in")
    git(repo, "checkout", "-q", "main")
    write(repo, roadmap(block("05", Status="claimed", Where="`codex/isolated-20260924`")))
    assert cr.run(repo, "main", None, False) == []


def test_unmerged_branch_and_landed_rows_are_fine(repo):
    git(repo, "branch", "-q", "codex/isolated-20260924")
    git(repo, "checkout", "-q", "codex/isolated-20260924")
    (repo / "h").write_text("x")
    git(repo, "add", "h")
    git(repo, "commit", "-qm", "unmerged")
    git(repo, "checkout", "-q", "main")
    merged_branch(repo, "fix/ws07-bot-text-once", 154)
    write(repo, roadmap(block("05", Status="claimed", Where="`codex/isolated-20260924`"),
                        block("07", Status="landed", Where="main; was `fix/ws07-bot-text-once`")))
    assert messages(cr.run(repo, "main", None, False), "error") == []


# --------------------------------------------------------------- production

PHRASES = [
    ("landed; deployed since `539f8f6` and present in production `39fc6f9`", "present in production"),
    ("landed in PR #144 (`c2f0f49`); not in verified production `39fc6f9`", "not in verified production"),
    ("in-progress: merged but not deployed in production `39fc6f9`", "not deployed in production"),
    ("landed; still in production `03b9e60`", "still in production"),
]


@pytest.mark.parametrize("status,phrase", PHRASES)
def test_current_production_claims_warn_before_the_production_line_exists(status, phrase):
    found = cr.check_production_phrases(cr.parse_blocks(roadmap(block("02", Status=status))), has_line=False)
    assert [f.level for f in found] == ["warning"] and phrase in found[0].message


def test_they_become_errors_once_the_production_line_exists():
    found = cr.check_production_phrases(cr.parse_blocks(roadmap(block("02", Status=PHRASES[0][0]))), has_line=True)
    assert [f.level for f in found] == ["error"]


@pytest.mark.parametrize("status", ["landed in #144 (`c2f0f49`)", "deployed in `39fc6f9` on 09-30",
                                    "accepted: Larry on the Mac 2026-09-30, production `03b9e60`"])
def test_event_wording_is_not_flagged(status):
    assert cr.check_production_phrases(cr.parse_blocks(roadmap(block("15", Status=status))), True) == []


def receipt(directory: Path, sha: str, when: str = "2026-10-02T15:51:04-04:00", status: str = "deployed") -> None:
    directory.mkdir(exist_ok=True)
    (directory / f"deployment-receipt-{sha[:7]}.json").write_text(
        json.dumps({"status": status, "main_revision": sha, "deployed_at": when}))


def test_production_line_must_match_the_newest_receipt(tmp_path):
    logs = tmp_path / "logs"
    receipt(logs, "7c4637e" + "0" * 33)
    text = roadmap(block("07"), production="`39fc6f9`, deployed 2026-09-30 17:59 (receipt x)")
    found = cr.check_receipt(text, cr.parse_blocks(text), logs)
    assert len(found) == 1 and "newest receipt is 7c4637e" in found[0].message
    text = roadmap(block("07"), production="`7c4637e`, deployed 2026-10-02 15:51 (receipt x)")
    assert cr.check_receipt(text, cr.parse_blocks(text), logs) == []


def test_a_row_naming_an_old_production_build_is_caught_by_the_receipt(tmp_path):
    # WS-02/09/10/11 named 03b9e60 after 39fc6f9 deployed (09-30).
    logs = tmp_path / "logs"
    receipt(logs, "39fc6f9" + "0" * 33)
    text = roadmap(block("09", Status="landed and still in production `03b9e60`"))
    found = messages(cr.check_receipt(text, cr.parse_blocks(text), logs), "error")
    assert found == ["WS-09: Status names production `03b9e60`; newest receipt is 39fc6f9 deployed 2026-10-02T15:51:04-04:00"]


def test_newest_means_latest_deployed_at_not_file_time(tmp_path):
    logs = tmp_path / "logs"
    receipt(logs, "7c4637e" + "0" * 33, when="2026-10-02T15:51:04-04:00")
    receipt(logs, "39fc6f9" + "0" * 33, when="2026-09-30T17:59:25-04:00")  # written last, older deploy
    assert cr.newest_receipt(logs)[0].startswith("7c4637e")


def test_failed_receipts_are_skipped(tmp_path):
    logs = tmp_path / "logs"
    receipt(logs, "aaaaaaa" + "0" * 33, status="failed")
    assert "no deployed receipt" in cr.check_receipt(roadmap(block("07")), [], logs)[0].message


# ------------------------------------------------------------------- PR age

def test_old_prs_need_a_next_step():
    now = datetime(2026, 10, 2, 19, 0, tzinfo=timezone.utc)
    blocks = cr.parse_blocks(roadmap(block("08", **{"Next step": "codex: resolve PR #142 and land it"})))
    prs = [{"number": 142, "title": "WS-08", "createdAt": "2026-09-30T21:00:00Z"},
           {"number": 138, "title": "CX-15", "createdAt": "2026-09-30T17:40:00Z"},
           {"number": 155, "title": "new", "createdAt": (now - timedelta(hours=3)).isoformat()}]
    assert messages(cr.pr_age_findings(prs, blocks, now)) == ["PR #138: open 2 days and no row's Next step names it (CX-15)"]


# --------------------------------------------------------------- change log

def test_changelog_checks_wait_for_the_marker(tmp_path):
    text = roadmap(block("07"), changelog="- 2026-10-02: mentions docs/roadmap-log/ in passing\n")
    assert cr.check_changelog(text, tmp_path) == []


def test_after_the_move_entries_in_section_8_and_bad_log_files_are_errors(tmp_path):
    text = roadmap(block("07"), changelog=f"{cr.LOG_MARKER}\n\n- 2026-10-03: added here by mistake\n")
    log = tmp_path / cr.LOG_DIR
    log.mkdir(parents=True)
    (log / "2026-10-03-ws-07-claude-ok.md").write_text("---\ndate: 2026-10-03\nsystem: claude\nrows: WS-07\nprs: [156]\n---\ntext\n")
    (log / "2026-10-03-ws-07-codex-no-pr.md").write_text("---\ndate: 2026-10-03\nsystem: codex\nrows: WS-07\nprs: []\n---\nno PR\n")
    (log / "2026-10-03-ws-07-codex-no-prs-key.md").write_text("---\ndate: 2026-10-03\nsystem: codex\nrows: WS-07\n---\n")
    (log / "2026-10-03-ws-99-codex-bad.md").write_text("---\ndate: 2026-10-03\nsystem: codex\nrows: WS-99\nprs: []\n---\n")
    (log / "no-front-matter.md").write_text("just text\n")
    found = messages(cr.check_changelog(text, tmp_path), "error")
    assert found == [
        "§8: 1 entries in ROADMAP.md §8; add a file under docs/roadmap-log/ instead",
        "docs/roadmap-log/2026-10-03-ws-07-codex-no-prs-key.md: front matter lacks prs",
        "docs/roadmap-log/2026-10-03-ws-99-codex-bad.md: names WS-99, which ROADMAP.md does not define",
        "docs/roadmap-log/no-front-matter.md: no front matter",
    ]


# --------------------------------------------------------------------- ids

def test_duplicate_and_undefined_ids():
    text = roadmap(block("07"), block("07")) + "\nSee WS-42.\n"
    found = cr.check_ids(text, cr.parse_blocks(text))
    assert [f.level for f in found] == ["error", "warning"]
    assert "defined twice" in found[0].message and found[1].where == "WS-42"


# --------------------------------------------------------------------- CLI

def test_warn_only_reports_but_exits_zero(repo, capsys):
    merged_branch(repo, "ws18/audio-output-switch", 144)
    write(repo, roadmap(block("18", Status="review", Where="`ws18/audio-output-switch`")))
    assert cr.main(["--root", str(repo), "--main", "main"]) == 1
    assert cr.main(["--root", str(repo), "--main", "main", "--warn-only"]) == 0
    assert "1 errors" in capsys.readouterr().out


def test_the_real_roadmap_parses_into_complete_blocks():
    root = Path(__file__).resolve().parents[2]
    text = (root / "ROADMAP.md").read_text(encoding="utf-8")
    blocks = cr.parse_blocks(text)
    assert len(blocks) >= 18
    # Structure only: lifecycle wording is a reported error the roadmap's
    # owners fix (warn-only in CI for now), not a reason to fail this suite.
    assert [m for m in messages(cr.check_fields(blocks), "error") if "missing fields" in m] == []
