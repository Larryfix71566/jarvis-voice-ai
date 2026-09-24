"""Send a session's connect greeting once, after the pipeline has started.

pipecat fires the transport's ``on_client_connected`` before the StartFrame
has travelled the pipeline, and a context frame pushed then is dropped
("LLMUserAggregator ... StartFrame not received yet"). That happened on every
connect in the production log from 2026-09-11 onward: the greeting note
stayed in the context but triggered no reply, so Mortimer only greeted once
the user spoke. The greeting now waits for BOTH events, in either order.
"""
from __future__ import annotations

import asyncio
from typing import Awaitable, Callable


class ConnectGreeting:
    def __init__(self, send: Callable[[], Awaitable[None]]) -> None:
        self._send = send
        self._connected = False
        self._started = False
        self._sent = False
        self._lock = asyncio.Lock()

    @property
    def sent(self) -> bool:
        return self._sent

    async def client_connected(self) -> None:
        self._connected = True
        await self._maybe_send()

    async def pipeline_started(self) -> None:
        self._started = True
        await self._maybe_send()

    async def _maybe_send(self) -> None:
        async with self._lock:
            if self._connected and self._started and not self._sent:
                self._sent = True          # once per session, even if send raises
                await self._send()
