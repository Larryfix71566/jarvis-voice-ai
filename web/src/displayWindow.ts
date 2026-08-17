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
  | { t: "clear" }
  // Popup presence protocol (2026-08-17): a console reload loses popupRef
  // (module state), which used to make hasLivePopup() report false while
  // the popup was still open — showing the same result in BOTH places.
  // The popup broadcasts a heartbeat; the console tracks its freshness,
  // and hasLivePopup() consults both the ref and the heartbeat.
  | { t: "alive" } // popup -> console: heartbeat, every ALIVE_INTERVAL_MS
  | { t: "bye" } // popup -> console: closing now (pagehide)
  | { t: "close" } // console -> popup: close yourself (ref-less close)
  | { t: "ping" }; // console -> popup: "anyone there?" (fresh console load)

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
    if (e.data?.t === "hello" || e.data?.t === "alive") {
      lastAliveAt = Date.now();
    }
    if (e.data?.t === "bye") {
      lastAliveAt = 0;
    }
  };
  ch.addEventListener("message", onMessage);
  // A console that just loaded has no idea whether a popup from a previous
  // page-load is still open — ask, so the in-page panel can hide within
  // one round-trip instead of waiting out a heartbeat interval.
  ch.postMessage({ t: "ping" } satisfies DisplayMessage);
  return () => {
    ch.removeEventListener("message", onMessage);
    consoleWired = false;
  };
}

// --- popup side ------------------------------------------------------------

/** Popup side: subscribe. Posts {t:"hello"} once on first subscription so
 * a window opened after a result arrived is not blank (D40). Also runs the
 * presence protocol: an {t:"alive"} heartbeat while open, {t:"bye"} on
 * pagehide, and self-close on a console {t:"close"} — so a console that
 * reloaded (and lost its window ref) still knows this popup exists and can
 * still close it. Returns an unsubscribe function. */
export function subscribeDisplay(cb: (m: DisplayMessage) => void): () => void {
  const ch = getChannel();
  const onMessage = (e: MessageEvent<DisplayMessage>) => {
    if (e.data?.t === "close") {
      window.close(); // script-opened window: self-close is permitted
      return;
    }
    if (e.data?.t === "ping") {
      ch.postMessage({ t: "alive" } satisfies DisplayMessage);
      return;
    }
    cb(e.data);
  };
  ch.addEventListener("message", onMessage);
  ch.postMessage({ t: "hello" } satisfies DisplayMessage);
  const heartbeat = window.setInterval(() => {
    ch.postMessage({ t: "alive" } satisfies DisplayMessage);
  }, ALIVE_INTERVAL_MS);
  const onPageHide = () => {
    ch.postMessage({ t: "bye" } satisfies DisplayMessage);
  };
  window.addEventListener("pagehide", onPageHide);
  return () => {
    ch.removeEventListener("message", onMessage);
    window.clearInterval(heartbeat);
    window.removeEventListener("pagehide", onPageHide);
  };
}

// --- popup lifecycle (console side) ---------------------------------------

let popupRef: Window | null = null;

// Presence protocol timing: the popup heartbeats every 2s; the console
// treats it as live while the last beat is fresher than 2.5 intervals —
// tolerant of one dropped message, still fast enough that a killed popup
// brings the in-page fallback back within ~5s (DisplayPanel's 1s poll
// re-evaluates hasLivePopup continuously).
const ALIVE_INTERVAL_MS = 2000;
const ALIVE_STALE_MS = ALIVE_INTERVAL_MS * 2.5;
let lastAliveAt = 0;

// --- D42 implemented (2026-08-17): auto-place the popup on the extended
// screen when one is available, and move it there when one is added.
// Uses the Window Management API (Chromium; permission is prompted on
// first use — safe here because openDisplayWindow always runs inside the
// ⧉ button's user gesture). Firefox/Safari lack the API: feature-detect
// and fall back to today's behavior (user drags once, the named window
// remembers its position).

interface ScreenDetailedLike {
  availLeft: number;
  availTop: number;
  availWidth: number;
  availHeight: number;
  isPrimary: boolean;
}
interface ScreenDetailsLike {
  screens: ScreenDetailedLike[];
  currentScreen: ScreenDetailedLike;
  addEventListener(type: "screenschange", cb: () => void): void;
  removeEventListener(type: "screenschange", cb: () => void): void;
}

let screenDetails: ScreenDetailsLike | null = null;
let screensChangeWired = false;

/** The "extra" screen = any screen that is not the one hosting the console. */
function extendedScreen(details: ScreenDetailsLike): ScreenDetailedLike | null {
  return details.screens.find((s) => s !== details.currentScreen) ?? null;
}

function moveToScreen(win: Window, s: ScreenDetailedLike): void {
  try {
    win.moveTo(s.availLeft, s.availTop);
    win.resizeTo(s.availWidth, s.availHeight);
  } catch {
    /* browser refused the move — user can still drag manually */
  }
}

function wireScreensChange(details: ScreenDetailsLike): void {
  if (screensChangeWired) return;
  screensChangeWired = true;
  details.addEventListener("screenschange", () => {
    // A monitor was added (or removed). If the popup is live and an
    // extended screen now exists, move the popup onto it.
    if (!hasLivePopup()) return;
    const target = extendedScreen(details);
    if (target) moveToScreen(popupRef!, target);
  });
}

/** Best-effort async placement — never blocks or fails the open. */
function placeOnExtendedScreen(win: Window): void {
  const getDetails = (
    window as unknown as { getScreenDetails?: () => Promise<ScreenDetailsLike> }
  ).getScreenDetails;
  if (typeof getDetails !== "function") return; // API absent — fall back
  const placed = (details: ScreenDetailsLike) => {
    screenDetails = details;
    wireScreensChange(details);
    const target = extendedScreen(details);
    if (target && !win.closed) moveToScreen(win, target);
  };
  if (screenDetails) {
    placed(screenDetails);
    return;
  }
  getDetails
    .call(window)
    .then(placed)
    .catch(() => {
      /* permission denied — popup stays where the browser put it */
    });
}

/** Whether a live popup currently exists — DisplayPanel hides itself while
 * true (D41), since the payload is showing on the other screen. Consults
 * BOTH the window ref (this tab opened it) and the heartbeat (it was
 * opened before this console loaded — a reload loses the ref, and without
 * the heartbeat the same result would show in both places). */
export function hasLivePopup(): boolean {
  if (popupRef !== null && !popupRef.closed) return true;
  return lastAliveAt > 0 && Date.now() - lastAliveAt < ALIVE_STALE_MS;
}

/** Console side: open (or refocus) the pop-out window. The fixed window
 * NAME is what makes the browser reuse and remember the same window
 * across opens (D41). Returns the window, or null if the browser blocked
 * it — callers MUST handle null and fall back to the in-page window
 * rather than silently losing the payload. */
export function openDisplayWindow(): Window | null {
  if (hasLivePopup()) {
    // A popup alive only via heartbeat (console reloaded, ref lost):
    // recover the ref through named-window reuse — an empty URL returns
    // the existing window WITHOUT navigating/reloading it.
    if (popupRef === null || popupRef.closed) {
      popupRef = window.open("", "mortimer-display");
    }
    if (popupRef && !popupRef.closed) {
      popupRef.focus();
      // Re-run placement on every open request, not just the first: an
      // already-open popup sitting on the console's screen is exactly
      // the case "move it to the extra monitor" needs to handle.
      placeOnExtendedScreen(popupRef);
    }
    return popupRef;
  }
  const win = window.open(
    "/display.html",
    "mortimer-display",
    "width=560,height=440,menubar=no,toolbar=no,location=no,status=no",
  );
  popupRef = win;
  // D42: by default the popup lands on the extended screen when one is
  // available (and follows one added later, via screenschange). Async and
  // best-effort — a browser without the API or a denied permission leaves
  // the popup exactly where today's behavior put it.
  if (win) placeOnExtendedScreen(win);
  return win;
}

export function closeDisplayWindow(): void {
  if (popupRef && !popupRef.closed) popupRef.close();
  popupRef = null;
  // Ref-less close: a popup surviving a console reload has no popupRef,
  // but it obeys {t:"close"} over the channel (it self-closes — permitted
  // because it is a script-opened window).
  try {
    getChannel().postMessage({ t: "close" } satisfies DisplayMessage);
  } catch {
    /* channel unavailable — nothing left to close remotely */
  }
  lastAliveAt = 0;
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
