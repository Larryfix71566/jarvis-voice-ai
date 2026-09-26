"""Frozen privilege snapshot (MORTIMER_SECURITY_HARDENING_PLAN.md D-H9,
CROSS_PLAN_RESOLUTION.md §A). This file is DENIED in
config/self_edit_allowlist.json (ALLOWLIST_SEQUENCE.md row W0), so the self-edit
loop cannot change what it asserts. Any legitimate change to a server's
privilege surface is a human commit that edits BOTH the manifest AND this
snapshot — which is exactly the review gate the resolution chose over an
outright deny of config/agents.yaml and mcp_servers/*/skill.yaml.
"""

import yaml

from jarvis.skills.registry import REPO_ROOT

# EXPECTED[server] = (requires_env, optional_env, env_map). Order-independent
# for the lists (sorted before compare); the env_map is compared exactly,
# key AND value — an `env:` value can rename or supply a literal.
#
# Deviation from the plan's literal §7.6 text, logged during implementation
# (2026-08-27): mcp-notes and mcp-reminders each gain
# `optional_env: [JARVIS_SENSITIVE_GUARD_ENABLED]` here, matching the same
# addition made to their skill.yaml manifests in Step 8 (the notes/reminders
# financial gates call jarvis.sensitive.detect_financial, which transitively
# reads that kill switch — undeclared, K2 scoping would silently strip it
# from just these two subprocesses). See the manifests' own comments.
# 2026-09-10 GC1/GC3 re-audit: code-defaulted settings move from required
# to optional. Their names remain explicitly frozen here; the union of
# forwarded names and every env map are unchanged. Credentials stay required.
EXPECTED = {
    "mcp-time":      ([], [], {}),
    "mcp-notes":     ([], ["JARVIS_SENSITIVE_GUARD_ENABLED"],
                      {"JARVIS_DB_PATH": "${JARVIS_DB_PATH}"}),
    # 2026-09-04 — MORTIMER_GRAPH_LAYER_PLAN.md GL12/GL15 (K2): the graph kill
    # switch and knobs must be declared to reach the child.
    "mcp-memory":    ([], ["JARVIS_GRAPHS_ENABLED", "JARVIS_GRAPH_DEPTH",
                           "JARVIS_GRAPH_MAX_NODES", "JARVIS_GRAPH_SINCE"],
                      {"JARVIS_DB_PATH": "${JARVIS_DB_PATH}"}),
    "mcp-reminders": ([], ["JARVIS_SENSITIVE_GUARD_ENABLED"],
                      {"JARVIS_DB_PATH": "${JARVIS_DB_PATH}",
                       "JARVIS_TIMEZONE": "${JARVIS_TIMEZONE}"}),
    "mcp-system":    ([], [], {}),
    "mcp-runlog":    ([], ["JARVIS_GRAPHS_ENABLED", "JARVIS_GRAPH_DEPTH",
                           "JARVIS_GRAPH_MAX_NODES", "JARVIS_GRAPH_SINCE"], {}),
    "mcp-web":       (["TAVILY_API_KEY"], ["JARVIS_UNITS"],
                      {"TAVILY_API_KEY": "${TAVILY_API_KEY}"}),
    "mcp-git":       ([], ["JARVIS_REPO_ROOT"], {"JARVIS_DB_PATH": "${JARVIS_DB_PATH}"}),
    "mcp-repo":      ([], ["JARVIS_REPO_ROOT"], {}),
    "mcp-apps":      (["GITHUB_TOKEN", "GITHUB_OWNER"],
                      ["JARVIS_REGISTRY_REPO", "JARVIS_REGISTRY_BRANCH"],
                      {"GITHUB_TOKEN": "${GITHUB_TOKEN}",
                       "GITHUB_OWNER": "${GITHUB_OWNER}"}),
    "mcp-selfedit":  ([], ["JARVIS_UPGRADE_PROFILE"], {}),
    "mcp-screen":    ([],
                      ["JARVIS_SCREEN_ENABLED", "JARVIS_VISION_PROFILE",
                       "JARVIS_SCREEN_RETENTION_HOURS", "JARVIS_UPGRADE_MODELS"],
                      {}),
    # logic.py supplies localhost:8484; an explicit URL still reaches the child.
    "mcp-kb":        ([], ["KB_BASE_URL"], {}),
    # Status spec T2.6: a thin sidecar client; JARVIS_ADMIN_URL is in
    # BASE_ENV_KEYS, and no secret ever reaches this child.
    "mcp-status":    ([], [], {}),
}


def _skill(server: str) -> dict:
    pkg = server.replace("-", "_")
    return yaml.safe_load(
        (REPO_ROOT / "mcp_servers" / pkg / "skill.yaml").read_text()) or {}


def _env_maps() -> dict:
    data = yaml.safe_load((REPO_ROOT / "config" / "mcp_servers.yaml").read_text())
    servers = data if isinstance(data, list) else (
        data.get("servers") or data.get("mcp_servers") or [])
    return {s["name"]: (s.get("env") or {}) for s in servers}


def test_privilege_surface_is_frozen():
    env_maps = _env_maps()
    drift = []
    for server, (req, opt, env) in EXPECTED.items():
        y = _skill(server)
        got_req = sorted(str(n) for n in (y.get("requires_env") or []))
        got_opt = sorted(str(n) for n in (y.get("optional_env") or []))
        got_env = env_maps.get(server, {})
        if got_req != sorted(req):
            drift.append(f"{server}.requires_env: {got_req} != {sorted(req)}")
        if got_opt != sorted(opt):
            drift.append(f"{server}.optional_env: {got_opt} != {sorted(opt)}")
        if got_env != env:
            drift.append(f"{server} env: map: {got_env} != {env}")
    assert not drift, (
        "A server's privilege surface changed. If this is an intended, "
        "human-reviewed grant, edit EXPECTED here (a DENIED file — a self-edit "
        "cannot) in the SAME commit:\n  " + "\n  ".join(drift))


def test_no_server_gained_an_unfrozen_env_map_key():
    """Defence for review F12: a re-grant via a NEW server's env: map, or a new
    key on an existing one, is caught even if EXPECTED was not updated."""
    for server, got in _env_maps().items():
        assert server in EXPECTED, f"unfrozen server {server} in config/mcp_servers.yaml"
        for key in got:
            assert key in EXPECTED[server][2], (
                f"{server} env: map gained key {key!r} — a secret re-grant "
                f"(review F12). Freeze it in EXPECTED (a human commit).")
