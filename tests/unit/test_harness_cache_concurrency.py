"""Deterministic process interleavings; fake documents/selection/notices only."""
import json
import multiprocessing as mp
import socket
import sqlite3
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from jarvis.status import harness as H

NOW = datetime(2026, 10, 22, tzinfo=timezone.utc)


def selection():
    return {"model": "synthetic", "digest": "a" * 64}


def changed_selection():
    return {"model": "synthetic-changed", "digest": "b" * 64}


def seed(path, model="claude-opus-5", now=NOW):
    return H.refresh_report(path, fetch=lambda _: model, selection=selection, now=now)


def raw(path):
    return json.loads((path / H.REPORT_NAME).read_text())


def _deny(*args, **kwargs):
    raise AssertionError("external I/O forbidden in synthetic harness worker")


def _worker(path, mode, reached, proceed, result):
    """Spawn-safe worker: only fake inputs and the supplied temporary directory."""
    socket.socket.connect = socket.socket.connect_ex = _deny
    sqlite3.connect = _deny
    class DeniedPopen(subprocess.Popen):
        def __init__(self, *args, **kwargs):
            _deny()
    subprocess.Popen = DeniedPopen
    path = Path(path)

    def pause():
        reached.set()
        assert proceed.wait(10), "parent did not release deterministic barrier"

    try:
        if mode == "before_passive_read":
            def read_selection():
                pause()
                return selection()
            H.run_passive(status_dir=path, selection=read_selection, now=NOW, notice=lambda *a: 1)
        elif mode == "during_notice":
            def notice(*args):
                pause()
                return 1
            H.run_passive(status_dir=path, selection=changed_selection, now=NOW, notice=notice)
        elif mode == "slow_fetch":
            def fetch(_):
                pause()
                return "claude-fable-5"
            seed_now = NOW - timedelta(hours=1)
            H.refresh_report(path, fetch=fetch, selection=selection, now=seed_now)
        elif mode == "locked_passive_read":
            import fcntl
            original = H._raw
            def read(directory):
                value = original(directory)
                pause()
                return value
            H._raw = read
            publish = H._publish
            def locked_publish(directory, report):
                # Independently prove the committing phase still owns the lock;
                # an unchanged passive run would never exercise this path.
                with (directory / H.LOCK_NAME).open("r+") as lock:
                    with pytest.raises(BlockingIOError):
                        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                publish(directory, report)
            H._publish = locked_publish
            H.run_passive(status_dir=path, selection=changed_selection, now=NOW, notice=lambda *a: -1)
        elif mode == "refresh":
            from contextlib import contextmanager
            writer_lock = H._writer_lock
            @contextmanager
            def entering_lock(directory):
                reached.set()
                with writer_lock(directory):
                    yield
            H._writer_lock = entering_lock
            seed(path, "claude-sonnet-5")
        elif mode == "partial_temp_write":
            from jarvis.status import daily
            def dump(payload, file, **kwargs):
                text = json.dumps(payload, **kwargs)
                middle = len(text) // 2
                file.write(text[:middle])
                file.flush()
                pause()
                file.write(text[middle:])
            daily.json.dump = dump
            seed(path, "claude-sonnet-5")
        else:
            raise AssertionError(mode)
        result.put(None)
    except BaseException as exc:
        result.put(repr(exc))
        raise


@pytest.fixture
def workers():
    context = mp.get_context("spawn")
    running = []
    def start(path, mode):
        reached, proceed, result = context.Event(), context.Event(), context.Queue()
        process = context.Process(target=_worker, args=(str(path), mode, reached, proceed, result))
        process.start()
        running.append((process, proceed, result))
        assert reached.wait(10), "worker did not reach barrier"
        return process, proceed, result
    yield start
    for process, proceed, result in running:
        proceed.set()
        process.join(10)
        if process.is_alive():
            process.terminate()
            process.join(5)
            pytest.fail("worker did not terminate")
        assert process.exitcode == 0, result.get(timeout=2)
        assert result.get(timeout=2) is None
        result.close()


def test_refresh_survives_passive_wait_before_read(tmp_path, workers):
    seed(tmp_path)
    process, proceed, _ = workers(tmp_path, "before_passive_read")
    seed(tmp_path, "claude-sonnet-5")
    expected = raw(tmp_path)
    proceed.set()
    process.join(10)
    assert raw(tmp_path) == expected


def test_late_notice_ack_does_not_overwrite_same_timestamp_refresh(tmp_path, workers):
    seed(tmp_path)
    process, proceed, _ = workers(tmp_path, "during_notice")
    before = raw(tmp_path)
    seed(tmp_path, "claude-sonnet-5")
    expected = raw(tmp_path)
    assert before["generated_at"] == expected["generated_at"]
    assert before["generation"] != expected["generation"]
    proceed.set()
    process.join(10)
    assert raw(tmp_path) == expected


def test_writer_lock_covers_passive_read_through_commit(tmp_path, workers):
    import fcntl
    seed(tmp_path)
    passive, proceed, _ = workers(tmp_path, "locked_passive_read")
    # A separate descriptor cannot acquire the lock while passive holds its
    # captured read. This proves the invariant without a timing-based sleep.
    with (tmp_path / H.LOCK_NAME).open("r+") as lock:
        with pytest.raises(BlockingIOError):
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    refresh, _, _ = workers(tmp_path, "refresh")
    proceed.set()
    passive.join(10)
    refresh.join(10)
    assert raw(tmp_path)["sources"][0]["models"] == ["claude-sonnet-5"]
    assert raw(tmp_path)["configured_selection"]["digest"] == "a" * 64


def test_fetch_does_not_hold_writer_lock_and_last_completion_wins(tmp_path, workers):
    seed(tmp_path)
    slow, proceed, _ = workers(tmp_path, "slow_fetch")
    seed(tmp_path, "claude-sonnet-5")
    assert raw(tmp_path)["sources"][0]["models"] == ["claude-sonnet-5"]
    proceed.set()
    slow.join(10)
    final = raw(tmp_path)
    assert final["sources"][0]["models"] == ["claude-fable-5"]
    assert final["sources"][0]["retrieved_at"] == (NOW - timedelta(hours=1)).isoformat()


def test_legacy_cache_is_readable_and_metadata_upgrade_keeps_source_dates(tmp_path):
    seed(tmp_path, now=NOW - timedelta(days=3))
    old = raw(tmp_path)
    del old["generation"]
    (tmp_path / H.REPORT_NAME).write_text(json.dumps(old))
    assert H.read_report(tmp_path, selection=selection, now=NOW)["freshness"] == "stale"
    H.run_passive(status_dir=tmp_path, selection=selection, now=NOW, notice=lambda *a: 1)
    new = raw(tmp_path)
    assert new["sources"] == old["sources"]
    assert len(new["generation"]) == 32


def test_failed_notice_retries_same_generation_and_ack_keeps_evidence(tmp_path):
    seed(tmp_path)
    H.run_passive(status_dir=tmp_path, selection=changed_selection, now=NOW, notice=lambda *a: -1)
    pending = raw(tmp_path)
    assert pending["notice_pending"] is True
    H.run_passive(status_dir=tmp_path, selection=changed_selection, now=NOW, notice=lambda *a: 1)
    assert raw(tmp_path) == dict(pending, notice_pending=False)


def test_lock_symlink_is_refused_without_changing_report(tmp_path):
    seed(tmp_path)
    before = raw(tmp_path)
    (tmp_path / H.LOCK_NAME).unlink()
    (tmp_path / H.LOCK_NAME).symlink_to(tmp_path / H.REPORT_NAME)
    with pytest.raises(OSError):
        seed(tmp_path, "claude-sonnet-5")
    assert raw(tmp_path) == before


def test_overlapping_passive_acknowledgements_preserve_fresh_generation(tmp_path, workers):
    seed(tmp_path)
    first, release_first, _ = workers(tmp_path, "during_notice")
    second, release_second, _ = workers(tmp_path, "during_notice")
    seed(tmp_path, "claude-sonnet-5")
    expected = raw(tmp_path)
    release_second.set()
    second.join(10)
    release_first.set()
    first.join(10)
    assert raw(tmp_path) == expected


def test_concurrent_readers_only_observe_complete_reports(tmp_path, workers):
    seed(tmp_path)
    before = raw(tmp_path)
    process, proceed, _ = workers(tmp_path, "partial_temp_write")
    # The child is paused with half a JSON document on disk. Readers still
    # see the complete old report because the partial bytes are in a temp file.
    assert raw(tmp_path) == before
    assert H.read_report(tmp_path, selection=selection, now=NOW)["ok"] is True
    proceed.set()
    process.join(10)
    after = raw(tmp_path)
    assert {tuple(s["models"]) for s in after["sources"]} == {("claude-sonnet-5",)}
    assert after["generation"] != before["generation"]
