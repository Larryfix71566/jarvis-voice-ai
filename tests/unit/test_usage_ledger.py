from types import SimpleNamespace

from jarvis import usage_ledger
from jarvis.usage_ledger import provider_from_base_url


def test_subscription_clients_are_distinguished_from_paid_api_routes():
    assert provider_from_base_url("subscription://claude") == "subscription"
    assert provider_from_base_url("subscription://codex") == "subscription"


def test_missing_provider_usage_is_recorded_as_unknown_not_zero_cost(monkeypatch, tmp_path):
    monkeypatch.setattr(usage_ledger, "DB_PATH", tmp_path / "costs.db")
    monkeypatch.setattr(usage_ledger, "_price_map_cache", {
        "models": {"test/model": {"input_per_m": 10.0, "output_per_m": 20.0}}
    })
    usage_ledger.record_completion(
        rung="kb_digest", provider="test", model="model",
        response=SimpleNamespace(id="completion-unknown", usage=None),
        billing_source="subscription", route_name="subscription",
    )
    with usage_ledger._conn() as conn:
        row = conn.execute(
            "SELECT input_tokens, output_tokens, usage_known,"
            " cache_breakdown_known, billing_source, route_name, computed_cost"
            " FROM llm_calls"
        ).fetchone()
    assert row == (0, 0, 0, 0, "subscription", "subscription", None)


def test_known_provider_usage_and_route_metadata_are_preserved(monkeypatch, tmp_path):
    monkeypatch.setattr(usage_ledger, "DB_PATH", tmp_path / "costs.db")
    monkeypatch.setattr(usage_ledger, "_price_map_cache", {
        "models": {"test/model": {"input_per_m": 10.0, "output_per_m": 20.0}}
    })
    usage_ledger.record_completion(
        rung="kb_digest", provider="test", model="model",
        response=SimpleNamespace(
            usage=SimpleNamespace(
                prompt_tokens=40, completion_tokens=5,
                prompt_tokens_details=SimpleNamespace(cached_tokens=10, cache_write_tokens=5),
            ),
        ),
        billing_source="provider_api", route_name="direct_api",
    )
    with usage_ledger._conn() as conn:
        row = conn.execute(
            "SELECT input_tokens, output_tokens, cache_write_tokens,"
            " cache_read_tokens, usage_known, cache_breakdown_known,"
            " billing_source, route_name FROM llm_calls"
        ).fetchone()
    assert row == (25, 5, 5, 10, 1, 1, "provider_api", "direct_api")


def test_debug_usage_logs_only_normalized_counts(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(usage_ledger, "DB_PATH", tmp_path / "costs.db")
    monkeypatch.setattr(usage_ledger, "_price_map_cache", {"models": {}})
    monkeypatch.setenv("JARVIS_DEBUG_USAGE_LEDGER", "1")
    private_field = "PRIVATE_PROVIDER_USAGE_CANARY"
    response = SimpleNamespace(
        id="private-id",
        usage=SimpleNamespace(
            prompt_tokens=12,
            completion_tokens=3,
            prompt_tokens_details=SimpleNamespace(
                cached_tokens=4, cache_write_tokens=2,
            ),
            provider_private_field=private_field,
        ),
    )

    usage_ledger.record_completion(
        rung="kb_digest", provider="test", model="test/model",
        response=response,
    )

    stderr = capsys.readouterr().err
    assert "prompt_tokens=12 completion_tokens=3" in stderr
    assert "cache_read_tokens=4 cache_write_tokens=2" in stderr
    assert private_field not in stderr
    assert "raw_usage" not in stderr


def test_ledger_failure_logs_only_error_class(monkeypatch, capsys):
    canary = "PRIVATE_DATABASE_ERROR_CANARY /Users/private/path"

    def fail_connection():
        raise RuntimeError(canary)

    monkeypatch.setattr(usage_ledger, "_conn", fail_connection)
    usage_ledger.record_call(
        rung="supervisor", provider="test", model="model")

    stderr = capsys.readouterr().err
    assert "usage_ledger: record failed error_type=RuntimeError" in stderr
    assert canary not in stderr
    assert "/Users/private/path" not in stderr


def test_unknown_rung_warning_does_not_log_dynamic_rung(
        monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(usage_ledger, "DB_PATH", tmp_path / "costs.db")
    monkeypatch.setattr(usage_ledger, "_price_map_cache", {"models": {}})
    canary = "PRIVATE_RUNG_CANARY"

    usage_ledger.record_call(rung=canary, provider="test", model="model")

    stderr = capsys.readouterr().err
    assert "usage_ledger: unknown rung" in stderr
    assert canary not in stderr
    with usage_ledger._conn() as conn:
        row = conn.execute("SELECT rung FROM llm_calls").fetchone()
    assert row == (canary,)
