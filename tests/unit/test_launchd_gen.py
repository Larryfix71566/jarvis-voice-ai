"""Unit tests for scripts/launchd_gen.py (gap-closure plan GC7). Every
substituted value goes through xml.sax.saxutils.escape -- a raw `&&` inside
a plist <string> is invalid XML and `launchctl bootstrap` rejects the file
outright, so these parse the rendered output with plistlib rather than
just string-matching for the substantive checks."""
from __future__ import annotations

import plistlib
from pathlib import Path

from scripts import launchd_gen


def test_bot_plist_contains_wait_for_and_escaped_ampersand():
    xml = launchd_gen.render("bot", Path("/repo"))
    assert "wait_for.sh" in xml
    assert "&amp;&amp;" in xml
    assert " && " not in xml
    assert "<true/>" in xml  # KeepAlive


def test_backup_plist_has_calendar_interval_and_no_keepalive():
    xml = launchd_gen.render("backup", Path("/repo"), hour=4, minute=30)
    assert "StartCalendarInterval" in xml
    assert "<integer>4</integer>" in xml
    assert "<integer>30</integer>" in xml
    assert "KeepAlive" not in xml


def test_repo_path_with_ampersand_is_escaped():
    xml = launchd_gen.render("admin", Path("/Users/l & r/repo"))
    assert "/Users/l & r/repo" not in xml
    assert "/Users/l &amp; r/repo" in xml


def test_dry_run_writes_nothing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    launchd_gen.main(["--dry-run"])
    capsys.readouterr()
    assert not (tmp_path / "Library").exists()


def test_every_service_plist_parses_with_plistlib():
    for svc in launchd_gen.ALL_SERVICES:
        xml = launchd_gen.render(svc, Path("/repo"))
        parsed = plistlib.loads(xml.encode("utf-8"))
        assert parsed["Label"] == f"com.mortimer.{svc}"


def test_backup_job_uses_system_python_not_the_venv():
    """2026-09-05 — the backup job has no interpreter fallback, so it must not
    depend on uv's managed interpreter store, which uv may relocate on a python
    upgrade. A silently-dead nightly backup is the worst failure mode here."""
    xml = launchd_gen.render("backup", Path("/repo"))
    assert "<string>/usr/bin/python3</string>" in xml
    assert ".venv/bin/python" not in xml


def test_backup_db_uses_only_stdlib():
    """What makes /usr/bin/python3 safe above. If someone adds a third-party
    import to backup_db.py, the nightly job would break under system python —
    fail here instead, where the reason is obvious."""
    import ast as _ast
    import sys as _sys

    src = (Path(__file__).resolve().parents[2] / "scripts" / "backup_db.py").read_text()
    roots = set()
    for node in _ast.walk(_ast.parse(src)):
        if isinstance(node, _ast.Import):
            roots.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, _ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    non_stdlib = sorted(roots - _sys.stdlib_module_names - {"__future__"})
    assert not non_stdlib, (
        f"backup_db.py imports non-stdlib {non_stdlib}; either vendor it or "
        f"point the launchd backup job back at an interpreter that has it"
    )


def test_mortimer_sh_restarts_every_launchd_service():
    """scripts/mortimer.sh keeps its own list of services to kickstart.

    2026-09-06: under launchd the script used to REFUSE — exit 3 with a
    hint naming only com.mortimer.bot, one of five — so "one command to
    start or restart the whole stack" was false in the configuration that
    actually ships. It now kickstarts them, which means it carries a second
    copy of the roster. This is the drift guard: a service added to
    launchd_gen.SERVICES and not to LAUNCHD_SERVICES would silently never
    be restarted, and you would find out by debugging stale code.
    """
    import re
    from pathlib import Path

    from scripts.launchd_gen import SERVICES

    root = Path(__file__).resolve().parents[2]
    src = (root / "scripts" / "mortimer.sh").read_text(encoding="utf-8")
    m = re.search(r"^LAUNCHD_SERVICES=\(([^)]*)\)", src, re.M)
    assert m, "LAUNCHD_SERVICES not found in scripts/mortimer.sh"
    listed = m.group(1).split()
    assert set(listed) == set(SERVICES), (
        f"mortimer.sh restarts {sorted(listed)} but launchd_gen installs "
        f"{sorted(SERVICES)}"
    )
    # bot's ProgramArguments wait on vault's port 8484 (wait_for.sh), so
    # vault must be kickstarted before bot.
    assert listed.index("vault") < listed.index("bot")
    # backup is StartCalendarInterval, not a daemon — nothing to restart.
    assert "backup" not in listed


def test_mortimer_sh_no_longer_refuses_to_start_under_launchd():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    src = (root / "scripts" / "mortimer.sh").read_text(encoding="utf-8")
    # `stop` legitimately still refuses: every service is KeepAlive=true, so
    # killing one only respawns it. `start` must not.
    assert src.count("exit 3") == 1, "only `stop` may refuse under launchd"
    assert "launchd_restart" in src


def test_mortimer_sh_logs_follow_the_files_launchd_writes():
    """The plists write logs/<svc>.launchd.log; `logs` used to tail only
    logs/<svc>.log, so under launchd it followed files nothing wrote to."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    src = (root / "scripts" / "mortimer.sh").read_text(encoding="utf-8")
    template = (root / "scripts" / "launchd"
                / "com.mortimer.template.plist").read_text(encoding="utf-8")
    assert "logs/__SVC__.launchd.log" in template
    assert "logs/bot.launchd.log" in src
