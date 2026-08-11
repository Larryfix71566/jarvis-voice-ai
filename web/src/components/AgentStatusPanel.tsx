import { useCallback, useEffect, useRef, useState } from "react";
import { RTVIEvent } from "@pipecat-ai/client-js";
import { useRTVIClientEvent } from "@pipecat-ai/client-react";

/**
 * AgentStatusPanel — live status window for delegated sub-agent runs.
 *
 * The bot emits one card lifecycle per delegation over the RTVI
 * server-message channel:
 *   {"type":"agent","name","display_name","state":"working","task"}
 *   {"type":"agent_tool","name","display_name","tool"}          (progress)
 *   {"type":"agent","name","display_name","state":"done","ok","detail"}
 * This panel opens a card on "working", appends tool chips as progress
 * arrives, and settles it on "done": success fades out after a few
 * seconds; failures stay until dismissed, showing the failure reason.
 * Development/self-edit runs additionally get a stage readout derived
 * from the tools being called (planning → proposing → validating →
 * submitting). OrbField's satellites read the same events — this panel
 * is the detailed view, satellites stay the ambient one.
 */

const DONE_FADE_MS = 8000;
const MAX_TOOLS = 10;
const STAGES = ["planning", "proposing", "validating", "submitting"] as const;

interface RunState {
  id: number;
  name: string;
  displayName: string;
  task: string;
  tools: string[];
  stage: number; // index into STAGES (self-edit runs only)
  startedAt: number;
  doneAt: number | null;
  ok: boolean;
  detail: string;
}

interface AgentLifecycleMsg {
  type?: string;
  name?: string;
  display_name?: string;
  state?: string;
  task?: string;
  ok?: boolean;
  detail?: string;
  tool?: string;
}

function clamp(s: string, max: number): string {
  const t = s.trim().replace(/\s+/g, " ");
  return t.length > max ? t.slice(0, max - 1) + "…" : t;
}

function fmtElapsed(ms: number): string {
  const s = Math.max(0, Math.round(ms / 1000));
  const m = Math.floor(s / 60);
  return m > 0 ? `${m}:${String(s % 60).padStart(2, "0")}` : `${s}s`;
}

/** Map a tool name onto a self-edit stage. */
function toolStage(tool: string): number {
  const t = tool.toLowerCase();
  if (/valid|test|pytest|check/.test(t)) return 2;
  if (/submit|push|pull_request|\bpr\b/.test(t)) return 3;
  if (/propos|write|edit|apply|patch|create/.test(t)) return 1;
  return 0;
}

/** Development runs (developer agent / selfedit_* tools) get stages. */
function isSelfEditRun(name: string, tools: string[]): boolean {
  const n = name.toLowerCase();
  return (
    n.includes("self") ||
    n.includes("edit") ||
    n.includes("develop") ||
    tools.some((t) => t.toLowerCase().startsWith("selfedit"))
  );
}

export default function AgentStatusPanel() {
  const [runs, setRuns] = useState<RunState[]>([]);
  const seq = useRef(0);
  const runIds = useRef(new Map<string, number>()); // agent name -> live run id
  const timers = useRef(new Map<number, ReturnType<typeof setTimeout>>());
  const [, setTick] = useState(0);

  const clearTimer = (id: number) => {
    const t = timers.current.get(id);
    if (t !== undefined) {
      clearTimeout(t);
      timers.current.delete(id);
    }
  };

  const removeRun = useCallback((id: number) => {
    setRuns((rs) => {
      const run = rs.find((r) => r.id === id);
      if (run) runIds.current.delete(run.name);
      return rs.filter((r) => r.id !== id);
    });
    const t = timers.current.get(id);
    if (t !== undefined) {
      clearTimeout(t);
      timers.current.delete(id);
    }
  }, []);

  // Unmount: cancel pending fade removals.
  useEffect(() => {
    const pending = timers.current;
    return () => pending.forEach((t) => clearTimeout(t));
  }, []);

  // 1s heartbeat to keep elapsed times live while anything is working.
  const anyWorking = runs.some((r) => r.doneAt === null);
  useEffect(() => {
    if (!anyWorking) return;
    const t = setInterval(() => setTick((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, [anyWorking]);

  useRTVIClientEvent(RTVIEvent.ServerMessage, (data: unknown) => {
    const msg = data as AgentLifecycleMsg;
    if (typeof msg?.type !== "string" || typeof msg?.name !== "string") return;
    const name = msg.name;
    const displayName =
      typeof msg.display_name === "string" && msg.display_name !== ""
        ? msg.display_name
        : name;

    if (msg.type === "agent" && msg.state === "working") {
      // Fresh run for this agent — replaces any previous card.
      const prevId = runIds.current.get(name);
      if (prevId !== undefined) clearTimer(prevId);
      seq.current += 1;
      const id = seq.current;
      runIds.current.set(name, id);
      const run: RunState = {
        id,
        name,
        displayName,
        task: typeof msg.task === "string" ? clamp(msg.task, 200) : "",
        tools: [],
        stage: 0,
        startedAt: Date.now(),
        doneAt: null,
        ok: false,
        detail: "",
      };
      setRuns((rs) => [...rs.filter((r) => r.name !== name), run]);
    } else if (msg.type === "agent_tool" && typeof msg.tool === "string") {
      const tool = msg.tool;
      setRuns((rs) =>
        rs.map((r) =>
          r.name === name && r.doneAt === null
            ? {
                ...r,
                displayName,
                tools: [...r.tools, tool].slice(-MAX_TOOLS),
                stage: Math.max(r.stage, toolStage(tool)),
              }
            : r,
        ),
      );
    } else if (msg.type === "agent" && msg.state === "done") {
      // Bots predating ok/detail send neither — assume success.
      const ok = msg.ok !== false;
      const detail = typeof msg.detail === "string" ? clamp(msg.detail, 300) : "";
      setRuns((rs) =>
        rs.map((r) =>
          r.name === name && r.doneAt === null
            ? { ...r, displayName, doneAt: Date.now(), ok, detail }
            : r,
        ),
      );
      const id = runIds.current.get(name);
      if (ok && id !== undefined) {
        clearTimer(id);
        timers.current.set(
          id,
          setTimeout(() => removeRun(id), DONE_FADE_MS),
        );
      }
    }
  });

  if (runs.length === 0) return null;

  const now = Date.now();
  return (
    <div className="agent-status" aria-live="polite">
      {runs.map((r) => {
        const working = r.doneAt === null;
        const elapsed = fmtElapsed((r.doneAt ?? now) - r.startedAt);
        const cardClass =
          "agent-card" +
          (working
            ? " agent-card-working"
            : r.ok
              ? " agent-card-ok"
              : " agent-card-fail");
        return (
          <div key={r.id} className={cardClass}>
            <div className="agent-card-head">
              <span className="agent-card-dot" />
              <span className="agent-card-name">{r.displayName}</span>
              <span className="agent-card-time">
                {working ? elapsed : `${r.ok ? "done" : "failed"} · ${elapsed}`}
              </span>
              {!working && (
                <button
                  type="button"
                  className="agent-card-close"
                  onClick={() => removeRun(r.id)}
                  aria-label="Dismiss"
                >
                  ×
                </button>
              )}
            </div>

            {r.task && <div className="agent-card-task">{r.task}</div>}

            {r.tools.length > 0 && (
              <div className="agent-card-tools">
                {r.tools.map((t, i) => (
                  <span
                    key={`${r.id}-${i}`}
                    className={
                      "agent-tool" +
                      (working && i === r.tools.length - 1
                        ? " agent-tool-live"
                        : "")
                    }
                  >
                    {t}
                  </span>
                ))}
              </div>
            )}

            {isSelfEditRun(r.name, r.tools) && (
              <div className="agent-stages">
                {STAGES.map((s, i) => (
                  <span
                    key={s}
                    className={
                      "agent-stage" +
                      (i <= r.stage ? " agent-stage-hit" : "") +
                      (working && i === r.stage ? " agent-stage-live" : "")
                    }
                  >
                    {s}
                  </span>
                ))}
              </div>
            )}

            {!working && !r.ok && r.detail && (
              <div className="agent-card-detail">{r.detail}</div>
            )}
          </div>
        );
      })}
    </div>
  );
}
