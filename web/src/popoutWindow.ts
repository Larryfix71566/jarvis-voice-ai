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

// Shell zombie-webview fix (2026-08-18): after a {t:"close"} command, a
// shell popup waits this long, then goes silent only if its document
// actually went hidden (i.e. the native close visibly worked). The
// shell closes windows same-millisecond per its own log, so 1.5s is
// generous; a close that failed leaves the page visible and beating.
const CLOSE_CONFIRM_DELAY_MS = 1500;

// S3: verified (not assumed) popout success. window.open()'s return
// value is uninformative in two failure-shaped-like-success cases:
// inside the shell it is ALWAYS null by design (the shell branch hands
// off to native code), and in a plain browser a popup-blocker rejection
// also returns null — same value, opposite meanings. confirmPopout
// resolves the ambiguity by polling isAlive() (window ref OR heartbeat)
// until it reports true or the timeout elapses. Every open path (button
// and voice, display and drawer) must go through this rather than
// branching on `win !== null`.
const POPOUT_CONFIRM_TIMEOUT_MS = 5000;
const POPOUT_CONFIRM_POLL_MS = 200;

export function confirmPopout(
  isAlive: () => boolean,
  timeoutMs: number = POPOUT_CONFIRM_TIMEOUT_MS,
): Promise<boolean> {
  if (isAlive()) return Promise.resolve(true);
  return new Promise((resolve) => {
    const deadline = Date.now() + timeoutMs;
    const tick = () => {
      if (isAlive()) {
        resolve(true);
        return;
      }
      if (Date.now() >= deadline) {
        resolve(false);
        return;
      }
      setTimeout(tick, POPOUT_CONFIRM_POLL_MS);
    };
    tick();
  });
}

/** A human-readable reason for a confirmed popout failure,
 * distinguishing the shell (something is wrong natively — check its
 * logs) from a plain browser (almost certainly the popup blocker) so
 * the spoken/inline message points at the right fix. */
export function describePopoutFailure(): string {
  const inShell = Boolean((window as unknown as { mortimerShell?: unknown }).mortimerShell);
  return inShell
    ? "The panel window didn't open — check the shell logs."
    : "The browser blocked the popup — allow pop-ups for this page and try again.";
}

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
    const inShell = Boolean((window as unknown as { mortimerShell?: unknown }).mortimerShell);

    // Zombie-webview handling (2026-08-18, confirmed via the
    // com.mortimer.shell log): SwiftUI keeps a closed Window scene's
    // content — this webview and its timers — ALIVE after
    // NSWindow.close(). pagehide never fires, so the old unconditional
    // heartbeat kept claiming presence from inside an invisible, closed
    // window, and the console flipped right back to "popped" within a
    // beat of every pop-in. The heartbeat is now start/stoppable; on a
    // {t:"close"} command inside the shell we confirm shortly after
    // that the document actually went hidden (the native close visibly
    // worked) and only then go silent — a close that FAILED leaves the
    // page visible and beating, so the console still flips back
    // honestly. Gating silence on the explicit close command (never on
    // visibilitychange alone) keeps mere occlusion from reading as
    // "closed".
    let heartbeatId: number | null = null;
    const startBeat = () => {
      if (heartbeatId !== null) return;
      heartbeatId = window.setInterval(() => {
        ch.postMessage({ t: "alive" } satisfies PresenceMessage);
      }, ALIVE_INTERVAL_MS);
    };
    const stopBeat = () => {
      if (heartbeatId === null) return;
      window.clearInterval(heartbeatId);
      heartbeatId = null;
    };
    // Re-popout after a shell pop-in re-shows this SAME kept-alive
    // webview — resume presence when it becomes visible again (the
    // hello also triggers the console's snapshot replay).
    const onVisibility = () => {
      if (document.visibilityState === "visible" && heartbeatId === null) {
        ch.postMessage({ t: "hello" } satisfies PresenceMessage);
        startBeat();
      }
    };

    const onEvent = (e: MessageEvent<M | PresenceMessage>) => {
      const data = e.data as { t?: string };
      if (data?.t === "close") {
        window.close(); // browser: permitted; shell: a no-op
        if (inShell) {
          window.setTimeout(() => {
            if (document.visibilityState === "hidden") {
              ch.postMessage({ t: "bye" } satisfies PresenceMessage);
              stopBeat();
            }
          }, CLOSE_CONFIRM_DELAY_MS);
        }
        return;
      }
      if (data?.t === "ping") {
        // A silenced zombie must not answer a fresh console's ping and
        // resurrect presence — only reply while actively beating.
        if (heartbeatId !== null) {
          ch.postMessage({ t: "alive" } satisfies PresenceMessage);
        }
        return;
      }
      onMessage(e.data);
    };
    ch.addEventListener("message", onEvent);
    if (inShell) document.addEventListener("visibilitychange", onVisibility);
    ch.postMessage({ t: "hello" } satisfies PresenceMessage);
    startBeat();
    const onPageHide = () => {
      ch.postMessage({ t: "bye" } satisfies PresenceMessage);
    };
    window.addEventListener("pagehide", onPageHide);
    return () => {
      ch.removeEventListener("message", onEvent);
      if (inShell) document.removeEventListener("visibilitychange", onVisibility);
      stopBeat();
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
      // S1 (MORTIMER_SHELL_FIX_AND_SCREEN_VISION_PLAN.md): the native
      // side (ShellController.openWindow / ShellWindowKind) only
      // recognizes the bare role — "display" | "drawer" | "console" —
      // NOT the browser window name passed in as `windowName`
      // ("mortimer-display" / "mortimer-drawer"). Sending `windowName`
      // was the exact cause of the shell's popout doing nothing on its
      // first real test: ShellWindowKind(rawValue:) failed to parse and
      // the bridge's ignore-unknown design swallowed it with no error
      // anywhere. `entry.role` is the contract — do not reintroduce
      // `windowName` here.
      handler?.postMessage({ cmd: "openWindow", name: entry.role });
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
    // Shell branch (2026-08-18): inside the shell, entry.win is ALWAYS
    // null (open() returned null by design) so the ref-based close does
    // nothing, and a WKWebView hosted by a native window cannot
    // window.close() itself. Ask the native side to close it instead,
    // same bare-role contract as openWindow (see the S1 comment above).
    const shell = (window as unknown as { mortimerShell?: { version: number } }).mortimerShell;
    if (shell) {
      const handler = (
        window as unknown as {
          webkit?: { messageHandlers?: { mortimer?: { postMessage(msg: unknown): void } } };
        }
      ).webkit?.messageHandlers?.mortimer;
      handler?.postMessage({ cmd: "closeWindow", name: entry.role });
      // Also broadcast: the popup uses {t:"close"} as the explicit
      // signal to confirm-hidden-then-go-silent (the zombie-webview fix
      // in wirePopupSide — SwiftUI keeps the closed window's webview
      // alive, so pagehide never fires and the heartbeat would
      // otherwise run forever inside an invisible window).
      postMessage({ t: "close" } satisfies PresenceMessage);
      entry.win = null;
      // Deliberately do NOT zero lastAliveAt: if the native close
      // fails, the popup stays visible and keeps beating, so presence
      // honestly flips the UI back (S3's honesty rule). On success the
      // popup's confirm-hidden logic sends {t:"bye"} and stops beating.
      return;
    }
    if (entry.win && !entry.win.closed) entry.win.close();
    entry.win = null;
    postMessage({ t: "close" } satisfies PresenceMessage);
    entry.lastAliveAt = 0;
  }

  return { name, postMessage, wireConsoleSide, wirePopupSide, isAlive, open, close };
}
