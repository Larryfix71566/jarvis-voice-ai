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
