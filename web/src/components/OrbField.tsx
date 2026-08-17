import { useEffect, useRef, useState } from "react";
import { RTVIEvent } from "@pipecat-ai/client-js";
import {
  usePipecatConversation,
  useRTVIClientEvent,
} from "@pipecat-ai/client-react";
import type { ConversationMessage } from "@pipecat-ai/client-react";
import { isWakeWordRunning, subscribeWake } from "../wakeWord";
import { AGENT_LAYOUT, publishFieldRect } from "../agentLayout";
import {
  getRuns,
  requestAgentFilter,
  subscribeRuns,
  type RunState,
} from "../agentRuns";
import { hasPendingDraft, subscribeResults } from "../displayResults";
import { applyUiMessage } from "../uiCommands";
import { play as playSound } from "../sounds";
import AmbientStrip from "./AmbientStrip";
import { bootWave } from "./VoiceWave";
import type { VoiceState } from "../voiceState";

/** Satellite positions on the stage (star-layout plan §5.1) — shared with
 * AgentStatusPanel via agentLayout.ts so the two can never drift apart
 * again (plan D3). */
const AGENTS = AGENT_LAYOUT;

interface AgentMsg {
  type?: string;
  name?: string;
  state?: string;
  ok?: boolean;
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
  // Engagement plan E1 — amber readout underglow while a draft awaits
  // confirmation, and a thinking shimmer between LLM start and speech.
  const [attention, setAttention] = useState(hasPendingDraft);
  const [thinking, setThinking] = useState(false);
  // E2 — boot sequence counter: increments when a connection arrives
  // (connecting -> live); keys the readout/satellites so their one-shot
  // entrance animations replay on every (re)connect. Every connect is
  // an arrival.
  const [bootPulse, setBootPulse] = useState(0);
  const prevStateRef = useRef<VoiceState>(state);
  useEffect(() => {
    const prev = prevStateRef.current;
    prevStateRef.current = state;
    if (prev === "connecting" && (state === "listening" || state === "speaking")) {
      setBootPulse((p) => p + 1);
      bootWave();
      playSound("boot");
    }
  }, [state]);
  const { messages } = usePipecatConversation();
  const fieldRef = useRef<HTMLElement | null>(null);

  // Sub-agent lifecycle: the Supervisor's delegate_task emissions.
  // E3: the delegation tick / outcome tones ride this existing listener.
  //
  // MINIMUM PRESENCE WINDOW (Larry, 2026-08-16: "the agent enhancements
  // were very fast and almost not noticeable"): most delegations finish
  // in 3-7s, so the lit satellite + flowing beam were gone before the
  // eye arrived. The working VISUAL now holds at least MIN_WORKING_MS
  // from its start even when the run finishes sooner — the done sound
  // still plays immediately (audio is truthful; the visual lingers).
  const workingSinceRef = useRef<Record<string, number>>({});
  const holdTimersRef = useRef<Record<string, number>>({});
  useEffect(() => {
    const timers = holdTimersRef.current;
    return () => {
      for (const id of Object.values(timers)) window.clearTimeout(id);
    };
  }, []);
  useRTVIClientEvent(RTVIEvent.ServerMessage, (data: unknown) => {
    const msg = data as AgentMsg;
    if (msg?.type !== "agent" || typeof msg.name !== "string") return;
    const name = msg.name.toLowerCase();
    if (msg.state === "working") {
      workingSinceRef.current[name] = Date.now();
      setWorking((w) => ({ ...w, [name]: true }));
      playSound("tick");
    } else if (msg.state === "done") {
      playSound(msg.ok === false ? "fail" : "done");
      const MIN_WORKING_MS = 2500;
      const elapsed = Date.now() - (workingSinceRef.current[name] ?? 0);
      const settle = () => {
        setWorking((w) => ({ ...w, [name]: false }));
        setDoneAt((d) => ({ ...d, [name]: Date.now() }));
      };
      const remaining = MIN_WORKING_MS - elapsed;
      if (remaining <= 0) {
        settle();
      } else {
        window.clearTimeout(holdTimersRef.current[name]);
        holdTimersRef.current[name] = window.setTimeout(settle, remaining);
      }
    }
  });

  useEffect(
    () => subscribeResults(() => setAttention(hasPendingDraft())),
    [],
  );
  // E5 — satellite instrumentation: each satellite's most recent
  // completed run (tick + hover tooltip) from the run store. Read-only
  // subscription; AgentStatusPanel remains the single RTVI listener
  // feeding that store (plan D10).
  const [runHistory, setRunHistory] = useState<RunState[]>(getRuns);
  useEffect(() => subscribeRuns(setRunHistory), []);
  const lastRunFor = (key: string): RunState | undefined => {
    for (let i = runHistory.length - 1; i >= 0; i--) {
      const r = runHistory[i];
      if (r.name === key && r.doneAt !== null) return r;
    }
    return undefined;
  };
  const openRunsFor = (key: string) => {
    // Same convergence rule as voice (U2): route through the ui-command
    // dispatch so a satellite click and "show me the runs" hit the same
    // setters; the filter rides the agentRuns store.
    requestAgentFilter(key);
    applyUiMessage({ type: "ui", action: "drawer_tab", tab: "runs" });
  };
  // E1 thinking shimmer — client-js emits these alongside the speaking
  // events; different event types than the listeners above, so the
  // single-listener-per-type rule holds.
  useRTVIClientEvent(RTVIEvent.BotLlmStarted, () => setThinking(true));
  useRTVIClientEvent(RTVIEvent.BotLlmStopped, () => setThinking(false));

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
      {/* E4 — ambient signs of life, top-left; renders nothing while
          disconnected. */}
      <AmbientStrip
        connected={state === "listening" || state === "speaking"}
      />

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

      {AGENTS.map((a, i) => {
        const last = lastRunFor(a.key);
        return (
          <div
            key={`${a.key}-${doneAt[a.key] ?? 0}-${bootPulse}`}
            className={
              "satellite satellite-clickable" +
              (bootPulse > 0 ? " boot-sat" : "") +
              (working[a.key] ? " satellite-working" : "") +
              (!working[a.key] && doneAt[a.key] ? " satellite-done" : "")
            }
            style={{
              left: `${a.x}%`,
              top: `${a.y}%`,
              // E2: staggered entrance, 80ms apart in layout order; the
              // 200ms base offset lets the readout cascade lead.
              animationDelay: bootPulse > 0 ? `${200 + i * 80}ms` : undefined,
            }}
            // E5: hover = last task; click = Runs tab filtered to this
            // agent. The map becomes an instrument, not decoration.
            title={
              last
                ? `Last: ${last.task.length > 80 ? last.task.slice(0, 79) + "…" : last.task}`
                : `No runs yet — click for ${a.label}'s history`
            }
            onClick={() => openRunsFor(a.key)}
          >
            <span className="satellite-dot" />
            <span className="satellite-name">{a.label}</span>
            {last && (
              <span
                className={
                  "satellite-tick " +
                  (last.ok ? "satellite-tick-ok" : "satellite-tick-fail")
                }
                aria-hidden="true"
              >
                {last.ok ? "✓" : "✗"}
              </span>
            )}
          </div>
        );
      })}

      <div className="orb-center">
        <div
          key={`readout-${bootPulse}`}
          className={
            "orb-readout" +
            (wakeArmed ? " orb-readout-armed" : "") +
            (attention ? " orb-readout-attn" : "")
          }
        >
          {/* E2: per-letter cascade on boot (40ms steps, keyed above so
              it replays each connect); plain text before first boot. */}
          {bootPulse > 0
            ? "M.O.R.T.I.M.E.R.".split("").map((ch, i) => (
                <span
                  key={i}
                  className="boot-letter"
                  style={{ animationDelay: `${i * 40}ms` }}
                >
                  {ch}
                </span>
              ))
            : "M.O.R.T.I.M.E.R."}
        </div>
        {/* E1: "Thinking" shows during LLM inference unless Mortimer is
            already audibly speaking — speech outranks the shimmer. */}
        <div
          className={
            thinking && state !== "speaking"
              ? "orb-label orb-label-thinking"
              : `orb-label orb-label-${state}`
          }
        >
          <span className="orb-dot" />
          {thinking && state !== "speaking" ? "Thinking" : STATE_LABEL[state]}
        </div>
      </div>

      {/* MORTIMER_CAPTION_PLACEMENT_PLAN.md C1/C4: lives outside
          .orb-center (own bottom-anchored position, see .live-caption
          in command-deck.css) and only renders once there's something
          to show — a visible frosted panel must never sit empty. */}
      {/* E8 — first-run hint where the captions will live: connected,
          nothing said yet. Replaced forever by the first caption. */}
      {!lastUser && !lastAssistant &&
        (state === "listening" || state === "speaking") && (
          <div className="live-caption stage-hint">
            <div className="caption caption-user">
              Try: "What's the weather?" · "Show me the runs" · "Remind me
              in twenty minutes"
            </div>
          </div>
        )}

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
