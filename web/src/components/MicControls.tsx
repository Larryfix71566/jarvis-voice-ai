import { useEffect, useRef, useState } from "react";
import {
  usePipecatClient,
  usePipecatClientTransportState,
} from "@pipecat-ai/client-react";
import {
  startWakeWord,
  stopWakeWord,
  wakeWordAvailable,
} from "../wakeWord";

function isTypingTarget(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  const tag = el?.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
}

export default function MicControls() {
  const client = usePipecatClient();
  const state = usePipecatClientTransportState();
  const connected = state === "ready" || state === "connected";
  const [muted, setMuted] = useState(false);
  const [pttHeld, setPttHeld] = useState(false);
  const [wakeOn, setWakeOn] = useState(false);
  const [wakeError, setWakeError] = useState<string | null>(null);
  // Only auto-mute on keyup when this keydown did the unmute.
  const pttOwned = useRef(false);

  // Stop the wake-word listener when unmounted.
  useEffect(() => {
    return () => {
      void stopWakeWord();
    };
  }, []);

  useEffect(() => {
    if (!connected || !client) return;

    const down = (e: KeyboardEvent) => {
      if (e.code !== "Space" || e.repeat || isTypingTarget(e.target)) return;
      e.preventDefault();
      pttOwned.current = true;
      setPttHeld(true);
      client.enableMic(true);
    };
    const up = (e: KeyboardEvent) => {
      if (e.code !== "Space" || !pttOwned.current) return;
      pttOwned.current = false;
      setPttHeld(false);
      client.enableMic(false);
      setMuted(true);
    };
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
    };
  }, [client, connected]);

  const toggleMute = () => {
    if (!client) return;
    const next = !muted;
    client.enableMic(!next);
    setMuted(next);
  };

  const toggleWakeWord = async () => {
    if (wakeOn) {
      await stopWakeWord();
      setWakeOn(false);
      return;
    }
    try {
      setWakeError(null);
      // On wake: chime (inside wakeWord.ts) + unmute so Mortimer hears you.
      await startWakeWord(() => {
        client?.enableMic(true);
        setMuted(false);
      });
      setWakeOn(true);
    } catch (err) {
      setWakeError(err instanceof Error ? err.message : "wake word failed");
    }
  };

  const live = connected && !muted;
  return (
    <div className="mic-controls">
      <button
        type="button"
        className={live ? "btn btn-mic-on" : "btn btn-mic-off"}
        onClick={toggleMute}
        disabled={!connected}
      >
        {live ? "🎙 Mic on" : "🔇 Mic off"}
      </button>
      <span className={pttHeld ? "ptt ptt-live" : "ptt"}>
        {pttHeld ? "Talking…" : "Hold SPACE to talk"}
      </span>
      <button
        type="button"
        className={wakeOn ? "btn btn-wake-on" : "btn btn-wake-off"}
        onClick={toggleWakeWord}
        disabled={!wakeWordAvailable}
        title='Say "Mortimer" to unmute (local openWakeWord sidecar)'
      >
        {wakeOn ? "👂 Wake word on" : "Wake word off"}
      </button>
      {wakeError && <span className="wake-error">{wakeError}</span>}
    </div>
  );
}
