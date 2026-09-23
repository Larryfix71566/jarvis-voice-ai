"""Session state for the Command Console protocol.

This module is intentionally transport-neutral. It owns generations, stale
revision rejection and duplicate request replay; the UI and the Supervisor
remain clients of the same deterministic state machine.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from time import monotonic
from typing import Any, Callable
import uuid

from jarvis.bot.console_protocol import response, validate_request


@dataclass
class ConsoleSession:
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    generation: str = field(default_factory=lambda: str(uuid.uuid4()))
    revision: int = 0
    # The protocol contract is deliberately bounded: replay is useful for a
    # short reconnect window, but an unbounded request cache would turn a long
    # lived voice session into a memory sink.  Keep the insertion time beside
    # each response so pruning is deterministic and independent of payload
    # contents.
    _responses: "OrderedDict[str, tuple[float, dict[str, Any]]]" = field(
        default_factory=OrderedDict, repr=False
    )
    response_cache_limit: int = 128
    response_cache_ttl_s: float = 300.0
    _clock: Callable[[], float] = field(default=monotonic, repr=False, compare=False)
    _inventory: dict[str, Any] | None = field(default=None, repr=False)

    @property
    def inventory(self) -> dict[str, Any] | None:
        """The latest bounded snapshot supplied by the native client."""
        return self._inventory

    def update_inventory(self, inventory: dict[str, Any]) -> None:
        """Replace the native snapshot without mutating request replay state."""
        self._inventory = dict(inventory)
        revision = inventory.get("revision")
        if isinstance(revision, int) and not isinstance(revision, bool) and revision >= 0:
            self.revision = revision

    def rotate_generation(self) -> str:
        self.generation = str(uuid.uuid4())
        self.revision += 1
        self._responses.clear()
        return self.generation

    def _prune_responses(self, now: float) -> None:
        expired = [
            request_id for request_id, (created, _)
            in self._responses.items()
            if now - created >= self.response_cache_ttl_s
        ]
        for request_id in expired:
            self._responses.pop(request_id, None)
        while len(self._responses) > self.response_cache_limit:
            self._responses.popitem(last=False)

    def accept(self, message: dict[str, Any], *, inventory: Callable[[], dict],
               apply: Callable[[dict], tuple[str, str]] | None = None) -> dict[str, Any]:
        now = self._clock()
        self._prune_responses(now)
        try:
            request = validate_request(message)
        except ValueError as exc:
            # Malformed requests have no trustworthy request id; callers get a
            # plain error object suitable for diagnostics and no state change.
            return {"type": "console/result", "version": 1, "status": "error",
                    "code": "invalid_request", "summary": str(exc)[:240]}
        request_id = request["request_id"]
        cached = self._responses.get(request_id)
        if cached is not None:
            return cached[1]
        if request["session_id"] != self.session_id or request["generation"] != self.generation:
            result = response(request_id=request_id, session_id=self.session_id,
                              generation=self.generation, status="error",
                              code="stale_session", summary="This console session is no longer current.")
        elif request["revision"] != self.revision:
            result = response(request_id=request_id, session_id=self.session_id,
                              generation=self.generation, status="error",
                              code="stale_selection", summary="The console changed; please choose the item again.")
        else:
            current_inventory = self._inventory if self._inventory is not None else inventory()
            if not isinstance(current_inventory, dict):
                result = response(request_id=request_id, session_id=self.session_id,
                                  generation=self.generation, status="error",
                                  code="inventory_unavailable", summary="Console inventory is unavailable.")
            elif request["action"] == "inventory":
                result = response(request_id=request_id, session_id=self.session_id,
                                  generation=self.generation, status="ok", code="inventory",
                                  summary="Console inventory ready.") | {"data": current_inventory}
            elif apply is None:
                result = response(request_id=request_id, session_id=self.session_id,
                                  generation=self.generation, status="unsupported", code="not_wired",
                                  summary="That console action is not available yet.")
            else:
                status, summary = apply(request)
                result = response(request_id=request_id, session_id=self.session_id,
                                  generation=self.generation, status=status, code=status, summary=summary)
        self._responses[request_id] = (now, result)
        self._prune_responses(now)
        return result
