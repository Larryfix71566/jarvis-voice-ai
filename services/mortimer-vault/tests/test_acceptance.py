import subprocess
from pathlib import Path

import pytest

from mortimer_vault.index import Index
from mortimer_vault.vault import Vault, VaultError


def git_log(repo: Path):
    r = subprocess.run(["git", "log", "--oneline"], cwd=repo, capture_output=True, text=True)
    return r.stdout.strip().splitlines()


# 1. Round-trip
def test_round_trip(vault, paths):
    rec = vault.write(type="area", body="hello world", tags=["x"], confidence="high",
                       source_sessions=[], id="test-area")
    read_back = vault.read("test-area")
    assert read_back.body == "hello world"
    assert read_back.frontmatter["id"] == "test-area"
    assert read_back.frontmatter["confidence"] == "high"
    log = git_log(paths.vault)
    create_commits = [l for l in log if "create test-area" in l]
    assert len(create_commits) == 1


# 2. Atomicity: no partial content, no leftover .tmp files
def test_atomicity_no_tmp_leftovers(vault, paths):
    vault.write(type="area", body="content", tags=[], confidence="medium",
                source_sessions=[], id="atomic-test")
    path = paths.user_dir("local") / "areas" / "atomic-test.md"
    assert path.exists()
    tmp_files = list(path.parent.glob(".*.tmp"))
    assert tmp_files == []
    # content is fully the new content, never partial
    text = path.read_text()
    assert "content" in text


# 3. Stale write
def test_stale_write_rejected(vault):
    vault.write(type="area", body="v1", tags=[], confidence="medium", source_sessions=[], id="stale-test")
    rec1 = vault.read("stale-test")
    rec2 = vault.read("stale-test")
    vault.write(type="area", body="v2", tags=[], confidence="medium", source_sessions=[],
                id="stale-test", expected_hash=rec1.content_hash)
    with pytest.raises(VaultError) as exc:
        vault.write(type="area", body="v3", tags=[], confidence="medium", source_sessions=[],
                    id="stale-test", expected_hash=rec2.content_hash)
    assert exc.value.code == "STALE_FILE"


# 4. Decision guard
def test_decision_guard(vault):
    vault.write(type="decision", body="We decided to use SwiftUI natively.", tags=[],
                confidence="high", source_sessions=[], id="dec-test")
    rec = vault.read("dec-test")
    with pytest.raises(VaultError) as exc:
        vault.write(type="decision", body="We decided something else entirely.", tags=[],
                    confidence="high", source_sessions=[], id="dec-test",
                    expected_hash=rec.content_hash)
    assert exc.value.code == "DECISION_GUARD"

    rec2 = vault.read("dec-test")
    updated = vault.write(type="decision", body="We decided to use SwiftUI natively. Confirmed.",
                          tags=[], confidence="high", source_sessions=[], id="dec-test",
                          expected_hash=rec2.content_hash,
                          previous_excerpt="We decided to use SwiftUI natively.")
    assert "Confirmed" in vault.read("dec-test").body


# 5. Digest boundary
def test_digest_boundary(vault):
    from mortimer_vault import DIGEST_MAX_CHARS
    too_long = "a" * (DIGEST_MAX_CHARS + 1)
    with pytest.raises(VaultError) as exc:
        vault.write(type="session-digest", body=too_long, tags=[], confidence="medium", source_sessions=[])
    assert exc.value.code == "VALIDATION_FAILED"
    assert "DIGEST_MAX_CHARS" in exc.value.message

    exactly = "a" * DIGEST_MAX_CHARS
    rec = vault.write(type="session-digest", body=exactly, tags=[], confidence="medium", source_sessions=[])
    assert rec.id


# 6. Disposable index
def test_disposable_index(vault, index, paths):
    for i in range(20):
        vault.write(type="area", body=f"note number {i} links to [[area-0]]", tags=["t"],
                    confidence="medium", source_sessions=[], id=f"area-{i}")
    index.rebuild_full()
    results1, _ = index.search("note")
    neighbors1 = index.neighbors("area-0")

    index.close()
    paths.index_db.unlink()
    index2 = Index(paths, "local")
    index2.rebuild_full()
    results2, _ = index2.search("note")
    neighbors2 = index2.neighbors("area-0")

    assert [r["id"] for r in results1] == [r["id"] for r in results2]
    assert sorted(n["id"] for n in neighbors1) == sorted(n["id"] for n in neighbors2)
    index2.close()


# 7. External edit reconciliation (without watcher timing; test the sync path directly)
def test_external_edit_reconciliation(vault, index, paths):
    rec = vault.write(type="area", body="original", tags=[], confidence="medium",
                       source_sessions=[], id="ext-edit")
    index.rebuild_full()

    path = paths.user_dir("local") / "areas" / "ext-edit.md"
    text = path.read_text()
    text = text.replace("original", "edited externally")
    path.write_text(text)

    index.sync_incremental()
    results, _ = index.search("edited")
    assert any(r["id"] == "ext-edit" for r in results)

    with pytest.raises(VaultError) as exc:
        vault.write(type="area", body="v2", tags=[], confidence="medium", source_sessions=[],
                    id="ext-edit", expected_hash=rec.content_hash)
    assert exc.value.code == "STALE_FILE"


# 8. Tolerant indexing
def test_tolerant_indexing_broken_frontmatter(paths, index):
    path = paths.user_dir("local") / "areas" / "broken.md"
    path.write_text("---\nid: broken\ntype: area\n---\nbody text here\n")
    index._index_one(path)  # should not raise despite missing required fields
    row = index._conn.execute("SELECT valid FROM files WHERE id = 'broken'").fetchone()
    assert row["valid"] == 0
    results, _ = index.search("body")
    # invalid files are excluded from search (valid=1 filter) but must not crash
    assert isinstance(results, list)


# 9. Unresolved links
def test_unresolved_links(vault, index):
    vault.write(type="area", body="see [[does-not-exist]] for more", tags=[], confidence="medium",
                source_sessions=[], id="link-source")
    index.rebuild_full()
    row = index._conn.execute(
        "SELECT target_exists FROM links WHERE source_id='link-source' AND target_id='does-not-exist'"
    ).fetchone()
    assert row["target_exists"] == 0
    neighbors = index.neighbors("link-source")
    assert all(n["id"] != "does-not-exist" for n in neighbors)


# 10. Access flush
def test_access_flush(vault, paths):
    import time
    vault.write(type="area", body="a", tags=[], confidence="medium", source_sessions=[], id="af-1")
    vault.write(type="area", body="b", tags=[], confidence="medium", source_sessions=[], id="af-2")
    vault.write(type="area", body="c", tags=[], confidence="medium", source_sessions=[], id="af-3")

    before = len(git_log(paths.vault))
    time.sleep(1.1)  # timestamps are second-precision (§4); ensure last_accessed actually changes
    vault.read("af-1")
    vault.read("af-2")
    vault.read("af-3")
    after_reads = len(git_log(paths.vault))
    assert after_reads == before  # reads never commit

    n = vault.flush_access()
    assert n == 3
    after_flush = len(git_log(paths.vault))
    assert after_flush == before + 1  # exactly one commit


# 11. Delete rules
def test_delete_rules(vault):
    cap = vault.write(type="capture", body="captured note", tags=[], confidence="low", source_sessions=[])
    vault.delete(cap.id)
    with pytest.raises(VaultError) as exc:
        vault.read(cap.id)
    assert exc.value.code == "NOT_FOUND"

    area = vault.write(type="area", body="area note", tags=[], confidence="medium",
                       source_sessions=[], id="undeletable")
    with pytest.raises(VaultError) as exc:
        vault.delete("undeletable")
    assert exc.value.code == "DELETE_FORBIDDEN"


# 12. Ranking determinism (frozen clock, per spec §12 item 12: "fixed fixture set + frozen clock")
def test_ranking_determinism(vault, paths, monkeypatch):
    for i in range(5):
        vault.write(type="area", body=f"apple banana cherry {i}", tags=[], confidence="high",
                    source_sessions=[], id=f"rank-{i}")

    monkeypatch.setattr("mortimer_vault.index._days_since", lambda ts: 3.0)

    index_a = Index(paths, "local")
    index_a.rebuild_full()
    results_a, _ = index_a.search("apple")
    index_a.close()

    index_b = Index(paths, "local")
    index_b.rebuild_full()
    results_b, _ = index_b.search("apple")
    index_b.close()

    assert results_a == results_b


# 13. Import
def test_import(tmp_path, paths, monkeypatch):
    src = tmp_path / "legacy"
    src.mkdir()
    (src / "ai-assistant-app.md").write_text("# Notes\nSome legacy content.")
    (src / "Window Architecture!!.md").write_text("Window notes.")
    (src / "window-architecture.md").write_text("Collision target.")

    from mortimer_vault.cli import cmd_import
    import argparse
    args = argparse.Namespace(src_dir=str(src))
    cmd_import(args)

    from mortimer_vault.vault import Vault
    v = Vault(paths, "local")
    ids = v._all_ids()
    assert "ai-assistant-app" in ids
    assert "window-architecture" in ids
    assert "window-architecture-2" in ids

    log = git_log(paths.vault)
    create_commits = [l for l in log if "vault: create" in l]
    assert len(create_commits) >= 3
