---
name: layered-geolocation
description: Design or debug location resolution in an application — a layered chain of stored preference, device/browser API, and IP fallback, with consent, explicit staleness, and honest reporting of which layer answered. Use when implementing, reviewing or fixing any feature that needs to know where the user is.
metadata:
  source: procedure:17
  agent: developer
  promoted_successes: 9
  promoted_failures: 4
---

# Layered geolocation

## When to use this

Implementing or reviewing any feature that depends on the user's
location. Nine successes and four failures in the run log — the failures
came from treating one layer as the whole answer, which is what the
layering below exists to prevent.

## The chain, most trustworthy first

1. **Explicit configuration.** An operator-set coordinate pair wins
   over everything. It is the override channel and the test seam.
2. **Device location.** On a Mac this is CoreLocation, which uses WiFi
   positioning rather than a GPS receiver — accurate to roughly a city
   block, which is far better than layer 3 and good enough for weather,
   timezone and nearby-search. It requires a usage-description key and
   a granted permission; both can be absent, and absence is not an
   error.
3. **IP geolocation.** Accurate to tens of miles, sometimes to the wrong
   metro entirely. A last resort, never a default.

Each layer falls through to the next on failure. None of them raises.

## The rules that the failures came from

- **Say which layer answered.** A caller that cannot distinguish a
  block-accurate fix from an IP guess will present both with the same
  confidence, which is how a user ends up told they are in a city they
  have never visited.
- **Location is not durable.** Cache it with an age, expire it, and
  invalidate on meaningful movement. A stored home city that overrides a
  live fix is the specific defect this design exists to avoid.
- **Consent is a first-class state**, distinct from failure. "Not yet
  asked", "denied", and "granted but unavailable" need different
  handling and different messages.
- **Never silently substitute.** If no layer answered, the answer is "I
  don't know where you are", not a plausible city.

## Storage

Coordinates are personal data. Keep them in memory or in a short-lived
cache; do not write them to the fact store, do not log them, and do not
put them in a URL or query string.
