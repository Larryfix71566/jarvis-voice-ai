"""Jarvis text REPL (plan Phase 2, step 2.4).

Run from the repo root:  python -m jarvis.cli
Commands: /tools, /reset, /quit
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid

from jarvis.agents.supervisor import Orchestrator
from jarvis.config import load_settings
from jarvis.logging_config import setup_logging
from jarvis.skills.registry import REPO_ROOT, SkillRegistry

BANNER = "JARVIS text interface — commands: /tools, /reset, /quit"
GRAY = "\033[90m"
RESET = "\033[0m"


def bridge_settings_to_env(settings) -> None:
    """MCP children read config from the process environment (plan §6.3);
    bridge Settings values so stdio servers inherit them."""
    os.environ.setdefault("JARVIS_DB_PATH", settings.jarvis_db_path)
    os.environ.setdefault("JARVIS_TIMEZONE", settings.jarvis_timezone)
    if settings.tavily_api_key:
        os.environ.setdefault("TAVILY_API_KEY", settings.tavily_api_key)


async def main() -> None:
    settings = load_settings()
    setup_logging(settings.jarvis_log_level)
    bridge_settings_to_env(settings)

    registry = SkillRegistry(REPO_ROOT / "config" / "mcp_servers.yaml")
    print("Starting skill servers…")
    await registry.start()
    orchestrator = Orchestrator(settings, registry, session_id=str(uuid.uuid4()))
    print(BANNER)

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
            start = time.perf_counter()
            reply = await orchestrator.chat(line)
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            print(f"Jarvis: {reply}")
            print(f"{GRAY}[{elapsed_ms}ms]{RESET}")
    finally:
        await registry.stop()


if __name__ == "__main__":
    asyncio.run(main())
