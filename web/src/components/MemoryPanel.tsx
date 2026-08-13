import { useCallback, useEffect, useState } from "react";

const API = "http://localhost:7861";

interface Fact {
  key: string;
  content: string;
  source_session_id: string | null;
  updated_at: string;
}

interface ObservationGroup {
  key: string;
  sessions: number;
  promote_after: number;
  latest_content: string;
  promoted: boolean;
}

interface Usage {
  fact_count: number;
  max_facts: number;
  max_context_chars: number;
  over_capacity: boolean;
}

interface Overview {
  ok: boolean;
  facts: Fact[];
  summary: string;
  observations: ObservationGroup[];
  usage: Usage;
}

/**
 * MemoryPanel — visibility/correction surface for Mortimer's long-term
 * memory (plan Phase 5e). The only correction path before this was
 * spoken "forget that," which requires already knowing the bad fact
 * exists. This panel lists everything Mortimer has learned (facts,
 * pending/promoted behavioral observations, the running summary, and
 * capacity usage against the Phase 5c prioritization cap) and lets the
 * user delete a fact directly.
 */
export default function MemoryPanel() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [unreachable, setUnreachable] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const r = await fetch(`${API}/api/memory`);
      setOverview(await r.json());
      setUnreachable(false);
    } catch {
      setUnreachable(true);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const t = setInterval(refresh, 15000);
    return () => clearInterval(t);
  }, [refresh]);

  const onDelete = async (key: string) => {
    setNote(null);
    const r = await fetch(`${API}/api/memory/fact/${encodeURIComponent(key)}`, {
      method: "DELETE",
    });
    const res = await r.json();
    setNote(res.ok ? `Forgot "${key}".` : (res.error ?? "delete failed"));
    void refresh();
  };

  if (unreachable) {
    return (
      <div className="memory-panel">
        <div className="panel-title">Memory</div>
        <div className="memory-offline">admin sidecar offline</div>
      </div>
    );
  }

  if (!overview) {
    return (
      <div className="memory-panel">
        <div className="panel-title">Memory</div>
      </div>
    );
  }

  const { facts, summary, observations, usage } = overview;

  return (
    <div className="memory-panel">
      <div className="panel-title">Memory</div>

      <div className="memory-usage">
        <span className={usage.over_capacity ? "memory-usage-over" : "memory-usage-ok"}>
          {usage.fact_count} / {usage.max_facts} facts
        </span>
        {usage.over_capacity && (
          <span className="memory-usage-note">
            over capacity — user.* facts prioritized, oldest others dropped
          </span>
        )}
      </div>

      {facts.length === 0 ? (
        <div className="memory-empty">No facts stored yet.</div>
      ) : (
        <div className="memory-facts">
          {facts.map((f) => (
            <div key={f.key} className="memory-fact-row">
              <div className="memory-fact-body">
                <span className="memory-fact-key">{f.key}</span>
                <span className="memory-fact-content">{f.content}</span>
              </div>
              <button
                type="button"
                className="memory-fact-delete"
                onClick={() => void onDelete(f.key)}
                aria-label={`Forget ${f.key}`}
                title="Forget this fact"
              >
                ×
              </button>
            </div>
          ))}
        </div>
      )}

      {summary && (
        <div className="memory-summary">
          <div className="memory-section-label">Running summary</div>
          <div className="memory-summary-text">{summary}</div>
        </div>
      )}

      {observations.length > 0 && (
        <div className="memory-observations">
          <div className="memory-section-label">Learning (not yet facts)</div>
          {observations
            .filter((o) => !o.promoted)
            .map((o) => (
              <div key={o.key} className="memory-obs-row">
                <span className="memory-obs-key">{o.key}</span>
                <span className="memory-obs-progress">
                  {o.sessions}/{o.promote_after} sessions
                </span>
              </div>
            ))}
        </div>
      )}

      {note && <div className="memory-note">{note}</div>}
    </div>
  );
}
