"""Unit tests for jarvis/research/crawl.py
(MORTIMER_SITE_RESEARCH_AND_COMPARISON_PLAN.md R2, R3, R5, R9). Pure —
an injected fake TavilyCrawlClient stands in for httpx, matching the
AdminClient-seam convention used throughout this repo's logic.py modules."""

from __future__ import annotations

from jarvis.research import crawl


class _FakeClient:
    """Records the last payload sent and returns a canned (status, body)."""

    def __init__(self, status: int, body: dict | None):
        self.status = status
        self.body = body
        self.last_json: dict | None = None
        self.last_url: str | None = None

    def post(self, url, headers, json):
        self.last_url = url
        self.last_json = json
        return (self.status, self.body)


def _ok_body(pages: list[tuple[str, str]], credits: int = 4) -> dict:
    return {
        "base_url": "https://example.com",
        "results": [{"url": u, "raw_content": c} for u, c in pages],
        "usage": {"credits": credits},
    }


# --------------------------------------------------------------------- R3

def test_crawl_always_sends_instructions():
    """R3 — instructions is ALWAYS present, even with an empty focus,
    because omitting it silently disables chunks_per_source."""
    client = _FakeClient(200, _ok_body([("https://a.com", "# A\nbody")]))
    crawl.crawl_site(client, "https://a.com", focus="", api_key="k")
    assert client.last_json["instructions"] == crawl.DEFAULT_FOCUS

    client2 = _FakeClient(200, _ok_body([("https://a.com", "# A\nbody")]))
    crawl.crawl_site(client2, "https://a.com", focus="pricing", api_key="k")
    assert client2.last_json["instructions"] == "pricing"
    assert "instructions" in client2.last_json  # never omitted


# --------------------------------------------------------------------- R2

def test_model_cannot_widen_crawl_bounds():
    """R2 — crawl_site's signature exposes no per-call override for
    max_depth/max_breadth/limit/etc.: only url, focus, api_key, config.
    Everything that shapes the request comes from config, not a caller-
    supplied field a model could set."""
    import inspect

    params = set(inspect.signature(crawl.crawl_site).parameters)
    assert params == {"client", "url", "focus", "api_key", "config"}


def test_limit_clamped_to_hard_cap():
    """R2 — a config `limit` above RESEARCH_HARD_PAGE_CAP is clamped,
    independent of what config says. Two bounds: config guards a model,
    the hard cap guards a config typo."""
    client = _FakeClient(200, _ok_body([("https://a.com", "x")]))
    cfg = {"limit": 5000, "chunks_per_source": 3, "max_depth": 2,
           "max_breadth": 20, "extract_depth": "basic", "timeout_s": 120}
    crawl.crawl_site(client, "https://a.com", focus="x", api_key="k", config=cfg)
    assert client.last_json["limit"] == crawl.RESEARCH_HARD_PAGE_CAP


def test_normal_limit_under_cap_is_unclamped():
    client = _FakeClient(200, _ok_body([("https://a.com", "x")]))
    cfg = {"limit": 10, "chunks_per_source": 3, "max_depth": 2,
           "max_breadth": 20, "extract_depth": "basic", "timeout_s": 120}
    crawl.crawl_site(client, "https://a.com", focus="x", api_key="k", config=cfg)
    assert client.last_json["limit"] == 10


# --------------------------------------------------------------------- R5

def test_digest_is_assembled_in_code_not_by_model():
    """R5 — build_site_digest is a pure, deterministic string builder over
    the crawl result; it takes no model, makes no call, and its output is
    reproducible from the same input every time."""
    result = {
        "ok": True, "url": "https://a.com", "page_count": 2,
        "pages": [
            {"url": "https://a.com/1", "title": "Home", "content": "Welcome."},
            {"url": "https://a.com/2", "title": "Pricing", "content": "$9/mo."},
        ],
    }
    digest1 = crawl.build_site_digest(result)
    digest2 = crawl.build_site_digest(result)
    assert digest1 == digest2  # deterministic
    assert "Home" in digest1 and "Pricing" in digest1
    assert "Welcome." in digest1 and "$9/mo." in digest1
    assert "https://a.com" in digest1


def test_digest_states_failure_plainly():
    result = {"ok": False, "url": "https://bad.com", "error": "timeout", "error_kind": "unreachable"}
    digest = crawl.build_site_digest(result)
    assert "CRAWL FAILED" in digest
    assert "timeout" in digest
    assert "unreachable" in digest


# --------------------------------------------------------------------- R9

def test_budget_error_distinguished_from_rate_limit():
    """R9 — 432/433 (plan/PayGo credit limit) is a distinct 'budget'
    taxonomy from 429 ('rate'), matching jarvis/keyhealth.py's rejected/
    unfunded/unreachable discipline: a budget problem and a rate problem
    call for different remediation and must never be reported the same."""
    for status in (432, 433):
        client = _FakeClient(status, {"detail": {"error": "plan limit exceeded"}})
        result = crawl.crawl_site(client, "https://a.com", "x", "k")
        assert result["ok"] is False
        assert result["error_kind"] == "budget"

    client = _FakeClient(429, {"detail": {"error": "rate limited"}})
    result = crawl.crawl_site(client, "https://a.com", "x", "k")
    assert result["ok"] is False
    assert result["error_kind"] == "rate"


def test_unreachable_vs_invalid_taxonomy():
    client = _FakeClient(500, {"detail": {"error": "internal error"}})
    assert crawl.crawl_site(client, "https://a.com", "x", "k")["error_kind"] == "unreachable"

    client2 = _FakeClient(401, {"detail": {"error": "bad key"}})
    assert crawl.crawl_site(client2, "https://a.com", "x", "k")["error_kind"] == "invalid"

    client3 = _FakeClient(0, None)  # timeout sentinel
    assert crawl.crawl_site(client3, "https://a.com", "x", "k")["error_kind"] == "unreachable"


def test_total_credits_sums_only_successful_sites():
    ok = {"ok": True, "credits": 4}
    failed = {"ok": False}
    assert crawl.total_credits(ok, failed) == 4
    assert crawl.total_credits(ok, ok) == 8
