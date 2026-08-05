"""List the ElevenLabs voice library (plan Phase 5, step 5.2).

Usage: python3 scripts/list_voices.py
Prints: voice_id | name | labels — used to populate config/voices.yaml.
"""

import os
import sys

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from jarvis.config import load_settings  # noqa: E402


def main() -> None:
    settings = load_settings()
    resp = httpx.get(
        "https://api.elevenlabs.io/v1/voices",
        headers={"xi-api-key": settings.elevenlabs_api_key},
        timeout=30,
    )
    resp.raise_for_status()
    for v in resp.json()["voices"]:
        labels = ", ".join(f"{k}={x}" for k, x in (v.get("labels") or {}).items())
        print(f"{v['voice_id']} | {v['name']} | {labels}")


if __name__ == "__main__":
    main()
