# WS-03 — deployed Versions wording, 2026-10-06

Result: **the dormant-auth Versions explanation passes this narrow visual
subcheck**. SW-A overall remains open. SW-B and SW-C remain the only fully
accepted Skills gates (2/12).

## Build and observation

Codex inspected the unlocked Mac through the native accessibility tree and
screenshot. The running native process was PID `32144`, executable
`/Users/larryfix/jarvis-voice-ai-clean/macos/MortimerHost/.build/MortimerHost.app/Contents/MacOS/MortimerHost`.
Its bundle `MortimerSourceRevision` was
`bde22bb6425c6bf36a3e0d7cf53f2785c274190d`, matching the recorded production
deployment receipt from 2026-10-03 16:34 EDT.

The initial display-name lookup selected the older Xcode-built `Mortimer.app` at
`~/Library/Developer/Xcode/DerivedData/Mortimer-caojwgrnnqhylkgrvwoimlobukrc/Build/Products/Debug/Mortimer.app`.
Its “Mortimer stack isn't running” text matches the retired MortimerShell
RetryView. The actual bot launchd service was running from production. Codex
opened the already-installed native MortimerHost; no rebuild, deployment or
service restart was performed.

Voice stayed **disconnected** throughout the check. Codex selected
**Tools → Skills → Current weather in Fahrenheit → Versions**, without
connecting voice, invoking a skill, enabling authentication or calling a model.

## Visible result and local HTTP corroboration

The selected Versions view displayed:

> **Version evidence unavailable**
>
> Version and candidate history require bearer authentication, which is not
> enabled for this local session. The Skills library and process remain available.

The local catalog returned HTTP 200. Its observed schema uses `items` and
`skill_id`; the selected ID was `current-weather-with-fahrenheit`. A read of
`/api/skills/current-weather-with-fahrenheit/versions` returned HTTP 503:

```json
{"detail": "Skills requests require bearer authentication"}
```

This response explains the history restriction; it is not evidence that the
catalog or backend is down. The library loaded six skills and the selected
skill's Overview and Versions controls were available.

## Evidence and limits

The [screenshot](versions.png), [complete accessibility text](accessibility.txt),
[local HTTP record](http-response.json) and [manifest](manifest.json) identify
the exact observed app build. The manifest records their
SHA-256 values and capture timestamps.

This receipt verifies only the deployed dormant-auth message. It does not
verify authenticated version/candidate history, owner-scoped inventory,
creator readiness, actual skill execution, voice, VoiceOver/keyboard, physical
display transfer, VM lifecycle, provider quality, activation, rollback or the
remaining SW-A baseline journeys. It changes no settings or acceptance
thresholds. Preparation for authentication remains separate from activation.
