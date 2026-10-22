"""Exact approvals, synthetic metadata and temporary SQLite only."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import pytest
from jarvis import model_preferences as P
from jarvis.db import get_conn

@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path/"preferences.db"))
    monkeypatch.setenv("JARVIS_LLM_ACCESS_MODE", "legacy")

def draft():
    return P.stage_preference("developer", "claude-opus", "direct_api")

def test_exact_preview_saved_readback_not_runtime_adoption():
    d=draft()
    assert d["proposal"]["current"]["model"]
    assert d["draft_id"].endswith(":"+d["proposal_digest"])
    assert not P.list_preferences()
    result=P.confirm_preference(d["draft_id"])
    assert result["state"] == "saved" and result["runtime_adoption"] == "unverified"
    assert result["configured_model"] == d["proposal"]["candidate"]["model"]
    assert result["saved_preference"]["profile"] == d["profile"]

@pytest.mark.parametrize("change", ["model", "endpoint", "capabilities", "privacy", "limits"])
def test_mutated_registry_route_requires_new_confirmation(monkeypatch, change):
    d=draft(); original=P.inspect_route_choice
    def changed(*args, **kwargs):
        policy, profile, access=original(*args, **kwargs)
        if change == "model": profile=dict(profile, model="synthetic-changed-id")
        elif change == "endpoint": access=replace(access,base_url="https://synthetic.invalid/v1")
        elif change == "capabilities": access=replace(access,capabilities=(*access.capabilities,"synthetic"))
        elif change == "privacy": access=replace(access,privacy="local_only")
        elif change == "limits": policy=replace(policy,limits=replace(policy.limits,max_output_tokens_per_call=37))
        return policy,profile,access
    monkeypatch.setattr(P,"inspect_route_choice",changed)
    with pytest.raises(P.ModelPreferenceError,match="stale"): P.confirm_preference(d["draft_id"])
    assert not P.list_preferences()

def test_newer_preference_invalidates_earlier_approval():
    old=draft(); new=draft(); P.confirm_preference(new["draft_id"])
    with pytest.raises(P.ModelPreferenceError,match="stale"): P.confirm_preference(old["draft_id"])

def test_changed_access_mode_invalidates_draft(monkeypatch):
    d=draft(); monkeypatch.setenv("JARVIS_LLM_ACCESS_MODE","direct_apis_disabled")
    with pytest.raises(P.ModelPreferenceError,match="stale"): P.confirm_preference(d["draft_id"])

def test_expired_and_legacy_drafts_fail_closed():
    d=draft()
    with get_conn() as db: db.execute("UPDATE model_route_drafts SET expires_at='2000-01-01T00:00:00+00:00' WHERE draft_id=?",(d["draft_id"],))
    with pytest.raises(P.ModelPreferenceError,match="expired"): P.confirm_preference(d["draft_id"])
    d=draft()
    with get_conn() as db: db.execute("UPDATE model_route_drafts SET draft_id='old-token' WHERE draft_id=?",(d["draft_id"],))
    with pytest.raises(P.ModelPreferenceError,match="legacy"): P.confirm_preference("old-token")
    assert not P.list_preferences()

def test_concurrent_replay_saves_once():
    d=draft()
    def consume(_):
        try: return P.confirm_preference(d["draft_id"])["state"]
        except P.ModelPreferenceError: return "refused"
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(consume,range(2))) == ["refused","saved"]
    assert len(P.list_preferences()) == 1

def test_failed_save_rolls_back_draft_consumption():
    d=draft()
    with get_conn() as db: db.execute("CREATE TRIGGER fail_insert BEFORE INSERT ON model_route_preferences BEGIN SELECT RAISE(ABORT,'synthetic'); END")
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError): P.confirm_preference(d["draft_id"])
    assert not P.list_preferences()
    with get_conn() as db:
        assert db.execute("SELECT 1 FROM model_route_drafts WHERE draft_id=?",(d["draft_id"],)).fetchone()
        db.execute("DROP TRIGGER fail_insert")
    assert P.confirm_preference(d["draft_id"])["state"] == "saved"


def test_existing_harness_draft_cannot_bypass_block():
    d=draft()
    with get_conn() as db:
        db.execute("UPDATE model_route_drafts SET workload='voice_supervisor' WHERE draft_id=?",(d["draft_id"],))
    with pytest.raises(P.ModelPreferenceError,match="Harness switching is unavailable"):
        P.confirm_preference(d["draft_id"])
    assert not P.list_preferences()

@pytest.mark.asyncio
async def test_voice_confirmation_never_reaches_persistence(monkeypatch):
    from jarvis.bot.model_route_tool import handle_model_route
    d=draft()
    monkeypatch.setattr(P,"confirm_preference",lambda *a,**kw:pytest.fail("voice confirmation sink"))
    result=await handle_model_route(dict(workload="developer",profile="claude-opus",route="direct_api",confirm=True,draft_id=d["draft_id"]))
    assert "Voice confirmation is unavailable" in result
    assert not P.list_preferences()

@pytest.mark.asyncio
async def test_voice_preview_has_exact_identity_but_no_approval_token():
    from jarvis.bot.model_route_tool import handle_model_route
    result=await handle_model_route(dict(workload="developer",profile="claude-opus",route="direct_api",confirm=False))
    assert "Configured selection:" in result and "Proposed selection:" in result
    assert "Eligibility and active runtime are unverified" in result
    assert "v1:" not in result
    assert not P.list_preferences()
