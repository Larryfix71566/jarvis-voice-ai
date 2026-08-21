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

/** K5 — the four knowledge layers, from GET /api/knowledge. */
interface Knowledge {
  ok: boolean;
  memory: {
    live: number;
    archived: number;
    tiers: Record<string, number>;
    reaching_prompt: number;
    not_reaching_prompt: number;
    context_chars: number;
  };
  procedures: Record<string, number>;
  skills: {
    on_disk: number;
    invalid: number;
    registered: number;
    enabled: { name: string; has_scripts: boolean }[];
  };
  workflows: { name: string; source: string; has_done_when: boolean }[];
}

interface Overview {
  ok: boolean;
  facts: Fact[];
  summary: string;
  observations: ObservationGroup[];
  usage: Usage;
}

/** MORTIMER_MEMORY_AUTOCONSOLIDATION_PLAN.md A3 — one row per
 * contradiction/cluster/audience item the sweep queued rather than
 * resolving on its own. `keys` has 2 entries for cluster/contradiction,
 * 1 for audience. */
interface MemoryReview {
  id: number;
  kind: "cluster" | "contradiction" | "audience";
  keys: string[];
  detail: string;
  status: string;
  created_at: string;
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
  const [knowledge, setKnowledge] = useState<Knowledge | null>(null);
  const [reviews, setReviews] = useState<MemoryReview[]>([]);
  const [rewriteDrafts, setRewriteDrafts] = useState<Record<number, string>>({});
  const [unreachable, setUnreachable] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const r = await fetch(`${API}/api/memory`);
      setOverview(await r.json());
      // K5: the four layers. Failing to load this must not blank the
      // panel — memory visibility is the more important half.
      try {
        const k = await fetch(`${API}/api/knowledge`);
        const kj = (await k.json()) as Knowledge;
        setKnowledge(kj.ok ? kj : null);
      } catch {
        setKnowledge(null);
      }
      // A3: the review queue. Same "must not blank the panel" discipline.
      try {
        const rv = await fetch(`${API}/api/memory/reviews`);
        const rvj = await rv.json();
        setReviews(rvj.ok ? rvj.reviews : []);
      } catch {
        setReviews([]);
      }
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

  const onResolveReview = async (
    id: number,
    action: string,
    rewriteContent?: string,
  ) => {
    setNote(null);
    const r = await fetch(`${API}/api/memory/reviews/${id}/resolve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, rewrite_content: rewriteContent ?? null }),
    });
    const res = await r.json();
    setNote(res.ok ? "Review resolved." : (res.error ?? "resolve failed"));
    void refresh();
  };

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

      {/* K5 — the four knowledge layers. The number that matters is
          `not_reaching_prompt`: on 2026-08-18 the store held 180 facts
          and ~14 reached the Supervisor, discoverable ONLY by reading a
          log line. Truncation is visible here now. */}
      {knowledge && (
        <div className="knowledge-layers">
          <div className="knowledge-row">
            <span className="knowledge-label">Memory</span>
            <span className="knowledge-value">
              {knowledge.memory.live} live
              {knowledge.memory.archived > 0 &&
                ` · ${knowledge.memory.archived} archived`}
            </span>
          </div>
          <div className="knowledge-tiers">
            {(["identity", "preference", "project", "system"] as const).map((t) =>
              knowledge.memory.tiers[t] ? (
                <span key={t} className="knowledge-tier">
                  {t} {knowledge.memory.tiers[t]}
                  {t === "system" && " (hidden)"}
                </span>
              ) : null,
            )}
          </div>
          {knowledge.memory.not_reaching_prompt > 0 && (
            <div className="knowledge-warn" role="status">
              {knowledge.memory.not_reaching_prompt} of {knowledge.memory.live}{" "}
              facts do not reach the prompt ({knowledge.memory.reaching_prompt}{" "}
              do, {knowledge.memory.context_chars} chars)
            </div>
          )}
          <div className="knowledge-row">
            <span className="knowledge-label">Procedures</span>
            <span className="knowledge-value">
              {Object.entries(knowledge.procedures)
                .map(([k, v]) => `${v} ${k}`)
                .join(" · ") || "none"}
            </span>
          </div>
          {/* K3 — "on disk" and "enabled" are deliberately separate.
              A large gap is the normal state after importing skills:
              each one is inert until its name is added by hand to
              config/skills.yaml, which is the individual review Larry
              asked for. Only `invalid` is a defect. */}
          <div className="knowledge-row">
            <span className="knowledge-label">Skills</span>
            <span className="knowledge-value">
              {knowledge.skills
                ? `${knowledge.skills.enabled.length} enabled of ${knowledge.skills.on_disk} on disk`
                : "none"}
              {knowledge.skills?.invalid ? ` · ${knowledge.skills.invalid} invalid` : ""}
            </span>
          </div>
          <div className="knowledge-row">
            <span className="knowledge-label">Workflows</span>
            <span className="knowledge-value">
              {knowledge.workflows.length || "none"}
              {knowledge.workflows.some((w) => !w.has_done_when) &&
                ` · ${knowledge.workflows.filter((w) => !w.has_done_when).length} without done_when`}
            </span>
          </div>
        </div>
      )}

      {/* A3 — Larry resolves what the sweep would not (contradictions,
          mixed-content clusters it capped/skipped, task-rule/implemented
          audience calls). Amber matches the engagement layer's existing
          needs-your-confirmation semantic (--attn), same vocabulary as
          .knowledge-warn above. */}
      {reviews.length > 0 && (
        <div className="memory-review-section">
          <div className="memory-review-title">
            Needs your review ({reviews.length})
          </div>
          {reviews.map((rv) => (
            <div key={rv.id} className="memory-review-row">
              <div className="memory-review-detail">{rv.detail}</div>
              <div className="memory-review-keys">{rv.keys.join(" · ")}</div>
              <div className="memory-review-actions">
                {rv.kind === "audience" ? (
                  <>
                    {rv.detail.includes("task rule") ? (
                      <button
                        type="button"
                        onClick={() => void onResolveReview(rv.id, "convert_workflow")}
                      >
                        Convert to workflow
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={() => void onResolveReview(rv.id, "archive_implemented")}
                      >
                        Archive as implemented
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => void onResolveReview(rv.id, "keep_interaction")}
                    >
                      Keep as-is
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      type="button"
                      onClick={() => void onResolveReview(rv.id, "keep_a")}
                    >
                      Keep {rv.keys[0]}
                    </button>
                    {rv.keys[1] && (
                      <button
                        type="button"
                        onClick={() => void onResolveReview(rv.id, "keep_b")}
                      >
                        Keep {rv.keys[1]}
                      </button>
                    )}
                    <input
                      type="text"
                      placeholder="rewrite instead…"
                      className="memory-review-rewrite-input"
                      value={rewriteDrafts[rv.id] ?? ""}
                      onChange={(e) =>
                        setRewriteDrafts((prev) => ({ ...prev, [rv.id]: e.target.value }))
                      }
                    />
                    <button
                      type="button"
                      disabled={!rewriteDrafts[rv.id]}
                      onClick={() =>
                        void onResolveReview(rv.id, "rewrite", rewriteDrafts[rv.id])
                      }
                    >
                      Rewrite
                    </button>
                  </>
                )}
                <button
                  type="button"
                  className="memory-review-dismiss"
                  onClick={() => void onResolveReview(rv.id, "dismiss")}
                  title="Both are true — leave as-is, don't ask again"
                >
                  Dismiss
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

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
