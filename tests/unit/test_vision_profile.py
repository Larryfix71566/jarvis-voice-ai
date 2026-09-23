import pytest
from jarvis.vision import NoVisionProfileError, profile_summary, resolve_vision_profile


def test_profile_resolution_requires_vision_capable_key(monkeypatch):
    registry = {"profiles": {"plain": {"vision": False, "api_key_env": "KEY"}}}
    monkeypatch.delenv("JARVIS_VISION_PROFILE", raising=False)
    monkeypatch.delenv("KEY", raising=False)
    with pytest.raises(NoVisionProfileError):
        resolve_vision_profile(registry)


def test_profile_summary_exposes_only_bounded_labels():
    summary = profile_summary({"id": "vision-1", "label": "Local Vision"})
    assert summary == {"id": "vision-1", "label": "Local Vision"}
