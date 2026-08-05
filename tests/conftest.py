import sys
from pathlib import Path

# Ensure the repository root is importable when pytest runs from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os

import pytest

from jarvis.db import run_migrations


def pytest_collection_modifyitems(config, items):
    """`live` tests call real external APIs; they run only with RUN_LIVE=1."""
    if os.environ.get("RUN_LIVE") == "1":
        return
    skip_live = pytest.mark.skip(reason="live test — set RUN_LIVE=1 to enable")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    """Point JARVIS_DB_PATH at a migrated temp database (notes/reminders tests)."""
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("JARVIS_DB_PATH", str(db_path))
    run_migrations()
    return db_path
