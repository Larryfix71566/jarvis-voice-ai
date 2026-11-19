---
date: 2026-11-19
system: claude
rows: [WS-15]
prs: []
---

# 2026-11-19: the weather chip names the device's city, not weather.gov's nearest place

- **System:** Claude (Claude Code cloud session), at the coordinator's request. Planned by Claude Opus 5.5; the Python half was implemented by a Claude Sonnet helper and checked here.
- **Row:** WS-15 (Weather: fresh location and current radar), as a follow-up to its accepted scope. The row's status lines are left for the daily batch (§0 rule 16).
- **Larry's words (UTC, Claude Duet channel), 2026-11-19 02:10:12:** "continue development, asign to sub-agents anything you can do in parallel". The coordinator picked this item from the follow-up recorded in [2026-11-18-weather-filler-and-location-answer.md](2026-11-18-weather-filler-and-location-answer.md) ("Not changed here: the weather chip says Mulberry").

## Why the chip said Mulberry

The sidecar had no device fix on file (`/api/status/location` returned `source: ip`, label Buford), because the Mac posted a CoreLocation fix to `POST /api/location` only when the bot asked for one. The chip's text is `get_weather()["location"]`, and for the IP's coordinates weather.gov's nearest NWS place is "Mulberry", which won over every other label.

## Change

- **Mac app:** a new `ConnectLocationReporter` (`macos/MortimerHost/Sources/MortimerHost/App/ConnectLocationReporter.swift`) asks `DeviceLocator` for one fix each time the app connects (on `voice/catalog`, beside the existing `location/hello`) and every 30 minutes while connected, and posts it to the sidecar's existing `POST /api/location` with the reverse-geocoded label ("Alpharetta, GA"). 30 minutes is half the sidecar's one-hour keep (`DEVICE_LOCATION_MAX_AGE_S`), so a connected app's fix never ages out. It stops on `offline` and `failed`.
- **Permission:** `DeviceLocator.connectFix()` asks only when Location Services already allows a fix; with "not determined", "denied" or "restricted" it posts nothing and the sidecar keeps its IP fallback. The existing first-run prompt (`locator.start()`) is unchanged; when Larry answers it with Allow, `locationManagerDidChangeAuthorization` asks for the fix at once instead of waiting 30 minutes.
- **Sidecar (`jarvis/ambient_weather.py`):** when the location came from the device, its own label replaces weather.gov's nearest-place name in the chip, as `jarvis/bot/weather_tool.py` already does for the weather card. IP and env-override labels are unchanged (weather.gov's name still wins for an IP guess). A label change at the same spot now invalidates the 15-minute weather cache, as a real move already did.
- **Unchanged:** the bot's per-request `location/request` path (D-L6) for local weather and "where am I". The status tool's location (`/api/status/location`, `jarvis/status/location.py`) reads the same sidecar device fix, so it now reports `source: device` after a connect.

## Evidence

- Python, Linux, Python 3.12 with the CI lock installed: see the PR body for the `pytest tests/unit` and Pyflakes results at the pushed commit. New tests: `tests/unit/test_ambient_weather.py::TestDeviceLabelWins` (5).
- Swift: `ConnectLocationReporterTests` (8 tests) runs in CI's macOS `swift-tests` job; no Swift toolchain in this Linux session.

## Not verified

- The macOS Location Services prompt and a real CoreLocation fix on the Mac, and the chip reading "Alpharetta, GA" on the deployed build. Live check: deploy `next` with this change, open the app, allow Location Services if asked, and read the chip and `/api/status/location` (`source: device`).

## Next actor

- larry: merge the PR into `next`; then the live check above on the next deploy.
