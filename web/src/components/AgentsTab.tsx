import { useEffect, useState } from "react";
import {
  MAX_AGENT_RUNS,
  STAGES,
  fmtElapsed,
  getRuns,
  removeRun,
  shortModel,
  subscribeRuns,
  type RunState,
} from "../agentRuns";

/**
 * AgentsTab — the side drawer's Agents tab body.
 *
 * Larry 2026-08-18: this used to be the Agents tab, showing ONLY the
 * runs isSelfEditRun() routed away from the satellite field (plan D9);
 * the other four sub-agents rendered as floating cards over the stage.
 * That split meant "where do I look for agent activity" had two answers.
 * Now every sub-agent run lands here, newest first, and the floating
 * cards are gone — the satellites remain the stage's ambient signal
 * (working pulse, done tick, hover for last task, click to filter Runs).
 *
 * Completed runs here do NOT auto-fade after 8s the way the anchored
 * cards did (plan D8): this is a surface the user deliberately opened to
 * read, and opening it just after a run finished should show what
 * happened, not an empty panel. The per-run dismiss button still removes
 * a settled run immediately.
 *
 * Registers no RTVI listener of its own — AgentRunFeeder is the single
 * listener (plan D10), and this component only subscribes to the store.
 */
export default function AgentsTab() {
  const [allRuns, setAllRuns] = useState<RunState[]>(getRuns);
  const [, setTick] = useState(0);

  useEffect(() => subscribeRuns(setAllRuns), []);

  // No agent filter any more — every sub-agent's runs belong here.
  const runs = allRuns
    .slice(-MAX_AGENT_RUNS)
    .reverse(); // newest first

  // 1s heartbeat to keep elapsed times live while anything is working.
  const anyWorking = runs.some((r) => r.doneAt === null);
  useEffect(() => {
    if (!anyWorking) return;
    const t = setInterval(() => setTick((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, [anyWorking]);

  const now = Date.now();

  return (
    <div className="agent-runs" aria-live="polite">
      <div className="panel-title">Agents</div>

      {runs.length === 0 ? (
        <div className="agent-runs-empty">No agent runs yet.</div>
      ) : (
        runs.map((r) => {
          const working = r.doneAt === null;
          const elapsed = fmtElapsed((r.doneAt ?? now) - r.startedAt);
          return (
            <div
              key={r.id}
              className={
                "agent-card developer-run-card" +
                (working
                  ? " agent-card-working"
                  : r.ok
                    ? " agent-card-ok"
                    : " agent-card-fail")
              }
            >
              <div className="agent-card-head">
                <span className="agent-card-dot" />
                <span className="agent-card-name">{r.displayName}</span>
                {/* Larry 2026-08-19 — which LLM is doing this work.
                    Shows the RESOLVED model, so a profile that silently
                    fell back to the voice model reads as the voice model
                    here (and gets the amber treatment), rather than
                    claiming the assignment it failed to get. Empty for
                    runs from a bot that predates the field. */}
                {r.model && (
                  <span
                    className={
                      "agent-card-model" +
                      /* K4 — unusable outranks fallback. A fallback still
                         has a working model behind it; an unusable
                         credential means every call fails, so it takes the
                         louder colour. */
                      (r.modelUnusable
                        ? " agent-card-model-unusable"
                        : r.modelFallback
                          ? " agent-card-model-fallback"
                          : "")
                    }
                    title={
                      r.modelUnusable
                        ? `${r.model} — credential refused: ${r.modelUnusableDetail || "every call through this model will fail"}`
                        : r.modelFallback
                          ? `${r.model} — fallback: the configured model profile could not be resolved`
                          : r.model
                    }
                  >
                    {shortModel(r.model)}
                    {r.modelUnusable ? " ✕" : r.modelFallback ? " ⚠" : ""}
                  </span>
                )}
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

              {!working && !r.ok && r.detail && (
                <div className="agent-card-detail">{r.detail}</div>
              )}
            </div>
          );
        })
      )}
    </div>
  );
}
