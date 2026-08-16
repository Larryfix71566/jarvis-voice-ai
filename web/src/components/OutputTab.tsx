import { useEffect, useRef, useState } from "react";
import {
  clearResults,
  getResults,
  removeResult,
  subscribeResults,
  type DisplayResult,
} from "../displayResults";
import { relTimeFromMs } from "../timeFormat";
import DisplayContent from "./DisplayContent";

/**
 * OutputTab — the drawer's Output tab body (MORTIMER_SIDE_DRAWER_PLAN.md
 * D28/D32). Shows DRAWER-ROUTED work-product results (diffs, commits,
 * app scaffolds) as a bounded, newest-first, collapsible list — never the
 * informational answers, which stay in the floating/pop-out window
 * (displayWindow.ts). Registers no RTVI listener of its own (D30) — all
 * state comes from the displayResults.ts store, which App.tsx's single
 * display listener feeds.
 */
export default function OutputTab() {
  const [results, setResults] = useState<DisplayResult[]>(getResults);
  const [expandedId, setExpandedId] = useState<number | null>(
    () => getResults()[0]?.id ?? null,
  );
  const lastNewestId = useRef<number | null>(getResults()[0]?.id ?? null);

  useEffect(
    () =>
      subscribeResults((next) => {
        setResults(next);
        const newest = next[0]?.id ?? null;
        // Auto-expand only a genuinely NEW newest item (D32) — not every
        // store update, which would re-expand after the user collapsed it.
        if (newest !== null && newest !== lastNewestId.current) {
          setExpandedId(newest);
        }
        lastNewestId.current = newest;
      }),
    [],
  );

  const toggle = (id: number) => setExpandedId((cur) => (cur === id ? null : id));

  return (
    <div className="output-tab">
      <div className="panel-title">
        Output
        {results.length > 0 && (
          <button type="button" className="output-clear" onClick={clearResults}>
            Clear
          </button>
        )}
      </div>

      {results.length === 0 ? (
        <div className="output-empty">No output yet.</div>
      ) : (
        <div className="output-list">
          {results.map((r) => (
            <div key={r.id} className="output-item">
              <div
                className="output-item-head"
                role="button"
                tabIndex={0}
                onClick={() => toggle(r.id)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    toggle(r.id);
                  }
                }}
                aria-expanded={expandedId === r.id}
              >
                <span className="output-item-title">{r.payload.title ?? "Result"}</span>
                {r.payload.agent && (
                  <span className="output-item-agent">{r.payload.agent}</span>
                )}
                <span className="output-item-time">{relTimeFromMs(r.receivedAt)}</span>
                <button
                  type="button"
                  className="output-item-remove"
                  aria-label="Dismiss"
                  onClick={(e) => {
                    e.stopPropagation();
                    removeResult(r.id);
                  }}
                >
                  ×
                </button>
              </div>
              {expandedId === r.id && (
                <div className="output-item-body">
                  <DisplayContent payload={r.payload} />
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
