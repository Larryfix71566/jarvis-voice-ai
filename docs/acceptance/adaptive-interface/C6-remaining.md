# What is left, and what closes each

**Status index, reconciled 2026-09-17 against `e6b34cf`:** this file is a
chronological investigation log, including resolved items and superseded
proposals. Use `RELEASE_READINESS.md` for release gates. PR #76 is merged;
the release consolidation merged as PR #80 (`88b206f`, 2026-09-22). This does not
prove that the running services have loaded the release fixes.

**Reconciled 2026-09-22 against main `88b206f`.** PR #80 is no longer under
review. It merged as `88b206f` on 2026-09-22 (squash of branch head
`1318f65`). PR #76's code reached main through PR #78 (`af2d0cf`); #76's own
merge (`e6b34cf`) changed only `docs/REPO_MAP.md`. The commit hashes cited
below as `1acd275`, `fabc349` and `2bc51dc` are branch commits and are not
ancestors of main. Their content is on main via `af2d0cf` (checked by
matching each commit's added lines against the tree at `af2d0cf`). Whether
the running services have loaded `88b206f` is still not recorded.

**Historical inventory at `1acd275`** (branch commit; content on main via
`af2d0cf`):
Fourteen
items. Two are decisions,
two are investigations, three need one hardware run each, one needs
re-specifying, two are someone else's call, and one is a defect with a
measured cause.

Items 10 and 11 were added by Larry on 2026-09-16 from daily driving, not
from the plan. They outrank items 1-9: both are in the interface he is now
using every day.

---

## 1. Step 7 — delete the D8 band-aid — RESOLVED 2026-09-17 (partial)

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

**RESOLVED 2026-09-17 as the partial option, on the question Larry asked:**
would the band-aid be used for a remote connection in the future roadmap,
or does the native path remove the need altogether? **It would, and the
native path does not.** Read from the code:

1. **Remote is WebRTC by design.** `usesNativeAudio`
   (`JarvisClient.swift:114`) returns true only when the bot host is in
   `{127.0.0.1, ::1, localhost}` (D1); every other host gets
   `DirectWebRTCTransport`, and the coordinator is gated to exactly that
   transport. Remote is the only path on which it ever runs.
2. **The native path avoids the bug rather than fixing it.** From the
   coordinator's own docstring: AirPods Pro 3 present as *two* CoreAudio
   devices — a 48 kHz output and a separate 24 kHz mic — and WebRTC runs
   *one* duplex audio unit so it can echo-cancel, so the 24 kHz capture
   clock drags 48 kHz playout to half speed. `AudioEngineIO` taps input and
   converts at whatever rate the hardware reports; there is no shared
   duplex clock to drag. The bug is structural to libwebrtc's ADM in this
   build, which exposes no device-selection API — the system default input
   is the only lever that exists.
3. **Native cannot take over remote.** `NativeAudioTransport` contains no
   jitter buffer, no loss concealment and no reordering (zero matches):
   raw 16 kHz Int16 PCM on a WebSocket. Those absences are exactly why it
   is *better* on loopback (§3.4: no Opus, no jitter buffer) and why it
   would be unusable over a WAN.

**A cross-plan error this exposed, now fixed in both places.** The
native-audio plan said step 7 was "Subsumed by T1.4 if the whole WebRTC
client path goes." It does not go: `MORTIMER_WEB_RETIREMENT_PLAN.md`
retires the *web console*, and its only mention of WebRTC is a `CLAUDE.md`
edit that **keeps** the Swift client's — the architecture diagram becomes
"Native app (JarvisKit) --WebRTC--> Python bot". T2 needs that path too, so
the conditional could never fire. The Mortimer Plan Status page had
repeated the same wrong claim (that T1.4 dissolves this item); both are
corrected.

**What changed:** `JarvisFlags.matchInputRate` and
`JARVIS_MATCH_INPUT_RATE` are deleted, and the correction runs
unconditionally on the WebRTC path. A kill switch for a fix whose own
docstring says a mismatch "produces unusable audio" had no legitimate
off-position, and it is the same class of lever as `JARVIS_FORCE_WEBRTC`,
found this week to have been silently doing nothing. The coordinator and
the input notice **stay** — the notice truthfully reports a device change
the user did not make, which matters more on a remote session, not less.
D8 is amended in the plan with all of the above.

**No replacement test**, deliberately: the guarantee is now "no symbol
exists to turn this off", which the compiler enforces and a test cannot
express without adding a production introspection hook purely for the
test's sake. `AudioInputCoordinator.rateMismatch`'s own tests still cover
the decision the coordinator makes.

**When the coordinator can actually go:** when the WebRTC *client* path
does, which no current plan does. Not gated on the native path being the
local default, which it now is.

## 2. `layoutVersion` default — CLOSED 2026-09-17 (C9.5, on G-C8's escape hatch)

**This entry was wrong as first written.** It said "No plan step covers
flipping it, so it would have stayed hidden indefinitely." The closure plan
covers it three times:

- **L4:** "Deployment target: `main` + installed on the MacBook Air with
  adaptive layout ON by default. `mortimer.interface.layoutVersion` defaults
  to `1` after acceptance."
- **G30** (gap register): "Adaptive layout off by default (L4)" → closure
  item **C9.5** → "Default flipped in its own PR after C8".
- C9 ladder item 7 spells out the change: default `1`, keep
  `Debug ▸ Use previous layout`, update both plans' status headers,
  `CLAUDE.md` and `docs/REPO_MAP.md`.

So the default being 0 is deliberate, tracked and sequenced — not an
oversight.

**What actually stands in front of it: C8 has not started.** C8 is an
integrated acceptance pass on the deployment Mac with five requirements —
the P0 preservation matrix exercised in *both* legacy and adaptive modes,
the §9.2 visual cases at five sizes, §9.3 real audio on the C0.4
paired-trial protocol, §9.4 monitor and rollback cases, and an independent
C5 receipt for the exact commit. Gate G-C8 requires every row to carry
positive evidence, or to be named in `C8-open-items.md` with Larry's written
acceptance as a known limitation.

Evidence it is unrun: `P0-preservation-checklist.md` has no exercised rows,
and `C8-open-items.md` does not exist.

**Why the gate is the right shape.** Flipping the default gives the adaptive
layout to everyone who launches the app, and the preservation matrix is
precisely the instrument for establishing that everything the previous
layout could do, the new one still can. Defaulting it on beforehand is the
class of regression that checklist was written to catch.

**To close.** Two separable things, and conflating them is what made this
look like an oversight:
- *Using* the adaptive layout needs no gate and is already done —
  `Debug ▸ Preview adaptive layout`, which persists per user. One menu
  press. That was the thing actually wanted.
- *Defaulting* it is C9.5 behind C8. Either run C8, or take the plan's own
  escape hatch: flip it and record the unexercised rows in
  `C8-open-items.md` with written acceptance. The second is legitimate under
  Gate G-C8, but it should be a deliberate choice rather than a shortcut
  taken by someone unaware the gate existed.

**CLOSED 2026-09-17.** Larry: "lets push layoutVersion default to 1 and
clear that item." Default flipped to `1` in all three declarations
(`MortimerHostApp`, `ConsoleView`, `DisplayWindowView` — they must agree or
the app disagrees with itself about which layout it is in). `Debug ▸ Use
previous layout` retained per L4, so the rollback is a menu press.
*(Reconciled 2026-09-22 against main `88b206f`: the flip to `1` reached main
in `af2d0cf` (PR #78). PR #80, `88b206f`, then moved the default to `2`
(Command Console), with a one-time migration of missing/`1` preferences to
`2` in `MortimerHostApp`. There are now more than three declarations: every
`@AppStorage("mortimer.interface.layoutVersion")` defaults to `2`. The
`ConsoleView.swift:88` citation below is now `:105`. See `C8-open-items.md`
for the current line map.)*

**C8 was NOT run**, and this closes on Gate G-C8's second route: every
unexercised row named in `C8-open-items.md` with Larry's written acceptance.
That file groups the 24 rows by whether the flag can reach them, which is
the substance of the acceptance rather than a formality:

- **13 rows are structurally outside the flag.** `DrawerView()` is
  instantiated at `ConsoleView.swift:88`, outside the `layoutVersion`
  branch, so the eight drawer tabs and the shared tab behaviours render
  identically in both modes. The flag can neither break nor hide a defect
  in them. They remain owed as T1.3 §8 V3–V8, not as a gate on this flip.
- **6 rows have incidental evidence** from daily use since 09-15 — top bar,
  mic toggle and wake-while-muted, orb states, agent satellites, the app
  menus, and `DisplayContentView` (the memory graph rendered to the display
  window at 12:51 today). Not row-by-row screenshots, which is what C8
  asks for, but not unknown either.
- **5 rows are the accepted risk**, each reachable only in adaptive mode:
  the drawer's width and drag path, display-panel routing through the
  workspace instead of `SingleDisplayPanel`, the workspace pins/A-B
  surfaces, the `OrbFieldView` notices inside a 150 px or 140 px compact
  region, and `DisplayWindowView`'s supporting-content branch. Plus
  multi-display DP8, which is unwalked in both places.

Of those five, the one worth watching is the **pending-draft notice**: the
others fail visibly (a wrong width, a result that does not appear), while
missing that notice means not knowing a write is awaiting confirmation.

Also updated per C9 ladder item 7: both plan status headers, `CLAUDE.md`
(with the three-declarations rule and the "do not cite C9.5 as evidence the
preservation matrix passed" caveat) and `docs/REPO_MAP.md` (naming
`AdaptiveStageView` and `WaveTuningView`, paid for by condensing prose to
stay under the character cap — 7963 now).

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

## 4. The input channel's observation count — RESOLVED 2026-09-17 — NOT A DEFECT

**It was never a rejection rate.** `observations` is not a count of accepted
samples against offered ones — it is how many of the report's trailing
60-second window had a level present at all, and it is hard-capped:

```
observations = min(hz * window, hz * seconds-of-level-present)
             = min(30 * 60, 30 * seconds)   =   min(1800, 30 * seconds)
```

`AudioActivityObserver.sample()` appends to `displayed` once per 30 Hz tick
per channel whenever the snapshot carries a `measuredAt`, then drops
everything older than `moment - 60`. So the figure is a **duty cycle over a
trailing minute**, and 1800 is its ceiling, not a healthy reading.

| report | observations | = seconds of level | % of window |
| --- | --- | --- | --- |
| 2026-09-17T01:35Z input | 1800 | 60.0 | 100% — **saturated** |
| the "1568" case | 1568 | 52.3 | 87% |
| the "840" case | 840 | 28.0 | 47% |
| 2026-09-17T01:49Z input | 220 | 7.3 | 12% |
| the "76" case | 76 | 2.5 | 4% |

The 87-second session that produced 76 is not a path delivering 8,700
buffers and accepting 76. It is a report written when only the last 2.5
seconds of the trailing minute had a level — the window looks back 60 s
from the moment the report is taken, not over the session.

**The discriminating check, on two reports 14 minutes apart.** If the count
measured sampling health, an 8.2x drop in it would move the cadence. It does
not:

| | observations | arrivals | arrival p50 | arrival p95 |
| --- | --- | --- | --- | --- |
| 01:35 input | 1800 | 1800 | 19.5 ms | 24.7 ms |
| 01:49 input | 220 | 220 | 19.9 ms | 25.2 ms |

Same cadence at both ends. And `observations == arrivals` on the input
channel in both, which is the earlier note that "`shown` equalled `arrivals`
exactly" — correct, and it means every tick carried a *fresh* buffer. The
accumulator was not refusing anything. Nothing to instrument; no run needed.

**Two real gaps this exposed, neither a defect in the meter.**

1. *The gate has no minimum-sample floor.* `AudioMeterLatencyReport` renders
   `"gate": "pass"` from `arrival_p95 <= 50 ms` at any count above zero, so a
   report taken 2.5 s after connect passes on 76 samples, where p95 is the
   72nd value of 76. Defensible, thin, and nothing in the artefact says so.
2. *The artefact invites exactly the misreading above.* It records
   `window_seconds: 60` and `sample_hz: 30` but not how much of the window
   held data, so a saturated window and a 7-second one are indistinguishable
   from a full one without doing this arithmetic by hand.

Proposed, NOT done here: a `coverage` field
(`observations / (window_seconds * sample_hz)`) and a sample floor on the
verdict. Both change what a **gate** reports, and per section 6 of the
closure plan that is Larry's call, not a side-errand — the same reasoning
that left the C3.1 frame-time gate alone below.

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

## 6. §3.4 latency parity — RE-SPECIFIED AND CLOSED 2026-09-17

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

**CLOSED 2026-09-17, on evidence already on disk.** Re-specified in the
plan (§3.4 finding) into the two halves that can be attributed: the
pipeline half is `TURN user_end->first_audio`, which the bot prints per
turn; the transport half is what the C7.5 meter measures on native and
cannot be measured on WebRTC with this build. Every `bot-c6.log*` is a
native session: 39 `TURN` lines, 7 artefacts at 0–19 ms excluded, **32 real
turns — median 1084 ms, p95 2613 ms**, against the §9 WebRTC session's
899/1379/1431 ms. 21 of 32 native turns sit at or below the WebRTC median.
No native penalty on the pipeline half; the transport half is better by
construction (no codec, no jitter buffer). Caveat recorded in the plan: the
WebRTC side is n=3.

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

## 8. Plan Status → IMPLEMENTED — LARRY'S CALL, NARROWED 2026-09-17

Why it is still listed, precisely: §6 step 8 of the native-audio plan
assigns this flip to Larry, "after §8" — the plan names him as the actor, so
no amount of work here closes it. What *has* changed is the blocker list.

Closed since this item was written: item 1 (step 7, resolved as a partial —
D8 AMENDED), item 2 (`layoutVersion` default), item 6 (§3.4 latency parity,
closed on the 32 native turns already on disk). The docs half of step 8 is
also done — `CLAUDE.md:92` carries the native-audio section and
`docs/REPO_MAP.md:116` names `NativeAudioTransport` (at `88b206f` that
line is `docs/REPO_MAP.md:113`; `CLAUDE.md:92` is unchanged — reconciled
2026-09-22).

Still blocking the unqualified word — **two**, both needing AirPods in hand
(item 4 resolved 2026-09-17 by a code read: it was never a defect):

- item 3 — rebuild churn, one earbud-removal run
- item 7 — §3.3 echo bench, or written acceptance of the indirect evidence

Item 5 (24 kHz steady state) is opportunistic and does not gate this line.

The plan header and §6 steps 7/8 were refreshed 2026-09-17 to say exactly
this; they previously read "Step 7 and five measurement items remain open",
which was wrong on both counts. The consumer of the status line is
`MORTIMER_ADAPTIVE_INTERFACE_CLOSURE_PLAN.md` C11 item 2.

## 9. PR #71's two open questions — SEPARATE WORKSTREAM

The model-registry split plan merged with two questions unanswered: where
the supervisor pin lives (`model_endpoints.yaml` vs the already-denied
`config/upgrade_agent.yaml`), and whether `scripts/sync_models.py` should be
Tier 0. Both shape the implementation, so they want answering before anyone
starts it.

## 10. The wave lost its amplitude and width — ARCHIVED 2026-09-23 (replaced by the atom display)

**Archived 2026-09-23 — the wave is no longer drawn.** Larry, 2026-09-23: *"the
wave has been replaced by a new visual representation of the AI so that can be
removed or archived in the plan."* Checked against `main` at `88b206f` (no Swift
source changed in `ce797a3`): `WaveEngine.draw` calls `drawAtom` and returns
whenever a measured presentation is supplied, which is layouts 1 and 2. The
wave is drawn only on the legacy layout 0, with its original simulated
envelope, not the measured wave this item tuned. What this item produced now
splits two ways:

- **Still live — it feeds the atom (UI2-21).** `AudioPresentationTuning.presentationLevel`,
  its four per-channel dB windows and their sliders under `Debug ▸ Wave level
  windows`, the crossed-window fallback, and the 0…1 clamp. `drawAtom` reads
  both channels through it. `PresentationLevelMappingTests`, including the
  shared-window relation, still test the atom's input, and
  `testUnavailableSpeechRendersIdenticallyAcrossTime` now guards the atom
  staying still when nothing arrives.
- **Unreachable on every layout.** The 10b width slider (`waveWidthFraction` is
  read only on the measured-wave path, after the atom's `return`), the
  `staticTrace` easing freeze from `2bc51dc` (reached only when there is no
  presentation, where `staticTrace` is always false), and the wave's depth
  layers. Removing them, and renaming the Debug window now that it tunes the
  atom, is a code change with its own build and test run; it is not part of
  this archive.

The record below is kept as history.

**What it is.** Larry, 2026-09-16: "the sine wave for voice interaction lost
its amplitude and width from the previous version, I want that back."

**Cause.** Three separate terms, all in `VoiceWaveView.draw`'s adaptive
branch (`presentation != nil`), plus a layout choice. The amplitude line is
`amp = h * (dyn.base + breath + voice + 0.01 * flash) * ampScale`
(VoiceWaveView.swift:235, `ampScale = 2.0`):

1. **`dyn.base` is pinned to `0.004`** (VoiceWaveView.swift:196). That is the
   `.offline` target. The legacy path eases `dyn.base` toward the per-state
   target - `0.016` speaking, `0.01` listening (the `targets` table, :93-98).
   So the adaptive trace draws its *resting* thickness from the offline value
   in every state, a 4x cut while speaking.
2. **`voice = level * 0.115` now carries a real level** (:218). Both paths use
   the same `0.115`. Legacy fed it `simLevel(t)`, which returns
   `0.25 + 0.75*|...|` - a floor of 0.25 and a ceiling of 1.0 (:144-147).
   Adaptive feeds it `measuredEnvelope.advance(...)`, i.e. linear RMS, 0...1
   full scale (`AudioLevelSample.rms`). Speech RMS is nowhere near 1.
   Worked, at `h = 800`: legacy speaking peak
   `800 * (0.016 + 0.115) * 2 = 210 px`; adaptive at a measured RMS of 0.10,
   `800 * (0.004 + 0.0115) * 2 = 25 px`.
3. **`dyn.speed` is pinned to `0.45`** (:199), against a legacy speaking
   target of `1.0`. The wobble runs at a little under half rate, which reads
   as less alive even at equal amplitude.

**Width** is not the window function - `env = exp(-((x-cx)/(0.11*w))^4)` is
identical on both paths, so the lobe is always the same *fraction* of `w`.
What changed is `w`. Legacy renders the wave as a full-window background
(`ConsoleView.swift:44`, `.ignoresSafeArea()`), so `w` is the window width.
Adaptive has three call sites (`AdaptiveStageView.swift:53/66/78`) and only
the first is full-size: `.rail` clamps to `height: 150`, `.bottom` to
`width: 140`. At `w = 140` the lobe's half-width is `0.11 * 140 = 15 px`.

**What is not yet measured.** The actual RMS of Larry's speech through this
capture path. Item 2's figure of 0.10 above is illustrative, not observed -
no artifact records level magnitudes (`P2-latency.json` records arrival
*timing* only). That number sets how much of the 210 -> 25 px gap is the
level scale versus the base pin, so it decides which term to fix and by how
much.

**To close.** In order:
- Log `max(userLevel, outputLevel)` over one ordinary conversation. One
  os_log line in `VoicePresentationState.derive`, one session, one number.
- Then pick a mapping deliberately rather than reusing `0.115`: a measured
  RMS needs its own curve (a gain, or a perceptual/log mapping) to land in
  the same visual range the simulation occupied. This is the real decision -
  the honest level should stay honest and still be visible.
- Let `dyn.base` and `dyn.speed` ease to their per-state targets on the
  adaptive path too, instead of being pinned to the offline values. Keep the
  §7 colour pinning, which is a separate and deliberate choice (C2.4).
- Decide the frame: whether `.rail`/`.bottom` should give the wave more room,
  or whether the full-size `.conversation` wave is the one Larry means by
  "the previous version". Ask before changing the layout; the numbers above
  are enough to fix amplitude without touching it.

**CLOSED for amplitude, 2026-09-16 (`fabc349`; branch commit, content on
main via `af2d0cf`).** Fixed by mapping the level
through its channel's dBFS window before the envelope, and by letting
`dyn.base` and `dyn.speed` ease to their per-state targets instead of being
pinned to `0.004` (the `.offline` value) and `0.45`. A gain constant was
ruled out by measurement, not preference: the input channel spans 134x
between its median and its p95, and `VoiceEnvelope.advance` rejects a target
outside 0…1, so a large gain would make loud syllables vanish rather than
clip. Because a dB-normalised level occupies 0…1 the way `simLevel` did,
`0.115` needed no change and stopped being an inherited constant.

Verified against Larry's own session, not against the arithmetic — the
reading at 2026-09-17T00:33:36Z, written by the automatic session-end
trigger:

| channel | median | p95 | peak | legacy |
|---|---|---|---|---|
| input | 75 px | 189 px | 208 px | 72–210 px |
| playout | 85 px | 181 px | 205 px | 72–210 px |

Larry, on seeing it: *"visually it is back to what we had in the previous
interface so I like it."* That is the acceptance — the criterion was always
perceptual, and no measurement substitutes for it.

Which window reads best is also perceptual, so the four dB values are
UserDefaults-backed and `Debug ▸ Wave level windows` drags them live while
talking, with the measured values as fallbacks and a copyable summary.
Larry: *"I like that implementation."* The defaults were left where they
are, because they are where he liked the trace.

Note for the record: the input median measured 0.0012 on the first reading
and 0.0046 on the second — a 4x spread, from how much inter-syllable silence
falls inside the 60 s window. So the trace is livelier on continuous speech
than on sparse speech by design; raising the floor toward −50 dB would
compress that if it ever grates.

**Compact-rail follow-up (2026-09-18):** the measured presentation now uses
separate post-normalization gains for the two real channels: `0.55` for input
and `0.42` for playout. This is a rendering correction only; it does not add
an envelope when no measured level arrives. The fresh receipt recorded 403
input arrivals and 84 playout arrivals, so the input path is now physically
observed while the two-channel P2 arrival-count gate remains open.

**WIDTH — CLOSED 2026-09-17 as a slider** (`1acd275`; branch commit,
content on main via `af2d0cf`). Larry: "add a slider
option like the amplitude so that it is customizable by the user."

The `0.11` in the super-Gaussian window
`exp(-((x - cx) / (0.11 * w))^4)` *is* the width: the lobe's half-width as a
fraction of the frame, identical on every layout mode. It is now
`AudioPresentationTuning.waveWidthFraction` — UserDefaults-backed with 0.11
as the fallback, clamped to 0.04…0.45 so a stray `defaults write` can
neither divide the window by zero nor exceed the frame — and it is the fifth
slider in `Debug ▸ Wave level windows`, carried in the copyable summary as
`width 0.11`. Applied on the adaptive path only; the legacy rollback keeps
the constant, because a rollback's value is being the thing already known.

**What the slider cannot do, stated so it is not discovered later:** widen
the *frame*. In `AdaptiveStageView`'s `.bottom` mode the wave draws into
`width: 140` and in `.rail` into `height: 150`, so the lobe is a fraction of
that however the slider is set; only `.conversation` gives it the full
stage. If the trace still reads narrow after the slider is at 0.45, the
remaining change is a layout one — which mode gets more room — and that
needs Larry to name the mode he is in when it reads wrong. Not carried as an
open item: the slider is the thing he asked for, and there is no evidence
yet that it is insufficient.

One test: the fraction reads back exactly, clamps 0.0 → 0.04 and 3.0 → 0.45,
and falls back to 0.11 on a non-finite value. The tuning tests'
save-and-restore covers the width key too, so a tuning session survives a
test run.

**Regression risk.** C7's whole point was that the meter shows measured
audio. Re-inflating the trace must not reintroduce motion when nothing is
arriving: `staticTrace` (:152) and the `VoiceEnvelope` clamp on stale or
absent levels are what keep that true, and any gain applied has to sit
*inside* them, not around them.

## 11. A sub-agent is unusable after an error — ROOT CAUSE FIXED 2026-09-17

**What it is.** Larry, 2026-09-16: "when a sub-agent hits an error it is no
longer usable... I need to be able to overcome an error and not have to
re-boot the interface to regain the use of the sub-agent."

**Only one mechanism in the codebase refuses a delegation *because* of a
prior error**: the A2 retry guard (`jarvis/agents/delegate.py:330-364`).
On `FAILED:` it records `last_failure[agent] = (task_tokens, now)` (:462).
The next delegation to that agent is refused when all of:
- it arrives within `RETRY_GUARD_WINDOW_S = 120` s of the failure;
- `_overlap_score(prior, new) >= 0.5`;
- and it is not an *earned* continuation.

Three properties make it match Larry's description exactly:

- **It is session state.** `last_failure` is a closure local of
  `build_delegate_tool`, called from `build_pipeline` (pipeline.py:417),
  called from `run_session`, which pipecat runs **once per connection**
  (`jarvis/bot/bot.py:65`). A reconnect builds a fresh empty dict - which is
  what "re-boot the interface" does.
- **The escape hatch cannot be reached after a plain failure.** `continuation`
  is only honoured if `awaiting_user[agent]` is true, and that is set from
  the *agent's own reply* containing `NEEDS-INPUT:` or being exhausted
  (:458). A plain `FAILED:` sets it **false**. So after an ordinary failure
  there is no legitimate way for the Supervisor to re-delegate - and no way
  for Larry to authorise one either. An unearned claim is logged
  `delegate_continuation_unearned` and refused anyway.
- **A short natural re-ask is the most likely thing to be refused.**
  `_overlap_score` divides by the *smaller* token set
  (`jarvis/procedures.py:137-146`), so any terse follow-up whose tokens are a
  subset of the failed task scores **1.0**. "try the memory graph again"
  after a failed memory-graph task is a guaranteed refusal.

**The second candidate is the prompt, not the code.** Supervisor rule 11
(`jarvis/prompts.py:73`) says to report the sub-agent's reason and *ask how
to proceed*, and "Never immediately re-delegate a reworded version of a task
that FAILED". A model over-applying that will refuse to try again for the
rest of the conversation - also conversation-scoped, so also cleared by a
reconnect. Same symptom, different fix.

**Why the one occurrence that matters cannot be attributed.** A guard
refusal returns before `run_id` is generated, so **it creates no run row** -
`agent_runs` cannot show it. Its only trace is
`logger.info("delegate_retry_guard_refused ...")` on the bot's stdout.

That stdout *is* captured. The launcher Larry actually runs,
`closure-checks/run-bot-c6.command`, pipes it to
`closure-checks/logs/bot-c6.log` with `PYTHONUNBUFFERED=1`. The defect was
that it used a bare `tee`, which **truncates** - so every relaunch destroyed
the session before it:

- The librarian failed at 2026-09-16T00:09:18 UTC, which is 20:09 local.
- `bot-c6.log`'s first line is `2026-09-15 20:47:10`: a single launch,
  431 KB, ending 21:59. The bot was relaunched at 20:47 and took the 20:09
  session's log with it.
- What survives in that window: three delegations, all `analyst`, all
  `subagent_done` with no failure, and **zero** `delegate_retry_guard`
  lines. Nothing to attribute, and nothing that rules the guard out either.

`scripts/mortimer.sh` has rotated the launchd stack's logs through five
generations since the run-logging plan's D11, for exactly this reason. The
closure-checks launcher never did. Fixed 2026-09-16: same rotation, then
`tee -a`. That launcher lives under `closure-checks/`, which
`.git/info/exclude` ignores, so the fix is on the deployment Mac and not in
this commit.

What the run log *does* show (queried 2026-09-16): 40 runs, 4 failed. The
one relevant sequence is 2026-09-13 - analyst failed at 22:44:41, ran fine
at 22:49:54 (5 min later, outside the 120 s window), failed again at
22:50:18. Consistent with the guard, and equally consistent with no guard at
all. The newest failure is the librarian above,
`memory_graph_view found no node matching "interests"`, with **no librarian
run after it**.

**To close.** Three steps, in order:
1. **Stop destroying the log.** Done 2026-09-16 - the launcher rotates five
   generations and appends instead of truncating. Until that was in, the next
   occurrence would have been erased by the next restart, which is precisely
   what happened to the last one.
2. **Reproduce and discriminate.** The librarian failure above is
   reproducible - ask for a memory graph of a node that does not exist. Then
   re-ask *in the same words* inside 120 s:
   - Mortimer relays "blocked by a safety guard" wording, or the log shows
     `delegate_retry_guard_refused` -> **the guard**. Fix is an
     authorisation path.
   - Mortimer instead says it failed and asks how to proceed, and will not
     act on "try it again" -> **rule 11**. Fix is a prompt amendment.
   Then wait past 120 s and ask again. If it runs, nothing is permanently
   latched and a reconnect was never actually required - worth knowing either
   way.
3. **Fix, per the outcome.** If it is the guard, the design constraint is
   real and must be kept: A2 exists because a live session produced six
   reworded retries in a row, one inventing "vault credentials", so
   authorisation must come from a source the Supervisor **cannot author**.
   `NEEDS-INPUT:` qualifies because another model wrote it. Options, to
   choose before writing code:
   - *User speech as the authoriser.* Allow one retry when a user transcript
     frame arrived between the refusal and the retry. STT output is not
     model-authored, so it cannot be forged - the same property that makes
     `NEEDS-INPUT:` usable.
   - *Refuse once, then warn.* The first re-delegation is refused; a second
     runs with the refusal text appended to the task. Bounded, not unbounded.
   - *Shorten the window.* Least invasive, does not solve "I want to retry
     now", and 120 s was not chosen arbitrarily.
   Whichever is chosen, the refusal text should stop claiming there is no way
   forward when there now is one.

**What must not regress.** The A2 test suite, and the 2026-08-25 carve-out
for the confirm-half of a two-phase flow (`_shares_long_identifier`). Any
new path has to leave both intact.

---

## Test result for item 11 — 2026-09-16, 11:42-11:45 local

Ran per the plan above: bot relaunched on the rotating launcher, the
librarian asked for a memory graph of a topic with no nodes, then asked
again in the same words. `closure-checks/logs/bot-c6.log`, one launch,
126 KB.

**Neither candidate fired.**

- **`delegate_retry_guard` lines in the log: zero.** Two librarian
  delegations went out 8 s apart with near-identical tasks
  (`toolu_015xcQQq...` at 11:44:12.869, `toolu_01QXiSD...` at 11:44:20.972)
  and **both ran to completion**. A developer delegation at 11:45:02 also
  ran fine, 41 s, `tools_ok=10`.
- **Rule 11 did not fire either.** The Supervisor relayed the failure
  correctly, re-delegated immediately, then delegated onward to the
  developer. It never declined to try again.

**Why the guard could not fire, which is itself the finding.** The first
delegation was orphaned by an interruption at 11:44:18.845
(`delegate_orphaned_by_interruption run_id=101c52cf`) and did not record its
failure until `subagent_done` at 11:44:21.964 - but the *second* delegation
was issued at 11:44:20.972, about a second **before** `last_failure` was
armed. In the interrupt-heavy path Larry actually uses, a retry routinely
outruns the failure record, so the 120 s window is much harder to reach than
reading the code suggests. The guard is real; it is not what he hit.

**What did reproduce is a third mechanism, and it is the better candidate.**
`SkillRegistry` is built per session (`pipeline.py:979`) and stopped in
`run_session`'s `finally` (`pipeline.py:1440`), where `stop()` sets
`self._tools = {}` (`skills/registry.py:286`). A sub-agent run survives the
session by design (barge-in survival, delegate.py's docstring) - but its
**tools do not**. Measured:

- 11:45:25.433 `[session] client disconnected`, pipeline cancelled.
- 11:45:27.6 the developer's `repo_read_file` calls still work.
- 11:45:33.6 and 11:45:43.9 its `repo_search` calls come back
  `Unknown tool 'repo_search'. Available: none.`
  (`skills/registry.py:332`, with `self._tools` empty).

`repo_search` is a real tool - `mcp-repo` started with 5 tools at
11:43:38 - so this is not a hallucinated name. The run finished `ok` with
`tools_failed=2`, and its own reply says the two failures stopped it from
answering the question it was sent to answer.

That is a sub-agent that is genuinely unusable after an error, triggered
from the client side, and cured by reconnecting - the shape of Larry's
report. **Not yet confirmed as what he experienced**: this needs a
disconnect while a run is in flight. What would test it: delegate a long
task, disconnect the app mid-run, reconnect, and check whether the run's
later tool calls carry `Available: none`.

**Fix shape.** The barge-in design deliberately outlives the voice turn.
Either the registry has to outlive it too (hoist it above `run_session`, or
reference-count it against in-flight detached runs), or a detached run has
to be told its tools are gone and say so, instead of reporting `ok` with two
silent failures. The second is smaller; the first is what the design implies.

**FIXED 2026-09-17 — reproduced by test, not by disconnect.** The
registry-teardown candidate above is confirmed and closed. Mechanism, read
from the source: `run_session` builds one `SkillRegistry` per connection
and its `finally` called `registry.stop()` unconditionally
(`pipeline.py:1440`), emptying `_tools`; barge-in survival deliberately runs
the sub-agent in a detached task the turn's cancellation cannot reach, and
nothing cancels that task at shutdown either — the delegate code even names
"session shutdown" as the case where the task *is* cancelled, and that case
never happened. Neither cancelled nor supported.

Fix: `build_delegate_tool` takes a caller-owned `in_flight` set (like
`late_delivery`); `Runtime.detached_runs` holds it; teardown calls
`drain_detached(runtime.detached_runs, timeout=DETACHED_DRAIN_TIMEOUT_S)`
(120 s — a developer run measured 41 s) **before** `registry.stop()`, and
logs `session_teardown_under_detached_runs` with the count if the deadline
passes. Per-session on purpose: `_background_tasks` is module-level, shared
across sessions, and holds `learn_from_run` and late-delivery tasks teardown
has no reason to wait on.

`tests/unit/test_delegate_teardown.py`, five tests, spawn-free: the defect
reproduced (stop under a detached run → `Unknown tool 'get_current_time'.
Available: none.`), the fix (drain first → the run's tool call returns
`12:00`), the deadline (returns 1 still running), the clean path (nothing
left in flight), and the empty case. **5/5 pass**; delegate + registry
neighbours 63/63; bot wiring 31/31.

## 12. The bot wrote to the wrong database from 2026-09-13 to 2026-09-16 — FIXED

**What it is.** Larry, mid-test: *"I don't understand why they're not there.
We've had many discussions. There should be many memories."* He is right, and
the memories were never lost.

**Measured, both databases, 2026-09-16:**

| | `~/jarvis-voice-ai-clean/data/jarvis.db` | `…/active-repo/data/jarvis.db` |
|---|---|---|
| conversations | 2842, last 2026-09-11T19:20 | 288, last 2026-09-16T15:45 |
| extraction cursor | 2842, updated 2026-09-11T19:20 | **0, updated 1970-01-01** |
| memories | **434** | 2 |
| observations | **146** | 0 |

Everything Larry has said to Mortimer since 2026-09-13 went into
`active-repo/data/jarvis.db`: 288 conversations, an extraction cursor that
has **never advanced**, and two memory rows - a rolling summary and
`fact:user.name`. His real memory, 434 memories and 146 observations, is
intact in the clean copy, where the extraction worker had caught up
completely as of 09-11.

**Why nothing was extracted even there.** `extract_facts_and_observations =
not memory_extraction_v2_enabled()` (`bot/memory_watcher.py:85`,
`bot/pipeline.py:1390`). v2 is on, so the legacy in-session fact writes are
correctly skipped - hence `v2_writes_skipped=True` on every
`memory_updated` line - and the v2 worker
(`jarvis/memory_extraction_worker.py`, launched as `extractor` by
`scripts/mortimer.sh`) is supposed to do the work instead. That worker runs
against the clean copy: `logs/extractor.launchd.log` there was last written
2026-09-11T19:20, and `active-repo/logs/` has no extractor log at all. So
the DB the bot writes has no extractor, and the DB the extractor watches
gets no conversations.

**This also corrects the developer agent's own finding.** It reported
"real emptiness, not lost data… those facts were never stored." True of the
database it could see, and wrong about Larry. It could not check further
because `repo_search` had gone toolless (item 11 above).

**Not a stale read.** The write-ahead logs settled it: active-repo's
`jarvis.db-wal` was 1.77 MB timestamped 15:45 - the test session - while the
clean copy's was 8 KB and untouched since 2026-09-11T19:23, as was its main
database file.

**Root cause - `load_dotenv(override=True)`.** Found by tracing
`sqlite3.connect`, after three rounds of reading the code reached the wrong
conclusion:

`pipecat/runner/run.py:140` calls `load_dotenv(override=True)` at module
import. `find_dotenv` walks up from site-packages and reaches
`~/jarvis-voice-ai-clean/.env`, line 28 of which was
`JARVIS_DB_PATH=data/jarvis.db` - **relative**. `override=True` overwrites
the launcher's absolute export *inside the process*, and the relative path
then resolves against the bot's cwd, which is `active-repo`. The trace,
in the server process (pid 8541 = `Started server process [8541]`):

```
pipeline.py:895  run_session -> run_migrations()
db.py:627        conn = conn or get_conn()
db.py:613        sqlite3.connect("data/jarvis.db")   <- literal relative string
```

Every static reading was correct and irrelevant: `_default_db_path()` does
read the env var, `config.py`'s two bridges do use `setdefault`,
`vault.inject_env` does fill only empty names, and nothing in `jarvis/`
mutates `os.environ`. The mutation is in a dependency, at import time, and
only on the import path `bot.py` takes - `from pipecat.runner.run import
main` inside its `__main__` block. A staged probe that imported
`jarvis.bot.pipeline` and stopped there printed the correct path at every
stage, because it was one import short of the bug.

**Second casualty, same cause.** Only two keys in that `.env` held relative
paths: `JARVIS_DB_PATH` (line 28) and `JARVIS_WAKEWORD_MODEL` (line 38). The
launcher exports both absolute and both were reverted, so the wake-word
model had been resolving against `active-repo` too. `JARVIS_VAULT_PATH` is
not in the `.env` at all, which is why the vault kept working - override can
only clobber a key the file defines.

**Fix.** Both keys in `~/jarvis-voice-ai-clean/.env` made absolute. The
`.env` is the authoritative source precisely because pipecat re-reads it
with `override=True` on every launch; no shell export can outrank it. The
launcher's own exports are now redundant rather than wrong.

**Verified 2026-09-16 12:30.** Traced opens in both the server process
(pid 8669) and an MCP child (pid 8682) now name
`/Users/larryfix/jarvis-voice-ai-clean/data/jarvis.db`. The real database,
read live:

| | before | after |
|---|---|---|
| conversations | 2842, last 09-11 | **2847, last 16:31:26** |
| extraction cursor | 2842 @ 09-11T19:20 | **2847 @ 16:31:39** |
| memories | 434 | 434 |
| agent_runs | - | 458, last 16:31:17 |

The extraction worker was alive and watching the right database the whole
time - it simply had nothing to do. Thirteen seconds after the bot started
writing to the right file, the cursor was current.

**The stranded conversations: merged, and it produced nothing.** Larry chose
to see the plan first (`closure-checks/MERGE-PLAN.md`), then applied it at
12:38. 299 conversations and 44 `agent_runs` moved; destination went
2847 → 3146 with `conversations_fts` matching at 3146, which is the FTS
trigger confirming itself rather than being assumed. The extraction worker
picked them up on its next tick with no cursor rewind, exactly as the plan
predicted, and ran to 3146.

Yield, measured from the worker's own log across the merged range
(turn > 2847):

| | |
|---|---|
| exchanges extracted | 94 |
| facts | **0** |
| observations | **1** |
| promoted | 0 |

**CORRECTED 2026-09-17 — the yield conclusion below was wrong.** The
`memory_exchange_extracted facts=N` line is logged *after* the writes
succeed, and every one of the 28 failures was raised *inside* a write
(`upsert_fact` / `add_observation`). So the 94 that logged `facts=0` were
exchanges with nothing to store, and the 28 that failed were exactly the
ones that had something. The true yield of those three days is unknown and
bounded above by 28 exchanges — see item 13, which found why they failed.
Recoverable: rewind the cursor to 2847 after item 13's fix is in; the
novelty gate deduplicates what was already stored. **Larry's call**, added
to the list as item 12b.

(Original text, kept for the record:) Not a deduplication artifact - the
per-exchange log lines themselves report `facts=0 observations=0`. `memories`
stayed at 434 and `observations` went 119 → 120.

**So the backfill was not the win; the fix was.** From 2026-09-16 12:30 on,
conversations reach the database the extractor watches. That is the thing
that was broken for three days and is now demonstrably working.

## 13. `get_conn` has no busy timeout — RE-DIAGNOSED: A SELF-DEADLOCK, FIXED 2026-09-17

**What it is.** The backfill lost **28 of 122** attempted exchanges to
`sqlite3.OperationalError: database is locked`, raised from
`memory.py:671 upsert_fact` and `memory.py:728 add_observation` by way of
`memory_extraction.py:267 / :307`.

**Cause.** `jarvis/db.py:613` is `sqlite3.connect(path)` with no `timeout`
argument and no `PRAGMA busy_timeout` beside the `journal_mode=WAL` it does
set. Python's default allows 5 s and no more. Every writer in the codebase
funnels through `get_conn`, and it is the one connection helper that was
given nothing - `usage_ledger.py:184` and `costs_api.py:54` both pass
`timeout=5.0` explicitly.

**Why it had never been seen.** WAL permits many readers but serialises
writers. The bot and the extraction worker are two writers by design, but
from 09-13 to 09-16 they were writing to *different files* (item 12), so
they never contended - and before that, the load never included ~150
back-to-back extractions racing a live voice session.

**Where the lost exchanges went.** Nowhere recoverable: the cursor advanced
past them at tick end, so those turns are never revisited. Recovery would
mean rewinding the cursor to before turn 2933 and re-extracting ~100
exchanges. **Not worth doing** - the 94 that succeeded in that same range
yielded 0 facts, so the 28 that failed almost certainly held nothing either.
That retires the rewind question rather than leaving it open.

**To close.** Add a real `timeout` and a `PRAGMA busy_timeout` in `get_conn`.
It is two lines, but it is the shared chokepoint for every database write in
the application, so it wants its own change, its own test, and a deliberate
value - not a number picked to make one backfill pass. The discriminating
test already exists: two writers, one under sustained load, and count the
`OperationalError`s.

**Note for the record:** every §8 acceptance session ran against
`active-repo/data/jarvis.db`. The audio and transport measurements do not
depend on the database, so nothing measured is invalidated - but any run-log
evidence cited from those sessions lives in that file, not the real one.

**RE-DIAGNOSED AND FIXED 2026-09-17.** The busy timeout was the wrong
target. `tick_once` opens one connection for the whole tick and, per
session, writes to `memory_extraction_pending` (`_set_pending` or
`_clear_pending` — an INSERT or DELETE). Python's sqlite3 opens an implicit
transaction on the first DML and holds the write lock until commit, and the
tick committed **once, at the end**. `extract_from_exchange` writes through
a *second* connection (`memory_extraction.py:370`), same process, same
thread — so from the second session on, its `upsert_fact` waits the full 5 s
for a lock the same thread holds, then fails. A longer timeout would only
lengthen the wait before the identical failure; `db.py` is deliberately
untouched. Never seen before because a normal tick carries one session's
rows, so its pending write lands after its only extraction.

Fix: `conn.commit()` after each session's pending write
(`memory_extraction_worker.py`), releasing the lock before the next
session's extraction. Regression test in
`tests/unit/test_memory_extraction_worker.py`: session A leaves a pending
write, session B's extraction must land a fact through its own connection,
and the tick must finish in under 4 s (a self-deadlock stalls ≥ 5 s per
blocked write). **12/12 pass** in that file.

**Consequence for item 12:** the 28 lost exchanges were the ones with
content. Recorded there as item 12b.

## 12b. Re-extract the 28 exchanges the deadlock lost — LARRY'S CALL

With item 13 fixed, rewinding `memory_extraction_cursor` to **2847** makes
the worker re-walk the 299 merged rows; the novelty gate skips what is
already stored, so the cost is ~149 LLM calls on the `memory_extraction`
rung and the gain is whatever those 28 exchanges held. One `UPDATE` with the
bot stopped, and the worker does the rest on its next tick. Not done
unasked: it is a write into the real database and a bill.

## 14. The interruption storm — DIAGNOSED AND FIXED 2026-09-17

**What it is.** Nine `[system] Your previous reply was interrupted by the
user before any audio played` notes in a 90-second conversation on
2026-09-16 11:43, three per user turn, on every turn — including turns where
the bot had finished speaking two seconds before the user spoke. Larry:
"Stop talking over me."

**Measured.** In `bot-c6.log.5`, pipecat logs exactly **one**
`LLMUserAggregator#0: broadcasting interruption` per user turn. The LLM
context carries exactly **three** notes per user turn. One frame, three
notes.

**Mechanism.** `InterruptionNotifier` is a task-level observer, and an
observer's `on_push_frame` runs once per processor hop
(`pipecat/processors/frame_processor.py:868–893`) — the same
`InterruptionFrame` object is observed at aggregator→LLM, LLM→TTS,
TTS→output, output→assistant-aggregator. It is a `SystemFrame`, so those
hops are not synchronous with one another: by the time the hops after the
LLM are observed, the aggregator has closed the user turn and the LLM has
pushed `LLMFullResponseStartFrame` for the **new** reply, which re-arms
`_assistant_active`. The old turn's boundary frame, at its remaining three
hops, then reads as three fresh barge-ins against the new reply. Three hops
downstream of the LLM; three notes. A second, independent race: the notifier
cleared `_assistant_active` only *after* awaiting the inject, so any hop
landing during that await also saw the reply as active. Every existing test
pushed each frame exactly once, which is why none of them caught either.

**Fix** (`jarvis/bot/interruption.py`): record `frame.id` on first sight
regardless of state and ignore later hops of the same frame; clear
`_assistant_active` before the await. Four tests added to
`tests/unit/test_interruption.py`: a routine boundary seen at four hops
across a re-arm injects nothing; a genuine barge-in seen at four hops
injects exactly once; two distinct barge-ins on two replies inject twice
(the dedupe is per frame, not per turn); and a hop arriving mid-inject with
a *distinct* frame does not see the reply as active. **12/12 pass** in that
file.

**What this does not claim.** It removes the spurious notes, which were
padding every turn's context and telling the model it kept getting cut off
when it hadn't. Whether the bot also *starts speaking too early* — the
other reading of "stop talking over me" — is a turn-detection question
(Deepgram Flux end-of-turn), separate, and not diagnosed here.

---

## Also closed 2026-09-17, outside the numbered list

**Six plans had no status line at all** — a plan with no status cannot be
audited, and more than one of this week's wrong turns came from trusting a
header over the code. Each now carries one written against the tree:
`GEOLOCATION_DEVELOPMENT_PLAN` and `GEOLOCATION_BACKEND_SPEC` are
TypeScript-shaped, dated "2024", never built, and superseded in intent by
`jarvis/ambient_weather.py`; `INTERVAL_POLLING_CAPABILITY` is orphaned and
says so itself ("the goal names no codebase"); `MORTIMER_DRAWER_POPOUT_PLAN`
is implemented in `web/` with DP8 unverified and superseded by the native
drawer window; `MORTIMER_SELFEDIT_TIERS_PLAN` and
`MORTIMER_PLAN_REVIEW_AND_DOCS_PLAN` are implemented, with evidence cited
per decision. R6's routing eval was not re-run and the status line says so.

**`docs/REPO_MAP.md` was over its prompt cap and silently truncating.** PR
#73's native-audio lines took it to 8109 characters against the 8000 in
`jarvis/repo_map.py`, and over the cap `load_repo_map_suffix` truncates —
so every sub-agent prompt since 09-15 carried a repository map cut off
mid-sentence, and `test_repo_map_under_cap_and_names_phase_modules` had been
failing on `main`. The `macos/` section is tightened by 121 characters; all
sixteen modules the test names are still present; now 7988. Note for whoever
checks this next: the cap is on **characters**, and `wc -c` reports 8096
bytes for the same file because of 108 multi-byte em-dashes.

**Item 10 shipped two defects, both caught 2026-09-17 and fixed in
`2bc51dc`** (branch commit; content on main via `af2d0cf`). Item 10 is still closed — the amplitude Larry accepted on sight
is unchanged — but its first commit was green only because the launcher
lied, so the record belongs here.

1. *A real regression.* Removing the `dyn.base = 0.004` pin let the resting
   thickness ease to the per-state target, which is what made the wave
   visible. But `VoiceWaveView.draw`'s easing block runs once per draw call
   unconditionally, so with `assistantSpeaking` true and no measured audio
   `base` crawled 0.004 → 0.016 across successive draws: the trace thickened
   four-fold while nothing was arriving.
   `testUnavailableSpeechRendersIdenticallyAcrossTime` caught it as an
   11329-vs-11409-byte PNG between `now: 10` and `now: 20`. `staticTrace`
   zeroed `speed` and the phases and its comment claimed it "stops motion
   dead" — it stopped lateral motion only. Fixed by freezing the whole
   easing block under `staticTrace`, not by snapping `base` to `tg.base`,
   which would pop the trace the moment audio stopped.

2. *A guessed threshold in my own test.*
   `testThePlayoutWindowKeepsMortimersVoiceMoving` asserted the playout
   trace run through the *input* window travels less than 0.15. It travels
   0.1721327612353618 — the playout p95 (−8.4 dB) sits above the input
   window's −10 dB ceiling and clamps to 1.0 while the median lands at
   0.828 — reproduced to sixteen digits on three consecutive runs. Not
   relaxed to 0.18, which is the same guess with a bigger number: replaced
   with the relation the test actually claims, that the shared window gives
   less than half the travel of the dedicated one (0.172 against 0.510),
   with both figures pinned.

**The launcher displayed one test run and gated on a different one.**
`QUEUED-swift.sh` ran `swift test` twice per package — once piped to `grep`
for display, then again inside the `if` for the gate — so the two failures
above printed on screen (`Executed 162 tests, with 2 failures`) and the
commit went ahead anyway. The gate regex was correct; it judged a separate
run. Every launcher now captures once into a variable and gates on those
same bytes; the rule is written up in `closure-checks/LAUNCHER-RULES.md`.

**New observation — the C3.1 frame-time gate is load-sensitive, and §6 of
the closure plan designates it a gate rather than a report.** Running the
162-test MortimerHost suite three times back to back stretched the third
run from 63 s to 312 s, and only in that run did
`MemoryGraphFrameTimeTests.testPanAndZoomFrameTimesOnTheDenseHubFixtureMeetTheP95Gate`
fail — p50 frame time 510 ms against its ≤33 ms gate, with its own
self-check ("the measured span does not respond to drawing cost") also
tripping, which says the measurement had stopped measuring Canvas work at
all. `DrawerTabStripRenderingTests.testOverflowButtonsReachBothEndsWithoutChangingSelection`
failed in the same run only. Both passed in runs 1 and 2 and again on the
clean confirming run. So: not flaky in the ordinary sense — they are
accurate under contention and meaningless under it. A CI machine running
suites in parallel will fail this gate intermittently and the failure will
look like a graphics regression. Untested: whether the gate can detect its
own invalidity and skip rather than fail. Naming it here rather than
fixing it, because it is a gate and changing its behaviour is not a
side-errand.
