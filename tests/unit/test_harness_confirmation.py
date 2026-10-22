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


def test_removed_saved_profile_can_be_repaired_without_inventing_current_model():
    P.confirm_preference(draft()["draft_id"])
    with get_conn() as db:
        db.execute("UPDATE model_route_preferences SET profile='removed-profile' WHERE workload='developer'")
    repair=draft()
    current=repair["proposal"]["current"]
    assert current["profile"] == "removed-profile" and current["model"] is None
    assert current["resolution_state"] == "unresolved"
    assert P.confirm_preference(repair["draft_id"])["state"] == "saved"
    assert P.list_preferences()[0]["profile"] == "claude-opus"


def test_unresolved_override_is_bound_and_changed_override_refuses(monkeypatch):
    monkeypatch.setenv("JARVIS_MODEL_PROFILE_DEVELOPER", "removed-profile")
    repair=draft()
    assert repair["proposal"]["current"]["model"] is None
    monkeypatch.setenv("JARVIS_MODEL_PROFILE_DEVELOPER", "another-removed-profile")
    with pytest.raises(P.ModelPreferenceError,match="stale"):
        P.confirm_preference(repair["draft_id"])
    assert not P.list_preferences()


def test_remaining_route_errors_use_preference_error_envelope(monkeypatch):
    monkeypatch.setattr(P,"_identity",lambda *a,**kw: (_ for _ in ()).throw(P.ModelRouteError("synthetic identity failure")))
    with pytest.raises(P.ModelPreferenceError,match="synthetic identity failure"):
        draft()
    assert not P.list_preferences()


def test_validation_cannot_use_transient_different_configuration(monkeypatch):
    d=draft(); original=P.inspect_route_choice; calls=[]
    def transient(*args,**kwargs):
        values=original(*args,**kwargs); calls.append(args)
        # Preview current + candidate use A; validator sees B; later reads would
        # return A again. Bind what was actually validated, not just two reads.
        if len(calls)==3:
            policy,record,access=values
            return policy,dict(record,model="synthetic-transient-model"),access
        return values
    monkeypatch.setattr(P,"inspect_route_choice",transient)
    with pytest.raises(P.ModelPreferenceError,match="validation configuration changed"):
        P.confirm_preference(d["draft_id"])
    assert len(calls)==3 and not P.list_preferences()


@pytest.mark.parametrize("during_validation",["none","draft","current","configuration"])
def test_catalog_wait_releases_writer_and_rechecks_afterward(monkeypatch,during_validation):
    from tests.unit.test_model_preferences import _confidential_catalog
    import sqlite3,os
    monkeypatch.setenv("SAYGM_API_KEY","synthetic-key")
    monkeypatch.setattr("jarvis.saygm.fetch_catalog",lambda **kw:_confidential_catalog())
    d=P.stage_preference("memory","claude-sonnet-5","saygm","confidential")
    checks=[]; original=P.inspect_route_choice
    def catalog(**kwargs):
        # Real independent SQLite writer succeeds while fake network validation
        # is pending. This would raise 'database is locked' in the prior patch.
        with sqlite3.connect(os.environ["JARVIS_DB_PATH"],timeout=0) as other:
            other.execute("BEGIN IMMEDIATE")
            if during_validation=="draft":
                other.execute("UPDATE model_route_drafts SET route='local' WHERE draft_id=?",(d["draft_id"],))
            elif during_validation=="current":
                other.execute("INSERT INTO model_route_preferences(workload,profile,route,privacy,updated_at) VALUES ('memory','claude-sonnet-5','local','confidential','synthetic')")
        if during_validation=="configuration":
            def changed(*args,**kw):
                policy,record,access=original(*args,**kw)
                return policy,dict(record,model="synthetic-changed-model"),access
            monkeypatch.setattr(P,"inspect_route_choice",changed)
        checks.append("writer available")
        return _confidential_catalog()
    monkeypatch.setattr("jarvis.saygm.fetch_catalog",catalog)
    if during_validation=="none":
        assert P.confirm_preference(d["draft_id"])["state"]=="saved"
    else:
        with pytest.raises(P.ModelPreferenceError,match="stale|changed"):
            P.confirm_preference(d["draft_id"])
        assert all(x["route"]!="saygm" for x in P.list_preferences())
    assert checks==["writer available"]


@pytest.mark.asyncio
async def test_voice_preview_describes_unresolved_current_selection(monkeypatch):
    from jarvis.bot.model_route_tool import handle_model_route
    monkeypatch.setenv("JARVIS_MODEL_PROFILE_DEVELOPER","removed-profile")
    result=await handle_model_route(dict(workload="developer",profile="claude-opus",route="direct_api",confirm=False))
    assert "Configured selection: unresolved" in result and "Proposed selection:" in result
    assert "v1:" not in result
