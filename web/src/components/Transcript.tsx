import { useEffect, useRef, useState } from "react";
import { getRuns, subscribeRuns, type RunState } from "../agentRuns";
import {
  getConversation,
  subscribeConversation,
  type ConversationEntry,
} from "../conversationFeed";

function formatTime(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleTimeString();
}

// Engagement plan E7 — one entry in the merged transcript flow: either a
// spoken message or a run-event chip ("→ Analyst" at start, "✓/✗" at
// completion), ordered by timestamp so the Log tells the session's
// story, not just its words.
//
// DP4: this used to read `usePipecatConversation()` directly — a session
// hook unusable in the popped-out drawer window. It now reads
// conversationFeed.ts's store instead (fed, in the console, by the ONE
// remaining usePipecatConversation consumer in App.tsx; fed, in the
// drawer window, by relayed events) — same content, same ordering, same
// live updates, just a different supply line depending on context.
type FlowItem =
  | { kind: "message"; at: number; entry: ConversationEntry }
  | { kind: "chip"; at: number; label: string; tone: "start" | "ok" | "fail" };

export default function Transcript() {
  const [visible, setVisible] = useState<ConversationEntry[]>(getConversation);
  const [runs, setRuns] = useState<RunState[]>(getRuns);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => subscribeConversation(setVisible), []);
  useEffect(() => subscribeRuns(setRuns), []);

  const flow: FlowItem[] = [
    ...visible.map((m): FlowItem => ({
      kind: "message",
      at: new Date(m.createdAt).getTime() || 0,
      entry: m,
    })),
    ...runs.flatMap((r): FlowItem[] => {
      const items: FlowItem[] = [
        {
          kind: "chip",
          at: r.startedAt,
          label: `→ ${r.displayName}`,
          tone: "start",
        },
      ];
      if (r.doneAt !== null) {
        items.push({
          kind: "chip",
          at: r.doneAt,
          label: `${r.ok ? "✓" : "✗"} ${r.displayName}`,
          tone: r.ok ? "ok" : "fail",
        });
      }
      return items;
    }),
  ].sort((a, b) => a.at - b.at);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [visible, runs]);

  return (
    <div className="transcript">
      {flow.length === 0 && (
        <div className="transcript-empty">
          Transcript will appear here once you start talking.
        </div>
      )}
      {flow.map((item, i) =>
        item.kind === "chip" ? (
          <div
            key={`chip-${item.at}-${i}`}
            className={`transcript-chip transcript-chip-${item.tone}`}
          >
            {item.label}
          </div>
        ) : (
          <div
            key={`${item.entry.id}-${i}`}
            className={
              item.entry.role === "user"
                ? "bubble-row bubble-right"
                : "bubble-row bubble-left"
            }
          >
            <div
              className={
                item.entry.role === "user" ? "bubble bubble-user" : "bubble bubble-jarvis"
              }
            >
              <div className="bubble-meta">
                {item.entry.role === "user" ? "You" : "Mortimer"} ·{" "}
                {formatTime(item.entry.createdAt)}
              </div>
              <div className="bubble-text">{item.entry.text}</div>
            </div>
          </div>
        ),
      )}
      <div ref={bottomRef} />
    </div>
  );
}
