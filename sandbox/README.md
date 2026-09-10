# Mortimer development sandbox foundation

Status: real VM provisioning, restart persistence, boundary observations,
application test suites, browser smoke, patch export and timeout shutdown
have been exercised. See [the acceptance record](VALIDATION.md) for exact
coverage and source revisions. Agent integration and full voice/application
journeys remain required before replacing the existing self-edit validator.

## Boundary

The host controller creates a disposable Tart macOS VM from an explicit
image and imports source from an explicit Git commit. It rejects source
symlinks/submodules and excludes private-data directories, environment
files, common credential files and detected tokens. Uncommitted host files
are not imported. Each task receives one read-only share containing its
sanitized source archive and trusted setup scripts. It receives no live
checkout, host home, shared writable Git directory, credentials or SSH agent.
Clipboard sharing and host audio pass-through are disabled.

Development commands execute through Tart's guest agent. Missing tools or
network isolation fail closed; no command falls back to host execution.
The controller currently limits this 16 GB development Mac to one active VM,
4 CPUs and 8 GiB of memory. Command timeouts stop the VM so work cannot
continue after its client is killed. Task state is saved outside the repo.

The provisioning phase permits public network access through Softnet to install
dependencies into a fresh trusted guest. Explicit rules block private networks,
the host gateway and all host IPv4 interface addresses observed at launch.
Softnet's default gateway exception is unsafe for this purpose: the real host
listener probe caught it before the explicit rules were added. Guest setup
uses public DNS because the host's DNS proxy is also blocked.
Only known, reviewed source should be used during this phase.
After successful preparation the controller flushes the guest filesystem
before stopping the VM. This is necessary because stopping Tart is not a
guest OS shutdown; recently installed browser files were lost without the
flush in the first activation attempt. Then
development restarts with all IPv4 destinations blocked. A prepared task
cannot be restarted in provisioning mode. Repeat the actual canary probes on
each host in both modes. Do not describe configuration flags or mocked tests
as proof that those probes passed. A failed IPv6 connection alone is not proof
of complete IPv6 containment.

## Host prerequisites

- An Apple silicon Mac with a compatible macOS release.
- Tart 2.37.0, installed using the [official instructions](https://tart.run/quick-start/).
- A root-owned Softnet helper. `bash sandbox/install-network-helper.sh`
  downloads version 0.23.0, checks its archive checksum, and asks macOS for
  administrator approval. It installs the verified binary with the required
  setuid permission at `/usr/local/libexec/mortimer-sandbox/softnet`. This is
  a persistent privileged helper; its installation needs explicit approval.
- Adequate disk space for the Xcode guest. The inspected Xcode 26.5 image
  downloads approximately 69 GB compressed; source, dependencies and guest
  disk growth need additional space. Do not start multiple large downloads.

Set `MORTIMER_TART` to the absolute Tart executable path if it is not on PATH.
Run the controller with host permissions to both launch and stop Tart;
restricted execution can prevent virtualization or termination. A failed
stop remains an error and does not clear the recorded active task.
Use `--home` to select a dedicated state directory. Its default is
`~/Documents/Codex/MortimerSandbox`; this is separate from `MORTIMER_HOME`,
which selects the application's private knowledge data.

```bash
python3 sandbox/control.py doctor
python3 sandbox/control.py create --repo /absolute/path/to/repo \
  --ref COMMIT_SHA --image ghcr.io/cirruslabs/macos-tahoe-xcode:26.5
# First boot offline and observe the boundary before provisioning:
python3 sandbox/control.py start TASK_ID --headless
# Wait for the guest agent, then use the same home/tool paths as the controller:
python3 sandbox/probe.py --home /absolute/sandbox/home --tart /absolute/path/to/tart TASK_ID
python3 sandbox/control.py stop TASK_ID
python3 sandbox/control.py start TASK_ID --provision
# Wait for the guest desktop/agent to be ready, then:
python3 sandbox/probe.py --home /absolute/sandbox/home --tart /absolute/path/to/tart --provisioning TASK_ID
python3 sandbox/control.py prepare TASK_ID
# Preparation stops the VM. Restart it offline for development:
python3 sandbox/control.py start TASK_ID
python3 sandbox/control.py exec TASK_ID /bin/bash '/Volumes/My Shared Files/input/checks.sh'
python3 sandbox/control.py exec TASK_ID /bin/bash '/Volumes/My Shared Files/input/preview.sh'
python3 sandbox/control.py exec TASK_ID /bin/bash '/Volumes/My Shared Files/input/browser-smoke.sh'
python3 sandbox/control.py export TASK_ID
python3 sandbox/control.py stop TASK_ID
```

Use an immutable image digest for an accepted base image; the version tag
above is the initial bootstrap candidate, not an attested production image.
Run `status TASK_ID` to inspect saved state and source identifiers.

## Included development tools and checks

Guest preparation installs the locked Python backend dependencies, the
bundled knowledge-base package, Node 22 web dependencies, Swift package
dependencies, and a Chromium browser with Playwright 1.63.0. The Xcode image
provides the native toolchain. Fake placeholder keys permit configuration
parsing, and all application databases and knowledge records live under
`/Users/admin/mortimer/state` inside the VM.

The check script runs policy/controller regressions, backend unit tests,
scripted sub-agent evaluations, latency enforcement, knowledge-base tests,
web compilation, and both native Swift test suites.
It attempts every group and records separate logs even when one fails.
The preview script starts guest-local knowledge-base, admin, cost and web
services, and requires successful HTTP responses before reporting readiness.
The browser smoke script checks console rendering and read-only navigation
through all seven panels, recording a screenshot and JSON report inside the
guest. It does not test voice, editing or publication. The VM desktop can
be used to launch/debug the native application.

`probe.py` runs synthetic host-file and network canaries against a running
guest, verifies that the source share exists and rejects writes, and checks
the actual guest CPU/memory allocation. It writes observations under the
host task directory and stops the VM on failure. By default public traffic
must fail; `--provisioning` requires public traffic to succeed while the same
host/private-network canaries remain blocked. A failed IPv6 connection
is recorded separately: it alone cannot prove filtering versus absent routing.
Neither these probes nor passing unit tests establish complete containment.

Two source files contain intentionally fake credential-shaped fixtures.
`REVIEWED_TEST_FIXTURES` permits only their reviewed path and exact SHA-256
content. A changed or moved fixture is still rejected by the source scanner.

The exported patch is saved as data, with a SHA-256 identifier. It is not
applied, pushed, merged or deployed automatically. A guest-controlled report
does not authorize publication. Review exported patches for sensitive files
and rerun required checks on the exact proposed candidate before publishing.

## Work still required for the complete development environment

1. Extend the recorded VM checks to additional application journeys and
   hosts. Package a reusable prepared base image with a fresh-workspace
   import protocol; the verified bootstrap image is still prepared per task.
2. Add a credential proxy with scoped development accounts, budgets and
   approved destinations; connect recorded/fake speech providers and complete
   voice journeys. Offline placeholder keys do not implement those providers.
3. Add guest task editing/import APIs and integrate them with the self-edit
   and app-build agents. The existing `SelfEditService._run` is not changed
   in this initial foundation; its current host-execution risk remains until
   the tested guest runner replaces it.
4. Add independent verification and durable, resumable publishing tied to
   an exact candidate. Then add application templates, migration/rollback
   journeys, retention and idle cleanup, and additional platform workers.
5. Perform real microphone, speaker, Bluetooth and permission checks on a
   development Mac. Those are separate from virtualized test coverage.

## Controller regression tests

```bash
python3 -m unittest discover -s sandbox/tests -v
```

These test source export and controller failure behavior without starting
VMs or touching private data. The dedicated Sandbox controller CI workflow runs them.
