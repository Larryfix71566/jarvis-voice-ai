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
