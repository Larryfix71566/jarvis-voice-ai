#!/usr/bin/env python3
"""Exercise a running VM boundary using synthetic host canaries.

Run before importing proposed code. Reports are observations, not a claim
that unit tests alone prove containment. No production data is used.
"""
import argparse
import json
from pathlib import Path
import socket
import tempfile
import threading

from control import Controller, SandboxError

GUEST_PROBE = r'''
import json, os, pathlib, socket, subprocess, sys
canary, port, shared = sys.argv[1], int(sys.argv[2]), sys.argv[3]
result = {}
result['shared_source_readable'] = (pathlib.Path(shared) / 'source.tar').is_file()
try:
    pathlib.Path(canary).read_bytes()
    result['host_file_read_blocked'] = False
except OSError:
    result['host_file_read_blocked'] = True
try:
    (pathlib.Path(shared) / 'guest-write-canary').write_text('test')
    result['shared_input_write_blocked'] = False
except OSError:
    result['shared_input_write_blocked'] = True
scratch = pathlib.Path('/Users/admin/mortimer-probe.txt')
scratch.write_text('guest write works')
result['guest_scratch_writable'] = scratch.read_text() == 'guest write works'
scratch.unlink()
route = subprocess.run(['/sbin/route', '-n', 'get', 'default'], capture_output=True, text=True)
gateway = next((line.split(':', 1)[1].strip() for line in route.stdout.splitlines() if line.strip().startswith('gateway:')), None)
result['gateway'] = gateway
def connect(host, port):
    try:
        with socket.create_connection((host, port), timeout=3):
            return True
    except OSError:
        return False
result['host_gateway_blocked'] = gateway is not None and not connect(gateway, port)
result['public_ipv4_blocked'] = not connect('1.1.1.1', 443)
result['metadata_address_blocked'] = not connect('169.254.169.254', 80)
result['public_ipv6_connection_failed'] = not connect('2606:4700:4700::1111', 443)
result['guest_memory_bytes'] = int(subprocess.check_output(['/usr/sbin/sysctl', '-n', 'hw.memsize']))
result['guest_cpu_count'] = int(subprocess.check_output(['/usr/sbin/sysctl', '-n', 'hw.ncpu']))
result['virtualized'] = subprocess.check_output(['/usr/sbin/sysctl', '-n', 'kern.hv_vmm_present'], text=True).strip() == '1'
result['resource_limits_match'] = result['guest_memory_bytes'] == 8192 * 1024 * 1024 and result['guest_cpu_count'] == 4
print(json.dumps(result))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', type=Path, required=True)
    parser.add_argument('--tart', required=True)
    parser.add_argument('--softnet', default='/usr/local/libexec/mortimer-sandbox/softnet')
    parser.add_argument('--provisioning', action='store_true',
                        help='Expect public internet during trusted dependency setup')
    parser.add_argument('task')
    args = parser.parse_args()
    controller = Controller(args.home, args.tart, args.softnet)
    state = controller.read(args.task)
    network = 'provisioning' if args.provisioning else 'offline'
    status = 'provisioning' if args.provisioning else 'running'
    if state.get('network') != network or state.get('status') != status:
        raise SandboxError('Task state does not match the requested probe mode')
    accepted = []
    done = threading.Event()
    listener = socket.socket()
    listener.bind(('0.0.0.0', 0))
    listener.listen(4)
    listener.settimeout(0.2)
    port = listener.getsockname()[1]

    def accept_connections():
        while not done.is_set():
            try:
                conn, address = listener.accept()
                accepted.append(address[0])
                conn.close()
            except socket.timeout:
                pass

    thread = threading.Thread(target=accept_connections)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix='host-canary-', dir=controller.home) as directory:
            canary = Path(directory) / 'not-a-real-secret.txt'
            canary.write_text('synthetic host boundary canary')
            response = controller.guest(args.task, ['/usr/bin/python3', '-c', GUEST_PROBE,
                                        str(canary), str(port), '/Volumes/My Shared Files/input'],
                                        timeout=45, capture=True)
            result = json.loads(response.stdout)
            result['host_canary_unchanged'] = canary.read_text() == 'synthetic host boundary canary'
            result['host_input_unchanged'] = not (controller.task_dir(args.task) / 'input/guest-write-canary').exists()
            result['host_listener_unreached'] = not accepted
    except (Exception, KeyboardInterrupt):
        controller.stop(args.task)
        raise
    finally:
        done.set()
        thread.join(timeout=2)
        listener.close()
    required = ['shared_source_readable', 'resource_limits_match',
                'host_file_read_blocked', 'shared_input_write_blocked', 'guest_scratch_writable',
                'host_gateway_blocked', 'metadata_address_blocked',
                'virtualized', 'host_canary_unchanged', 'host_input_unchanged', 'host_listener_unreached']
    result['network_mode'] = network
    result['expected_public_network_behavior'] = result['public_ipv4_blocked'] is (not args.provisioning)
    required.append('expected_public_network_behavior')
    result['observed_checks_passed'] = all(result.get(name) is True for name in required)
    result['ipv6_limit'] = 'A failed connection alone does not distinguish filtering from absent IPv6 routing.'
    filename = 'provisioning-containment-observations.json' if args.provisioning else 'containment-observations.json'
    report = controller.task_dir(args.task) / filename
    report.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    if not result['observed_checks_passed']:
        controller.stop(args.task)
        raise SandboxError('Containment observation failed; VM stopped')


if __name__ == '__main__':
    main()
