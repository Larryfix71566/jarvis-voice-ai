---
name: mcp-server-authoring
description: Build or extend an MCP skill server in this repository — the logic/server split, tool naming and descriptions, error messages an agent can act on, the draft-confirm gate for writes, the skill.yaml manifest, and the two config files that must both be edited before a new server is reachable. Use when adding a server under mcp_servers/ or adding a tool to an existing one.
metadata:
  source: authored 2026-08-18
  concept_from: anthropics/skills mcp-builder
  agent: developer
---

# Authoring an MCP skill server

## When this does not apply

This is about writing server code. Calling an existing tool, or asking
what a server does, needs none of it.

## The shape every server here follows

Two files, and the split is the testability seam:

- **`logic.py`** — pure and injectable. Network and database clients are
  passed in, never constructed inside. This is what unit tests exercise.
- **`server.py`** — FastMCP wiring only. Decorated functions that call
  into `logic` and return its result.

`mcp_servers/mcp_runlog/` is the smallest complete example; `mcp_repo` is
the one to copy for anything that writes.

## The entrypoint that has already cost a debugging session

`server.py` must end with:

```python
if __name__ == "__main__":
    mcp.run()
```

Omit it and the process imports cleanly, prints nothing, and exits 0
without ever starting the stdio transport. That surfaces at
`SkillRegistry.start()` as `mcp.shared.exceptions.McpError: Connection
closed` **on the next server in the list**, not on the broken one. The
tell is the missing startup banner in the failing server's own stderr —
not the stack frame, which points somewhere else entirely.

## Two config files, both required

A server that exists but is not registered is invisible; a server that is
registered but not routed reaches no agent.

1. `config/mcp_servers.yaml` — how to spawn it.
2. `config/agents.yaml` — which sub-agents may call it.

**Leave `env: {}` unless a variable is guaranteed present.** `expand_env_vars`
leaves an unknown `${VAR}` as literal text, so an optional variable hands
the child process the literal string `"${VAR}"`. That once gave `mcp-repo`
a phantom repo root and made every read report "does not exist". The child
inherits the full parent environment anyway — an explicit list buys
nothing and can actively lie.

## The manifest

Every server carries `skill.yaml`, kept in sync with the real tool list —
`scripts/check_skills.py` fails CI if it drifts:

```yaml
name: mcp-example
version: 0.1.0
class: standard          # `privileged` only if it changes something
tools: [example_read, example_write]
requires_env: []
requires_keychain: []
scopes: []
test: "python3 -m pytest tests/unit/test_mcp_example_logic.py -q"
```

Claim `standard` for a read-only server and leave the three requirement
lists empty — an overstated manifest is a false claim about what the
server needs.

## Tool descriptions are the routing signal

Tool selection happens off the schema text, not off `config/agents.yaml`
alone. So the description must disambiguate against every other tool the
same agent can see. `mcp_repo` and `mcp_apps` both touch files, and each
description opens by saying which world it is in — "Local working tree on
this machine:" versus "GitHub:" — because without that the model picks by
vibe.

- Consistent prefixes, action-oriented: `repo_read_file`, `runlog_list`.
- State the bound in the description when there is one ("LIMIT capped at
  50"), so the model does not ask for 5,000 and get a surprise.
- Return bounded previews, never a raw payload. `runlog_detail` returns
  the JSONL `payload_path` for a human to open rather than dumping the
  file through a tool result.

## Errors must tell the agent what to do

A tool result is read by a model that will otherwise invent an
explanation. Name what failed and what would fix it. "Authentication
failed (401) — the GitHub token is missing or expired" is actionable;
"request failed" invites a guess, and the guess becomes what the user
hears.

Results must also classify correctly under `jarvis/toolresult.py`'s
`classify_tool_result`, which is the single shared judge of whether a
call succeeded. It reads a transport-level failure prefix, then a JSON
body with `ok: false` or a non-empty `error` key. So: return
`{"error": "..."}` on failure and plain data on success. **Never add a
second success heuristic anywhere in the tool path** — a transport-level
`ok=1` alongside a body saying `{"error": ...}` is exactly what let a 401
reach a user as "the sidecar may be offline".

## Writes are two-phase, always

Any tool that changes something drafts first and executes only on a
separate confirmed call, through the `actions` table `mcp_git` and
`mcp_repo` both use. The draft returns a summary and `pending: true`; a
later call with the `action_id` performs the write. Never invent an
`action_id`; if a draft is missing, used, or expired, prepare it again.

Path-confined servers keep two separate deny lists — one for reading, one
for writing. Something being readable does not make it writable.

## Before it is finished

- `python -c "import mcp_servers.mcp_example.server"` — import smoke.
- `python3 -m pytest tests/unit/test_mcp_example_logic.py -q`.
- `python scripts/check_skills.py` — manifest matches the server.
- `tests/integration/test_registry.py` counts total tools; adding tools
  changes `TOTAL_TOOLS` and that test will fail until it is updated.

## If you cannot read the existing servers

If the repository tools are unavailable, say so and stop. Do not write a
server from the general MCP pattern — the conventions above are what make
one belong in this codebase, and a server that ignores them imports fine
and fails in ways that point at other files.
