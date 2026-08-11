"""Server-side input audio filters (voice isolation plan, Workstream A).

`TransportParams.audio_in_filter` is the pluggable pipeline seam (plan §3.2,
prep task V1d): `DeepFilterNetFilter` is the Workstream-A neural suppressor,
`NullAudioFilter` is a no-op proving the seam, and the deferred Workstream-V
voice gate will attach behind the same `BaseAudioFilter` interface later.

Everything is OFF unless `JARVIS_NS_ENABLED=true` (feature flag + kill
switch, plan task A2 step 3). Engines are optional dependencies:

    pip install deepfilternet   # DeepFilterNet 3 (best quality; pulls torch)
    pip install pyrnnoise       # RNNoise (lighter; plan A0 fallback)

Engines are imported lazily inside start(); a missing engine degrades to
pass-through with an error log instead of breaking sessions (plan A3 spirit:
the pipeline must never be worse than the baseline because a filter failed).
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import numpy as np
from loguru import logger

from pipecat.audio.filters.base_audio_filter import BaseAudioFilter
from pipecat.frames.frames import (
    FilterControlFrame,
    FilterEnableFrame,
    FilterUpdateSettingsFrame,
)

if TYPE_CHECKING:
    from jarvis.config import Settings


class DeepFilterNetFilter(BaseAudioFilter):
    """DeepFilterNet 3 neural noise suppression (plan A2, recommended engine).

    Blockwise streaming wrapper around `df.enhance.enhance`: input is
    accumulated into fixed blocks (default 30 ms), each block is enhanced,
    and block edges are smoothed with a short linear crossfade (default
    10 ms) held back one block. Added latency ~= block_ms + STFT delay
    (~10 ms) ~= 40 ms — the plan §3.4 budget. Block size and crossfade are
    Phase-2 tuning knobs (⚙ in the plan).

    Note: this uses the Python `deepfilternet` package blockwise, not the
    Rust streaming core; the eval harness (scripts/eval_ns.py) is the tool
    for checking boundary artifacts and RTF on production hardware before
    rollout.
    """

    ENGINE_SR = 48000  # DeepFilterNet always runs at 48 kHz

    def __init__(
        self,
        *,
        atten_lim_db: float | None = None,
        post_filter: bool = False,
        block_ms: float = 30.0,
        xfade_ms: float = 10.0,
        log_stats: bool = True,
        stats_interval_s: float = 30.0,
    ) -> None:
        self._atten_lim_db = atten_lim_db
        self._post_filter = post_filter
        self._block_ms = block_ms
        self._xfade_ms = xfade_ms
        self._log_stats = log_stats
        self._stats_interval_s = stats_interval_s

        self._filtering = True
        self._ready = False
        self._sample_rate = 0

        self._torch = None
        self._model = None
        self._df_state = None
        self._enhance_fn = None
        self._block = 0
        self._xfade = 0
        self._resampler_in = None
        self._resampler_out = None

        self._buf = np.zeros(0, dtype=np.float32)  # 48 kHz float domain
        self._tail: np.ndarray | None = None  # held-back crossfade samples

        # Telemetry (plan A2 step 4 / V1a): RTF + volume, [ns] log lines.
        self._blocks = 0
        self._audio_s = 0.0
        self._cpu_s = 0.0
        self._last_stats_t = time.monotonic()

    # -- engine loading (isolated so tests can inject a fake engine) -------

    def _load_engine(self):
        """Import torch/deepfilternet and load DeepFilterNet 3.

        Returns (torch_module, enhance_fn, model, df_state). Raises on any
        failure; the caller degrades to pass-through.
        """
        import torch  # noqa: PLC0415 - intentional lazy optional import
        from df.enhance import enhance, init_df  # noqa: PLC0415

        model, df_state, _ = init_df(
            post_filter=self._post_filter,
            log_level="WARNING",
            log_file=None,
        )
        return torch, enhance, model, df_state

    # -- BaseAudioFilter interface -----------------------------------------

    async def start(self, sample_rate: int):
        self._sample_rate = sample_rate
        try:
            self._torch, self._enhance_fn, self._model, self._df_state = (
                self._load_engine()
            )
        except Exception as e:  # noqa: BLE001 - any engine failure = passthrough
            logger.error(
                f"[ns] DeepFilterNet unavailable, noise suppression OFF "
                f"(audio passes through unchanged): {e}. "
                f"Install with: pip install deepfilternet"
            )
            return

        hop = self._df_state.hop_size()
        # Block = block_ms rounded UP to a whole number of hops, at least
        # n_fft (2 hops at 50% overlap) so the STFT has a full window.
        raw = int(self.ENGINE_SR * self._block_ms / 1000)
        self._block = max(2 * hop, ((raw + hop - 1) // hop) * hop)
        self._xfade = min(int(self.ENGINE_SR * self._xfade_ms / 1000), self._block // 4)

        if sample_rate != self.ENGINE_SR:
            try:
                from pipecat.audio.resamplers.soxr_stream_resampler import (  # noqa: PLC0415
                    SOXRStreamAudioResampler,
                )

                self._resampler_in = SOXRStreamAudioResampler(quality="QQ")
                self._resampler_out = SOXRStreamAudioResampler(quality="QQ")
            except Exception as e:  # noqa: BLE001
                logger.error(
                    f"[ns] cannot resample {sample_rate}<->{self.ENGINE_SR}: {e}; "
                    f"noise suppression OFF"
                )
                return

        self._ready = True
        logger.info(
            f"[ns] DeepFilterNet3 active: in={sample_rate} Hz, "
            f"block={self._block} ({self._block / self.ENGINE_SR * 1000:.0f} ms), "
            f"xfade={self._xfade}, atten_lim_db={self._atten_lim_db}, "
            f"post_filter={self._post_filter}"
        )

    async def stop(self):
        if self._log_stats and self._blocks:
            rtf = self._cpu_s / self._audio_s if self._audio_s else 0.0
            logger.info(
                f"[ns] session summary: audio={self._audio_s:.1f}s "
                f"cpu={self._cpu_s:.1f}s rtf={rtf:.3f} blocks={self._blocks}"
            )
        self._model = None
        self._df_state = None
        self._ready = False
        self._buf = np.zeros(0, dtype=np.float32)
        self._tail = None

    async def process_frame(self, frame: FilterControlFrame):
        if isinstance(frame, FilterEnableFrame):
            # Runtime kill switch (plan A2 step 3).
            self._filtering = frame.enable
            logger.info(f"[ns] filtering {'enabled' if frame.enable else 'disabled'}")
        elif isinstance(frame, FilterUpdateSettingsFrame):
            # Plan A3 strength knob, runtime-tunable during Phase 2.
            atten = frame.settings.get("atten_lim_db")
            if atten is not None:
                self._atten_lim_db = float(atten)
                logger.info(f"[ns] atten_lim_db -> {self._atten_lim_db}")

    async def filter(self, audio: bytes) -> bytes:
        if not self._ready or not self._filtering:
            return audio

        if self._resampler_in is not None:
            audio = await self._resampler_in.resample(
                audio, self._sample_rate, self.ENGINE_SR
            )
        if not audio:
            return b""

        samples = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0
        self._buf = np.concatenate([self._buf, samples])

        out: list[np.ndarray] = []
        while len(self._buf) >= self._block:
            block = self._buf[: self._block]
            self._buf = self._buf[self._block :]
            enhanced = self._enhance_block(block)
            out.append(self._crossfade(enhanced))

        self._maybe_log_stats()
        if not out:
            return b""  # buffering; transport skips empty frames

        pcm = (np.clip(np.concatenate(out), -1.0, 1.0) * 32767).astype(np.int16)
        result = pcm.tobytes()
        if self._resampler_out is not None:
            result = await self._resampler_out.resample(
                result, self.ENGINE_SR, self._sample_rate
            )
        return result

    # -- internals ----------------------------------------------------------

    def _enhance_block(self, block: np.ndarray) -> np.ndarray:
        t0 = time.perf_counter()
        audio_t = self._torch.from_numpy(block).unsqueeze(0)
        with self._torch.no_grad():
            enhanced = self._enhance_fn(
                self._model, self._df_state, audio_t,
                atten_lim_db=self._atten_lim_db,
            )
        self._cpu_s += time.perf_counter() - t0
        self._blocks += 1
        self._audio_s += len(block) / self.ENGINE_SR
        # pad=True => same length as input; slice defensively.
        return enhanced.squeeze(0).cpu().numpy()[: len(block)].astype(np.float32)

    def _crossfade(self, enhanced: np.ndarray) -> np.ndarray:
        """Blend block edges; holds back the last `xfade` samples (one-xfade
        constant delay, flushed on session end — negligible)."""
        if self._xfade <= 0:
            return enhanced
        head = enhanced[: self._xfade]
        if self._tail is not None:
            n = len(self._tail)
            w = np.arange(1, n + 1, dtype=np.float32) / (n + 1)
            head = self._tail * (1 - w) + enhanced[:n] * w
        self._tail = enhanced[-self._xfade :]
        return np.concatenate([head, enhanced[self._xfade : -self._xfade]])

    def _maybe_log_stats(self):
        if not self._log_stats:
            return
        now = time.monotonic()
        if now - self._last_stats_t >= self._stats_interval_s and self._audio_s:
            self._last_stats_t = now
            logger.info(
                f"[ns] stats: audio={self._audio_s:.0f}s cpu={self._cpu_s:.1f}s "
                f"rtf={self._cpu_s / self._audio_s:.3f} blocks={self._blocks}"
            )


class NullAudioFilter(BaseAudioFilter):
    """No-op pass-through (plan prep task V1d): proves the audio_in_filter
    seam accepts a stage that can be inserted and removed behind a flag
    without touching capture, transport, or STT."""

    def __init__(self) -> None:
        self._filtering = True

    async def start(self, sample_rate: int):
        logger.info(f"[ns] NullAudioFilter active (pass-through) at {sample_rate} Hz")

    async def stop(self):
        pass

    async def process_frame(self, frame: FilterControlFrame):
        if isinstance(frame, FilterEnableFrame):
            self._filtering = frame.enable

    async def filter(self, audio: bytes) -> bytes:
        return audio


def build_audio_filter(settings: "Settings") -> BaseAudioFilter | None:
    """Factory (plan A0 decision rule + A2 kill switch).

    Returns None when noise suppression is disabled — TransportParams then
    behaves exactly as before this change. Engine selection via
    JARVIS_NS_FILTER: deepfilternet | rnnoise | null | none.
    """
    if not settings.jarvis_ns_enabled:
        return None

    kind = settings.jarvis_ns_filter.strip().lower()
    if kind in ("none", "off"):
        return None
    if kind == "null":
        return NullAudioFilter()
    if kind == "deepfilternet":
        return DeepFilterNetFilter(
            atten_lim_db=settings.jarvis_ns_atten_lim_db,
            post_filter=settings.jarvis_ns_post_filter,
            log_stats=settings.jarvis_ns_log_stats,
        )
    if kind == "rnnoise":
        # Plan A0 lightweight fallback; reuses pipecat's built-in filter
        # (requires: pip install pyrnnoise).
        from pipecat.audio.filters.rnnoise_filter import RNNoiseFilter  # noqa: PLC0415

        return RNNoiseFilter()

    logger.warning(
        f"[ns] unknown JARVIS_NS_FILTER={settings.jarvis_ns_filter!r}; "
        f"noise suppression disabled"
    )
    return None
