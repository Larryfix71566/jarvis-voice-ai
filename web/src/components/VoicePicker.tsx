import { useState } from "react";
import { RTVIEvent } from "@pipecat-ai/client-js";
import {
  usePipecatClient,
  useRTVIClientEvent,
} from "@pipecat-ai/client-react";

interface Voice {
  id: string;
  label: string;
}

export default function VoicePicker() {
  const client = usePipecatClient();
  const [voices, setVoices] = useState<Voice[]>([]);
  const [current, setCurrent] = useState<string>("");

  useRTVIClientEvent(RTVIEvent.ServerMessage, (data: unknown) => {
    const msg = data as { type?: string; voices?: Voice[]; current?: string; voice?: string };
    if (msg?.type === "voice/catalog" && Array.isArray(msg.voices)) {
      setVoices(msg.voices.map((v) => ({ id: v.id, label: v.label })));
      setCurrent(msg.current ?? "");
    } else if (msg?.type === "voice/current" && typeof msg.voice === "string") {
      setCurrent(msg.voice); // reconcile optimistic select with server truth
    }
  });

  const onChange = (id: string) => {
    setCurrent(id); // optimistic; reconciled on voice/current
    client?.sendClientMessage("voice/set", { voice: id });
  };

  return (
    <label className="voice-picker">
      <span>Voice</span>
      <select
        value={current}
        onChange={(e) => onChange(e.target.value)}
        disabled={voices.length === 0}
      >
        {voices.length === 0 && <option value="">(connect first)</option>}
        {voices.map((v) => (
          <option key={v.id} value={v.id}>
            {v.label}
          </option>
        ))}
      </select>
    </label>
  );
}
