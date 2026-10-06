import asyncio
import threading
import pytest
from jarvis.model_execution import ModelAdmissionController

@pytest.mark.parametrize("priority",["interactive","background"])
async def test_actual_delivered_lease_survives_double_cancel_cleanup(priority):
    controller=ModelAdmissionController()
    entered,release,returned=threading.Event(),threading.Event(),threading.Event()
    captured=[]
    original=controller._acquire
    def hold_after_real_lease(requested,cancelled):
        acquired=original(requested,cancelled)
        captured.append((acquired,cancelled))
        assert acquired is True
        entered.set()
        assert release.wait(3)
        returned.set()
        return acquired
    controller._acquire=hold_after_real_lease
    body=[]
    async def use():
        async with controller.slot(priority):
            body.append(True)
    before=set(asyncio.all_tasks())
    owner=asyncio.create_task(use())
    try:
        assert await asyncio.to_thread(entered.wait,2)
        expected=(1,0) if priority=="interactive" else (0,1)
        assert controller.active_counts==expected
        owner.cancel()
        assert await asyncio.to_thread(captured[0][1].wait,2)
        owner.cancel()
    finally:
        release.set()
        pending=[task for task in asyncio.all_tasks() if task not in before]
        await asyncio.wait_for(asyncio.gather(*pending,return_exceptions=True),2)
    assert returned.is_set() and owner.cancelled() and body==[]
    assert controller.active_counts==(0,0),("real lease leaked after two cancellations",priority,controller.active_counts)
