import { useEffect, useState } from "react";
import { relTime, relTimeFromMs } from "../timeFormat";

const API = "http://localhost:7861";

/**
 * AmbientStrip — the idle screen's signs of life
 * (MORTIMER_ENGAGEMENT_DESIGN_PLAN.md E4).
 *
 * A vertical stack of small frosted chips anchored top-left of the
 * stage: clock (always, client-side), next reminder + last-session
 * summary (GET /api/ambient, polled every 60s — chips hide when null or
 * when the sidecar is down; being down must never add an error
 * surface), and last-known weather (localStorage cache written by
 * displayWindow.publish as a side effect of the user ASKING — this
 * component never fetches weather). Renders nothing while disconnected:
 * the dead screen before Connect stays clean.
 */

interface AmbientData {
  reminder: { text: string; due_at: string } | null;
  summary: string | null;
}

interface WeatherCache {
  title: string;
  at: number;
}

function readWeatherCache(): WeatherCache | null {
  try {
    const raw = localStorage.getItem("mortimer.ambient.weather");
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    const w = parsed as WeatherCache;
    if (typeof w?.title !== "string" || typeof w?.at !== "number") return null;
    return w;
  } catch {
    return null;
  }
}

function truncate(s: string, max: number): string {
  const t = s.trim();
  return t.length > max ? t.slice(0, max - 1) + "…" : t;
}

export default function AmbientStrip({ connected }: { connected: boolean }) {
  const [now, setNow] = useState(() => new Date());
  const [data, setData] = useState<AmbientData | null>(null);
  const [weather, setWeather] = useState<WeatherCache | null>(readWeatherCache);

  // Clock + weather-cache refresh, every 30s.
  useEffect(() => {
    if (!connected) return;
    const id = window.setInterval(() => {
      setNow(new Date());
      setWeather(readWeatherCache());
    }, 30_000);
    return () => window.clearInterval(id);
  }, [connected]);

  // Sidecar poll, every 60s; failure hides the sidecar-backed chips.
  useEffect(() => {
    if (!connected) return;
    let cancelled = false;
    const poll = async () => {
      try {
        const r = await fetch(`${API}/api/ambient`);
        const j = (await r.json()) as { ok?: boolean } & AmbientData;
        if (!cancelled) setData(j.ok ? j : null);
      } catch {
        if (!cancelled) setData(null);
      }
    };
    void poll();
    const id = window.setInterval(() => void poll(), 60_000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [connected]);

  if (!connected) return null;

  return (
    <div className="ambient-strip" aria-label="Ambient status">
      <div className="ambient-chip ambient-clock">
        {now.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}
      </div>
      {data?.reminder && (
        <div className="ambient-chip">
          ⏰ {truncate(data.reminder.text, 60)} · {relTime(data.reminder.due_at)}
        </div>
      )}
      {weather && (
        <div className="ambient-chip">
          {truncate(weather.title, 48)} · {relTimeFromMs(weather.at)}
        </div>
      )}
      {data?.summary && (
        <div className="ambient-chip ambient-summary">
          {truncate(data.summary, 90)}
        </div>
      )}
    </div>
  );
}
