import { useState } from "react";
import { RTVIEvent } from "@pipecat-ai/client-js";
import { useRTVIClientEvent } from "@pipecat-ai/client-react";

interface AgentMsg {
  type?: string;
  name?: string;
  state?: string;
}

interface HistoryEntry {
  name: string;
  at: string;
}

const MAX_HISTORY = 5;

function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export default function AgentActivity() {
  const [working, setWorking] = useState<string | null>(null);
  const [history, setHistory] = useState<HistoryEntry[]>([]);

  useRTVIClientEvent(RTVIEvent.ServerMessage, (data: unknown) => {
    const msg = data as AgentMsg;
    if (msg?.type !== "agent" || typeof msg.name !== "string") return;
    const name = capitalize(msg.name);
    if (msg.state === "working") {
      setWorking(name);
    } else if (msg.state === "done") {
      setWorking((cur) => (cur === name ? null : cur));
      setHistory((h) =>
        [{ name, at: new Date().toLocaleTimeString() }, ...h].slice(0, MAX_HISTORY),
      );
    }
  });

  return (
    <div className="agent-activity">
      <div className="panel-title">Agent Activity</div>
      {working ? (
        <div className="agent-chip">⚙ {working} working…</div>
      ) : (
        <div className="agent-chip agent-chip-idle">Idle</div>
      )}
      <ul className="agent-history">
        {history.map((h, i) => (
          <li key={`${h.at}-${i}`}>
            <span className="agent-history-name">{h.name}</span> done · {h.at}
          </li>
        ))}
      </ul>
    </div>
  );
}
