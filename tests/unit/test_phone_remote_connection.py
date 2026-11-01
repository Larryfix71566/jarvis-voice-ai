"""Offline connection contract: codec, clock, lease and owned ASGI fixtures."""
import asyncio
import base64
import json
import threading
import unittest
from types import SimpleNamespace

from jarvis.bot.phone_remote_connection import (
    CONNECTION_PROTOCOL, ConnectionClock, ConnectionRegistry, ConnectionFailure,
    ConnectionLease, ConnectionReply, HandshakeError, _CONNECTION_CONSTRUCTION,
    decode_proof, handshake_response, parse_handshake, create_offline_connection_host,
)
from jarvis.bot.phone_admission_store import StoreUnavailable
from tests.unit.test_phone_remote_login import sign_challenge_proof


def handshake(operation, payload, rid="challenge"):
    return json.dumps(dict(protocol=CONNECTION_PROTOCOL, request_id=rid,
                           operation=operation, payload=payload))


def wire(operation="session.status", payload=None, rid="status"):
    return json.dumps(dict(kind="mortimer.phone-remote.v1", protocol_version=1,
        request_id=rid, operation=operation, payload={} if payload is None else payload))


class InMemoryProofClient:
    """A single real ASGI invocation; no trusted context injection."""
    def __init__(self, host):
        from jarvis.bot.phone_remote_asgi import create_phone_remote_connection_asgi
        self.app = create_phone_remote_connection_asgi(host, enabled=True)
        self.incoming, self.outgoing = asyncio.Queue(), asyncio.Queue()
        self.task = None
        self.transcript = []
        self.send_failure_request = None
        self.send_hook = None

    async def start(self):
        async def send(event):
            if self.send_hook is not None:await self.send_hook(event)
            if event.get('type')=='websocket.send' and self.send_failure_request is not None and json.loads(event['text']).get('request_id')==self.send_failure_request:
                raise OSError('synthetic send loss')
            self.transcript.append(event)
            await self.outgoing.put(event)
        self.task = asyncio.create_task(self.app(
            {"type": "websocket", "path": "/ws/phone-remote",
             "state": {"owner_id": "untrusted", "trusted_context": "forged"},
             "headers": [(b"authorization", b"Bearer fabricated")]},
            self.incoming.get, send))
        await self.incoming.put({"type": "websocket.connect"})
        event = await asyncio.wait_for(self.outgoing.get(), 5)
        assert event["type"] == "websocket.accept", event

    async def exchange(self, raw):
        await self.incoming.put({"type": "websocket.receive", "text": raw})
        event = await asyncio.wait_for(self.outgoing.get(), 5)
        return json.loads(event["text"]) if event["type"] == "websocket.send" else event

    async def challenge(self, device="d-channel", grant="g-channel"):
        result = await self.exchange(handshake("auth.challenge", dict(device_id=device, grant_id=grant)))
        assert result["status"] == "ok", result
        return SimpleNamespace(**result["payload"])

    async def prove(self, challenge, private):
        proof = sign_challenge_proof(challenge, private)
        return await self.exchange(handshake("auth.prove", dict(challenge_id=challenge.challenge_id,
            proof=base64.urlsafe_b64encode(proof).rstrip(b"=").decode()), "prove"))

    async def login(self, private, device="d-channel", grant="g-channel"):
        await self.start()
        result = await self.prove(await self.challenge(device, grant), private)
        assert result["status"] == "ok", result
        assert set(result["payload"]) == {"authenticated", "expires_at_ms"}
        return result

    async def close(self):
        if self.task is None:
            return
        if not self.task.done():
            await self.incoming.put({"type": "websocket.disconnect", "code": 1000})
        await asyncio.wait_for(self.task, 5)


class ConnectionCodecTests(unittest.TestCase):
    def test_strict_handshake_positive_and_closed_envelopes(self):
        raw=handshake("auth.challenge", {"device_id":"d", "grant_id":"g"})
        self.assertEqual(parse_handshake(raw.encode()), parse_handshake(raw))
        value=json.loads(raw)
        variants=[None,b'',b'\xef\xbb\xbf'+raw.encode(),b'\xff',raw+'{}',
            raw.replace('"device_id": "d"','"device_id": "d", "device_id": "d"'),
            json.dumps({**value,'owner_id':'forged'}),json.dumps({**value,'request_id':True}),
            json.dumps({**value,'request_id':'x'*129}),json.dumps({**value,'protocol':'other'}),
            json.dumps({**value,'payload':{'device_id':' d','grant_id':'g'}}),
            json.dumps({**value,'payload':{'device_id':'d','grant_id':'g','session_id':'forged'}}),
            '['*100+']'*100,raw.replace('"d"','NaN'),raw.replace('"d"','Infinity')]
        for invalid in variants:
            with self.subTest(invalid=str(invalid)[:60]):
                with self.assertRaises(HandshakeError):parse_handshake(invalid)

    def test_proof_canonical_bytes_and_limits(self):
        for size in (1,4096):
            raw=b'x'*size;encoded=base64.urlsafe_b64encode(raw).rstrip(b'=').decode()
            self.assertEqual(decode_proof(encoded),raw)
            request=handshake('auth.prove',{'challenge_id':'AAAAAAAAAAAAAAAAAAAAAA','proof':encoded},'p')
            self.assertEqual(parse_handshake(request)['payload']['proof'],encoded)
        for value in ('', 'eA==','eA=', '+A', '/A','__8=', 'A', 'eA\n', 4, True,
                      base64.urlsafe_b64encode(b'x'*4097).rstrip(b'=').decode()):
            with self.subTest(value=str(value)[:30]):
                with self.assertRaises(ValueError):decode_proof(value)

    def test_handshake_output_validation_and_no_failure_echo(self):
        for expiry in (True,1.0,0,2**53):
            with self.subTest(expiry=expiry):
                with self.assertRaises(ValueError):handshake_response('r',payload={'authenticated':True,'expires_at_ms':expiry})
        for reason in ('invalid_request','not_authorized','capacity','authority_unavailable'):
            self.assertEqual(json.loads(handshake_response(None,reason=reason))['payload'],{})
        with self.assertRaises(ValueError):handshake_response('r',payload={'authenticated':True,'expires_at_ms':10,'session_id':'secret'})
        with self.assertRaises(ValueError):handshake_response('r',reason='secret')


class ConnectionClockLeaseTests(unittest.TestCase):
    def fixture(self):
        clock=ConnectionClock(wall_ms=10000,monotonic_ms=100)
        host=SimpleNamespace(_lock=threading.Lock(),_closed=False,_fenced=False,
            _quiescing=False,_proof_enabled=True)
        registry=ConnectionRegistry(host,clock,_CONNECTION_CONSTRUCTION)
        return clock,host,registry

    def test_clock_coherent_under_F_and_never_F_to_L(self):
        clock,_,_=self.fixture()
        started,finished=threading.Event(),threading.Event()
        def update():
            started.set();clock.set_time(wall_ms=1,monotonic_ms=200);finished.set()
        with clock.service._lock:
            t=threading.Thread(target=update);t.start();self.assertTrue(started.wait(1))
            self.assertFalse(finished.wait(.02))
            self.assertEqual(clock.image_locked(),(10000,100))
            with self.assertRaises(StoreUnavailable):clock.set_time(wall_ms=2,monotonic_ms=300)
        t.join(1);self.assertFalse(t.is_alive());self.assertTrue(finished.is_set())
        self.assertEqual(clock.snapshot(),(1,200))
        with self.assertRaises(ValueError):clock.set_time(wall_ms=10,monotonic_ms=199)
        with self.assertRaises(StoreUnavailable):clock.service.set_time(999)
        with self.assertRaises(StoreUnavailable):clock.snapshot()

    def test_timer_epoch_does_not_retire_active_connection(self):
        _,_,r=self.fixture();token=object();lease=r.open(token);epoch,_=r.timer(lease,token)
        with r.lock:r.records[lease].state='active';r.records[lease].epoch=None
        self.assertFalse(r.expire_handshake(lease,token,epoch))
        self.assertFalse(r.records[lease].cancel.is_set())
        other=object();second=r.open(other);e,_=r.timer(second,other)
        self.assertTrue(r.expire_handshake(second,other,e));self.assertNotIn(second,r.records)
        self.assertFalse(r.expire_handshake(lease,token,object()))

    def test_exact_handles_tokens_capacity_and_retiring_slot(self):
        _,_,r=self.fixture();tokens=[object() for _ in range(65)]
        leases=[r.open(t) for t in tokens[:64]]
        self.assertTrue(all(type(l) is ConnectionLease for l in leases))
        self.assertEqual(r.open(tokens[-1]),ConnectionFailure('capacity'))
        r.close(ConnectionLease(),tokens[0]);r.close(leases[0],tokens[1]);self.assertEqual(len(r.records),64)
        with r.lock:r.records[leases[0]].in_flight=1
        r.close(leases[0],tokens[0]);self.assertEqual(len(r.records),64)
        with r.lock:r.records[leases[0]].in_flight=0;r._retire_locked(r.records[leases[0]])
        self.assertIs(type(r.open(tokens[-1])),ConnectionLease)
        self.assertIsNone(r.cancel_event(leases[0],tokens[0]))

    def test_reply_copy_foreign_and_expiry_at_final_egress(self):
        clock,_,r=self.fixture();token=object();lease=r.open(token)
        with r.lock:
            record=r.records[lease];record.state='active';record.epoch=None
            record.expires_at_ms=20000;record.monotonic_deadline_ms=500
        reply=r._seal(record,'checked',True)
        self.assertEqual(r.claim(lease,token,ConnectionReply('checked',True)),ConnectionFailure())
        clock.set_time(wall_ms=1,monotonic_ms=500)
        self.assertEqual(r.claim(lease,token,reply),ConnectionFailure())
        self.assertNotIn(lease,r.records)

    def test_default_disabled_and_truthy_dependency_rejection(self):
        _,host,r=self.fixture();host._proof_enabled=False
        self.assertIs(type(r.open(object())),ConnectionFailure)
        for value in ('true',1,None,object()):
            with self.subTest(value=str(value)):
                with self.assertRaises(TypeError):create_offline_connection_host('unused',enabled=value)


class ConnectionPruningTests(unittest.TestCase):
    fixture = ConnectionClockLeaseTests.fixture
    def test_expired_idle_capacity_is_reclaimed_but_owned_record_waits_for_worker(self):
        clock,host,r=self.fixture()
        leases=[r.open(object()) for _ in range(64)]
        owned=r.records[leases[0]];owned.in_flight=1
        for record in r.records.values():
            record.state='active';record.expires_at_ms=2_000_000_000_000;record.monotonic_deadline_ms=2000
        clock.set_time(wall_ms=1,monotonic_ms=2000)
        self.assertIs(type(r.open(object())),ConnectionLease)
        self.assertEqual(len(r.records),2)
        self.assertEqual(owned.state,'retiring');self.assertTrue(owned.cancel.is_set())
        completion=SimpleNamespace(connection_record=owned)
        r.finish_owned(completion)
        self.assertNotIn(owned.lease,r.records)


class PairedClockReviewTests(unittest.TestCase):
    def test_both_gate_identities_and_raw_divergence_fail_closed_without_repair(self):
        from jarvis.bot.phone_remote_login import LoginClockGate
        from jarvis.bot.phone_remote_service import FakeClockGate
        for mutation in ('login-identity','service-identity','raw-login'):
            with self.subTest(mutation=mutation):
                clock=ConnectionClock()
                if mutation=='login-identity':clock.login=LoginClockGate(wall_ms=1800000000000,monotonic_ms=1000)
                elif mutation=='service-identity':clock.service=FakeClockGate(1800000000)
                else:clock.login._monotonic_ms+=1
                with self.assertRaises(StoreUnavailable):clock.snapshot()
                with self.assertRaises(StoreUnavailable):clock.set_time(wall_ms=1800000000000,monotonic_ms=1001)

    def test_reserved_namespace_classifier_ignores_nested_business_content(self):
        from jarvis.bot.phone_remote_connection import is_handshake_attempt
        self.assertTrue(is_handshake_attempt('{"protocol":"mortimer.phone-connection.v1","payload":null}'))
        self.assertTrue(is_handshake_attempt('{"operation":"auth.prove","payload":false}'))
        self.assertTrue(is_handshake_attempt('{"protocol":"mortimer.phone-connection.v1","protocol":"other"}'))
        self.assertFalse(is_handshake_attempt(wire('session.status',{'text':'auth.prove','protocol':'mortimer.phone-connection.v1'})))
        self.assertFalse(is_handshake_attempt('{broken'))


class PairedClockLockOrderTests(unittest.TestCase):
    def test_direct_login_apis_refuse_f_to_l_before_taking_login_lock(self):
        for operation in ('set','snapshot','commit'):
            with self.subTest(operation=operation):
                clock=ConnectionClock()
                with clock.service._lock:
                    with self.assertRaises(StoreUnavailable):
                        if operation=='set':clock.login.set_time(wall_ms=1,monotonic_ms=1001)
                        elif operation=='snapshot':clock.login.snapshot()
                        else:
                            with clock.login.commit_guard():pass


class TerminalSendAdmissionTests(unittest.TestCase):
    fixture=ConnectionClockLeaseTests.fixture
    def test_host_terminal_transition_serializes_before_send_admission(self):
        for flag,value in (('_closed',True),('_fenced',True),('_proof_enabled',False)):
            with self.subTest(flag=flag):
                clock,host,registry=self.fixture();token=object();lease=registry.open(token)
                self.assertIs(registry.begin_send(lease,token),registry.records[lease].cancel)
                registry.end_send(lease,token)
                started,done=threading.Event(),threading.Event();result=[]
                def attempt():
                    started.set();result.append(registry.begin_send(lease,token));done.set()
                with host._lock:
                    worker=threading.Thread(target=attempt);worker.start();self.assertTrue(started.wait(1))
                    self.assertFalse(done.wait(.05),'send admission bypassed host lock')
                    setattr(host,flag,value)
                worker.join(1);self.assertFalse(worker.is_alive());self.assertEqual(result,[False])
                self.assertEqual(registry.records[lease].pending_sends,0)
                self.assertTrue(registry._sends_drained.is_set())


class RetainedLifetimeTests(unittest.TestCase):
    fixture=ConnectionClockLeaseTests.fixture
    def test_retirement_is_nonextending_and_retains_slot_until_exact_cleanup(self):
        clock,host,registry=self.fixture();token=object();lease=registry.open(token)
        record=registry.records[lease]
        record.state='active';record.expires_at_ms=20000;record.monotonic_deadline_ms=1000
        record.cleanup_complete=False
        with clock.service._lock:self.assertTrue(registry.lifetime_locked(record))
        registry.close(lease,token);deadline=record.retirement_deadline
        registry.close(lease,token)
        self.assertEqual(record.retirement_deadline,deadline)
        self.assertIs(registry.records[lease],record)
        with clock.service._lock:self.assertFalse(registry.lifetime_locked(record))
        self.assertFalse(registry.begin_send(lease,token))
        record.cleanup_complete=True
        registry.close(lease,token)
        self.assertNotIn(lease,registry.records)

    def test_retired_or_absent_lifetime_cannot_use_no_permit_fallback(self):
        clock,host,registry=self.fixture();token=object();lease=registry.open(token)
        record=registry.records[lease];record.state='active';record.expires_at_ms=20000;record.monotonic_deadline_ms=500
        self.assertIsNone(registry.permit)
        with clock.service._lock:
            self.assertTrue(registry.lifetime_locked(record))
            self.assertFalse(registry.lifetime_locked(None))
        clock.set_time(wall_ms=1,monotonic_ms=500)
        with clock.service._lock:self.assertFalse(registry.lifetime_locked(record))


class RetirementWatchdogReviewTests(unittest.TestCase):
    def test_stale_deadline_is_revalidated_and_true_stall_still_fences(self):
        from unittest.mock import patch
        from types import MethodType
        from jarvis.bot.phone_remote_service import _AuthorityChildServiceHost
        for mode in ('completed','replacement-retirement','stalled','drain-completed','drain-stalled'):
            with self.subTest(mode=mode):
                _,host,registry=ConnectionClockLeaseTests().fixture()
                host._connections=registry;host._current=None
                host._terminal=threading.Event();host._drained=threading.Event()
                host._quiescence_deadline=None
                waits=iter((False,True))
                host._maintenance_stop=SimpleNamespace(wait=lambda _:next(waits))
                host._thread=SimpleNamespace(is_alive=lambda:True)
                closed=[]
                def close_anchor():
                    self.assertTrue(host._lock.acquire(blocking=False),'anchor close under H')
                    host._lock.release()
                    self.assertFalse(registry.lock._is_owned(),'anchor close under C')
                    closed.append(True)
                host._anchor=SimpleNamespace(close=close_anchor)
                host._terminal_failure=MethodType(_AuthorityChildServiceHost._terminal_failure,host)
                now=[100.0]
                with patch('jarvis.bot.phone_remote_service.time.monotonic',side_effect=lambda:now[0]):
                    token=object();lease=registry.open(token);record=registry.records[lease]
                    survivor_token=object();survivor=registry.open(survivor_token)
                    record.cleanup_complete=False;registry.close(lease,token)
                    self.assertEqual(record.retirement_deadline,105)
                    original=registry.retirement_deadline
                    def snapshot_then_cleanup():
                        deadline=original();now[0]=104.999
                        if mode!='stalled':
                            with host._lock,registry.lock:
                                record.cleanup_complete=True;registry._retire_locked(record)
                            self.assertNotIn(lease,registry.records)
                        if mode=='replacement-retirement':
                            registry.records[survivor].cleanup_complete=False
                            registry.close(survivor,survivor_token)
                            self.assertEqual(registry.records[survivor].retirement_deadline,109.999)
                        if mode.startswith('drain-'):
                            host._quiescing=True;host._quiescence_deadline=105
                            if mode=='drain-completed':host._drained.set()
                        now[0]=105.001
                        return deadline
                    registry.retirement_deadline=snapshot_then_cleanup
                    _AuthorityChildServiceHost._watch_retirement(host)
                terminal=mode in ('stalled','drain-stalled')
                self.assertEqual(host._fenced,terminal)
                self.assertEqual(host._terminal.is_set(),terminal)
                self.assertEqual(bool(closed),terminal)
                if not terminal:self.assertIn(survivor,registry.records)
