/**
 * Wake word (plan Phase 7.4 stretch — client-side only, server unchanged).
 *
 * Picovoice Porcupine Web runs locally in the browser listening for a
 * custom-trained "Mortimer" keyword. Porcupine ships no built-in Mortimer
 * keyword, so the model file must be trained once in Picovoice Console
 * (platform: Web) and placed at web/public/mortimer.ppn. On detection the
 * listener plays a chime and invokes the onWake callback (the UI unmutes
 * the mic). Everything is opt-in: without VITE_PICOVOICE_ACCESS_KEY (free
 * key from https://console.picovoice.ai) the feature is unavailable and
 * the toggle stays disabled.
 */

import { PorcupineWorker } from "@picovoice/porcupine-web";
import { WebVoiceProcessor } from "@picovoice/web-voice-processor";

const ACCESS_KEY: string = import.meta.env.VITE_PICOVOICE_ACCESS_KEY ?? "";

/** Custom "Mortimer" keyword model served from web/public. */
const MORTIMER_KEYWORD = {
  publicPath: "/mortimer.ppn",
  customWritePath: "mortimer",
  forceWrite: true,
  label: "Mortimer",
};

/** Whether the wake-word feature can run (key configured). */
export const wakeWordAvailable = ACCESS_KEY.length > 0;

let worker: PorcupineWorker | null = null;
let running = false;

/** Short two-tone chime via WebAudio (no asset file needed). */
export function playChime(): void {
  try {
    const ctx = new AudioContext();
    const notes: Array<[number, number]> = [
      [880, 0],
      [1320, 0.12],
    ];
    for (const [freq, offset] of notes) {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "sine";
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(0.18, ctx.currentTime + offset);
      gain.gain.exponentialRampToValueAtTime(
        0.001,
        ctx.currentTime + offset + 0.25,
      );
      osc.connect(gain).connect(ctx.destination);
      osc.start(ctx.currentTime + offset);
      osc.stop(ctx.currentTime + offset + 0.3);
    }
    window.setTimeout(() => void ctx.close(), 800);
  } catch {
    // AudioContext unavailable (autoplay policy) — wake still applies.
  }
}

/** Start listening for "Mortimer". onWake fires on every detection. */
export async function startWakeWord(onWake: () => void): Promise<void> {
  if (!wakeWordAvailable || running) return;
  let instance: PorcupineWorker;
  try {
    instance = await PorcupineWorker.create(
      ACCESS_KEY,
      MORTIMER_KEYWORD,
      () => {
        playChime();
        onWake();
      },
      { publicPath: "/porcupine_params.pv" },
      {
        processErrorCallback: (error: { message?: string; toString(): string }) =>
          console.warn("wake word processing error:", error?.message ?? String(error)),
      },
    );
  } catch (err) {
    const hint =
      'wake word model missing — train "Mortimer" in Picovoice Console ' +
      "(platform: Web) and place the .ppn at web/public/mortimer.ppn";
    throw new Error(
      err instanceof Error && err.message ? `${hint} (${err.message})` : hint,
    );
  }
  worker = instance;
  await WebVoiceProcessor.subscribe(instance);
  running = true;
}

/** Stop listening and release mic + worker resources. */
export async function stopWakeWord(): Promise<void> {
  if (worker !== null) {
    await WebVoiceProcessor.unsubscribe(worker);
    await worker.release();
    worker.terminate();
    worker = null;
  }
  running = false;
}

export function isWakeWordRunning(): boolean {
  return running;
}
