/**
 * popoutWindow.ts — shared pop-out plumbing (MORTIMER_DRAWER_POPOUT_PLAN.md
 * DP2), extracted from displayWindow.ts (which implemented the presence
 * protocol and extended-screen placement first, 2026-08-17/D42).
 *
 * Two callers use this: displayWindow.ts (channel "mortimer.display",
 * window name "mortimer-display" — unchanged from before this extraction)
 * and the new drawer relay (channel "mortimer.drawerwin", window name
 * "mortimer-drawer"). One implementation, two windows — a presence or
 * placement bug can no longer exist in only one of them.
 *
 * Exposes:
 *   - createPopoutChannel(name, role) — BroadcastChannel + presence
 *     protocol (hello/alive/bye/close/ping), ref-recovery via named-window
 *     reuse, and open/close/isAlive, returned as one object per channel.
 *   - placeOnExtendedScreen(win, slot) — Window Management API placement
 *     for a single window against the first extended screen.
 *   - DP8 slot placement: a module-level registry of every live popout
 *     (keyed by channel name) recomputes both popouts' slots on every
 *     open — see repositionAll() below, called from PopoutChannel.open().
 */

export type Slot = "fill" | "left" | "right";
export type PopoutRole = "display" | "drawer";

export type PresenceMessage =
  | { t: "hello" } // popup -> console: "I just opened, send current"
  | { t: "alive" } // popup -> console: heartbeat, every ALIVE_INTERVAL_MS
  | { t: "bye" } // popup -> console: closing now (pagehide)
  | { t: "close" } // console -> popup: close yourself (ref-less close)
  | { t: "ping" }; // console -> popup: "anyone there?" (fresh console load)

function isPresenceType(t: string): t is PresenceMessage["t"] {
  return t === "hello" || t === "alive" || t === "bye" || t === "close" || t === "ping";
}

// Presence protocol timing: the popup heartbeats every 2s; the console
// treats it as live while the last beat is fresher than 2.5 intervals —
// tolerant of one dropped message, still fast enough that a killed popup
// brings the in-page fallback back within ~5s.
const ALIVE_INTERVAL_MS = 2000;
const ALIVE_STALE_MS = ALIVE_INTERVAL_MS * 2.5;

// --- DP8: shared registry of every live popout, across both channels ------
//
// Keyed by BroadcastChannel name. `win` is only present on the console tab
// that opened (or recovered the ref to) the popup. Slot placement needs to
// know about BOTH popouts to split the screen, which is exactly why this
// lives at module scope rather than inside one PopoutChannel closure.

interface RegistryEntry {
  role: PopoutRole;
  win: Window | null;
  lastAliveAt: number;
}

const registry = new Map<string, RegistryEntry>();

function entryFor(name: string, role: PopoutRole): RegistryEntry {
  let e = registry.get(name);
  if (!e) {
    e = { role, win: null, lastAliveAt: 0 };
    registry.set(name, e);
  }
  return e;
}

function liveEntries(): RegistryEntry[] {
  return [...registry.values()].filter(
    (e) => (e.win !== null && !e.win.closed) || (e.lastAliveAt > 0 && Date.now() - e.lastAliveAt < ALIVE_STALE_MS),
  );
}

// --- Window Management API placement (D42, generalized here for DP8) ------

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

/** Every screen that is not the one hosting the console, in stable order. */
function extendedScreens(details: ScreenDetailsLike): ScreenDetailedLike[] {
  return details.screens.filter((s) => s !== details.currentScreen);
}

function slotGeometry(screen: ScreenDetailedLike, slot: Slot): {
  x: number; y: number; w: number; h: number;
} {
  if (slot === "left") {
    return { x: screen.availLeft, y: screen.availTop, w: screen.availWidth * 0.6, h: screen.availHeight };
  }
  if (slot === "right") {
    return {
      x: screen.availLeft + screen.availWidth * 0.6,
      y: screen.availTop,
      w: screen.availWidth * 0.4,
      h: screen.availHeight,
    };
  }
  return { x: screen.availLeft, y: screen.availTop, w: screen.availWidth, h: screen.availHeight };
}

function moveToSlot(win: Window, screen: ScreenDetailedLike, slot: Slot): void {
  try {
    const g = slotGeometry(screen, slot);
    win.moveTo(g.x, g.y);
    win.resizeTo(g.w, g.h);
  } catch {
    /* browser refused the move — user can still drag manually */
  }
}

/** Best-effort, single-window placement against the first extended screen
 * (the common one-extra-monitor case). Exported per DP2's spec; the DP8
 * two-popout split and the >2-screen case are computed by repositionAll()
 * below, which calls this same geometry helper with an explicit screen. */
export function placeOnExtendedScreen(win: Window, slot: Slot): void {
  // B3 — inside the shell, native Swift code applies DP8's placement
  // semantics directly against NSScreen; the web-side Window Management
  // API path must never also run, or the two would race/double-place.
  if ((window as unknown as { mortimerShell?: unknown }).mortimerShell) return;
  const getDetails = (
    window as unknown as { getScreenDetails?: () => Promise<ScreenDetailsLike> }
  ).getScreenDetails;
  if (typeof getDetails !== "function") return; // API absent — fall back
  const placed = (details: ScreenDetailsLike) => {
    screenDetails = details;
    wireScreensChange(details);
    const target = extendedScreens(details)[0];
    if (target && !win.closed) moveToSlot(win, target, slot);
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

/** DP8 — recompute placement for every currently-live popout. Called
 * whenever a popout opens (so opening the second one repositions the
 * first) and on screenschange (so a monitor added later picks it up). */
function repositionAll(details: ScreenDetailsLike): void {
  const ext = extendedScreens(details);
  if (ext.length === 0) return; // no extra monitor — nothing to place

  const live = liveEntries().filter((e) => e.win !== null && !e.win.closed);
  if (live.length === 0) return;

  if (live.length === 1) {
    moveToSlot(live[0].win!, ext[0], "fill");
    return;
  }

  // Both display and drawer are live. DP8: display gets the first extended
  // screen, drawer the second if one exists; otherwise both split the one
  // extended screen (display left 60%, drawer right 40%).
  const display = live.find((e) => e.role === "display");
  const drawer = live.find((e) => e.role === "drawer");
  if (ext.length >= 2) {
    if (display) moveToSlot(display.win!, ext[0], "fill");
    if (drawer) moveToSlot(drawer.win!, ext[1], "fill");
  } else {
    if (display) moveToSlot(display.win!, ext[0], "left");
    if (drawer) moveToSlot(drawer.win!, ext[0], "right");
  }
}

function wireScreensChange(details: ScreenDetailsLike): void {
  if (screensChangeWired) return;
  screensChangeWired = true;
  details.addEventListener("screenschange", () => repositionAll(details));
}

function repositionAllBestEffort(): void {
  const getDetails = (
    window as unknown as { getScreenDetails?: () => Promise<ScreenDetailsLike> }
  ).getScreenDetails;
  if (typeof getDetails !== "function") return;
  const run = (details: ScreenDetailsLike) => {
    screenDetails = details;
    wireScreensChange(details);
    repositionAll(details);
  };
  if (screenDetails) {
    run(screenDetails);
    return;
  }
  getDetails.call(window).then(run).catch(() => {
    /* permission denied — popups stay where the browser put them */
  });
}

// --- PopoutChannel ----------------------------------------------------------

export interface PopoutChannel<M> {
  readonly name: string;
  /** Console or popup side: post any domain message (or a presence
   * message, though the protocol methods below normally handle those). */
  postMessage(msg: M | PresenceMessage): void;
  /** Console side: install the message listener. Presence types (hello/
   * alive/bye) update the live-tracking state internally AND are still
   * forwarded to `onMessage` so the caller can reply to a hello with a
   * domain snapshot. Also pings once on wire-up, so a console that just
   * reloaded finds out within one round-trip whether a popup from a
   * previous load is still open. Idempotent per instance (a second call
   * is a no-op until the first is torn down). Returns an unsubscribe fn. */
  wireConsoleSide(onMessage: (m: M | PresenceMessage) => void): () => void;
  /** Popup side: subscribe and run the full presence protocol — hello
   * once on mount, a heartbeat while open, bye on pagehide, and self-close
   * on a console {t:"close"} (permitted for a script-opened window). Domain
   * messages (and hello/ping's raw form) are forwarded to `onMessage`.
   * Returns an unsubscribe function. */
  wirePopupSide(onMessage: (m: M | PresenceMessage) => void): () => void;
  /** Console side: true if a popup is live, via either the window ref
   * (this tab opened it) or a fresh heartbeat (opened before this console
   * loaded, e.g. before a reload lost the ref). */
  isAlive(): boolean;
  /** Console side: open (or refocus) the popout window, named `windowName`
   * so the browser reuses/remembers it across opens. Re-runs DP8 slot
   * placement for every live popout (this one and its sibling) on every
   * call — an already-open popout gets moved, not just a freshly-opened
   * one. Returns the window, or null if the browser blocked it. */
  open(url: string, windowName: string, features: string): Window | null;
  /** Console side: close the popup (ref-based, and ref-less via the
   * {t:"close"} broadcast for a popup that outlived a console reload). */
  close(): void;
}

/** Parameterized BroadcastChannel + presence-protocol wrapper (DP2).
 * `role` feeds DP8's slot assignment (display=left/first-extra-screen,
 * drawer=right/second-extra-screen) — it does not affect anything else. */
export function createPopoutChannel<M>(name: string, role: PopoutRole): PopoutChannel<M> {
  let channel: BroadcastChannel | null = null;
  function getChannel(): BroadcastChannel {
    if (!channel) channel = new BroadcastChannel(name);
    return channel;
  }

  const entry = entryFor(name, role);
  let consoleWired = false;

  function postMessage(msg: M | PresenceMessage): void {
    try {
      getChannel().postMessage(msg);
    } catch {
      /* BroadcastChannel unavailable (very old browser) */
    }
  }

  function isAlive(): boolean {
    if (entry.win !== null && !entry.win.closed) return true;
    return entry.lastAliveAt > 0 && Date.now() - entry.lastAliveAt < ALIVE_STALE_MS;
  }

  function wireConsoleSide(onMessage: (m: M | PresenceMessage) => void): () => void {
    if (consoleWired) return () => {};
    consoleWired = true;
    const ch = getChannel();
    const onEvent = (e: MessageEvent<M | PresenceMessage>) => {
      const data = e.data as { t?: string };
      if (typeof data?.t === "string" && isPresenceType(data.t)) {
        if (data.t === "hello" || data.t === "alive") entry.lastAliveAt = Date.now();
        if (data.t === "bye") entry.lastAliveAt = 0;
      }
      onMessage(e.data);
    };
    ch.addEventListener("message", onEvent);
    ch.postMessage({ t: "ping" } satisfies PresenceMessage);
    return () => {
      ch.removeEventListener("message", onEvent);
      consoleWired = false;
    };
  }

  function wirePopupSide(onMessage: (m: M | PresenceMessage) => void): () => void {
    const ch = getChannel();
    const onEvent = (e: MessageEvent<M | PresenceMessage>) => {
      const data = e.data as { t?: string };
      if (data?.t === "close") {
        window.close(); // script-opened window: self-close is permitted
        return;
      }
      if (data?.t === "ping") {
        ch.postMessage({ t: "alive" } satisfies PresenceMessage);
        return;
      }
      onMessage(e.data);
    };
    ch.addEventListener("message", onEvent);
    ch.postMessage({ t: "hello" } satisfies PresenceMessage);
    const heartbeat = window.setInterval(() => {
      ch.postMessage({ t: "alive" } satisfies PresenceMessage);
    }, ALIVE_INTERVAL_MS);
    const onPageHide = () => {
      ch.postMessage({ t: "bye" } satisfies PresenceMessage);
    };
    window.addEventListener("pagehide", onPageHide);
    return () => {
      ch.removeEventListener("message", onEvent);
      window.clearInterval(heartbeat);
      window.removeEventListener("pagehide", onPageHide);
    };
  }

  function open(url: string, windowName: string, features: string): Window | null {
    // B2 (MORTIMER_MODEL_DISCIPLINE_AND_MAC_SHELL_PLAN.md): inside the
    // Mortimer shell, a WKUserScript injects window.mortimerShell at
    // documentStart before any app code runs. The shell owns opening and
    // placing its own native Display/Drawer windows — posting through the
    // injected message handler and returning null here means voice's
    // display_popout/drawer_popout paths (which only check the return
    // value via isAlive()'s heartbeat-based presence, unchanged since the
    // console-reload fix) keep working with no Window ref at all. A plain
    // browser has no window.mortimerShell, so this branch is dead there —
    // existing behavior is untouched.
    const shell = (window as unknown as { mortimerShell?: { version: number } }).mortimerShell;
    if (shell) {
      const handler = (
        window as unknown as {
          webkit?: { messageHandlers?: { mortimer?: { postMessage(msg: unknown): void } } };
        }
      ).webkit?.messageHandlers?.mortimer;
      handler?.postMessage({ cmd: "openWindow", name: windowName });
      return null;
    }
    if (isAlive()) {
      // A popup alive only via heartbeat (console reloaded, ref lost):
      // recover the ref through named-window reuse — an empty URL returns
      // the existing window WITHOUT navigating/reloading it.
      if (entry.win === null || entry.win.closed) {
        entry.win = window.open("", windowName);
      }
      if (entry.win && !entry.win.closed) {
        entry.win.focus();
      }
      repositionAllBestEffort();
      return entry.win;
    }
    const win = window.open(url, windowName, features);
    entry.win = win;
    if (win) repositionAllBestEffort();
    return win;
  }

  function close(): void {
    if (entry.win && !entry.win.closed) entry.win.close();
    entry.win = null;
    postMessage({ t: "close" } satisfies PresenceMessage);
    entry.lastAliveAt = 0;
  }

  return { name, postMessage, wireConsoleSide, wirePopupSide, isAlive, open, close };
}
