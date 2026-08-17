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

  // Engagement plan E6 — dossier grouping by key prefix. The content is
  // the hero; keys render dimmed mono. Empty groups are omitted.
  const groups: { title: string; facts: Fact[] }[] = [
    {
      title: "About you",
      facts: facts.filter(
        (f) =>
          !f.key.startsWith("user.preference.") &&
          !f.key.startsWith("user.style."),
      ),
    },
    {
      title: "Preferences",
      facts: facts.filter((f) => f.key.startsWith("user.preference.")),
    },
    {
      title: "Style",
      facts: facts.filter((f) => f.key.startsWith("user.style.")),
    },
  ].filter((g) => g.facts.length > 0);

  const pendingObs = observations.filter((o) => !o.promoted);

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

      {facts.length === 0 && (
        <div className="memory-empty">No facts stored yet.</div>
      )}

      {groups.map((g) => (
        <div key={g.title} className="memory-card">
          <div className="memory-card-title">{g.title}</div>
          {g.facts.map((f) => (
            <div key={f.key} className="memory-fact-row">
              <div className="memory-fact-body">
                <span className="memory-fact-content">{f.content}</span>
                <span className="memory-fact-key">{f.key}</span>
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
      ))}

      {pendingObs.length > 0 && (
        <div className="memory-card">
          <div className="memory-card-title">Observations (not yet facts)</div>
          {pendingObs.map((o) => (
            <div key={o.key} className="memory-obs-row">
              <div className="memory-obs-body">
                <span className="memory-fact-content">{o.latest_content}</span>
                <span className="memory-fact-key">{o.key}</span>
              </div>
              <div
                className="memory-obs-bar"
                title={`${o.sessions}/${o.promote_after} sessions toward becoming a fact`}
              >
                <div
                  className="memory-obs-bar-fill"
                  style={{
                    width: `${Math.min(100, (o.sessions / o.promote_after) * 100)}%`,
                  }}
                />
              </div>
            </div>
          ))}
        </div>
      )}

      {summary && (
        <div className="memory-card memory-card-summary">
          <div className="memory-card-title">Session summary</div>
          <div className="memory-summary-text">{summary}</div>
        </div>
      )}

      {note && <div className="memory-note">{note}</div>}
    </div>
  );
}
