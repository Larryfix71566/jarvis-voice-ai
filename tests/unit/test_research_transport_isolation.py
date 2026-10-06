"""Real HTTP client boundaries, with inert transports and no network."""

import httpx
import pytest

from jarvis.research import crawl


def _transport_clients(monkeypatch, handler):
    original = httpx.Client
    clients = []

    def factory(**kwargs):
        client = original(transport=httpx.MockTransport(handler), **kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr(crawl.httpx, "Client", factory)
    return clients


def test_response_cookie_cannot_cross_to_next_site(monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"results": []},
                              headers={"set-cookie": "session=marker; Path=/; Secure"})

    clients = _transport_clients(monkeypatch, handler)
    client = crawl.TavilyCrawlClient(timeout=3)
    for name in ("first", "second"):
        assert client.post(crawl.TAVILY_CRAWL_URL, {"Authorization": "Bearer fixture-key"},
                           {"url": "https://example.com/" + name}) == (200, {"results": []})
    assert len(requests) == 2
    assert all("cookie" not in request.headers for request in requests)
    assert all(request.headers["authorization"] == "Bearer fixture-key" for request in requests)
    assert all(client.is_closed for client in clients)


def test_process_proxy_and_certificate_override_cannot_change_transport(monkeypatch, tmp_path):
    # Construct the real HTTP transport, so inherited TLS/proxy settings would
    # take effect. Intercept only the final request handler to avoid network.
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("SSL_CERT_FILE", str(tmp_path / "nonexistent-certificate.pem"))
    observed = []

    def handle(transport, request):
        observed.append((type(transport._pool).__name__, str(request.url)))
        return httpx.Response(200, json={"results": []})

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", handle)
    assert crawl.TavilyCrawlClient().post(crawl.TAVILY_CRAWL_URL, {}, {}) == (200, {"results": []})
    assert observed == [("ConnectionPool", crawl.TAVILY_CRAWL_URL)]


def test_redirect_never_sends_credentials_to_new_endpoint(monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(307, headers={"location": "https://another.example/crawl"})

    clients = _transport_clients(monkeypatch, handler)
    assert crawl.TavilyCrawlClient().post(crawl.TAVILY_CRAWL_URL,
        {"Authorization": "Bearer fixture-key"}, {}) == (307, None)
    assert [str(request.url) for request in requests] == [crawl.TAVILY_CRAWL_URL]
    assert all(client.is_closed for client in clients)


@pytest.mark.parametrize("url", ["http://api.tavily.com/crawl", "https://api.tavily.com/other",
                               "https://another.example/crawl"])
def test_changed_endpoint_refuses_before_client_construction(monkeypatch, url):
    def unexpected(**kwargs):
        pytest.fail("a changed endpoint constructed an HTTP client")

    monkeypatch.setattr(crawl.httpx, "Client", unexpected)
    assert crawl.TavilyCrawlClient().post(url, {"Authorization": "Bearer fixture-key"}, {}) == (-1, None)


@pytest.mark.parametrize("error, expected", [(httpx.ReadTimeout("fixture"), 0),
                                           (httpx.ConnectError("fixture"), -1)])
def test_transport_failure_closes_client_and_preserves_taxonomy(monkeypatch, error, expected):
    def handler(request):
        raise error

    clients = _transport_clients(monkeypatch, handler)
    assert crawl.TavilyCrawlClient().post(crawl.TAVILY_CRAWL_URL, {}, {}) == (expected, None)
    assert len(clients) == 1 and clients[0].is_closed


def test_non_json_failure_closes_client_and_preserves_status(monkeypatch):
    clients = _transport_clients(monkeypatch,
        lambda request: httpx.Response(429, text="fixture rate limit"))
    assert crawl.TavilyCrawlClient().post(crawl.TAVILY_CRAWL_URL, {}, {}) == (429, None)
    assert clients[0].is_closed
