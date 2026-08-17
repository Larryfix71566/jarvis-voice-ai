import { useCallback, useEffect, useRef, useState } from "react";
import type { KeyboardEvent, PointerEvent } from "react";
import GitPanel from "./GitPanel";
import EditModePanel from "./EditModePanel";
import MemoryPanel from "./MemoryPanel";
import RunsPanel from "./RunsPanel";
import DeveloperRunsTab from "./DeveloperRunsTab";
import OutputTab from "./OutputTab";
import Transcript from "./Transcript";
import { getRuns, isSelfEditRun, subscribeRuns } from "../agentRuns";
import { hasPendingDraft, subscribeResults } from "../displayResults";

/**
 * SideDrawer — the console's single right-side tabbed drawer
 * (MORTIMER_SIDE_DRAWER_PLAN.md).
 *
 * NAMING (plan D1/§0.4): this is the side DRAWER. "Sidecar" in this
 * codebase means the admin Python process on :7861 — never this.
 *
 * One container, one width, one resize handle, one open/closed state, and
 * exactly one visible body (plan D4) — which is what makes the old
 * "two .git-popover panels stacked at identical coordinates" defect
 * impossible by construction.
 *
 * It PUSHES the stage rather than covering it (plan D2/D3): the root is a
 * flex sibling of `.main` inside `.stage-row`, and its width is applied as
 * an inline `flexBasis` (plan D25). The element is always mounted so the
 * open/close transition has something to animate; only the tab strip and
 * the active body mount while open (plan D23), so no panel polls behind a
 * closed drawer.
 */

export type TabKey =
  | "repo"
  | "edit"
  | "memory"
  | "runs"
  | "developer"
  | "output" // plan D35 — drawer-routed display results (D28/D32)
  | "transcript"; // topbar-collapse: the Log folded in as a tab (the old
                  // standalone TranscriptDrawer is retired — one drawer,
                  // one right edge, no exclusivity dance)

/** Tab order in the strip — also the order used to validate a stored
 * `mortimer.drawer.tab` value in App.tsx (plan D13). */
export const TAB_KEYS: readonly TabKey[] = [
  "repo",
  "edit",
  "memory",
  "runs",
  "developer",
  "output",
  "transcript",
];

const TAB_LABELS: Record<TabKey, string> = {
  repo: "Repo",
  edit: "Edit",
  memory: "Memory",
  runs: "Runs",
  developer: "Developer",
  output: "Output",
  transcript: "Log",
};

// --- tuning knobs (plan §6) ---------------------------------------------

/** ⚙ TUNING KNOB — drawer width on first visit and after a handle
 * double-click (plan D12). */
export const DRAWER_DEFAULT_WIDTH_PX = 400;

/** ⚙ TUNING KNOB — narrowest the drawer may be dragged; below roughly this
 * the memory/runs panels stop being legible (plan D12). */
export const DRAWER_MIN_WIDTH_PX = 300;

/** ⚙ TUNING KNOB — arrow-key resize step in px (plan D20). */
export const DRAWER_RESIZE_KEY_STEP_PX = 16;

/** Widest the drawer may be, evaluated at drag time (plan D12) — the 60vw
 * ceiling is what stops a drag from squeezing the stage out of existence. */
export function drawerMaxWidthPx(): number {
  const vw = typeof window === "undefined" ? 1280 : window.innerWidth;
  return Math.min(720, vw * 0.6);
}

/** Clamp a candidate width into [MIN, MAX] (plan D12/D13). */
export function clampDrawerWidth(px: number): number {
  return Math.min(drawerMaxWidthPx(), Math.max(DRAWER_MIN_WIDTH_PX, px));
}

export interface SideDrawerProps {
  open: boolean;
  activeTab: TabKey;
  /** px; ignored while closed (plan D23) and in overlay mode (plan D16). */
  width: number;
  /** Plan D31 — a new drawer-routed result arrived while the drawer was
   * open on a tab other than Output. Owned by App.tsx (it decides the
   * three-case auto-open rule); this component only renders the dot. */
  outputDot: boolean;
  onTabChange: (tab: TabKey) => void;
  onClose: () => void;
  onWidthChange: (width: number) => void;
}

export default function SideDrawer({
  open,
  activeTab,
  width,
  outputDot,
  onTabChange,
  onClose,
  onWidthChange,
}: SideDrawerProps) {
  const [resizing, setResizing] = useState(false);
  const dragRef = useRef<{ startX: number; startWidth: number } | null>(null);
  const rafRef = useRef<number | null>(null);
  const pendingRef = useRef<number | null>(null);

  // Plan D7: the Developer TAB carries the same live indicator the topbar
  // button does, for when the drawer is already open. Read-only
  // subscription — no RTVI listener here (plan D10's single-listener rule).
  const [devRunning, setDevRunning] = useState(() =>
    getRuns().some((r) => isSelfEditRun(r.name, r.tools) && r.doneAt === null),
  );
  useEffect(
    () =>
      subscribeRuns((runs) =>
        setDevRunning(
          runs.some((r) => isSelfEditRun(r.name, r.tools) && r.doneAt === null),
        ),
      ),
    [],
  );

  // Engagement plan E1 — the Output tab's dot goes amber while the
  // newest result is a pending draft (same one-rule source as the
  // topbar toggle's dot).
  const [attention, setAttention] = useState(hasPendingDraft);
  useEffect(
    () => subscribeResults(() => setAttention(hasPendingDraft())),
    [],
  );

  // Width writes during a drag are coalesced into one rAF callback (plan
  // D12): every width change resizes .orb-field, which fires OrbField's
  // ResizeObserver, which re-renders every anchored status card — running
  // that chain at pointermove frequency is the jank this avoids.
  const queueWidth = useCallback(
    (px: number) => {
      pendingRef.current = px;
      if (rafRef.current !== null) return;
      rafRef.current = requestAnimationFrame(() => {
        rafRef.current = null;
        const next = pendingRef.current;
        pendingRef.current = null;
        if (next !== null) onWidthChange(next);
      });
    },
    [onWidthChange],
  );

  useEffect(() => {
    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    };
  }, []);

  const onHandlePointerDown = (e: PointerEvent<HTMLDivElement>) => {
    if (!open) return;
    e.preventDefault();
    // setPointerCapture is what makes a drag that leaves the element (or
    // the window) keep tracking, without a document-level listener (D11).
    e.currentTarget.setPointerCapture(e.pointerId);
    dragRef.current = { startX: e.clientX, startWidth: width };
    setResizing(true);
  };

  const onHandlePointerMove = (e: PointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    if (drag === null) return;
    // The handle is on the LEFT edge: dragging left grows the drawer.
    queueWidth(clampDrawerWidth(drag.startWidth + (drag.startX - e.clientX)));
  };

  const endDrag = (e: PointerEvent<HTMLDivElement>) => {
    if (dragRef.current === null) return;
    dragRef.current = null;
    setResizing(false);
    if (e.currentTarget.hasPointerCapture(e.pointerId)) {
      e.currentTarget.releasePointerCapture(e.pointerId);
    }
  };

  const onHandleKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "ArrowLeft") {
      e.preventDefault();
      onWidthChange(clampDrawerWidth(width + DRAWER_RESIZE_KEY_STEP_PX));
    } else if (e.key === "ArrowRight") {
      e.preventDefault();
      onWidthChange(clampDrawerWidth(width - DRAWER_RESIZE_KEY_STEP_PX));
    }
  };

  const renderBody = () => {
    switch (activeTab) {
      case "repo":
        return <GitPanel />;
      case "edit":
        return <EditModePanel />;
      case "memory":
        return <MemoryPanel />;
      case "runs":
        return <RunsPanel />;
      case "developer":
        return <DeveloperRunsTab />;
      case "output":
        return <OutputTab />;
      case "transcript":
        return <Transcript />;
    }
  };

  return (
    <aside
      className={
        "side-drawer" +
        (open ? " side-drawer-open" : "") +
        (resizing ? " side-drawer-resizing" : "")
      }
      style={{ flexBasis: open ? width : 0 }}
      aria-hidden={!open}
    >
      <div
        className="side-drawer-handle"
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize drawer"
        // Not focusable while closed: the root is aria-hidden then, and a
        // focusable descendant of an aria-hidden subtree is an a11y fault.
        tabIndex={open ? 0 : -1}
        onPointerDown={onHandlePointerDown}
        onPointerMove={onHandlePointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        onDoubleClick={() => onWidthChange(clampDrawerWidth(DRAWER_DEFAULT_WIDTH_PX))}
        onKeyDown={onHandleKeyDown}
      />

      {open && (
        <div className="side-drawer-inner">
          <div className="side-drawer-tabs" role="tablist" aria-label="Console panels">
            {TAB_KEYS.map((key) => (
              <button
                key={key}
                type="button"
                role="tab"
                id={`side-drawer-tab-${key}`}
                aria-selected={activeTab === key}
                aria-controls="side-drawer-body"
                className={
                  "side-drawer-tab" +
                  (activeTab === key ? " side-drawer-tab-active" : "")
                }
                onClick={() => onTabChange(key)}
              >
                {TAB_LABELS[key]}
                {key === "developer" && devRunning && (
                  <span className="side-drawer-tab-dot" aria-hidden="true" />
                )}
                {key === "output" && (outputDot || attention) && (
                  <span
                    className={
                      "side-drawer-tab-dot" +
                      (attention ? " side-drawer-tab-dot-attn" : "")
                    }
                    aria-hidden="true"
                  />
                )}
              </button>
            ))}
            <button
              type="button"
              className="side-drawer-close"
              onClick={onClose}
              aria-label="Close drawer"
            >
              ×
            </button>
          </div>

          <div
            className="side-drawer-body"
            id="side-drawer-body"
            role="tabpanel"
            aria-labelledby={`side-drawer-tab-${activeTab}`}
          >
            {renderBody()}
          </div>
        </div>
      )}
    </aside>
  );
}
