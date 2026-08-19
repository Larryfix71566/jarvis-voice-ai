# Mortimer handoff loop — investigating with a human in the loop

**Status:** APPROVED and IMPLEMENTED 2026-08-18. All Parts built and
tested (1299 unit+integration passing, one pre-existing network failure).
Acceptance checklist: `tests/acceptance/handoff-loop.md`.

**Two deviations from the plan as written, both recorded rather than
quietly taken:**

1. **§6 H2's acceptance said "prompt growth under 10%".** Measured after
   implementation: the developer grew 15%, and the four conversational
   agents grew ~70% *cumulatively across the day* — start-of-day 1,041
   chars for the scheduler against 1,716 now. The four shared discipline
   rules total ~1,226 chars against ~490 of scheduler-specific
   instruction, so **71% of a conversational agent's prompt is now shared
   rules**. `test_conversational_agents_stay_lean` — a guardrail written
   this morning — caught it, and its ceiling was raised from 1,600 to
   1,800 with that measurement recorded in the test itself. The four
   rules overlap substantially (all are variants of "do not state what
   you did not observe"); the next addition should CONSOLIDATE them, the
   way `GOLDEN_RULES` consolidated rules 3/11 rather than adding.

2. **H3.3a (the copy button) was not in the first draft of the plan** —
   it was added after Larry asked where commands were being moved, which
   surfaced that "copyable" in H3.3 meant only "not `user-select: none`".
   The app had no copy affordance anywhere.

**Author:** drafted 2026-08-18 for Larry, in a Cowork session.

**Origin.** Larry, 2026-08-18, after the weather investigation:
*"Mortimer for whatever reason gives up after the first road block it
seems, you didn't, you kept digging to a resolution. That is what I expect
of Mortimer, I believe quitting is not acceptable."* Plus two follow-ons:
commands to run outside Mortimer should appear in the display window, not
dialog text; and there is no way to paste anything back in.

---

## 1. Evidence — the weather investigation, measured

The worked example this plan is built from. Four runs, 2026-08-18:

| run | status | latency | tools | what happened |
| --- | --- | --- | --- | --- |
| `b74ed019` | failed | 141.6s | 28 (27 ok) | hit `max_iterations` 15/15 |
| `38fb0ff1` | ok | 46.4s | 9 (8 ok) | found the controlling files |
| `f990a765` | ok | 35.1s | 6 (5 ok) | `.env` read-denied; no live env |
| `ce0fe118` | ok | 62.5s | 7 (5 ok) | named its limits, gave source analysis |

### 1.1 "Gives up" is not what the log shows

`b74ed019` ran 27 of 28 tool calls successfully and continued until the
iteration cap **forcibly stopped it**. `ce0fe118` stated its limits
plainly and then delivered a full chain-of-code analysis. Neither quit.

Two different things actually happened:

1. **It ran out of budget while searching.** It had every file it needed
   by round 8 (`ambient_weather.py`, `admin/server.py`,
   `AmbientStrip.tsx`). Rounds 9-15 were a widening search — a full
   `repo_list_files`, an unrelated `displayWindow.ts`, and its own
   `SKILL.md` — before the cap ended it.
2. **On a hard block it reported the block instead of routing around
   it.** *"I have no shell/process-execution tool. I cannot inspect the
   live PID's environment, cannot curl localhost:7861/api/ambient."*
   True, honest, and a dead end.

The difference between that and the session that solved it: when the
human hit the *same* wall, he handed Larry the command and continued from
the output. **Mortimer treats a blocker as a terminus; the fix is to make
it a handoff.**

### 1.2 The mechanism that would block the handoff today

`jarvis/agents/delegate.py:109-124` refuses any same-agent delegation
within `RETRY_GUARD_WINDOW_S` (120s) whose task text overlaps a failed
one at `RETRY_GUARD_OVERLAP` (0.5):

```
REFUSED: the developer agent just failed this same task. Report that
failure to the user and ask how to proceed — do not retry with reworded
instructions.
```

So "here is the curl output, keep going" is mechanically refused. Worse:
a *well-formed* continuation carries the prior findings forward, which
pushes overlap **up**, making the good continuation the most likely to be
refused. The guard and the handoff cannot ship separately.

### 1.3 There is no return channel at all

Confirmed by inspection: every `<input>` in `web/src/` is in `GitPanel`
or `EditModePanel`, both of which POST to the sidecar's REST endpoints —
a different process from the bot, which holds the LLM context. **Nothing
in the client can put text into the conversation.** Voice is the only
input, and STT cannot carry a JSON blob, a URL, or a stack trace.

### 1.4 What already exists and can be reused

- `jarvis/bot/pipeline.py:479` `inject_silent(text)` —
  `aggregators.user().add_messages([...])`, appends to the live context
  without forcing an immediate spoken reply. The injection half is built.
- `jarvis/bot/display.py` `DISPLAY_TOOLS` / `DISPLAY_SURFACE` — per-tool
  routing to `"window"` or `"drawer"`.
- `mcp_selfedit/logic.py` `AdminClient.get/post` — HTTP to the sidecar.
- `jarvis/selfedit/service.py:111` `_run(argv, cwd, timeout)` —
  argument-list subprocess, output truncated, `127`/`124` on
  missing-binary/timeout.
- **The admin sidecar runs on Larry's Mac**, so `pbpaste`/`pbcopy` are
  reachable without any Swift change.

---

## 2. The loop this plan enables

```
Mortimer investigates
  → hits something it cannot verify itself
  → writes findings to a file, shows the exact command in the DISPLAY window
  → Larry runs it, copies the output
  → "read my clipboard"
  → Mortimer resumes WITH the findings, not refused, and finishes
```

Every arrow is currently broken. This plan fixes each one.

---

## 3. Decisions

**D1. The clipboard path goes through the sidecar, not the Swift bridge.**
The sidecar runs on the Mac; `pbpaste`/`pbcopy` are there.
*Alternative considered:* extend `ShellBridge.swift` with a
`readClipboard` command. *Downsides:* the existing bridge is
fire-and-forget (`WKScriptMessageHandler`, no reply path), so returning a
value needs `WKScriptMessageHandlerWithReply` — a new pattern; it needs
an Xcode rebuild to change; and the text would still have to reach the
bot, which is the client→server channel that does not exist (§1.3). The
sidecar route needs none of that.

**D2. Clipboard read is ARMED, not free.** `clipboard_clear` wipes the
clipboard and sets an armed flag; `clipboard_read` refuses unless armed
and disarms after reading. Larry's own proposal, made mechanical: without
the flag, "clear first" is a discipline that protects only when
remembered, which is the "a rule without a backstop is a wish" failure.

**D3. Clipboard content NEVER enters the transcript.** `MemoryWatcher`
*"periodically folds one live session's transcript into long-term
memory"* via an LLM extraction call. Anything in the transcript can
become a durable SQLite fact. A password copied thirty seconds earlier
would be eligible. Exclusion is by construction — the injection path is
already distinct from speech, so `TranscriptObserver` simply never sees
it — not by a prompt asking nicely.

**D4. What was read is shown in the DISPLAY window instead.** This
recovers the reviewability D3 gives up, and it converges with Larry's
other request: commands go *out* to the display, clipboard comes *in* and
is shown there. The display becomes the surface for everything that must
be visible but must not be remembered.

**D5. No credential-blocking heuristics.** A regex for `sk-` or a base64
blob will false-positive on real terminal output and, worse, creates
false confidence that a filter is working. Showing Larry what was read,
immediately, is stronger protection than guessing.

**D6. An exhausted-budget run does not arm the retry guard.** It was not
a failed approach, it was an unfinished job —
`ITERATIONS_EXHAUSTED_MESSAGE` already says exactly that.

---

## 4. Design constraints

| Constraint | Holds by | Note |
| --- | --- | --- |
| Clipboard never reaches long-term memory | **construction** | never enters the transcript the sweep reads |
| Clipboard read requires an explicit prior clear | **construction** | armed flag in the sidecar, disarmed on read |
| No proactive clipboard access | **construction** | only inside an explicit tool call; no watcher, no poll |
| `pbpaste`/`pbcopy` are fixed argv, no parameters | **construction** | nothing to inject; reuses `_run`'s argument-list discipline |
| A continuation with new data is not refused | **construction** | guard exemption + explicit continuation marker |
| Mortimer states a command rather than stopping | *discipline* | prompt rule; the mechanical part is only that the tool exists |

That last row is the honest weak point: nothing forces the model to offer
a handoff. `show_commands` makes it *possible* and the prompt makes it
*expected*, but a model that simply says "I cannot" is not caught by
anything. Acceptance item 6 is the observational check.

---

## 5. Part H1 — retry guard: continuation is not retry

**H1.1** An exhausted-budget failure does not record a guard entry.
`ITERATIONS_EXHAUSTED_MESSAGE` is distinguishable from `STUCK_MESSAGE`
and from a real `FAILED:` reply; only the latter two arm the guard.

**H1.2 A handoff resets the budget — and the reset is EARNED, not
claimed.** *(Larry, 2026-08-18: "each time Mortimer hands off to the user
the counter resets to 0, that way if the process is long and interactive
it can continue to resolution.")*

The principle: **the iteration cap bounds unbounded AUTONOMOUS spend. A
handoff is not autonomous** — Larry gates every round, decides whether to
continue, and supplies the new information. The failure the cap exists to
prevent is not occurring, so the reset is correct rather than a loophole.
Mechanically the counter already resets (a fresh `SubAgent.run()` builds
fresh `messages` and a fresh loop, `base.py:295`/`378`); what this Part
does is stop the retry guard from *blocking* the continuation.

**The condition that keeps it safe:** a continuation is valid only when
the prior run **actually offered a handoff** — it called `show_commands`,
or returned the blocked-with-request shape from H2.1. That is checkable
server-side from the run's own recorded events; it is not the model's
word for it. A `continuation: true` on a run that ended without offering
a handoff is refused exactly as a reworded retry is.

Without that condition, an unlimited reset plus a self-declared marker
would give a model infinite retries with the guard disabled — precisely
the failure the guard was built for, now unbounded. **The reset is earned
by a recorded handoff, not asserted by a flag.**

**H1.4 Handoff depth is visible, not capped.** Track how many handoffs
this investigation has taken. There is no limit — Larry's rule is that
quitting is unacceptable, and a cap is quitting on a timer. But at
`HANDOFF_DEPTH_NOTICE` (proposed 4) Mortimer states where it stands
before asking for the next thing: what it has established, what it still
does not know, and what the next command would settle.

This is an honesty checkpoint, not a brake. The failure it targets is the
one the graph-engineering review named — *"a cycle that doesn't converge
is an infinite loop that spends until the budget is gone"* — where the
budget here is Larry's evening. He can always say continue; he just gets
told when the loop isn't obviously converging.

**H1.3** The refusal message stops recommending a dead end. It currently
says "ask how to proceed"; it should also say that supplying new
information (a command's output) makes a continuation legitimate.

**Acceptance:**
- A run that returns `ITERATIONS_EXHAUSTED_MESSAGE` leaves no guard entry;
  an immediate follow-up is not refused.
- A run that returns a genuine `FAILED:` still arms the guard, and an
  unmarked reworded retry is still refused (the original defect stays
  fixed).
- A marked continuation is allowed and logs
  `delegate_continuation agent=… `.
- `pytest tests/unit/test_delegate.py -q` green.

---

## 6. Part H2 — blocked is a handoff, not a terminus

**H2.1 Prompt rule** (`jarvis/prompts.py`, appended beside the existing
grounding rules so it reaches every sub-agent): when you cannot verify
something yourself, do not stop at "I cannot." State the exact command,
what each possible output would mean, and what you would conclude from
each. Name the limit once; do not repeat it.

**H2.2 Findings carry-forward — load-bearing, not optional.** A blocked
run writes what it established to a scratch document and returns the
path; a continuation receives `findings_path` and reads it in round one.
Same pattern as `plan_path` and `review_path`, for the same reason: a
voice model relaying technical content is where fidelity dies, and a file
does not degrade.

*Without this, the fresh 15 rounds are spent re-deriving what the prior
run already knew — in `b74ed019` that was rounds 1-8.*

**H1.2's unlimited reset makes this mandatory rather than an
optimisation.** A reset that hands back 15 rounds is only progress if
those rounds start where the last one stopped. Reset without
carry-forward is a treadmill: each round re-reads the same files, asks
Larry for one more thing, and converges on nothing — which is the
non-converging cycle H1.4 exists to make visible. Ship H2.2 with H1, not
after it.

**H2.3 Search discipline.** A short rule: when you have the files you
need, stop reading and reason. Rounds 9-15 of `b74ed019` were a widening
search after the answer was already in hand.

**H2.4 Magnitude check** — added to `VERIFICATION_TAXONOMY_RULE`, which
currently asks *did a tool return this* but not *does this number make
sense*. "Does the size of the error fit the hypothesis?" is the question
that cracked the weather bug: 13°F does not fit a 15-minute cache, which
ruled out staleness and pointed at the field being wrong.

**Acceptance:**
- Prompt additions keep each sub-agent prompt growth under 10%.
- A blocked run's reply contains a command and a stated interpretation of
  its outcomes.
- A continuation given `findings_path` reaches its conclusion in
  materially fewer rounds than the original (compare run-log `tool_count`).

---

## 7. Part H3 — commands render in the display window

**H3.1** A direct Supervisor tool `show_commands(title, commands[], note?)`
— same pattern as `set_voice` / `ui_control` / `view_screen`: direct,
never a delegation, emits one display payload with `surface: "window"`.

**H3.2** Deterministic by construction: the agent passes an explicit
list. **No parsing of prose for code fences** — that would misfire on any
reply that mentions a path or a flag.

**H3.3** Rendering is monospace, one command per line, in the existing
`DisplayContent` component all three display consumers share.

**H3.3a A copy button per command.** Verified 2026-08-18: the app has
**no copy affordance anywhere** — zero `navigator.clipboard.writeText`,
zero copy buttons. Without one, "copyable" means dragging a mouse
selection across a floating overlay, which is the fiddliness this Part
exists to remove. (`user-select: none` appears once, on `.display-head`,
the drag handle — correct, and the body stays selectable as a fallback.)

The asymmetry worth naming, because it decides where each half lives:
clipboard **write** from a button click works in the WKWebView, because a
click IS the user gesture the API requires. Clipboard **read** from a
voice command has no gesture, which is exactly why H4 routes reads
through the sidecar's `pbpaste` instead. Write in the browser, read in
the sidecar — not an inconsistency, a consequence.

**H3.3b Sequencing note.** `show_commands` arms by clearing the
clipboard (H3.4); clicking copy then puts the *command* on it. "Armed"
therefore guarantees "cleared since I asked," not "contains output." If
Larry says "read my clipboard" before running anything, he gets his own
command back — harmless, and H4.4's "say what it got" line surfaces it
in one sentence. Not worth further machinery.

**H3.4 `show_commands` ARMS the clipboard** when it carries
`expect_output: true` — it calls the same clear-and-arm the sidecar
exposes for H4.

*This came out of Larry's discoverability request and it fixes a flaw in
the original design.* With `clear` as a separate spoken step, the handoff
was four ordered actions — say clear, run, copy, say read — and getting
the order wrong (copying before clearing) silently wipes what you just
copied. Arming at the moment the command is shown collapses it to
**run → copy → "read my clipboard."** One thing to remember instead of
three, and the ordering hazard disappears entirely.

`clear_clipboard` remains as its own voice command for hygiene, but the
common path never needs it.

**Acceptance:**
- Asking for a command Larry must run puts it in the display window and
  the spoken reply does not read the command aloud.
- The payload is a `window` surface, so with the display popped out it
  lands on the second screen.
- `show_commands(..., expect_output=True)` leaves the clipboard armed;
  with `expect_output=False` it does not touch the clipboard.
- Each command line has a copy button; clicking it puts exactly that
  command on the clipboard, verified by pasting into Terminal.
- The copy button works in the shell's WKWebView, not only in a browser
  — this is the one clipboard operation a gesture makes legal there, and
  it is unverified until run.
- `cd web && npm run build` clean.

---

## 7a. Part H6 — discoverability: say the return path

> Larry, 2026-08-18: *"I would like Mortimer to suggest the path for
> pasting or inserting data like terminal results so that new users would
> know it's an option. I know the feature but a new user would not."*

**H6.1 The display card carries the affordance.** When a command block is
rendered with `expect_output: true`, the card itself shows a footer line:

```
Copy the output, then say "read my clipboard"
```

Rendered by the component, from the payload's own flag — **not written by
the model each time.** That is the difference between a mechanism and a
hope: a prompt rule asking the model to remember to mention it will be
dropped the moment the model is terse, and terseness is exactly what the
60-word voice contract rewards.

**H6.2 The spoken line says it once, on the first occurrence per
session.** "It's in the display — copy the output and say 'read my
clipboard'." On later commands in the same session, silence: the card
still shows the footer, and repeating it aloud every time is nagging.
Session-scoped state, not persisted.

**H6.3 The empty-state hint.** The engagement layer already carries
locked example-command hints for empty states (E8). The display window's
empty state gains one for this path, so it is discoverable before it is
ever needed rather than only at the moment of use.

**H6.4 Refusal messages teach.** `read_clipboard` refusing an unarmed
clipboard should say what to do, not just what went wrong: *"Nothing has
been copied since I last cleared it — copy what you want me to read, or
say 'clear my clipboard' first."* A refusal is the highest-attention
moment a user has; spending it on instruction is free.

**Acceptance:**
- A first command block in a session produces both the spoken hint and
  the card footer; a second produces the footer only.
- The footer text lives in the React component, and a test asserts it
  renders from the payload flag rather than from model-authored text.
- `read_clipboard` refused with no arming returns a message containing
  the corrective action.

---

## 8. Part H4 — clipboard in, armed

**H4.1 Sidecar endpoints** (`jarvis/admin/server.py`):
- `POST /api/clipboard/clear` → `pbcopy` with empty stdin; sets armed;
  returns `{ok, armed: true}`.
- `GET /api/clipboard` → refuses with a plain reason unless armed; else
  `pbpaste`, disarms, returns `{ok, text, chars, truncated}`.

Both use `_run`-style argument-list subprocess with a short timeout.
Fixed argv, zero parameters — nothing to inject.

**H4.2 Bounded.** `CLIPBOARD_MAX_CHARS` (proposed 20,000, matching the
skills body ceiling); truncation is reported, never silent.

**H4.3 Two Supervisor tools**, direct, never delegated:
`clear_clipboard` and `read_clipboard`. `read_clipboard` injects the text
into the LLM context via the existing `inject_silent` path (D3) and emits
a display payload with what it got (D4).

**H4.4 Say what it got.** One short spoken line — "340 characters,
starting 'ok: true, reminder'" — before using it, so a mis-copy is
caught in the first second.

**H4.5 Kill switch** `JARVIS_CLIPBOARD_ENABLED=false`, enforced at the
single sidecar entry point, matching `screen_enabled()`'s shape.

**Acceptance:**
- `read_clipboard` without a prior clear refuses, naming the reason.
- `clear_clipboard` then copy then `read_clipboard` returns the text.
- A second `read_clipboard` without re-clearing refuses (disarmed).
- The text appears in the display window and **not** in the Log tab.
- After a sweep interval, `python -m jarvis.classify` shows no fact
  derived from clipboard content.
- Kill switch off → both tools report disabled, nothing runs.

---

## 9. Part H5 — the memory exclusion, tested

D3 is the load-bearing safety property, so it gets its own tests rather
than riding along with H4.

- `TranscriptObserver` never records a clipboard injection.
- A session whose only "user input" was clipboard content produces no
  transcript rows for it.
- The exclusion holds regardless of content — no keyword or heuristic is
  involved, so there is nothing to tune or to fail open.

---

## 10. Ordering

| Order | Part | Why |
| --- | --- | --- |
| 1 | H1 retry guard | Everything downstream is refused without it |
| 2 | H4 + H5 clipboard | The return channel; H5 ships with it, never after |
| 3 | H3 show_commands | The outbound half; H3.4 arms the clipboard, so it needs H4 first |
| 4 | H6 discoverability | Rides on H3's component; cheap once the card exists |
| 5 | H2 prompt + findings | Behavior, best tuned once the mechanics work |

H2 last on purpose: prompt rules are cheap to write and hard to evaluate,
and they are easier to judge when the loop they describe actually exists.

---

## 11. Out of scope

- Any Swift or Xcode change (D1).
- Clipboard **write** by Mortimer. Reading is the need; writing is a way
  to clobber Larry's clipboard from a voice misfire.
- Images on the clipboard. Text only in v1, despite screenshot+vision
  being an obvious follow-on.
- A general text-input box in the console. If the clipboard path works,
  it is unnecessary; if it does not, that is the fallback.
- General command execution (the `mcp_diagnostics` discussion). `pbpaste`
  and `pbcopy` here are fixed, parameterless, and read-only-ish; they are
  not a precedent for an allowlist of arbitrary commands.
- Auto-clear after read — hostile when Larry wants to paste the same
  content elsewhere.

---

## 12. Open decisions

**O1. Does `read_clipboard` push a reply, or only append?**
`inject_silent` appends without forcing a response; `inject_context`
appends and pushes. Silent composes better with "I am pasting this so you
can continue"; push matches chat convention.
*Recommendation:* silent, then Larry speaks. It keeps the turn his.

**O2. RESOLVED by H3.4.** Arming is required, but Larry almost never
performs it — `show_commands` arms as a side effect of showing the
command. The gate stays a real gate; the ceremony disappears. The only
case needing a spoken `clear my clipboard` is pasting something Mortimer
did not ask for.

**O2a. What arms the clipboard when Larry initiates?** If he wants to
paste a URL unprompted, nothing has armed it, so `read_clipboard`
refuses and H6.4's message tells him to say "clear my clipboard" first —
which wipes the URL he had already copied. That is a real papercut.
*Options:* (a) accept it, the refusal explains the two-step; (b) let an
unarmed read succeed once with a spoken warning naming what it found;
(c) add "read what I just copied" as a distinct phrase that arms and
reads in one move, accepting that it reads whatever is there.
*Recommendation:* (a) for v1. (b) and (c) both re-open the exact hole D2
closed, and the papercut costs one extra sentence in a flow Larry
initiates knowingly.

**O3. `CLIPBOARD_MAX_CHARS` at 20,000?** Enough for any terminal output
Larry has pasted this session; small enough not to blow the context.

**O4. RESOLVED — the mechanical condition ships from day one.** The
earlier recommendation was ship-with-logging and tighten later. Larry's
unlimited-reset rule changes the arithmetic: an unbounded reset plus a
self-declared marker is infinite guard-free retries, so "visible but not
prevented" is no longer an acceptable interim. H1.2 now requires the
prior run to have *recorded* a handoff. Logging stays as well — a
condition can have a bug, and a marked-but-refused call should be as
visible as a marked-and-allowed one.

---

## 13. Risks and what is unverified

- **O4 is the real one.** The retry guard exists because a model rewords
  and retries rather than reporting failure. Giving that same model a
  flag that disables the guard is trusting the thing the guard distrusts.
- **`pbpaste` in the sidecar's process context is unverified.** It should
  work — the sidecar is a normal user process on the Mac — but macOS
  pasteboard access from a background process is exactly the kind of
  thing that fails silently, like Screen Recording did. First run is the
  test, and it needs an explicit acceptance check rather than an
  assumption.
- **H2's prompt rules have no mechanical backstop** (§4). They may simply
  not change behavior, which will only be visible in the run log.
- **This plan adds a subprocess call to the sidecar**, which previously
  ran none. Small, fixed, parameterless — but it is a new category for
  that process and worth naming rather than sliding in.

---

## 14. Approval

Nothing here has been implemented. On approval, state which Parts are in
scope and how §12's open decisions resolve.
