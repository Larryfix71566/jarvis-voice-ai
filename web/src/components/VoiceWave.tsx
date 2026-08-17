import { useEffect, useRef } from "react";
import { usePipecatClientMediaTrack } from "@pipecat-ai/client-react";
import { getFieldRect, subscribeFieldRect } from "../agentLayout";
import { subscribeWake } from "../wakeWord";
import type { VoiceState } from "../voiceState";

/**
 * VoiceWave — SILO-style voice display.
 *
 * A full-viewport horizontal sine field rendered behind everything
 * (position: fixed, z-index 0): the agent satellites, readout, and bars
 * float over it. Silent states show a dim, slow-breathing trace; when
 * Mortimer speaks the wave blooms bright cyan-white and is driven by the
 * REAL bot audio (Web Audio AnalyserNode on the bot's WebRTC track). If
 * the track is unavailable it falls back to a simulated speech envelope,
 * so the display still answers BotStartedSpeaking/BotStoppedSpeaking.
 * Wake-word detections flash the whole field briefly.
 */

interface Dyn {
  base: number; // resting amplitude (fraction of viewport height)
  speed: number; // phase drift multiplier
  alpha: number; // trace opacity 0..1
  glow: number; // phosphor glow 0..1
  cr: number; // eased color channels
  cg: number;
  cb: number;
}

const COLORS: Record<VoiceState, [number, number, number]> = {
  offline: [95, 130, 150], // dim slate
  connecting: [44, 201, 255],
  listening: [44, 201, 255], // silent: dim cyan
  speaking: [190, 240, 255], // talking: bright cyan-white
};

const TARGETS: Record<VoiceState, Pick<Dyn, "base" | "speed" | "alpha" | "glow">> = {
  offline: { base: 0.004, speed: 0.12, alpha: 0.16, glow: 0 },
  connecting: { base: 0.014, speed: 1.4, alpha: 0.3, glow: 0.25 },
  listening: { base: 0.01, speed: 0.45, alpha: 0.34, glow: 0.15 },
  speaking: { base: 0.016, speed: 1.0, alpha: 0.92, glow: 1 },
};

/** Global vertical scale for the whole wave (user-tuned: 2x). */
const AMP_SCALE = 2;

/** Trace layers: main + two phase-offset echoes for the phosphor look. */
const LAYERS = [
  { aMul: 1, fMul: 1, po: 0, width: 2 },
  { aMul: 0.45, fMul: 1.35, po: 0.9, width: 1.4 },
  { aMul: 0.22, fMul: 0.72, po: -1.6, width: 1 },
];

/** Simulated speech envelope — only used when no bot audio track exists. */
function simLevel(t: number): number {
  const s = Math.abs(Math.sin(t * 6.1) * 0.6 + Math.sin(t * 9.7 + 1.3) * 0.4);
  return 0.25 + 0.75 * s;
}

// Engagement plan E2 — boot ramp: the wave rises from flatline over
// 900ms when a connection arrives. Module-level trigger (same pub/sub-
// lite style as wakeWord's flash) so OrbField can fire it without prop
// drilling; 0 = never booted = full amplitude (e.g. a hot reload
// mid-session must not flatline the wave).
const BOOT_RAMP_MS = 900;
const bootStart = { current: 0 };

export function bootWave(): void {
  bootStart.current = performance.now();
}

export default function VoiceWave({ state }: { state: VoiceState }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const stateRef = useRef<VoiceState>(state);
  stateRef.current = state;

  const analyserRef = useRef<AnalyserNode | null>(null);
  const levelRef = useRef(0); // smoothed voice level 0..1
  const wakeFlashRef = useRef(0); // 1 on wake detection, decays to 0
  // Horizontal center of the STAGE (.orb-field), in viewport px — the
  // canvas is full-viewport, but the stage shrinks when the side drawer
  // pushes it (.stage-row flex), and the wave's peak must stay centered
  // on the stage (aligned with the readout/satellites), not the viewport.
  // OrbField already publishes its measured rect for exactly this kind of
  // cross-component anchoring (agentLayout.ts); null = no rect yet, fall
  // back to viewport center.
  const stageCxRef = useRef<number | null>(null);
  const botTrack = usePipecatClientMediaTrack("audio", "bot");

  // Wake-word flash: the field surges when "Mortimer" is detected.
  useEffect(
    () =>
      subscribeWake(() => {
        wakeFlashRef.current = 1;
      }),
    [],
  );

  // Track the stage center (drawer open/close/resize all re-publish the
  // rect via OrbField's ResizeObserver — including every frame of the
  // drawer's width transition, so the wave follows it smoothly).
  useEffect(() => {
    const apply = (rect: { left: number; width: number } | null) => {
      stageCxRef.current = rect === null ? null : rect.left + rect.width / 2;
    };
    apply(getFieldRect());
    return subscribeFieldRect(apply);
  }, []);

  // Real-audio drive: analyse the bot's WebRTC track (tap only — audio
  // keeps playing through PipecatClientAudio; this graph never reaches a
  // destination, so nothing is doubled or muted).
  useEffect(() => {
    if (!botTrack) return;
    let audioCtx: AudioContext;
    let source: MediaStreamAudioSourceNode;
    try {
      audioCtx = new AudioContext();
      source = audioCtx.createMediaStreamSource(new MediaStream([botTrack]));
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 512;
      source.connect(analyser);
      analyserRef.current = analyser;
    } catch {
      analyserRef.current = null; // fall back to the simulated envelope
      return;
    }
    // The context can start suspended under autoplay policy; the Connect
    // click (and any later tap) counts as a user gesture, so resume there.
    const resume = () => void audioCtx.resume().catch(() => {});
    resume();
    window.addEventListener("pointerdown", resume);
    return () => {
      window.removeEventListener("pointerdown", resume);
      analyserRef.current = null;
      source.disconnect();
      void audioCtx.close().catch(() => {});
    };
  }, [botTrack]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const size = { w: window.innerWidth, h: window.innerHeight };
    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      size.w = window.innerWidth;
      size.h = window.innerHeight;
      canvas.width = Math.floor(size.w * dpr);
      canvas.height = Math.floor(size.h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    window.addEventListener("resize", resize);

    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const reducedRef = { current: mq.matches };
    const onMq = (e: MediaQueryListEvent) => {
      reducedRef.current = e.matches;
    };
    mq.addEventListener("change", onMq);

    const dyn: Dyn = {
      base: TARGETS.offline.base,
      speed: TARGETS.offline.speed,
      alpha: TARGETS.offline.alpha,
      glow: 0,
      cr: COLORS.offline[0],
      cg: COLORS.offline[1],
      cb: COLORS.offline[2],
    };
    const buf = new Uint8Array(512);
    let p1 = 0;
    let p2 = 0;
    let p3 = 0;
    let cxEased = -1; // sentinel: snap to target on the first frame
    let last = performance.now();
    let raf = 0;

    const frame = (now: number) => {
      const dt = Math.min((now - last) / 1000, 0.1);
      last = now;
      const t = now / 1000;
      const st = stateRef.current;
      const reduced = reducedRef.current;

      // --- voice level: real RMS when available, simulated when speaking ---
      let target = 0;
      const analyser = analyserRef.current;
      if (analyser) {
        analyser.getByteTimeDomainData(buf);
        let sum = 0;
        for (let i = 0; i < buf.length; i++) {
          const v = (buf[i] - 128) / 128;
          sum += v * v;
        }
        target = Math.min(1, Math.sqrt(sum / buf.length) * 3.5);
      } else if (st === "speaking") {
        target = simLevel(t);
      }
      // fast attack, slow release — feels like a VU meter
      const lv = levelRef.current;
      levelRef.current =
        target > lv ? lv + (target - lv) * 0.45 : lv + (target - lv) * 0.06;

      // --- wake flash decay (~0.7s surge across the whole field) ---
      wakeFlashRef.current = Math.max(0, wakeFlashRef.current - dt * 1.4);
      const flash = reduced ? 0 : wakeFlashRef.current;

      // --- ease dynamics + color toward the current state ---
      const tg = TARGETS[st];
      const [tr, tg_, tb] = COLORS[st];
      dyn.base += (tg.base - dyn.base) * 0.06;
      dyn.speed += (tg.speed - dyn.speed) * 0.06;
      dyn.alpha += (tg.alpha - dyn.alpha) * 0.06;
      dyn.glow += (tg.glow - dyn.glow) * 0.06;
      dyn.cr += (tr - dyn.cr) * 0.06;
      dyn.cg += (tg_ - dyn.cg) * 0.06;
      dyn.cb += (tb - dyn.cb) * 0.06;

      if (!reduced) {
        p1 += dt * 2.2 * dyn.speed;
        p2 -= dt * 3.1 * dyn.speed;
        p3 += dt * 5.3 * dyn.speed;
      }

      const { w, h } = size;
      // Center on the stage, not the viewport (see stageCxRef above);
      // eased so a drawer snap (no CSS transition on open) still slides
      // the wave over rather than teleporting it.
      const cxTarget = stageCxRef.current ?? w / 2;
      cxEased = cxEased < 0 ? cxTarget : cxEased + (cxTarget - cxEased) * 0.12;
      const cx = cxEased;
      const cy = h * 0.5;
      const breath = st === "listening" ? 0.004 + 0.004 * Math.sin(t * 0.9) : 0;
      const voice = st === "speaking" ? levelRef.current * 0.115 : 0;
      // E2 boot ramp — eased 0→1 over BOOT_RAMP_MS from bootWave();
      // instant under reduced motion.
      let bootRamp = 1;
      if (!reduced && bootStart.current > 0) {
        const p = Math.min(1, (now - bootStart.current) / BOOT_RAMP_MS);
        bootRamp = p * (2 - p); // ease-out
      }
      const amp =
        h * (dyn.base + breath + voice + flash * 0.02) * (reduced ? 0.4 : 1) *
        AMP_SCALE * bootRamp;
      const alpha = Math.min(1, dyn.alpha + flash * 0.45);
      const glow = Math.min(1, dyn.glow + flash);

      ctx.clearRect(0, 0, w, h);

      const glowOn = glow > 0.05 && !reduced;
      if (glowOn) {
        ctx.shadowBlur = 26 * glow;
        ctx.shadowColor = `rgba(44, 201, 255, ${0.75 * glow})`;
      }

      const r = Math.round(dyn.cr);
      const g = Math.round(dyn.cg);
      const b = Math.round(dyn.cb);

      for (const L of LAYERS) {
        ctx.beginPath();
        for (let x = 0; x <= w; x += 3) {
          // Super-Gaussian window: tight central plateau (middle ~10% of
          // the screen holds >=94% of peak) with fast falloff either side
          const env = Math.exp(-(((x - cx) / (0.11 * w)) ** 4));
          // slow speech-like wobble along the trace
          const mod = 0.65 + 0.35 * Math.sin(0.012 * x * L.fMul + t * 6.3 * dyn.speed + L.po);
          const y =
            cy +
            env * amp * L.aMul * mod *
              (0.55 * Math.sin(0.04 * x * L.fMul + p1 * L.fMul + L.po) +
                0.3 * Math.sin(0.084 * x * L.fMul + p2 * L.fMul - L.po) +
                0.15 * Math.sin(0.172 * x * L.fMul + p3 * L.fMul + L.po * 2));
          if (x === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.strokeStyle = `rgba(${r}, ${g}, ${b}, ${alpha * L.aMul})`;
        ctx.lineWidth = L.width;
        ctx.lineJoin = "round";
        ctx.stroke();
      }
      ctx.shadowBlur = 0;

      raf = requestAnimationFrame(frame);
    };

    raf = requestAnimationFrame(frame);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
      mq.removeEventListener("change", onMq);
    };
  }, []);

  return <canvas ref={canvasRef} className="voice-wave" aria-hidden="true" />;
}
