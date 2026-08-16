"""Truth table for jarvis.toolresult.classify_tool_result (plan D1)."""

import json

from jarvis.toolresult import classify_tool_result


class TestTransportFailures:
    def test_generic_failed_prefix(self):
        out = classify_tool_result("web_search", "web_search failed: timed out after 30s.")
        assert out.ok is False
        assert out.body_failure is False
        assert "timed out" in out.error

    def test_unknown_tool(self):
        out = classify_tool_result("nope", "Unknown tool 'nope'. Available: a, b.")
        assert out.ok is False
        assert out.body_failure is False

    def test_not_available_in_context(self):
        out = classify_tool_result("git_status", "Tool 'git_status' is not available in this context.")
        assert out.ok is False
        assert out.body_failure is False


class TestBodyFailures:
    def test_ok_false(self):
        body = json.dumps({"ok": False, "error": "could not read x (HTTP 401): Bad credentials"})
        out = classify_tool_result("app_read", body)
        assert out.ok is False
        assert out.body_failure is True
        assert "401" in out.error

    def test_error_key_without_ok_key(self):
        body = json.dumps({"error": "something broke"})
        out = classify_tool_result("some_tool", body)
        assert out.ok is False
        assert out.body_failure is True
        assert out.error == "something broke"

    def test_ok_false_no_error_message(self):
        body = json.dumps({"ok": False})
        out = classify_tool_result("some_tool", body)
        assert out.ok is False
        assert out.body_failure is True
        assert out.error == "tool reported ok: false"

    def test_error_message_truncated_to_300(self):
        body = json.dumps({"ok": False, "error": "x" * 500})
        out = classify_tool_result("some_tool", body)
        assert len(out.error) == 300


class TestSuccess:
    def test_ok_true(self):
        body = json.dumps({"ok": True, "result": "fine"})
        out = classify_tool_result("some_tool", body)
        assert out.ok is True
        assert out.error is None
        assert out.body_failure is False

    def test_bare_data_no_ok_key(self):
        # Most tools (git_status, get_weather, ...) return plain data with
        # no ok/error key at all. This MUST classify as success — rule 3's
        # entire reason for existing is not penalizing these.
        body = json.dumps({"branch": "main", "clean": True})
        out = classify_tool_result("git_status", body)
        assert out.ok is True

    def test_non_json_text(self):
        out = classify_tool_result("get_current_time", "2026-08-14T19:00:00-04:00")
        assert out.ok is True

    def test_empty_string(self):
        out = classify_tool_result("some_tool", "")
        assert out.ok is True

    def test_json_array(self):
        out = classify_tool_result("list_notes", json.dumps([{"id": 1}, {"id": 2}]))
        assert out.ok is True

    def test_json_object_with_falsy_but_present_error_key(self):
        # error: "" or error: None must NOT be treated as a failure —
        # only a truthy error value counts (mirrors D1's "or obj.get('error')
        # is truthy" rule precisely).
        out = classify_tool_result("some_tool", json.dumps({"ok": True, "error": ""}))
        assert out.ok is True
        out2 = classify_tool_result("some_tool", json.dumps({"ok": True, "error": None}))
        assert out2.ok is True


class TestRealWorldPayloads:
    """Regression cases lifted verbatim from MORTIMER_AGENT_TRUST_PLAN.md
    Appendix A — the actual failures that motivated this module."""

    def test_app_write_file_401(self):
        body = json.dumps({
            "ok": False,
            "error": "could not read plans/MORTIMER_LOGGING_IMPLEMENTATION_PLAN.md "
                     "in jarvis: read of plans/MORTIMER_LOGGING_IMPLEMENTATION_PLAN.md "
                     "in jarvis failed (HTTP 401): Bad credentials",
        })
        out = classify_tool_result("app_write_file", body)
        assert out.ok is False
        assert out.body_failure is True

    def test_prepare_commit_lock_failure(self):
        body = json.dumps({
            "ok": False,
            "error": "git add failed: fatal: Unable to create "
                     "'/repo/.git/index.lock': File exists.",
        })
        out = classify_tool_result("prepare_commit", body)
        assert out.ok is False
        assert out.body_failure is True
