"""ui_control tool (MORTIMER_VOICE_UI_PLAN.md U1).

A Supervisor-only tool (not a sub-agent tool) for voice control of the
console's UI chrome: side drawer, tabs, transcript, display windows,
mic mute, wake word. Wired exactly like set_voice
(jarvis/bot/voice_switch.py's build_set_voice_tool is the template) —
a direct Supervisor action with no sub-agent involved.

The bot holds NO UI state (U1): it validates the command and emits one
app message; the browser — which owns the state — applies it through
the same setters the buttons use, so voice and click can never diverge.
"Already open" no-ops are detected client-side and come back as a
`ui/noop` message the bot speaks verbatim via TTSSpeakFrame
(pipeline.py), never through the LLM.

Feedback contract (U5, enforced by the prompt addendum in
jarvis/prompts.py): "ok" → the Supervisor says nothing; "ok-muted" →
one-phrase sign-off; an error sentence → relayed in one short sentence.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

UI_ACTIONS = frozenset({
    "drawer_open", "drawer_close", "drawer_tab",
    "transcript_open", "transcript_close",
    "display_popout", "display_close", "overlay_dismiss",
    "mic_mute", "wake_on", "wake_off",
})

UI_TABS = frozenset({
    "repo", "edit", "memory", "runs", "developer", "output", "transcript",
})

# Actions for which a tab argument is meaningful. drawer_tab REQUIRES it;
# drawer_open accepts it optionally.
_TAB_REQUIRED = frozenset({"drawer_tab"})
_TAB_ALLOWED = frozenset({"drawer_open", "drawer_tab"})

UI_CONTROL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "ui_control",
        "description": (
            "Control the console interface. Call when the user asks to "
            "open/close/show/hide a UI element by voice. Actions: "
            "drawer_open (optional tab) — the right-side tabbed panel "
            "holding Repo/Edit/Memory/Runs/Developer/Output/Transcript; "
            "users may call it the drawer, side panel, sidebar, or "
            "sidecar — drawer_close, drawer_tab (requires tab; the "
            "transcript tab is the conversation log), transcript_open, "
            "transcript_close (shortcuts for the log tab), display_popout "
            "(move informational content like weather or research to the "
            "SEPARATE pop-out display window — 'the big screen' / 'the "
            "other screen' / 'second monitor'; NOT the drawer), "
            "display_close (close that window / 'show it here'), "
            "overlay_dismiss (dismiss the on-stage content panel / "
            "'close that'), mic_mute (stop listening), wake_on, "
            "wake_off. When in doubt between the drawer and the display "
            "window, a bare 'open the sidecar/panel/drawer' means "
            "drawer_open. There is deliberately no mic_unmute: while "
            "muted the user cannot be heard, so the command could never "
            "arrive — unmuting is the wake word's or the mic button's job."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": sorted(UI_ACTIONS)},
                "tab": {
                    "type": "string",
                    "enum": sorted(UI_TABS),
                    "description": "Drawer tab, for drawer_open/drawer_tab",
                },
            },
            "required": ["action"],
        },
    },
}


def resolve_ui_command(arguments: dict) -> tuple[dict | None, str]:
    """Pure validation (unit-testable, no side effects).

    Returns (message, reply): `message` is the app message to send (or
    None when invalid), `reply` is the handler's return string per the
    U5 feedback contract.
    """
    action = str(arguments.get("action", "")).strip()
    tab = str(arguments.get("tab", "")).strip().lower()

    if action not in UI_ACTIONS:
        return None, (
            f"I can't do '{action}' — valid UI actions are: "
            f"{', '.join(sorted(UI_ACTIONS))}."
        )
    if action in _TAB_REQUIRED and not tab:
        return None, (
            "Which panel? The drawer tabs are: "
            f"{', '.join(sorted(UI_TABS))}."
        )
    if tab and action not in _TAB_ALLOWED:
        # A tab on a non-drawer action is ignored, not an error — the
        # intent is unambiguous without it.
        tab = ""
    if tab and tab not in UI_TABS:
        return None, (
            f"There's no '{tab}' panel — the drawer tabs are: "
            f"{', '.join(sorted(UI_TABS))}."
        )

    message: dict[str, Any] = {"type": "ui", "action": action}
    if tab:
        message["tab"] = tab
    reply = "ok-muted" if action == "mic_mute" else "ok"
    return message, reply


def build_ui_control_tool(
    send_message: Callable[[dict], Awaitable[None]],
) -> tuple[dict, Callable[[dict], Any]]:
    """Return (openai_tool_schema, async_handler) for ui_control.

    `send_message` receives the app message for the client (pipeline.py
    injects a transport-bound send_app_message closure, the same
    injection style set_voice uses for push_frame).
    """

    async def handler(arguments: dict) -> str:
        message, reply = resolve_ui_command(arguments)
        if message is None:
            return reply
        await send_message(message)
        return reply

    return UI_CONTROL_SCHEMA, handler
