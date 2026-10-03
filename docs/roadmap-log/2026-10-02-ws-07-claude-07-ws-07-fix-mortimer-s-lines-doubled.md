---
date: 2026-10-02
system: claude
rows: [WS-07]
prs: []
---

- 2026-10-02 (WS-07 fix: Mortimer's lines doubled in the thread): Claude (Cowork). Larry saw each Mortimer line twice, interleaved, in the CC7a thread; the LLM context and the server transcript held it once. Cause: pipecat's RTVI observer sends one `bot-llm-text` per LLM text frame; the LLM pushes token frames and ReplyGuard (`log` mode in production) pushes new sentence frames, so the app received both. Fix: the observer ignores frames pushed by the LLM itself (`rtvi_observer_params`, `build_task`); every LLM frame is still reported once when the guard passes it on, and the thread shows what is spoken. Reproduced and pinned in `tests/unit/test_rtvi_bot_text.py`. Remaining: Larry's thread check on a build that contains it (UI2-22).
