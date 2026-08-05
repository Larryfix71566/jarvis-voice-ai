"""set_voice tool + app-message voice path (plan Phase 5, steps 5.3-5.4).

Resolution is pure and testable; side effects (pushing a
TTSUpdateSettingsFrame into the pipeline) are injected by the caller so the
CLI can reuse resolution without a pipeline.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Awaitable, Callable

import yaml

from pipecat.frames.frames import TTSUpdateSettingsFrame

from jarvis.prompts import render_voice_catalog

VOICES_PATH = Path(__file__).resolve().parents[2] / "config" / "voices.yaml"

SET_VOICE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "set_voice",
        "description": (
            "Switch the speaking voice. Call when the user asks to change "
            "or select a voice."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "voice": {
                    "type": "string",
                    "description": "Voice id or label from the catalog",
                },
            },
            "required": ["voice"],
        },
    },
}


def load_voice_catalog(path: str | Path | None = None) -> dict:
    data = yaml.safe_load(Path(path or VOICES_PATH).read_text(encoding="utf-8"))
    return {"default": data["default"], "voices": data["voices"]}


def resolve_voice(query: str, catalog: dict) -> dict | None:
    """id exact, else case-insensitive label substring. None if no match."""
    q = query.strip().lower()
    if not q:
        return None
    for v in catalog["voices"]:
        if v["id"].lower() == q:
            return v
    for v in catalog["voices"]:
        if q in v["label"].lower():
            return v
    return None


def available_list(catalog: dict) -> str:
    return ", ".join(v["id"] for v in catalog["voices"])


def catalog_summary(catalog: dict) -> str:
    return render_voice_catalog(catalog["voices"])


def build_set_voice_tool(
    push_frame: Callable[[Any], Awaitable[None]],
    catalog: dict | None = None,
) -> tuple[dict, Callable[[dict], Any]]:
    """Return (openai_tool_schema, async_handler) for set_voice.

    push_frame receives a TTSUpdateSettingsFrame with the new voice (Phase 5
    wiring). The handler returns the confirmation sentence, which the
    Supervisor then speaks in the new voice.
    """
    catalog = catalog or load_voice_catalog()

    async def handler(arguments: dict) -> str:
        query = str(arguments.get("voice", ""))
        voice = resolve_voice(query, catalog)
        if voice is None:
            return (f"I don't have a voice called '{query}'. "
                    f"Available: {available_list(catalog)}.")
        await push_frame(TTSUpdateSettingsFrame(
            settings={"voice": voice["elevenlabs_voice_id"]}))
        return f"Voice switched to {voice['label']}."

    return SET_VOICE_SCHEMA, handler
