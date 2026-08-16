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
 */

import type { DisplayPayload } from "./displayResults";

export const DISPLAY_CHANNEL = "mortimer.display";

type DisplayMessage =
  | { t: "payload"; payload: DisplayPayload }
  | { t: "hello" } // popup -> console: "I just opened, send current"
  | { t: "clear" };

const LS_POPOUT = "mortimer.display.popout";

let channel: BroadcastChannel | null = null;
function getChannel(): BroadcastChannel {
  if (!channel) channel = new BroadcastChannel(DISPLAY_CHANNEL);
  return channel;
}

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
  try {
    getChannel().postMessage({ t: "payload", payload } satisfies DisplayMessage);
  } catch {
    /* BroadcastChannel unavailable (very old browser) — in-page still works */
  }
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
 * the console mounts) — idempotent-ish via a module-level guard. */
let consoleWired = false;
export function wireConsoleSide(): () => void {
  if (consoleWired) return () => {};
  consoleWired = true;
  const ch = getChannel();
  const onMessage = (e: MessageEvent<DisplayMessage>) => {
    if (e.data?.t === "hello" && latest) {
      ch.postMessage({ t: "payload", payload: latest } satisfies DisplayMessage);
    }
  };
  ch.addEventListener("message", onMessage);
  return () => {
    ch.removeEventListener("message", onMessage);
    consoleWired = false;
  };
}

// --- popup side ------------------------------------------------------------

/** Popup side: subscribe. Posts {t:"hello"} once on first subscription so
 * a window opened after a result arrived is not blank (D40). Returns an
 * unsubscribe function. */
export function subscribeDisplay(cb: (m: DisplayMessage) => void): () => void {
  const ch = getChannel();
  const onMessage = (e: MessageEvent<DisplayMessage>) => cb(e.data);
  ch.addEventListener("message", onMessage);
  ch.postMessage({ t: "hello" } satisfies DisplayMessage);
  return () => ch.removeEventListener("message", onMessage);
}

// --- popup lifecycle (console side) ---------------------------------------

let popupRef: Window | null = null;

/** Whether a live popup currently exists — DisplayPanel hides itself while
 * true (D41), since the payload is showing on the other screen. */
export function hasLivePopup(): boolean {
  return popupRef !== null && !popupRef.closed;
}

/** Console side: open (or refocus) the pop-out window. The fixed window
 * NAME is what makes the browser reuse and remember the same window
 * across opens (D41). Returns the window, or null if the browser blocked
 * it — callers MUST handle null and fall back to the in-page window
 * rather than silently losing the payload. */
export function openDisplayWindow(): Window | null {
  if (hasLivePopup()) {
    popupRef!.focus();
    return popupRef;
  }
  // D42 (deferred): a future `placement` argument would consult
  // window.getScreenDetails() here to position on a chosen screen. Today
  // the user drags the popup to the target monitor once and the browser
  // remembers the position for the named window.
  const win = window.open(
    "/display.html",
    "mortimer-display",
    "width=560,height=440,menubar=no,toolbar=no,location=no,status=no",
  );
  popupRef = win;
  return win;
}

export function closeDisplayWindow(): void {
  if (popupRef && !popupRef.closed) popupRef.close();
  popupRef = null;
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
