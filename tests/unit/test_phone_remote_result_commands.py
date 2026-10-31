"""Synthetic view effects, authority/visibility gates and deterministic races."""
import copy
import json
import sqlite3
import threading
import unittest
import uuid
from contextlib import contextmanager
from dataclasses import replace
from unittest.mock import patch

from jarvis.auth import ClientIdentity
from jarvis.bot.phone_admission_store import FakeProtectedAnchor, PhoneAdmissionStore
from jarvis.bot.phone_remote_result_commands import ACTIONS, CommandCapability, MAX_INT
from jarvis.bot.phone_remote_results import PhoneRemoteResults, PhoneResultCollectionGrantV1, SyntheticResultRecord, SyntheticResultsSource
from jarvis.bot.phone_remote_service import PhoneRemoteService, FakeContextVerifier, FakeMediaAdapter, FakeClockGate, TrustedRequestContext


def uid(n): return str(uuid.UUID(int=n))
def row(n, revision=1, classification='ordinary'):
    return SyntheticResultRecord(uid(n), revision, f'title-{n}', f'body-{n}', 1, classification)
def wire(operation, payload, rid='r'):
    return json.dumps(dict(kind='mortimer.phone-remote.v1', protocol_version=1,
                          request_id=rid, operation=operation, payload=payload))


class CardFixture:
    def __init__(self, scopes=('read', 'action'), count=2, *, db=None, anchor=None, owner='a', clock=None):
        self.db = db if db is not None else sqlite3.connect(':memory:', check_same_thread=False)
        self.anchor = anchor if anchor is not None else FakeProtectedAnchor()
        self.store = PhoneAdmissionStore(self.db, self.anchor)
        self.identity = ClientIdentity(name='fixture', user_id=owner)
        self.device, self.grant, self.session = 'device-'+owner, 'grant-'+owner, 'session-'+owner
        self.store.add_device(identity=self.identity, device_id=self.device, owner_id=owner, public_key=b'public', key_algorithm='test')
        self.store.add_grant(identity=self.identity, grant_id=self.grant, device_id=self.device, owner_id=owner, scopes=list(scopes))
        incarnation = self.store.login(identity=self.identity, session_id=self.session, grant_id=self.grant,
                                       owner_id=owner, now=1, expires_at=100)
        self.context = TrustedRequestContext(self.identity, owner, self.session, self.device, incarnation)
        self.source = SyntheticResultsSource([row(n) for n in range(1, count+1)])
        grant = PhoneResultCollectionGrantV1(owner, self.device, self.grant, str(uuid.uuid4()), tuple(uid(n) for n in range(1, 26)))
        self.results = PhoneRemoteResults(grant, self.source, clock=lambda: 2.)
        self.service = PhoneRemoteService(self.store, FakeContextVerifier(), FakeMediaAdapter(), clock=clock or FakeClockGate(2), results=self.results)
        self.registry = self.service.result_commands
        self.capability = self.registry.register(self.results, tuple(sorted(ACTIONS)))
        self.counter = 0
        self.view = None

    def close(self):
        self.store._drop_admissions(); self.db.close()

    def call(self, operation, payload, rid=None):
        self.counter += 1
        return self.service.handle(wire(operation, payload, rid or f'r{self.counter}'), self.context)

    def sync(self):
        snapshot = self.call('results.snapshot', {})
        assert snapshot['status'] == 'ok', snapshot
        p = snapshot['payload']
        response = self.call('results.view', {k:p[k] for k in ['generation', 'collection_epoch']})
        if response['status'] == 'ok': self.view = response['payload']
        return response

    def target(self, n=1):
        card = next(c for c in self.view['cards'] if c['result_id'] == uid(n))
        return {**{k:self.view[k] for k in ['generation', 'collection_epoch', 'view_id', 'view_revision']},
                'result_id':uid(n), 'result_revision':card['result_revision']}

    def action(self, operation, n=1, rid=None):
        result = self.call(operation, self.target(n), rid)
        if result['status'] == 'ok':self.view = result['payload']
        return result


class ResultCommandTests(unittest.TestCase):
    def setUp(self): self.f = CardFixture()
    def tearDown(self): self.f.close()
    def assertReason(self, value, reason):
        self.assertEqual(value['reason'], reason); self.assertEqual(value['payload'], {})

    def test_five_actions_mobile_only_noops_close_reopen(self):
        f=self.f;self.assertEqual(f.sync()['status'],'ok'); source=f.source.snapshot()
        self.assertEqual(f.action('results.select')['payload']['selected_result_id'],uid(1))
        revision=f.view['view_revision'];f.action('results.select');self.assertEqual(f.view['view_revision'],revision)
        self.assertTrue(f.action('results.pin')['payload']['cards'][0]['pinned'])
        self.assertFalse(f.action('results.unpin')['payload']['cards'][0]['pinned'])
        f.action('results.pin');f.action('results.close')
        self.assertIsNone(f.view['selected_result_id']);self.assertFalse(f.view['cards'][0]['open']);self.assertFalse(f.view['cards'][0]['pinned'])
        revision=f.view['view_revision'];f.action('results.close');self.assertEqual(f.view['view_revision'],revision)
        self.assertReason(f.action('results.select'),'request_conflict')
        f.action('results.reopen');self.assertEqual(f.view['selected_result_id'],uid(1));self.assertTrue(f.view['cards'][0]['open'])
        self.assertEqual(f.source.snapshot(),source)

    def test_other_visible_edit_or_appearance_requires_view_first(self):
        f=self.f;f.sync();prior=copy.deepcopy(f.view)
        for records in ([row(1),row(2,2)], [row(1),row(2,2),row(3)]):
            with self.subTest(records=records):
                f.source.replace(records);self.assertReason(f.action('results.pin'),'request_conflict')
                stored=next(iter(f.registry._views.values()));self.assertEqual(stored.payload,prior)
                f.sync();self.assertGreater(f.view['view_revision'],prior['view_revision']);prior=copy.deepcopy(f.view)
        self.assertEqual(f.action('results.pin')['status'],'ok')

    def test_capture_then_other_edit_conflicts_without_effect(self):
        f=self.f;f.sync();old=f.registry.prepare
        def prepare(*args):
            value=old(*args);f.source.replace([row(1),row(2,2)]);return value
        with patch.object(f.registry,'prepare',prepare):self.assertReason(f.action('results.pin'),'request_conflict')
        self.assertFalse(next(iter(f.registry._views.values())).payload['cards'][0]['pinned'])

    def test_post_effect_pre_ack_and_post_ack_source_change_withheld_terminal(self):
        for post_ack in (False,True):
            with self.subTest(post_ack=post_ack):
                f=CardFixture();self.addCleanup(f.close);f.sync();request=f.target();orig=f.service._service_commit
                @contextmanager
                def change():
                    with orig():
                        yield
                        if not post_ack:f.source.replace([row(1),row(2,2)])
                    if post_ack:f.source.replace([row(1),row(2,2)])
                with patch.object(f.service,'_service_commit',change):
                    first=f.call('results.pin',request,'lost')
                self.assertReason(first,'authority_unavailable')
                self.assertReason(f.call('results.pin',request,'lost'),'authority_unavailable')
                stored=next(iter(f.registry._views.values()));self.assertTrue(stored.payload['cards'][0]['pinned'])
                self.assertEqual(stored.payload['view_revision'],1)
                f.sync();self.assertTrue(f.view['cards'][0]['pinned'])

    def test_historical_replay_survives_ordinary_edit_and_appearance_without_effect(self):
        f=self.f;f.sync();request=f.target();receipt=f.call('results.pin',request,'same')
        f.source.replace([row(1,2),row(2),row(3)])
        f.sync();f.action('results.unpin')
        self.assertEqual(f.call('results.pin',request,'same'),receipt)
        self.assertFalse(next(iter(f.registry._views.values())).payload['cards'][0]['pinned'])
        self.assertReason(f.call('results.close',request,'same'),'request_conflict')

    def test_capability_lifecycle_effective_changes_invalidate_every_old_receipt(self):
        f=self.f;f.sync();request=f.target();receipt=f.call('results.select',request,'old')
        self.assertIs(f.registry.update(f.results,f.capability,tuple(sorted(ACTIONS))),f.capability)
        self.assertEqual(f.call('results.select',request,'old'),receipt)
        for operations in (('results.select',),tuple(sorted(ACTIONS))):
            previous=f.capability;f.capability=f.registry.update(f.results,previous,operations)
            self.assertEqual(f.capability.capability_id,previous.capability_id);self.assertEqual(f.capability.version,previous.version+1)
            self.assertReason(f.call('results.select',request,'old'),'not_authorized')
            self.assertReason(f.call('results.select',f.target()),'request_conflict')
            f.sync();self.assertEqual(f.action('results.select')['status'],'ok')
        f.capability=f.registry.revoke(f.results,f.capability)
        self.assertIs(f.registry.revoke(f.results,f.capability),f.capability)
        self.assertReason(f.action('results.select'),'not_authorized');f.sync();self.assertEqual(f.view['allowed_operations'],[])
        with self.assertRaises(ValueError):f.registry.update(f.results,f.capability,('results.select',))
        old=f.capability;f.capability=f.registry.replace(f.results,old,tuple(sorted(ACTIONS)))
        self.assertNotEqual(old.capability_id,f.capability.capability_id);self.assertEqual(f.capability.version,old.version+1)
        self.assertReason(f.call('results.select',request,'old'),'not_authorized')
        with self.assertRaises(ValueError):f.registry.revoke(f.results,old)
        with self.assertRaises(ValueError):f.registry.revoke(f.results,replace(f.capability))

    def test_capability_transition_blocks_through_ack_and_publication(self):
        f=self.f;f.sync();request=f.target();orig=f.service._service_commit;attempt=threading.Event();done=threading.Event();threads=[]
        def revoke():
            attempt.set();f.registry.revoke(f.results,f.capability);done.set()
        @contextmanager
        def delayed():
            with orig():yield
            t=threading.Thread(target=revoke);threads.append(t);t.start();self.assertTrue(attempt.wait(1));self.assertFalse(done.wait(.05))
        with patch.object(f.service,'_service_commit',delayed):result=f.call('results.pin',request,'ack')
        for t in threads:t.join(2);self.assertFalse(t.is_alive())
        self.assertEqual(result['status'],'ok');self.assertTrue(done.is_set())
        self.assertReason(f.call('results.pin',request,'ack'),'not_authorized')

    def test_capability_change_during_prepare_view_must_refresh(self):
        f=self.f;f.sync();old=f.registry.prepare
        def prepare(*args):
            value=old(*args);f.registry.update(f.results,f.capability,('results.select',));return value
        with patch.object(f.registry,'prepare',prepare):self.assertReason(f.action('results.select'),'request_conflict')

    def test_grant_replacement_cannot_rebind_capability(self):
        f=self.f;f.sync();old=f.results._grant
        f.results.replace_grant(replace(old,version=old.version+1));f.sync()
        self.assertEqual(f.view['allowed_operations'],[]);self.assertReason(f.action('results.pin'),'not_authorized')
        f.capability=f.registry.replace(f.results,f.capability,tuple(sorted(ACTIONS)));f.sync()
        self.assertEqual(f.action('results.pin')['status'],'ok')

    def test_unknown_protected_missing_and_foreign_targets_never_disclose(self):
        f=self.f;f.sync();target=f.target()
        for identity in (uid(3),str(uuid.uuid4())):
            with self.subTest(identity=identity):self.assertReason(f.call('results.pin',{**target,'result_id':identity}),'not_authorized')
        f.source.replace([row(1),row(2,2,'protected')]);self.assertReason(f.call('results.pin',target),'authority_unavailable')
        f.sync();self.assertEqual(len(f.view['cards']),1)
        f.source.replace([row(1),row(2,3,'unclassified')]);self.assertReason(f.action('results.pin'),'authority_unavailable')
        self.assertNotIn('title-',json.dumps([e for e in f.service._ledger.values() if e['operation'] not in {'results.snapshot','results.resume'}],default=str))

    def test_historical_visibility_loss_withholds_all_returned_ids(self):
        f=self.f;f.sync();request=f.target();f.call('results.pin',request,'receipt')
        f.source.replace([row(1),row(2,2,'protected')])
        self.assertReason(f.call('results.pin',request,'receipt'),'authority_unavailable')

    def test_hidden_activity_does_not_conflict_or_change_visible_state(self):
        f=self.f;f.source.replace([row(1),row(2),row(3,1,'protected')]);f.sync()
        f.source.replace([row(1),row(2),row(3,2,'protected'),row(30)])
        self.assertEqual(f.action('results.pin')['status'],'ok');self.assertEqual(len(f.view['cards']),2)

    def test_scope_intersection_and_capability_are_independent(self):
        for scopes in (('read',),('action',)):
            with self.subTest(scopes=scopes):
                f=CardFixture(scopes=scopes);self.addCleanup(f.close)
                if scopes==('read',):
                    self.assertEqual(f.sync()['status'],'ok');self.assertReason(f.action('results.pin'),'not_authorized')
                else:self.assertReason(f.call('results.view',{'generation':f.results.generation,'collection_epoch':f.results._epoch}),'not_authorized')
        f=self.f;f.sync();f.registry.revoke(f.results,f.capability);self.assertReason(f.action('results.pin'),'not_authorized')

    def test_pin_limit_and_version_overflow_do_not_mutate(self):
        f=CardFixture(count=25);self.addCleanup(f.close);f.sync()
        for n in range(1,21):self.assertEqual(f.action('results.pin',n)['status'],'ok')
        self.assertReason(f.action('results.pin',21),'request_capacity')
        self.assertEqual(f.action('results.pin',1)['status'],'ok')
        view=next(iter(f.registry._views.values()));view.payload['view_revision']=MAX_INT;f.view=copy.deepcopy(view.payload)
        self.assertReason(f.action('results.unpin',1),'authority_unavailable');self.assertTrue(view.payload['cards'][0]['pinned'])
        slot=f.registry._slot(f.results);slot.capability=replace(slot.capability,version=MAX_INT)
        with self.assertRaises(ValueError):f.registry.revoke(f.results,slot.capability)

    def test_shared_facades_use_one_registry_and_reject_conflicting_projector(self):
        f=self.f;f.sync();other=PhoneRemoteService(f.store,FakeContextVerifier(),FakeMediaAdapter(),results=f.results)
        self.assertIs(other.result_commands,f.registry)
        different=PhoneRemoteResults(f.results._grant,f.source)
        with self.assertRaises(TypeError):PhoneRemoteService(f.store,FakeContextVerifier(),FakeMediaAdapter(),results=different)
        request=wire('results.pin',f.target(),'both');receipt=f.service.handle(request,f.context)
        self.assertEqual(other.handle(request,f.context),receipt)

    def test_effect_then_raise_and_reentry_are_not_reexecuted(self):
        f=self.f;f.sync();target=f.target();orig=f.registry.apply;calls=[]
        def fail(*args):
            calls.append(1);orig(*args);raise RuntimeError('synthetic failure')
        with patch.object(f.registry,'apply',fail):self.assertReason(f.call('results.pin',target,'uncertain'),'authority_unavailable')
        self.assertReason(f.call('results.pin',target,'uncertain'),'authority_unavailable')
        self.assertEqual(len(calls),1);self.assertTrue(next(iter(f.registry._views.values())).payload['cards'][0]['pinned'])

    def test_malformed_requests_leave_complete_state_unchanged(self):
        f=self.f;f.sync();target=f.target();before=copy.deepcopy(f.service._ledger);view=copy.deepcopy(f.view)
        for changes in ({'view_revision':0.0},{'view_revision':True},{'result_revision':'1'},
                        {'owner_id':'b'},{'result_id':'wrong'},{'action':'shell'}):
            with self.subTest(changes=changes):self.assertReason(f.call('results.pin',{**target,**changes}),'malformed_request')
        self.assertEqual(f.service._ledger,before);self.assertEqual(next(iter(f.registry._views.values())).payload,view)

    def test_reentrant_effect_is_uncertain_and_shared_facade_cannot_retry(self):
        f=self.f;f.sync();target=f.target();original=f.registry.apply
        def reenter(*args):
            effect=original(*args)
            nested=f.call('results.close',target,'nested')
            self.assertEqual(nested['reason'],'authority_unavailable')
            return effect
        with patch.object(f.registry,'apply',reenter):
            self.assertReason(f.call('results.pin',target,'outer'),'authority_unavailable')
        self.assertTrue(next(iter(f.registry._views.values())).payload['cards'][0]['pinned'])
        self.assertReason(f.call('results.pin',target,'outer'),'authority_unavailable')
        self.assertTrue(f.service._runtime.card_authority_failed)

    def test_shared_runtime_two_owners_identical_ids_are_isolated(self):
        a=self.f;b=CardFixture(db=a.db,anchor=a.anchor,owner='b',clock=a.service.clock)
        inc=a.store.login(identity=a.identity,session_id=a.session,grant_id=a.grant,owner_id='a',now=1,expires_at=100)
        a.context=replace(a.context,login_incarnation=inc)
        a.sync();b.sync();before=copy.deepcopy(b.view)
        target=a.target();self.assertEqual(a.call('results.pin',target,'identical')['status'],'ok')
        response=b.call('results.close',b.target(),'identical')
        self.assertEqual(response['status'],'ok');self.assertFalse(response['payload']['cards'][0]['open'])
        a.registry.revoke(a.results,a.capability)
        self.assertEqual(b.call('results.close',b.target(),'identical'),response)
        self.assertEqual(b.view,before)
        self.assertNotEqual(a.view['view_id'],b.view['view_id'])

    def test_expired_binding_retires_view_without_evicting_receipt(self):
        f=self.f;f.sync();self.assertEqual(len(f.registry._views),1)
        f.service.clock.set_time(101)
        self.assertReason(f.action('results.pin'),'not_authorized')
        self.assertEqual(f.registry._views,{});self.assertTrue(f.service._ledger)

    def test_all_source_changes_at_capture_effect_ack_and_history(self):
        for changed in ([row(1,2),row(2)],[row(1),row(2,2)],[row(1),row(2),row(3)]):
            for boundary in ('capture','effect','ack','history'):
                with self.subTest(changed=changed,boundary=boundary):
                    f=CardFixture();self.addCleanup(f.close);f.sync();target=f.target()
                    if boundary=='capture':
                        original=f.registry.prepare
                        def captured(*args):
                            value=original(*args);f.source.replace(changed);return value
                        with patch.object(f.registry,'prepare',captured):result=f.call('results.pin',target,'race')
                        self.assertReason(result,'request_conflict')
                        self.assertFalse(next(iter(f.registry._views.values())).payload['cards'][0]['pinned'])
                    elif boundary in ('effect','ack'):
                        original=f.service._service_commit
                        @contextmanager
                        def commit():
                            with original():
                                yield
                                if boundary=='effect':f.source.replace(changed)
                            if boundary=='ack':f.source.replace(changed)
                        with patch.object(f.service,'_service_commit',commit):result=f.call('results.pin',target,'race')
                        self.assertReason(result,'authority_unavailable')
                        stored=copy.deepcopy(next(iter(f.registry._views.values())).payload)
                        self.assertTrue(stored['cards'][0]['pinned'])
                        self.assertEqual(f.call('results.pin',target,'race'),result)
                        self.assertEqual(next(iter(f.registry._views.values())).payload,stored)
                    else:
                        result=f.call('results.pin',target,'race');f.source.replace(changed)
                        self.assertEqual(f.call('results.pin',target,'race'),result)

    def test_returned_dictionaries_cannot_mutate_owned_view_or_receipts(self):
        f=self.f;f.sync();target=f.target();first=f.call('results.pin',target,'immutable')
        expected=copy.deepcopy(first)
        first['payload']['cards'][0]['pinned']=False
        first['payload']['allowed_operations'].clear()
        second=f.call('results.pin',target,'immutable');self.assertEqual(second,expected)
        second['payload']['cards'].clear()
        self.assertEqual(f.call('results.pin',target,'immutable'),expected)
        self.assertTrue(next(iter(f.registry._views.values())).payload['cards'][0]['pinned'])

    def test_capability_lifecycle_invalidates_cached_view_and_action_in_all_orders(self):
        for transition in ('narrow','expand','revoke','replace'):
            for boundary in ('before','capture','history'):
                with self.subTest(transition=transition,boundary=boundary):
                    f=CardFixture();self.addCleanup(f.close)
                    if transition=='expand':f.capability=f.registry.update(f.results,f.capability,('results.pin',))
                    f.sync();target=f.target();read={k:f.view[k] for k in ('generation','collection_epoch')}
                    read_receipt=f.call('results.view',read,'read')
                    def change():
                        if transition=='revoke':f.registry.revoke(f.results,f.capability)
                        elif transition=='replace':f.registry.replace(f.results,f.capability,tuple(sorted(ACTIONS)))
                        else:f.registry.update(f.results,f.capability,('results.pin',) if transition=='narrow' else tuple(sorted(ACTIONS)))
                    if boundary=='history':
                        first=f.call('results.pin',target,'old');self.assertEqual(first['status'],'ok');change()
                        self.assertReason(f.call('results.pin',target,'old'),'not_authorized')
                    elif boundary=='before':
                        change();self.assertReason(f.call('results.pin',target),'not_authorized' if transition=='revoke' else 'request_conflict')
                    else:
                        original=f.registry.prepare
                        def capture(*args):
                            prepared=original(*args);change();return prepared
                        with patch.object(f.registry,'prepare',capture):
                            self.assertReason(f.call('results.pin',target),'not_authorized' if transition=='revoke' else 'request_conflict')
                    self.assertReason(f.call('results.view',read,'read'),'authority_unavailable')
                    self.assertEqual(read_receipt['status'],'ok')

    def test_classification_loss_before_effect_during_ack_and_after_done(self):
        for boundary in ('capture','ack','history'):
            for target in (1,2):
                with self.subTest(boundary=boundary,target=target):
                    f=CardFixture();self.addCleanup(f.close);f.sync();request=f.target()
                    def tighten():f.source.replace([row(n,2 if n==target else 1,'protected' if n==target else 'ordinary') for n in (1,2)])
                    if boundary=='capture':
                        original=f.registry.prepare
                        def captured(*args):
                            value=original(*args);tighten();return value
                        with patch.object(f.registry,'prepare',captured):result=f.call('results.pin',request,'private')
                        self.assertNotEqual(result['status'],'ok')
                    elif boundary=='ack':
                        original=f.service._service_commit
                        @contextmanager
                        def commit():
                            with original():yield
                            tighten()
                        with patch.object(f.service,'_service_commit',commit):result=f.call('results.pin',request,'private')
                        self.assertReason(result,'authority_unavailable')
                    else:
                        self.assertEqual(f.call('results.pin',request,'private')['status'],'ok');tighten()
                        result=f.call('results.pin',request,'private');self.assertReason(result,'authority_unavailable')
                    self.assertEqual(result['payload'],{})
                    self.assertNotEqual(f.call('results.pin',request,'private')['status'],'ok')
                    f.sync();self.assertNotIn(uid(target),[c['result_id'] for c in f.view['cards']])

    def test_foreign_binding_cannot_retire_another_view(self):
        f=self.f;f.sync();saved=copy.deepcopy(next(iter(f.registry._views.values())).payload)
        foreign=replace(f.store.current_binding(identity=f.identity,owner_id='a',session_id=f.session,
            device_id=f.device,login_incarnation=f.context.login_incarnation,now=2),owner_id='b')
        from jarvis.bot.phone_remote_result_commands import CommandDenied
        with self.assertRaises(CommandDenied):f.registry.prepare(f.results,foreign)
        self.assertEqual(next(iter(f.registry._views.values())).payload,saved)

    def test_revocation_between_prepare_and_commit_changes_no_mobile_state(self):
        for kind in ('signout','grant','feature'):
            with self.subTest(kind=kind):
                f=CardFixture();self.addCleanup(f.close);f.sync();prior=copy.deepcopy(f.view)
                original=f.registry.prepare
                def prepared(*args):
                    value=original(*args)
                    if kind=='feature':f.service.enabled=False
                    elif kind=='signout':f.store.revoke_session(identity=f.identity,session_id=f.session,owner_id='a')
                    else:f.store.revoke_grant(identity=f.identity,grant_id=f.grant,owner_id='a')
                    return value
                with patch.object(f.registry,'prepare',prepared):
                    self.assertReason(f.action('results.pin'),'feature_off' if kind=='feature' else 'not_authorized')
                if kind=='feature':self.assertEqual(next(iter(f.registry._views.values())).payload,prior)
                else:self.assertEqual(f.registry._views,{})

    def test_two_logins_same_result_and_request_ids_have_distinct_views(self):
        f=self.f;f.sync();first_context=f.context;target=f.target()
        first=f.call('results.pin',target,'same-login-id');self.assertEqual(first['status'],'ok')
        inc=f.store.login(identity=f.identity,session_id='second-session',grant_id=f.grant,owner_id='a',now=1,expires_at=100)
        f.context=replace(f.context,session_id='second-session',login_incarnation=inc)
        f.sync();self.assertNotEqual(f.view['view_id'],first['payload']['view_id'])
        self.assertFalse(f.view['cards'][0]['pinned'])
        second=f.call('results.close',f.target(),'same-login-id');self.assertEqual(second['status'],'ok')
        self.assertFalse(second['payload']['cards'][0]['open'])
        f.context=first_context
        self.assertEqual(f.call('results.pin',target,'same-login-id'),first)

    def test_each_effective_capability_change_waits_for_first_publication(self):
        for transition in ('narrow','expand','replace'):
            with self.subTest(transition=transition):
                f=CardFixture();self.addCleanup(f.close)
                if transition=='expand':f.capability=f.registry.update(f.results,f.capability,('results.pin',))
                f.sync();target=f.target();attempt=threading.Event();done=threading.Event();threads=[]
                original=f.service._service_commit
                def change():
                    attempt.set()
                    if transition=='replace':f.registry.replace(f.results,f.capability,tuple(sorted(ACTIONS)))
                    else:f.registry.update(f.results,f.capability,('results.pin',) if transition=='narrow' else tuple(sorted(ACTIONS)))
                    done.set()
                @contextmanager
                def commit():
                    with original():yield
                    worker=threading.Thread(target=change);threads.append(worker);worker.start()
                    self.assertTrue(attempt.wait(1));self.assertFalse(done.is_set())
                with patch.object(f.service,'_service_commit',commit):first=f.call('results.pin',target,'inflight')
                for worker in threads:worker.join(2);self.assertFalse(worker.is_alive())
                self.assertEqual(first['status'],'ok');self.assertTrue(done.is_set())
                self.assertReason(f.call('results.pin',target,'inflight'),'not_authorized')

    def test_view_capacity_never_evicts_live_views_and_retires_ended_binding(self):
        f=self.f;f.sync();original=copy.deepcopy(f.view);first_context=f.context
        for n in range(1,128):
            session=f'capacity-{n}'
            inc=f.store.login(identity=f.identity,session_id=session,grant_id=f.grant,owner_id='a',now=1,expires_at=100)
            f.context=replace(f.context,session_id=session,login_incarnation=inc);f.sync()
        self.assertEqual(len(f.registry._views),128)
        inc=f.store.login(identity=f.identity,session_id='capacity-over',grant_id=f.grant,owner_id='a',now=1,expires_at=100)
        f.context=replace(f.context,session_id='capacity-over',login_incarnation=inc)
        snapshot=f.call('results.snapshot',{})['payload']
        payload={k:snapshot[k] for k in ('generation','collection_epoch')}
        self.assertReason(f.call('results.view',payload),'request_capacity')
        self.assertEqual(len(f.registry._views),128)
        self.assertIn(original,[v.payload for v in f.registry._views.values()])
        f.store.revoke_session(identity=f.identity,session_id=first_context.session_id,owner_id='a')
        f.service.notify_revocation();self.assertEqual(len(f.registry._views),127)
        self.assertEqual(f.call('results.view',payload)['status'],'ok')
        self.assertEqual(len(f.registry._views),128)

    def test_review_ack_reentry_never_publishes_or_promotes_historical_receipt(self):
        for historical in (False,True):
            with self.subTest(historical=historical):
                f=CardFixture();self.addCleanup(f.close);f.sync();target=f.target()
                if historical:self.assertEqual(f.call('results.pin',target,'outer')['status'],'ok')
                original=f.service._service_commit
                @contextmanager
                def reentered():
                    with original():yield
                    self.assertReason(f.call('results.close',target,'nested'),'authority_unavailable')
                with patch.object(f.service,'_service_commit',reentered):
                    self.assertReason(f.call('results.pin',target,'outer'),'authority_unavailable')
                self.assertReason(f.call('results.pin',target,'outer'),'authority_unavailable')
                entry=next(e for (b,r),e in f.service._ledger.items() if r=='outer')
                self.assertEqual(entry['state'],'uncertain');self.assertIsNone(entry['receipt'])

    def test_review_collection_uuid_replacement_preserves_unique_slot(self):
        f=self.f;f.sync();grant=replace(f.results._grant,version=2,collection_id=uid(999))
        f.results.replace_grant(grant)
        f.capability=f.registry.replace(f.results,f.capability,tuple(sorted(ACTIONS)))
        f.sync();f.action('results.pin')
        self.assertIs(f.registry.attach(f.results),f.registry);self.assertEqual(len(f.registry._slots),1)
        duplicate=PhoneRemoteResults(grant,f.source,clock=lambda:2.)
        with self.assertRaises(TypeError):
            PhoneRemoteService(f.store,FakeContextVerifier(),FakeMediaAdapter(),results=duplicate)
        self.assertEqual(len(f.registry._slots),1)
        self.assertTrue(f.view['cards'][0]['pinned'])

    def test_review_stale_context_cannot_retire_reused_session_survivor(self):
        f=self.f;f.sync();old=f.context
        f.store.revoke_session(identity=f.identity,session_id=f.session,owner_id='a')
        incarnation=f.store.login(identity=f.identity,session_id=f.session,grant_id=f.grant,owner_id='a',now=1,expires_at=100)
        f.context=replace(f.context,login_incarnation=incarnation);f.sync();f.action('results.pin')
        survivor=f.context;view=copy.deepcopy(f.view);f.context=old
        self.assertReason(f.call('results.pin',f.target()),'not_authorized')
        f.context=survivor
        self.assertEqual(f.action('results.unpin')['status'],'ok')
        self.assertEqual(f.view['view_id'],view['view_id']);self.assertEqual(f.view['view_revision'],view['view_revision']+1)

    def test_review_collection_move_collision_is_atomic_in_both_orders(self):
        for move_first in (True,False):
            with self.subTest(move_first=move_first):
                f=CardFixture();self.addCleanup(f.close);f.sync()
                old=f.results._grant;replacement=replace(old,version=2,collection_id=uid(998))
                duplicate=PhoneRemoteResults(replacement,f.source,clock=lambda:2.)
                if move_first:
                    f.results.replace_grant(replacement)
                    with self.assertRaises(TypeError):f.registry.attach(duplicate)
                    self.assertIs(f.results._grant,replacement)
                else:
                    f.registry.attach(duplicate)
                    before=copy.deepcopy(f.view)
                    with self.assertRaises(TypeError):f.results.replace_grant(replacement)
                    self.assertIs(f.results._grant,old)
                    self.assertEqual(next(iter(f.registry._views.values())).payload,before)
                self.assertEqual(len(f.registry._slots),len({f.registry._slot_key(s.projector) for s in f.registry._slots.values()}))
                from jarvis.bot.phone_remote_result_commands import PhoneResultCommandRegistry
                with self.assertRaises(TypeError):PhoneResultCommandRegistry(threading.RLock()).attach(f.results)

    def test_review_swallowed_publication_reentry_is_terminal(self):
        f=self.f;f.sync();target=f.target();original=f.registry.publication
        def publication(*args,**kwargs):
            receipt=original(*args,**kwargs)
            self.assertReason(f.call('results.close',target,'nested-publication'),'authority_unavailable')
            return receipt
        with patch.object(f.registry,'publication',publication):
            self.assertReason(f.call('results.pin',target,'outer-publication'),'authority_unavailable')
        entry=next(e for (b,r),e in f.service._ledger.items() if r=='outer-publication')
        self.assertEqual(entry['state'],'uncertain');self.assertIsNone(entry['receipt'])

    def test_review_publication_denial_prioritizes_terminal_latch(self):
        for terminal,historical in ((False,False),(True,False),(True,True)):
            with self.subTest(terminal=terminal,historical=historical):
                f=CardFixture();self.addCleanup(f.close);f.sync();target=f.target()
                if historical:self.assertEqual(f.call('results.pin',target,'combined')['status'],'ok')
                original=f.registry.publication;calls=[]
                def publication(*args,**kwargs):
                    calls.append(None)
                    if len(calls)==(2 if historical else 1):
                        if terminal:self.assertReason(f.call('results.close',target,'nested-denial'),'authority_unavailable')
                        f.source.replace([row(1),row(2,2,'protected' if historical else 'ordinary')])
                    return original(*args,**kwargs)
                with patch.object(f.registry,'publication',publication):
                    self.assertReason(f.call('results.pin',target,'combined'),'authority_unavailable')
                entry=next(e for (b,r),e in f.service._ledger.items() if r=='combined')
                self.assertEqual(entry['state'],'uncertain' if terminal else 'withheld')
                if terminal:self.assertIsNone(entry['receipt'])
                else:
                    self.assertFalse(f.service._runtime.card_authority_failed)
                    self.assertEqual(f.call('session.status',{})['status'],'ok')
                self.assertReason(f.call('results.pin',target,'combined'),'authority_unavailable')
