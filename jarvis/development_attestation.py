"""Local admin-to-bot source attestations; no provider or guest authority.

Importing this module publishes nothing. Only the authenticated admin creator
association initializes the signer. Its private key stays in process memory;
the fixed owner-only host anchor contains public verification material.
"""
from __future__ import annotations

import base64
import errno
import fcntl
import hashlib
import json
import math
import os
import re
import secrets
import stat
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from jarvis.privacy_policy import (
    DataPolicy, ToolExecutionScope, ToolResultEnvelope, _json_text,
    issue_tool_result, strictest, validate_tool_result,
)
from jarvis.tenant import is_valid_user_id

PROTOCOL = "mortimer.development-source.v1"
WORKSPACE_PROTOCOL = "mortimer.workspace-source.v1"
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}\Z")
_SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_REQUIRED_CONTEXT = frozenset({
    "owner_id", "bot_session_id", "request_id", "developer_run_id",
    "creator_revision", "skill_id", "sandbox_job_id",
})
_OPTIONAL_CONTEXT = frozenset({"sandbox_session_id", "sandbox_task_id", "source_commit"})
_DIRECTORY = ".source-authority"
_ANCHOR = "admin-ed25519-public.json"
_LEASE = "admin-ed25519-public.lock"
_TTL = 600.0
_lock = threading.RLock()
_issuers: dict[str, "_Issuer"] = {}
_inflight_leases: set[int] = set()
_challenges: dict[str, float] = {}


class DevelopmentSourceAttestationError(ValueError):
    """One fixed payload-free provenance refusal."""

    def __init__(self) -> None:
        super().__init__("development_source_attestation_invalid")


@dataclass(frozen=True)
class AuthorityPin:
    key_id: str
    generation: str
    _public_key: bytes = field(repr=False)
    _home: str = field(repr=False)
    _identity: tuple = field(repr=False)


@dataclass
class _Issuer:
    key: Ed25519PrivateKey = field(repr=False)
    pin: AuthorityPin
    lease: int = field(repr=False)
    pid: int


def _after_fork() -> None:
    # Forked children must not use or keep the admin issuer. Descriptors also
    # carry CLOEXEC; closing here does not unlock the parent's open-file lease.
    global _issuers, _inflight_leases, _challenges, _lock
    for descriptor in {issuer.lease for issuer in _issuers.values()} | _inflight_leases:
        try:
            os.close(descriptor)
        except OSError:
            pass
    _issuers, _inflight_leases, _challenges, _lock = {}, set(), {}, threading.RLock()


os.register_at_fork(after_in_child=_after_fork)


def _clock(value: object) -> float:
    if type(value) not in {int, float} or not math.isfinite(value) or value < 0:
        raise DevelopmentSourceAttestationError()
    return float(value)


def _canonical(value: object) -> bytes:
    try:
        return _json_text(value).encode("utf-8")
    except (ValueError, TypeError, AttributeError, RecursionError):
        raise DevelopmentSourceAttestationError() from None


def _context(value: object) -> dict[str, str]:
    if (type(value) is not dict or not _REQUIRED_CONTEXT <= value.keys()
            or value.keys() - _REQUIRED_CONTEXT - _OPTIONAL_CONTEXT
            or any(type(item) is not str or not _ID.fullmatch(item) for item in value.values())
            or not is_valid_user_id(value["owner_id"])
            or not _HEX.fullmatch(value["creator_revision"])
            or not _SLUG.fullmatch(value["skill_id"])):
        raise DevelopmentSourceAttestationError()
    try:
        for name in ("bot_session_id", "request_id", "developer_run_id", "sandbox_job_id"):
            if str(uuid.UUID(value[name])) != value[name]:
                raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise DevelopmentSourceAttestationError() from None
    return dict(value)


def _workspace_context(value: object) -> dict[str, str]:
    required = {"owner_id", "bot_session_id", "developer_run_id", "workspace_kind", "lineage_id"}
    optional = {"sandbox_job_id", "sandbox_session_id", "sandbox_task_id", "source_commit"}
    if (type(value) is not dict or not required <= value.keys()
            or value.keys() - required - optional
            or any(type(item) is not str or not _ID.fullmatch(item) for item in value.values())
            or not is_valid_user_id(value["owner_id"])
            or value["workspace_kind"] not in {"selfedit", "app-build"}):
        raise DevelopmentSourceAttestationError()
    try:
        for name in ("bot_session_id", "developer_run_id", "sandbox_job_id"):
            if name in value and str(uuid.UUID(value[name])) != value[name]:
                raise ValueError()
        if "source_commit" in value and not re.fullmatch(r"[0-9a-f]{40,64}", value["source_commit"]):
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise DevelopmentSourceAttestationError() from None
    return dict(value)


def _home() -> Path:
    path = Path(os.environ.get(
        "MORTIMER_SANDBOX_HOME", str(Path.home() / "Documents/Codex/MortimerSandbox"),
    ))
    if not path.is_absolute() or ".." in path.parts:
        raise DevelopmentSourceAttestationError()
    return path


def _owner_stat(metadata: os.stat_result, *, directory: bool = False) -> None:
    if (metadata.st_uid != os.getuid()
            or (not stat.S_ISDIR(metadata.st_mode) if directory else not stat.S_ISREG(metadata.st_mode))
            or (stat.S_IMODE(metadata.st_mode) != 0o700 if directory else
                stat.S_IMODE(metadata.st_mode) != 0o600 or metadata.st_nlink != 1)):
        raise DevelopmentSourceAttestationError()


def _directory(home: Path, *, create: bool = False) -> int:
    try:
        # A path string supplied by response JSON can never choose authority.
        # Reject symlinks in every existing host path component before using
        # O_NOFOLLOW directory handles for the authority itself.
        for component in (home, *home.parents):
            if component.is_symlink():
                raise DevelopmentSourceAttestationError()
        home_meta = home.stat()
        if (not stat.S_ISDIR(home_meta.st_mode) or home_meta.st_uid != os.getuid()
                or stat.S_IMODE(home_meta.st_mode) & 0o022):
            raise DevelopmentSourceAttestationError()
        parent = os.open(home, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            if create:
                try:
                    os.mkdir(_DIRECTORY, mode=0o700, dir_fd=parent)
                except FileExistsError:
                    pass
            descriptor = os.open(_DIRECTORY, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                 dir_fd=parent)
            try:
                _owner_stat(os.fstat(descriptor), directory=True)
            except BaseException:
                os.close(descriptor)
                raise
            return descriptor
        finally:
            os.close(parent)
    except (OSError, ValueError):
        raise DevelopmentSourceAttestationError() from None


def _file(directory: int, name: str, *, create: bool = False) -> int:
    descriptor = os.open(name, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC
                         | (os.O_CREAT if create else 0), mode=0o600, dir_fd=directory)
    try:
        _owner_stat(os.fstat(descriptor))
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def _pin(home: Path) -> AuthorityPin:
    directory = _directory(home)
    try:
        lease = _file(directory, _LEASE)
        try:
            lease_meta = os.fstat(lease)
            try:
                fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                if exc.errno not in {errno.EAGAIN, errno.EACCES}:
                    raise
            else:
                fcntl.flock(lease, fcntl.LOCK_UN)
                raise DevelopmentSourceAttestationError()  # stale anchor without a live admin lease
        finally:
            os.close(lease)
        descriptor = _file(directory, _ANCHOR)
        try:
            metadata = os.fstat(descriptor)
            if metadata.st_size > 8192:
                raise DevelopmentSourceAttestationError()
            encoded = os.read(descriptor, 8193)
        finally:
            os.close(descriptor)
        value = json.loads(encoded)
        if (type(value) is not dict or set(value) != {
                "protocol", "key_id", "generation", "public_key", "created_at"}
                or value["protocol"] != PROTOCOL
                or type(value["generation"]) is not str or not _HEX.fullmatch(value["generation"])
                or type(value["public_key"]) is not str
                or _clock(value["created_at"]) > _clock(time.time())):
            raise DevelopmentSourceAttestationError()
        public = base64.b64decode(value["public_key"], validate=True)
        if len(public) != 32 or value["key_id"] != hashlib.sha256(public).hexdigest():
            raise DevelopmentSourceAttestationError()
        return AuthorityPin(value["key_id"], value["generation"], public, str(home), (
            os.fstat(directory).st_dev, os.fstat(directory).st_ino,
            lease_meta.st_dev, lease_meta.st_ino, lease_meta.st_uid, lease_meta.st_mode,
            metadata.st_dev, metadata.st_ino, metadata.st_uid, metadata.st_mode,
            hashlib.sha256(encoded).hexdigest(),
        ))
    finally:
        os.close(directory)


def pin_source_authority() -> AuthorityPin:
    """Read the fixed trusted host anchor; never accept an HTTP public key."""
    try:
        return _pin(_home())
    except (OSError, ValueError, TypeError, KeyError):
        raise DevelopmentSourceAttestationError() from None


def _publish(directory: int, value: dict) -> None:
    try:
        _owner_stat(os.stat(_ANCHOR, dir_fd=directory, follow_symlinks=False))
    except FileNotFoundError:
        pass
    temporary = ".pending-" + secrets.token_hex(16)
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                         mode=0o600, dir_fd=directory)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(_canonical(value))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, _ANCHOR, src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)
    finally:
        try:
            os.unlink(temporary, dir_fd=directory)
        except FileNotFoundError:
            pass


def ensure_admin_source_authority() -> AuthorityPin:
    """Admin-only lazy initialization, with one process owning the lifetime lease."""
    try:
        initializer_pid = os.getpid()
        home = _home()
        with _lock:
            existing = _issuers.get(str(home))
            if existing is not None:
                if existing.pid != os.getpid() or _pin(home) != existing.pin:
                    raise DevelopmentSourceAttestationError()
                return existing.pin
            directory = _directory(home, create=True)
            lease = None
            try:
                lease = _file(directory, _LEASE, create=True)
                if os.getpid() != initializer_pid:
                    os.close(lease)
                    lease = None
                    raise DevelopmentSourceAttestationError()
                _inflight_leases.add(lease)
                fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
                key = Ed25519PrivateKey.generate()
                public = key.public_key().public_bytes(
                    serialization.Encoding.Raw, serialization.PublicFormat.Raw,
                )
                if os.getpid() != initializer_pid:
                    raise DevelopmentSourceAttestationError()
                _publish(directory, {
                    "protocol": PROTOCOL, "key_id": hashlib.sha256(public).hexdigest(),
                    "generation": secrets.token_hex(32),
                    "public_key": base64.b64encode(public).decode("ascii"),
                    "created_at": _clock(time.time()),
                })
                if os.getpid() != initializer_pid:
                    raise DevelopmentSourceAttestationError()
                pin = _pin(home)
                _issuers[str(home)] = _Issuer(key, pin, lease, initializer_pid)
                _inflight_leases.discard(lease)
                lease = None  # the issuer holds this lease until process exit
                return pin
            finally:
                if lease is not None and os.getpid() == initializer_pid:
                    _inflight_leases.discard(lease)
                    os.close(lease)
                os.close(directory)
    except (OSError, ValueError, TypeError, KeyError):
        raise DevelopmentSourceAttestationError() from None


def new_source_challenge() -> str:
    """Create a one-use, process-local verifier challenge before the HTTP call."""
    with _lock:
        now = time.monotonic()
        for old, started in list(_challenges.items()):
            if now - started >= _TTL:
                _challenges.pop(old, None)
        if len(_challenges) >= 4096:
            raise DevelopmentSourceAttestationError()
        challenge = secrets.token_hex(32)
        _challenges[challenge] = now
        return challenge


def _binding(scope: ToolExecutionScope) -> dict:
    return {
        "parent_request_id": scope.parent_request_id, "task_id": scope.task_id,
        "tool_call_id": scope.tool_call_id, "tool_name": scope.tool_name,
        "argument_digest": scope.argument_digest,
        "input_policy": {"level": scope.input_policy.level, "source": scope.input_policy.source},
    }


def sign_tool_source(scope: ToolExecutionScope, envelope: ToolResultEnvelope, *,
                     context: dict[str, str], challenge: str) -> dict:
    """Sign only a locally sealed host classification after authorization rechecks."""
    return _sign_tool_source(scope, envelope, context=context, challenge=challenge,
                             protocol=PROTOCOL, validate_context=_context)


def sign_workspace_source(scope: ToolExecutionScope, envelope: ToolResultEnvelope, *,
                          context: dict[str, str], challenge: str) -> dict:
    """Ordinary work has its own context; it never invents creator revisions."""
    return _sign_tool_source(scope, envelope, context=context, challenge=challenge,
                             protocol=WORKSPACE_PROTOCOL, validate_context=_workspace_context)


def _sign_tool_source(scope, envelope, *, context, challenge, protocol, validate_context):
    try:
        policy, content = validate_tool_result(scope, envelope)
        context = validate_context(context)
        if (type(challenge) is not str or not _HEX.fullmatch(challenge)
                or context["developer_run_id"] != scope.parent_request_id):
            raise DevelopmentSourceAttestationError()
        with _lock:
            issuer = _issuers.get(str(_home()))
            if issuer is None or issuer.pid != os.getpid() or pin_source_authority() != issuer.pin:
                raise DevelopmentSourceAttestationError()
            now = _clock(time.time())
            payload = {
                "protocol": protocol, "key_id": issuer.pin.key_id, "generation": issuer.pin.generation,
                "issued_at": now, "expires_at": now + _TTL, "challenge": challenge,
                "context": context, "binding": _binding(scope),
                "result": {"content": content, "content_digest": envelope.content_digest,
                           "policy": {"level": policy.level, "source": policy.source},
                           "source_scope": envelope.source_scope,
                           "canonical_refs": list(envelope.canonical_refs)},
            }
            signature = issuer.key.sign(_canonical(payload))
            if pin_source_authority() != issuer.pin:
                raise DevelopmentSourceAttestationError()
            return {**payload, "signature": base64.b64encode(signature).decode("ascii")}
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        raise DevelopmentSourceAttestationError() from None


def verify_tool_source(pin: AuthorityPin, scope: ToolExecutionScope, receipt: dict, *,
                       context: dict[str, str], challenge: str) -> ToolResultEnvelope:
    """Verify exact host provenance, then re-seal under the bot's original local scope."""
    return _verify_tool_source(pin, scope, receipt, context=context, challenge=challenge,
                               protocol=PROTOCOL, validate_context=_context)


def verify_workspace_source(pin: AuthorityPin, scope: ToolExecutionScope, receipt: dict, *,
                            context: dict[str, str], challenge: str) -> ToolResultEnvelope:
    return _verify_tool_source(pin, scope, receipt, context=context, challenge=challenge,
                               protocol=WORKSPACE_PROTOCOL, validate_context=_workspace_context)


def _verify_tool_source(pin, scope, receipt, *, context, challenge, protocol, validate_context):
    try:
        if type(pin) is not AuthorityPin or pin_source_authority() != pin:
            raise DevelopmentSourceAttestationError()
        if (type(receipt) is not dict or set(receipt) != {
                "protocol", "key_id", "generation", "issued_at", "expires_at", "challenge",
                "context", "binding", "result", "signature"}
                or receipt["protocol"] != protocol or receipt["key_id"] != pin.key_id
                or receipt["generation"] != pin.generation or receipt["challenge"] != challenge
                or validate_context(receipt["context"]) != validate_context(context)
                or context["developer_run_id"] != scope.parent_request_id
                or type(receipt["signature"]) is not str):
            raise DevelopmentSourceAttestationError()
        payload = {key: value for key, value in receipt.items() if key != "signature"}
        Ed25519PublicKey.from_public_bytes(pin._public_key).verify(
            base64.b64decode(receipt["signature"], validate=True), _canonical(payload),
        )
        now = _clock(time.time())
        issued, expires = _clock(receipt["issued_at"]), _clock(receipt["expires_at"])
        if issued > now or now >= expires or expires - issued != _TTL:
            raise DevelopmentSourceAttestationError()
        expected = _binding(scope)
        binding = receipt["binding"]
        if (type(binding) is not dict or set(binding) != set(expected)
                or any(binding[key] != expected[key] for key in expected if key != "input_policy")):
            raise DevelopmentSourceAttestationError()
        input_policy = binding["input_policy"]
        result = receipt["result"]
        if (type(result) is not dict or set(result) != {
                "content", "content_digest", "policy", "source_scope", "canonical_refs"}
                or type(result["content"]) is not str
                or hashlib.sha256(result["content"].encode("utf-8")).hexdigest() != result["content_digest"]
                or type(result["policy"]) is not dict or set(result["policy"]) != {"level", "source"}
                or type(input_policy) is not dict or set(input_policy) != {"level", "source"}
                or type(result["canonical_refs"]) is not list):
            raise DevelopmentSourceAttestationError()
        policy = DataPolicy(**result["policy"])
        floor = DataPolicy(**input_policy)
        if strictest(scope.input_policy, floor, policy).level != policy.level:
            raise DevelopmentSourceAttestationError()
        with _lock:
            started = _challenges.pop(challenge, None)
            if started is None or not 0 <= time.monotonic() - started < _TTL:
                raise DevelopmentSourceAttestationError()
        if pin_source_authority() != pin:
            raise DevelopmentSourceAttestationError()
        return issue_tool_result(scope, result["content"], policy, result["source_scope"],
                                 tuple(result["canonical_refs"]))
    except (OSError, ValueError, TypeError, KeyError, AttributeError, InvalidSignature):
        raise DevelopmentSourceAttestationError() from None
