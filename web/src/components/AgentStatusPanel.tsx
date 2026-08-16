import { useCallback, useEffect, useState } from "react";
import { RTVIEvent } from "@pipecat-ai/client-js";
import { useRTVIClientEvent } from "@pipecat-ai/client-react";
import {
  ANCHORED_CARDS_MIN_STAGE_PX,
  ANCHORED_CARDS_MIN_WIDTH_PX,
  ASSUMED_CARD_HEIGHT_PX,
  CARD_GAP_PX,
  CARD_WIDTH_PX,
  TOPBAR_HEIGHT_PX,
  VIEWPORT_MARGIN_PX,
  agentViewportPosition,
  findAgentLayout,
  subscribeFieldRect,
  type AgentLayoutEntry,
  type FieldRect,
} from "../agentLayout";
import {
  STAGES,
  applyServerMessage,
  fmtElapsed,
  getRuns,
  isSelfEditRun,
  removeRun,
  subscribeRuns,
  type RunState,
} from "../agentRuns";

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
 *
 * Run STATE no longer lives here — it lives in agentRuns.ts (side-drawer
 * plan D10), because the Developer tab inside the side drawer renders from
 * the same store and its body unmounts on every tab switch. This component
 * is the ONE place that registers the RTVI ServerMessage listener (plan
 * D10's single-listener rule) and forwards it to applyServerMessage(); it
 * renders only the runs that are NOT routed to the Developer tab
 * (`!isSelfEditRun`, plan D9).
 *
 * Positioning (star-layout plan §5.3/§5.4): each card anchors near its
 * agent's satellite in OrbField instead of stacking in a fixed corner.
 * This component stays OUTSIDE .main and position: fixed (star plan D4) —
 * .orb-field has overflow: hidden and .main is a stacking context that
 * would trap cards under the top/bottom bars, so cards are positioned in
 * viewport pixels computed from OrbField's published field rect
 * (agentLayout.ts), not rendered inside OrbField itself.
 *
 * Below ANCHORED_CARDS_MIN_WIDTH_PX (viewport), below
 * ANCHORED_CARDS_MIN_STAGE_PX (measured stage width — side-drawer plan
 * D15), before the field has been measured, or for an agent not present in
 * the shared layout table, a card falls back to the original stacked
 * bottom-left column so it is never lost.
 */

/** Anchored card viewport position, clamped on-screen (star plan §5.4).
 *
 * Horizontal bounds derive from the field rect, not window.innerWidth
 * (side-drawer plan D14): with a pushing drawer the usable stage no longer
 * reaches the window's right edge, and a window-clamped card would slide
 * underneath the drawer. With the drawer closed the field spans the full
 * width, so the two are equivalent — this is the bound that was always
 * meant. Vertical bounds still use window.innerHeight; the drawer does not
 * affect vertical extent. */
function computeAnchoredStyle(
  entry: AgentLayoutEntry,
  fieldRect: FieldRect,
  cardHeight: number,
): { left: number; top: number } {
  const satellite = agentViewportPosition(entry, fieldRect);
  // agentViewportPosition only returns null when fieldRect is null, which
  // cannot happen here (fieldRect is a required non-null argument) — the
  // non-null assertion documents that invariant rather than silencing a
  // real possibility.
  const point = satellite!;

  let left: number;
  let top: number;
  switch (entry.cardAnchor) {
    case "above":
      left = point.x - CARD_WIDTH_PX / 2;
      top = point.y - CARD_GAP_PX - cardHeight;
      break;
    case "left":
      left = point.x - CARD_GAP_PX - CARD_WIDTH_PX;
      top = point.y - cardHeight / 2;
      break;
    case "right":
      left = point.x + CARD_GAP_PX;
      top = point.y - cardHeight / 2;
      break;
  }

  const stageLeft = fieldRect.left;
  const stageRight = fieldRect.left + fieldRect.width;
  const vh = window.innerHeight;
  const topFloor = TOPBAR_HEIGHT_PX + VIEWPORT_MARGIN_PX;

  if (left < stageLeft + VIEWPORT_MARGIN_PX) left = stageLeft + VIEWPORT_MARGIN_PX;
  if (left + CARD_WIDTH_PX > stageRight - VIEWPORT_MARGIN_PX) {
    left = stageRight - CARD_WIDTH_PX - VIEWPORT_MARGIN_PX;
  }
  if (top < topFloor) top = topFloor;
  if (top + cardHeight > vh - VIEWPORT_MARGIN_PX) {
    top = vh - cardHeight - VIEWPORT_MARGIN_PX;
  }

  return { left, top };
}

export default function AgentStatusPanel() {
  const [allRuns, setAllRuns] = useState<RunState[]>(getRuns);
  const [, setTick] = useState(0);

  // Star-layout positioning state (star plan §5.3).
  const [fieldRect, setFieldRect] = useState<FieldRect | null>(null);
  const [viewportWidth, setViewportWidth] = useState(
    typeof window === "undefined" ? ANCHORED_CARDS_MIN_WIDTH_PX : window.innerWidth,
  );
  const [cardHeights, setCardHeights] = useState<Record<number, number>>({});

  useEffect(() => subscribeRuns(setAllRuns), []);
  useEffect(() => subscribeFieldRect(setFieldRect), []);

  useEffect(() => {
    const onResize = () => setViewportWidth(window.innerWidth);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  // Drop measured heights for runs that no longer exist.
  useEffect(() => {
    setCardHeights((prev) => {
      const live = new Set(allRuns.map((r) => r.id));
      const stale = Object.keys(prev).filter((k) => !live.has(Number(k)));
      if (stale.length === 0) return prev;
      const next = { ...prev };
      for (const k of stale) delete next[Number(k)];
      return next;
    });
  }, [allRuns]);

  const measureCard = useCallback(
    (id: number) => (el: HTMLDivElement | null) => {
      if (!el) return;
      const h = el.getBoundingClientRect().height;
      setCardHeights((prev) => (prev[id] === h ? prev : { ...prev, [id]: h }));
    },
    [],
  );

  // 1s heartbeat to keep elapsed times live while anything is working.
  const anyWorking = allRuns.some((r) => r.doneAt === null);
  useEffect(() => {
    if (!anyWorking) return;
    const t = setInterval(() => setTick((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, [anyWorking]);

  // The single RTVI listener for agent lifecycle messages (plan D10).
  useRTVIClientEvent(RTVIEvent.ServerMessage, applyServerMessage);

  // Developer/self-edit runs render in the side drawer's Developer tab
  // (plan D9), not as anchored satellite cards.
  const runs = allRuns.filter((r) => !isSelfEditRun(r.name, r.tools));

  if (runs.length === 0) return null;

  const now = Date.now();

  // Star plan D12 + side-drawer D15: below the viewport breakpoint, below
  // the stage-width threshold, or before OrbField has published a field
  // rect, no card can be anchored — all of them fall back together.
  const canAnchor =
    viewportWidth >= ANCHORED_CARDS_MIN_WIDTH_PX &&
    fieldRect !== null &&
    fieldRect.width >= ANCHORED_CARDS_MIN_STAGE_PX;

  const anchored: Array<{ run: RunState; entry: AgentLayoutEntry }> = [];
  const fallback: RunState[] = [];
  for (const r of runs) {
    const entry = canAnchor ? findAgentLayout(r.name) : undefined;
    if (entry) {
      anchored.push({ run: r, entry });
    } else {
      fallback.push(r);
    }
  }

  const renderCardBody = (r: RunState) => {
    const working = r.doneAt === null;
    const elapsed = fmtElapsed((r.doneAt ?? now) - r.startedAt);
    return (
      <>
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
                  (working && i === r.tools.length - 1 ? " agent-tool-live" : "")
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
      </>
    );
  };

  const cardClassFor = (r: RunState) => {
    const working = r.doneAt === null;
    return (
      "agent-card" +
      (working ? " agent-card-working" : r.ok ? " agent-card-ok" : " agent-card-fail")
    );
  };

  return (
    <div className="agent-status" aria-live="polite">
      {anchored.map(({ run: r, entry }) => {
        const height = cardHeights[r.id] ?? ASSUMED_CARD_HEIGHT_PX;
        // fieldRect is non-null here — `entry` is only set when canAnchor
        // (which requires fieldRect !== null) was true above.
        const { left, top } = computeAnchoredStyle(entry, fieldRect!, height);
        return (
          <div
            key={r.id}
            ref={measureCard(r.id)}
            className={cardClassFor(r) + " agent-card-anchored"}
            style={{ left, top, width: CARD_WIDTH_PX }}
          >
            {renderCardBody(r)}
          </div>
        );
      })}

      {fallback.length > 0 && (
        <div className="agent-status-fallback">
          {fallback.map((r) => (
            <div key={r.id} ref={measureCard(r.id)} className={cardClassFor(r)}>
              {renderCardBody(r)}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
