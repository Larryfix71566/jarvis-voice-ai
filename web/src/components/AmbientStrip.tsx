import { useEffect, useState } from "react";
import { relTime, relTimeFromMs } from "../timeFormat";

const API = "http://localhost:7861";

/**
 * AmbientStrip — the idle screen's signs of life
 * (MORTIMER_ENGAGEMENT_DESIGN_PLAN.md E4).
 *
 * A vertical stack of small frosted chips anchored top-left of the
 * stage: clock (always, client-side), next reminder + last-session
 * summary + live weather (GET /api/ambient, polled every 60s — chips
 * hide when null or when the sidecar is down; being down must never add
 * an error surface). Renders nothing while disconnected: the dead screen
 * before Connect stays clean.
 *
 * Larry 2026-08-18, two changes:
 * 1. Weather is CURRENT, for the current location — fetched by the
 *    sidecar (jarvis/ambient_weather.py), never by this client, so the
 *    "the ambient layer never initiates its own API call" rule holds.
 *    The old localStorage ask-cache survives only as a fallback for an
 *    older sidecar that doesn't serve a `weather` field.
 * 2. The informational chips (not the clock) are dismissible via a
 *    hover ×. A dismissal hides that chip until its CONTENT changes,
 *    persisted in localStorage keyed by the dismissed content so a
 *    reload doesn't resurrect it. The reminder chip also self-expires:
 *    once due_at passes (60s grace) it hides on the next 30s clock
 *    tick, without waiting for the 60s sidecar poll.
 */

interface AmbientData {
  reminder: { text: string; due_at: string } | null;
  summary: string | null;
  weather?: {
    summary: string;
    temp_f: number;
    location: string;
    at: number;
  } | null;
}

interface WeatherCache {
  title: string;
  at: number;
}

type ChipType = "reminder" | "weather" | "summary";

const LS_DISMISSED = "mortimer.ambient.dismissed";
const REMINDER_EXPIRY_GRACE_MS = 60_000;

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

function readDismissed(): Partial<Record<ChipType, string>> {
  try {
    const raw = localStorage.getItem(LS_DISMISSED);
    if (!raw) return {};
    const parsed: unknown = JSON.parse(raw);
    if (parsed === null || typeof parsed !== "object") return {};
    const out: Partial<Record<ChipType, string>> = {};
    for (const t of ["reminder", "weather", "summary"] as const) {
      const v = (parsed as Record<string, unknown>)[t];
      if (typeof v === "string") out[t] = v;
    }
    return out;
  } catch {
    return {};
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
  const [dismissed, setDismissed] =
    useState<Partial<Record<ChipType, string>>>(readDismissed);

  // Clock + weather-cache refresh. This tick is also what re-evaluates
  // reminder expiry below (`now` is a render dependency).
  //
  // 10s, tightened from 30s (2026-08-18) for the minute hairline: at 30s
  // it only had two positions per minute and read as broken rather than
  // progressing. 10s gives six steps — enough to see movement between
  // glances — without a per-second re-render, which would cost a React
  // pass every second to move a bar by 1.6% of its width.
  useEffect(() => {
    if (!connected) return;
    const id = window.setInterval(() => {
      setNow(new Date());
      setWeather(readWeatherCache());
    }, 10_000);
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

  const dismiss = (type: ChipType, contentKey: string) => {
    setDismissed((prev) => {
      const next = { ...prev, [type]: contentKey };
      try {
        localStorage.setItem(LS_DISMISSED, JSON.stringify(next));
      } catch {
        /* storage unavailable — dismissal lasts this session only */
      }
      return next;
    });
  };

  if (!connected) return null;

  // Reminder expiry: hide once due_at + grace is behind `now`. A due_at
  // that fails to parse is never treated as expired (show it — the
  // wrong-but-visible outcome beats silently eating a reminder).
  const reminderDueMs = data?.reminder ? Date.parse(data.reminder.due_at) : NaN;
  const reminderExpired =
    Number.isFinite(reminderDueMs) &&
    now.getTime() > reminderDueMs + REMINDER_EXPIRY_GRACE_MS;

  const reminderKey = data?.reminder
    ? `${data.reminder.text}|${data.reminder.due_at}`
    : null;
  // Live sidecar weather wins; the legacy asked-about-weather cache is
  // only a fallback for an older sidecar that doesn't serve weather.
  const live = data?.weather ?? null;
  const weatherText = live
    ? `${live.summary} ${live.temp_f}°${live.location ? ` · ${live.location}` : ""}`
    : weather
      ? `${truncate(weather.title, 48)} · ${relTimeFromMs(weather.at)}`
      : null;
  const weatherKey = live
    ? `${live.summary}|${live.temp_f}|${live.location}`
    : weather
      ? `${weather.title}|${weather.at}`
      : null;
  const summaryKey = data?.summary ?? null;

  return (
    <div className="ambient-strip" aria-label="Ambient status">
      {/* Larry 2026-08-18: "the time display is boring and needs more
          work and the addition of the date."

          Three changes, all presentation — no new data source, no new
          failure mode:
          1. TYPOGRAPHY. A large thin time over a small dim date, so it
             reads as a display rather than a label. `font-variant-numeric:
             tabular-nums` in the CSS is load-bearing: without it the
             digits shift width as they change and the whole block twitches
             every minute.
          2. THE DATE, SPOKEN-STYLE. "Tuesday, 19 August" rather than
             8/19/2026 — the same choice VOICE_ADDENDUM already makes for
             dates aloud, so screen and speech agree.
          3. SECONDS AS A HAIRLINE. A one-pixel bar filling across each
             minute, not a ticking digit. It gives the sense of live time
             while keeping the wave's motion monopoly: one pixel of slow
             travel, updated on the existing 30s tick rather than a new
             per-second timer. */}
      <div className="ambient-clockblock" aria-label="Current time and date">
        <div className="ambient-time">
          {now.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}
        </div>
        <div className="ambient-date">
          {now.toLocaleDateString([], {
            weekday: "long",
            day: "numeric",
            month: "long",
          })}
        </div>
        <div className="ambient-minute" aria-hidden="true">
          <i style={{ width: `${(now.getSeconds() / 60) * 100}%` }} />
        </div>
      </div>
      {data?.reminder &&
        reminderKey !== null &&
        !reminderExpired &&
        dismissed.reminder !== reminderKey && (
          <div className="ambient-chip ambient-chip-dismissible">
            ⏰ {truncate(data.reminder.text, 60)} · {relTime(data.reminder.due_at)}
            <button
              type="button"
              className="ambient-dismiss"
              aria-label="Dismiss reminder"
              title="Dismiss"
              onClick={() => dismiss("reminder", reminderKey)}
            >
              ×
            </button>
          </div>
        )}
      {weatherText !== null &&
        weatherKey !== null &&
        dismissed.weather !== weatherKey && (
          <div className="ambient-chip ambient-chip-dismissible">
            {weatherText}
            <button
              type="button"
              className="ambient-dismiss"
              aria-label="Dismiss weather"
              title="Dismiss"
              onClick={() => dismiss("weather", weatherKey)}
            >
              ×
            </button>
          </div>
        )}
      {data?.summary &&
        summaryKey !== null &&
        dismissed.summary !== summaryKey && (
          <div className="ambient-chip ambient-summary ambient-chip-dismissible">
            {truncate(data.summary, 90)}
            <button
              type="button"
              className="ambient-dismiss"
              aria-label="Dismiss summary"
              title="Dismiss"
              onClick={() => dismiss("summary", summaryKey)}
            >
              ×
            </button>
          </div>
        )}
    </div>
  );
}
