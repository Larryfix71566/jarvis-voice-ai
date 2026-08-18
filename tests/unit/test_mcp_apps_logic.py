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


def test_app_write_file_add_then_update(client):
    client.repos["app1"] = {}
    add = logic.app_write_file(client, "app1", "src/new.js", "// new", "add file")
    assert add["ok"] and add["action"] == "add"
    upd = logic.app_write_file(client, "app1", "src/new.js", "// v2")
    assert upd["ok"] and upd["action"] == "update"
    assert client.repos["app1"]["src/new.js"] == "// v2"


def test_app_write_file_path_guard(client):
    result = logic.app_write_file(client, "app1", "../evil", "x")
    assert not result["ok"]


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
        self.posts: list[tuple[str, dict]] = []

    def get(self, path):
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
    result = logic.app_build_start(admin, "demo-app", "add a button", confirm=True)
    assert result["ok"] and result["started"]
    assert admin.posts[0][0] == "/api/appbuild/start"
    assert admin.posts[0][1]["app"] == "demo-app"


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


def test_app_build_submit_previews_then_confirms():
    admin = FakeAdminClient(
        get_responses={
            "/api/appbuild/job": {"ok": True, "job": {"state": "done"}, "status": {
                "active": True, "proposals": [{"path": "src/x.js", "rationale": "y"}],
                "validated_ok": True,
            }},
        },
        post_responses={"/api/appbuild/submit": {"ok": True, "pr_url": "https://example.invalid/pr/1"}},
    )
    preview = logic.app_build_submit(admin, confirm=False)
    assert preview["ok"] and preview["needs_confirmation"]
    confirmed = logic.app_build_submit(admin, confirm=True)
    assert confirmed["ok"] and confirmed["pr_url"] == "https://example.invalid/pr/1"
