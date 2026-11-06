"""Adversarial tests for the offline native phone-auth proof verifier."""
from __future__ import annotations

import base64
import json
import struct
import unittest
from dataclasses import dataclass, fields as dataclass_fields, replace

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import (
    decode_dss_signature,
    encode_dss_signature,
)

import jarvis.bot.phone_remote_auth_proof as auth_proof
from jarvis.bot.phone_remote_auth_proof import (
    MAX_PROOF_BYTES,
    P256_ORDER,
    PURPOSE,
    PROTOCOL,
    ProofExpectation,
    verify_auth_proof,
)


NOW_MS = 1_800_000_000_000
EXPIRY_MS = NOW_MS + 60_000
_UNSET = object()


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


@dataclass(frozen=True)
class _TestFields:
    protocol: str
    purpose: str
    challenge_id: bytes
    challenge_nonce: bytes
    service_id: str
    host_id: str
    enrolled_key_id: str
    authority_generation: int
    expires_at_ms: int


def _fields() -> _TestFields:
    return _TestFields(
        protocol=PROTOCOL,
        purpose=PURPOSE,
        challenge_id=bytes.fromhex("00112233445566778899aabbccddeeff"),
        challenge_nonce=bytes(range(32)),
        service_id="svc.test",
        host_id="host-A",
        enrolled_key_id="key-1",
        authority_generation=7,
        expires_at_ms=EXPIRY_MS,
    )


def _expectation(fields: _TestFields) -> ProofExpectation:
    return ProofExpectation(
        protocol=fields.protocol,
        purpose=fields.purpose,
        challenge_id=fields.challenge_id,
        challenge_nonce=fields.challenge_nonce,
        service_id=fields.service_id,
        host_id=fields.host_id,
        enrolled_key_id=fields.enrolled_key_id,
        authority_generation=fields.authority_generation,
        expires_at_ms=fields.expires_at_ms,
    )


def _wire(fields: _TestFields, signature: bytes) -> bytes:
    value = {
        "protocol": fields.protocol,
        "purpose": fields.purpose,
        "challenge_id": _b64(fields.challenge_id),
        "challenge_nonce": _b64(fields.challenge_nonce),
        "service_id": fields.service_id,
        "host_id": fields.host_id,
        "enrolled_key_id": fields.enrolled_key_id,
        "authority_generation": fields.authority_generation,
        "expires_at_ms": fields.expires_at_ms,
        "signature": _b64(signature),
    }
    return json.dumps(value, separators=(",", ":")).encode("utf-8")


def _transcript_oracle(fields: _TestFields) -> bytes:
    """Independent test-side implementation of the specified wire transcript."""
    domain = bytes.fromhex("4d6f7274696d657250686f6e654175746850726f6f6600763100")
    values = (
        fields.protocol.encode("ascii"),
        fields.purpose.encode("ascii"),
        fields.challenge_id,
        fields.challenge_nonce,
        fields.service_id.encode("ascii"),
        fields.host_id.encode("ascii"),
        fields.enrolled_key_id.encode("ascii"),
    )
    return (
        domain
        + b"".join(struct.pack(">H", len(value)) + value for value in values)
        + struct.pack(">Q", fields.authority_generation)
        + struct.pack(">Q", fields.expires_at_ms)
    )


def _signed(fields: _TestFields, private_key: ec.EllipticCurvePrivateKey) -> bytes:
    signature = private_key.sign(
        _transcript_oracle(fields), ec.ECDSA(hashes.SHA256())
    )
    return _wire(fields, signature)


def _public_sec1(private_key: ec.EllipticCurvePrivateKey) -> bytes:
    return private_key.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )


class PhoneRemoteAuthProofTests(unittest.TestCase):
    def setUp(self) -> None:
        self.key_a = ec.generate_private_key(ec.SECP256R1())
        self.key_b = ec.generate_private_key(ec.SECP256R1())
        self.fields = _fields()
        self.expected = _expectation(self.fields)
        self.signature = self.key_a.sign(
            _transcript_oracle(self.fields), ec.ECDSA(hashes.SHA256())
        )
        self.proof = _wire(self.fields, self.signature)

    def _verify(
        self,
        proof: bytes | object = _UNSET,
        *,
        key: bytes | object = _UNSET,
        expected: object = _UNSET,
        now: object = NOW_MS,
    ):
        return verify_auth_proof(
            self.proof if proof is _UNSET else proof,
            enrolled_public_key_sec1=(
                _public_sec1(self.key_a) if key is _UNSET else key
            ),
            expected=self.expected if expected is _UNSET else expected,
            now_ms=now,
        )

    def test_valid_signature_verifies_with_server_selected_key(self) -> None:
        self.assertEqual(self._verify().code, "ok")
        self.assertTrue(self._verify().valid)

    def test_transcript_matches_independent_literal_oracle(self) -> None:
        fields = _TestFields(
            protocol=PROTOCOL,
            purpose=PURPOSE,
            challenge_id=bytes.fromhex("00112233445566778899aabbccddeeff"),
            challenge_nonce=bytes(range(32)),
            service_id="svc.test",
            host_id="host-A",
            enrolled_key_id="key-1",
            authority_generation=7,
            expires_at_ms=1_800_000_000_123,
        )
        expected_hex = (
            "4d6f7274696d657250686f6e654175746850726f6f6600763100"
            "001c6d6f7274696d65722e70686f6e652d617574682d70726f6f662e7631"
            "001470686f6e652e73657373696f6e2e637265617465"
            "001000112233445566778899aabbccddeeff"
            "0020000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f"
            "00087376632e74657374"
            "0006686f73742d41"
            "00056b65792d31"
            "0000000000000007"
            "000001a3185c507b"
        )
        transcript = _transcript_oracle(fields)
        self.assertEqual(len(transcript), 171)
        self.assertEqual(transcript.hex(), expected_hex)
        signature = self.key_a.sign(transcript, ec.ECDSA(hashes.SHA256()))
        self.assertEqual(
            self._verify(_wire(fields, signature), expected=_expectation(fields)).code,
            "ok",
        )

    def test_json_whitespace_and_member_order_are_not_signed(self) -> None:
        fields_obj = {
            "protocol": self.fields.protocol,
            "purpose": self.fields.purpose,
            "challenge_id": _b64(self.fields.challenge_id),
            "challenge_nonce": _b64(self.fields.challenge_nonce),
            "service_id": self.fields.service_id,
            "host_id": self.fields.host_id,
            "enrolled_key_id": self.fields.enrolled_key_id,
            "authority_generation": self.fields.authority_generation,
            "expires_at_ms": self.fields.expires_at_ms,
            "signature": _b64(self.signature),
        }
        reordered = json.dumps(fields_obj, indent=2, sort_keys=True).encode("utf-8")
        self.assertEqual(self._verify(reordered).code, "ok")

    def test_proof_signed_by_key_b_fails_with_trusted_key_a_even_when_ids_match(self) -> None:
        proof_b = _signed(self.fields, self.key_b)
        self.assertEqual(self._verify(proof_b, key=_public_sec1(self.key_a)).code,
                         "invalid_signature")
        self.assertEqual(self._verify(proof_b, key=_public_sec1(self.key_b)).code,
                         "ok")

    def test_context_only_mutation_is_a_context_mismatch(self) -> None:
        mutations = {
            "challenge_id": bytes.fromhex("10112233445566778899aabbccddeeff"),
            "challenge_nonce": bytes([1]) + bytes(range(1, 32)),
            "service_id": "svc.other",
            "host_id": "host-B",
            "enrolled_key_id": "key-2",
            "authority_generation": self.fields.authority_generation + 1,
            "expires_at_ms": self.fields.expires_at_ms + 1,
        }
        for name, value in mutations.items():
            with self.subTest(field=name):
                changed = replace(self.fields, **{name: value})
                self.assertEqual(
                    self._verify(_wire(changed, self.signature)).code,
                    "context_mismatch",
                )

    def test_context_and_proof_mutation_with_old_signature_fails_crypto(self) -> None:
        mutations = {
            "challenge_id": bytes.fromhex("10112233445566778899aabbccddeeff"),
            "challenge_nonce": bytes([1]) + bytes(range(1, 32)),
            "service_id": "svc.other",
            "host_id": "host-B",
            "enrolled_key_id": "key-2",
            "authority_generation": self.fields.authority_generation + 1,
            "expires_at_ms": self.fields.expires_at_ms + 1,
        }
        for name, value in mutations.items():
            with self.subTest(field=name):
                changed_fields = replace(self.fields, **{name: value})
                changed_expectation = replace(self.expected, **{name: value})
                self.assertEqual(
                    self._verify(
                        _wire(changed_fields, self.signature),
                        expected=changed_expectation,
                    ).code,
                    "invalid_signature",
                )

    def test_fixed_protocol_and_purpose_are_pinned(self) -> None:
        for key, value in (
            ("protocol", "mortimer.phone-auth-proof.v2"),
            ("purpose", "phone.session.other"),
        ):
            obj = json.loads(self.proof)
            obj[key] = value
            with self.subTest(field=key):
                self.assertEqual(self._verify(json.dumps(obj).encode()).code,
                                 "malformed")

    def test_signature_field_tampering_fails(self) -> None:
        r, s = decode_dss_signature(self.signature)
        tampered = encode_dss_signature(r, s + 1 if s + 1 < P256_ORDER else s - 1)
        self.assertEqual(self._verify(_wire(self.fields, tampered)).code,
                         "invalid_signature")

    def test_valid_high_s_and_low_s_signatures_are_both_accepted(self) -> None:
        r, s = decode_dss_signature(self.signature)
        low_s = min(s, P256_ORDER - s)
        high_s = P256_ORDER - low_s
        low = encode_dss_signature(r, low_s)
        high = encode_dss_signature(r, high_s)
        self.assertEqual(self._verify(_wire(self.fields, low)).code, "ok")
        self.assertEqual(self._verify(_wire(self.fields, high)).code, "ok")

    def test_expiration_boundary_is_exclusive(self) -> None:
        self.assertEqual(self._verify(now=EXPIRY_MS - 1).code, "ok")
        self.assertEqual(self._verify(now=EXPIRY_MS).code, "expired")

    def test_invalid_caller_time_fails_closed_without_exception(self) -> None:
        for value in (True, False, -1, 1.0, float("nan"), float("inf"),
                      (1 << 53)):
            with self.subTest(now=value):
                self.assertEqual(self._verify(now=value).code, "invalid_expectation")

    def test_invalid_expected_context_fails_closed_without_exception(self) -> None:
        for expectation in (
            object(),
            object.__new__(ProofExpectation),
            replace(self.expected, challenge_id=bytearray(self.expected.challenge_id)),
            replace(self.expected, challenge_nonce=b"short"),
            replace(self.expected, service_id=""),
            replace(self.expected, host_id="host/invalid"),
            replace(self.expected, enrolled_key_id="key\u00e9"),
            replace(self.expected, authority_generation=True),
            replace(self.expected, authority_generation=0),
            replace(self.expected, expires_at_ms=True),
            replace(self.expected, expires_at_ms=(1 << 53)),
        ):
            with self.subTest(expectation=expectation):
                self.assertEqual(self._verify(expected=expectation).code,
                                 "invalid_expectation")

    def test_duplicate_keys_including_escaped_equivalent_names_are_rejected(self) -> None:
        obj = json.loads(self.proof)
        ordered = list(obj.items())
        members = [json.dumps(key) + ":" + json.dumps(value) for key, value in ordered]
        exact_duplicate = ("{" + ",".join(members + [members[0]]) + "}").encode()
        escaped_duplicate = (
            b'{"protocol":"' + PROTOCOL.encode() + b'","purpose":"' +
            PURPOSE.encode() + b'","pur\\u0070ose":"' + PURPOSE.encode() +
            b'",' + b",".join(
                (json.dumps(key) + ":" + json.dumps(value)).encode()
                for key, value in ordered
                if key not in {"protocol", "purpose"}
            ) + b"}"
        )
        self.assertEqual(self._verify(exact_duplicate).code, "malformed")
        self.assertEqual(self._verify(escaped_duplicate).code, "malformed")

    def test_unknown_missing_nested_and_nonfinite_json_are_rejected(self) -> None:
        obj = json.loads(self.proof)
        unknown = dict(obj, unexpected="x")
        missing = dict(obj)
        del missing["signature"]
        nested = dict(obj, service_id={"value": obj["service_id"]})
        nonfinite = dict(obj, expires_at_ms=float("nan"))
        cases = (
            json.dumps(unknown).encode(),
            json.dumps(missing).encode(),
            json.dumps(nested).encode(),
            json.dumps(nonfinite).encode(),
            b'{"protocol":"mortimer.phone-auth-proof.v1","purpose":"phone.session.create",'
            b'"x":[[[[[0]]]]]}',
        )
        for value in cases:
            with self.subTest(value=value[:100]):
                self.assertEqual(self._verify(value).code, "malformed")

    def test_size_utf8_and_top_level_shape_are_closed(self) -> None:
        self.assertEqual(self._verify(b" " * (MAX_PROOF_BYTES + 1)).code,
                         "malformed")
        self.assertEqual(self._verify(b"\xff").code, "malformed")
        self.assertEqual(self._verify(b"[]").code, "malformed")
        self.assertEqual(self._verify(None).code, "malformed")
        self.assertEqual(self._verify(bytearray(self.proof)).code, "malformed")

    def test_wrong_scalar_json_types_and_identifier_bounds_are_rejected(self) -> None:
        cases = []
        for name, value in (
            ("authority_generation", True),
            ("authority_generation", 1.0),
            ("authority_generation", 0),
            ("authority_generation", 1 << 63),
            ("expires_at_ms", True),
            ("expires_at_ms", 1.0),
            ("expires_at_ms", 0),
            ("expires_at_ms", 1 << 53),
            ("service_id", ""),
            ("host_id", "host/with/slash"),
            ("enrolled_key_id", "k" * 129),
        ):
            obj = json.loads(self.proof)
            obj[name] = value
            cases.append(json.dumps(obj).encode())
        for value in cases:
            with self.subTest(value=value):
                self.assertEqual(self._verify(value).code, "malformed")

    def test_noncanonical_base64url_and_bad_signature_der_are_rejected(self) -> None:
        obj = json.loads(self.proof)
        for value in (obj["signature"] + "=", "!", "a"):
            changed = dict(obj, signature=value)
            self.assertEqual(self._verify(json.dumps(changed).encode()).code,
                             "malformed")
        malformed_der = (
            b"not-der!!",
            bytes.fromhex("30080202000102020001"),  # nonminimal DER integers
            bytes.fromhex("3006020100020101"),  # canonical DER with r == 0
            b"\x30\x26\x02\x01\x01\x02\x21\x00"
            + P256_ORDER.to_bytes(32, "big"),  # s == P-256 order
        )
        for signature in malformed_der:
            with self.subTest(signature=signature.hex()):
                self.assertEqual(self._verify(_wire(self.fields, signature)).code,
                                 "invalid_signature")

    def test_wrong_public_key_shapes_and_curves_are_rejected(self) -> None:
        p384 = ec.generate_private_key(ec.SECP384R1())
        p384_bytes = p384.public_key().public_bytes(
            serialization.Encoding.X962,
            serialization.PublicFormat.UncompressedPoint,
        )
        for key in (
            b"short",
            bytearray(_public_sec1(self.key_a)),
            b"\x04" + b"\x00" * 64,
            p384_bytes,
        ):
            with self.subTest(key_length=len(key)):
                self.assertEqual(self._verify(key=key).code, "unsupported_key")

    def test_result_contains_no_authority_or_sensitive_fields(self) -> None:
        changed = replace(self.fields, service_id="svc.other")
        invalid_signature = self._verify(_wire(changed, self.signature))
        changed_expectation = replace(self.expected, service_id="svc.other")
        context_rebound = self._verify(
            _wire(changed, self.signature), expected=changed_expectation
        )
        outcomes = (
            self._verify(),
            self._verify(b"not-json"),
            self._verify(_wire(changed, self.signature)),
            self._verify(now=EXPIRY_MS),
            invalid_signature,
            context_rebound,
            self._verify(key=b"bad-key"),
            self._verify(expected=object.__new__(ProofExpectation)),
        )
        sensitive_values = (
            _b64(self.fields.challenge_id),
            _b64(self.fields.challenge_nonce),
            _b64(self.signature),
            self.fields.service_id,
            self.fields.host_id,
            self.fields.enrolled_key_id,
        )
        for result in outcomes:
            with self.subTest(code=result.code):
                self.assertEqual(
                    {field.name for field in dataclass_fields(result)},
                    {"valid", "code"},
                )
                rendered = repr(result)
                for sensitive in sensitive_values:
                    self.assertNotIn(sensitive, rendered)
        self.assertEqual(repr(self.expected), "ProofExpectation(<redacted>)")

    def test_parsed_proof_and_transcript_helpers_are_not_public_api(self) -> None:
        for name in ("PhoneAuthProof", "ProofDecodeResult", "decode_auth_proof",
                     "AuthProofFields", "canonical_transcript"):
            with self.subTest(name=name):
                self.assertFalse(hasattr(auth_proof, name))


if __name__ == "__main__":
    unittest.main()
