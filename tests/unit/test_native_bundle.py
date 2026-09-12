"""Packaging contracts; fake build/sign/open boundaries never launch an app."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class NativeBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="native bundle ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.package = self.root / "MortimerHost"
        (self.package / "scripts").mkdir(parents=True)
        original = Path(__file__).resolve().parents[2] / "macos/MortimerHost/scripts/bundle.sh"
        self.script = self.package / "scripts/bundle.sh"
        self.script.write_bytes(original.read_bytes())
        self.products = self.package / ".build/debug"
        self.products.mkdir(parents=True)
        (self.products / "MortimerHost").write_bytes(b"synthetic executable")
        resource = self.products / "JarvisKit_JarvisKit.bundle"
        resource.mkdir()
        (resource / "fixture.json").write_text('{"synthetic":true}')
        self.framework = self.products / "WebRTC.framework"
        version = self.framework / "Versions/A"
        version.mkdir(parents=True)
        (version / "WebRTC").write_bytes(b"synthetic pinned framework")
        (self.framework / "Versions/Current").symlink_to("A")
        (self.framework / "WebRTC").symlink_to("Versions/Current/WebRTC")
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.log = self.root / "commands.jsonl"
        boundary = '''import json,os,pathlib,sys
name=pathlib.Path(sys.argv[0]).name
with open(os.environ['BUNDLE_TEST_LOG'],'a') as log:
    log.write(json.dumps([name,*sys.argv[1:]])+'\\n')
failure=os.environ.get('BUNDLE_TEST_FAILURE')
if failure=='build' and name=='swift': sys.exit(61)
if name=='codesign':
    if failure=='verify' and '--verify' in sys.argv: sys.exit(62)
    if '--sign' in sys.argv:
        if failure=='framework-sign' and sys.argv[-1].endswith('.framework'): sys.exit(63)
        if failure=='app-sign' and sys.argv[-1].endswith('.app'): sys.exit(64)
'''
        for name in ["swift", "codesign", "open"]:
            path = self.bin / name
            path.write_text("#!" + sys.executable + "\n" + boundary)
            path.chmod(0o755)
        self.app = self.package / ".build/MortimerHost.app"

    def run_bundle(self, failure=""):
        env = {**os.environ, "PATH": str(self.bin) + ":/usr/bin:/bin",
               "BUNDLE_TEST_LOG": str(self.log), "BUNDLE_TEST_FAILURE": failure}
        result = subprocess.run(["/bin/bash", str(self.script), "debug"], env=env,
                                capture_output=True, text=True, timeout=20)
        commands = [json.loads(line) for line in self.log.read_text().splitlines()]
        return result, commands

    def test_runtime_and_resources_are_embedded_and_signed_before_launch(self):
        result, commands = self.run_bundle()
        self.assertEqual(result.returncode, 0, result.stderr)
        embedded = self.app / "Contents/MacOS/WebRTC.framework"
        self.assertEqual((embedded / "WebRTC").read_bytes(), b"synthetic pinned framework")
        self.assertTrue((embedded / "Versions/Current").is_symlink())
        self.assertTrue((embedded / "WebRTC").resolve().is_relative_to(self.app.resolve()))
        self.assertTrue((self.app / "Contents/MacOS/JarvisKit_JarvisKit.bundle/fixture.json").is_file())
        self.assertEqual(commands, [
            ["swift", "build", "-c", "debug"],
            ["codesign", "--force", "--sign", "-", str(embedded)],
            ["codesign", "--force", "--sign", "-", str(self.app)],
            ["codesign", "--verify", "--deep", "--strict", str(self.app)],
            ["open", str(self.app)],
        ])

    def test_missing_runtime_prevents_signing_and_launch(self):
        (self.framework / "Versions/A/WebRTC").unlink()
        result, commands = self.run_bundle()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Missing bundled WebRTC runtime", result.stderr)
        self.assertEqual([command[0] for command in commands], ["swift"])

    def test_build_failure_prevents_launch(self):
        result, commands = self.run_bundle("build")
        self.assertEqual(result.returncode, 61)
        self.assertEqual([command[0] for command in commands], ["swift"])

    def test_framework_or_app_signing_failure_prevents_launch(self):
        for failure, status in [("framework-sign", 63), ("app-sign", 64)]:
            with self.subTest(failure=failure):
                self.log.unlink(missing_ok=True)
                result, commands = self.run_bundle(failure)
                self.assertEqual(result.returncode, status)
                self.assertNotIn("open", [command[0] for command in commands])

    def test_signature_verification_failure_prevents_launch(self):
        result, commands = self.run_bundle("verify")
        self.assertEqual(result.returncode, 62)
        self.assertNotIn("open", [command[0] for command in commands])


if __name__ == "__main__":
    unittest.main()
