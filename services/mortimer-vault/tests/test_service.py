"""Exercise the bundled HTTP service using disposable data only."""
import importlib
import sys

from fastapi.testclient import TestClient


def test_http_document_round_trip(home):
    # The service initializes its storage on import; the home fixture must
    # set MORTIMER_HOME first, before importing any service code.
    service = importlib.import_module("mortimer_vault.service")
    try:
        with TestClient(service.app) as client:
            health = client.get("/health")
            assert health.status_code == 200
            assert health.json()["status"] == "ok"
            created = client.post("/write", json={
                "id": "sandbox-document", "type": "area",
                "body": "Synthetic sandbox knowledge", "tags": ["test"],
                "confidence": "high", "source_sessions": [],
            })
            assert created.status_code == 200, created.text
            read = client.post("/read", json={"id": "sandbox-document"})
            assert read.status_code == 200
            assert read.json()["body"] == "Synthetic sandbox knowledge"
            search = client.post("/search", json={"query": "sandbox"})
            assert search.status_code == 200
            assert "sandbox-document" in [item["id"] for item in search.json()["results"]]
            assert client.post("/read", json={"id": "missing-document"}).status_code == 404
            assert client.post("/flush_access").status_code == 200
            assert service._paths.home == home
    finally:
        sys.modules.pop("mortimer_vault.service", None)
