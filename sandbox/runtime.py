"""Installed host configuration and persistent workspace-to-session routing."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path

from sandbox.artifacts import SandboxError
from sandbox.control import Controller
from sandbox.durable import atomic_json
from sandbox.images import Images
from sandbox.profiles import get_profile
from sandbox.publish import GitHubAPI, Publisher, REPOSITORY
from sandbox.session import Session
from sandbox.source import GitSource
from sandbox.verify import Verifier


class Runtime:
    def __init__(self, controller, configured_images: dict[str, str]):
        self.controller = controller
        self.images = Images(controller)
        self.verifier = Verifier(controller, self.images)
        self.source = GitSource(controller.home)
        self.configured_images = dict(configured_images)
        self.workspaces = controller.home / 'workspaces'
        self.workspaces.mkdir(exist_ok=True, mode=0o700)

    @classmethod
    def configured(cls):
        home = Path(os.environ.get('MORTIMER_SANDBOX_HOME', str(Path.home() / 'Documents/Codex/MortimerSandbox')))
        path = home / 'settings.json'
        if not path.is_file() or path.is_symlink():
            raise SandboxError('The development sandbox needs its host setup configuration before it can start.')
        try:
            settings = json.loads(path.read_bytes())
            if settings.get('version') != 1 or not isinstance(settings['images'], dict):
                raise ValueError()
            return cls(Controller(home, settings['tart'], settings['softnet']), settings['images'])
        except (ValueError, KeyError, TypeError):
            raise SandboxError('The host sandbox configuration is invalid.') from None

    def _key(self, repository: str, kind: str) -> str:
        if not isinstance(repository, str) or not REPOSITORY.fullmatch(repository) or kind not in {'selfedit', 'app-build'}:
            raise SandboxError('Invalid sandbox workspace')
        return hashlib.sha256((repository.casefold() + '\0' + kind).encode()).hexdigest()

    def active(self, repository: str, kind: str, allowed) -> Session | None:
        path = self.workspaces / (self._key(repository, kind) + '.json')
        if not path.exists():
            return None
        record = json.loads(path.read_bytes())
        if record.get('repository', '').casefold() != repository.casefold() or record.get('kind') != kind:
            raise SandboxError('Workspace identity does not match its session record')
        profile = get_profile(record['profile'])
        return Session(self.controller, self.images, self.verifier, profile, allowed, record['session'])

    def start(self, repository: str, kind: str, base_branch: str, token: str, profile_name: str, allowed,
              goal: str, run_id: str | None = None) -> Session:
        if not isinstance(goal, str) or not goal.strip() or len(goal) > 8000:
            raise SandboxError('A development goal of at most 8,000 characters is required.')
        key = self._key(repository, kind)
        with (self.workspaces / (key + '.lock')).open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            previous = self.active(repository, kind, allowed)
            if previous and previous.status()['phase'] not in {'published', 'reverted', 'cancelled', 'setup_failed'}:
                raise SandboxError('A development session is already active; resume or cancel it first.')
            profile = get_profile(profile_name)
            image = self.configured_images.get(profile_name)
            if not image:
                raise SandboxError('No prepared sandbox image is configured for this application profile.')
            self.images.read(image, profile)
            repo, ref = self.source.fetch(repository, base_branch, token)
            def allocated(session):
                atomic_json(self.workspaces / (key + '.json'), {'repository': repository, 'kind': kind,
                    'profile': profile_name, 'session': session.id})
            return Session.create(self.controller, self.images, self.verifier, profile, allowed,
                image_id=image, repo=repo, ref=ref, repository=repository, base_branch=base_branch,
                kind=kind, goal=goal, run_id=run_id, on_created=allocated)

    @staticmethod
    def publisher(token: str) -> Publisher:
        return Publisher(GitHubAPI(token))
