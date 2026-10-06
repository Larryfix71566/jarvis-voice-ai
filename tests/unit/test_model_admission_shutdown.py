import asyncio
import threading

import pytest

from jarvis.model_execution import ModelAdmissionController


@pytest.mark.parametrize('priority', ['interactive', 'background'])
def test_actual_loop_shutdown_releases_grant_without_async_delivery(priority):
    controller = ModelAdmissionController()
    entered, release = threading.Event(), threading.Event()
    captured, owners, body, errors = [], [], [], []
    original = controller._acquire

    def held_acquire(requested, cancelled):
        acquired = original(requested, cancelled)
        assert acquired is True
        captured.append(cancelled)
        entered.set()
        assert release.wait(3)
        return acquired

    controller._acquire = held_acquire

    def release_after_real_owner_cancellation():
        try:
            assert entered.wait(3)
            assert captured[0].wait(3)
        except BaseException as exc:
            errors.append(exc)
        finally:
            release.set()

    async def main():
        async def use():
            async with controller.slot(priority):
                body.append(True)
        owners.append(asyncio.create_task(use()))
        assert await asyncio.to_thread(entered.wait, 3)
        expected = (1, 0) if priority == 'interactive' else (0, 1)
        assert controller.active_counts == expected
        # Returning invokes real asyncio.run cancellation of BOTH the owner
        # and the pending asyncio.to_thread delivery task, then executor drain.

    monitor = threading.Thread(target=release_after_real_owner_cancellation)
    monitor.start()
    try:
        asyncio.run(main())
    finally:
        release.set()
        monitor.join(3)
    assert not monitor.is_alive() and errors == []
    assert owners[0].cancelled() and body == []
    assert controller.active_counts == (0, 0)
