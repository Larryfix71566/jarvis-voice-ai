"""Focused tests for the offline phone-admission policy boundary."""
import json
from pathlib import Path
import unittest
import copy

from jarvis.auth import ClientIdentity
from jarvis.bot.phone_admission import PhoneAdmissionCore


FIXTURE = Path(__file__).parents[1] / "fixtures/phone_admission_contract/v1.json"


def constants():
    return json.loads(FIXTURE.read_text())["constants"]


def identity(user_id="owner-a", name="verified-test"):
    return ClientIdentity(name=name, user_id=user_id)


def issue_event():
    return {"type": "issue", "ticket": "t1", "session": "a1", "digest": "offer"}


def fixture_state():
    grants = {
        "A": {"owner": "owner-a", "enabled": True, "scope": ["voice", "read", "action"]},
        "B": {"owner": "owner-b", "enabled": True, "scope": ["voice", "read", "action"]},
    }
    sessions = {
        "a1": {"grant": "A", "generation": 0, "epoch": 1, "process": 1, "enabled": True},
        "a2": {"grant": "A", "generation": 0, "epoch": 1, "process": 1, "enabled": True},
        "b1": {"grant": "B", "generation": 0, "epoch": 1, "process": 1, "enabled": True},
    }
    return grants, sessions, {"p1": "a1", "p2": "a2", "p3": "b1"}


class PhoneAdmissionBoundaryTests(unittest.TestCase):
    def make_core(self, *, feature_enabled=True):
        grants, sessions, peers = fixture_state()
        return PhoneAdmissionCore(constants(), feature_enabled=feature_enabled,
                                  initial_grants=grants, initial_sessions=sessions,
                                  initial_peers=peers)

    def test_admission_requires_verified_identity_and_denies_without_mutation(self):
        core = self.make_core()
        event = issue_event()
        before = copy.deepcopy(core.__dict__)

        self.assertEqual(core.step(event), {"admitted": False, "reason": "identity-required"})
        self.assertEqual(core.__dict__, before)
        self.assertEqual(core.step(event, identity=object()),
                         {"admitted": False, "reason": "identity-invalid"})
        self.assertEqual(core.__dict__, before)
        self.assertEqual(core.step(event, identity=identity(name=" ")),
                         {"admitted": False, "reason": "identity-invalid"})
        self.assertEqual(core.__dict__, before)
        self.assertEqual(core.step(event, identity=identity()), {"admitted": True, "reason": "ok"})

    def test_verified_user_must_match_session_for_ticket_command_output_and_login(self):
        core = self.make_core()
        wrong_user = identity("owner-b")
        correct_user = identity()

        self.assertEqual(core.step(issue_event(), identity=wrong_user),
                         {"admitted": False, "reason": "binding-mismatch"})
        self.assertEqual(core.step(issue_event(), identity=correct_user),
                         {"admitted": True, "reason": "ok"})
        consume = {"type": "consume", "ticket": "t1", "session": "a1", "owner": "owner-a",
                   "grant": "A", "digest": "offer", "peer": "p4"}
        self.assertEqual(core.step(consume, identity=wrong_user),
                         {"admitted": False, "reason": "binding-mismatch"})
        self.assertFalse(core.tickets["t1"]["used"])
        self.assertEqual(core.step(consume, identity=correct_user), {"admitted": True, "reason": "ok"})

        command = {"type": "command", "peer": "p1", "owner": "owner-a",
                   "action": "fixture-action", "protocol": 1}
        self.assertEqual(core.step(command, identity=wrong_user),
                         {"admitted": False, "reason": "binding-mismatch"})
        self.assertEqual(core.commands, [])
        output = {"type": "emit", "peer": "p1", "sink": "text", "classification": "ordinary",
                  "provenance": True, "source_allowed": True}
        self.assertEqual(core.step(output, identity=wrong_user),
                         {"admitted": False, "reason": "binding-mismatch"})
        self.assertEqual(core.emissions, [])
        login = {"type": "login", "grant": "A", "session": "a-new"}
        self.assertEqual(core.step(login, identity=wrong_user),
                         {"admitted": False, "reason": "binding-mismatch"})
        self.assertNotIn("a-new", core.sessions)

    def test_feature_off_refuses_every_admission_event(self):
        core = self.make_core(feature_enabled=False)
        principal = identity()
        events = [
            issue_event(),
            {"type": "consume", "ticket": "unknown", "session": "a1", "owner": "owner-a",
             "grant": "A", "digest": "offer", "peer": "p4"},
            {"type": "command", "peer": "p1", "action": "fixture-action", "protocol": 1},
            {"type": "emit", "peer": "p1", "sink": "text"},
            {"type": "login", "grant": "A", "session": "a-new"},
        ]
        before = copy.deepcopy(core.__dict__)
        for event in events:
            with self.subTest(event=event):
                self.assertEqual(core.step(event, identity=principal),
                                 {"admitted": False, "reason": "feature-off"})
        self.assertEqual(core.__dict__, before)

    def test_feature_switch_must_be_an_explicit_boolean(self):
        with self.assertRaisesRegex(ValueError, "explicit bool"):
            PhoneAdmissionCore(constants(), feature_enabled=1, initial_grants={},
                               initial_sessions={}, initial_peers={})

    def test_initial_peer_state_cannot_reference_an_unknown_session(self):
        grants, sessions, peers = fixture_state()
        peers["p4"] = "missing-session"
        with self.assertRaisesRegex(ValueError, "in-memory authority state"):
            PhoneAdmissionCore(constants(), feature_enabled=True, initial_grants=grants,
                               initial_sessions=sessions, initial_peers=peers)


if __name__ == "__main__":
    unittest.main()
