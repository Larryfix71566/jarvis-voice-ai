import sys
from pathlib import Path

# Ensure the repository root is importable when pytest runs from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os
import tempfile

import pytest

# Test isolation for the credential vault (MORTIMER_CREDENTIAL_VAULT_
# PLAN.md): once a real data/secrets.vault exists on a dev machine,
# load_settings() — and jarvis.admin.server's IMPORT-TIME inject_env()
# call, which runs during collection, before any fixture — would decrypt
# real credentials into the test process environment. Point the vault at
# a nonexistent path at conftest-import time, which precedes every test-
# module import. Module-level on purpose: a fixture is too late for
# import-time side effects. Exemption: RUN_LIVE=1 runs deliberately use
# real credentials, which post-migration live in the vault — those keep
# real injection. test_vault.py's own autouse fixture overrides the path
# per-test to exercise a real (temp) vault.
if os.environ.get("RUN_LIVE") != "1":
    os.environ.setdefault(
        "JARVIS_VAULT_PATH",
        os.path.join(tempfile.mkdtemp(prefix="mortimer-test-"), "no.vault"),
    )

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
