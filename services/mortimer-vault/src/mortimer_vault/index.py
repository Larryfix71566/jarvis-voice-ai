"""Disposable derived index over the vault (§7). Rebuildable from zero at any time."""
from __future__ import annotations

import hashlib
import logging
import re
import sqlite3
import threading
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from .config import Paths, load_retrieval_config
from .mdfile import ParseError, parse
from .schema import CONFIDENCE_ORDER, now_iso, validate_tolerant

LOG = logging.getLogger("mortimer_vault.index")

LINK_RE = re.compile(r"\[\[([a-z0-9][a-z0-9-]*)\]\]")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS files (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    type TEXT,
    created TEXT,
    updated TEXT,
    last_accessed TEXT,
    confidence TEXT,
    schema INTEGER,
    path TEXT,
    content_hash TEXT,
    valid INTEGER,
    indexed_at TEXT
);
CREATE TABLE IF NOT EXISTS tags (
    file_id TEXT,
    tag TEXT,
    PRIMARY KEY (file_id, tag)
);
CREATE TABLE IF NOT EXISTS links (
    source_id TEXT,
    target_id TEXT,
    target_exists INTEGER,
    PRIMARY KEY (source_id, target_id)
);
CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(
    id UNINDEXED, body, tokenize = 'porter unicode61'
);
"""


def _hash_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


class Index:
    def __init__(self, paths: Paths, user_id: str):
        self.paths = paths
        self.user_id = user_id
        self.paths.index_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = paths.index_db
        self._lock = threading.RLock()
        self._conn = self._connect()
        self._check_fts5()
        self._conn.executescript(SCHEMA_SQL)
        self._conn.commit()
        self._observer: Observer | None = None

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        return conn

    def _check_fts5(self) -> None:
        try:
            self._conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS __fts5_check USING fts5(x)")
            self._conn.execute("DROP TABLE __fts5_check")
        except sqlite3.OperationalError as e:
            raise RuntimeError(
                "SQLite FTS5 extension is not available; mortimer-vault requires FTS5"
            ) from e

    def close(self) -> None:
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=2)
        self._conn.close()

    # ---- (re)build --------------------------------------------------------

    def _iter_files(self):
        user_dir = self.paths.user_dir(self.user_id)
        for sub in ("areas", "sessions", "inbox"):
            d = user_dir / sub
            if not d.exists():
                continue
            for p in sorted(d.glob("*.md")):
                yield p

    def _index_one(self, path: Path) -> None:
        raw = path.read_bytes()
        content_hash = _hash_bytes(raw)
        try:
            fm, body = parse(raw.decode("utf-8"))
            valid, _reason = validate_tolerant(fm)
        except ParseError as e:
            fm = {}
            body = ""
            valid = False
            LOG.warning("failed to parse %s: %s", path, e)

        file_id = fm.get("id") or path.stem
        with self._lock:
            self._conn.execute(
                """INSERT INTO files
                   (id, user_id, type, created, updated, last_accessed, confidence,
                    schema, path, content_hash, valid, indexed_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     user_id=excluded.user_id, type=excluded.type, created=excluded.created,
                     updated=excluded.updated, last_accessed=excluded.last_accessed,
                     confidence=excluded.confidence, schema=excluded.schema, path=excluded.path,
                     content_hash=excluded.content_hash, valid=excluded.valid,
                     indexed_at=excluded.indexed_at
                """,
                (
                    file_id,
                    self.user_id,
                    fm.get("type"),
                    fm.get("created"),
                    fm.get("updated"),
                    fm.get("last_accessed"),
                    fm.get("confidence"),
                    fm.get("schema"),
                    str(path),
                    content_hash,
                    1 if valid else 0,
                    now_iso(),
                ),
            )
            self._conn.execute("DELETE FROM tags WHERE file_id = ?", (file_id,))
            for tag in fm.get("tags") or []:
                self._conn.execute("INSERT OR IGNORE INTO tags (file_id, tag) VALUES (?,?)", (file_id, tag))

            self._conn.execute("DELETE FROM links WHERE source_id = ?", (file_id,))
            existing_ids = {r["id"] for r in self._conn.execute("SELECT id FROM files")}
            for target in set(LINK_RE.findall(body)):
                self._conn.execute(
                    "INSERT OR REPLACE INTO links (source_id, target_id, target_exists) VALUES (?,?,?)",
                    (file_id, target, 1 if target in existing_ids else 0),
                )

            self._conn.execute("DELETE FROM fts WHERE id = ?", (file_id,))
            self._conn.execute("INSERT INTO fts (id, body) VALUES (?,?)", (file_id, body))
            self._conn.commit()

    def _remove_by_path(self, path: Path) -> None:
        with self._lock:
            row = self._conn.execute("SELECT id FROM files WHERE path = ?", (str(path),)).fetchone()
            if not row:
                return
            file_id = row["id"]
            self._conn.execute("DELETE FROM files WHERE id = ?", (file_id,))
            self._conn.execute("DELETE FROM tags WHERE file_id = ?", (file_id,))
            self._conn.execute("DELETE FROM links WHERE source_id = ?", (file_id,))
            self._conn.execute("DELETE FROM fts WHERE id = ?", (file_id,))
            self._conn.commit()

    def rebuild_full(self) -> int:
        with self._lock:
            self._conn.executescript(
                "DELETE FROM files; DELETE FROM tags; DELETE FROM links; DELETE FROM fts;"
            )
            self._conn.commit()
        n = 0
        for p in self._iter_files():
            self._index_one(p)
            n += 1
        # recompute target_exists now that all files are indexed
        self._recompute_link_existence()
        return n

    def _recompute_link_existence(self) -> None:
        with self._lock:
            existing_ids = {r["id"] for r in self._conn.execute("SELECT id FROM files")}
            for row in self._conn.execute("SELECT source_id, target_id FROM links").fetchall():
                exists = 1 if row["target_id"] in existing_ids else 0
                self._conn.execute(
                    "UPDATE links SET target_exists = ? WHERE source_id = ? AND target_id = ?",
                    (exists, row["source_id"], row["target_id"]),
                )
            self._conn.commit()

    def sync_incremental(self) -> int:
        """Startup incremental pass: compare content_hash of every file to the index (§7)."""
        n_changed = 0
        seen_paths = set()
        for p in self._iter_files():
            seen_paths.add(str(p))
            raw_hash = _hash_bytes(p.read_bytes())
            row = self._conn.execute("SELECT content_hash FROM files WHERE path = ?", (str(p),)).fetchone()
            if row is None or row["content_hash"] != raw_hash:
                self._index_one(p)
                n_changed += 1
        # remove index rows for files that no longer exist on disk
        for row in self._conn.execute("SELECT path FROM files").fetchall():
            if row["path"] not in seen_paths:
                self._remove_by_path(Path(row["path"]))
                n_changed += 1
        self._recompute_link_existence()
        return n_changed

    def count_files(self) -> int:
        return self._conn.execute("SELECT COUNT(*) AS c FROM files").fetchone()["c"]

    # ---- watcher ------------------------------------------------------------

    def start_watcher(self) -> None:
        handler = _VaultEventHandler(self)
        observer = Observer()
        observer.schedule(handler, str(self.paths.user_dir(self.user_id)), recursive=True)
        observer.start()
        self._observer = observer

    def watcher_alive(self) -> bool:
        return bool(self._observer and self._observer.is_alive())

    # ---- search / neighbors --------------------------------------------------

    def search(self, query: str, k: int | None = None, type: str | None = None,
               tags: list[str] | None = None, confidence_min: str | None = None) -> tuple[list[dict], dict]:
        cfg = load_retrieval_config(self.paths)
        fts_k = k or cfg["fts_k"]
        max_results = cfg["max_results"]
        weights = cfg["confidence_weights"]
        half_life = cfg["recency_half_life_days"]

        with self._lock:
            rows = self._conn.execute(
                """SELECT f.id, f.type, f.updated, f.confidence, bm25(fts) AS raw_bm25
                   FROM fts JOIN files f ON f.id = fts.id
                   WHERE fts MATCH ? AND f.valid = 1
                   ORDER BY raw_bm25 LIMIT ?""",
                (query, fts_k),
            ).fetchall()

            candidates = {r["id"]: dict(r) for r in rows}

            # one-hop link expansion (both directions)
            expanded_ids = set()
            for fid in list(candidates.keys()):
                for r in self._conn.execute(
                    "SELECT target_id AS other FROM links WHERE source_id = ? AND target_exists = 1", (fid,)
                ).fetchall():
                    expanded_ids.add(r["other"])
                for r in self._conn.execute(
                    "SELECT source_id AS other FROM links WHERE target_id = ?", (fid,)
                ).fetchall():
                    expanded_ids.add(r["other"])
            expanded_ids -= set(candidates.keys())

            for fid in expanded_ids:
                frow = self._conn.execute(
                    "SELECT id, type, updated, confidence FROM files WHERE id = ? AND valid = 1", (fid,)
                ).fetchone()
                if frow:
                    candidates[fid] = {**dict(frow), "raw_bm25": None}

        if type:
            candidates = {k_: v for k_, v in candidates.items() if v["type"] == type}
        if confidence_min:
            min_rank = CONFIDENCE_ORDER[confidence_min]
            candidates = {
                k_: v for k_, v in candidates.items()
                if CONFIDENCE_ORDER.get(v["confidence"], -1) >= min_rank
            }
        if tags:
            with self._lock:
                tagged = set()
                for t in tags:
                    for r in self._conn.execute("SELECT file_id FROM tags WHERE tag = ?", (t,)).fetchall():
                        tagged.add(r["file_id"])
            candidates = {k_: v for k_, v in candidates.items() if k_ in tagged}

        # normalize bm25 (lower raw_bm25 == better match in sqlite fts5) onto [0.5, 1.0]
        bm25_vals = [v["raw_bm25"] for v in candidates.values() if v["raw_bm25"] is not None]
        if bm25_vals:
            best, worst = min(bm25_vals), max(bm25_vals)
        else:
            best = worst = 0.0

        def normalized_bm25(raw):
            if raw is None:
                return None
            if best == worst:
                return 1.0
            # best (lowest raw) -> 1.0, worst (highest raw) -> 0.5
            return 1.0 - 0.5 * ((raw - best) / (worst - best))

        floor = 0.5 * min((normalized_bm25(v) for v in bm25_vals), default=1.0) if bm25_vals else 0.5

        scored = []
        for fid, v in candidates.items():
            norm = normalized_bm25(v["raw_bm25"])
            if norm is None:
                norm = 0.5 * (min([normalized_bm25(b) for b in bm25_vals]) if bm25_vals else 1.0)
                norm = floor
            conf_w = weights.get(v["confidence"], 0.0)
            days = _days_since(v["updated"])
            recency = 0.5 ** (days / half_life) if half_life > 0 else 1.0
            score = norm * conf_w * recency
            snippet = self._snippet(fid, query) if v["raw_bm25"] is not None else ""
            scored.append({
                "id": fid, "type": v["type"], "snippet": snippet, "score": score,
                "updated": v["updated"], "confidence": v["confidence"],
            })

        scored.sort(key=lambda x: (-x["score"], x["id"]))
        results = scored[:max_results]
        meta = {"max_injected_tokens": cfg["max_injected_tokens"]}
        return results, meta

    def _snippet(self, file_id: str, query: str) -> str:
        with self._lock:
            row = self._conn.execute(
                "SELECT snippet(fts, 1, '', '', '…', 32) AS s FROM fts WHERE id = ? AND fts MATCH ?",
                (file_id, query),
            ).fetchone()
        return row["s"] if row else ""

    def neighbors(self, id: str) -> list[dict]:
        with self._lock:
            out_rows = self._conn.execute(
                "SELECT target_id AS other FROM links WHERE source_id = ? AND target_exists = 1", (id,)
            ).fetchall()
            in_rows = self._conn.execute(
                "SELECT source_id AS other FROM links WHERE target_id = ?", (id,)
            ).fetchall()

        out_ids = {r["other"] for r in out_rows}
        in_ids = {r["other"] for r in in_rows}
        both = out_ids & in_ids
        only_out = out_ids - both
        only_in = in_ids - both

        results = []
        for fid, direction in [(i, "both") for i in both] + [(i, "out") for i in only_out] + [(i, "in") for i in only_in]:
            with self._lock:
                frow = self._conn.execute(
                    "SELECT id, type, updated, confidence FROM files WHERE id = ?", (fid,)
                ).fetchone()
            if frow:
                results.append({**dict(frow), "direction": direction})
        return results


def _days_since(iso_ts: str | None) -> float:
    if not iso_ts:
        return 10_000.0
    from datetime import datetime, timezone
    try:
        dt = datetime.strptime(iso_ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return 10_000.0
    return (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0


class _VaultEventHandler(FileSystemEventHandler):
    """Debounced watcher: ignores .git/.obsidian/*.tmp; reindexes changed .md files (§7)."""

    def __init__(self, index: Index, debounce_seconds: float = 0.5):
        self.index = index
        self.debounce_seconds = debounce_seconds
        self._timers: dict[str, threading.Timer] = {}
        self._tlock = threading.Lock()

    def _ignored(self, path: str) -> bool:
        return ".git" in path or ".obsidian" in path or path.endswith(".tmp")

    def _schedule(self, path: str, deleted: bool = False):
        if self._ignored(path) or not path.endswith(".md"):
            return
        with self._tlock:
            existing = self._timers.get(path)
            if existing:
                existing.cancel()
            t = threading.Timer(self.debounce_seconds, self._process, args=(path, deleted))
            t.daemon = True
            self._timers[path] = t
            t.start()

    def _process(self, path: str, deleted: bool):
        p = Path(path)
        try:
            if deleted or not p.exists():
                self.index._remove_by_path(p)
            else:
                self.index._index_one(p)
            self.index._recompute_link_existence()
        except Exception:
            LOG.exception("watcher failed to process %s", path)

    def on_modified(self, event):
        if not event.is_directory:
            self._schedule(event.src_path)

    def on_created(self, event):
        if not event.is_directory:
            self._schedule(event.src_path)

    def on_deleted(self, event):
        if not event.is_directory:
            self._schedule(event.src_path, deleted=True)

    def on_moved(self, event):
        if not event.is_directory:
            self._schedule(event.src_path, deleted=True)
            self._schedule(event.dest_path)
