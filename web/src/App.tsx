import { useEffect, useState } from "react";
import { RTVIEvent } from "@pipecat-ai/client-js";
import {
  usePipecatClientTransportState,
  useRTVIClientEvent,
} from "@pipecat-ai/client-react";
import ConnectButton from "./components/ConnectButton";
import OrbField from "./components/OrbField";
import VoiceWave from "./components/VoiceWave";
import DisplayPanel from "./components/DisplayPanel";
import MicControls from "./components/MicControls";
import TranscriptDrawer from "./components/TranscriptDrawer";
import VoicePicker from "./components/VoicePicker";
import GitPanel from "./components/GitPanel";
import EditModePanel from "./components/EditModePanel";
import AgentStatusPanel from "./components/AgentStatusPanel";
import MemoryPanel from "./components/MemoryPanel";
import type { VoiceState } from "./voiceState";
import "./App.css";
import "./command-deck.css";
import "./editmode.css";
import "./agentstatus.css";
import "./memory.css";

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

function isTypingTarget(target: EventTarget | null): boolean {
  const tag = (target as HTMLElement | null)?.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
}

export default function App() {
  const [speaking, setSpeaking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [gitOpen, setGitOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [memoryOpen, setMemoryOpen] = useState(false);
  const transport = usePipecatClientTransportState();

  const connected = transport === "ready" || transport === "connected";
  const voiceState: VoiceState = connected
    ? speaking
      ? "speaking"
      : "listening"
    : transport === "disconnected" || transport === "error"
      ? "offline"
      : "connecting";

  useRTVIClientEvent(RTVIEvent.BotStartedSpeaking, () => {
    setSpeaking(true);
    setError(null); // a successful turn dismisses the banner
  });
  useRTVIClientEvent(RTVIEvent.BotStoppedSpeaking, () => setSpeaking(false));
  useRTVIClientEvent(RTVIEvent.Error, (message: unknown) =>
    setError(errorText(message)),
  );

  // T toggles the transcript drawer (voice-first; text on demand).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.code !== "KeyT" || e.repeat || isTypingTarget(e.target)) return;
      setDrawerOpen((o) => !o);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="app">
      <VoiceWave state={voiceState} />
      <header className="topbar">
        <div className="brand">MORTIMER</div>
        <ConnectButton />
        <VoicePicker />
        <button
          type="button"
          className="btn"
          onClick={() => setGitOpen((o) => !o)}
          title="Repository (admin sidecar)"
        >
          ⚙ Repo
        </button>
        <button
          type="button"
          className="btn"
          onClick={() => setEditOpen((o) => !o)}
          title="Self-development edit mode (PRs only — merge on GitHub)"
        >
          ✎ Edit
        </button>
        <button
          type="button"
          className="btn"
          onClick={() => setMemoryOpen((o) => !o)}
          title="Long-term memory (view and forget facts)"
        >
          🧠 Memory
        </button>
        <button
          type="button"
          className="btn"
          onClick={() => setDrawerOpen((o) => !o)}
          title="Transcript history (T)"
        >
          Log
        </button>
      </header>

      {gitOpen && (
        <div className="git-popover">
          <GitPanel />
        </div>
      )}

      {editOpen && (
        <div className="git-popover">
          <EditModePanel />
        </div>
      )}

      {memoryOpen && (
        <div className="git-popover">
          <MemoryPanel />
        </div>
      )}

      {error && <div className="error-banner">{error}</div>}

      <main className="main">
        <OrbField state={voiceState} />
      </main>

      <footer className="bottombar">
        <MicControls />
        <div className="hints">SPACE talk · T transcript</div>
      </footer>

      <TranscriptDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)} />

      {/* agent status window — live sub-agent progress (z-25) */}
      <AgentStatusPanel />

      {/* results window — floats in front of everything (z-30) */}
      <DisplayPanel />
    </div>
  );
}
