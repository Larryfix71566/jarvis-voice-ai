import { useEffect, useRef, useState } from "react";
import { RTVIEvent } from "@pipecat-ai/client-js";
import {
  usePipecatConversation,
  useRTVIClientEvent,
} from "@pipecat-ai/client-react";
import type { ConversationMessage } from "@pipecat-ai/client-react";
import { isWakeWordRunning, subscribeWake } from "../wakeWord";
import { AGENT_LAYOUT, publishFieldRect } from "../agentLayout";
import type { VoiceState } from "../voiceState";

/** Satellite positions on the stage (star-layout plan §5.1) — shared with
 * AgentStatusPanel via agentLayout.ts so the two can never drift apart
 * again (plan D3). */
const AGENTS = AGENT_LAYOUT;

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

const STATE_LABEL: Record<VoiceState, string> = {
  offline: "Standby",
  connecting: "Spinning up",
  listening: "Listening",
  speaking: "Speaking",
};

/**
 * The command-deck stage: agent satellites + live captions over the
 * full-viewport VoiceWave (the wave owns voice display — the old orb
 * was removed). Wake state shows as a center burst + readout glow.
 */
export default function OrbField({ state }: { state: VoiceState }) {
  const [working, setWorking] = useState<Record<string, boolean>>({});
  const [doneAt, setDoneAt] = useState<Record<string, number>>({});
  const [wakePulse, setWakePulse] = useState(0);
  const [wakeArmed, setWakeArmed] = useState(false);
  const { messages } = usePipecatConversation();
  const fieldRef = useRef<HTMLElement | null>(null);

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

  // Wake burst + armed readout glow (wake state lives in MicControls;
  // poll cheaply).
  useEffect(() => subscribeWake(() => setWakePulse((p) => p + 1)), []);
  useEffect(() => {
    const t = setInterval(() => setWakeArmed(isWakeWordRunning()), 1000);
    return () => clearInterval(t);
  }, []);

  // Publish .orb-field's measured rect (plan §5.2 step 2) so
  // AgentStatusPanel can anchor status cards to their satellite's
  // on-screen position — AgentStatusPanel lives outside .main (plan D4)
  // and has no other way to know where the field is.
  useEffect(() => {
    const el = fieldRef.current;
    if (!el) return;

    const publish = () => {
      const rect = el.getBoundingClientRect();
      publishFieldRect({
        left: rect.left,
        top: rect.top,
        width: rect.width,
        height: rect.height,
      });
    };

    publish();
    const observer = new ResizeObserver(publish);
    observer.observe(el);
    window.addEventListener("scroll", publish, true);
    window.addEventListener("resize", publish);
    return () => {
      observer.disconnect();
      window.removeEventListener("scroll", publish, true);
      window.removeEventListener("resize", publish);
      publishFieldRect(null);
    };
  }, []);

  const lastAssistant = [...messages]
    .reverse()
    .find((m) => m.role === "assistant" && messageText(m).trim() !== "");
  const lastUser = [...messages]
    .reverse()
    .find((m) => m.role === "user" && messageText(m).trim() !== "");

  return (
    <section className="orb-field" ref={fieldRef}>
      {/* wake burst: expanding ring from the field center */}
      {wakePulse > 0 && <div key={wakePulse} className="wake-ripple" />}

      {/* beams: satellite -> center, lit while an agent works */}
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
        <div className={wakeArmed ? "orb-readout orb-readout-armed" : "orb-readout"}>
          M.O.R.T.I.M.E.R.
        </div>
        <div className={`orb-label orb-label-${state}`}>
          <span className="orb-dot" />
          {STATE_LABEL[state]}
        </div>
      </div>

      {/* MORTIMER_CAPTION_PLACEMENT_PLAN.md C1/C4: lives outside
          .orb-center (own bottom-anchored position, see .live-caption
          in command-deck.css) and only renders once there's something
          to show — a visible frosted panel must never sit empty. */}
      {(lastUser || lastAssistant) && (
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
      )}
    </section>
  );
}
