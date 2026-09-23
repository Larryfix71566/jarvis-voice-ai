# Candidate reconnect attempt — 2026-09-18

This receipt records the follow-up reconnect exercise after the earlier
supporting-display run. It is a failure receipt; it does not close the
reconnect gate.

## Observed sequence

- The existing launchd services were restarted. Read-only checks then returned
  `GET /api/health` = `200 OK` from the admin service and `GET /` = `307`
  redirect from the bot on `127.0.0.1:7860`.
- The exact release-review candidate was rebuilt and launched from
  `macos/MortimerHost/.build/MortimerHost.app`.
- The candidate initially showed `ERROR VOICE` with
  `Socket is not connected`. Selecting **Connect** changed the UI to
  `CONNECTING VOICE`.
- The accessibility/screenshot observer could not obtain a settled post-connect
  state before its bounded observation timed out. No `READY VOICE` state was
  recorded for this attempt.

## Acceptance effect

The local services were healthy at the time of the retry, but candidate
reconnect readiness was not demonstrated. UI2-06, UI2-19 and UI2-20 therefore
retain their reconnect and long-lived-session gates. No credentials or memory
contents were written to this receipt.
