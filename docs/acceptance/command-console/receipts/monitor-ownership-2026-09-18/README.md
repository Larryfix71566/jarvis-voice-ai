# Mixed supporting-stage ownership — September 18, 2026

Source: release-review working tree on `b224c84`, including uncommitted changes.
Rebuilt review executable SHA-256:
`6683151f25449100547556d9a0ebb0537ea0513969b31553889696a9a60d1fbd`.

## Corrected behavior

Pointer-selected graph/result content previously lost precedence when transport
panels existed, although the main console said that selection was on the other
display. The stage now reserves one of its four tiles for an unrepresented
pointer selection. A selection already owned by a panel reuses that renderer.
Only explicit pins can appear outside the stage; a displaced unpinned result
remains available in workspace history. Main-window locators now follow actual
visible ownership for every result, including each comparison pane separately.
Layout 1 retains its single selected supporting-content behavior.

## Verification

- `focused-tests.log`: 52 tests passed across content panels, supporting
  display, workspace rendering/state, screen placement and placement policy.
- `live-grid-tests.log`: 3 supporting-display rendering tests passed after
  adding the real two-display mixed-content exercise. The test renders a
  pointer-selected result alongside three transport tiles in real NSWindows
  on the built-in panel and C34H89x, checking screen assignment and accessible
  content. It also checks that the displaced fourth transport tile does not
  escape into an extra floating panel. Five workspace results remain stored.
- `built-in-grid.png` and `external-grid.png`: captured synthetic stage
  renders. These are XCTest-hosted views, not screenshots of a provider journey.
- Plan-manifest checks: 5 passed. `git diff --check` passed.

The first mixed-content test attempts failed because the test process had not
enabled accessibility. Screenshots already contained the content. Enabling
`AXEnhancedUserInterface` before inspecting the rendered tree corrected the
test setup; no content assertion or tile limit was removed.

## Running candidate

The prior app bundle was backed up at
`/private/tmp/MortimerHost-before-monitor-ownership-20260918.app`.
Three stale review instances were stopped; the separate Xcode build and all
backend services were left running. The rebuilt review app (PID 80622) opened
in compact Conversation mode. Pointer navigation loaded the memory graph
(405 visible / 500 loaded nodes; 37 visible relationships), then moved it to
the single `Mortimer Display` stage. Switching back to the console showed the
return locator with no graph controls duplicated in the main surface.

The client still showed `CONNECTING VOICE` while its local socket was
established. This is not a successful voice handshake or provider journey.
Earlier socket-error sessions ended after the backend explicitly logged its
five-minute idle timeout; those errors alone do not prove a display-close bug.

Physical unplug/reconnect is pending user action. Mirroring, three displays,
voice-triggered repeat requests, duplicate-fetch instrumentation and complete
exact-candidate acceptance remain open. This receipt does not close UI2-06,
UI2-19 or UI2-20, and does not supersede the full release gates.

## Connection-startup diagnosis and correction

A one-second native sample of PID 80622 and native transport logs distinguish
the network handshake from the blocked audio engine. The socket opened at
16:39:30.160 and received `voice/catalog` at 16:39:36.605. At 16:41 the audio
startup thread was still inside `AVAudioEngine.inputNode`, waiting on the
AVAudioIOUnit/CoreAudio device-property call. This evidence establishes where
startup was blocked, not why the macOS audio service failed to return.

The sandbox native transport now bounds audio startup at 30 seconds. Its
timeout detaches the failed session without synchronously stopping an engine
whose queue is blocked. The late startup completion stops its orphaned engine;
it cannot revive that session or close a replacement session. This does not
claim to repair the underlying hardware/service condition.

`audio-start-deadline-tests.log` records 22 passing transport tests, including
the blocked-start/late-completion/replacement-session regression.
`jarviskit-startup-full.log` records 190 tests passed with zero failures.
The executable hash above predates this connection-startup correction; it
remains the identity of the observed graph handoff, not the new audio build.

Full post-correction verification passed: JarvisKit 190/190 and MortimerHost
233/233 (`host-full.log`). The companion `P4-frame-time.json` records 300 graph
frames at p50 8.561 ms, p95 9.783 ms, max 14.570 ms, below the unchanged 33 ms
gate. The rebuilt/signed executable including the startup correction has
SHA-256 `10a653a8e8943c5ddd3e97f0ada1b578e68f6bd23ec483ec44322501f6f39933`.
It was launched for the next live startup and monitor exercise.

Live verification of that executable showed the new explicit message
`audio device startup timed out; check the selected input/output devices and reconnect`,
an enabled Connect button and responsive graph navigation. The timeout/UI
recovery behavior is verified on the Mac; successful audio startup remains
open. The prior indefinite Connecting state is not being counted as a voice
acceptance pass.
