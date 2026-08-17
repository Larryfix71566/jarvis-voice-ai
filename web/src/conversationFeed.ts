/**
 * conversationFeed — module-level store for the spoken conversation log
 * (MORTIMER_DRAWER_POPOUT_PLAN.md DP4).
 *
 * Transcript.tsx used to call usePipecatConversation() directly — a
 * session hook that only works inside a PipecatClientProvider, i.e. only
 * in the main console. That made the Log tab unusable in a popped-out
 * drawer window, which has (and must never construct) a session.
 *
 * This store follows the exact publish/subscribe shape agentRuns.ts
 * established: a headless component in App.tsx (the ONE remaining
 * usePipecatConversation consumer) feeds every new message in here via
 * _pushMessage, and Transcript.tsx reads from the store instead. Bounded
 * at 200 entries — same "bounded, oldest-dropped-first" discipline as
 * agentRuns.ts's MAX_DEVELOPER_RUNS and displayResults.ts's
 * MAX_DISPLAY_RESULTS.
 *
 * The console also relays every pushed message onto the drawer's
 * BroadcastChannel (App.tsx's drawer relay module) so a popped-out drawer
 * window's OWN copy of this store — fed by relayed events rather than by
 * usePipecatConversation, which it can never call — stays in sync.
 */

/** Minimal shape this store needs from @pipecat-ai/client-react's
 * ConversationMessage — kept narrow so this module has zero dependency on
 * pipecat-client-react (drawerMain.tsx's import graph must never reach
 * it transitively, DP1). Transcript.tsx already only reads these fields. */
export interface ConversationEntry {
  id: string; // createdAt is not guaranteed unique; dedupe key
  role: string;
  createdAt: string;
  text: string;
}

/** ⚙ TUNING KNOB — bounded history; oldest dropped first (DP4). */
export const MAX_CONVERSATION_ENTRIES = 200;

let entries: ConversationEntry[] = [];
export type ConversationListener = (entries: ConversationEntry[]) => void;
const listeners = new Set<ConversationListener>();

function notify(): void {
  const snapshot = entries.slice();
  for (const cb of listeners) cb(snapshot);
}

/** Current entries, oldest first (matches usePipecatConversation's order,
 * which Transcript.tsx already assumed). */
export function getConversation(): ConversationEntry[] {
  return entries.slice();
}

export function subscribeConversation(cb: ConversationListener): () => void {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

/** Feeder-only mutator — called by App.tsx's headless usePipecatConversation
 * consumer with the FULL current message list on every change (matching
 * how usePipecatConversation itself reports state: not incremental). Also
 * called by the drawer window's relay-side apply function with entries
 * decoded from a relayed snapshot/event, so the two contexts share one
 * code path for "what does 'the current conversation' mean". */
export function _setConversation(next: ConversationEntry[]): void {
  entries = next.slice(-MAX_CONVERSATION_ENTRIES);
  notify();
}

export function clearConversation(): void {
  entries = [];
  notify();
}
