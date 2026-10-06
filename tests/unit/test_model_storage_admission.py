"""Queued capacity waits cannot starve an admitted task's private DB work."""
import asyncio
from pathlib import Path

import pytest

from jarvis import db
from jarvis.model_execution import ModelAdmissionController
from jarvis.storage_context import state_to_thread, storage_scope


async def test_queued_admission_does_not_occupy_private_storage_workers(tmp_path):
    controller = ModelAdmissionController()
    waiters = []

    async def waiting_call():
        async with controller.slot('background'):
            pytest.fail('queued background call started while its slot was occupied')

    def actual_database_path():
        connection = db.get_conn()
        try:
            connection.execute('SELECT 1')
            return Path(connection.execute('PRAGMA database_list').fetchone()[2])
        finally:
            connection.close()

    async with storage_scope(db_path=tmp_path / 'pilot.db',
                             costs_db_path=tmp_path / 'costs.db'):
        async with controller.slot('background'):
            try:
                waiters = [asyncio.create_task(waiting_call()) for _ in range(2)]
                async with asyncio.timeout(5):
                    while True:
                        with controller._condition:
                            registered = len(controller._waiters)
                        if registered == 2:
                            break
                        await asyncio.sleep(0.001)
                # Both waits are causally registered before real DB work.
                # Putting them in the two-worker storage pool deadlocks this.
                path = await asyncio.wait_for(state_to_thread(actual_database_path), 5)
                assert path == tmp_path / 'pilot.db'
                assert controller.active_counts == (0, 1)
            finally:
                for waiter in waiters:
                    waiter.cancel()
                await asyncio.gather(*waiters, return_exceptions=True)
    assert controller.active_counts == (0, 0)
