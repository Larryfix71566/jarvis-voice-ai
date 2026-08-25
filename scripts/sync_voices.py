#!/usr/bin/env python3
"""Rewrite config/voices.yaml from the voices actually on the ElevenLabs account.

The catalog was hand-written with five voices while the account carries 22
(Larry 2026-08-24: "I want all 22 listed as voice choices in the
interface"). Everything downstream — the console's VoicePicker, the CLI,
the set_voice tool, and the Supervisor prompt's voice list — already reads
config/voices.yaml through `load_voice_catalog`, so syncing the FILE gives
all four surfaces the full list with no second code path and no
network dependency at boot. A fetch-at-startup design was considered and
rejected for exactly that reason: the voice catalog would become a thing
that can fail while the bot is coming up.

Deliberately a SCRIPT, not automatic: the result lands in a diff you can
read before it ships, same discipline as scripts/check_env.py and
scripts/probe_planner.py.

  python scripts/sync_voices.py            # preview the diff, writes nothing
  python scripts/sync_voices.py --write    # rewrite config/voices.yaml

The `default:` voice is PRESERVED across a sync if it still exists on the
account; a default that has disappeared is reported loudly rather than
silently reassigned, because a wrong default is a bot that boots and then
cannot speak.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import httpx  # noqa: E402
import yaml  # noqa: E402

from jarvis.vault import inject_env  # noqa: E402

VOICES_PATH = REPO_ROOT / "config" / "voices.yaml"
BASE = "https://api.elevenlabs.io"


def slugify(name: str, taken: set[str]) -> str:
    """A stable, SPEAKABLE id — this is what the user says out loud and what
    `resolve_voice` matches on first.

    ElevenLabs names its stock voices `Name - Description` ("Brian - Deep,
    Resonant and Comforting"), so slugifying the whole string produced
    `brian-deep-resonant-and-comforting`, which is unsayable as a voice
    command. Only the part before the first dash becomes the id; the full
    string still becomes the LABEL, so the picker keeps the description and
    `resolve_voice`'s label-substring fallback can still match on it.
    """
    head = re.split(r"\s+[-–—]\s+", name.strip(), maxsplit=1)[0]
    base = re.sub(r"[^a-z0-9]+", "-", head.lower()).strip("-") or "voice"
    candidate = base
    n = 2
    while candidate in taken:
        candidate = f"{base}-{n}"
        n += 1
    return candidate


def describe(v: dict) -> str:
    """Human label: name plus whatever accent/description the account has."""
    name = v.get("name") or "Unnamed"
    labels = v.get("labels") or {}
    bits = [labels.get(k) for k in ("accent", "gender", "age", "use_case")]
    detail = ", ".join(b for b in bits if b)
    desc = (v.get("description") or "").strip()
    if not detail and desc:
        detail = desc[:60]
    return f"{name} ({detail})" if detail else name


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true",
                    help="rewrite config/voices.yaml (default: preview only)")
    args = ap.parse_args(argv[1:])

    inject_env()
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        print("FAIL: ELEVENLABS_API_KEY is not set.")
        return 2

    try:
        r = httpx.get(f"{BASE}/v2/voices", headers={"xi-api-key": key},
                      params={"page_size": 100}, timeout=30)
        r.raise_for_status()
        account = r.json().get("voices") or []
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: could not list voices ({type(exc).__name__}: {exc})")
        return 1

    current = yaml.safe_load(VOICES_PATH.read_text(encoding="utf-8"))
    old_default = current.get("default")
    old_by_vid = {v["elevenlabs_voice_id"]: v for v in current.get("voices", [])}

    taken: set[str] = set()
    entries = []
    for v in sorted(account, key=lambda x: (x.get("name") or "").lower()):
        vid = v.get("voice_id")
        if not vid:
            continue
        # Keep the hand-written id/label for a voice already in the catalog —
        # "jarvis" is a curated name the user says aloud, and regenerating it
        # from the account's own name would silently break that habit.
        existing = old_by_vid.get(vid)
        if existing:
            vid_id, label = existing["id"], existing["label"]
        else:
            vid_id, label = slugify(v.get("name") or vid, taken), describe(v)
        taken.add(vid_id)
        entries.append({"id": vid_id, "elevenlabs_voice_id": vid, "label": label})

    ids = {e["id"] for e in entries}
    if old_default in ids:
        new_default = old_default
    else:
        new_default = entries[0]["id"] if entries else ""
        print(f"WARNING: default '{old_default}' is no longer on the account; "
              f"falling back to '{new_default}' — set it deliberately before shipping.")

    added = [e for e in entries if e["elevenlabs_voice_id"] not in old_by_vid]
    removed = [v for vid, v in old_by_vid.items()
               if vid not in {e["elevenlabs_voice_id"] for e in entries}]

    print(f"account voices : {len(entries)}")
    print(f"catalog before : {len(old_by_vid)}")
    print(f"default        : {new_default}")
    if added:
        print(f"\nadding {len(added)}:")
        for e in added:
            print(f"  + {e['id']:<28} {e['label']}")
    if removed:
        # A catalog voice missing from the account is not housekeeping — it
        # is a voice the user can currently SELECT and which will then
        # synthesize nothing. That is the same silent-empty-stream shape
        # that cost an hour of debugging on 2026-08-24, so say so plainly.
        print(f"\nremoving {len(removed)} — NOT on the account, so selecting "
              f"{'it' if len(removed) == 1 else 'them'} today produces silence:")
        for v in removed:
            print(f"  - {v['id']:<28} {v['label']}")
    if not added and not removed:
        print("\nno change — catalog already matches the account.")

    if not args.write:
        print("\n(preview only — re-run with --write to apply)")
        return 0

    header = (
        "# Voice catalog (plan §6.5, Phase 5 step 5.2 — exact schema).\n"
        "# GENERATED by scripts/sync_voices.py from the ElevenLabs account.\n"
        "# Hand edits to `default:` are preserved by a re-sync; hand edits to\n"
        "# an existing voice's id/label are preserved too (matched on\n"
        "# elevenlabs_voice_id), so a curated name like `jarvis` survives.\n"
    )
    body = yaml.safe_dump(
        {"default": new_default, "voices": entries},
        sort_keys=False, allow_unicode=True, width=100,
    )
    VOICES_PATH.write_text(header + body, encoding="utf-8")
    print(f"\nwrote {VOICES_PATH.relative_to(REPO_ROOT)} ({len(entries)} voices)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
