"""Handoff tools — MORTIMER_HANDOFF_LOOP_PLAN.md H3/H4/H6.

Three DIRECT Supervisor tools, same pattern as `set_voice`, `ui_control`
and `view_screen`: registered on the Supervisor itself, never delegated,
each with an injected side effect so the bot holds no state of its own.

    show_commands    put commands Larry must run in the DISPLAY window
                     rather than in spoken/dialog text, and arm the
                     clipboard for the output they will produce
    clear_clipboard  wipe + arm, on request
    read_clipboard   read what was copied, ONLY if armed

Why these three are one module: they are one loop. Mortimer shows a
command, Larry runs it and copies the output, Mortimer reads it back and
continues. Splitting them across files would hide that the arming in
`show_commands` and the refusal in `read_clipboard` are the same
mechanism seen from two ends.

**H5, the load-bearing safety property.** Clipboard text is injected into
the LLM context through `inject_silent`, which appends to the live
context WITHOUT it becoming a transcript entry. `MemoryWatcher`
periodically folds the transcript into long-term memory via an LLM
extraction call, so anything in the transcript can become a durable
SQLite fact — a password copied thirty seconds earlier included. Keeping
clipboard content out of the transcript is what prevents that, and it is
structural: the injection path is simply not the speech path.

What Larry sees instead is the display window (H3/D4), which is
ephemeral. Everything that must be visible but must not be remembered
goes there.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

# H4.4 — how much of the text to read back aloud so a mis-copy is caught
# in the first second. Short: this is spoken, and the full content is on
# screen.
PREVIEW_CHARS = 60

MAX_COMMANDS = 10

SHOW_COMMANDS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "show_commands",
        "description": (
            "Put one or more commands the USER must run themselves into the "
            "display window, where they can be read and copied. Use this "
            "instead of speaking a command aloud — a spoken command cannot "
            "be copied. Set expect_output true when you need what the "
            "command prints; that arms the clipboard so the user can copy "
            "the output and say 'read my clipboard'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Short heading, e.g. 'Check the live weather payload'.",
                },
                "commands": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "The commands, one per entry, exactly as typed. No "
                        "surrounding prose, no shell comments — zsh does not "
                        "treat # as a comment interactively and will try to "
                        "glob the rest of the line."
                    ),
                },
                "note": {
                    "type": "string",
                    "description": "Optional one-line explanation of what to look for.",
                },
                "expect_output": {
                    "type": "boolean",
                    "description": "True when you need the command's output back.",
                },
            },
            "required": ["title", "commands"],
        },
    },
}

CLEAR_CLIPBOARD_SCHEMA = {
    "type": "function",
    "function": {
        "name": "clear_clipboard",
        "description": (
            "Wipe the user's clipboard and arm it, so the next thing they "
            "copy is the only thing you can read. Use when the user wants to "
            "paste you something you did not ask for. Commands shown with "
            "show_commands arm it already — do not call this as well."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}

READ_CLIPBOARD_SCHEMA = {
    "type": "function",
    "function": {
        "name": "read_clipboard",
        "description": (
            "Read what the user copied, so you can continue with data only "
            "they could get — command output, a URL, an error message. Only "
            "works after the clipboard was armed (by show_commands or "
            "clear_clipboard); this refuses otherwise, which is deliberate."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}


def build_show_commands_tool(
    emit_display: Callable[[dict], None],
    arm_clipboard: Callable[[], dict],
    *,
    hint_state: dict | None = None,
) -> tuple[dict, Callable[[dict], Any]]:
    """H3 — commands go to the display window, never to spoken text.

    `hint_state` is session-scoped (H6.2): the return path is said aloud
    once per session, because the card carries it every time and
    repeating it turns a helpful pointer into nagging.
    """
    state = hint_state if hint_state is not None else {}

    async def handler(arguments: dict) -> str:
        title = str(arguments.get("title", "")).strip() or "Run this"
        raw = arguments.get("commands") or []
        if isinstance(raw, str):          # tolerate a single string
            raw = [raw]
        commands = [str(c).strip() for c in raw if str(c).strip()][:MAX_COMMANDS]
        if not commands:
            return "I had no command to show."
        note = str(arguments.get("note", "")).strip()
        expect_output = bool(arguments.get("expect_output"))

        # H3.4 — arm here, so Larry never has to. With `clear` as a
        # separate spoken step the handoff was four ordered actions and
        # copying before clearing silently wiped the copy; arming at the
        # moment the command is shown collapses it to run → copy → read.
        armed = False
        if expect_output:
            try:
                armed = bool((await asyncio.to_thread(arm_clipboard)).get("ok"))
            except Exception:  # noqa: BLE001 — showing the command still helps
                logger.exception("show_commands_arm_failed")
            if not armed:
                logger.warning("show_commands_not_armed title=%s", title)

        emit_display({
            "type": "display",
            "surface": "window",
            "tool": "show_commands",
            "title": title,
            "commands": commands,
            "note": note,
            # H6.1 — the card renders its own footer from this flag. The
            # affordance must not depend on the model remembering to
            # mention it: the 60-word voice contract rewards terseness,
            # and terseness drops exactly this kind of sentence.
            "expect_output": expect_output and armed,
        })
        logger.info("show_commands title=%s count=%d expect_output=%s armed=%s",
                    title, len(commands), expect_output, armed)

        if not expect_output:
            return "Shown in the display window."
        if not armed:
            return (
                "Shown in the display window. I could not arm the clipboard, "
                "so say 'clear my clipboard' before copying the output."
            )
        # H6.2 — spoken once per session; the card says it every time.
        if not state.get("said_return_path"):
            state["said_return_path"] = True
            return (
                "It's in the display window. Run it, copy the output, then "
                "say 'read my clipboard'."
            )
        return "It's in the display window — copy the output when you have it."

    return SHOW_COMMANDS_SCHEMA, handler


def build_clear_clipboard_tool(
    clear: Callable[[], dict],
) -> tuple[dict, Callable[[dict], Any]]:
    async def handler(arguments: dict) -> str:
        result = await asyncio.to_thread(clear)
        if not result.get("ok"):
            return str(result.get("error") or "I couldn't clear the clipboard.")
        return "Clipboard cleared. Copy what you'd like me to read."

    return CLEAR_CLIPBOARD_SCHEMA, handler


def build_read_clipboard_tool(
    read: Callable[[], dict],
    inject: Callable[[str], Awaitable[None]],
    emit_display: Callable[[dict], None],
) -> tuple[dict, Callable[[dict], Any]]:
    """H4/H5 — read, show, inject; never transcribe, never remember.

    `inject` must be the SILENT context append. Using the speech path
    would put clipboard content in the transcript, which the memory sweep
    reads — see the module docstring.
    """

    async def handler(arguments: dict) -> str:
        result = await asyncio.to_thread(read)
        if not result.get("ok"):
            return str(result.get("error") or "I couldn't read the clipboard.")
        text = str(result.get("text") or "")
        if result.get("empty"):
            return "The clipboard is empty — copy the text you want me to read."

        # D4 — visible in the display (ephemeral), not in the Log tab
        # (persisted, and swept into memory).
        emit_display({
            "type": "display",
            "surface": "window",
            "tool": "read_clipboard",
            "title": "Read from your clipboard",
            "content": text,
            "chars": result.get("chars"),
            "truncated": bool(result.get("truncated")),
        })

        await inject(
            "The user pasted this from their clipboard — use it to continue:\n\n"
            + text
        )

        # H4.4 — say what it got, so a mis-copy is obvious immediately.
        preview = " ".join(text.split())[:PREVIEW_CHARS]
        suffix = " (truncated)" if result.get("truncated") else ""
        return f"Got {result.get('chars')} characters{suffix}, starting: {preview}"

    return READ_CLIPBOARD_SCHEMA, handler
