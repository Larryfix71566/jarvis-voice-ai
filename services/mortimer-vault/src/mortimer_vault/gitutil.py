"""Thin wrapper around the system git binary (§2, §6.2). No GitPython."""
from __future__ import annotations

import subprocess
from pathlib import Path

AUTHOR = "Mortimer Vault <vault@mortimer.local>"


def _run(repo: Path, args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )


def ensure_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    if not (repo / ".git").exists():
        _run(repo, ["init", "-q"])
        gitignore = repo / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text(".obsidian/\n*.tmp\n")
        _run(repo, ["add", ".gitignore"])
        commit(repo, "vault: initialize repository")


def commit(repo: Path, message: str, paths: list[str] | None = None) -> None:
    if paths:
        _run(repo, ["add", *paths])
    else:
        _run(repo, ["add", "-A"])
    # Nothing to commit is not an error in our flows (idempotent .gitignore init etc.)
    result = subprocess.run(
        [
            "git",
            "-c",
            f"user.name={AUTHOR.split('<')[0].strip()}",
            "-c",
            f"user.email={AUTHOR.split('<')[1].rstrip('>')}",
            "commit",
            "-q",
            "-m",
            message,
            "--author",
            AUTHOR,
            "--allow-empty-message",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 and "nothing to commit" not in (result.stdout + result.stderr):
        raise RuntimeError(f"git commit failed: {result.stderr}")


def rm(repo: Path, path: str, message: str) -> None:
    _run(repo, ["rm", "-q", path])
    commit(repo, message)


def head(repo: Path) -> str | None:
    try:
        result = _run(repo, ["rev-parse", "HEAD"])
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None
