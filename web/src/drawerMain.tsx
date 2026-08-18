import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import DrawerWindowApp from "./components/DrawerWindowApp";
// :root color/font tokens (App.css) plus the drawer's own chrome
// (sidedrawer.css) and the shared .display-* rendering CSS the Output tab
// reuses (command-deck.css) — CSS-only imports, no side effects.
//
// MORTIMER_DRAWER_POPOUT_PLAN.md DP1 (carried over verbatim from D39):
// this entry must NOT import "./App" or "./jarvisClient", directly or
// transitively, and must never use an @pipecat-ai/client-react hook —
// jarvisClient.ts patches getUserMedia and constructs a PipecatClient at
// module load time, and this window never has (and must never request)
// a voice session. Every tab component DrawerWindowApp renders (GitPanel,
// EditModePanel, MemoryPanel, RunsPanel, AgentsTab, OutputTab,
// Transcript) is already free of pipecat-client-react imports — verified
// by grep before this entry was wired up, and worth re-checking if any of
// them ever gains a new import.
import "./App.css";
import "./sidedrawer.css";
import "./drawerwindow.css";
import "./command-deck.css";
import "./editmode.css";
import "./memory.css";
import "./runs.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <DrawerWindowApp />
  </StrictMode>,
);
