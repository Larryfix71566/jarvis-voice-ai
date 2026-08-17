import { useEffect, useRef, useState } from "react";
import { usePipecatConversation } from "@pipecat-ai/client-react";
import type { ConversationMessage } from "@pipecat-ai/client-react";
import { getRuns, subscribeRuns, type RunState } from "../agentRuns";

function messageText(message: ConversationMessage): string {
  return message.parts
    .map((part) => {
      if (typeof part.text === "string") return part.text;
      if (part.text && typeof part.text === "object" && "spoken" in part.text) {
        return part.text.spoken;
      }
      return "";
    })
    .join("");
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleTimeString();
}

// Engagement plan E7 — one entry in the merged transcript flow: either a
// spoken message or a run-event chip ("→ Analyst" at start, "✓/✗" at
// completion), ordered by timestamp so the Log tells the session's
// story, not just its words.
type FlowItem =
  | { kind: "message"; at: number; message: ConversationMessage }
  | { kind: "chip"; at: number; label: string; tone: "start" | "ok" | "fail" };

export default function Transcript() {
  const { messages } = usePipecatConversation();
  const [runs, setRuns] = useState<RunState[]>(getRuns);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => subscribeRuns(setRuns), []);

  const visible = messages.filter(
    (m) =>
      (m.role === "user" || m.role === "assistant") &&
      messageText(m).trim() !== "",
  );

  const flow: FlowItem[] = [
    ...visible.map((m): FlowItem => ({
      kind: "message",
      at: new Date(m.createdAt).getTime() || 0,
      message: m,
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
  }, [messages, runs]);

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
            key={`${item.message.createdAt}-${i}`}
            className={
              item.message.role === "user"
                ? "bubble-row bubble-right"
                : "bubble-row bubble-left"
            }
          >
            <div
              className={
                item.message.role === "user" ? "bubble bubble-user" : "bubble bubble-jarvis"
              }
            >
              <div className="bubble-meta">
                {item.message.role === "user" ? "You" : "Mortimer"} ·{" "}
                {formatTime(item.message.createdAt)}
              </div>
              <div className="bubble-text">{messageText(item.message)}</div>
            </div>
          </div>
        ),
      )}
      <div ref={bottomRef} />
    </div>
  );
}
