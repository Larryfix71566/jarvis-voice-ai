import unittest
from unittest.mock import Mock
from sandbox.artifacts import SandboxError
from sandbox.workspace import SandboxWorkspace

class WorkspaceAdapterTests(unittest.TestCase):
    def setUp(self):
        self.session = Mock(id='a' * 32)
        self.state = {'phase': 'editing', 'branch': 'mortimer/selfedit/test', 'goal': 'Update app',
                      'task': 'b' * 12, 'ref': 'c' * 40, 'proposals': []}
        self.session.status.side_effect = lambda: dict(self.state)
        self.runtime = Mock()
        self.runtime.active.return_value = self.session
        self.runtime.start.return_value = self.session
        self.factory = Mock(return_value=self.runtime)
        self.allowed = lambda p: p == 'app.py'
        self.workspace = self.make()

    def make(self):
        return SandboxWorkspace(repository=lambda: 'owner/repo', token=lambda: 'host-only-token',
            kind='selfedit', profile='mortimer', base_branch=lambda: 'main', allowed=self.allowed,
            runtime_factory=self.factory)

    def test_constructor_does_not_boot_or_access_credentials(self):
        self.factory.assert_not_called()
        self.runtime.start.assert_not_called()
        self.assertTrue(self.workspace.start_session('Update app', 'run-id')['ok'])
        self.runtime.start.assert_called_once_with('owner/repo', 'selfedit', 'main', 'host-only-token',
            'mortimer', self.allowed, 'Update app', 'run-id')
        self.assertIsNone(self.workspace.work_root)

    def test_reopened_adapter_uses_persistent_session_for_every_operation(self):
        reopened = self.make()
        self.session.read_file.return_value = {'ok': True, 'content': 'from VM'}
        self.assertEqual(reopened.read_file('app.py')['content'], 'from VM')
        reopened.propose_edit('app.py', 'new', 'reason', 'visible change')
        self.session.propose_edit.assert_called_once_with('app.py', 'new', 'reason', 'visible change')
        reopened.validate(); self.session.validate.assert_called_once()
        reopened.cancel(); self.session.cancel.assert_called_once()
        reopened.revert(); self.session.revert.assert_called_once()
        self.assertEqual(reopened.branch, self.state['branch'])

    def test_missing_sandbox_returns_actionable_error_without_fallback(self):
        factory = Mock(side_effect=SandboxError('Sandbox is not configured'))
        self.workspace._runtime_factory = factory
        for operation in [lambda: self.workspace.start_session('Goal'), lambda: self.workspace.read_file('app.py'),
                          lambda: self.workspace.propose_edit('app.py', 'new', 'reason'), self.workspace.validate,
                          self.workspace.submit, self.workspace.revert]:
            result = operation()
            self.assertFalse(result['ok'])
            self.assertIn('not configured', result['error'])
        self.runtime.start.assert_not_called()

    def test_submission_passes_host_publisher_and_returns_existing_api_keys(self):
        self.session.submit.return_value = {'ok': True, 'number': 42, 'url': 'https://github.com/owner/repo/pull/42'}
        result = self.workspace.submit()
        self.runtime.publisher.assert_called_once_with('host-only-token')
        self.assertEqual(result['pr_number'], 42)
        self.assertEqual(result['pr_url'], result['url'])
        self.assertNotIn('host-only-token', repr(self.session.submit.call_args))
        self.state['phase'] = 'published'
        self.assertFalse(self.workspace.status()['active'])
        self.assertIsNone(self.workspace.branch)

    def test_only_completed_validation_is_shown_as_passed(self):
        for phase in ['editing', 'validating', 'validation_failed', 'cancelled']:
            self.state['phase'] = phase
            self.assertFalse(self.workspace.status()['validated_ok'])
        self.state['phase'] = 'validated'
        self.assertTrue(self.workspace.status()['validated_ok'])

if __name__ == '__main__': unittest.main()
