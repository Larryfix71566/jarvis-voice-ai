import pytest

from jarvis.saygm import SayGMError, confidential_model, parse_catalog


def test_catalog_distinguishes_confidential_and_upstream_routes():
    models = parse_catalog({"data": [
        {"id": "private-1-TEE", "tier": "confidential", "gateway_provider": "chutes"},
        {"id": "claude-fable-5", "tier": "frontier", "gateway_provider": "anthropic"},
        {"id": "open-1", "tier": "open", "gateway_provider": "openai"},
    ]})
    assert models[0].confidential
    assert not models[1].confidential
    assert not models[2].confidential
    assert confidential_model(models, "private-1-TEE").tier == "confidential"


def test_frontier_route_cannot_satisfy_confidential_request():
    models = parse_catalog({"data": [{"id": "claude-fable-5", "tier": "frontier"}]})
    with pytest.raises(SayGMError, match="not a confidential"):
        confidential_model(models, "claude-fable-5")


def test_malformed_catalog_fails_closed():
    with pytest.raises(SayGMError, match="no list"):
        parse_catalog({"data": {}})


def test_catalog_preserves_upstream_provider_for_display():
    model = parse_catalog({"data": [{
        "id": "frontier", "tier": "frontier", "gateway_provider": "anthropic",
        "owned_by": "anthropic",
    }]})[0]
    assert model.gateway_provider == "anthropic"
    assert model.owned_by == "anthropic"
