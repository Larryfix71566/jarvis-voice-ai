import { useEffect, useState } from "react";
import type { CSSProperties } from "react";
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
  task?: string;
}

/** Line-glyph icons, one per specialist (stroke follows currentColor). */
function AgentIcon({ agent }: { agent: string }) {
  const common = {
    width: 16,
    height: 16,
    viewBox: "0 0 16 16",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.4,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
  };
  switch (agent) {
    case "scheduler":
      return (
        <svg {...common}>
          <rect x="2" y="3" width="12" height="11" rx="1.5" />
          <path d="M2 7h12M5 1.5v3M11 1.5v3" />
        </svg>
      );
    case "librarian":
      return (
        <svg {...common}>
          <path d="M3 2h7a2 2 0 0 1 2 2v10H5a2 2 0 0 1-2-2V2z" />
          <path d="M3 12a2 2 0 0 1 2-2h7" />
        </svg>
      );
    case "analyst":
      return (
        <svg {...common}>
          <path d="M2 14h12" />
          <path d="M4 10v4M8 6v8M12 3v11" />
        </svg>
      );
    default: // systems
      return (
        <svg {...common}>
          <rect x="4.5" y="4.5" width="7" height="7" rx="1" />
          <path d="M6.5 1.5v3M9.5 1.5v3M6.5 11.5v3M9.5 11.5v3" />
          <path d="M1.5 6.5h3M1.5 9.5h3M11.5 6.5h3M11.5 9.5h3" />
        </svg>
      );
  }
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
  const [tasks, setTasks] = useState<Record<string, string>>({});
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
      if (typeof msg.task === "string" && msg.task.trim() !== "") {
        setTasks((t) => ({ ...t, [name]: msg.task as string }));
      }
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

      {AGENTS.map((a) => {
        const isWorking = !!working[a.key];
        const isDone = !isWorking && !!doneAt[a.key];
        const status = isWorking
          ? truncate(tasks[a.key] ?? "working…", 48)
          : isDone
            ? "done"
            : "standby";
        // Subtle pull toward the orb while active (percent of card size).
        const pull = {
          "--px": `${(50 - a.x) * 0.08}%`,
          "--py": `${(50 - a.y) * 0.08}%`,
        } as CSSProperties;
        return (
          <div
            key={`${a.key}-${doneAt[a.key] ?? 0}`}
            className={
              "satellite" +
              (isWorking ? " satellite-working" : "") +
              (isDone ? " satellite-done" : "")
            }
            style={{ left: `${a.x}%`, top: `${a.y}%`, ...pull }}
          >
            <span className="satellite-icon">
              <AgentIcon agent={a.key} />
            </span>
            <span className="satellite-text">
              <span className="satellite-name">{a.label}</span>
              <span className="satellite-status">{status}</span>
            </span>
          </div>
        );
      })}

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
