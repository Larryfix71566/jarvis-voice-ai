import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import DisplayWindowApp from "./components/DisplayWindowApp";
// :root color/font tokens (App.css) and the shared .display-* rendering
// CSS (command-deck.css) — CSS-only imports, no side effects. This entry
// must NOT import "./App" or "./jarvisClient", directly or transitively:
// jarvisClient.ts patches getUserMedia and constructs a PipecatClient at
// module load time (plan D39), and App.tsx's hooks require a
// PipecatClientProvider this window never has.
import "./App.css";
import "./command-deck.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <DisplayWindowApp />
  </StrictMode>,
);
