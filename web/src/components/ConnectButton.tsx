import { useState } from "react";
import { usePipecatClientTransportState } from "@pipecat-ai/client-react";
import { connect, disconnect } from "../jarvisClient";

const PILL_CLASS: Record<string, string> = {
  disconnected: "pill pill-idle",
  error: "pill pill-error",
};

function pillClass(state: string): string {
  if (state === "ready" || state === "connected") return "pill pill-ready";
  return PILL_CLASS[state] ?? "pill pill-busy"; // amber for connecting etc.
}

export default function ConnectButton() {
  const state = usePipecatClientTransportState();
  const [busy, setBusy] = useState(false);
  const connected = state === "ready" || state === "connected";
  const connecting = !connected && state !== "disconnected" && state !== "error";

  const onClick = async () => {
    setBusy(true);
    try {
      if (connected) {
        await disconnect();
      } else {
        await connect();
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="connect-group">
      <button
        type="button"
        className={connected ? "btn btn-danger" : "btn btn-primary"}
        onClick={onClick}
        disabled={busy || connecting}
      >
        {connected ? "Disconnect" : connecting ? "Connecting…" : "Connect"}
      </button>
      <span className={pillClass(state)}>{state}</span>
    </div>
  );
}
