# Mortimer visual review (Fable 5.2), 2026-11-18

Reviewer: Fable 5.2. Written for comparison with Astra's independent review; no UI work starts until both are compared.

Basis: two screenshots from Larry's Mac (disconnected with the Agents drawer open; connected mid-conversation with the drawer closed) and source at `8d3be6df` (branch `next`). Paths are relative to `macos/MortimerHost/Sources/MortimerHost`. Tags: [pixels] = visible in the screenshot; [code] = read from source, not seen on screen.

## 1. Verdict

The orb is the best thing in the window and also the smallest: a 76 pt marble perched on top of the old cockpit, which nobody removed. The new parts were added, the old parts stayed, so the screen is five horizontal bands, a status stack, six chip boxes and a drawer of 9 pt scoreboard, with most facts stated three or four times. It reads busy because it is busy; current voice interfaces show one presence element and almost nothing else.

## Top 5 changes (summary)

1. **Clear the rail (S).** Remove the old status stack, the six agent chips, and the clock, weather and memory chips under the orb. The code comments say those slots were retired; they are still mounted (`Console/AdaptiveStageView.swift:79`, `:94`; `Console/VoiceWaveView.swift:539`, `:566`).
2. **Bigger orb (S).** Rail 200 to 260 pt, orb roughly doubled (`Console/AdaptiveLayoutMetrics.swift:9`, `Console/AdaptiveStageView.swift:78`, `Console/CometOrbRenderer.swift:35`).
3. **Readable transcript (S to M).** Cap it at about 680 pt wide instead of about 1,700, speaker once per run, timestamps on hover (`Console/ConversationThreadView.swift:648-678`).
4. **One composer pill (M).** Replace the 210 pt bottom stack (tray, drop zone, mic bar) with a pill and a paperclip menu; the mic moves into the orb with a visible mute (`Console/AttachmentTrayView.swift`, `Console/TypedComposerRow.swift`, `Console/MicControlsView.swift`).
5. **One top capsule (S to M).** Merge the two top bars and stop saying each state three or four times: READY beside Disconnect, two push-to-talk hints, the "Command Console" title (`Console/TopBarView.swift`, `Console/ConsoleActionBar.swift`, `Console/MicControlsView.swift:42-53`, `:78-81`).

## Screenshot 2: connected, mid-conversation

With the drawer closed and the app connected, the clutter just moves: into a full-width transcript and an even busier rail. [pixels]

- **The transcript runs the full window width, lines up to about 1,700 pt.** Every row gets a caps speaker label, a timestamp and a hairline; 14 rows, all stamped 10:39 PM. `Console/ConversationThreadView.swift:648-678` (84 pt label column, text at `maxWidth: .infinity`, rule under every row).
- **The rail got denser, not calmer.** Large 10:39 clock, date, a weather chip, a memory chip showing internal note text ("confirm via left panel, not mem..."), then the name, MORTIMER SPEAKING, Microphone muted and the six agent chips (Analyst red with an x). `Console/VoiceWaveView.swift:539` (AmbientStripView), `:566` (SystemVitalsView), `Console/AdaptiveStageView.swift:79`.
- **State colour clash, now on pixels.** The orb is rust while the label beside it says MORTIMER SPEAKING in cyan. `Console/VoiceWaveView.swift:671-679`.
- **States contradict each other on one screen.** READY next to a red Disconnect button; "Mortimer speaking" next to "Microphone muted" and "Mic off".
- **The bottom 210 pt is unchanged:** composer, Add content tray, drop zone, mic bar.
- **The orb works.** Speaking, the rust plasma reads clearly even at 76 pt. Making it bigger is the cheapest way to make the window feel current.

Three changes this shot adds to the list in section 4:

- **A (S).** Cap the transcript at about 680 pt reading width, centred in the stage, and drop the per-row hairline. `Console/ConversationThreadView.swift:670-675`.
- **B (S to M).** Group consecutive turns: speaker label once per run, timestamp on hover or once per group. `Console/ConversationThreadView.swift:648-678`.
- **C (S).** Take the clock, weather and memory chips off the rail (idle screen only, or a glance popover), and never show raw memory-note text. `Console/VoiceWaveView.swift:539`, `:566`, `Console/AmbientStripView.swift`.

## 2. What makes it feel busy, ranked

1. **Five full-width bands wrap the content, about 30% of the height (298 of 1000 pt, 331 with the banner).** Region: top bar, red banner, "Command Console" row, composer tray, mic bar. `Console/ConsoleView.swift:43-73`, `Console/CommandConsoleView.swift:16-38`. [pixels]
2. **The orb is tiny and the leftovers under it are louder.** Region: left rail below the orb: "Mortimer", STANDBY, "Microphone muted", six outlined caps chips. `Console/AdaptiveStageView.swift:79` (OrbFieldView still mounted), `Console/VoiceWaveView.swift:533-571`, orb size `Console/CometOrbRenderer.swift:35`. [pixels]
3. **The open drawer is the densest, brightest surface on screen.** Region: right column, three nested score cards in 9 pt mono with cyan numbers and amber warnings. `Drawer/CouncilRosterView.swift:118-253`. [pixels] Opt-in, but it outshouts the orb.
4. **Every state is announced three or four times.** Regions: top bar (Connect, ERROR), banner, rail (STANDBY, "Microphone muted"), mic bar ("Mic off", two push-to-talk hints); the name Mortimer appears four times. `Console/TopBarView.swift:73-80`, `Console/ConsoleView.swift:92-103`, `Console/VoiceWaveView.swift:549`, `Console/MicControlsView.swift:42-53`, `:78-81`. [pixels]
5. **22 always-visible controls (30 with the drawer), most of them occasional.** Regions: top bar (voice picker, Display), action row (Knowledge, Tools, Expand voice), rail chips, tray, mic bar. `Console/TopBarView.swift:127-153`, `Console/ConsoleActionBar.swift:94-117`. [pixels]
6. **The composer explains itself three times and takes 122 pt.** Region: bottom, above the mic bar: "Add content", a caption sentence, a drop zone, Paste, Choose. `Console/AttachmentTrayView.swift:17-29`, `:48-57`. [pixels]
7. **Too many type voices: 5 sizes, 8 treatments, 7 kerning values across 37 labels.** Regions: brand (top left), rail chips, mic bar hints, each a different tracked-caps style. `Console/TopBarView.swift:50`, `Console/VoiceWaveView.swift:638`, `:723`, `Console/MicControlsView.swift:44`. [pixels], values [code]
8. **Outline soup: about 30 bordered shapes in three radius systems (2, 6 to 12, 16).** Regions: everywhere; bezel buttons beside square HUD chips beside glass capsules. `App/Glass.swift:15-21`, `Console/VoiceWaveView.swift:736`. [pixels]
9. **Colour is not one language.** Region: cyan, red, amber, rust and green all visible at once in this shot. `App/AppTheme.swift:14-36`. [pixels] Up to 8 hues when answering, and the rail label uses green for listening while the orb uses indigo: `Console/VoiceWaveView.swift:671-679`. [code]
10. **The empty stage is not composed.** Region: centre: one greeting at the bottom of about 660 pt of black, orb top left, nothing aligned to anything. `Console/ConversationThreadView.swift:350-360`. [pixels]
11. **A raw system error is the headline.** Region: red banner under the top bar. `Console/ConsoleView.swift:92-103`. [pixels]
12. **Colour emoji in a monochrome HUD.** Region: mic bar, left and right ends. `Console/MicControlsView.swift:36`, `:59`, `:73`. [pixels]
13. **The carousel will be one flat card with Previous and Next at this window size.** Region: stage, when answering. Neighbours need 720 pt of carousel width: `Display/ResultCarouselView.swift:60`. [code]

## 3. Side by side with references

Reference comparisons come from page text, not from images: no image hosts were reachable from the review environment, and Instagram refused automated reads, so no Instagram source is cited.

| Reference | What it does (per page text) | Mortimer in the same spot today |
|---|---|---|
| Siri, iOS 18.1 (https://9to5mac.com/2024/07/30/this-is-the-new-siri-with-apple-intelligence-in-ios-181-beta-1/) | Presence is a glow around the display; on Mac a smaller design in the top right | 76 pt orb plus nine lines of status and five bands [pixels] |
| ChatGPT Voice (https://techcrunch.com/2025/11/25/chatgpts-voice-mode-is-no-longer-a-separate-interface/) | Old orb screen: blue circle, mute, video, X. Now voice runs inside the chat | Orb and thread already share a window (good), ringed by 22 controls [pixels] |
| Gemini Live (https://9to5google.com/2026/04/19/gemini-live-app-redesign/) | One pill with a waveform, share left, mute right, one transcript button | 122 pt tray plus a 68 pt mic bar with five items [pixels] |
| Perplexity voice (https://www.techradar.com/computing/artificial-intelligence/perplexitys-voice-mode-gets-a-futuristic-makeover-on-your-iphone) | Sphere replaces the mic icon and responds to voice and touch | Orb tap and hold exist but are off (`Console/VoiceWaveView.swift:33`); separate Mic button [code] |
| Perplexity composer (https://ai-design-patterns.pages.dev/teardowns/perplexity/composer) | Inputs behind "+", sources secondary until needed | Paste, Choose, caption and drop zone always shown [pixels] |
| Claude voice (https://www.tomsguide.com/ai/claudes-free-voice-mode-has-landed-heres-how-to-access-it) | Key phrases shown in real time while speaking | Full transcript rows with caps speaker label and timestamp [pixels] |
| rabbitOS 2 (https://www.rabbit.tech/newsroom/rabbitos-2-launch) | One card per feature, browsed like a Rolodex; bottom buttons mute, type, camera | Carousel neighbours hidden under 720 pt [code] |
| Raycast system (https://design.hagicode.com/designs/raycast/DESIGN.md) | Borders at 6 to 10% white, four type sizes, accent "punctuates" | Glass borders at 14% white (`App/Glass.swift:53-55`), about 30 outlines, 5 sizes, 5 accents [pixels] |
| Raycast Quick AI (https://manual.raycast.com/ai/quick-ai.md) | Composer with one Add Context menu; other actions in the Command-K panel | Every action is a permanent button [pixels] |
| Dia (https://browsercompany.substack.com/p/the-strategy-behind-dias-design) | Controls appear on hover or need; no banners; novelty spent in one place | Setup controls permanent; raw banner; brand dot and state dot animate beside the orb |
| ElevenLabs Orb (https://ui.elevenlabs.io/docs/components/orb) | Four states, driven by input and output volume, two colours | Closest match: the orb itself is on pattern. The frame is the problem |

## 4. Prioritized changes

Sizes are estimates: S under a day, M 1 to 3 days, L a week or more.

### Do first (S)

1. **Unmount OrbFieldView from the rail and bottom slots.** Removes the name, state label, notices and six chips. `Console/AdaptiveStageView.swift:79`, `:94`.
2. **Give the orb room.** Rail 200 to 260, slot 150 to 220. `Console/AdaptiveLayoutMetrics.swift:9`, `Console/AdaptiveStageView.swift:78`.
3. **Delete duplicates.** "Command Console" title (`Console/ConsoleActionBar.swift:97-102`), ERROR pill (`Console/TopBarView.swift:73-80`), both push-to-talk hints (`Console/MicControlsView.swift:42-53`, `:78-81`), "Add content" headline, caption and drop zone (`Console/AttachmentTrayView.swift:17-29`, `:48-57`), carousel "Results" headline (`Display/ResultCarouselView.swift:35`).
4. **Error banner:** one plain line plus Retry, gone on reconnect. `Console/ConsoleView.swift:92-103`.
5. **Wire the needs-you ring** (pass `needsYou`) and drop the amber sentence. `Console/AdaptiveStageView.swift:70,77,89`, `Console/VoiceWaveView.swift:550`.
6. **Only the orb moves at rest; SF Symbols replace emoji.** `Console/TopBarView.swift:231-257`, `Console/MicControlsView.swift:36,59,73`.
7. **Lower the carousel neighbour threshold** or give the carousel the larger share. `Display/ResultCarouselView.swift:60-62`, `Console/AdaptiveStageView.swift:125-131`.

### Next (M)

8. **One composer pill:** field, paperclip menu (Paste, Choose), Send. About 44 pt instead of 122. `Console/AttachmentTrayView.swift`, `Console/TypedComposerRow.swift`.
9. **Fold the mic bar into the orb.** Set `interactive: true`, move wake word and sound into a menu, keep a visible mute (Gemini hid mute, then restored it). `Console/AdaptiveStageView.swift:70,77,89`, `Console/MicControlsView.swift`.
10. **Merge top bar and action row into one capsule** with an overflow menu for Connect, Voice, Display, Panels. `Console/TopBarView.swift`, `Console/ConsoleActionBar.swift`, `Console/CommandConsoleView.swift:17-29`.
11. **Type and shape tokens:** three sizes, one caps style, one kerning, one radius scale, borders at 10% white or less. `App/Glass.swift`, `App/AppTheme.swift`, call sites.
12. **Raise the orb's glass factor** toward the mockup's 163 to 184 pt, behind `OrbShellFrameTimeTests`. `Console/CometOrbRenderer.swift:35`.
13. **Drawer:** 11 pt floor, no glass on nested cards. `Drawer/CouncilRosterView.swift`, `Drawer/AgentsTab.swift`.

### Bigger moves (L)

14. **Composed empty state:** large orb centred on an empty stage, moving to the rail on the first turn. `Console/AdaptiveStageView.swift:52-97`.
15. **Finish direction 6's frame:** rail, one four-item capsule, carousel, composer pill, plus a Command-K palette for everything secondary. Retires the band stack in `Console/ConsoleView.swift:40-74`.

### What the cleaned-up idle and answering screens look like

**Idle.** A dark window with the orb large and alone, dim when offline. One quiet line under it if something is wrong ("Offline. Retry"). One floating capsule at the top with four items, one composer pill at the bottom. No chips, no status stack, no hint strings.

**Answering.** The orb sits in the rail at full rail width, rust arcs, nothing under it. The stage is the thread on one side and one glass card in focus on the other, neighbours hinted at the edges, a small "1 of N". Rust is the only accent on screen; a yellow ring appears on the orb only when approval is needed.

## 5. Optional orb ideas

Strictly optional. The orb is a keeper; nothing in section 4 depends on these.

- Drop the 17 static stripes inside the glass if they read as seams once the orb is larger (`Console/CometOrbRenderer.swift:79-94`). Judge after change 2.
- Live refraction shader, the spec's first choice; gated by the 10% frame-time rule.
- Tilt parallax as a cheaper depth cue. The spec holds it as the fallback, and switching needs Larry's OK.
- A collapsed mode: the orb as a small floating circle when the window is not in focus, as Gemini's pill collapses.

## 6. What's not verified yet

Two states have pixels: disconnected, and connected with Mortimer speaking. These shots would settle the rest:

- **Connected idle, drawer closed:** whether the clock, ambient chips and vitals crowd the rail further.
- **Listening (mic open):** indigo arcs against the green LISTENING label; whether the colour clash is visible.
- **Mortimer speaking, mid-answer:** rust arcs, activity row, how many accents are on screen at once.
- **A result showing at this window size, then at about 1720 pt wide:** confirms the flat-card carousel and the neighbour threshold.
- **Pending approval:** confirms no yellow ring and the amber sentence.
- **Click and hold on the orb with the mic button in frame:** confirms orb input is dead.

Also untested: frame time of a larger orb (`OrbShellFrameTimeTests` on the Mac), whether the drawer opens by default on launch, and every reference comparison against real images.

## Limits of this review

- Fable compared Mortimer with what the reference pages say, not with images of them.
- The result carousel and the listening and approval states have not been seen on screen; the answering screenshot was blocked by the weather bug.
- Sizes S/M/L are estimates. Counts (controls, labels, type sizes) come from source read at `8d3be6df` plus the screenshots, not from a measuring tool.
