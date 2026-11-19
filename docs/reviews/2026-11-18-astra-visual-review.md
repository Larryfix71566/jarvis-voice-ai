# Mortimer: put the conversation in command

**Independent interface review · 18 November 2026 · Mac command console**  
**Recommendation:** Keep the glass orb, composed answers and result carousel. Change what gets the stage. At rest, Mortimer should look like someone you can talk to; the full console should appear when you ask to inspect the work.

## What the Mac window actually showed

I inspected the native Mortimer window and its accessibility tree while it was disconnected, with the Agents panel open. This was one real window state, not necessarily the default on a fresh install. I did not connect the microphone, trigger a run, open private records or test the phone.

| Where my eye went | What was on screen | Why it matters |
|---|---|---|
| Right, first | “No agent activity this session,” immediately above dense historical council cards with scores, timestamps, colored warnings and model labels. | The loudest part of the window described neither the current conversation nor a decision I needed to make. “No activity” and a wall of activity read as contradictory until you understand the time scopes. |
| Center, second | A large dark expanse, “Conversation,” and a sentence directing me to the microphone controls. The microphone was disabled. The useful Connect button lived at the far upper left. | The screen had plenty of space, but it separated the instruction from the one action that could fulfill it. This is a hierarchy problem, not a shortage of whitespace. |
| Left | A restrained, dark glass orb in standby, followed by six outlined role buttons: Developer, Analyst, Systems, App Builder, Librarian and Scheduler. | The orb is the one unmistakably Mortimer object. Idle roles were larger collectively and looked as actionable as starting a conversation. |
| Top and bottom | Knowledge Atlas and Memory graph appeared twice in successive rows. A permanent Add content shelf offered Paste, Choose and a drop target. Beneath it another band advertised Space twice, plus mic, wake word and sound. | These are useful capabilities. Displaying each affordance independently teaches the window's implementation rather than the user's next move. “Close” also failed to name what it closes: the panel, not Mortimer. |

**Version boundary.** GitHub’s [enhanced branch at inspection](https://github.com/Larryfix71566/jarvis-voice-ai/commit/8d3be6df028454223fd363f042182e40735ea5fc) contained #385; [main](https://github.com/Larryfix71566/jarvis-voice-ai/commit/fd9a156ee1429dc7df3e5d1ec0cf29ebdedd09d7) was separate. The normal on-disk bundle reported the enhanced revision **and** a dirty-source flag. I did not establish that the visible process was that exact binary. The enhanced source has a single command action row and conditional thread activity/approval UI; those improvements must not be scored as absent just because this disconnected window did not exhibit them. Conversely, a source merge is not a visual acceptance result.

## The direction: one room, two levels of detail

**The front room is the conversation.** One quiet charcoal canvas, a glass orb, one line of honest status, one composer. Top right: a labeled **Inspect** button, visually secondary. No persistent roster, no models, no historical warnings. A person who likes the console can explicitly pin Inspect open, or keep it on the second display. Do not silently reopen it or steal focus when an agent starts. Preserve existing keyboard access; give occasional users a visible way in.

**The back room is the operator console.** Keep the real depth: active agents, tools, council rounds, costs, logs and history. Open to *this run* from its activity line; place older sessions behind History. Atlas and Memory graph stay discoverable in the same workspace switcher, not in duplicate toolbars. This is a change in default emphasis, not a request to delete expert tools.

| Moment | What owns the stage | What stays reachable |
|---|---|---|
| Disconnected | Still orb, “Not connected,” one enabled **Connect** action beside the explanation. No instruction to speak until it will work. | Connection details on demand; typed draft only if it can actually be kept. |
| Ready / listening | Orb and one plain-language state (“Ready” or “Listening”); one line to type, attach or use the mic. Show the Space hint once. | Mute must be explicit and reachable without color or animation. Whole canvas accepts a drop; reveal the drop zone during drag, preview before sharing. |
| Working | Orb moves to the thread margin. One current-tense line under the request, e.g. “Searching your notes.” No general-purpose spinner pretending to be progress. | Click the line to inspect the active run. Stop/interrupt remains accessible. Preserve focus and scroll position when other work finishes. |
| Needs a decision | The card names the action, destination and consequence; **Approve** and **Decline** sit together. A yellow orb rim draws attention but does not carry the message alone. | Keyboard and screen reader users can act in place. No hiding approvals in a global inspector. |
| Answer ready | One composed answer takes the center. Lead with what happened, then the useful artifact or evidence. One selected result; only show a result count or “Show all” when there is more than one. | Thread, provenance and other results are one deliberate action away; the orb stays small and interruptible. |

**What makes this feel advanced:** the same orb yields its place to the work. When a request produces an answer, the light recedes to the margin and the answer takes its position. When Mortimer needs permission, the movement stops and the action is readable. With Reduce Motion, the same sequence is a direct cut with a text label. Skip star fields, decorative particle systems and animated metrics. Glass works best as Mortimer’s material signature, not as the finish on every rectangle. Preserve the [approved palette and orb specification](https://github.com/Larryfix71566/jarvis-voice-ai/blob/8d3be6df028454223fd363f042182e40735ea5fc/docs/interface-research/orb-plasma/ORB_SPEC.md), including rust for Mortimer, teal for the speaker, yellow for approval, and static/offline behavior. Natural-case text for instructions; monospace for identifiers and measurements in Inspect.

## What I would prototype first

1. **Fix the disconnected scene before changing any shader.** Put the single connection action beside the orb. Hide disabled voice preferences, remove both duplicate navigation and duplicate shortcut hints where present, and make the inspector opt-in for the conversational view.
2. **Use one request to prove the transition.** Prototype “Find the latest project brief,” with synthetic content. Show ready → listening → searching → one composed answer. Then swap in a request requiring approval, and interrupt another run. Keep the same field, not separate voice and attachment shelves. Reuse the existing thread activity and approvals rather than building rival versions.
3. **Tune visual detail last.** Check the new hierarchy first in grayscale; then tune contrast, spacing and motion at actual Mac size. Let the orb command attention only while it has something to say. Use the second display for the full operator view rather than shrinking the same console onto every screen.

**Decision test for the next demo:** Show fresh users a five-second still of disconnected, processing and approval states. Can they name the state and their next action without coaching? Can they connect, attach a file without sending it accidentally, identify who will receive it, decline an approval with the keyboard and find the last run in Inspect? Repeat at narrow and wide widths, with Reduce Motion and with the inspector pinned. If success depends on animation, scrolling a roster or reading a tooltip, the hierarchy still needs work. These are proposed checks, not test results.

## Useful references, and where the analogy stops

- **Shipped desktop interaction:** [Raycast Quick AI](https://manual.raycast.com/ai/quick-ai) answers in the launcher, with a deliberate handoff into full AI Chat. Its [YouTube introduction](https://www.youtube.com/watch?v=syONnJrvpFI) is a product demo, not evidence about today’s exact appearance. Borrow the compact-to-deep relationship, not the launcher’s appearance.
- **Shipped voice interaction:** [Gemini Live](https://support.google.com/gemini/answer/15274899?hl=en) documents hold, mute, interruption, and switching between voice and text within a conversation. Borrow the explicit controls and continuity. Mortimer also needs approvals and auditable work, which a voice-call interface alone cannot handle.
- **Visual study, not a shipped assistant:** [Alex Dubranov’s AI Orb](https://dubralex.com/projects/ai-orb) separates the listening view from the tuning surface. The [studio image](https://dubralex.com/projects/AI-orb/AI-orb-1.webp) makes that separation tangible: a single luminous form, a small status label and considerable breathing room. Borrow the division of responsibilities, not the purple palette or an assumption that its runtime proves end-to-end usability.

I found no Instagram reel I could verify as a relevant original demonstration, and did not use reposts as evidence. The external references above are supporting examples; the recommendation comes from the visible Mortimer window. No parallel review informed this assessment.
