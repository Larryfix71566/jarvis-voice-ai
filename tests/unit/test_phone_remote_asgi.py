import asyncio
import contextvars
import gc
import hashlib
import json
import sqlite3
import threading
import unittest
import weakref
from dataclasses import replace

from jarvis.auth import ClientIdentity
from jarvis.bot.phone_remote_asgi import ASGI_PATH, PhoneRemoteASGI
from jarvis.bot.phone_admission_store import FakeProtectedAnchor, PhoneAdmissionStore
from jarvis.bot.phone_remote_protocol import PROTOCOL
from jarvis.bot.phone_remote_service import (
    FakeClockGate, FakeContextVerifier, FakeMediaAdapter, PhoneRemoteService,
    TrustedRequestContext,
)


def envelope(operation="session.status", payload=None, request_id="req-1", **extra):
    value = {
        "kind": PROTOCOL,
        "protocol_version": 1,
        "request_id": request_id,
        "operation": operation,
        "payload": {} if payload is None else payload,
    }
    value.update(extra)
    return json.dumps(value, separators=(",", ":"))


class RecordingService:
    def __init__(self, result=None, error=None):
        self.calls = []
        self.result = result
        self.error = error

    def handle(self, raw, context):
        self.calls.append((raw, context))
        if self.error is not None:
            raise self.error
        request = json.loads(raw)
        if self.result is not None:
            return self.result
        operation = request["operation"]
        if operation == "session.status":
            return {"request_id": request["request_id"], "status": "ok",
                    "reason": "none", "payload": {"readiness": "ready"}}
        if operation in {"voice.offer", "voice.update"}:
            return {"request_id": request["request_id"], "status": "ok",
                    "reason": "none", "payload": {"peer_id": "peer-a", "sdp": "answer"}}
        if operation == "voice.end":
            return {"request_id": request["request_id"], "status": "ok",
                    "reason": "none", "payload": {"peer_id": "peer-a", "ended": True}}
        return {"request_id": request["request_id"], "status": "unavailable",
                "reason": "operation_unavailable", "payload": {}}


class BlockingMedia(FakeMediaAdapter):
    def __init__(self):
        super().__init__()
        self.started = threading.Event()
        self.release = threading.Event()
        self.finished = threading.Event()

    def prepare(self, sdp, peer_id=None, resource=None):
        self.started.set()
        if not self.release.wait(3):
            raise RuntimeError("test media barrier timed out")
        try:
            return super().prepare(sdp, peer_id, resource)
        finally:
            self.finished.set()


class BoundedBlockingService(RecordingService):
    def __init__(self):
        super().__init__()
        self.lock = threading.Lock()
        self.release = threading.Event()
        self.one_started = threading.Event()
        self.four_started = threading.Event()
        self.started = 0
        self.active = 0
        self.maximum_active = 0

    def handle(self, raw, context):
        with self.lock:
            self.started += 1
            self.active += 1
            self.maximum_active = max(self.maximum_active, self.active)
            self.one_started.set()
            if self.started >= 4:
                self.four_started.set()
        try:
            if not self.release.wait(3):
                raise RuntimeError("test dispatch barrier timed out")
            return super().handle(raw, context)
        finally:
            with self.lock:
                self.active -= 1


class PhoneRemoteASGITests(unittest.TestCase):
    def setUp(self):
        self.context = TrustedRequestContext(
            ClientIdentity(name="test", user_id="owner-a"),
            "owner-a", "session-a", "device-a", "incarnation-a")

    def invoke(self, app, events, *, scope=None):
        queue = list(events)
        sent = []

        async def receive():
            if queue:
                return queue.pop(0)
            return {"type": "websocket.disconnect", "code": 1000}

        async def send(message):
            sent.append(message)

        async def run():
            await app(scope or {"type": "websocket", "path": ASGI_PATH}, receive, send)

        asyncio.run(run())
        return sent

    @staticmethod
    def sent_text(messages):
        return [json.loads(m["text"]) for m in messages if m["type"] == "websocket.send"]

    def test_default_off_and_malformed_gate_never_resolve_context_or_service(self):
        for enabled in (False, None, "true", 1, object()):
            with self.subTest(enabled=type(enabled).__name__):
                service = RecordingService()
                provider_calls = []
                app = PhoneRemoteASGI(service, lambda scope, request: provider_calls.append(scope),
                                      enabled=enabled)
                sent = self.invoke(app, [{"type": "websocket.connect"},
                                         {"type": "websocket.disconnect", "code": 1000}])
                self.assertEqual(sent, [{"type": "websocket.close", "code": 1008}])
                self.assertEqual(service.calls, [])
                self.assertEqual(provider_calls, [])

    def test_missing_dependencies_and_wrong_path_are_not_usable(self):
        for service, provider in ((None, lambda _scope, _request: self.context),
                                  (RecordingService(), None)):
            with self.subTest(service=service, provider=provider):
                app = PhoneRemoteASGI(service, provider, enabled=True)
                sent = self.invoke(app, [{"type": "websocket.connect"}])
                self.assertEqual(sent, [{"type": "websocket.close", "code": 1008}])
        service = RecordingService()
        app = PhoneRemoteASGI(service, lambda _scope, _request: self.context, enabled=True)
        sent = self.invoke(app, [{"type": "websocket.connect"}],
                           scope={"type": "websocket", "path": "/elsewhere"})
        self.assertEqual(sent, [{"type": "websocket.close", "code": 1008}])
        self.assertEqual(service.calls, [])

    def test_non_websocket_scope_is_unmounted_404(self):
        sent = self.invoke(PhoneRemoteASGI(enabled=True), [],
                           scope={"type": "http", "path": ASGI_PATH})
        self.assertEqual(sent, [
            {"type": "http.response.start", "status": 404,
             "headers": [(b"content-length", b"0")]},
            {"type": "http.response.body", "body": b""},
        ])

    def test_valid_wire_is_forwarded_byte_for_byte_with_server_context(self):
        service = RecordingService()
        scope = {"type": "websocket", "path": ASGI_PATH,
                 "state": {"trusted_context": self.context}}
        provider_calls = []

        def provider(actual_scope, request):
            provider_calls.append((actual_scope, request))
            if request is not None:
                raise AssertionError("session.status does not request a ticket")
            return actual_scope["state"]["trusted_context"]

        raw = envelope("session.status", request_id="exact-wire")
        sent = self.invoke(PhoneRemoteASGI(service, provider, enabled=True), [
            {"type": "websocket.connect"},
            {"type": "websocket.receive", "text": raw},
            {"type": "websocket.disconnect", "code": 1000},
        ], scope=scope)
        self.assertEqual(service.calls, [(raw, self.context)])
        self.assertEqual(provider_calls, [(scope, None)])
        self.assertEqual(sent[0], {"type": "websocket.accept"})
        self.assertEqual(self.sent_text(sent), [{
            "request_id": "exact-wire", "status": "ok", "reason": "none",
            "payload": {"readiness": "ready"},
        }])

    def test_asgi_text_and_bytes_allow_the_other_field_to_be_null(self):
        raw_text = envelope("session.status", request_id="text-null")
        raw_bytes = envelope("session.status", request_id="bytes-null").encode()
        for event, expected in (
                ({"type": "websocket.receive", "text": raw_text, "bytes": None}, raw_text),
                ({"type": "websocket.receive", "bytes": raw_bytes, "text": None}, raw_bytes)):
            with self.subTest(expected=type(expected).__name__):
                service = RecordingService()
                sent = self.invoke(PhoneRemoteASGI(
                    service, lambda _scope, _request: self.context, enabled=True), [
                        {"type": "websocket.connect"}, event,
                        {"type": "websocket.disconnect", "code": 1000},
                    ])
                self.assertEqual(service.calls, [(expected, self.context)])
                self.assertEqual(self.sent_text(sent)[0]["status"], "ok")

        service = RecordingService()
        sent = self.invoke(PhoneRemoteASGI(
            service, lambda _scope, _request: self.context, enabled=True), [
                {"type": "websocket.connect"},
                {"type": "websocket.receive", "text": raw_text, "bytes": raw_bytes},
                {"type": "websocket.disconnect", "code": 1000},
            ])
        self.assertEqual(service.calls, [])
        self.assertEqual(self.sent_text(sent)[0]["reason"], "malformed_request")

    @staticmethod
    def make_real_service(media=None):
        db = sqlite3.connect(":memory:", check_same_thread=False)
        store = PhoneAdmissionStore(db, FakeProtectedAnchor())
        identity = ClientIdentity(name="asgi-test", user_id="owner-a")
        store.add_device(identity=identity, device_id="device-a", owner_id="owner-a",
                         public_key=b"test-public-key", key_algorithm="test")
        store.add_grant(identity=identity, grant_id="grant-a", device_id="device-a",
                        owner_id="owner-a", scopes=["read", "voice"])
        incarnation = store.login(identity=identity, session_id="session-a",
                                  grant_id="grant-a", owner_id="owner-a",
                                  now=1, expires_at=100)
        context = TrustedRequestContext(identity, "owner-a", "session-a", "device-a",
                                        incarnation)
        service = PhoneRemoteService(store, FakeContextVerifier(), media or FakeMediaAdapter(),
                                     clock=FakeClockGate(2))
        return db, store, service, context

    def test_real_s2_offer_then_update_resolves_fresh_server_ticket_context(self):
        db, store, service, connection = self.make_real_service()
        offer_context = replace(connection, ticket_id="server-offer-ticket")
        store.issue_ticket(identity=connection.identity, ticket_id=offer_context.ticket_id,
            session_id=connection.session_id, owner_id=connection.owner_id, purpose="offer",
            payload_digest=hashlib.sha256(b"offer-sdp").hexdigest(), now=2, expires_at=20)
        update_contexts = {}
        provider_calls = []

        def provider(scope, request):
            provider_calls.append(None if request is None else request["operation"])
            if request is None:
                return connection
            if request["operation"] == "voice.offer":
                return offer_context
            if request["operation"] == "voice.update":
                return update_contexts[request["request_id"]]
            raise AssertionError("unexpected request-specific context lookup")

        sent = []
        step = 0

        async def receive():
            nonlocal step
            step += 1
            if step == 1:
                return {"type": "websocket.connect"}
            if step == 2:
                return {"type": "websocket.receive",
                        "text": envelope("voice.offer", {"sdp": "offer-sdp"}, "offer-1")}
            if step == 3:
                offer_reply = next(json.loads(item["text"]) for item in sent
                                   if item["type"] == "websocket.send")
                peer_id = offer_reply["payload"]["peer_id"]
                update_sdp = "update-sdp"
                store.issue_ticket(identity=connection.identity,
                    ticket_id="server-update-ticket", session_id=connection.session_id,
                    owner_id=connection.owner_id, purpose="update",
                    payload_digest=hashlib.sha256(update_sdp.encode()).hexdigest(), now=2,
                    expires_at=20, peer_id=peer_id)
                update_contexts["update-1"] = replace(
                    connection, ticket_id="server-update-ticket")
                return {"type": "websocket.receive", "text": envelope(
                    "voice.update", {"peer_id": peer_id, "sdp": update_sdp}, "update-1")}
            return {"type": "websocket.disconnect", "code": 1000}

        async def send(message):
            sent.append(message)

        async def run():
            await PhoneRemoteASGI(service, provider, enabled=True)(
                {"type": "websocket", "path": ASGI_PATH}, receive, send)

        try:
            asyncio.run(run())
            replies = self.sent_text(sent)
            self.assertEqual([reply["status"] for reply in replies], ["ok", "ok"])
            self.assertEqual(provider_calls, [None, "voice.offer", "voice.update"])
            self.assertTrue(store._tickets["server-offer-ticket"]["consumed"])
            self.assertTrue(store._tickets["server-update-ticket"]["consumed"])
        finally:
            store._drop_admissions()
            db.close()

    def test_blocking_s2_media_does_not_block_other_connections_and_cancel_drains(self):
        db, store, service, connection = self.make_real_service(BlockingMedia())
        media = service.media
        store.issue_ticket(identity=connection.identity, ticket_id="blocking-offer-ticket",
            session_id=connection.session_id, owner_id=connection.owner_id, purpose="offer",
            payload_digest=hashlib.sha256(b"blocking-sdp").hexdigest(), now=2, expires_at=20)
        offer_context = replace(connection, ticket_id="blocking-offer-ticket")

        def provider(_scope, request):
            if request is None:
                return connection
            if request["operation"] == "voice.offer":
                return offer_context
            return connection

        offer_sent = []

        async def offer_receive():
            if not getattr(offer_receive, "started", False):
                offer_receive.started = True
                return {"type": "websocket.connect"}
            return {"type": "websocket.receive", "text": envelope(
                "voice.offer", {"sdp": "blocking-sdp"}, "blocking-offer")}

        async def offer_send(message):
            offer_sent.append(message)

        status_sent = []

        async def status_receive():
            events = getattr(status_receive, "events", None)
            if events is None:
                status_receive.events = iter([
                    {"type": "websocket.connect"},
                    {"type": "websocket.receive", "text": envelope(
                        "session.status", request_id="parallel-status")},
                    {"type": "websocket.disconnect", "code": 1000},
                ])
                events = status_receive.events
            return next(events)

        async def status_send(message):
            status_sent.append(message)

        app = PhoneRemoteASGI(service, provider, enabled=True)

        async def scenario():
            offer_task = asyncio.create_task(app(
                {"type": "websocket", "path": ASGI_PATH}, offer_receive, offer_send))
            self.assertTrue(await asyncio.to_thread(media.started.wait, 2))

            status_task = asyncio.create_task(app(
                {"type": "websocket", "path": ASGI_PATH}, status_receive, status_send))
            await asyncio.wait_for(status_task, timeout=1)
            self.assertEqual(self.sent_text(status_sent)[0]["status"], "ok")

            loop_progress = asyncio.Event()
            asyncio.get_running_loop().call_soon(loop_progress.set)
            await asyncio.wait_for(loop_progress.wait(), timeout=0.2)

            offer_task.cancel()
            await asyncio.sleep(0)
            self.assertFalse(offer_task.done(), "cancel must drain the synchronous worker")
            media.release.set()
            with self.assertRaises(asyncio.CancelledError):
                await asyncio.wait_for(offer_task, timeout=2)
            self.assertTrue(media.finished.is_set())
            self.assertEqual(offer_sent, [{"type": "websocket.accept"}])

        try:
            asyncio.run(scenario())
        finally:
            media.release.set()
            store._drop_admissions()
            db.close()

    def test_sync_context_provider_does_not_block_event_loop(self):
        service = RecordingService()
        started = threading.Event()
        release = threading.Event()
        returned = []

        def blocking_provider(_scope, _request):
            started.set()
            if not release.wait(3):
                raise RuntimeError("provider barrier timed out")
            return self.context

        app = PhoneRemoteASGI(service, blocking_provider, enabled=True)

        async def receive():
            return {"type": "websocket.connect"}

        async def send(_message):
            pass

        async def scenario():
            task = asyncio.create_task(app(
                {"type": "websocket", "path": ASGI_PATH}, receive, send))
            self.assertTrue(await asyncio.to_thread(started.wait, 2))
            progressed = asyncio.Event()
            asyncio.get_running_loop().call_soon(progressed.set)
            await asyncio.wait_for(progressed.wait(), timeout=0.2)
            release.set()
            await task
            returned.append(True)

        try:
            asyncio.run(scenario())
            self.assertEqual(returned, [True])
        finally:
            release.set()

    def test_sync_provider_receives_fresh_contextvars_per_request(self):
        service = RecordingService()
        request_marker = contextvars.ContextVar("phone-request-marker", default="unset")
        observed = []
        both_providers_started = threading.Barrier(2)

        def provider(_scope, _request):
            value = request_marker.get()
            observed.append(value)
            request_marker.set("worker-contamination")
            if value in {"request-A", "request-B"}:
                both_providers_started.wait(timeout=2)
            return self.context

        app = PhoneRemoteASGI(service, provider, enabled=True)

        async def one(value, request_id):
            request_marker.set(value)
            events = iter([
                {"type": "websocket.connect"},
                {"type": "websocket.receive", "text": envelope(request_id=request_id)},
                {"type": "websocket.disconnect", "code": 1000},
            ])

            async def receive():
                return next(events)

            async def send(_message):
                pass

            await app({"type": "websocket", "path": ASGI_PATH}, receive, send)

        async def scenario():
            await asyncio.gather(
                one("request-A", "context-A"),
                one("request-B", "context-B"),
            )
            await one("request-C", "context-C")

        asyncio.run(scenario())
        self.assertEqual(set(observed), {"request-A", "request-B", "request-C"})

    def test_cancelled_sync_provider_drains_returned_future_before_connection_exit(self):
        service = RecordingService()
        provider_started = threading.Event()
        provider_release = threading.Event()
        future_started = threading.Event()
        future_release = threading.Event()
        future_finished = threading.Event()
        loop_holder = {}

        async def late_provider_effect():
            future_started.set()
            while not future_release.is_set():
                await asyncio.sleep(0.002)
            future_finished.set()
            return self.context

        def provider(_scope, _request):
            provider_started.set()
            if not provider_release.wait(3):
                raise RuntimeError("provider barrier timed out")
            loop = loop_holder["loop"]
            return asyncio.run_coroutine_threadsafe(late_provider_effect(), loop)

        app = PhoneRemoteASGI(service, provider, enabled=True)
        sent = []

        async def receive():
            return {"type": "websocket.connect"}

        async def send(message):
            sent.append(message)

        async def scenario():
            loop_holder["loop"] = asyncio.get_running_loop()
            task = asyncio.create_task(app(
                {"type": "websocket", "path": ASGI_PATH}, receive, send))
            self.assertTrue(await asyncio.to_thread(provider_started.wait, 2))
            task.cancel()
            provider_release.set()
            self.assertTrue(await asyncio.to_thread(future_started.wait, 2))
            await asyncio.sleep(0.02)
            self.assertFalse(task.done(), "provider future must remain owned during cancellation")
            future_release.set()
            with self.assertRaises(asyncio.CancelledError):
                await asyncio.wait_for(task, timeout=2)
            self.assertTrue(future_finished.is_set())

        try:
            asyncio.run(scenario())
            self.assertEqual(sent, [])
            self.assertEqual(service.calls, [])
        finally:
            provider_release.set()
            future_release.set()

    def test_reusable_custom_awaitable_is_normalized_and_executed_once_on_cancel(self):
        service = RecordingService()
        provider_started = threading.Event()
        awaitable_started = None
        awaitable_release = None
        context = self.context
        effects = []
        await_calls = []

        class ReusableAwaitable:
            def __await__(self):
                await_calls.append("await")

                async def run():
                    awaitable_started.set()
                    await awaitable_release.wait()
                    effects.append("completed")
                    return context

                return run().__await__()

        awaitable = ReusableAwaitable()

        def provider(_scope, _request):
            provider_started.set()
            return awaitable

        app = PhoneRemoteASGI(service, provider, enabled=True)
        sent = []

        async def receive():
            return {"type": "websocket.connect"}

        async def send(message):
            sent.append(message)

        async def scenario():
            nonlocal awaitable_started, awaitable_release
            awaitable_started = asyncio.Event()
            awaitable_release = asyncio.Event()
            task = asyncio.create_task(app(
                {"type": "websocket", "path": ASGI_PATH}, receive, send))
            try:
                self.assertTrue(await asyncio.to_thread(provider_started.wait, 2))
                await asyncio.wait_for(awaitable_started.wait(), timeout=2)
                task.cancel()
                await asyncio.sleep(0)
                self.assertFalse(task.done(), "cancellation must drain the same owned task")
                awaitable_release.set()
                with self.assertRaises(asyncio.CancelledError):
                    await asyncio.wait_for(task, timeout=2)
            finally:
                awaitable_release.set()

        asyncio.run(scenario())
        self.assertEqual(await_calls, ["await"])
        self.assertEqual(effects, ["completed"])
        self.assertEqual(service.calls, [])
        self.assertEqual(sent, [])

    def test_dispatch_limit_is_shared_by_adapter_wrappers_on_same_loop(self):
        service = BoundedBlockingService()
        apps = [
            PhoneRemoteASGI(service, lambda _scope, _request: self.context, enabled=True)
            for _ in range(2)
        ]

        async def one_connection(index):
            events = iter([
                {"type": "websocket.connect"},
                {"type": "websocket.receive", "text": envelope(
                    request_id=f"multi-wrapper-{index}")},
                {"type": "websocket.disconnect", "code": 1000},
            ])
            sent = []

            async def receive():
                return next(events)

            async def send(message):
                sent.append(message)

            await apps[index % len(apps)](
                {"type": "websocket", "path": ASGI_PATH}, receive, send)
            return sent

        async def scenario():
            tasks = [asyncio.create_task(one_connection(index)) for index in range(7)]
            self.assertTrue(await asyncio.to_thread(service.four_started.wait, 2))
            await asyncio.sleep(0.02)
            with service.lock:
                self.assertEqual(service.active, 4)
                self.assertEqual(service.started, 4)
                self.assertEqual(service.maximum_active, 4)
            service.release.set()
            results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=2)
            self.assertEqual(len(results), 7)
            self.assertEqual(service.started, 7)
            self.assertEqual(service.maximum_active, 4)

        try:
            asyncio.run(scenario())
        finally:
            service.release.set()

    def test_event_loop_shutdown_cancellation_retains_worker_until_thread_finishes(self):
        service = BoundedBlockingService()
        app = PhoneRemoteASGI(service, lambda _scope, _request: self.context, enabled=True)
        events = iter([
            {"type": "websocket.connect"},
            {"type": "websocket.receive", "text": envelope(request_id="shutdown-drain")},
        ])

        async def receive():
            return next(events)

        async def send(_message):
            pass

        async def scenario():
            asyncio.create_task(app(
                {"type": "websocket", "path": ASGI_PATH}, receive, send))
            self.assertTrue(await asyncio.to_thread(service.one_started.wait, 2))
            # asyncio.run now cancels the connection task during loop shutdown.

        releaser = threading.Timer(0.15, service.release.set)
        releaser.start()
        try:
            asyncio.run(scenario())
            self.assertTrue(service.release.is_set())
            self.assertEqual(service.active, 0)
            self.assertTrue(service.maximum_active <= 4)
        finally:
            service.release.set()
            releaser.join(timeout=1)

    def test_service_dispatch_parallelism_is_bounded(self):
        service = BoundedBlockingService()
        app = PhoneRemoteASGI(service, lambda _scope, _request: self.context, enabled=True)

        async def one_connection(index):
            events = iter([
                {"type": "websocket.connect"},
                {"type": "websocket.receive", "text": envelope(
                    request_id=f"bounded-{index}")},
                {"type": "websocket.disconnect", "code": 1000},
            ])
            sent = []

            async def receive():
                return next(events)

            async def send(message):
                sent.append(message)

            await app({"type": "websocket", "path": ASGI_PATH}, receive, send)
            return sent

        async def scenario():
            tasks = [asyncio.create_task(one_connection(index)) for index in range(5)]
            self.assertTrue(await asyncio.to_thread(service.four_started.wait, 2))
            await asyncio.sleep(0.02)
            with service.lock:
                self.assertEqual(service.active, 4)
                self.assertEqual(service.started, 4)
                self.assertEqual(service.maximum_active, 4)
            service.release.set()
            results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=2)
            self.assertEqual(len(results), 5)
            self.assertEqual(service.started, 5)
            self.assertEqual(service.maximum_active, 4)

        try:
            asyncio.run(scenario())
        finally:
            service.release.set()

    def test_all_closed_operations_are_forwarded_and_reserved_effects_stay_unavailable(self):
        cases = [
            ("session.status", {}),
            ("voice.offer", {"sdp": "offer"}),
            ("voice.update", {"peer_id": "peer-a", "sdp": "offer"}),
            ("voice.end", {"peer_id": "peer-a"}),
            ("results.snapshot", {}), ("results.resume", {"cursor": "A" * 43}),
            ("call.state", {}), ("call.answer", {}), ("call.decline", {}),
        ]
        for index, (operation, payload) in enumerate(cases):
            with self.subTest(operation=operation):
                service = RecordingService()
                raw = envelope(operation, payload, request_id=f"req-{index}")

                def provider(_scope, request):
                    if request is not None and operation in {"voice.offer", "voice.update"}:
                        return replace(self.context, ticket_id=f"ticket-{index}")
                    return self.context

                sent = self.invoke(PhoneRemoteASGI(service, provider, enabled=True), [
                    {"type": "websocket.connect"},
                    {"type": "websocket.receive", "text": raw},
                    {"type": "websocket.disconnect", "code": 1000},
                ])
                expected_context = (replace(self.context, ticket_id=f"ticket-{index}")
                                    if operation in {"voice.offer", "voice.update"}
                                    else self.context)
                self.assertEqual(service.calls, [(raw, expected_context)])
                response = self.sent_text(sent)[0]
                self.assertEqual(response["request_id"], f"req-{index}")
                if operation.startswith("results.") or operation.startswith("call."):
                    self.assertEqual(response, {
                        "request_id": f"req-{index}", "status": "unavailable",
                        "reason": "operation_unavailable", "payload": {},
                    })

    def test_results_resume_without_cursor_is_rejected_before_service_dispatch(self):
        service = RecordingService()
        raw = envelope("results.resume", {}, request_id="missing-cursor")

        sent = self.invoke(PhoneRemoteASGI(
            service, lambda _scope, _request: self.context, enabled=True), [
                {"type": "websocket.connect"},
                {"type": "websocket.receive", "text": raw},
                {"type": "websocket.disconnect", "code": 1000},
            ])

        self.assertEqual(service.calls, [])
        self.assertEqual(self.sent_text(sent), [{
            "request_id": "missing-cursor", "status": "denied",
            "reason": "malformed_request", "payload": {},
        }])

    def test_request_ticket_context_cannot_change_authenticated_binding(self):
        service = RecordingService()
        raw = envelope("voice.offer", {"sdp": "offer"}, "wrong-binding")

        def provider(_scope, request):
            if request is None:
                return self.context
            return replace(self.context, session_id="other-session", ticket_id="ticket")

        sent = self.invoke(PhoneRemoteASGI(service, provider, enabled=True), [
            {"type": "websocket.connect"},
            {"type": "websocket.receive", "text": raw},
            {"type": "websocket.disconnect", "code": 1000},
        ])
        self.assertEqual(service.calls, [])
        self.assertEqual(self.sent_text(sent), [{
            "request_id": "wrong-binding", "status": "denied",
            "reason": "not_authorized", "payload": {},
        }])

    def test_malformed_closed_json_and_oversized_frames_never_reach_service(self):
        duplicate = (
            '{"kind":"mortimer.phone-remote.v1","kind":"x",'
            '"protocol_version":1,"request_id":"dup",'
            '"operation":"session.status","payload":{}}'
        )
        deep = (
            '{"kind":"mortimer.phone-remote.v1","protocol_version":1,'
            '"request_id":"deep","operation":"session.status",'
            '"payload":{"x":' + ("[" * 66) + "0" + ("]" * 66) + "}}"
        )
        frames = ["not-json", duplicate, envelope(extra={"owner_id": "attacker"}),
                  envelope(request_id="nonfinite", extra_float=float("nan")),
                  b"\xff", b"x" * (1_048_576 + 1), deep,
                  {"both": True}]
        events = [{"type": "websocket.connect"}]
        for frame in frames:
            if isinstance(frame, dict):
                events.append({"type": "websocket.receive", "text": "{}", "bytes": b"{}"})
            elif isinstance(frame, bytes):
                events.append({"type": "websocket.receive", "bytes": frame})
            else:
                events.append({"type": "websocket.receive", "text": frame})
        events.append({"type": "websocket.disconnect", "code": 1000})
        service = RecordingService()
        sent = self.invoke(PhoneRemoteASGI(service, lambda _scope, _request: self.context,
                                           enabled=True), events)
        self.assertEqual(service.calls, [])
        replies = self.sent_text(sent)
        self.assertEqual(len(replies), len(frames))
        for reply in replies:
            self.assertEqual(reply["status"], "denied")
            self.assertEqual(reply["reason"], "malformed_request")
            self.assertEqual(reply["payload"], {})

    def test_unsupported_protocol_uses_closed_incompatible_response(self):
        raw = envelope(request_id="future", protocol_version=2)
        service = RecordingService()
        sent = self.invoke(PhoneRemoteASGI(service, lambda _scope, _request: self.context,
                                           enabled=True), [
            {"type": "websocket.connect"},
            {"type": "websocket.receive", "text": raw},
            {"type": "websocket.disconnect", "code": 1000},
        ])
        self.assertEqual(service.calls, [])
        self.assertEqual(self.sent_text(sent), [{
            "request_id": "future", "status": "incompatible",
            "reason": "unsupported_protocol", "payload": {},
        }])

    def test_untrusted_json_identity_is_never_used_as_context(self):
        service = RecordingService()
        raw = envelope(request_id="forged", owner_id="attacker", device_id="other",
                       session_id="foreign", scopes=["admin"])
        sent = self.invoke(PhoneRemoteASGI(service, lambda _scope, _request: self.context,
                                           enabled=True), [
            {"type": "websocket.connect"},
            {"type": "websocket.receive", "text": raw},
            {"type": "websocket.disconnect", "code": 1000},
        ])
        self.assertEqual(service.calls, [])
        reply = self.sent_text(sent)[0]
        self.assertEqual((reply["status"], reply["reason"]),
                         ("denied", "malformed_request"))

    def test_context_provider_errors_and_wrong_context_fail_closed_without_leaks(self):
        for provider, code in ((lambda _scope, _request: (_ for _ in ()).throw(
                RuntimeError("context-secret-canary")), 1011),
                (lambda _scope, _request: {"owner_id": "owner-a"}, 1008)):
            with self.subTest(code=code):
                service = RecordingService()
                sent = self.invoke(PhoneRemoteASGI(service, provider, enabled=True), [
                    {"type": "websocket.connect"}])
                self.assertEqual(sent, [{"type": "websocket.close", "code": code}])
                self.assertNotIn("context-secret-canary", repr(sent))
                self.assertEqual(service.calls, [])

    def test_service_exception_and_invalid_responses_are_content_free(self):
        canary = "private-service-canary"
        invalid = [
            RecordingService(error=RuntimeError(canary)),
            RecordingService(result={"request_id": "req-1", "status": "ok",
                                     "reason": "none", "payload": {"secret": canary}}),
            RecordingService(result={"request_id": "wrong-id", "status": "ok",
                                     "reason": "none", "payload": {"readiness": "ready"}}),
        ]
        for service in invalid:
            with self.subTest(service=service):
                raw = envelope(request_id="req-1")
                sent = self.invoke(PhoneRemoteASGI(service, lambda _scope, _request: self.context,
                                                   enabled=True), [
                    {"type": "websocket.connect"},
                    {"type": "websocket.receive", "text": raw},
                    {"type": "websocket.disconnect", "code": 1000},
                ])
                self.assertNotIn(canary, repr(sent))
                self.assertEqual(self.sent_text(sent), [{
                    "request_id": "req-1", "status": "unavailable",
                    "reason": "authority_unavailable", "payload": {},
                }])

    def test_disconnect_stops_reads_and_drops_connection_context(self):
        service = RecordingService()
        context = TrustedRequestContext(
            ClientIdentity(name="transient", user_id="owner-a"),
            "owner-a", "session-transient", "device-a", "incarnation-transient")
        reference = weakref.ref(context)
        held = {"context": context}
        app = PhoneRemoteASGI(service, lambda _scope, _request: held["context"], enabled=True)
        sent = self.invoke(app, [
            {"type": "websocket.connect"},
            {"type": "websocket.disconnect", "code": 1000},
            {"type": "websocket.receive", "text": envelope()},
        ])
        self.assertEqual(sent, [{"type": "websocket.accept"}])
        self.assertEqual(service.calls, [])
        held["context"] = None
        del context
        gc.collect()
        self.assertIsNone(reference())

    def test_missing_connect_does_not_resolve_context(self):
        service = RecordingService()
        provider_calls = []
        sent = self.invoke(PhoneRemoteASGI(
            service, lambda scope, request: provider_calls.append(scope), enabled=True), [
                {"type": "websocket.disconnect", "code": 1000}])
        self.assertEqual(sent, [])
        self.assertEqual(provider_calls, [])


if __name__ == "__main__":
    unittest.main()

class PhoneCardASGITests(unittest.TestCase):
    def test_checked_card_wire_uses_only_trusted_context_and_rejects_identity_smuggling(self):
        from tests.unit.test_phone_remote_result_commands import CardFixture, wire
        fixture=CardFixture();self.addCleanup(fixture.close);fixture.sync()
        calls=[]
        def provider(scope,request):
            calls.append(None if request is None else request['operation']);return fixture.context
        app=PhoneRemoteASGI(fixture.service,provider,enabled=True)
        messages=[{'type':'websocket.connect'},
            {'type':'websocket.receive','text':wire('results.pin',fixture.target(),'pin')},
            {'type':'websocket.receive','text':wire('results.close',{**fixture.target(),'owner_id':'b'},'forged')},
            {'type':'websocket.disconnect','code':1000}]
        sent=[]
        async def receive():return messages.pop(0)
        async def send(message):sent.append(message)
        asyncio.run(app({'type':'websocket','path':ASGI_PATH},receive,send))
        replies=[json.loads(m['text']) for m in sent if m['type']=='websocket.send']
        self.assertEqual([r['reason'] for r in replies],['none','malformed_request'])
        self.assertTrue(replies[0]['payload']['cards'][0]['pinned'])
        self.assertEqual(calls,[None])  # non-voice requests use the admitted connection binding


class ProofASGIConstructionTests(unittest.IsolatedAsyncioTestCase):
    async def test_unprepared_host_truthy_flags_and_spoofed_scope_never_call_provider(self):
        from jarvis.bot.phone_remote_asgi import create_phone_remote_connection_asgi
        from jarvis.bot.phone_remote_service import _AuthorityChildServiceHost
        for host in (None,object(),object.__new__(_AuthorityChildServiceHost)):
            for enabled in (False,True,1,'true'):
                sent=[]
                async def receive():raise AssertionError('unprepared adapter consumed transport')
                async def send(event):sent.append(event)
                await create_phone_remote_connection_asgi(host,enabled=enabled)(
                    {'type':'websocket','path':ASGI_PATH,'state':{'trusted_context':object()}},receive,send)
                self.assertEqual(sent,[{'type':'websocket.close','code':1008}])

    async def test_proof_factory_http_is_unmounted_and_has_no_context_provider_parameter(self):
        from jarvis.bot.phone_remote_asgi import create_phone_remote_connection_asgi
        with self.assertRaises(TypeError):create_phone_remote_connection_asgi(context_provider=lambda:object())
        sent=[]
        async def receive():raise AssertionError('HTTP input consumed')
        async def send(event):sent.append(event)
        await create_phone_remote_connection_asgi()({'type':'http','path':ASGI_PATH},receive,send)
        self.assertEqual(sent[0]['status'],404)
