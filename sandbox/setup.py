"""Register a prepared image and configure the installed development runtime."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from sandbox.artifacts import SandboxError
from sandbox.control import Controller
from sandbox.durable import atomic_json
from sandbox.images import Images
from sandbox.profiles import PROFILES, get_profile


def configure(controller, profile_name: str, image_id: str) -> dict:
    profile = get_profile(profile_name)
    Images(controller).read(image_id, profile)
    if not controller.doctor()['ready_to_boot']:
        raise SandboxError('The VM runtime or its approved network helper is not ready.')
    path = controller.home / 'settings.json'
    if path.is_symlink(): raise SandboxError('Invalid sandbox settings path')
    settings = json.loads(path.read_bytes()) if path.exists() else {'version': 1, 'images': {}}
    if settings.get('version') != 1 or not isinstance(settings.get('images'), dict):
        raise SandboxError('Invalid existing sandbox settings')
    settings.update(tart=controller.tart, softnet=controller.softnet)
    settings['images'][profile_name] = image_id
    atomic_json(path, settings)
    return {'ok': True, 'profile': profile_name, 'image': image_id}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', type=Path, default=Path.home() / 'Documents/Codex/MortimerSandbox')
    parser.add_argument('--tart')
    parser.add_argument('--softnet', default='/usr/local/libexec/mortimer-sandbox/softnet')
    parser.add_argument('--profile', choices=sorted(PROFILES), default='mortimer')
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument('--image', help='An already registered prepared image identifier')
    selection.add_argument('--prepared-task', help='A fresh stopped preparation task that never entered development')
    args = parser.parse_args()
    controller = Controller(args.home, args.tart or str(args.home / 'tools/tart.app/Contents/MacOS/tart'), args.softnet)
    image = args.image or Images(controller).register(args.prepared_task, get_profile(args.profile))
    print(json.dumps(configure(controller, args.profile, image)))

if __name__ == '__main__':
    try: main()
    except SandboxError as exc: raise SystemExit(str(exc))
