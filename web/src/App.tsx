import { useEffect, useState } from "react";
import { RTVIEvent } from "@pipecat-ai/client-js";
import {
  usePipecatClient,
  usePipecatClientTransportState,
  usePipecatConversation,
  useRTVIClientEvent,
} from "@pipecat-ai/client-react";
import type { ConversationMessage } from "@pipecat-ai/client-react";
import ConnectButton from "./components/ConnectButton";
import OrbField from "./components/OrbField";
import VoiceWave from "./components/VoiceWave";
import DisplayPanel from "./components/DisplayPanel";
import MicControls from "./components/MicControls";
import VoicePicker from "./components/VoicePicker";
import CapabilityChip from "./components/CapabilityChip";
import AgentRunFeeder from "./components/AgentRunFeeder";
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
  closeDisplayWindow,
  hasLivePopup,
  openDisplayWindow,
  publish as publishWindowPayload,
  wireConsoleSide,
  writePopoutPreference,
} from "./displayWindow";
import { confirmPopout, describePopoutFailure } from "./popoutWindow";
import { applyUiMessage, subscribeUiCommands } from "./uiCommands";
import { _setConversation } from "./conversationFeed";
import {
  closeDrawerWindow,
  hasLiveDrawerWindow,
  openDrawerWindow,
  readDrawerPopoutPreference,
  wireDrawerConsoleSide,
  writeDrawerPopoutPreference,
} from "./drawerRelay";
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

/**
 * ConversationFeeder — DP4's ONE remaining usePipecatConversation()
 * consumer. Headless (renders nothing): every time the session's message
 * list changes, it filters to visible user/assistant text (same filter
 * Transcript.tsx used to apply itself) and pushes the result into
 * conversationFeed.ts, which both the in-page Log tab and (via the drawer
 * relay) a popped-out drawer window read from. Keeping this the only
 * caller of the hook is what lets Transcript.tsx be reused, unmodified,
 * inside drawerMain.tsx's Vite entry — which must never construct a
 * PipecatClient or call a pipecat-client-react hook (DP1).
 */
function ConversationFeeder() {
  const { messages } = usePipecatConversation();
  useEffect(() => {
    const visible = messages.filter(
      (m) =>
        (m.role === "user" || m.role === "assistant") &&
        messageText(m).trim() !== "",
    );
    _setConversation(
      visible.map((m, i) => ({
        id: `${m.createdAt}-${i}`,
        role: m.role,
        createdAt: m.createdAt,
        text: messageText(m),
      })),
    );
  }, [messages]);
  return null;
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
  // listener in AgentRunFeeder, so two useRTVIClientEvent(ServerMessage)
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
  // Same idea for the drawer window's store relay (DP3) — separate
  // channel, separate wiring, same one-mount-is-enough guard internally.
  useEffect(() => wireDrawerConsoleSide(), []);

  // DP5: while a drawer window is alive, the in-page drawer body must not
  // render and the topbar Panels button switches meaning. Polled like
  // displayLive below (named-window reuse/heartbeat presence has no
  // single open/close event to hook).
  const [drawerWinLive, setDrawerWinLive] = useState(hasLiveDrawerWindow);
  useEffect(() => {
    const id = window.setInterval(() => setDrawerWinLive(hasLiveDrawerWindow()), 1000);
    return () => window.clearInterval(id);
  }, []);
  // S3: transient inline notices for a button-initiated popout that
  // fails confirmation — auto-dismiss, no persistent chrome.
  const [drawerPopoutError, setDrawerPopoutError] = useState<string | null>(null);
  useEffect(() => {
    if (!drawerPopoutError) return;
    const id = window.setTimeout(() => setDrawerPopoutError(null), 4000);
    return () => window.clearTimeout(id);
  }, [drawerPopoutError]);
  const [displayPopoutError, setDisplayPopoutError] = useState<string | null>(null);
  useEffect(() => {
    if (!displayPopoutError) return;
    const id = window.setTimeout(() => setDisplayPopoutError(null), 4000);
    return () => window.clearTimeout(id);
  }, [displayPopoutError]);
  const openDrawerPopout = (onFail?: (reason: string) => void) => {
    writeDrawerPopoutPreference(true);
    openDrawerWindow();
    // S3: openDrawerWindow()'s return value is uninformative on its own
    // — always null inside the shell (success arrives asynchronously via
    // the heartbeat) and also null when a browser blocks the popup.
    // Confirm via presence instead, and never persist the preference on
    // an unconfirmed open.
    void confirmPopout(hasLiveDrawerWindow).then((ok) => {
      setDrawerWinLive(ok);
      if (!ok) {
        writeDrawerPopoutPreference(false);
        const reason = describePopoutFailure();
        setDrawerPopoutError(reason);
        onFail?.(reason);
      }
    });
  };
  // Larry 2026-08-18: there was no click target anywhere to bring a
  // popped drawer back in-page — the topbar button only refocused it.
  // Same close path the "bring the panels back" voice command uses.
  const popInDrawer = () => {
    closeDrawerWindow();
    writeDrawerPopoutPreference(false);
    setDrawerWinLive(false);
  };
  // DP9: if a previous session left the popout preference on (the window
  // outlived the console's ref but died some other way before this load),
  // reopen it on the FIRST user gesture anywhere — matching browser popup
  // rules, which block window.open() outside a gesture. One-shot: removes
  // itself after firing, and never fires at all if a live window is
  // already found (nothing to reopen).
  useEffect(() => {
    if (!readDrawerPopoutPreference() || hasLiveDrawerWindow()) return;
    const onFirstGesture = () => {
      window.removeEventListener("pointerdown", onFirstGesture);
      if (!hasLiveDrawerWindow()) {
        openDrawerWindow();
        setDrawerWinLive(true);
      }
    };
    window.addEventListener("pointerdown", onFirstGesture);
    return () => window.removeEventListener("pointerdown", onFirstGesture);
  }, []);

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
        // DP6 — pop the panels out to the second screen / bring them back.
        case "drawer_popout": {
          if (drawerWinLive) {
            noop("The panels are already on the display screen.");
            return;
          }
          openDrawerPopout();
          return;
        }
        case "drawer_popin": {
          if (!drawerWinLive) {
            noop("The panels aren't popped out.");
            return;
          }
          closeDrawerWindow();
          writeDrawerPopoutPreference(false);
          setDrawerWinLive(false);
          return;
        }
        default:
          // display_*/mic_*/wake_* belong to DisplayPanel/MicControls.
          return;
      }
    });
  }, [client, drawerOpen, drawerTab, drawerWinLive]);

  // Read-only subscription to the run store, for the D7 topbar indicator.
  // This must NOT register a second RTVI listener — AgentRunFeeder is the
  // single listener (plan D10).
  useEffect(() => subscribeRuns(setRuns), []);
  const selfEditRunning = runs.some(
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
    writePopoutPreference(true);
    openDisplayWindow();
    void confirmPopout(hasLivePopup).then((ok) => {
      setDisplayLive(ok);
      if (!ok) {
        writePopoutPreference(false);
        setDisplayPopoutError(describePopoutFailure());
      }
    });
  };
  // Same pop-in gap, same fix, for the display window.
  const popInDisplay = () => {
    closeDisplayWindow();
    writePopoutPreference(false);
    setDisplayLive(false);
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
      <ConversationFeeder />
      <VoiceWave state={voiceState} />
      <header className="topbar">
        <div className="brand">MORTIMER</div>
        <ConnectButton />
        <VoicePicker />
        <CapabilityChip />
        {/* Topbar-collapse: ONE toggle replaces the old six per-tab
            buttons and the Log button — the drawer's own tab strip (now
            including a Log tab) is the switcher, and voice reaches every
            tab directly ("show me the runs"). The aggregate dot carries
            the D7/D31 always-visible signals (live self-edit run, new
            output) while the drawer is closed; the per-tab dots inside
            the drawer say which tab wants attention once it's open. */}
        <button
          type="button"
          className={drawerOpen || drawerWinLive ? "btn btn-active" : "btn"}
          aria-expanded={drawerOpen}
          onClick={() => (drawerWinLive ? openDrawerPopout() : toggleDrawer())}
          title={
            drawerWinLive
              ? "Panels are on the display screen — click to focus/move"
              : "Console panels (Esc closes · T opens the Log)"
          }
        >
          {/* DP5: while popped, the button's meaning and label change —
              it no longer toggles the in-page drawer (which is hidden),
              it refocuses/re-places the popped window. */}
          {drawerWinLive ? "◪ Panels ⧉" : drawerOpen ? "◨ Close" : "◧ Panels"}
          {/* E1: attention (amber, pending confirmation) outranks the
              cyan live/new signal. Fed by the same stores in both modes. */}
          {!drawerOpen && !drawerWinLive && (selfEditRunning || outputDot || attention) && (
            <span
              className={attention ? "btn-live-dot btn-live-dot-attn" : "btn-live-dot"}
              aria-hidden="true"
            />
          )}
        </button>
        {/* Same pop-in gap, same fix, for the display window. */}
        {displayLive && (
          <button
            type="button"
            className="btn btn-popin"
            onClick={popInDisplay}
            title="Bring the display back into this window"
          >
            ↩︎
          </button>
        )}
        {displayPopoutError && (
          <span className="popout-error-notice" role="status">
            {displayPopoutError}
          </span>
        )}
        {/* Larry 2026-08-18: while popped out, the button above only
            refocuses the popout — this is the click target that brings
            it back in-page (previously voice-only). */}
        {drawerWinLive && (
          <button
            type="button"
            className="btn btn-popin"
            onClick={popInDrawer}
            title="Bring the panels back into this window"
          >
            ↩︎
          </button>
        )}
        {drawerPopoutError && (
          <span className="popout-error-notice" role="status">
            {drawerPopoutError}
          </span>
        )}
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
          onClick={() => openDisplay()}
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
            existence, and the run store outlives the tab bodies. DP5:
            `open` is forced false while a drawer window is live — the
            underlying `drawerOpen`/`drawerTab` state is left untouched so
            it can be restored verbatim once the window closes (D41's
            fallback-never-loses-anything rule). */}
        <SideDrawer
          open={drawerOpen && !drawerWinLive}
          activeTab={drawerTab}
          width={drawerWidth}
          outputDot={outputDot}
          onTabChange={setDrawerTab}
          onClose={() => setDrawerOpen(false)}
          onWidthChange={setDrawerWidth}
          onPopOut={openDrawerPopout}
        />
      </div>

      <footer className="bottombar">
        <MicControls />
        <SoundToggle />
        <div className="hints">SPACE talk · T transcript</div>
      </footer>

      {/* Headless: owns the single RTVI ServerMessage subscription that
          feeds agentRuns.ts (plan D10). The live sub-agent view itself
          now lives in the drawer's Agents tab. */}
      <AgentRunFeeder />

      {/* results window — floats in front of everything (z-30) */}
      <DisplayPanel />
    </div>
  );
}
