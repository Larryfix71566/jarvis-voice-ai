"""Local wake-word model trainer for Mortimer (no notebook required).

Trains a small classifier on top of openWakeWord's frozen speech-embedding
model, using WAV clips you generate locally (see
``scripts/wakeword_gen_samples_mac.sh``). The exported ``.onnx`` file loads
directly into the existing sidecar (``jarvis/wakeword/server.py``).

Data layout (created by the sample generator):

    data/wakeword/positive/*.wav   # clips of the wake phrase ("Mortimer")
    data/wakeword/negative/*.wav   # similar words + other speech

Usage (inside the project venv):

    uv pip install torch --index-url https://download.pytorch.org/whl/cpu
    uv pip install onnx onnxscript
    python -m jarvis.wakeword.train --data-dir data/wakeword --out models/mortimer.onnx

Training is fully local: audio never leaves the machine.
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

import numpy as np

SAMPLE_RATE = 16000
WINDOW_FRAMES = 16          # classifier input: 16 embedding frames x 96 dims
WINDOW_STEP = 2             # stride between windows within one clip
EMBEDDING_DIM = 96
#: openWakeWord's embedding model needs a 76-frame mel window (76 x 160
#: samples); shorter clips crash its batch path, so skip them up front.
MIN_CLIP_SAMPLES = 76 * 160 + 1


def make_windows(embeddings: np.ndarray, window: int = WINDOW_FRAMES,
                 step: int = WINDOW_STEP) -> list[np.ndarray]:
    """Slice (n_frames, EMBEDDING_DIM) embeddings into fixed-size windows.

    Clips shorter than ``window`` frames are padded by repeating the final
    frame so every clip yields at least one window.
    """
    embeddings = np.asarray(embeddings, dtype=np.float32)
    if embeddings.ndim == 1:  # single-frame batch squeezed by openwakeword
        embeddings = embeddings[None, :]
    if embeddings.ndim != 2 or embeddings.shape[1] != EMBEDDING_DIM:
        raise ValueError(
            f"expected (n_frames, {EMBEDDING_DIM}) embeddings, got {embeddings.shape}")
    if embeddings.shape[0] == 0:
        raise ValueError("no embedding frames — clip is too short or silent")
    if embeddings.shape[0] < window:
        pad = np.repeat(embeddings[-1:], window - embeddings.shape[0], axis=0)
        embeddings = np.vstack([embeddings, pad])
    return [embeddings[i:i + window]
            for i in range(0, embeddings.shape[0] - window + 1, step)]


def load_wav(path: Path) -> np.ndarray:
    """Read a WAV file as int16 mono 16 kHz PCM."""
    from scipy.io import wavfile

    sr, data = wavfile.read(path)
    if sr != SAMPLE_RATE:
        raise ValueError(f"{path}: expected {SAMPLE_RATE} Hz, got {sr}")
    if data.ndim == 2:  # stereo -> mono
        data = data.mean(axis=1)
    if data.dtype == np.float32 or data.dtype == np.float64:
        data = np.clip(data, -1.0, 1.0)
        data = (data * 32767).astype(np.int16)
    elif data.dtype != np.int16:
        data = data.astype(np.int16)
    return data


def _augment(clip: np.ndarray, rng: random.Random) -> list[np.ndarray]:
    """Gain jitter + light noise to multiply sample diversity cheaply."""
    variants = []
    for _ in range(2):
        gain = rng.uniform(0.6, 1.4)
        noise = rng.uniform(0.0, 0.01) * 32767
        x = clip.astype(np.float64) * gain
        x = x + np.random.default_rng(rng.randrange(1 << 30)).standard_normal(len(x)) * noise
        variants.append(np.clip(x, -32768, 32767).astype(np.int16))
    return variants


def _embed_clip(audio_features, clip: np.ndarray) -> np.ndarray | None:
    """Embeddings for one clip, or None if it can't be embedded.

    Returns None for clips shorter than the embedding window and for any
    clip the feature models reject — one bad take must not abort a run.
    """
    if len(clip) < MIN_CLIP_SAMPLES:
        return None
    try:
        emb = audio_features._get_embeddings(clip)
    except Exception:
        return None
    if emb.size == 0:
        return None
    return np.atleast_2d(emb)  # single-frame output arrives squeezed to (96,)


def _clip_embeddings(audio_features, clips: list[np.ndarray]) -> np.ndarray:
    windows = []
    skipped = 0
    for clip in clips:
        emb = _embed_clip(audio_features, clip)
        if emb is None:
            skipped += 1  # clip too short or rejected by the feature models
            continue
        windows.extend(make_windows(emb))
    if skipped:
        print(f"  note: skipped {skipped} clip(s) too short for embeddings")
    return np.stack(windows).astype(np.float32)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", default="data/wakeword",
                        help="folder containing positive/ and negative/ WAV dirs")
    parser.add_argument("--out", default="models/mortimer.onnx",
                        help="output ONNX model path")
    parser.add_argument("--epochs", type=int, default=60)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)

    data_dir = Path(args.data_dir)
    pos_dir, neg_dir = data_dir / "positive", data_dir / "negative"
    if not pos_dir.is_dir() or not neg_dir.is_dir():
        print(f"error: expected {pos_dir}/ and {neg_dir}/ — "
              "run scripts/wakeword_gen_samples_mac.sh first", file=sys.stderr)
        return 1

    pos_paths = sorted(pos_dir.glob("*.wav"))
    neg_paths = sorted(neg_dir.glob("*.wav"))
    if len(pos_paths) < 20 or len(neg_paths) < 20:
        print(f"error: need >= 20 clips per class (found {len(pos_paths)} positive, "
              f"{len(neg_paths)} negative)", file=sys.stderr)
        return 1

    try:
        import torch
        import torch.nn as nn
    except ImportError:
        print("error: torch is required for training (inference does not need it).\n"
              "  uv pip install torch --index-url https://download.pytorch.org/whl/cpu",
              file=sys.stderr)
        return 1

    from openwakeword.utils import AudioFeatures
    from jarvis.wakeword.server import ensure_feature_models

    rng = random.Random(args.seed)
    torch.manual_seed(args.seed)

    # Split by clip (not window) so augmented copies can't leak across folds.
    rng.shuffle(pos_paths)
    rng.shuffle(neg_paths)
    n_pos_val = max(1, len(pos_paths) // 5)
    n_neg_val = max(1, len(neg_paths) // 5)
    val_paths = pos_paths[:n_pos_val] + neg_paths[:n_neg_val]
    val_labels = [1] * n_pos_val + [0] * n_neg_val

    print(f"loading {len(pos_paths)} positive + {len(neg_paths)} negative clips ...")
    pos_train = [load_wav(p) for p in pos_paths[n_pos_val:]]
    neg_train = [load_wav(p) for p in neg_paths[n_neg_val:]]
    val_clips = [load_wav(p) for p in val_paths]

    # Cheap augmentation on the training split only.
    pos_aug = pos_train + [v for c in pos_train for v in _augment(c, rng)]
    neg_aug = neg_train + [v for c in neg_train for v in _augment(c, rng)]

    print("extracting embeddings (openWakeWord AudioFeatures, local ONNX) ...")
    ensure_feature_models()  # one-time download of the shared ONNX feature models
    audio_features = AudioFeatures(inference_framework="onnx")
    X_pos = _clip_embeddings(audio_features, pos_aug)
    X_neg = _clip_embeddings(audio_features, neg_aug)
    X_val = _clip_embeddings(audio_features, val_clips)

    X = np.vstack([X_pos, X_neg])
    y = np.array([1.0] * len(X_pos) + [0.0] * len(X_neg), dtype=np.float32)
    perm = np.random.default_rng(args.seed).permutation(len(X))
    X, y = X[perm], y[perm]
    print(f"training set: {len(X)} windows ({len(X_pos)} wake, {len(X_neg)} other)")

    model = nn.Sequential(
        nn.Flatten(),
        nn.Linear(WINDOW_FRAMES * EMBEDDING_DIM, 128), nn.ReLU(), nn.Dropout(0.2),
        nn.Linear(128, 32), nn.ReLU(),
        nn.Linear(32, 1), nn.Sigmoid(),
    )
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    loss_fn = nn.BCELoss()
    Xt, yt = torch.from_numpy(X), torch.from_numpy(y).unsqueeze(1)

    model.train()
    for epoch in range(args.epochs):
        order = torch.randperm(len(Xt))
        total = 0.0
        for i in range(0, len(Xt), 64):
            idx = order[i:i + 64]
            opt.zero_grad()
            loss = loss_fn(model(Xt[idx]), yt[idx])
            loss.backward()
            opt.step()
            total += loss.item() * len(idx)
        if (epoch + 1) % 10 == 0:
            print(f"  epoch {epoch + 1}/{args.epochs}  loss {total / len(Xt):.4f}")

    # Held-out report (mean score per clip over its windows). Clips too
    # short to embed are excluded from the stats, not scored as negatives.
    model.eval()
    with torch.no_grad():
        scores = model(torch.from_numpy(X_val)).squeeze(1).numpy()
    per_clip, per_label, cursor = [], [], 0
    for clip, label in zip(val_clips, val_labels):
        emb = _embed_clip(audio_features, clip)
        if emb is None:
            continue
        n = len(make_windows(emb))
        per_clip.append(float(scores[cursor:cursor + n].mean()))
        per_label.append(label)
        cursor += n
    pos_scores = [s for s, l in zip(per_clip, per_label) if l == 1]
    neg_scores = [s for s, l in zip(per_clip, per_label) if l == 0]
    print(f"held-out ({len(per_clip)} scorable clips):")
    print(f"  wake clips   — min {min(pos_scores):.3f}  "
          f"p25 {np.percentile(pos_scores, 25):.3f}  mean {np.mean(pos_scores):.3f}")
    print(f"  other clips  — max {max(neg_scores):.3f}  "
          f"p95 {np.percentile(neg_scores, 95):.3f}  mean {np.mean(neg_scores):.3f}")
    # Suggested threshold: midpoint between the low quartile of wake scores
    # and the 95th percentile of other-speech scores — robust to outliers.
    threshold = float((np.percentile(pos_scores, 25)
                       + np.percentile(neg_scores, 95)) / 2)
    threshold = min(max(threshold, 0.05), 0.95)
    print(f"  suggested JARVIS_WAKEWORD_THRESHOLD={threshold:.2f}")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        torch.onnx.export(model, torch.zeros(1, WINDOW_FRAMES, EMBEDDING_DIM),
                          str(out_path), input_names=["input"],
                          output_names=["output"], opset_version=13)
    except ModuleNotFoundError as exc:
        print(f"error: ONNX export needs an extra package ({exc.name}).\n"
              "  uv pip install onnx onnxscript   # then re-run this command",
              file=sys.stderr)
        return 1
    print(f"saved {out_path}")

    # Sanity check: load through the exact path the sidecar uses.
    from openwakeword.model import Model
    probe = Model(wakeword_models=[str(out_path)], inference_framework="onnx")
    print(f"sidecar load OK — input shape {probe.model_inputs}, "
          f"model name '{out_path.stem}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
