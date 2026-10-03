# Mortimer: local weather with today, the week, and a live radar map (WS-15, Option A)

**Author:** Claude (Cowork), 2026-09-29
**Status:** ACCEPTED 2026-09-30 (Larry, on the Mac; production `03b9e60`). Receipt: `docs/acceptance/weather/ws15-weather-location-radar-2026-09-30.md`. Follow-ups F1–F5 are in the roadmap backlog.
**Workstream:** WS-15 in `ROADMAP.md`
**Supersedes:** W5/W6 of `MORTIMER_WEATHER_FAHRENHEIT_AND_RADAR_PLAN.md` (the one-card merge and the stacked RainViewer/CARTO radar). W1–W4, W7 and W8 stand: Weather.gov primary, both unit sets, `JARVIS_UNITS`, no new kill switches.
**Research:** `Claude outputs/ws15/ws15_weather_research.html` (09-29), sources listed there.

**Origin, Larry 09-29:**
- *"it defaults to memory for weather instead of checking current location"*
- *"no radar showed up, also radar is not providing the correct underlying map for the area"*
- *"local weather based on our current location … a summary of today's weather, a weekly weather summary and current radar data with mapping of not only the weather but the location like you would have with google maps or the weather channel app"*

---

## 1. Findings this plan fixes (read-only evidence, 09-29)

| # | Finding | Evidence |
|---|---|---|
| E1 | The place comes from memory. | Run `74b907c1` (10:08 EDT): the task said *"typically in Spartanburg, SC"*; the analyst fetched Spartanburg. Larry was at Folly Beach. |
| E2 | No location reaches weather. | `resolve_location` (device, then IP, then unavailable; never memory) is wired only into `system_status`. `get_weather(city)` and `get_weather_radar(city)` take only a city name. |
| E3 | Device location works. | 11:39 EDT: `authorization=authorized`; the fix was accurate to 35 m, 0.4 s old, labelled `Folly Beach, SC`. |
| E4 | No weekly forecast. | `get_weather` caps the forecast at 3 days (`min(int(days), 3)`). The 10:08 reply said "humidity/wind data unavailable". Weather.gov's `/points`, then `forecast` (7 days), then `forecastHourly` is not fully used, and alerts are not fetched. |
| E5 | The radar map is unusable. | `imagesStack` (`DisplayContentView.swift`) stacks the 3×3 tiles vertically on an unlabelled dark basemap at zoom 6, with no pin. |
| E6 | The radar source is now limited. | Since 2026-01-01, RainViewer's free API stops at zoom 7 with one colour scheme and 2 h of 10-minute frames, and is for personal/educational use only. |
| E7 | No radar appeared at all. | **Cause found (G-2, 09-29 17:27).** The app received the card (`kind=image`, 9 radar + 9 basemap tiles, `displayOpen=false`) and routed it to the workspace. `WorkspaceStore.receive` only makes the **first** result of a session active; later results are only marked unread. The spoken reply's text result had arrived 16 s earlier, so the radar card sat unread and was never rendered (no image-stack log line). |
| E8 | Mortimer said "I don't have a weather radar tool yet". | 09-29 17:28 test session: the analyst had called `get_weather_radar` and the card had been sent. The voice model can't see the analyst's tools, so it answered from assumption and offered to build radar through self-development (`HANDOFF_ADDENDUM`'s "isn't something I have a tool for" line). |

## 2. What Option A delivers

- **Location:** "What's the weather?" uses a device fix, or the internet location said as approximate, never memory. A named place ("in Alpharetta") still works.
- **Spoken answer** (built in code, 40 words or fewer): now, today, and the week's headline. For example: *"At Folly Beach it's 75 and clear, high 82. Storms possible Thursday and Friday; otherwise sunny, highs near 80."* Any active alert comes first.
- **Card:**
  - Header: place, source ("this Mac's location" or "approximate"), current temperature, condition, feels-like, humidity, wind.
  - Today: high/low, chance of rain, the NWS short forecast.
  - The next 12 hours as a strip.
  - 7 days: one row per day with icon, high/low bar and chance of rain.
  - Active NWS alerts as a banner.
- **Map:** native Apple Maps (MapKit) with streets, labels, and standard or hybrid satellite. You can pan and zoom, and there's a pin at the fix.
- **Radar on the map:** the NOAA NEXRAD composite via Iowa Environmental Mesonet (IEM), updated every 5 minutes with real detail to zoom 8, and a 50-minute loop (play/pause, time stamp). Outside the lower 48 states it falls back to RainViewer (zoom 7).
- **Cost:** $0. No keys, no accounts.

## 3. Architecture

```
voice: "what's the weather?"
  └─ local_weather (new direct tool, bot process)
       ├─ resolve_location(device → IP → unavailable)         [existing, reused]
       ├─ weather_report(lat, lon, label)  ── thread ──►  jarvis/weather/report.py (new)
       │     ├─ Weather.gov: /points (cached) → forecast (7 d) + forecastHourly + /alerts/active?point=
       │     ├─ fallback: Open-Meteo daily 7 d + hourly (outside the US, or on NWS failure)
       │     └─ radar_layers(lat, lon): IEM templates (current + m05m…m50m) or RainViewer frames
       ├─ push display payload  kind="weather"  weather={…schema v1…}  surface=window
       └─ return spoken summary (code-built)
voice: "weather in Alpharetta"
  └─ delegate → analyst → mcp_web.get_weather_report(city="Alpharetta") → same report + same card
app: DisplayPayload.weather → WeatherCardView (header, today, hourly, 7-day, alerts)
                              └─ RadarMapView (MKMapView + MKTileOverlay per frame + pin + loop)
```

**Report schema v1**, the one object both paths produce:

```json
{"schema": 1, "place": {"label": "Folly Beach, SC", "lat": 32.661, "lon": -79.928,
  "source": "device|ip|named", "approximate": false},
 "units": "imperial",
 "now": {"temp_f": 75, "temp_c": 24, "feels_f": 77, "condition": "Clear", "humidity": 68,
         "wind": "SE 8 mph", "observed_at": "…", "source": "weather.gov"},
 "today": {"high_f": 82, "low_f": 72, "pop": 10, "short": "Sunny", "detail": "…"},
 "hourly": [{"t": "…", "temp_f": 76, "pop": 5, "icon": "clear-day"}],
 "days": [{"date": "2026-09-30", "name": "Wed", "high_f": 82, "low_f": 73, "pop": 20,
           "short": "Mostly Sunny", "icon": "partly-cloudy-day"}],
 "alerts": [{"event": "Rip Current Statement", "severity": "Moderate", "ends": "…",
             "headline": "…"}],
 "radar": {"provider": "iem|rainviewer", "max_native_zoom": 8,
           "frames": [{"t": "…", "template": "https://…/{z}/{x}/{y}.png"}],
           "attribution": "Radar: NOAA NEXRAD via Iowa Environmental Mesonet"},
 "sources": ["weather.gov", "iem"], "fetched_at": "…"}
```

- Every temperature is sent in both °F and °C (W2); only the imperial names are shown above.
- The map itself (Apple Maps) needs no URL: MapKit supplies it.
- `images`/`basemap_images` are also filled with the old 3×3 RainViewer set, so an app build without the new view still shows something.

## 4. Gates before the build (each is small; the result is recorded in this plan)

- **G-1 Probe (Larry, 2 minutes, command supplied by Claude).** From the Mac, fetch IEM tiles for Folly Beach at z6–9 using both reported paths (`/cache/tile.py/1.0.0/nexrad-n0q-900913/…` and `/c/tile.py/1.0.0/nexrad-n0q-m05m-900913/…`), plus `api.weather.gov/points/32.661,-79.928` and `alerts/active?point=…`. Record HTTP status and size. This fixes the tile templates and confirms z8 is the last zoom with real data. The Cowork VM and cloud session can't reach these hosts, so it has to run in the Mac's own terminal.
- **G-2 Why radar didn't show (E7).** Add two app log lines to `mortimerhost-window.log`:
  1. When a display payload arrives: renderer (workspace or display window), panel id, image count.
  2. When an `AsyncImage` fails: host and error only.

  Reproduce on the current build. If the cause is outside the weather view (e.g. window payloads dropped in general), stop and file it separately, because that code borders WS-09.
- **G-3 MapKit spike (Claude, throwaway branch, about 1 hour).** An `MKMapView` inside MortimerHost (ad-hoc signed, macOS 26 target, not sandboxed) with one IEM `MKTileOverlay`, built with `bundle.sh` and run on the Mac. **Pass:** Apple's map renders with the radar overlay and the pin. **Fail:** fall back to Option C's MapLibre web view for the map only; the rest of this plan is unchanged. MapKit working in an ad-hoc-signed app is likely but untested.

## 4a. Gate results (09-29)

- **G-1 (probe from the Mac, 17:17 UTC).**
  - IEM `/cache/tile.py/1.0.0/nexrad-n0q-900913/{z}/{x}/{y}.png` and `…nexrad-n0q-m05m-900913/…` return 200 at z6–z9. The `/c/…` form returns 404, so use `/cache/`.
  - Weather.gov answered all three calls: `/points` (200), `alerts/active?point=` (200), `forecast` (14 periods) and `forecastHourly` (156 periods, with `relativeHumidity`, `windSpeed`, `windDirection` and `probabilityOfPrecipitation`).
- **G-2 (diagnostic build, 17:27).** Found the cause of E7 (§1). PR 2 makes a weather card come to the front instead of sitting unread.
- **G-3 (MapKit spike, 17:24).**
  - Apple's map rendered fully in an ad-hoc-signed, unsandboxed app (7 `fullyRendered=true` renders, no failures).
  - IEM tiles loaded for the current frame and the 5- and 10-minute frames (36 each, 400–1,955 bytes, i.e. real data), with no failures.
  - **Constraint found:** with `maximumZ=8`, MapKit requests no radar tiles at all when zoomed closer than z8, so the radar disappears at the opening ~60 km view. S6 must serve z>8 by cropping and enlarging the parent z8 tile (a custom `MKTileOverlay.loadTile`).
- **Correction:** there is no `JARVIS_WEATHER_ENABLED` switch; the existing one is `JARVIS_AMBIENT_WEATHER_ENABLED`, and it gates only the ambient chip. Following W8 (no new kill switches), `local_weather` is registered unconditionally. Rollback is a revert.

## 5. Build steps (branch `ws15/weather-location-radar`, after G-1 to G-3)

**S1. Data layer: `jarvis/weather/report.py` (new; pure functions, injected fetchers)**
- `weather_report(lat, lon, label, source, *, days=7, hours=12, fetch=…)` returns schema v1.
- Weather.gov:
  - Cache `/points` in-process for 24 h, keyed on lat/lon rounded to 0.01°; NWS says the mappings rarely change.
  - Pair day and night periods into 7 days.
  - Take hourly temperature, humidity, wind and chance of rain.
  - Take alerts from `/alerts/active?point=lat,lon`.
  - Current conditions keep the existing observation-first logic (`weathergov_current`, W4 labels).
  - Keep the existing User-Agent.
- Fallback to Open-Meteo, daily 7 days plus hourly, when outside the US or on any NWS failure. `sources` says which answered.
- `radar_layers(lat, lon)`:
  - Inside the CONUS bounding box: IEM templates for now and for m05m…m50m, `max_native_zoom=8`.
  - Otherwise: RainViewer frames, `max_native_zoom=7`, colour scheme 2.
  - No network call for IEM (the URLs are fixed templates); one call for RainViewer.
- `mcp_web`'s existing `get_weather` keeps its return shape (the analyst and older paths use it). Its `days` cap moves from 3 to 7.

**S2. `mcp_servers/mcp_web`: `get_weather_report(city="", lat=None, lon=None)` (new tool)**
- Geocodes a city with the existing Open-Meteo geocoder, or takes lat/lon, then calls `weather_report`.
- `get_weather_radar` stays for compatibility.
- The analyst prompt (line 470) changes to: "Weather for a named place: call `get_weather_report`."

**S3. `local_weather` direct tool: new `jarvis/bot/weather_tool.py`, registered in `pipeline.py` beside `system_status`**
- `resolve_location(runtime.device_location, protected=…, ip_lookup=…)`.
- On success: run `weather_report` in a thread, push the `kind="weather"` payload through the existing display sender, and return the code-built spoken summary.
- **Protected turn:** weather is an external lookup, so it follows `system_status`'s `EXTERNAL_TOPICS` rule. Say it's unavailable on a private turn; call nothing.
- **Unavailable:** "Location isn't available (reason). Ask the user which place. Do not guess a place."
- Registered only when `JARVIS_WEATHER_ENABLED` is on (W8: no new switch).

**S3a. E8 fix.** `local_weather`'s code-built answer states whether a card with radar was sent. `WEATHER_ADDENDUM` tells the voice model the radar is on that card and never to say it has no radar.

**S4. `jarvis/bot/display.py`**
- A `weather` pseudo-tool (like `weather_report`) builds `kind="weather"` with the `weather` object, plus the legacy `images`/`basemap_images`, `surface="window"`.
- `WeatherReportMerger` stays for any analyst run that still calls the two old tools.

**S5. Prompts and evals (`jarvis/prompts.py`, `tests/evals/`)**
- Voice model: "Current, local or 'here' weather, including rain/umbrella questions with no place named: call `local_weather` yourself. Never delegate it, never name a place. A named place: delegate to the analyst." Rule 3 gains "or `local_weather`".
- Evals:
  - "What's the weather?", "Do I need an umbrella today?" and "What's the week look like?" call `local_weather`.
  - "Weather in Alpharetta" goes to the analyst (the existing control case).
  - A negative case: no `delegate_task` text for local weather may contain a remembered place.

**S6. App**
- **JarvisKit `AppMessage.swift`:** optional `weather: WeatherReport?` on `DisplayPayload`, a `Decodable` struct for schema v1. Unknown schema versions decode to nil and the legacy images show instead.
- **`Display/WeatherCardView.swift` (new):**
  - Header (now), alert banner, today, a 12-hour strip, and 7 rows for the week.
  - Plain SwiftUI using the app's `AppTheme` and glass styles.
  - Attribution line, e.g. "Forecast: NWS · Radar: NOAA via IEM".
- **`Display/RadarMapView.swift` (new):**
  - `NSViewRepresentable` wrapping `MKMapView`.
  - One `MKTileOverlay` per frame from `radar.frames[].template`, with `canReplaceMapContent=false` and a max native zoom so tiles upscale past z8 instead of disappearing.
  - The current frame is shown; the others are preloaded, hidden.
  - A pin at `place`. The initial span is about 60 km around the pin, with zoom out to about 600 km.
  - A standard/hybrid toggle, play/pause for the loop (0.5 s per frame), and "Radar HH:MM · N min ago".
  - Reduce Motion: no autoplay.
- **`DisplayContentView.swift`:** `kind == "weather"` with a decoded report routes to `WeatherCardView`; otherwise today's path is unchanged. Both the workspace and the display window use `DisplayContentView`, so both get it (A4).
- The two G-2 log lines stay: they're cheap and useful.

**S7. Tests**
- **Python:**
  - `test_weather_report.py` (new): pairing 14 periods into 7 days; hourly mapping; alerts; points cache; fallback to Open-Meteo; units under both `JARVIS_UNITS` values; the CONUS switch between IEM and RainViewer; the schema v1 shape.
  - `test_local_weather.py` (new): device, then IP, then unavailable; the protected turn calls nothing; the summary is code-built and 40 words or fewer; the tool has no place argument.
  - `test_mcp_web_logic.py`: `get_weather_report` for both city and lat/lon; `get_weather` with `days=7`.
  - `test_display.py`: the `kind="weather"` payload, including the legacy images.
- **Swift:**
  - Decoding, including unknown-schema fallback.
  - Tile-template substitution.
  - Frame stepping and Reduce Motion.
  - Routing to `WeatherCardView` versus the legacy stack.
- DEPLOY-MAIN's verify phase runs the full suites.

**S8. Land, deploy, accept**
1. PR with WS-15 set to `review`.
2. Larry merges and runs DEPLOY-MAIN.
3. Larry runs the acceptance checks (§6).
4. Receipt at `docs/acceptance/weather/ws15-weather-location-radar-<date>.md`; WS-15 moves to `accepted`.

## 5a. PR 1 as built (09-29)

PR 1 is smaller than S1/S2 as written: it reuses the existing, tested Weather.gov/Open-Meteo path instead of adding `jarvis/weather/report.py` first. The schema-v1 report and `get_weather_report` move to PR 2, where the native card needs them.

- **`jarvis/weathergov.py`:** new `period_pop`, `hourly_forecast` and `active_alerts`. `daily_forecast` gains additive `pop`/`detail` keys.
- **`mcp_servers/mcp_web/logic.py`:**
  - `get_weather` = geocode, then the new `weather_at(lat, lon, label, days)`; `get_weather_radar` = geocode, then the new `radar_at(lat, lon, label)`.
  - The forecast cap goes from 3 to 7 days.
  - Humidity and wind come from the current hourly period (`wind` is NWS text such as "SE 8 mph"), and chance of rain from each period.
  - New additive keys: `hourly`, `alerts` (None = lookup failed, [] = none active), `lat`, `lon`.
  - The Open-Meteo path returns the same shape.
- **`jarvis/bot/weather_tool.py` (new):** `local_weather`.
  - Takes no arguments. Place order: device fix, then IP (said as approximate), then "ask which place".
  - Refused on a protected turn.
  - Pushes one `weather_report` card; returns a code-built summary covering the alert, now, today, the rest of the week, and whether a card with radar was sent.
- **`jarvis/bot/tool_schemas.py`, `jarvis/prompts.py` (`WEATHER_ADDENDUM`), `jarvis/agents/supervisor.py`:** a `weather` flag, appended last so every earlier menu and prompt stays byte-identical.
- **`jarvis/bot/pipeline.py`:** registers `local_weather` with the session's `resolve_location` and the app-message sender.
- **`jarvis/bot/display.py`:** alerts lead the weather card.
- **Evals:** three `require_tool: local_weather` cases in `tests/evals/voice_workflow_cases.yaml`; the eval passes `weather=True`.
- **Known limit until PR 2:** the card is still the legacy RainViewer tile stack, and it can still sit unread in the workspace (E7). The spoken answer now says a card with radar was sent, so Mortimer no longer denies having radar.

## 5b. PR 2 as built (09-29)

- **Larry's decision (09-29):** *"it still shows the text on one window and the radar on another, they should be on one window."* He chose the **main window**: the weather card lives only in Mortimer's main window and is selected when it arrives. It never goes to the supporting display, and it never waits unread (fixes E7).
- **Server:**
  - `jarvis/bot/weather_card.py` (new) builds the schema-1 view (`weather_view`), which is display-ready in the user's units, with SF Symbol names.
  - Radar is IEM inside the lower 48 (current plus 5–50 minute frames, native zoom 8) and RainViewer elsewhere (native zoom 7).
  - `build_display_payload` gives a `weather_report` card `kind: "weather"` plus the `weather` view, keeping the markdown body and legacy images as the fallback.
  - `local_weather` passes the place (label, source, approximate). Its "card with radar" wording follows the view: inside the US it uses NOAA radar even if RainViewer fails.
- **App:**
  - JarvisKit `WeatherCard` is decoded leniently on `DisplayPayload.weather`; an unknown schema gives nil and falls back to the body.
  - `WeatherCardView`: header with the place and its source, now, humidity and wind, alerts, a 12-hour strip, the week, the map, and attribution.
  - `RadarMapView`: `MKMapView` with a pin, a map/satellite toggle, and play/pause through the frames every 0.6 s. There is no autoplay under Reduce Motion.
  - `RadarTileOverlay` serves zooms past the native level by enlarging the parent tile (`RadarTileMath`), so radar stays visible at street level (the G-3 constraint).
  - `DisplayContentView` routes `kind == "weather"` to the card.
  - `AppMessageRouter.showsInMainWindowOnly` keeps it in the main window and selects it.
- **Known remaining:** the spoken reply's text still arrives as its own result, and it's also mirrored to the supporting display when that window is open (existing behaviour of `ResponseResultRouter`). The weather card, which carries the same summary, stays in front in the main window.

## 6. Acceptance (Larry on the Mac; Claude checks the logs)

| # | Do | Pass |
|---|---|---|
| A1 | "What's the weather?" | Names your current place (device). The spoken answer covers now, today and the week in 40 words or fewer. |
| A2 | Look at the card | Header, today, 12 hours and 7 days all present, with humidity and wind filled in. |
| A3 | Look at the map | Apple map with streets and labels, a pin at your spot, and radar updated within 10 minutes. Zooming in shows street level; play loops about 50 minutes. |
| A4 | Repeat with the display window closed, then open | The card and map appear both times. |
| A5 | "What's the weather in Alpharetta?" | Same card for Alpharetta. |
| A6 | Location permission off, then "What's the weather?" | Says approximate (internet location) or asks which place. Never Spartanburg or another remembered place. Turn the permission back on afterwards. |
| A7 | "Weather in London" | A card with RainViewer radar (zoom 7) and an Open-Meteo forecast; no errors. |
| A8 | Claude reads the run log for A1 and A6 | No task text or tool call carries a remembered place. |

## 7. Scope, ownership, risk, rollback

- **Files:**
  - Python: `jarvis/weather/__init__.py` and `jarvis/weather/report.py` (new); `jarvis/weathergov.py` (the hourly/alerts/points helpers, if they belong there); `mcp_servers/mcp_web/logic.py`, `mcp_servers/mcp_web/server.py`; `jarvis/bot/weather_tool.py` (new); tool registration in `jarvis/bot/pipeline.py`; `jarvis/bot/display.py`; weather lines in `jarvis/prompts.py`.
  - Swift: `macos/JarvisKit/Sources/JarvisKit/AppMessage.swift`; `Display/DisplayContentView.swift`; `Display/WeatherCardView.swift` and `Display/RadarMapView.swift` (new).
  - The tests and evals above.
- **Ownership:** re-checked 09-29, none of these is inside another block's scope. WS-09's scope is `OrbFieldView.swift` and its tests; WS-03's shared files are the console view-mode files, not `Display/`. If G-2 points into WS-09's display-window code, stop and add a §4 conflict entry.
- **Third-party use:** NWS and IEM data are US-government/public. IEM asks not to be used by apps with thousands of simultaneous users; Mortimer has one user. RainViewer's free tier is personal-use, which Mortimer is. Attribution is shown on the card.
- **Privacy:** coordinates go to `api.weather.gov` (rounded to 0.01°, about 1 km) and, outside the US, to Open-Meteo. Map tiles reveal only the area being viewed. Protected turns make no external calls (S3).
- **Rollback:** revert the PR; DEPLOY-MAIN's `ROLLBACK.sh` restores the previous release. `JARVIS_WEATHER_ENABLED=false` still turns weather off entirely. Older app builds keep working via the legacy images.
- **Not in scope:** push notifications for severe weather, forecast radar (RainViewer dropped nowcast), and moving ambient weather (`ambient_weather.py`) onto this path. That last one is a good follow-up.

## 8. Order and size

| Step | Who | Size |
|---|---|---|
| G-1 probe | Larry (command from Claude) | 2 min |
| G-2 radar-missing logging + reproduce | Claude, then Larry reproduces | S |
| G-3 MapKit spike | Claude, then Larry runs the build | S |
| S1–S2 data layer + tool | Claude | M |
| S3–S5 local_weather, display, prompts, evals | Claude | M |
| S6 app views | Claude | M–L |
| S7 tests | Claude (with each step) | M |
| S8 deploy + acceptance | Larry, Claude checks logs | 20 min |

S1–S5 can land as one PR before S6. The voice answer and the location fix work immediately, with the legacy radar images, while the map is built. The native map lands as a second PR.
