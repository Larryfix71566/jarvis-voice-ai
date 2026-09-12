"""Installed host profiles choose required checks and reusable dependencies."""
from dataclasses import dataclass
import hashlib
import json

from sandbox.artifacts import Candidate, SandboxError, source_path_allowed

PYTHON = "/Users/admin/mortimer/dependencies/python/bin/python"
KB_PYTHON = "/Users/admin/mortimer/dependencies/knowledge-python/bin/python"
VERIFICATION = "/Users/admin/mortimer/verification"

@dataclass(frozen=True)
class Profile:
    name: str
    dependencies: tuple[str, ...]
    caches: tuple[str, ...]
    checks: tuple[tuple[str, tuple[str, ...]], ...]
    seeds: tuple[tuple[str, ...], ...] = ()
    requires_graphics: bool = False

    def validate_source(self, candidate: Candidate):
        if self.name != "web-app":
            return
        files = {file.path: file for file in candidate.files}
        try:
            manifest = json.loads(files["manifest.json"].data)
            entry = manifest["entry_point"]
            if (not isinstance(entry, str) or not source_path_allowed(entry) or not entry.endswith(".html")
                    or entry not in files or manifest.get("dependencies") != [] or "src/app.js" not in files):
                raise ValueError()
        except (ValueError, KeyError, TypeError):
            raise SandboxError("This profile requires the dependency-free web starter; prepare a matching profile for another application runtime") from None

    def dependency_key(self, candidate: Candidate) -> str:
        files = {file.path: file for file in candidate.files}
        if any(path not in files for path in self.dependencies):
            raise SandboxError("Source is missing a required dependency manifest")
        return Candidate(tuple(files[path] for path in self.dependencies)).fingerprint

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(json.dumps({"name": self.name, "dependencies": self.dependencies,
            "caches": self.caches, "checks": self.checks, "seeds": self.seeds,
            "requires_graphics": self.requires_graphics}, sort_keys=True).encode()).hexdigest()


MORTIMER = Profile(
    name="mortimer",
    dependencies=("requirements.txt", "requirements-lock.txt", "services/mortimer-vault/pyproject.toml",
                  "web/package.json", "web/package-lock.json", "macos/JarvisKit/Package.swift",
                  "macos/JarvisKit/Package.resolved", "macos/MortimerHost/Package.swift",
                  "macos/MortimerHost/Package.resolved"),
    caches=(".venv", "services/mortimer-vault/.venv", "web/node_modules",
            "macos/JarvisKit/.build", "macos/MortimerHost/.build"),
    checks=(
        ("backend-imports", (PYTHON, "-c", "import jarvis, jarvis.config, jarvis.cli, jarvis.runlog")),
        ("baseline-backend", (PYTHON, "-m", "pytest", VERIFICATION + "/tests/unit", "-q")),
        ("backend", (PYTHON, "-m", "pytest", "tests/unit", "-q")),
        ("scripted-evals", (PYTHON, "-m", "pytest", VERIFICATION + "/tests/evals/sub_agent_evals.py", "-q")),
        ("latency", (PYTHON, "scripts/latency_probe.py", "--budget", "tests/fixtures/latency_sample.log")),
        ("knowledge-base", (KB_PYTHON, "-m", "pytest", "services/mortimer-vault/tests", "-q")),
        ("baseline-knowledge-base", (KB_PYTHON, "-m", "pytest", VERIFICATION + "/services/mortimer-vault/tests", "-q")),
        ("web", ("npm", "--prefix", "web", "run", "build")),
        ("native-library", ("swift", "test", "--package-path", "macos/JarvisKit")),
        ("native-app", ("swift", "test", "--package-path", "macos/MortimerHost")),
        ("baseline-native-library", ("swift", "test", "--package-path", VERIFICATION + "/macos/JarvisKit")),
        ("baseline-native-app", ("swift", "test", "--package-path", VERIFICATION + "/macos/MortimerHost")),
    ),
    seeds=((PYTHON, "scripts/init_db.py"), (KB_PYTHON, "-m", "mortimer_vault.cli", "init")),
    requires_graphics=True,
)

WEB_APP = Profile(
    name="web-app", dependencies=(), caches=(".venv",),
    checks=(("javascript", ("node", "--check", "src/app.js")),
            ("browser", ("node", "/Volumes/My Shared Files/input/static-web-check.mjs"))),
)

PROFILES = {profile.name: profile for profile in [MORTIMER, WEB_APP]}


def get_profile(name: str) -> Profile:
    try:
        return PROFILES[name]
    except KeyError:
        raise SandboxError("No installed development profile for this application") from None
