"""Unit tests for jarvis/bot/display.py (display-panel payloads)."""

import json

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

    def test_empty_result_returns_none(self):
        assert build("web_search", {"answer": "", "results": []}) is None


class TestGetWeather:
    DATA = {
        "city": "Tokyo, Japan",
        "human": "In Tokyo, Japan it's currently 30°C and partly cloudy.",
        "daily": [
            {"date": "2026-08-11", "max_c": 33, "min_c": 25,
             "precip_probability": 20, "condition": "partly cloudy"},
        ],
    }

    def test_table_rendered(self):
        p = build("get_weather", self.DATA, args={"city": "tokyo"})
        assert p["kind"] == "markdown"
        assert p["title"] == "Weather — Tokyo, Japan"
        assert "30°C" in p["body"]
        assert "| 2026-08-11 | 33°C | 25°C | 20% | partly cloudy |" in p["body"]


class TestGetWeatherRadar:
    DATA = {
        "city": "Berlin, Germany",
        "lat": 52.52, "lon": 13.4, "ts": 1754900000,
        "tiles": [f"https://tilecache.rainviewer.com/t{i}.png" for i in range(9)],
    }

    def test_image_payload(self):
        p = build("get_weather_radar", self.DATA, args={"city": "berlin"})
        assert p["kind"] == "image"
        assert p["title"] == "Radar — Berlin, Germany"
        assert len(p["images"]) == 9
        assert "Berlin, Germany" in p["body"]

    def test_no_tiles_returns_none(self):
        assert build("get_weather_radar", {"city": "X", "tiles": []}) is None


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
