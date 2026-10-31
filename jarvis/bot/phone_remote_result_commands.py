"""Bounded synthetic mobile-view state, owned by one authority runtime.

No console dispatch, source writes, external effects or production authorization.
Lock order: service runtime R -> projector P -> synthetic source S.
"""
from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass

from jarvis.bot.phone_remote_results import PhoneRemoteResults, _binding_key

ACTIONS = frozenset({'results.select', 'results.pin', 'results.unpin',
                     'results.close', 'results.reopen'})
OPERATIONS = ACTIONS | {'results.view'}
MAX_INT = (1 << 63) - 1


class CommandDenied(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class CommandCapability:
    capability_id: str
    version: int
    active: bool
    allowed_operations: tuple[str, ...]
    generation: str
    grant: object


@dataclass(frozen=True)
class CommandPreparation:
    source: tuple
    capability: tuple | None


@dataclass
class _Slot:
    projector: PhoneRemoteResults
    capability: CommandCapability | None = None


@dataclass
class _View:
    payload: dict
    source: tuple
    capability: tuple | None
    synchronized: bool = True


class PhoneResultCommandRegistry:
    """Trusted fixture-control handle; never passed to a phone or a model."""
    def __init__(self, runtime_lock):
        self._lock = runtime_lock
        self._slots = {}
        self._views = {}
        self._bindings = {}

    @staticmethod
    def _slot_key(projector):
        return PhoneResultCommandRegistry._grant_key(projector._grant)

    @staticmethod
    def _grant_key(grant):
        return grant.owner_id, grant.device_id, grant.phone_grant_id, grant.collection_id

    def attach(self, projector):
        if type(projector) is not PhoneRemoteResults:
            raise TypeError('commands require the exact synthetic projector')
        with self._lock, projector._lock:
            if projector._command_registry not in (None, self):
                raise TypeError('projector already belongs to another command runtime')
            key = self._slot_key(projector)
            prior = self._slots.get(key)
            if prior is not None and prior.projector is not projector:
                raise TypeError('conflicting projector for shared command slot')
            if prior is None:
                if len(self._slots) >= 128:
                    raise ValueError('command slot capacity')
                self._slots[key] = _Slot(projector)
            projector._command_registry = self
            return self

    def _slot(self, projector):
        # Identity lookup preserves the slot after a collection-grant replacement;
        # replacement still needs an explicit control transition to rebind it.
        for slot in self._slots.values():
            if slot.projector is projector:
                return slot
        raise ValueError('unregistered command projector')

    def replace_collection_grant(self, projector, grant):
        from jarvis.bot.phone_remote_results import PhoneResultCollectionGrantV1
        if type(grant) is not PhoneResultCollectionGrantV1:
            raise TypeError('invalid synthetic grant')
        with self._lock, projector._lock:
            slot = self._slot(projector)
            new_key = self._grant_key(grant)
            collision = self._slots.get(new_key)
            if collision is not None and collision is not slot:
                raise TypeError('conflicting replacement command slot')
            old_key = self._slot_key(projector)
            projector._replace_grant_locked(grant)
            if old_key != new_key:
                del self._slots[old_key]
                self._slots[new_key] = slot
            self.retire_projector(projector)
            # Existing capability retains its exact old grant and must be
            # explicitly replaced; a collection move cannot rebind authority.

    @staticmethod
    def _operations(operations):
        if (type(operations) is not tuple or len(operations) != len(set(operations))
                or any(type(op) is not str or op not in ACTIONS for op in operations)):
            raise ValueError('invalid command operation subset')
        return tuple(sorted(operations))

    def register(self, projector, operations):
        return self._change(projector, None, operations, 'register')

    def update(self, projector, expected, operations):
        return self._change(projector, expected, operations, 'update')

    def revoke(self, projector, expected):
        return self._change(projector, expected, (), 'revoke')

    def replace(self, projector, expected, operations):
        return self._change(projector, expected, operations, 'replace')

    def _change(self, projector, expected, operations, kind):
        operations = self._operations(operations)
        with self._lock, projector._lock:
            slot = self._slot(projector)
            old = slot.capability
            if expected is not old or (expected is not None and type(expected) is not CommandCapability):
                raise ValueError('stale capability compare-and-swap')
            if kind == 'register' and (old is not None or not operations):
                raise ValueError('capability already registered or empty')
            if kind != 'register' and old is None:
                raise ValueError('capability absent')
            if kind in {'register', 'replace'} and (not operations or not projector._active):
                raise ValueError('active collection and operations required')
            if kind == 'update' and (not old.active or old.grant is not projector._grant
                                     or old.generation != projector.generation):
                raise ValueError('capability replacement required')
            if kind in {'update', 'revoke'} and old.allowed_operations == operations:
                return old
            if old is not None and old.version == MAX_INT:
                raise ValueError('capability version exhausted')
            value = CommandCapability(str(uuid.uuid4()) if kind in {'register', 'replace'} else old.capability_id,
                1 if old is None else old.version + 1, bool(operations), operations,
                projector.generation, projector._grant)
            slot.capability = value
            return value

    def _capability(self, projector):
        cap = self._slot(projector).capability
        token = None if cap is None else (cap.capability_id, cap.version)
        allowed = () if (cap is None or not cap.active or cap.grant is not projector._grant
                         or cap.generation != projector.generation or not projector._active) else cap.allowed_operations
        return token, allowed

    def _source(self, projector, binding):
        try:
            return projector.command_state(binding)
        except PermissionError:
            raise CommandDenied('not_authorized') from None
        except Exception:
            raise CommandDenied('authority_unavailable') from None

    def prepare(self, projector, binding):
        # Retire only objectively invalidated collections, never another
        # binding's view merely because this caller failed authorization.
        with self._lock, projector._lock:
            current = (projector.generation, projector._epoch)
            self._views = {key: view for key, view in self._views.items()
                if key[1] != id(projector) or (projector._active and view.source[:2] == current)}
            self._trim_bindings()
        # This is bounded immutable synthetic capture, with no callback/clock.
        source = self._source(projector, binding)
        with self._lock, projector._lock:
            # Collection invalidation retires prior views at the next registry
            # observation; ordinary revision changes leave saved views intact.
            self._views = {key: view for key, view in self._views.items()
                if key[1] != id(projector) or view.source[:2] == source[:2]}
            self._trim_bindings()
            token, _ = self._capability(projector)
            return CommandPreparation(source, token)

    def _key(self, projector, binding):
        return _binding_key(binding), id(projector), projector.generation

    def _authorize(self, projector, binding, operation):
        token, allowed = self._capability(projector)
        if 'read' not in binding.scopes or (operation in ACTIONS and
                ('action' not in binding.scopes or operation not in allowed)):
            raise CommandDenied('not_authorized')
        return token, allowed

    def apply(self, projector, binding, request, prepared):
        """Atomic in-memory effect; called under R/G, never invokes callbacks."""
        with self._lock, projector._lock, projector._source._lock:
            operation, payload = request['operation'], request['payload']
            token, allowed = self._authorize(projector, binding, operation)
            source = self._source(projector, binding)
            if payload['generation'] != source[0] or payload['collection_epoch'] != source[1]:
                raise CommandDenied('authority_unavailable')
            rows = {item[0]: item[1] for item in source[4]}
            if operation in ACTIONS and payload['result_id'] not in rows:
                raise CommandDenied('not_authorized')
            if source != prepared.source or token != prepared.capability:
                raise CommandDenied('request_conflict' if operation in ACTIONS else 'authority_unavailable')
            key = self._key(projector, binding)
            view = self._views.get(key)
            if view is not None and (view.payload['generation'], view.payload['collection_epoch']) != source[:2]:
                view = None
            if operation == 'results.view':
                if view is None and key not in self._views and len(self._views) >= 128:
                    raise CommandDenied('request_capacity')
                old_cards = {} if view is None else {c['result_id']: c for c in view.payload['cards']}
                cards = [dict(result_id=rid, result_revision=rev,
                              open=old_cards.get(rid, {}).get('open', True),
                              pinned=old_cards.get(rid, {}).get('pinned', False))
                         for rid, rev in rows.items()]
                selected = None if view is None else view.payload['selected_result_id']
                if selected not in rows:
                    selected = None
                value = dict(generation=source[0], collection_epoch=source[1],
                    view_id=str(uuid.uuid4()) if view is None else view.payload['view_id'],
                    view_revision=0 if view is None else view.payload['view_revision'],
                    selected_result_id=selected, allowed_operations=list(allowed), cards=cards)
                changed = view is not None and (value != view.payload or source != view.source
                                                or token != view.capability or not view.synchronized)
            else:
                if (view is None or not view.synchronized or view.source != source or view.capability != token
                        or payload['view_id'] != view.payload['view_id']
                        or payload['view_revision'] != view.payload['view_revision']
                        or payload['result_revision'] != rows[payload['result_id']]):
                    raise CommandDenied('request_conflict')
                value = copy.deepcopy(view.payload)
                target = next(c for c in value['cards'] if c['result_id'] == payload['result_id'])
                if operation in {'results.select', 'results.pin', 'results.unpin'} and not target['open']:
                    raise CommandDenied('request_conflict')
                if operation == 'results.select':
                    value['selected_result_id'] = target['result_id']
                elif operation == 'results.pin':
                    if not target['pinned'] and sum(c['pinned'] for c in value['cards']) >= 20:
                        raise CommandDenied('request_capacity')
                    target['pinned'] = True
                elif operation == 'results.unpin':
                    target['pinned'] = False
                elif operation == 'results.close':
                    target['open'] = target['pinned'] = False
                    if value['selected_result_id'] == target['result_id']:
                        value['selected_result_id'] = None
                elif operation == 'results.reopen':
                    target['open'] = True
                    value['selected_result_id'] = target['result_id']
                changed = value != view.payload
            if changed:
                if value['view_revision'] == MAX_INT:
                    raise CommandDenied('authority_unavailable')
                value['view_revision'] += 1
            # Construct and validate before installing anything observable.
            from jarvis.bot.phone_remote_protocol import validate_success_payload, encode_response, response
            if not validate_success_payload(operation, value):
                raise CommandDenied('authority_unavailable')
            encode_response(response(request['request_id'], 'ok', 'none', value), operation=operation)
            self._views[key] = _View(copy.deepcopy(value), source, token)
            self._bindings[_binding_key(binding)] = binding
            return value, (source, token, key)

    def publication(self, projector, binding, request, receipt, witness, *, historical=False):
        """R/P/S-held publication gate; historical replay never mutates a view."""
        with self._lock, projector._lock, projector._source._lock:
            operation = request['operation']
            token, _ = self._authorize(projector, binding, operation)
            source = self._source(projector, binding)
            prior_source, prior_capability, key = witness
            if token != prior_capability:
                raise CommandDenied('not_authorized' if operation in ACTIONS else 'authority_unavailable')
            if source[:4] != prior_source[:4]:
                self.retire_projector(projector)
                raise CommandDenied('authority_unavailable')
            if historical:
                current = {row[0]: row for row in source[4]}
                if any(row[0] not in current or current[row[0]][2:] != row[2:] for row in prior_source[4]):
                    raise CommandDenied('authority_unavailable')
            elif source != prior_source:
                if key in self._views:
                    self._views[key].synchronized = False
                raise CommandDenied('authority_unavailable')
            return receipt

    def retire_binding(self, binding):
        with self._lock:
            key = _binding_key(binding)
            self._views = {k: v for k, v in self._views.items() if k[0] != key}
            self._bindings.pop(key, None)

    def bindings(self):
        with self._lock:
            return tuple(self._bindings.values())

    def retire_context(self, context):
        with self._lock:
            for binding in tuple(self._bindings.values()):
                if (binding.owner_id == context.owner_id and binding.session_id == context.session_id
                        and binding.device_id == context.device_id
                        and binding.login_incarnation == context.login_incarnation):
                    self.retire_binding(binding)

    def _trim_bindings(self):
        live = {key[0] for key in self._views}
        self._bindings = {key: value for key, value in self._bindings.items() if key in live}

    def retire_projector(self, projector):
        with self._lock:
            self._views = {key: value for key, value in self._views.items() if key[1] != id(projector)}
            self._trim_bindings()
