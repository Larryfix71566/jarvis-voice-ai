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

## Remaining scope

The existing SelfEditService and application-build agent still need the
verified guest runner integrated; their existing host execution paths are
unchanged. Scoped provider access, speech mocks, complete voice journeys,
application templates, independent publication checks, reusable prepared
images, and physical audio/permission tests remain separate work. Guest
reports never authorize applying, pushing, merging or deploying a change.
