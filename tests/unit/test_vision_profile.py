import pytest

from jarvis.vision import (
    NoVisionProfileError,
    execution_route_summary,
    profile_summary,
    resolve_vision_execution_route,
    resolve_vision_profile,
)


def test_profile_resolution_requires_vision_capable_key(monkeypatch):
    registry = {"profiles": {"plain": {"vision": False, "api_key_env": "KEY"}}}
    monkeypatch.delenv("JARVIS_VISION_PROFILE", raising=False)
    monkeypatch.delenv("KEY", raising=False)
    with pytest.raises(NoVisionProfileError):
        resolve_vision_profile(registry)


def test_profile_summary_exposes_only_bounded_labels():
    summary = profile_summary({"id": "vision-1", "label": "Local Vision"})
    assert summary == {"id": "vision-1", "label": "Local Vision"}


def test_vision_execution_route_uses_routing_policy_when_enabled(monkeypatch):
    import jarvis.model_routing as routing

    selected = object()
    seen = []
    monkeypatch.setattr(
        routing, "resolve_model_route_checked",
        lambda workload: seen.append(workload) or selected,
    )
    assert resolve_vision_execution_route(routing_enabled=True) is selected
    assert seen == ["vision"]


def test_vision_execution_route_preserves_legacy_profile_when_routing_disabled(monkeypatch):
    import jarvis.model_routing as routing
    import jarvis.vision as vision

    selected = object()
    seen = []
    monkeypatch.setattr(vision, "resolve_vision_profile", lambda: {"name": "legacy-vision"})
    monkeypatch.setattr(
        routing, "resolve_model_route",
        lambda workload, **kwargs: seen.append((workload, kwargs)) or selected,
    )
    assert resolve_vision_execution_route(routing_enabled=False) is selected
    assert seen == [("vision", {"explicit_profile": "legacy-vision", "explicit_route": "direct_api"})]


def test_execution_route_summary_discloses_model_route_and_billing():
    class Selected:
        identity = "provider/model-x"
        model = "model-x"
        route = type("Route", (), {"name": "subscription", "billing": "subscription"})()

    assert execution_route_summary(Selected()) == {
        "id": "provider/model-x",
        "label": "model-x via subscription (subscription)",
    }
