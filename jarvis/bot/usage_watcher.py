"""UsageMetricsObserver — supervisor-rung cost-ledger hookup
(MORTIMER_OPTIMIZATION_PLAN.md Phase 0, step 1 of the readiness checklist).

Confirmed 2026-09-01: the live voice pipeline never calls
jarvis.agents.supervisor.Orchestrator (that class is jarvis/cli.py's
text-only entry point — a live voice turn never touched it, verified by a
debug print that never fired). The actual Supervisor completion is
pipecat's own OpenAILLMService, constructed directly in jarvis/bot/
pipeline.py. This observer is how we see those calls without touching
BaseOpenAILLMService._process_context's carefully-commented stream-closing
logic (see that method's own docstring re: uvloop/MagicStack#699) or
overriding get_chat_completions and re-wrapping the raw stream ourselves.

Confirmed against the installed pipecat 1.4.0:
- BaseOpenAILLMService.build_chat_completion_params already sets
  stream_options={"include_usage": True} unconditionally.
- _process_context's `async for chunk in chunk_iter` loop, on seeing
  chunk.usage, builds an LLMTokenUsage and calls
  self.start_llm_usage_metrics(tokens), which pushes a
  MetricsFrame(data=[LLMUsageMetricsData(processor=..., model=...,
  value=tokens)]) downstream — but ONLY when
  self.can_generate_metrics() (True for BaseOpenAILLMService, confirmed)
  AND self.usage_metrics_enabled (gated by PipelineParams(enable_metrics=
  True, enable_usage_metrics=True) on the PipelineTask — nothing in this
  repo set that before this patch; grep confirmed zero existing
  MetricsFrame/LLMUsageMetricsData consumers anywhere in jarvis/, so
  turning it on is additive, not a behavior change for anything else).

KNOWN GAP — half-closed as of Phase 1 (Rev 3.2) landing step (iii):
LLMTokenUsage.cache_creation_input_tokens is the discriminator
on_push_frame now branches on (`is None` vs. a real int — confirmed
against the installed pipecat 1.4.0's own two LLM services, not assumed).
Under OpenAILLMService (the compat path — still the default whenever
JARVIS_ANTHROPIC_NATIVE=0, or for any non-Anthropic base_url),
BaseOpenAILLMService._process_context never sets that field, so it stays
None: the OLD behaviour applies unchanged, prompt_tokens is cache-
INCLUSIVE (subtract reads back out), and cache_write_tokens always
reports 0 through this path. That half of the gap is real and permanent
for the compat path — Anthropic's OpenAI-compatibility layer does not
support prompt caching at all, the reason Phase 1 exists in the first
place. Under AnthropicLLMService (Path A, wired in landing step (iii)),
_report_usage_metrics always sets cache_creation_input_tokens to a real
int (0 or more, never None): prompt_tokens is already uncached-only, no
subtraction needed, and cache_write rides through with full fidelity —
no gap. Landing step (iii) also adds a `supervisor_cache_cold` WARNING
(task 8) when a native-path turn >= 2 reports a zero cache read — the
one log line that turns a silent miss back into a visible one. The other
12 planned call sites (jarvis/agents/base.py's SubAgent._loop,
memory_sweep.py, council.py, etc.) call usage_ledger.record_completion()
directly on the raw client response object and were never affected by
this gap either way.

Same BaseObserver/on_push_frame pattern as SpeakingStateTracker (jarvis/
bot/progress_watcher.py) and InterruptionNotifier (jarvis/bot/
interruption.py): frames pushed directly via push_frame from inside a
service's metrics helper never reach a normal in-pipeline processor, so a
dedicated task observer is the established way this codebase already
taps frames like that.
"""

from __future__ import annotations

import logging
from collections import deque

from pipecat.frames.frames import MetricsFrame
from pipecat.metrics.metrics import LLMUsageMetricsData
from pipecat.observers.base_observer import BaseObserver, FramePushed
from pipecat.processors.frame_processor import FrameDirection

from jarvis.usage_ledger import record_call

logger = logging.getLogger(__name__)


class UsageMetricsObserver(BaseObserver):
    """Writes one usage_ledger row per LLMUsageMetricsData frame seen.

    rung/provider are fixed at construction — one instance per pipeline,
    wired for the top-level Supervisor LLM service only (Phase 0 step 1:
    supervisor rung first, the other 12 sites follow the plan's readiness
    checklist in order, each via record_completion() at its own call
    site rather than this frame-based path)."""

    # Confirmed 2026-09-01 (live session, JARVIS_DEBUG instrumentation):
    # a single MetricsFrame is forwarded BY REFERENCE through every
    # downstream processor hop (id(frame) identical start to finish, 2-13
    # hops observed depending on where the frame originates) — pipecat's
    # task-level observers see push_frame() at every hop, not just the
    # originating one. Without dedup, one real LLM completion produced 5+
    # identical ledger rows. Bounded (not an unbounded set — this process
    # runs for days) since real MetricsFrame traffic per voice turn is a
    # handful of objects; 256 is generously larger than any single turn's
    # propagation window could plausibly need.
    _DEDUP_WINDOW = 256

    def __init__(
        self,
        rung: str,
        provider: str,
        session_id: str,
        default_model: str = "unknown",
    ) -> None:
        super().__init__()
        self._rung = rung
        self._provider = provider
        self._session_id = session_id
        self._default_model = default_model
        self._seen_ids: set[int] = set()
        self._seen_order: deque[int] = deque()
        # Phase 1 (Rev 3.2) landing step (iii), task 8's cold-cache
        # alert -- counts native-Anthropic (Path A) turns only, since
        # the warning is only meaningful (and only ever fires) there.
        self._native_turn_count = 0

    async def on_push_frame(self, data: FramePushed) -> None:
        if data.direction != FrameDirection.DOWNSTREAM:
            return
        frame = data.frame
        if not isinstance(frame, MetricsFrame):
            return
        fid = id(frame)
        if fid in self._seen_ids:
            return  # already recorded this exact frame at an earlier hop
        self._seen_ids.add(fid)
        self._seen_order.append(fid)
        if len(self._seen_order) > self._DEDUP_WINDOW:
            self._seen_ids.discard(self._seen_order.popleft())
        for item in frame.data:
            if not isinstance(item, LLMUsageMetricsData):
                continue
            try:
                tokens = item.value
                cached = tokens.cache_read_input_tokens or 0
                if tokens.cache_creation_input_tokens is None:
                    # OpenAI/compat semantics: prompt_tokens is CACHE-
                    # INCLUSIVE, so reads must be subtracted back out to
                    # get the true uncached count. cache_write is never
                    # reported through this frame path (KNOWN GAP — see
                    # module docstring; permanent on this path).
                    input_tokens = max((tokens.prompt_tokens or 0) - cached, 0)
                    cache_write_tokens = 0
                else:
                    # Native Anthropic semantics (Path A, landing step
                    # (iii)): prompt_tokens is ALREADY uncached-only, so
                    # no subtraction; cache writes are a real int, no
                    # longer a gap.
                    input_tokens = tokens.prompt_tokens or 0
                    cache_write_tokens = tokens.cache_creation_input_tokens or 0
                    self._native_turn_count += 1
                    if self._native_turn_count >= 2 and cached == 0:
                        # Task 8's alert: turn 1 legitimately has nothing
                        # to read yet, so it never warns.
                        logger.warning(
                            "supervisor_cache_cold turn=%d prompt_tokens=%d",
                            self._native_turn_count, tokens.prompt_tokens or 0,
                        )
                record_call(
                    rung=self._rung,
                    provider=self._provider,
                    model=item.model or self._default_model,
                    session_id=self._session_id,
                    input_tokens=input_tokens,
                    output_tokens=tokens.completion_tokens or 0,
                    cache_write_tokens=cache_write_tokens,
                    cache_read_tokens=cached,
                )
            except Exception:  # noqa: BLE001 — cost logging must never
                # break a live voice turn (same discipline as
                # usage_ledger.record_call's own internal catch).
                logger.warning("usage_watcher record_call failed", exc_info=True)
