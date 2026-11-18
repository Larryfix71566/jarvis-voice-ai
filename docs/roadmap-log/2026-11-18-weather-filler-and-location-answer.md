---
date: 2026-11-18
system: claude
rows: []
prs: []
---

# 2026-11-18: weather requests after "Okay" and bare-city answers

- **System:** Claude (Claude Code cloud session), at the coordinator's request.
- **Rows:** none; a defect fix found on the deployed `next` build (8d3be6d). Scope: `jarvis/bot/weather_intent.py`, one call site in `jarvis/bot/pipeline.py`, and a new unit test file.
- **Larry's words (UTC, Claude Duet channel):**
  - 03:40:37: "weather request failed so review the logs to see why"
  - 03:43:24: "Fix it"
  - 03:44:20: "if I ask for the weather it should default to the current location, which mortimer should already know because it is displayed in the interface"

## What failed

1. "Okay. Show me the weather." parsed as a named place, "okay. show me the". The intent guard then refused `local_weather`, whose refusal text tells the Supervisor to ask which place. That is why Mortimer asked for a location; the Supervisor prompt already routes a placeless weather request to `local_weather`.
2. "Alpharetta.", the answer to Mortimer's "Which location do you want?", parsed as not-weather, so every analyst `get_weather`/`get_weather_radar` call was refused as `weather_reuse_invalid_request` before reaching mcp-web.

## Change

- Leading acknowledgements and the assistant's name ("okay", "ok", "alright", "hey", "um", "yeah", "thanks", "Mortimer", ...) are stripped before parsing.
- Words from an earlier sentence never become the place: "I'm going to Denver. Show me the weather." is now `unclear`, not a named place containing a sentence break.
- "Weather please" no longer parses "please" as a place.
- A bare place ("Alpharetta.", "Alpharetta, Georgia", "In Spartanburg.") counts as a named weather target only when the previous accepted intent was a weather request and the assistant's last words before this turn asked which place. "Here." in that position means device weather. The place always comes from the user's accepted input; the assistant text only gates it.
- Unchanged: unclear named targets still refuse, the Portland, Maine qualifier rule, "and Portland" follow-ups.

## Not changed here: the weather chip says Mulberry

Read from the Mac's admin sidecar at 2026-11-18 ~03:55 UTC: `/api/status/location` returned `source: ip`, label Buford, so no device fix was on file; `/api/ambient` showed weather.gov station KGVL and location "Mulberry". The chip is labelled with weather.gov's nearest-place name for IP-geolocated coordinates. The Mac only posts a CoreLocation fix to `/api/location` when the bot asks for one (a `local_weather` call), and tonight that call was refused before it asked. Proposed follow-up: request one device fix when the shell connects (and refresh within the 1-hour max age) so the chip uses the device, and prefer the device's own label over weather.gov's nearest-place name, as `weather_tool.py` already does for the weather card.
