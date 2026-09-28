"""Unit tests for mcp_servers/mcp_apps/logic.py.

Fully offline: a FakeClient stands in for github.GitHubClient, so no
network and no GITHUB_TOKEN are needed.
"""

from __future__ import annotations

import pytest

from mcp_servers.mcp_apps import logic


class FakeClient:
    """In-memory stand-in for GitHubClient (repo -> {path: content})."""

    def __init__(self):
        self.repos: dict[str, dict[str, str]] = {}
        self.puts: list[tuple[str, str, str, str]] = []  # repo, path, message, branch

    def repo_exists(self, name: str) -> bool:
        return name in self.repos

    def create_repo(self, name: str, description: str = "", private: bool = True) -> dict:
        self.repos[name] = {}
        return {"html_url": f"https://github.com/fake/{name}", "private": private}

    def get_file(self, repo: str, path: str, branch: str):
        content = self.repos.get(repo, {}).get(path)
        if content is None:
            return None
        return {"content": content, "sha": f"sha-{repo}-{path}"}

    def put_file(self, repo, path, content, message, branch, sha=None) -> dict:
        if repo not in self.repos:
            self.repos[repo] = {}
        self.repos[repo][path] = content
        self.puts.append((repo, path, message, branch))
        return {"commit": {"sha": f"commit-{len(self.puts):04d}"}}


@pytest.fixture()
def client():
    return FakeClient()


@pytest.fixture(autouse=True)
def registry_env(monkeypatch):
    monkeypatch.setenv("JARVIS_REGISTRY_REPO", "mortimer-repo")
    monkeypatch.setenv("JARVIS_REGISTRY_BRANCH", "mortimer-dev")


# ------------------------------------------------------------- validation


@pytest.mark.parametrize("name", ["expense-tracker", "app1", "a-b-c"])
def test_validate_app_name_ok(name):
    assert logic.validate_app_name(name) == name


def test_validate_app_name_normalizes():
    assert logic.validate_app_name("Expense Tracker") == "expense-tracker"
    assert logic.validate_app_name("my_app") == "my-app"


@pytest.mark.parametrize("bad", ["", "ab", "-bad", "bad-", "bad!!", "a" * 70])
def test_validate_app_name_rejects(bad):
    with pytest.raises(ValueError):
        logic.validate_app_name(bad)


@pytest.mark.parametrize("bad", ["", "../x", "a/../b", "/abs", ".git/config",
                                 "a/.git/b", "back\\slash"])
def test_validate_repo_path_rejects(bad):
    with pytest.raises(ValueError):
        logic.validate_repo_path(bad)


@pytest.mark.parametrize("ok", ["src/index.html", "README.md", "a/b/c.txt"])
def test_validate_repo_path_ok(ok):
    assert logic.validate_repo_path(ok) == ok


# -------------------------------------------------------------- templates


def test_scaffold_files_renders_placeholders():
    files = logic.scaffold_files("expense-tracker", "web_app", "Track expenses")
    assert set(files) == {
        "manifest.json", "README.md", "src/index.html", "src/app.js", "src/style.css",
    }
    assert "expense-tracker" in files["manifest.json"]
    assert "Track expenses" in files["manifest.json"]
    assert "__APP_NAME__" not in "".join(files.values())
    assert "__CREATED_AT__" not in "".join(files.values())


def test_scaffold_files_unknown_template():
    with pytest.raises(ValueError):
        logic.scaffold_files("app1", "no-such-template", "")


# --------------------------------------------------------------- registry


def test_registry_add_insert_and_replace():
    reg = logic.registry_add({"apps": []}, {"name": "a", "created_at": "1"})
    reg = logic.registry_add(reg, {"name": "b", "created_at": "2"})
    reg = logic.registry_add(reg, {"name": "a", "created_at": "3"})
    assert [a["name"] for a in reg["apps"]] == ["b", "a"]
    assert reg["apps"][1]["created_at"] == "3"


# ------------------------------------------------------------- app_create


def test_app_create_preview_creates_nothing(client):
    result = logic.app_create(client, "Expense Tracker", description="Track expenses")
    assert result["ok"] and result["pending"]
    assert result["proposed_name"] == "expense-tracker"
    assert "expense-tracker" in result["summary"]
    assert client.repos == {}  # preview must not touch anything


def test_app_create_confirmed_creates_repo_and_registers(client):
    result = logic.app_create(client, "expense-tracker", confirm=True)
    assert result["ok"] and not result["pending"]
    assert result["repo_url"] == "https://github.com/fake/expense-tracker"
    assert set(client.repos["expense-tracker"]) == set(result["files"])
    # Registry written to the registry repo on the working branch
    registry_puts = [p for p in client.puts if p[1] == logic.REGISTRY_PATH]
    assert len(registry_puts) == 1
    assert registry_puts[0][3] == "mortimer-dev"
    import json
    registry = json.loads(client.repos["mortimer-repo"][logic.REGISTRY_PATH])
    assert registry["apps"][0]["name"] == "expense-tracker"


def test_app_create_refuses_existing_repo(client):
    client.repos["expense-tracker"] = {}
    result = logic.app_create(client, "expense-tracker", confirm=True)
    assert not result["ok"]
    assert "already exists" in result["error"]


def test_app_create_rejects_bad_name(client):
    result = logic.app_create(client, "bad name!!")
    assert not result["ok"]


# ---------------------------------------------------------- app_write_file


@pytest.mark.parametrize("path", ["src/new.js", "README.md", "../evil"])
def test_app_write_file_never_contacts_github(path):
    class ForbiddenClient:
        def __getattr__(self, name):
            raise AssertionError("Retired writer accessed GitHub: " + name)
    result = logic.app_write_file(ForbiddenClient(), "app1", path, "replacement")
    assert result["ok"] is False and result["code"] == "sandbox_required"
    assert result["replacement_tools"][0] == "app_build_start"
    assert "commit" not in result


# ------------------------------------------------------------- app_register


def test_app_register_refuses_main_branch(client, monkeypatch):
    monkeypatch.setenv("JARVIS_REGISTRY_BRANCH", "main")
    result = logic.app_register(client, "app1", "https://x/app1")
    assert not result["ok"]
    assert "main" in result["error"]
    assert client.puts == []


def test_app_register_idempotent(client):
    assert logic.app_register(client, "app1", "https://x/app1")["ok"]
    assert logic.app_register(client, "app1", "https://x/app1")["ok"]
    listed = logic.app_list(client)
    assert len(listed["apps"]) == 1


# ------------------------------------------------------- app_list/app_read


def test_app_list_empty(client):
    assert logic.app_list(client)["apps"] == []


def test_app_read_roundtrip(client):
    client.repos["app1"] = {"README.md": "hello"}
    result = logic.app_read(client, "app1", "README.md")
    assert result["ok"] and result["content"] == "hello"
    assert not logic.app_read(client, "app1", "missing.txt")["ok"]


# ------------------------------------------------------------- app-build
# D6 — thin HTTP clients of the admin sidecar's /api/appbuild/* endpoints;
# `client` here is a fake AdminClient (get/post), not the FakeClient above.


class FakeAdminClient:
    def __init__(self, get_responses=None, post_responses=None):
        self._get_responses = get_responses or {}
        self._post_responses = post_responses or {}
        self.gets: list[tuple[str, dict | None]] = []
        self.posts: list[tuple[str, dict]] = []

    def get(self, path, params=None):
        self.gets.append((path, params))
        if params:
            self.get_params = (path, params)
        return self._get_responses.get(path, {"ok": True, "job": {}, "status": {}})

    def post(self, path, json=None):
        self.posts.append((path, json or {}))
        return self._post_responses.get(path, {"ok": True})


def test_app_build_start_previews_without_confirm():
    result = logic.app_build_start(FakeAdminClient(), "demo-app", "add a button")
    assert result["ok"] and result["needs_confirmation"]
    assert result["app"] == "demo-app"


def test_app_build_start_rejects_bad_app_name():
    result = logic.app_build_start(FakeAdminClient(), "Not Valid!", "goal", confirm=True)
    assert not result["ok"]
    assert "invalid app name" in result["error"]


def test_app_build_start_rejects_empty_goal():
    result = logic.app_build_start(FakeAdminClient(), "demo-app", "  ", confirm=True)
    assert not result["ok"]
    assert "goal" in result["error"]


def test_app_build_start_confirmed_posts_to_sidecar():
    admin = FakeAdminClient(
        post_responses={"/api/appbuild/start": {"ok": True, "started": True, "profile": "kimi-k3"}},
    )
    result = logic.app_build_start(
        admin, "demo-app", "add a button", confirm=True, run_id="app-run-123",
    )
    assert result["ok"] and result["started"]
    assert admin.posts[0][0] == "/api/appbuild/start"
    assert admin.posts[0][1]["app"] == "demo-app"
    assert admin.posts[0][1]["run_id"] == "app-run-123"


def test_app_build_start_without_execution_id_does_not_call_sidecar():
    admin = FakeAdminClient()
    result = logic.app_build_start(
        admin, "demo-app", "add a button", confirm=True,
    )
    assert result["ok"] is False
    assert "execution ID" in result["error"]
    assert admin.posts == []


def test_app_build_start_passes_injected_execution_identity():
    admin = FakeAdminClient(
        post_responses={"/api/appbuild/start": {"ok": True, "started": True}},
    )
    result = logic.app_build_start(
        admin, "demo-app", "add a button", confirm=True, run_id="stable-run",
    )
    assert result["started"]
    assert admin.posts[0][1]["run_id"] == "stable-run"


def test_app_build_start_reports_duplicate_as_not_started():
    admin = FakeAdminClient(post_responses={"/api/appbuild/start": {
        "ok": True, "started": False, "duplicate": True,
        "state": "unknown", "action_run_id": "stable-run",
        "summary": "Already claimed; reconcile before retrying.",
    }})
    result = logic.app_build_start(
        admin, "demo-app", "add a button", confirm=True, run_id="stable-run",
    )
    assert result["ok"] and result["duplicate"] and not result["started"]
    assert result["state"] == "unknown"


def test_app_build_status_queries_a_specific_action_receipt():
    admin = FakeAdminClient(get_responses={"/api/appbuild/job": {
        "ok": True,
        "job": {"state": "unknown", "reconciliation_required": True},
        "status": {"active": False},
    }})
    result = logic.app_build_status(admin, "stable-run")
    assert result["ok"] and "Do not retry" in result["summary"]
    assert "prior app-build action may have started" in result["summary"]
    assert admin.get_params == ("/api/appbuild/job", {"run_id": "stable-run"})


def test_app_build_status_queries_submission_identity():
    admin = FakeAdminClient(get_responses={"/api/appbuild/job": {
        "ok": True,
        "job": {"state": "unknown", "submit_action_id": "session-1"},
        "status": {"active": True},
    }})
    result = logic.app_build_status(admin, submission_id="session-1")
    assert result["ok"] and "Do not retry" in result["summary"]
    assert admin.get_params == (
        "/api/appbuild/job", {"submit_action_id": "session-1"},
    )


def test_app_build_status_rejects_two_identities():
    admin = FakeAdminClient()
    result = logic.app_build_status(
        admin, action_run_id="run-1", submission_id="session-1",
    )
    assert not result["ok"]
    assert admin.gets == []


def test_app_build_status_reports_running():
    admin = FakeAdminClient(get_responses={
        "/api/appbuild/job": {"ok": True, "job": {
            "state": "running", "app": "demo-app", "profile": "kimi-k3", "goal": "add a button",
        }, "status": {}},
    })
    result = logic.app_build_status(admin)
    assert result["ok"]
    assert "Still building" in result["summary"]


def test_app_build_submit_refused_before_validation():
    admin = FakeAdminClient(get_responses={
        "/api/appbuild/job": {"ok": True, "job": {"state": "done"}, "status": {
            "active": True, "proposals": [{"path": "src/x.js", "rationale": "y"}],
            "validated_ok": False,
        }},
    })
    result = logic.app_build_submit(admin, confirm=True)
    assert not result["ok"]
    assert "validation" in result["error"]


@pytest.mark.parametrize("confirm", [False, True])
def test_app_build_submit_opens_the_draft_without_a_second_yes(confirm):
    # W9 (MORTIMER_VOICE_WORKFLOWS_PLAN.md Phase 4, Larry 2026-09-25): the
    # yes to app_build_start covers through the draft PR; confirm is ignored.
    admin = FakeAdminClient(
        get_responses={
            "/api/appbuild/job": {"ok": True, "job": {"state": "done"}, "status": {
                "active": True, "proposals": [{"path": "src/x.js", "rationale": "y"}],
                "validated_ok": True,
            }},
        },
        post_responses={"/api/appbuild/submit": {"ok": True, "pr_url": "https://example.invalid/pr/1"}},
    )
    result = logic.app_build_submit(admin, confirm=confirm)
    assert result["ok"] and result["pr_url"] == "https://example.invalid/pr/1"
    assert "needs_confirmation" not in result
    assert "I cannot merge it myself" in result["summary"]


def test_app_build_start_preview_says_the_yes_covers_the_draft():
    preview = logic.app_build_start(FakeAdminClient(), app="weather-app", goal="add a chart")
    assert preview["needs_confirmation"] is True
    assert "that yes also covers opening the draft pull request" in preview["summary"]
    assert "merging stays with you" in preview["summary"]


def test_app_submit_reports_background_work_without_a_fabricated_pr_url():
    admin = FakeAdminClient(get_responses={'/api/appbuild/job': {'ok':True, 'job':{},
        'status': {'active':True, 'proposals':[{'path':'src/app.js'}], 'validated_ok':True}}},
        post_responses={'/api/appbuild/submit': {'ok':True, 'started':True, 'state':'submitting',
            'action_run_id':'session-1'}})
    result = logic.app_build_submit(admin, confirm=True)
    assert result['ok'] and result['started']
    assert result['submission_id'] == 'session-1'
    assert 'pr_url' not in result
    assert 'has started' in result['summary']


def test_app_submit_unknown_outcome_is_not_reported_as_opened():
    admin = FakeAdminClient(
        get_responses={'/api/appbuild/job': {'ok':True, 'job':{},
            'status': {'active':True, 'proposals':[{'path':'src/app.js'}], 'validated_ok':True}}},
        post_responses={'/api/appbuild/submit': {
            'ok':True, 'started':False, 'state':'unknown',
            'reconciliation_required':True, 'action_run_id':'session-unknown',
        }},
    )
    result = logic.app_build_submit(admin, confirm=True)
    assert not result['ok']
    assert result['state'] == 'unknown'
    assert result['submission_id'] == 'session-unknown'
    assert result['reconciliation_required']
    assert 'Do not retry' in result['summary']


def test_app_submit_duplicate_with_saved_pr_reports_existing_pr():
    admin = FakeAdminClient(
        get_responses={'/api/appbuild/job': {'ok':True, 'job':{},
            'status': {'active':True, 'proposals':[{'path':'src/app.js'}], 'validated_ok':True}}},
        post_responses={'/api/appbuild/submit': {
            'ok':True, 'started':False, 'duplicate':True,
            'state':'completed', 'action_run_id':'session-done',
            'pr_url':'https://example.invalid/pr/7',
        }},
    )
    result = logic.app_build_submit(admin, confirm=True)
    assert result['ok'] and result['already_submitted']
    assert result['pr_url'] == 'https://example.invalid/pr/7'
    assert 'already available' in result['summary']


def test_recovered_app_status_reports_a_saved_publication():
    admin = FakeAdminClient(get_responses={'/api/appbuild/job': {'ok':True,
        'job': {'state':'recovered', 'summary':'Reopened the saved workspace.'},
        'status': {'active':False, 'publication':{'url':'https://github.com/test/app/pull/1'}}}})
    result = logic.app_build_status(admin)
    assert 'https://github.com/test/app/pull/1' in result['summary']
    assert 'No app-build' not in result['summary']
