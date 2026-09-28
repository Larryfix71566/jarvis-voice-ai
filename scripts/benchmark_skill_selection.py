"""Benchmark the real, provider-free runtime selector on 100 fixed skills."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import yaml

from jarvis import agent_skills, skill_catalog
from jarvis.skill_catalog import _package_digest
from jarvis.skill_selection import (
    RUNTIME_PACKAGE_SNAPSHOT_TTL_SECONDS,
    clear_runtime_package_snapshot,
    prewarm_runtime_package_snapshot,
    select_runtime_primary_skill,
)

FIXTURE = ROOT / "tests" / "fixtures" / "skills_workspace" / "performance-100-skills.json"


class _Registry:
    def tools_for(self, _server_names: list[str]) -> list[str]:
        return []


def _materialize_packages(root: Path, fixture: dict) -> tuple[Path, dict[str, str]]:
    skills_root = root / "skills"
    skills_root.mkdir()
    enabled: list[str] = []
    revisions: dict[str, str] = {}
    for index in range(fixture["skill_count"]):
        skill_id = f"{fixture['skill_id_prefix']}-{index:03d}"
        marker = f"{fixture['trigger_token_prefix']}{index:03d}"
        package = skills_root / skill_id
        package.mkdir()
        (package / "SKILL.md").write_text(
            f"---\nname: {skill_id}\ndescription: {marker} "
            f"{fixture['description_suffix']}\n---\n" + ("x" * fixture["body_chars"]),
            encoding="utf-8",
        )
        manifest = {
            "schema_version": 1,
            "skill_id": skill_id,
            "display_name": skill_id,
            "category": "benchmark",
            "version": "1.0.0",
            "source": {"kind": "synthetic_fixture"},
            "capabilities": [],
            "required_tools": [],
            "required_credentials": [],
            "reference_paths": [],
            "example_ids": [],
            "related_workflow_ids": [],
            "compatible_with": [],
            "process": None,
        }
        (package / "mortimer.yaml").write_text(
            yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8",
        )
        enabled.append(skill_id)
        revisions[skill_id] = _package_digest(package)
    config_path = root / "skills.yaml"
    config_path.write_text(yaml.safe_dump({
        "schema_version": 2,
        "enabled": enabled,
        "revisions": revisions,
    }, sort_keys=False), encoding="utf-8")
    return config_path, revisions


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(percentile * len(ordered)) - 1)]


def benchmark(samples_per_case: int) -> dict:
    raw = FIXTURE.read_bytes()
    fixture = json.loads(raw)
    if (fixture.get("schema_version") != 1
            or fixture.get("skill_count") != 100
            or not isinstance(fixture.get("requests"), list)
            or len(fixture["requests"]) < 2):
        raise ValueError("invalid fixed 100-skill benchmark fixture")

    with tempfile.TemporaryDirectory(prefix="mortimer-skill-bench-") as temporary:
        temp_root = Path(temporary)
        config_path, revisions = _materialize_packages(temp_root, fixture)
        old_skill_dir, old_agent_config = agent_skills.SKILLS_DIR, agent_skills.SKILLS_CONFIG
        old_catalog_config = skill_catalog.SKILLS_CONFIG
        old_flags = {
            key: os.environ.get(key)
            for key in ("JARVIS_SKILLS_SELECTION_V2", "JARVIS_SKILLS_WORKSPACE_ENABLED")
        }
        try:
            agent_skills.SKILLS_DIR = temp_root / "skills"
            agent_skills.SKILLS_CONFIG = config_path
            skill_catalog.SKILLS_CONFIG = config_path
            os.environ["JARVIS_SKILLS_SELECTION_V2"] = "1"
            os.environ["JARVIS_SKILLS_WORKSPACE_ENABLED"] = "1"
            route = type("RouteSnapshot", (), {
                "route": type("Route", (), {
                    "capabilities": ("text", "tools"),
                    "privacy": "approved_external",
                })(),
            })()
            requests = fixture["requests"]
            latencies: dict[str, list[float]] = {case["id"]: [] for case in requests}
            clear_runtime_package_snapshot()
            prewarm_start = time.perf_counter()
            prewarm_runtime_package_snapshot()
            prewarm_ms = (time.perf_counter() - prewarm_start) * 1000
            config_sha256 = hashlib.sha256(config_path.read_bytes()).hexdigest()
            for _ in range(samples_per_case):
                for case in requests:
                    started = time.perf_counter()
                    decision = select_runtime_primary_skill(
                        case["request"], registry=_Registry(), server_names=[],
                        resolved_route=route, private_route=False, sensitive_task=False,
                    )
                    latencies[case["id"]].append((time.perf_counter() - started) * 1000)
                    actual = decision.selected.name if decision.selected else None
                    if actual != case["expected_skill_id"]:
                        raise RuntimeError(
                            f"fixture mismatch for {case['id']}: {actual!r}"
                        )
                    if decision.supporting is not None:
                        raise RuntimeError("synthetic performance corpus unexpectedly selected support")
        finally:
            agent_skills.SKILLS_DIR, agent_skills.SKILLS_CONFIG = old_skill_dir, old_agent_config
            skill_catalog.SKILLS_CONFIG = old_catalog_config
            for key, value in old_flags.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            clear_runtime_package_snapshot()

    cases = {
        case_id: {
            "samples": len(values),
            "p50_ms": round(_percentile(values, 0.50), 3),
            "p95_ms": round(_percentile(values, 0.95), 3),
            "max_ms": round(max(values), 3),
        }
        for case_id, values in latencies.items()
    }
    candidate_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    candidate_dirty = bool(subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, check=True,
        capture_output=True, text=True,
    ).stdout.strip())
    return {
        "schema_version": 1,
        "suite": "runtime_skill_selection_100_public_fixture",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "candidate_commit": candidate_commit,
        "candidate_dirty": candidate_dirty,
        "fixture_sha256": hashlib.sha256(raw).hexdigest(),
        "fixture_skill_count": fixture["skill_count"],
        "synthetic_package_set_sha256": hashlib.sha256(json.dumps(
            revisions, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")).hexdigest(),
        "synthetic_config_sha256": config_sha256,
        "implementation_sha256": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in (
                "scripts/benchmark_skill_selection.py",
                "jarvis/skill_selection.py",
                "jarvis/agents/base.py",
            )
        },
        "snapshot_prewarm_ms": round(prewarm_ms, 3),
        "snapshot_ttl_seconds": RUNTIME_PACKAGE_SNAPSHOT_TTL_SECONDS,
        "evidence_mode": "real_runtime_selector_synthetic_packages_no_provider",
        "provider_calls": 0,
        "cases": cases,
        "acceptance_budget_ms_p95": 20.0,
        "budget_passed": all(case["p95_ms"] <= 20.0 for case in cases.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=200,
                        help="measured iterations per case (default: 200)")
    parser.add_argument("--output", type=Path,
                        help="optional JSON receipt output path")
    args = parser.parse_args()
    if args.samples < 20:
        parser.error("--samples must be at least 20")
    report = benchmark(args.samples)
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    else:
        sys.stdout.write(encoded)
    return 0 if report["budget_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
