---
date: 2026-11-19
system: claude
rows: []
prs: []
---

# 2026-11-19: weather backup fetch, honest refusal codes, outcome logging

- **System:** Claude (Claude Code cloud session), at the coordinator's request.
- **Rows:** none; a defect fix found on the deployed build. Scope: `jarvis/bot/weather_reuse.py`, `jarvis/bot/weather_tool.py`, `jarvis/skills/registry.py`, one log line in `jarvis/bot/pipeline.py`, and weather unit tests.
- **Larry's words (UTC 2026-11-19 03:03:00, Claude Duet channel):** "we should add a backup service to avoid this issue in the future"

## What failed

Deployed incident 2026-11-18 21:51 ET. The turn's accepted `WeatherIntent` was not "local" (no device-location request, no console query and no weather HTTP happened during `local_weather`), so `local_weather` returned its "named or unclear weather target" refusal. The Supervisor then delegated to the analyst with a city from memory ("Alpharetta, Georgia"). Each analyst `get_weather` / `get_weather_radar` call was refused in 0 ms by `WeatherReuseBridge.lookup` because `intent.permits(...)` was False, reported as `weather_reuse_invalid_request`, which the Supervisor spoke as "the weather service returned an invalid request error".

## Change

1. `weather_reuse.py`: an intent mismatch now returns `not_requested` instead of `invalid_request` (argument-validation failures keep `invalid_request`). New `HARD_REFUSAL_CODES = {protected_turn, not_requested}`: these refuse the whole tool call. Every other refusal only means the retained card could not be reused.
2. `weather_tool.py` (`local_weather`): a soft reuse refusal falls through to the live fetch instead of returning. The intent refusal text is split: a named place says to delegate with exactly that place; an unclear request says to ask the user and not to delegate or recall a place. One INFO line per exit, `local_weather_result outcome=...` (never coordinates, place, weather body or error text).
3. `registry.py` (`get_weather` / `get_weather_radar` reuse block): soft refusals log `weather_reuse_fallback tool=... code=...` and fall through to the normal MCP fetch like a miss. `protected_turn`, `not_requested` and the replaced-session `stale_selection` check still refuse.
4. `pipeline.py`: `weather_intent kind=...` INFO log for any weather intent (never the place).
5. `weather_intent.py` (separate commit): plain phrasing now reads as local, so the 21:51 ET request is no longer refused as non-local. A leading decline ("no thanks", "not right now, but") is stripped like a filler; "like", "looking (like)", "going to be (like)", "outside", "doing" between the weather word and the place are not places; "me" / "us" count as local. Earlier-sentence places still give `unclear`.
6. Tests updated and added in `test_weather_reuse.py` and `test_acceptance_weather_routing.py`, including a reproduction of the incident.

## Not changed

- The intent parser's place extraction beyond item 5.
- WS-17's "refuse without silently fetching" rule is reversed for soft refusals, at Larry's request.

## Next actor

Larry: review and merge.
