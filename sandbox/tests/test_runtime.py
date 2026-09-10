from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from sandbox.artifacts import SandboxError
from sandbox.control import Controller
from sandbox.durable import atomic_json
from sandbox.profiles import MORTIMER
from sandbox.runtime import Runtime

class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.c = Controller(self.home, '/missing/tart', '/missing/softnet')
        self.runtime = Runtime(self.c, {'mortimer': 'a' * 64})
        self.runtime.images = Mock()
        self.runtime.source = Mock()
        self.runtime.source.fetch.return_value = (self.home, 'b' * 40)
        self.allowed = lambda p: True

    def start(self):
        return self.runtime.start('owner/repo', 'selfedit', 'main', 'host-token', 'mortimer', self.allowed, 'Goal')

    def test_session_reference_is_saved_before_vm_setup_and_survives_failure(self):
        identifier = 'c' * 32
        def create(*args, **kwargs):
            directory = self.home / 'sessions' / identifier; directory.mkdir(parents=True)
            atomic_json(directory / 'session.json', {'phase': 'setup_failed', 'task': None})
            kwargs['on_created'](Mock(id=identifier))
            raise SandboxError('VM setup failed')
        with patch('sandbox.runtime.Session.create', side_effect=create):
            with self.assertRaises(SandboxError): self.start()
        reopened = Runtime(self.c, {'mortimer': 'a' * 64}).active('OWNER/REPO', 'selfedit', self.allowed)
        self.assertEqual(reopened.id, identifier)
        self.assertEqual(reopened.status()['phase'], 'setup_failed')
        for path in self.home.rglob('*.json'):
            self.assertNotIn('host-token', path.read_text())

    def test_active_workspace_and_missing_image_refuse_before_source_fetch(self):
        with patch.object(self.runtime, 'active', return_value=Mock(status=lambda: {'phase': 'validating'})):
            with self.assertRaises(SandboxError): self.start()
        self.runtime.source.fetch.assert_not_called()
        self.runtime.configured_images.clear()
        with self.assertRaises(SandboxError): self.start()
        self.runtime.source.fetch.assert_not_called()

    def test_unconfigured_runtime_fails_without_creating_a_checkout(self):
        with patch.dict('os.environ', {'MORTIMER_SANDBOX_HOME': str(self.home / 'absent')}):
            with self.assertRaises(SandboxError): Runtime.configured()
        self.assertFalse((self.home / 'absent').exists())

if __name__ == '__main__': unittest.main()
