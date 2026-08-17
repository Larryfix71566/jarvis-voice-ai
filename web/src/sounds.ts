/**
 * sounds.ts — Mortimer's four-tone audio identity
 * (MORTIMER_ENGAGEMENT_DESIGN_PLAN.md E3).
 *
 * Synthesized Web Audio, zero assets. The shared AudioContext is created
 * lazily on the first play — which always happens after the Connect
 * click, so autoplay policy is satisfied. Master gain 0.08: texture, not
 * notification noise. The hybrid voice-feedback rule (silence on visible
 * success) is what makes room for these — a soft tick confirms what
 * speech deliberately doesn't.
 *
 * Master toggle persisted at localStorage["mortimer.sounds"] (default
 * ON), guarded reads per the drawer-keys discipline. No per-tone
 * settings; voice control of the toggle is deliberately deferred.
 */

const LS_SOUNDS = "mortimer.sounds";
const MASTER_GAIN = 0.08;

let ctx: AudioContext | null = null;

function getCtx(): AudioContext | null {
  if (typeof AudioContext === "undefined") return null;
  if (!ctx) ctx = new AudioContext();
  if (ctx.state === "suspended") void ctx.resume().catch(() => {});
  return ctx;
}

export function soundsEnabled(): boolean {
  try {
    return localStorage.getItem(LS_SOUNDS) !== "off";
  } catch {
    return true;
  }
}

export function setSoundsEnabled(on: boolean): void {
  try {
    localStorage.setItem(LS_SOUNDS, on ? "on" : "off");
  } catch {
    /* storage unavailable — the toggle just won't persist */
  }
}

/** One oscillator note with a click-free gain envelope. */
function note(
  audio: AudioContext,
  type: OscillatorType,
  freq: number,
  startAt: number, // seconds, in audio-context time
  durationS: number,
  peak: number,
): void {
  const osc = audio.createOscillator();
  const gain = audio.createGain();
  osc.type = type;
  osc.frequency.value = freq;
  gain.gain.setValueAtTime(0, startAt);
  gain.gain.linearRampToValueAtTime(peak, startAt + 0.01);
  gain.gain.exponentialRampToValueAtTime(0.001, startAt + durationS);
  osc.connect(gain);
  gain.connect(audio.destination);
  osc.start(startAt);
  osc.stop(startAt + durationS + 0.02);
}

export type ToneName = "boot" | "tick" | "done" | "fail";

/** Play a tone; silently a no-op when toggled off or audio unavailable.
 * Specs locked by the plan (E3's table). */
export function play(tone: ToneName): void {
  if (!soundsEnabled()) return;
  const audio = getCtx();
  if (!audio) return;
  const t = audio.currentTime;
  switch (tone) {
    case "boot":
      // Two ascending sines, 180ms total — the arrival chirp.
      note(audio, "sine", 520, t, 0.09, MASTER_GAIN);
      note(audio, "sine", 780, t + 0.09, 0.09, MASTER_GAIN);
      return;
    case "tick":
      // 1.2 kHz blip, 30ms — a delegation left the station.
      note(audio, "sine", 1200, t, 0.03, MASTER_GAIN * 0.6);
      return;
    case "done":
      // 660+990 Hz dyad, 120ms — work came back clean.
      note(audio, "sine", 660, t, 0.12, MASTER_GAIN);
      note(audio, "sine", 990, t, 0.12, MASTER_GAIN * 0.7);
      return;
    case "fail":
      // 220 Hz triangle, 160ms — something went wrong.
      note(audio, "triangle", 220, t, 0.16, MASTER_GAIN);
      return;
  }
}
