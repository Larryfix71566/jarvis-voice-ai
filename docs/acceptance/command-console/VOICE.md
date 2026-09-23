# Voice parity acceptance

The backend now owns a versioned `ConsoleSession` with generation, revision,
duplicate, bounded replay-cache, and stale-request handling. Pointer and voice requests share the
same `console/request` schema. The current server returns truthful
`unsupported` results for actions whose native state owner is not connected;
it never claims a panel or recipient action succeeded.

- [x] Protocol fixture round-trip and malformed-action rejection.
- [x] Duplicate request replay and stale generation/revision rejection.
- [x] Native layout-2 pointer actions use the same coordinator and validated
  request shapes as voice actions; full Mac voice exercise remains open.
- [x] Hands-free approval accepts only the exact final-transcription phrases
  “Send these items” and “Cancel these items” while a matching offer is
  pending; the one-time consent carries session, generation, batch and user
  turn IDs and reuses the native manifest path. Normalization and
  non-matching speech are covered in `test_shared_content`.
- [x] The locked Command Console voice fixture contains all 14 required
  navigation, graph, Atlas, display, sharing and input phrases; protocol tests
  validate each fixture case against the closed Python action catalog.
- [x] The fresh candidate's native transport reaches the bot WebSocket
  handshake without blocking socket callbacks behind CoreAudio startup;
  `NativeAudioTransportTests` pass 21/21, including the main-actor
  CoreAudio-start regression.
- [ ] Mac end-to-end voice exercise for every enabled action.
- [ ] Ambiguous/duplicate title and unavailable-display voice acceptance.
