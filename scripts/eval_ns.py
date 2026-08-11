"""Offline evaluation harness for the noise-suppression stage (plan §6, E1/E2).

Mixes clean speech with noise at controlled SNRs, runs each mixture through
the SAME filter class the production transport uses, and reports SNR
improvement, (optional) STOI, and real-time factor. Enhanced WAVs are written
for listening QA (plan §2.2 "no audible artifacts").

Usage:
    python -m scripts.eval_ns \
        --clean data/eval/clean --noise data/eval/noise \
        --snr 0 5 10 15 --out data/eval/out

Inputs must be 16-bit PCM WAV (any sample rate; linear-resampled to 48 kHz).
Install the engine under test first: pip install deepfilternet
Optional: pip install pystoi  (adds STOI columns)

TODO (plan Phase 0/2): DNSMOS perceptual scoring; WER delta via Deepgram on
enhanced vs raw (needs DEEPGRAM_API_KEY); interferer-speech splits for the
deferred Workstream-V gate metrics.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
import wave
from pathlib import Path

import numpy as np

SR = 48000  # engine domain (plan: capture 48 kHz, suppress before downsample)


def read_wav(path: Path) -> np.ndarray:
    """Read a 16-bit PCM WAV as float32 mono, resampled to SR."""
    with wave.open(str(path), "rb") as w:
        raw = w.readframes(w.getnframes())
        channels, rate = w.getnchannels(), w.getframerate()
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        x = x.reshape(-1, channels).mean(axis=1)
    if rate != SR:
        idx = np.linspace(0, len(x) - 1, int(len(x) * SR / rate))
        x = np.interp(idx, np.arange(len(x)), x).astype(np.float32)
    return x


def write_wav(path: Path, x: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(x, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def mix_at_snr(clean: np.ndarray, noise: np.ndarray, snr_db: float) -> np.ndarray:
    if len(noise) < len(clean):
        reps = int(np.ceil(len(clean) / len(noise)))
        noise = np.tile(noise, reps)
    noise = noise[: len(clean)]
    gain = np.sqrt(np.mean(clean**2) / (np.mean(noise**2) + 1e-12))
    scale = gain / (10 ** (snr_db / 20))
    return clean + noise * scale


async def run_filter(audio_filter, x: np.ndarray) -> tuple[np.ndarray, float]:
    """Feed 10 ms chunks through a production filter; returns (output, cpu_s)."""
    await audio_filter.start(SR)
    out, cpu = [], 0.0
    hop = int(SR * 0.01)
    for i in range(0, len(x), hop):
        chunk = (np.clip(x[i : i + hop], -1, 1) * 32767).astype(np.int16).tobytes()
        t0 = time.perf_counter()
        result = await audio_filter.filter(chunk)
        cpu += time.perf_counter() - t0
        if result:
            out.append(np.frombuffer(result, dtype=np.int16))
    await audio_filter.stop()
    y = np.concatenate(out).astype(np.float32) / 32768.0 if out else np.zeros(0, np.float32)
    return y, cpu


def align(a: np.ndarray, b: np.ndarray, max_lag: int = SR // 2) -> tuple[np.ndarray, np.ndarray]:
    """Align b to a by cross-correlation peak (filters add small delays)."""
    n = min(len(a), len(b), SR * 5)
    corr = np.correlate(a[:n], b[:n], mode="full")
    lag = int(np.argmax(corr[len(corr) // 2 - max_lag : len(corr) // 2 + max_lag])) - max_lag
    b_shift = np.roll(b, lag)
    m = min(len(a), len(b_shift))
    return a[:m], b_shift[:m]


def snr_db(clean: np.ndarray, estimate: np.ndarray) -> float:
    clean, estimate = align(clean, estimate)
    err = clean - estimate
    return float(10 * np.log10(np.mean(clean**2) / (np.mean(err**2) + 1e-12)))


def stoi_score(clean: np.ndarray, estimate: np.ndarray) -> float | None:
    try:
        from pystoi import stoi
    except ModuleNotFoundError:
        return None
    clean, estimate = align(clean, estimate)
    return float(stoi(clean, estimate, SR, extended=True))


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--clean", type=Path, required=True, help="dir of clean-speech WAVs")
    ap.add_argument("--noise", type=Path, required=True, help="dir of noise WAVs")
    ap.add_argument("--snr", type=float, nargs="+", default=[0, 5, 10, 15])
    ap.add_argument("--out", type=Path, default=Path("data/eval/out"))
    ap.add_argument("--filter", default="deepfilternet",
                    choices=["deepfilternet", "null"], help="engine under test")
    args = ap.parse_args()

    from jarvis.audio.filters import DeepFilterNetFilter, NullAudioFilter

    factory = (
        (lambda: DeepFilterNetFilter(log_stats=False))
        if args.filter == "deepfilternet"
        else (lambda: NullAudioFilter())
    )

    clean_files = sorted(args.clean.glob("*.wav"))
    noise_files = sorted(args.noise.glob("*.wav"))
    if not clean_files or not noise_files:
        raise SystemExit("no WAVs found — see module docstring for expected layout")

    results = []
    for clean_path in clean_files:
        clean = read_wav(clean_path)
        for snr in args.snr:
            noise = read_wav(noise_files[hash((clean_path.name, snr)) % len(noise_files)])
            noisy = mix_at_snr(clean, noise, snr)
            enhanced, cpu = await run_filter(factory(), noisy)
            row = {
                "clean": clean_path.name,
                "snr_in_db": snr,
                "snr_out_db": round(snr_db(clean, enhanced), 2),
                "stoi": (lambda s: round(s, 3) if s is not None else None)(
                    stoi_score(clean, enhanced)
                ),
                "rtf": round(cpu / (len(noisy) / SR), 3),
            }
            results.append(row)
            print(row, flush=True)
            write_wav(args.out / f"{clean_path.stem}_snr{snr:g}_enhanced.wav", enhanced)

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "results.json").write_text(json.dumps(results, indent=2))
    print(f"\nwrote {args.out / 'results.json'} ({len(results)} rows)")


if __name__ == "__main__":
    asyncio.run(main())
