"""Unit tests for jarvis/bot/display.py (display-panel payloads)."""

import json
import pytest

from jarvis.bot.display import (
    DEFAULT_DISPLAY_SURFACE,
    DISPLAY_SURFACE,
    build_display_payload,
)


def build(tool, data, args=None, result=None):
    return build_display_payload(
        agent="analyst",
        display_name="Analyst",
        tool=tool,
        arguments=args or {},
        result_str=result if result is not None else json.dumps(data),
    )


def build_with_run(tool, data, run_id, agent="developer", display_name="Developer", args=None):
    return build_display_payload(
        agent=agent,
        display_name=display_name,
        tool=tool,
        arguments=args or {},
        result_str=json.dumps(data),
        run_id=run_id,
    )


class TestGuards:
    def test_unknown_tool_returns_none(self):
        assert build("git_status", {"branch": "main"}) is None

    def test_invalid_json_returns_none(self):
        assert build("web_search", None, result="not json") is None

    def test_error_dict_returns_none(self):
        assert build("web_search", {"error": "Web search is unavailable."}) is None

    def test_ok_false_returns_none(self):
        assert build("app_create", {"ok": False, "error": "repo exists"}) is None

    def test_non_dict_returns_none(self):
        assert build("web_search", None, result="[1, 2]") is None


class TestWebSearch:
    DATA = {
        "answer": "The answer is 42.",
        "results": [
            {"title": "Source A", "url": "https://a.example", "snippet": "aaa"},
            {"title": "Source B", "url": "https://b.example", "snippet": "bbb"},
        ],
    }

    def test_payload_shape(self):
        p = build("web_search", self.DATA, args={"query": "meaning of life"})
        assert p is not None
        assert p["kind"] == "markdown"
        assert p["title"] == "Research — meaning of life"
        assert "The answer is 42." in p["body"]
        assert "Source A" in p["body"]
        assert p["images"] == []
        assert [l["url"] for l in p["links"]] == [
            "https://a.example", "https://b.example",
        ]
        assert p["agent"] == "Analyst"
        assert p["ts"] > 0
        # Engagement plan E1 — additive tool field: the client's
        # attention rule (draft-gated tools) and ambient weather cache
        # both key off which tool produced the payload.
        assert p["tool"] == "web_search"

    def test_run_id_is_carried_for_presentation_grouping(self):
        p = build_with_run("web_search", self.DATA, "run-42")
        assert p["run_id"] == "run-42"

    def test_empty_result_returns_none(self):
        assert build("web_search", {"answer": "", "results": []}) is None


class TestGetWeather:
    # W2 (MORTIMER_WEATHER_FAHRENHEIT_AND_RADAR_PLAN.md): the payload
    # always carries BOTH unit sets plus a `units` field naming which is
    # primary — this is the shape get_weather actually returns now.
    DATA = {
        "city": "Tokyo, Japan",
        "units": "imperial",
        "human": "In Tokyo, Japan it's currently 86°F and partly cloudy.",
        "daily": [
            {"date": "2026-08-11", "max_f": 91, "min_f": 77,
             "max_c": 33, "min_c": 25,
             "precip_probability": 20, "condition": "partly cloudy"},
        ],
    }

    def test_table_rendered(self):
        p = build("get_weather", self.DATA, args={"city": "tokyo"})
        assert p["kind"] == "markdown"
        assert p["title"] == "Weather — Tokyo, Japan"
        assert "86°F" in p["body"]
        assert "| 2026-08-11 | 91°F | 77°F | 20% | partly cloudy |" in p["body"]

    def test_table_follows_units_field(self):
        """W3: the formatter reads the payload's OWN `units` field — it
        never guesses from which keys happen to be present (W2 guarantees
        both f/c are always there together)."""
        metric_data = dict(self.DATA, units="metric",
                            human="In Tokyo, Japan it's currently 30°C and partly cloudy.")
        p = build("get_weather", metric_data, args={"city": "tokyo"})
        assert "30°C" in p["body"]
        assert "| 2026-08-11 | 33°C | 25°C | 20% | partly cloudy |" in p["body"]
        assert "°F" not in p["body"]

    def test_missing_units_field_defaults_to_imperial(self):
        data = {k: v for k, v in self.DATA.items() if k != "units"}
        p = build("get_weather", data, args={"city": "tokyo"})
        assert "91°F" in p["body"]


class TestGetWeatherRadar:
    DATA = {
        "city": "Berlin, Germany",
        "lat": 52.52, "lon": 13.4, "ts": 1754900000,
        "tiles": [f"https://tilecache.rainviewer.com/t{i}.png" for i in range(9)],
        "basemap_tiles": [f"https://a.basemaps.cartocdn.com/b{i}.png" for i in range(9)],
    }

    def test_image_payload(self):
        p = build("get_weather_radar", self.DATA, args={"city": "berlin"})
        assert p["kind"] == "image"
        assert p["title"] == "Radar — Berlin, Germany"
        assert len(p["images"]) == 9
        assert "Berlin, Germany" in p["body"]

    def test_no_tiles_returns_none(self):
        assert build("get_weather_radar", {"city": "X", "tiles": []}) is None

    def test_basemap_images_passed_through(self):
        """W6: the payload carries the basemap tiles the frontend stacks
        underneath the precipitation overlay."""
        p = build("get_weather_radar", self.DATA, args={"city": "berlin"})
        assert len(p["basemap_images"]) == 9
        assert p["basemap_images"][0].startswith("https://a.basemaps.cartocdn.com/")

    def test_missing_basemap_tiles_defaults_to_empty(self):
        data = {k: v for k, v in self.DATA.items() if k != "basemap_tiles"}
        p = build("get_weather_radar", data, args={"city": "berlin"})
        assert p["basemap_images"] == []


class TestWeatherReport:
    """W5 — the merged get_weather + get_weather_radar card."""

    WEATHER = TestGetWeather.DATA
    RADAR = TestGetWeatherRadar.DATA

    def test_merges_conditions_and_radar(self):
        p = build("weather_report", {"weather": self.WEATHER, "radar": self.RADAR})
        assert p is not None
        # WS-15 PR 2: a card with conditions carries the structured view.
        assert p["kind"] == "weather" and p["weather"]["schema"] == 1
        assert len(p["images"]) == 9
        assert "86°F" in p["body"]
        assert "Latest precipitation radar" in p["body"]
        assert p["title"] == "Weather — Tokyo, Japan"

    def test_survives_missing_radar(self):
        """Never suppress the answer — a lone conditions result still
        renders as a (markdown-only) card."""
        p = build("weather_report", {"weather": self.WEATHER, "radar": None})
        assert p is not None
        # WS-15 PR 2: a card with conditions carries the structured view.
        assert p["kind"] == "weather" and p["weather"]["schema"] == 1
        assert p["images"] == []
        assert "86°F" in p["body"]

    def test_survives_missing_weather(self):
        p = build("weather_report", {"weather": None, "radar": self.RADAR})
        assert p is not None
        assert p["kind"] == "image"
        assert len(p["images"]) == 9

    def test_both_missing_returns_none(self):
        assert build("weather_report", {"weather": None, "radar": None}) is None

    def test_basemap_images_carried_through_merge(self):
        p = build("weather_report", {"weather": self.WEATHER, "radar": self.RADAR})
        assert len(p["basemap_images"]) == 9


class TestWeatherReportMerger:
    """W5 — the pairing/flush state machine itself, independent of the
    formatter tested above."""

    def _merger(self):
        from jarvis.bot.display import WeatherReportMerger
        return WeatherReportMerger()

    def test_waits_for_the_pair(self):
        m = self._merger()
        first = m.offer("run-1", "analyst", "Analyst", "get_weather",
                         json.dumps(TestGetWeather.DATA))
        assert first is None  # still waiting on radar

    def test_emits_once_both_arrive(self):
        m = self._merger()
        m.offer("run-1", "analyst", "Analyst", "get_weather",
                 json.dumps(TestGetWeather.DATA))
        second = m.offer("run-1", "analyst", "Analyst", "get_weather_radar",
                          json.dumps(TestGetWeatherRadar.DATA))
        assert second is not None
        # WS-15 PR 2: a card with conditions carries the structured view.
        assert second["kind"] == "weather" and second["weather"]["schema"] == 1
        assert "86°F" in second["body"]

    def test_radar_error_still_finalizes_with_conditions_only(self):
        m = self._merger()
        m.offer("run-1", "analyst", "Analyst", "get_weather",
                 json.dumps(TestGetWeather.DATA))
        result = m.offer("run-1", "analyst", "Analyst", "get_weather_radar",
                          json.dumps({"error": "Radar data failed."}))
        assert result is not None
        # WS-15 PR 2: a card with conditions carries the structured view.
        assert result["kind"] == "weather" and result["weather"]["schema"] == 1
        assert "86°F" in result["body"]

    def test_finalize_flushes_a_lone_pending_half(self):
        """A run that only ever calls get_weather (radar tool never
        invoked at all) must still show its answer once the run ends."""
        m = self._merger()
        assert m.offer("run-1", "analyst", "Analyst", "get_weather",
                        json.dumps(TestGetWeather.DATA)) is None
        flushed = m.finalize("run-1")
        assert flushed is not None
        # WS-15 PR 2: a card with conditions carries the structured view.
        assert flushed["kind"] == "weather" and flushed["weather"]["schema"] == 1
        assert "86°F" in flushed["body"]

    def test_finalize_on_empty_run_returns_none(self):
        m = self._merger()
        assert m.finalize("never-existed") is None

    def test_separate_runs_do_not_cross_contaminate(self):
        m = self._merger()
        m.offer("run-A", "analyst", "Analyst", "get_weather",
                 json.dumps(TestGetWeather.DATA))
        # run-B's radar arriving must not complete run-A's pending half,
        # and (having no get_weather half of its own) must still wait.
        result_b = m.offer("run-B", "analyst", "Analyst", "get_weather_radar",
                            json.dumps(TestGetWeatherRadar.DATA))
        assert result_b is None
        # run-A's half is untouched by run-B's activity.
        flushed_a = m.finalize("run-A")
        assert flushed_a is not None
        assert "86°F" in flushed_a["body"]


class TestWeatherReuseMerger:
    def offer(self, merger, tool, city="Alpha", *, ts=0, fresh_until=900, reused=False,
              verified=True, metadata_city=None):
        from jarvis.bot.weather_reuse import named_weather_subject_key
        raw = dict(TestGetWeather.DATA if tool == "get_weather" else TestGetWeatherRadar.DATA,
                   city=f"Nearest provider place for {city}")
        metadata = {"subject_key": named_weather_subject_key(metadata_city or city), "ts": ts,
                    "fresh_until": fresh_until, "reused": reused} if verified else None
        return merger.offer("run-1", "analyst", "Analyst", tool, json.dumps(raw),
                            arguments={"city": city}, metadata=metadata)

    @pytest.mark.parametrize("order", [("get_weather", "get_weather_radar"),
                                      ("get_weather_radar", "get_weather")])
    def test_mixed_cached_and_fetched_halves_keep_original_zero_and_earliest_expiry(self, order):
        from jarvis.bot.display import WeatherReportMerger
        merger = WeatherReportMerger()
        first = self.offer(merger, order[0], ts=0, fresh_until=300, reused=True)
        second = self.offer(merger, order[1], ts=100, fresh_until=1000)
        assert first is None and second is not None
        assert second["ts"] == 0 and second["fresh_until"] == 300
        assert second["subject_key"] == "weather:named:alpha"
        assert second["data_policy"] == "approved_external"
        assert second["weather_source"]["subject_aliases"] == ["alpha"]
        assert second["weather_source"]["radar"]["ts"] == TestGetWeatherRadar.DATA["ts"]
        assert merger.finalize_all("run-1") == []

    def test_all_cached_halves_and_lone_cached_half_do_not_replay_native_arrival(self):
        from jarvis.bot.display import WeatherReportMerger
        merger = WeatherReportMerger()
        assert self.offer(merger, "get_weather", reused=True) is None
        assert self.offer(merger, "get_weather_radar", reused=True) is None
        assert merger.finalize_all("run-1") == []
        assert self.offer(merger, "get_weather", reused=True) is None
        assert merger.finalize_all("run-1") == []
        assert merger._pending == {}

    def test_same_run_different_requested_places_never_merge_and_all_are_flushed(self):
        from jarvis.bot.display import WeatherReportMerger
        merger = WeatherReportMerger()
        assert self.offer(merger, "get_weather", "Alpha") is None
        assert self.offer(merger, "get_weather_radar", "Atlanta") is None
        flushed = merger.finalize_all("run-1")
        assert [payload["subject_key"] for payload in flushed] == ["weather:named:alpha", "weather:named:atlanta"]
        assert flushed[0]["weather_source"]["radar"] is None
        assert flushed[1]["weather_source"]["weather"] is None
        assert merger._pending == {}

    def test_multiple_subjects_in_one_run_pair_only_matching_requested_city(self):
        from jarvis.bot.display import WeatherReportMerger
        merger = WeatherReportMerger()
        assert self.offer(merger, "get_weather", "Alpha") is None
        assert self.offer(merger, "get_weather", "Atlanta") is None
        alpha = self.offer(merger, "get_weather_radar", "ALPHA")
        assert alpha["subject_key"] == "weather:named:alpha"
        assert alpha["weather_source"]["weather"]["city"].endswith("Alpha")
        assert alpha["weather_source"]["radar"]["city"].endswith("ALPHA")
        rest = merger.finalize_all("run-1")
        assert len(rest) == 1 and rest[0]["subject_key"] == "weather:named:atlanta"

    @pytest.mark.parametrize("kind", ["missing", "wrong_subject", "bad_time"])
    def test_unverified_half_never_mints_cache_authority_from_its_display_city(self, kind):
        from jarvis.bot.display import WeatherReportMerger
        merger = WeatherReportMerger()
        assert self.offer(merger, "get_weather") is None
        options = {"verified": False} if kind == "missing" else (
            {"metadata_city": "Atlanta"} if kind == "wrong_subject" else {"fresh_until": 901})
        result = self.offer(merger, "get_weather_radar", **options)
        assert result["subject_key"] == "weather:named:alpha"
        assert not {"weather_source", "fresh_until", "data_policy"}.intersection(result)

    def test_same_subject_tool_failure_keeps_valid_other_half_and_its_original_timing(self):
        from jarvis.bot.display import WeatherReportMerger
        merger = WeatherReportMerger()
        self.offer(merger, "get_weather", ts=0, fresh_until=400)
        result = merger.offer("run-1", "analyst", "Analyst", "get_weather_radar",
                              '{"ok":false,"error":"unavailable"}', arguments={"city": "Alpha"})
        assert result["ts"] == 0 and result["fresh_until"] == 400
        assert result["weather_source"]["radar"] is None

    def test_source_overflow_preserves_legacy_body_and_safe_key_without_cache(self):
        raw = {"weather": {**TestGetWeather.DATA, "human": "x" * (16 * 1024)}, "radar": None}
        result = build_display_payload("analyst", "Analyst", "weather_report", {}, json.dumps(raw),
            weather_metadata={"subject_key": "weather:named:alpha", "ts": 0, "fresh_until": 900})
        assert result["subject_key"] == "weather:named:alpha" and len(result["body"]) > 16 * 1024
        assert "weather_source" not in result and "fresh_until" not in result
        assert result["ts"] == 0 and result["data_policy"] == "approved_external"


class TestAppTools:
    def test_app_create_preview(self):
        data = {
            "ok": True, "pending": True, "proposed_name": "weather-app",
            "template": "web_app", "files": ["index.html", "README.md"],
            "summary": "Ready to create private repo 'weather-app'…",
        }
        p = build("app_create", data, args={"name": "weather-app"})
        assert p["title"] == "Project plan — weather-app"
        assert "`index.html`" in p["body"]

    def test_app_create_done_links_repo(self):
        data = {
            "ok": True, "pending": False, "name": "weather-app",
            "repo_url": "https://github.com/x/weather-app",
            "files": ["index.html"], "commits": ["abc"],
            "summary": "Created private repo …",
        }
        p = build("app_create", data, args={"name": "weather-app"})
        assert p["title"] == "Project created — weather-app"
        assert p["links"][0]["url"] == "https://github.com/x/weather-app"

    def test_app_write_file(self):
        data = {
            "ok": True, "app": "weather-app", "path": "src/App.tsx",
            "action": "update", "commit": "abcdef123456",
            "summary": "Updated src/App.tsx in weather-app.",
        }
        p = build("app_write_file", data,
                  args={"app": "weather-app", "path": "src/App.tsx",
                        "rationale": "fix layout"})
        assert p["title"] == "Code — weather-app/src/App.tsx"
        assert "fix layout" in p["body"]
        assert "abcdef1" in p["body"]


class TestDisplaySurface:
    """Plan D36 — surface routing (window vs drawer)."""

    def test_web_search_is_window(self):
        p = build("web_search", TestWebSearch.DATA, args={"query": "x"})
        assert p["surface"] == "window"

    def test_get_weather_is_window(self):
        p = build("get_weather", TestGetWeather.DATA, args={"city": "tokyo"})
        assert p["surface"] == "window"

    def test_git_diff_summary_is_drawer(self):
        data = {"stat": [" a | 1 +"], "summary_line": "1 file changed"}
        p = build("git_diff_summary", data)
        assert p["surface"] == "drawer"

    def test_app_create_is_drawer(self):
        data = {
            "ok": True, "pending": True, "proposed_name": "weather-app",
            "files": ["index.html"], "summary": "Ready…",
        }
        p = build("app_create", data, args={"name": "weather-app"})
        assert p["surface"] == "drawer"

    def test_unknown_tool_defaults_to_drawer(self):
        # A future tool added to DISPLAY_TOOLS/formatters but not yet
        # classified in DISPLAY_SURFACE must default to the non-intrusive
        # surface (drawer), not silently pop a window (D36 rationale).
        assert DISPLAY_SURFACE.get("some_future_tool", DEFAULT_DISPLAY_SURFACE) == "drawer"
        assert DEFAULT_DISPLAY_SURFACE == "drawer"


class TestGitTools:
    def test_diff_summary(self):
        data = {"stat": [" web/src/App.tsx | 10 +++++-----",
                         " 1 file changed, 5 insertions(+), 5 deletions(-)"],
                "summary_line": " 1 file changed, 5 insertions(+), 5 deletions(-)"}
        p = build("git_diff_summary", data)
        assert p["title"] == "Working tree changes"
        assert "App.tsx" in p["body"]

    def test_diff_summary_empty_returns_none(self):
        assert build("git_diff_summary", {"stat": [], "summary_line": "no changes"}) is None

    def test_prepare_commit(self):
        data = {"ok": True, "action_id": 3,
                "summary": "Commit 2 file(s) on branch 'main'…"}
        p = build("prepare_commit", data)
        assert p["title"] == "Git — draft commit"
        assert "2 file(s)" in p["body"]

    def test_commit_result(self):
        data = {"ok": True, "result": "[main abc1234] ship it"}
        p = build("commit", data)
        assert p["title"] == "Git — committed"
        assert "abc1234" in p["body"]

    def test_push_result(self):
        data = {"ok": True, "result": "To github.com:x/y.git\n   a..b  main -> main"}
        p = build("push", data)
        assert p["title"] == "Git — pushed"


class TestRepoWriteDraft:
    """MORTIMER_PLANNING_PATHWAY_PLAN.md P5 — the phantom-completion fix's
    display half: full draft content in the Output tab, not just a
    summary."""

    def test_draft_shows_full_content_from_arguments(self):
        data = {"ok": True, "pending": True, "action_id": 7,
                 "path": "docs/plans/x.md", "action": "create", "bytes": 42,
                 "summary": "Will create docs/plans/x.md (42 bytes)."}
        args = {"path": "docs/plans/x.md", "content": "# Plan\n\nBody here."}
        p = build("repo_write_file", data, args=args)
        assert p["title"] == "Repo — draft create docs/plans/x.md"
        assert p["body"] == "# Plan\n\nBody here."
        assert p["kind"] == "markdown"

    def test_missing_content_returns_none(self):
        data = {"ok": True, "pending": True, "path": "x.md", "action": "create"}
        assert build("repo_write_file", data, args={"path": "x.md"}) is None

    def test_content_truncated_over_30000_chars(self):
        from jarvis.bot.display import DOC_DISPLAY_MAX_CHARS

        long_content = "x" * (DOC_DISPLAY_MAX_CHARS + 500)
        data = {"ok": True, "pending": True, "path": "big.md", "action": "create"}
        p = build("repo_write_file", data, args={"content": long_content})
        assert len(p["body"]) > DOC_DISPLAY_MAX_CHARS
        assert p["body"].startswith("x" * 100)
        assert "truncated for display" in p["body"]
        assert "the draft itself is complete" in p["body"]

    def test_surface_is_drawer(self):
        assert DISPLAY_SURFACE["repo_write_file"] == "drawer"


class TestRepoRead:
    """MORTIMER_PLANNING_PATHWAY_PLAN.md P6 — "show me the geolocation
    plan" renders the committed doc in the overlay/popup."""

    def test_read_shows_content(self):
        data = {"ok": True, "path": "docs/plans/geo.md", "bytes": 10,
                 "content": "# Geolocation plan"}
        p = build("repo_read_file", data, args={"path": "docs/plans/geo.md"})
        assert p["title"] == "Repo — docs/plans/geo.md"
        assert p["body"] == "# Geolocation plan"

    def test_empty_content_returns_none(self):
        data = {"ok": True, "path": "empty.md", "content": ""}
        assert build("repo_read_file", data, args={"path": "empty.md"}) is None

    def test_surface_is_window(self):
        assert DISPLAY_SURFACE["repo_read_file"] == "window"


class TestGraphView:
    """MORTIMER_GRAPH_LAYER_PLAN.md GL12 — one image card, shared by both
    memory_graph_view (librarian) and graph_view (developer)."""

    def test_graph_view_payload_is_image_window(self):
        url = "http://127.0.0.1:7861/api/graph/memory/image.png?focus=fact%3Auser.style.a"
        data = {"ok": True, "graph": "memory", "focus": "fact:user.style.a",
                "image_url": url, "summary": "2 memories within 2 of a.", "truncated": False}
        p = build("memory_graph_view", data)
        assert p["kind"] == "image"
        assert p["surface"] == "window"
        assert p["images"] == [url]
        assert p["title"] == "Memory graph — fact:user.style.a"

    def test_graph_view_truncated_line(self):
        url = "http://127.0.0.1:7861/api/graph/execution/image.png?focus=run%3Ar1"
        data = {"ok": True, "graph": "execution", "focus": "run:r1", "image_url": url,
                "summary": "1 runs within 1 of r1.", "truncated": True,
                "truncated_reason": "run cap"}
        p = build("graph_view", data)
        assert "Truncated: run cap." in p["body"]

    def test_memory_graph_focus_miss_prefix(self):
        """Status spec T4.6: an unmatched memory focus shows the overview, said so."""
        url = "http://127.0.0.1:7861/api/graph/memory/image.png?focus=&depth=2"
        data = {"ok": True, "graph": "memory", "focus": None, "focus_miss": "zzz",
                "image_url": url, "summary": "2 memories within 2 of the whole graph.",
                "truncated": False}
        p = build("memory_graph_view", data)
        assert p["body"] == ("No memory matched 'zzz'; showing the overview.\n"
                             "2 memories within 2 of the whole graph.")
        assert p["title"] == "Memory graph — whole graph"

    def test_graph_view_ok_false_returns_none(self):
        assert build("memory_graph_view", {"ok": False, "error": "no node matches 'zzz'"}) is None
