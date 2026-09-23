from jarvis.usage_ledger import provider_from_base_url


def test_subscription_clients_are_distinguished_from_paid_api_routes():
    assert provider_from_base_url("subscription://claude") == "subscription"
    assert provider_from_base_url("subscription://codex") == "subscription"
