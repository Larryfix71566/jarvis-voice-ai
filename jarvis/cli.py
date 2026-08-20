"""Jarvis text REPL (plan Phase 2 step 2.4, Phase 3 step 3.3, Phase 5 step 5.5).

Run from the repo root:  python -m jarvis.cli
Commands: /tools, /reset, /voice [id], /quit
Runs the Supervisor in delegating mode; sub-agent activity is printed as
"[Scheduler] calling set_reminder…" lines (plan step 3.1).
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid

from jarvis.agents.supervisor import Orchestrator
from jarvis.config import bridge_settings_to_env, load_settings
from jarvis.logging_config import setup_logging
from jarvis.skills.registry import REPO_ROOT, SkillRegistry

BANNER = "{name} text interface — commands: /tools, /reset, /quit"
GRAY = "\033[90m"
RESET = "\033[0m"


# E1 — the implementation moved to jarvis/config.py, beside load_settings
# and expand_env_vars, and SkillRegistry.start() now calls it itself. Kept as
# a re-export because pipeline.py and two tests import it from here; the
# import above IS the definition.
__all__ = ["bridge_settings_to_env"]


async def main() -> None:
    settings = load_settings()
    setup_logging(settings.jarvis_log_level)
    bridge_settings_to_env(settings)

    registry = SkillRegistry(REPO_ROOT / "config" / "mcp_servers.yaml")
    print("Starting skill servers…")
    await registry.start()

    def on_event(event: dict) -> None:
        if event.get("type") == "agent_tool":
            print(f"{GRAY}[{event['display_name']}] calling "
                  f"{event['tool']}…{RESET}")

    orchestrator = Orchestrator(
        settings, registry, session_id=str(uuid.uuid4()), on_event=on_event
    )
    print(BANNER.format(name=settings.jarvis_name.upper()))

    try:
        while True:
            try:
                line = input("you> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not line:
                continue
            if line == "/quit":
                break
            if line == "/reset":
                orchestrator.reset(str(uuid.uuid4()))
                print("session reset.")
                continue
            if line == "/tools":
                for server in registry.server_names:
                    print(f"{server}:")
                    for tool in registry.tools_for([server]):
                        print(f"  - {tool}")
                continue
            if line.startswith("/voice"):
                # Phase 5 step 5.5: CLI confirms resolution logic only
                # (no audio in the terminal).
                from jarvis.bot.voice_switch import (
                    available_list,
                    catalog_summary,
                    load_voice_catalog,
                    resolve_voice,
                )
                catalog = load_voice_catalog()
                parts = line.split(maxsplit=1)
                if len(parts) == 1:
                    print(catalog_summary(catalog))
                    print(f"current default: {catalog['default']}")
                else:
                    voice = resolve_voice(parts[1], catalog)
                    if voice is None:
                        print(f"I don't have a voice called '{parts[1]}'. "
                              f"Available: {available_list(catalog)}.")
                    else:
                        print(f"Voice switched to {voice['label']}. "
                              f"(applies in the browser client)")
                continue
            start = time.perf_counter()
            reply = await orchestrator.chat(line)
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            print(f"{settings.jarvis_name}: {reply}")
            print(f"{GRAY}[{elapsed_ms}ms]{RESET}")
    finally:
        await registry.stop()


if __name__ == "__main__":
    asyncio.run(main())
