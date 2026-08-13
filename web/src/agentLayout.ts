/**
 * Shared sub-agent layout (star-layout plan §5.1/D3).
 *
 * Single source of truth for the five-satellite star arrangement, imported
 * by both OrbField (renders the satellites + beams) and AgentStatusPanel
 * (anchors each run's status card near its agent's satellite). This module
 * exists because the two components previously kept independent copies of
 * the agent roster, which is exactly how Developer went missing from the
 * satellite field while staying correct everywhere else (config/agents.yaml,
 * the backend event stream, AgentStatusPanel's own card rendering) — see
 * MORTIMER_STAR_LAYOUT_PLAN.md §1.
 *
 * Positions are hardcoded, not derived from config/agents.yaml (plan D2):
 * they are hand-tuned geometry, not data. tests/unit/
 * test_agents_yaml_frontend_parity.py guards against this list drifting
 * out of sync with the backend roster again.
 *
 * Coordinates are percentages of the `.orb-field` box (same convention the
 * satellites already used: `left: x%; top: y%` with
 * `transform: translate(-50%, -50%)`), NOT aspect-corrected (plan D5) — the
 * pentagon stretches with the field's aspect ratio, matching the beam SVG's
 * `preserveAspectRatio="none"`.
 */

export interface AgentLayoutEntry {
  /** Backend agent key — matches config/agents.yaml `name` and the `name`
   * field on delegate_start/delegate_done events. */
  key: string;
  /** Display label shown under the satellite dot. */
  label: string;
  /** Percentage of `.orb-field` width, satellite center. */
  x: number;
  /** Percentage of `.orb-field` height, satellite center. */
  y: number;
  /** Direction the status card extends FROM the satellite (plan D9). */
  cardAnchor: "above" | "left" | "right";
}

/**
 * Radial pentagon, apex at top, centered at (50, 50), horizontal radius 34,
 * vertical radius 27 (plan §5.1a). Developer at the apex (plan D6); the
 * other four keep their pre-existing rough quadrant (plan D7). Side points
 * anchor cards INWARD (plan §5.1a) — outward would push a 300px card past
 * the viewport edge at x=82%/x=18% on common widths.
 *
 * Do not recompute these at runtime — use the table as given (plan §5.1a).
 */
export const AGENT_LAYOUT: AgentLayoutEntry[] = [
  { key: "developer", label: "Developer", x: 50, y: 23, cardAnchor: "above" },
  { key: "analyst", label: "Analyst", x: 82, y: 42, cardAnchor: "left" },
  { key: "systems", label: "Systems", x: 70, y: 72, cardAnchor: "left" },
  { key: "librarian", label: "Librarian", x: 30, y: 72, cardAnchor: "right" },
  { key: "scheduler", label: "Scheduler", x: 18, y: 42, cardAnchor: "right" },
];

/** Look up a layout entry by backend agent key (case-sensitive — keys are
 * always lowercase per config/agents.yaml). */
export function findAgentLayout(key: string): AgentLayoutEntry | undefined {
  return AGENT_LAYOUT.find((a) => a.key === key);
}

// --- tuning knobs (plan §6 — adjust values here only, after seeing it on
// screen; do not scatter these into CSS or component bodies) -------------

/** ⚙ TUNING KNOB — status card width in px (plan D11: shrunk from 360 so
 * five anchored cards can coexist without overlapping). */
export const CARD_WIDTH_PX = 300;

/** ⚙ TUNING KNOB — gap in px between the satellite chip and its card. */
export const CARD_GAP_PX = 14;

/** ⚙ TUNING KNOB — minimum distance in px a card keeps from any viewport
 * edge (plan §5.4 clamp). */
export const VIEWPORT_MARGIN_PX = 12;

/** ⚙ TUNING KNOB — below this viewport width, fall back to the original
 * stacked bottom-left column (plan D12). Matches the existing
 * `@media (max-width: 860px)` breakpoint in command-deck.css. */
export const ANCHORED_CARDS_MIN_WIDTH_PX = 860;

/** Fallback assumed card height in px, used for the first paint before a
 * card's real height has been measured (plan §5.4). */
export const ASSUMED_CARD_HEIGHT_PX = 160;

/** Height of `.topbar` in px (App.css) — cards may never sit above this
 * (plan §5.4 step 5). */
export const TOPBAR_HEIGHT_PX = 52;

// --- field-rect publisher (plan §5.1c) -----------------------------------
//
// Mirrors the module-level Set<listener> + subscribe/unsubscribe pattern
// already used by wakeWord.ts's subscribeWake — deliberately not React
// Context or a state library, to match existing conventions in this file
// set.

export interface FieldRect {
  left: number;
  top: number;
  width: number;
  height: number;
}

let fieldRect: FieldRect | null = null;
type FieldRectListener = (rect: FieldRect | null) => void;
const fieldRectListeners = new Set<FieldRectListener>();

/** Called by OrbField whenever `.orb-field`'s measured bounding rect
 * changes (mount, ResizeObserver, window scroll/resize). */
export function publishFieldRect(rect: FieldRect | null): void {
  fieldRect = rect;
  for (const cb of fieldRectListeners) cb(rect);
}

/** Current field rect, or null if OrbField hasn't measured yet. */
export function getFieldRect(): FieldRect | null {
  return fieldRect;
}

/** Subscribe to field rect changes; returns an unsubscribe function. */
export function subscribeFieldRect(cb: FieldRectListener): () => void {
  fieldRectListeners.add(cb);
  return () => {
    fieldRectListeners.delete(cb);
  };
}

// --- percentage -> viewport pixel helper (plan §5.1d) --------------------

export interface ViewportPoint {
  x: number;
  y: number;
}

/** Convert an agent's x/y percentages into a viewport pixel position,
 * given the current field rect. Returns null when no rect has been
 * published yet (OrbField hasn't measured `.orb-field` on this render). */
export function agentViewportPosition(
  entry: AgentLayoutEntry,
  rect: FieldRect | null,
): ViewportPoint | null {
  if (rect === null) return null;
  return {
    x: rect.left + (entry.x / 100) * rect.width,
    y: rect.top + (entry.y / 100) * rect.height,
  };
}
