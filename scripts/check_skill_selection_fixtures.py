"""Run the public, provider-free Skills selection fixture corpus."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jarvis.agent_skills import load_skills, match_skill
from jarvis.skill_catalog import inspect_package
from jarvis.skill_selection import (
    capabilities_for_inventory,
    load_capability_requirements,
    select_primary_skill,
)

FIXTURE = ROOT / "tests" / "fixtures" / "skills_workspace" / "selection-evaluation.json"
_CASE_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_CATEGORIES = {"positive", "no_skill", "overlap"}


def evaluate_fixture(path: Path = FIXTURE) -> dict:
    """Evaluate frozen public prompts under synthetic ready-route evidence."""
    raw = path.read_bytes()
    document = json.loads(raw)
    if (not isinstance(document, dict)
            or set(document) != {"schema_version", "cases"}
            or document.get("schema_version") != 1
            or not isinstance(document.get("cases"), list)
            or not document["cases"]):
        raise ValueError("invalid selection fixture document")

    cases = document["cases"]
    seen: set[str] = set()
    for case in cases:
        if (not isinstance(case, dict)
                or set(case) != {"id", "category", "request", "expected_skill_id"}
                or not isinstance(case.get("id"), str)
                or not _CASE_ID.fullmatch(case["id"])
                or case["id"] in seen
                or case.get("category") not in _CATEGORIES
                or not isinstance(case.get("request"), str)
                or not case["request"].strip()
                or len(case["request"]) > 2_000):
            raise ValueError("invalid selection fixture case")
        expected = case["expected_skill_id"]
        if expected is not None and (
            not isinstance(expected, str) or not _CASE_ID.fullmatch(expected)
        ):
            raise ValueError("invalid expected skill ID")
        if (case["category"] == "no_skill") != (expected is None):
            raise ValueError("no_skill cases must expect no skill")
        seen.add(case["id"])

    skills = load_skills()
    if not skills:
        raise ValueError("no enabled skills are available for fixture evaluation")
    catalog = {skill.name: inspect_package(skill.path.parent) for skill in skills}
    if any(case["expected_skill_id"] not in catalog
           for case in cases if case["expected_skill_id"] is not None):
        raise ValueError("fixture names a skill outside the enabled catalog")

    available_tools = frozenset(
        tool for entry in catalog.values() for tool in entry.required_tools
    )
    available_capabilities = capabilities_for_inventory(
        frozenset({"text", "tools"}), available_tools,
        requirements=load_capability_requirements(),
    )
    readiness = {skill_id: "ready" for skill_id in catalog}
    privacy_compatible = frozenset(catalog)

    results = []
    failures = 0
    for case in cases:
        legacy = match_skill(case["request"], skills)
        v2 = select_primary_skill(
            case["request"], skills, catalog,
            available_tools=available_tools,
            available_capabilities=available_capabilities,
            readiness=readiness,
            privacy_compatible_skill_ids=privacy_compatible,
        )
        legacy_id = legacy.name if legacy is not None else None
        v2_id = v2.selected.name if v2.selected is not None else None
        expected = case["expected_skill_id"]
        passed = legacy_id == expected and v2_id == expected
        failures += int(not passed)
        results.append({
            "case_id": case["id"],
            "category": case["category"],
            "expected_skill_id": expected,
            "legacy_skill_id": legacy_id,
            "v2_skill_id": v2_id,
            "v2_supporting_skill_id": (
                v2.supporting.name if v2.supporting is not None else None
            ),
            "v2_support_reason": v2.support_reason,
            "v2_reason": v2.reason,
            "v2_candidates": [
                {
                    "skill_id": row.skill_id,
                    "score": round(row.score, 6),
                    "shared_token_count": row.shared_token_count,
                    "threshold_met": row.threshold_met,
                    "reason": row.reason,
                }
                for row in v2.candidates
            ],
            "passed": passed,
        })

    package_revisions = {
        skill_id: entry.revision for skill_id, entry in sorted(catalog.items())
    }
    return {
        "schema_version": 1,
        "suite": "public_skill_selection_fixtures",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fixture_sha256": hashlib.sha256(raw).hexdigest(),
        "package_revisions": package_revisions,
        "evidence_mode": "synthetic_ready_route_and_tool_inventory",
        "provider_calls": 0,
        "summary": {
            "case_count": len(results),
            "passed": len(results) - failures,
            "failed": failures,
            "positive_cases": sum(r["category"] == "positive" for r in results),
            "no_skill_cases": sum(r["category"] == "no_skill" for r in results),
            "overlap_cases": sum(r["category"] == "overlap" for r in results),
        },
        "cases": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        help="optional path for the JSON receipt (default: stdout)")
    args = parser.parse_args()
    try:
        report = evaluate_fixture()
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        parser.error(str(exc))
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    else:
        sys.stdout.write(encoded)
    return 0 if report["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
