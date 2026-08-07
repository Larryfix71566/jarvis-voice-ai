"""openWakeWord sidecar — local wake-word detection for "Mortimer".

Replaces the Picovoice wake word (Picovoice discontinued its free tier on
2026-06-30). Localhost-only websocket server on JARVIS_WAKEWORD_PORT
(default 7862): the web console streams 16 kHz 16-bit mono PCM, each
1280-sample chunk is scored by the openWakeWord model, and a WakeGate
decides when a wake fires; the sidecar then pushes
{"type": "wake", "model": ..., "score": ...} back down the same socket.

The bot pipeline is untouched: detection lives in this sidecar, the chime
and mic-unmute happen client-side. Fully local — no keys, no cloud.

Model: a custom "Mortimer" model is REQUIRED (openWakeWord ships none).
Train one free with openWakeWord's synthetic-data notebook
(https://github.com/dscripka/openWakeWord — "training new models") and set
JARVIS_WAKEWORD_MODEL to the .onnx (or .tflite) path.

Run:  python -m jarvis.wakeword.server   (or ./scripts/run_wakeword.sh)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

import numpy as np

from jarvis.wakeword.logic import WakeGate

logger = logging.getLogger("jarvis.wakeword")

#: openWakeWord consumes audio in fixed 80 ms frames at 16 kHz.
CHUNK_SAMPLES = 1280
CHUNK_BYTES = CHUNK_SAMPLES * 2  # 16-bit mono

DEFAULT_MODEL = "models/mortimer.onnx"


def load_model():
    """Load the custom wake-word model; exit with a clear message otherwise."""
    try:
        from openwakeword.model import Model
    except ImportError:
        sys.exit(
            "openWakeWord is not installed — run: pip install openwakeword"
        )
    model_path = os.environ.get("JARVIS_WAKEWORD_MODEL", DEFAULT_MODEL)
    if not Path(model_path).exists():
        sys.exit(
            f"Wake-word model not found: {model_path}\n"
            "Train a custom 'Mortimer' model (free, synthetic data — see the "
            "openWakeWord repo's training notebook), then set "
            "JARVIS_WAKEWORD_MODEL in .env to the .onnx/.tflite path."
        )
    framework = "tflite" if model_path.endswith(".tflite") else "onnx"
    model = Model(
        wakeword_model_paths=[model_path], inference_framework=framework
    )
    return model, Path(model_path).stem


async def handle_connection(ws, model, model_name: str, gate: WakeGate) -> None:
    """One console connection: PCM16 in, wake events out."""
    logger.info("console connected")
    buf = bytearray()
    try:
        async for message in ws:
            if isinstance(message, str):
                continue  # only binary PCM frames carry audio
            buf.extend(message)
            while len(buf) >= CHUNK_BYTES:
                chunk = np.frombuffer(bytes(buf[:CHUNK_BYTES]), dtype=np.int16)
                del buf[:CHUNK_BYTES]
                scores = model.predict(chunk)
                score = max(scores.values()) if scores else 0.0
                if gate.check(score, time.monotonic()):
                    await ws.send(
                        json.dumps(
                            {
                                "type": "wake",
                                "model": model_name,
                                "score": round(float(score), 3),
                            }
                        )
                    )
    except Exception as exc:  # connection closed / client vanished
        logger.info("console disconnected (%s)", type(exc).__name__)


async def amain() -> None:
    import websockets

    logging.basicConfig(
        level=os.environ.get("JARVIS_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    model, model_name = load_model()
    port = int(os.environ.get("JARVIS_WAKEWORD_PORT", "7862"))
    threshold = float(os.environ.get("JARVIS_WAKEWORD_THRESHOLD", "0.5"))
    cooldown = float(os.environ.get("JARVIS_WAKEWORD_COOLDOWN", "2.0"))

    async def _handler(ws, *_):
        # Per-connection gate: one console's wake never mutes another's.
        await handle_connection(ws, model, model_name, WakeGate(threshold, cooldown))

    async with websockets.serve(_handler, "127.0.0.1", port):
        logger.info(
            "wake-word sidecar listening on 127.0.0.1:%d (model=%s, "
            "threshold=%.2f, cooldown=%.1fs)",
            port, model_name, threshold, cooldown,
        )
        await asyncio.Future()  # serve forever


if __name__ == "__main__":
    asyncio.run(amain())
