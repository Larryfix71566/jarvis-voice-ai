import { useCallback, useEffect, useRef, useState } from "react";
import { RTVIEvent } from "@pipecat-ai/client-js";
import { useRTVIClientEvent } from "@pipecat-ai/client-react";
import { marked } from "marked";
import DOMPurify from "dompurify";

/**
 * DisplayPanel — results window floating in FRONT of everything (z-30).
 *
 * When a sub-agent's tool produces something worth seeing (research
 * findings, a weather radar, a project plan, a coding diff/commit
 * summary), the bot sends {"type":"display","display":{...}} over the
 * RTVI server-message channel and this window opens with it. Markdown
 * bodies are rendered (sanitized), image payloads show as a seamless
 * tile grid (e.g. the 3×3 radar mosaic), and link lists open in new
 * tabs. Drag by the header, resize from the corner, Esc or × to close.
 */

interface DisplayLink {
  label?: string;
  url: string;
}

export interface DisplayPayload {
  kind?: string; // "markdown" | "image" | "links"
  title?: string;
  body?: string; // markdown
  images?: string[];
  links?: DisplayLink[];
  agent?: string;
  ts?: number;
}

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

function renderMarkdown(body: string): string {
  const html = marked.parse(body, { async: false });
  return DOMPurify.sanitize(html);
}

export default function DisplayPanel() {
  const [item, setItem] = useState<DisplayPayload | null>(null);
  const [pos, setPos] = useState<Pos>(() => ({
    x: Math.max(16, window.innerWidth - DEFAULT_W - 48),
    y: 72,
  }));
  const [size, setSize] = useState<Size>({ w: DEFAULT_W, h: DEFAULT_H });
  const panelRef = useRef<HTMLDivElement | null>(null);

  // Incoming display payloads from the bot.
  useRTVIClientEvent(RTVIEvent.ServerMessage, (data: unknown) => {
    const msg = data as { type?: string; display?: DisplayPayload };
    if (msg?.type !== "display" || !msg.display) return;
    setItem(msg.display);
  });

  const close = useCallback(() => setItem(null), []);

  // Esc closes.
  useEffect(() => {
    if (!item) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [item, close]);

  if (!item) return null;

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

  /** Resize from the bottom-right corner handle. */
  const onResizePointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    e.preventDefault();
    const start = { x: e.clientX, y: e.clientY, w: size.w, h: size.h };
    const move = (ev: PointerEvent) => {
      setSize({
        w: Math.min(Math.max(320, start.w + ev.clientX - start.x), window.innerWidth - 32),
        h: Math.min(Math.max(200, start.h + ev.clientY - start.y), window.innerHeight - 32),
      });
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  const images = item.images ?? [];
  const links = item.links ?? [];
  // 9 radar tiles form one seamless 3×3 map; anything else is a gallery.
  const seamless = images.length === 9;

  return (
    <div
      ref={panelRef}
      className="display-panel"
      style={{ left: pos.x, top: pos.y, width: size.w, height: size.h }}
      role="dialog"
      aria-label={item.title ?? "Result"}
    >
      <div className="display-head" onPointerDown={onHeaderPointerDown}>
        <span className="display-title">
          {item.title ?? "Result"}
          {item.agent && <span className="display-agent"> · {item.agent}</span>}
        </span>
        <button type="button" className="btn display-close" onClick={close}>
          ×
        </button>
      </div>

      <div className="display-body">
        {item.kind === "image" && images.length > 0 && (
          <div className={seamless ? "display-tiles" : "display-gallery"}>
            {images.map((src) => (
              <img key={src} src={src} alt={item.title ?? "result image"} />
            ))}
          </div>
        )}

        {item.body && (
          <div
            className="display-markdown"
            // Body is agent-generated markdown → sanitized HTML.
            dangerouslySetInnerHTML={{ __html: renderMarkdown(item.body) }}
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

      <div className="display-resize" onPointerDown={onResizePointerDown} />
    </div>
  );
}
