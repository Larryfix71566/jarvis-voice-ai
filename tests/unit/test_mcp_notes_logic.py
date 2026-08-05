"""Unit tests for mcp_servers/mcp_notes/logic.py (plan Phase 1 Tests)."""

from mcp_servers.mcp_notes import logic


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
