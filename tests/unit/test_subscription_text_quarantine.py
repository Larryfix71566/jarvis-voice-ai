"""Real text-owner guards with inert runners: no provider process starts."""
import asyncio
import threading
from types import SimpleNamespace

import pytest

from jarvis import subscription as S


@pytest.mark.parametrize('client_type,runner', [
    (S.SubscriptionTextClient, '_run_claude_response_async'),
    (S.CodexSubscriptionTextClient, '_run_codex_response_async'),
])
async def test_active_and_later_calls_cannot_publish_after_owner_cleanup_failure(monkeypatch, client_type, runner):
    entered, fail, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    calls = []
    async def inert(*args):
        calls.append(args)
        if len(calls) == 1:
            await fail.wait()
            raise S.SubscriptionRuntimeError('PRIVATE_CLEANUP_CANARY', category='cleanup')
        entered.set()
        await release.wait()
        return SimpleNamespace(text='PRIVATE_LATE_RESULT_CANARY')
    monkeypatch.setattr(S, runner, inert)
    client = client_type('fixture')
    first = asyncio.create_task(client.chat.completions.create(messages=[]))
    second = asyncio.create_task(client.chat.completions.create(messages=[]))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        fail.set()
        with pytest.raises(S.SubscriptionRuntimeError) as failure:
            await first
        assert failure.value.category == 'cleanup' and client.cleanup_unverified
        release.set()
        with pytest.raises(S.SubscriptionRuntimeError) as suppressed:
            await second
        assert suppressed.value.category == 'cleanup'
        assert 'PRIVATE_LATE_RESULT' not in str(suppressed.value)
        with pytest.raises(S.SubscriptionRuntimeError):
            await client.chat.completions.create(messages=[])
        assert len(calls) == 2
    finally:
        for task in (first, second):
            if not task.done():
                task.cancel()
        await asyncio.gather(first, second, return_exceptions=True)


@pytest.mark.parametrize('client_type,runner', [
    (S.SubscriptionSyncTextClient, '_run_claude_response'),
    (S.CodexSubscriptionSyncTextClient, '_run_codex_response'),
])
def test_sync_native_owner_retains_failure_and_refuses_reuse(monkeypatch, client_type, runner):
    calls = []
    def inert(*args):
        calls.append(args)
        raise S.SubscriptionRuntimeError('PRIVATE_CLEANUP_CANARY', category='cleanup')
    monkeypatch.setattr(S, runner, inert)
    client = client_type('fixture')
    for _ in range(2):
        with pytest.raises(S.SubscriptionRuntimeError) as failure:
            client.chat.completions.create(messages=[])
        assert failure.value.category == 'cleanup'
    assert client.cleanup_unverified and len(calls) == 1


async def test_codex_receipt_wait_cannot_launch_after_quarantine(monkeypatch):
    waiting, release = threading.Event(), threading.Event()
    def receipt(_model):
        waiting.set()
        assert release.wait(2)
        return ['inert-never-start'], {}
    async def forbidden(*args, **kwargs):
        pytest.fail('quarantined owner must not create a provider subprocess')
    monkeypatch.setenv(S._CODEX_NO_TOOL_VERIFICATION_ENV, '1')
    monkeypatch.setattr(S, 'validate_codex_capability_receipt', receipt)
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', forbidden)
    client = S.CodexSubscriptionTextClient('fixture')
    call = asyncio.create_task(client.chat.completions.create(messages=[]))
    try:
        assert await asyncio.to_thread(waiting.wait, 2)
        client.chat.completions.cleanup_unverified = True
        release.set()
        with pytest.raises(S.SubscriptionRuntimeError) as failure:
            await asyncio.wait_for(call, 2)
        assert failure.value.category == 'cleanup'
    finally:
        release.set()
        if not call.done():
            call.cancel()
        await asyncio.gather(call, return_exceptions=True)


@pytest.mark.parametrize('client_type,runner', [
    (S.SubscriptionTextClient, '_run_claude_response_async'),
    (S.CodexSubscriptionTextClient, '_run_codex_response_async'),
])
async def test_normalized_auth_failure_does_not_claim_unverified_cleanup(monkeypatch, client_type, runner):
    async def refused(*args):
        raise S.SubscriptionRuntimeError('not signed in', category='authentication')
    monkeypatch.setattr(S, runner, refused)
    client = client_type('fixture')
    with pytest.raises(S.SubscriptionRuntimeError):
        await client.chat.completions.create(messages=[])
    assert not client.cleanup_unverified
