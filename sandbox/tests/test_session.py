from pathlib import Path
import hashlib
import io
import json
import subprocess
import tarfile
import tempfile
from threading import Event, Thread
import unittest
from unittest.mock import patch

from sandbox.artifacts import Candidate, File, SandboxError
from sandbox.control import Controller
from sandbox.profiles import Profile
from sandbox.session import Session
from test_files import rpc


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.c = Controller(self.root, '/missing/tart', '/missing/softnet')
        self.profile = Profile('test', (), (), (('required', ('check',)),))
        self.events = []
        self.guests = {}
        self.fail_hydration = False
        self.cancel_in_check = False
        for name in ('start', 'stop', 'destroy', 'rpc', 'reconcile', 'cancel'):
            p = patch.object(self.c, name, side_effect=getattr(self, name))
            p.start(); self.addCleanup(p.stop)
        self.session = Session.create(self.c, self, self, self.profile, lambda p: p == 'app.py',
            image_id='image', repo=self.root, ref='a' * 40, repository='owner/repo', base_branch='main',
            kind='selfedit', goal='Update the app')

    def create(self, image, repo, ref, profile, **kwargs):
        task = kwargs['task_id']
        inputs = self.c.home / 'tasks' / task / 'input'
        inputs.mkdir(parents=True)
        target = inputs / 'source.tar'
        with tarfile.open(target, 'w') as tar:
            item = tarfile.TarInfo('app.py'); item.size = 8; item.mode = 0o644
            tar.addfile(item, io.BytesIO(b'original'))
        self.c.save(task, {'vm': 'mortimer-' + task, 'status': 'created', 'hydrated': False,
            'source_commit': ref, 'source_sha256': hashlib.sha256(target.read_bytes()).hexdigest()})
        guest = self.root / ('guest-' + task); guest.mkdir(); (guest / 'app.py').write_bytes(b'original')
        self.guests[task] = guest
        return task

    def reconcile(self, task): return self.c.read(task)

    def start(self, task, **kwargs):
        self.events.append(('start', task))
        state = self.c.read(task); state.update(status='running', network='offline'); self.c.save(task, state)
    def stop(self, task):
        self.events.append(('stop', task))
        state = self.c.read(task); state['status'] = 'stopped'; self.c.save(task, state)
    def destroy(self, task):
        self.events.append(('destroy', task))
        state = self.c.read(task); state['status'] = 'deleted'; self.c.save(task, state)
    def cancel(self, task):
        self.events.append(('cancel', task))
        if self.c.read(task)['status'] in {'running', 'provisioning'}:
            self.stop(task)
    def wait_ready(self, task): pass
    def hydrate(self, task):
        if self.fail_hydration:
            raise SandboxError('hydration failed')
        state = self.c.read(task); state.update(hydrated=True, worker='mortimer-dev'); self.c.save(task, state)
    def rpc(self, task, request): return rpc.dispatch(self.guests[task], request)
    def verify(self, files, *args):
        candidate = files.freeze()
        self.stop(files.task)
        if self.cancel_in_check:
            self.session.cancel()
            raise SandboxError('cancelled during verification')
        return {'passed': True, 'candidate': candidate.fingerprint, 'attempt': 'b' * 32,
            'verification_task': 'c' * 12, 'checks': [{'name': 'required', 'passed': True, 'returncode': 0, 'seconds': 1}]}

    def test_resume_preserves_edits_and_requires_fresh_readiness_after_restart(self):
        self.session.propose_edit('app.py', 'saved edit', 'keep it')
        task = self.session.status()['task']
        self.assertTrue(self.session.status()['ready'])
        self.stop(task)
        self.assertFalse(self.session.status()['ready'])
        self.assertTrue(self.session.resume()['ready'])
        self.assertEqual(self.session.read_file('app.py')['content'], 'saved edit')
        self.c._ready_tasks.clear()  # A newly constructed host runtime trusts no cached readiness.
        self.assertFalse(self.session.status()['ready'])
        self.session.resume()
        self.assertTrue(self.session.status()['ready'])
        self.assertEqual(len(self.session.status()['proposals']), 1)

    def test_resume_invalidates_an_abandoned_verification(self):
        self.session.propose_edit('app.py', 'saved edit', 'keep it')
        state = self.session._read(); state.update(phase='validating', checks=[{'ok':True}]); self.session._save(state)
        self.session.resume()
        self.assertEqual(self.session.status()['phase'], 'validation_failed')
        self.assertEqual(self.session.status()['checks'], [])
        self.assertIn('interrupted', self.session.status()['recovery_notice'])
        self.assertIsNone(self.session._files(state).status()['verification'])

    def test_resume_finishes_cancellation_interrupted_after_durable_marker(self):
        task = self.session.status()['task']
        (self.session.directory / 'cancelled.json').write_text('{"requested_at": 1}')

        with self.assertRaisesRegex(SandboxError, 'session has ended'):
            self.session.resume()

        self.assertIn(('cancel', task), self.events)
        self.assertEqual(self.c.read(task)['status'], 'stopped')
        self.assertEqual(self.session._read()['phase'], 'cancelled')

    def test_reopen_reads_same_guest_and_preserves_validation_invalidation(self):
        self.session.propose_edit('app.py', 'updated', 'needed')
        self.assertTrue(self.session.validate()['ok'])
        reopened = Session(self.c, self, self, self.profile, lambda p: p == 'app.py', self.session.id)
        self.assertEqual(reopened.read_file('app.py')['content'], 'updated')
        reopened.propose_edit('app.py', 'second update', 'follow-up')
        self.assertEqual(reopened.status()['phase'], 'editing')
        self.assertEqual(reopened.status()['checks'], [])
        self.assertIn('-original', reopened.status()['proposals'][0]['diff'])
        self.assertEqual(len(reopened.status()['proposals']), 1)
        with self.assertRaises(SandboxError): reopened.propose_edit('secret.env', 'data', 'denied')
        self.assertFalse((self.root / 'app.py').exists())

    def test_baseline_text_reads_the_base_snapshot_without_the_guest_or_the_policy(self):
        # W8: a human-only file is outside the edit policy, yet its base
        # bytes are needed to show it read-only and to draft a proposal.
        self.session.propose_edit('app.py', 'edited in the guest', 'change')
        denied = Session(self.c, self, self, self.profile, lambda p: False, self.session.id)
        calls = len(self.events)
        with patch.object(self.c, 'rpc', side_effect=AssertionError('guest consulted')):
            base = denied.baseline_text('app.py')
            missing = denied.baseline_text('docs/new.md')
            with self.assertRaises(SandboxError): denied.baseline_text('.env')
            with self.assertRaises(SandboxError): denied.baseline_text('data/jarvis.db')
        self.assertEqual((base['exists'], base['content'], base['mode']), (True, 'original', 0o644))
        self.assertEqual((missing['exists'], missing['content']), (False, ''))
        self.assertEqual(len(self.events), calls)
        with self.assertRaises(SandboxError): denied.read_file('app.py')
        self.session.revert()
        with self.assertRaises(SandboxError): denied.baseline_text('app.py')

    def test_cancel_interrupts_validation_without_waiting_for_session_lock(self):
        self.cancel_in_check = True
        with self.assertRaises(SandboxError): self.session.validate()
        self.assertEqual(self.session.status()['phase'], 'cancelled')
        with self.assertRaises(SandboxError): self.session.read_file('app.py')
        self.assertEqual(self.c.read(self.session.status()['task'])['status'], 'stopped')

    def test_failed_setup_remains_owned_and_stops_vm(self):
        self.fail_hydration = True
        with self.assertRaises(SandboxError):
            Session.create(self.c, self, self, self.profile, lambda p: True, image_id='image', repo=self.root,
                ref='a' * 40, repository='owner/repo', base_branch='main', kind='app-build', goal='New application')
        records = [json.loads(p.read_bytes()) for p in (self.root / 'sessions').glob('*/session.json')]
        failed = next(r for r in records if r['phase'] == 'setup_failed')
        self.assertEqual(self.c.read(failed['task'])['status'], 'stopped')

    def test_publication_failure_can_be_retried_and_blocks_further_edits(self):
        class Publisher:
            count = 0
            def publish(inner, files, *args, **kwargs):
                (files.directory / 'publication.json').write_text('{}')
                inner.count += 1
                if inner.count == 1: raise SandboxError('lost response')
                return {'ok': True, 'number': 1}
        publisher = Publisher()
        with self.assertRaises(SandboxError): self.session.submit(publisher, 'Title', 'Body')
        self.assertEqual(self.session.status()['phase'], 'publication_pending')
        with self.assertRaises(SandboxError): self.session.propose_edit('app.py', 'late edit', 'denied')
        self.assertTrue(self.session.submit(publisher, 'Title', 'Body')['ok'])
        self.assertEqual(self.session.status()['phase'], 'published')
        self.assertEqual(self.c.read(self.session.status()['task'])['status'], 'stopped')

    def test_interrupted_publication_recovers_after_reopening_session(self):
        # Model a host crash after the session journal enters publishing and
        # the publisher persists its idempotency record, but before the result
        # is saved back into session.json.
        task = self.session.status()['task']
        (self.c.task_dir(task) / 'publication.json').write_text('{}')
        state = self.session._read()
        state['phase'] = 'publishing'
        self.session._save(state)

        reopened = Session(self.c, self, self, self.profile, lambda p: p == 'app.py', self.session.id)
        self.assertTrue(reopened.resume()['ready'])
        self.assertEqual(reopened.status()['phase'], 'publication_pending')

        class Publisher:
            def publish(inner, files, *args, **kwargs):
                self.assertTrue((files.directory / 'publication.json').is_file())
                return {'ok': True, 'number': 17, 'recovered': True}

        result = reopened.submit(Publisher(), 'Title', 'Body')
        self.assertEqual(result['number'], 17)
        self.assertTrue(result['recovered'])
        self.assertEqual(reopened.status()['phase'], 'published')
        self.assertEqual(reopened.status()['publication']['number'], 17)

    def test_submit_preflight_holds_session_lock_through_publication(self):
        self.session.propose_edit('app.py', 'creator candidate', 'draft skill')
        self.assertTrue(self.session.validate()['ok'])
        preflight_entered = Event()
        edit_attempted = Event()
        edit_finished = Event()
        edit_result = []

        def late_edit():
            self.assertTrue(preflight_entered.wait(2))
            edit_attempted.set()
            try:
                edit_result.append(self.session.propose_edit('app.py', 'late edit', 'race'))
            except SandboxError:
                edit_result.append({'ok': False})
            finally:
                edit_finished.set()

        editor = Thread(target=late_edit)
        editor.start()

        def preflight(files, state):
            self.assertEqual(state['phase'], 'validated')
            self.assertEqual(files.frozen().fingerprint, state['candidate'])
            preflight_entered.set()
            self.assertTrue(edit_attempted.wait(2))
            self.assertFalse(edit_finished.wait(0.05))

        class Publisher:
            def publish(inner, files, *args, **kwargs):
                self.assertFalse(edit_finished.is_set())
                (files.directory / 'publication.json').write_text('{}')
                return {'ok': True, 'number': 1}

        result = self.session.submit(Publisher(), 'Title', 'Body', preflight=preflight)
        editor.join(2)

        self.assertFalse(editor.is_alive())
        self.assertTrue(result['ok'])
        self.assertEqual(edit_result, [{'ok': False}])
        self.assertEqual(self.session.status()['phase'], 'published')

    def test_revert_is_idempotent_and_retains_record(self):
        self.assertTrue(self.session.revert()['ok'])
        self.assertTrue(self.session.revert()['ok'])
        self.assertEqual(self.session.status()['phase'], 'reverted')
        self.assertEqual(sum(e[0] == 'destroy' for e in self.events), 1)
        with self.assertRaises(SandboxError): self.session.read_file('app.py')


if __name__ == '__main__': unittest.main()
