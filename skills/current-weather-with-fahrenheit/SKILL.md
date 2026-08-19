---
name: current-weather-with-fahrenheit
description: Retrieve and report current weather for a location — temperature, conditions, wind, humidity and any active alerts — with every temperature in Fahrenheit and the unit stated explicitly. Use for any current-conditions or short-term forecast question.
metadata:
  source: procedure:16
  agent: analyst
  promoted_successes: 5
  promoted_failures: 0
---

# Current weather, reported in Fahrenheit

## When this does not apply

Ignore this skill for historical climate data or long-range outlooks — it
covers live conditions and the next day or two. Merely naming a city or a
season is not a weather request.

## When to use this

Any current-conditions or near-term forecast question. Five successes,
zero failures in the run log — the shape is settled; what follows is the
part that is easy to get wrong.

## Location comes from the device, never from a default

Larry's standing rule: use the CURRENT location. Do not fall back to a
home or work city because it is the one you have seen before. The
resolution order implemented in `jarvis/ambient_weather.py` is:

1. `JARVIS_WEATHER_LAT` / `JARVIS_WEATHER_LON` if explicitly configured
2. device location reported by the Mac shell
3. IP geolocation — a last resort, accurate to tens of miles

If the location is a guess, say which of these produced it. "Around
Spartanburg, from your network address" is honest; naming the city flat
is not, when hop 3 is what answered.

## Units are not optional

Every temperature carries `°F`. Not "72", not "72 degrees" — `72°F`.
This is a stated preference that has been violated enough times to
become a logged bug, so treat a bare number as a defect.

Wind in mph, humidity as a percentage, precipitation in inches.

## What a complete answer contains

- Temperature, and "feels like" when it differs meaningfully
- Conditions in words, not a numeric code
- Wind speed and direction
- Humidity
- **Any active alerts, first** — a tornado warning outranks the
  temperature that was asked for

## Source

Weather.gov (`api.weather.gov`) is primary in the US: it reports
Fahrenheit natively, gives a human forecast phrase rather than a WMO
code, and returns the nearest city name for free. It is a two-hop API —
`/points/{lat},{lon}` resolves a gridpoint and yields the forecast URL —
and it requires a `User-Agent` header identifying the client.
Open-Meteo is the fallback outside the US or on any failure; it returns
Celsius and numeric weather codes, so both need converting.

If neither source answers, say the lookup failed. Do not report the last
value you saw as if it were current.

## If a tool is unavailable

No weather tool: say you could not look it up. No location: say you do not
know where to look and ask. A remembered temperature is not a current one,
and a remembered city is not a current location — reporting either as
though it were live is the specific failure this skill exists to prevent.
