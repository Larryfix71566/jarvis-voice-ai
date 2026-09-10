"""Localhost-only HTTP service on 127.0.0.1:8484 (§8)."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from . import USER_ID
from .config import Paths
from .gitutil import head as git_head
from .index import Index
from .vault import Vault, VaultError

app = FastAPI(title="mortimer-vault")

_paths = Paths.build()
_vault = Vault(_paths, USER_ID)
_index = Index(_paths, USER_ID)


@app.on_event("startup")
def _startup():
    if _index.count_files() == 0:
        _index.rebuild_full()
    else:
        _index.sync_incremental()
    _index.start_watcher()


@app.on_event("shutdown")
def _shutdown():
    _vault.flush_access()
    _index.close()


def _err(e: VaultError) -> JSONResponse:
    status = {
        "NOT_FOUND": 404,
        "STALE_FILE": 409,
        "DECISION_GUARD": 409,
        "DELETE_FORBIDDEN": 403,
        "DUPLICATE_ID": 409,
        "VALIDATION_FAILED": 422,
        "BAD_ID": 422,
    }.get(e.code, 400)
    return JSONResponse(status_code=status, content=e.to_dict())


class ReadReq(BaseModel):
    id: str


class WriteReq(BaseModel):
    type: str
    body: str
    tags: list[str] = []
    confidence: str
    source_sessions: list[str] = []
    id: Optional[str] = None
    expected_hash: Optional[str] = None
    previous_excerpt: Optional[str] = None


class DeleteReq(BaseModel):
    id: str


class SearchReq(BaseModel):
    query: str
    k: Optional[int] = None
    type: Optional[str] = None
    tags: Optional[list[str]] = None
    confidence_min: Optional[str] = None


class NeighborsReq(BaseModel):
    id: str


@app.post("/read")
def read(req: ReadReq):
    try:
        rec = _vault.read(req.id)
    except VaultError as e:
        return _err(e)
    return {
        "id": rec.id,
        "frontmatter": rec.frontmatter,
        "body": rec.body,
        "content_hash": rec.content_hash,
    }


@app.post("/write")
def write(req: WriteReq):
    try:
        rec = _vault.write(
            type=req.type,
            body=req.body,
            tags=req.tags,
            confidence=req.confidence,
            source_sessions=req.source_sessions,
            id=req.id,
            expected_hash=req.expected_hash,
            previous_excerpt=req.previous_excerpt,
        )
    except VaultError as e:
        return _err(e)
    _index._index_one(rec.path)
    _index._recompute_link_existence()
    return {
        "id": rec.id,
        "frontmatter": rec.frontmatter,
        "content_hash": rec.content_hash,
    }


@app.post("/delete")
def delete(req: DeleteReq):
    try:
        _vault.delete(req.id)
    except VaultError as e:
        return _err(e)
    from pathlib import Path
    _index._remove_by_path(_vault.user_dir / "inbox" / f"{req.id}.md")
    return {"deleted": req.id}


@app.post("/search")
def search(req: SearchReq):
    results, meta = _index.search(
        query=req.query, k=req.k, type=req.type, tags=req.tags, confidence_min=req.confidence_min
    )
    return {"results": results, "meta": meta}


@app.post("/neighbors")
def neighbors(req: NeighborsReq):
    return {"neighbors": _index.neighbors(req.id)}


@app.post("/flush_access")
def flush_access():
    n = _vault.flush_access()
    return {"flushed": n}


@app.get("/health")
def health():
    return {
        "status": "ok",
        "files_indexed": _index.count_files(),
        "watcher_alive": _index.watcher_alive(),
        "git_head": git_head(_paths.vault),
    }
