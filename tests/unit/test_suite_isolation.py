"""The suite must never point at the developer's real vault or cost ledger.

tests/conftest.py sets both paths at import time. It used setdefault, so a
JARVIS_VAULT_PATH exported in the shell won and the suite loaded real
credentials (2026-09-23). Live runs (RUN_LIVE=1) deliberately use the real
vault and ledger, so they are the one case this does not apply to.
"""
import os


def _throwaway(name: str) -> bool:
    return "mortimer-test-" in os.environ.get(name, "")


def test_real_vault_is_never_the_test_vault():
    if os.environ.get("RUN_LIVE") == "1":
        return  # live runs use the real vault on purpose (conftest exemption)
    assert _throwaway("JARVIS_VAULT_PATH"), os.environ.get("JARVIS_VAULT_PATH")


def test_real_cost_ledger_is_never_the_test_ledger():
    if os.environ.get("RUN_LIVE") == "1":
        return
    assert _throwaway("JARVIS_COSTS_DB"), os.environ.get("JARVIS_COSTS_DB")
