from pathlib import Path
import hashlib
import io
import json
import subprocess
import tarfile
import tempfile
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
        for name in ('start', 'stop', 'destroy', 'rpc', 'reconcile'):
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

    def test_revert_is_idempotent_and_retains_record(self):
        self.assertTrue(self.session.revert()['ok'])
        self.assertTrue(self.session.revert()['ok'])
        self.assertEqual(self.session.status()['phase'], 'reverted')
        self.assertEqual(sum(e[0] == 'destroy' for e in self.events), 1)
        with self.assertRaises(SandboxError): self.session.read_file('app.py')


if __name__ == '__main__': unittest.main()
