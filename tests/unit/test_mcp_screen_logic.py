"""Unit tests for mcp_servers/mcp_screen/logic.py
(MORTIMER_SHELL_FIX_AND_SCREEN_VISION_PLAN.md V1/V2/V4).

All subprocess/vision-API calls are injected via capture_fn/client_factory/
fetch — no real screenshot or network call happens in this suite.
"""

from __future__ import annotations

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
    def test_happy_path_returns_answer_and_deletes_temp_file(self, tmp_path, monkeypatch):
        monkeypatch.delenv("JARVIS_SCREEN_ENABLED", raising=False)
        monkeypatch.setenv("JARVIS_VISION_PROFILE", "claude-sonnet")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
        shot = _write_fake_screenshot(tmp_path)

        result = logic.screen_view(
            "what is on screen",
            display=2,
            capture_fn=lambda d: shot,
            client_factory=lambda profile: (FakeVisionClient("A code editor."), "claude-sonnet-5"),
            registry=VISION_REGISTRY,
        )

        assert result["answer"] == "A code editor."
        assert result["display"] == 2
        assert result["profile"] == "claude-sonnet"
        assert result["low_confidence"] is False
        assert not shot.exists()  # V4: never persists

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

    def test_capture_failure_returns_error_dict(self, monkeypatch):
        monkeypatch.delenv("JARVIS_SCREEN_ENABLED", raising=False)
        monkeypatch.setenv("JARVIS_VISION_PROFILE", "claude-sonnet")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "x")

        def failing_capture(d):
            raise RuntimeError("screencapture exited 1")

        result = logic.screen_view(
            "what is on screen", capture_fn=failing_capture, registry=VISION_REGISTRY,
        )
        assert "error" in result
        assert "capture failed" in result["error"].lower()

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
