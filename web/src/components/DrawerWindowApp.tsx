import { useEffect, useState } from "react";
import GitPanel from "./GitPanel";
import EditModePanel from "./EditModePanel";
import MemoryPanel from "./MemoryPanel";
import RunsPanel from "./RunsPanel";
import DeveloperRunsTab from "./DeveloperRunsTab";
import OutputTab from "./OutputTab";
import Transcript from "./Transcript";
import { TAB_KEYS, type TabKey } from "./SideDrawer";
import { getRuns, isSelfEditRun, subscribeRuns } from "../agentRuns";
import { hasPendingDraft, subscribeResults } from "../displayResults";
import { wireDrawerWindowSide } from "../drawerRelay";

/**
 * DrawerWindowApp — root of the popped-out drawer window
 * (MORTIMER_DRAWER_POPOUT_PLAN.md DP1/DP3). Mounted by drawerMain.tsx into
 * drawer.html, a THIRD Vite entry alongside the main console and the
 * display window — this module's import graph must never reach
 * jarvisClient.ts (no mic access, no PipecatClient, no session; DP7: this
 * window is a work surface, never a second console).
 *
 * Renders the SAME tab strip and tab-body components the in-page
 * SideDrawer mounts, full-bleed (no width drag — the OS window is the
 * size control) and with its own active-tab persistence key
 * (`mortimer.drawerwin.tab`, deliberately separate from the in-page
 * drawer's `mortimer.drawer.tab` so the two don't fight over one key).
 *
 * Data supply (DP3): Repo/Edit/Memory/Runs fetch the admin sidecar
 * directly and work unchanged here. The Dev tab (agentRuns.ts), Output
 * tab (displayResults.ts), and Log tab (conversationFeed.ts, via
 * Transcript.tsx) have no RTVI connection in this window — they are fed
 * by `wireDrawerWindowSide`, which applies events relayed from the
 * console over the drawer's BroadcastChannel, including a replay
 * handshake on mount so a window opened mid-session is never blank.
 */

const TAB_LABELS: Record<TabKey, string> = {
  repo: "Repo",
  edit: "Edit",
  memory: "Memory",
  runs: "Runs",
  developer: "Developer",
  output: "Output",
  transcript: "Log",
};

const LS_TAB = "mortimer.drawerwin.tab";

function readStoredTab(): TabKey {
  try {
    const raw = localStorage.getItem(LS_TAB);
    return TAB_KEYS.includes(raw as TabKey) ? (raw as TabKey) : "runs";
  } catch {
    return "runs";
  }
}

function writeStoredTab(tab: TabKey): void {
  try {
    localStorage.setItem(LS_TAB, tab);
  } catch {
    /* storage unavailable — tab just won't persist across reopens */
  }
}

export default function DrawerWindowApp() {
  const [activeTab, setActiveTabState] = useState<TabKey>(readStoredTab);
  const [devRunning, setDevRunning] = useState(() =>
    getRuns().some((r) => isSelfEditRun(r.name, r.tools) && r.doneAt === null),
  );
  const [attention, setAttention] = useState(hasPendingDraft);

  const setActiveTab = (tab: TabKey) => {
    setActiveTabState(tab);
    writeStoredTab(tab);
  };

  useEffect(
    () =>
      subscribeRuns((runs) =>
        setDevRunning(
          runs.some((r) => isSelfEditRun(r.name, r.tools) && r.doneAt === null),
        ),
      ),
    [],
  );
  useEffect(() => subscribeResults(() => setAttention(hasPendingDraft())), []);

  // DP3/DP4: wires the relayed agentRuns/displayResults/conversationFeed
  // updates from the console, AND applies forwarded drawer_open/drawer_tab
  // voice commands (DP6) to this window's own tab state — the console
  // forwards them here instead of applying them in-page while this window
  // is live (uiCommands.ts's forwarding branch).
  useEffect(
    () =>
      wireDrawerWindowSide((action, tab) => {
        if ((action === "drawer_open" || action === "drawer_tab") && tab) {
          const t = TAB_KEYS.includes(tab as TabKey) ? (tab as TabKey) : null;
          if (t !== null) setActiveTab(t);
        }
      }),
    [],
  );

  const renderBody = () => {
    switch (activeTab) {
      case "repo":
        return <GitPanel />;
      case "edit":
        return <EditModePanel />;
      case "memory":
        return <MemoryPanel />;
      case "runs":
        return <RunsPanel />;
      case "developer":
        return <DeveloperRunsTab />;
      case "output":
        return <OutputTab />;
      case "transcript":
        return <Transcript />;
    }
  };

  return (
    <div className="drawer-window">
      <div className="side-drawer-tabs" role="tablist" aria-label="Console panels">
        {TAB_KEYS.map((key) => (
          <button
            key={key}
            type="button"
            role="tab"
            id={`drawer-window-tab-${key}`}
            aria-selected={activeTab === key}
            aria-controls="drawer-window-body"
            className={
              "side-drawer-tab" + (activeTab === key ? " side-drawer-tab-active" : "")
            }
            onClick={() => setActiveTab(key)}
          >
            {TAB_LABELS[key]}
            {key === "developer" && devRunning && (
              <span className="side-drawer-tab-dot" aria-hidden="true" />
            )}
            {key === "output" && attention && (
              <span className="side-drawer-tab-dot side-drawer-tab-dot-attn" aria-hidden="true" />
            )}
          </button>
        ))}
      </div>
      <div
        className="drawer-window-body"
        id="drawer-window-body"
        role="tabpanel"
        aria-labelledby={`drawer-window-tab-${activeTab}`}
      >
        {renderBody()}
      </div>
    </div>
  );
}
