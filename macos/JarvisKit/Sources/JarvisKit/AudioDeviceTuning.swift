#if os(macOS)
import AVFoundation
import CoreAudio
import os

private let deviceLog = Logger(subsystem: "com.mortimer.jarviskit", category: "audio-device")

/// The device I/O buffer, measured 2026-09-13 because the meter said so.
///
/// C7.5's latency reading (input levels arriving 137 ms old, displayed
/// p95 204 ms against a 150 ms gate) turned out to be dominated by a
/// single fact: both taps deliver **4800 frames — 100 ms of audio — ten
/// times a second**, whatever `installTap(bufferSize: 1024)` asks for.
/// `bufferSize` is a hint; the real quantum comes from the device's
/// `kAudioDevicePropertyBufferFrameSize`.
///
/// That buffer sits in front of everything, not just the wave: it is
/// 100 ms before the bot hears a word and 100 ms before a barge-in can
/// register. This reads the current value and, when
/// `JARVIS_AUDIO_IO_FRAMES` asks, requests a different one — off by
/// default, because the HAL setting is per device and shared with every
/// other app using it.
public enum AudioDeviceTuning {
    /// `JARVIS_AUDIO_IO_FRAMES=512` (env or UserDefaults) requests 512
    /// frames — 10.7 ms at 48 kHz. Unset changes nothing.
    public static var requestedFrames: UInt32? {
        if let raw = ProcessInfo.processInfo.environment["JARVIS_AUDIO_IO_FRAMES"], let value = UInt32(raw) {
            return value
        }
        let stored = UserDefaults.standard.integer(forKey: "JARVIS_AUDIO_IO_FRAMES")
        return stored > 0 ? UInt32(stored) : nil
    }

    static func defaultDevice(input: Bool) -> AudioDeviceID? {
        var id = AudioDeviceID(0)
        var size = UInt32(MemoryLayout<AudioDeviceID>.size)
        var address = AudioObjectPropertyAddress(
            mSelector: input ? kAudioHardwarePropertyDefaultInputDevice : kAudioHardwarePropertyDefaultOutputDevice,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain)
        let status = AudioObjectGetPropertyData(AudioObjectID(kAudioObjectSystemObject), &address, 0, nil, &size, &id)
        return status == noErr ? id : nil
    }

    static func bufferFrames(_ device: AudioDeviceID, input: Bool) -> UInt32? {
        var frames = UInt32(0)
        var size = UInt32(MemoryLayout<UInt32>.size)
        var address = AudioObjectPropertyAddress(
            mSelector: kAudioDevicePropertyBufferFrameSize,
            mScope: input ? kAudioDevicePropertyScopeInput : kAudioDevicePropertyScopeOutput,
            mElement: kAudioObjectPropertyElementMain)
        let status = AudioObjectGetPropertyData(device, &address, 0, nil, &size, &frames)
        return status == noErr ? frames : nil
    }

    /// The range the device will accept, so a refused request can say why.
    static func bufferFrameRange(_ device: AudioDeviceID, input: Bool) -> ClosedRange<UInt32>? {
        var range = AudioValueRange()
        var size = UInt32(MemoryLayout<AudioValueRange>.size)
        var address = AudioObjectPropertyAddress(
            mSelector: kAudioDevicePropertyBufferFrameSizeRange,
            mScope: input ? kAudioDevicePropertyScopeInput : kAudioDevicePropertyScopeOutput,
            mElement: kAudioObjectPropertyElementMain)
        let status = AudioObjectGetPropertyData(device, &address, 0, nil, &size, &range)
        guard status == noErr else { return nil }
        return UInt32(range.mMinimum)...UInt32(range.mMaximum)
    }

    @discardableResult
    static func setBufferFrames(_ frames: UInt32, on device: AudioDeviceID, input: Bool) -> Bool {
        var value = frames
        var address = AudioObjectPropertyAddress(
            mSelector: kAudioDevicePropertyBufferFrameSize,
            mScope: input ? kAudioDevicePropertyScopeInput : kAudioDevicePropertyScopeOutput,
            mElement: kAudioObjectPropertyElementMain)
        let status = AudioObjectSetPropertyData(device, &address, 0, nil,
                                                UInt32(MemoryLayout<UInt32>.size), &value)
        return status == noErr
    }

    /// Called before the engine starts. Always logs what the devices are
    /// doing; only changes anything when asked to.
    public static func report(applyRequest: Bool = true) {
        let want = requestedFrames
        for input in [true, false] {
            let role = input ? "input" : "output"
            guard let device = defaultDevice(input: input) else {
                deviceLog.notice("default \(role, privacy: .public) device: none")
                continue
            }
            let before = bufferFrames(device, input: input)
            let range = bufferFrameRange(device, input: input)
            if applyRequest, let want {
                let clamped = range.map { min(max(want, $0.lowerBound), $0.upperBound) } ?? want
                let ok = setBufferFrames(clamped, on: device, input: input)
                let after = bufferFrames(device, input: input)
                deviceLog.notice("""
                    \(role, privacy: .public) device \(device, privacy: .public): \
                    buffer \(before ?? 0, privacy: .public) → requested \(clamped, privacy: .public) \
                    (\(ok ? "accepted" : "REFUSED", privacy: .public)), now \(after ?? 0, privacy: .public) frames, \
                    range \(range?.lowerBound ?? 0, privacy: .public)…\(range?.upperBound ?? 0, privacy: .public)
                    """)
            } else {
                deviceLog.notice("""
                    \(role, privacy: .public) device \(device, privacy: .public): \
                    buffer \(before ?? 0, privacy: .public) frames, \
                    range \(range?.lowerBound ?? 0, privacy: .public)…\(range?.upperBound ?? 0, privacy: .public)
                    """)
            }
        }
    }
}
#endif
