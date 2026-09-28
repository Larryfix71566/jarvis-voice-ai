#!/usr/bin/env python3
"""Sample one process's resident memory during a manually prepared UI soak.

Start Mortimer with Skills Workspace's library and live activity trace visible,
then run this tool with the app PID. It records timestamped RSS samples and
estimates monotonic growth with a Theil-Sen slope. It does not launch or control
the app, and it never records command-line arguments or environment variables.
"""
from __future__ import annotations

import argparse
import json
import platform
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

MIB = 1024 * 1024


def resident_bytes(pid: int) -> int:
    """Return RSS bytes for a live PID using the host's `ps` command."""
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "rss="], check=False,
            capture_output=True, text=True,
        )
    except OSError as exc:
        raise RuntimeError(
            "could not start ps to read resident memory; run this soak in a local host terminal"
        ) from exc
    if result.returncode != 0 or not result.stdout.strip():
        raise ProcessLookupError(f"process {pid} is not visible or has exited")
    try:
        rss_kib = int(result.stdout.strip())
    except ValueError as exc:
        raise RuntimeError("ps returned an invalid resident-memory value") from exc
    if rss_kib < 0:
        raise RuntimeError("ps returned a negative resident-memory value")
    return rss_kib * 1024


def theil_sen_slope(samples: list[dict[str, float]]) -> float:
    """Median pairwise RSS slope in bytes/second."""
    slopes = [
        (right["rss_bytes"] - left["rss_bytes"])
        / (right["elapsed_seconds"] - left["elapsed_seconds"])
        for index, left in enumerate(samples)
        for right in samples[index + 1:]
        if right["elapsed_seconds"] > left["elapsed_seconds"]
    ]
    return statistics.median(slopes) if slopes else 0.0


def summarize(samples: list[dict[str, float]], threshold_mib: float) -> dict:
    if len(samples) < 3:
        raise ValueError("at least three samples are required")
    elapsed = samples[-1]["elapsed_seconds"] - samples[0]["elapsed_seconds"]
    if elapsed <= 0:
        raise ValueError("samples must span a positive duration")
    slope = theil_sen_slope(samples)
    estimated_growth_mib = max(0.0, slope * elapsed / MIB)
    return {
        "sample_count": len(samples),
        "elapsed_seconds": round(elapsed, 3),
        "first_rss_mib": round(samples[0]["rss_bytes"] / MIB, 3),
        "last_rss_mib": round(samples[-1]["rss_bytes"] / MIB, 3),
        "minimum_rss_mib": round(min(s["rss_bytes"] for s in samples) / MIB, 3),
        "maximum_rss_mib": round(max(s["rss_bytes"] for s in samples) / MIB, 3),
        "theil_sen_growth_mib": round(estimated_growth_mib, 3),
        "growth_threshold_mib": threshold_mib,
        "budget_passed": estimated_growth_mib <= threshold_mib,
    }


def sample_process(pid: int, duration: float, interval: float,
                   threshold_mib: float) -> dict:
    if pid <= 0 or duration <= 0 or interval <= 0 or threshold_mib < 0:
        raise ValueError("PID and duration/interval must be positive; threshold must be nonnegative")
    started = time.monotonic()
    samples: list[dict] = []
    while True:
        elapsed = time.monotonic() - started
        rss = resident_bytes(pid)
        samples.append({
            "elapsed_seconds": elapsed,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "rss_bytes": rss,
        })
        elapsed = time.monotonic() - started
        if elapsed >= duration:
            break
        time.sleep(min(interval, max(0.0, duration - elapsed)))
    summary = summarize(samples, threshold_mib)
    return {
        "schema_version": 1,
        "suite": "skills_workspace_process_memory_soak",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "pid": pid,
        "duration_requested_seconds": duration,
        "sample_interval_seconds": interval,
        "measurement": "resident_set_size_ps_rss",
        "growth_estimator": "median_pairwise_theil_sen_slope_over_elapsed_window",
        "samples": samples,
        **summary,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, required=True, help="MortimerHost process ID")
    parser.add_argument("--duration-seconds", type=float, default=600,
                        help="soak duration (default: 600 seconds)")
    parser.add_argument("--interval-seconds", type=float, default=30,
                        help="sample interval (default: 30 seconds)")
    parser.add_argument("--threshold-mib", type=float, default=10,
                        help="maximum estimated monotonic RSS growth (default: 10 MiB)")
    parser.add_argument("--output", type=Path, help="optional JSON result path")
    args = parser.parse_args()
    try:
        report = sample_process(args.pid, args.duration_seconds,
                                args.interval_seconds, args.threshold_mib)
    except (ValueError, RuntimeError, ProcessLookupError) as exc:
        parser.error(str(exc))
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    else:
        sys.stdout.write(encoded)
    return 0 if report["budget_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
