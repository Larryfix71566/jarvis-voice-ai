"""A later source policy must remove earlier content while preserving trace facts."""
import json

from jarvis.db import get_conn, run_migrations
from jarvis.runlog.store import RunLogger


def test_source_tightening_scrubs_earlier_mcp_buffer_and_sql_previews(tmp_path):
    db = tmp_path / "runlog.sqlite"
    conn = get_conn(db)
    run_migrations(conn)
    conn.close()
    root = tmp_path / "runlog-root"
    logger = RunLogger("source-run", "developer", "Developer", "SYNTHETIC_PRIVATE_TASK",
                       db_path=db, root=root, enabled=True)
    logger.start()
    logger.tool_call("get_note", {"query": "SYNTHETIC_PRIVATE_ARGUMENT"}, tool_call_id="source-call")
    logger.mcp_call("get_note", "mcp-notes", False, 9, error="SYNTHETIC_PRIVATE_MCP_ERROR")
    logger.tool_result("get_note", "SYNTHETIC_PRIVATE_RESULT", 10, False, tool_call_id="source-call")
    before = [(record["seq"], record["type"]) for record in logger._buffer]
    counters = (logger._tool_count, logger._tools_ok, logger._tools_failed, logger._payload_bytes)

    logger.mark_sensitive()

    assert [(record["seq"], record["type"]) for record in logger._buffer] == before
    assert (logger._tool_count, logger._tools_ok, logger._tools_failed, logger._payload_bytes) == counters
    assert "SYNTHETIC_PRIVATE" not in repr(logger._buffer)
    mcp = next(record for record in logger._buffer if record["type"] == "mcp_call")
    assert {key: mcp[key] for key in ("tool", "server", "ok", "latency_ms")} == {
        "tool": "get_note", "server": "mcp-notes", "ok": False, "latency_ms": 9,
    }
    conn = get_conn(db)
    events = conn.execute("SELECT tool_call_id,args_preview,result_preview FROM agent_events WHERE run_id='source-run'").fetchall()
    task = conn.execute("SELECT task FROM agent_runs WHERE run_id='source-run'").fetchone()[0]
    conn.close()
    assert task == "<sensitive>"
    assert "SYNTHETIC_PRIVATE" not in repr([tuple(row) for row in events])
    assert [row[0] for row in events if row[0] is not None] == ["source-call", "source-call"]
    logger.finish("SYNTHETIC_PRIVATE_REPLY")
    payload = next(root.rglob("*.jsonl")).read_text()
    assert "SYNTHETIC_PRIVATE" not in payload
    assert [json.loads(line)["type"] for line in payload.splitlines()] == [
        "run_start", "tool_call", "mcp_call", "tool_result", "run_end",
    ]


def test_tightening_after_finish_rewrites_existing_payload_without_deleting_metadata(tmp_path):
    db = tmp_path / "runlog.sqlite"
    conn = get_conn(db)
    run_migrations(conn)
    conn.close()
    root = tmp_path / "payloads"
    logger = RunLogger("finished-source-run", "developer", "Developer", "synthetic task",
                       db_path=db, root=root, enabled=True)
    logger.start()
    logger.mcp_call("get_note", "mcp-notes", False, 8, error="SYNTHETIC_PRIVATE_MCP_ERROR")
    logger.finish("SYNTHETIC_PRIVATE_REPLY")
    before = [(record["seq"], record["type"]) for record in logger._buffer]

    logger.mark_sensitive()

    assert "SYNTHETIC_PRIVATE" not in next(root.rglob("*.jsonl")).read_text()
    assert [(record["seq"], record["type"]) for record in logger._buffer] == before
    conn = get_conn(db)
    reply = conn.execute("SELECT reply_preview FROM agent_runs WHERE run_id='finished-source-run'").fetchone()[0]
    conn.close()
    assert reply == "<sensitive>"
