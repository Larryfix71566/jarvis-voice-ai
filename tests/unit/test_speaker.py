"""Unit tests for jarvis/speaker.py
(MORTIMER_VOICE_ISOLATION_TIER12_PLAN.md Tier 2, §5).

No torch, no network, no model files — Encoder is never constructed here.
"""

from __future__ import annotations

import numpy as np
import pytest

from jarvis import speaker


class TestKillSwitch:
    def test_kill_switch_defaults_off(self, monkeypatch):
        monkeypatch.delenv(speaker.KILL_SWITCH_ENV, raising=False)
        assert speaker.enabled() is False

    def test_kill_switch_true_enables(self, monkeypatch):
        monkeypatch.setenv(speaker.KILL_SWITCH_ENV, "true")
        assert speaker.enabled() is True

    def test_kill_switch_false_stays_off(self, monkeypatch):
        monkeypatch.setenv(speaker.KILL_SWITCH_ENV, "false")
        assert speaker.enabled() is False


class TestThreshold:
    def test_default_threshold(self, monkeypatch):
        monkeypatch.delenv(speaker.THRESHOLD_ENV, raising=False)
        assert speaker.threshold() == speaker.DEFAULT_THRESHOLD

    def test_custom_threshold(self, monkeypatch):
        monkeypatch.setenv(speaker.THRESHOLD_ENV, "0.55")
        assert speaker.threshold() == 0.55

    def test_unparseable_threshold_falls_back(self, monkeypatch):
        monkeypatch.setenv(speaker.THRESHOLD_ENV, "not-a-number")
        assert speaker.threshold() == speaker.DEFAULT_THRESHOLD


class TestVerdict:
    def test_verdict_passes_above_threshold(self, monkeypatch):
        monkeypatch.delenv(speaker.THRESHOLD_ENV, raising=False)
        assert speaker.verdict(0.9, 2.0, True) == "pass"

    def test_verdict_drops_below_threshold(self, monkeypatch):
        monkeypatch.delenv(speaker.THRESHOLD_ENV, raising=False)
        assert speaker.verdict(0.1, 2.0, True) == "drop"

    def test_short_utterance_always_passes(self, monkeypatch):
        monkeypatch.delenv(speaker.THRESHOLD_ENV, raising=False)
        assert speaker.verdict(0.0, speaker.MIN_VERIFY_SECS - 0.1, True) == "pass"

    def test_no_score_passes(self):
        assert speaker.verdict(None, 5.0, True) == "pass"

    def test_no_profile_passes(self):
        assert speaker.verdict(0.0, 5.0, False) == "pass"


class TestCosine:
    def test_identical_vectors_score_one(self):
        a = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        assert speaker.cosine(a, a) == pytest.approx(1.0)

    def test_orthogonal_vectors_score_zero(self):
        a = np.array([1.0, 0.0], dtype=np.float32)
        b = np.array([0.0, 1.0], dtype=np.float32)
        assert speaker.cosine(a, b) == pytest.approx(0.0)

    def test_zero_vector_never_raises(self):
        a = np.zeros(3, dtype=np.float32)
        b = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        assert speaker.cosine(a, b) == 0.0


class TestProfileRoundtrip:
    def test_profile_roundtrip(self, tmp_path):
        path = tmp_path / "profile.npy"
        embedding = np.array([0.1, 0.2, 0.3], dtype=np.float32)
        speaker.save_profile(embedding, path=path)
        loaded = speaker.load_profile(path=path)
        assert loaded is not None
        assert np.allclose(loaded, embedding)

    def test_missing_profile_returns_none(self, tmp_path):
        path = tmp_path / "does_not_exist.npy"
        assert speaker.load_profile(path=path) is None

    def test_corrupt_profile_returns_none_not_raise(self, tmp_path):
        path = tmp_path / "corrupt.npy"
        path.write_bytes(b"not a numpy file")
        assert speaker.load_profile(path=path) is None

    def test_metadata_roundtrip(self, tmp_path):
        path = tmp_path / "meta.json"
        meta = {"files": ["a.wav", "b.wav"], "pairwise_scores": [0.7, 0.8]}
        speaker.save_profile_metadata(meta, path=path)
        loaded = speaker.load_profile_metadata(path=path)
        assert loaded == meta


class TestEnrollRefusesSingleFile:
    def test_enroll_refuses_single_file(self, capsys):
        rc = speaker._cmd_enroll(["only_one.wav"])
        assert rc == 1
        out = capsys.readouterr().out
        assert "at least 2" in out

    def test_enroll_refuses_missing_files_before_model_load(self, capsys):
        # Missing-file check runs BEFORE any model download attempt, so a
        # typo'd path fails fast instead of after a 100MB download.
        rc = speaker._cmd_enroll(["nope_a.wav", "nope_b.wav"])
        assert rc == 1
        assert "not found" in capsys.readouterr().out


class TestEncoderLoadNeverDownloads:
    def test_load_refuses_when_model_dir_missing(self, tmp_path):
        # L2: the pipeline's load() must never download — a missing dir is
        # an immediate False, no network. (The 2026-08-21 enrollment bug
        # was the CLI calling load() and therefore never being able to
        # download; download() is the CLI-only entry point.)
        enc = speaker.Encoder(model_dir=tmp_path / "does_not_exist")
        assert enc.load() is False

    def test_download_is_a_distinct_entry_point(self):
        assert speaker.Encoder.download is not speaker.Encoder.load


# ------------------------------------------------- S10: windowed verify
# MORTIMER_SESSION_MISSES_PLAN.md S10 — `verify --windowed` scores a WAV
# with the LIVE gate's sliding windows (Gate v2 F1), so the effectiveness
# protocol can finally be run offline on data/speaker_captures/. Still no
# torch: a fake encoder returns a chosen embedding per slice.


class _ScriptedEncoder:
    """Returns a unit vector whose cosine against `profile` is the next
    scripted score. profile is [1, 0]; [s, sqrt(1-s^2)] has cosine s."""

    def __init__(self, scores):
        self._scores = list(scores)
        self.calls = 0

    def embed(self, pcm16: bytes, sample_rate: int):
        self.calls += 1
        if not self._scores:
            return None
        s = self._scores.pop(0)
        if s is None:
            return None
        return np.array([s, float(np.sqrt(max(0.0, 1.0 - s * s)))], dtype=np.float32)


def _silence(seconds: float, rate: int = 16000) -> bytes:
    return b"\x00\x00" * int(seconds * rate)


class TestWindowedScore:
    PROFILE = np.array([1.0, 0.0], dtype=np.float32)

    def test_returns_whole_then_best(self):
        """_window_slices puts the WHOLE buffer last, so the last score is
        the pre-F1 number and the max is what the live gate would use — the
        exact distinction that decides whether the gate can be turned on."""
        from jarvis.bot.speaker_gate import _window_slices

        pcm = _silence(9.0)
        n_slices = len(_window_slices(len(pcm), 16000))
        assert n_slices > 1, "a 9 s buffer must produce sub-windows plus the whole"
        scores = [0.20] * (n_slices - 2) + [0.71, 0.33]   # best mid-buffer, whole last
        enc = _ScriptedEncoder(scores)
        whole, best = speaker.windowed_score(pcm, 16000, enc, self.PROFILE)
        assert whole == pytest.approx(0.33, abs=1e-3)
        assert best == pytest.approx(0.71, abs=1e-3)
        assert enc.calls == n_slices

    def test_short_buffer_is_a_single_window(self):
        pcm = _silence(1.0)
        enc = _ScriptedEncoder([0.55])
        whole, best = speaker.windowed_score(pcm, 16000, enc, self.PROFILE)
        assert whole == pytest.approx(0.55, abs=1e-3)
        assert best == pytest.approx(0.55, abs=1e-3)
        assert enc.calls == 1

    def test_all_embeddings_failing_returns_none(self):
        enc = _ScriptedEncoder([None] * 20)
        assert speaker.windowed_score(_silence(9.0), 16000, enc, self.PROFILE) == (None, None)

    def test_a_failed_window_does_not_sink_the_others(self):
        from jarvis.bot.speaker_gate import _window_slices

        pcm = _silence(9.0)
        n = len(_window_slices(len(pcm), 16000))
        enc = _ScriptedEncoder([None] + [0.20] * (n - 3) + [0.66, 0.31])
        whole, best = speaker.windowed_score(pcm, 16000, enc, self.PROFILE)
        assert best == pytest.approx(0.66, abs=1e-3)
        assert whole == pytest.approx(0.31, abs=1e-3)


class TestVerifyCLI:
    @staticmethod
    def _wav(path, seconds=9.0, rate=16000, channels=1, width=2):
        import wave

        with wave.open(str(path), "wb") as w:
            w.setnchannels(channels)
            w.setsampwidth(width)
            w.setframerate(rate)
            w.writeframes(b"\x00" * int(seconds * rate * width * channels))
        return str(path)

    @pytest.fixture
    def cli(self, monkeypatch):
        """A profile and a downloadable encoder, without torch."""
        monkeypatch.setattr(speaker, "load_profile",
                            lambda *a, **kw: np.array([1.0, 0.0], dtype=np.float32))
        enc = _ScriptedEncoder([0.42] * 40)
        enc.download = lambda: True
        monkeypatch.setattr(speaker, "Encoder", lambda *a, **kw: enc)
        return enc

    def test_verify_windowed_flag_parses_and_reports(self, cli, tmp_path, capsys):
        path = self._wav(tmp_path / "turn.wav")
        assert speaker.main(["verify", "--windowed", path]) == 0
        out = capsys.readouterr().out
        assert "turn.wav" in out
        assert "best_window=" in out and "whole=" in out
        assert "min best_window=" in out and "threshold=" in out

    def test_verify_windowed_takes_many_files(self, cli, tmp_path, capsys):
        a = self._wav(tmp_path / "a.wav")
        b = self._wav(tmp_path / "b.wav")
        assert speaker.main(["verify", "--windowed", a, b]) == 0
        out = capsys.readouterr().out
        assert "a.wav" in out and "b.wav" in out

    def test_verify_windowed_skips_non_mono(self, cli, tmp_path, capsys):
        path = self._wav(tmp_path / "stereo.wav", channels=2)
        assert speaker.main(["verify", "--windowed", path]) == 0
        out = capsys.readouterr().out
        assert "skipped: need 16-bit mono" in out

    def test_verify_without_the_flag_keeps_the_whole_file_report(self, cli, tmp_path, capsys):
        cli.embed_file = lambda p: np.array([0.9, 0.436], dtype=np.float32)
        path = self._wav(tmp_path / "turn.wav", seconds=2.0)
        assert speaker.main(["verify", path]) == 0
        out = capsys.readouterr().out
        assert out.startswith("score=")
        assert "best_window=" not in out

    def test_verify_with_no_paths_is_a_usage_error(self, capsys):
        assert speaker.main(["verify", "--windowed"]) == 2
        assert "usage:" in capsys.readouterr().out
