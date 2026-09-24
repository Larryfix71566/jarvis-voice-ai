# Acceptance — handoff loop (MORTIMER_HANDOFF_LOOP_PLAN.md)

Manual checklist. Not run by pytest. Requires the shell, the bot, and the
admin sidecar; restart everything first:

```
./scripts/mortimer.sh stop
./scripts/mortimer.sh start
```

**Do not paste a shell comment (`#`) onto a command line.** zsh does not
treat it as a comment interactively and will try to glob the rest of the
line — that cost two broken handoffs on 2026-08-18.

## The loop, end to end

This is the whole feature; if this passes, the rest is detail.

- [ ] Ask Mortimer something it cannot verify itself, e.g. *"why is the
      weather chip showing the wrong temperature — check the live value."*
- [ ] The specialist's reply asks for something (`NEEDS-INPUT:` in the run
      log) rather than stopping at "I cannot".
- [ ] The command appears in the **display window**, not spoken aloud.
- [ ] Mortimer says the return path once: "run it, copy the output, then
      say 'read my clipboard'."
- [ ] Click the **copy** button on the command; paste into Terminal. The
      pasted text is exactly the command.
- [ ] Run it, select and copy the output.
- [ ] Say **"read my clipboard."** Mortimer says how many characters it
      got and the first few words.
- [ ] The output appears in the display window.
- [ ] It **does not** appear in the drawer's Log tab.
- [ ] Mortimer continues the investigation with the new data instead of
      starting over, and is not REFUSED.

## Arming (H4/D2)

- [ ] Copy something, then say "read my clipboard" **without** any command
      having been shown. It refuses and tells you what to do.
- [ ] Say "clear my clipboard", copy something, say "read my clipboard" —
      it works.
- [ ] Say "read my clipboard" again immediately. Refused: one read per arm.

Manual sidecar check of the same property:

```
curl -s localhost:7861/api/clipboard | python3 -m json.tool
curl -s -X POST localhost:7861/api/clipboard/clear | python3 -m json.tool
curl -s localhost:7861/api/clipboard | python3 -m json.tool
```

The first refuses (unarmed), the second arms, the third returns whatever
you copied in between.

## Memory exclusion (H5) — the load-bearing property

- [ ] After a clipboard read, wait past one memory sweep interval, then
      run `python -m jarvis.classify` and confirm **no fact derived from
      the clipboard content** exists.
- [ ] `sqlite3 data/jarvis.db "SELECT content FROM conversations ORDER BY id DESC LIMIT 10;"`
      shows no clipboard content.

If either fails, stop and say so — this is the property that keeps a
copied password out of long-term memory.

## Handoff depth (H1.4)

- [ ] Drive an investigation through four handoffs. On the fourth,
      Mortimer states what it has established, what it still does not
      know, and what information would settle it.
- [ ] Continue past four. It keeps going — the notice is guidance, not a
      cap. `grep delegate_continuation logs/bot.log` shows increasing
      `depth=`.

## Retry guard (H1.1/H1.2)

- [ ] `grep -E "delegate_retry_guard_refused|delegate_continuation" logs/bot.log`
      after a session: continuations are allowed, genuine reworded retries
      are still refused.
- [ ] `grep delegate_continuation_unearned logs/bot.log` should be empty.
      If it is not, the Supervisor is claiming continuations it did not
      earn — the flag is being guessed at rather than used, and the
      addendum wording needs sharpening.

## Kill switch

- [ ] `JARVIS_CLIPBOARD_ENABLED=false`, restart: "read my clipboard" says
      it is disabled, and `show_commands` still works.

## Known unverified

- **`pbpaste` from the sidecar's process context.** It should work — the
  sidecar is a normal user process — but macOS pasteboard access from a
  background process is exactly the category that fails *silently*, the
  way Screen Recording did. The first real run is the test. If
  `/api/clipboard` returns empty text when the clipboard plainly is not,
  that is this, not the arming.
- **The copy button inside the shell's WKWebView.** `navigator.clipboard.writeText`
  needs a user gesture; a click is one, so it should be legal there — but
  it has not been run. Text selection still works as a fallback.
