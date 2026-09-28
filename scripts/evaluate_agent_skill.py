#!/usr/bin/env python3
"""Run a gated, bounded skill comparison on frozen public fixtures."""
from __future__ import annotations

import argparse
import asyncio
import re
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jarvis.agents.upgrade_agent import registry_source
from jarvis.model_execution import execute_chat
from jarvis.model_routing import (
    ModelRouteError,
    load_skill_evaluation_limits,
    resolve_model_route_checked,
)
from jarvis.skill_catalog import inspect_package
from jarvis.skill_evaluation import (
    SkillEvaluationBudget,
    load_skill_evaluation_fixture,
    require_frozen_skill_evaluation_fixture,
    run_skill_evaluation,
    write_blinded_evaluation,
)

SKILL_SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
FIXTURE_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")


def _private_directory(path: Path) -> Path:
    if path.is_symlink() or not path.is_dir():
        raise ValueError("evaluation output directories must already exist and be real")
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise ValueError("evaluation output directories must have mode 0700")
    return path.resolve()


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill", required=True, help="repository skill slug")
    parser.add_argument("--fixture", required=True, help="frozen evaluation fixture ID")
    parser.add_argument("--review-dir", required=True, type=Path,
                        help="private directory for blinded review outputs")
    parser.add_argument("--key-dir", required=True, type=Path,
                        help="separate private directory for condition key")
    args = parser.parse_args()
    if not SKILL_SLUG.fullmatch(args.skill):
        parser.error("--skill must be a lowercase repository skill slug")
    if not FIXTURE_ID.fullmatch(args.fixture):
        parser.error("--fixture must be a lowercase fixture ID")
    return args


async def _run() -> int:
    args = _arguments()
    skill_path = ROOT / "skills" / args.skill / "SKILL.md"
    fixture_path = (ROOT / "tests" / "fixtures" / "skills_workspace"
                    / "evaluations" / f"{args.fixture}.json")
    review_dir = _private_directory(args.review_dir)
    key_dir = _private_directory(args.key_dir)
    if review_dir == key_dir:
        raise ValueError("review and condition-key directories must be separate")
    review_path = review_dir / "review.json"
    key_path = key_dir / "condition-key.json"
    metrics_path = key_dir / "usage-metrics.json"
    if review_path.exists() or key_path.exists() or metrics_path.exists():
        raise FileExistsError("evaluation output already exists; choose fresh directories")
    if skill_path.is_symlink() or not skill_path.resolve().is_relative_to(ROOT / "skills"):
        raise ValueError("skill package path must remain inside the repository skills directory")
    if fixture_path.is_symlink() or not fixture_path.resolve().is_relative_to(
            ROOT / "tests" / "fixtures" / "skills_workspace" / "evaluations"):
        raise ValueError("fixture path must remain inside the repository evaluation fixtures")
    if skill_path.stat().st_size > 256_000:
        raise ValueError("skill instructions exceed the 256-kilobyte package limit")
    package = inspect_package(skill_path.parent, config_path=ROOT / "config" / "skills.yaml")
    if package.installation != "installed" or package.revision is None or package.blockers:
        raise ValueError("skill package failed the read-only catalog integrity check")
    skill_bytes = skill_path.read_bytes()
    skill_instructions = skill_bytes.decode("utf-8")
    limits = load_skill_evaluation_limits(ROOT / "config" / "model_access.yaml")
    if limits is None:
        raise ModelRouteError("skill evaluation is not explicitly enabled in model_access.yaml")
    cases, digest = load_skill_evaluation_fixture(
        fixture_path, max_cases=limits.max_cases,
        expected_fixture_id=args.fixture,
    )
    # Verify exact reviewed fixture bytes before resolving a route or invoking
    # any provider. Matching fixture_id alone is not sufficient authorization.
    require_frozen_skill_evaluation_fixture(args.fixture, digest)
    required_case_ids = {
        "create-new-skill", "improve-existing-skill", "ambiguous-scope",
        "reuse-existing-skill", "malicious-resource-content", "missing-dependency",
    }
    if ({case.case_id for case in cases} != required_case_ids
            or limits.repetitions != 2 or limits.max_calls < 24):
        raise ValueError("SW-G requires its six frozen cases, two repetitions, and 24-call budget")
    skill_revision = package.revision
    route = resolve_model_route_checked(
        "skill_eval",
        policy_path=ROOT / "config" / "model_access.yaml",
        registry_path=registry_source(config_dir=ROOT / "config"),
    )
    budget = SkillEvaluationBudget(limits, route)
    trials = await run_skill_evaluation(
        cases,
        skill_instructions=skill_instructions,
        fixture_id=args.fixture,
        fixture_sha256=digest,
        limits=limits,
        route=route,
        execute=execute_chat,
        budget=budget,
    )
    package_after = inspect_package(
        skill_path.parent, config_path=ROOT / "config" / "skills.yaml",
    )
    if package_after.revision != skill_revision:
        raise ValueError("skill package changed during evaluation")
    write_blinded_evaluation(
        trials,
        review_path=review_path,
        condition_key_path=key_path,
        metrics_path=metrics_path,
        fixture_sha256=digest,
        skill_revision=skill_revision,
        model_identity=route.identity,
    )
    print(f"Completed {len(trials)} bounded trials for {len(cases)} fixtures.")
    print(f"Blinded review: {review_path}")
    print(f"Condition key (keep from reviewer): {key_path}")
    print(f"Usage metrics (keep with condition key): {metrics_path}")
    return 0


def main() -> int:
    try:
        return asyncio.run(_run())
    except KeyboardInterrupt:
        print("Evaluation cancelled; reserved budget remains consumed.", file=sys.stderr)
        return 130
    except Exception as exc:  # noqa: BLE001 — never print raw provider diagnostics
        print(f"Evaluation stopped ({type(exc).__name__}); no details were logged.",
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
