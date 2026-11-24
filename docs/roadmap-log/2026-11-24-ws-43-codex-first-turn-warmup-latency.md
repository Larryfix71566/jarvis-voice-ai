---
date: 2026-11-24
system: codex
rows: [WS-43]
prs: []
---

## First-turn Claude CLI warm-up and useful-speech timing

- On the voice LLM start frame, schedule one spare for the first turn behind the existing streaming and pre-start gates. Warm-up runs only with the recorded, host-classified system-only context and registered menu. No conversation history enters the spare. First request binds the spare when its normal identity checks match. Existing receipt checks, later-turn rearming, cleanup, and cold fallback remain in place.
- `scripts/latency_probe.py --acceptance [samples.jsonl]` budgets explicitly labeled first useful audible speech. Holding acknowledgements are reported separately; completed turn IDs determine class, independent of log order. Empty or incomplete windows fail. The JSONL format and labeling instructions are in the probe's module docstring. The legacy first-output-frame CI probe is unchanged and is not live acceptance evidence. No prompt/reply text is needed.
- Evidence: 41 focused offline tests passed (including startup, gated/privacy negative cases, first-turn binding, stop before first prompt, and strict latency probe). Changed-file Ruff, Git diff checks, offline tokenizer smoke and the existing CI latency fixture passed. The eight existing Unix socket-dependent tests hit the same local sandbox refusal on baseline `next` and the candidate. No actual model call, microphone/audio, app launch, install, controller or runtime change.
- Next: verify exact-head hosted checks and separately run attended audible acceptance on a separately authorized test build. Record the authoritatively matched build and distinct model/flag conditions before comparing measured figures. No performance or acceptance pass claimed.
