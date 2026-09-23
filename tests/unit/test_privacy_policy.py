import pytest

from jarvis.model_routing import AccessRoute, ModelRouteError
from jarvis.privacy_policy import DataPolicy, PrivacyLevel, assert_route_allowed, strictest


def _route(privacy):
    return AccessRoute("test", "test", "test", None, privacy)


def test_unlabeled_data_defaults_to_confidential():
    assert DataPolicy().level == "confidential"


def test_strictest_policy_wins_when_context_is_combined():
    result = strictest(DataPolicy("approved_external", "web"),
                       DataPolicy("local_only", "vault"))
    assert result.level == "local_only"
    assert result.source == "web+vault"


def test_external_route_is_rejected_for_confidential_data():
    with pytest.raises(ModelRouteError, match="requires 'confidential'"):
        assert_route_allowed(_route("approved_external"), DataPolicy())


def test_confidential_route_is_allowed_for_confidential_data():
    assert_route_allowed(_route("confidential"), DataPolicy())


def test_local_only_is_stricter_than_confidential():
    assert PrivacyLevel.LOCAL_ONLY > PrivacyLevel.CONFIDENTIAL
