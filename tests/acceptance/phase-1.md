# Phase 1 Acceptance Checklist — MCP Skill Servers

Gate: all automated tests green + coverage ≥90% per logic.py + this checklist ticked.

## Automated
- [x] `pytest tests/unit -q` — all green
- [x] `pytest tests/unit -q --cov=mcp_servers --cov-report=term-missing` — ≥90% on every `logic.py`
- [x] `pytest tests/integration -q` — all green (stdio spawn, exact tool sets, happy-path calls)

## Manual (requires a human + browser — DEFERRED)
- [ ] `mcp dev mcp_servers/mcp_notes/server.py` opens the MCP Inspector; `create_note` then `search_notes` called from the UI return sane results

> The Inspector step requires an interactive browser session and is deferred to
> the human gate review. All server behavior it would exercise is covered by
> `tests/integration/test_mcp_servers.py` over real stdio connections.
