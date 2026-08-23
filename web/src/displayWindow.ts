/**
 * displayWindow.ts — relay + popup lifecycle for INFORMATIONAL display
 * payloads (MORTIMER_SIDE_DRAWER_PLAN.md D40/D41/D42).
 *
 * Only `surface: "window"` payloads pass through here (plan D28/D36/D37) —
 * work product goes to displayResults.ts instead. Imported by BOTH Vite
 * entries (main + display, D39): the console side publishes, the popup
 * side subscribes. Neither side owns a session; this is pure relay.
 *
 * BroadcastChannel is same-origin/same-browser only — this does NOT cross
 * devices. A second physical machine as a display would need server-side
 * fan-out (bot/admin sidecar over a websocket), out of scope here.
 *
 * The presence protocol (hello/alive/bye/ping/close heartbeat) and the
 * Window Management API placement logic used to live here; both are now
 * shared plumbing in popoutWindow.ts (MORTIMER_DRAWER_POPOUT_PLAN.md DP2),
 * extracted so the new drawer pop-out window (drawer relay module) can use
 * the exact same implementation. This file is a thin domain wrapper around
 * one `PopoutChannel<DisplayMessage>` — same channel name, same messages,
 * same exported function names/signatures as before the extraction.
 */

import type { DisplayPayload } from "./displayResults";
import { createPopoutChannel, type PresenceMessage } from "./popoutWindow";

export const DISPLAY_CHANNEL = "mortimer.display";

type DisplayDomainMessage =
  | { t: "payload"; payload: DisplayPayload }
  | { t: "clear" };

type DisplayMessage = DisplayDomainMessage | PresenceMessage;

const LS_POPOUT = "mortimer.display.popout";

const popout = createPopoutChannel<DisplayDomainMessage>(DISPLAY_CHANNEL, "display");

// --- console side --------------------------------------------------------

/** Latest informational payload — kept here so a `{t:"hello"}` from a
 * freshly-opened popup can be answered even if the console has no other
 * listener for it (D40's replay handshake). This is ALSO what the popped-
 * out external window itself always shows (there is only one physical
 * popup — see the G8 module docstring below for why per-panel POPOUT
 * still means "this panel's content, on the one external window"). */
let latest: DisplayPayload | null = null;
const inPageListeners = new Set<(payload: DisplayPayload | null) => void>();

function notifyInPage() {
  for (const cb of inPageListeners) cb(latest);
}

/**
 * G8 (MORTIMER_SESSION_GAPS_AND_SELFEDIT_CONVERGENCE_PLAN.md, in-page
 * panel registry): before this, a second `surface: "window"` result while
 * the first was still open silently REPLACED it — a follow-up weather
 * check while a research brief was still on screen made the brief
 * disappear with no way back short of asking again. `publish()` now
 * appends a new, independently-closable panel instead of overwriting a
 * single `latest` slot, up to `MAX_OPEN_DISPLAY_PANELS`.
 *
 * The external pop-out window is UNCHANGED in shape: there is exactly one
 * physical browser window (`popout`, channel "mortimer.display"), and the
 * shell's native side only knows the three fixed roles console/display/
 * drawer (see popoutWindow.ts's `open()` — `entry.role` is the contract,
 * not an arbitrary id), so per-panel real OS windows is out of scope here
 * without shell changes. "Pop-out works per-panel" instead means: popping
 * out ANY specific in-page panel sends THAT panel's payload to the one
 * external window (via `popOutPanel`) and removes it from the in-page
 * stack, exactly mirroring what closing/graduating a card to the second
 * screen should feel like. While the popup is live, new publishes still
 * update the external window (via `latest`/the channel) but do NOT also
 * open a redundant in-page panel — unchanged from the pre-G8 behavior.
 */
export const MAX_OPEN_DISPLAY_PANELS = 15;

export interface DisplayWindowPanel {
  id: string;
  payload: DisplayPayload;
}

let panels: DisplayWindowPanel[] = [];
let panelSeq = 0;
const panelListeners = new Set<(panels: DisplayWindowPanel[]) => void>();
const noticeListeners = new Set<(text: string) => void>();

function notifyPanels() {
  for (const cb of panelListeners) cb(panels);
}

function notifyEviction(text: string) {
  for (const cb of noticeListeners) cb(text);
}

/** Subscribe to the live in-page panel stack. Returns an unsubscribe fn. */
export function subscribePanels(cb: (panels: DisplayWindowPanel[]) => void): () => void {
  panelListeners.add(cb);
  cb(panels);
  return () => panelListeners.delete(cb);
}

/** Subscribe to transient "an old panel was auto-closed" notices (shown as
 * a small toast, mirroring the existing popout-error transient pattern). */
export function subscribeEvictionNotice(cb: (text: string) => void): () => void {
  noticeListeners.add(cb);
  return () => noticeListeners.delete(cb);
}

/** Console side: publish to the popout channel and (unless a popup is
 * already live — see the docstring above) append a new in-page panel. */
export function publish(payload: DisplayPayload): void {
  latest = payload;
  notifyInPage();
  // Engagement plan E4 — ambient weather cache: remember the last
  // weather answer's title + when it arrived, purely as a side effect
  // of the user asking (NO proactive fetching, ever). AmbientStrip
  // renders it with its age.
  if (payload.tool === "get_weather" && payload.title) {
    try {
      localStorage.setItem(
        "mortimer.ambient.weather",
        JSON.stringify({ title: payload.title, at: Date.now() }),
      );
    } catch {
      /* storage unavailable — the ambient chip just won't show */
    }
  }
  popout.postMessage({ t: "payload", payload });
  if (hasLivePopup()) return; // shown externally already — no in-page panel
  panelSeq += 1;
  const panel: DisplayWindowPanel = { id: String(panelSeq), payload };
  panels = [...panels, panel];
  if (panels.length > MAX_OPEN_DISPLAY_PANELS) {
    panels = panels.slice(panels.length - MAX_OPEN_DISPLAY_PANELS);
    notifyEviction(
      `Closed the oldest of ${MAX_OPEN_DISPLAY_PANELS} open panels to make room.`,
    );
  }
  notifyPanels();
}

/** Console side: close one in-page panel by id (the panel's own × button). */
export function closePanel(id: string): void {
  const next = panels.filter((p) => p.id !== id);
  if (next.length === panels.length) return;
  panels = next;
  notifyPanels();
}

/** Console side: pop ONE panel's payload out to the single external
 * window, and remove it from the in-page stack — see the module docstring
 * for why this is "per-panel pop-out" without per-panel OS windows. */
export function popOutPanel(id: string): void {
  const panel = panels.find((p) => p.id === id);
  if (panel) {
    latest = panel.payload;
    notifyInPage();
    popout.postMessage({ t: "payload", payload: panel.payload });
  }
  closePanel(id);
  openDisplayWindow();
}

/** D41's mandatory fallback, carried into the multi-panel world: if the
 * external popup goes away (closed, or a blocked/failed pop attempt) while
 * it was the ONLY place a result was showing, that result must not be
 * silently lost. Call when the container detects popupOpen flipping from
 * true to false; re-adds `latest` as an in-page panel unless one already
 * shows it (avoids a duplicate if publish() already handled it). */
export function restoreLatestAsPanel(): void {
  if (!latest) return;
  if (panels.some((p) => p.payload === latest)) return;
  panelSeq += 1;
  panels = [...panels, { id: String(panelSeq), payload: latest }];
  notifyPanels();
}

/** In-page (DisplayPanel) subscription — mirrors the same `latest` value
 * the popup receives, so the console-side fallback path (D41) shows
 * exactly what the popup would have shown. Returns an unsubscribe fn. */
export function subscribeLatest(cb: (payload: DisplayPayload | null) => void): () => void {
  inPageListeners.add(cb);
  cb(latest);
  return () => inPageListeners.delete(cb);
}

/** Console side: reply to a popup's hello with the current payload, and
 * listen for hello on the channel. Call once from App.tsx (or wherever
 * the console mounts) — idempotent-ish via popoutWindow's own guard. */
export function wireConsoleSide(): () => void {
  return popout.wireConsoleSide((m) => {
    if ((m as DisplayDomainMessage).t === "payload" || (m as DisplayDomainMessage).t === "clear") {
      return; // domain messages have no console-side reaction here
    }
    if ((m as PresenceMessage).t === "hello" && latest) {
      popout.postMessage({ t: "payload", payload: latest });
    }
  });
}

// --- popup side ------------------------------------------------------------

/** Popup side: subscribe. Posts {t:"hello"} once on first subscription so
 * a window opened after a result arrived is not blank (D40). Also runs the
 * presence protocol via popoutWindow.ts: an {t:"alive"} heartbeat while
 * open, {t:"bye"} on pagehide, and self-close on a console {t:"close"} —
 * so a console that reloaded (and lost its window ref) still knows this
 * popup exists and can still close it. Returns an unsubscribe function. */
export function subscribeDisplay(cb: (m: DisplayMessage) => void): () => void {
  return popout.wirePopupSide(cb);
}

// --- popup lifecycle (console side) ---------------------------------------

/** Whether a live popup currently exists — DisplayPanel hides itself while
 * true (D41), since the payload is showing on the other screen. Consults
 * BOTH the window ref (this tab opened it) and the heartbeat (it was
 * opened before this console loaded — a reload loses the ref, and without
 * the heartbeat the same result would show in both places). */
export function hasLivePopup(): boolean {
  return popout.isAlive();
}

/** Console side: open (or refocus) the pop-out window. The fixed window
 * NAME is what makes the browser reuse and remember the same window
 * across opens (D41). Returns the window, or null if the browser blocked
 * it — callers MUST handle null and fall back to the in-page window
 * rather than silently losing the payload. Placement (D42/DP8) is handled
 * by popoutWindow.ts on every call, not just the first. */
export function openDisplayWindow(): Window | null {
  return popout.open(
    "/display.html",
    "mortimer-display",
    "width=560,height=440,menubar=no,toolbar=no,location=no,status=no",
  );
}

export function closeDisplayWindow(): void {
  popout.close();
}

// --- preference (guarded localStorage reads, D13's discipline) -----------

export function readPopoutPreference(): boolean {
  try {
    return localStorage.getItem(LS_POPOUT) === "true";
  } catch {
    return false;
  }
}

export function writePopoutPreference(on: boolean): void {
  try {
    localStorage.setItem(LS_POPOUT, String(on));
  } catch {
    /* storage unavailable — preference is simply not persisted */
  }
}
