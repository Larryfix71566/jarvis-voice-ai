# GC24-03 receipt — speaker and audio-gate log redaction

**Date:** 2026-09-25  
**Branch:** `codex/isolated-20260924`  
**Base/HEAD at start:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`  
**State:** verified in the dirty isolated tree; concurrent work was preserved.

## Change

Speaker-profile and voice-gate logs now omit local profile/model/WAV paths,
raw threshold configuration values, capture paths, turn identifiers,
exception text, and tracebacks. The logs keep bounded event names, bounded
exception class names, existing score/window diagnostics, and capture
duration. Best-effort error handling and the speaker-gate fail-open behavior
remain unchanged. Transcript content and audio bytes remain outside logs.

## Verification

- `./.venv/bin/pytest -q tests/unit/test_speaker.py tests/unit/test_speaker_gate.py --tb=short`
  — **69 passed, 2 existing dependency deprecation warnings**.
- `./.venv/bin/ruff check --select F,I jarvis/speaker.py jarvis/bot/speaker_gate.py tests/unit/test_speaker.py tests/unit/test_speaker_gate.py`
  — passed.
- `./.venv/bin/python -m compileall -q jarvis/speaker.py jarvis/bot/speaker_gate.py tests/unit/test_speaker.py tests/unit/test_speaker_gate.py`
  — passed.
- `git diff --check` — passed.
- Canary tests cover corrupt profile/metadata, missing and failed model load,
  embedding and WAV failures, threshold parsing, capture success/failure,
  scoring, and UI/drop-note delivery failures.

## Still open

This closes only the speaker/profile and voice-gate logging paths listed
above. It does not establish voiceprint storage/retention policy or broader
audio data-flow safety. Slices C–E and the full GC24-03 source-to-sink audit
remain open. No live microphone, provider, installed Mac, deployment, or
release test was run.
