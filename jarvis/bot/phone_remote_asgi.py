"""Offline ASGI adapter for the synthetic Mortimer phone service.

This module is deliberately not mounted by the bot. A server-owned caller must
inject the R3.9 service, an authenticated request-context provider, and the
exact boolean feature gate. It creates no authority, transport, or listener.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import contextvars
import inspect
import threading
import weakref

from jarvis.bot.phone_remote_protocol import (
    ProtocolError,
    encode_response,
    parse_request,
    response,
)
from jarvis.bot.phone_remote_service import TrustedRequestContext

ASGI_PATH = "/ws/phone-remote"
_CLOSE_POLICY = 1008
_CLOSE_INTERNAL = 1011
_DISPATCH_LIMIT = 4
_DISPATCH_LOCK = threading.Lock()
_DISPATCH_SLOTS_BY_LOOP = weakref.WeakKeyDictionary()
_WORKERS_BY_LOOP = weakref.WeakKeyDictionary()


def _loop_state(loop):
    """Return shared bounded dispatch state for every adapter on this loop."""
    with _DISPATCH_LOCK:
        slots = _DISPATCH_SLOTS_BY_LOOP.get(loop)
        if slots is None:
            slots = asyncio.Semaphore(_DISPATCH_LIMIT)
            _DISPATCH_SLOTS_BY_LOOP[loop] = slots
            _WORKERS_BY_LOOP[loop] = set()
        return slots, _WORKERS_BY_LOOP[loop]


def _own_awaitable(value):
    """Normalize an arbitrary awaitable exactly once to an owned task/future."""
    if isinstance(value, concurrent.futures.Future):
        return asyncio.wrap_future(value)
    if isinstance(value, asyncio.Future):
        return value
    return asyncio.ensure_future(value)


async def _await_owned(task):
    """Await the same normalized task and drain it before cancellation escapes."""
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        try:
            task.result()
        except Exception:
            pass
        raise


class PhoneRemoteASGI:
    """Small injected-dependency ASGI app; it never creates production state."""

    def __init__(self, service=None, context_provider=None, *, enabled=False):
        # bool is exact and deliberately fail-closed: strings such as "true",
        # integers, absent values, and other truthy objects do not enable it.
        self._enabled = type(enabled) is bool and enabled is True
        self._service = service
        self._context_provider = context_provider
    async def _blocking_call(self, function, *args, hold_for_awaitable=False):
        """Bound sync dependencies through thread and optional awaitable work."""
        loop = asyncio.get_running_loop()
        slots, workers = _loop_state(loop)
        await slots.acquire()
        try:
            call_context = contextvars.copy_context()
            worker = loop.run_in_executor(
                None, call_context.run, function, *args)
        except BaseException:
            slots.release()
            raise
        with _DISPATCH_LOCK:
            workers.add(worker)

        def completed(done):
            # Future callbacks run on the event-loop thread. Keeping the future
            # in workers also retains ownership if its awaiting task is cancelled.
            workers.discard(done)
            if not hold_for_awaitable:
                slots.release()

        worker.add_done_callback(completed)
        owned_result = None
        try:
            result = await asyncio.shield(worker)
            if hold_for_awaitable and (
                    inspect.isawaitable(result)
                    or isinstance(result, concurrent.futures.Future)):
                owned_result = _own_awaitable(result)
                result = await _await_owned(owned_result)
            return result
        except asyncio.CancelledError:
            # Do not let cancellation of a request cancel a running thread or
            # release its shared slot early. Drain it before this call returns.
            while not worker.done():
                try:
                    await asyncio.shield(worker)
                except asyncio.CancelledError:
                    continue
                except Exception:
                    break
            try:
                result = worker.result()
            except Exception:
                result = None
            if (owned_result is None and (inspect.isawaitable(result) or isinstance(
                    result, concurrent.futures.Future))):
                owned_result = _own_awaitable(result)
            if owned_result is not None:
                try:
                    await _await_owned(owned_result)
                except asyncio.CancelledError:
                    # Preserve the original request cancellation after the
                    # callback's returned asynchronous work has completed.
                    pass
                except Exception:
                    pass
            raise
        finally:
            if hold_for_awaitable:
                slots.release()

    async def _dispatch(self, service, raw, context):
        """Run blocking service work off-loop with bounded, owned lifetime.

        Cancellation cannot stop a running synchronous service call. Shield it,
        drain it before propagating cancellation, and hold the bounded slot until
        the call has completed so no service effects are left detached.
        """
        return await self._blocking_call(service.handle, raw, context)

    async def _request_context(self, provider, scope, request):
        # None resolves the authenticated connection binding. A voice request
        # is passed only as an untrusted selector for a server-owned ticket.
        # Invoke even sync providers off-loop. Async providers return their
        # coroutine from this bounded call and are awaited on the event loop.
        return await self._blocking_call(
            provider, scope, request, hold_for_awaitable=True)

    @staticmethod
    def _same_connection_binding(connection, request_context):
        return (
            type(connection) is TrustedRequestContext
            and type(request_context) is TrustedRequestContext
            and request_context.identity is connection.identity
            and request_context.owner_id == connection.owner_id
            and request_context.session_id == connection.session_id
            and request_context.device_id == connection.device_id
            and request_context.login_incarnation == connection.login_incarnation
        )

    @staticmethod
    async def _close(send, code):
        await send({"type": "websocket.close", "code": code})

    @staticmethod
    async def _http_not_found(send):
        await send({
            "type": "http.response.start",
            "status": 404,
            "headers": [(b"content-length", b"0")],
        })
        await send({"type": "http.response.body", "body": b""})

    async def __call__(self, scope, receive, send):
        if type(scope) is not dict or type(scope.get("type")) is not str:
            return
        if scope["type"] == "http":
            await self._http_not_found(send)
            return
        if scope["type"] != "websocket":
            return
        if scope.get("path") != ASGI_PATH:
            await self._close(send, _CLOSE_POLICY)
            return
        service = self._service
        context_provider = self._context_provider
        if (self._enabled is not True or service is None
                or not callable(getattr(service, "handle", None))
                or not callable(context_provider)):
            await self._close(send, _CLOSE_POLICY)
            return

        try:
            first = await receive()
        except Exception:
            await self._close(send, _CLOSE_INTERNAL)
            return
        if type(first) is not dict or first.get("type") != "websocket.connect":
            return

        try:
            connection_context = await self._request_context(context_provider, scope, None)
        except Exception:
            # Provider details can contain identity or credential information.
            await self._close(send, _CLOSE_INTERNAL)
            return
        if type(connection_context) is not TrustedRequestContext:
            await self._close(send, _CLOSE_POLICY)
            return
        if connection_context.ticket_id is not None:
            await self._close(send, _CLOSE_POLICY)
            return

        try:
            await send({"type": "websocket.accept"})
            while True:
                event = await receive()
                if type(event) is not dict:
                    break
                if event.get("type") == "websocket.disconnect":
                    break
                if event.get("type") != "websocket.receive":
                    break

                # Do not normalize or reconstruct valid input: the existing
                # service owns envelope parsing, authorization and effects.
                text_frame = event.get("text")
                bytes_frame = event.get("bytes")
                if type(text_frame) is str and bytes_frame is None:
                    raw = text_frame
                elif type(bytes_frame) is bytes and text_frame is None:
                    raw = bytes_frame
                else:
                    raw = None
                try:
                    request = parse_request(raw)
                except ProtocolError as error:
                    reply = response(error.request_id, error.status, error.reason)
                    await send({"type": "websocket.send",
                                "text": encode_response(reply)})
                    continue

                context = connection_context
                if request["operation"] in {"voice.offer", "voice.update"}:
                    try:
                        context = await self._request_context(
                            context_provider, scope, request)
                    except Exception:
                        safe = response(request["request_id"], "unavailable",
                                        "authority_unavailable")
                        await send({"type": "websocket.send",
                                    "text": encode_response(safe)})
                        continue
                    if not self._same_connection_binding(connection_context, context):
                        safe = response(request["request_id"], "denied", "not_authorized")
                        await send({"type": "websocket.send",
                                    "text": encode_response(safe)})
                        continue
                    if type(context.ticket_id) is not str or not context.ticket_id:
                        safe = response(request["request_id"], "denied", "not_authorized")
                        await send({"type": "websocket.send",
                                    "text": encode_response(safe)})
                        continue

                try:
                    reply = await self._dispatch(service, raw, context)
                    if (type(reply) is not dict
                            or reply.get("request_id") != request["request_id"]):
                        raise ValueError("invalid service response")
                    text = encode_response(reply, operation=request["operation"])
                except Exception:
                    # Keep adapter errors content-free, including failures in
                    # fake or future injected implementations.
                    safe = response(request["request_id"], "unavailable",
                                    "authority_unavailable")
                    text = encode_response(safe)
                await send({"type": "websocket.send", "text": text})
        except Exception:
            # Never send adapter/service exception text to the remote caller.
            await self._close(send, _CLOSE_INTERNAL)
        finally:
            # The adapter retains no per-connection registry. R3.9 revalidates
            # this server-injected binding on each request; disconnect does
            # not fabricate a phone session-signout or synthesize a ticket.
            connection_context = None


def create_phone_remote_asgi(service=None, context_provider=None, *, enabled=False):
    """Construct the offline ASGI adapter from server-owned injected values."""
    return PhoneRemoteASGI(service, context_provider, enabled=enabled)


class PhoneRemoteConnectionASGI(PhoneRemoteASGI):
    """Unmounted proof handshake; no scope/context-provider authority is used."""
    def __init__(self, host=None, *, enabled=False):
        from jarvis.bot.phone_remote_service import _AuthorityChildServiceHost
        from jarvis.bot.phone_remote_connection import ConnectionRegistry
        super().__init__(enabled=enabled)
        self._host = host if (type(host) is _AuthorityChildServiceHost
            and type(getattr(host, "_connections", None)) is ConnectionRegistry
            and host._connections.host is host) else None

    async def __call__(self, scope, receive, send):
        from dataclasses import asdict
        from jarvis.bot.phone_remote_connection import (
            CONNECTION_PROTOCOL, ConnectionFailure, ConnectionLease, ConnectionReply,
            HandshakeError, parse_handshake, decode_proof, handshake_response, is_handshake_attempt,
        )
        if type(scope) is not dict:
            return
        if scope.get("type") == "http":
            await self._http_not_found(send)
            return
        if scope.get("type") != "websocket":
            return
        host = self._host
        if scope.get("path") != ASGI_PATH or not self._enabled or host is None:
            await self._close(send, _CLOSE_POLICY)
            return
        lease = None
        token = object()
        reader = timer = sending = None
        pending = asyncio.Queue(maxsize=1)
        closed = False
        close_code = _CLOSE_POLICY
        disconnected = False
        phase = "challenge"
        challenge_request_id = None

        def retire(code=_CLOSE_POLICY, *, disconnect=False):
            nonlocal closed, close_code, disconnected
            closed, close_code = True, code
            disconnected = disconnected or disconnect
            if lease is not None:
                host.close_connection(lease, token)
            if sending is not None and not sending.done():
                sending.cancel()
            while not pending.empty():
                pending.get_nowait()
            pending.put_nowait(None)

        async def send_owned(event, *, terminal=False):
            nonlocal sending
            if closed and not terminal:
                return False
            retained = lease is not None and host._connections.begin_send(lease, token)
            if not retained and not terminal:
                # The owner/lease can retire after reply claim, or between
                # open and accept. Refusal settles this invocation locally;
                # it must not wait for another phone frame to discover closure.
                retire(_CLOSE_INTERNAL)
                return False
            task = monitor = None
            try:
                if retained and retained.is_set():
                    retire()
                    return False
                task = asyncio.create_task(send(event))
                sending = task
                async def watch_owner_retirement():
                    # A registry close can originate on the owner worker. Poll
                    # its existing local Event without consuming an executor
                    # slot or invoking callbacks under registry/service locks.
                    while not task.done():
                        if retained.is_set():
                            retire()
                            return
                        await asyncio.sleep(.01)
                if retained:
                    monitor = asyncio.create_task(watch_owner_retirement())
                await asyncio.shield(task)
                return True
            except asyncio.CancelledError:
                cancelled_by_caller = not closed
                if cancelled_by_caller:
                    retire(disconnect=True)
                if task is not None:
                    task.cancel()
                    while not task.done():
                        try:
                            await asyncio.shield(task)
                        except asyncio.CancelledError:
                            continue
                        except Exception:
                            break
                if cancelled_by_caller:
                    raise
                return False
            finally:
                if monitor is not None:
                    monitor.cancel()
                    while not monitor.done():
                        try:
                            await asyncio.shield(monitor)
                        except asyncio.CancelledError:
                            continue
                    if not monitor.cancelled():
                        monitor.exception()
                if task is not None and task.done() and not task.cancelled():
                    task.exception()
                sending = None
                if retained:
                    host._connections.end_send(lease, token)

        async def owned(function, *args):
            task = asyncio.create_task(self._blocking_call(function, *args))
            try:
                return await asyncio.shield(task)
            except asyncio.CancelledError:
                retire(disconnect=True)
                while not task.done():
                    try:
                        await asyncio.shield(task)
                    except asyncio.CancelledError:
                        continue
                    except Exception:
                        break
                # A cancelled open may have allocated a lease before returning.
                if task.done() and not task.cancelled():
                    try:
                        value = task.result()
                        if type(value) is ConnectionLease:
                            host.close_connection(value, token)
                    except Exception:
                        pass
                raise

        async def read_frames():
            try:
                while True:
                    event = await receive()
                    if type(event) is not dict:
                        retire()
                        return
                    if event.get("type") == "websocket.disconnect":
                        retire(disconnect=True)
                        return
                    if closed:
                        retire(close_code)
                        return
                    if event.get("type") != "websocket.receive":
                        retire()
                        return
                    text, data = event.get("text"), event.get("bytes")
                    raw = text if type(text) is str and data is None else data if type(data) is bytes and text is None else None
                    try:
                        size = len(raw.encode("utf-8", "strict")) if type(raw) is str else len(raw) if type(raw) is bytes else 0
                    except UnicodeError:
                        size = 0
                    if size == 0 or size > (1_048_576 if phase == "active" else 8192) or pending.full():
                        retire()
                        return
                    pending.put_nowait(raw)
            except asyncio.CancelledError:
                raise
            except Exception:
                retire(_CLOSE_INTERNAL)

        async def fail(rid, reason, *, handshake):
            if closed:
                return
            wire = (handshake_response(rid, reason=reason) if handshake else
                    encode_response(response(rid, "denied" if reason in {"not_authorized", "invalid_request"} else "unavailable",
                        "not_authorized" if reason in {"not_authorized", "invalid_request"} else "authority_unavailable")))
            if not await send_owned({"type": "websocket.send", "text": wire}):
                return
            retire(_CLOSE_INTERNAL if reason == "authority_unavailable" else _CLOSE_POLICY)

        try:
            first = await receive()
            if type(first) is not dict or first.get("type") != "websocket.connect":
                return
            lease = await owned(host.open_connection, token)
            if type(lease) is not ConnectionLease:
                lease = None
                await self._close(send, _CLOSE_POLICY)
                return
            epoch, deadline = host._connections.timer(lease, token)
            loop = asyncio.get_running_loop()

            def timeout():
                # Cancellation of the TimerHandle alone cannot revoke a callback
                # that is already queued. Epoch/state arbitration owns that race.
                if host._connections.expire_handshake(lease, token, epoch):
                    retire(_CLOSE_INTERNAL)

            import time
            timer = loop.call_later(max(0, deadline - time.monotonic()), timeout)
            reader = asyncio.create_task(read_frames())
            if not await send_owned({"type": "websocket.accept"}):
                retire(close_code)
            while not closed:
                raw = await pending.get()
                if raw is None or closed:
                    break
                if phase != "active":
                    try:
                        request = parse_handshake(raw)
                    except HandshakeError as exc:
                        await fail(exc.request_id, "invalid_request", handshake=True)
                        break
                    rid = request["request_id"]
                    expected = "auth.challenge" if phase == "challenge" else "auth.prove"
                    if request["operation"] != expected or rid == challenge_request_id:
                        await fail(rid, "invalid_request", handshake=True)
                        break
                    payload = request["payload"]
                    if phase == "challenge":
                        result = await owned(host.connection_challenge, lease, token,
                                             payload["device_id"], payload["grant_id"])
                        if closed:
                            break
                        if type(result) is ConnectionFailure:
                            await fail(rid, result.reason, handshake=True)
                            break
                        wire = handshake_response(rid, payload=asdict(result))
                        challenge_request_id = rid
                        phase = "proof"
                    else:
                        result = await owned(host.connection_prove, lease, token,
                                             payload["challenge_id"], decode_proof(payload["proof"]))
                        if closed:
                            break
                        if result is not True:
                            await fail(rid, result.reason if type(result) is ConnectionFailure else "authority_unavailable", handshake=True)
                            break
                        result = await owned(host.activate_connection, lease, token, rid)
                        if closed:
                            break
                        if type(result) is not ConnectionReply:
                            await fail(rid, result.reason if type(result) is ConnectionFailure else "authority_unavailable", handshake=True)
                            break
                        timer.cancel()
                        phase = "active"
                        wire = await owned(host.claim_connection_reply, lease, token, result)
                        if type(wire) is ConnectionFailure:
                            await fail(rid, wire.reason, handshake=True)
                            break
                else:
                    # No authentication envelope is a business request/downgrade.
                    if is_handshake_attempt(raw):
                        retire()
                        break
                    try:
                        request = parse_request(raw)
                    except ProtocolError as exc:
                        wire = encode_response(response(exc.request_id, exc.status, exc.reason))
                    else:
                        result = await owned(host.handle_connection, lease, token, raw)
                        if closed:
                            break
                        if type(result) is not ConnectionReply:
                            await fail(request["request_id"], result.reason if type(result) is ConnectionFailure else "authority_unavailable", handshake=False)
                            break
                        wire = await owned(host.claim_connection_reply, lease, token, result)
                        if type(wire) is ConnectionFailure:
                            await fail(request["request_id"], wire.reason, handshake=False)
                            break
                if not closed and not await send_owned({"type": "websocket.send", "text": wire}):
                    break
            if not disconnected:
                await send_owned({"type": "websocket.close", "code": close_code}, terminal=True)
        except asyncio.CancelledError:
            retire(disconnect=True)
            raise
        except Exception:
            retire(_CLOSE_INTERNAL)
            if not disconnected:
                await send_owned({"type": "websocket.close", "code": _CLOSE_INTERNAL}, terminal=True)
        finally:
            if timer is not None:
                timer.cancel()
            if lease is not None:
                host.close_connection(lease, token)
            if reader is not None:
                reader.cancel()
                while not reader.done():
                    try:
                        await asyncio.shield(reader)
                    except asyncio.CancelledError:
                        continue
                    except Exception:
                        break
                if not reader.cancelled():
                    reader.exception()


def create_phone_remote_connection_asgi(host=None, *, enabled=False):
    return PhoneRemoteConnectionASGI(host, enabled=enabled)
