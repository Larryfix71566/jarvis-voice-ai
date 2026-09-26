"""T2.3 — log_search()."""

from __future__ import annotations

import inspect
from datetime import datetime

import pytest

from jarvis.status import logs as L
from jarvis.status.logs import LOG_SOURCES, log_search

NOW = datetime(2026, 9, 22, 12, 0, 0)
KEY = "sk-ant-api03-FIXTUREKEYVALUE0123456789"


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(L, "_now", lambda: NOW)
    (tmp_path / "logs").mkdir()
    return tmp_path


def _write(repo, source, lines):
    path = repo / LOG_SOURCES[source]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


FIXTURE = [
    "2026-09-22 09:00:00,001 INFO jarvis.bot old line far outside the window",
    "2026-09-22 11:30:00,123 INFO jarvis.bot session_connect id=1",
    "  continuation line without a timestamp",
    "[11:31:02] USER: my bank password is hunter2",
    "[11:31:05] MORTIMER: noted",
    "2026-09-22 11:32:00.456 DEBUG pipecat Generating chat from context [{'role': 'system'}]",
    f"2026-09-22 11:33:00 INFO key_health key={KEY} Authorization: Bearer abc.def.ghi",
    "2026-09-22 11:34:00 INFO probe x-api-key=supersecretvalue header",
    "2026-09-22 11:35:00 INFO token " + "A1b2" * 12,
    "2026-09-22 11:36:00 INFO commit " + "f" * 40,
    "2026-09-22 11:40:00 WARNING jarvis.bot session_disconnect id=1 " + "x " * 300,
]


def test_log_search_has_no_path_parameter():
    params = inspect.signature(log_search).parameters
    assert list(params) == ["source", "query", "since_minutes", "limit"]
    assert not any("path" in p or "file" in p for p in params)


def test_unknown_source_is_an_error(repo):
    out = log_search("../../etc/passwd", "")
    assert out["ok"] is False
    assert "unknown log source" in out["error"]


def test_missing_file(repo):
    out = log_search("bot", "")
    assert out == {"ok": False, "error": "no log file yet for source 'bot'"}


def test_window_and_inheritance(repo):
    _write(repo, "bot", FIXTURE)
    out = log_search("bot", "", since_minutes=60)
    assert out["ok"] is True
    text = "\n".join(out["lines"])
    assert "old line far outside" not in text
    assert "session_connect" in text
    assert "continuation line" in text            # inherits 11:30
    out = log_search("bot", "", since_minutes=180)
    assert "old line far outside" in "\n".join(out["lines"])


def test_conversation_lines_always_dropped(repo):
    _write(repo, "bot", FIXTURE)
    text = "\n".join(log_search("bot", "", since_minutes=600)["lines"])
    assert "USER:" not in text and "MORTIMER:" not in text
    assert "hunter2" not in text
    assert log_search("bot", "hunter2", since_minutes=600)["lines"] == []


def test_log_search_drops_llm_context_lines(repo):
    _write(repo, "bot", FIXTURE)
    text = "\n".join(log_search("bot", "", since_minutes=600)["lines"])
    assert "Generating chat from context" not in text


def test_log_search_redacts_keys(repo):
    _write(repo, "bot", FIXTURE)
    out = log_search("bot", "", since_minutes=600)
    text = "\n".join(out["lines"])
    assert KEY not in text
    assert "FIXTUREKEYVALUE" not in text
    assert "sk-…" in text
    assert "Bearer <redacted>" in text
    assert "abc.def.ghi" not in text
    assert "x-api-key <redacted>" in text
    assert "supersecretvalue" not in text
    assert "A1b2" * 12 not in text
    assert "f" * 40 not in text
    # A query for the key finds nothing (no oracle), and is not echoed.
    probe = log_search("bot", KEY, since_minutes=600)
    assert probe["lines"] == []
    assert KEY not in str(probe)


def test_query_filter_is_case_insensitive(repo):
    _write(repo, "bot", FIXTURE)
    out = log_search("bot", "SESSION_CONNECT", since_minutes=600)
    assert len(out["lines"]) == 1
    assert "session_connect" in out["lines"][0]


def test_truncation_and_limit(repo):
    _write(repo, "bot", FIXTURE)
    out = log_search("bot", "", since_minutes=600, limit=2)
    assert len(out["lines"]) == 2
    assert all(len(l) <= 300 for l in out["lines"])
    assert "session_disconnect" in out["lines"][-1]
    lines = [f"2026-09-22 11:{m:02d}:00 INFO line {m}" for m in range(0, 59)] * 5
    _write(repo, "admin", lines)
    assert len(log_search("admin", "", since_minutes=600, limit=10_000)["lines"]) == 200


def test_reads_at_most_last_5mb(repo, monkeypatch):
    monkeypatch.setattr(L, "MAX_READ_BYTES", 200)
    lines = ["2026-09-22 11:50:00 INFO early-marker"] + [
        f"2026-09-22 11:55:{i % 60:02d} INFO filler {i}" for i in range(40)]
    _write(repo, "bot", lines)
    out = log_search("bot", "", since_minutes=60, limit=200)
    assert out["clipped_to_last_5mb"] is True
    assert "early-marker" not in "\n".join(out["lines"])
    assert all(l.startswith("2026-09-22") for l in out["lines"])  # no partial first line


def test_every_source_is_under_logs():
    for rel in LOG_SOURCES.values():
        assert rel.startswith("logs/") and ".." not in rel


@pytest.mark.parametrize("line,secret", [
    ("token=ghp_" + "a1B2c3D4e5" * 4, "a1B2c3D4e5" * 4),
    ("using gho_" + "Z9y8X7w6V5" * 3 + " for oauth", "Z9y8X7w6V5" * 3),
    ("ghs_" + "Qq11Ww22Ee33Rr44Tt55" + " app token", "Qq11Ww22Ee33Rr44Tt55"),
    ("GITHUB_TOKEN=github_pat_11ABCDEFG0_" + "xYz123" * 4, "xYz123" * 4),
    ("TAVILY_API_KEY=tvly-dev-AbC123xyz", "AbC123xyz"),
    ("Authorization: token hunter2secret", "hunter2secret"),
    ("authorization: Basic dXNlcjpwYXNz", "dXNlcjpwYXNz"),
    ("fetching https://larry:s3cretPass@github.com/x/y.git", "s3cretPass"),
    ("remote postgres://svc:pw-9876@db.local:5432/app", "pw-9876"),
])
def test_redact_covers_github_tavily_authorization_and_url_userinfo(line, secret):
    """Review finding 6 (I1): each of these formats reached log_search
    output verbatim."""
    from jarvis.status.logs import redact

    out = redact(line)
    assert secret not in out, out
    assert "<redacted>" in out or "sk-…" in out, out


def test_redact_leaves_ordinary_urls_alone():
    from jarvis.status.logs import redact

    line = "GET https://api.github.com/repos/x/y/pulls?page=2 took 120ms"
    assert redact(line) == line
