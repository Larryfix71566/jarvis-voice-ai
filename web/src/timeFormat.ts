/**
 * timeFormat.ts — shared relative-time formatting
 * (MORTIMER_SIDE_DRAWER_PLAN.md D34).
 *
 * Lifted from RunsPanel.tsx's local `relTime`, which took an ISO string.
 * The Output tab's DisplayResult.receivedAt (displayResults.ts, D29) is a
 * millisecond epoch (Date.now()), not ISO, so the millisecond form is the
 * primitive and `relTime` is defined in terms of it.
 *
 * IMPORTANT: do not call either of these on a display payload's raw `ts`
 * field (jarvis/bot/display.py) — that is epoch SECONDS (`time.time()`),
 * not milliseconds and not ISO. Passing it here yields a plausible-looking
 * wrong date (effectively January 1970), not a crash. Use
 * DisplayResult.receivedAt instead.
 */

/** "12s ago" / "5m ago" / "3h ago" / "2d ago" from a millisecond epoch. */
export function relTimeFromMs(ms: number): string {
  const delta = Date.now() - ms;
  const s = Math.max(0, Math.floor(delta / 1000));
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

/** Same, from an ISO 8601 string. */
export function relTime(iso: string): string {
  return relTimeFromMs(new Date(iso).getTime());
}
