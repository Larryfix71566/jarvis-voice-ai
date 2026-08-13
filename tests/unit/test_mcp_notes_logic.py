"""Unit tests for mcp_servers/mcp_notes/logic.py (plan Phase 1 Tests; Phase
5a search_sessions tests below)."""

from mcp_servers.mcp_notes import logic
from jarvis.db import get_conn, now_iso


def _insert_conversation(session_id, role, content):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO conversations (session_id, role, content, created_at) "
            "VALUES (?, ?, ?, ?)",
            (session_id, role, content, now_iso()),
        )


def _make_notes():
    logic.create_note("Wifi password", "The password is swordfish", "home,wifi")
    logic.create_note("Dentist info", "Dr. Patel on Main Street", "health")
    logic.create_note("Gift ideas", "Mom likes gardening books", "family")


class TestCreateNote:
    def test_happy_path(self, fresh_db):
        result = logic.create_note("Wifi password", "swordfish", "home")
        assert result["id"] == 1
        assert result["message"] == "Note saved: Wifi password"

    def test_empty_title_error(self, fresh_db):
        assert "error" in logic.create_note("", "body")

    def test_empty_body_error(self, fresh_db):
        assert "error" in logic.create_note("title", "")


class TestListNotes:
    def test_newest_first(self, fresh_db):
        _make_notes()
        notes = logic.list_notes()["notes"]
        assert [n["title"] for n in notes] == ["Gift ideas", "Dentist info", "Wifi password"]

    def test_tag_filter(self, fresh_db):
        _make_notes()
        notes = logic.list_notes(tag="health")["notes"]
        assert len(notes) == 1
        assert notes[0]["title"] == "Dentist info"

    def test_limit_respected(self, fresh_db):
        _make_notes()
        assert len(logic.list_notes(limit=2)["notes"]) == 2


class TestSearchNotes:
    def test_matches_body_and_tags_case_insensitive(self, fresh_db):
        _make_notes()
        assert len(logic.search_notes("SWORDFISH")["notes"]) == 1
        assert len(logic.search_notes("WIFI")["notes"]) == 1

    def test_no_match_returns_empty(self, fresh_db):
        _make_notes()
        assert logic.search_notes("submarine")["notes"] == []

    def test_empty_query_error(self, fresh_db):
        assert "error" in logic.search_notes("  ")


class TestGetNote:
    def test_found(self, fresh_db):
        created = logic.create_note("t", "b")
        assert logic.get_note(created["id"])["note"]["title"] == "t"

    def test_not_found(self, fresh_db):
        assert "error" in logic.get_note(999)


class TestUpdateNote:
    def test_update_body_bumps_updated_at(self, fresh_db):
        created = logic.create_note("t", "b")
        original = logic.get_note(created["id"])["note"]
        result = logic.update_note(created["id"], body="new body")
        assert result["message"] == f"Note {created['id']} updated."
        updated = logic.get_note(created["id"])["note"]
        assert updated["body"] == "new body"
        assert updated["title"] == "t"
        assert updated["updated_at"] >= original["updated_at"]

    def test_not_found(self, fresh_db):
        assert "error" in logic.update_note(999, body="x")

    def test_nothing_to_update(self, fresh_db):
        created = logic.create_note("t", "b")
        assert "error" in logic.update_note(created["id"])


class TestDeleteNote:
    def test_happy(self, fresh_db):
        created = logic.create_note("t", "b")
        assert "Deleted" in logic.delete_note(created["id"])["message"]
        assert "error" in logic.get_note(created["id"])

    def test_not_found(self, fresh_db):
        assert "error" in logic.delete_note(999)


class TestSearchSessions:
    """Plan Phase 5a: FTS5 full-text search over the conversations table."""

    def test_finds_matching_conversation_row(self, fresh_db):
        _insert_conversation("s1", "user", "the garage door code is four four eight two")
        _insert_conversation("s1", "assistant", "got it, garage code noted")
        _insert_conversation("s2", "user", "what's the weather in Paris")

        result = logic.search_sessions("garage")
        assert "results" in result
        session_ids = {r["session_id"] for r in result["results"]}
        assert session_ids == {"s1"}
        assert len(result["results"]) == 2  # both garage-mentioning rows

    def test_no_match_returns_empty_results(self, fresh_db):
        _insert_conversation("s1", "user", "what's the weather in Paris")
        result = logic.search_sessions("submarine")
        assert result["results"] == []

    def test_empty_query_error(self, fresh_db):
        assert "error" in logic.search_sessions("")
        assert "error" in logic.search_sessions("   ")

    def test_limit_respected(self, fresh_db):
        for i in range(5):
            _insert_conversation(f"s{i}", "user", "garage door update number "
                                 f"{i}")
        result = logic.search_sessions("garage", limit=2)
        assert len(result["results"]) == 2

    def test_limit_capped_at_max(self, fresh_db):
        for i in range(25):
            _insert_conversation(f"s{i}", "user", f"garage door update {i}")
        result = logic.search_sessions("garage", limit=1000)
        assert len(result["results"]) == logic.MAX_SEARCH_RESULTS

    def test_multi_word_query_requires_all_tokens(self, fresh_db):
        _insert_conversation("s1", "user", "the garage door code is set")
        _insert_conversation("s2", "user", "the front door is locked")

        result = logic.search_sessions("garage door")
        session_ids = {r["session_id"] for r in result["results"]}
        assert session_ids == {"s1"}

    def test_special_characters_do_not_crash_search(self, fresh_db):
        """FTS5 operators/quotes in user input must not produce a malformed
        MATCH query — each token is quoted individually."""
        _insert_conversation("s1", "user", "the code is \"4482\" -maybe")
        # None of these should raise, even though they contain FTS5 syntax
        # characters (unbalanced quotes, "-", "*") that would be operators
        # if passed through unquoted.
        assert "error" not in logic.search_sessions('"unbalanced quote')
        assert "error" not in logic.search_sessions("wildcard*")
        assert "error" not in logic.search_sessions("-exclude term")
        assert "error" not in logic.search_sessions("NOT a real operator")

    def test_result_includes_snippet_and_metadata(self, fresh_db):
        _insert_conversation("s1", "user", "remember the garage door code")
        result = logic.search_sessions("garage")
        row = result["results"][0]
        assert row["session_id"] == "s1"
        assert row["role"] == "user"
        assert "created_at" in row
        assert "garage" in row["snippet"].lower()

    def test_case_insensitive(self, fresh_db):
        _insert_conversation("s1", "user", "The Garage Door Code")
        result = logic.search_sessions("GARAGE")
        assert len(result["results"]) == 1

    def test_deleted_conversation_row_removed_from_index(self, fresh_db):
        """FTS5 sync triggers (migration 0005) must keep the index in sync
        with row deletion, not just insertion."""
        _insert_conversation("s1", "user", "garage door code")
        assert len(logic.search_sessions("garage")["results"]) == 1

        with get_conn() as conn:
            conn.execute("DELETE FROM conversations WHERE session_id = 's1'")

        assert logic.search_sessions("garage")["results"] == []
