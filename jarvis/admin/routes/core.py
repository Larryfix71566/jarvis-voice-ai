"""Admin sidecar routes: health, architecture reference and the git panel (/api/health, /api/architecture, /api/git/*).

Moved verbatim from jarvis/admin/server.py (B6). Helpers, state and imported
modules are reached as `srv.<name>` at call time, never imported here, so a
test that monkeypatches jarvis.admin.server is seen by these handlers.
Only jarvis.admin.server imports this module.
"""

from __future__ import annotations

from jarvis.admin import server as srv
from jarvis.admin.server import (  # request bodies named in signatures
    ActionIn,
    CommitDraftIn,
)

# Routes register on the server's one FastAPI app (see the B6 note there).
app = srv.app


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.get("/api/git/status")
def status() -> dict:
    return srv.logic.git_status()


@app.get("/api/architecture")
def architecture_reference() -> dict:
    """Expose the checked-in architecture contract to the native sidecar.

    This is a read-only view of the repository document, not a second
    architecture store.  The digest lets the UI identify exactly which
    document the user is reading, while the bounded response protects the
    local admin service if a future document grows unexpectedly.
    """
    root = srv.Path(srv.os.environ.get("JARVIS_REPO_ROOT", str(srv.REPO_ROOT)))
    path = root / "docs" / "ARCHITECTURE.md"
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        return {"ok": False, "error": f"architecture reference unavailable: {exc}"}
    max_chars = 120_000
    truncated = len(content) > max_chars
    visible = content[:max_chars] if truncated else content
    return {
        "ok": True,
        "path": "docs/ARCHITECTURE.md",
        "content": visible,
        "sha256": srv.hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "truncated": truncated,
    }


@app.get("/api/git/log")
def log(n: int = 5) -> dict:
    return srv.logic.git_log(n)


@app.get("/api/git/diff")
def diff() -> dict:
    return srv.logic.git_diff_summary()


@app.get("/api/git/actions")
def actions(status: str = "all", limit: int = 10) -> dict:
    return srv.logic.list_actions(status, limit)


@app.post("/api/git/prepare-commit")
def prepare_commit(body: CommitDraftIn) -> dict:
    # Legacy console requests must refuse without inspecting or staging the
    # host index, even when the client omitted the old optional file list.
    return srv.logic.prepare_commit(body.message, body.paths or [])


@app.post("/api/git/commit")
def commit(body: ActionIn) -> dict:
    return srv.logic.commit(body.action_id)


@app.post("/api/git/prepare-push")
def prepare_push() -> dict:
    return srv.logic.prepare_push()


@app.post("/api/git/push")
def push(body: ActionIn) -> dict:
    return srv.logic.push(body.action_id)
