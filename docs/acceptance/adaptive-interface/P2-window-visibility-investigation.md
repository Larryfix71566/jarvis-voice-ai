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
