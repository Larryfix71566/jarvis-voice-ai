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


# ---- status spec T4.5: calendar-job table. Goldens captured from the
# pre-refactor render() (backup special case) so the table changes nothing.

BACKUP_GOLDEN_AMP = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
    '<plist version="1.0"><dict>\n'
    '  <key>Label</key><string>com.mortimer.backup</string>\n'
    '  <key>ProgramArguments</key><array><string>/usr/bin/python3</string><string>scripts/backup_db.py</string></array>\n'
    '  <key>WorkingDirectory</key><string>/Users/larry/jarvis &amp; co</string>\n'
    '  <key>EnvironmentVariables</key><dict><key>PATH</key><string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin</string></dict>\n'
    '  <key>StandardOutPath</key><string>/Users/larry/jarvis &amp; co/logs/backup.launchd.log</string>\n'
    '  <key>StandardErrorPath</key><string>/Users/larry/jarvis &amp; co/logs/backup.launchd.log</string>\n'
    '  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>3</integer><key>Minute</key><integer>15</integer></dict>\n'
    '</dict></plist>\n'
)
BACKUP_GOLDEN_0430 = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
    '<plist version="1.0"><dict>\n'
    '  <key>Label</key><string>com.mortimer.backup</string>\n'
    '  <key>ProgramArguments</key><array><string>/usr/bin/python3</string><string>scripts/backup_db.py</string></array>\n'
    '  <key>WorkingDirectory</key><string>/repo</string>\n'
    '  <key>EnvironmentVariables</key><dict><key>PATH</key><string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin</string></dict>\n'
    '  <key>StandardOutPath</key><string>/repo/logs/backup.launchd.log</string>\n'
    '  <key>StandardErrorPath</key><string>/repo/logs/backup.launchd.log</string>\n'
    '  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>4</integer><key>Minute</key><integer>30</integer></dict>\n'
    '</dict></plist>\n'
)
DAEMON_SHA256 = {
    "vault": "820b81e2e5ef04f47cd648b76bb395602bd597fe30d05281a892656d201e0c03",
    "bot": "016ad396c68f380854cf949fba83db1779d627582c98259de40bda894632151e",
    "extractor": "5fc93ffa6bd97f7cdc27291cf146beef2968851bc8b4a856578f0862af57424b",
    "admin": "7c3106dbb8f151d9e3c5aa22f6160e5c1c04923774ad7249cef608368afe1639",
    "costs": "b43c6fa408d56cec31f742622f5366b3b1b40022608461951eb057fcf7b9e862",
}


def test_backup_plist_is_byte_identical_to_before():
    assert launchd_gen.render("backup", Path("/Users/larry/jarvis & co")) == BACKUP_GOLDEN_AMP
    assert launchd_gen.render("backup", Path("/repo"), 4, 30) == BACKUP_GOLDEN_0430


def test_daemon_plists_are_byte_identical_to_before():
    import hashlib

    for svc, digest in DAEMON_SHA256.items():
        rendered = launchd_gen.render(svc, Path("/repo"))
        assert hashlib.sha256(rendered.encode()).hexdigest() == digest, svc


def test_status_daily_plist_argv_and_schedule():
    xml = launchd_gen.render("status-daily", Path("/Users/larry/jarvis & co"))
    parsed = plistlib.loads(xml.encode("utf-8"))
    assert parsed["Label"] == "com.mortimer.status-daily"
    assert parsed["ProgramArguments"] == [
        "/bin/bash", "-c",
        "cd /Users/larry/jarvis & co && set -a && . ./.env && set +a && "
        "exec .venv/bin/python -m jarvis.status.daily"]
    assert parsed["StartCalendarInterval"] == {"Hour": 6, "Minute": 30}
    assert "KeepAlive" not in parsed and "RunAtLoad" not in parsed
    assert parsed["StandardOutPath"] == "/Users/larry/jarvis & co/logs/status-daily.launchd.log"


def test_hour_minute_flags_apply_to_backup_only():
    xml = launchd_gen.render("status-daily", Path("/repo"), hour=4, minute=45)
    assert plistlib.loads(xml.encode())["StartCalendarInterval"] == {"Hour": 6, "Minute": 30}
    assert launchd_gen.ALL_SERVICES == (*launchd_gen.SERVICES, "backup", "status-daily")
    assert launchd_gen.CALENDAR_JOBS["backup"] == (["/usr/bin/python3", "scripts/backup_db.py"], 3, 15)
