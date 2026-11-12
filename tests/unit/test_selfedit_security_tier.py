"""WS-34 B3: security modules and config/model_access.yaml belong in the
self-edit deny tier (Tier 0).

The deny entries themselves are a HUMAN commit to config/self_edit_allowlist.json
(C8 rule); they ship as docs/plans/ws34-b3-allowlist.patch. This file lands
before that commit, so the exposure report is informational and asserts nothing.
"""
from __future__ import annotations

from pathlib import Path

from jarvis.selfedit.allowlist import DENIED, Allowlist

REPO_ROOT = Path(__file__).resolve().parents[2]
ALLOWLIST_JSON = REPO_ROOT / "config" / "self_edit_allowlist.json"

# Set A (B2_B3_B4_PLAN.md section 2).
SECURITY_TIER = (
    "jarvis/auth.py",
    "jarvis/authmw.py",
    "jarvis/bind.py",
    "jarvis/request_guard.py",
    "jarvis/tenant.py",
    "jarvis/sensitive.py",
    "jarvis/bot/sensitive_turn.py",
    "jarvis/privacy_policy.py",
    "jarvis/development_attestation.py",
    "jarvis/provider_access.py",
    "config/model_access.yaml",
    "mcp_servers/development_boundary.py",
    "jarvis/bot/phone_remote_auth_proof.py",
    "jarvis/bot/phone_remote_login.py",
    "jarvis/bot/phone_admission.py",
    "jarvis/bot/phone_admission_store.py",
    "jarvis/bot/phone_remote_authority_channel.py",
    "jarvis/bot/phone_remote_recovery.py",
    "scripts/set_github_token.sh",
    "scripts/backup_db.py",
    "scripts/restore_check.py",
)

# Not on `next` yet: jarvis/request_guard.py ships with B2 (PR #342) and
# scripts/restore_check.py with B4 (PR #341). Remove from here once both merge.
PENDING_PATHS = (
    "jarvis/request_guard.py",
    "scripts/restore_check.py",
)


def test_security_tier_paths_exist() -> None:
    """A rename must fail loudly: a deny entry for a moved file protects nothing."""
    missing = [
        p for p in SECURITY_TIER
        if p not in PENDING_PATHS and not (REPO_ROOT / p).exists()
    ]
    assert not missing, f"security-tier paths missing from the tree: {missing}"


def test_report_security_tier_exposure(capsys) -> None:
    """INFORMATIONAL, asserts nothing. Reports which Set A paths a self-edit
    can still change; Larry's B3 allowlist commit empties the list."""
    allowlist = Allowlist.load(ALLOWLIST_JSON)
    exposed = [p for p in SECURITY_TIER if allowlist.tier(p) != DENIED]
    with capsys.disabled():
        print("\nB3 self-edit exposure: "
              + (", ".join(exposed) if exposed else "none — B3 commit is in"))
