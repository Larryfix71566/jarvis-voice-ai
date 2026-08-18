"""Unit tests for jarvis/classify.py (K6, the conversion layer).

classify_fact is pure — no DB, no model, no network.
"""

from __future__ import annotations

from jarvis.classify import (
    DELETE_STALE,
    KEEP,
    NEEDS_REVIEW,
    TO_WORKFLOW,
    classify_all,
    classify_fact,
    format_report,
)


class TestWorkflowDetection:
    def test_a_rule_with_ordering_is_a_workflow(self):
        """Larry's own words, verbatim from the live store."""
        c = classify_fact("user.preference.api_research",
                          "Research alternative APIs first before modifying code",
                          "preference")
        assert c.destination == TO_WORKFLOW

    def test_a_rule_with_a_modal_is_a_workflow(self):
        c = classify_fact("user.style.progress_visibility",
                          "Must show real-time progress during task execution",
                          "preference")
        assert c.destination == TO_WORKFLOW

    def test_a_taste_is_not_a_workflow(self):
        """'Fahrenheit' is a preference, not a rule about how to work.
        Requiring a process VERB plus a modal/ordering word is what keeps
        tastes out of the workflow bucket."""
        assert classify_fact("user.preference.units", "Fahrenheit",
                             "preference").destination == KEEP
        assert classify_fact("user.style.response_length",
                             "Prefers short answers", "preference").destination == KEEP

    def test_project_tier_rules_go_to_review_not_extraction(self):
        """Measured on the real store: rule-SHAPED project facts were a bug
        report and a feature description. `project` says what is being
        built, not how work should be done."""
        c = classify_fact("bug.weather_display_celsius",
                          "Weather display showing Celsius instead of Fahrenheit "
                          "despite user preference", "project")
        assert c.destination == NEEDS_REVIEW
        assert "project facts describe what is built" in c.reason


class TestStaleDetection:
    def test_volatile_state_is_stale(self):
        c = classify_fact("project.repo", "19 commits ahead of main", "project")
        assert c.destination == DELETE_STALE

    def test_rederivable_system_facts_are_stale(self):
        c = classify_fact("project.mortimer.config",
                          "Servers are listed in config/mcp_servers.yaml", "system")
        assert c.destination == DELETE_STALE
        assert "ask the source" in c.reason

    def test_system_facts_are_not_deleted_on_a_hunch(self):
        """'Probably doesn't belong' is not a licence to delete."""
        c = classify_fact("project.mortimer.goal",
                          "Larry wants a calm assistant", "system")
        assert c.destination == NEEDS_REVIEW


class TestSafety:
    def test_identity_is_never_reclassified(self):
        c = classify_fact("user.location.rule",
                          "Always use the current device location before "
                          "checking weather", "identity")
        assert c.destination == KEEP
        assert "never auto-reclassified" in c.reason

    def test_ambiguity_goes_to_review_not_a_default(self):
        c = classify_fact("user.notes.thing",
                          "Steps to reproduce: open the app", "project")
        assert c.destination == NEEDS_REVIEW

    def test_classify_is_total(self):
        for args in (("", "", ""), (None, None, None)):
            assert classify_fact(*args).destination in (
                KEEP, TO_WORKFLOW, DELETE_STALE, NEEDS_REVIEW)


class TestReport:
    def test_report_states_nothing_changed_and_offers_no_bulk_apply(self):
        text = format_report(classify_all([
            {"key": "a", "content": "19 commits ahead", "tier": "project"},
        ]))
        assert "Nothing has been changed" in text
        assert "no bulk apply" in text

    def test_empty_store(self):
        assert "No facts stored" in format_report([])


class TestArchiveNotDelete:
    def test_archived_facts_leave_the_prompt_but_stay_readable(self, tmp_path):
        """K6.3 — conversion must be reversible. A fact that was
        over-deleted on 2026-08-18 had to be reconstructed from truncated
        console output; archiving makes that unnecessary."""
        from jarvis.db import get_conn, run_migrations
        from jarvis.memory import archive_fact, render_memory_context, upsert_fact

        conn = get_conn(tmp_path / "t.db")
        run_migrations(conn)
        upsert_fact(conn, "user.preference.thing", "some durable preference", "s1")
        assert "some durable preference" in render_memory_context(conn)

        assert archive_fact(conn, "user.preference.thing", "workflow:thing") is True
        assert "some durable preference" not in render_memory_context(conn)

        row = conn.execute(
            "SELECT content, became, archived_at FROM memories "
            "WHERE key = 'user.preference.thing'"
        ).fetchone()
        assert row["content"] == "some durable preference"  # intact
        assert row["became"] == "workflow:thing"
        assert row["archived_at"] is not None
        conn.close()

    def test_archiving_twice_is_a_no_op(self, tmp_path):
        from jarvis.db import get_conn, run_migrations
        from jarvis.memory import archive_fact, upsert_fact

        conn = get_conn(tmp_path / "t.db")
        run_migrations(conn)
        upsert_fact(conn, "k", "v", "s1")
        assert archive_fact(conn, "k", "x") is True
        assert archive_fact(conn, "k", "y") is False  # already archived
        conn.close()
