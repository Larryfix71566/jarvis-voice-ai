from types import SimpleNamespace

from jarvis.model_sync import certify as C


def cand(vendor="anthropic", roles=("claude-fable-5",), voice=False, model="m-new"):
    return {"model": model, "replaces": "m-old", "vendor": vendor, "roles": list(roles), "voice": voice}


def ok_probe(which, model):
    return {"ok": True}


def runner_ms(ms):
    # advance a fake clock via perf_counter patch is overkill: sleep-free by patching time
    def r(model, messages, timeout):
        C.time.sleep(ms / 1000.0)
        return "Sure."
    return r


def test_anthropic_pass_with_manual(tmp_path):
    seen = []
    r = C.certify(cand(), status_dir=tmp_path, probe=lambda w, m: seen.append((w, m)) or {"ok": True})
    assert r["passed"] and seen == [("claude", "m-new")]
    assert [s["name"] for s in r["steps"]] == ["subscription_probe"]
    assert any("verify_claude_developer_capability.py --model m-new --live" in m for m in r["manual"])
    assert r["certified_at"]


def test_probe_failure_stops(tmp_path):
    r = C.certify(cand(voice=True), status_dir=tmp_path,
                  probe=lambda w, m: {"ok": False, "category": "model_unavailable"})
    assert not r["passed"] and len(r["steps"]) == 1
    assert r["steps"][0]["detail"] == "model_unavailable"


def test_moonshot(tmp_path):
    r = C.certify(cand("moonshot"), status_dir=tmp_path, probe=ok_probe)
    assert not r["passed"] and r["steps"][0]["detail"] == "no subscription route for this vendor"


def test_probe_exception_never_raises(tmp_path):
    def boom(w, m):
        raise RuntimeError("x")
    r = C.certify(cand(), status_dir=tmp_path, probe=boom)
    assert not r["passed"] and r["steps"][0]["detail"] == "RuntimeError"


def test_codex_receipt(tmp_path):
    calls = []

    def rs(argv, timeout):
        calls.append((argv, timeout))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    r = C.certify(cand("openai", roles=["voice"]), status_dir=tmp_path, probe=ok_probe, run_script=rs)
    assert r["passed"] and [s["name"] for s in r["steps"]] == ["subscription_probe", "codex_receipt"]
    argv, timeout = calls[0]
    assert argv[1:4] == ["scripts/verify_subscription_capability.py", "--model", "m-new"]
    assert argv[-1].endswith("model-sync/receipts/m-new.json") and timeout == 180
    assert r["manual"] == []

    def bad(argv, timeout):
        return SimpleNamespace(returncode=1, stdout="", stderr="a\n" + "x" * 500)

    r = C.certify(cand("openai"), status_dir=tmp_path, probe=ok_probe, run_script=bad)
    assert not r["passed"] and len(r["steps"][-1]["detail"]) == 200


def test_voice_bench_fast_and_slow():
    fast = C.voice_bench("m", runner=runner_ms(1), runs=5)
    assert fast["ok"] and fast["runs"] == 5 and fast["errors"] == 0
    slow = C.voice_bench("m", runner=runner_ms(60), runs=5)  # fast enough to run, patch gates below
    assert slow["ok"]


def test_voice_gates(monkeypatch):
    seq = iter([0, 1.0, 0, 1.3, 0, 1.0, 0, 1.0, 0, 1.0])  # 1000,1300,1000,1000,1000 ms
    monkeypatch.setattr(C.time, "perf_counter", lambda: next(seq))
    b = C.voice_bench("m", runner=lambda *a: "ok", runs=5)
    assert b["p50_ms"] == 1000.0 and b["p90_ms"] == 1300.0 and b["ok"]
    seq2 = iter([0, 1.3] * 5)  # p50 1300 > 1200
    monkeypatch.setattr(C.time, "perf_counter", lambda: next(seq2))
    assert not C.voice_bench("m", runner=lambda *a: "ok", runs=5)["ok"]
    seq3 = iter([0, 0.5, 0, 0.5, 0, 0.5, 0, 0.5, 0, 4.0])  # p90 4000 > 3500
    monkeypatch.setattr(C.time, "perf_counter", lambda: next(seq3))
    b = C.voice_bench("m", runner=lambda *a: "ok", runs=5)
    assert b["p50_ms"] == 500.0 and b["p90_ms"] == 4000.0 and not b["ok"]


def test_voice_errors_fail():
    def r(model, messages, timeout):
        if messages[-1]["content"].startswith("Turn"):
            raise TimeoutError
        return "ok"
    b = C.voice_bench("m", runner=r, runs=5)
    assert b["errors"] == 1 and b["runs"] == 4 and not b["ok"]


def test_certify_voice_step(tmp_path):
    r = C.certify(cand(roles=["voice"], voice=True), status_dir=tmp_path, probe=ok_probe,
                  voice_runner=lambda m, msgs, t: "ok")
    assert r["passed"] and r["steps"][-1]["name"] == "voice_bench"
    assert r["manual"] == ["python scripts/latency_probe.py  # after switching OPENAI_MODEL, on live logs"]
    r = C.certify(cand(roles=["voice"], voice=True), status_dir=tmp_path, probe=ok_probe,
                  voice_runner=lambda m, msgs, t: "")
    assert not r["passed"]
