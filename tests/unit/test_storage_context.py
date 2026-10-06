"""Real store/worker lifetimes without providers, global path lending or sleeps."""
import asyncio
from contextlib import closing
from contextvars import ContextVar, copy_context
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading

import pytest

from jarvis import db, model_routing, usage_ledger
from jarvis.storage_context import (
    StorageScopeUnavailable, costs_path, database_path, preferences_enabled,
    state_to_thread, storage_scope,
)
from jarvis.tenant import current_user_id, user_id_scope


def paths(root):
    return dict(db_path=root / 'jarvis.db', costs_db_path=root / 'costs.db')


async def test_scope_paths_real_connections_explicit_precedence_preferences_and_legacy(tmp_path, monkeypatch):
    outside = tmp_path / 'outside.db'
    costs = tmp_path / 'outside-costs.db'
    explicit = tmp_path / 'explicit.db'
    monkeypatch.setenv('JARVIS_DB_PATH', str(outside))
    monkeypatch.setenv('JARVIS_MODEL_PREFERENCES_ENABLED', '1')
    monkeypatch.setattr(usage_ledger, 'DB_PATH', costs)
    environment = dict(os.environ)
    with closing(db.get_conn(explicit)) as conn:
        assert Path(conn.execute('PRAGMA database_list').fetchone()[2]) == explicit
    scope_paths = paths(tmp_path / 'owned')
    async with storage_scope(**scope_paths):
        assert preferences_enabled(True) is False
        assert db._default_db_path() == scope_paths['db_path']
        with closing(db.get_conn(explicit)) as conn:
            assert Path(conn.execute('PRAGMA database_list').fetchone()[2]) == explicit
        with closing(db.get_conn()) as conn:
            assert Path(conn.execute('PRAGMA database_list').fetchone()[2]) == scope_paths['db_path']
        assert usage_ledger.existing_model_budget_connection() is None
        with closing(usage_ledger.model_budget_connection()) as conn:
            assert Path(conn.execute('PRAGMA database_list').fetchone()[2]) == scope_paths['costs_db_path']
            assert conn.execute('SELECT COUNT(*) FROM llm_calls').fetchone() == (0,)
        with closing(usage_ledger.existing_model_budget_connection()) as conn:
            assert Path(conn.execute('PRAGMA database_list').fetchone()[2]) == scope_paths['costs_db_path']
        monkeypatch.setattr('jarvis.model_preferences.list_preferences', lambda: pytest.fail('saved preference read'))
        assert model_routing.resolve_policy('developer').profile == 'claude-opus'
        assert dict(os.environ) == environment
    assert db._default_db_path() == outside and costs_path(costs) == costs
    assert preferences_enabled(True) is True
    assert not outside.exists() and not costs.exists()


async def test_concurrent_and_nested_contexts_copy_full_caller_identity(tmp_path):
    source = ContextVar('test_source_owner')
    entered = asyncio.Event()
    release = asyncio.Event()
    both_entered = set()
    async def operation(name):
        with user_id_scope(name):
            token = source.set(name + '-source')
            try:
                async with storage_scope(**paths(tmp_path / name)) as outer:
                    first = await state_to_thread(lambda: (current_user_id(), source.get(), db._default_db_path()))
                    async with storage_scope(**paths(tmp_path / (name + '-nested'))):
                        assert await state_to_thread(db._default_db_path) == tmp_path / (name + '-nested') / 'jarvis.db'
                    assert db._default_db_path() == outer.paths.db
                    both_entered.add(name)
                    if len(both_entered) == 2:
                        entered.set()
                    await release.wait()
                    second = await state_to_thread(lambda: (current_user_id(), source.get(), db._default_db_path()))
                    return first, second
            finally:
                source.reset(token)
    tasks = [asyncio.create_task(operation(name)) for name in ('alice', 'bob')]
    await asyncio.wait_for(entered.wait(), 2)
    release.set()
    results = await asyncio.gather(*tasks)
    for name, (first, second) in zip(('alice', 'bob'), results):
        assert first == second == (name, name + '-source', tmp_path / name / 'jarvis.db')


async def test_retired_copied_context_refuses_all_store_readers_and_explicit_connection(tmp_path):
    async with storage_scope(**paths(tmp_path / 'owned')):
        copied = copy_context()
    for operation in (
        lambda: database_path(tmp_path / 'outside.db'),
        lambda: costs_path(tmp_path / 'outside-costs.db'),
        lambda: preferences_enabled(True),
        lambda: db.get_conn(tmp_path / 'explicit.db'),
        usage_ledger._conn, usage_ledger.existing_model_budget_connection,
    ):
        with pytest.raises(StorageScopeUnavailable, match='storage_scope_closed'):
            copied.run(operation)
    assert not (tmp_path / 'explicit.db').exists()


@pytest.mark.parametrize('cancel', [False, True])
async def test_held_real_sql_worker_drains_before_delete_on_timeout_and_cancel(tmp_path, monkeypatch, cancel):
    root = tmp_path / 'owned'; root.mkdir()
    entered, release, written = threading.Event(), threading.Event(), threading.Event()
    closing = asyncio.Event()
    cancellable = asyncio.Event()
    deleted = []
    real_connect = sqlite3.connect
    def connect(path, *args, **kwargs):
        if Path(path) == root / 'jarvis.db':
            entered.set()
            assert release.wait(3)
        return real_connect(path, *args, **kwargs)
    monkeypatch.setattr(sqlite3, 'connect', connect)
    def write():
        with closing_connection(db.get_conn()) as conn:
            conn.execute('CREATE TABLE public_fixture(value INTEGER)')
            conn.commit()
        written.set()
    def cleanup():
        assert written.is_set()
        for item in root.iterdir(): item.unlink()
        root.rmdir(); deleted.append(True)
    async def operation():
        async with storage_scope(**paths(root), cleanup=cleanup, drain_timeout_s=2):
            worker = asyncio.create_task(state_to_thread(write))
            assert await asyncio.to_thread(entered.wait, 2)
            try:
                if cancel:
                    cancellable.set()
                    await worker
                else:
                    with pytest.raises(TimeoutError):
                        await asyncio.wait_for(worker, .01)
            finally:
                closing.set()
    task = asyncio.create_task(operation())
    if cancel:
        await asyncio.wait_for(cancellable.wait(), 2)
        task.cancel()
    await asyncio.wait_for(closing.wait(), 2)
    assert root.exists() and not task.done() and not deleted
    release.set()
    if cancel:
        with pytest.raises(asyncio.CancelledError): await task
    else:
        await task
    assert written.is_set() and deleted == [True] and not root.exists()


closing_connection = closing


async def test_finite_drain_quarantines_until_actual_worker_finishes_and_daemon_does_not_hold_exit(tmp_path):
    root = tmp_path / 'owned'; root.mkdir()
    entered, release, cleaned = threading.Event(), threading.Event(), threading.Event()
    def work():
        entered.set()
        assert release.wait(3)
    def cleanup():
        root.rmdir(); cleaned.set()
    try:
        with pytest.raises(StorageScopeUnavailable, match='storage_cleanup_unverified'):
            async with storage_scope(**paths(root), cleanup=cleanup, drain_timeout_s=.01) as scope:
                task = asyncio.create_task(state_to_thread(work))
                assert await asyncio.to_thread(entered.wait, 2)
                copied = copy_context()
        assert root.exists() and not cleaned.is_set() and not scope.cleanup_verified
        assert scope.cleanup_duration_ms >= 10 and scope.pending_workers == 1
        assert scope._threads and all(thread.daemon for thread in scope._threads)
        with pytest.raises(StorageScopeUnavailable, match='storage_scope_closed'):
            copied.run(db._default_db_path)
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
    assert await asyncio.to_thread(cleaned.wait, 2)
    assert not root.exists()


async def test_foreign_real_sql_worker_does_not_borrow_pilot_path_and_original_spend_assertions_hold(tmp_path, monkeypatch):
    from tests.unit import test_model_use_pilot as original
    outside = tmp_path / 'outside.db'
    monkeypatch.setenv('JARVIS_DB_PATH', str(outside))
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    captured, errors, workers = [], [], []
    real_connect, real_rmdir, real_fake = sqlite3.connect, os.rmdir, original.fake_client
    def connect(path, *args, **kwargs):
        if Path(path) == outside:
            captured.append(Path(path)); entered.set()
            assert release.wait(3)
        return real_connect(path, *args, **kwargs)
    def write():
        try:
            with closing_connection(db.get_conn()) as conn:
                conn.execute('CREATE TABLE foreign_fixture(value INTEGER)'); conn.commit()
        except BaseException as exc: errors.append(type(exc))
        finally: finished.set()
    def client(*args, **kwargs):
        value = real_fake(*args, **kwargs); create = value.chat.completions.create
        async def response(**parameters):
            if not workers:
                assert db._default_db_path() != outside
                worker = threading.Thread(target=write); workers.append(worker); worker.start()
                assert await asyncio.to_thread(entered.wait, 2)
            return await create(**parameters)
        value.chat.completions.create = response
        return value
    def remove(path, *args, **kwargs):
        if 'ws05-pilot-' in str(path):
            release.set(); assert finished.wait(3)
        return real_rmdir(path, *args, **kwargs)
    monkeypatch.setattr(sqlite3, 'connect', connect)
    monkeypatch.setattr(os, 'rmdir', remove)
    monkeypatch.setattr(original, 'fake_client', client)
    try:
        await original.test_live_spend_reservation_stops_before_over_budget_request(monkeypatch)
    finally:
        release.set()
        for worker in workers:
            worker.join(3); assert not worker.is_alive()
    assert captured == [outside] and not errors and outside.exists()


async def test_actual_timed_out_pilot_resolver_drains_real_sql_before_cleanup(tmp_path, monkeypatch):
    from scripts import run_model_use_pilot as pilot
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    closing_scope = asyncio.Event()
    observed = []
    original_resolve = model_routing.resolve_model_route_checked
    original_isolation = pilot.isolated_state
    from contextlib import asynccontextmanager
    @asynccontextmanager
    async def isolation():
        async with original_isolation() as scope:
            close = scope.close_submissions
            def close_submissions():
                closing_scope.set()
                return close()
            scope.close_submissions = close_submissions
            yield scope
    def resolve(*args, **kwargs):
        path = db._default_db_path(); observed.append(path)
        entered.set()
        assert release.wait(3)
        try:
            with closing_connection(db.get_conn()) as conn:
                conn.execute('CREATE TABLE public_resolver_fixture(value INTEGER)'); conn.commit()
            return original_resolve(*args, **kwargs)
        finally:
            finished.set()
    monkeypatch.setattr(pilot, 'isolated_state', isolation)
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'synthetic-unused')
    monkeypatch.setattr(model_routing, 'resolve_model_route_checked', resolve)
    monkeypatch.setattr(model_routing, 'make_route_client', lambda *a, **k: pytest.fail('late route inference'))
    operation = asyncio.create_task(pilot.run_pilot(mode='live', profile='claude-sonnet-5', timeout_s=.01))
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        await asyncio.wait_for(closing_scope.wait(), 2)
        assert not operation.done() and observed[0].parent.exists()
    finally:
        release.set()
    result = await operation
    assert finished.is_set() and not observed[0].parent.exists()
    assert result['storage_cleanup']['verified'] is True
    assert result['provider_requests_attempted'] == 0
    assert all(row['error_category'] == 'TimeoutError' for row in result['trials'])


async def test_cleanup_error_is_fixed_retained_and_not_retried(tmp_path):
    calls = []
    def cleanup():
        calls.append(True)
        raise OSError('PRIVATE_CLEANUP_CANARY')
    with pytest.raises(StorageScopeUnavailable) as error:
        async with storage_scope(**paths(tmp_path), cleanup=cleanup) as scope:
            pass
    assert str(error.value) == 'storage_cleanup_failed'
    assert scope.cleanup_verified is False and scope.cleanup_error == 'storage_cleanup_failed'
    assert calls == [True]


def test_stuck_owned_daemon_worker_cannot_hold_real_process_exit(tmp_path):
    program = '''
import asyncio, threading
from pathlib import Path
from jarvis.storage_context import storage_scope, state_to_thread, StorageScopeUnavailable
async def run():
    entered = threading.Event()
    def stuck():
        entered.set()
        threading.Event().wait()
    try:
        async with storage_scope(db_path=Path('/private/tmp/unused-scope.db'),
                                 costs_db_path=Path('/private/tmp/unused-scope-costs.db'),
                                 drain_timeout_s=.01):
            asyncio.create_task(state_to_thread(stuck))
            assert await asyncio.to_thread(entered.wait, 1)
    except StorageScopeUnavailable as error:
        assert error.code == 'storage_cleanup_unverified'
    else:
        raise AssertionError('stuck work was claimed clean')
asyncio.run(run())
'''
    result = subprocess.run([sys.executable, '-c', program], timeout=3,
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_real_loop_shutdown_cancelling_private_drain_cannot_spin_or_hold_exit():
    program = '''
import asyncio, threading
from pathlib import Path
from jarvis.storage_context import storage_scope, state_to_thread
async def run():
    closing = asyncio.Event()
    async def operation():
        entered = threading.Event()
        def stuck():
            entered.set()
            threading.Event().wait()
        async with storage_scope(db_path=Path('/private/tmp/unused-shutdown.db'),
                                 costs_db_path=Path('/private/tmp/unused-shutdown-costs.db'),
                                 drain_timeout_s=60) as scope:
            close = scope.close_submissions
            def close_submissions():
                closing.set()
                return close()
            scope.close_submissions = close_submissions
            asyncio.create_task(state_to_thread(stuck))
            assert await asyncio.to_thread(entered.wait, 1)
    asyncio.create_task(operation())
    await closing.wait()
asyncio.run(run())
'''
    result = subprocess.run([sys.executable, '-c', program], timeout=3,
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert 'storage_cleanup_unverified' in result.stderr
