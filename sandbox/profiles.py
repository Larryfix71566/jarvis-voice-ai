"""Installed host profiles choose required checks and reusable dependencies."""
from dataclasses import dataclass
import hashlib
import json

from sandbox.artifacts import Candidate, SandboxError

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

    def dependency_key(self, candidate: Candidate) -> str:
        files = {file.path: file for file in candidate.files}
        if any(path not in files for path in self.dependencies):
            raise SandboxError("Source is missing a required dependency manifest")
        return Candidate(tuple(files[path] for path in self.dependencies)).fingerprint

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(json.dumps({"name": self.name, "dependencies": self.dependencies,
            "caches": self.caches, "checks": self.checks, "seeds": self.seeds}, sort_keys=True).encode()).hexdigest()


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
)

PROFILES = {MORTIMER.name: MORTIMER}


def get_profile(name: str) -> Profile:
    try:
        return PROFILES[name]
    except KeyError:
        raise SandboxError("No installed development profile for this application") from None
