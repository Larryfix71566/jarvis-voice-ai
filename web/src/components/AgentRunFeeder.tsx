import { RTVIEvent } from "@pipecat-ai/client-js";
import { useRTVIClientEvent } from "@pipecat-ai/client-react";
import { applyServerMessage } from "../agentRuns";

/**
 * AgentRunFeeder — headless. Renders nothing.
 *
 * Larry 2026-08-18: this was AgentStatusPanel, which both owned the RTVI
 * subscription AND drew the floating agent cards over the stage. The
 * cards moved into the drawer's Agents tab (AgentsTab.tsx); the
 * subscription had to stay exactly where it was, because this component
 * is the SINGLE registrant of the ServerMessage listener that feeds
 * agentRuns.ts (plan D10 — two listeners for the same type is the bug
 * that rule exists to prevent), and it is always mounted whereas drawer
 * tab bodies unmount on every tab switch. Same shape as App.tsx's
 * ConversationFeeder: subscribe, push into the module store, render null.
 *
 * Stale-run cleanup that used to live here went with the cards: it only
 * existed to expire anchored cards after DONE_FADE_MS (plan D8), and the
 * Agents tab deliberately keeps settled runs visible until dismissed.
 */
export default function AgentRunFeeder() {
  useRTVIClientEvent(RTVIEvent.ServerMessage, applyServerMessage);
  return null;
}
