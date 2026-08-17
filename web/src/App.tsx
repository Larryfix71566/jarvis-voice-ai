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
import VoicePicker from "./components/VoicePicker";
import AgentStatusPanel from "./components/AgentStatusPanel";
import SideDrawer, {
  DRAWER_DEFAULT_WIDTH_PX,
  TAB_KEYS,
  clampDrawerWidth,
  type TabKey,
} from "./components/SideDrawer";
import { getRuns, isSelfEditRun, subscribeRuns, type RunState } from "./agentRuns";
import {
  applyServerMessage as applyDisplayResult,
  hasPendingDraft,
  subscribeResults,
} from "./displayResults";
import {
  hasLivePopup,
  openDisplayWindow,
  publish as publishWindowPayload,
  wireConsoleSide,
  writePopoutPreference,
} from "./displayWindow";
import { applyUiMessage, subscribeUiCommands } from "./uiCommands";
import { play as playSound, setSoundsEnabled, soundsEnabled } from "./sounds";
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

/** E3 — master sound toggle (bottombar). Plays the boot chirp on
 * re-enable as its own confirmation. */
function SoundToggle() {
  const [on, setOn] = useState(soundsEnabled);
  const toggle = () => {
    const next = !on;
    setSoundsEnabled(next);
    setOn(next);
    if (next) playSound("boot");
  };
  return (
    <button
      type="button"
      className="btn"
      onClick={toggle}
      title={on ? "Sounds on" : "Sounds off"}
    >
      {on ? "🔊" : "🔇"}
    </button>
  );
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
  useRTVIClientEvent(RTVIEvent.Error, (message: unknown) => {
    setError(errorText(message));
    playSound("fail"); // E3 — the error banner has a voice too
  });

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
          return;
        }
        // The Log is a drawer tab now (topbar-collapse) — these two
        // actions remain in the tool vocabulary as shortcuts for it.
        case "transcript_open": {
          if (drawerOpen && drawerTab === "transcript") {
            noop("The transcript is already open.");
            return;
          }
          setDrawerTab("transcript");
          setDrawerOpen(true);
          return;
        }
        case "transcript_close": {
          if (!drawerOpen || drawerTab !== "transcript") {
            noop("The transcript isn't open.");
            return;
          }
          setDrawerOpen(false);
          return;
        }
        default:
          // display_*/mic_*/wake_* belong to DisplayPanel/MicControls.
          return;
      }
    });
  }, [client, drawerOpen, drawerTab]);

  // Read-only subscription to the run store, for the D7 topbar indicator.
  // This must NOT register a second RTVI listener — AgentStatusPanel is the
  // single listener (plan D10).
  useEffect(() => subscribeRuns(setRuns), []);
  const devRunning = runs.some(
    (r) => isSelfEditRun(r.name, r.tools) && r.doneAt === null,
  );

  // Engagement plan E1 — amber needs-your-confirmation state, derived
  // from the display-results store's one rule (hasPendingDraft).
  const [attention, setAttention] = useState(hasPendingDraft);

  // Topbar ⧉ Display button: live state mirrors DisplayPanel's 1s poll
  // (named-window reuse has no open/close event to hook).
  const [displayLive, setDisplayLive] = useState(hasLivePopup);
  useEffect(() => {
    const id = window.setInterval(() => setDisplayLive(hasLivePopup()), 1000);
    return () => window.clearInterval(id);
  }, []);
  const openDisplay = () => {
    // Same semantics as DisplayPanel's ⧉: opening from the topbar also
    // opts in to future payloads going to the popup.
    writePopoutPreference(true);
    const win = openDisplayWindow();
    setDisplayLive(win !== null);
  };
  useEffect(
    () => subscribeResults(() => setAttention(hasPendingDraft())),
    [],
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

  // Topbar-collapse: one toggle button replaces the six per-tab buttons
  // (the drawer's own tab strip is the tab switcher; voice reaches tabs
  // directly). Toggle = open on the last-used tab / close.
  const toggleDrawer = () => setDrawerOpen((o) => !o);

  // T toggles the Log — now the drawer's transcript tab (three-case:
  // closed -> open on transcript; open on transcript -> close; open on
  // another tab -> switch). Escape closes the drawer (plan D20) —
  // window-level, one keyboard pattern, with the isTypingTarget guard so
  // Escape inside a panel's text input does not close the drawer out
  // from under the user mid-edit.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.repeat || isTypingTarget(e.target)) return;
      if (e.code === "KeyT") {
        if (drawerOpen && drawerTab === "transcript") {
          setDrawerOpen(false);
        } else {
          setDrawerTab("transcript");
          setDrawerOpen(true);
        }
      } else if (e.key === "Escape") {
        setDrawerOpen((o) => (o ? false : o));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [drawerOpen, drawerTab]);

  return (
    <div className="app">
      <VoiceWave state={voiceState} />
      <header className="topbar">
        <div className="brand">MORTIMER</div>
        <ConnectButton />
        <VoicePicker />
        {/* Topbar-collapse: ONE toggle replaces the old six per-tab
            buttons and the Log button — the drawer's own tab strip (now
            including a Log tab) is the switcher, and voice reaches every
            tab directly ("show me the runs"). The aggregate dot carries
            the D7/D31 always-visible signals (live self-edit run, new
            output) while the drawer is closed; the per-tab dots inside
            the drawer say which tab wants attention once it's open. */}
        <button
          type="button"
          className={drawerOpen ? "btn btn-active" : "btn"}
          aria-expanded={drawerOpen}
          onClick={toggleDrawer}
          title="Console panels (Esc closes · T opens the Log)"
        >
          {drawerOpen ? "◨ Close" : "◧ Panels"}
          {/* E1: attention (amber, pending confirmation) outranks the
              cyan live/new signal. */}
          {!drawerOpen && (devRunning || outputDot || attention) && (
            <span
              className={attention ? "btn-live-dot btn-live-dot-attn" : "btn-live-dot"}
              aria-hidden="true"
            />
          )}
        </button>
        {/* Persistent display-window control: the ⧉ inside DisplayPanel
            only exists while a result is showing, which left no way to
            open (or re-place) the second-screen window from an idle
            console. Opening with no payload shows "Waiting for a
            result…"; clicking while it's already open re-runs
            extended-screen placement (a no-op on browsers without the
            Window Management API — Safari drags it once by hand). */}
        <button
          type="button"
          className={displayLive ? "btn btn-active" : "btn"}
          onClick={openDisplay}
          title={
            displayLive
              ? "Display window is open — click to refocus / move it to the extra screen"
              : "Open the display window (park it on a second monitor)"
          }
        >
          ⧉ Display
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
          onTabChange={setDrawerTab}
          onClose={() => setDrawerOpen(false)}
          onWidthChange={setDrawerWidth}
        />
      </div>

      <footer className="bottombar">
        <MicControls />
        <SoundToggle />
        <div className="hints">SPACE talk · T transcript</div>
      </footer>

      {/* agent status window — live sub-agent progress (z-25) */}
      <AgentStatusPanel />

      {/* results window — floats in front of everything (z-30) */}
      <DisplayPanel />
    </div>
  );
}
