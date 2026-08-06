"""Unit tests for mcp_servers/mcp_web/logic.py (plan Phase 1 Tests)."""

import httpx
import pytest

from mcp_servers.mcp_web import logic


class FakeResponse:
    def __init__(self, payload, status=200, url="https://x"):
        self._payload = payload
        self.status_code = status
        self._url = url

    def raise_for_status(self):
        if self.status_code >= 400:
            req = httpx.Request("GET", self._url)
            resp = httpx.Response(self.status_code, request=req)
            raise httpx.HTTPStatusError("error", request=req, response=resp)

    def json(self):
        return self._payload


class TestWebSearch:
    def test_happy_path_maps_results(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
        payload = {
            "answer": "Short answer.",
            "results": [
                {"title": "A", "url": "https://a", "content": "x" * 400},
                {"title": "B", "url": "https://b", "content": "short"},
            ],
        }
        monkeypatch.setattr(logic.httpx, "post", lambda *a, **k: FakeResponse(payload))
        result = logic.web_search("query", max_results=2)
        assert result["answer"] == "Short answer."
        assert [r["title"] for r in result["results"]] == ["A", "B"]
        assert len(result["results"][0]["snippet"]) == 300

    def test_no_key_degraded_mode(self, monkeypatch):
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        result = logic.web_search("anything")
        assert result["error"] == "Web search is unavailable (no API key configured)."

    def test_empty_query_error(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
        assert "error" in logic.web_search("  ")

    def test_http_status_error(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
        monkeypatch.setattr(logic.httpx, "post", lambda *a, **k: FakeResponse({}, 500))
        assert logic.web_search("q")["error"] == "Web search failed (HTTP 500)."

    def test_network_error(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")

        def boom(*a, **k):
            raise httpx.ConnectError("down")

        monkeypatch.setattr(logic.httpx, "post", boom)
        assert logic.web_search("q")["error"] == "Web search failed: ConnectError."


def _sse(payload: dict) -> str:
    import json as _json

    return "event: message\ndata: " + _json.dumps(payload) + "\n\n"


class FakeMCPSearchResponse(FakeResponse):
    """FakeResponse with an SSE .text body for the hosted MCP endpoint."""

    def __init__(self, inner_results, status=200):
        super().__init__({}, status)
        inner = {"results": inner_results, "answer": "MCP answer."}
        import json as _json

        rpc = {"jsonrpc": "2.0", "id": 1,
               "result": {"content": [{"type": "text", "text": _json.dumps(inner)}]}}
        self.text = _sse(rpc)


class TestWebSearchMCPTransport:
    """D-011: hosted-MCP-first transport with REST fallback."""

    def test_mcp_primary_used_and_mapped(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
        calls = []

        def fake_post(url, **kwargs):
            calls.append(url)
            assert "mcp.tavily.com" in url  # REST must not be needed
            return FakeMCPSearchResponse([
                {"title": "A", "url": "https://a", "content": "x" * 400},
            ])

        monkeypatch.setattr(logic.httpx, "post", fake_post)
        result = logic.web_search("query", max_results=2)
        assert len(calls) == 1
        assert result["answer"] == "MCP answer."
        assert result["results"][0]["title"] == "A"
        assert len(result["results"][0]["snippet"]) == 300

    def test_mcp_transport_error_falls_back_to_rest(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")

        def fake_post(url, **kwargs):
            if "mcp.tavily.com" in url:
                raise httpx.ConnectError("waf blocked")
            return FakeResponse({"answer": "REST answer.", "results": []})

        monkeypatch.setattr(logic.httpx, "post", fake_post)
        assert logic.web_search("q")["answer"] == "REST answer."

    def test_mcp_jsonrpc_error_falls_back_to_rest(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")

        class ErrorBody(FakeResponse):
            text = _sse({"jsonrpc": "2.0", "id": 1,
                         "error": {"code": -32601, "message": "no such tool"}})

        def fake_post(url, **kwargs):
            if "mcp.tavily.com" in url:
                return ErrorBody({})
            return FakeResponse({"answer": "REST answer.", "results": []})

        monkeypatch.setattr(logic.httpx, "post", fake_post)
        assert logic.web_search("q")["answer"] == "REST answer."

    def test_both_transports_down_reports_rest_error(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")

        def fake_post(url, **kwargs):
            if "mcp.tavily.com" in url:
                raise httpx.ConnectError("waf blocked")
            return FakeResponse({}, 403)

        monkeypatch.setattr(logic.httpx, "post", fake_post)
        assert logic.web_search("q")["error"] == "Web search failed (HTTP 403)."


GEO_PAYLOAD = {
    "results": [{
        "name": "Tokyo", "country": "Japan",
        "latitude": 35.69, "longitude": 139.69,
    }]
}
FORECAST_PAYLOAD = {
    "current": {
        "temperature_2m": 30.4, "relative_humidity_2m": 66,
        "weather_code": 2, "wind_speed_10m": 9.1,
    },
    "daily": {
        "time": ["2026-08-04", "2026-08-05"],
        "temperature_2m_max": [33.0, 32.0],
        "temperature_2m_min": [25.0, 24.5],
        "precipitation_probability_max": [20, 55],
        "weather_code": [2, 61],
    },
}


def _fake_get_factory(geo_payload, forecast_payload):
    def fake_get(url, params=None, timeout=None):
        if "geocoding" in url:
            return FakeResponse(geo_payload)
        return FakeResponse(forecast_payload)
    return fake_get


class TestGetWeather:
    def test_happy_path(self, monkeypatch):
        monkeypatch.setattr(
            logic.httpx, "get", _fake_get_factory(GEO_PAYLOAD, FORECAST_PAYLOAD)
        )
        result = logic.get_weather("tokyo", days=2)
        assert result["city"] == "Tokyo, Japan"
        assert result["current"]["condition"] == "partly cloudy"
        assert result["current"]["temperature_c"] == 30.4
        assert len(result["daily"]) == 2
        assert result["daily"][1]["condition"] == "slight rain"
        assert "30.4°C" in result["human"]
        assert "Tokyo, Japan" in result["human"]

    def test_city_not_found(self, monkeypatch):
        monkeypatch.setattr(
            logic.httpx, "get", _fake_get_factory({"results": []}, FORECAST_PAYLOAD)
        )
        assert "couldn't find" in logic.get_weather("Atlantis")["error"]

    def test_empty_city_error(self):
        assert "error" in logic.get_weather("  ")

    def test_geocode_network_error(self, monkeypatch):
        def boom(*a, **k):
            raise httpx.ConnectError("down")
        monkeypatch.setattr(logic.httpx, "get", boom)
        assert logic.get_weather("Tokyo")["error"].startswith("Weather lookup failed")

    def test_forecast_network_error(self, monkeypatch):
        def fake_get(url, params=None, timeout=None):
            if "geocoding" in url:
                return FakeResponse(GEO_PAYLOAD)
            raise httpx.ConnectError("down")
        monkeypatch.setattr(logic.httpx, "get", fake_get)
        assert logic.get_weather("Tokyo")["error"].startswith("Weather forecast failed")

    def test_unknown_wmo_code(self, monkeypatch):
        payload = dict(FORECAST_PAYLOAD)
        payload["current"] = dict(FORECAST_PAYLOAD["current"], weather_code=999)
        monkeypatch.setattr(
            logic.httpx, "get", _fake_get_factory(GEO_PAYLOAD, payload)
        )
        result = logic.get_weather("Tokyo")
        assert result["current"]["condition"] == "unknown conditions"

    def test_days_clamped(self, monkeypatch):
        captured = {}

        def fake_get(url, params=None, timeout=None):
            captured.update(params or {})
            if "geocoding" in url:
                return FakeResponse(GEO_PAYLOAD)
            return FakeResponse(FORECAST_PAYLOAD)

        monkeypatch.setattr(logic.httpx, "get", fake_get)
        logic.get_weather("Tokyo", days=9)
        assert captured["forecast_days"] == 3
