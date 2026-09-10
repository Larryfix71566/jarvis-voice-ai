"""K2 per-server env scoping (MORTIMER_SECURITY_HARDENING_PLAN.md §7.2)."""

import os
import re
from pathlib import Path

import pytest
import yaml

from jarvis.skills.registry import (
    BASE_ENV_KEYS, REPO_ROOT, build_child_env, load_requires_env,
)

SERVERS = sorted(p.parent.name for p in (REPO_ROOT / "mcp_servers").glob("*/skill.yaml"))


def _declared(pkg: str) -> set[str]:
    """requires_env + optional_env — both are grants the server may receive."""
    data = yaml.safe_load((REPO_ROOT / "mcp_servers" / pkg / "skill.yaml").read_text())
    return set(data.get("requires_env") or []) | set(data.get("optional_env") or [])


_ENV_CALL = re.compile(
    r"""os\.(?:environ\.get|getenv|environ)\(?\s*\[?\s*(?:["']([A-Z][A-Z0-9_]+)["']"""
    r"""|([A-Z][A-Z0-9_]+))"""            # a bare NAME (a module constant)
)
_CONST = re.compile(r"""^([A-Z][A-Z0-9_]*)\s*=\s*["']([A-Z][A-Z0-9_]+)["']""", re.M)
_JARVIS_IMPORT = re.compile(r"^\s*from\s+(jarvis\.[\w.]+)\s+import\b", re.M)


def _module_path(dotted: str) -> Path | None:
    p = REPO_ROOT / (dotted.replace(".", "/") + ".py")
    return p if p.exists() else None


# K2 review gap (MORTIMER_GRAPH_LAYER_PLAN.md GL9/GL15, 2026-09-05): two
# independent reasons _read_transitive cannot see these four names for
# mcp_memory/mcp_runlog, confirmed by hand rather than by the analyzer.
# (1) `from jarvis import graphs` names the PACKAGE jarvis.graphs
# (jarvis/graphs/__init__.py); _module_path only ever builds "<dotted>.py"
# and never "<dotted>/__init__.py", so it can't resolve a package import at
# all — jarvis/graphs/config.py, where three of these four are actually
# read, is never even opened. (2) Independently of (1), config.py reads
# them through its own _int_env(name, default)/_str_env(name, default)
# helpers, where `name` is a lowercase parameter — not a literal string or
# an ALL-CAPS module constant passed directly to os.environ.get(...), the
# one shape _ENV_CALL's regex recognizes. Fixing (1) alone would still miss
# them. Hand-confirmed: jarvis/graphs/config.py's
# _int_env("JARVIS_GRAPH_DEPTH", ...) and
# _int_env("JARVIS_GRAPH_MAX_NODES", ...) and
# _str_env("JARVIS_GRAPH_SINCE", ...); jarvis/graphs/__init__.py's
# graphs_enabled() reads JARVIS_GRAPHS_ENABLED as a literal os.environ.get
# call (a shape the regex WOULD see, but never reaches, since (1) already
# stops _read_transitive from opening any file in the package).
_KNOWN_INDIRECT_TRANSITIVE_READS: dict[str, set[str]] = {
    # keyed by directory name under mcp_servers/ (this file's `pkg`), not the
    # hyphenated server name skill.yaml/EXPECTED use elsewhere in the repo.
    "mcp_memory": {"JARVIS_GRAPHS_ENABLED", "JARVIS_GRAPH_DEPTH",
                   "JARVIS_GRAPH_MAX_NODES", "JARVIS_GRAPH_SINCE"},
    "mcp_runlog": {"JARVIS_GRAPHS_ENABLED", "JARVIS_GRAPH_DEPTH",
                   "JARVIS_GRAPH_MAX_NODES", "JARVIS_GRAPH_SINCE"},
}


def _reads_of(src: str) -> set[str]:
    """Env names read in one source string, resolving module-level
    NAME = "ENV_VAR" constants (review F8, the repo's dominant style)."""
    names: set[str] = set()
    consts = dict(_CONST.findall(src))              # NAME -> ENV_VAR
    for lit, const in _ENV_CALL.findall(src):
        if lit:
            names.add(lit)
        elif const in consts:
            names.add(consts[const])
    return names


def _read_local(pkg: str) -> set[str]:
    """Env names read in the server package's OWN .py files (precise)."""
    names: set[str] = set()
    for path in (REPO_ROOT / "mcp_servers" / pkg).rglob("*.py"):
        names |= _reads_of(path.read_text())
    return names


def _read_transitive(pkg: str) -> set[str]:
    """_read_local plus env names read in any jarvis.* module the package
    imports, one level deep (review F11). Deliberately OVER-approximates — an
    imported module read for other reasons still counts — so it is used only
    to CONFIRM a declaration is justified, never to demand a new one."""
    names = _read_local(pkg)
    for path in (REPO_ROOT / "mcp_servers" / pkg).rglob("*.py"):
        for dotted in _JARVIS_IMPORT.findall(path.read_text()):
            mod = _module_path(dotted)
            if mod is not None:
                names |= _reads_of(mod.read_text())
    return names


@pytest.mark.parametrize("pkg", SERVERS)
def test_no_server_reads_an_undeclared_var(pkg):
    """Every env name a server reads in its OWN package — as a literal or via a
    module constant (review F8, the repo's dominant style) — is declared
    (requires_env/optional_env) or in BASE_ENV_KEYS. This is the test that
    would have caught all six under-declared servers in R-1, mcp-screen's
    constant-style reads included. Transitive reads (through a jarvis.* import)
    are out of this test's scope (R-H1) — following imports here would
    over-approximate and demand spurious declarations; the one known transitive
    read, mcp-screen's JARVIS_UPGRADE_MODELS, is declared by hand (Step 1)."""
    undeclared = _read_local(pkg) - _declared(pkg) - set(BASE_ENV_KEYS)
    assert not undeclared, (
        f"{pkg} reads {sorted(undeclared)} but declares neither them nor "
        f"BASE_ENV_KEYS coverage — add them to requires_env/optional_env in "
        f"mcp_servers/{pkg}/skill.yaml"
    )


@pytest.mark.parametrize("pkg", SERVERS)
def test_every_declared_var_is_actually_read(pkg):
    """The inverse: a declaration nothing reads is a grant nobody needs. A read
    may be transitive (mcp-screen's JARVIS_UPGRADE_MODELS is read through
    jarvis.agents.upgrade_agent), so this confirms against the OVER-approximating
    transitive set — plus _KNOWN_INDIRECT_TRANSITIVE_READS for the handful of
    hand-confirmed reads _read_transitive structurally cannot see (see that
    dict's comment)."""
    read = _read_transitive(pkg) | _KNOWN_INDIRECT_TRANSITIVE_READS.get(pkg, set())
    for name in _declared(pkg):
        assert name in read, f"{pkg} declares {name} but nothing (resolved) reads it"


def test_mcp_time_gets_no_github_token(monkeypatch):
    """The roadmap's own T4a acceptance, as a unit test."""
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_" + "x" * 36)
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-secret")
    monkeypatch.setenv("JARVIS_TIMEZONE", "America/Chicago")
    env = build_child_env({"name": "mcp-time", "env": {}})
    assert "GITHUB_TOKEN" not in env
    assert "TAVILY_API_KEY" not in env
    assert env["JARVIS_TIMEZONE"] == "America/Chicago"


def test_declared_var_reaches_its_own_server(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_" + "x" * 36)
    monkeypatch.setenv("GITHUB_OWNER", "larry")
    env = build_child_env({"name": "mcp-apps", "env": {}})
    assert env["GITHUB_TOKEN"].startswith("ghp_")
    assert env["GITHUB_OWNER"] == "larry"


def test_base_env_keys_are_copied_only_when_present(monkeypatch):
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    env = build_child_env({"name": "mcp-time", "env": {}})
    assert "VIRTUAL_ENV" not in env
    assert "PATH" in env


def test_missing_declared_var_warns_and_does_not_crash(monkeypatch, caplog):
    """K2: spawn proceeds, a WARNING names the server and the variable."""
    from jarvis.skills import registry
    # GC1/GC3: repo root now correctly has a default; exercise a real
    # credential requirement and restore the warning cache after this test.
    monkeypatch.setattr(registry, "_WARNED_MISSING", set())
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    with caplog.at_level("WARNING"):
        env = build_child_env({"name": "mcp-web", "env": {}})
    assert "TAVILY_API_KEY" not in env
    assert "mcp_server_env_missing" in caplog.text
    assert "mcp-web" in caplog.text
    assert "TAVILY_API_KEY" in caplog.text


def test_missing_var_warns_once_per_process(monkeypatch, caplog):
    """Measured: without dedupe, mcp-screen printed 6 WARNINGs per spawn."""
    from jarvis.skills import registry
    # GC1/GC3: repo root now correctly has a default; exercise a real
    # credential requirement and restore the warning cache after this test.
    monkeypatch.setattr(registry, "_WARNED_MISSING", set())
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    with caplog.at_level("WARNING"):
        build_child_env({"name": "mcp-web", "env": {}})
        assert "mcp_server_env_missing" in caplog.text
        caplog.clear()
        build_child_env({"name": "mcp-web", "env": {}})
    assert "mcp_server_env_missing" not in caplog.text


def test_dynamic_source_resolves_vision_keys(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-secret")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_" + "x" * 36)
    env = build_child_env({"name": "mcp-screen", "env": {}})
    assert env["OPENROUTER_API_KEY"] == "or-secret"
    assert "GITHUB_TOKEN" not in env


def test_absent_dynamic_keys_are_silent(monkeypatch, caplog):
    """A dynamic source means "whichever of these exists" — mcp-screen needs
    ONE vision key and the source yields four, so three absences are normal
    and must not warn (D-H1 step 3)."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-secret")
    for name in ("ANTHROPIC_API_KEY", "MOONSHOT_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    with caplog.at_level("WARNING"):
        build_child_env({"name": "mcp-screen", "env": {}})
    assert "ANTHROPIC_API_KEY" not in caplog.text
    assert "OPENAI_API_KEY" not in caplog.text


def test_unknown_dynamic_source_is_a_hard_error(tmp_path, monkeypatch):
    from jarvis.skills.registry import _resolve_dynamic_env
    with pytest.raises(ValueError, match="is not one of"):
        _resolve_dynamic_env("mcp-fake", [{"source": "everything"}])


def test_vault_names_source_is_reserved_for_t4b():
    from jarvis.skills.registry import _resolve_dynamic_env
    with pytest.raises(ValueError, match="not available before T4b"):
        _resolve_dynamic_env("mcp-fake", [{"source": "vault_names"}])


def test_explicit_env_map_still_wins(monkeypatch):
    """The `env:` map in config/mcp_servers.yaml is applied by
    _start_server AFTER build_child_env (registry.py:193-206, unchanged by
    this plan), so it still overrides. Asserted against _start_server's
    real composition, not against build_child_env alone."""
    monkeypatch.setenv("JARVIS_DB_PATH", "/base/jarvis.db")
    env = build_child_env({"name": "mcp-notes", "env": {}})
    assert env["JARVIS_DB_PATH"] == "/base/jarvis.db"
    # Replicate _start_server's next lines to prove ordering:
    from jarvis.config import expand_env_vars
    for key, value in {"JARVIS_DB_PATH": "/override/x.db"}.items():
        env[key] = expand_env_vars(str(value))
    assert env["JARVIS_DB_PATH"] == "/override/x.db"


def test_pythonpath_is_still_prefixed_when_absent(monkeypatch):
    """build_child_env may omit PYTHONPATH entirely; registry.py:207's
    env.get("PYTHONPATH", "") already handles that, and must keep doing so."""
    monkeypatch.delenv("PYTHONPATH", raising=False)
    env = build_child_env({"name": "mcp-time", "env": {}})
    assert "PYTHONPATH" not in env
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    assert env["PYTHONPATH"].startswith(str(REPO_ROOT))


def test_kill_switch_restores_full_inheritance(monkeypatch):
    monkeypatch.setenv("JARVIS_ENV_SCOPING_ENABLED", "false")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_" + "x" * 36)
    env = build_child_env({"name": "mcp-time", "env": {}})
    assert env["GITHUB_TOKEN"].startswith("ghp_")


def test_missing_skill_yaml_degrades_to_base_only(caplog):
    # NOTE: load_requires_env returns a 3-tuple (required, optional,
    # dynamic) per its own signature/docstring — the plan text's
    # 2-value unpack here was a bug (would raise "too many values to
    # unpack"). Fixed during implementation (T4a Step 1, 2026-08-27).
    with caplog.at_level("WARNING"):
        required, optional, dynamic = load_requires_env("mcp-does-not-exist")
    assert required == [] and optional == [] and dynamic == []
    assert "skill_yaml_missing" in caplog.text
