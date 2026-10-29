import json
import unittest

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


if __name__ == "__main__":
    unittest.main()
