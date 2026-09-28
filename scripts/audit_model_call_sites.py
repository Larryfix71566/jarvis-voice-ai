#!/usr/bin/env python3
"""Inventory production model call sites and their routing classification.

The command is static and secret-free. It scans production Python modules with
Python's AST, records direct provider completions and ``execute_chat`` callers,
and applies the reviewed ownership map below. ``--require-covered`` exits
non-zero if a call site is not classified, so adding a new call requires an
explicit routing decision.
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOTS = (ROOT / "jarvis", ROOT / "mcp_servers")

# The map is intentionally explicit. New production call sites must either be
# added to one of these ownership families or remain visible as unclassified.
FAMILY_BY_PATH = {
    "agents/supervisor.py": ("voice_exempt", "Supervisor remains on the existing Haiku route"),
    "agents/base.py": ("agent_routed", "SubAgent route resolution and policy redaction"),
    "agents/upgrade_agent.py": ("planner_routed", "Planner route resolution/failover"),
    "bot/shared_content.py": ("mixed_routed", "Shared text/image analysis uses the validated vision boundary"),
    "council/council.py": ("council_routed", "Council route and request-policy boundary"),
    "memory_model.py": ("background_routed", "Dedicated memory/background route factory"),
    "memory.py": ("background_routed", "Memory fold-in uses memory route factory"),
    "memory_extraction.py": ("background_routed", "Memory extraction uses memory route factory"),
    "memory_sweep.py": ("background_routed", "Maintenance sweep uses memory route factory"),
    "kb_digest.py": ("background_routed", "Knowledge digest uses background route factory"),
    "procedures.py": ("background_routed", "Procedure description uses background route factory"),
    "bot/pipeline.py": ("mixed_routed", "Voice supervisor plus validated shared-content vision route"),
    "model_execution.py": ("execution_boundary", "Provider-neutral policy execution boundary"),
    "memory_automation_eval.py": (
        "background_routed",
        "Production memory classifier uses confidential execution; shadow uses synthetic approved-external workload",
    ),
    "mcp_servers/mcp_screen/logic.py": (
        "screen_routed", "Production screen vision uses the shared boundary; injected client is a test seam",
    ),
}


def _is_completion_create(node: ast.Call) -> bool:
    current: ast.AST | None = node.func
    attrs: list[str] = []
    while isinstance(current, ast.Attribute):
        attrs.append(current.attr)
        current = current.value
    return attrs[:3] == ["create", "completions", "chat"]


def _is_execute_chat(node: ast.Call) -> bool:
    current = node.func
    return ((isinstance(current, ast.Name) and current.id == "execute_chat")
            or (isinstance(current, ast.Attribute) and current.attr == "execute_chat"))


def _is_vision_boundary(node: ast.Call) -> bool:
    current = node.func
    return ((isinstance(current, ast.Name)
             and current.id == "analyze_shared_content_via_boundary")
            or (isinstance(current, ast.Attribute)
                and current.attr == "analyze_shared_content_via_boundary"))


def build_report() -> dict:
    rows: list[dict] = []
    for source_root in SOURCE_ROOTS:
        for path in sorted(source_root.rglob("*.py")):
            rel = path.relative_to(ROOT).as_posix()
            family = FAMILY_BY_PATH.get(rel.removeprefix("jarvis/"))
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
            except (OSError, SyntaxError) as exc:
                rows.append({"file": rel, "status": "parse_error", "error": type(exc).__name__})
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and (
                    _is_completion_create(node) or _is_execute_chat(node)
                    or _is_vision_boundary(node)
                ):
                    if family:
                        owner, rationale = family
                        status = "covered"
                    else:
                        owner, rationale, status = "unclassified", "No reviewed ownership mapping", "review_required"
                    rows.append({
                        "file": rel,
                        "line": node.lineno,
                        "kind": (
                            "provider_adapter" if _is_completion_create(node)
                            else "shared_boundary"
                        ),
                        "owner": owner,
                        "status": status,
                        "rationale": rationale,
                    })
    return {
        "version": "model-call-site-inventory-v2",
        "source": ["jarvis/", "mcp_servers/"],
        "secret_free": True,
        "call_sites": rows,
        "counts": {
            "total": len(rows),
            "covered": sum(row["status"] == "covered" for row in rows),
            "review_required": sum(row["status"] != "covered" for row in rows),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--require-covered", action="store_true")
    args = parser.parse_args()
    report = build_report()
    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 1 if args.require_covered and report["counts"]["review_required"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
