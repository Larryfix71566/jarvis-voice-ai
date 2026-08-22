import { useCallback, useEffect, useRef, useState } from "react";
import { usePipecatClient } from "@pipecat-ai/client-react";
import DisplayContent from "./DisplayContent";
import {
  closeDisplayWindow,
  closePanel,
  hasLivePopup,
  openDisplayWindow,
  popOutPanel,
  readPopoutPreference,
  restoreLatestAsPanel,
  subscribeEvictionNotice,
  subscribePanels,
  writePopoutPreference,
  type DisplayWindowPanel,
} from "../displayWindow";
import { confirmPopout, describePopoutFailure } from "../popoutWindow";
import { subscribeUiCommands } from "../uiCommands";

/**
 * DisplayPanel — container for INFORMATIONAL results windows floating in
 * FRONT of everything (z-30) (MORTIMER_SIDE_DRAWER_PLAN.md D28/D41/D43).
 *
 * G8 (MORTIMER_SESSION_GAPS_AND_SELFEDIT_CONVERGENCE_PLAN.md): this used
 * to render exactly one payload at a time — a follow-up result while the
 * first was still open silently replaced it. It now renders the FULL
 * in-page panel stack from displayWindow.ts's registry (`subscribePanels`),
 * each an independent `SingleDisplayPanel` with its own position, size,
 * and close button, cascade-offset so a new one never lands exactly on
 * top of the last. See displayWindow.ts's module docstring for why
 * pop-out (⧉) still targets the single external window rather than a
 * per-panel OS window.
 *
 * Narrowed by the side-drawer plan: work-product results (diffs, commits,
 * app scaffolds) now go to the drawer's Output tab (OutputTab.tsx) — this
 * container only ever shows `surface: "window"` payloads. It no longer
 * listens to RTVI directly; App.tsx's single D30/D37 display listener
 * dispatches by `surface` and calls `displayWindow.publish()`.
 */

interface Pos {
  x: number;
  y: number;
}

interface Size {
  w: number;
  h: number;
}

const DEFAULT_W = 540;
const DEFAULT_H = 420;

// G8 — successive panels cascade so they never land exactly on top of one
// another; wraps back to the top-left band after a few so it never marches
// fully off screen.
const CASCADE_STEP = 28;
const CASCADE_WRAP = 6;

// MORTIMER_PLAN_REVIEW_AND_DOCS_PLAN.md W1 — persisted, user-resized
// footprint, same read-guarded try/catch discipline as the drawer's
// `mortimer.drawer.*` keys. Shared across panels as the default for any
// NEW panel — the last size the user chose is the best guess for the
// next one, not per-panel persistence (which would need a growing key set
// for no real benefit).
const DISPLAY_SIZE_LS_KEY = "mortimer.display.size";

// W1 clamp bounds. Min keeps content legible; max is evaluated at drag/
// resize time since it depends on the current viewport.
const DISPLAY_SIZE_MIN_W = 280;
const DISPLAY_SIZE_MIN_H = 180;

function displayMaxSize(): Size {
  return { w: window.innerWidth * 0.9, h: window.innerHeight * 0.85 };
}

function clampDisplaySize(size: Size): Size {
  const max = displayMaxSize();
  return {
    w: Math.min(max.w, Math.max(DISPLAY_SIZE_MIN_W, size.w)),
    h: Math.min(max.h, Math.max(DISPLAY_SIZE_MIN_H, size.h)),
  };
}

function readStoredDisplaySize(): Size | null {
  try {
    const raw = localStorage.getItem(DISPLAY_SIZE_LS_KEY);
    if (raw === null) return null;
    const parsed: unknown = JSON.parse(raw);
    if (
      typeof parsed !== "object" || parsed === null ||
      typeof (parsed as Size).w !== "number" ||
      typeof (parsed as Size).h !== "number"
    ) {
      return null;
    }
    return clampDisplaySize(parsed as Size);
  } catch {
    return null;
  }
}

function writeStoredDisplaySize(size: Size): void {
  try {
    localStorage.setItem(DISPLAY_SIZE_LS_KEY, JSON.stringify(size));
  } catch {
    /* storage unavailable (private browsing, quota) — size just won't
       persist across reloads; resizing still works this session */
  }
}

function cascadePos(index: number): Pos {
  const slot = index % CASCADE_WRAP;
  return {
    x: Math.max(16, window.innerWidth - DEFAULT_W - 48 - slot * CASCADE_STEP),
    y: 72 + slot * CASCADE_STEP,
  };
}

interface SingleDisplayPanelProps {
  panel: DisplayWindowPanel;
  index: number;
  onClose: (id: string) => void;
  onPopOut: (id: string) => void;
}

function SingleDisplayPanel({ panel, index, onClose, onPopOut }: SingleDisplayPanelProps) {
  const item = panel.payload;
  const [popoutError, setPopoutError] = useState<string | null>(null);
  useEffect(() => {
    if (!popoutError) return;
    const id = window.setTimeout(() => setPopoutError(null), 4000);
    return () => window.clearTimeout(id);
  }, [popoutError]);
  const [pos, setPos] = useState<Pos>(() => cascadePos(index));
  const [size, setSize] = useState<Size | null>(readStoredDisplaySize);
  const resizeStartRef = useRef<{ x: number; y: number; w: number; h: number } | null>(null);

  useEffect(() => {
    const onResize = () => {
      setSize((prev) => (prev === null ? null : clampDisplaySize(prev)));
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  const close = useCallback(() => onClose(panel.id), [onClose, panel.id]);

  const popOut = useCallback(() => {
    writePopoutPreference(true);
    onPopOut(panel.id);
    void confirmPopout(hasLivePopup).then((ok) => {
      if (!ok) setPopoutError(describePopoutFailure());
    });
  }, [onPopOut, panel.id]);

  const onHeaderPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if ((e.target as HTMLElement).closest("button")) return;
    e.preventDefault();
    const start = { x: e.clientX - pos.x, y: e.clientY - pos.y };
    const move = (ev: PointerEvent) => {
      setPos({
        x: Math.min(Math.max(0, ev.clientX - start.x), window.innerWidth - 80),
        y: Math.min(Math.max(0, ev.clientY - start.y), window.innerHeight - 60),
      });
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  const onResizePointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.currentTarget.setPointerCapture(e.pointerId);
    const current = size ?? { w: DEFAULT_W, h: DEFAULT_H };
    resizeStartRef.current = { x: e.clientX, y: e.clientY, w: current.w, h: current.h };
  };

  const onResizePointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const start = resizeStartRef.current;
    if (start === null) return;
    setSize(clampDisplaySize({ w: start.w + (e.clientX - start.x), h: start.h + (e.clientY - start.y) }));
  };

  const endResize = (e: React.PointerEvent<HTMLDivElement>) => {
    if (resizeStartRef.current === null) return;
    resizeStartRef.current = null;
    if (e.currentTarget.hasPointerCapture(e.pointerId)) {
      e.currentTarget.releasePointerCapture(e.pointerId);
    }
    setSize((current) => {
      if (current !== null) writeStoredDisplaySize(current);
      return current;
    });
  };

  return (
    <div
      className="display-panel"
      style={{
        left: pos.x, top: pos.y,
        zIndex: 30 + index,
        ...(size !== null ? { width: size.w, height: size.h } : {}),
      }}
      role="dialog"
      aria-label={item.title ?? "Result"}
    >
      <div className="display-head" onPointerDown={onHeaderPointerDown}>
        <span className="display-title">
          {item.title ?? "Result"}
          {item.agent && <span className="display-agent"> · {item.agent}</span>}
        </span>
        <button
          type="button"
          className="btn display-popout"
          onClick={popOut}
          title="Pop out to a separate window (park on a second monitor)"
        >
          ⧉
        </button>
        {popoutError && (
          <span className="popout-error-notice" role="status">
            {popoutError}
          </span>
        )}
        <button type="button" className="btn display-close" onClick={close}>
          ×
        </button>
      </div>

      <DisplayContent payload={item} />

      <div
        className="display-resize"
        onPointerDown={onResizePointerDown}
        onPointerMove={onResizePointerMove}
        onPointerUp={endResize}
        onPointerCancel={endResize}
      />
    </div>
  );
}

export default function DisplayPanel() {
  const client = usePipecatClient();
  const [panels, setPanels] = useState<DisplayWindowPanel[]>([]);
  const [popupOpen, setPopupOpen] = useState(hasLivePopup);
  const [popout, setPopout] = useState(readPopoutPreference);
  const [evictionNotice, setEvictionNotice] = useState<string | null>(null);

  useEffect(() => subscribePanels(setPanels), []);

  useEffect(
    () =>
      subscribeEvictionNotice((text) => {
        setEvictionNotice(text);
        window.setTimeout(() => setEvictionNotice(null), 4000);
      }),
    [],
  );

  // Named-window reuse (D41) has no single open/close event to hook, so a
  // short poll is what reliably brings the in-page fallback back when the
  // popup is closed by the user or the OS. On the FALLING edge (was live,
  // now isn't), D41's mandatory fallback re-surfaces whatever was showing
  // externally as an in-page panel rather than losing it silently.
  useEffect(() => {
    const id = window.setInterval(() => {
      setPopupOpen((was) => {
        const now = hasLivePopup();
        if (was && !now) restoreLatestAsPanel();
        return now;
      });
    }, 1000);
    return () => window.clearInterval(id);
  }, []);

  const handleClose = useCallback((id: string) => closePanel(id), []);
  const handlePopOut = useCallback((id: string) => {
    popOutPanel(id);
    setPopout(true);
  }, []);

  // Esc closes the most recently opened (topmost) panel.
  useEffect(() => {
    if (panels.length === 0 || popupOpen) return;
    const topId = panels[panels.length - 1].id;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") closePanel(topId);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [panels, popupOpen]);

  // Voice UI plan U2/U3: apply the display commands this component owns,
  // through the same code paths its buttons use.
  useEffect(() => {
    const noop = (reason: string) => {
      client?.sendClientMessage("ui/noop", { reason });
    };
    return subscribeUiCommands((cmd) => {
      switch (cmd.action) {
        case "display_popout": {
          writePopoutPreference(true);
          setPopout(true);
          openDisplayWindow();
          void confirmPopout(hasLivePopup).then((ok) => {
            setPopupOpen(ok);
            if (!ok) noop(describePopoutFailure());
          });
          return;
        }
        case "display_close": {
          const hadPopup = hasLivePopup();
          if (!hadPopup && !popout && panels.length === 0) {
            noop("The display window is already closed.");
            return;
          }
          closeDisplayWindow();
          writePopoutPreference(false);
          setPopout(false);
          setPopupOpen(false);
          return;
        }
        case "overlay_dismiss": {
          if (panels.length === 0 || popupOpen) {
            noop("There's nothing showing to dismiss.");
            return;
          }
          closePanel(panels[panels.length - 1].id);
          return;
        }
        default:
          return;
      }
    });
  }, [client, panels, popupOpen, popout]);

  if (popupOpen) return null; // showing on the external window instead

  return (
    <>
      {panels.map((p, i) => (
        <SingleDisplayPanel
          key={p.id}
          panel={p}
          index={i}
          onClose={handleClose}
          onPopOut={handlePopOut}
        />
      ))}
      {evictionNotice && (
        <div className="display-eviction-notice" role="status">
          {evictionNotice}
        </div>
      )}
    </>
  );
}
