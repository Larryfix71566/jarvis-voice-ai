/**
 * drawerRelay.ts — console <-> drawer-window plumbing
 * (MORTIMER_DRAWER_POPOUT_PLAN.md DP3/DP6), built on the shared
 * popoutWindow.ts (DP2) the same way displayWindow.ts is.
 *
 * The drawer's Repo/Edit/Memory/Runs tabs fetch the admin sidecar
 * directly and need no relay (DP3). The Dev tab (agentRuns.ts), Output
 * tab (displayResults.ts), and Log tab (conversationFeed.ts) are all fed,
 * in the console, by a single RTVI listener each (or, for the Log, the
 * one usePipecatConversation consumer) — this module is the ONE place
 * that republishes their changes onto the drawer channel, and the ONE
 * place that applies relayed events into those same stores' relay
 * setters on the popped side. `wireDrawerConsoleSide()` also implements
 * the replay handshake: on a drawer-window `hello`, it sends full current
 * snapshots of all three stores, mirroring displayWindow.ts's D40
 * pattern, so a window opened mid-session is never blank.
 *
 * Also carries the DP6 ui_control forwarding branch: while the drawer
 * window is live, `drawer_open`/`drawer_tab` voice commands are forwarded
 * here (from uiCommands.ts) instead of being applied in-page.
 */

import { applyRelayedRuns, getRuns, subscribeRuns, type RunState } from "./agentRuns";
import {
  applyRelayedResults,
  getResults,
  subscribeResults,
  type DisplayResult,
} from "./displayResults";
import {
  _setConversation,
  getConversation,
  subscribeConversation,
  type ConversationEntry,
} from "./conversationFeed";
import { createPopoutChannel, type PresenceMessage } from "./popoutWindow";
import type { UiCommand } from "./uiCommands";

export const DRAWER_CHANNEL = "mortimer.drawerwin";
const DRAWER_WINDOW_NAME = "mortimer-drawer";
const LS_DRAWERWIN_POPOUT = "mortimer.drawerwin.popout";

type DrawerDomainMessage =
  | { t: "runs"; runs: RunState[] }
  | { t: "results"; results: DisplayResult[] }
  | { t: "conversation"; entries: ConversationEntry[] }
  | { t: "ui"; action: string; tab?: string };

const channel = createPopoutChannel<DrawerDomainMessage>(DRAWER_CHANNEL, "drawer");

// --- console side ------------------------------------------------------

let consoleWired = false;

/** Console side: wires the three store relays plus the replay handshake.
 * Idempotent (guarded like displayWindow.ts's wireConsoleSide) — call
 * once from App.tsx. Returns an unsubscribe function. */
export function wireDrawerConsoleSide(): () => void {
  if (consoleWired) return () => {};
  consoleWired = true;

  const unsubMsg = channel.wireConsoleSide((m) => {
    const data = m as PresenceMessage;
    if (data.t === "hello") {
      channel.postMessage({ t: "runs", runs: getRuns() });
      channel.postMessage({ t: "results", results: getResults() });
      channel.postMessage({ t: "conversation", entries: getConversation() });
    }
  });
  const unsubRuns = subscribeRuns((runs) => channel.postMessage({ t: "runs", runs }));
  const unsubResults = subscribeResults((results) =>
    channel.postMessage({ t: "results", results }),
  );
  const unsubConvo = subscribeConversation((entries) =>
    channel.postMessage({ t: "conversation", entries }),
  );

  return () => {
    unsubMsg();
    unsubRuns();
    unsubResults();
    unsubConvo();
    consoleWired = false;
  };
}

export function hasLiveDrawerWindow(): boolean {
  return channel.isAlive();
}

/** Console side: open (or refocus/re-place) the drawer window. */
export function openDrawerWindow(): Window | null {
  return channel.open(
    "/drawer.html",
    DRAWER_WINDOW_NAME,
    "width=760,height=640,menubar=no,toolbar=no,location=no,status=no",
  );
}

export function closeDrawerWindow(): void {
  channel.close();
}

/** DP6 — called by uiCommands.ts's applyUiMessage for drawer_open/
 * drawer_tab when the drawer window is live, instead of notifying the
 * in-page listeners. */
export function forwardUiCommand(cmd: UiCommand): void {
  channel.postMessage({ t: "ui", action: cmd.action, tab: cmd.tab });
}

// --- popout preference (DP9, same guarded try/catch discipline) --------

export function readDrawerPopoutPreference(): boolean {
  try {
    return localStorage.getItem(LS_DRAWERWIN_POPOUT) === "true";
  } catch {
    return false;
  }
}

export function writeDrawerPopoutPreference(on: boolean): void {
  try {
    localStorage.setItem(LS_DRAWERWIN_POPOUT, String(on));
  } catch {
    /* storage unavailable — preference is simply not persisted */
  }
}

// --- drawer-window side --------------------------------------------------

/** Popup side: subscribe to relayed store updates and forwarded ui
 * commands. `onUi` is called for forwarded drawer_open/drawer_tab
 * commands; the three stores are applied directly via their relay
 * setters (no callback needed — DrawerWindowApp's tab components already
 * read those stores reactively). Returns an unsubscribe function. */
export function wireDrawerWindowSide(onUi: (action: string, tab?: string) => void): () => void {
  return channel.wirePopupSide((m) => {
    const msg = m as DrawerDomainMessage;
    if (msg.t === "runs") applyRelayedRuns(msg.runs);
    else if (msg.t === "results") applyRelayedResults(msg.results);
    else if (msg.t === "conversation") _setConversation(msg.entries);
    else if (msg.t === "ui") onUi(msg.action, msg.tab);
  });
}
