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

import os

from typing import Any, Awaitable, Callable

def ui_control_enabled() -> bool:
    """JARVIS_UI_CONTROL_ENABLED: on unless false/0/no. Extracted verbatim
    from build_pipeline's inline check (status spec T2.3) so the pipeline's
    registration site and jarvis.status.overview read ONE rule (R8)."""
    return os.environ.get(
        "JARVIS_UI_CONTROL_ENABLED", ""
    ).strip().lower() not in ("false", "0", "no")


UI_ACTIONS = frozenset({
    "drawer_open", "drawer_close", "drawer_tab",
    "drawer_popout", "drawer_popin",
    "transcript_open", "transcript_close",
    "display_popout", "display_close", "overlay_dismiss",
    "mic_mute", "wake_on", "wake_off",
    # WS-15 (Larry, 2026-09-29: "the map should be zoomable by voice"):
    # the weather card's map. The app applies these to the card on screen
    # and ignores them when none is showing.
    "map_zoom_in", "map_zoom_out", "map_reset",
    "radar_pause", "radar_play", "map_satellite", "map_standard",
    # Larry, 2026-09-30: "zoom to 10 miles" and "center the map on Atlanta".
    # map_zoom_to needs `miles` (the map's width, edge to edge); map_center
    # needs `place`, which the app finds with Apple Maps search.
    "map_zoom_to", "map_center",
})
MAP_MILES_MIN, MAP_MILES_MAX = 0.5, 3000.0
MAP_PLACE_MAX_LEN = 80

UI_TABS = frozenset({
    "repo", "edit", "memory", "runs", "agents", "output", "transcript",
    "costs",
})

# Actions for which a tab argument is meaningful. drawer_tab REQUIRES it;
# drawer_open accepts it optionally.
# Larry 2026-08-18: the Developer tab became Agents (all five sub-agents
# render there now, not just self-edit runs). Old phrasing still works —
# an alias costs nothing and "show me the developer tab" is muscle
# memory. Aliases are resolved BEFORE validation, so UI_TABS stays the
# single list of real tab keys.
TAB_ALIASES = {"developer": "agents", "dev": "agents", "agent": "agents"}

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
            "holding Repo/Edit/Memory/Runs/Developer/Output/Transcript/"
            "Costs; "
            "users may call it the drawer, side panel, sidebar, or "
            "sidecar — drawer_close, drawer_tab (requires tab; the "
            "transcript tab is the conversation log), drawer_popout (send "
            "the drawer/panels themselves to a separate second-screen "
            "window — 'put the panels on the other screen' / 'pop out "
            "the drawer'), drawer_popin (bring the popped-out drawer back "
            "in-page — 'bring the panels back' / 'show the drawer here "
            "again'), transcript_open, "
            "transcript_close (shortcuts for the log tab), display_popout "
            "(move informational content like weather or research to the "
            "SEPARATE pop-out display window — 'the big screen' / 'the "
            "other screen' / 'second monitor'; NOT the drawer), "
            "display_close (close that window / 'show it here'), "
            "overlay_dismiss (dismiss the on-stage content panel / "
            "'close that'), mic_mute (stop listening), wake_on, "
            "wake_off. Weather map (the weather card on screen): "
            "map_zoom_in ('zoom in' / 'closer'), map_zoom_out ('zoom out' / "
            "'show more'), map_reset ('reset the map' / 'back to my "
            "location'), radar_pause and radar_play (the radar loop), "
            "map_satellite and map_standard (satellite or plain map), map_zoom_to "
            "with miles ('zoom to 10 miles' = the map 10 miles wide), map_center "
            "with place ('center on Atlanta' / 'show Truist Park'; the app finds "
            "it and may take miles too). "
            "When in doubt between the drawer and the display "
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
                "miles": {
                    "type": "number",
                    "description": "map_zoom_to (required) or map_center (optional): "
                                   "how many miles wide the map should be, edge to edge",
                },
                "place": {
                    "type": "string",
                    "description": "map_center: the place or landmark to center on, "
                                   "as the user said it (e.g. 'Truist Park, Atlanta')",
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
    tab = TAB_ALIASES.get(tab, tab)

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
    if action in ("map_zoom_to", "map_center"):
        miles = arguments.get("miles")
        if miles is not None and miles != "":
            try:
                miles = float(miles)
            except (TypeError, ValueError):
                return None, "How many miles wide should the map be?"
            if not MAP_MILES_MIN <= miles <= MAP_MILES_MAX:
                return None, (f"The map can show between {MAP_MILES_MIN:g} and "
                              f"{MAP_MILES_MAX:g} miles across.")
            message["miles"] = miles
        elif action == "map_zoom_to":
            return None, "How many miles wide should the map be?"
        if action == "map_center":
            place = " ".join(str(arguments.get("place") or "").split())[:MAP_PLACE_MAX_LEN]
            if not place:
                return None, "Which place should the map center on?"
            message["place"] = place
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
