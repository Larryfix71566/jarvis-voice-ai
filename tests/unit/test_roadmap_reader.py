"""Canonical guarded source -> complete, attributable roadmap snapshot."""
import hashlib
import json
import subprocess
from pathlib import Path

from mcp_servers.mcp_repo import logic


def card(identity, status="landed", owner="`codex`", extra=""):
    return f'''<details id="{identity.lower()}">
<summary>{identity} — Interface</summary>
- **Owner:** {owner}
- **Status:** {status}
- **Next step:** larry: review
- **Unknown field:** must remain visible
- [ ] Larry: check the card
{extra}
</details>
'''


def test_full_document_after_30000_nested_details_and_code_fences():
    source = card("WS-01", "accepted") + "\n" + "x" * 31000 + "\n" + card("WS-17", extra="<details><summary>Evidence</summary>safe text</details>")
    source += '\n```md\n' + card("WS-99") + '```\n'
    rows, issues = logic._roadmap_cards(source)
    assert [row["id"] for row in rows] == ["WS-17", "WS-01"]
    assert rows[0]["lifecycle"] == "landed"  # not accepted
    assert rows[0]["checklist"][0]["checked"] is False
    assert rows[0]["fields"]["Unknown field"] == "must remain visible"
    assert "safe text" in rows[0]["details"]
    assert issues == []


def test_shared_owner_is_current_owner_not_authorship_and_unknown_lifecycle_stays():
    rows, issues = logic._roadmap_cards(card("WS-01", "done maybe", "`codex` and `claude`", "- **Implemented by:** larry"))
    assert rows[0]["owner"] == "`codex` and `claude`"
    assert rows[0]["lifecycle"] == "unclassified"
    assert rows[0]["status"] == "done maybe"
    assert any("unclassified" in issue for issue in issues)


def test_duplicate_and_malformed_sections_are_reported():
    rows, issues = logic._roadmap_cards(card("WS-01") + card("WS-01") + '<details id="ws-02">oops')
    assert len(rows) == 1
    assert any("duplicate" in issue for issue in issues)
    assert any("WS-02: unclosed" in issue for issue in issues)


def test_guarded_reader_provenance_logs_and_dirty_state(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_REPO_ROOT", str(tmp_path))
    doc = tmp_path / "ROADMAP.md"; doc.write_text(card("WS-17"))
    logs = tmp_path / "docs/roadmap-log"; logs.mkdir(parents=True)
    good = logs / 'entry.md'
    good.write_text('---\ndate: 2026-10-17\nrows: [WS-17]\nprs: []\n---\n# Progress\n')
    (logs / 'invalid.md').write_text('---\ndate: yesterday\nrows: [WS-17]\n---\n')
    subprocess.run(['git','init','-q',str(tmp_path)], check=True)
    subprocess.run(['git','-C',str(tmp_path),'add','.'], check=True)
    subprocess.run(['git','-C',str(tmp_path),'-c','user.name=Test','-c','user.email=test@example.invalid','-c','core.hooksPath=/dev/null','commit','-qm','fixture'], check=True)
    result = logic.repo_read_file('ROADMAP.md')
    snapshot = result['roadmap']
    assert snapshot['provenance']['sha256'] == hashlib.sha256(doc.read_bytes()).hexdigest()
    assert len(snapshot['provenance']['revision']) == 40
    assert snapshot['provenance']['dirty'] is False
    assert snapshot['provenance']['source_kind'] == 'local_checkout'
    assert snapshot['logs'][0]['sha256'] == hashlib.sha256(good.read_bytes()).hexdigest()
    assert snapshot['logs'][0]['rows'] == ['WS-17']
    assert any('invalid.md' in issue for issue in snapshot['issues'])
    doc.write_text(card('WS-17', 'accepted'))
    assert logic._roadmap_snapshot(tmp_path, logic.repo_read_file('ROADMAP.md')['content'])['provenance']['dirty'] is True


def test_guarded_logs_refuse_symlink_and_aggregate_bounds(tmp_path, monkeypatch):
    monkeypatch.setenv('JARVIS_REPO_ROOT', str(tmp_path))
    (tmp_path / 'ROADMAP.md').write_text(card('WS-01'))
    logs = tmp_path / 'docs/roadmap-log'; logs.mkdir(parents=True)
    secret = tmp_path / '.env'; secret.write_text('not a log')
    (logs / 'misplaced.md').symlink_to(secret)
    snapshot = logic._roadmap_snapshot(tmp_path, logic.repo_read_file('ROADMAP.md')['content'])
    assert snapshot['logs'] == []
    assert any('path refused' in issue for issue in snapshot['issues'])
    monkeypatch.setattr(logic, 'ROADMAP_SNAPSHOT_MAX_BYTES', 10)
    import pytest
    with pytest.raises(logic.RepoPathError, match='no workstreams were silently truncated'):
        logic._roadmap_snapshot(tmp_path, card('WS-01'))
    refused = logic.repo_read_file('ROADMAP.md')
    assert refused['ok'] is False
    assert 'no workstreams were silently truncated' in refused['error']
    assert 'roadmap' not in refused and 'content' not in refused


def test_generic_read_does_not_add_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv('JARVIS_REPO_ROOT', str(tmp_path))
    (tmp_path / 'plain.md').write_text('hello')
    assert logic.repo_read_file('plain.md') == {'ok':True, 'path':'plain.md', 'bytes':5, 'content':'hello'}


def test_roadmap_limit_is_separate_from_generic_file_limit(tmp_path, monkeypatch):
    monkeypatch.setenv('JARVIS_REPO_ROOT', str(tmp_path))
    monkeypatch.setattr(logic, 'REPO_READ_MAX_BYTES', 100)
    monkeypatch.setattr(logic, 'ROADMAP_READ_MAX_BYTES', 1000)
    text = card('WS-01', extra='x' * 500)
    (tmp_path / 'ROADMAP.md').write_text(text)
    (tmp_path / 'plain.md').write_text(text)

    result = logic.repo_read_file('ROADMAP.md')
    assert result['ok'] is True
    assert result['content'] == text
    ordinary = logic.repo_read_file('plain.md')
    assert ordinary['ok'] is False
    assert '100 byte limit' in ordinary['error']

    monkeypatch.setattr(logic, 'ROADMAP_READ_MAX_BYTES', 10)
    refused = logic.repo_read_file('ROADMAP.md')
    assert refused['ok'] is False
    assert '10 byte limit' in refused['error']
    assert 'content' not in refused and 'roadmap' not in refused


def test_roadmap_second_read_enforces_dedicated_limit(tmp_path, monkeypatch):
    monkeypatch.setenv('JARVIS_REPO_ROOT', str(tmp_path))
    doc = tmp_path / 'ROADMAP.md'
    doc.write_text(card('WS-01'))
    monkeypatch.setattr(logic, 'ROADMAP_READ_MAX_BYTES', doc.stat().st_size)
    original_read_bytes = Path.read_bytes

    def grown_read_bytes(path):
        if path == doc:
            return b'x' * (logic.ROADMAP_READ_MAX_BYTES + 1)
        return original_read_bytes(path)

    monkeypatch.setattr(Path, 'read_bytes', grown_read_bytes)
    refused = logic.repo_read_file('ROADMAP.md')
    assert refused['ok'] is False
    assert 'Roadmap grew beyond the read limit; not truncated' in refused['error']
    assert 'content' not in refused and 'roadmap' not in refused


def test_real_repo_has_complete_card_count_and_bounded_snapshot(monkeypatch):
    import re
    root = Path(__file__).resolve().parents[2]
    monkeypatch.setenv('JARVIS_REPO_ROOT', str(root))
    result = logic.repo_read_file('ROADMAP.md')
    assert result['ok'], result.get('error')
    expected = re.findall(r'<details id="(ws-\d+)">', result['content'])
    snapshot = logic._roadmap_snapshot(root, result['content'])
    assert {row['id'].lower() for row in snapshot['cards']} == set(expected)
    assert len(snapshot['cards']) == len(expected)
    assert len(json.dumps(snapshot).encode()) < logic.ROADMAP_SNAPSHOT_MAX_BYTES


def test_roadmap_read_adds_only_reserved_snapshot_field(tmp_path, monkeypatch):
    monkeypatch.setenv('JARVIS_REPO_ROOT', str(tmp_path))
    (tmp_path / 'ROADMAP.md').write_text(card('WS-01'))
    result = logic.repo_read_file('ROADMAP.md')
    assert set(result) == {'ok', 'path', 'bytes', 'content', 'roadmap'}


def test_log_count_and_total_size_refuse_instead_of_partial_snapshot(tmp_path, monkeypatch):
    import pytest
    monkeypatch.setenv('JARVIS_REPO_ROOT', str(tmp_path))
    (tmp_path / 'ROADMAP.md').write_text(card('WS-17'))
    logs = tmp_path / 'docs/roadmap-log'; logs.mkdir(parents=True)
    for index in range(3):
        (logs / f'{index}.md').write_text('---\ndate: 2026-10-17\nrows: [WS-17]\nprs: []\n---\n# Test\n')
    monkeypatch.setattr(logic, 'ROADMAP_LOG_MAX_FILES', 2)
    with pytest.raises(logic.RepoPathError, match='file limit'):
        logic._roadmap_snapshot(tmp_path, card('WS-17'))
    monkeypatch.setattr(logic, 'ROADMAP_LOG_MAX_FILES', 255)
    monkeypatch.setattr(logic, 'ROADMAP_LOG_TOTAL_MAX_BYTES', 10)
    with pytest.raises(logic.RepoPathError, match='total byte limit'):
        logic._roadmap_snapshot(tmp_path, card('WS-17'))
