# Transport probe (plan §5 step 2 / §3 N3)

**Branch taken: B (direct WebRTC over `stasel/WebRTC`).**

## Why the probe was not run

This package was written by an implementer with two available execution
environments — a cloud sandbox and a shell bridged to Larry's connected
Mac — and **neither has a Swift toolchain**:

```
$ which swift && swift --version && sw_vers
(exit code 1, no output — swift is not on PATH in either environment)
```

The bridged shell reaches Larry's Mac's *filesystem* (it is mounted), but
the shell itself runs inside an isolated Linux VM, not natively on the Mac
— so it cannot resolve or build a Swift package either.

Per the plan's own branch-selection rule (§5 step 2 / §3 N3):

> Any other combination, including no network → **Branch B**. Continue to
> step 5. Do not retry, do not adjust the probe, do not substitute a
> different version requirement.

"Cannot run the probe at all" falls under that rule — it is not a resolve
failure or a build failure, it is the absence of a toolchain to run either
step in. Branch B is therefore the correct default, not a guess, and it is
what this package ships as: `DirectWebRTCTransport.swift`,
`stasel/WebRTC` in `Package.swift`, `PipecatSDKTransport.swift` absent.

## How Larry can run the real probe

If it's worth checking whether Branch A (the official Pipecat SDK) is
viable, run this on the Mac itself, in a real Terminal (not the bridged
shell), with Xcode's command-line tools installed:

```bash
set -x
mkdir -p /tmp/pcprobe && cd /tmp/pcprobe
cat > Package.swift <<'EOF'
// swift-tools-version: 6.0
import PackageDescription
let package = Package(
    name: "pcprobe",
    platforms: [.macOS(.v26)],
    dependencies: [
        .package(url: "https://github.com/pipecat-ai/pipecat-client-ios-small-webrtc.git", from: "0.1.0"),
    ],
    targets: [.target(name: "pcprobe", dependencies: [
        .product(name: "PipecatClientIOSSmallWebrtc", package: "pipecat-client-ios-small-webrtc"),
    ])]
)
EOF
mkdir -p Sources/pcprobe
cat > Sources/pcprobe/Probe.swift <<'EOF'
import PipecatClientIOS
import PipecatClientIOSSmallWebrtc
@MainActor func probe(url: String) throws {
    let transport = SmallWebRTCTransport(options: RTVIClientOptions(params: RTVIClientParams(baseUrl: url)))
    _ = transport
}
EOF
swift package resolve ; echo "RESOLVE_EXIT=$?"
swift build            ; echo "BUILD_EXIT=$?"
grep -n "platforms" .build/checkouts/pipecat-client-ios-small-webrtc/Package.swift
```

**Branch selection — apply mechanically (unchanged from the plan):**
- `RESOLVE_EXIT=0` **and** `BUILD_EXIT=0` **and** the grepped `platforms:`
  line names `.macOS(` with a version ≤ 26 → Branch A qualifies. Follow
  plan §5 step 6 exactly: swap the `Package.swift` dependency, delete
  `DirectWebRTCTransport.swift`, write `PipecatSDKTransport.swift`, update
  this file's "Branch taken" line to A and record the exit codes and the
  grepped platform line below.
- Anything else → Branch B stays correct. No action needed; you may still
  record the exit codes below for the record.

## Real probe output (fill in if/when run)

```
RESOLVE_EXIT=
BUILD_EXIT=
platforms line=
```

## §8 V8 wake-word probe

Separately, `§3 N10`'s wake-word probe (`WAKE_PROBE=<code>`) is also
recorded by Larry, in this same file, when he runs §8 V8 — it decides
nothing about this package's build (both W1 and W2 code paths are written
unconditionally in `WakeWordListener.swift`), it is a runtime record only.

```
WAKE_PROBE=101  (2026-08-30 — Branch W1, live wake verified)
```

**History.** On 2026-08-28 this read `WAKE_PROBE=000`: the sidecar exited
at startup because `models/mortimer.onnx` did not exist (the plan's R-N9
scenario), the connect-time probe reported unreachable, and the host's
wake toggle stayed disabled — Branch W2 behaving as specified.

On 2026-08-30 Larry trained the model locally
(`bash scripts/wakeword_gen_samples_mac.sh` → 690 positive / 3036
negative clips; `python -m jarvis.wakeword.train` → held-out wake mean
0.953 vs other mean 0.004, suggested threshold 0.50; export required
`uv pip install onnx onnxscript` first; exported at ONNX opset 18 after
a non-fatal opset-13 down-conversion failure — the trainer's own
"sidecar load OK" check passed). With `./scripts/run_wakeword.sh`
running, the **live W1 test passed**: mic muted, wake toggle on, saying
"Mortimer" played the two-tone chime and re-enabled the mic.
