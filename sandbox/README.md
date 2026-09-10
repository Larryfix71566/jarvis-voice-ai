# Mortimer development sandbox

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

## Prepared images, independent verification and sessions

For the session runtime, register the task immediately after preparation stops
it, before that VM ever enters development. Registration creates a template
that is never booted. Every development or verification session clones it.

```bash
python3 -m sandbox.setup --home /absolute/sandbox/home \
  --tart /absolute/path/to/tart --prepared-task PREPARATION_TASK_ID
# Or select an existing registered image:
python3 -m sandbox.setup --home /absolute/sandbox/home \
  --tart /absolute/path/to/tart --image PREPARED_IMAGE_ID
```

This saves paths and image identifiers in the host's `settings.json`; it does
not store credentials. `MORTIMER_SANDBOX_HOME` selects that runtime for the
application adapter. The installed profiles are `mortimer` and `web-app`. The latter supports
the repository’s dependency-free HTML/CSS/JavaScript starter. Unknown runtimes
or dependency changes require a matching prepared profile before development
starts. Register each profile with `sandbox.setup --profile PROFILE`.

The host keeps GitHub authentication in memory and fetches a size-checked,
immutable revision into a private bare object store. No candidate checkout,
Git hooks, dependency installation or application test executes on the host.
`Session` owns the development task, goal, proposed edits and progress records.
`Runtime` persists the repository-to-session mapping before VM setup so a
restart can find an interrupted session. `SandboxWorkspace` exposes that
session through the application’s workspace interface. `SelfEditService` and
`AppWorkspace` now use that interface for reads, edits, validation, publication
and cancellation; they do not create host candidate worktrees. App builds use
the installed `web-app` profile, and candidate manifest commands cannot choose
the verification commands. API responses include the sandbox task and session
identity. Initial authoring setup returns promptly with an `opening` job that
voice status can poll; it does not wait for VM preparation inside the HTTP
request. Cancelling a running planner or a self-edit finish job stops VM work
and prevents a late successful validation from triggering submission.

Cold file access starts background VM resume and returns a retryable response;
the caller must explicitly retry the read or edit after readiness is reported.
No edit is queued by this warmup. A fresh host process reconciles the saved task
with Tart before resuming. Interrupted verification cancels its child VM and
clears its approval. App selection and saved draft-PR links survive a process
restart, and app submission runs in the background with status polling.

Legacy local file writes, Git staging/commit/push, and direct single-file app
writes return `sandbox_required`, including previously confirmed action IDs.
Every existing-repository change goes through self-edit or app-build sessions.
Plan, review and research saves use the same guarded VM editor. Open a self-edit
session for saving the document, then confirm `plan_adopt` or `research_save`.
The console's Save in sandbox button uses the same route. A cold session returns
retry guidance without queuing a write. Missing/busy sessions preserve the
generated result. Saves are restricted to Markdown under `docs/plans/`,
`docs/reviews/` and `docs/research/`, with the installed allowlist still enforced.
Run `selfedit_finish` to verify and prepare the draft PR; a sandbox save alone
does not publish the file. Merge the resulting PR before using its path from
the installed checkout in a later planning run. Initial app scaffolding and
registry updates still require migration, so the application is not yet sandbox-only.

Native appearance verification is unavailable until the guest preview is
integrated. It refuses with a clear error and never captures the host desktop.
This routing change is not deployment of a complete development environment.

Each fresh guest creates an unprivileged worker, replaces the image's known
administrator credential, and provides an empty synthetic Keychain for native
authentication tests. The worker cannot use sudo or modify the shared setup
code, installed Python/Node dependencies, or baseline tests. Candidate shell
startup files are not loaded by the command runner. Compiler output is separate
for candidate and baseline Swift tests.

Validation freezes a candidate, stops its development VM, and clones a separate
verification VM. The installed host profile selects the checks and synthetic
state seeds. The receipt binds the candidate, baseline commit, image, profile,
runner and saved log hashes. Check logs update while commands run; incomplete
lines are withheld until recognizable credentials can be redacted. Failed
checks, edits, interruption or a changed
runner invalidate publication eligibility. A fresh source capture must still
match before submission. Verification is evidence for these checks, not a
claim that arbitrary application behavior is safe.

Publication uses GitHub's object API with the accepted files as data. It records
its intent before external writes and resumes lost commit, branch and draft-PR
responses without creating duplicates or overwriting another branch. Edits are
refused once publication begins. Cancellation stops development and related
verification VMs, prevents late starts, and stops additional publication calls.
An already in-flight remote request can finish; its returned object is recorded
for recovery. Deleting a disposable task retains its review evidence.

## Work still required for the complete development environment

The complete scope is tracked in [IMPLEMENTATION.md](IMPLEMENTATION.md). It
includes closing remaining direct-write tool paths, bounding interrupted file
operations and cleanup,
complete application profiles and templates,
voice/provider simulations, a scoped host-vault broker, authenticated previews
and native journeys, runtime/storage/idle limits, checkpoints, and deployment
and database rollback workflows. Real microphone, speaker, Bluetooth and device
permission checks require separate physical-device evidence.

## Controller regression tests

```bash
python3 -m unittest discover -s sandbox/tests -v
```

These test source export and controller failure behavior without starting
VMs or touching private data. The dedicated Sandbox controller CI workflow runs them.
