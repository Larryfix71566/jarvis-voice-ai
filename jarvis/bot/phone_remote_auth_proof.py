"""Pure verifier for the bounded Mortimer native phone-auth proof format.

This module verifies proof of possession of a server-selected enrolled key.
It does not issue or consume challenges, identify owners/devices, enroll keys,
mint sessions, or provide a route. Callers must recheck and consume the
challenge in the same serialized authority transition that creates a session.
"""
from __future__ import annotations

import base64
import binascii
import json
import re
import struct
from dataclasses import dataclass
from typing import Final

from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import (
    decode_dss_signature,
    encode_dss_signature,
)


PROTOCOL: Final = "mortimer.phone-auth-proof.v1"
PURPOSE: Final = "phone.session.create"
MAX_PROOF_BYTES: Final = 4096
MAX_IDENTIFIER_BYTES: Final = 128
MAX_SAFE_INTEGER: Final = (1 << 53) - 1
MAX_AUTHORITY_GENERATION: Final = (1 << 63) - 1
MAX_SIGNATURE_BYTES: Final = 72
MIN_SIGNATURE_BYTES: Final = 8
P256_ORDER: Final = int(
    "FFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551", 16
)
_DOMAIN_SEPARATOR: Final = b"MortimerPhoneAuthProof\x00v1\x00"
_IDENTIFIER_RE: Final = re.compile(r"[A-Za-z0-9._:-]{1,128}\Z", re.ASCII)
_BASE64URL_RE: Final = re.compile(r"[A-Za-z0-9_-]+\Z", re.ASCII)
_PROOF_KEYS: Final = frozenset(
    {
        "protocol",
        "purpose",
        "challenge_id",
        "challenge_nonce",
        "service_id",
        "host_id",
        "enrolled_key_id",
        "authority_generation",
        "expires_at_ms",
        "signature",
    }
)


@dataclass(frozen=True, slots=True, repr=False)
class _AuthProofFields:
    """The exact values covered by the ECDSA transcript."""

    protocol: str
    purpose: str
    challenge_id: bytes
    challenge_nonce: bytes
    service_id: str
    host_id: str
    enrolled_key_id: str
    authority_generation: int
    expires_at_ms: int

    def __repr__(self) -> str:
        return "_AuthProofFields(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class _PhoneAuthProof:
    fields: _AuthProofFields
    signature: bytes

    def __repr__(self) -> str:
        return "_PhoneAuthProof(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class ProofExpectation:
    """Immutable server-derived challenge and authority context."""

    protocol: str
    purpose: str
    challenge_id: bytes
    challenge_nonce: bytes
    service_id: str
    host_id: str
    enrolled_key_id: str
    authority_generation: int
    expires_at_ms: int

    def __repr__(self) -> str:
        return "ProofExpectation(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class _ProofDecodeResult:
    proof: _PhoneAuthProof | None
    code: str

    def __repr__(self) -> str:
        return "_ProofDecodeResult(<redacted>)"


@dataclass(frozen=True, slots=True)
class ProofVerificationResult:
    valid: bool
    code: str


def _reject_constant(_value: str) -> None:
    raise ValueError("nonfinite JSON number")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _is_flat_json_object(raw: bytes) -> bool:
    """Preflight nesting before json.loads; only one object level is allowed."""
    depth = 0
    in_string = False
    escaped = False
    for byte in raw:
        if in_string:
            if escaped:
                escaped = False
            elif byte == 0x5C:  # backslash
                escaped = True
            elif byte == 0x22:  # quote
                in_string = False
            continue
        if byte == 0x22:
            in_string = True
        elif byte in (0x7B, 0x5B):  # { or [
            depth += 1
            if depth > 1:
                return False
        elif byte in (0x7D, 0x5D):  # } or ]
            depth -= 1
            if depth < 0:
                return False
    return depth == 0 and not in_string


def _decode_base64url(value: object, *, expected_size: int | None = None) -> bytes | None:
    if type(value) is not str or not value or _BASE64URL_RE.fullmatch(value) is None:
        return None
    if len(value) % 4 == 1:
        return None
    try:
        decoded = base64.urlsafe_b64decode(value + ("=" * (-len(value) % 4)))
    except (binascii.Error, ValueError):
        return None
    if base64.urlsafe_b64encode(decoded).rstrip(b"=").decode("ascii") != value:
        return None
    if expected_size is not None and len(decoded) != expected_size:
        return None
    return decoded


def _valid_identifier(value: object) -> bool:
    return (
        type(value) is str
        and len(value) <= MAX_IDENTIFIER_BYTES
        and _IDENTIFIER_RE.fullmatch(value) is not None
    )


def _valid_generation(value: object) -> bool:
    return (
        type(value) is int
        and 1 <= value <= MAX_AUTHORITY_GENERATION
    )


def _valid_expiration(value: object) -> bool:
    return type(value) is int and 1 <= value <= MAX_SAFE_INTEGER


def _decode_fields(value: object) -> _AuthProofFields | None:
    if type(value) is not dict or set(value) != _PROOF_KEYS:
        return None
    if value["protocol"] != PROTOCOL or type(value["protocol"]) is not str:
        return None
    if value["purpose"] != PURPOSE or type(value["purpose"]) is not str:
        return None
    challenge_id = _decode_base64url(value["challenge_id"], expected_size=16)
    challenge_nonce = _decode_base64url(value["challenge_nonce"], expected_size=32)
    signature = _decode_base64url(value["signature"])
    if challenge_id is None or challenge_nonce is None or signature is None:
        return None
    if not MIN_SIGNATURE_BYTES <= len(signature) <= MAX_SIGNATURE_BYTES:
        return None
    if not all(
        _valid_identifier(value[name])
        for name in ("service_id", "host_id", "enrolled_key_id")
    ):
        return None
    generation = value["authority_generation"]
    expiration = value["expires_at_ms"]
    if not _valid_generation(generation) or not _valid_expiration(expiration):
        return None
    return _AuthProofFields(
        protocol=value["protocol"],
        purpose=value["purpose"],
        challenge_id=challenge_id,
        challenge_nonce=challenge_nonce,
        service_id=value["service_id"],
        host_id=value["host_id"],
        enrolled_key_id=value["enrolled_key_id"],
        authority_generation=generation,
        expires_at_ms=expiration,
    )


def _decode_auth_proof(raw: object) -> _ProofDecodeResult:
    """Privately decode the proof envelope without exposing parsed fields."""
    if type(raw) is not bytes or not raw or len(raw) > MAX_PROOF_BYTES:
        return _ProofDecodeResult(None, "malformed")
    try:
        text = raw.decode("utf-8", "strict")
        if not _is_flat_json_object(raw):
            return _ProofDecodeResult(None, "malformed")
        value = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
        fields = _decode_fields(value)
        if fields is None:
            return _ProofDecodeResult(None, "malformed")
        signature = _decode_base64url(value["signature"])
        if signature is None:  # guarded by _decode_fields; retain fail-closed shape.
            return _ProofDecodeResult(None, "malformed")
        return _ProofDecodeResult(_PhoneAuthProof(fields, signature), "ok")
    except (UnicodeDecodeError, ValueError, TypeError, RecursionError):
        return _ProofDecodeResult(None, "malformed")


def _valid_expected_context(value: object) -> bool:
    if type(value) is not ProofExpectation:
        return False
    try:
        protocol = object.__getattribute__(value, "protocol")
        purpose = object.__getattribute__(value, "purpose")
        challenge_id = object.__getattribute__(value, "challenge_id")
        challenge_nonce = object.__getattribute__(value, "challenge_nonce")
        service_id = object.__getattribute__(value, "service_id")
        host_id = object.__getattribute__(value, "host_id")
        enrolled_key_id = object.__getattribute__(value, "enrolled_key_id")
        authority_generation = object.__getattribute__(value, "authority_generation")
        expires_at_ms = object.__getattribute__(value, "expires_at_ms")
    except AttributeError:
        return False
    if type(protocol) is not str or protocol != PROTOCOL:
        return False
    if type(purpose) is not str or purpose != PURPOSE:
        return False
    if type(challenge_id) is not bytes or len(challenge_id) != 16:
        return False
    if type(challenge_nonce) is not bytes or len(challenge_nonce) != 32:
        return False
    if not all(_valid_identifier(item) for item in (service_id, host_id, enrolled_key_id)):
        return False
    return _valid_generation(authority_generation) and _valid_expiration(expires_at_ms)


def _valid_now(now_ms: object) -> bool:
    return type(now_ms) is int and 0 <= now_ms <= MAX_SAFE_INTEGER


def _matches_expectation(fields: _AuthProofFields, expected: ProofExpectation) -> bool:
    return (
        fields.protocol == expected.protocol
        and fields.purpose == expected.purpose
        and fields.challenge_id == expected.challenge_id
        and fields.challenge_nonce == expected.challenge_nonce
        and fields.service_id == expected.service_id
        and fields.host_id == expected.host_id
        and fields.enrolled_key_id == expected.enrolled_key_id
        and fields.authority_generation == expected.authority_generation
        and fields.expires_at_ms == expected.expires_at_ms
    )


def _length_prefixed(field: bytes) -> bytes:
    if len(field) > 0xFFFF:
        raise ValueError("transcript field too long")
    return struct.pack(">H", len(field)) + field


def _canonical_transcript(fields: _AuthProofFields) -> bytes:
    """Return the private fixed-order signed bytes for validated proof fields."""
    if type(fields) is not _AuthProofFields:
        raise TypeError("fields must be _AuthProofFields")
    if (
        type(fields.protocol) is not str
        or fields.protocol != PROTOCOL
        or type(fields.purpose) is not str
        or fields.purpose != PURPOSE
        or type(fields.challenge_id) is not bytes
        or len(fields.challenge_id) != 16
        or type(fields.challenge_nonce) is not bytes
        or len(fields.challenge_nonce) != 32
        or not _valid_identifier(fields.service_id)
        or not _valid_identifier(fields.host_id)
        or not _valid_identifier(fields.enrolled_key_id)
        or not _valid_generation(fields.authority_generation)
        or not _valid_expiration(fields.expires_at_ms)
    ):
        raise ValueError("invalid proof fields")
    strings = (
        fields.protocol.encode("ascii"),
        fields.purpose.encode("ascii"),
        fields.challenge_id,
        fields.challenge_nonce,
        fields.service_id.encode("ascii"),
        fields.host_id.encode("ascii"),
        fields.enrolled_key_id.encode("ascii"),
    )
    return (
        _DOMAIN_SEPARATOR
        + b"".join(_length_prefixed(value) for value in strings)
        + struct.pack(">Q", fields.authority_generation)
        + struct.pack(">Q", fields.expires_at_ms)
    )


def verify_auth_proof(
    proof_bytes: object,
    *,
    enrolled_public_key_sec1: object,
    expected: object,
    now_ms: object,
) -> ProofVerificationResult:
    """Verify a proof against server-selected key, challenge and authority data.

    Evaluation order is fixed: expectation/time validation, proof decoding,
    exact context matching, expiration, public-key validation, DER validation,
    then ECDSA. This function never consumes a challenge or creates a session.
    """
    if not _valid_expected_context(expected) or not _valid_now(now_ms):
        return ProofVerificationResult(False, "invalid_expectation")

    decoded = _decode_auth_proof(proof_bytes)
    if decoded.proof is None:
        return ProofVerificationResult(False, "malformed")
    proof = decoded.proof
    if not _matches_expectation(proof.fields, expected):
        return ProofVerificationResult(False, "context_mismatch")
    if now_ms >= proof.fields.expires_at_ms:
        return ProofVerificationResult(False, "expired")

    if (
        type(enrolled_public_key_sec1) is not bytes
        or len(enrolled_public_key_sec1) != 65
        or enrolled_public_key_sec1[:1] != b"\x04"
    ):
        return ProofVerificationResult(False, "unsupported_key")
    try:
        public_key = ec.EllipticCurvePublicKey.from_encoded_point(
            ec.SECP256R1(), enrolled_public_key_sec1
        )
    except (ValueError, UnsupportedAlgorithm):
        return ProofVerificationResult(False, "unsupported_key")

    try:
        r, s = decode_dss_signature(proof.signature)
        if (
            encode_dss_signature(r, s) != proof.signature
            or not (1 <= r < P256_ORDER)
            or not (1 <= s < P256_ORDER)
        ):
            return ProofVerificationResult(False, "invalid_signature")
    except ValueError:
        return ProofVerificationResult(False, "invalid_signature")

    try:
        public_key.verify(
            proof.signature,
            _canonical_transcript(proof.fields),
            ec.ECDSA(hashes.SHA256()),
        )
    except InvalidSignature:
        return ProofVerificationResult(False, "invalid_signature")
    return ProofVerificationResult(True, "ok")
