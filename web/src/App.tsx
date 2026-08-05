import { useState } from "react";
import { RTVIEvent } from "@pipecat-ai/client-js";
import { useRTVIClientEvent } from "@pipecat-ai/client-react";
import ConnectButton from "./components/ConnectButton";
import MicControls from "./components/MicControls";
import Transcript from "./components/Transcript";
import VoicePicker from "./components/VoicePicker";
import AgentActivity from "./components/AgentActivity";
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
        <div className="brand">JARVIS</div>
        <ConnectButton />
        <VoicePicker />
      </header>

      {error && <div className="error-banner">{error}</div>}

      <main className="main">
        <div className="orb-wrap">
          <div className={speaking ? "orb orb-speaking" : "orb"} />
          <div className="orb-label">{speaking ? "Speaking" : "Listening"}</div>
        </div>
        <Transcript />
      </main>

      <footer className="bottombar">
        <MicControls />
        <AgentActivity />
      </footer>
    </div>
  );
}
