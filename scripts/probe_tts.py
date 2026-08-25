#!/usr/bin/env python3
"""Diagnose ElevenLabs TTS returning NO AUDIO.

`check_env.py` answers "is the key valid and the account reachable?" —
it lists voices and passes. That is not the same question as "will this
voice actually synthesize speech right now", and on 2026-08-24 the two
diverged: the key passed, 22 voices listed, and every TTS request came
back `final` in ~43ms with the text still marked *remaining* — i.e. an
empty stream, no audio, `Bot started speaking = 0`.

Three things that produce that exact silent-empty-stream shape and that
check_env cannot see:
  1. quota exhausted (character limit hit — the stream closes empty
     rather than erroring),
  2. the CONFIGURED voice id is not on the account (deleted, or a shared
     voice that was never added to the library),
  3. the model name is not enabled for this account's tier.

This script checks all three and synthesizes one short line over HTTP so
"did audio come back" is answered in bytes, not inference.

Usage:
    python scripts/probe_tts.py            # default voice from voices.yaml
    python scripts/probe_tts.py rachel     # a specific catalog voice id
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import httpx  # noqa: E402
import yaml  # noqa: E402

from jarvis.vault import inject_env  # noqa: E402

BASE = "https://api.elevenlabs.io"
MODEL = "eleven_flash_v2_5"
PROBE_TEXT = "Evening, Larry."


def main(argv: list[str]) -> int:
    inject_env()
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        print("FAIL: ELEVENLABS_API_KEY is not set.")
        return 2
    headers = {"xi-api-key": key}

    catalog = yaml.safe_load((REPO_ROOT / "config" / "voices.yaml").read_text())
    wanted = argv[1] if len(argv) > 1 else catalog["default"]
    entry = next((v for v in catalog["voices"] if v["id"] == wanted), None)
    if entry is None:
        print(f"FAIL: no voice '{wanted}' in config/voices.yaml")
        return 2
    voice_id = entry["elevenlabs_voice_id"]
    print(f"catalog voice : {entry['id']} -> {voice_id}")
    print(f"model         : {MODEL}\n")

    # 1. Quota — the most common cause of a silent empty stream.
    try:
        r = httpx.get(f"{BASE}/v1/user/subscription", headers=headers, timeout=15)
        if r.status_code == 200:
            s = r.json()
            used = s.get("character_count")
            limit = s.get("character_limit")
            tier = s.get("tier")
            left = (limit - used) if isinstance(used, int) and isinstance(limit, int) else None
            print(f"tier          : {tier}")
            print(f"characters    : {used:,} / {limit:,}" if left is not None
                  else f"characters    : {used} / {limit}")
            if left is not None:
                verdict = "EXHAUSTED — this is why there is no audio" if left <= 0 else "ok"
                print(f"remaining     : {left:,}  <- {verdict}")
        else:
            print(f"subscription  : HTTP {r.status_code} (could not read quota)")
    except Exception as exc:  # noqa: BLE001
        print(f"subscription  : unreachable ({type(exc).__name__})")

    # 2. Is the configured voice actually on the account?
    try:
        r = httpx.get(f"{BASE}/v2/voices", headers=headers,
                      params={"page_size": 100}, timeout=20)
        ids = {v.get("voice_id") for v in (r.json().get("voices") or [])}
        on_account = voice_id in ids
        print(f"\nvoice present : {on_account}"
              f"{'' if on_account else '  <- NOT on this account'}")
        if not on_account:
            print("                (a shared/deleted voice id yields an empty stream,"
                  " not an error)")
    except Exception as exc:  # noqa: BLE001
        print(f"\nvoice present : could not check ({type(exc).__name__})")

    # 3. The real question: does synthesis return bytes?
    print("\nsynthesizing one line…")
    try:
        r = httpx.post(
            f"{BASE}/v1/text-to-speech/{voice_id}",
            headers={**headers, "Content-Type": "application/json"},
            json={"text": PROBE_TEXT, "model_id": MODEL},
            timeout=30,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED: {type(exc).__name__}: {exc}")
        return 1

    if r.status_code != 200:
        print(f"HTTP {r.status_code}")
        print(f"body: {r.text[:400]}")
        return 1
    n = len(r.content)
    print(f"HTTP 200, {n:,} bytes of audio")
    print("VERDICT: TTS works over HTTP — the fault is the websocket path or config."
          if n > 1000 else
          "VERDICT: 200 but effectively NO AUDIO — matches the empty-stream symptom.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
