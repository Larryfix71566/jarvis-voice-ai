"""Unit tests for mcp_servers/mcp_screen/logic.py
(MORTIMER_SHELL_FIX_AND_SCREEN_VISION_PLAN.md V1/V2/V4).

All subprocess/vision-API calls are injected via capture_fn/client_factory/
fetch — no real screenshot or network call happens in this suite.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from mcp_servers.mcp_screen import logic

# --- screen_enabled / kill switch -----------------------------------------


class TestKillSwitch:
    def test_enabled_by_default(self, monkeypatch):
        monkeypatch.delenv("JARVIS_SCREEN_ENABLED", raising=False)
        assert logic.screen_enabled() is True

    def test_false_disables(self, monkeypatch):
        monkeypatch.setenv("JARVIS_SCREEN_ENABLED", "false")
        assert logic.screen_enabled() is False

    def test_screen_list_returns_error_when_disabled(self, monkeypatch):
        monkeypatch.setenv("JARVIS_SCREEN_ENABLED", "false")
        result = logic.screen_list(fetch=lambda: [{"resolution": "1x1", "main": True}])
        assert "error" in result

    def test_screen_view_returns_error_when_disabled(self, monkeypatch):
        monkeypatch.setenv("JARVIS_SCREEN_ENABLED", "false")
        result = logic.screen_view("what is this", capture_fn=lambda d: Path("/nonexistent"))
        assert "error" in result


# --- screen_list -----------------------------------------------------------


class TestScreenList:
    def test_maps_fetched_displays_to_1_based_index(self, monkeypatch):
        monkeypatch.delenv("JARVIS_SCREEN_ENABLED", raising=False)
        fetch = lambda: [
            {"resolution": "2560x1440", "main": True},
            {"resolution": "1920x1080", "main": False},
        ]
        result = logic.screen_list(fetch=fetch)
        assert result == {
            "displays": [
                {"index": 1, "resolution": "2560x1440", "main": True},
                {"index": 2, "resolution": "1920x1080", "main": False},
            ]
        }

    def test_empty_fetch_falls_back_to_single_unknown_display(self, monkeypatch):
        monkeypatch.delenv("JARVIS_SCREEN_ENABLED", raising=False)
        result = logic.screen_list(fetch=lambda: [])
        assert result == {"displays": [{"index": 1, "resolution": "unknown", "main": True}]}


class TestSystemProfilerParsing:
    def test_malformed_output_returns_empty_list_not_raise(self, monkeypatch):
        monkeypatch.setattr(
            logic.subprocess, "run",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no system_profiler here")),
        )
        assert logic._system_profiler_displays() == []


# --- vision profile resolution ---------------------------------------------


VISION_REGISTRY = {
    "profiles": {
        "claude-haiku": {"name": "claude-haiku", "vision": True, "api_key_env": "ANTHROPIC_API_KEY",
                          "base_url": "https://api.anthropic.com/v1/", "model": "claude-haiku-4-5"},
        "claude-sonnet": {"name": "claude-sonnet", "vision": True, "api_key_env": "ANTHROPIC_API_KEY",
                           "base_url": "https://api.anthropic.com/v1/", "model": "claude-sonnet-5"},
        "kimi-k3": {"name": "kimi-k3", "api_key_env": "MOONSHOT_API_KEY",
                    "base_url": "https://api.moonshot.ai/v1", "model": "kimi-k3"},
    }
}


class TestResolveVisionProfile:
    def test_env_selects_named_vision_profile_when_key_present(self, monkeypatch):
        monkeypatch.setenv("JARVIS_VISION_PROFILE", "claude-sonnet")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
        prof = logic._resolve_vision_profile(VISION_REGISTRY)
        assert prof["name"] == "claude-sonnet"

    def test_env_naming_non_vision_profile_raises(self, monkeypatch):
        monkeypatch.setenv("JARVIS_VISION_PROFILE", "kimi-k3")
        monkeypatch.setenv("MOONSHOT_API_KEY", "x")
        with pytest.raises(logic.NoVisionProfileError):
            logic._resolve_vision_profile(VISION_REGISTRY)

    def test_env_naming_profile_with_missing_key_raises(self, monkeypatch):
        monkeypatch.setenv("JARVIS_VISION_PROFILE", "claude-haiku")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with pytest.raises(logic.NoVisionProfileError):
            logic._resolve_vision_profile(VISION_REGISTRY)

    def test_no_env_picks_first_key_present_vision_profile_in_order(self, monkeypatch):
        monkeypatch.delenv("JARVIS_VISION_PROFILE", raising=False)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
        prof = logic._resolve_vision_profile(VISION_REGISTRY)
        assert prof["name"] == "claude-haiku"  # first in dict order

    def test_no_vision_profile_has_key_raises(self, monkeypatch):
        monkeypatch.delenv("JARVIS_VISION_PROFILE", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
        with pytest.raises(logic.NoVisionProfileError):
            logic._resolve_vision_profile(VISION_REGISTRY)


# --- screen_view -------------------------------------------------------


class FakeChoice:
    def __init__(self, content):
        self.message = type("M", (), {"content": content})()


class FakeResponse:
    def __init__(self, content):
        self.choices = [FakeChoice(content)]


class FakeVisionClient:
    def __init__(self, content="A browser window is open."):
        self.chat = type("Chat", (), {})()
        self.chat.completions = type("Completions", (), {})()
        self.chat.completions.create = lambda **kw: FakeResponse(content)


def _write_fake_screenshot(tmp_path: Path, size_bytes: int = 5000) -> Path:
    p = tmp_path / "fake.png"
    p.write_bytes(b"\x89PNG" + b"0" * size_bytes)
    return p


class TestScreenView:
    def test_production_vision_route_uses_shared_execution_boundary(self, tmp_path, monkeypatch):
        import jarvis.vision as vision
        from jarvis.model_routing import AccessRoute, ResolvedModelRoute

        monkeypatch.delenv("JARVIS_SCREEN_ENABLED", raising=False)
        monkeypatch.setenv("JARVIS_MODEL_ROUTING_ENABLED", "1")
        shot = _write_fake_screenshot(tmp_path)
        expected_image = shot.read_bytes()
        route = ResolvedModelRoute(
            workload="vision", profile_name="vision-profile", model="vision-model",
            provider="openai", base_url="https://example.invalid/v1/",
            route=AccessRoute(
                "direct_api", "openai_compatible", "provider_api", "VISION_API_KEY",
                "approved_external", capabilities=("text", "images"),
            ),
            api_key_env="VISION_API_KEY", identity="openai/vision-model",
            priority="interactive",
        )
        monkeypatch.setattr(vision, "resolve_vision_execution_route", lambda **kw: route)
        calls = []

        async def analyze(items, question, request_id, **kwargs):
            calls.append((items, question, request_id, kwargs))
            return "A terminal is open."

        monkeypatch.setattr(logic, "analyze_shared_content_via_boundary", analyze)
        result = logic.screen_view("what is open?", capture_fn=lambda _display: shot)

        assert result["answer"] == "A terminal is open."
        assert result["profile"] == "vision-profile"
        assert calls[0][0][0].kind == "image"
        assert calls[0][0][0].data == expected_image
        assert calls[0][1] == "what is open?"
        assert calls[0][2]
        assert calls[0][3]["resolved_route"] is route
        assert calls[0][3]["rung"] == "screen_vision"
        assert calls[0][3]["policy_source"] == "user-requested-screen-view"
        assert not shot.exists()

    def test_happy_path_returns_answer_and_deletes_temp_file(self, tmp_path, monkeypatch, caplog):
        caplog.set_level("INFO")
        monkeypatch.delenv("JARVIS_SCREEN_ENABLED", raising=False)
        monkeypatch.setenv("JARVIS_VISION_PROFILE", "claude-sonnet")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
        shot = _write_fake_screenshot(tmp_path)

        question = "QUESTION_CANARY: what is on screen?"
        answer = "ANSWER_CANARY: a code editor."
        result = logic.screen_view(
            question,
            display=2,
            capture_fn=lambda d: shot,
            client_factory=lambda profile: (FakeVisionClient(answer), "claude-sonnet-5"),
            registry=VISION_REGISTRY,
        )

        assert result["answer"] == answer
        assert result["display"] == 2
        assert result["profile"] == "claude-sonnet"
        assert result["low_confidence"] is False
        assert not shot.exists()  # V4: never persists
        assert "screen_view outcome=ok" in caplog.text
        assert "QUESTION_CANARY" not in caplog.text
        assert "ANSWER_CANARY" not in caplog.text
        assert str(tmp_path) not in caplog.text

    def test_tiny_capture_reports_low_confidence_without_calling_vision(self, tmp_path, monkeypatch):
        monkeypatch.delenv("JARVIS_SCREEN_ENABLED", raising=False)
        monkeypatch.setenv("JARVIS_VISION_PROFILE", "claude-sonnet")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
        shot = _write_fake_screenshot(tmp_path, size_bytes=10)  # below MIN_SCREENSHOT_BYTES

        called = []

        def client_factory(profile):
            called.append(True)
            return FakeVisionClient(), "m"

        result = logic.screen_view(
            "what is on screen",
            capture_fn=lambda d: shot,
            client_factory=client_factory,
            registry=VISION_REGISTRY,
        )
        assert result["low_confidence"] is True
        assert "Screen Recording" in result["answer"]
        assert called == []  # never sent to the vision model
        assert not shot.exists()

    def test_capture_failure_returns_error_dict_without_logging_exception(
        self, monkeypatch, caplog
    ):
        monkeypatch.delenv("JARVIS_SCREEN_ENABLED", raising=False)
        monkeypatch.setenv("JARVIS_VISION_PROFILE", "claude-sonnet")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "x")

        def failing_capture(d):
            raise RuntimeError("CAPTURE_CONTENT_CANARY /private/screen/shot.png")

        result = logic.screen_view(
            "what is on screen", capture_fn=failing_capture, registry=VISION_REGISTRY,
        )
        assert "error" in result
        assert "capture failed" in result["error"].lower()
        assert "screen_view outcome=capture_failed error_type=RuntimeError" in caplog.text
        assert "CAPTURE_CONTENT_CANARY" not in caplog.text
        assert "/private/screen/shot.png" not in caplog.text

    def test_no_vision_profile_returns_error_dict_not_raise(self, monkeypatch):
        monkeypatch.delenv("JARVIS_SCREEN_ENABLED", raising=False)
        monkeypatch.delenv("JARVIS_VISION_PROFILE", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)

        result = logic.screen_view(
            "what is on screen", registry=VISION_REGISTRY,
        )
        assert "error" in result

    def test_vision_call_failure_still_deletes_temp_file(self, tmp_path, monkeypatch):
        monkeypatch.delenv("JARVIS_SCREEN_ENABLED", raising=False)
        monkeypatch.setenv("JARVIS_VISION_PROFILE", "claude-sonnet")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
        shot = _write_fake_screenshot(tmp_path)

        def broken_client_factory(profile):
            raise RuntimeError("network down")

        result = logic.screen_view(
            "what is on screen",
            capture_fn=lambda d: shot,
            client_factory=broken_client_factory,
            registry=VISION_REGISTRY,
        )
        assert "error" in result
        assert not shot.exists()  # cleanup still happens on failure


class TestDiagnostics:
    """MORTIMER_SKILL_LIBRARY_PLAN.md Part G. Larry asked for what the
    vision model sees to reach the logs, time-boxed, so an untested
    capability can be troubleshot. Tier 1 (text + metadata) and G3
    (retain FAILED captures) are built; Tier 2 (retain every image) was
    designed and deliberately not built."""

    def _profile_registry(self):
        return {"profiles": {"v": {"model": "m", "base_url": "http://x",
                                   "api_key_env": "K", "vision": True}}}

    def test_low_confidence_capture_is_retained_without_logging_its_path(
        self, tmp_path, monkeypatch, caplog
    ):
        """G3 — a wallpaper-only image is the artifact that proves a
        missing Screen Recording grant, and is the one image nearly
        certain to hold nothing private."""
        import mcp_servers.mcp_screen.logic as mod

        monkeypatch.setenv("K", "key")
        monkeypatch.setattr(mod, "SCREEN_LOG_DIR", tmp_path / "screen")
        shot = tmp_path / "s.png"
        shot.write_bytes(b"x" * 10)          # below MIN_SCREENSHOT_BYTES

        result = mod.screen_view(
            "what is this", 1,
            capture_fn=lambda d: shot,
            registry=self._profile_registry(),
        )
        assert result["low_confidence"] is True
        kept = list((tmp_path / "screen").rglob("*.png"))
        assert len(kept) == 1
        assert "lowconf" in kept[0].name
        assert "screen_lowconf_retained" in caplog.text
        assert "screen_view outcome=low_confidence" in caplog.text
        assert str(tmp_path) not in caplog.text
        assert str(kept[0]) not in caplog.text

    def test_a_good_capture_is_never_retained(self, tmp_path, monkeypatch):
        """Tier 2 was NOT built. A successful capture still leaves no
        image on disk — the original guarantee holds for the normal path."""
        import mcp_servers.mcp_screen.logic as mod

        monkeypatch.setenv("K", "key")
        monkeypatch.setattr(mod, "SCREEN_LOG_DIR", tmp_path / "screen")
        shot = tmp_path / "s.png"
        shot.write_bytes(b"x" * 5000)

        class _Resp:
            choices = [type("C", (), {"message": type("M", (), {"content": "a desk"})()})()]

        class _Client:
            class chat:
                class completions:
                    @staticmethod
                    def create(**kw):
                        return _Resp()

        result = mod.screen_view(
            "what is this", 1,
            capture_fn=lambda d: shot,
            client_factory=lambda p: (_Client(), "m"),
            registry=self._profile_registry(),
        )
        assert result["low_confidence"] is False
        assert not (tmp_path / "screen").exists() or not list(
            (tmp_path / "screen").rglob("*.png"))

    def test_the_temp_file_is_still_always_deleted(self, tmp_path, monkeypatch):
        """The pre-existing guarantee must survive Part G."""
        import mcp_servers.mcp_screen.logic as mod

        monkeypatch.setenv("K", "key")
        monkeypatch.setattr(mod, "SCREEN_LOG_DIR", tmp_path / "screen")
        shot = tmp_path / "s.png"
        shot.write_bytes(b"x" * 10)
        mod.screen_view("q", 1, capture_fn=lambda d: shot,
                        registry=self._profile_registry())
        assert not shot.exists()

    def test_prune_deletes_only_expired_images(self, tmp_path, monkeypatch):
        import os

        import mcp_servers.mcp_screen.logic as mod

        monkeypatch.setenv("JARVIS_SCREEN_RETENTION_HOURS", "48")
        d = tmp_path / "screen" / "2026-08-18"
        d.mkdir(parents=True)
        old, new = d / "old.png", d / "new.png"
        old.write_bytes(b"x")
        new.write_bytes(b"x")
        now = 1_000_000.0
        os.utime(old, (now - 60 * 3600, now - 60 * 3600))   # 60h — expired
        os.utime(new, (now - 1 * 3600, now - 1 * 3600))     # 1h  — fresh

        assert mod.prune_screen_logs(tmp_path / "screen", now=now) == 1
        assert not old.exists()
        assert new.exists()

    def test_prune_failure_is_redacted_and_never_raises(
        self, tmp_path, monkeypatch, caplog
    ):
        import mcp_servers.mcp_screen.logic as mod

        directory = tmp_path / "SCREEN_PATH_CANARY"
        directory.mkdir()
        original_rglob = Path.rglob

        def fail_rglob(path, pattern):
            if path == directory:
                raise RuntimeError(f"PRUNE_CANARY {path}")
            return original_rglob(path, pattern)

        monkeypatch.setattr(Path, "rglob", fail_rglob)
        assert mod.prune_screen_logs(directory) == 0
        assert "screen_prune_failed error_type=RuntimeError" in caplog.text
        assert "PRUNE_CANARY" not in caplog.text
        assert str(directory) not in caplog.text

    def test_low_confidence_retention_failure_is_redacted(
        self, tmp_path, monkeypatch, caplog
    ):
        import mcp_servers.mcp_screen.logic as mod

        directory = tmp_path / "SCREEN_PATH_CANARY"

        def fail_write(_self, _data):
            raise RuntimeError("RETENTION_CONTENT_CANARY")

        monkeypatch.setattr(Path, "write_bytes", fail_write)
        assert mod._retain_failed_capture(b"synthetic", 7, directory) is None
        assert "screen_lowconf_retain_failed error_type=RuntimeError" in caplog.text
        assert "RETENTION_CONTENT_CANARY" not in caplog.text
        assert str(directory) not in caplog.text
        assert "display=7" not in caplog.text

    def test_retention_default_and_bad_values(self, monkeypatch, caplog):
        import mcp_servers.mcp_screen.logic as mod

        monkeypatch.delenv("JARVIS_SCREEN_RETENTION_HOURS", raising=False)
        assert mod.retention_hours() == 48
        monkeypatch.setenv(
            "JARVIS_SCREEN_RETENTION_HOURS",
            "RETENTION_CONFIG_CANARY /private/user/settings",
        )
        assert mod.retention_hours() == 48        # unparseable falls back
        assert "screen_retention_unparseable using=48" in caplog.text
        assert "RETENTION_CONFIG_CANARY" not in caplog.text
        assert "/private/user/settings" not in caplog.text
        monkeypatch.setenv("JARVIS_SCREEN_RETENTION_HOURS", "-5")
        assert mod.retention_hours() == 0         # never negative

    def test_retention_is_the_shortest_in_the_system(self):
        """Screenshots are the most sensitive artifact Mortimer holds;
        the run log keeps 30 days and council rounds 180."""
        import mcp_servers.mcp_screen.logic as mod

        assert mod.DEFAULT_RETENTION_HOURS <= 48


class TestAuthFailureIsNamed:
    """MORTIMER_KEY_VALIDITY_PLAN.md K7. MIN_SCREENSHOT_BYTES exists because
    a macOS Screen Recording denial fails silently into a wallpaper-only
    image; nothing did the same job for a dead credential. Since every
    `vision: true` profile is Anthropic, one bad ANTHROPIC_API_KEY kills
    screen vision entirely while _resolve_vision_profile reports SUCCESS —
    the key is present. Without this the user gets a capture-shaped error
    for a credential-shaped problem."""

    def _run(self, exc):
        from mcp_servers.mcp_screen import logic

        def fake_capture(display):
            p = Path(tempfile.mkdtemp()) / "shot.png"
            p.write_bytes(b"x" * (logic.MIN_SCREENSHOT_BYTES + 100))
            return p

        class Boom:
            class chat:
                class completions:
                    @staticmethod
                    def create(**kwargs):
                        raise exc

        return logic.screen_view(
            "what is on screen?",
            capture_fn=fake_capture,
            client_factory=lambda p: (Boom, "fake-vision-model"),
            registry={"profiles": {"v": {
                "name": "v", "model": "m", "base_url": "b",
                "api_key_env": "ANTHROPIC_API_KEY", "vision": True}}},
        )

    def test_a_401_is_reported_as_a_credential_problem(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "present-but-dead")
        exc = RuntimeError("Unauthorized")
        exc.status_code = 401
        result = self._run(exc)
        assert result.get("auth_rejected") is True
        assert "rejected the credential" in result["error"]
        assert "ANTHROPIC_API_KEY" in result["error"]
        assert "captured fine" in result["error"]

    def test_a_non_auth_failure_is_not_mislabelled_and_redacts_log(
        self, monkeypatch, caplog
    ):
        """The mirror risk: calling every model error a dead key would send
        the user to rotate a working credential."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "fine")
        result = self._run(RuntimeError("VISION_RESPONSE_CANARY /private/provider/body"))
        assert "auth_rejected" not in result
        assert "Vision model call failed" in result["error"]
        assert "VISION_RESPONSE_CANARY" not in caplog.text
        assert "/private/provider/body" not in caplog.text
        assert "Traceback" not in caplog.text


# --- D3: find the macOS tools even when launchd's PATH misses /usr/sbin ----

class TestMacosTool:
    def test_path_hit_wins(self, monkeypatch):
        monkeypatch.setattr(logic.shutil, "which", lambda name: f"/opt/x/{name}")
        assert logic.macos_tool("screencapture") == "/opt/x/screencapture"

    def test_falls_back_to_usr_sbin_when_path_misses_it(self, monkeypatch, tmp_path):
        # The 2026-09-08 failure: PATH without /usr/sbin.
        fake = tmp_path / "screencapture"
        fake.write_text("#!/bin/sh\n")
        fake.chmod(0o755)
        monkeypatch.setattr(logic.shutil, "which", lambda name: None)
        monkeypatch.setattr(logic, "MACOS_TOOL_DIRS", (str(tmp_path / "missing"), str(tmp_path)))
        assert logic.macos_tool("screencapture") == str(fake)

    def test_not_found_names_where_it_looked(self, monkeypatch):
        monkeypatch.setattr(logic.shutil, "which", lambda name: None)
        monkeypatch.setattr(logic, "MACOS_TOOL_DIRS", ("/nonexistent-a",))
        with pytest.raises(FileNotFoundError, match="screencapture not found on PATH or in /nonexistent-a"):
            logic.macos_tool("screencapture")

    def test_capture_uses_the_resolved_path(self, monkeypatch):
        calls = []
        monkeypatch.setattr(logic, "macos_tool", lambda name: f"/usr/sbin/{name}")
        monkeypatch.setattr(logic.subprocess, "run", lambda args, **kw: calls.append(args))
        path = logic._capture_screenshot(2)
        try:
            assert calls[0][:4] == ["/usr/sbin/screencapture", "-x", "-D", "2"]
        finally:
            path.unlink(missing_ok=True)

    def test_template_path_keeps_usr_sbin(self):
        # #79's fix, pinned where the services get their PATH.
        from pathlib import Path as _P
        tpl = (_P(__file__).resolve().parents[2] / "scripts" / "launchd" / "com.mortimer.template.plist").read_text()
        assert ":/usr/sbin:" in tpl
