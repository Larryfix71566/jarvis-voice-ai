import { useState } from "react";
import { RTVIEvent } from "@pipecat-ai/client-js";
import { useRTVIClientEvent } from "@pipecat-ai/client-react";

/* MORTIMER_CONFIRMATION_AND_CAPABILITY_PLAN.md H2 — a self-contained
 * component with its own ServerMessage listener (same pattern as
 * VoicePicker: multiple components listening for DIFFERENT message
 * types is fine — the rule App.tsx's own listener comment states is
 * "no two listeners for the SAME type"). Renders nothing until a
 * "capability" message arrives, and nothing visible unless at least one
 * agent reports fallback:true — a clean boot shows no chip at all. */

interface CapabilityAgent {
  name: string;
  display_name: string;
  profile: string | null;
  resolved_model: string | null;
  fallback: boolean;
}

export default function CapabilityChip() {
  const [agents, setAgents] = useState<CapabilityAgent[]>([]);

  useRTVIClientEvent(RTVIEvent.ServerMessage, (data: unknown) => {
    const msg = data as { type?: string; agents?: CapabilityAgent[] };
    if (msg?.type === "capability" && Array.isArray(msg.agents)) {
      setAgents(msg.agents);
    }
  });

  const degraded = agents.filter((a) => a.fallback);
  if (degraded.length === 0) return null;

  const title = degraded
    .map(
      (a) =>
        `${a.display_name}: assigned ${a.profile ?? "a profile"}, ` +
        `running on ${a.resolved_model ?? "the fallback model"} instead`,
    )
    .join("\n");

  return (
    <span className="capability-chip" title={title} aria-live="polite">
      ⚠ {degraded.length === 1 ? degraded[0].display_name : `${degraded.length} agents`} degraded
    </span>
  );
}
