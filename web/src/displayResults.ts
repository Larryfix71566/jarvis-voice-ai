/**
 * displayResults.ts — module-level store for DRAWER-ROUTED display
 * payloads (MORTIMER_SIDE_DRAWER_PLAN.md D29).
 *
 * Mirrors agentRuns.ts's publish/subscribe shape for the same reason as
 * D10: the Output tab body unmounts on tab switch and on drawer close
 * (plan D23), so state cannot live inside it — it has to outlive the
 * component that renders it.
 *
 * Only `surface: "drawer"` payloads land here (plan D28/D36/D37).
 * `surface: "window"` payloads go to displayWindow.ts instead — this
 * store never sees them.
 */

export interface DisplayPayload {
  kind?: string; // "markdown" | "image" | "links"
  title?: string;
  body?: string; // markdown
  images?: string[];
  // W6 (MORTIMER_WEATHER_FAHRENHEIT_AND_RADAR_PLAN.md) — a keyless CARTO
  // basemap layer at the SAME z/x/y as `images`, present only on radar
  // payloads (get_weather_radar, weather_report). RainViewer's tiles are
  // transparent precipitation overlays with nothing to composite onto
  // otherwise — DisplayContent stacks this UNDER `images` when present.
  basemap_images?: string[];
  links?: { label?: string; url: string }[];
  agent?: string;
  ts?: number; // epoch SECONDS from jarvis/bot/display.py — see timeFormat.ts's warning; do not use directly
  surface?: string; // "drawer" | "window" — plan D36
  tool?: string; // engagement plan E1 — which tool produced this (additive; absent from pre-E1 bots)
  // MORTIMER_HANDOFF_LOOP_PLAN.md H3 — commands the USER runs themselves.
  // A spoken command cannot be copied, so it goes here instead of into
  // dialog text.
  commands?: string[];
  note?: string;
  // H6.1 — the card renders its own "copy the output and say 'read my
  // clipboard'" footer from THIS FLAG, not from model-authored prose. A
  // prompt rule asking the model to mention the return path gets dropped
  // the moment it is terse, and the 60-word voice contract rewards
  // terseness.
  expect_output?: boolean;
  // H4 — clipboard text read back from the user. Shown here (ephemeral)
  // rather than in the Log tab, because the transcript is swept into
  // long-term memory and this content must never be remembered.
  content?: string;
  chars?: number;
  truncated?: boolean;
}

/** One received payload plus a client-side identity, since the payload
 *  itself has no id and two results can be identical. */
export interface DisplayResult {
  id: number;
  payload: DisplayPayload;
  receivedAt: number; // Date.now(), ms — see D34
}

export type DisplayListener = (results: DisplayResult[]) => void;

/** ⚙ TUNING KNOB — bounded history; oldest dropped first. */
export const MAX_DISPLAY_RESULTS = 20;

let results: DisplayResult[] = [];
let seq = 0;
const listeners = new Set<DisplayListener>();

function notify() {
  const snapshot = results.slice();
  for (const cb of listeners) cb(snapshot);
}

/** Newest FIRST (opposite of agentRuns.getRuns(), which is oldest-first —
 *  a results log reads newest-down, a run list reads oldest-up). */
export function getResults(): DisplayResult[] {
  return results.slice();
}

export function subscribeResults(cb: DisplayListener): () => void {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

/** Type-guards internally; ignores anything that is not
 *  {type: "display", display: {...}}. The ONLY mutator from RTVI events.
 *  Callers (App.tsx's D30/D37 listener) are responsible for only
 *  forwarding surface:"drawer" payloads here. */
export function applyServerMessage(msg: unknown): void {
  const m = msg as { type?: string; display?: DisplayPayload };
  if (m?.type !== "display" || !m.display) return;
  const entry: DisplayResult = {
    id: ++seq,
    payload: m.display,
    receivedAt: Date.now(),
  };
  results = [entry, ...results].slice(0, MAX_DISPLAY_RESULTS);
  notify();
}

export function removeResult(id: number): void {
  results = results.filter((r) => r.id !== id);
  notify();
}

/** MORTIMER_DRAWER_POPOUT_PLAN.md DP3 — same relay pattern as
 * agentRuns.ts's applyRelayedRuns: the drawer window's copy of this store
 * has no RTVI connection and is fed wholesale by the console's relay
 * (web/src/drawerRelay.ts) instead of applyServerMessage. */
export function applyRelayedResults(next: DisplayResult[]): void {
  results = next;
  notify();
}

/** Engagement plan E1 — the deterministic "needs your confirmation"
 * rule, in its ONE home: attention is active iff the NEWEST drawer
 * item was produced by a draft-gated tool (the draft→confirm pattern's
 * first halves). Self-clearing: the confirm's executed payload — or
 * anything newer — replaces it at the head of the list. */
const DRAFT_TOOLS = new Set(["prepare_commit", "prepare_push", "repo_write_file"]);

export function hasPendingDraft(): boolean {
  const newest = results[0];
  return newest !== undefined && DRAFT_TOOLS.has(newest.payload.tool ?? "");
}

export function clearResults(): void {
  results = [];
  notify();
}
