# Sandbox acceptance record — 2026-09-10

The macOS VM foundation was provisioned and exercised on an Apple silicon
Mac with 16 GiB host memory. Each task used four virtual CPUs and 8 GiB RAM.
This record covers the controller and guest environment, not completed
self-edit integration or end-to-end voice acceptance.

## Revisions and toolchain

The application suites ran against source commit
`0b95d4caa2cfe74be24c290dada7a4fba402ad2f`. A fresh task at
`df3ad32480517ed0d2e7d273a4953f59219f02bd` then verified the filesystem flush,
restart persistence, 19 controller regressions, browser, export and timeout
checks. The intervening changes were controller flush handling, its tests,
documentation, and reconciliation with merged PR #54.

- Tart 2.37.0 and checksum-verified Softnet 0.23.0.
- Image: `ghcr.io/cirruslabs/macos-tahoe-xcode:26.5` at manifest digest
  `sha256:61f6e857a3d65dd2f8daf9c51c7b837fa458bcc9181ae8556e645b534dab6bf6`.
- Guest macOS 26.4, build 25E246; Xcode 26.5, build 17F42.
- Swift 6.3.2; Python 3.12.14; Node 22.23.2; Playwright 1.63.0.

The source came from committed Git objects and passed the controller's
filtering and credential-pattern checks. No live checkout or real project
credentials were imported.

## Observed results

- Offline and provisioning probes: the synthetic host file was inaccessible,
  shared source was readable but could not be changed, guest scratch writes
  worked, the host listener was unreachable, and the metadata address was
  blocked. The actual guest CPU and memory matched the requested allocation.
- Public IPv4 traffic succeeded during trusted provisioning and failed after
  offline restart. IPv6 connections failed in both modes; that observation
  alone does not distinguish filtering from absent IPv6 routing and is not
  a claim of complete IPv6 containment.
- Controller regressions: 19 passed in the final fresh VM and on the host.
  The application run also passed all eight detached-checkout policy tests.
- Backend: 2,396 tests passed, with 11 warnings, in 337.73 seconds.
- Scripted sub-agent evaluations: 13 passed. Latency budget enforcement
  passed against the repository's sample log; this was not a live voice
  latency measurement.
- Knowledge base: 17 tests passed. The web build passed.
- Native Swift suites: JarvisKit 96 tests and MortimerHost 39 tests passed.
  These runs compiled the native packages; they were not manual native UI
  or physical microphone/speaker acceptance.
- Dependency consistency passed. RNNoise, Torch and torchaudio imported
  successfully in the first prepared guest.
- Knowledge-base, admin, costs and web previews returned HTTP 200 inside the
  guest. Chromium rendered the console and navigated all seven panels, with
  no uncaught page errors or failed requests in the recorded smoke run.
- Browser packages, Chromium downloads and the toolchain report survived a
  fresh provision/flush/stop/offline-start cycle.
- A synthetic guest edit exported as one patch with SHA-256
  `927ddc786bba5db31c8f3206b41e82db2453d8effd58ebc9d080ca80dad6834d`.
  The test edit was then removed; no patch was applied or published.
- A 30-second guest sleep with a one-second limit triggered controller
  shutdown. Both Tart's actual state and the saved task state were verified
  as stopped. The prepared VM was left stopped afterward.

## Issues found during activation

Softnet's default policy permits its host gateway. A real provisioning probe
reached a synthetic host listener, so the VM was stopped and provisioning
rules were changed to explicitly block private ranges and every observed
host IPv4 address. Public DNS replaces the blocked host DNS proxy. The
corrected rule passed repeated actual-VM probes, including a fresh task.

The lock file combined NumPy 1.26.4 with a headless OpenCV release requiring
NumPy 2. Aligning headless OpenCV with the existing 4.11.0.86 OpenCV pin
resolved the installation conflict; the guest dependency check passed.

The first preparation stopped Tart immediately after installation. Browser
files and the toolchain report did not survive that restart. The controller
now runs guest `sync` before marking preparation complete and stopping.
The fresh-task restart and browser checks verified persistence afterward.

## Independent session acceptance (2026-09-10)

A shared session fetched committed source into a host-only bare cache, created
an offline development VM, edited one documentation canary, froze its complete
candidate, and verified it in a separate fresh VM. All 12 checks passed:
backend imports; baseline and candidate backend suites (2,396 each); scripted
evaluations; latency fixture; baseline and candidate knowledge-base tests; web
build; and baseline/candidate native library (96 each) and app (39 each) tests.
The final guest capture matched the candidate exactly.

The host reopened the saved session and published the verified files through
GitHub's object API. An intentionally lost draft-create response was recovered
by retrying the same operation; only one PR existed. The temporary
[PR 57](https://github.com/Larryfix71566/jarvis-voice-ai/pull/57) was closed
without merging, and its branch and disposable VMs were deleted. Evidence was
retained in the host task records. See the committed
[receipt and publication record](acceptance/2026-09-10-session.json).

Additional actual-VM checks established that the worker cannot use sudo or
write protected tools, baseline tests or the read-only input share. A worker
login startup file that tried to bypass a check was not loaded. Native checks
passed across a restart. The final session's development and verification
stops both recorded successful filesystem flushes.

Setup testing found three issues: secure-token administrator password changes
needed the public image's factory credential; the automatic-login credential
also needed updating for Tart's agent to survive restarts; and native tests
needed a disposable Keychain plus a preferences directory and explicit default
selection before each native run. Sharing Swift compiler products across two
source roots caused duplicate-module failures; the baseline now gets resolved
dependency inputs and its own clean compiler output. Python and Node package
code stays protected while required build caches remain writable.

The installed host implementation passed 89 sandbox regressions and nine CI
policy tests. Candidate application checks ran inside VMs. This is evidence
for the listed checks, not a blanket claim about arbitrary candidate behavior.

## Remaining scope

Production agent routing, complete application profiles, scoped provider/vault
access, speech simulations, full voice and native preview journeys, lifecycle
quotas/checkpoints, and release/database rollback workflows remain. The full
scope is tracked in [IMPLEMENTATION.md](IMPLEMENTATION.md). Physical audio and
device permission tests require separate evidence.


## Application routing and web starter checkpoint

The adapters now use VM sessions. The complete unit suite plus the updated
self-edit API integration passed 2,340 tests inside development VM
`e1b7f62568f4`. After asynchronous authoring setup was added, the affected API
and voice-tool selection passed all 164 tests. The trusted host controller
suite passes 93 tests, including live log delivery and split-credential
redaction. These are separate runs, not additive test totals.

A broader `pytest tests` run was interrupted after 1,060 seconds while real
tool-server startup remained slow. Its failed-test cache identified the weather
integration test, which calls a real external API and now carries the suite’s
`live` marker. The whole integration suite has not passed; startup performance
and remaining integration failures require follow-up.

A disposable copy of the repository’s plain web starter was edited in VM
`a22b4261e933` and independently verified in VM `e3bd8c798ea7`. Both required
checks passed: JavaScript syntax and offline browser startup/initial render.
The complete candidate stayed unchanged. No repository or pull request was
created for this web fixture. This does not cover arbitrary application
interactions, backend dependencies, or native GUI behavior.

Exact revisions, fingerprints and log hashes are in
[the routing acceptance record](acceptance/2026-09-10-routing.json).

## Resume and reconnect checkpoint

Development VM `da3811daeb0d` passed 303 affected application/API tests, then
87 workspace and self-edit voice-tool tests after the publication-status fix.
The trusted controller suite passed 101 tests. These selections overlap and
must not be added together as distinct test coverage.

A documentation edit and its saved proposal survived a VM stop and fresh
host controller. Separate checks recovered from a stale recorded running state.
Controlled failure injection left verification child `f33b9d630250` running
with the session marked validating and a deliberately stale approval. Resume
stopped that child, refused its restart, cleared the approval and check list,
and preserved the edit. This was interruption recovery, not a completed
independent verification or publication of that candidate.

Both test VMs were deleted and the session reverted, retaining host evidence.
Exact identifiers and check log hashes are in
[the resume acceptance record](acceptance/2026-09-10-resume.json).


## Legacy writer retirement checkpoint

The complete unit suite passed 2,321 tests inside disposable VM `88a7ba0a49ab`.
A later API/MCP selection passed 118 tests, including actual stdio calls to the
retired repository and app writers. Its one failure was the app-builder prompt
length limit; the instructions were shortened and all 65 prompt tests passed
on the final version. These runs overlap and are not additive coverage totals.

Regression checks use temporary Git repositories inside the VM to confirm
legacy drafts cannot change the index, commit, or remote. Old file-write action
IDs cannot change repository files. The direct app writer refuses without
accessing its GitHub client, including through MCP without a token. Plan and
research save calls return the refusal and retain their generated job results.

The VM was deleted, retaining host logs. Exact source, overlay and log hashes
are in [the writer-boundary record](acceptance/2026-09-10-writer-boundary.json).
Initial app scaffolding, registry writes and replacement plan/research saving
remain unfinished. This check did not run the whole integration suite or create
an independent publication receipt.


## Generated document saving checkpoint

Plan/review/research saving passed an initial 221-test API/unit selection in
VM `52048bcb8af0`, followed by 127 tests for the final compatibility guards.
The console production build passed after its save message and button changed.
Counts overlap. Tests exercise installed path policy, busy/disabled/missing
sessions, cold retry without a queued edit, validation invalidation, the existing
validate/submit sequence, and refusal to misreport a legacy draft response as saved.
API tests inject the test VM runtime; they do not launch nested development VMs.

Separate real Session writes/readback preserved exact plan and research document
bytes, left verification invalidated, and did not create files in the host source
checkout. The disposable VM was deleted with logs retained. No independent
publication receipt or draft was generated for those synthetic documents.
Exact source/overlay/log hashes are in
[the document-saving record](acceptance/2026-09-10-document-saving.json).
