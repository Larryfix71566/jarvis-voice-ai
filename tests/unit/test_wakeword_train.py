"""Unit tests for the pure windowing/loading logic of the local trainer."""

import numpy as np
import pytest

from jarvis.wakeword.train import EMBEDDING_DIM, make_windows


def _emb(n_frames: int) -> np.ndarray:
    rng = np.random.default_rng(42)
    return rng.standard_normal((n_frames, EMBEDDING_DIM)).astype(np.float32)


def test_exact_multiple_no_padding():
    emb = _emb(32)
    wins = make_windows(emb, window=16, step=8)
    assert len(wins) == 3
    assert all(w.shape == (16, EMBEDDING_DIM) for w in wins)
    np.testing.assert_array_equal(wins[0], emb[:16])
    np.testing.assert_array_equal(wins[1], emb[8:24])


def test_step_one_window_count():
    assert len(make_windows(_emb(20), window=16, step=1)) == 5
    assert len(make_windows(_emb(20), window=16, step=4)) == 2


def test_short_clip_padded_with_last_frame():
    emb = _emb(5)
    wins = make_windows(emb, window=16, step=2)
    assert len(wins) == 1
    assert wins[0].shape == (16, EMBEDDING_DIM)
    np.testing.assert_array_equal(wins[0][:5], emb)
    # padding rows repeat the final frame
    np.testing.assert_array_equal(wins[0][5:], np.repeat(emb[-1:], 11, axis=0))


def test_single_frame_clip():
    wins = make_windows(_emb(1), window=16)
    assert len(wins) == 1


def test_rejects_wrong_shape():
    with pytest.raises(ValueError):
        make_windows(np.zeros((10, 5), dtype=np.float32))


def test_rejects_empty():
    with pytest.raises(ValueError):
        make_windows(np.zeros((0, EMBEDDING_DIM), dtype=np.float32))
