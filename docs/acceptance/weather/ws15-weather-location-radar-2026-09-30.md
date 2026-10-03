# WS-15 acceptance receipt — weather: fresh location and current radar

**Result:** ACCEPTED by Larry on the Mac, 2026-09-30, with the follow-ups
listed below recorded as backlog (none blocks acceptance).
**Production revision at acceptance:** `03b9e60` (PR #136), deployed with
DEPLOY-MAIN (all JarvisKit, MortimerHost and Python suites green in phase A).
**Plan:** `docs/plans/MORTIMER_WEATHER_LOCATION_AND_RADAR_PLAN.md` §6.
**Evidence sources:** `logs/bot.launchd.log`, `logs/agents/2026-09-29/`,
`logs/agents/2026-09-30/`, and the app's `com.mortimer.host:radar` os_log
category (read by Larry with `log show`). Claude read logs only; no code or
data was changed to produce this receipt.

## Checks

| # | Check | Result | Evidence |
|---|---|---|---|
| A1 | "What's the weather?" names the current place | PASS | 09-30 10:32, 11:54, 12:45: `local_weather` called with `{}` (no place argument); summary "Weather for Folly Beach, SC (this device's location)"; card shown (`display_payload tool=local_weather kind=weather`). |
| A2 | Card: header, today, 12 hours, 7 days, humidity, wind | PASS | Larry confirmed the card; spoken summaries carry humidity and wind ("humidity 72%, northeast wind 12 mph"). |
| A3 | Apple map, pin, current radar, street-level zoom, loop | PASS | Larry: "radar looks smooth now". Radar log 09-30 10:32: first frame 1.2 s, per-frame waits ≈0.6 s on the first lap, 10–26 fetches/10 s once loaded (was 10.8 s and ~3,000 fetches/10 s before PRs #126–#128). |
| A4 | Card with the display window closed and open | PASS | Card stays in the main window by Larry's one-window decision; display window opens without crashing after PR #131 (Larry, 09-30). |
| A5 | "What's the weather in Alpharetta?" | PASS | 09-30 11:04 and 12:46: analyst `get_weather` source `weather.gov`, radar, card `kind=weather`. |
| A6 | Location permission off | PASS (wording follow-up) | 12:52:30 `device_location_hello authorization=denied`; 12:52:39 and 12:53:16 `location_resolved source=ip device=denied`. Spoken: "You're approximately in Charleston right now, based on your internet connection." Weather: `local_weather` `{}`, card labelled from the internet connection. No remembered place anywhere in the session ("Spartanburg" absent). The spoken weather line said "You're in Charleston" without "approximately" (follow-up F3). Permission restored: 12:54:15 `authorized`; "Folly Beach, SC … accurate to about 40 meters". |
| A7 | "Weather in London" | PASS | 09-30 11:03 after PR #132: `get_weather` source `open-meteo`, RainViewer radar, card. (Before #132 Open-Meteo rejected `current=time`; Larry's curl proved it.) |
| A8 | No remembered place in task text or tool calls for A1/A6 | PASS | `local_weather` takes no place and was called with `{}` in every A1/A6 run; no delegation carried a place for "current" weather. |

## Added during acceptance (Larry's requests, all verified)

- Voice map control: `map_zoom_in/out`, `map_reset`, `radar_pause/play`,
  `map_satellite/standard` (09-29/30 logs); `map_zoom_to` (`miles: 10`,
  `miles: 50`) and `map_center` ("Truist Park, Atlanta" → Apple Maps
  33.890770, −84.467574, radar log 12:47:39).
- Stable app signing (PRs #133, #134): after the deploy of `03b9e60` Larry
  was not asked for microphone or location again; the first session reported
  `authorization=authorized`.
- Crash fix (PR #131): every content window receives the console's stores.

## PRs

#110, #114, #118, #120, #123, #126, #127, #128, #131, #132, #133, #134, #136.

## Follow-ups (backlog, not blocking)

- **F1 Retry guard and place names:** `jarvis/agents/delegate.py` refused
  "Alpharetta, Georgia" after a failed "London, England" (overlap 0.80; the
  substitution exemption allows only one changed word). Proposed: exempt when
  Larry's own words bring a token the failed task lacked.
- **F2 "London, UK" not geocoded:** the analyst's first `get_weather`
  returned "I couldn't find a place called 'London, UK'"; its retry worked.
- **F3 Spoken "approximate" dropped:** with location off, the weather line
  omitted "approximately" although the tool summary asks for it.
- **F4 Mortimer does not know which place the card shows:** it said "reset
  to your location" while the Atlanta card was open.
- **F5 Speech-to-text mishearings:** "zoom to 10 miles" → "It has been ten
  miles"; "show me the weather" → "Just show me the water".
