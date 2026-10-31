"""Offline tests for v3 login proof framing and fake clock controls."""
from __future__ import annotations

import base64
import json
import tempfile
import threading
import unittest
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from jarvis.bot.phone_remote_auth_proof import PROTOCOL, PURPOSE, ProofExpectation, verify_auth_proof
from jarvis.bot.phone_remote_login import (
    CHALLENGE_TTL_MS,
    KEY_ALGORITHM,
    LoginClockGate,
    _decode_challenge_id,
    _valid_p256_sec1,
)


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _transcript(fields: dict[str, object]) -> bytes:
    domain = bytes.fromhex("4d6f7274696d657250686f6e654175746850726f6f6600763100")
    values = (
        str(fields["protocol"]).encode("ascii"),
        str(fields["purpose"]).encode("ascii"),
        base64.urlsafe_b64decode(str(fields["challenge_id"]) + "=="),
        base64.urlsafe_b64decode(str(fields["challenge_nonce"]) + "=="),
        str(fields["service_id"]).encode("ascii"),
        str(fields["host_id"]).encode("ascii"),
        str(fields["enrolled_key_id"]).encode("ascii"),
    )
    return (domain + b"".join(len(value).to_bytes(2, "big") + value for value in values)
            + int(fields["authority_generation"]).to_bytes(8, "big")
            + int(fields["expires_at_ms"]).to_bytes(8, "big"))


def sign_challenge_proof(challenge, private_key: ec.EllipticCurvePrivateKey) -> bytes:
    """Create a synthetic proof for an actual disposable-process challenge."""
    fields: dict[str, object] = {
        "protocol": challenge.protocol,
        "purpose": challenge.purpose,
        "challenge_id": challenge.challenge_id,
        "challenge_nonce": challenge.challenge_nonce,
        "service_id": challenge.service_id,
        "host_id": challenge.host_id,
        "enrolled_key_id": challenge.enrolled_key_id,
        "authority_generation": challenge.authority_generation,
        "expires_at_ms": challenge.expires_at_ms,
    }
    fields["signature"] = _b64(private_key.sign(_transcript(fields), ec.ECDSA(hashes.SHA256())))
    return json.dumps(fields, separators=(",", ":")).encode("ascii")


class PhoneRemoteLoginTests(unittest.TestCase):
    def test_challenge_ids_require_canonical_unpadded_base64url_16_bytes(self):
        value = _b64(bytes(range(16)))
        self.assertEqual(_decode_challenge_id(value), bytes(range(16)))
        for invalid in (None, "", value + "=", value[:-1], "a" * 22, "A" * 21 + "/"):
            with self.subTest(invalid=invalid):
                self.assertIsNone(_decode_challenge_id(invalid))

    def test_only_canonical_uncompressed_p256_points_are_accepted(self):
        private = ec.generate_private_key(ec.SECP256R1())
        point = private.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        self.assertEqual(KEY_ALGORITHM, "p256-sha256-sec1-v1")
        self.assertTrue(_valid_p256_sec1(point))
        for invalid in (bytearray(point), point[:64], b"\x02" + point[1:], b"\x04" + bytes(64)):
            with self.subTest(length=len(invalid)):
                self.assertFalse(_valid_p256_sec1(invalid))

    def test_login_clock_barrier_serializes_expiry_change_after_signature_verification(self):
        initial_wall, initial_mono = 1_800_000_000_000, 1_000
        with tempfile.TemporaryDirectory(prefix="phone-login-clock-") as temp:
            root = Path(temp)
            entered, release, time_file = root / "entered", root / "release", root / "time.json"
            gate = LoginClockGate(wall_ms=initial_wall, monotonic_ms=initial_mono,
                                  verification_barrier=(str(entered), str(release), str(time_file)))
            worker = threading.Thread(target=gate.after_signature_verification)
            worker.start()
            for _ in range(500):
                if entered.exists():
                    break
                threading.Event().wait(0.002)
            self.assertTrue(entered.exists())
            time_file.write_text(json.dumps({"wall_ms": initial_wall + CHALLENGE_TTL_MS + 1,
                                             "monotonic_ms": initial_mono + CHALLENGE_TTL_MS + 1}),
                                 encoding="ascii")
            release.touch()
            worker.join(2)
            self.assertFalse(worker.is_alive())
            with gate.commit_guard() as (wall_ms, monotonic_ms):
                self.assertEqual(wall_ms, initial_wall + CHALLENGE_TTL_MS + 1)
                self.assertEqual(monotonic_ms, initial_mono + CHALLENGE_TTL_MS + 1)

    def test_clock_rejects_non_exact_or_negative_values(self):
        for bad in (True, 1.0, -1):
            with self.subTest(bad=bad), self.assertRaises(TypeError):
                LoginClockGate(wall_ms=bad, monotonic_ms=1)
        gate = LoginClockGate(wall_ms=1, monotonic_ms=1)
        with self.assertRaises(TypeError):
            gate.set_time(wall_ms=1, monotonic_ms=True)

    def test_proof_builder_matches_existing_verifier_contract(self):
        private = ec.generate_private_key(ec.SECP256R1())

        class Challenge:
            protocol = PROTOCOL
            purpose = PURPOSE
            challenge_id = _b64(bytes(range(16)))
            challenge_nonce = _b64(bytes(range(32)))
            service_id = "svc.test"
            host_id = "host-test"
            enrolled_key_id = "p256-sha256:" + __import__("hashlib").sha256(
                private.public_key().public_bytes(serialization.Encoding.X962,
                    serialization.PublicFormat.UncompressedPoint)).hexdigest()
            authority_generation = 7
            expires_at_ms = 1_800_000_060_000

        proof = sign_challenge_proof(Challenge(), private)
        expectation = ProofExpectation(PROTOCOL, PURPOSE, bytes(range(16)), bytes(range(32)),
            "svc.test", "host-test", Challenge.enrolled_key_id, 7, Challenge.expires_at_ms)
        point = private.public_key().public_bytes(serialization.Encoding.X962,
            serialization.PublicFormat.UncompressedPoint)
        checked = verify_auth_proof(proof, enrolled_public_key_sec1=point,
                                    expected=expectation, now_ms=1_800_000_000_000)
        self.assertTrue(checked.valid, checked.code)


if __name__ == "__main__":
    unittest.main()


class SealedConnectionAdmissionTests(unittest.TestCase):
    def test_seal_requires_exact_issuer_child_identity_and_one_consumption(self):
        from dataclasses import replace
        from jarvis.bot.phone_remote_login import PhoneRemoteLogin, _VerifiedLoginAdmission, LoginSession
        def issuer(child):
            value=object.__new__(PhoneRemoteLogin)
            value._lock=threading.RLock();value._admissions=set();value._child_incarnation=child
            return value
        a,b=issuer('child-a'),issuer('child-b')
        admission=_VerifiedLoginAdmission(a,'child-a','session','opaque-returned-incarnation',100,200,
            'owner','device','grant','host',2,3,frozenset({'read'}))
        a._admissions.add(admission)
        for invalid in (None,LoginSession('session',100),replace(admission),replace(admission,issuer=b),replace(admission,child_incarnation='child-b')):
            with self.subTest(type=type(invalid).__name__):self.assertFalse(a._consume_admission(invalid))
        self.assertFalse(b._consume_admission(admission))
        self.assertNotIn('opaque-returned-incarnation',repr(admission))
        self.assertTrue(a._consume_admission(admission));self.assertFalse(a._consume_admission(admission))
        a._admissions.add(admission);a._retire_admission(admission)
        self.assertFalse(a._consume_admission(admission))


class ConnectionSealRetirementTests(unittest.TestCase):
    def test_idle_close_does_not_reacquire_nonreentrant_login_lock(self):
        from types import SimpleNamespace
        from jarvis.bot.phone_remote_login import PhoneRemoteLogin
        login=object.__new__(PhoneRemoteLogin)
        login._lock=threading.Lock();login._admissions={None}
        key=bytes(16);record=SimpleNamespace(state='issued');login._records={key:record}
        with login._lock:
            self.assertFalse(login._retire_connection_seals([(None,_b64(key))],blocking=False))
        self.assertTrue(login._retire_connection_seals([(None,_b64(key))],blocking=False))
        self.assertEqual(record.state,'retired');self.assertEqual(login._admissions,set())
