import { useEffect, useRef } from "react";

export type OrbState = "offline" | "connecting" | "listening" | "speaking";

interface Dyn {
  energy: number; // waveform bar amplitude 0..1
  speed: number; // ring rotation multiplier
  glow: number; // core brightness 0..1
}

const TARGETS: Record<OrbState, Dyn> = {
  offline: { energy: 0.05, speed: 0.12, glow: 0.22 },
  connecting: { energy: 0.22, speed: 2.4, glow: 0.45 },
  listening: { energy: 0.3, speed: 0.55, glow: 0.65 },
  speaking: { energy: 1.0, speed: 1.0, glow: 1.0 },
};

const CYAN = "44, 201, 255";
const SIZE = 280;

// Deterministic pseudo-spectrum: layered sines per bar index.
function spectrum(i: number, t: number): number {
  const a = Math.sin(i * 0.7 + t * 2.1) * 0.5;
  const b = Math.sin(i * 1.9 - t * 3.3) * 0.3;
  const c = Math.sin(i * 3.1 + t * 5.7) * 0.2;
  return Math.abs(a + b + c);
}

export default function Orb({ state }: { state: OrbState }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const stateRef = useRef<OrbState>(state);
  stateRef.current = state;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = SIZE * dpr;
    canvas.height = SIZE * dpr;
    ctx.scale(dpr, dpr);

    const dyn: Dyn = { ...TARGETS.offline };
    let rot1 = 0;
    let rot2 = 0;
    let last = performance.now();
    let raf = 0;

    const frame = (now: number) => {
      const dt = Math.min((now - last) / 1000, 0.1);
      last = now;
      const t = now / 1000;

      // ease dynamics toward the current state's targets
      const target = TARGETS[stateRef.current];
      dyn.energy += (target.energy - dyn.energy) * 0.07;
      dyn.speed += (target.speed - dyn.speed) * 0.07;
      dyn.glow += (target.glow - dyn.glow) * 0.07;
      rot1 += dt * 0.25 * dyn.speed;
      rot2 -= dt * 0.4 * dyn.speed;

      const c = SIZE / 2;
      ctx.clearRect(0, 0, SIZE, SIZE);

      // --- outer tick ring ---
      ctx.save();
      ctx.translate(c, c);
      ctx.rotate(rot1);
      for (let i = 0; i < 96; i++) {
        const a = (i / 96) * Math.PI * 2;
        const major = i % 8 === 0;
        const r0 = major ? 122 : 127;
        const r1 = 134;
        ctx.strokeStyle = `rgba(${CYAN}, ${major ? 0.5 : 0.22})`;
        ctx.lineWidth = major ? 1.4 : 1;
        ctx.beginPath();
        ctx.moveTo(Math.cos(a) * r0, Math.sin(a) * r0);
        ctx.lineTo(Math.cos(a) * r1, Math.sin(a) * r1);
        ctx.stroke();
      }
      ctx.restore();

      // --- segmented arc rings (counter-rotating) ---
      const drawArcs = (
        radius: number,
        rot: number,
        segs: number,
        span: number,
        alpha: number,
        width: number,
      ) => {
        ctx.save();
        ctx.translate(c, c);
        ctx.rotate(rot);
        ctx.strokeStyle = `rgba(${CYAN}, ${alpha})`;
        ctx.lineWidth = width;
        for (let s = 0; s < segs; s++) {
          const start = (s / segs) * Math.PI * 2;
          ctx.beginPath();
          ctx.arc(0, 0, radius, start, start + span);
          ctx.stroke();
        }
        ctx.restore();
      };
      drawArcs(112, rot2, 5, 0.9, 0.35 + dyn.glow * 0.25, 1.6);
      drawArcs(98, -rot2 * 1.4, 3, 1.5, 0.25 + dyn.glow * 0.2, 1);

      // --- voice-reactive waveform bars ---
      ctx.save();
      ctx.translate(c, c);
      const bars = 72;
      for (let i = 0; i < bars; i++) {
        const a = (i / bars) * Math.PI * 2;
        const amp = spectrum(i, t) * dyn.energy;
        const r0 = 52;
        const r1 = r0 + 5 + amp * 26;
        ctx.strokeStyle = `rgba(${CYAN}, ${0.25 + amp * 0.65})`;
        ctx.lineWidth = 2;
        ctx.lineCap = "round";
        ctx.beginPath();
        ctx.moveTo(Math.cos(a) * r0, Math.sin(a) * r0);
        ctx.lineTo(Math.cos(a) * r1, Math.sin(a) * r1);
        ctx.stroke();
      }
      ctx.restore();

      // --- core: breathing radial glow ---
      const breathe = 1 + Math.sin(t * 1.3) * 0.04 * (0.4 + dyn.energy);
      const coreR = (26 + dyn.glow * 8) * breathe;
      const grad = ctx.createRadialGradient(c, c, 0, c, c, coreR * 2.2);
      grad.addColorStop(0, `rgba(220, 248, 255, ${0.35 + dyn.glow * 0.6})`);
      grad.addColorStop(0.35, `rgba(${CYAN}, ${0.25 + dyn.glow * 0.45})`);
      grad.addColorStop(1, `rgba(${CYAN}, 0)`);
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.arc(c, c, coreR * 2.2, 0, Math.PI * 2);
      ctx.fill();

      // inner bright nucleus
      ctx.fillStyle = `rgba(235, 252, 255, ${0.5 + dyn.glow * 0.5})`;
      ctx.beginPath();
      ctx.arc(c, c, 5 + dyn.glow * 4 * breathe, 0, Math.PI * 2);
      ctx.fill();

      raf = requestAnimationFrame(frame);
    };

    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, []);

  return <canvas ref={canvasRef} className="orb-canvas" width={SIZE} height={SIZE} />;
}
