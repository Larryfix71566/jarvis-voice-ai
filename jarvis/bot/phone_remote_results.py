"""Bounded synthetic results projection for the offline phone facade.

This module intentionally has no WorkspaceStore/native bridge.  Its collection
grant and source are constructed by trusted test setup and are never decoded
from a phone request.
"""
from __future__ import annotations

import base64
import json
import re
import threading
import time
import uuid
from dataclasses import dataclass


MAX_MEMBERS = 25
MAX_PAGE = 25
MAX_JOURNAL_EVENTS = 256
MAX_JOURNAL_BYTES = 512 * 1024
MAX_RESPONSE_BYTES = 512 * 1024
MAX_CURSORS = 256
MAX_CURSORS_PER_BINDING = 8
MAX_CURSOR_BYTES = 64 * 1024
CURSOR_TTL_SECONDS = 15 * 60
_TOKEN = re.compile(r"^[A-Za-z0-9_-]{43}$")
_MAX_I63 = (1 << 63) - 1
_MAX_SAFE_MS = (1 << 53) - 1


def _uuid(value: object) -> bool:
    if type(value) is not str or not value:
        return False
    try:
        return str(uuid.UUID(value)) == value
    except (ValueError, AttributeError):
        return False


def _token() -> str:
    return base64.urlsafe_b64encode(uuid.uuid4().bytes + uuid.uuid4().bytes).decode("ascii").rstrip("=")


def _valid_token(value):
    if type(value) is not str or not _TOKEN.fullmatch(value):
        return False
    try:
        decoded = base64.urlsafe_b64decode(value + "=")
    except (ValueError, TypeError):
        return False
    return len(decoded) == 32 and base64.urlsafe_b64encode(decoded).decode("ascii").rstrip("=") == value


def _binding_key(binding) -> tuple:
    return (binding.owner_id, binding.device_id, binding.grant_id, binding.session_id,
            binding.login_incarnation, binding.host_id, binding.host_generation,
            binding.grant_generation, binding.session_generation, binding.process_epoch,
            tuple(sorted(binding.scopes)))


def _json_size(value: dict) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":"),
                          allow_nan=False).encode("utf-8", "strict"))


@dataclass(frozen=True)
class PhoneResultCollectionGrantV1:
    """Trusted server-side synthetic read grant; it is not a wire DTO."""
    owner_id: str
    device_id: str
    phone_grant_id: str
    collection_id: str
    member_ids: tuple[str, ...]
    version: int = 1

    def __post_init__(self):
        if (type(self.owner_id) is not str or not self.owner_id
                or type(self.device_id) is not str or not self.device_id
                or type(self.phone_grant_id) is not str or not self.phone_grant_id
                or not _uuid(self.collection_id) or type(self.member_ids) is not tuple
                or len(self.member_ids) > MAX_MEMBERS or type(self.version) is not int
                or not 1 <= self.version <= _MAX_I63):
            raise ValueError("invalid synthetic collection grant")
        if any(not _uuid(item) for item in self.member_ids) or len(set(self.member_ids)) != len(self.member_ids):
            raise ValueError("invalid synthetic collection membership")


@dataclass(frozen=True)
class SyntheticResultRecord:
    """Server-owned source row used by offline tests only."""
    result_id: str
    revision: int
    title: str
    body: str
    received_at_ms: int
    classification: str = "ordinary"
    provenance_valid: bool = True

    def __post_init__(self):
        if not _uuid(self.result_id):
            raise ValueError("invalid result identity")
        if type(self.revision) is not int or not 1 <= self.revision <= _MAX_I63:
            raise ValueError("invalid result revision")
        if type(self.received_at_ms) is not int or not 0 <= self.received_at_ms <= _MAX_SAFE_MS:
            raise ValueError("invalid result time")
        for text, limit in ((self.title, 512), (self.body, 8192)):
            if type(text) is not str or not text or "\x00" in text:
                raise ValueError("invalid result text")
            if len(text.encode("utf-8", "strict")) > limit:
                raise ValueError("result text exceeds limit")
        if self.classification not in {"ordinary", "protected", "unclassified"}:
            raise ValueError("invalid result classification")
        if type(self.provenance_valid) is not bool:
            raise ValueError("invalid result provenance")

    def item(self) -> dict:
        return {"result_id": self.result_id, "revision": self.revision,
                "source": {"kind": "synthetic.workspace_result.v1", "id": self.result_id,
                           "revision": self.revision},
                "classification": "ordinary", "title": self.title, "body": self.body,
                "received_at_ms": self.received_at_ms}


class SyntheticResultsSource:
    """Mutable deterministic fixture source. Updates never call service code."""
    def __init__(self, records=()):
        records = tuple(records)
        if any(type(record) is not SyntheticResultRecord for record in records):
            raise TypeError("synthetic source accepts only immutable result records")
        if len({row.result_id for row in records}) > MAX_JOURNAL_EVENTS:
            raise ValueError("synthetic source identity history is full")
        self._lock = threading.RLock()
        self._version = 0
        self._records = tuple(records)
        self._history: list[tuple[int, str, SyntheticResultRecord | None, bool]] = []
        self._history_bytes = 0
        self._history_truncated_by_id: dict[str, int] = {}
        self._visibility_versions: dict[str, int] = {row.result_id: 0 for row in records}

    def snapshot(self):
        with self._lock:
            return self._version, tuple(self._records)

    def replace(self, records):
        values = tuple(records)
        if any(type(record) is not SyntheticResultRecord for record in values):
            raise TypeError("synthetic source accepts only immutable result records")
        with self._lock:
            previous = {row.result_id: row for row in self._records}
            current = {row.result_id: row for row in values}
            if len(current) != len(values):
                # Keep duplicate-source fixtures constructible for fail-closed
                # projector tests, but never accept a duplicate replacement.
                raise ValueError("duplicate synthetic source identity")
            for identity, new in current.items():
                old = previous.get(identity)
                if old is not None and old != new and new.revision <= old.revision:
                    raise ValueError("changed result revision must advance")
            new_ids = set(current) - set(self._visibility_versions)
            if len(self._visibility_versions) + len(new_ids) > MAX_JOURNAL_EVENTS:
                raise ValueError("synthetic source identity history is full")
            self._version += 1
            version = self._version
            additions = []
            for identity in set(previous) | set(current):
                old, new = previous.get(identity), current.get(identity)
                if old == new:
                    continue
                visible_transition = bool(old and old.classification == "ordinary"
                    and old.provenance_valid and (new is None or new.classification != "ordinary"
                                                  or not new.provenance_valid))
                if visible_transition:
                    self._visibility_versions[identity] = self._visibility_versions.get(identity, 0) + 1
                else:
                    self._visibility_versions.setdefault(identity, 0)
                # Preserve each ordinary revision for deterministic paging.
                # Protected/unselected changes are only remembered as a
                # non-content marker when a previously visible item vanished.
                additions.append((version, identity, new, visible_transition))
            self._records = values
            for event in additions:
                self._history.append(event)
                record = event[2]
                self._history_bytes += 256 + (len(record.title.encode("utf-8"))
                    + len(record.body.encode("utf-8")) if record is not None else 0)
            while (len(self._history) > MAX_JOURNAL_EVENTS
                   or self._history_bytes > MAX_JOURNAL_BYTES):
                version_removed, identity, record_removed, _ = self._history.pop(0)
                self._history_truncated_by_id[identity] = max(
                    version_removed, self._history_truncated_by_id.get(identity, 0))
                self._history_bytes -= 256 + (len(record_removed.title.encode("utf-8"))
                    + len(record_removed.body.encode("utf-8")) if record_removed is not None else 0)
            return self._version

    def history_since(self, version):
        with self._lock:
            return tuple(event for event in self._history if event[0] > version)

    def capture(self, member_ids, since_version):
        """Atomically capture selected history and visibility epochs with source rows."""
        with self._lock:
            members = set(member_ids)
            history = tuple(event for event in self._history
                            if event[0] > since_version and event[1] in members)
            # Truncated history for a currently excluded source cannot make
            # the selected, visible collection incomplete. Prior visibility
            # transitions are tracked independently by their version counters.
            visible = {row.result_id for row in self._records
                       if row.result_id in members and row.classification == "ordinary"
                       and row.provenance_valid}
            complete = not any(self._history_truncated_by_id.get(identity, 0) > since_version
                               for identity in visible)
            visibility = {identity: self._visibility_versions.get(identity, 0)
                          for identity in members}
            return self._version, tuple(self._records), history, complete, visibility


@dataclass
class _Cursor:
    binding: tuple
    grant_version: int
    generation: str
    epoch: str
    position: int
    high_water: int | None
    created: float
    receipt: dict | None = None


@dataclass(frozen=True)
class _Candidate:
    grant_version: int
    source_version: int
    records: tuple[SyntheticResultRecord, ...]
    now: float
    history: tuple
    history_complete: bool
    visibility_versions: tuple
    selected_state: tuple[SyntheticResultRecord, ...]


class PhoneRemoteResults:
    """Synthetic collection projector, journal and bounded resume-cursor owner."""
    def __init__(self, grant: PhoneResultCollectionGrantV1,
                 source: SyntheticResultsSource, *, clock=time.monotonic):
        if type(grant) is not PhoneResultCollectionGrantV1 or type(source) is not SyntheticResultsSource:
            raise TypeError("results require trusted synthetic grant and source")
        if clock is not time.monotonic and type(clock) is not type(lambda: 0):
            raise TypeError("clock must be a local callable")
        self._grant = grant
        self._source = source
        self._clock = clock
        self._lock = threading.RLock()
        self._generation = str(uuid.uuid4())
        self._epoch = str(uuid.uuid4())
        self._sequence = 0
        self._source_version_seen = 0
        self._visible: dict[str, SyntheticResultRecord] = {}
        self._visibility_versions: dict[str, int] = {}
        self._journal: list[dict] = []
        self._journal_bytes = 0
        self._cursors: dict[str, _Cursor] = {}
        self._active = True
        self._command_registry = None

    @property
    def generation(self):
        return self._generation

    def revoke(self):
        with self._lock:
            self._active = False
            self._epoch = str(uuid.uuid4())
            self._cursors.clear()

    def replace_grant(self, grant: PhoneResultCollectionGrantV1):
        if type(grant) is not PhoneResultCollectionGrantV1:
            raise TypeError("invalid synthetic grant")
        while True:
            registry = self._command_registry
            if registry is not None:
                # Enter R before P. Never call the registry while holding P.
                return registry.replace_collection_grant(self, grant)
            with self._lock:
                # Registration may have won the race before P was acquired.
                if self._command_registry is not None:
                    continue
                return self._replace_grant_locked(grant)

    def _replace_grant_locked(self, grant):
        if grant.version <= self._grant.version:
            raise ValueError("collection grant version must advance")
        self._grant = grant
        self._active = True
        self._epoch = str(uuid.uuid4())
        self._cursors.clear()
        self._visible.clear()
        self._visibility_versions.clear()
        self._journal.clear()
        self._journal_bytes = 0
        self._sequence = 0

    def cached_content_authorized(self, binding, receipt: dict) -> bool:
        """Recheck current identity/classification without requiring old revisions."""
        try:
            with self._lock, self._source._lock:
                # Cached visibility checks must not call the injected clock:
                # this method runs under authority/service commit guards.
                candidate = self._capture(binding, self._generation, now=0.0)
                current_versions = dict(candidate.visibility_versions)
                visibility_changed = any(
                    current_versions.get(identity, 0) != self._visibility_versions.get(identity, 0)
                    for identity in self._visible
                )
                missing_visible = any(identity not in {row.result_id for row in candidate.records}
                                      for identity in self._visible)
                if visibility_changed or missing_visible:
                    self._epoch = str(uuid.uuid4())
                    self._visible = {row.result_id: row for row in candidate.records}
                    self._journal = []
                    self._journal_bytes = 0
                    self._sequence = 0
                    self._cursors.clear()
                    self._source_version_seen = candidate.source_version
                    self._visibility_versions = current_versions
                payload = receipt.get("payload", {}) if type(receipt) is dict else {}
                if (not self._authorized(binding) or type(payload) is not dict
                        or payload.get("generation") != self._generation
                        or payload.get("collection_epoch") != self._epoch):
                    return False
                current = {record.result_id: record for record in candidate.records}
                items = payload.get("items", [])
                events = payload.get("events", [])
                if type(items) is not list or type(events) is not list:
                    return False
                for item in items:
                    if (type(item) is not dict or item.get("result_id") not in current
                            or item["result_id"] not in self._grant.member_ids
                            or current[item["result_id"]].classification != "ordinary"
                            or not current[item["result_id"]].provenance_valid):
                        return False
                for event in events:
                    item = event.get("item") if type(event) is dict else None
                    if (type(item) is not dict or item.get("result_id") not in current
                            or item["result_id"] not in self._grant.member_ids
                            or current[item["result_id"]].classification != "ordinary"
                            or not current[item["result_id"]].provenance_valid):
                        return False
                return True
        except Exception:
            return False

    def _authorized(self, binding) -> bool:
        grant = self._grant
        return (self._active and "read" in binding.scopes
                and binding.owner_id == grant.owner_id
                and binding.device_id == grant.device_id
                and binding.grant_id == grant.phone_grant_id)

    def _capture(self, binding, generation: str, *, now=None) -> _Candidate:
        if not _uuid(generation):
            raise ValueError("invalid process generation")
        if not self._authorized(binding):
            raise PermissionError("not authorized")
        member_ids = self._grant.member_ids
        version, records, history, history_complete, visibility_versions = self._source.capture(
            member_ids, self._source_version_seen)
        # Excluded source activity must not perturb this collection's result.
        if any(type(r) is not SyntheticResultRecord for r in records):
            raise RuntimeError("ambiguous result source")
        member_ids = set(member_ids)
        selected_records = [record for record in records if record.result_id in member_ids]
        if len(selected_records) > MAX_MEMBERS:
            raise RuntimeError("selected result collection exceeds its bound")
        ids = [record.result_id for record in selected_records]
        if len(ids) != len(set(ids)):
            raise RuntimeError("duplicate source identity")
        by_id = {record.result_id: record for record in selected_records}
        selected = []
        selected_state = []
        for result_id in self._grant.member_ids:
            record = by_id.get(result_id)
            if record is None:
                continue
            if record.classification == "unclassified" or not record.provenance_valid:
                raise RuntimeError("unverified result source")
            if record.classification == "ordinary":
                selected.append(record)
                selected_state.append(record)
        selected.sort(key=lambda row: row.result_id.encode("ascii"))
        sampled_now = float(self._clock()) if now is None else float(now)
        return _Candidate(self._grant.version, version, tuple(selected), sampled_now,
                          history, history_complete, tuple(sorted(visibility_versions.items())),
                          tuple(selected_state))

    def _source_matches(self, candidate: _Candidate) -> bool:
        _, records, _, _, visibility_versions = self._source.capture(
            self._grant.member_ids, candidate.source_version)
        if dict(candidate.visibility_versions) != visibility_versions:
            return False
        member_ids = set(self._grant.member_ids)
        selected = tuple(sorted((record for record in records
            if type(record) is SyntheticResultRecord and record.result_id in member_ids
            and record.classification == "ordinary" and record.provenance_valid),
            key=lambda row: row.result_id.encode("ascii")))
        expected = tuple(sorted(candidate.selected_state,
            key=lambda row: row.result_id.encode("ascii")))
        return selected == expected

    def _expired(self, now):
        dead = [token for token, cursor in self._cursors.items()
                if now - cursor.created >= CURSOR_TTL_SECONDS]
        for token in dead:
            self._cursors.pop(token, None)

    def _capacity_ok(self, binding_key, *, additional=1, now=None):
        if now is None:
            raise RuntimeError("cursor capacity requires a prepared clock sample")
        self._expired(now)
        live = [cursor for cursor in self._cursors.values() if cursor.binding == binding_key]
        size = sum(160 + len(cursor.binding) * 8 for cursor in self._cursors.values())
        return (len(self._cursors) + additional <= MAX_CURSORS
                and len(live) + additional <= MAX_CURSORS_PER_BINDING
                and size + additional * (160 + len(binding_key) * 8) <= MAX_CURSOR_BYTES)

    @staticmethod
    def _trim_journal(journal):
        retained = list(journal[-MAX_JOURNAL_EVENTS:])
        size = sum(_json_size(event) for event in retained)
        while retained and size > MAX_JOURNAL_BYTES:
            size -= _json_size(retained.pop(0))
        return retained, size

    def _reconcile(self, candidate: _Candidate):
        incoming = {record.result_id: record for record in candidate.records}
        # A source disappearing or becoming less trustworthy invalidates the
        # visible collection; ordinary revisions alone remain replayable.
        current_versions = dict(candidate.visibility_versions)
        invalidated = any(
            identity not in incoming for identity in self._visible
        ) or any(current_versions.get(identity, 0) != self._visibility_versions.get(identity, 0)
                 for identity in self._visible)
        changes = []
        history_changes = []
        if any(visible_transition and identity in self._visible
               for _, identity, _, visible_transition in candidate.history):
            invalidated = True
        for _, identity, record, _ in candidate.history:
            if record is not None and identity in self._grant.member_ids:
                if record.classification == "ordinary" and record.provenance_valid:
                    history_changes.append(record)
        if not invalidated:
            for identity, record in incoming.items():
                previous = self._visible.get(identity)
                if previous is not None and record.revision < previous.revision:
                    invalidated = True
                    break
                if previous is None and self._visible:
                    changes.append(record)
        if invalidated:
            return str(uuid.uuid4()), incoming, [], True
        # Keep every ordinary source revision observed by the projector, not
        # just the latest row when several updates occur between requests.
        if history_changes:
            changes = history_changes
        return self._epoch, incoming, changes, False

    def command_state(self, binding):
        """Immutable selected-state proof for mobile view commands (P -> S).

        No injected clock or callbacks. Ordinary edits don't alter historical
        result receipts; visibility loss retires the same collection epoch.
        """
        with self._lock, self._source._lock:
            candidate = self._capture(binding, self._generation, now=0.0)
            epoch, visible, _, invalidated = self._reconcile(candidate)
            if invalidated:
                self._epoch = epoch
                self._visible = visible
                self._journal = []
                self._journal_bytes = self._sequence = 0
                self._cursors.clear()
                self._source_version_seen = candidate.source_version
                self._visibility_versions = dict(candidate.visibility_versions)
            versions = dict(candidate.visibility_versions)
            rows = tuple((r.result_id, r.revision, versions.get(r.result_id, 0))
                         for r in candidate.records)
            return self._generation, self._epoch, id(self._grant), self._grant.version, rows

    def prepare_snapshot(self, binding, generation: str) -> tuple[str, _Candidate | None]:
        """Capture synthetic source input before acquiring authority commit locks."""
        try:
            candidate = self._capture(binding, generation)
        except PermissionError:
            return "not_authorized", None
        except Exception:
            return "authority_unavailable", None
        return "ok", candidate

    def snapshot(self, binding, generation: str, *, candidate=None,
                 request_id="x") -> tuple[str, dict | None]:
        """Finalize a prepared snapshot after the caller's v3 release ack."""
        if candidate is None:
            status, candidate = self.prepare_snapshot(binding, generation)
            if status != "ok":
                return status, None
        with self._lock, self._source._lock:
            if not self._authorized(binding):
                return "not_authorized", None
            if candidate.grant_version != self._grant.version:
                return "authority_unavailable", None
            if not self._source_matches(candidate):
                return "authority_unavailable", None
            epoch, visible, changes, invalidated = self._reconcile(candidate)
            sequence = 0 if invalidated else self._sequence
            journal = [] if invalidated else list(self._journal)
            if not journal and not visible:
                pass
            if invalidated or not self._visible:
                changes = list(candidate.records)
            for record in changes:
                if sequence >= _MAX_I63:
                    return "authority_unavailable", None
                sequence += 1
                journal.append({"sequence": sequence, "kind": "upsert", "item": record.item()})
            cursor = _token()
            payload = {"generation": self._generation, "collection_epoch": epoch,
                       "content_watermark": sequence, "cursor": cursor,
                       "items": [record.item() for record in candidate.records]}
            if _json_size({"request_id": request_id, "status": "ok", "reason": "none",
                           "payload": payload}) > MAX_RESPONSE_BYTES:
                return "authority_unavailable", None
            binding_key = _binding_key(binding)
            if not self._capacity_ok(binding_key, now=candidate.now):
                return "request_capacity", None
            if not candidate.history_complete:
                # This snapshot advances the source watermark. Uncommitted
                # cursors still expect the now-truncated interval, so retire
                # them instead of silently starting midway through the
                # remaining journal. Committed receipts remain replayable.
                self._cursors = {token: cursor for token, cursor in self._cursors.items()
                                 if cursor.receipt is not None}
            next_journal, next_journal_bytes = self._trim_journal(journal)
            self._epoch, self._visible, self._sequence = epoch, visible, sequence
            self._journal, self._journal_bytes = next_journal, next_journal_bytes
            self._source_version_seen = candidate.source_version
            self._visibility_versions = dict(candidate.visibility_versions)
            self._cursors[cursor] = _Cursor(binding_key, self._grant.version,
                self._generation, epoch, sequence, None, candidate.now)
            return "ok", payload

    def prepare_resume(self, binding, generation: str, token: str) -> tuple[str, _Candidate | None]:
        if not _valid_token(token):
            return "malformed_request", None
        try:
            candidate = self._capture(binding, generation)
        except PermissionError:
            return "not_authorized", None
        except Exception:
            return "authority_unavailable", None
        return "ok", candidate

    def resume(self, binding, generation: str, token: str, *, candidate=None,
               request_id="x") -> tuple[str, dict | None]:
        if candidate is None:
            status, candidate = self.prepare_resume(binding, generation, token)
            if status != "ok":
                return status, None
        with self._lock, self._source._lock:
            if not self._authorized(binding):
                return "not_authorized", None
            if candidate.grant_version != self._grant.version:
                return "reset", {"generation": generation, "collection_epoch": self._epoch,
                                  "reset_required": True}
            binding_key = _binding_key(binding)
            now = candidate.now
            self._expired(now)
            if not _valid_token(token):
                return "malformed_request", None
            cursor = self._cursors.get(token)
            if (cursor is None or cursor.binding != binding_key
                    or cursor.generation != generation or cursor.epoch != self._epoch
                    or cursor.grant_version != self._grant.version):
                return "reset", {"generation": generation, "collection_epoch": self._epoch,
                                  "reset_required": True}
            # Exact committed page replay is immutable, but current authority,
            # membership and classification still have to authorize its bytes.
            if cursor.receipt is not None:
                if not self._source_matches(candidate):
                    return "authority_unavailable", None
                epoch, visible, _, invalidated = self._reconcile(candidate)
                if invalidated:
                    self._epoch, self._visible, self._sequence = epoch, visible, 0
                    self._journal, self._journal_bytes = [], 0
                    self._source_version_seen = candidate.source_version
                    self._visibility_versions = dict(candidate.visibility_versions)
                    self._cursors.clear()
                    return "reset", {"generation": generation, "collection_epoch": epoch,
                                      "reset_required": True}
                current = {record.result_id: record for record in candidate.records}
                if any(identity not in current for identity in self._visible):
                    return "authority_unavailable", None
                for event in cursor.receipt.get("events", []):
                    item = event["item"]
                    row = current.get(item["result_id"])
                    if row is None or row.classification != "ordinary" or not row.provenance_valid:
                        return "authority_unavailable", None
                return "ok", cursor.receipt
            if not candidate.history_complete:
                epoch, visible, _, _ = self._reconcile(candidate)
                epoch = str(uuid.uuid4())
                self._epoch, self._visible, self._sequence = epoch, visible, 0
                self._journal, self._journal_bytes = [], 0
                self._source_version_seen = candidate.source_version
                self._visibility_versions = dict(candidate.visibility_versions)
                self._cursors.clear()
                return "reset", {"generation": generation, "collection_epoch": epoch,
                                  "reset_required": True}
            if not self._source_matches(candidate):
                return "authority_unavailable", None
            epoch, visible, changes, invalidated = self._reconcile(candidate)
            if invalidated:
                self._epoch = epoch
                self._visible = visible
                self._journal = []
                self._journal_bytes = 0
                self._sequence = 0
                self._source_version_seen = candidate.source_version
                self._visibility_versions = dict(candidate.visibility_versions)
                self._cursors.clear()
                return "reset", {"generation": generation, "collection_epoch": epoch,
                                  "reset_required": True}
            sequence = self._sequence
            journal = list(self._journal)
            for record in changes:
                if sequence >= _MAX_I63:
                    return "authority_unavailable", None
                sequence += 1
                journal.append({"sequence": sequence, "kind": "upsert", "item": record.item()})
            # Retention is applied before traversal so an obsolete cursor
            # resets before any partial page can be disclosed.
            journal, retained_bytes = self._trim_journal(journal)
            position = cursor.position
            high_water = cursor.high_water if cursor.high_water is not None else sequence
            events = [event for event in journal
                      if position < event["sequence"] <= high_water]
            earliest_retained = journal[0]["sequence"] if journal else sequence + 1
            if position < earliest_retained - 1:
                epoch = str(uuid.uuid4())
                self._epoch, self._visible, self._sequence = epoch, visible, 0
                self._journal, self._journal_bytes = [], 0
                self._source_version_seen = candidate.source_version
                self._visibility_versions = dict(candidate.visibility_versions)
                self._cursors.clear()
                return "reset", {"generation": generation, "collection_epoch": epoch,
                                  "reset_required": True}
            page = events[:MAX_PAGE]
            has_more = len(events) > len(page)
            next_position = page[-1]["sequence"] if page else high_water
            next_high = high_water if has_more else None
            next_token = _token()
            payload = {"generation": generation, "collection_epoch": epoch,
                       "content_watermark": high_water, "reset_required": False,
                       "has_more": has_more, "cursor": next_token, "events": page}
            if _json_size({"request_id": request_id, "status": "ok", "reason": "none",
                           "payload": payload}) > MAX_RESPONSE_BYTES:
                return "authority_unavailable", None
            if not self._capacity_ok(binding_key, now=candidate.now):
                return "request_capacity", None
            # Commit source reconciliation, response receipt and successor
            # cursor only after caller's v3 authority release has succeeded.
            next_journal, next_journal_bytes = journal, retained_bytes
            self._epoch, self._visible, self._sequence = epoch, visible, sequence
            self._journal, self._journal_bytes = next_journal, next_journal_bytes
            self._source_version_seen = candidate.source_version
            self._visibility_versions = dict(candidate.visibility_versions)
            cursor.receipt = payload
            self._cursors[next_token] = _Cursor(binding_key, self._grant.version,
                generation, epoch, next_position, next_high, now)
            return "ok", payload


__all__ = ["PhoneResultCollectionGrantV1", "SyntheticResultRecord",
           "SyntheticResultsSource", "PhoneRemoteResults"]
