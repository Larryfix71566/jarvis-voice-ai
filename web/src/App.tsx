import { useState } from "react";
import { RTVIEvent } from "@pipecat-ai/client-js";
import {
  usePipecatClientTransportState,
  useRTVIClientEvent,
} from "@pipecat-ai/client-react";
import ConnectButton from "./components/ConnectButton";
import Orb, { type OrbState } from "./components/Orb";
import MicControls from "./components/MicControls";
import Transcript from "./components/Transcript";
import VoicePicker from "./components/VoicePicker";
import AgentActivity from "./components/AgentActivity";
import GitPanel from "./components/GitPanel";
import "./App.css";

function errorText(message: unknown): string {
  const m = message as { data?: unknown };
  const d = m?.data;
  if (typeof d === "string") return d;
  if (d && typeof d === "object") {
    const o = d as Record<string, unknown>;
    if (typeof o.error === "string") return o.error;
    if (typeof o.message === "string") return o.message;
  }
  return "An error occurred.";
}

export default function App() {
  const [speaking, setSpeaking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const transport = usePipecatClientTransportState();

  const connected = transport === "ready" || transport === "connected";
  const orbState: OrbState = connected
    ? speaking
      ? "speaking"
      : "listening"
    : transport === "disconnected" || transport === "error"
      ? "offline"
      : "connecting";
  const orbLabel = {
    offline: "Standby",
    connecting: "Spinning up",
    listening: "Listening",
    speaking: "Speaking",
  }[orbState];

  useRTVIClientEvent(RTVIEvent.BotStartedSpeaking, () => {
    setSpeaking(true);
    setError(null); // a successful turn dismisses the banner
  });
  useRTVIClientEvent(RTVIEvent.BotStoppedSpeaking, () => setSpeaking(false));
  useRTVIClientEvent(RTVIEvent.Error, (message: unknown) =>
    setError(errorText(message)),
  );

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">MORTIMER</div>
        <ConnectButton />
        <VoicePicker />
      </header>

      {error && <div className="error-banner">{error}</div>}

      <main className="main">
        <section className="orb-wrap">
          <div className="hud-corner hud-tl" />
          <div className="hud-corner hud-tr" />
          <div className="hud-corner hud-bl" />
          <div className="hud-corner hud-br" />
          <div className="orb-readout">M.O.R.T.I.M.E.R.</div>
          <Orb state={orbState} />
          <div className={`orb-label orb-label-${orbState}`}>
            <span className="orb-dot" />
            {orbLabel}
          </div>
          <GitPanel />
        </section>
        <Transcript />
      </main>

      <footer className="bottombar">
        <MicControls />
        <AgentActivity />
      </footer>
    </div>
  );
}
