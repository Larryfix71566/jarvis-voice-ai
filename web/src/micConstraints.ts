/**
 * Capture hardening (voice isolation plan, task A1).
 *
 * client-js 1.13 / small-webrtc-transport 1.10 acquire the mic internally
 * via `navigator.mediaDevices.getUserMedia({ audio: true })` and expose no
 * constraint hook, so we wrap getUserMedia once at startup to merge the
 * constraints the plan requires — echo cancellation, browser noise
 * suppression, and auto gain control. The wrap also covers the wake-word
 * engine's mic acquisition, which benefits from the same treatment.
 *
 * Explicit constraints requested by a caller always win (spread last).
 */
let installed = false;

export function installMicConstraints(): void {
  if (installed) return;
  const devices =
    typeof navigator !== "undefined" ? navigator.mediaDevices : undefined;
  if (!devices?.getUserMedia) return; // non-secure context / SSR — nothing to do
  installed = true;

  const original = devices.getUserMedia.bind(devices);
  devices.getUserMedia = (constraints?: MediaStreamConstraints) => {
    if (constraints?.audio) {
      const audio =
        typeof constraints.audio === "boolean" ? {} : constraints.audio;
      constraints = {
        ...constraints,
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          ...audio,
        },
      };
    }
    return original(constraints);
  };
}
