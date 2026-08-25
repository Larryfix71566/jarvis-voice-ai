import { useCallback, useEffect, useRef, useState } from "react";
import { marked } from "marked";
import DOMPurify from "dompurify";
import type { DisplayPayload } from "../displayResults";

/** Zoom bounds for the radar map (Larry 2026-08-22: "add the ability to
 * zoom on any weather map"). MAX is 4 rather than something larger for an
 * honest reason: the tiles are 512px each rendered into roughly a third of
 * the panel width (~180px), so there are only ~2.8x of REAL pixels to
 * reveal. Up to that point zooming shows genuine detail; past it the
 * browser is interpolating. 4 leaves a little headroom past the honest
 * limit without pretending resolution exists that doesn't — true deeper
 * zoom needs higher-z tiles from RainViewer, which is a backend change
 * (radar_tile_grid's RADAR_ZOOM), not a CSS one. */
const RADAR_ZOOM_MIN = 1;
const RADAR_ZOOM_MAX = 4;
const RADAR_ZOOM_STEP = 0.5;

/**
 * DisplayContent — shared payload rendering (MORTIMER_SIDE_DRAWER_PLAN.md
 * D43), lifted verbatim from the original DisplayPanel.tsx body.
 *
 * Three consumers share this: DisplayPanel (the floating in-page window),
 * OutputTab (the drawer's Output tab, D28/D32), and DisplayWindowApp (the
 * popped-out window, D39). Only the CONTAINER differs between them —
 * `.display-panel`/`-head`/`-resize` for the window, `.output-item*` for
 * the tab, `.display-window` for the popup — the markdown/tiles/gallery/
 * links rendering and its CSS (`.display-body`, `.display-markdown`,
 * `.display-tiles`, `.display-gallery`, `.display-links`) is identical and
 * shared, per D33 ("delete nothing, gain a second and third consumer").
 */

function renderMarkdown(body: string): string {
  const html = marked.parse(body, { async: false });
  return DOMPurify.sanitize(html);
}

/**
 * H3.3a — a copy button per command. Verified 2026-08-18: the app had no
 * copy affordance at all, so "copyable" meant dragging a selection across
 * a floating overlay, which is the fiddliness this exists to remove.
 *
 * The asymmetry worth remembering: clipboard WRITE works here because a
 * click is the user gesture the API requires. Clipboard READ from a voice
 * command has no gesture, which is why reads go through the sidecar's
 * pbpaste instead. Not an inconsistency — a consequence.
 */
function CommandLine({ command }: { command: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(command);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false); // selection still works as a fallback
    }
  }

  return (
    <li className="display-command">
      <code>{command}</code>
      <button
        type="button"
        className="display-command-copy"
        onClick={copy}
        aria-label={`Copy: ${command}`}
      >
        {copied ? "copied" : "copy"}
      </button>
    </li>
  );
}

/**
 * ZoomableMap — pan/zoom wrapper for the seamless 3×3 tile map.
 *
 * Lives in DisplayContent (not DisplayPanel) deliberately: all three
 * surfaces that render a payload share this component, so the in-page
 * panel, the drawer's Output tab, and the popped-out window all get zoom
 * from one implementation rather than three.
 *
 * Wheel zoom is attached via a ref with `{ passive: false }` — React's
 * onWheel is registered passive, so preventDefault() there is ignored and
 * the page scrolls behind the map instead of it zooming.
 */
function ZoomableMap({ children }: { children: React.ReactNode }) {
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const dragRef = useRef<{ x: number; y: number; panX: number; panY: number } | null>(null);

  // Pan is clamped so the map can never be dragged fully off its own
  // viewport: at zoom z the overflow is (z-1)/2 of each half-dimension.
  const clampPan = useCallback((next: { x: number; y: number }, z: number) => {
    const el = viewportRef.current;
    if (!el) return next;
    const maxX = (el.clientWidth * (z - 1)) / 2;
    const maxY = (el.clientHeight * (z - 1)) / 2;
    return {
      x: Math.min(maxX, Math.max(-maxX, next.x)),
      y: Math.min(maxY, Math.max(-maxY, next.y)),
    };
  }, []);

  const applyZoom = useCallback((next: number) => {
    const z = Math.min(RADAR_ZOOM_MAX, Math.max(RADAR_ZOOM_MIN, next));
    setZoom(z);
    setPan((p) => (z === 1 ? { x: 0, y: 0 } : clampPan(p, z)));
  }, [clampPan]);

  useEffect(() => {
    const el = viewportRef.current;
    if (el === null) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      applyZoom(zoom + (e.deltaY < 0 ? RADAR_ZOOM_STEP : -RADAR_ZOOM_STEP));
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [zoom, applyZoom]);

  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (zoom === 1) return; // nothing to pan at 1x
    e.preventDefault();
    e.currentTarget.setPointerCapture(e.pointerId);
    dragRef.current = { x: e.clientX, y: e.clientY, panX: pan.x, panY: pan.y };
  };

  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const start = dragRef.current;
    if (start === null) return;
    setPan(clampPan({
      x: start.panX + (e.clientX - start.x),
      y: start.panY + (e.clientY - start.y),
    }, zoom));
  };

  const endDrag = (e: React.PointerEvent<HTMLDivElement>) => {
    dragRef.current = null;
    if (e.currentTarget.hasPointerCapture(e.pointerId)) {
      e.currentTarget.releasePointerCapture(e.pointerId);
    }
  };

  return (
    <div className="display-map">
      <div
        className="display-map-viewport"
        ref={viewportRef}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        onDoubleClick={() => applyZoom(zoom >= RADAR_ZOOM_MAX ? 1 : zoom + 1)}
        style={{ cursor: zoom === 1 ? "zoom-in" : dragRef.current ? "grabbing" : "grab" }}
      >
        <div
          className="display-map-inner"
          style={{
            transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
          }}
        >
          {children}
        </div>
      </div>
      <div className="display-map-controls">
        <button
          type="button"
          className="btn"
          onClick={() => applyZoom(zoom - RADAR_ZOOM_STEP)}
          disabled={zoom <= RADAR_ZOOM_MIN}
          aria-label="Zoom out"
        >
          −
        </button>
        <span className="display-map-level">{zoom.toFixed(1)}×</span>
        <button
          type="button"
          className="btn"
          onClick={() => applyZoom(zoom + RADAR_ZOOM_STEP)}
          disabled={zoom >= RADAR_ZOOM_MAX}
          aria-label="Zoom in"
        >
          +
        </button>
        {zoom > 1 && (
          <button
            type="button"
            className="btn"
            onClick={() => applyZoom(1)}
            aria-label="Reset zoom"
          >
            Reset
          </button>
        )}
      </div>
    </div>
  );
}

/** Wraps children in ZoomableMap only for a seamless tile map — a plain
 * multi-image gallery has no single map to pan, so it renders untouched. */
function Maybe(
  { zoomable, children }: { zoomable: boolean; children: React.ReactNode },
) {
  return zoomable ? <ZoomableMap>{children}</ZoomableMap> : <>{children}</>;
}

export default function DisplayContent({ payload }: { payload: DisplayPayload }) {
  const images = payload.images ?? [];
  const basemapImages = payload.basemap_images ?? [];
  const links = payload.links ?? [];
  const commands = payload.commands ?? [];
  // 9 radar tiles form one seamless 3×3 map; anything else is a gallery.
  const seamless = images.length === 9;
  // W6 (MORTIMER_WEATHER_FAHRENHEIT_AND_RADAR_PLAN.md) — only meaningful
  // for the seamless 3×3 radar case; a plain gallery has no basemap.
  const hasBasemap = seamless && basemapImages.length === images.length;

  return (
    <div className="display-body">
      {commands.length > 0 && (
        <div className="display-commands">
          {payload.note && <p className="display-command-note">{payload.note}</p>}
          <ul>
            {commands.map((c, i) => (
              <CommandLine key={`${i}-${c}`} command={c} />
            ))}
          </ul>
          {payload.expect_output && (
            <p className="display-command-return">
              Copy the output, then say “read my clipboard”
            </p>
          )}
        </div>
      )}

      {payload.content !== undefined && (
        <div className="display-clipboard">
          <p className="display-clipboard-head">
            {payload.chars} characters{payload.truncated ? " (truncated)" : ""} — shown
            here only, not saved
          </p>
          <pre>{payload.content}</pre>
        </div>
      )}

      {payload.kind === "image" && images.length > 0 && (
        <>
          <Maybe zoomable={seamless}>
          <div
            className={
              hasBasemap
                ? "display-tiles display-tiles-radar"
                : seamless
                ? "display-tiles"
                : "display-gallery"
            }
          >
            {hasBasemap &&
              basemapImages.map((src, i) => (
                // W6: the basemap grid sits UNDERNEATH the precipitation
                // overlay via CSS grid-area stacking (command-deck.css) —
                // both grids render the SAME 3×3 layout, one on top of
                // the other, at the SAME z/x/y coordinates the backend
                // already guaranteed match (jarvis/bot/display.py).
                <img
                  key={`basemap-${i}-${src}`}
                  src={src}
                  alt=""
                  aria-hidden="true"
                  className="display-tile-basemap"
                  style={{ gridArea: `tile-${i}` }}
                />
              ))}
            {images.map((src, i) => (
              <img
                key={src}
                src={src}
                alt={payload.title ?? "result image"}
                className={hasBasemap ? "display-tile-overlay" : undefined}
                style={hasBasemap ? { gridArea: `tile-${i}` } : undefined}
              />
            ))}
          </div>
          </Maybe>
          {hasBasemap && (
            <p className="display-basemap-attribution">
              Basemap © CARTO, © OpenStreetMap contributors
            </p>
          )}
        </>
      )}

      {payload.body && (
        <div
          className="display-markdown"
          // Body is agent-generated markdown → sanitized HTML.
          dangerouslySetInnerHTML={{ __html: renderMarkdown(payload.body) }}
        />
      )}

      {links.length > 0 && (
        <ul className="display-links">
          {links.map((l) => (
            <li key={l.url}>
              <a href={l.url} target="_blank" rel="noreferrer">
                {l.label || l.url}
              </a>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
