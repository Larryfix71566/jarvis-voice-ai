"""Local speaker-verification gate — policy, profile storage, and CLI.
MORTIMER_VOICE_ISOLATION_TIER12_PLAN.md Tier 2 (§4.1/§4.2).

WHAT THIS IS
------------
A convenience filter, not security: it drops transcripts that don't sound
like the enrolled voice, so the TV or a houseguest doesn't get answered.
A recording of the enrolled voice defeats it trivially, and that is stated
here rather than hidden — see L5 below.

FAIL-OPEN EVERYWHERE (L5)
-------------------------
An utterance PASSES (is never gated) when ANY of the following holds:
  - the cosine score is >= threshold,
  - the accumulated speech is shorter than MIN_VERIFY_SECS (too little
    voiceprint to judge — "yes"/"confirm" must never be silently eaten),
  - no profile has been enrolled yet,
  - the embedding model isn't on disk,
  - anything anywhere in the gate raised an exception.
Silently eating the user's own "yes" is the worst failure this feature can
have, which is why every ambiguous case resolves to "pass", never "drop".

LOGIC / IO SPLIT
----------------
Everything in this module down to `Encoder` is plain numpy/stdlib and is
exercised by tests/unit/test_speaker.py with no torch, no network, and no
model files — `Encoder` itself is the one class that touches torch/
speechbrain, and it is never constructed by unit tests. The pipeline
wiring (jarvis/bot/speaker_gate.py) is a second, thin layer on top.

KILL SWITCH (L8)
----------------
`JARVIS_SPEAKER_GATE_ENABLED` — unlike every other kill switch in this
repo, this one defaults FALSE. The feature is opt-in until Larry has run
the effectiveness protocol (plan §6) and confirmed it actually helps.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# --- Tunables (plan §4.1) ---------------------------------------------------

MIN_VERIFY_SECS = 1.0
GATE_HOLD_TIMEOUT_S = 0.6
DEFAULT_THRESHOLD = 0.40
THRESHOLD_ENV = "JARVIS_SPEAKER_THRESHOLD"
KILL_SWITCH_ENV = "JARVIS_SPEAKER_GATE_ENABLED"

MODEL_DIR = Path("data/models/ecapa")
PROFILE_JSON = Path("data/speaker_profile.json")
PROFILE_NPY = Path("data/speaker_profile.npy")

_SPEECHBRAIN_SOURCE = "speechbrain/spkrec-ecapa-voxceleb"


def enabled() -> bool:
    """Single enforcement point for the kill switch. Defaults to False
    (L8) — the opposite of every other switch in this repo, because this
    feature is opt-in until Larry has run the plan's effectiveness
    protocol, not something that ships on by default and gets disabled on
    trouble."""
    value = os.environ.get(KILL_SWITCH_ENV)
    if value is None:
        return False
    return value.strip().lower() in ("true", "1", "yes")


def threshold() -> float:
    """Read once per call — cheap, and lets a live .env edit + restart
    change it without touching code."""
    value = os.environ.get(THRESHOLD_ENV)
    if not value:
        return DEFAULT_THRESHOLD
    try:
        return float(value)
    except ValueError:
        logger.warning("speaker_threshold_unparseable value=%r — using default", value)
        return DEFAULT_THRESHOLD


def verdict(score: float | None, speech_secs: float, profile_loaded: bool) -> str:
    """Pure policy (L5). Returns "pass" or "drop". Every ambiguous or
    not-yet-known case resolves to "pass" — see module docstring."""
    if not profile_loaded:
        return "pass"
    if speech_secs < MIN_VERIFY_SECS:
        return "pass"
    if score is None:
        return "pass"
    if score >= threshold():
        return "pass"
    return "drop"


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    """Plain numpy cosine similarity. Returns 0.0 (never raises) if either
    vector has zero norm — degenerate input should read as "no match", not
    crash the caller."""
    a = np.asarray(a, dtype=np.float32).reshape(-1)
    b = np.asarray(b, dtype=np.float32).reshape(-1)
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0.0:
        return 0.0
    return float(np.dot(a, b) / denom)


def load_profile(path: Path = PROFILE_NPY) -> np.ndarray | None:
    """None on any failure (missing file, corrupt array) — logged once,
    never raised. A missing profile means the gate stays inert (L5)."""
    try:
        if not path.exists():
            return None
        arr = np.load(path)
        return np.asarray(arr, dtype=np.float32)
    except Exception:
        logger.warning("speaker_profile_load_failed path=%s", path, exc_info=True)
        return None


def save_profile(embedding: np.ndarray, path: Path = PROFILE_NPY) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(path, np.asarray(embedding, dtype=np.float32))


def save_profile_metadata(metadata: dict[str, Any], path: Path = PROFILE_JSON) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metadata, indent=2))


def load_profile_metadata(path: Path = PROFILE_JSON) -> dict[str, Any] | None:
    try:
        if not path.exists():
            return None
        return json.loads(path.read_text())
    except Exception:
        logger.warning("speaker_profile_metadata_load_failed path=%s", path, exc_info=True)
        return None


# --- Encoder (the one class that touches torch/speechbrain) ----------------


class Encoder:
    """Lazy torch/speechbrain wrapper. Constructed cheaply; `.load()` does
    the actual (possibly slow, possibly failing) model load and NEVER
    downloads — a fresh checkout with no model on disk boots with the gate
    inert rather than reaching out to the network at boot (L2)."""

    def __init__(self, model_dir: Path = MODEL_DIR) -> None:
        self.model_dir = model_dir
        self._model: Any = None

    def load(self) -> bool:
        """Load from disk ONLY — never downloads. The bot pipeline calls
        this at build time; a fresh checkout must boot with the gate inert
        rather than reaching out to the network (L2)."""
        if self._model is not None:
            return True
        if not self.model_dir.exists():
            logger.info("speaker_gate_inactive reason=model_dir_missing dir=%s", self.model_dir)
            return False
        return self._from_hparams()

    def download(self) -> bool:
        """Download (or reuse) the model — the ONE place download happens
        (L2). Called ONLY by the enrollment CLI, never by the pipeline."""
        if self._model is not None:
            return True
        self.model_dir.mkdir(parents=True, exist_ok=True)
        return self._from_hparams()

    def _from_hparams(self) -> bool:
        try:
            try:
                from speechbrain.inference.speaker import EncoderClassifier
            except ImportError:
                from speechbrain.pretrained import EncoderClassifier  # type: ignore
            self._model = EncoderClassifier.from_hparams(
                source=_SPEECHBRAIN_SOURCE,
                savedir=str(self.model_dir),
            )
            return True
        except Exception:
            logger.warning("speaker_gate_inactive reason=model_load_failed", exc_info=True)
            self._model = None
            return False

    def embed(self, pcm16: bytes, sample_rate: int) -> np.ndarray | None:
        """mono int16 PCM bytes -> float32 tensor -> ECAPA embedding.
        None + a log line on any exception (L5 — the caller treats a
        missing embedding as "pass")."""
        if self._model is None:
            return None
        try:
            import torch

            samples = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768.0
            waveform = torch.from_numpy(samples).unsqueeze(0)
            if sample_rate != 16000:
                import torchaudio

                waveform = torchaudio.functional.resample(waveform, sample_rate, 16000)
            with torch.no_grad():
                embedding = self._model.encode_batch(waveform)
            return embedding.squeeze().detach().cpu().numpy().astype(np.float32)
        except Exception:
            logger.warning("speaker_gate_embed_failed", exc_info=True)
            return None

    def embed_file(self, wav_path: Path) -> np.ndarray | None:
        """Convenience for the CLI: read a WAV file (soundfile) and embed
        it. Same None-on-any-failure discipline as `embed`."""
        if self._model is None:
            return None
        try:
            import soundfile as sf

            data, sample_rate = sf.read(str(wav_path), dtype="int16")
            if data.ndim > 1:
                data = data[:, 0]
            return self.embed(data.tobytes(), sample_rate)
        except Exception:
            logger.warning("speaker_gate_embed_file_failed path=%s", wav_path, exc_info=True)
            return None


# --- CLI (plan §4.2) --------------------------------------------------------


def _cmd_enroll(wav_paths: list[str]) -> int:
    if len(wav_paths) < 2:
        print("enroll requires at least 2 WAV files (got "
              f"{len(wav_paths)}) — record a few short samples and pass "
              "them all so the profile isn't overfit to one clip.")
        return 1

    missing = [p for p in wav_paths if not Path(p).exists()]
    if missing:
        print(f"File(s) not found: {', '.join(missing)}")
        return 1

    encoder = Encoder()
    print(f"Loading model into {MODEL_DIR} (downloads on first run)...")
    # download(), not load(): the CLI is the ONE place download is allowed.
    if not encoder.download():
        print("Could not load/download the speaker model — check network "
              "and that speechbrain is installed.")
        return 1

    embeddings = []
    for p in wav_paths:
        path = Path(p)
        emb = encoder.embed_file(path)
        if emb is None:
            print(f"Failed to embed {p} — skipping.")
            continue
        embeddings.append((p, emb))

    if len(embeddings) < 2:
        print("Fewer than 2 files embedded successfully — cannot enroll.")
        return 1

    mean_embedding = np.mean(np.stack([e for _, e in embeddings]), axis=0)
    pairwise_scores = [
        round(cosine(e, mean_embedding), 4) for _, e in embeddings
    ]

    save_profile(mean_embedding)
    save_profile_metadata({
        "files": [p for p, _ in embeddings],
        "pairwise_scores": pairwise_scores,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    lo, hi = min(pairwise_scores), max(pairwise_scores)
    print(
        f"Enrolled from {len(embeddings)} file(s). Your own samples score "
        f"{lo:.2f}-{hi:.2f} against your profile; the {threshold():.2f} "
        "threshold has "
        + ("plenty of" if lo - threshold() > 0.15 else "some")
        + " margin below your lowest self-score."
    )
    return 0


def _cmd_verify(wav_path: str) -> int:
    profile = load_profile()
    if profile is None:
        print("No profile enrolled yet — run `enroll` first.")
        return 1
    encoder = Encoder()
    # verify may also download: it's an offline CLI tool, same trust level
    # as enroll — only the PIPELINE is forbidden from downloading.
    if not encoder.download():
        print("Could not load/download the speaker model — check network "
              "and that speechbrain is installed.")
        return 1
    emb = encoder.embed_file(Path(wav_path))
    if emb is None:
        print(f"Failed to embed {wav_path}.")
        return 1
    score = cosine(emb, profile)
    v = verdict(score, MIN_VERIFY_SECS + 1.0, True)  # treat as a full utterance
    print(f"score={score:.4f} threshold={threshold():.2f} verdict={v}")
    return 0


def _cmd_status() -> int:
    profile = load_profile()
    meta = load_profile_metadata()
    print(f"gate enabled:      {enabled()}")
    print(f"threshold:         {threshold():.2f}")
    print(f"profile present:   {profile is not None}")
    if meta:
        print(f"enrolled from:     {len(meta.get('files', []))} file(s), "
              f"at {meta.get('created_at', '?')}")
    print(f"model dir present: {MODEL_DIR.exists()}")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print("usage: python -m jarvis.speaker enroll <wav...> | verify <wav> | status")
        return 2
    cmd, rest = argv[0], argv[1:]
    if cmd == "enroll":
        return _cmd_enroll(rest)
    if cmd == "verify":
        if not rest:
            print("usage: python -m jarvis.speaker verify <wav>")
            return 2
        return _cmd_verify(rest[0])
    if cmd == "status":
        return _cmd_status()
    print(f"unknown command: {cmd}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
