// MORTIMER_NATIVE_AUDIO_TRANSPORT_PLAN.md §3.3 — Voice Processing I/O echo
// bench (closure plan C6.1 hard-stop item 3, and the §3.5 concurrent wake
// engine item). Runs the real `AudioEngineIO` twice — VPIO on, then off —
// plays a speech-shaped signal through its player node and measures what
// the (processed) input tap hears while it plays. The bot hears exactly
// what that tap delivers, so the residual is the echo the pipeline's VAD
// and STT would see.
//
// Output: one JSON line per phase and a summary, plus 16 kHz WAV captures
// of every phase under --out so the residual can be listened to or fed to
// STT (§8: "the bot does not transcribe its own TTS").
//
// Nothing here is a pass/fail gate by itself — Larry reads the numbers
// against §3.3: residual during playback (VPIO on) close to the idle floor
// and well below the VPIO-off residual.

import AVFoundation
import CoreAudio
import Foundation
@testable import JarvisKit

struct Options {
    var seconds = 8.0
    var wake = false
    var out = FileManager.default.currentDirectoryPath
    var gain: Float = 0.5
}

var options = Options()
var args = Array(CommandLine.arguments.dropFirst())
while !args.isEmpty {
    let arg = args.removeFirst()
    switch arg {
    case "--seconds": options.seconds = Double(args.removeFirst()) ?? options.seconds
    case "--wake": options.wake = true
    case "--out": options.out = args.removeFirst()
    case "--gain": options.gain = Float(args.removeFirst()) ?? options.gain
    default: FileHandle.standardError.write(Data("unknown argument \(arg)\n".utf8)); exit(2)
    }
}

// MARK: - Device names (what the run was measured on)

func defaultDeviceName(_ selector: AudioObjectPropertySelector) -> String {
    var address = AudioObjectPropertyAddress(mSelector: selector, mScope: kAudioObjectPropertyScopeGlobal, mElement: kAudioObjectPropertyElementMain)
    var device = AudioDeviceID(0)
    var size = UInt32(MemoryLayout<AudioDeviceID>.size)
    guard AudioObjectGetPropertyData(AudioObjectID(kAudioObjectSystemObject), &address, 0, nil, &size, &device) == noErr else { return "?" }
    var nameAddress = AudioObjectPropertyAddress(mSelector: kAudioObjectPropertyName, mScope: kAudioObjectPropertyScopeGlobal, mElement: kAudioObjectPropertyElementMain)
    var name: Unmanaged<CFString>?
    var nameSize = UInt32(MemoryLayout<Unmanaged<CFString>?>.size)
    guard AudioObjectGetPropertyData(device, &nameAddress, 0, nil, &nameSize, &name) == noErr, let cf = name?.takeRetainedValue() else { return "?" }
    return cf as String
}

let inputName = defaultDeviceName(kAudioHardwarePropertyDefaultInputDevice)
let outputName = defaultDeviceName(kAudioHardwarePropertyDefaultOutputDevice)

// MARK: - Speech-shaped test signal (24 kHz Int16 mono, the ElevenLabs rate)

/// Band-limited noise (300–3400 Hz) amplitude-modulated in 4 Hz syllables,
/// in 1.6 s phrases with 0.4 s gaps — enough like speech to engage VPIO's AEC
/// the way TTS does, without a copyrighted voice file in the repo.
func speechShaped(seconds: Double, rate: Double = 24_000, gain: Float) -> Data {
    let frames = Int(seconds * rate)
    var rng = SystemRandomNumberGenerator()
    var y1 = 0.0, y2 = 0.0   // simple 2-pole band-pass state
    var out = Data(capacity: frames * 2)
    for i in 0..<frames {
        let t = Double(i) / rate
        let syllable = max(0, sin(2 * .pi * 4 * t))            // 4 Hz bursts
        let phrase = (t.truncatingRemainder(dividingBy: 2.0)) < 1.6 ? 1.0 : 0.0   // 1.6 s on, 0.4 s off
        let white = Double.random(in: -1...1, using: &rng)
        // band-pass: high-pass at ~300 Hz then low-pass at ~3.4 kHz (one pole each, applied twice)
        y1 += (white - y1) * 0.62      // low-pass
        y2 += (y1 - y2) * 0.075        // slow follower = low frequencies to subtract
        let band = (y1 - y2) * 2.2
        let v = band * syllable * phrase * Double(gain)
        let sample = Int16(max(-32768, min(32767, v * 32767)))
        withUnsafeBytes(of: sample.littleEndian) { out.append(contentsOf: $0) }
    }
    return out
}

// MARK: - WAV writer (16 kHz mono Int16 — what the bot receives)

func writeWAV(_ pcm: Data, rate: Int, to url: URL) throws {
    var header = Data()
    func u32(_ v: UInt32) { withUnsafeBytes(of: v.littleEndian) { header.append(contentsOf: $0) } }
    func u16(_ v: UInt16) { withUnsafeBytes(of: v.littleEndian) { header.append(contentsOf: $0) } }
    header.append(contentsOf: Array("RIFF".utf8)); u32(UInt32(36 + pcm.count)); header.append(contentsOf: Array("WAVE".utf8))
    header.append(contentsOf: Array("fmt ".utf8)); u32(16); u16(1); u16(1); u32(UInt32(rate)); u32(UInt32(rate * 2)); u16(2); u16(16)
    header.append(contentsOf: Array("data".utf8)); u32(UInt32(pcm.count))
    try (header + pcm).write(to: url)
}

// MARK: - One phase

struct Phase: Encodable {
    let name: String
    let voiceProcessing: Bool
    let seconds: Double
    let capturedRMS: Double          // mean RMS of the 16 kHz capture the bot would receive
    let capturedPeakRMS: Double      // max per-buffer RMS
    let playoutRMS: Double           // mean RMS at the main mixer (what the speaker got)
    let captureBuffers: Int
    let wakeBuffers: Int?            // --wake: buffers the concurrent wake-style engine received
    let wakeRMS: Double?
    let wav: String
}

final class Meter: @unchecked Sendable {   // lock-guarded
    private let lock = NSLock()
    private var sum = 0.0, peak = 0.0, count = 0
    private(set) var pcm = Data()
    func add(_ data: Data) {
        let samples = data.withUnsafeBytes { Array($0.bindMemory(to: Int16.self)) }
        guard !samples.isEmpty else { return }
        let rms = (samples.reduce(0.0) { $0 + pow(Double($1) / 32768, 2) } / Double(samples.count)).squareRoot()
        lock.withLock { sum += rms; peak = Swift.max(peak, rms); count += 1; pcm.append(data) }
    }
    var mean: Double { lock.withLock { count == 0 ? 0 : sum / Double(count) } }
    var peakRMS: Double { lock.withLock { peak } }
    var buffers: Int { lock.withLock { count } }
}

/// A second input engine shaped like WakeWordListener's (plain tap, no
/// VPIO, converted to 16 kHz Int16) running concurrently — §3.5 item.
final class WakeStyleEngine {
    let engine = AVAudioEngine()
    let meter = Meter()
    private var converter: CaptureConverter?
    func start() throws {
        let input = engine.inputNode
        let format = input.outputFormat(forBus: 0)
        converter = CaptureConverter(inputFormat: format)
        input.installTap(onBus: 0, bufferSize: 1024, format: format) { [self] buffer, _ in
            if let data = converter?.convert(buffer) { meter.add(data) }
        }
        try engine.start()
    }
    func stop() { engine.inputNode.removeTap(onBus: 0); engine.stop() }
}

/// Mean of the engine's playout slot, sampled at 20 Hz through a phase.
final class SlotSampler {
    private var sum = 0.0, n = 0
    func add(_ v: Double) { sum += v; n += 1 }
    var mean: Double { n == 0 ? 0 : sum / Double(n) }
}

func runPhase(name: String, voiceProcessing: Bool, play: Bool, signal: Data) throws -> Phase {
    let io = AudioEngineIO(voiceProcessing: voiceProcessing)
    let capture = Meter()
    let playout = SlotSampler()
    io.onCapturedPCM = { data, _ in capture.add(data) }
    try io.start()
    let wake: WakeStyleEngine? = options.wake ? WakeStyleEngine() : nil
    try wake?.start()
    Thread.sleep(forTimeInterval: 0.5)   // let the graph settle before measuring
    let started = Date()
    if play {
        // Feed the player in 40 ms frames the way the transport does.
        let frameBytes = 24_000 * 2 * 40 / 1000
        var offset = 0
        while offset < signal.count {
            let end = min(offset + frameBytes, signal.count)
            io.play(pcm: signal[offset..<end], sampleRate: 24_000, channels: 1)
            offset = end
        }
    }
    let deadline = started.addingTimeInterval(options.seconds)
    while Date() < deadline {
        if let level = io.latestPlayoutLevel { playout.add(level.rms) }
        Thread.sleep(forTimeInterval: 0.05)
    }
    let playoutMean = playout.mean
    wake?.stop()
    io.stop()
    let url = URL(fileURLWithPath: options.out).appendingPathComponent("vpio-bench-\(name).wav")
    try writeWAV(capture.pcm, rate: 16_000, to: url)
    return Phase(name: name, voiceProcessing: voiceProcessing, seconds: options.seconds,
                 capturedRMS: capture.mean, capturedPeakRMS: capture.peakRMS, playoutRMS: playoutMean,
                 captureBuffers: capture.buffers, wakeBuffers: wake?.meter.buffers, wakeRMS: wake?.meter.mean, wav: url.path)
}

// MARK: - Run

let signal = speechShaped(seconds: options.seconds, gain: options.gain)
var phases: [Phase] = []
do {
    let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys]
    print(#"{"bench":"vpio","input":"\#(inputName)","output":"\#(outputName)","seconds":\#(options.seconds),"wake":\#(options.wake)}"#)
    for (name, vp, play) in [("idle-vpio-on", true, false), ("play-vpio-on", true, true),
                             ("idle-vpio-off", false, false), ("play-vpio-off", false, true)] {
        let phase = try runPhase(name: name, voiceProcessing: vp, play: play, signal: signal)
        phases.append(phase)
        print(String(data: try encoder.encode(phase), encoding: .utf8)!)
    }
    // JSON has no NaN: a phase with a zero RMS (no capture at all) reports null.
    func dB(_ a: Double, _ b: Double) -> Any { b > 0 && a > 0 ? 20 * log10(a / b) : NSNull() }
    let idleOn = phases[0].capturedRMS, playOn = phases[1].capturedRMS
    let idleOff = phases[2].capturedRMS, playOff = phases[3].capturedRMS
    let summary: [String: Any] = [
        "residual_above_floor_dB_vpio_on": dB(playOn, idleOn),
        "residual_above_floor_dB_vpio_off": dB(playOff, idleOff),
        "vpio_echo_reduction_dB": dB(playOff, playOn),
        "input": inputName, "output": outputName,
    ]
    print(String(data: try JSONSerialization.data(withJSONObject: summary, options: [.sortedKeys]), encoding: .utf8)!)
} catch {
    FileHandle.standardError.write(Data("bench failed: \(error)\n".utf8))
    exit(1)
}
