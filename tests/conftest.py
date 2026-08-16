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


@pytest.fixture(autouse=True)
def _stub_procedures_learning(monkeypatch):
    """Safety default (MORTIMER_MEMORY_PROCEDURES_PLAN.md D13): every call
    through jarvis.agents.delegate.build_delegate_tool's handler
    unconditionally spawns jarvis.procedures.learn_from_run as a
    fire-and-forget background task after the delegation returns. Left
    un-stubbed, any test that drives that handler (most of
    tests/unit/test_delegate.py and the delegating-mode tests in
    tests/unit/test_orchestrator.py) would silently trigger a real
    jarvis.config.load_settings() call — which reads this repo's real
    .env — and, if it succeeds, a real LLM network call plus a write
    against the real data/jarvis.db. Tests that want to exercise
    learn_from_run itself re-patch jarvis.agents.delegate.learn_from_run
    (or call jarvis.procedures.learn_from_run directly) within the test
    body, which overrides this default for that test only."""
    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr(
        "jarvis.agents.delegate.learn_from_run", _noop, raising=False
    )
