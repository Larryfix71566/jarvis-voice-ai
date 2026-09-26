"""T2.3 — service_health() and the launchd_state parse moved out of
scripts/launchd_gen.py."""

from __future__ import annotations

import socket
import subprocess
from types import SimpleNamespace

from jarvis.status import services as S
from jarvis.status.services import launchd_state, service_health


def _fake_run(returncode: int, stdout: str = ""):
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(returncode=returncode, stdout=stdout)

    run.calls = calls
    return run


def test_launchd_state_parses_pid():
    run = _fake_run(0, "com.mortimer.bot = {\n\tstate = running\n\tpid = 4242\n}\n")
    assert launchd_state("bot", run=run) == "loaded (pid 4242)"
    assert run.calls[0][:2] == ["launchctl", "print"]
    assert run.calls[0][2].endswith("/com.mortimer.bot")


def test_launchd_state_idle_and_not_loaded():
    assert launchd_state("backup", run=_fake_run(0, "state = not running\n")) == "loaded (idle)"
    assert launchd_state("bot", run=_fake_run(113)) == "not loaded"


def test_launchd_state_unknown_without_launchctl(monkeypatch):
    monkeypatch.setattr(S.shutil, "which", lambda name: None)
    assert launchd_state("bot") == "unknown"


def test_launchd_gen_status_uses_launchd_state(monkeypatch):
    from scripts import launchd_gen

    seen = []
    monkeypatch.setattr(launchd_gen, "launchd_state", lambda svc: seen.append(svc) or "not loaded")
    assert launchd_gen.status() == {svc: "not loaded" for svc in launchd_gen.ALL_SERVICES}
    assert seen == list(launchd_gen.ALL_SERVICES)


def test_service_health_shape():
    probes = []

    def http(target):
        probes.append(target)
        return True, "HTTP 200"

    out = service_health(http=http, launchctl=lambda svc: "loaded (pid 1)")
    assert out["ok"] is True
    rows = {r["name"]: r for r in out["services"]}
    # Every launchd service (from launchd_gen's one list) is present.
    for name in ("vault", "bot", "extractor", "admin", "costs", "backup"):
        assert name in rows, name
    assert rows["admin"]["state"] == "up"            # by construction
    assert "7861" not in " ".join(probes)             # never self-called
    assert rows["extractor"]["state"] == "no port"
    assert rows["backup"]["state"] == "no port"
    assert rows["bot"]["state"] == "up"
    assert rows["bot"]["launchd"] == "loaded (pid 1)"
    assert sorted(probes) == sorted(S.PROBES.values())
    assert set(out["source"]) == {"head", "dirty_files"}


def test_service_health_marks_down_on_refused_port():
    # A real refused port: bind, learn the port, close, then probe it.
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    up, detail = S._http_probe(f"tcp://127.0.0.1:{port}")
    assert up is False
    assert detail == "connection refused"
    up, detail = S._http_probe(f"http://127.0.0.1:{port}/health")
    assert up is False

    out = service_health(http=lambda t: (False, "connection refused"),
                         launchctl=lambda svc: "unknown",
                         services=("bot", "costs", "vault"))
    rows = {r["name"]: r for r in out["services"]}
    assert rows["bot"]["state"] == "down"
    assert rows["costs"]["detail"] == "connection refused"
    assert rows["admin"]["state"] == "up"


def test_source_state_counts_dirty_files(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    for args in (["config", "user.email", "t@example.com"], ["config", "user.name", "t"]):
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True)
    (tmp_path / "a.txt").write_text("a")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "x"], check=True)
    (tmp_path / "a.txt").write_text("b")
    (tmp_path / "new.txt").write_text("n")
    state = S.source_state(tmp_path)
    assert len(state["head"]) == 40
    assert state["dirty_files"] == 2


def test_source_state_outside_git(tmp_path):
    assert S.source_state(tmp_path / "nope") == {"head": None, "dirty_files": None}
