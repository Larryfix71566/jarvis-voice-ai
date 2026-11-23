import json

import pytest

from jarvis import subscription
from jarvis.model_sync import subscription_lists as sl


def _payload(*models):
    return json.dumps({"type": "result", "is_error": False, "result": "OK",
                       "modelUsage": {m: {"inputTokens": 1} for m in models}})


def test_alias_picks_family():
    r = sl.claude_alias_probe("opus", run_sync=lambda *a, **k: _payload("claude-haiku-5-5", "claude-opus-5-5"))
    assert r["ok"] and r["model"] == "claude-opus-5-5"
    assert r["models"] == ["claude-haiku-5-5", "claude-opus-5-5"]
    r = sl.claude_alias_probe("haiku", run_sync=lambda *a, **k: _payload("claude-haiku-5-5", "claude-opus-5-5"))
    assert r["model"] == "claude-haiku-5-5"


def test_alias_argv_and_errors():
    seen = {}

    def ok(argv, prompt, timeout, provider):
        seen.update(argv=argv, prompt=prompt)
        return _payload("claude-sonnet-5")
    assert sl.claude_alias_probe("sonnet", run_sync=ok)["ok"]
    assert "sonnet" in seen["argv"] and "--restricted" in seen["argv"]
    assert seen["prompt"] == sl.ALIAS_PROMPT

    def boom(*a, **k):
        raise subscription.SubscriptionRuntimeError("Not logged in", category="authentication")
    r = sl.claude_alias_probe("opus", run_sync=boom)
    assert not r["ok"] and r["category"] == "authentication"
    assert sl.claude_alias_probe("opus", run_sync=lambda *a, **k: "not json")["category"] == "unresolved"
    assert sl.claude_alias_probe("opus", run_sync=lambda *a, **k: _payload("claude-haiku-5-5"))["category"] == "unresolved"
    with pytest.raises(ValueError):
        sl.claude_alias_probe("gpt", run_sync=lambda *a, **k: "")


def test_cli_version(monkeypatch):
    monkeypatch.setattr(subscription, "resolve_provider_executable", lambda w: "/bin/claude")

    class R:
        returncode, stdout = 0, "2.1.330 (Claude Code)\n"
    assert sl.claude_cli_version(run=lambda *a, **k: R()) == "2.1.330 (Claude Code)"
    monkeypatch.setattr(subscription, "resolve_provider_executable", lambda w: None)
    assert sl.claude_cli_version(run=lambda *a, **k: R()) is None


class FakeStdin:
    def __init__(self, proc): self.proc = proc
    def write(self, s):
        for line in s.splitlines():
            self.proc.on(json.loads(line))
    def flush(self): pass


class FakePopen:
    def __init__(self, argv, **kw):
        self.argv, self.kw, self.pid = argv, kw, 0
        self.out, self.sent = [], []
        self.stdin = FakeStdin(self)
        self.stdout = self
        self.terminated = False
    def on(self, msg):
        self.sent.append(msg)
        if msg.get("method") == "initialize":
            self.out.append(json.dumps({"method": "configWarning", "params": {}}))
            self.out.append(json.dumps({"id": msg["id"], "result": {"userAgent": "x"}}))
        elif msg.get("method") == "model/list":
            if msg["params"].get("cursor"):
                data, nxt = [{"id": "gpt-6.2-astra", "displayName": "A", "hidden": True}], None
            else:
                data, nxt = [{"id": "gpt-6.2-sol", "displayName": "S", "isDefault": True, "hidden": False}], "1"
            self.out.append(json.dumps({"id": msg["id"], "result": {"data": data, "nextCursor": nxt}}))
    def readline(self):
        # Block like a real pipe until a line arrives or the process ends
        # (the reader thread would otherwise see "" as end of output).
        import time
        for _ in range(200):
            if self.out:
                return self.out.pop(0) + "\n"
            if self.terminated:
                return ""
            time.sleep(0.01)
        return ""
    def terminate(self): self.terminated = True
    def kill(self): self.terminated = True
    def wait(self, timeout=None): return 0


def test_codex_list(monkeypatch):
    monkeypatch.setattr(subscription, "resolve_provider_executable", lambda w: "/bin/codex")
    procs = []

    def popen(argv, **kw):
        procs.append(FakePopen(argv, **kw))
        return procs[-1]
    r = sl.codex_model_list(popen=popen)
    assert r["ok"] and r["default"] == "gpt-6.2-sol"
    assert [m["id"] for m in r["models"]] == ["gpt-6.2-sol", "gpt-6.2-astra"]
    assert r["models"][1]["hidden"] is True
    p = procs[0]
    assert p.argv == ["/bin/codex", "app-server"] and p.kw["start_new_session"] is True
    assert "OPENAI_API_KEY" not in p.kw["env"]
    assert [m.get("method") for m in p.sent] == ["initialize", "initialized", "model/list", "model/list"]


def test_codex_not_installed_and_eof(monkeypatch):
    monkeypatch.setattr(subscription, "resolve_provider_executable", lambda w: None)
    assert sl.codex_model_list(popen=None)["category"] == "not_installed"
    monkeypatch.setattr(subscription, "resolve_provider_executable", lambda w: "/bin/codex")

    class Dead(FakePopen):
        def on(self, msg): pass
    r = sl.codex_model_list(popen=lambda a, **k: Dead(a, **k))
    assert not r["ok"] and r["category"] == "runtime_error"


def test_kimi_and_collect():
    assert sl.kimi_model_list()["category"] == "unsupported"
    deps = {"version": lambda: "2.1.330 (Claude Code)",
            "probe": lambda a: {"alias": a, "ok": True, "model": "m"},
            "codex": lambda: {"ok": True, "models": []},
            "kimi": lambda: (_ for _ in ()).throw(RuntimeError("x"))}
    got = sl.collect_subscriptions(deps=deps)
    assert got["claude"]["aliases"]["opus"]["ok"] and got["codex"]["ok"] and not got["kimi"]["ok"]
    skipped = sl.collect_subscriptions(probe_aliases=False, deps=deps)
    assert skipped["claude"]["aliases"]["fable"] == {"ok": False, "category": "skipped"}
