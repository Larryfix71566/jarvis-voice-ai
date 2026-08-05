import { useEffect, useRef } from "react";
import { usePipecatConversation } from "@pipecat-ai/client-react";
import type { ConversationMessage } from "@pipecat-ai/client-react";

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

export default function Transcript() {
  const { messages } = usePipecatConversation();
  const bottomRef = useRef<HTMLDivElement | null>(null);

  const visible = messages.filter(
    (m) =>
      (m.role === "user" || m.role === "assistant") &&
      messageText(m).trim() !== "",
  );

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className="transcript">
      {visible.length === 0 && (
        <div className="transcript-empty">
          Transcript will appear here once you start talking.
        </div>
      )}
      {visible.map((m, i) => (
        <div
          key={`${m.createdAt}-${i}`}
          className={
            m.role === "user" ? "bubble-row bubble-right" : "bubble-row bubble-left"
          }
        >
          <div className={m.role === "user" ? "bubble bubble-user" : "bubble bubble-jarvis"}>
            <div className="bubble-meta">
              {m.role === "user" ? "You" : "Jarvis"} · {formatTime(m.createdAt)}
            </div>
            <div className="bubble-text">{messageText(m)}</div>
          </div>
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
