import { marked } from "marked";
import DOMPurify from "dompurify";
import type { DisplayPayload } from "../displayResults";

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

export default function DisplayContent({ payload }: { payload: DisplayPayload }) {
  const images = payload.images ?? [];
  const links = payload.links ?? [];
  // 9 radar tiles form one seamless 3×3 map; anything else is a gallery.
  const seamless = images.length === 9;

  return (
    <div className="display-body">
      {payload.kind === "image" && images.length > 0 && (
        <div className={seamless ? "display-tiles" : "display-gallery"}>
          {images.map((src) => (
            <img key={src} src={src} alt={payload.title ?? "result image"} />
          ))}
        </div>
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
