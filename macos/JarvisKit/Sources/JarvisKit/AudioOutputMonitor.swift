#if os(macOS)
import Foundation
import CoreAudio
import os

private let monitorLog = Logger(subsystem: "com.mortimer.jarviskit", category: "audio-output")

/// 2026-09-05 — watches macOS's default OUTPUT device and reports when it
/// changes (AirPods connecting, a display's speakers, a dock).
///
/// Why this exists: the bot's voice arrives over WebRTC, and the plain
/// stasel/WebRTC M120 build's macOS audio device module opens the default
/// output device ONCE, when playout starts, and keeps that AudioDeviceID
/// for the life of the peer connection. It does not follow
/// kAudioHardwarePropertyDefaultOutputDevice afterwards, and the
/// framework exposes no playout-device API on macOS (the only
/// device-selection API, RTCAudioDeviceModule.outputDevice, is in the
/// LiveKit webrtc-sdk fork, not this dependency). So when AirPods connect
/// mid-session every other app moves to them and Mortimer keeps talking
/// to the old device — measured live 2026-09-05 13:13 ("voice no longer
/// comes through AirPods while all other sounds do"). The same mechanism
/// explains the earlier slow/stretched-voice episode: the device the ADM
/// was bound to went away underneath it.
///
/// The ONLY lever this build has is a reconnect (a new peer connection →
/// a new playout init → the current default device). A reconnect starts
/// a fresh bot session, so it is not done silently by default:
/// `JarvisClient` publishes the change for the app to surface with a
/// Reconnect action, and auto-reconnects only behind
/// `JarvisFlags.followAudioOutput`.
public final class AudioOutputMonitor: @unchecked Sendable {
    public struct Device: Equatable, Sendable {
        public let id: AudioDeviceID
        public let name: String
    }

    /// (previous, next) — `next` is nil when the system reports no
    /// default output device at all (no audio hardware).
    public typealias ChangeHandler = @MainActor (Device?, Device?) -> Void

    private let onChange: ChangeHandler
    private var listener: AudioObjectPropertyListenerBlock?
    private var address = AudioObjectPropertyAddress(
        mSelector: kAudioHardwarePropertyDefaultOutputDevice,
        mScope: kAudioObjectPropertyScopeGlobal,
        mElement: kAudioObjectPropertyElementMain
    )
    /// The last device seen — read on start() so the first change is a
    /// real change, not "nil → whatever is plugged in".
    public private(set) var current: Device?

    public init(onChange: @escaping ChangeHandler) {
        self.onChange = onChange
    }

    deinit { stop() }

    public func start() {
        guard listener == nil else { return }
        current = Self.defaultOutputDevice()
        let block: AudioObjectPropertyListenerBlock = { [weak self] _, _ in
            guard let self else { return }
            let next = Self.defaultOutputDevice()
            let previous = self.current
            guard next != previous else { return }
            self.current = next
            monitorLog.notice("default_output_changed from=\(previous?.name ?? "none", privacy: .public) to=\(next?.name ?? "none", privacy: .public)")
            let handler = self.onChange
            Task { @MainActor in handler(previous, next) }
        }
        listener = block
        let status = AudioObjectAddPropertyListenerBlock(
            AudioObjectID(kAudioObjectSystemObject), &address, DispatchQueue.main, block)
        if status != noErr {
            monitorLog.error("AudioObjectAddPropertyListenerBlock failed status=\(status)")
            listener = nil
        }
    }

    public func stop() {
        guard let block = listener else { return }
        AudioObjectRemovePropertyListenerBlock(
            AudioObjectID(kAudioObjectSystemObject), &address, DispatchQueue.main, block)
        listener = nil
    }

    /// The system's current default output device, or nil.
    public static func defaultOutputDevice() -> Device? {
        var deviceID = AudioDeviceID(kAudioObjectUnknown)
        var size = UInt32(MemoryLayout<AudioDeviceID>.size)
        var addr = AudioObjectPropertyAddress(
            mSelector: kAudioHardwarePropertyDefaultOutputDevice,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )
        let status = AudioObjectGetPropertyData(
            AudioObjectID(kAudioObjectSystemObject), &addr, 0, nil, &size, &deviceID)
        guard status == noErr, deviceID != kAudioObjectUnknown else { return nil }
        return Device(id: deviceID, name: deviceName(deviceID) ?? "device \(deviceID)")
    }

    static func deviceName(_ id: AudioDeviceID) -> String? {
        var addr = AudioObjectPropertyAddress(
            mSelector: kAudioObjectPropertyName,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )
        var nameRef: Unmanaged<CFString>? = nil
        var size = UInt32(MemoryLayout<Unmanaged<CFString>?>.size)
        let status = AudioObjectGetPropertyData(id, &addr, 0, nil, &size, &nameRef)
        guard status == noErr, let ref = nameRef else { return nil }
        return ref.takeRetainedValue() as String
    }
}

/// What `JarvisClient` publishes when the default output device changes
/// while a session is live.
public struct AudioOutputChange: Equatable, Sendable {
    public let from: String?
    public let to: String
    public let at: Date

    public init(from: String?, to: String, at: Date = Date()) {
        self.from = from
        self.to = to
        self.at = at
    }

    /// One line for a notice chip: "Audio output moved to AirPods Pro —
    /// Mortimer's voice is still on MacBook Air Speakers".
    public var noticeText: String {
        if let from { return "Audio output moved to \(to) — Mortimer's voice is still on \(from)" }
        return "Audio output moved to \(to) — Mortimer's voice did not follow"
    }
}
#endif
