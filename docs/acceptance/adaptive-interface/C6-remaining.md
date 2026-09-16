# What is left, and what closes each

State at `4c0bd01` on `fix/audio-device-resilience` (PR #73), 2026-09-15.
Nine items. Two are decisions, one is an investigation, three need one
hardware run each, one needs re-specifying, and two are someone else's call.

---

## 1. Step 7 — delete the D8 band-aid — DECISION

**What it is.** `AudioInputCoordinator` repoints the system default input to
a rate-matching mic before connecting, to dodge the AirPods 24 kHz
slow-voice bug. D8 says remove it, with `JARVIS_MATCH_INPUT_RATE` and the
input-notice chip, once the native path is the default.

**Why it is still open.** It is gated to `transport is DirectWebRTCTransport`
(JarvisClient.swift:238), so it runs *only* on the rollback path — which §9
has now proven works and which exists precisely for when the native path
misbehaves. Deleting it takes the flag too, so a rollback on AirPods
reinstates the original bug with nothing left to restore the fix.

**To close.** Choose one:
- *Full deletion, per the plan.* `AudioInputCoordinator.swift` +
  `AudioInputChange`, `JarvisFlags.matchInputRate`
  (JarvisConfig.swift:133), `JarvisClient`'s `audioInputChange` /
  `audioInputCoordinator` / connect-path call / `restore()`,
  `AppMessageRouter`'s `audioInputSink`, `UICommandRouter`'s
  `audioInputNotice` + `showAudioInputNotice`, `OrbFieldView`:184 and :244,
  and the `AudioOutputTests` block at lines 53–91. Plus the P0
  preservation-checklist entry. One commit, revertible.
- *Partial.* Delete the flag and the notice UI; keep the coordinator running
  unconditionally on the WebRTC path. Needs a D8 amendment saying why.

Either way it is one commit. Nothing else depends on it.

## 2. `layoutVersion` default — DECISION

**What it is.** The adaptive interface is behind
`@AppStorage("mortimer.interface.layoutVersion") = 0` and a Debug menu item
labelled "Preview adaptive layout" (MortimerHostApp.swift:145). Default 0
shows `OrbFieldView` — the previous layout.

**Why it matters.** It is the reason the new interface appeared not to
exist. Every session up to 2026-09-15 21:36 ran the old view. No plan step
covers flipping it, so it would have stayed hidden indefinitely.

**To close.** Decide whether the adaptive layout is the intended default.
- *Yes:* change the default at the three `@AppStorage` sites (`ConsoleView`,
  `MortimerHostApp`, `DisplayWindowView`), add a test pinning it, and keep
  the menu item as the way back.
- *No:* say so in the closure plan, so the next person does not lose a week
  to it.

## 3. The rebuild churn — ONE HARDWARE RUN

**What it is.** On 2026-09-14, two device changes produced **six** engine
rebuilds in 3.4 s, each costing ~700 ms of dead audio — about 3.5 s where
0.7 s was needed.

**Where it stands.** Instrumented: the configuration-change observer now
logs the current device signature against the one the running graph was
built with, and prints `— NO DEVICE DIFFERENCE` when they match. Three
later sessions did not reproduce it, and in those both changes were
genuine, so the "our own rebuild provokes the next notification"
hypothesis is **unsupported**. The difference is what was done to the
hardware: the churn followed an earbud being physically removed (input
alternating 1 ch / 2 ch), not a Settings switch.

**To close.** One session, connect, then **pull an earbud out** — not a
Settings change. Then read the signature lines:
- all `NO DEVICE DIFFERENCE` → skipping those notifications is safe, and the
  fix is a two-line guard in the observer.
- signatures genuinely differ → it is the hardware settling, there is
  nothing to fix, and it gets recorded as expected behaviour.

## 4. The input channel's observation count — INVESTIGATION

**What it is.** Input observations per session: 1568, 840, **76**, 959. The
76 came from an 87 s session whose capture path delivered ~100 buffers/s —
roughly 8,700 buffers producing 76 accepted observations. `shown` equalled
`arrivals` exactly, so every entry was fresh; the accumulator simply had
nothing to hold most of the time.

**Why it matters.** The C7.5 gate now reads input arrival p95, so the figure
it depends on rested on a 76-sample base once. A gate is only as good as
the sample under it.

**To close.** Not a measurement — a code read plus one instrumented run.
`AudioActivityAccumulator` refuses observations on watermark, 300 ms
staleness and mute-eligibility rules; none obviously explains a 97%
rejection rate on a live capture path. Log the refusal reason per rejected
observation, run one session, count by reason. That says whether it is a
defect or correct behaviour nobody had quantified.

## 5. 24 kHz steady state — OPPORTUNISTIC RUN

**What it is.** AirPods negotiate either rate between sessions: 24 kHz
(480-frame buffers, 20 ms, input arrival p95 41.9 ms) or 48 kHz (10 ms,
23.5 ms). The steady-state gate has only been measured at 48 kHz.

**Why it matters.** 41.9 ms is the closest any healthy measurement has come
to the 50 ms gate. If 24 kHz is the normal case for some configuration, the
threshold has less headroom than it appears.

**To close.** A no-device-change AirPods session that happens to come up at
24 kHz — the engine log line says which. What *determines* the rate is not
known; until it is, this is repeat-until-observed rather than a test that
can be asked for.

## 6. §3.4 latency parity — RE-SPECIFY, THEN TWO SHORT RUNS

**What it is.** The plan wants native vs WebRTC latency compared, gated on a
C0.4 WebRTC baseline that was never captured.

**Why it cannot be done as written.** The client meter needs
`AudioLevelSource`, which only `NativeAudioTransport` implements —
`DirectWebRTCTransport` cannot, since this WebRTC build exposes no audio
renderer. So there is no client-side WebRTC latency to compare against, and
no amount of running produces one.

**To close.** Use the server-side turn metric instead, which the pipeline
emits transport-agnostically: `TURN user_end->first_audio`. The WebRTC
session on 2026-09-15 already produced 899, 1379 and 1431 ms. Two short
matched sessions — same device, same kind of question — give the comparison
the plan actually wanted. Amend §3.4 to name that metric.

## 7. §3.3 echo on AirPods — TWO BENCH RUNS, OR ACCEPT INDIRECT

**What it is.** The echo bench on AirPods-both and AirPods-out +
built-in-mic. Measured on the built-in array only (50.1 dB reduction,
residual 20.3 dB below the idle floor, 0 Silero turns against a control
raising 10).

**Where it stands.** Four AirPods conversations completed with no sign of
the bot transcribing itself, which is indirect evidence, not a measurement.

**To close.** Either `./closure-checks/run-echo-config.command airpods-both`
and `… airpods-out-builtin-mic` — about five minutes, silent, no
conversation needed — or record it as indirectly covered with that caveat
stated. The bench is cheap enough that measuring is the better answer.

## 8. Plan Status → IMPLEMENTED — LARRY'S CALL

Unchanged deliberately. §8 is now done; items 1–7 above are what stands
between here and that line being true.

## 9. PR #71's two open questions — SEPARATE WORKSTREAM

The model-registry split plan merged with two questions unanswered: where
the supervisor pin lives (`model_endpoints.yaml` vs the already-denied
`config/upgrade_agent.yaml`), and whether `scripts/sync_models.py` should be
Tier 0. Both shape the implementation, so they want answering before anyone
starts it.
