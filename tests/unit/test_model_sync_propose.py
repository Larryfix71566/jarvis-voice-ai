import base64

import pytest

from jarvis.model_sync import propose as P

OLD, NEW = "claude-fable-5", "claude-fable-5-2"
TOKEN = "ghp_SECRETTOKEN123"


def test_replace_exact_basics():
    text = f"model: {OLD}\nother: {OLD}-1\nx: {OLD}.5\nanthropic/{OLD}\n"
    out, n = P.replace_exact(text, OLD, NEW)
    assert n == 2
    assert f"model: {NEW}\n" in out
    assert f"other: {OLD}-1" in out
    assert f"x: {OLD}.5" in out
    assert f"anthropic/{NEW}" in out


def test_replace_exact_prefix_ids():
    out, n = P.replace_exact("claude-opus-5-5 and claude-opus-5", "claude-opus-5", "claude-opus-5-1")
    assert n == 1 and out == "claude-opus-5-5 and claude-opus-5-1"
    out, n = P.replace_exact("preclaude-opus-5 x-claude-opus-5", "claude-opus-5", "claude-opus-5-1")
    assert n == 0


def test_replace_exact_comments():
    text = f"# {OLD} here\nkey: {OLD}  # was {OLD}\n"
    out, n = P.replace_exact(text, OLD, NEW)
    assert n == 1
    assert out == f"# {OLD} here\nkey: {NEW}  # was {OLD}\n"


def test_replace_exact_refuses_alias():
    for bad in ("opus", "sonnet", "haiku", "fable", "default", "not-a-model"):
        with pytest.raises(ValueError):
            P.replace_exact("x", OLD, bad)


def test_branch_name():
    assert P.branch_name("A B", "gpt-6.2-sol") == "mortimer/model-sync-a-b-to-gpt-6.2-sol"


def b64(s):
    return base64.b64encode(s.encode()).decode()


class Resp:
    def __init__(self, code, data=None, text=""):
        self.status_code, self._d, self.text = code, data, text

    def json(self):
        return self._d


class FakeHttp:
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def request(self, method, url, **kw):
        self.calls.append((method, url, kw))
        for (m, frag), resp in self.routes:
            if m == method and frag in url:
                return resp(kw) if callable(resp) else resp
        return Resp(404, {})


def happy_routes(ref_resp=None):
    return [
        (("GET", "/pulls?"), Resp(200, [])),
        (("GET", "/git/ref/heads/next"), Resp(200, {"object": {"sha": "abc"}})),
        (("POST", "/git/refs"), ref_resp or Resp(201, {})),
        (("GET", "contents/config/a.yaml"), Resp(200, {"content": b64(f"m: {OLD}\n"), "sha": "s1"})),
        (("GET", "contents/config/b.yaml"), Resp(200, {"content": b64("m: other\n"), "sha": "s2"})),
        (("PUT", "contents/config/a.yaml"), Resp(200, {})),
        (("POST", "/pulls"), Resp(201, {"html_url": "https://github.com/o/r/pull/9"})),
    ]


EV = {"reason": "newer release", "certification": {"steps": [{"name": "p", "ok": True, "detail": "ok"}],
                                                   "manual": ["python x.py"]}}


def test_pr_exists(tmp_path):
    http = FakeHttp([(("GET", "/pulls?"), Resp(200, [{"html_url": "https://u"}]))])
    r = P.propose(OLD, NEW, ["a"], EV, status_dir=tmp_path, token=TOKEN, repo="o/r", http=http)
    assert r["status"] == "pr_exists" and r["url"] == "https://u"
    assert len(http.calls) == 1
    assert "head=o:mortimer/model-sync-" in http.calls[0][1]
    assert http.calls[0][2]["headers"]["Authorization"] == f"Bearer {TOKEN}"


@pytest.mark.parametrize("ref", [None, Resp(422, {}, "Reference already exists")])
def test_happy_path(tmp_path, ref):
    http = FakeHttp(happy_routes(ref))
    r = P.propose(OLD, NEW, ["config/a.yaml", "config/b.yaml"], EV, status_dir=tmp_path,
                  token=TOKEN, repo="o/r", http=http)
    assert r["status"] == "pr_opened" and r["url"].endswith("/pull/9")
    puts = [c for c in http.calls if c[0] == "PUT"]
    assert len(puts) == 1
    body = puts[0][2]["json"]
    assert base64.b64decode(body["content"]).decode() == f"m: {NEW}\n"
    assert body["sha"] == "s1" and body["branch"] == r["branch"]
    pr = [c for c in http.calls if c[0] == "POST" and c[1].endswith("/pulls")][0][2]["json"]
    assert pr["base"] == "next" and pr["draft"] is False and "config/a.yaml" in pr["body"]
    assert "config/b.yaml" not in pr["body"]


def test_no_change(tmp_path):
    routes = [x for x in happy_routes() if x[0][1] != "contents/config/a.yaml" or x[0][0] != "GET"]
    routes.insert(0, (("GET", "contents/config/a.yaml"), Resp(200, {"content": b64("m: z\n"), "sha": "s"})))
    http = FakeHttp(routes)
    r = P.propose(OLD, NEW, ["config/a.yaml"], EV, status_dir=tmp_path, token=TOKEN, repo="o/r", http=http)
    assert r["status"] == "no_change"
    assert not any(c[0] == "PUT" or c[1].endswith("/pulls") and c[0] == "POST" for c in http.calls)


def test_error_scrubbed(tmp_path):
    class Boom(FakeHttp):
        def request(self, method, url, **kw):
            raise RuntimeError(f"connect failed with {TOKEN} in it")

    r = P.propose(OLD, NEW, ["a"], EV, status_dir=tmp_path, token=TOKEN, repo="o/r", http=Boom([]))
    assert r["status"] == "error" and TOKEN not in str(r) and "<redacted>" in r["error"]
    http = FakeHttp([(("GET", "/pulls?"), Resp(500, {}))])
    r = P.propose(OLD, NEW, ["a"], EV, status_dir=tmp_path, token=TOKEN, repo="o/r", http=http)
    assert r["status"] == "error" and TOKEN not in str(r) and len(r["error"]) <= 300


def test_alias_is_error(tmp_path):
    r = P.propose(OLD, "opus", ["a"], EV, status_dir=tmp_path, token=TOKEN, http=FakeHttp([]))
    assert r["status"] == "error"


def test_no_token_patch(tmp_path, monkeypatch):
    monkeypatch.delenv("JARVIS_GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    root = tmp_path / "root"
    (root / "config").mkdir(parents=True)
    f = root / "config" / "a.yaml"
    f.write_text(f"m: {OLD}\n")
    (root / "config" / "b.yaml").write_text("m: x\n")
    sd = tmp_path / "status"
    r = P.propose(OLD, NEW, ["config/a.yaml", "config/b.yaml"], EV, status_dir=sd, repo_root=root)
    assert r["status"] == "proposal_written"
    patch = (sd / "model-sync" / "proposals" / f"{OLD}-to-{NEW}.patch")
    assert r["patch"] == str(patch)
    txt = patch.read_text()
    assert "--- a/config/a.yaml" in txt and "+++ b/config/a.yaml" in txt and f"+m: {NEW}" in txt
    assert f.read_text() == f"m: {OLD}\n"  # checkout untouched
    r2 = P.propose("claude-opus-9", "claude-opus-9-1", ["config/a.yaml"], EV, status_dir=sd, repo_root=root)
    assert r2["status"] == "no_change"


def test_render_body():
    b = P.render_body(OLD, NEW, EV, ["config/a.yaml"])
    assert b.rstrip().endswith("🤖 Generated by Mortimer's daily model check")
    assert "Nothing switches until Larry merges and redeploys." in b
    assert "| p | pass | ok |" in b and "python x.py" in b
