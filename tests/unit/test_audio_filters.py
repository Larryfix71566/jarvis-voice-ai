"""Unit tests for jarvis.audio.filters (voice isolation plan, Workstream A).

Run: pytest tests/unit/test_audio_filters.py
No torch/deepfilternet needed: the engine is injected via a fake.
"""

from __future__ import annotations

import numpy as np
import pytest

from pipecat.frames.frames import FilterEnableFrame, FilterUpdateSettingsFrame

from jarvis.audio.filters import (
    DeepFilterNetFilter,
    NullAudioFilter,
    build_audio_filter,
)
from jarvis.config import Settings

SR = 48000


def _settings(**overrides) -> Settings:
    base = dict(
        _env_file=None,
        openai_api_key="test",
        deepgram_api_key="test",
        elevenlabs_api_key="test",
    )
    base.update(overrides)
    return Settings(**base)


# -- fake DeepFilterNet engine (identity enhancement) -----------------------


class _FakeTensor:
    def __init__(self, arr):
        self._arr = np.asarray(arr, dtype=np.float32)

    def unsqueeze(self, dim):
        return _FakeTensor(self._arr[None, :])

    def squeeze(self, dim):
        return _FakeTensor(self._arr[0])

    def cpu(self):
        return self

    def numpy(self):
        return self._arr


class _NoGrad:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _FakeTorch:
    @staticmethod
    def from_numpy(arr):
        return _FakeTensor(arr)

    @staticmethod
    def no_grad():
        return _NoGrad()


class _FakeDfState:
    @staticmethod
    def hop_size():
        return 480


def _fake_enhance(model, df_state, audio_t, atten_lim_db=None):
    return audio_t  # identity: output == input


def _install_fake_engine(monkeypatch, filt: DeepFilterNetFilter) -> None:
    monkeypatch.setattr(
        filt,
        "_load_engine",
        lambda: (_FakeTorch, _fake_enhance, object(), _FakeDfState()),
    )


def _pcm(samples: np.ndarray) -> bytes:
    return (np.clip(samples, -1, 1) * 32767).astype(np.int16).tobytes()


def _samples(data: bytes) -> np.ndarray:
    return np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0


# -- factory -----------------------------------------------------------------


def test_factory_disabled_by_default():
    assert build_audio_filter(_settings()) is None


def test_factory_disabled_returns_none_even_with_engine():
    assert build_audio_filter(_settings(jarvis_ns_filter="deepfilternet")) is None


def test_factory_null_and_none():
    assert isinstance(
        build_audio_filter(_settings(jarvis_ns_enabled=True, jarvis_ns_filter="null")),
        NullAudioFilter,
    )
    assert (
        build_audio_filter(_settings(jarvis_ns_enabled=True, jarvis_ns_filter="none"))
        is None
    )


def test_factory_deepfilternet_carries_settings():
    filt = build_audio_filter(
        _settings(
            jarvis_ns_enabled=True,
            jarvis_ns_filter="deepfilternet",
            jarvis_ns_atten_lim_db=12.0,
        )
    )
    assert isinstance(filt, DeepFilterNetFilter)
    assert filt._atten_lim_db == 12.0


def test_factory_rnnoise():
    from pipecat.audio.filters.rnnoise_filter import RNNoiseFilter

    filt = build_audio_filter(
        _settings(jarvis_ns_enabled=True, jarvis_ns_filter="rnnoise")
    )
    assert isinstance(filt, RNNoiseFilter)


def test_factory_unknown_engine_disables():
    assert (
        build_audio_filter(_settings(jarvis_ns_enabled=True, jarvis_ns_filter="bogus"))
        is None
    )


def test_settings_env_parsing(monkeypatch):
    monkeypatch.setenv("JARVIS_NS_ENABLED", "true")
    monkeypatch.setenv("JARVIS_NS_ATTEN_LIM_DB", "9.5")
    s = _settings()
    assert s.jarvis_ns_enabled is True
    assert s.jarvis_ns_atten_lim_db == 9.5


# -- NullAudioFilter (V1d seam) ----------------------------------------------


async def test_null_filter_passthrough():
    filt = NullAudioFilter()
    await filt.start(SR)
    audio = _pcm(np.full(480, 0.25, dtype=np.float32))
    assert await filt.filter(audio) == audio
    await filt.stop()


# -- DeepFilterNetFilter ------------------------------------------------------


async def test_engine_missing_degrades_to_passthrough(monkeypatch):
    filt = DeepFilterNetFilter(log_stats=False)

    def _boom():
        raise ImportError("No module named 'df'")

    monkeypatch.setattr(filt, "_load_engine", _boom)
    await filt.start(SR)
    audio = _pcm(np.full(480, 0.25, dtype=np.float32))
    assert await filt.filter(audio) == audio  # unchanged, session survives


async def test_buffers_until_one_full_block(monkeypatch):
    filt = DeepFilterNetFilter(log_stats=False)
    _install_fake_engine(monkeypatch, filt)
    await filt.start(SR)
    assert filt._block == 1440  # 30 ms rounded to hops of 480

    chunk = _pcm(np.full(480, 0.5, dtype=np.float32))
    assert await filt.filter(chunk) == b""  # 480 < block: still buffering
    assert await filt.filter(chunk) == b""
    out = await filt.filter(chunk)  # 1440 samples total -> one block
    # identity enhance + crossfade hold-back: block - xfade samples emitted
    assert len(_samples(out)) == filt._block - filt._xfade
    np.testing.assert_allclose(
        _samples(out), np.full(len(_samples(out)), 0.5, dtype=np.float32),
        atol=2 / 32768,
    )


async def test_two_blocks_constant_signal_is_transparent(monkeypatch):
    filt = DeepFilterNetFilter(log_stats=False)
    _install_fake_engine(monkeypatch, filt)
    await filt.start(SR)
    block = _pcm(np.full(filt._block, 0.5, dtype=np.float32))
    out1 = _samples(await filt.filter(block))
    out2 = _samples(await filt.filter(block))
    combined = np.concatenate([out1, out2])
    assert len(combined) == 2 * (filt._block - filt._xfade)
    # identity engine + crossfade => output equals input (crossfade region too)
    np.testing.assert_allclose(
        combined, np.full(len(combined), 0.5, dtype=np.float32), atol=2 / 32768
    )


async def test_enable_frame_is_runtime_kill_switch(monkeypatch):
    filt = DeepFilterNetFilter(log_stats=False)
    _install_fake_engine(monkeypatch, filt)
    await filt.start(SR)

    await filt.process_frame(FilterEnableFrame(enable=False))
    audio = _pcm(np.full(480, 0.5, dtype=np.float32))
    assert await filt.filter(audio) == audio  # bypassed

    await filt.process_frame(FilterEnableFrame(enable=True))
    assert await filt.filter(audio) == b""  # filtering again -> buffering
    await filt.stop()


async def test_update_settings_sets_atten_lim(monkeypatch):
    filt = DeepFilterNetFilter(log_stats=False)
    _install_fake_engine(monkeypatch, filt)
    await filt.start(SR)
    await filt.process_frame(FilterUpdateSettingsFrame(settings={"atten_lim_db": 6}))
    assert filt._atten_lim_db == 6.0
    await filt.stop()
