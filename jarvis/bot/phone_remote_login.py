"""Offline proof-to-session composition for the process-owned authority.

This is a typed in-process API for synthetic/offline integration tests. It is
not a route, enrollment mechanism, Keychain adapter, or production login
service. Challenge state belongs to one child incarnation and is never stored
in SQLite.
"""
from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import secrets
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from cryptography.hazmat.primitives.asymmetric import ec

from jarvis.auth import ClientIdentity
from jarvis.bot.phone_admission_store import (
    LoginChallengeContext,
    PhoneAdmissionStore,
    StoreDenied,
    StoreUnavailable,
)
from jarvis.bot.phone_remote_auth_proof import (
    MAX_SAFE_INTEGER,
    PROTOCOL,
    PURPOSE,
    ProofExpectation,
    verify_auth_proof,
)
from jarvis.bot.phone_remote_authority_channel import (
    NativeProtectedAnchorV3, NativeProtectedAnchorV4,
    run_store_operation,
)


CHALLENGE_TTL_MS = 60_000
MAX_CHALLENGES = 64
MAX_CHALLENGES_PER_DEVICE = 4
MAX_FAILED_PROOFS = 3
MAX_PROOF_BYTES = 4096
SESSION_TTL_MS = 43_200_000
KEY_ALGORITHM = "p256-sha256-sec1-v1"
_UNPADDED_B64URL = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
)


@dataclass(frozen=True, slots=True, repr=False)
class ChallengeResponse:
    protocol: str
    purpose: str
    challenge_id: str
    challenge_nonce: str
    service_id: str
    host_id: str
    enrolled_key_id: str
    authority_generation: int
    expires_at_ms: int

    def __repr__(self) -> str:
        return "ChallengeResponse(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class LoginSession:
    session_id: str
    expires_at_ms: int

    def __repr__(self) -> str:
        return "LoginSession(<redacted>)"


@dataclass(frozen=True, slots=True, eq=False, repr=False)
class _VerifiedLoginAdmission:
    """One-use server-only receipt, issued after the native login release ACK."""
    issuer: object
    child_incarnation: str
    session_id: str
    login_incarnation: str
    expires_at_ms: int
    monotonic_deadline_ms: int
    owner_id: str
    device_id: str
    grant_id: str
    host_id: str
    host_generation: int
    grant_generation: int
    scopes: frozenset[str]

    def __repr__(self):
        return "_VerifiedLoginAdmission(<redacted>)"


@dataclass(frozen=True, slots=True)
class LoginFailure:
    code: str


@dataclass(slots=True, repr=False)
class _Challenge:
    challenge_id: bytes
    nonce: bytes
    device_id: str
    grant_id: str
    owner_id: str
    public_key: bytes
    key_algorithm: str
    grant_generation: int
    scopes: frozenset[str]
    host_id: str
    host_generation: int
    key_fingerprint: str
    expectation: ProofExpectation
    expires_at_ms: int
    monotonic_deadline_ms: int
    state: str = "issued"
    failed_attempts: int = 0

    def __repr__(self) -> str:
        return "_Challenge(<redacted>)"


class LoginClockGate:
    """Deterministic clock whose commit guard serializes deadline checks."""

    def __init__(self, *, wall_ms: int, monotonic_ms: int,
                 verification_barrier: tuple[str, str, str] | None = None) -> None:
        if (type(wall_ms) is not int or type(monotonic_ms) is not int
                or wall_ms < 0 or monotonic_ms < 0):
            raise TypeError("clock values must be nonnegative exact integers")
        self._wall_ms = wall_ms
        self._monotonic_ms = monotonic_ms
        self._lock = threading.RLock()
        if verification_barrier is not None and (
                type(verification_barrier) is not tuple or len(verification_barrier) != 3
                or any(type(path) is not str or not path for path in verification_barrier)):
            raise TypeError("verification barrier must be three nonempty paths")
        self._verification_barrier = verification_barrier
        self._connection_clock = None

    def set_time(self, *, wall_ms: int, monotonic_ms: int) -> None:
        if (type(wall_ms) is not int or type(monotonic_ms) is not int
                or wall_ms < 0 or monotonic_ms < 0):
            raise TypeError("clock values must be nonnegative exact integers")
        if self._connection_clock is not None:
            self._connection_clock.check_login_entry(self)
        with self._lock:
            if self._connection_clock is not None:
                self._connection_clock.reject_login_write(self)
            self._wall_ms = wall_ms
            self._monotonic_ms = monotonic_ms

    def snapshot(self) -> tuple[int, int]:
        if self._connection_clock is not None:
            self._connection_clock.check_login_entry(self)
        with self._lock:
            if self._connection_clock is not None:
                with self._connection_clock.login_guard(self) as image:
                    return image
            return self._wall_ms, self._monotonic_ms

    def after_signature_verification(self) -> None:
        """Optional deterministic file barrier used only by disposable-process tests."""
        barrier = self._verification_barrier
        if barrier is None:
            return
        entered_path, release_path, time_path = (Path(part) for part in barrier)
        entered_path.write_text("verified", encoding="ascii")
        deadline = time.monotonic() + 20
        while not release_path.exists() and time.monotonic() < deadline:
            time.sleep(0.005)
        if not release_path.exists():
            raise StoreUnavailable("login test clock barrier unavailable")
        try:
            raw = time_path.read_bytes()
            if len(raw) > 128:
                raise ValueError("oversized clock value")
            value = json.loads(raw.decode("ascii"))
            if (type(value) is not dict or value.keys() != {"wall_ms", "monotonic_ms"}
                    or type(value["wall_ms"]) is not int or value["wall_ms"] < 0
                    or type(value["monotonic_ms"]) is not int or value["monotonic_ms"] < 0):
                raise ValueError("invalid clock value")
        except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise StoreUnavailable("login test clock value unavailable") from exc
        self.set_time(wall_ms=value["wall_ms"], monotonic_ms=value["monotonic_ms"])

    @contextlib.contextmanager
    def commit_guard(self):
        # Only this concrete gate is accepted; changes cannot interleave the
        # final challenge deadline check and the serialized store transition.
        if self._connection_clock is not None:
            self._connection_clock.check_login_entry(self)
        with self._lock:
            if self._connection_clock is None:
                yield self._wall_ms, self._monotonic_ms
            else:
                # Caller already holds L; paired proof commits additionally
                # hold F. Service-side guards never acquire L.
                with self._connection_clock.login_guard(self) as image:
                    yield image


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _decode_challenge_id(value: object) -> bytes | None:
    if (type(value) is not str or len(value) != 22
            or any(ch not in _UNPADDED_B64URL for ch in value)):
        return None
    try:
        raw = base64.urlsafe_b64decode(value + "==")
    except (ValueError, TypeError):
        return None
    if len(raw) != 16 or _b64url(raw) != value:
        return None
    return raw


def _valid_p256_sec1(value: object) -> bool:
    if type(value) is not bytes or len(value) != 65 or value[0] != 4:
        return False
    try:
        key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), value)
    except (ValueError, TypeError):
        return False
    return type(key.curve) is ec.SECP256R1


class PhoneRemoteLogin:
    """Single-child challenge registry and proof-backed session creator."""

    def __init__(self, store: PhoneAdmissionStore, anchor: NativeProtectedAnchorV3 | NativeProtectedAnchorV4,
                 *, clock: LoginClockGate, service_id: str,
                 operation_runner: Callable[..., object] = run_store_operation) -> None:
        if (type(store) is not PhoneAdmissionStore or type(anchor) not in {NativeProtectedAnchorV3, NativeProtectedAnchorV4}
                or store.anchor is not anchor or type(clock) is not LoginClockGate
                or operation_runner is not run_store_operation
                or type(service_id) is not str or not service_id.strip()):
            raise TypeError("unsupported offline login dependencies")
        self._store = store
        self._anchor = anchor
        self._clock = clock
        self._service_id = service_id
        self._operation_runner = operation_runner
        self._records: dict[bytes, _Challenge] = {}
        self._admissions: set[_VerifiedLoginAdmission] = set()
        self._lock = threading.Lock()
        self._child_incarnation = anchor._child_incarnation

    def issue_challenge(self, *, device_id: object, grant_id: object) -> ChallengeResponse | LoginFailure:
        if (type(device_id) is not str or not device_id.strip() or device_id != device_id.strip()
                or type(grant_id) is not str or not grant_id.strip() or grant_id != grant_id.strip()):
            return LoginFailure("not_authorized")
        wall_ms, mono_ms = self._clock.snapshot()
        self._expire_records(mono_ms)
        challenge_id = secrets.token_bytes(16)
        nonce = secrets.token_bytes(32)
        expires_at_ms = wall_ms + CHALLENGE_TTL_MS
        deadline_ms = mono_ms + CHALLENGE_TTL_MS
        if expires_at_ms > MAX_SAFE_INTEGER:
            return LoginFailure("unavailable")
        with self._lock:
            live = [record for record in self._records.values()
                    if mono_ms < record.monotonic_deadline_ms]
            per_device = sum(1 for record in live if record.device_id == device_id)
            if len(live) >= MAX_CHALLENGES or per_device >= MAX_CHALLENGES_PER_DEVICE:
                return LoginFailure("capacity")
            placeholder = _Challenge(challenge_id, nonce, device_id, grant_id, "", b"", "",
                0, frozenset(), "", 0, "", ProofExpectation(
                    PROTOCOL, PURPOSE, challenge_id, nonce, self._service_id, "host-invalid",
                    "key-invalid", 1, expires_at_ms), expires_at_ms, deadline_ms,
                state="resolving")
            self._records[challenge_id] = placeholder
        try:
            context = self._operation_runner("session.challenge", self._store.login_challenge_context,
                device_id=device_id, grant_id=grant_id, anchor=self._anchor)
        except StoreDenied:
            with self._lock:
                # No challenge was exposed, so there is no replay tombstone
                # to retain for an unknown/revoked selector denial.
                self._records.pop(challenge_id, None)
            return LoginFailure("not_authorized")
        except StoreUnavailable:
            with self._lock:
                placeholder.state = "retired"
            raise
        except BaseException as exc:
            with self._lock:
                placeholder.state = "retired"
            raise StoreUnavailable("login challenge unavailable") from exc
        if type(context) is not LoginChallengeContext:
            with self._lock:
                placeholder.state = "retired"
            raise StoreUnavailable("login challenge context malformed")
        if context.key_algorithm != KEY_ALGORITHM or not _valid_p256_sec1(context.public_key):
            with self._lock:
                self._records.pop(challenge_id, None)
            return LoginFailure("not_authorized")
        key_id = "p256-sha256:" + hashlib.sha256(context.public_key).hexdigest()
        expectation = ProofExpectation(
            PROTOCOL, PURPOSE, challenge_id, nonce, self._service_id, context.host_id,
            key_id, context.host_generation, expires_at_ms,
        )
        record = _Challenge(challenge_id, nonce, context.device_id, context.grant_id,
            context.owner_id, context.public_key, context.key_algorithm,
            context.grant_generation, context.scopes, context.host_id,
            context.host_generation, hashlib.sha256(context.public_key).hexdigest(),
            expectation, expires_at_ms, deadline_ms)
        with self._lock:
            # The placeholder reserves capacity throughout the external store read.
            self._records[challenge_id] = record
        return ChallengeResponse(PROTOCOL, PURPOSE, _b64url(challenge_id), _b64url(nonce),
            self._service_id, context.host_id, key_id, context.host_generation, expires_at_ms)

    def complete_login(self, *, challenge_id: object, proof_bytes: object) -> LoginSession | LoginFailure:
        return self._complete_login(challenge_id=challenge_id, proof_bytes=proof_bytes)

    def _complete_for_connection(self, *, challenge_id, proof_bytes):
        return self._complete_login(challenge_id=challenge_id, proof_bytes=proof_bytes,
                                    _connection=True)

    def _consume_admission(self, admission):
        with self._lock:
            if (type(admission) is not _VerifiedLoginAdmission
                    or admission.issuer is not self or admission not in self._admissions
                    or admission.child_incarnation != self._child_incarnation):
                return False
            self._admissions.remove(admission)
            return True

    def _retire_admission(self, admission):
        with self._lock:
            self._admissions.discard(admission)

    def _retire_connection_seals(self, retired, *, blocking):
        """Drop local seals without blocking an event-loop close on proof work."""
        if not self._lock.acquire(blocking=blocking):
            return False
        try:
            for admission, challenge_id in retired:
                self._admissions.discard(admission)
                record = self._records.get(_decode_challenge_id(challenge_id))
                if record is not None and record.state == "issued":
                    record.state = "retired"
            return True
        finally:
            self._lock.release()

    def _retire_challenge(self, challenge_id):
        key = _decode_challenge_id(challenge_id)
        with self._lock:
            record = self._records.get(key)
            if record is not None and record.state == "issued":
                record.state = "retired"

    def _complete_login(self, *, challenge_id, proof_bytes, _connection=False):
        challenge_id_bytes = _decode_challenge_id(challenge_id)
        if challenge_id_bytes is None:
            return LoginFailure("challenge_unavailable")
        wall_ms, mono_ms = self._clock.snapshot()
        self._expire_records(mono_ms)
        with self._lock:
            record = self._records.get(challenge_id_bytes)
            if record is None or record.state != "issued":
                return LoginFailure("challenge_unavailable")
            if wall_ms >= record.expires_at_ms or mono_ms >= record.monotonic_deadline_ms:
                record.state = "retired"
                return LoginFailure("challenge_unavailable")
            if type(proof_bytes) is not bytes or not proof_bytes or len(proof_bytes) > MAX_PROOF_BYTES:
                record.failed_attempts += 1
                if record.failed_attempts >= MAX_FAILED_PROOFS:
                    record.state = "retired"
                return LoginFailure("proof_rejected")
            record.state = "verifying"

        verification = verify_auth_proof(proof_bytes,
            enrolled_public_key_sec1=record.public_key,
            expected=record.expectation, now_ms=wall_ms)
        if not verification.valid:
            with self._lock:
                current = self._records.get(challenge_id_bytes)
                if current is record and current.state == "verifying":
                    current.failed_attempts += 1
                    current.state = ("retired" if current.failed_attempts >= MAX_FAILED_PROOFS
                                     else "issued")
            return LoginFailure("proof_rejected")

        self._clock.after_signature_verification()

        session_id = secrets.token_hex(16)
        with self._lock:
            current = self._records.get(challenge_id_bytes)
            if current is not record or current.state != "verifying":
                return LoginFailure("challenge_unavailable")
            current.state = "in_flight"
        try:
            # A concrete clock gate keeps test time changes ordered with the
            # exact store preflight and transaction; no arbitrary callback is
            # executed inside the store/anchor critical section.
            with self._clock.commit_guard() as (commit_wall_ms, commit_mono_ms):
                expires_at_ms = commit_wall_ms + SESSION_TTL_MS
                if expires_at_ms > MAX_SAFE_INTEGER:
                    with self._lock:
                        record.state = "retired"
                    return LoginFailure("unavailable")
                identity = ClientIdentity(name="phone-auth-proof", user_id=record.owner_id)
                try:
                    incarnation = self._operation_runner("session.login", self._store.login_proof,
                        anchor=self._anchor, identity=identity, session_id=session_id,
                        device_id=record.device_id, grant_id=record.grant_id,
                        owner_id=record.owner_id, expected_host_id=record.host_id,
                        expected_host_generation=record.host_generation,
                        expected_grant_generation=record.grant_generation,
                        expected_key_algorithm=record.key_algorithm,
                        expected_key_fingerprint=record.key_fingerprint,
                        challenge_expires_at_ms=record.expires_at_ms,
                        monotonic_deadline_ms=record.monotonic_deadline_ms,
                        now_ms=commit_wall_ms, monotonic_now_ms=commit_mono_ms,
                        expires_at_ms=expires_at_ms)
                except StoreDenied:
                    record.state = "retired"
                    expired = (commit_wall_ms >= record.expires_at_ms
                               or commit_mono_ms >= record.monotonic_deadline_ms)
                    return LoginFailure("challenge_unavailable" if expired else "not_authorized")
                if type(incarnation) is not str or not incarnation:
                    raise StoreUnavailable("login incarnation unavailable")
                with self._lock:
                    record.state = "consumed"
                    if _connection:
                        admission = _VerifiedLoginAdmission(self, self._child_incarnation,
                            session_id, incarnation, expires_at_ms,
                            commit_mono_ms + SESSION_TTL_MS, record.owner_id,
                            record.device_id, record.grant_id, record.host_id,
                            record.host_generation, record.grant_generation, record.scopes)
                        self._admissions.add(admission)
                        return admission
                return LoginSession(session_id, expires_at_ms)
        except StoreUnavailable:
            with self._lock:
                record.state = "retired"
            raise
        except BaseException as exc:
            with self._lock:
                record.state = "retired"
            raise StoreUnavailable("login outcome unavailable") from exc

    def _expire_records(self, monotonic_ms: int) -> None:
        with self._lock:
            expired = [key for key, record in self._records.items()
                       if monotonic_ms >= record.monotonic_deadline_ms]
            for key in expired:
                del self._records[key]

    @property
    def child_incarnation(self) -> str:
        return self._child_incarnation
