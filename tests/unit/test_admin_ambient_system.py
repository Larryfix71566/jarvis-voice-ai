"""System vitals on /api/ambient (Larry 2026-08-18).

The console's bottom-right readout. Served from the SAME
mcp_system.logic the systems agent uses, so the chip and the spoken
answer can never disagree about the same machine.
"""

from __future__ import annotations

import pytest


class TestSystemVitals:
    def test_it_reports_the_metrics_and_no_flags_when_healthy(self, monkeypatch):
        import jarvis.admin.server as srv
        from mcp_servers.mcp_system import logic as syslogic

        monkeypatch.setattr(syslogic, "get_system_status", lambda: {
            "cpu_percent": 12.0, "memory_percent": 61.0, "disk_percent": 44.0,
            "battery_percent": 88.0, "uptime_hours": 5.5, "human": "…"})
        v = srv._system_vitals()
        assert v["cpu"] == 12.0 and v["memory"] == 61.0 and v["disk"] == 44.0
        assert v["flags"] == []          # silent when healthy

    def test_it_flags_at_the_same_threshold_the_agent_warns_at(self, monkeypatch):
        """The chip must turn amber at exactly the point the systems agent
        starts saying "warning" aloud — one rule, read from the module."""
        import jarvis.admin.server as srv
        from mcp_servers.mcp_system import logic as syslogic

        monkeypatch.setattr(syslogic, "get_system_status", lambda: {
            "cpu_percent": syslogic.FLAG_THRESHOLD, "memory_percent": 10.0,
            "disk_percent": 91.0, "battery_percent": None,
            "uptime_hours": 1.0, "human": "…"})
        v = srv._system_vitals()
        assert set(v["flags"]) == {"cpu", "disk"}
        assert v["threshold"] == syslogic.FLAG_THRESHOLD

    def test_a_missing_battery_is_none_not_zero(self, monkeypatch):
        """A desktop has no battery sensor; 0% would read as "about to
        die" — the classic null-as-zero bug."""
        import jarvis.admin.server as srv
        from mcp_servers.mcp_system import logic as syslogic

        monkeypatch.setattr(syslogic, "get_system_status", lambda: {
            "cpu_percent": 1.0, "memory_percent": 1.0, "disk_percent": 1.0,
            "battery_percent": None, "uptime_hours": 1.0, "human": "…"})
        assert srv._system_vitals()["battery"] is None

    def test_a_failure_hides_the_chip_rather_than_breaking_the_strip(self, monkeypatch):
        """A vitals readout must never be the reason the ambient strip
        stops working."""
        import jarvis.admin.server as srv
        from mcp_servers.mcp_system import logic as syslogic

        def boom():
            raise RuntimeError("psutil unavailable")

        monkeypatch.setattr(syslogic, "get_system_status", boom)
        assert srv._system_vitals() is None
