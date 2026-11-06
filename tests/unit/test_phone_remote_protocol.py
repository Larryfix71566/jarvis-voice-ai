import json
import unittest
import uuid

from jarvis.bot.phone_remote_protocol import PROTOCOL, ProtocolError, encode_response, parse_request, response


def envelope(operation="session.status", payload=None, **extra):
    value = {"kind": PROTOCOL, "protocol_version": 1, "request_id": "r-1",
             "operation": operation, "payload": {} if payload is None else payload}
    value.update(extra)
    return json.dumps(value, separators=(",", ":"))


class ProtocolTests(unittest.TestCase):
    def test_closed_envelopes_and_payloads(self):
        self.assertEqual(parse_request(envelope())["operation"], "session.status")
        for raw in (envelope(extra="bad"), envelope("voice.offer"),
                    envelope("voice.offer", {"sdp": "x", "ticket": "secret"}),
                    envelope("voice.offer", {"sdp": 4}),
                    envelope("unknown")):
            with self.subTest(raw=raw), self.assertRaises(ProtocolError):
                parse_request(raw)

    def test_duplicate_keys_nonfinite_and_untrusted_ids_fail_closed(self):
        cases = [('{"kind":"%s","kind":"%s","protocol_version":1,"request_id":"x","operation":"session.status","payload":{}}' % (PROTOCOL, PROTOCOL)),
                 envelope().replace('"payload":{}', '"payload":{"x":1e999}'),
                 envelope().replace('"request_id":"r-1"', '"request_id":""')]
        for raw in cases:
            with self.assertRaises(ProtocolError) as error:
                parse_request(raw)
            self.assertIsNone(error.exception.request_id)
        for raw in (envelope().replace('"request_id":"r-1"', '"request_id":"\\ud800"'),
                    envelope("voice.offer", {"sdp": "\ud800"})):
            with self.assertRaises(ProtocolError):
                parse_request(raw)

    def test_depth_size_version_and_identifier_bounds(self):
        deep = {"v": None}
        for _ in range(66):
            deep = {"v": deep}
        for raw in (envelope().replace('"payload":{}', '"payload":' + json.dumps(deep)),
                    " " * 1_048_577,
                    envelope().replace('"protocol_version":1', '"protocol_version":2'),
                    envelope().replace('"request_id":"r-1"', '"request_id":"' + 'x' * 129 + '"')):
            with self.assertRaises(ProtocolError):
                parse_request(raw)
        with self.assertRaises(ProtocolError) as error:
            parse_request(envelope().replace('"protocol_version":1', '"protocol_version":2'))
        self.assertEqual((error.exception.status, error.exception.reason), ("incompatible", "unsupported_protocol"))

    def test_response_is_four_fields_and_content_free_errors(self):
        error = response("r", "denied", "not_authorized")
        self.assertEqual(set(error), {"request_id", "status", "reason", "payload"})
        self.assertEqual(error["payload"], {})
        self.assertEqual(json.loads(encode_response(error)), error)

    def test_response_encoder_rejects_invalid_ids_reasons_and_operation_dtos(self):
        with self.assertRaises(ValueError):
            encode_response({"request_id": 42, "status": "invented", "reason": "secret text",
                             "payload": {"secret": "canary"}})
        with self.assertRaises(ValueError):
            encode_response(response("r", "ok", "none", {"readiness": "ready"}))
        good = response("r", "ok", "none", {"readiness": "ready"})
        self.assertEqual(json.loads(encode_response(good, operation="session.status")), good)
        with self.assertRaises(ValueError):
            encode_response(response("r", "ok", "none", {"readiness": "ready", "extra": True}),
                            operation="session.status")
        with self.assertRaises(ValueError):
            encode_response(response("r", "denied", "not_authorized", {"leak": "private"}),
                            operation="session.status")

    def test_results_requests_are_closed_and_cursor_grammar_is_canonical(self):
        cursor = "A" * 43
        self.assertEqual(parse_request(envelope("results.snapshot"))["operation"], "results.snapshot")
        self.assertEqual(parse_request(envelope("results.resume", {"cursor": cursor}))[
            "payload"]["cursor"], cursor)
        for payload in ({}, {"cursor": "=" * 43}, {"cursor": "A" * 42},
                        {"cursor": "A" * 42 + "B"},
                        {"cursor": cursor, "owner_id": "alice"}):
            with self.subTest(payload=payload), self.assertRaises(ProtocolError):
                parse_request(envelope("results.resume", payload))

    def test_results_response_byte_limit_covers_the_complete_envelope(self):
        from unittest.mock import patch
        item_id = str(uuid.uuid4())
        item = {"result_id": item_id, "revision": 1,
            "source": {"kind": "synthetic.workspace_result.v1", "id": item_id, "revision": 1},
            "classification": "ordinary", "title": "t", "body": "b", "received_at_ms": 0}
        result = response("long-request-id", "ok", "none", {
            "generation": str(uuid.uuid4()), "collection_epoch": str(uuid.uuid4()),
            "content_watermark": 1, "cursor": "A" * 43, "items": [item]})
        payload_size = len(json.dumps(result["payload"], separators=(",", ":"),
                                      ensure_ascii=False).encode("utf-8"))
        with patch("jarvis.bot.phone_remote_protocol._MAX_RESULTS_RESPONSE_BYTES", payload_size + 1):
            with self.assertRaises(ValueError):
                encode_response(result, operation="results.snapshot")

    def test_results_response_dtos_reject_wrong_shapes_and_accept_content_free_reset(self):
        result_id = str(uuid.uuid4())
        item = {"result_id": result_id, "revision": 1,
                "source": {"kind": "synthetic.workspace_result.v1", "id": result_id, "revision": 1},
                "classification": "ordinary", "title": "title", "body": "body", "received_at_ms": 0}
        snap = response("r", "ok", "none", {"generation": str(uuid.uuid4()),
            "collection_epoch": str(uuid.uuid4()), "content_watermark": 1,
            "cursor": "A" * 43, "items": [item]})
        self.assertEqual(json.loads(encode_response(snap, operation="results.snapshot")), snap)
        bad = response("r", "ok", "none", dict(snap["payload"], items=[dict(item, body="x" * 8193)]))
        with self.assertRaises(ValueError):
            encode_response(bad, operation="results.snapshot")
        reset = response("r", "ok", "none", {"generation": str(uuid.uuid4()),
            "collection_epoch": str(uuid.uuid4()), "reset_required": True})
        self.assertEqual(json.loads(encode_response(reset, operation="results.resume")), reset)
        malformed_reset = response("r", "ok", "none", dict(reset["payload"], cursor="A" * 43))
        with self.assertRaises(ValueError):
            encode_response(malformed_reset, operation="results.resume")

if __name__ == "__main__":
    unittest.main()

    def test_card_wire_closed_inventory_exact_numbers_and_error_matrix(self):
        from tests.unit.test_phone_remote_result_commands import CardFixture, ACTIONS
        fixture=CardFixture();self.addCleanup(fixture.close);fixture.sync()
        for operation in sorted(ACTIONS):
            target=fixture.target()
            self.assertEqual(parse_request(envelope(operation,target))['payload'],target)
            for key in ('view_revision','result_revision'):
                for bad in (True,1.0,'1',-1,2**63):
                    with self.subTest(operation=operation,key=key,bad=bad),self.assertRaises(ProtocolError):
                        parse_request(envelope(operation,{**target,key:bad}))
            for extra in ({'owner_id':'other'},{'command':'shell'},{'confirmed':True}):
                with self.assertRaises(ProtocolError):parse_request(envelope(operation,{**target,**extra}))
            for status,reasons in {'denied':['malformed_request','not_authorized','request_conflict','request_capacity'],
                    'unavailable':['feature_off','authority_unavailable','owner_busy','operation_unavailable'],
                    'incompatible':['unsupported_protocol']}.items():
                for reason in reasons:
                    value=response('r',status,reason)
                    self.assertEqual(json.loads(encode_response(value,operation=operation)),value)
            with self.assertRaises(ValueError):
                encode_response(response('r','unavailable','voice_not_ready'),operation=operation)
        for mutation in ({'view_revision':True},{'view_revision':1.0},{'cards':fixture.view['cards']*2},
                         {'allowed_operations':['results.pin','results.pin']},{'extra':0}):
            with self.assertRaises(ValueError):
                encode_response(response('r','ok','none',{**fixture.view,**mutation}),operation='results.view')
