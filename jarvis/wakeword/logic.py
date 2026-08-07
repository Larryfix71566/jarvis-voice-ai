"""Wake-word gating logic — pure and unit-tested, no model dependency.

The sidecar server feeds a stream of per-chunk detection scores from
openWakeWord into a WakeGate; the gate decides when a wake actually fires:
a score at or above the threshold, then suppressed for ``cooldown_s`` so one
spoken "Mortimer" produces exactly one wake event, not a burst.
"""

from __future__ import annotations


class WakeGate:
    """Threshold + cooldown decision over a detection-score stream."""

    def __init__(self, threshold: float = 0.5, cooldown_s: float = 2.0) -> None:
        if not 0.0 < threshold < 1.0:
            raise ValueError(f"threshold must be in (0, 1), got {threshold!r}")
        if cooldown_s < 0.0:
            raise ValueError(f"cooldown_s must be >= 0, got {cooldown_s!r}")
        self.threshold = threshold
        self.cooldown_s = cooldown_s
        self._last_fired_at: float | None = None

    def check(self, score: float, now: float) -> bool:
        """Return True exactly once per wake utterance."""
        if score < self.threshold:
            return False
        if (
            self._last_fired_at is not None
            and now - self._last_fired_at < self.cooldown_s
        ):
            return False
        self._last_fired_at = now
        return True

    def reset(self) -> None:
        self._last_fired_at = None
