"""WS-05 harness brief: the daily status job stays quiet and offline.

The scheduled `jarvis.status.daily.run()` reaches `model_access_status` through
its default `access_status` collector with an explicit registry. That is a
supplied snapshot, so the harness brief must be the fixed "not supplied" stub:
no cached-report read, no preference-store read, no public-document fetch, and
nothing that would make two identical days produce a daily notice.

Every other collector is the existing synthetic fixture from
test_status_daily.py; only `access_status` runs the real code path. Synthetic
data only; any socket connection fails the test.
"""
from __future__ import annotations

import json
import socket
from datetime import datetime, timezone

import pytest

from jarvis.status import daily as D
from jarvis.status import harness as H
from tests.unit.test_status_daily import _deps

DAY1 = datetime(2026, 10, 22, 10, 30, tzinfo=timezone.utc)
DAY2 = datetime(2026, 10, 23, 10, 30, tzinfo=timezone.utc)
STUB = {"ok": False, "error": "Harness reader not supplied for this snapshot."}


@pytest.fixture
def no_ambient_harness(monkeypatch):
    """Fail on any ambient harness read, fetch, passive run or network use."""
    monkeypatch.setattr(H, "read_report", lambda *a, **k: pytest.fail("harness.read_report called"))
    monkeypatch.setattr(H, "configured_selection",
                        lambda *a, **k: pytest.fail("harness.configured_selection called"))
    monkeypatch.setattr(H, "fetch_document", lambda *a, **k: pytest.fail("public document fetched"))
    monkeypatch.setattr(H, "run_passive", lambda *a, **k: pytest.fail("passive brief run by daily.run"))
    monkeypatch.setattr(socket.socket, "connect",
                        lambda *a, **k: pytest.fail("network connection attempted"))


def _real_access_deps():
    deps = _deps()
    del deps["access_status"]   # use daily's default: model_access_status(registry=...)
    return deps


def test_default_access_status_returns_the_fixed_stub(no_ambient_harness):
    registry = _deps()["registry"]()
    access_status = D._default_deps()["access_status"]
    first, second = access_status(registry), access_status(registry)
    assert first["harness_brief"] == STUB
    assert second["harness_brief"] == first["harness_brief"]
    assert first["coverage_gaps"] == []


def test_two_identical_days_write_no_notice_and_no_harness_state(tmp_path, no_ambient_harness):
    notices = []
    day1 = D.run(status_dir=tmp_path, deps=_real_access_deps(), now=DAY1,
                 notice=lambda *a: notices.append(a) or 1)
    day2 = D.run(status_dir=tmp_path, deps=_real_access_deps(), now=DAY2,
                 notice=lambda *a: notices.append(a) or 1)

    assert notices == []
    assert day1["notice"] is None and day2["notice"] is None
    assert not D.has_changes(day2["changes"])
    for snap in (day1, day2):
        assert snap["coverage_gaps"] == []
        assert not any(e["step"] == "model_access_status" for e in snap["errors"])
    # The snapshot keeps only coverage gaps from access status; the brief never lands.
    for path in sorted(tmp_path.glob("daily-*.json")):
        assert "harness" not in json.loads(path.read_text())
    assert not (tmp_path / H.REPORT_NAME).exists()
