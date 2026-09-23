from __future__ import annotations

from scripts.audit_model_call_sites import build_report


def test_production_model_call_sites_have_reviewed_ownership():
    report = build_report()
    assert report["counts"]["total"] >= 13
    assert report["counts"]["review_required"] == 0
    assert any(
        item["owner"] == "voice_exempt"
        for item in report["call_sites"]
    )
    assert any(
        item["owner"] == "mixed_routed"
        for item in report["call_sites"]
    )
