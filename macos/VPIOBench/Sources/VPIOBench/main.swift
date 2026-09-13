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
    var probe = false
    var channels = false
    var vpioOnly = false       // skip the VPIO-off phases (process-state isolation)
    var wakeTap = false        // wake fed from the engine's own monitor tap (the shipped design)
    var mute = false           // capture disabled, i.e. the state the wake listener runs in
    var settle = 0.5           // seconds between engine start and playback
    var signalPath: String?
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
    case "--probe": options.probe = true
    case "--channels": options.channels = true
    case "--vpio-only": options.vpioOnly = true
    case "--wake-tap": options.wakeTap = true
    case "--mute": options.mute = true
    case "--settle": options.settle = Double(args.removeFirst()) ?? options.settle
    case "--signal": options.signalPath = args.removeFirst()
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

// MARK: - Microphone permission (a command-line tool must ask; nothing asks for it)

/// TCC does not prompt for a bare executable's AVAudioEngine input the way
/// it does for an app bundle — the engine just fails to initialize
/// (-10875 on the first run, 2026-09-13). Ask explicitly, blocking until
/// the dialog is answered, and report the state in the header line.
func microphonePermission() -> String {
    switch AVCaptureDevice.authorizationStatus(for: .audio) {
    case .authorized: return "authorized"
    case .denied: return "denied"
    case .restricted: return "restricted"
    case .notDetermined:
        let semaphore = DispatchSemaphore(value: 0)
        var granted = false
        AVCaptureDevice.requestAccess(for: .audio) { ok in granted = ok; semaphore.signal() }
        semaphore.wait()
        return granted ? "granted-now" : "denied-now"
    @unknown default: return "unknown"
    }
}
let microphone = microphonePermission()

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
    let monitorBuffers: Int?         // --wake-tap: buffers the monitor sink received
    let monitorRMS: Double?
    let monitorPeakRMS: Double?
    let monitorWav: String?
    let muted: Bool
    let tapFormat: String            // what AudioEngineIO installed its input tap with
    let settle: Double
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

func runPhase(name: String, voiceProcessing: Bool, play: Bool, signal: Data, signalRate: Double) throws -> Phase {
    let io = AudioEngineIO(voiceProcessing: voiceProcessing)
    let capture = Meter()
    let playout = SlotSampler()
    io.onCapturedPCM = { data, _ in capture.add(data) }
    // The shipped wake source (§3.5): the engine's own monitor tap, which
    // delivers whether or not capture is enabled — no second engine.
    let monitor = Meter()
    if options.wakeTap { io.onMonitorPCM = { data in monitor.add(data) } }
    try io.start()
    if options.mute { io.setCaptureEnabled(false) }
    let wake: WakeStyleEngine? = options.wake ? WakeStyleEngine() : nil
    try wake?.start()
    let tapFormat = io.captureTapFormat.map { "\($0)" } ?? "nil"
    Thread.sleep(forTimeInterval: options.settle)   // let the graph settle before measuring
    let started = Date()
    if play {
        // Feed the player in 40 ms frames the way the transport does.
        let frameBytes = Int(signalRate) * 2 * 40 / 1000
        var offset = 0
        while offset < signal.count {
            let end = min(offset + frameBytes, signal.count)
            io.play(pcm: signal[offset..<end], sampleRate: signalRate, channels: 1)
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
    var monitorURL: URL?
    if options.wakeTap {
        let mURL = URL(fileURLWithPath: options.out).appendingPathComponent("vpio-bench-\(name)-monitor.wav")
        try writeWAV(monitor.pcm, rate: 16_000, to: mURL)
        monitorURL = mURL
    }
    return Phase(name: name, voiceProcessing: voiceProcessing, seconds: options.seconds,
                 capturedRMS: capture.mean, capturedPeakRMS: capture.peakRMS, playoutRMS: playoutMean,
                 captureBuffers: capture.buffers, wakeBuffers: wake?.meter.buffers, wakeRMS: wake?.meter.mean,
                 monitorBuffers: options.wakeTap ? monitor.buffers : nil,
                 monitorRMS: options.wakeTap ? monitor.mean : nil,
                 monitorPeakRMS: options.wakeTap ? monitor.peakRMS : nil,
                 monitorWav: monitorURL?.path, muted: options.mute,
                 tapFormat: tapFormat, settle: options.settle, wav: url.path)
}

// MARK: - Run

// MARK: - Graph probe (--probe): which VPIO graph shapes start on this device

/// 2026-09-13, MacBook Air mic + speakers: with Voice Processing enabled the
/// input node reports 9 ch / 48 kHz and the output node 0 ch / 0 Hz, and
/// `mainMixer → output` with `format: nil` fails kAUInitialize (-10875).
/// Each variant below builds a fresh engine and reports whether it starts
/// and whether the input tap delivers, so the fix in AudioEngineIO is
/// chosen from a measurement, not a guess.
func probeGraphs() {
    struct Variant { let name: String; let connectInput: AVAudioFormat?; let tapFormat: AVAudioFormat?; let outputFormat: AVAudioFormat?; let inputToMixer: Bool }
    let mono48 = AVAudioFormat(standardFormatWithSampleRate: 48_000, channels: 1)!
    let stereo48 = AVAudioFormat(standardFormatWithSampleRate: 48_000, channels: 2)!
    // A tap format must equal the input bus format, so an explicit tap
    // format is only used where `connect` has set that bus to it first
    // (a mismatch raises an ObjC exception, not an error).
    let variants: [Variant] = [
        Variant(name: "tap-only, mixer->out nil (current)", connectInput: nil, tapFormat: nil, outputFormat: nil, inputToMixer: false),
        Variant(name: "tap-only, mixer->out stereo48", connectInput: nil, tapFormat: nil, outputFormat: stereo48, inputToMixer: false),
        Variant(name: "tap-only, mixer->out mono48", connectInput: nil, tapFormat: nil, outputFormat: mono48, inputToMixer: false),
        Variant(name: "input->mixer(input fmt), mixer->out nil", connectInput: nil, tapFormat: nil, outputFormat: nil, inputToMixer: true),
        Variant(name: "input->mixer(input fmt), mixer->out stereo48", connectInput: nil, tapFormat: nil, outputFormat: stereo48, inputToMixer: true),
        Variant(name: "input->mixer(mono48), mixer->out stereo48", connectInput: mono48, tapFormat: mono48, outputFormat: stereo48, inputToMixer: true),
        Variant(name: "input->mixer(mono48), mixer->out mono48", connectInput: mono48, tapFormat: mono48, outputFormat: mono48, inputToMixer: true),
    ]
    for v in variants {
        let engine = AVAudioEngine()
        let before = engine.inputNode.outputFormat(forBus: 0)
        var line: [String: Any] = ["probe": v.name, "inputBeforeVPIO": "\(before)"]
        do {
            try engine.inputNode.setVoiceProcessingEnabled(true)
            let input = engine.inputNode
            let inputFormat = input.outputFormat(forBus: 0)
            line["inputAfterVPIO"] = "\(inputFormat)"
            line["outputNodeBefore"] = "\(engine.outputNode.outputFormat(forBus: 0))"
            if v.inputToMixer {
                engine.connect(input, to: engine.mainMixerNode, format: v.connectInput ?? inputFormat)
                input.volume = 0   // AVAudioMixing on the source: never feed the mic to the speaker
            }
            engine.connect(engine.mainMixerNode, to: engine.outputNode, format: v.outputFormat)
            let meter = Meter()
            var tapFrames = 0
            let lock = NSLock()
            input.installTap(onBus: 0, bufferSize: 1024, format: v.tapFormat) { buffer, _ in
                lock.withLock { tapFrames += Int(buffer.frameLength) }
                _ = meter
            }
            engine.prepare()
            try engine.start()
            Thread.sleep(forTimeInterval: 0.6)
            line["started"] = true
            line["tapFrames"] = lock.withLock { tapFrames }
            line["tapFormat"] = "\(input.outputFormat(forBus: 0))"
            line["outputNodeAfter"] = "\(engine.outputNode.outputFormat(forBus: 0))"
            line["mixerOut"] = "\(engine.mainMixerNode.outputFormat(forBus: 0))"
            input.removeTap(onBus: 0)
            engine.stop()
        } catch {
            line["started"] = false
            line["error"] = "\(error)"
            line["outputNodeAfter"] = "\(engine.outputNode.outputFormat(forBus: 0))"
        }
        print(String(data: try! JSONSerialization.data(withJSONObject: line, options: [.sortedKeys]), encoding: .utf8)!)
    }
}

if options.probe {
    print(#"{"bench":"vpio-probe","input":"\#(inputName)","output":"\#(outputName)","microphone":"\#(microphone)"}"#)
    probeGraphs()
    exit(0)
}

// MARK: - Per-channel capture under VPIO (--channels)

/// 2026-09-13: with Voice Processing on, the MacBook Air input bus reports
/// 9 channels and AudioEngineIO's mono downmix of them carried the bot's
/// voice almost untouched (2.2 dB down, Silero opened 9 user turns). If the
/// echo-cancelled voice is one of those channels and the rest are raw array
/// channels, averaging them is the bug. This taps all channels as delivered,
/// plays the signal, and reports idle vs playback RMS per channel, writing
/// each channel as a 16 kHz WAV for the VAD to judge.
func perChannelCapture(signal: Data, signalRate: Double) throws {
    let engine = AVAudioEngine()
    let hardwareOutput = engine.outputNode.outputFormat(forBus: 0)
    try engine.inputNode.setVoiceProcessingEnabled(true)
    let input = engine.inputNode
    let tapFormat = input.outputFormat(forBus: 0)
    let channels = Int(tapFormat.channelCount)
    guard channels > 0, tapFormat.sampleRate > 0 else { throw JarvisError.transport("input reports \(tapFormat)") }
    let player = AVAudioPlayerNode()
    engine.attach(player)
    engine.connect(engine.mainMixerNode, to: engine.outputNode,
                   format: AVAudioFormat(standardFormatWithSampleRate: hardwareOutput.sampleRate, channels: hardwareOutput.channelCount))
    let mono = AVAudioFormat(standardFormatWithSampleRate: tapFormat.sampleRate, channels: 1)!
    let converters = (0..<channels).map { _ in CaptureConverter(inputFormat: mono)! }
    let idle = (0..<channels).map { _ in Meter() }
    let play = (0..<channels).map { _ in Meter() }
    let phaseLock = NSLock()
    var playing = false
    input.installTap(onBus: 0, bufferSize: 1024, format: nil) { buffer, _ in
        let frames = Int(buffer.frameLength)
        guard frames > 0, let src = buffer.floatChannelData else { return }
        let isPlaying = phaseLock.withLock { playing }
        for ch in 0..<channels {
            guard let monoBuffer = AVAudioPCMBuffer(pcmFormat: mono, frameCapacity: AVAudioFrameCount(frames)) else { continue }
            if buffer.format.isInterleaved {
                for i in 0..<frames { monoBuffer.floatChannelData![0][i] = src[0][i * channels + ch] }
            } else {
                monoBuffer.floatChannelData![0].update(from: src[ch], count: frames)
            }
            monoBuffer.frameLength = AVAudioFrameCount(frames)
            if let data = converters[ch].convert(monoBuffer) { (isPlaying ? play[ch] : idle[ch]).add(data) }
        }
    }
    engine.prepare()
    try engine.start()
    print(#"{"channels":\#(channels),"tapFormat":"\#(tapFormat)","voiceProcessing":\#(input.isVoiceProcessingEnabled)}"#)
    Thread.sleep(forTimeInterval: 3.0)               // idle window
    phaseLock.withLock { playing = true }
    guard let format = AVAudioFormat(standardFormatWithSampleRate: signalRate, channels: 1) else { return }
    engine.connect(player, to: engine.mainMixerNode, format: format)
    let frameBytes = Int(signalRate) * 2 * 40 / 1000
    var offset = 0
    while offset < signal.count {
        let end = min(offset + frameBytes, signal.count)
        if let b = PlayoutDecoder.buffer(fromInt16: signal[offset..<end], sampleRate: signalRate, channels: 1) { player.scheduleBuffer(b) }
        offset = end
    }
    player.play()
    Thread.sleep(forTimeInterval: Double(signal.count / 2) / signalRate + 0.5)
    input.removeTap(onBus: 0)
    player.stop(); engine.stop()
    for ch in 0..<channels {
        let url = URL(fileURLWithPath: options.out).appendingPathComponent("vpio-ch\(ch)-play.wav")
        try writeWAV(play[ch].pcm, rate: 16_000, to: url)
        let ratio: Any = idle[ch].mean > 0 && play[ch].mean > 0 ? 20 * log10(play[ch].mean / idle[ch].mean) : NSNull()
        let line: [String: Any] = ["channel": ch, "idleRMS": idle[ch].mean, "playRMS": play[ch].mean, "playPeakRMS": play[ch].peakRMS,
                                   "playAboveIdle_dB": ratio, "wav": url.path]
        print(String(data: try JSONSerialization.data(withJSONObject: line, options: [.sortedKeys]), encoding: .utf8)!)
    }
}

if options.channels {
    guard let path = options.signalPath else { FileHandle.standardError.write(Data("--channels needs --signal <wav>\n".utf8)); exit(2) }
    do {
        let loaded = try loadWAV(path)
        print(#"{"bench":"vpio-channels","input":"\#(inputName)","output":"\#(outputName)","microphone":"\#(microphone)","signal":"\#(path)"}"#)
        try perChannelCapture(signal: loaded.pcm, signalRate: loaded.rate)
    } catch { FileHandle.standardError.write(Data("channels bench failed: \(error)\n".utf8)); exit(1) }
    exit(0)
}

/// A real voice for the AEC to cancel: any PCM16 mono WAV (make one with
/// `say -o tts.wav --data-format=LEI16@24000 "…"`). Played at its own rate;
/// the phase length follows the file.
func loadWAV(_ path: String) throws -> (pcm: Data, rate: Double) {
    let data = try Data(contentsOf: URL(fileURLWithPath: path))
    guard data.count > 44, String(data: data[0..<4], encoding: .ascii) == "RIFF", String(data: data[8..<12], encoding: .ascii) == "WAVE" else {
        throw JarvisError.transport("\(path) is not a RIFF/WAVE file")
    }
    var offset = 12
    var rate = 0.0, channels = 0, bits = 0
    var pcm = Data()
    while offset + 8 <= data.count {
        let id = String(data: data[offset..<offset + 4], encoding: .ascii) ?? ""
        let size = Int(data[offset + 4..<offset + 8].withUnsafeBytes { $0.loadUnaligned(as: UInt32.self) })
        let body = offset + 8
        if id == "fmt " {
            let fmt = data[body..<body + 16]
            channels = Int(fmt[fmt.startIndex + 2..<fmt.startIndex + 4].withUnsafeBytes { $0.loadUnaligned(as: UInt16.self) })
            rate = Double(fmt[fmt.startIndex + 4..<fmt.startIndex + 8].withUnsafeBytes { $0.loadUnaligned(as: UInt32.self) })
            bits = Int(fmt[fmt.startIndex + 14..<fmt.startIndex + 16].withUnsafeBytes { $0.loadUnaligned(as: UInt16.self) })
        } else if id == "data" {
            pcm = data[body..<min(body + size, data.count)]
        }
        offset = body + size + (size & 1)
    }
    guard channels == 1, bits == 16, rate > 0, !pcm.isEmpty else {
        throw JarvisError.transport("\(path): need PCM16 mono, got \(channels) ch / \(bits)-bit / \(rate) Hz")
    }
    return (Data(pcm), rate)
}

let signal: Data
let signalRate: Double
if let path = options.signalPath {
    do {
        let loaded = try loadWAV(path)
        signal = loaded.pcm; signalRate = loaded.rate
        options.seconds = Double(signal.count / 2) / signalRate + 0.5
    } catch { FileHandle.standardError.write(Data("\(error)\n".utf8)); exit(2) }
} else {
    signal = speechShaped(seconds: options.seconds, gain: options.gain); signalRate = 24_000
}
var phases: [Phase] = []
do {
    let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys]
    print(#"{"bench":"vpio","input":"\#(inputName)","output":"\#(outputName)","microphone":"\#(microphone)","seconds":\#(options.seconds),"wake":\#(options.wake),"signal":"\#(options.signalPath ?? "speech-shaped noise")"}"#)
    // VPIO-off phases first: if the plain engine cannot start either, the
    // fault is the device/permission, not Voice Processing. A failed phase
    // is reported and the run continues so one invocation says everything.
    var failures: [String: String] = [:]
    var byName: [String: Phase] = [:]
    let all: [(String, Bool, Bool)] = [("idle-vpio-off", false, false), ("play-vpio-off", false, true),
                                       ("idle-vpio-on", true, false), ("play-vpio-on", true, true)]
    for (name, vp, play) in all where vp || !options.vpioOnly {
        do {
            let phase = try runPhase(name: name, voiceProcessing: vp, play: play, signal: signal, signalRate: signalRate)
            phases.append(phase); byName[name] = phase
            print(String(data: try encoder.encode(phase), encoding: .utf8)!)
        } catch {
            let text = String(describing: error).replacingOccurrences(of: "\"", with: "'")
            failures[name] = text
            print(#"{"name":"\#(name)","failed":"\#(text)"}"#)
        }
    }
    // JSON has no NaN: a missing phase or a zero RMS reports null.
    func dB(_ a: Double?, _ b: Double?) -> Any { if let a, let b, b > 0, a > 0 { return 20 * log10(a / b) }; return NSNull() }
    let idleOn = byName["idle-vpio-on"]?.capturedRMS, playOn = byName["play-vpio-on"]?.capturedRMS
    let idleOff = byName["idle-vpio-off"]?.capturedRMS, playOff = byName["play-vpio-off"]?.capturedRMS
    let summary: [String: Any] = [
        "residual_above_floor_dB_vpio_on": dB(playOn, idleOn),
        "residual_above_floor_dB_vpio_off": dB(playOff, idleOff),
        "vpio_echo_reduction_dB": dB(playOff, playOn),
        "monitor_residual_above_floor_dB_vpio_on": dB(byName["play-vpio-on"]?.monitorRMS, byName["idle-vpio-on"]?.monitorRMS),
        "input": inputName, "output": outputName, "microphone": microphone,
        "failed_phases": failures,
    ]
    print(String(data: try JSONSerialization.data(withJSONObject: summary, options: [.sortedKeys]), encoding: .utf8)!)
    if !failures.isEmpty { exit(1) }
} catch {
    FileHandle.standardError.write(Data("bench failed: \(error)\n".utf8))
    exit(1)
}
