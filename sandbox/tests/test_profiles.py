import json
import unittest
from sandbox.artifacts import Candidate, File, SandboxError
from sandbox.profiles import WEB_APP

class WebProfileTests(unittest.TestCase):
    def source(self, **override):
        manifest={'name':'example','entry_point':'src/index.html','dependencies':[]}
        manifest.update(override)
        return Candidate((File('manifest.json',0o644,json.dumps(manifest).encode()),
            File('src/index.html',0o644,b'<html>Example</html>'),File('src/app.js',0o644,b'console.log(1)')))

    def test_starter_names_share_runtime_dependencies_but_checks_are_host_selected(self):
        first,second=self.source(),self.source(name='another-app')
        WEB_APP.validate_source(first);WEB_APP.validate_source(second)
        self.assertEqual(WEB_APP.dependency_key(first),WEB_APP.dependency_key(second))
        self.assertEqual(WEB_APP.checks[-1][1][-1],'/Volumes/My Shared Files/input/static-web-check.mjs')

    def test_unsupported_runtimes_and_missing_or_escaping_entries_are_refused(self):
        for source in [self.source(dependencies=['external-package']), self.source(entry_point='../host.html'),
                       self.source(entry_point='missing.html'), Candidate(())]:
            with self.assertRaises(SandboxError): WEB_APP.validate_source(source)

if __name__=='__main__':unittest.main()
