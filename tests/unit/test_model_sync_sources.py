"""Tests for jarvis.model_sync.sources (no network)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from jarvis.model_sync import sources

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "model_sync"


def fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


FILES = {
    "anthropic_release_notes": "anthropic-release-notes-feed.xml",
    "anthropic_deprecations": "anthropic-model-deprecations.md",
    "codex_changelog": "openai-codex-changelog.md",
    "codex_models": "openai-codex-models.md",
    "kimi_changelog": "kimi-platform-changelog.md",
    "npm_claude_code": "npm-claude-code-latest.json",
    "npm_codex": "npm-codex-latest.json",
}


def fake_fetch(name: str) -> str:
    return fx(FILES[name])


def test_allowlist_exact():
    assert sources.PUBLIC_SOURCES["npm_claude_code"] == "https://registry.npmjs.org/@anthropic-ai/claude-code/latest"
    assert sources.PUBLIC_SOURCES["npm_codex"] == "https://registry.npmjs.org/@openai/codex/latest"
    assert len(sources.PUBLIC_SOURCES) == 7


def test_fetch_refuses_unknown_name():
    with pytest.raises(ValueError):
        sources.fetch_public("https://example.com/")
    with pytest.raises(ValueError):
        sources.fetch_public("nope")


class _Resp:
    def __init__(self, status, body):
        self.status, self._body = status, body

    def read(self, n=-1):
        return self._body if n < 0 else self._body[:n]


def _conn_factory(status, body, seen):
    class Conn:
        def __init__(self, host, timeout=None, context=None):
            seen["host"], seen["timeout"] = host, timeout

        def request(self, method, path, headers=None):
            seen["req"] = (method, path, headers)

        def getresponse(self):
            return _Resp(status, body)

        def close(self):
            seen["closed"] = True
    return Conn


def test_fetch_non_200_refused(monkeypatch):
    seen: dict = {}
    monkeypatch.setattr(sources.http.client, "HTTPSConnection", _conn_factory(302, b"", seen))
    with pytest.raises(ValueError):
        sources.fetch_public("npm_codex")
    assert seen["closed"]


def test_fetch_ok_path_and_headers(monkeypatch):
    seen: dict = {}
    monkeypatch.setattr(sources.http.client, "HTTPSConnection", _conn_factory(200, "é".encode(), seen))
    assert sources.fetch_public("npm_codex", timeout=3) == "é"
    assert seen["host"] == "registry.npmjs.org" and seen["timeout"] == 3
    method, path, headers = seen["req"]
    assert (method, path) == ("GET", "/@openai/codex/latest")
    assert headers["User-Agent"] == "Mortimer-model-sync/1"


def test_fetch_size_cap(monkeypatch):
    seen: dict = {}
    body = b"x" * (sources.MAX_BYTES + 1)
    monkeypatch.setattr(sources.http.client, "HTTPSConnection", _conn_factory(200, body, seen))
    with pytest.raises(ValueError):
        sources.fetch_public("npm_codex")


def test_anthropic_feed_real_fixture():
    rows = sources.parse_anthropic_feed(fx("anthropic-release-notes-feed.xml"))
    launches = {r["model"]: r["date"] for r in rows if r["kind"] == "launch"}
    assert launches["claude-fable-5-2"] == "2026-11-09"
    assert launches["claude-haiku-5-5"] == "2026-10-07"
    assert launches["claude-sonnet-5-5"] == "2026-09-28"
    assert launches["claude-opus-5-5"] == "2026-09-22"
    assert all(r["vendor"] == "anthropic" and r["source"] == "anthropic_release_notes" for r in rows)
    assert len({(r["model"], r["kind"]) for r in rows}) == len(rows)
    # the fast-mode deprecation names opus 4.8 without launching it on that date
    assert not any(r["model"] == "claude-opus-4-8" and r["kind"] == "launch" and r["date"] == "2026-10-30"
                   for r in rows)


def test_anthropic_feed_truncated_and_junk():
    xml = fx("anthropic-release-notes-feed.xml")
    cut = xml[: xml.index("2026 00:00:00 GMT</pubDate>", 3000) + 200]
    assert sources.parse_anthropic_feed(cut)  # no raise, still yields rows
    for junk in ("", "<rss>", None, 5, "<item><pubDate>garbage</pubDate><description>x</description></item>"):
        assert sources.parse_anthropic_feed(junk) == []


def test_deprecations_real_fixture():
    rows = {r["model"]: r for r in sources.parse_anthropic_deprecations(fx("anthropic-model-deprecations.md"))}
    s = rows["claude-sonnet-4-5-20250929"]
    assert s["state"] == "deprecated" and s["deprecated"] == "2026-09-30"
    assert s["retirement"] == "2026-11-30" and s["replacement"] == "claude-sonnet-5-5"
    assert s["earliest_retirement"] is None and s["source"] == "anthropic_deprecations"
    f = rows["claude-fable-5"]
    assert f["state"] == "active" and f["retirement"] is None
    assert f["earliest_retirement"] == "2027-06-09" and f["deprecated"] is None
    assert rows["claude-mythos-preview"]["retirement"] is None
    assert rows["claude-mythos-preview"]["state"] == "deprecated"
    assert rows["claude-opus-4-1-20250805"]["state"] == "retired"
    assert rows["claude-opus-4-1-20250805"]["replacement"] == "claude-opus-4-8"


def test_deprecations_junk():
    assert sources.parse_anthropic_deprecations("") == []
    assert sources.parse_anthropic_deprecations(None) == []
    assert sources.parse_anthropic_deprecations("| a | b |\n| - | - |") == []


def test_openai_changelog_synthetic():
    out = sources.parse_openai_changelog(fx("openai-codex-changelog.md"))
    launches = {r["model"]: r for r in out["launches"]}
    assert launches["gpt-6.2-sol"]["date"] == "2026-11-20"
    assert launches["gpt-6.2-astra"]["date"] == "2026-11-20"
    assert launches["gpt-6.1-terra"]["kind"] == "launch"
    assert "gpt-5.3-codex" in launches and "gpt-6.2-luna" in launches
    assert launches["gpt-6-astra"]["date"] == "2026-09-15"
    assert launches["gpt-6.2-sol"]["vendor"] == "openai"
    ret = {r["model"]: r for r in out["retirements"]}
    assert ret["gpt-5.5"]["retirement"] == "2026-10-14"
    assert "gpt-6.2-sol" not in ret  # the replacement is not retired


def test_openai_inline_date_needs_year_hint():
    text = "Codex 0.171.0 (Nov 20): Added GPT-6.2 Sol and Astra to model catalogs, with Sol as the default"
    assert {r["date"] for r in sources.parse_openai_changelog(text)["launches"]} == {None}
    got = sources.parse_openai_changelog(text, default_year=2026)["launches"]
    assert {r["model"] for r in got} == {"gpt-6.2-sol", "gpt-6.2-astra"}
    assert {r["date"] for r in got} == {"2026-11-20"}


def test_openai_list_expansion():
    out = sources.parse_openai_changelog("Added GPT-6 Astra, Sol and Terra to the catalog.")
    assert {r["model"] for r in out["launches"]} == {"gpt-6-astra", "gpt-6-sol", "gpt-6-terra"}


def test_openai_models_page():
    rows = sources.parse_openai_models(fx("openai-codex-models.md"))
    assert {r["model"] for r in rows} == {"gpt-6.2-sol", "gpt-6-astra", "gpt-5.3-codex"}
    assert all(r["kind"] == "listed" for r in rows)


def test_openai_junk():
    assert sources.parse_openai_changelog("") == {"launches": [], "retirements": []}
    assert sources.parse_openai_changelog(None) == {"launches": [], "retirements": []}
    assert sources.parse_openai_models(None) == []


def test_kimi_changelog():
    rows = {r["model"]: r for r in sources.parse_kimi_changelog(fx("kimi-platform-changelog.md"))}
    assert rows["kimi-k3.1-pro"]["date"] == "2026-11-12"
    assert rows["kimi-k2.7-code"]["date"] == "2026-11-03"
    assert rows["kimi-k2.7-code"]["kind"] == "launch" and rows["kimi-k2.7-code"]["vendor"] == "moonshot"
    assert sources.parse_kimi_changelog(None) == []


def test_npm_latest():
    assert sources.parse_npm_latest(fx("npm-claude-code-latest.json")) == "2.1.330"
    assert sources.parse_npm_latest(fx("npm-codex-latest.json")) == "0.171.0"
    assert sources.parse_npm_latest('{"version": "latest"}') is None
    assert sources.parse_npm_latest("not json") is None
    assert sources.parse_npm_latest("[]") is None


NOW = datetime(2026, 11, 23, 6, 30, tzinfo=timezone.utc)


def test_collect_public_all_ok():
    out = sources.collect_public(fetch=fake_fetch, now=NOW)
    assert set(out["sources"]) == set(sources.PUBLIC_SOURCES)
    for st in out["sources"].values():
        assert st["ok"] and st["error"] is None and len(st["sha256"]) == 64
        assert st["fetched_at"].startswith("2026-11-23T06:30:00")
    assert out["cli_latest"] == {"claude": "2.1.330", "codex": "0.171.0"}
    keys = [(r["model"], r["source"]) for r in out["launches"]]
    assert len(keys) == len(set(keys))
    assert ("claude-fable-5-2", "anthropic_release_notes") in keys
    assert ("gpt-6.2-sol", "codex_changelog") in keys
    assert ("gpt-6.2-sol", "codex_models") in keys
    assert ("kimi-k3.1-pro", "kimi_changelog") in keys
    deps = {(d["model"], d["source"]): d for d in out["deprecations"]}
    assert deps[("claude-sonnet-4-5-20250929", "anthropic_deprecations")]["replacement"] == "claude-sonnet-5-5"
    g = deps[("gpt-5.5", "codex_changelog")]
    assert g["state"] == "deprecated" and g["retirement"] == "2026-10-14" and g["replacement"] is None
    json.dumps(out)


def test_collect_public_survives_failing_source():
    def fetch(name):
        if name == "kimi_changelog":
            raise TimeoutError("x" * 500)
        return fake_fetch(name)
    out = sources.collect_public(fetch=fetch, now=NOW)
    bad = out["sources"]["kimi_changelog"]
    assert bad["ok"] is False and bad["sha256"] is None
    assert bad["error"].startswith("TimeoutError: ") and len(bad["error"]) <= 200
    assert all(v["ok"] for k, v in out["sources"].items() if k != "kimi_changelog")
    assert out["cli_latest"]["claude"] == "2.1.330"
    assert not any(r["source"] == "kimi_changelog" for r in out["launches"])
    assert any(r["model"] == "claude-fable-5-2" for r in out["launches"])


def test_collect_public_garbage_everywhere():
    out = sources.collect_public(fetch=lambda n: "\x00junk <<>>", now=NOW)
    assert out["launches"] == [] and out["deprecations"] == []
    assert out["cli_latest"] == {"claude": None, "codex": None}
