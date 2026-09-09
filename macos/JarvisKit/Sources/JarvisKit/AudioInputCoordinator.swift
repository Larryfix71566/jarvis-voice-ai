#if os(macOS)
import Foundation
import CoreAudio
import os

private let inputLog = Logger(subsystem: "com.mortimer.jarviskit", category: "audio-input")

/// 2026-09-05 — the default-input band-aid for the AirPods slow-voice bug.
///
/// Root cause (confirmed from Larry's Audio MIDI Setup): AirPods Pro 3
/// present as TWO CoreAudio devices — a 48 kHz output and a SEPARATE
/// 24 kHz microphone. WebRTC runs one duplex audio unit for capture and
/// playout (echo cancellation), so when the session's input device is the
/// 24 kHz AirPods mic and the output is the 48 kHz AirPods speaker, the
/// 48 kHz playout gets dragged through the 24 kHz capture clock: half
/// speed, an octave down — "slow, not like Mortimer." Nothing server-side;
/// the bot's audio measured normal throughout.
///
/// This build's WebRTC has NO device-selection API, so the only lever is
/// the SYSTEM default input device, which the ADM reads when it initialises
/// at connect. So: right before connecting, if the default input's sample
/// rate does not match the default output's, we point the system default
/// input at a matching-rate device (the built-in 48 kHz mic), remember what
/// it was, and restore it on disconnect. Both ends then run at 48 kHz and
/// the duplex unit is clean — AirPods stay as the 48 kHz OUTPUT.
///
/// This is the stopgap. The real fix is the native-audio transport
/// (docs/plans/MORTIMER_NATIVE_AUDIO_TRANSPORT_PLAN.md), where AVAudioEngine
/// + VoiceProcessingIO pick devices and resample properly and this whole
/// class goes away.
public final class AudioInputCoordinator: @unchecked Sendable {
    /// The device we moved the default input AWAY from, to restore on
    /// disconnect. nil when we did not reassign.
    private var savedInputDevice: AudioDeviceID?

    public init() {}

    /// Pure decision: two live device rates "mismatch" (worth reassigning)
    /// when both are known and differ by more than a rounding point.
    public static func rateMismatch(input: Double, output: Double, tolerance: Double = 1) -> Bool {
        input > 0 && output > 0 && abs(input - output) > tolerance
    }

    /// Called BEFORE the transport connects (so the ADM initialises on the
    /// right device). If the default input rate ≠ the default output rate,
    /// repoint the system default input at a device whose rate matches the
    /// output — preferring the built-in mic — and return the change for the
    /// UI. Returns nil when nothing needed changing or no matching device
    /// exists.
    @discardableResult
    public func matchInputToOutputIfNeeded() -> AudioInputChange? {
        guard let out = Self.defaultOutputDevice(),
              let inp = Self.defaultInputDevice() else { return nil }
        let outRate = Self.nominalSampleRate(out.id)
        let inRate = Self.nominalSampleRate(inp.id)
        guard Self.rateMismatch(input: inRate, output: outRate) else { return nil }

        guard let target = Self.inputDeviceMatching(rate: outRate), target.id != inp.id else {
            inputLog.notice("input \(inp.name, privacy: .public) @\(Int(inRate)) ≠ output @\(Int(outRate)) but no matching-rate input device found; leaving as-is")
            return nil
        }
        guard Self.setDefaultInputDevice(target.id) else {
            inputLog.error("failed to set default input to \(target.name, privacy: .public)")
            return nil
        }
        savedInputDevice = inp.id
        inputLog.notice("default input moved \(inp.name, privacy: .public) @\(Int(inRate)) → \(target.name, privacy: .public) @\(Int(outRate)) to match output")
        return AudioInputChange(from: inp.name, to: target.name, fromRate: Int(inRate), toRate: Int(outRate))
    }

    /// Restore the user's original default input, if we changed it.
    public func restore() {
        guard let saved = savedInputDevice else { return }
        savedInputDevice = nil
        if Self.setDefaultInputDevice(saved) {
            inputLog.notice("default input restored")
        }
    }

    // MARK: - CoreAudio reads (self-contained; small dupes of AudioOutputMonitor's)

    struct Device { let id: AudioDeviceID; let name: String }

    static func defaultOutputDevice() -> Device? { defaultDevice(kAudioHardwarePropertyDefaultOutputDevice) }
    static func defaultInputDevice() -> Device? { defaultDevice(kAudioHardwarePropertyDefaultInputDevice) }

    private static func defaultDevice(_ selector: AudioObjectPropertySelector) -> Device? {
        var id = AudioDeviceID(kAudioObjectUnknown)
        var size = UInt32(MemoryLayout<AudioDeviceID>.size)
        var addr = AudioObjectPropertyAddress(mSelector: selector,
                                              mScope: kAudioObjectPropertyScopeGlobal,
                                              mElement: kAudioObjectPropertyElementMain)
        let status = AudioObjectGetPropertyData(AudioObjectID(kAudioObjectSystemObject), &addr, 0, nil, &size, &id)
        guard status == noErr, id != kAudioObjectUnknown else { return nil }
        return Device(id: id, name: deviceName(id) ?? "device \(id)")
    }

    static func nominalSampleRate(_ id: AudioDeviceID) -> Double {
        var rate: Float64 = 0
        var size = UInt32(MemoryLayout<Float64>.size)
        var addr = AudioObjectPropertyAddress(mSelector: kAudioDevicePropertyNominalSampleRate,
                                              mScope: kAudioObjectPropertyScopeGlobal,
                                              mElement: kAudioObjectPropertyElementMain)
        let status = AudioObjectGetPropertyData(id, &addr, 0, nil, &size, &rate)
        return status == noErr ? Double(rate) : 0
    }

    static func deviceName(_ id: AudioDeviceID) -> String? {
        var ref: Unmanaged<CFString>? = nil
        var size = UInt32(MemoryLayout<Unmanaged<CFString>?>.size)
        var addr = AudioObjectPropertyAddress(mSelector: kAudioObjectPropertyName,
                                              mScope: kAudioObjectPropertyScopeGlobal,
                                              mElement: kAudioObjectPropertyElementMain)
        let status = AudioObjectGetPropertyData(id, &addr, 0, nil, &size, &ref)
        guard status == noErr, let ref else { return nil }
        return ref.takeRetainedValue() as String
    }

    /// An input device whose nominal rate matches `rate`, preferring the
    /// built-in mic, then any other input device at that rate.
    static func inputDeviceMatching(rate: Double) -> Device? {
        let inputs = allDevices().filter { hasInputChannels($0) }
        // Prefer built-in at the matching rate.
        if let builtIn = inputs.first(where: { isBuiltIn($0) && rateMismatch(input: nominalSampleRate($0), output: rate) == false && nominalSampleRate($0) > 0 }) {
            return Device(id: builtIn, name: deviceName(builtIn) ?? "built-in mic")
        }
        // Else any input device already at the matching rate.
        if let any = inputs.first(where: { nominalSampleRate($0) > 0 && rateMismatch(input: nominalSampleRate($0), output: rate) == false }) {
            return Device(id: any, name: deviceName(any) ?? "device \(any)")
        }
        return nil
    }

    @discardableResult
    static func setDefaultInputDevice(_ id: AudioDeviceID) -> Bool {
        var dev = id
        var addr = AudioObjectPropertyAddress(mSelector: kAudioHardwarePropertyDefaultInputDevice,
                                              mScope: kAudioObjectPropertyScopeGlobal,
                                              mElement: kAudioObjectPropertyElementMain)
        let status = AudioObjectSetPropertyData(AudioObjectID(kAudioObjectSystemObject), &addr, 0, nil,
                                                UInt32(MemoryLayout<AudioDeviceID>.size), &dev)
        return status == noErr
    }

    private static func allDevices() -> [AudioDeviceID] {
        var size: UInt32 = 0
        var addr = AudioObjectPropertyAddress(mSelector: kAudioHardwarePropertyDevices,
                                              mScope: kAudioObjectPropertyScopeGlobal,
                                              mElement: kAudioObjectPropertyElementMain)
        guard AudioObjectGetPropertyDataSize(AudioObjectID(kAudioObjectSystemObject), &addr, 0, nil, &size) == noErr else { return [] }
        let count = Int(size) / MemoryLayout<AudioDeviceID>.size
        guard count > 0 else { return [] }
        var ids = [AudioDeviceID](repeating: 0, count: count)
        guard AudioObjectGetPropertyData(AudioObjectID(kAudioObjectSystemObject), &addr, 0, nil, &size, &ids) == noErr else { return [] }
        return ids
    }

    private static func hasInputChannels(_ id: AudioDeviceID) -> Bool {
        var size: UInt32 = 0
        var addr = AudioObjectPropertyAddress(mSelector: kAudioDevicePropertyStreamConfiguration,
                                              mScope: kAudioObjectPropertyScopeInput,
                                              mElement: kAudioObjectPropertyElementMain)
        guard AudioObjectGetPropertyDataSize(id, &addr, 0, nil, &size) == noErr, size > 0 else { return false }
        let raw = UnsafeMutableRawPointer.allocate(byteCount: Int(size), alignment: MemoryLayout<AudioBufferList>.alignment)
        defer { raw.deallocate() }
        guard AudioObjectGetPropertyData(id, &addr, 0, nil, &size, raw) == noErr else { return false }
        let list = UnsafeMutableAudioBufferListPointer(raw.assumingMemoryBound(to: AudioBufferList.self))
        return list.reduce(0) { $0 + Int($1.mNumberChannels) } > 0
    }

    private static func isBuiltIn(_ id: AudioDeviceID) -> Bool {
        var transport: UInt32 = 0
        var size = UInt32(MemoryLayout<UInt32>.size)
        var addr = AudioObjectPropertyAddress(mSelector: kAudioDevicePropertyTransportType,
                                              mScope: kAudioObjectPropertyScopeGlobal,
                                              mElement: kAudioObjectPropertyElementMain)
        guard AudioObjectGetPropertyData(id, &addr, 0, nil, &size, &transport) == noErr else { return false }
        return transport == kAudioDeviceTransportTypeBuiltIn
    }
}

/// What JarvisClient publishes when it repointed the default input so the
/// duplex audio unit runs at one rate.
public struct AudioInputChange: Equatable, Sendable {
    public let from: String
    public let to: String
    public let fromRate: Int
    public let toRate: Int
    public let at: Date

    public init(from: String, to: String, fromRate: Int, toRate: Int, at: Date = Date()) {
        self.from = from
        self.to = to
        self.fromRate = fromRate
        self.toRate = toRate
        self.at = at
    }

    /// One line for a notice chip.
    public var noticeText: String {
        "Mic set to \(to) — \(from) runs at \(fromRate/1000) kHz, which would slow Mortimer's voice"
    }
}
#endif
