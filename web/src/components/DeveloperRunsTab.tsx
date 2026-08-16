import { useEffect, useState } from "react";
import {
  MAX_DEVELOPER_RUNS,
  STAGES,
  fmtElapsed,
  getRuns,
  isSelfEditRun,
  removeRun,
  subscribeRuns,
  type RunState,
} from "../agentRuns";

/**
 * DeveloperRunsTab — the side drawer's Developer tab body (plan §5.3).
 *
 * Renders the runs that isSelfEditRun() routes away from the satellite
 * field (plan D9), newest first, capped at MAX_DEVELOPER_RUNS. Unlike the
 * anchored cards, completed runs here do NOT auto-fade after 8s (plan D8):
 * this is a surface the user deliberately opened to read, and opening it
 * just after a run finished should show what happened, not an empty panel.
 * The per-run dismiss button still removes a settled run immediately.
 *
 * Registers no RTVI listener of its own — AgentStatusPanel is the single
 * listener (plan D10), and this component only subscribes to the store.
 */
export default function DeveloperRunsTab() {
  const [allRuns, setAllRuns] = useState<RunState[]>(getRuns);
  const [, setTick] = useState(0);

  useEffect(() => subscribeRuns(setAllRuns), []);

  const runs = allRuns
    .filter((r) => isSelfEditRun(r.name, r.tools))
    .slice(-MAX_DEVELOPER_RUNS)
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
    <div className="developer-runs" aria-live="polite">
      <div className="panel-title">Developer</div>

      {runs.length === 0 ? (
        <div className="developer-runs-empty">No development runs yet.</div>
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
