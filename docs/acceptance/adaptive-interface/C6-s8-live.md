# C6 §8 — live session on the native transport

Run 2026-09-15 20:08:17–20:11:08 EDT, MacBook Air (Mac17,4), branch
`fix/audio-device-resilience` at `92b1373`. Bot from this working copy on
:7870 against the real vault/DB. AirPods as both output and input to start,
then switched to built-in mid-session.

Logs: `closure-checks/logs/app-oslog.log` (JarvisKit/host subsystems),
`app-system.log` (everything the process logged, Apple's subsystems
included — added after the 2026-09-14 crash was invisible to the first
predicate), `bot-c6.log`.

---

## Verdicts

| §8 item | Verdict | Evidence |
|---|---|---|
| Local session on the native path, AirPods both ways | **pass** | Full conversation; capture 100 buffers/s, 480-frame buffers, age at callback 11.4 ms median |
| Switching output mid-session follows without a reconnect | **pass** | One `connect:`, one socket, no `socket closed` until the 20:11:08 disconnect, across six engine rebuilds |
| Wake word while muted | **pass** | `wake event: model=mortimer score=0.900000` at 20:10:53.872 |
| Speaking indicator lights | **untested** | Needs an observer; not in any log |
| `forceWebRTC` rollback | **not run** | |
| §3.3 echo on the two AirPods configurations | **not run** | |

## The crash fix holds

Six engine rebuilds (`#1`–`#6`, 20:10:20.6 → 20:10:33.2), every one of them a
detach and reattach of the player node — the exact event that terminated the
app on 2026-09-14. Zero fatal lines in `app-system.log`. The `playerAttached`
guard does its job.

## The device-settling fix earned its place

`audio devices settled after 50 ms` fired on two of the six rebuilds
(20:10:20.681, 20:10:32.573) — one 50 ms step each. Those two rebuilds read a
half-built device and would otherwise have thrown; before the crash fix, that
throw came with a dead session that never recovered.

## The retry budget is still a guess

All six rebuilds succeeded on **attempt 1**, so the retry path was never
entered. The 6 × 0.5 s budget remains untested. What IS now measured is the
cost of one successful rebuild — notification to engine running:

| rebuild | ms |
|---|---|
| #1 | 922 |
| #2 | 667 |
| #3 | 693 |
| #4 | 686 |
| #5 | 704 |
| #6 | 701 |

So roughly 700 ms of dead audio per rebuild.

## C7.5 latency gate, on AirPods

`input: 1568 shown, displayed p95 24.5 ms, arrival p95 24.5 ms over 1523
arrivals; playout: 431 shown, displayed p95 65.5 ms, arrival p95 1.0 ms over
406 arrivals` — against a 150 ms gate. **Pass**, and the first time the gate
has been measured on a Bluetooth input. Written to
`P2-latency.json` by the app at session end (`p95_ms` 65.5, against 67.6 on
the 2026-09-13 built-in run).

One detail there corroborates finding 2 below: input `worst_ms` is **294.2**,
against 26.5 on the built-in run. A single observation that stale is the
rebuild gap appearing in the latency data — the gate is a p95 so it survives,
but the churn is visible in the numbers, not only in the log.

---

## Finding 1 — the readiness gate does not gate on readiness

`connect()` was changed (commit `e9ad1ba`) to return only once the server
showed a sign of life, so that `.connected` would mean the bot could answer.
It does not:

| event | time |
|---|---|
| WebSocket accepted (bot) | 20:08:20.541 |
| socket open → established (app) | 20:08:20.666 |
| `.connected` — UI says ready | 20:08:20.684 |
| **pipeline started** (bot) | 20:08:26.456 |
| `pong gap 5.79s` logged | 20:08:26.459 |

uvicorn answers pings from its protocol layer, so the first pong arrived
while the loop was still free; the loop then blocked for 5.77 s starting the
MCP servers, which is what the pong gap records. A pong proves the socket
layer is alive, not that the pipeline is running — so the gate fires 5.8 s
early and the original defect stands.

The correct signal is the bot's first *frame*, which `establish` also accepts
— the pong simply wins the race. Before moving the gate, the transport now
logs the first inbound frame's kind and its delay from socket open, because
nothing currently records what the server sends first. **Open until that
measurement exists.**

## Finding 2 — four of the six rebuilds were self-inflicted

CoreAudio reported exactly two hardware changes:

```
20:10:27.869  kAudioHardwarePropertyDefaultInputDevice: new dev=71
20:10:28.527  kAudioHardwarePropertyDefaultOutputDevice: new dev=76
```

and **no `kAudioHardwareProperty*` change after that**. Everything from
20:10:28.8 onward is `SelectDevice` churn against a new AUHAL object per
rebuild. Rebuilds #3–#6 each arrived ~220 ms after the previous one finished:
building the graph emits `AVAudioEngineConfigurationChange`, the observer
rebuilds, and round it goes until the topology stops moving. Two device
changes cost about 3.5 s of dead audio where ~0.7 s was needed.

A debounce would only pace the loop, since each notification arrives *after*
its rebuild. Skipping notifications whose device signature is unchanged is
the causal fix — but whether that is safe is genuinely open: rebuilds #2–#5
read `1 ch before VPIO` and #6 read `2 ch`, so the hardware was still
settling, and skipping might leave the graph built on a transient read. The
observer now logs the device signature at notification time against the one
the running graph was built with, which decides it. **No fix shipped on
speculation.**

## Still open after this run

- Both findings above, each pending one instrumented rerun.
- Speaking indicator (needs a person watching), `forceWebRTC` rollback,
  §3.3 on the two AirPods configurations.
- §3.4 latency parity — still blocked on a C0.4 WebRTC baseline that has
  never been captured.

---

# Second run, 2026-09-15 20:22:33–20:27:11

Instrumented rerun at `e4f785f` to settle the two findings above. Step markers
recorded this time (`closure-checks/logs/s8-markers.log`), so actions are
attributed rather than inferred: AirPods both ways → conversation → output to
built-in speakers → back to AirPods → wake word while muted → disconnect.

No fatal lines. Two engine rebuilds, both recovered.

## Finding 1 — settled, and fixed

```
20:22:33.341  socket open
20:22:33.341  session established          (on the first pong, same ms)
20:22:33.359  state = .connected
20:22:39.065  first inbound frame: message type=server-message
              data.type=voice/catalog, 5724 ms after the socket opened
```

There is no `bot-ready` on this path — the first thing the server sends is the
voice catalog, and it arrives when the pipeline is actually running. So the
frame is the readiness signal and the pong is not: uvicorn answers pings from
its protocol layer while the session is still being built.

`pongReceived` no longer establishes. `connect`, `transportDidConnect` and the
stall watchdog all now key on the first frame.

**That also closed a near-miss nobody had noticed.** The watchdog was armed at
socket open with a 6 s threshold while the first frame took 5.72 s here and
5.79 s in the first run — under 300 ms between a healthy start and a spurious
teardown. It had been passing on luck.

The coupling introduced is worth stating: the native path now requires the
server to send something unprompted at session start. It does (`voice/catalog`,
then the greeting), and `nativeReadyDeadline` (30 s) bounds the wait — but a
server that only answered when spoken to would never be reported connected.

Pinned by `testAnsweredPingsAloneNeverMakeTheSessionReady`.

## Finding 2 — NOT confirmed; this run argues against it

Both configuration changes were genuine:

```
20:24:48.720  devices now [in 71@48000 out 76@48000], built against [in 93@48000 out 87@48000]
20:26:01.779  devices now [in 183@48000 out 177@48000], built against [in 71@48000 out 76@48000]
```

Zero `— NO DEVICE DIFFERENCE` lines, and the six-rebuild loop did not
reproduce at all. The hypothesis that our own rebuild provokes the next
notification is **unsupported**: the instrumentation that would have caught it
was in place and caught nothing.

The difference between the runs is what was done to the hardware. The first
run's churn followed an **earbud being removed**, with the input alternating
1 ch / 2 ch across rebuilds — AirPods genuinely renegotiating. This run used
deliberate switches in System Settings, which are clean. So the churn is
more likely the hardware settling than a feedback loop, and repeating the
earbud removal with the signature logging in place is what would settle it.

No fix shipped. The instrumentation stays.

## The retry path finally ran

Switching **to** AirPods needed two attempts:

```
20:26:01.779  configuration change
20:26:02.779  input device 183: buffer 480 frames    output 177: buffer 512, range 15…960
20:26:05.393  rebuild attempt 1 failed; retrying
20:26:05.895  input device 183: buffer 480           output 177: buffer 480, range 8…4096
20:26:06.494  engine started, rebuilt (#2, attempt 2)
```

**4.72 s total**, against 862 ms for the switch to built-in. Note the output
device's buffer configuration changed between the two attempts (512 frames /
range 15…960 → 480 / 8…4096): the device was still activating when attempt 1
ran. So the retry budget is doing real work, and the driver is device
activation time rather than the number of gaps.

Why attempt 1 failed is **not recorded**, because `rebuildLocked` logged
`error.localizedDescription`, which renders a `JarvisError` as
`"The operation couldn't be completed. (JarvisKit.JarvisError error 1.)"` and
discards the message. Fixed to `String(describing:)`; the next retried
rebuild will say what it hit.

## AirPods run the engine at 24 kHz

```
capture 24000 Hz mono, channel 0 of 3 (hardware 1 ch before VPIO), output 24000 Hz 2 ch
input tap: 100 buffers in 2.0s (49.6/s), 480 frames each at 24000 Hz = 20.0 ms of audio
```

Against 512 frames at 48 kHz — 10.7 ms — on the built-in array. The capture
quantum doubles on Bluetooth. It does not threaten the C7.5 gate (24.5 ms
input displayed p95 measured on AirPods in the first run), but it is the
floor on this path and belongs in any future latency work.

## The C7.5 gate FAILED on the second run

`P2-latency.json`, written at session end. This supersedes the passing
figures above, and it is the first failure the gate has recorded.

```
gate      FAIL        (threshold: displayed p95 under 150 ms)
p95_ms    167.6
window    the last 60 s of the session, 20:26:05–20:27:05
input     displayed p50 35.2, p95 41.9, worst 42.0, 840 arrivals
playout   arrival p50 0.9, p95 1.0  —  displayed p50 0.9, p95 167.6,
          worst 271.1, 243 arrivals / 275 observations
```

Facts, before any explanation:

- **The failure is entirely the playout channel.** Input is 41.9 ms with a
  worst case of 42.0 — a distribution with no tail at all. Playout *arrival*
  is 1.0 ms; it is the *displayed* age that blows the gate.
- **Input roughly doubled**, 24.5 → 41.9 ms, which tracks the 24 kHz AirPods
  path measured above: a 480-frame buffer at 24 kHz is 20 ms of audio against
  10.7 ms on the built-in array.
- **The window is the last 60 s**, not the session, and it contains the 4.72 s
  two-attempt rebuild that finished at 20:26:06.494.
- **The playout sample is sparse** — 275 observations in 60 s, because playout
  only produces levels while the bot is speaking. A p95 over that sample is
  roughly the fourteenth worst reading.

[likely] the tail comes from playout stamping immediately after a rebuild:
`resetPlayoutTimeline` clears the slice list and `lastScheduledEnd`, so the
first slices scheduled against a fresh player clock can be anchored wrong,
and in a sparse sample a handful of stale stamps move the p95 a long way. The
first run shows the same shape with a smaller tail (playout worst 298.9 ms,
p95 65.5).

[guessing] whether the 24 kHz path alone would fail. Input at 41.9 ms says
the device costs real latency, but 20 ms of quantum does not account for
167.6 ms on its own.

**The measurement that discriminates:** one session on AirPods with *no
device change at all* — connect, talk for a minute or two, disconnect,
touch nothing. If playout displayed p95 comes in under 150 ms, the rebuild
is the cause and the fix is in the timeline reset. If it is still ~167 ms,
the 24 kHz path itself is, and the gate needs either a fix or a
device-dependent threshold.

Until that exists, **C7.5 should not be described as passing.** It passes on
the built-in array (67.6 ms) and on a mixed session (65.5 ms) and fails on
this one.

---

# Third run, 2026-09-15 20:48:00–20:49:27 — steady state

The discriminating session the gate failure asked for: AirPods set before
connecting, a two-minute conversation, **no device touched**.

```
rebuilds                        0
configuration-change notices    0
fatal lines                     0
engine                          capture 48000 Hz mono, channel 0 of 3
                                (hardware 1 ch before VPIO), output 48000 Hz 2 ch
gate                            pass, p95 34.3 ms
  input    displayed p95 23.5   arrival p95 23.5   worst 23.5   obs 76
  playout  displayed p95 34.3   arrival p95  1.0   worst 298.7  obs 1514
```

## What this settles, and what it does not

**Settles:** with no rebuild, the gate passed comfortably. The 167.6 ms
failure was not a steady-state property of the code.

**Does NOT settle the 24 kHz question.** This session came up at **48 kHz**
(480 frames = 10.0 ms), not the 24 kHz of the second run. AirPods negotiate
either rate between sessions, which is a variable that was not known before
and was not controlled for. The 24 kHz path remains unmeasured in steady
state.

## The real finding: the gate was reading the wrong number

Three sessions of identical code on one Mac:

| run | playout obs | displayed p95 | arrival p95 | worst | verdict |
|---|---|---|---|---|---|
| 1 | 431 | 65.5 ms | 1.7 ms | 298.9 ms | pass |
| 2 | 275 | **167.6 ms** | 1.0 ms | 271.1 ms | **FAIL** |
| 3 | 1514 | 34.3 ms | 1.0 ms | 298.7 ms | pass |

Arrival latency never moved. From `AudioActivityObserver.sample()`:

```swift
let delay = moment - measuredAt
displayed.append((channel, measuredAt, delay))               // every 30 Hz tick
if lastSeen[channel] != measuredAt { arrivals.append(...) }  // once per level
```

`snapshot.outputMeasuredAt` is a **held** value, and the accumulator keeps
one for up to 300 ms of staleness. So each time the bot stops speaking, the
playout channel appends about nine increasingly stale entries — 33, 66, 100
… 300 ms — for a single measurement. The `worst_ms` column is that ceiling,
which is why it reads ~300 ms in every run including the passing ones.

The verdict was therefore a function of how much the bot happened to talk: a
dense session buries those idle entries below p95, a sparse one lets them
set it. The gate was measuring what fraction of samples caught a channel
between bursts. The rebuild in run 2 mattered mostly by making the playout
sample sparse, not by being slow.

**The gate now reads arrival p95, at 50 ms.** From the data: healthy input
arrival p95 of 23.5, 24.5, 25.2 and 41.9 ms (the last on the 24 kHz
Bluetooth path) against ~110 ms for the D10 tap regression the gate exists
to catch. `displayed` stays in the report, labelled, with `gate_metric:
"arrival_p95"` beside the verdict so the two are not confused. Pinned by
`testAQuietBotDoesNotFailTheGate`, which encodes run 2's numbers.

## Unexplained: the input channel's observation count

| run | input obs | session length |
|---|---|---|
| 1 | 1568 | ~9 min |
| 2 | 840 | ~4.6 min |
| 3 | **76** | ~87 s |

Run 3's capture path delivered ~100 buffers/s throughout (the tap
diagnostic confirms it), so roughly 8,700 buffers produced 76 accepted
observations. `shown` equalled `arrivals` exactly, so every entry was a
fresh level — the accumulator simply had nothing to hold most of the time.
No explanation yet, and it means the input arrival figure the gate now
depends on rests on a thin sample in at least one session. **Open.**

## A harness defect worth recording

`run-s8-steady.command` set `JARVIS_BOT_URL` with `launchctl setenv`, which
is user-wide, and cleaned up only `JARVIS_FORCE_WEBRTC`. `JarvisConfig`
reads the environment before UserDefaults, so the leftover `:7870` failed
`ConfigAndAuthTests.testDefaultURLsAreLoopback` in the next `swift test`
run — the test was right and the harness had changed the machine it
measured on. Both session launchers now unset both variables on exit.

Separately, that test reads ambient process environment and so can fail for
reasons unrelated to the code under test. Worth making hermetic.
