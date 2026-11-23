from jarvis.model_sync import pins


def _write(tmp_path):
    (tmp_path / "generated").mkdir()
    (tmp_path / "generated" / "x.yaml").write_text("model: claude-opus-9-9\n")
    (tmp_path / "profiles.yaml").write_text(
        "# old: claude-sonnet-3-7-sonnet\n"
        "profiles:\n"
        "  - name: fast\n"
        "    model: claude-haiku-4-5  # was claude-haiku-3-5\n"
        "  - name: big\n"
        "    model: gpt-6-astra\n"
        "workloads:\n"
        "  voice_supervisor:\n"
        "    profile: claude-haiku-4-5\n")
    return tmp_path


def test_scan_fixture(tmp_path):
    found = pins.scan_config(_write(tmp_path))
    models = [(f["model"], f["context"], f["line"]) for f in found]
    assert ("claude-haiku-4-5", "fast", 4) in models
    assert ("gpt-6-astra", "big", 6) in models
    assert ("claude-haiku-4-5", "voice_supervisor", 9) in models
    assert not any(m[0] in ("claude-haiku-3-5", "claude-opus-9-9") for m in models)
    assert not any("claude-sonnet-3-7" in m[0] for m in models)
    assert all(f["file"].endswith("profiles.yaml") for f in found)


def test_scan_missing_dir(tmp_path):
    assert pins.scan_config(tmp_path / "nope") == []


def test_scan_real_repo():
    found = pins.scan_config()
    assert any(f["model"].startswith("claude-") for f in found)
    assert all(not f["file"].startswith("config/generated/") for f in found)


def test_voice_pin(tmp_path):
    (tmp_path / "model_access.yaml").write_text(
        "workloads:\n  voice_supervisor:\n    profile: fast-voice\n")
    (tmp_path / "model_endpoints.yaml").write_text(
        "endpoints:\n  claude-subscription:\n    provider: anthropic\n    kind: subscription\n")
    (tmp_path / "model_profiles.yaml").write_text(
        "profiles:\n  - name: fast-voice\n    endpoint: claude-subscription\n"
        "    model: claude-haiku-4-5\n    identity: anthropic/claude-haiku-4-5\n")
    src = "config/model_access.yaml:workloads.voice_supervisor"
    assert pins.voice_pin(tmp_path, {}) == {"model": "claude-haiku-4-5", "source": src}
    (tmp_path / "model_profiles.yaml").write_text("profiles: []\n")
    (tmp_path / "model_access.yaml").write_text(
        "workloads:\n  voice_supervisor:\n    profile: claude-sonnet-5-5\n")
    assert pins.voice_pin(tmp_path, {})["model"] == "claude-sonnet-5-5"


def test_voice_pin_env_fallback(tmp_path):
    assert pins.voice_pin(tmp_path, {}) is None
    assert pins.voice_pin(tmp_path, {"OPENAI_MODEL": "gpt-4.1-mini"}) == {
        "model": "gpt-4.1-mini", "source": "env:OPENAI_MODEL"}
    assert pins.voice_pin(tmp_path, {"OPENAI_MODEL": "whatever"}) is None


def test_cli_and_collect(tmp_path):
    cli = pins.cli_pins()
    assert cli["claude"] and cli["codex"]
    got = pins.collect_pins(_write(tmp_path), {"OPENAI_MODEL": "gpt-6-astra"})
    assert set(got) == {"models", "voice", "cli"} and got["voice"]["model"] == "gpt-6-astra"
