"""Unit tests for the admin sidecar's graph endpoints (MORTIMER_GRAPH_LAYER_
PLAN.md GL11, §5 step 10). TestClient(app) with JARVIS_DB_PATH on a temp
file — the test_admin_council.py pattern. These endpoints are thin: every
edge is derived in jarvis.graphs, so these tests pin shape/status-code/
content-type contracts, not graph-building logic (covered in
test_graphs_*.py)."""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from jarvis.admin.server import app
from jarvis.db import get_conn, now_iso, run_migrations
from jarvis.graphs import config as gcfg


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    db_path = tmp_path / "admin_graph_test.db"
    monkeypatch.setenv("JARVIS_DB_PATH", str(db_path))
    conn = get_conn(db_path)
    run_migrations(conn)
    conn.execute(
        "INSERT INTO memories (kind, key, content, created_at, updated_at, tier) "
        "VALUES ('fact', 'user.style.a', 'short answers', ?, ?, 'preference')",
        (now_iso(), now_iso()),
    )
    conn.commit()
    conn.close()
    return db_path


def test_graph_json_ok_shape():
    c = TestClient(app)
    res = c.get("/api/graph/memory").json()
    assert res["ok"] is True
    assert set(res) == {
        "ok", "graph", "focus", "depth", "edge_types", "node_count",
        "edge_count", "truncated", "truncated_reason", "nodes", "edges",
        "legend",
    }


def test_graph_json_reserved_name():
    c = TestClient(app)
    res = c.get("/api/graph/knowledge").json()
    assert res["ok"] is False
    assert "not built yet" in res["error"]


def test_graph_json_unknown_name():
    c = TestClient(app)
    res = c.get("/api/graph/nonsense").json()
    assert res["ok"] is False
    assert "unknown graph" in res["error"]


def test_graph_image_png_content_type_and_size():
    c = TestClient(app)
    res = c.get("/api/graph/memory/image.png", params={"w": 500, "h": 400})
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/png"
    img = Image.open(io.BytesIO(res.content))
    assert img.size == (500, 400)


def test_graph_image_svg_content_type():
    c = TestClient(app)
    res = c.get("/api/graph/memory/image.svg")
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/svg+xml"


def test_graph_image_error_still_200_png():
    c = TestClient(app)
    res = c.get("/api/graph/memory/image.png", params={"focus": "zzz-nothing"})
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/png"
    img = Image.open(io.BytesIO(res.content))
    assert img.size[0] > 0 and img.size[1] > 0


def test_graph_image_bad_fmt_404():
    c = TestClient(app)
    res = c.get("/api/graph/memory/image.jpg")
    assert res.status_code == 404


def test_graph_disabled_env(monkeypatch):
    monkeypatch.setenv("JARVIS_GRAPHS_ENABLED", "false")
    c = TestClient(app)
    res = c.get("/api/graph/memory").json()
    assert res["ok"] is False

    img_res = c.get("/api/graph/memory/image.png")
    assert img_res.status_code == 200
    assert img_res.headers["content-type"] == "image/png"


def test_size_query_is_clamped():
    c = TestClient(app)
    low = c.get("/api/graph/memory/image.png", params={"w": 10})
    img = Image.open(io.BytesIO(low.content))
    assert img.size[0] == gcfg.GRAPH_IMAGE_MIN_PX

    high = c.get("/api/graph/memory/image.png", params={"w": 99999})
    img = Image.open(io.BytesIO(high.content))
    assert img.size[0] == gcfg.GRAPH_IMAGE_MAX_PX
