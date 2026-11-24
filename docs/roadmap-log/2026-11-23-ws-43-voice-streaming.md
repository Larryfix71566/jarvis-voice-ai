---
date: 2026-11-23
system: claude
rows: [WS-43]
prs: []
---

# 2026-11-23: voice streaming and a pre-started Claude CLI (WS-43)

- **System:** Claude (Claude Code cloud session, Claude Duet thread), at the coordinator's request. Planned and reviewed by Claude Opus 5.5; implemented by Claude Sonnet 5.5 helpers.
- **Larry's words (UTC, Claude Duet channel):** 21:10 "Build streaming"; 21:15 "merged" (PRs 412 and 413, so this is built on `next` b97e033).
- **Row:** no existing row covered speaking the voice reply while it is being written, so this PR adds the WS-43 block and its §3 config-key reservation; merging approves both.
- **Why:** the investigation (Claude Duet project file `voice-streaming-investigation-2026-11-23.md`) measured a buffered CLI turn on the Mac at 1378/1628 ms p50/p90 (Opus 5.5 low), 1404/2204 (Sonnet 5.5 low), 1246/1793 (Haiku 5.5 low), of which about 840 ms is CLI start-up; a pre-started, streamed CLI put the first sentence at 767 ms (Sonnet low) to about 1002 ms (Opus low) in the container. The `scripts/latency_probe.py` gate for a non-delegated turn is p50 at most 1.2 s.
- **Change (all behind `JARVIS_VOICE_STREAMING_ENABLED=1`, voice only):**
  1. The voice CLI gets `--include-partial-messages`; each `text_delta` goes straight to the pipeline as an `LLMTextFrame`, where the existing ReplyGuard sentence streaming and ElevenLabs take it. Time-to-first-byte now stops at the first text.
  2. After each finished turn (and once at start), the next turn's CLI process is started and initialized with the same system prompt and tool menu, then waits. The next turn binds its first request to it if model, menu, system prompt and ids still match; otherwise it is closed and the turn starts cold, as today. Its 120 s deadline starts when the prompt is written, not at launch. Stop, cancel and disconnect close it.
  3. If the user interrupts mid-reply, the part already spoken is registered with the voice source policy, so the next turn's context is still classified (without this the subscription route would refuse every later turn).
  - `JARVIS_VOICE_PRESTART_ENABLED=0` keeps streaming without the waiting process, for measuring each part. `JARVIS_VOICE_EFFORT=low|medium|high` adds `--effort` to the voice CLI, independent of streaming.
  - New profile `claude-opus-5-5` so `JARVIS_MODEL_PROFILE_VOICE_SUPERVISOR` can select it for the latency run. Like `claude-fable-5-2` in WS-42, it adds one name to the model list the voice prompt and the console picker show, even with every flag off. No Haiku 5.5 profile: Larry's 2026-09-01 floor (`tests/unit/test_model_floor.py`) keeps Haiku out of the registry, because any registry profile can be named for a delegated task.
- **Receipts:** with any flag on, the CLI arguments differ, so the voice tool menu is recorded under a different file name and needs its own receipt (`scripts/verify_claude_tool_receipts.py --workload voice_supervisor --live --output FOLDER`). With the flags off, arguments, menu files and receipts are unchanged. The "One moment..." line before a tool call is the streamed text of that round.
- **CLI:** no newer CLI is needed: `--include-partial-messages` and `--effort` ran on the pinned `claude` 2.1.291 with Opus 5.5 and Sonnet 5.5 in the investigation (§4).
- **Verified here:** see the PR (unit and integration counts on Linux, Python 3.12, fake CLI only).
- **Not tested:** a real streamed turn through Pipecat, ElevenLabs and the Mac's audio; the idle cost of a waiting CLI on the subscription; what is heard when a turn fails after its first sentence (the same error line as today, but after speech).
- **Next actor:** Larry: merge, deploy, receipts, latency run (Claude Duet project file `voice-streaming-mac-steps-2026-11-23.md`).
