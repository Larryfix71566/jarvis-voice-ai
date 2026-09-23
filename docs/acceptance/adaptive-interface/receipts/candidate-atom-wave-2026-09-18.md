# Candidate atom voice display — 2026-09-18

UI2-21 sandbox implementation and rendering acceptance for the compact
Command Center voice display.

## Implemented behavior

- Adaptive Command Center presentation uses a compact atom: shared nucleus,
  two tilted orbital planes, and bounded measured-energy glow/particles.
- User microphone audio is rendered on a teal orbital channel; Mortimer
  playout audio is rendered on a warm orange orbital channel.
- Both channels render independently during overlap. Missing speech measurements
  do not synthesize speech movement; connected idle/muted retains ambient motion.
- Reduced Motion disables orbital motion while preserving the state and color
  cues. Legacy layouts retain the existing Silo wave for rollback.
- The glass/comet revision replaces the earlier wireframe geometry. The sphere
  radius is now `0.255` of the available short side; comet paths use 1.53 and
  1.17 times that radius, with separate -0.48/+0.56 radian orientations. This
  corrects the old comet projection, where both channels followed the same
  flattened ellipse despite the advertised tilt.
- Angular velocity remains `0.60 + 0.90 * energy` radians/second with bounded
  elapsed-time accumulation. Geometry and bloom fit the compact voice region.
- Active electrons now render as tapered cyan/orange comets with bright heads,
  long particle tails, and a deliberate gap before the sphere. Listening keeps
  a restrained low-energy comet presence so the active interface does not look
  frozen while still reserving full brightness and scale for measured speech.
- Each channel now carries two staggered comet heads per orbital plane, matching
  the layered reference motion while retaining independent user/Mortimer color
  attribution.
- The former full orbital wireframe rings were removed from the adaptive atom;
  the comet heads and tails are now the sole electron motion treatment.
- `CometOrbRenderer.swift` draws a blue glass shell with broken specular
  highlights, soft reflections, irregular internal filaments, diffuse colored
  light and motes. The latitude/longitude grid and three regular spirals are
  removed. Comets have bright cores and dispersed sparks; tail bloom fades
  with the tail instead of drawing a uniform blurred arc.
- Both comet colors remain visible as ready indicators. Measured audio lifts
  each channel's brightness independently; the nucleus identifies the current
  talker. Back/front passes and depth-dependent intensity give orbital depth.
- Mortimer's channel is warm orange `#E07020`; the nucleus follows the active
  talker (teal for user activity, orange for Mortimer activity, periwinkle
  while idle or connected/muted, neutral while offline or connecting).
- Connected idle and mic-muted states share a periwinkle glow `#7C8CFF` and
  gentle comet/plasma motion. Muted input never supplies speech energy. The mic
  control and accessible "Muted" label still indicate input status. Mortimer's
  measured playout retains orange priority even when the mic is muted.
- The energy volume extends to 75% of the sphere radius, with a smaller hot
  center and transparent falloff. This is a procedural native approximation of
  the selected image, not a claim of photorealistic or pixel-exact equivalence.
- Existing measured dB windows, gains, controls, compact startup, captions,
  and accessibility label/value path remain unchanged.

## Acceptance evidence

- Connected/muted follow-up: `VoiceWaveRenderingTests` and
  `VoicePresentationStateTests`: **17 executed, 0 failures** (10 rendering tests).
  Verified muted/idle render equivalence, continued muted motion, disconnected
  stillness, Reduced Motion, and measured assistant output with input muted.
- Glass/comet revision: `VoiceWaveRenderingTests`, `PresentationLevelMappingTests`
  and `CompactConversationTests`: **19 executed, 0 failures** (8 rendering tests).
- Native user, Mortimer and idle previews were generated and visually inspected
  at a 400×180 point compact canvas (`.build/interface-fixtures/orb-*.png`).
  These confirm the grid removal, glass highlights, separate comet colors,
  colored internal filaments and unbroken compact bounds.
- Reference-video follow-up:
  Orbital phase is accumulated from elapsed frame time, not uptime multiplied
  by audio amplitude. A regression test verifies bounded travel at long uptime,
  with level changes, paused motion and resume. Live visual acceptance remains open.
- Earlier evidence, before the glass/comet revision: `AdaptiveInterfaceClosureC2Tests`, `CompactConversationTests`,
  `FullConsoleRenderingTests`, and `PresentationLevelMappingTests`: **28
  executed, 0 failures**.
- The overlap test finds both teal and warm orange channels in one rendered frame.
- The nucleus test verifies teal while the user is speaking and orange while
  Mortimer is speaking.
- The unavailable-speech test renders identical frames across time, proving no
  synthetic speech animation when measured output is absent.
- The new Reduced Motion test verifies identical idle frames across time,
  including the plasma and idle pulse (the prior uptime-based pulse did not
  freeze). All procedural motion now derives from the pausable orbital phase.
- Earlier live candidate accessibility evidence exposes `Voice activity — user teal,
  Mortimer orange` with the current state value (verified in compact
  Conversation mode after relaunch).
