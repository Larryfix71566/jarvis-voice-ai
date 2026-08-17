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
 * listener for it (D40's replay handshake). Also what the in-page
 * DisplayPanel falls back to reading when no popup is live (D41). */
let latest: DisplayPayload | null = null;
const inPageListeners = new Set<(payload: DisplayPayload | null) => void>();

function notifyInPage() {
  for (const cb of inPageListeners) cb(latest);
}

/** Console side: publish to the in-page window AND the channel. */
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
