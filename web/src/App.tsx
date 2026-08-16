import { useEffect, useState } from "react";
import { RTVIEvent } from "@pipecat-ai/client-js";
import {
  usePipecatClient,
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
import AgentStatusPanel from "./components/AgentStatusPanel";
import SideDrawer, {
  DRAWER_DEFAULT_WIDTH_PX,
  TAB_KEYS,
  clampDrawerWidth,
  type TabKey,
} from "./components/SideDrawer";
import { getRuns, isSelfEditRun, subscribeRuns, type RunState } from "./agentRuns";
import { applyServerMessage as applyDisplayResult } from "./displayResults";
import { publish as publishWindowPayload, wireConsoleSide } from "./displayWindow";
import { applyUiMessage, subscribeUiCommands } from "./uiCommands";
import type { VoiceState } from "./voiceState";
import "./App.css";
import "./command-deck.css";
import "./editmode.css";
import "./agentstatus.css";
import "./memory.css";
import "./runs.css";
import "./sidedrawer.css";

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

// --- side-drawer preferences (plan D13) ---------------------------------
//
// localStorage is user-editable and survives across builds, so every read
// is wrapped in try/catch and validated: anything missing, unparseable, or
// out of range falls back to the D6 defaults (closed, tab "runs", default
// width). Reads happen in useState lazy initializers, NOT effects —
// hydrating in an effect paints one frame at the wrong width/open state.

const LS_WIDTH = "mortimer.drawer.width";
const LS_OPEN = "mortimer.drawer.open";
const LS_TAB = "mortimer.drawer.tab";

function readStoredWidth(): number {
  try {
    const raw = localStorage.getItem(LS_WIDTH);
    if (raw === null) return DRAWER_DEFAULT_WIDTH_PX;
    const n = Number(raw);
    if (Number.isNaN(n)) return DRAWER_DEFAULT_WIDTH_PX;
    return clampDrawerWidth(n);
  } catch {
    return DRAWER_DEFAULT_WIDTH_PX;
  }
}

function readStoredOpen(): boolean {
  try {
    return localStorage.getItem(LS_OPEN) === "true";
  } catch {
    return false;
  }
}

function readStoredTab(): TabKey {
  try {
    const raw = localStorage.getItem(LS_TAB);
    return TAB_KEYS.includes(raw as TabKey) ? (raw as TabKey) : "runs";
  } catch {
    return "runs";
  }
}

export default function App() {
  const [speaking, setSpeaking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [transcriptOpen, setTranscriptOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState<boolean>(readStoredOpen);
  const [drawerTab, setDrawerTab] = useState<TabKey>(readStoredTab);
  const [drawerWidth, setDrawerWidth] = useState<number>(readStoredWidth);
  const [outputDot, setOutputDot] = useState(false);
  const [runs, setRuns] = useState<RunState[]>(getRuns);
  const client = usePipecatClient();
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

  // Plan D30/D37 — the single "type: display" listener, dispatching by
  // `surface`. This is a DIFFERENT type than D10's agent-lifecycle
  // listener in AgentStatusPanel, so two useRTVIClientEvent(ServerMessage)
  // registrations coexisting here is fine (they filter on different
  // `msg.type`); what must not happen is two listeners for the SAME type.
  useRTVIClientEvent(RTVIEvent.ServerMessage, (data: unknown) => {
    const msg = data as { type?: string; display?: { surface?: string } };
    // Voice UI plan U2: forward ui_control commands into the module
    // store; applyUiMessage ignores every other type, so this can sit
    // unconditionally ahead of the display filter below.
    applyUiMessage(data);
    if (msg?.type !== "display" || !msg.display) return;
    // A missing/unrecognized surface degrades to "drawer" (D36) — the
    // non-intrusive outcome, and correct for an older bot talking to a
    // newer console.
    if (msg.display.surface === "window") {
      publishWindowPayload(msg.display);
      return;
    }
    applyDisplayResult(msg);
    // D31's three-case auto-open rule, drawer-routed results only.
    if (!drawerOpen) {
      setDrawerOpen(true);
      setDrawerTab("output");
    } else if (drawerTab !== "output") {
      setOutputDot(true);
    }
    // drawerOpen && drawerTab === "output": nothing extra — the item just
    // appears in the already-visible list.
  });

  // Wire the console side of the popup relay once (D40's hello/replay
  // handshake) — idempotent internally, but one mount is enough.
  useEffect(() => wireConsoleSide(), []);

  // Clear the Output dot once the tab is actually viewed (D31).
  useEffect(() => {
    if (drawerOpen && drawerTab === "output") setOutputDot(false);
  }, [drawerOpen, drawerTab]);

  // Voice UI plan U2: apply the drawer/transcript commands this component
  // owns, through the SAME state setters the buttons use. Deps include the
  // current open/tab state so no-op detection reads fresh values; the
  // store's subscribe/unsubscribe is cheap, so re-subscribing per render
  // of these deps is fine. A command that changes nothing sends ui/noop
  // with a spoken sentence — the bot voices it verbatim (no LLM).
  useEffect(() => {
    const noop = (reason: string) => {
      client?.sendClientMessage("ui/noop", { reason });
    };
    return subscribeUiCommands((cmd) => {
      switch (cmd.action) {
        case "drawer_open": {
          const tab = TAB_KEYS.includes(cmd.tab as TabKey)
            ? (cmd.tab as TabKey)
            : null;
          if (drawerOpen && (tab === null || tab === drawerTab)) {
            noop("The drawer is already open.");
            return;
          }
          if (tab !== null) setDrawerTab(tab);
          setDrawerOpen(true);
          setTranscriptOpen(false); // plan D17
          return;
        }
        case "drawer_close": {
          if (!drawerOpen) {
            noop("The drawer is already closed.");
            return;
          }
          setDrawerOpen(false);
          return;
        }
        case "drawer_tab": {
          const tab = TAB_KEYS.includes(cmd.tab as TabKey)
            ? (cmd.tab as TabKey)
            : null;
          if (tab === null) return; // bot validates; unknown tab never sent
          if (drawerOpen && tab === drawerTab) {
            noop(`The ${tab} panel is already showing.`);
            return;
          }
          setDrawerTab(tab);
          setDrawerOpen(true);
          setTranscriptOpen(false); // plan D17
          return;
        }
        case "transcript_open": {
          if (transcriptOpen) {
            noop("The transcript is already open.");
            return;
          }
          setTranscriptOpen(true);
          setDrawerOpen(false); // plan D17
          return;
        }
        case "transcript_close": {
          if (!transcriptOpen) {
            noop("The transcript is already closed.");
            return;
          }
          setTranscriptOpen(false);
          return;
        }
        default:
          // display_*/mic_*/wake_* belong to DisplayPanel/MicControls.
          return;
      }
    });
  }, [client, drawerOpen, drawerTab, transcriptOpen]);

  // Read-only subscription to the run store, for the D7 topbar indicator.
  // This must NOT register a second RTVI listener — AgentStatusPanel is the
  // single listener (plan D10).
  useEffect(() => subscribeRuns(setRuns), []);
  const devRunning = runs.some(
    (r) => isSelfEditRun(r.name, r.tools) && r.doneAt === null,
  );

  // Persist drawer preferences (plan D13).
  useEffect(() => {
    try {
      localStorage.setItem(LS_WIDTH, String(drawerWidth));
    } catch {
      /* storage unavailable — preference is simply not persisted */
    }
  }, [drawerWidth]);
  useEffect(() => {
    try {
      localStorage.setItem(LS_OPEN, String(drawerOpen));
    } catch {
      /* ignore */
    }
  }, [drawerOpen]);
  useEffect(() => {
    try {
      localStorage.setItem(LS_TAB, drawerTab);
    } catch {
      /* ignore */
    }
  }, [drawerTab]);

  // Plan D5's three-case toggle: closed -> open on X; open on X -> close
  // (tab stays X for next open); open on Y -> switch to X, stay open.
  // Opening or switching the side drawer closes the transcript drawer
  // (plan D17 — both live at the right edge, z-20).
  const onTabButton = (tab: TabKey) => {
    if (drawerOpen && drawerTab === tab) {
      setDrawerOpen(false);
      return;
    }
    setDrawerTab(tab);
    setDrawerOpen(true);
    setTranscriptOpen(false);
  };

  const openTranscript = (open: boolean) => {
    setTranscriptOpen(open);
    if (open) setDrawerOpen(false); // plan D17
  };

  // T toggles the transcript drawer (voice-first; text on demand).
  // Escape closes the side drawer (plan D20) — window-level, same shape and
  // same isTypingTarget guard, so there is one keyboard pattern in this
  // file rather than two. The guard is why Escape inside a panel's text
  // input does not close the drawer out from under the user mid-edit.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.repeat || isTypingTarget(e.target)) return;
      if (e.code === "KeyT") {
        setTranscriptOpen((o) => {
          const next = !o;
          if (next) setDrawerOpen(false); // plan D17
          return next;
        });
      } else if (e.key === "Escape") {
        setDrawerOpen((o) => (o ? false : o));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const tabButtonClass = (tab: TabKey) =>
    "btn" + (drawerOpen && drawerTab === tab ? " btn-active" : "");

  return (
    <div className="app">
      <VoiceWave state={voiceState} />
      <header className="topbar">
        <div className="brand">MORTIMER</div>
        <ConnectButton />
        <VoicePicker />
        <button
          type="button"
          className={tabButtonClass("repo")}
          aria-expanded={drawerOpen && drawerTab === "repo"}
          onClick={() => onTabButton("repo")}
          title="Repository (admin sidecar)"
        >
          ⚙ Repo
        </button>
        <button
          type="button"
          className={tabButtonClass("edit")}
          aria-expanded={drawerOpen && drawerTab === "edit"}
          onClick={() => onTabButton("edit")}
          title="Self-development edit mode (PRs only — merge on GitHub)"
        >
          ✎ Edit
        </button>
        <button
          type="button"
          className={tabButtonClass("memory")}
          aria-expanded={drawerOpen && drawerTab === "memory"}
          onClick={() => onTabButton("memory")}
          title="Long-term memory (view and forget facts)"
        >
          🧠 Memory
        </button>
        <button
          type="button"
          className={tabButtonClass("runs")}
          aria-expanded={drawerOpen && drawerTab === "runs"}
          onClick={() => onTabButton("runs")}
          title="Sub-agent run history"
        >
          📋 Runs
        </button>
        <button
          type="button"
          className={tabButtonClass("developer")}
          aria-expanded={drawerOpen && drawerTab === "developer"}
          onClick={() => onTabButton("developer")}
          title="Development run status (live self-edit progress)"
        >
          🛠 Dev
          {/* Plan D7: the topbar is the only always-visible surface, so the
              live self-edit indicator has to live here — otherwise a
              multi-minute run behind a closed drawer has no on-screen
              evidence at all. */}
          {devRunning && <span className="btn-live-dot" aria-hidden="true" />}
        </button>
        <button
          type="button"
          className={tabButtonClass("output")}
          aria-expanded={drawerOpen && drawerTab === "output"}
          onClick={() => onTabButton("output")}
          title="Output — work-product results (diffs, commits, app scaffolds)"
        >
          📄 Output
          {/* Plan D31: a new drawer-routed result while the drawer is open
              on another tab shows a dot here rather than yanking the user
              off what they're reading. */}
          {outputDot && <span className="btn-live-dot" aria-hidden="true" />}
        </button>
        <button
          type="button"
          className="btn"
          onClick={() => openTranscript(!transcriptOpen)}
          title="Transcript history (T)"
        >
          Log
        </button>
      </header>

      {error && <div className="error-banner">{error}</div>}

      <div className="stage-row">
        <main className="main">
          <OrbField state={voiceState} />
        </main>

        {/* Always mounted (plan D23) — an element cannot transition into
            existence, and the run store outlives the tab bodies. */}
        <SideDrawer
          open={drawerOpen}
          activeTab={drawerTab}
          width={drawerWidth}
          outputDot={outputDot}
          onTabChange={(tab) => {
            setDrawerTab(tab);
            setTranscriptOpen(false);
          }}
          onClose={() => setDrawerOpen(false)}
          onWidthChange={setDrawerWidth}
        />
      </div>

      <footer className="bottombar">
        <MicControls />
        <div className="hints">SPACE talk · T transcript</div>
      </footer>

      <TranscriptDrawer
        open={transcriptOpen}
        onClose={() => setTranscriptOpen(false)}
      />

      {/* agent status window — live sub-agent progress (z-25) */}
      <AgentStatusPanel />

      {/* results window — floats in front of everything (z-30) */}
      <DisplayPanel />
    </div>
  );
}
