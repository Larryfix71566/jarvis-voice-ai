from __future__ import annotations

import uuid
import unittest
from types import SimpleNamespace

from jarvis.bot.phone_remote_results import (
    MAX_PAGE, PhoneRemoteResults, PhoneResultCollectionGrantV1,
    SyntheticResultRecord, SyntheticResultsSource,
)


OWNER = "alice"
DEVICE = "device-a"
GRANT = "grant-a"


def ident(n: int) -> str:
    return str(uuid.UUID(int=n))


def record(n, revision=1, classification="ordinary", title=None, body=None):
    return SyntheticResultRecord(ident(n), revision, title or f"title-{n}",
                                 body or f"body-{n}", 1_800_000_000_000,
                                 classification, True)


def binding(*, device=DEVICE, grant=GRANT, scopes=("read",), session="session-a"):
    return SimpleNamespace(owner_id=OWNER, device_id=device, grant_id=grant,
        session_id=session, login_incarnation="host:1", host_id="host-test",
        host_generation=1, grant_generation=1, session_generation=1,
        process_epoch="epoch-1", scopes=frozenset(scopes))


def setup(records):
    member_ids = tuple(sorted((row.result_id for row in records)))
    grant = PhoneResultCollectionGrantV1(OWNER, DEVICE, GRANT, ident(9000), member_ids)
    source = SyntheticResultsSource(records)
    return PhoneRemoteResults(grant, source, clock=lambda: 100.0), source


class PhoneRemoteResultsTests(unittest.TestCase):
    def test_snapshot_is_complete_sorted_and_has_opaque_resume_cursor(self):
        rows = [record(8), record(2), record(4)]
        results, _ = setup(rows)
        status, payload = results.snapshot(binding(), results.generation)
        self.assertEqual(status, "ok")
        self.assertEqual([item["result_id"] for item in payload["items"]],
                         sorted(row.result_id for row in rows))
        self.assertEqual(len(payload["cursor"]), 43)
        self.assertEqual(payload["content_watermark"], 3)

    def test_snapshot_bounds_25_and_rejects_26_without_partial_result(self):
        results, _ = setup([record(n) for n in range(1, 26)])
        status, payload = results.snapshot(binding(), results.generation)
        self.assertEqual((status, len(payload["items"])), ("ok", 25))
        with self.assertRaises(ValueError):
            setup([record(n) for n in range(1, 27)])

    def test_duplicate_identity_and_unclassified_selected_record_fail_closed(self):
        duplicate = [record(1), record(1, revision=2)]
        grant = PhoneResultCollectionGrantV1(OWNER, DEVICE, GRANT, ident(9001), (ident(1),))
        results = PhoneRemoteResults(grant, SyntheticResultsSource(duplicate), clock=lambda: 1.0)
        self.assertEqual(results.snapshot(binding(), results.generation)[0], "authority_unavailable")
        unclassified, _ = setup([record(2, classification="unclassified")])
        self.assertEqual(unclassified.prepare_snapshot(binding(), unclassified.generation)[0],
                         "authority_unavailable")

    def test_protected_canary_does_not_change_visible_watermark_or_bytes(self):
        results, source = setup([record(1), record(2, classification="protected")])
        status, first = results.snapshot(binding(), results.generation)
        self.assertEqual(status, "ok")
        source.replace([record(1), record(2, revision=99, classification="protected")])
        status, second = results.snapshot(binding(), results.generation)
        self.assertEqual(status, "ok")
        self.assertEqual(len(first["items"]), 1)
        self.assertEqual(first["content_watermark"], second["content_watermark"])
        self.assertEqual(first["collection_epoch"], second["collection_epoch"])
        self.assertEqual(first["items"], second["items"])

    def test_snapshot_then_update_resume_and_historical_receipt_replay(self):
        results, source = setup([record(1)])
        _, snap = results.snapshot(binding(), results.generation)
        source.replace([record(1, revision=2, title="updated")])
        status, page = results.resume(binding(), results.generation, snap["cursor"])
        self.assertEqual(status, "ok")
        self.assertEqual(page["events"][0]["item"]["revision"], 2)
        source.replace([record(1, revision=3, title="later")])
        status, replay = results.resume(binding(), results.generation, snap["cursor"])
        self.assertEqual(status, "ok")
        self.assertEqual(replay, page)

    def test_snapshot_observed_ordinary_revisions_are_paginated_in_frozen_high_water(self):
        rows = [record(1)]
        results, source = setup(rows)
        _, snap = results.snapshot(binding(), results.generation)
        for revision in range(2, 31):
            source.replace([record(1, revision=revision, title=f"r{revision}")])
        status, first = results.resume(binding(), results.generation, snap["cursor"])
        self.assertEqual(status, "ok")
        self.assertEqual(len(first["events"]), MAX_PAGE)
        self.assertTrue(first["has_more"])
        status, second = results.resume(binding(), results.generation, first["cursor"])
        self.assertEqual(status, "ok")
        self.assertFalse(second["has_more"])
        self.assertEqual([e["item"]["revision"] for e in first["events"]], list(range(2, 27)))
        self.assertEqual([e["item"]["revision"] for e in second["events"]], list(range(27, 31)))

    def test_selected_source_identity_replacement_rotates_epoch_and_returns_reset(self):
        results, source = setup([record(1)])
        _, snap = results.snapshot(binding(), results.generation)
        source.replace([])
        status, reset = results.resume(binding(), results.generation, snap["cursor"])
        self.assertEqual(status, "reset")
        self.assertEqual(reset["reset_required"], True)
        self.assertEqual(set(reset), {"generation", "collection_epoch", "reset_required"})

    def test_current_visibility_change_withholds_cached_historical_content(self):
        results, source = setup([record(1)])
        _, snap = results.snapshot(binding(), results.generation)
        source.replace([record(1, revision=2, title="ordinary update")])
        _, page = results.resume(binding(), results.generation, snap["cursor"])
        source.replace([record(1, revision=3, classification="protected")])
        self.assertFalse(results.cached_content_authorized(binding(), {"payload": page}))

    def test_binding_scope_and_grant_are_checked_from_server_context(self):
        results, _ = setup([record(1)])
        self.assertEqual(results.snapshot(binding(device="other"), results.generation)[0], "not_authorized")
        self.assertEqual(results.snapshot(binding(scopes=("voice",)), results.generation)[0], "not_authorized")
        self.assertEqual(results.snapshot(binding(grant="other"), results.generation)[0], "not_authorized")

    def test_grant_replacement_invalidates_old_cursor_without_content(self):
        results, _ = setup([record(1)])
        _, snap = results.snapshot(binding(), results.generation)
        replacement = PhoneResultCollectionGrantV1(OWNER, DEVICE, GRANT, ident(9002), (ident(1),), version=2)
        results.replace_grant(replacement)
        status, reset = results.resume(binding(), results.generation, snap["cursor"])
        self.assertEqual(status, "reset")
        self.assertEqual(set(reset), {"generation", "collection_epoch", "reset_required"})

    def test_cursor_replay_is_binding_bound_and_tokens_are_canonical(self):
        results, _ = setup([record(1)])
        _, snap = results.snapshot(binding(), results.generation)
        self.assertEqual(results.resume(binding(session="other"), results.generation, snap["cursor"])[0], "reset")
        self.assertEqual(results.prepare_resume(binding(), results.generation, "=" * 43)[0],
                         "malformed_request")
        self.assertEqual(results.prepare_resume(binding(), results.generation,
            "A" * 42 + "B")[0], "malformed_request")

    def test_cached_receipt_is_invalidated_by_collection_epoch_and_visibility_history(self):
        for transition in ("protected_round_trip", "removed_reinserted", "grant_replaced"):
            with self.subTest(transition=transition):
                results, source = setup([record(1)])
                _, snapshot = results.snapshot(binding(), results.generation)
                if transition == "protected_round_trip":
                    source.replace([record(1, revision=2, classification="protected")])
                    source.replace([record(1, revision=3, title="visible again")])
                elif transition == "removed_reinserted":
                    source.replace([])
                    source.replace([record(1, revision=2, title="reinserted")])
                else:
                    results.replace_grant(PhoneResultCollectionGrantV1(
                        OWNER, DEVICE, GRANT, ident(9001), (ident(1),), version=2))
                self.assertFalse(results.cached_content_authorized(
                    binding(), {"payload": snapshot}))

    def test_committed_cursor_replay_reconciles_visibility_round_trip(self):
        results, source = setup([record(1)])
        _, snapshot = results.snapshot(binding(), results.generation)
        source.replace([record(1, revision=2, title="ordinary update")])
        self.assertEqual(results.resume(binding(), results.generation, snapshot["cursor"])[0], "ok")
        source.replace([record(1, revision=3, classification="protected")])
        source.replace([record(1, revision=4, title="visible again")])
        status, reset = results.resume(binding(), results.generation, snapshot["cursor"])
        self.assertEqual(status, "reset")
        self.assertTrue(reset["reset_required"])

    def test_removed_member_snapshot_tracks_remaining_published_membership(self):
        results, source = setup([record(1), record(2)])
        _, first = results.snapshot(binding(), results.generation)
        source.replace([record(1, revision=2)])
        _, after_removal = results.snapshot(binding(), results.generation)
        self.assertEqual([item["result_id"] for item in after_removal["items"]], [ident(1)])
        source.replace([record(1, revision=3, classification="protected")])
        source.replace([record(1, revision=4)])
        self.assertFalse(results.cached_content_authorized(binding(), {"payload": after_removal}))
        self.assertFalse(results.cached_content_authorized(binding(), {"payload": first}))

    def test_ordinary_history_retention_preserves_cached_receipts_but_resets_old_cursor(self):
        results, source = setup([record(1)])
        _, snapshot = results.snapshot(binding(), results.generation)
        source.replace([record(1, revision=2)])
        _, page = results.resume(binding(), results.generation, snapshot["cursor"])
        for revision in range(3, 302):
            source.replace([record(1, revision=revision)])
        self.assertTrue(results.cached_content_authorized(binding(), {"payload": snapshot}))
        self.assertEqual(results.resume(binding(), results.generation, snapshot["cursor"]),
                         ("ok", page))
        results.snapshot(binding(), results.generation)
        self.assertEqual(results.resume(binding(), results.generation, snapshot["cursor"]),
                         ("ok", page), "committed historical receipt remains replayable")
        status, reset = results.resume(binding(), results.generation, page["cursor"])
        self.assertEqual(status, "reset")
        self.assertTrue(reset["reset_required"])

    def test_fresh_snapshot_retires_uncommitted_cursor_after_history_truncation(self):
        results, source = setup([record(1)])
        _, old_snapshot = results.snapshot(binding(), results.generation)
        for revision in range(2, 302):
            source.replace([record(1, revision=revision, title=f"revision-{revision}")])
        _, fresh_snapshot = results.snapshot(binding(), results.generation)
        status, reset = results.resume(binding(), results.generation, old_snapshot["cursor"])
        self.assertEqual(status, "reset")
        self.assertTrue(reset["reset_required"])
        self.assertEqual(results.resume(binding(), results.generation, fresh_snapshot["cursor"])[0],
                         "ok")

    def test_excluded_source_churn_does_not_invalidate_selected_receipt(self):
        selected, excluded = record(1), record(2, classification="protected")
        results, source = setup([selected, excluded])
        _, snapshot = results.snapshot(binding(), results.generation)
        for revision in range(2, 302):
            source.replace([selected, record(2, revision=revision, classification="protected")])
        self.assertTrue(results.cached_content_authorized(binding(), {"payload": snapshot}))
        self.assertEqual(results.snapshot(binding(), results.generation)[0], "ok")
        status, page = results.resume(binding(), results.generation, snapshot["cursor"])
        self.assertEqual(status, "ok")
        self.assertFalse(any(event["item"]["result_id"] == ident(2)
                             for event in page["events"]))

    def test_prepared_snapshot_rejects_selected_source_change_but_ignores_unselected_change(self):
        results, source = setup([record(1)])
        status, candidate = results.prepare_snapshot(binding(), results.generation)
        self.assertEqual(status, "ok")
        source.replace([record(1, revision=2, classification="protected")])
        self.assertEqual(results.snapshot(binding(), results.generation,
            candidate=candidate)[0], "authority_unavailable")

        results, source = setup([record(1)])
        status, candidate = results.prepare_snapshot(binding(), results.generation)
        self.assertEqual(status, "ok")
        source.replace([record(1), record(2, revision=2, title="excluded change")])
        self.assertEqual(results.snapshot(binding(), results.generation,
            candidate=candidate)[0], "ok")

    def test_source_revision_must_advance_and_history_is_bounded_before_resume(self):
        results, source = setup([record(1)])
        _, snapshot = results.snapshot(binding(), results.generation)
        with self.assertRaises(ValueError):
            source.replace([record(1, title="same revision changed")])
        for revision in range(2, 2_002):
            source.replace([record(1, revision=revision, title=f"revision-{revision}")])
        self.assertLessEqual(len(source._history), 256)
        status, page = results.resume(binding(), results.generation, snapshot["cursor"])
        self.assertEqual(status, "reset")
        self.assertTrue(page["reset_required"])
        self.assertEqual(results.snapshot(binding(), results.generation)[0], "ok")

    def test_byte_retention_resets_before_partial_page_and_fresh_snapshot_still_works(self):
        from unittest.mock import patch
        results, source = setup([record(1)])
        _, snapshot = results.snapshot(binding(), results.generation)
        source.replace([record(1, revision=2, body="x" * 256)])
        with patch("jarvis.bot.phone_remote_results.MAX_JOURNAL_BYTES", 1):
            status, page = results.resume(binding(), results.generation, snapshot["cursor"])
        self.assertEqual(status, "reset")
        self.assertTrue(page["reset_required"])
        self.assertEqual(page.keys(), {"generation", "collection_epoch", "reset_required"})
        self.assertEqual(results.snapshot(binding(), results.generation)[0], "ok")


if __name__ == "__main__":
    unittest.main()

    def test_command_capture_preserves_snapshot_resume_history_and_hides_unselected_activity(self):
        results,source=setup([record(1),record(2,classification='protected')])
        _,snapshot=results.snapshot(binding(),results.generation)
        state=results.command_state(binding())
        source.replace([record(1,revision=2),record(2,revision=2,classification='protected'),record(9)])
        changed=results.command_state(binding())
        self.assertEqual(state[:4],changed[:4]);self.assertNotEqual(state[4],changed[4])
        status,page=results.resume(binding(),results.generation,snapshot['cursor'])
        self.assertEqual(status,'ok');self.assertEqual([e['item']['revision'] for e in page['events']],[2])
        source.replace([record(1,revision=2),record(2,revision=3,classification='protected')])
        self.assertEqual(changed,results.command_state(binding()))
        self.assertEqual(results.resume(binding(),results.generation,snapshot['cursor'])[1],page)
