import { useCallback, useEffect, useState } from "react";
import { AGENT_LAYOUT } from "../agentLayout";
import {
  consumeRequestedAgentFilter,
  subscribeAgentFilter,
} from "../agentRuns";
import { relTime } from "../timeFormat";

const API = "http://localhost:7861";

// Run status taxonomy (run-logging plan D9) — orphaned is a presentation-
// only label applied by the server, never stored.
type RunStatus = "ok" | "failed" | "timeout" | "running" | "orphaned";

const STATUSES: RunStatus[] = ["ok", "failed", "timeout", "running", "orphaned"];

interface RunRow {
  run_id: string;
  session_id: string | null;
  agent: string;
  display_name: string;
  task: string;
  status: RunStatus;
  started_at: string;
  ended_at: string | null;
  latency_ms: number | null;
  tool_count: number;
  // MORTIMER_AGENT_TRUST_PLAN.md D5 — optional because a row written
  // before migration 0008 has neither; render falls back to tool_count.
  tools_ok?: number;
  tools_failed?: number;
  error: string | null;
  reply_preview: string | null;
  payload_path: string | null;
}

interface AgentEvent {
  id: number;
  run_id: string;
  seq: number;
  type: "tool_call" | "tool_result" | "mcp_call";
  tool: string | null;
  server: string | null;
  ok: number | null;
  latency_ms: number | null;
  args_preview: string | null;
  result_preview: string | null;
  created_at: string;
}

// Discriminated union mirroring the JSONL payload schema exactly
// (MORTIMER_RUN_LOGGING_PLAN.md §5.3a, D19) — kept in sync with
// jarvis/runlog/store.py's record shapes; tsc catches drift on `type`.
type PayloadRecord =
  | { type: "run_start"; seq: number; run_id: string; agent: string;
      display_name: string; session_id: string | null; task: string;
      started_at: string }
  | { type: "tool_call"; seq: number; tool: string; arguments: unknown;
      at: string }
  | { type: "tool_result"; seq: number; tool: string; ok: boolean;
      latency_ms: number; result: unknown; at: string }
  | { type: "mcp_call"; seq: number; tool: string; server: string;
      ok: boolean; latency_ms: number; error: string | null; at: string }
  | { type: "run_end"; seq: number; status: string; latency_ms: number | null;
      tool_count: number; reply: unknown; error: string | null;
      ended_at: string }
  | { type: "truncated"; seq: number; reason: "events" | "bytes";
      dropped_after_seq: number; at: string };

interface RunDetail {
  run: RunRow;
  events: AgentEvent[];
  payload: PayloadRecord[];
}

const STATUS_CLASS: Record<RunStatus, string> = {
  ok: "run-status-ok",
  failed: "run-status-failed",
  timeout: "run-status-dim",
  orphaned: "run-status-dim",
  running: "run-status-live",
};

/**
 * RunsPanel — read-only review surface for the sub-agent run log
 * (MORTIMER_RUN_LOGGING_PLAN.md, D12/D15). Every delegation writes a run
 * via jarvis/agents/base.py's SubAgent.run(); this panel is the console
 * counterpart to `python -m jarvis.runlog`, reading the same
 * GET /api/runs / GET /api/runs/{run_id} endpoints. No delete, no re-run —
 * deletion is retention pruning's job (D10), and a re-run action is a
 * separate confirmation-gated feature, not this panel's.
 */
export default function RunsPanel() {
  const [runs, setRuns] = useState<RunRow[] | null>(null);
  const [unreachable, setUnreachable] = useState(false);
  // E5: a satellite click may have requested a filter before this tab
  // body mounted — consume it at mount, and stay subscribed for clicks
  // while mounted.
  const [agentFilter, setAgentFilter] = useState(
    () => consumeRequestedAgentFilter() ?? "",
  );
  useEffect(() => subscribeAgentFilter(setAgentFilter), []);
  const [statusFilter, setStatusFilter] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (agentFilter) params.set("agent", agentFilter);
      if (statusFilter) params.set("status", statusFilter);
      const r = await fetch(`${API}/api/runs?${params.toString()}`);
      const res = await r.json();
      setRuns(res.runs ?? []);
      setUnreachable(false);
    } catch {
      setUnreachable(true);
    }
  }, [agentFilter, statusFilter]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const toggleExpand = async (runId: string) => {
    if (expanded === runId) {
      setExpanded(null);
      setDetail(null);
      return;
    }
    setExpanded(runId);
    setDetail(null);
    setDetailLoading(true);
    try {
      const r = await fetch(`${API}/api/runs/${encodeURIComponent(runId)}`);
      const res = await r.json();
      setDetail(res.ok ? res : null);
    } catch {
      setDetail(null);
    } finally {
      setDetailLoading(false);
    }
  };

  if (unreachable) {
    return (
      <div className="runs-panel">
        <div className="panel-title">Runs</div>
        <div className="runs-offline">admin sidecar offline</div>
      </div>
    );
  }

  return (
    <div className="runs-panel">
      <div className="panel-title">Runs</div>

      <div className="runs-filters">
        <select
          value={agentFilter}
          onChange={(e) => setAgentFilter(e.target.value)}
          className="runs-filter-select"
        >
          <option value="">all agents</option>
          {AGENT_LAYOUT.map((a) => (
            <option key={a.key} value={a.key}>{a.label}</option>
          ))}
        </select>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="runs-filter-select"
        >
          <option value="">all statuses</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <button type="button" className="runs-refresh" onClick={() => void refresh()}>
          ↻
        </button>
      </div>

      {!runs ? (
        <div className="runs-empty">loading…</div>
      ) : runs.length === 0 ? (
        <div className="runs-empty">
          No runs yet — try "check how my computer is doing".
        </div>
      ) : (
        <div className="runs-list">
          {runs.map((r) => (
            <div key={r.run_id} className="runs-row-wrap">
              <button
                type="button"
                className="runs-row"
                onClick={() => void toggleExpand(r.run_id)}
              >
                <span className={`runs-dot ${STATUS_CLASS[r.status]}`} />
                <span className="runs-agent">{r.display_name || r.agent}</span>
                <span className="runs-time">{relTime(r.started_at)}</span>
                <span className="runs-latency">
                  {r.latency_ms !== null ? `${r.latency_ms}ms` : "-"}
                </span>
                <span className="runs-tools" title="tool calls: ok/failed">
                  {r.tools_ok !== undefined && r.tools_failed !== undefined
                    ? `${r.tools_ok}/${r.tools_failed}`
                    : r.tool_count}
                </span>
                <span className="runs-task">{r.task}</span>
              </button>

              {expanded === r.run_id && (
                <div className="runs-detail">
                  {detailLoading && <div className="runs-empty">loading…</div>}
                  {!detailLoading && !detail && (
                    <div className="runs-empty">failed to load detail</div>
                  )}
                  {!detailLoading && detail && (
                    <>
                      {detail.run.error && (
                        <div className="runs-detail-error">{detail.run.error}</div>
                      )}
                      <div className="runs-events">
                        {detail.events.map((ev) => (
                          <div key={ev.id} className="runs-event-row">
                            <span className="runs-event-seq">[{ev.seq}]</span>
                            <span className="runs-event-type">{ev.type}</span>
                            <span className="runs-event-tool">{ev.tool ?? "-"}</span>
                            {ev.ok !== null && (
                              <span className={ev.ok ? "run-status-ok" : "run-status-failed"}>
                                {ev.ok ? "ok" : "failed"}
                              </span>
                            )}
                            {ev.latency_ms !== null && (
                              <span className="runs-event-latency">{ev.latency_ms}ms</span>
                            )}
                          </div>
                        ))}
                      </div>
                      {detail.payload.length === 0 ? (
                        <div className="runs-empty">
                          payload pruned or unavailable
                        </div>
                      ) : (
                        <div className="runs-payload">
                          {detail.payload.map((rec) => (
                            <pre key={rec.seq} className="runs-payload-record">
                              {JSON.stringify(rec, null, 2)}
                            </pre>
                          ))}
                        </div>
                      )}
                    </>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
