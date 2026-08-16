/**
 * uiCommands — module-level pub/sub for voice UI-control commands
 * (MORTIMER_VOICE_UI_PLAN.md U2).
 *
 * The bot's ui_control tool emits {"type": "ui", "action": ..., "tab"?}
 * app messages. App.tsx's existing ServerMessage listener forwards them
 * here (no new RTVI listener registrations — same filter-by-type
 * coexistence rule as the display listener); each OWNER of a piece of
 * UI state subscribes and applies only the actions it owns, through the
 * exact same setters its buttons call, so voice and click can never
 * diverge:
 *   - App.tsx: drawer_open/drawer_close/drawer_tab, transcript_open/close
 *   - DisplayPanel.tsx: display_popout/display_close/overlay_dismiss
 *   - MicControls.tsx: mic_mute, wake_on/wake_off
 *
 * Commands are EVENTS, not state — no replay for late subscribers, and
 * a command arriving while its owner is unmounted is dropped (nothing
 * to apply it to; the no-op path never fires either, which is correct:
 * an unmounted owner means the surface doesn't exist right now).
 *
 * Publish/subscribe follows the shape established by agentLayout.ts and
 * agentRuns.ts — deliberately not React Context or a state library.
 */

export interface UiCommand {
  action: string;
  tab?: string;
}

type Listener = (cmd: UiCommand) => void;

const listeners = new Set<Listener>();

export function subscribeUiCommands(fn: Listener): () => void {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

/** App.tsx's ServerMessage listener calls this with any {"type": "ui"}
 * message; anything else is ignored here so the call site can forward
 * unconditionally. */
export function applyUiMessage(msg: unknown): void {
  const m = msg as { type?: string; action?: string; tab?: string };
  if (m?.type !== "ui" || typeof m.action !== "string") return;
  const cmd: UiCommand = { action: m.action };
  if (typeof m.tab === "string") cmd.tab = m.tab;
  for (const fn of listeners) fn(cmd);
}
