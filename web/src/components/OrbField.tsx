import { useEffect, useState } from "react";
import { RTVIEvent } from "@pipecat-ai/client-js";
import {
  usePipecatConversation,
  useRTVIClientEvent,
} from "@pipecat-ai/client-react";
import type { ConversationMessage } from "@pipecat-ai/client-react";
import Orb, { type OrbState } from "./Orb";
import { isWakeWordRunning, subscribeWake } from "../wakeWord";

/** Fixed satellite positions on the stage (percent of the field). */
const AGENTS = [
  { key: "scheduler", label: "Scheduler", x: 17, y: 24 },
  { key: "librarian", label: "Librarian", x: 17, y: 74 },
  { key: "analyst", label: "Analyst", x: 83, y: 24 },
  { key: "systems", label: "Systems", x: 83, y: 74 },
];

interface AgentMsg {
  type?: string;
  name?: string;
  state?: string;
}

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

function truncate(s: string, max = 160): string {
  const t = s.trim().replace(/\s+/g, " ");
  return t.length > max ? t.slice(0, max - 1) + "…" : t;
}

const ORB_LABEL: Record<OrbState, string> = {
  offline: "Standby",
  connecting: "Spinning up",
  listening: "Listening",
  speaking: "Speaking",
};

export default function OrbField({ state }: { state: OrbState }) {
  const [working, setWorking] = useState<Record<string, boolean>>({});
  const [doneAt, setDoneAt] = useState<Record<string, number>>({});
  const [wakePulse, setWakePulse] = useState(0);
  const [wakeArmed, setWakeArmed] = useState(false);
  const { messages } = usePipecatConversation();

  // Sub-agent lifecycle: the Supervisor's delegate_task emissions.
  useRTVIClientEvent(RTVIEvent.ServerMessage, (data: unknown) => {
    const msg = data as AgentMsg;
    if (msg?.type !== "agent" || typeof msg.name !== "string") return;
    const name = msg.name.toLowerCase();
    if (msg.state === "working") {
      setWorking((w) => ({ ...w, [name]: true }));
    } else if (msg.state === "done") {
      setWorking((w) => ({ ...w, [name]: false }));
      setDoneAt((d) => ({ ...d, [name]: Date.now() }));
    }
  });

  // Wake ripple + armed halo (wake state lives in MicControls; poll cheaply).
  useEffect(() => subscribeWake(() => setWakePulse((p) => p + 1)), []);
  useEffect(() => {
    const t = setInterval(() => setWakeArmed(isWakeWordRunning()), 1000);
    return () => clearInterval(t);
  }, []);

  const lastAssistant = [...messages]
    .reverse()
    .find((m) => m.role === "assistant" && messageText(m).trim() !== "");
  const lastUser = [...messages]
    .reverse()
    .find((m) => m.role === "user" && messageText(m).trim() !== "");

  return (
    <section className="orb-field">
      {/* beams: satellite -> orb, lit while an agent works */}
      <svg className="orb-beams" viewBox="0 0 100 100" preserveAspectRatio="none">
        {AGENTS.map((a) => (
          <line
            key={`${a.key}-${doneAt[a.key] ?? 0}`}
            x1={a.x}
            y1={a.y}
            x2={50}
            y2={50}
            vectorEffect="non-scaling-stroke"
            className={
              "beam" +
              (working[a.key] ? " beam-live" : "") +
              (!working[a.key] && doneAt[a.key] ? " beam-done" : "")
            }
          />
        ))}
      </svg>

      {AGENTS.map((a) => (
        <div
          key={`${a.key}-${doneAt[a.key] ?? 0}`}
          className={
            "satellite" +
            (working[a.key] ? " satellite-working" : "") +
            (!working[a.key] && doneAt[a.key] ? " satellite-done" : "")
          }
          style={{ left: `${a.x}%`, top: `${a.y}%` }}
        >
          <span className="satellite-dot" />
          <span className="satellite-name">{a.label}</span>
        </div>
      ))}

      <div className="orb-center">
        <div className="orb-readout">M.O.R.T.I.M.E.R.</div>
        <div className={wakeArmed ? "orb-halo orb-halo-armed" : "orb-halo"}>
          <Orb state={state} />
          {wakePulse > 0 && <div key={wakePulse} className="wake-ripple" />}
        </div>
        <div className={`orb-label orb-label-${state}`}>
          <span className="orb-dot" />
          {ORB_LABEL[state]}
        </div>
        <div className="live-caption">
          {lastUser && (
            <div className="caption caption-user">
              You — {truncate(messageText(lastUser))}
            </div>
          )}
          {lastAssistant && (
            <div className="caption caption-bot">
              {truncate(messageText(lastAssistant))}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
