import { useState } from "react";
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
