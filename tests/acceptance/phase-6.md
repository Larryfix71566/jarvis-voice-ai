# Phase 6 Acceptance Checklist — Web Client

Setup: `./scripts/run_bot.sh` in one terminal, `./scripts/run_web.sh` in
another, open `http://localhost:5173`.

- [ ] Connect button: pill shows gray `disconnected` → amber while connecting
      → green `ready` after clicking Connect
- [ ] Speak "what time is it" → transcript lines for BOTH sides appear within
      ~2 s (user right-aligned, Jarvis left), agent feed shows the Scheduler
      chip while working, orb pulses while Jarvis speaks
- [ ] Voice picker populated from the catalog (rachel / george / eric,
      current pre-selected); switch to george → audible voice change on the
      next reply + `voice/current` reconciliation (server log shows the
      TTSUpdateSettingsFrame path)
- [ ] Reminder request ("remind me to stretch in one hour") → agent chip
      "⚙ Scheduler working…" then a timestamped "done" history entry
- [ ] Mic toggle off → no transcription happens while muted
- [ ] Hold SPACE → mic unmutes only while held (ignore auto-repeat: holding
      does not flicker); release → muted again
- [ ] Kill the bot (`Ctrl-C`), restart it, click Disconnect then Connect (or
      refresh once — record which) → session resumes without a hard refresh
- [ ] Trigger an error (e.g. stop the bot mid-turn) → red error banner
      appears; banner auto-dismisses on the next successful turn
- [ ] `cd web && npm run build` → clean (zero TS errors) — DONE in CI of this
      phase: strict `tsc -b` + vite build pass

## BLOCKED ITEM (same as Phase 5)
Audible verification (voice switch heard, orb-synced speech) requires the
ElevenLabs account block to be lifted — TTS generation currently returns 401
`detected_unusual_activity`. All client-side behavior above is otherwise
verifiable; the build gate is fully green.

## Notes
- App messages ride the rtvi-ai `server-message` envelope (D-005); the bot
  accepts both the locked raw `voice/set` shape and the client-js
  `client-message` envelope.
- Dev server talks to the bot cross-origin (`localhost:5173` →
  `localhost:7860/api/offer`); the pipecat runner allows all origins by
  default, no proxy needed.
- npm on this sandbox mount: `--no-bin-links`, scripts call tsc/vite by
  explicit node path (D-006). If node_modules is ever corrupted by the mount,
  reinstall on a local filesystem and copy it in (see git history).
