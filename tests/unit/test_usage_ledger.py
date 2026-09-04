"""Unit tests for jarvis/usage_ledger.py's record_completion() adapter
(MORTIMER_OPTIMIZATION_PLAN.md Phase 1, Rev 3.2, landing step (i), task 3).

Scope: the two bugs that go live once caching is on — record_completion()
previously subtracted cache READS but not cache WRITES from input_tokens
(double-billing writes at both the 1.25x/2.0x cache-write multiplier and
the full 1.0x input rate), and _CACHE_WRITE_ALIASES did not know about the
`prompt_tokens_details.cache_write_tokens` shape (OpenRouter, and now
jarvis/anthropic_shim.py's own _convert_response()).

record_call() (the actual SQLite write) is monkeypatched out in every
test — this file never touches data/costs.db or config/model_prices.yaml.
Usage objects are exercised as both plain dicts and attribute objects
(SimpleNamespace) since _get() supports both and real call sites see both
(a dict from a raw JSON response, a pydantic/attrs object from an SDK).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from jarvis import usage_ledger


@pytest.fixture
def captured_calls(monkeypatch):
    calls = []

    def _fake_record_call(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(usage_ledger, "record_call", _fake_record_call)
    return calls


def _response(usage):
    return SimpleNamespace(id="resp_1", usage=usage)


class TestRecordCompletionInputTokensFormula:
    def test_no_cache_activity_unchanged(self, captured_calls):
        # Pre-caching baseline (today's compat-layer behaviour): no cache
        # fields present at all -> input_tokens == prompt_tokens, exactly
        # as before this fix.
        usage_ledger.record_completion(
            rung="supervisor", provider="anthropic", model="claude-haiku-4-5",
            response=_response({"prompt_tokens": 500, "completion_tokens": 40}),
        )
        call = captured_calls[0]
        assert call["input_tokens"] == 500
        assert call["cache_read_tokens"] == 0
        assert call["cache_write_tokens"] == 0

    def test_cache_read_only_regression(self, captured_calls):
        # Today's only live case (OpenAI/OpenRouter cached_tokens, no
        # writes reported) -- must be unchanged by this fix.
        usage_ledger.record_completion(
            rung="supervisor", provider="openai", model="gpt-x",
            response=_response({
                "prompt_tokens": 1000, "completion_tokens": 40,
                "prompt_tokens_details": {"cached_tokens": 300},
            }),
        )
        call = captured_calls[0]
        assert call["cache_read_tokens"] == 300
        assert call["cache_write_tokens"] == 0
        assert call["input_tokens"] == 1000 - 300

    def test_cache_write_subtracted_dict_top_level_alias(self, captured_calls):
        # Native anthropic-shim / pipecat shape: cache_creation_input_tokens
        # at the top level of usage, alongside prompt_tokens_details.cached_tokens.
        usage_ledger.record_completion(
            rung="developer", provider="anthropic", model="claude-sonnet-5",
            response=_response({
                "prompt_tokens": 1000, "completion_tokens": 40,
                "prompt_tokens_details": {"cached_tokens": 300},
                "cache_creation_input_tokens": 150,
            }),
        )
        call = captured_calls[0]
        assert call["cache_read_tokens"] == 300
        assert call["cache_write_tokens"] == 150
        # Before the fix this would have been 1000 - 300 = 700, double
        # billing the 150 write tokens at both 1.0x and the write multiplier.
        assert call["input_tokens"] == 1000 - 300 - 150

    def test_cache_write_subtracted_openrouter_nested_alias(self, captured_calls):
        # OpenRouter / jarvis/anthropic_shim.py's own shape: BOTH cache
        # fields live inside prompt_tokens_details, no top-level
        # cache_creation_input_tokens at all.
        usage_ledger.record_completion(
            rung="council", provider="openrouter", model="anthropic/claude-sonnet-5",
            response=_response({
                "prompt_tokens": 2000, "completion_tokens": 80,
                "prompt_tokens_details": {"cached_tokens": 500, "cache_write_tokens": 200},
            }),
        )
        call = captured_calls[0]
        assert call["cache_read_tokens"] == 500
        assert call["cache_write_tokens"] == 200
        assert call["input_tokens"] == 2000 - 500 - 200

    def test_cache_write_and_read_via_attribute_object(self, captured_calls):
        # SimpleNamespace stand-in for a pydantic CompletionUsage /
        # PromptTokensDetails object (what a real openai.types.chat.
        # ChatCompletion.usage actually is, including the object returned
        # by jarvis/anthropic_shim.py's _convert_response()).
        usage = SimpleNamespace(
            prompt_tokens=1500, completion_tokens=60,
            prompt_tokens_details=SimpleNamespace(cached_tokens=400, cache_write_tokens=100),
        )
        usage_ledger.record_completion(
            rung="selfedit_executor", provider="anthropic", model="claude-sonnet-5",
            response=_response(usage),
        )
        call = captured_calls[0]
        assert call["cache_read_tokens"] == 400
        assert call["cache_write_tokens"] == 100
        assert call["input_tokens"] == 1500 - 400 - 100

    def test_input_tokens_never_negative(self, captured_calls):
        # Defensive: if a provider ever reports cache tokens that sum to
        # more than prompt_tokens (has happened with rounding on other
        # providers per the existing max(...,0) guard), clamp to zero
        # rather than recording a negative token count.
        usage_ledger.record_completion(
            rung="supervisor", provider="anthropic", model="claude-haiku-4-5",
            response=_response({
                "prompt_tokens": 100, "completion_tokens": 10,
                "prompt_tokens_details": {"cached_tokens": 80},
                "cache_creation_input_tokens": 50,
            }),
        )
        call = captured_calls[0]
        assert call["input_tokens"] == 0

    def test_top_level_alias_takes_priority_over_nested_when_both_present(self, captured_calls):
        # _find_first walks _CACHE_WRITE_ALIASES in order; the top-level
        # cache_creation_input_tokens alias is checked before the nested
        # prompt_tokens_details.cache_write_tokens one. Real responses
        # only ever populate one or the other, but the priority itself
        # should stay stable and documented by a test.
        usage_ledger.record_completion(
            rung="supervisor", provider="anthropic", model="claude-haiku-4-5",
            response=_response({
                "prompt_tokens": 1000, "completion_tokens": 10,
                "cache_creation_input_tokens": 111,
                "prompt_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 222},
            }),
        )
        call = captured_calls[0]
        assert call["cache_write_tokens"] == 111

    def test_missing_usage_does_not_raise(self, captured_calls):
        usage_ledger.record_completion(
            rung="supervisor", provider="anthropic", model="claude-haiku-4-5",
            response=SimpleNamespace(id="resp_1"),
        )
        call = captured_calls[0]
        assert call["input_tokens"] == 0
        assert call["cache_write_tokens"] == 0
        assert call["cache_read_tokens"] == 0

    def test_gen_id_falls_back_to_response_id(self, captured_calls):
        usage_ledger.record_completion(
            rung="supervisor", provider="anthropic", model="claude-haiku-4-5",
            response=_response({"prompt_tokens": 10, "completion_tokens": 1}),
        )
        assert captured_calls[0]["gen_id"] == "resp_1"


class TestCacheWriteAliases:
    def test_alias_tuple_has_both_shapes(self):
        assert (None, "cache_creation_input_tokens") in usage_ledger._CACHE_WRITE_ALIASES
        assert ("prompt_tokens_details", "cache_write_tokens") in usage_ledger._CACHE_WRITE_ALIASES


# ------------------------- Phase 3 Rev 3.3: plan_state on executor rows

class TestPlanState:
    def test_record_completion_passes_plan_state_through(self, captured_calls):
        usage_ledger.record_completion(
            rung="selfedit_executor", provider="anthropic", model="claude-sonnet-5",
            response=_response({"prompt_tokens": 10, "completion_tokens": 1}),
            plan_state="planned",
        )
        assert captured_calls[0]["plan_state"] == "planned"

    def test_record_completion_default_plan_state_is_none(self, captured_calls):
        usage_ledger.record_completion(
            rung="supervisor", provider="anthropic", model="claude-haiku-4-5",
            response=_response({"prompt_tokens": 10, "completion_tokens": 1}),
        )
        assert captured_calls[0]["plan_state"] is None

    def test_plan_state_round_trips_through_sqlite(self, tmp_path, monkeypatch):
        """The real write path, against a fresh temp ledger."""
        monkeypatch.setattr(usage_ledger, "DB_PATH", tmp_path / "costs.db")
        usage_ledger.record_call(
            rung="selfedit_executor", provider="anthropic", model="claude-sonnet-5",
            input_tokens=5, output_tokens=1, plan_state="planless",
        )
        usage_ledger.record_call(
            rung="supervisor", provider="anthropic", model="claude-haiku-4-5",
            input_tokens=5, output_tokens=1,
        )
        conn = usage_ledger._conn()
        try:
            rows = conn.execute(
                "SELECT rung, plan_state FROM llm_calls ORDER BY id"
            ).fetchall()
        finally:
            conn.close()
        assert rows == [("selfedit_executor", "planless"), ("supervisor", None)]

    def test_existing_ledger_without_the_column_is_upgraded_in_place(
        self, tmp_path, monkeypatch,
    ):
        """Larry's data/costs.db predates plan_state. CREATE TABLE IF NOT
        EXISTS does nothing for an existing file, so _conn() must add the
        column itself — once — and keep every existing row intact."""
        import sqlite3
        db = tmp_path / "old.db"
        old_schema = _schema_without(("plan_state", "quantity", "unit"))
        assert "plan_state" not in old_schema  # the helper actually removed it
        legacy = sqlite3.connect(db)
        legacy.executescript(old_schema)
        legacy.execute(
            "INSERT INTO llm_calls (ts, month, rung, provider, model) "
            "VALUES ('2026-09-01T00:00:00+00:00', '2026-09', 'supervisor', 'anthropic', 'm')"
        )
        legacy.commit(); legacy.close()

        monkeypatch.setattr(usage_ledger, "DB_PATH", db)
        conn = usage_ledger._conn()   # first connect: adds the column
        conn.close()
        conn = usage_ledger._conn()   # second connect: must be a no-op, not a failure
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(llm_calls)")}
            assert "plan_state" in cols
            assert conn.execute("SELECT COUNT(*) FROM llm_calls").fetchone()[0] == 1
            assert conn.execute("SELECT plan_state FROM llm_calls").fetchone()[0] is None
        finally:
            conn.close()


def _schema_without(columns: tuple[str, ...]) -> str:
    """usage_ledger._SCHEMA with the named trailing columns removed — the
    shape of a ledger file written before those columns existed. Rebuilds
    the CREATE TABLE from its column lines so the test does not depend on
    the exact comment text of the current schema."""
    lines = usage_ledger._SCHEMA.splitlines()
    out: list[str] = []
    skipping = False
    for line in lines:
        stripped = line.strip()
        name = stripped.split(" ")[0] if stripped else ""
        if name in columns:
            skipping = True   # drop this column line and its continuation comments
            continue
        if skipping and stripped.startswith("--"):
            continue
        skipping = False
        out.append(line)
    # Whatever column now ends the list must lose its trailing comma. Walk
    # back from ");" over continuation comments to the last column line.
    close = next(i for i, line in enumerate(out) if line.strip() == ");")
    i = close - 1
    while out[i].strip().startswith("--"):
        i -= 1
    head, _, comment = out[i].partition("--")
    head = head.rstrip()
    if head.endswith(","):
        head = head[:-1]
    out[i] = head + ("  --" + comment if comment else "")
    return "\n".join(out)


class TestVoiceTransportRows:
    """MORTIMER_SESSION_MISSES_PLAN.md S1/S4 — tts/stt rows carry
    quantity/unit, zero tokens, and are priced per natural unit."""

    @pytest.fixture
    def voice_prices(self, monkeypatch):
        monkeypatch.setattr(usage_ledger, "_price_map_cache", {"models": {
            "elevenlabs/eleven_flash_v2_5": {"unit": "chars", "usd_per_1k_chars": 0.10},
            "deepgram/flux-general-en": {"unit": "seconds", "usd_per_minute": 0.0077},
            "anthropic/claude-haiku-4-5": {"input_per_m": 1.0, "output_per_m": 5.0},
        }})

    def test_voice_row_prices_chars_per_1k(self, tmp_path, monkeypatch, voice_prices):
        monkeypatch.setattr(usage_ledger, "DB_PATH", tmp_path / "costs.db")
        usage_ledger.record_call(
            rung="tts", provider="elevenlabs", model="eleven_flash_v2_5",
            session_id="s1", quantity=2409, unit="chars",
        )
        conn = usage_ledger._conn()
        try:
            row = conn.execute(
                "SELECT quantity, unit, input_tokens, output_tokens, "
                "cache_write_tokens, cache_read_tokens, computed_cost FROM llm_calls"
            ).fetchone()
        finally:
            conn.close()
        assert row[0] == 2409.0 and row[1] == "chars"
        assert row[2:6] == (0, 0, 0, 0)
        assert row[6] == pytest.approx(0.2409)

    def test_voice_row_prices_seconds_per_minute(self, tmp_path, monkeypatch, voice_prices):
        monkeypatch.setattr(usage_ledger, "DB_PATH", tmp_path / "costs.db")
        usage_ledger.record_call(
            rung="stt", provider="deepgram", model="flux-general-en",
            quantity=165, unit="seconds",
        )
        conn = usage_ledger._conn()
        try:
            cost, = conn.execute("SELECT computed_cost FROM llm_calls").fetchone()
        finally:
            conn.close()
        assert cost == pytest.approx(165 / 60 * 0.0077)

    def test_voice_row_with_token_only_entry_is_unpriced(self, voice_prices):
        # A mapped model whose entry has no unit price: unpriced, never free
        # (and never the token arithmetic — that would price 2,409 "input
        # tokens" of speech at Haiku's rate).
        assert usage_ledger.compute_cost(
            "anthropic", "claude-haiku-4-5", 0, 0, quantity=2409, unit="chars",
        ) is None

    def test_voice_row_with_wrong_unit_is_unpriced(self, voice_prices):
        # unit/price mismatch (seconds against a per-1K-chars entry) is a
        # caller bug that must surface as a gap, not a number.
        assert usage_ledger.compute_cost(
            "elevenlabs", "eleven_flash_v2_5", 0, 0, quantity=60, unit="seconds",
        ) is None

    def test_token_rows_have_null_quantity_and_unit(self, tmp_path, monkeypatch, voice_prices):
        monkeypatch.setattr(usage_ledger, "DB_PATH", tmp_path / "costs.db")
        usage_ledger.record_call(
            rung="supervisor", provider="anthropic", model="claude-haiku-4-5",
            input_tokens=6, output_tokens=24, cache_write_tokens=8500,
        )
        conn = usage_ledger._conn()
        try:
            row = conn.execute("SELECT quantity, unit, computed_cost FROM llm_calls").fetchone()
        finally:
            conn.close()
        assert row[0] is None and row[1] is None
        assert row[2] == pytest.approx(6 * 1e-6 + 8500 * 1e-6 * 1.25 + 24 * 5e-6)

    def test_conn_adds_quantity_and_unit_columns_in_place(self, tmp_path, monkeypatch):
        """A ledger written by the Rev 3.3 code has plan_state but neither
        voice column; _conn() must add both, once, keeping existing rows."""
        import sqlite3
        db = tmp_path / "rev33.db"
        legacy = sqlite3.connect(db)
        legacy.executescript(_schema_without(("quantity", "unit")))
        legacy.execute(
            "INSERT INTO llm_calls (ts, month, rung, provider, model, plan_state) "
            "VALUES ('2026-09-03T00:00:00+00:00', '2026-09', 'selfedit_executor', "
            "'anthropic', 'm', 'planless')"
        )
        legacy.commit(); legacy.close()

        monkeypatch.setattr(usage_ledger, "DB_PATH", db)
        usage_ledger._conn().close()   # adds the columns
        conn = usage_ledger._conn()    # idempotent
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(llm_calls)")}
            assert {"quantity", "unit", "plan_state"} <= cols
            assert conn.execute(
                "SELECT plan_state, quantity, unit FROM llm_calls"
            ).fetchone() == ("planless", None, None)
        finally:
            conn.close()

    def test_tts_and_stt_are_known_rungs(self):
        assert "tts" in usage_ledger.RUNGS and "stt" in usage_ledger.RUNGS
