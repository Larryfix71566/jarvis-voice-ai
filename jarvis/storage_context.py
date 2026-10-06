"""Host-owned diagnostic stores and the lifetime of their bounded workers.

This context changes no process environment, persisted policy or allowance.
Ordinary callers retain their existing paths and asyncio executor behavior.
"""
from __future__ import annotations

import asyncio
from concurrent.futures import Future
from contextlib import asynccontextmanager
from contextvars import ContextVar, copy_context
from dataclasses import dataclass
from functools import partial
import math
from pathlib import Path
import queue
import threading
import time


class StorageScopeUnavailable(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class _Paths:
    db: Path
    costs: Path
    preferences: bool


_current = ContextVar('mortimer_storage_scope', default=None)
_worker = ContextVar('mortimer_storage_worker', default=None)
_quarantined = set()
_quarantine_lock = threading.Lock()


class _Scope:
    def __init__(self, paths, cleanup):
        self.paths, self._cleanup = paths, cleanup
        self._lock = threading.Lock()
        self._queue = queue.Queue()
        self._threads = []
        self._futures = []
        self._closing = self._retired = False
        self._cleanup_claimed = False
        self.cleanup_verified = False
        self.cleanup_duration_ms = 0.0
        self.cleanup_error = None

    def assert_active(self):
        with self._lock:
            if self._retired or (self._closing and _worker.get() is not self):
                raise StorageScopeUnavailable('storage_scope_closed')

    @property
    def pending_workers(self):
        with self._lock:
            return sum(not future.done() for future in self._futures)

    def submit(self, fn, args, kwargs):
        context = copy_context()
        operation = partial(fn, *args, **kwargs)
        future = Future()
        with self._lock:
            if self._closing or self._retired:
                raise StorageScopeUnavailable('storage_scope_closed')
            self._futures.append(future)
            self._queue.put((future, context, operation))
            if len(self._threads) < 2:
                thread = threading.Thread(target=self._run, daemon=True,
                                          name='mortimer-isolated-store')
                self._threads.append(thread)
                thread.start()
        return future

    def _run(self):
        while True:
            item = self._queue.get()
            if item is None:
                return
            future, context, operation = item
            if not future.set_running_or_notify_cancel():
                continue
            def invoke():
                token = _worker.set(self)
                try:
                    return operation()
                finally:
                    _worker.reset(token)
            try:
                result = context.run(invoke)
            except BaseException as exc:
                future.set_exception(exc)
            else:
                future.set_result(result)

    def close_submissions(self):
        with self._lock:
            self._closing = True
            futures = tuple(self._futures)
            threads = tuple(self._threads)
        # A queued call can be cancelled; an admitted running call remains
        # owned until its actual concurrent future finishes.
        for future in futures:
            future.cancel()
        for _ in threads:
            self._queue.put(None)
        return futures

    def _delete(self):
        if self._cleanup is not None:
            try:
                self._cleanup()
            except BaseException:
                self.cleanup_error = 'storage_cleanup_failed'
                with _quarantine_lock:
                    _quarantined.add(self)
                raise StorageScopeUnavailable('storage_cleanup_failed') from None

    def quarantine(self, futures):
        with _quarantine_lock:
            _quarantined.add(self)
        def completed(_):
            with self._lock:
                if self._cleanup_claimed or any(not future.done() for future in futures):
                    return
                self._cleanup_claimed = True
                cleanup, self._cleanup = self._cleanup, None
            try:
                if cleanup is not None:
                    cleanup()
            except BaseException:
                # Retain the failed cleanup owner/evidence. No retry or raw
                # exception content is exposed as successful cleanup.
                self.cleanup_error = 'storage_cleanup_failed'
                self._failed_cleanup = cleanup
            else:
                with _quarantine_lock:
                    _quarantined.discard(self)
        for future in futures:
            future.add_done_callback(completed)
        completed(None)


def assert_storage_scope_active():
    scope = _current.get()
    if scope is not None:
        scope.assert_active()


def database_path(default):
    scope = _current.get()
    if scope is None:
        return default
    scope.assert_active()
    return scope.paths.db


def costs_path(default):
    scope = _current.get()
    if scope is None:
        return default
    scope.assert_active()
    return scope.paths.costs


def preferences_enabled(default):
    scope = _current.get()
    if scope is None:
        return default
    scope.assert_active()
    return scope.paths.preferences


async def state_to_thread(fn, /, *args, **kwargs):
    scope = _current.get()
    if scope is None:
        return await asyncio.to_thread(fn, *args, **kwargs)
    future = scope.submit(fn, args, kwargs)
    return await asyncio.wrap_future(future)


@asynccontextmanager
async def storage_scope(*, db_path, costs_db_path, model_preferences_enabled=False,
                        drain_timeout_s=10.0, cleanup=None):
    """Retire only after draining; quarantine private stores on finite expiry.

    Callbacks run once after actual workers finish. They must own only the
    supplied private stores. Running work must close its own connections.
    """
    if (type(model_preferences_enabled) is not bool
            or type(drain_timeout_s) not in {int, float}
            or not math.isfinite(drain_timeout_s) or drain_timeout_s <= 0):
        raise ValueError('invalid storage scope')
    paths = _Paths(Path(db_path), Path(costs_db_path), model_preferences_enabled)
    if not paths.db.is_absolute() or not paths.costs.is_absolute():
        raise ValueError('storage scope paths must be absolute')
    scope = _Scope(paths, cleanup)
    token = _current.set(scope)
    try:
        yield scope
    finally:
        started = time.monotonic()
        futures = scope.close_submissions()
        async def drain():
            waiting = [asyncio.wrap_future(future) for future in futures if not future.done()]
            if waiting:
                done, pending = await asyncio.wait(waiting, timeout=drain_timeout_s)
                for completed in done:
                    if not completed.cancelled():
                        completed.exception()
                for remaining in pending:
                    remaining.cancel()
            return all(future.done() for future in futures)
        operation = asyncio.create_task(drain())
        cancelled = False
        try:
            while True:
                try:
                    verified = await asyncio.shield(operation)
                    break
                except asyncio.CancelledError:
                    cancelled = True
                    if operation.done():
                        # Loop shutdown can cancel the private drain task as
                        # well as its caller. Re-awaiting it would spin forever.
                        verified = all(future.done() for future in futures)
                        break
        finally:
            with scope._lock:
                scope._retired = True
            _current.reset(token)
            scope.cleanup_duration_ms = (time.monotonic() - started) * 1000
        if not verified:
            scope.cleanup_error = 'storage_cleanup_unverified'
            scope.quarantine(futures)
            raise StorageScopeUnavailable('storage_cleanup_unverified')
        try:
            scope._delete()
        finally:
            scope.cleanup_duration_ms = (time.monotonic() - started) * 1000
        scope.cleanup_verified = True
        if cancelled:
            raise asyncio.CancelledError()
