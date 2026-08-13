#!/usr/bin/env python3
"""Context growth probe (plan Phase 6, step 6a — measure first).

Reconstructs the growing LLM context turn-by-turn for a real conversation
session pulled from the `conversations` table, and reports cumulative
token counts. This is the "instrument token counts per turn, hold a
conversation, record the curve" step the plan requires before any
compression code may be written — the answer determines whether Phase 6b+
is needed at all.

Token counts use tiktoken's cl100k_base encoding as an approximation.
Mortimer's configured model is Claude (via the Anthropic OpenAI-compat
endpoint) by default, not a tiktoken-tokenized OpenAI model, so these are
estimates, not exact Anthropic token counts — cl100k_base is close enough
for a growth *trend*, which is what 6a needs, not an exact context-window
budget.

Usage:
    python3 scripts/context_growth_probe.py [session_id]
    python3 scripts/context_growth_probe.py --list          # show sessions
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from jarvis.db import get_conn  # noqa: E402
from jarvis.prompts import (  # noqa: E402
    SUPERVISOR_PROMPT,
    VOICE_ADDENDUM,
    render_agent_catalog,
)


class _CharApproxEncoder:
    """Fallback when tiktoken's encoding file can't be fetched (e.g. no
    network egress to openaipublic.blob.core.windows.net, as in this
    sandbox). ~4 chars/token is the standard rough heuristic for English
    prose — cruder than a real tokenizer, but adequate for a growth
    *trend*, which is what 6a needs. Flagged clearly wherever it's used."""

    def encode(self, text: str) -> list[int]:
        return [0] * max(1, (len(text) + 3) // 4)


def _encoder():
    try:
        import tiktoken

        return tiktoken.get_encoding("cl100k_base"), "tiktoken/cl100k_base"
    except Exception:
        return _CharApproxEncoder(), "char-approx (~4 chars/token, tiktoken unavailable)"


def _approx_system_prompt() -> str:
    """Rendered system prompt with realistic placeholder sizes — not the
    exact live prompt (memory_context/voice_catalog vary per install), but
    representative of its typical size for a single-user deployment."""
    agent_catalog = render_agent_catalog([
        {"name": "scheduler", "display_name": "Scheduler",
         "description": "Time, dates, day-of-week and calendar questions "
         "in the user's timezone; reminders, alarms, scheduling and planning."},
        {"name": "librarian", "display_name": "Librarian",
         "description": "Long-term memory: store and recall facts, notes, preferences."},
        {"name": "analyst", "display_name": "Analyst",
         "description": "Web research, current events, sports results, "
         "weather, the time in other cities, and general lookups."},
        {"name": "systems", "display_name": "Systems",
         "description": "Local machine status: CPU, memory, disk, battery, uptime."},
        {"name": "developer", "display_name": "Developer",
         "description": "The Jarvis git repository and app/self-development."},
    ])
    voice_catalog = "- rachel: Rachel (warm, conversational)\n- adam: Adam (deep, confident)"
    memory_context = (
        "- user.name: Larry\n- user.style.brevity: prefers short answers\n"
        "Previously discussed: reviewed the Mortimer upgrade plan phases."
    )
    return (
        SUPERVISOR_PROMPT.format(
            jarvis_name="Mortimer", user_name="Boss", timezone="America/New_York",
            agent_catalog=agent_catalog, voice_catalog=voice_catalog,
            memory_context=memory_context,
        )
        + "\n" + VOICE_ADDENDUM
    )


def measure_session(session_id: str, db_path: str | None = None) -> list[dict]:
    """Cumulative token count after each turn, system prompt included."""
    enc, method = _encoder()
    if not hasattr(measure_session, "_reported_method"):
        print(f"[token counting method: {method}]\n", file=sys.stderr)
        measure_session._reported_method = True
    system_prompt = _approx_system_prompt()
    system_tokens = len(enc.encode(system_prompt))

    with get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT role, content, created_at FROM conversations "
            "WHERE session_id = ? ORDER BY id",
            (session_id,),
        ).fetchall()

    curve = []
    running_tokens = system_tokens
    for i, row in enumerate(rows, start=1):
        turn_tokens = len(enc.encode(row["content"]))
        running_tokens += turn_tokens
        curve.append({
            "turn": i,
            "role": row["role"],
            "turn_tokens": turn_tokens,
            "cumulative_tokens": running_tokens,
            "content_preview": row["content"][:60],
        })
    return curve


def list_sessions(db_path: str | None = None) -> list[dict]:
    with get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT session_id, COUNT(*) AS n, MIN(created_at) AS start, "
            "MAX(created_at) AS end FROM conversations "
            "GROUP BY session_id ORDER BY n DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def render_table(curve: list[dict]) -> str:
    lines = [f"{'turn':>4} {'role':<10} {'turn_tok':>9} {'cumulative':>11}  preview"]
    for row in curve:
        lines.append(
            f"{row['turn']:>4} {row['role']:<10} {row['turn_tokens']:>9} "
            f"{row['cumulative_tokens']:>11}  {row['content_preview']}"
        )
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    if len(argv) > 1 and argv[1] == "--list":
        for s in list_sessions():
            print(f"{s['session_id']}  turns={s['n']:>3}  {s['start']} .. {s['end']}")
        return 0

    if len(argv) > 1:
        session_id = argv[1]
    else:
        sessions = list_sessions()
        if not sessions:
            print("No conversation sessions found in the database.")
            return 1
        session_id = sessions[0]["session_id"]
        print(f"(no session_id given — using the largest: {session_id}, "
              f"{sessions[0]['n']} rows)\n")

    curve = measure_session(session_id)
    if not curve:
        print(f"No conversation rows for session {session_id}.")
        return 1

    print(render_table(curve))
    print()
    print(f"System prompt: {curve[0]['cumulative_tokens'] - curve[0]['turn_tokens']} tokens")
    print(f"Final cumulative context: {curve[-1]['cumulative_tokens']} tokens "
          f"over {len(curve)} messages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
