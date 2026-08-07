/**
 * Wake word (stretch — client-triggered, bot pipeline untouched).
 *
 * Detection runs in the local openWakeWord sidecar
 * (./scripts/run_wakeword.sh, 127.0.0.1:7862): this module captures the
 * mic at 16 kHz, streams PCM16 frames over a websocket, and the sidecar
 * replies {"type":"wake"} when it hears "Mortimer". On wake: chime +
 * onWake (the UI unmutes the mic). Fully local — no keys, no cloud.
 * (Picovoice's free tier was discontinued 2026-06-30, so openWakeWord
 * replaced it.) The sidecar needs a custom-trained Mortimer model —
 * see JARVIS_WAKEWORD_MODEL and README §4.
 */

const WS_URL = "ws://localhost:7862/ws";

/** No key is needed; sidecar problems surface as an error on toggle. */
export const wakeWordAvailable = true;

/** AudioWorklet source: float32 in, transferable PCM16 ArrayBuffer out. */
const WORKLET_SRC = `
class PCMProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (ch && ch.length) {
      const pcm = new Int16Array(ch.length);
      for (let i = 0; i < ch.length; i++) {
        const s = Math.max(-1, Math.min(1, ch[i]));
        pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
      }
      this.port.postMessage(pcm.buffer, [pcm.buffer]);
    }
    return true;
  }
}
registerProcessor("pcm-processor", PCMProcessor);
`;

let stream: MediaStream | null = null;
let ctx: AudioContext | null = null;
let node: AudioWorkletNode | null = null;
let ws: WebSocket | null = null;
let running = false;

/** Short two-tone chime via WebAudio (no asset file needed). */
export function playChime(): void {
  try {
    const chimeCtx = new AudioContext();
    const notes: Array<[number, number]> = [
      [880, 0],
      [1320, 0.12],
    ];
    for (const [freq, offset] of notes) {
      const osc = chimeCtx.createOscillator();
      const gain = chimeCtx.createGain();
      osc.type = "sine";
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(0.18, chimeCtx.currentTime + offset);
      gain.gain.exponentialRampToValueAtTime(
        0.001,
        chimeCtx.currentTime + offset + 0.25,
      );
      osc.connect(gain).connect(chimeCtx.destination);
      osc.start(chimeCtx.currentTime + offset);
      osc.stop(chimeCtx.currentTime + offset + 0.3);
    }
    window.setTimeout(() => void chimeCtx.close(), 800);
  } catch {
    // AudioContext unavailable (autoplay policy) — wake still applies.
  }
}

function cleanup(): void {
  node?.disconnect();
  node = null;
  if (ctx !== null) {
    void ctx.close();
    ctx = null;
  }
  stream?.getTracks().forEach((t) => t.stop());
  stream = null;
  ws?.close();
  ws = null;
  running = false;
}

/** Start listening for "Mortimer". onWake fires on every detection. */
export async function startWakeWord(onWake: () => void): Promise<void> {
  if (running) return;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });

    ws = new WebSocket(WS_URL);
    await new Promise<void>((resolve, reject) => {
      if (ws === null) return reject(new Error("no socket"));
      ws.onopen = () => resolve();
      ws.onerror = () =>
        reject(
          new Error(
            "wake-word sidecar unreachable — start it with ./scripts/run_wakeword.sh",
          ),
        );
    });
    ws.onmessage = (ev: MessageEvent) => {
      try {
        const msg = JSON.parse(String(ev.data));
        if (msg?.type === "wake") {
          playChime();
          onWake();
        }
      } catch {
        // malformed frame — ignore
      }
    };
    ws.onclose = () => {
      if (running) cleanup();
    };

    ctx = new AudioContext({ sampleRate: 16000 });
    const moduleUrl = URL.createObjectURL(
      new Blob([WORKLET_SRC], { type: "application/javascript" }),
    );
    await ctx.audioWorklet.addModule(moduleUrl);
    URL.revokeObjectURL(moduleUrl);
    const source = ctx.createMediaStreamSource(stream);
    node = new AudioWorkletNode(ctx, "pcm-processor");
    node.port.onmessage = (e: MessageEvent) => {
      if (ws !== null && ws.readyState === WebSocket.OPEN) {
        ws.send(e.data as ArrayBuffer);
      }
    };
    source.connect(node);
    // The worklet writes no output samples, so this link is silent; it only
    // guarantees the graph keeps pulling audio through the processor.
    node.connect(ctx.destination);
    running = true;
  } catch (err) {
    cleanup();
    throw err instanceof Error ? err : new Error("wake word failed");
  }
}

/** Stop listening and release mic + socket + audio resources. */
export async function stopWakeWord(): Promise<void> {
  cleanup();
}

export function isWakeWordRunning(): boolean {
  return running;
}
