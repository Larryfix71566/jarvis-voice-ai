# mortimer-vault

Curated memory vault for Mortimer/Jarvis: canonical Markdown files with YAML
frontmatter, git-versioned, with a disposable SQLite/FTS5 derived index and a
localhost HTTP service exposing memory operations as tools for the
supervisor. Obsidian-compatible by construction — no plugin required.

Bundled in the Mortimer repository under `services/mortimer-vault`.
This is the knowledge-base service, separate from `jarvis/vault.py`, which
stores encrypted API credentials. Embeddings, authentication, remote Git,
multi-user support and the digester are outside this package's scope.

## Install

```bash
# From the root of the Mortimer repository:
bash scripts/setup_kb.sh
```

Creates a package-local `.venv` and installs the service and test dependencies.
Set `MORTIMER_KB_PYTHON` to select a Python executable (default: `python3.12`).
Requires Python 3.12+ and a `git` binary on `PATH`. SQLite must be built
with FTS5 (standard on most distributions; the service raises a clear error
at startup if it's missing).

## Quickstart

```bash
export MORTIMER_HOME=~/Mortimer      # optional; this is the existing default
services/mortimer-vault/.venv/bin/mortimer-vault init  # new data directories only
bash scripts/run_kb.sh              # runs on 127.0.0.1:8484
```

Existing installations keep their documents at the same `MORTIMER_HOME`;
no import or data migration is needed. Stop the old service before launching
the repository copy, because both use port 8484. `MORTIMER_VAULT_DIR` can
still explicitly select an external package during the transition.

For development, set `MORTIMER_HOME` to a disposable directory such as
`$PWD/.sandbox-data/knowledge-base`; never point a development instance at
your live documents. The setup script does not create or migrate data.
Private documents, credentials, virtual environments and indexes are not
part of the source package.

## Tests

From the repository root:

```bash
services/mortimer-vault/.venv/bin/python -m pytest services/mortimer-vault/tests -q
```

Tests use temporary knowledge directories and synthetic documents; no API
keys or running production service are required. The Knowledge base GitHub
workflow runs the suite independently of the main application's checks.

## CLI

| Command | Purpose |
|---|---|
| `mortimer-vault init` | Create the vault layout, git repo, and default `retrieval.yaml`. |
| `mortimer-vault serve` | Run the HTTP service + file watcher on `127.0.0.1:8484`. |
| `mortimer-vault reindex [--full]` | Rebuild the derived index (incremental by default). |
| `mortimer-vault import <dir>` | One-time backfill of legacy `.md` files into `areas/`. |
| `mortimer-vault check` | Strict frontmatter validation of every vault file; nonzero exit on failure. |
| `mortimer-vault search "<query>"` | Debug wrapper over `/search`. |

## HTTP API

Base URL: `http://127.0.0.1:8484`. No auth — localhost, single-user only.

### `POST /read`

```bash
curl -s -X POST http://127.0.0.1:8484/read \
  -H 'Content-Type: application/json' \
  -d '{"id": "window-architecture"}'
```

### `POST /write`

```bash
curl -s -X POST http://127.0.0.1:8484/write \
  -H 'Content-Type: application/json' \
  -d '{
    "type": "area",
    "id": "window-architecture",
    "body": "Command Center ships first; Constellation is additive.",
    "tags": ["architecture"],
    "confidence": "high",
    "source_sessions": []
  }'
```

To update an existing file, include `expected_hash` (from a prior `/read` or
`/write` response) and, if the file's `type` is `decision`,
`previous_excerpt` containing a verbatim substring of its current body:

```bash
curl -s -X POST http://127.0.0.1:8484/write \
  -H 'Content-Type: application/json' \
  -d '{
    "type": "area",
    "id": "window-architecture",
    "expected_hash": "<hash from /read>",
    "body": "Command Center ships first; Constellation is additive. See [[ai-assistant-app]].",
    "tags": ["architecture"],
    "confidence": "high",
    "source_sessions": []
  }'
```

### `POST /delete`

Only `type: capture` files may be deleted through the API.

```bash
curl -s -X POST http://127.0.0.1:8484/delete \
  -H 'Content-Type: application/json' \
  -d '{"id": "01m1bzek4dv4wj904xqzyv36gn"}'
```

### `POST /search`

```bash
curl -s -X POST http://127.0.0.1:8484/search \
  -H 'Content-Type: application/json' \
  -d '{"query": "Constellation"}'
```

### `POST /neighbors`

```bash
curl -s -X POST http://127.0.0.1:8484/neighbors \
  -H 'Content-Type: application/json' \
  -d '{"id": "window-architecture"}'
```

### `POST /flush_access`

Flushes buffered `last_accessed` updates from prior reads into a single git
commit. Call this at the end of a session.

```bash
curl -s -X POST http://127.0.0.1:8484/flush_access -d '{}'
```

### `GET /health`

```bash
curl -s http://127.0.0.1:8484/health
```

## Orchestrator tool mapping

The six endpoints above map to supervisor tool names `memory_read`,
`memory_write`, `memory_delete`, `memory_search`, `memory_neighbors`, and
`memory_flush` with identical parameters. Tool registration itself happens
in the orchestrator, not here (§8 of the build spec).

## Obsidian

See `docs/obsidian.md`. Two audit Bases (`docs/bases/all-decisions.base`,
`docs/bases/stale-memory.base`) are included.

## Tests

```bash
pytest tests/ -v
```

13 automated tests corresponding to build-spec §12 items 1–13. Item 14
(Obsidian compatibility) is manual — see `docs/obsidian.md`.
