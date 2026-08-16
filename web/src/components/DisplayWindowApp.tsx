import { useEffect, useState } from "react";
import DisplayContent from "./DisplayContent";
import type { DisplayPayload } from "../displayResults";
import { subscribeDisplay } from "../displayWindow";
import "../displaywindow.css";

/**
 * DisplayWindowApp — root of the popped-out display window
 * (MORTIMER_SIDE_DRAWER_PLAN.md D39/D40/D43). Mounted by displayMain.tsx
 * into display.html, a SEPARATE Vite entry from the main console — this
 * module's import graph must never reach jarvisClient.ts (no mic access,
 * no PipecatClient, no session).
 *
 * Shows the latest informational payload only, full-bleed, on whichever
 * monitor the user has dragged this window to. `subscribeDisplay` posts
 * the {t:"hello"} replay handshake on mount so a window opened after a
 * result arrived is not blank.
 */
export default function DisplayWindowApp() {
  const [payload, setPayload] = useState<DisplayPayload | null>(null);

  useEffect(
    () =>
      subscribeDisplay((m) => {
        if (m.t === "payload") setPayload(m.payload);
        else if (m.t === "clear") setPayload(null);
      }),
    [],
  );

  if (!payload) {
    return <div className="display-window display-window-empty">Waiting for a result…</div>;
  }

  return (
    <div className="display-window">
      <div className="display-window-head">
        <span className="display-window-title">
          {payload.title ?? "Result"}
          {payload.agent && <span className="display-agent"> · {payload.agent}</span>}
        </span>
      </div>
      <DisplayContent payload={payload} />
    </div>
  );
}
