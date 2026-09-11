# Window visibility verification remains incomplete

Status: candidate implementation and tests are uncommitted; no pass or release
acceptance. The last completed implementation commit remains b5f09ea before this
investigation. WindowVisibilityReader observes the existing NSWindow's visibility,
occlusion, minimization and app hide notifications. VoiceWaveView uses it to
pause animation and clear transient amplitude when hidden. The intended behavior
has not passed the visible/resume checks in the current test environment.

## Evidence

- `p2-window-visibility`: full host run failed visible/resume assertions;
  SHA-256 `8ceb5dd0be15e3a0afd03f4178a351a9c1183b8e55acfb4ff7e06392922a27c8`.
- `p2-window-visibility-activated`: focused run with a regular application
  activation policy still failed; SHA-256
  `0187e7b58ad7d851556bb01401447e18e55492a81eb723675e17929bdb20b4d3`.
- Explicit native event pumping and finishLaunching did not fix the observation.
  The latter diagnostic log is `p2-window-finish-launching`, SHA-256
  `50f11daa2e909ed4ef09699d74cb6e3127866a7da36ccb69b76294eabb99dbaa`.
  The window reported visible/on-active-space, but the application was inactive
  and its window lacked the visible occlusion flag.
- The standalone native app probe in `probes/WindowVisibilityProbe.swift` also
  fails shown/reshown/restored checks. It must be compiled with the actual current
  WindowVisibilityReader.swift into an app bundle and launched as the worker,
  not run as an administrator or substituted with a mock. This probe is outside
  the shipping target and does not supersede the failing ordinary tests.
- Read-only IORegistry inspection confirmed `CGSSessionScreenIsLocked = true`
  for the console worker, both before and after the latest VM restart. This
  explains why visibility cannot yet be accepted. It does not prove that all
  application observer behavior is otherwise correct.

## Isolated development environment changes

Only disposable development task 66fed310bde6 was changed. The desktop originally
used admin while candidate commands ran as the unprivileged mortimer-dev worker.
A synthetic random worker password and automatic worker login were configured
inside the VM; no production credentials/accounts were changed. The password
was not printed or retained by the host. Idle screensaver/ask-for-password
preferences were adjusted for that disposable worker, but they did not unlock
the session. The VM remains offline and the worker remains outside sudoers.

After worker autologin, Tart exec itself runs as mortimer-dev. The existing
controller worker_prefix unconditionally invokes sudo, so ordinary run_check
now fails at its Keychain setup before running tests. No sudo privilege was
added as a workaround. Subsequent diagnostics explicitly verified worker UID
and identity, selected only the disposable test Keychain when needed, and ran
inside the same offline VM. Those are diagnostic logs, not frozen verification
receipts. The controller and its frozen profile have not been modified.

The current VM keeper is the host process started during the latest scoped
controller stop/start. Old VM state and verification artifacts remain preserved.
Local helper scripts in the work directory, run_gui_visibility.py and
run_visibility_app_probe.py, reproduce the guarded diagnostics. The app probe
writes only synthetic result JSON under the disposable worker home.

## Next required work

Restore a usable unlocked worker GUI test environment without granting worker
administrative rights or running candidate code as admin. A fresh disposable
clone with a deliberately configured GUI worker and an explicit, verified
screen-lock policy is preferable to guessing credentials or altering the host.
Preserve the current task and all logs before changing its setup. If the runner
must support an already-unprivileged executor, make that a separately tested
identity-guarded controller change; never omit worker validation.

Then rerun the exact visible/hide/minimize/restore/detach checks and the full
host suite. Keep the current assertions and report all initial failures. Also
verify actual occlusion, application hide/unhide, callback teardown and the
wave's display scheduling. Do not claim all visibility requirements from just
an NSView disappear callback or a successful offscreen screenshot.

## Fresh-clone follow-up and approval constraint

A fresh offline development task `ab9c8fe5bf23` was created in session
`9d49cb3a928943de994a888d497c9933`. The previous task remains preserved.
The fresh task hydrated successfully and received the unfinished visibility
sources/tests. Its worker remains UID 502 without sudo rights.

On this host, restricted-shell Tart calls timed out whereas the scoped controller
channel used to launch the VM successfully returned the guest identity. Do not
restart merely because a restricted observation times out: confirm the existing
VM through the working channel and wait for any cleanup process to terminate.

The fresh GUI worker authenticated successfully and was configured for automatic
login. In its own logged-in session, sysadminctl explicitly reported screenLock
is off. A private synthetic one-time credential remains inside the disposable
worker home at `.gui-test-password` for controlled setup; it must not be printed
or copied into the repository and should be removed after setup is resolved.
No production account or credential was used.

The normal-app probe nevertheless still failed shown/reshown/restored acceptance.
Screen-lock policy being off is not proof that the current screen is unlocked.
The current probe result is retained in the local window-visibility-probe work
directory; do not treat any successful hide/detach subset as overall acceptance.

A Computer Use attempt reported pending host Accessibility and Screen Recording
permissions. Larry stated that he cannot approve inside the VM. Stop that UI
route rather than repeatedly requesting approval or bypassing it with another
UI automation technology. The pending Computer Use permission belongs to the
host, and has not been granted. Continue independent controller/repository work;
GUI acceptance remains open. No visibility assertion has been removed or relaxed.

## Host approval received; setup screen confirmed

Larry subsequently approved Computer Use. Tart accessibility and screenshot
access now work. The fresh VM visibly remains in Setup Assistant, initially on
Accessibility and then on “How Do You Connect?”. A Messages Agent request for
the “sandbox” keychain repeatedly reappears after Cancel. No password was entered
and no keychain access was granted. The earlier statement that host permission
has not been granted is superseded by this observation.

The normal-app probe was rerun through the scoped controller channel after
approval. It still reported overall `passed: false`: shown, reshown, restored
and actual minimization failed; hide/detach passed. Application activation was
false and occlusion remained 8192. Setup has not been confirmed complete, so
neither this result nor host approval establishes desktop visibility acceptance.

## Recurring keychain prompt resolved

Inspection of `sandbox/guest/worker.sh` confirmed that provisioning creates the
worker's default `sandbox.keychain-db` with a synthetic test credential. Its
unlock does not survive the GUI restart. Through the trusted controller, a
guest-only command verified UID 502 and the virtual-machine flag, then unlocked
that exact keychain using its existing provisioned credential (exit 0). No
credential was changed and no host keychain or production vault was accessed.

After dismissing the outstanding dialog once, it stopped recurring. Computer Use
advanced Setup Assistant through offline connection selection and the Data &
Privacy notice. The next observed screen requests an age range. Desktop setup
and visibility acceptance are still incomplete. A GUI setup runbook must account
for unlocking the synthetic test keychain after a worker-session restart; this
recovery has not yet been added to the normal frozen verification runner.

## Worker dispatch after GUI login

The controller previously always prefixed candidate commands with `sudo -u
mortimer-dev`. When Tart's executor is already in that unprivileged GUI session,
sudo correctly refuses access. The dispatcher now recognizes the actual worker
UID/name and runs directly; a root/admin session still drops privileges with
noninteractive sudo. Both routes verify real UID, effective UID and name before
candidate execution and set HOME/USER/LOGNAME to the worker. Unexpected accounts,
a failed sudo invocation, and a failed privilege drop stop before the payload.
The worker has not been added to sudoers or given an administrator role.

All 107 sandbox tests passed in the offline VM, including five new shell-dispatch
tests exercising direct worker execution, literal argv and exit-code preservation,
root/admin dispatch, mismatched identities, and failed privilege drops. The OS
identity/sudo boundaries are stand-ins in those unit tests; they do not prove an
actual administrator-session transition. Log SHA-256:
`d467f3376f64fdeea59c695d312738cffc219910d91d7437d93c786da2b19751`.

A separate invocation using the real Tart worker session and the new dispatcher
returned real/effective UID 502, HOME `/Users/mortimer-dev`, USER/LOGNAME
`mortimer-dev`, and a failed `sudo -n true` privilege check. Host and guest hashes
matched for the executed controller and tests:

- `sandbox/control.py`: `6df7a06227f3522f93112ceb6d59ca48210c27dc2549cd7e7c09eb7391782eb5`
- `sandbox/tests/test_control.py`: `b106c68da0c866564ff20d9cb109b305a181daa53e316be6a2639b0e51759ca4`

These are development diagnostics, not a fresh frozen verification receipt or
proof of desktop/visibility acceptance. Setup remains paused at the age-range
selection pending Larry's confirmation. P2 live metering and hardware acceptance
remain open independently of this runner correction.

## Desktop recovered and native behavior checked

On the next observation, setup had advanced to the Welcome screen. Computer Use
completed Get Started and confirmed the worker desktop. The pending age-selection
block above is superseded. The temporary `.gui-test-password` file was removed
inside the VM after setup; its contents were not displayed or copied out.

On this macOS 26.4 development VM, the original standalone probe passed all six
show/hide/minimize/restore/detach checks. The complete host suite then exposed one
initial-visibility failure among 118 tests: actual occlusion was visible while
the observer still reported false. The failing log was preserved (SHA-256
`038ae7d8a35c7ac466f0c31264b16fa760ec3c192a5b62480c5d874df8705b10`).
No assertion or wait duration was weakened. The observer now also listens for
completed window updates and reads visibility when its deferred callback is
delivered. This fixes a pre-show value remaining cached until a later transition.
The complete 118-test suite subsequently passed (log SHA-256
`7f336cb578794c0e94d9c2217a581be0d2c5701707a87c98690fc463293d8f75`).

The standalone probe was extended with real full-window occlusion/uncovering and
application hide/unhide. All ten checks passed; the sanitized result is retained
in `P2-window-visibility-probe-result.json`. These observe actual AppKit states,
not synthetic notification posts.

Two more tests mount the actual wave animation and count presentation requests:
active visible animation requests new samples; hidden animation stops and resumes
when shown; the reduced-motion animation remains static. SwiftUI's system
Reduce Motion environment value is read-only, so an initial test-build failure
was preserved (log SHA-256
`852694a626cf1380fc9cb645f86210b912d0d4f12d96a11c2aa010fc83490baa`).
The view now passes that system value to its shared animation content; tests
supply the value to the same content without changing macOS preferences.

Final result: all **120 host tests passed**, no skips, in 40.090 seconds of test
execution (44.125 seconds for the verifier check including build/setup). Log
SHA-256 `72aa77fa7473319a136a5ae7c42c424dc8352befd6260640ac25725af3dcb51d`.
The four native window tests cover initial visibility, hide/show/minimize/detach,
stale callback teardown, wave sampling suspension/resumption, and reduced motion.
Exact source hashes and environment/check metadata are in
`P2-desktop-verification.json`.

This is positive development-VM evidence, not a new independent frozen receipt.
The normal verification VM's GUI-session prerequisites still need resolving;
do not skip these tests or count a headless failure as acceptance. System-setting
toggle/VoiceOver acceptance, CPU/frame timing on the deployment hardware, real
audio input/playout observations and the remaining hardware matrix stay open.
