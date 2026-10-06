import pytest

from jarvis.saygm import SayGMError, confidential_model, fetch_catalog, parse_catalog, validate_endpoint


def test_catalog_distinguishes_confidential_and_upstream_routes():
    models = parse_catalog({"data": [
        {"id": "private-1-TEE", "tier": "confidential", "gateway_provider": "chutes",
         "api_shapes": ["chat.completions"]},
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


@pytest.mark.parametrize("entries", [
    [{"id": "Qwen/private-TEE", "tier": "frontier", "api_shapes": ["chat.completions"]}],
    [{"id": "Qwen/private", "tier": "confidential", "api_shapes": ["chat.completions"]}],
    [{"id": "Qwen/private-TEE", "tier": "confidential"}],
    [{"id": "Qwen/private-TEE", "tier": "confidential", "api_shapes": ["responses"]}],
    [{"id": "Qwen/private-TEE", "tier": "confidential", "api_shapes": ["chat.completions"],
      "available": False}],
    [{"id": "Qwen/private-TEE", "tier": "confidential", "api_shapes": ["chat.completions"]}] * 2,
])
def test_confidential_selection_rejects_unqualified_or_ambiguous_entry(entries):
    with pytest.raises(SayGMError):
        confidential_model(parse_catalog({"data": entries}), "Qwen/private")


@pytest.mark.parametrize("reverse", [False, True])
def test_confidential_selection_preserves_exact_id_and_is_order_independent(reverse):
    entries = [
        {"id": "Qwen/private", "tier": "open", "api_shapes": ["chat.completions"]},
        {"id": "Qwen/private-TEE", "tier": "confidential", "api_shapes": ["chat.completions"]},
    ]
    models = parse_catalog({"data": entries[::-1] if reverse else entries})
    selected = confidential_model(models, "Qwen/private")
    assert selected.model == "Qwen/private-TEE"
    assert selected.capabilities == ("text",)


def test_fetch_catalog_rejects_unapproved_endpoint_before_urlopen(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("unapproved endpoint received credentials")
    monkeypatch.setattr("jarvis.saygm.urlopen", forbidden)
    with pytest.raises(SayGMError, match="not approved"):
        fetch_catalog(api_key="fixture", base_url="https://fixture.example.invalid/v1")
    with pytest.raises(SayGMError, match="not approved"):
        validate_endpoint("https://api.saygm.com/v1", "OTHER_PROVIDER_KEY")


@pytest.mark.parametrize("http_status", [None, 401, 302])
def test_catalog_transport_failure_never_echoes_exception_or_response_body(monkeypatch, http_status):
    from urllib.error import HTTPError
    from io import BytesIO
    canary = "PRIVATE_CATALOG_EXCEPTION_CANARY"
    exc = (HTTPError("https://api.saygm.com/v1/models", http_status, canary, {},
                     BytesIO(canary.encode())) if http_status is not None else RuntimeError(canary))
    def fail(*args, **kwargs):
        raise exc
    monkeypatch.setattr("jarvis.saygm.urlopen", fail)
    with pytest.raises(SayGMError) as caught:
        fetch_catalog(api_key=canary)
    assert canary not in str(caught.value)
    assert "error_type=" in str(caught.value)
    if http_status:
        assert f"HTTP {http_status}" in str(caught.value)


def test_catalog_transport_does_not_forward_key_on_real_redirect():
    from http.server import BaseHTTPRequestHandler, HTTPServer
    import threading
    from urllib.error import HTTPError
    from urllib.request import Request
    from jarvis import saygm

    received = []
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            received.append((self.path, self.headers.get("Authorization")))
            if self.path == "/source":
                self.send_response(302)
                self.send_header("Location", f"http://127.0.0.1:{self.server.server_port}/sink")
            else:
                self.send_response(200)
            self.end_headers()
        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        request = Request(f"http://127.0.0.1:{server.server_port}/source",
                          headers={"Authorization": "Bearer fixture-key"})
        with pytest.raises(HTTPError) as caught:
            saygm.urlopen(request, timeout=2)
        assert caught.value.code == 302
        assert received == [("/source", "Bearer fixture-key")]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
