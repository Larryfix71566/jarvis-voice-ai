import { useEffect, useState } from "react";

const API = "http://localhost:7861";
const POLL_MS = 60_000;

/**
 * SystemVitals — bottom-right machine readout (Larry 2026-08-18: "would I
 * be better served to have a gauge cluster with those KPIs on screen?").
 *
 * The answer implemented here is deliberately NOT a live gauge cluster,
 * for three reasons, all of which are rules this codebase already holds:
 *
 * 1. **The wave keeps its motion monopoly** (engagement plan): animated
 *    gauges are continuous movement in the corner of a voice-first
 *    interface, competing with the one element allowed to move.
 * 2. **These numbers are boring 99% of the time.** CPU 12%, memory 61%,
 *    disk 44% — read twice on day one, never again. Persistent UI that
 *    carries no information does not stay neutral; it trains the eye to
 *    skip that corner, so it also fails on the day it matters.
 * 3. **The 85% threshold already exists** in mcp_system's FLAG_THRESHOLD,
 *    which the systems agent speaks aloud. The UI expression of a
 *    threshold is an exception indicator, not a dial.
 *
 * So: silent when healthy, amber when a metric crosses the SAME threshold
 * the agent warns at, and the full cluster on demand. Data rides the
 * existing 60s /api/ambient poll — no second poller, no fast timer.
 *
 * Battery is the exception to "silent when healthy": it is the one metric
 * a person acts on, and it changes predictably. NOTE it duplicates the
 * macOS menu bar when the menu bar is visible; if that redundancy annoys,
 * flip BATTERY_ALWAYS to false and it becomes exception-only like the
 * rest (shown under LOW_BATTERY).
 */

const BATTERY_ALWAYS = true;
const LOW_BATTERY = 20;

export interface SystemData {
  cpu: number | null;
  memory: number | null;
  disk: number | null;
  battery: number | null;
  uptime_hours: number | null;
  flags: string[];
  threshold: number;
}

const LABELS: Record<string, string> = {
  cpu: "CPU",
  memory: "MEM",
  disk: "DISK",
};

function pct(v: number | null): string {
  return v === null || v === undefined ? "—" : `${Math.round(v)}%`;
}

/** Uptime in the largest sensible unit — "3d" reads faster than "72h".
 *  Not exported: a second export beside the component trips the
 *  react-refresh lint rule, and nothing else needs it. */
function formatUptime(hours: number | null): string {
  if (hours === null || hours === undefined) return "—";
  if (hours < 1) return `${Math.round(hours * 60)}m`;
  if (hours < 48) return `${Math.round(hours)}h`;
  return `${Math.round(hours / 24)}d`;
}

export default function SystemVitals({ connected }: { connected: boolean }) {
  const [data, setData] = useState<SystemData | null>(null);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    if (!connected) return;
    let cancelled = false;

    async function load() {
      try {
        const res = await fetch(`${API}/api/ambient`);
        const body: unknown = await res.json();
        const system = (body as { system?: SystemData | null })?.system ?? null;
        if (!cancelled) setData(system);
      } catch {
        // The sidecar being down is not this component's story to tell —
        // the capability chip already covers that. Stay silent.
        if (!cancelled) setData(null);
      }
    }

    void load();
    const id = window.setInterval(() => void load(), POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [connected]);

  if (!connected || !data) return null;

  const flags = data.flags ?? [];
  const batteryLow = data.battery !== null && data.battery <= LOW_BATTERY;
  const showBattery =
    data.battery !== null && (BATTERY_ALWAYS || batteryLow);

  // Silent when there is nothing to say.
  if (!expanded && flags.length === 0 && !showBattery) return null;

  if (expanded) {
    return (
      <div className="vitals vitals-expanded" role="status">
        <button
          type="button"
          className="vitals-close"
          onClick={() => setExpanded(false)}
          aria-label="Collapse system vitals"
        >
          ×
        </button>
        {(["cpu", "memory", "disk"] as const).map((k) => (
          <div
            key={k}
            className={`vitals-row${flags.includes(k) ? " vitals-flagged" : ""}`}
          >
            <span className="vitals-label">{LABELS[k]}</span>
            <span className="vitals-bar">
              <i style={{ width: `${Math.min(100, data[k] ?? 0)}%` }} />
            </span>
            <span className="vitals-value">{pct(data[k])}</span>
          </div>
        ))}
        {data.battery !== null && (
          <div className={`vitals-row${batteryLow ? " vitals-flagged" : ""}`}>
            <span className="vitals-label">BATT</span>
            <span className="vitals-bar">
              <i style={{ width: `${Math.min(100, data.battery)}%` }} />
            </span>
            <span className="vitals-value">{pct(data.battery)}</span>
          </div>
        )}
        <div className="vitals-uptime">up {formatUptime(data.uptime_hours)}</div>
      </div>
    );
  }

  return (
    <button
      type="button"
      className="vitals vitals-collapsed"
      onClick={() => setExpanded(true)}
      title="System vitals"
    >
      {flags.map((k) => (
        <span key={k} className="vitals-chip vitals-flagged">
          {LABELS[k] ?? k} {pct(data[k as "cpu" | "memory" | "disk"])}
        </span>
      ))}
      {showBattery && (
        <span className={`vitals-chip${batteryLow ? " vitals-flagged" : ""}`}>
          {pct(data.battery)}
        </span>
      )}
    </button>
  );
}
