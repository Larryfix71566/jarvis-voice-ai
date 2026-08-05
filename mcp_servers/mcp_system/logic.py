"""mcp-system: local machine status pure logic (plan Phase 1, §1.5).

psutil-only, no network. `human` sentences flag any metric >= 85%.
"""

from __future__ import annotations

import time

import psutil

FLAG_THRESHOLD = 85.0


def get_system_status() -> dict:
    cpu = psutil.cpu_percent(interval=0.1)
    memory = psutil.virtual_memory().percent
    disk = psutil.disk_usage("/").percent
    battery_sensor = psutil.sensors_battery()
    battery = round(battery_sensor.percent, 1) if battery_sensor else None
    uptime_hours = round((time.time() - psutil.boot_time()) / 3600, 1)

    parts = [
        f"CPU at {cpu}%",
        f"memory at {memory}%",
        f"disk at {disk}%",
    ]
    if battery is not None:
        parts.append(f"battery at {battery}%")
    human = "System status: " + ", ".join(parts) + f"; uptime {uptime_hours} hours."

    flags = []
    if cpu >= FLAG_THRESHOLD:
        flags.append("CPU")
    if memory >= FLAG_THRESHOLD:
        flags.append("memory")
    if disk >= FLAG_THRESHOLD:
        flags.append("disk")
    if flags:
        human += " Warning: " + ", ".join(flags) + " at or above 85%."

    return {
        "cpu_percent": cpu,
        "memory_percent": memory,
        "disk_percent": disk,
        "battery_percent": battery,
        "uptime_hours": uptime_hours,
        "human": human,
    }


def get_top_processes(limit: int = 5) -> dict:
    limit = max(1, min(int(limit), 20))
    # Prime per-process CPU measurement (first sample is always 0.0).
    for proc in psutil.process_iter():
        try:
            proc.cpu_percent()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    time.sleep(0.1)

    rows = []
    for proc in psutil.process_iter(["name", "memory_percent"]):
        try:
            rows.append({
                "name": proc.info["name"] or f"pid-{proc.pid}",
                "cpu_percent": proc.cpu_percent(),
                "memory_percent": round(proc.info["memory_percent"] or 0.0, 2),
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    rows.sort(key=lambda r: r["cpu_percent"], reverse=True)
    return {"processes": rows[:limit]}
