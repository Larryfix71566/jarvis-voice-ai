"""Cross-process provenance and anchor races using synthetic local sources."""
import json
import os
import subprocess
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from jarvis import development_attestation as attestation
from jarvis.privacy_policy import DataPolicy, issue_tool_result, make_tool_execution_scope, validate_tool_result


@pytest.fixture
def authority(tmp_path, monkeypatch):
    home = tmp_path / "sandbox"
    home.mkdir(mode=0o700)
    monkeypatch.setenv("MORTIMER_SANDBOX_HOME", str(home))
    monkeypatch.setattr(attestation, "_issuers", {})
    monkeypatch.setattr(attestation, "_inflight_leases", set())
    monkeypatch.setattr(attestation, "_challenges", {})
    yield home
    for issuer in attestation._issuers.values():
        os.close(issuer.lease)
    attestation._issuers.clear()


def context():
    return {
        "owner_id": "creator-owner", "bot_session_id": str(uuid.uuid4()),
        "request_id": str(uuid.uuid4()), "developer_run_id": str(uuid.uuid4()),
        "creator_revision": "a" * 64, "skill_id": "public-fixture",
        "sandbox_job_id": str(uuid.uuid4()), "source_commit": "b" * 40,
    }


def scope(ctx, policy=DataPolicy("approved_external", "public-fixture")):
    return make_tool_execution_scope(ctx["developer_run_id"], "developer-task", "call-1", "file_read",
                                     {"path": "skills/public-fixture/SKILL.md"}, policy)


def receipt(ctx, call_scope, challenge, *, policy=DataPolicy("approved_external", "host-project")):
    result = issue_tool_result(call_scope, '{"ok":true,"content":"public fixture"}', policy,
                               "approved_development_source", ("source-sha",))
    return attestation.sign_tool_source(call_scope, result, context=ctx, challenge=challenge)


def test_import_and_bot_read_never_publish_authority(authority):
    assert not (authority / ".source-authority").exists()
    with pytest.raises(attestation.DevelopmentSourceAttestationError):
        attestation.pin_source_authority()
    assert not (authority / ".source-authority").exists()


def test_local_seal_is_reissued_for_distinct_bot_scope_and_input_floor(authority):
    pin = attestation.ensure_admin_source_authority()
    ctx = context()
    admin_scope = scope(ctx, DataPolicy("confidential", "verified-host-run"))
    bot_scope = scope(ctx)
    challenge = attestation.new_source_challenge()
    signed = receipt(ctx, admin_scope, challenge)
    result = attestation.verify_tool_source(pin, bot_scope, signed, context=ctx, challenge=challenge)
    policy, content = validate_tool_result(bot_scope, result)
    assert policy.level == "confidential"
    assert content == '{"ok":true,"content":"public fixture"}'
    assert "_seal" not in json.dumps(signed) and "_seal_key" not in json.dumps(signed)
    assert "public fixture" not in repr(result)
    with pytest.raises(attestation.DevelopmentSourceAttestationError):
        attestation.verify_tool_source(pin, bot_scope, signed, context=ctx, challenge=challenge)


@pytest.mark.parametrize("section,key,value", [
    (None, "protocol", "provider-policy"), (None, "generation", "c" * 64),
    (None, "key_id", "c" * 64), (None, "challenge", "c" * 64),
    (None, "issued_at", 0), (None, "expires_at", 9999999999),
    (None, "signature", "AAAA"),
    ("context", "owner_id", "other-owner"),
    ("context", "bot_session_id", str(uuid.uuid4())),
    ("context", "request_id", str(uuid.uuid4())),
    ("context", "developer_run_id", str(uuid.uuid4())),
    ("context", "creator_revision", "c" * 64),
    ("context", "skill_id", "other-skill"),
    ("context", "sandbox_job_id", str(uuid.uuid4())),
    ("context", "source_commit", "c" * 40),
    ("binding", "parent_request_id", str(uuid.uuid4())),
    ("binding", "task_id", "other-task"), ("binding", "tool_call_id", "other-call"),
    ("binding", "tool_name", "edit_propose"), ("binding", "argument_digest", "c" * 64),
    ("binding", "input_policy", {"level": "local_only", "source": "host"}),
    ("result", "content", "SYNTHETIC_TAMPER_CANARY"),
    ("result", "content_digest", "c" * 64),
    ("result", "policy", {"level": "approved_external", "source": "provider-json"}),
    ("result", "source_scope", "forged-source"),
    ("result", "canonical_refs", ["forged-url-root"]),
])
def test_each_wire_binding_requires_admin_signature(authority, section, key, value):
    pin = attestation.ensure_admin_source_authority()
    ctx, challenge = context(), attestation.new_source_challenge()
    call_scope = scope(ctx)
    signed = receipt(ctx, call_scope, challenge)
    (signed if section is None else signed[section])[key] = value
    with pytest.raises(attestation.DevelopmentSourceAttestationError) as error:
        attestation.verify_tool_source(pin, call_scope, signed, context=ctx, challenge=challenge)
    assert str(error.value) == "development_source_attestation_invalid"
    assert "CANARY" not in str(error.value)


def test_valid_approved_source_remains_approved_and_wrong_scope_refuses(authority):
    pin = attestation.ensure_admin_source_authority()
    ctx, challenge = context(), attestation.new_source_challenge()
    call_scope = scope(ctx)
    signed = receipt(ctx, call_scope, challenge)
    with pytest.raises(attestation.DevelopmentSourceAttestationError):
        attestation.verify_tool_source(pin, replace(call_scope, task_id="other-task"), signed,
                                      context=ctx, challenge=challenge)
    result = attestation.verify_tool_source(pin, call_scope, signed, context=ctx, challenge=challenge)
    assert validate_tool_result(call_scope, result)[0].level == "approved_external"


@pytest.mark.parametrize("mutation", ["replace-anchor", "replace-lease", "unsafe-anchor-mode", "unsafe-dir-mode"])
def test_pinned_authority_change_or_unsafe_modes_refuse(authority, mutation):
    pin = attestation.ensure_admin_source_authority()
    ctx, challenge = context(), attestation.new_source_challenge()
    call_scope = scope(ctx)
    signed = receipt(ctx, call_scope, challenge)
    directory = authority / ".source-authority"
    anchor = directory / "admin-ed25519-public.json"
    if mutation == "replace-anchor":
        duplicate = directory / "duplicate"
        duplicate.write_bytes(anchor.read_bytes())
        duplicate.chmod(0o600)
        duplicate.replace(anchor)
    elif mutation == "replace-lease":
        lease = directory / "admin-ed25519-public.lock"
        lease.unlink()
        lease.touch(mode=0o600)
    elif mutation == "unsafe-anchor-mode":
        anchor.chmod(0o644)
    else:
        directory.chmod(0o755)
    with pytest.raises(attestation.DevelopmentSourceAttestationError):
        attestation.verify_tool_source(pin, call_scope, signed, context=ctx, challenge=challenge)


@pytest.mark.parametrize("target", ["home", "directory", "anchor", "lease"])
def test_symlink_authority_is_never_followed_or_overwritten(authority, tmp_path, monkeypatch, target):
    if target == "home":
        link = tmp_path / "home-link"
        link.symlink_to(authority, target_is_directory=True)
        monkeypatch.setenv("MORTIMER_SANDBOX_HOME", str(link))
    else:
        directory = authority / ".source-authority"
        if target == "directory":
            other = tmp_path / "other-directory"
            other.mkdir(mode=0o700)
            directory.symlink_to(other, target_is_directory=True)
        else:
            directory.mkdir(mode=0o700)
            other = tmp_path / "public-canary"
            other.write_text("SYNTHETIC_CANARY")
            other.chmod(0o600)
            (directory / f"admin-ed25519-public.{'json' if target == 'anchor' else 'lock'}").symlink_to(other)
    with pytest.raises(attestation.DevelopmentSourceAttestationError):
        attestation.ensure_admin_source_authority()
    if target in {"anchor", "lease"}:
        assert other.read_text() == "SYNTHETIC_CANARY"


def test_one_process_initialization_is_idempotent_under_threads(authority):
    with ThreadPoolExecutor(max_workers=8) as pool:
        pins = list(pool.map(lambda _: attestation.ensure_admin_source_authority(), range(16)))
    assert all(pin == pins[0] for pin in pins)
    anchor = authority / ".source-authority/admin-ed25519-public.json"
    assert anchor.stat().st_mode & 0o777 == 0o600
    assert (authority / ".source-authority").stat().st_mode & 0o777 == 0o700
    assert "private" not in anchor.read_text()


def test_stale_authority_without_live_process_lease_refuses(authority):
    pin = attestation.ensure_admin_source_authority()
    issuer = attestation._issuers.pop(str(authority))
    os.close(issuer.lease)
    with pytest.raises(attestation.DevelopmentSourceAttestationError):
        attestation.pin_source_authority()
    replacement = attestation.ensure_admin_source_authority()
    assert replacement.generation != pin.generation


def test_signed_expired_challenge_refuses_without_raw_payload(authority, monkeypatch):
    pin = attestation.ensure_admin_source_authority()
    ctx, challenge = context(), attestation.new_source_challenge()
    call_scope = scope(ctx)
    signed = receipt(ctx, call_scope, challenge)
    original = attestation.time.monotonic()
    monkeypatch.setattr(attestation.time, "monotonic", lambda: original + 601)
    with pytest.raises(attestation.DevelopmentSourceAttestationError):
        attestation.verify_tool_source(pin, call_scope, signed, context=ctx, challenge=challenge)


def test_concurrent_verifiers_consume_a_challenge_exactly_once(authority):
    pin = attestation.ensure_admin_source_authority()
    ctx, challenge = context(), attestation.new_source_challenge()
    call_scope = scope(ctx)
    signed = receipt(ctx, call_scope, challenge)

    def verify(_):
        try:
            attestation.verify_tool_source(pin, call_scope, signed, context=ctx, challenge=challenge)
            return True
        except attestation.DevelopmentSourceAttestationError:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(verify, range(32))) == 1


def test_signed_unknown_challenge_and_stricter_bot_floor_refuse(authority):
    pin = attestation.ensure_admin_source_authority()
    ctx, challenge = context(), attestation.new_source_challenge()
    call_scope = scope(ctx)
    signed = receipt(ctx, call_scope, challenge)
    with pytest.raises(attestation.DevelopmentSourceAttestationError):
        attestation.verify_tool_source(pin, replace(call_scope, input_policy=DataPolicy("confidential", "caller")),
                                      signed, context=ctx, challenge=challenge)
    unknown = "f" * 64
    with pytest.raises(attestation.DevelopmentSourceAttestationError):
        attestation.verify_tool_source(pin, call_scope, receipt(ctx, call_scope, unknown),
                                      context=ctx, challenge=unknown)
    assert validate_tool_result(call_scope, attestation.verify_tool_source(
        pin, call_scope, signed, context=ctx, challenge=challenge,
    ))[0].level == "approved_external"


def test_exact_signed_wall_clock_expiry_refuses(authority, monkeypatch):
    pin = attestation.ensure_admin_source_authority()
    ctx, challenge = context(), attestation.new_source_challenge()
    call_scope = scope(ctx)
    signed = receipt(ctx, call_scope, challenge)
    monkeypatch.setattr(attestation.time, "time", lambda: signed["expires_at"])
    with pytest.raises(attestation.DevelopmentSourceAttestationError):
        attestation.verify_tool_source(pin, call_scope, signed, context=ctx, challenge=challenge)


@pytest.mark.parametrize("mutation", ["hard-link", "in-place", "ancestor-link"])
def test_additional_anchor_alias_and_rewrite_refuse(authority, tmp_path, monkeypatch, mutation):
    pin = attestation.ensure_admin_source_authority()
    ctx, challenge = context(), attestation.new_source_challenge()
    call_scope = scope(ctx)
    signed = receipt(ctx, call_scope, challenge)
    anchor = authority / ".source-authority/admin-ed25519-public.json"
    if mutation == "hard-link":
        os.link(anchor, authority / "hard-link")
    elif mutation == "in-place":
        value = json.loads(anchor.read_text())
        value["created_at"] = 0
        anchor.write_text(json.dumps(value))
    else:
        link = tmp_path / "ancestor-link"
        link.symlink_to(tmp_path, target_is_directory=True)
        monkeypatch.setenv("MORTIMER_SANDBOX_HOME", str(link / "sandbox"))
    with pytest.raises(attestation.DevelopmentSourceAttestationError):
        attestation.verify_tool_source(pin, call_scope, signed, context=ctx, challenge=challenge)


def test_fork_during_publication_cannot_inherit_unregistered_private_signer(authority):
    # Run the real fork in a fresh interpreter so pytest's own threads and
    # plugins are not forked. The child must not inherit an in-flight signer.
    script = """
import json,os,uuid
from jarvis import development_attestation as a
from jarvis.privacy_policy import DataPolicy,make_tool_execution_scope,issue_tool_result,validate_tool_result
ctx={'owner_id':'creator-owner','bot_session_id':str(uuid.uuid4()),'request_id':str(uuid.uuid4()),'developer_run_id':str(uuid.uuid4()),'creator_revision':'a'*64,'skill_id':'public-fixture','sandbox_job_id':str(uuid.uuid4())}
scope=make_tool_execution_scope(ctx['developer_run_id'],'task','call','file_read',{},DataPolicy('approved_external','public'))
result=issue_tool_result(scope,'public fixture',DataPolicy('approved_external','host'),'host-source')
challenge=a.new_source_challenge()
read,write=os.pipe()
publish=a._publish
child=False
pid=None
def fork_after_publish(directory,value):
    global child,pid
    publish(directory,value)
    pid=os.fork()
    if pid==0:
        child=True
        os.close(read)
    else:
        os.close(write)
a._publish=fork_after_publish
try:
    pin=a.ensure_admin_source_authority()
    receipt=a.sign_tool_source(scope,result,context=ctx,challenge=challenge)
    signed=True
except a.DevelopmentSourceAttestationError:
    signed=False
if child:
    os.write(write,json.dumps({'signed':signed}).encode())
    os.close(write)
    os._exit(0)
with os.fdopen(read) as pipe:
    child_result=json.load(pipe)
os.waitpid(pid,0)
verified=a.verify_tool_source(pin,scope,receipt,context=ctx,challenge=challenge)
print(json.dumps({'child_signed':child_result['signed'],'parent_signed':signed,'content':validate_tool_result(scope,verified)[1],'parent_live':a.pin_source_authority()==pin}))
"""
    completed = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=5)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "child_signed": False, "parent_signed": True, "content": "public fixture", "parent_live": True,
    }


def test_independent_admin_process_signs_and_excludes_competing_issuer(authority):
    ctx, challenge = context(), attestation.new_source_challenge()
    call_scope = scope(ctx)
    script = """
import json,sys
from jarvis import development_attestation as a
from jarvis.privacy_policy import DataPolicy,make_tool_execution_scope,issue_tool_result
data=json.loads(sys.stdin.readline())
a.ensure_admin_source_authority()
scope=make_tool_execution_scope(data['context']['developer_run_id'],'developer-task','call-1','file_read',{'path':'skills/public-fixture/SKILL.md'},DataPolicy('approved_external','public-fixture'))
result=issue_tool_result(scope,'public fixture',DataPolicy('approved_external','host-project'),'approved_development_source')
print(json.dumps(a.sign_tool_source(scope,result,context=data['context'],challenge=data['challenge'])),flush=True)
sys.stdin.readline()
"""
    child = subprocess.Popen([sys.executable, "-c", script], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        child.stdin.write(json.dumps({"context": ctx, "challenge": challenge}) + "\n")
        child.stdin.flush()
        signed = json.loads(child.stdout.readline())
        pin = attestation.pin_source_authority()
        with pytest.raises(attestation.DevelopmentSourceAttestationError):
            attestation.ensure_admin_source_authority()
        assert attestation.pin_source_authority() == pin  # contender cannot churn anchor
        result = attestation.verify_tool_source(pin, call_scope, signed, context=ctx, challenge=challenge)
        assert validate_tool_result(call_scope, result)[1] == "public fixture"
    finally:
        child.communicate("release\n", timeout=5)
    assert child.returncode == 0
