import { useCallback, useEffect, useRef, useState } from "react";
import { usePipecatClient } from "@pipecat-ai/client-react";
import DisplayContent from "./DisplayContent";
import type { DisplayPayload } from "../displayResults";
import {
  closeDisplayWindow,
  hasLivePopup,
  openDisplayWindow,
  readPopoutPreference,
  subscribeLatest,
  writePopoutPreference,
} from "../displayWindow";
import { subscribeUiCommands } from "../uiCommands";

/**
 * DisplayPanel — INFORMATIONAL results window floating in FRONT of
 * everything (z-30) (MORTIMER_SIDE_DRAWER_PLAN.md D28/D41/D43).
 *
 * Narrowed by the side-drawer plan: work-product results (diffs, commits,
 * app scaffolds) now go to the drawer's Output tab (OutputTab.tsx) — this
 * panel only ever shows `surface: "window"` payloads (a weather forecast
 * or research brief: glanceable, transient, answers a question you just
 * asked). It no longer listens to RTVI directly; App.tsx's single D30/D37
 * display listener dispatches by `surface` and calls
 * `displayWindow.publish()` for this panel's payloads.
 *
 * Also gains a pop-out (⧉) into a real second browser window that can be
 * parked on a second monitor (D39–D42). While a live popup exists, this
 * in-page window renders nothing — the result is showing on the other
 * screen — and reappears automatically if the popup is closed or blocked
 * (D41's mandatory fallback: an informational answer must never be
 * silently lost to a popup blocker).
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

// MORTIMER_PLAN_REVIEW_AND_DOCS_PLAN.md W1 — persisted, user-resized
// footprint, same read-guarded try/catch discipline as the drawer's
// `mortimer.drawer.*` keys.
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

export default function DisplayPanel() {
  const client = usePipecatClient();
  const [item, setItem] = useState<DisplayPayload | null>(null);
  const [dismissed, setDismissed] = useState(false);
  const [popupOpen, setPopupOpen] = useState(hasLivePopup);
  const [popout, setPopout] = useState(readPopoutPreference);
  const [pos, setPos] = useState<Pos>(() => ({
    x: Math.max(16, window.innerWidth - DEFAULT_W - 48),
    y: 72,
  }));
  // null = no user resize yet — the CSS default (max-width: 40vw;
  // max-height: 40vh, W1) governs; a resize (or a stored size from a
  // previous session) sets explicit inline dimensions that override it.
  const [size, setSize] = useState<Size | null>(readStoredDisplaySize);
  const resizeStartRef = useRef<{ x: number; y: number; w: number; h: number } | null>(null);

  // Re-clamp a stored/dragged size on viewport resize (W1).
  useEffect(() => {
    const onResize = () => {
      setSize((prev) => (prev === null ? null : clampDisplaySize(prev)));
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  // The shared "latest informational payload" — published by App.tsx's
  // surface dispatch. A new payload always un-dismisses the panel and, if
  // the popout preference is on, attempts to (re)open the popup.
  useEffect(
    () =>
      subscribeLatest((payload) => {
        setItem(payload);
        setDismissed(false);
        if (payload && popout && !hasLivePopup()) {
          const win = openDisplayWindow();
          setPopupOpen(win !== null);
          // win === null → browser blocked the popup; popupOpen stays
          // false, so the in-page panel below renders the fallback.
        }
      }),
    [popout],
  );

  // Named-window reuse (D41) has no single open/close event to hook, so a
  // short poll is what reliably brings the in-page fallback back when the
  // popup is closed by the user or the OS.
  useEffect(() => {
    const id = window.setInterval(() => setPopupOpen(hasLivePopup()), 1000);
    return () => window.clearInterval(id);
  }, []);

  const close = useCallback(() => setDismissed(true), []);

  const popOut = useCallback(() => {
    writePopoutPreference(true);
    setPopout(true);
    const win = openDisplayWindow();
    setPopupOpen(win !== null);
  }, []);

  // Esc closes.
  useEffect(() => {
    if (!item || popupOpen || dismissed) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [item, popupOpen, dismissed, close]);

  // Voice UI plan U2/U3: apply the display commands this component owns,
  // through the same code paths its buttons use. display_popout/close
  // also set/clear the persisted popout preference — voice has identical
  // semantics to clicking ⧉ (U3). A command that changes nothing sends
  // ui/noop with a spoken sentence — the bot voices it verbatim (no LLM).
  useEffect(() => {
    const noop = (reason: string) => {
      client?.sendClientMessage("ui/noop", { reason });
    };
    return subscribeUiCommands((cmd) => {
      switch (cmd.action) {
        case "display_popout": {
          if (hasLivePopup()) {
            noop("It's already showing on the display window.");
            return;
          }
          writePopoutPreference(true);
          setPopout(true);
          const win = openDisplayWindow();
          setPopupOpen(win !== null);
          if (win === null) {
            noop("The browser blocked the display window — it may need a popup permission.");
          }
          return;
        }
        case "display_close": {
          const hadPopup = hasLivePopup();
          if (!hadPopup && !popout) {
            noop("The display window is already closed.");
            return;
          }
          closeDisplayWindow();
          writePopoutPreference(false);
          setPopout(false);
          setPopupOpen(false);
          // The current payload falls back to the in-page overlay (D41).
          setDismissed(false);
          return;
        }
        case "overlay_dismiss": {
          if (!item || popupOpen || dismissed) {
            noop("There's nothing showing to dismiss.");
            return;
          }
          close();
          return;
        }
        default:
          return;
      }
    });
  }, [client, item, popupOpen, dismissed, popout, close]);

  // While a live popup exists, the result is showing on the other screen —
  // this window stays out of the way entirely (D41).
  if (!item || popupOpen || dismissed) return null;

  /** Drag the window by its header. */
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

  /** Resize from the bottom-right corner handle (W1) — same pointer-
   * capture drag pattern SideDrawer.tsx uses for its width handle, so
   * the drag keeps tracking even if the pointer leaves the handle. */
  const onResizePointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.currentTarget.setPointerCapture(e.pointerId);
    const current = size ?? { w: DEFAULT_W, h: DEFAULT_H };
    resizeStartRef.current = {
      x: e.clientX, y: e.clientY, w: current.w, h: current.h,
    };
  };

  const onResizePointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const start = resizeStartRef.current;
    if (start === null) return;
    setSize(
      clampDisplaySize({
        w: start.w + (e.clientX - start.x),
        h: start.h + (e.clientY - start.y),
      }),
    );
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
