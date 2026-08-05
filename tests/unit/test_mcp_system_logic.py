"""Unit tests for mcp_servers/mcp_system/logic.py (plan Phase 1 Tests)."""

import psutil
import pytest

from mcp_servers.mcp_system import logic


class TestGetSystemStatus:
    def test_shape_and_types(self):
        result = logic.get_system_status()
        for key in ("cpu_percent", "memory_percent", "disk_percent",
                    "battery_percent", "uptime_hours", "human"):
            assert key in result
        assert 0.0 <= result["cpu_percent"] <= 100.0
        assert 0.0 <= result["memory_percent"] <= 100.0
        assert result["battery_percent"] is None or isinstance(
            result["battery_percent"], (int, float)
        )
        assert "System status:" in result["human"]
        assert "uptime" in result["human"]

    def test_warning_flag_branch(self, monkeypatch):
        monkeypatch.setattr(logic.psutil, "cpu_percent", lambda interval=0: 95.0)
        monkeypatch.setattr(
            logic.psutil, "virtual_memory",
            lambda: type("VM", (), {"percent": 50.0})(),
        )
        result = logic.get_system_status()
        assert "Warning" in result["human"]
        assert "CPU" in result["human"]

    def test_no_battery_branch(self, monkeypatch):
        monkeypatch.setattr(logic.psutil, "sensors_battery", lambda: None)
        result = logic.get_system_status()
        assert result["battery_percent"] is None
        assert "battery" not in result["human"]

    def test_battery_present_branch(self, monkeypatch):
        monkeypatch.setattr(
            logic.psutil, "sensors_battery",
            lambda: type("B", (), {"percent": 77.3})(),
        )
        result = logic.get_system_status()
        assert result["battery_percent"] == 77.3
        assert "battery at 77.3%" in result["human"]

    def test_memory_and_disk_flag_branches(self, monkeypatch):
        monkeypatch.setattr(
            logic.psutil, "virtual_memory",
            lambda: type("VM", (), {"percent": 90.0})(),
        )
        monkeypatch.setattr(
            logic.psutil, "disk_usage",
            lambda path: type("D", (), {"percent": 91.0})(),
        )
        result = logic.get_system_status()
        assert "memory" in result["human"]
        assert "disk" in result["human"]


class TestGetTopProcesses:
    def test_shape_sorted_and_limited(self):
        result = logic.get_top_processes(limit=3)
        procs = result["processes"]
        assert 1 <= len(procs) <= 3
        for proc in procs:
            assert set(proc) == {"name", "cpu_percent", "memory_percent"}
        cpus = [p["cpu_percent"] for p in procs]
        assert cpus == sorted(cpus, reverse=True)

    def test_limit_clamped(self):
        assert len(logic.get_top_processes(limit=0)["processes"]) >= 1

    def test_process_iter_exception_paths(self, monkeypatch):
        class BoomProc:
            pid = 1
            info = {"name": "boom", "memory_percent": 1.0}

            def cpu_percent(self):
                raise psutil.NoSuchProcess(1)

        monkeypatch.setattr(
            logic.psutil, "process_iter", lambda *a, **k: [BoomProc()]
        )
        assert logic.get_top_processes()["processes"] == []
