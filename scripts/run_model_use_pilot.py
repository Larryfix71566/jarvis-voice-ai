#!/usr/bin/env python3
"""Bounded WS-05 public/synthetic route-quality diagnostics; default is dry.

Dry mode reads configuration only. Offline mode injects a deterministic fake
client into the actual policy/execution boundary and proves fixture wiring,
never provider quality. Live mode requires explicit profile/route and budgets.
No mode writes production, loads private prompts, saves model response text,
changes preferences or activates deployed routing. Development remains blocked
until an actual Mortimer sandbox tool driver is integrated.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import hashlib
import inspect
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FIXTURE = ROOT / "tests/fixtures/model_use_pilot_cases.json"
# Updated only with a reviewed fixture/scorer change, never from a CLI argument.
FIXTURE_SHA256 = "f87af8c1cd15f05b56b690bf51cc54d6b4e7d61ef67ee398af90bbfbae291a39"
SCORER_VERSION = "model-use-exact-source-and-classification-v2"


class PilotUnavailable(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def load_fixture() -> tuple[dict, str]:
    if FIXTURE.is_symlink():
        raise PilotUnavailable("fixture_symlink_refused")
    raw = FIXTURE.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != FIXTURE_SHA256:
        raise PilotUnavailable("fixture_digest_mismatch")
    data = json.loads(raw)
    if data.get("content_class") != "public_synthetic" or data.get("version") != "model-use-public-synthetic-v1":
        raise PilotUnavailable("fixture_contract_mismatch")
    ids = [case["id"] for case in data["cases"]]
    if len(ids) != len(set(ids)):
        raise PilotUnavailable("duplicate_fixture_case")
    return data, digest


@asynccontextmanager
async def isolated_state(*, drain_timeout_s=10.0):
    """Use private caller-context stores; drain their workers before deletion."""
    from jarvis.storage_context import StorageScopeUnavailable, storage_scope
    scratch = tempfile.TemporaryDirectory(prefix="ws05-pilot-")
    scope = None
    try:
        async with storage_scope(db_path=Path(scratch.name) / "pilot.db",
                                 costs_db_path=Path(scratch.name) / "costs.db",
                                 model_preferences_enabled=False,
                                 drain_timeout_s=drain_timeout_s,
                                 cleanup=scratch.cleanup) as scope:
            yield scope
    except StorageScopeUnavailable as exc:
        if (exc.code not in {"storage_cleanup_unverified", "storage_cleanup_failed"}
                or scope is None or scope.cleanup_verified or scope.cleanup_error != exc.code):
            raise
        # The scope retains this directory's cleanup callback until actual
        # workers finish. run_pilot reports this fixed failure explicitly.


def score_case(case: dict, text: str) -> dict:
    """Score only parsed model output, not input-derived surrogate behaviors."""
    def unscored(reason: str) -> dict:
        return {"passed": False, "checks": len(case["expected"]), "checks_passed": 0,
                "schema_valid": False, "strict_format_passed": False,
                "content_scored": False, "format_failure_reason": reason}
    try:
        decoded = json.loads(text)
    except (ValueError, TypeError):
        return unscored("markdown_code_fence" if isinstance(text, str) and text.lstrip().startswith("```")
                        else "invalid_json")
    try:
        if case["group"] == "memory":
            from jarvis.memory_automation import Classification
            if not isinstance(decoded, list) or len(decoded) != 1:
                return unscored("unexpected_json_type_or_count")
            try:
                Classification.from_dict(decoded[0])  # production closed schema
            except (ValueError, TypeError):
                return unscored("classification_schema_invalid")
            observed = decoded[0]
            checks = [observed.get(key) in expected if isinstance(expected, list)
                      else type(observed.get(key)) is type(expected) and observed.get(key) == expected
                      for key, expected in case["expected"].items()]
        else:
            if not isinstance(decoded, dict):
                return unscored("unexpected_json_type_or_count")
            expected = case["expected"]
            # JSON numeric values can be int/float; booleans must not pass as 0/1.
            checks = [isinstance(decoded, dict) and set(decoded) == set(expected)]
            for key, value in expected.items():
                actual = decoded.get(key) if isinstance(decoded, dict) else None
                equal = actual == value
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    equal = equal and isinstance(actual, (int, float)) and not isinstance(actual, bool)
                else:
                    equal = equal and type(actual) is type(value)
                checks.append(equal)
        return {"passed": all(checks), "checks": len(checks), "checks_passed": sum(checks),
                "schema_valid": True, "strict_format_passed": True,
                "content_scored": True, "format_failure_reason": None}
    except Exception:
        return unscored("scoring_contract_invalid")


def _golden_response(case: dict) -> str:
    if case["group"] != "memory":
        return json.dumps(case["expected"])
    candidate = case["candidate"]
    fields = {"key": candidate["key"], "scope": "global", "memory_type": "fact",
              "provenance": "user", "evidence_status": "unknown", "confidence": 0.5,
              "evidence": candidate["source_turn_ids"], "reason_code": "insufficient_evidence",
              "subject": None, "project": None, "valid_from": None, "valid_until": None}
    fields.update({key: value[0] if isinstance(value, list) else value
                   for key, value in case["expected"].items()})
    return json.dumps([fields])


def _messages(case: dict) -> tuple[str, str | None]:
    if case["group"] == "memory":
        from jarvis.memory_automation_eval import PROVIDER_CLASSIFIER_SYSTEM_PROMPT
        return json.dumps({"policy_version": "b1", "candidates": [case["candidate"]]}, sort_keys=True), PROVIDER_CLASSIFIER_SYSTEM_PROMPT
    return case["instructions"], None


def _route_metadata(resolved) -> dict:
    return {"workload": resolved.workload, "profile": resolved.profile_name,
            "requested_model": resolved.model, "canonical_identity": resolved.identity,
            "provider": resolved.provider, "route": resolved.route.name,
            "billing_source": resolved.route.billing, "route_privacy": resolved.route.privacy,
            "route_capabilities": list(resolved.route.capabilities),
            "provider_bill_or_allowance_verified": False,
            "response_model_identity_independently_reported": False}


def _reserve_cost(resolved, input_bytes: int, max_output: int) -> float | None:
    """Conservative configured-price reservation, explicitly not a provider bill."""
    import yaml
    prices = yaml.safe_load((ROOT / "config/model_prices.yaml").read_bytes()) or {}
    row = prices.get("models", {}).get(f"{resolved.provider}/{resolved.model}")
    if not row or not {"input_per_m", "output_per_m"}.issubset(row):
        return None
    values = [row["input_per_m"], row["output_per_m"], row.get("cache_write_mult", 1.25)]
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or
           not math.isfinite(value) or value < 0 for value in values):
        return None
    # UTF-8 bytes + bounded message framing, rather than an optimistic chars/4.
    return ((input_bytes + 1024) * values[0] * max(1, values[2]) + max_output * values[1]) / 1_000_000


def _aggregate(rows: list[dict]) -> dict:
    complete = [row for row in rows if row.get("status") == "completed"]
    durations = [row["timing"]["total_ms"] for row in complete]
    return {"completed": len(complete), "passed": sum(row["quality"]["passed"] for row in complete),
            "content_scored_trials": sum(row["quality"].get("content_scored", row["quality"].get("schema_valid", False)) for row in complete),
            "median_completion_ms": statistics.median(durations) if durations else None,
            "p95_completion_ms": sorted(durations)[math.ceil(0.95 * len(durations)) - 1] if durations else None,
            "p95_method": "nearest_rank", "latency_samples": len(durations),
            "sufficient_for_stable_p95_claim": False}


def _source_identity() -> dict:
    result = subprocess.run(["git", "--no-optional-locks", "-C", str(ROOT), "rev-parse", "HEAD"],
                            capture_output=True, text=True, timeout=10)
    revision = result.stdout.strip() if result.returncode == 0 else None
    return {"source_revision": revision,
            "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "configured_price_map_sha256": hashlib.sha256((ROOT / "config/model_prices.yaml").read_bytes()).hexdigest(),
            "execution_boundary_sha256": hashlib.sha256((ROOT / "jarvis/model_execution.py").read_bytes()).hexdigest()}


def compare_receipts(baseline: dict, candidate: dict) -> dict:
    """Compare matching live diagnostics without promoting them to rollout proof."""
    if any("storage_cleanup" in receipt and
           (type(receipt["storage_cleanup"]) is not dict
            or receipt["storage_cleanup"].get("verified") is not True)
           for receipt in (baseline, candidate)):
        raise PilotUnavailable("comparison_cleanup_unverified")
    for field in ("fixture_sha256", "scorer_version", "group"):
        if baseline.get(field) != candidate.get(field):
            raise PilotUnavailable("incomparable_receipt_corpus")
    if baseline.get("mode") != "live" or candidate.get("mode") != "live":
        raise PilotUnavailable("comparison_requires_live_evidence")
    def completed(receipt):
        return {(row["case_id"], row["repetition"]): row for row in receipt["trials"]
                if row.get("status") == "completed"}
    left, right = completed(baseline), completed(candidate)
    if not left or set(left) != set(right) or len(left) != len(baseline["trials"]) or len(right) != len(candidate["trials"]):
        raise PilotUnavailable("comparison_requires_matching_complete_trials")
    a, b = _aggregate(list(left.values())), _aggregate(list(right.values()))
    median_delta = b["median_completion_ms"] - a["median_completion_ms"]
    p95_delta = b["p95_completion_ms"] - a["p95_completion_ms"]
    if not all(math.isfinite(value) for value in (median_delta, p95_delta)):
        raise PilotUnavailable("invalid_comparison_timing")
    baseline_failed = a["passed"] != len(left)
    quality_available = not baseline_failed and a["content_scored_trials"] == len(left) and b["content_scored_trials"] == len(right)
    return {"matched_trials": len(left), "median_delta_ms": median_delta,
            "p95_delta_ms": p95_delta, "quality_comparison_available": quality_available,
            "baseline_gate_failed": baseline_failed,
            "candidate_gate_failed": b["passed"] != len(right),
            "candidate_quality_no_regression": b["passed"] >= a["passed"] if quality_available else None,
            "short_task_median_target_exceeded": median_delta > 1000,
            "p95_review_threshold_exceeded": p95_delta > 2000,
            "stable_p95_or_rollout_acceptance_claimed": False}


async def run_pilot(*, mode: str = "dry", group: str = "research", profile: str | None = None,
                    route: str = "direct_api", repetitions: int = 1, max_calls: int = 12,
                    deadline_s: float = 180, timeout_s: float = 45,
                    max_output_tokens: int | None = 1024, max_input_bytes: int = 16384,
                    max_spend_usd: float | None = None, policy_path: Path | None = None,
                    registry_path: Path | None = None, client_factory=None) -> dict:
    if mode not in {"dry", "offline", "live"} or group not in {"research", "memory", "development"}:
        raise PilotUnavailable("invalid_mode_or_group")
    if not (type(repetitions) is int and 1 <= repetitions <= 5 and type(max_calls) is int and 1 <= max_calls <= 32):
        raise PilotUnavailable("invalid_call_budget")
    if not (not isinstance(timeout_s, bool) and not isinstance(deadline_s, bool) and
            0 < timeout_s <= 60 and 0 < deadline_s <= 300 and timeout_s <= deadline_s and
            ((type(max_output_tokens) is int and 1 <= max_output_tokens <= 2000) or
             (max_output_tokens is None and (route in {"subscription", "codex_subscription"} or
                                             (mode == "offline" and route == "local")))) and
            type(max_input_bytes) is int and 1 <= max_input_bytes <= 65536):
        raise PilotUnavailable("invalid_time_or_token_budget")
    if max_spend_usd is not None and (isinstance(max_spend_usd, bool) or not math.isfinite(max_spend_usd) or max_spend_usd <= 0):
        raise PilotUnavailable("invalid_spend_budget")
    if mode == "live" and (not profile or client_factory is not None):
        raise PilotUnavailable("live_requires_exact_profile_and_owned_client")
    data, digest = load_fixture()
    cases = [case for case in data["cases"] if case["group"] == group]
    if len(cases) * repetitions > max_calls:
        raise PilotUnavailable("requested_cases_exceed_call_budget")
    report = {"version": "model-use-pilot-v1", "workstream": "WS-05", "mode": mode,
              **_source_identity(),
              "group": group, "captured_at_utc": datetime.now(timezone.utc).isoformat(),
              "fixture_version": data["version"], "fixture_sha256": digest,
              "scorer_version": SCORER_VERSION, "trials": [], "provider_requests_attempted": 0,
              "catalog_preflight_attempts": 0,
              "budget": {"max_calls": max_calls, "repetitions": repetitions,
                         "deadline_s": deadline_s, "timeout_s": timeout_s,
                         "max_output_tokens": max_output_tokens, "max_input_bytes": max_input_bytes,
                         "output_token_budget_available": max_output_tokens is not None,
                         "max_spend_usd": max_spend_usd, "configured_price_reserved_usd": 0.0},
              "handling": {"production_writes": False, "private_workload_text_read": False,
                           "response_text_saved": False, "provider_error_text_saved": False,
                           "production_routing_changed": False}, "mar_i_complete": False,
              "limitations": ["one workload diagnostic, not three-workload deployed acceptance",
                              "cold isolated requests; no persistent session warm-up claim",
                              "billing identity comes from resolved route, not independent billing settings",
                              "memory quality covers classification only, not admission/deduplication/restart",
                              "development requires an actual Mortimer sandbox tool driver",
                              "offline outcomes measure fixture wiring, not provider quality",
                              "subscription output-token limits require independent runtime support; request limits alone are not proof",
                              "configured-price reservations are estimates, not verified provider charges"]}
    report["limitations"].append("research fixtures measure source-grounded synthesis, not source retrieval or complete research workflows")
    start = time.monotonic()
    resolved_cache = {}
    async with isolated_state() as storage:
        from jarvis.storage_context import state_to_thread
        from jarvis.model_routing import inspect_route_choice, resolve_model_route, resolve_model_route_checked, make_route_client
        from jarvis.model_execution import ModelContextMessage, ModelExecutionRequest, ModelOutputRequirements, execute_chat
        from jarvis.privacy_policy import DataPolicy
        for repetition in range(repetitions):
            for case in cases:
                trial = {"case_id": case["id"], "repetition": repetition + 1,
                         "case_sha256": hashlib.sha256(json.dumps(case, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
                         "cold_request": True, "status": "unavailable"}
                report["trials"].append(trial)
                if group == "development":
                    trial["reason"] = "sandbox_development_driver_required"
                    continue
                events, clients = {}, []
                try:
                    requested_profile = profile
                    if requested_profile is None:
                        from jarvis.model_routing import resolve_policy
                        requested_profile = resolve_policy(case["workload"], path=policy_path, include_preferences=False).profile
                    policy, record, choice = inspect_route_choice(case["workload"], requested_profile, route,
                                                                  policy_path=policy_path, registry_path=registry_path)
                    trial["selection"] = {"workload": policy.workload, "profile": requested_profile,
                                          "requested_model": record["model"], "route": choice.name,
                                          "billing_source": choice.billing, "required_privacy": case["privacy"],
                                          "route_privacy": choice.privacy,
                                          "required_capabilities": list(policy.required_capabilities),
                                          "route_capabilities": list(choice.capabilities)}
                    if mode == "dry":
                        # Resolve with placeholders so privacy/capability guards run,
                        # without credential loading or confidential catalog calls.
                        dummy = {choice.credential_env: "offline-placeholder"} if choice.credential_env else {}
                        resolve_model_route(case["workload"], explicit_profile=requested_profile,
                                            explicit_route=route, policy_path=policy_path,
                                            registry_path=registry_path, environ=dummy)
                        trial["status"] = "dry_ready_unverified"
                        continue
                    if mode == "live":
                        key = (case["workload"], requested_profile, route)
                        if key not in resolved_cache:
                            remaining = deadline_s - (time.monotonic() - start)
                            if remaining <= 0:
                                raise PilotUnavailable("batch_deadline")
                            # At most one catalog preflight for this exact batch
                            # selection; never fetch a new route between trials.
                            if route == "saygm" and policy.privacy == "confidential":
                                report["catalog_preflight_attempts"] += 1
                            try:
                                resolved_cache[key] = await asyncio.wait_for(state_to_thread(
                                    resolve_model_route_checked, case["workload"],
                                    explicit_profile=requested_profile, explicit_route=route,
                                    policy_path=policy_path, registry_path=registry_path),
                                    timeout=min(timeout_s, remaining))
                            except Exception as exc:
                                resolved_cache[key] = exc
                        resolved = resolved_cache[key]
                        if isinstance(resolved, Exception):
                            raise resolved
                    else:
                        resolved = resolve_model_route(case["workload"], explicit_profile=requested_profile,
                                                       explicit_route=route, policy_path=policy_path,
                                                       registry_path=registry_path,
                                                       environ={choice.credential_env: "offline-placeholder"} if choice.credential_env else {})
                    trial["selection"] = _route_metadata(resolved)
                    instructions, system = _messages(case)
                    if system:
                        trial["production_classifier_prompt_sha256"] = hashlib.sha256(system.encode()).hexdigest()
                    size = len(instructions.encode()) + len((system or "").encode())
                    if size > max_input_bytes:
                        raise PilotUnavailable("input_byte_budget")
                    remaining = deadline_s - (time.monotonic() - start)
                    if remaining <= 0:
                        raise PilotUnavailable("batch_deadline")
                    if mode == "live" and resolved.route.billing != "subscription":
                        reserve = _reserve_cost(resolved, size, max_output_tokens)
                        if reserve is None or max_spend_usd is None:
                            raise PilotUnavailable("paid_route_price_or_spend_budget_unverified")
                        new_total = report["budget"]["configured_price_reserved_usd"] + reserve
                        if new_total > max_spend_usd:
                            raise PilotUnavailable("configured_price_reservation_exceeds_budget")
                        report["budget"]["configured_price_reserved_usd"] = new_total
                    def observe(event):
                        label = event.progress_stage if event.event_type == "progress" else event.event_type
                        events.setdefault(label, time.monotonic())
                        if mode == "live" and label == "provider_request":
                            report["provider_requests_attempted"] += 1
                    def factory(selected):
                        if mode == "live":
                            client = make_route_client(selected, timeout=min(timeout_s, remaining), max_retries=0)
                            clients.append(client)
                            return client
                        if client_factory:
                            return client_factory(selected, case)
                        async def create(**kwargs):
                            return SimpleNamespace(id=None, choices=[SimpleNamespace(message=SimpleNamespace(content=_golden_response(case), tool_calls=[], model_extra={}))], usage=None)
                        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
                    request = ModelExecutionRequest(workload=case["workload"], task_id=f"pilot:{case['id']}:{repetition}",
                                                    parent_request_id=f"pilot:{digest[:16]}", instructions=instructions,
                                                    context=(ModelContextMessage("system", system, DataPolicy("approved_external", "public-classifier-instructions")),) if system else (),
                                                    data_policy=DataPolicy(case["privacy"], "public-synthetic-pilot"),
                                                    output=ModelOutputRequirements(max_tokens=max_output_tokens, require_nonempty_text=True),
                                                    timeout_s=min(timeout_s, remaining))
                    result = await execute_chat(request, resolved, client_factory=factory, event_sink=observe)
                    trial.update(status="completed", quality=score_case(case, result.text),
                                 execution_route=result.route, execution_billing_source=result.billing,
                                 result_policy=result.data_policy.level,
                                 usage={"prompt_tokens": result.prompt_tokens, "completion_tokens": result.completion_tokens,
                                        "usage_known": result.prompt_tokens is not None and result.completion_tokens is not None},
                                 timing={"queue_ms": (events["started"] - events["queued"]) * 1000,
                                         "provider_ms": (events["response_received"] - events["provider_request"]) * 1000,
                                         "total_ms": result.duration_ms, "first_useful_output_ms": None})
                except Exception as exc:
                    # No response text or str(exception), even on provider failure.
                    trial["error_category"] = type(exc).__name__
                    if isinstance(exc, PilotUnavailable):
                        trial["reason"] = exc.code
                    trial["status"] = "failed" if "provider_request" in events else "unavailable"
                finally:
                    for client in clients:
                        close = getattr(client, "close", None) or getattr(client, "aclose", None)
                        if close:
                            try:
                                result = close()
                                if inspect.isawaitable(result):
                                    await result
                            except Exception:
                                pass
    report["storage_cleanup"] = {"verified": storage.cleanup_verified,
                                  "duration_ms": storage.cleanup_duration_ms,
                                  "pending_workers": storage.pending_workers,
                                  "batch_deadline_overrun_ms": max(0.0, (time.monotonic() - start - deadline_s) * 1000)}
    if not storage.cleanup_verified:
        report["error"] = storage.cleanup_error or "storage_cleanup_unverified"
        report["deadline_guarantee_available"] = False
    report["summary"] = _aggregate(report["trials"])
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("dry", "offline", "live"), default="dry")
    parser.add_argument("--group", choices=("research", "memory", "development"), default="research")
    parser.add_argument("--profile")
    parser.add_argument("--route", choices=("direct_api", "subscription", "codex_subscription", "saygm", "local"), default="direct_api")
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--max-calls", type=int, default=12)
    parser.add_argument("--deadline-s", type=float, default=180)
    parser.add_argument("--timeout-s", type=float, default=45)
    parser.add_argument("--max-output-tokens", type=int, default=1024)
    parser.add_argument("--allow-unbounded-subscription-output", action="store_true",
                        help="explicitly request no output-token cap for a subscription-only diagnostic")
    parser.add_argument("--max-input-bytes", type=int, default=16384)
    parser.add_argument("--max-spend-usd", type=float)
    parser.add_argument("--policy", type=Path)
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--vault-path", type=Path, help="explicit existing vault, live mode only; never modified")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--baseline-receipt", type=Path, help="compare a matching live receipt; offline evidence is refused")
    args = parser.parse_args(argv)
    try:
        if args.output and args.output.resolve().is_relative_to((Path.home() / "jarvis-voice-ai-clean").resolve()):
            raise PilotUnavailable("production_output_refused")
        if args.vault_path:
            if args.mode != "live" or not args.vault_path.is_file():
                raise PilotUnavailable("explicit_live_vault_required")
            from jarvis.vault import inject_env
            old = os.environ.get("JARVIS_VAULT_PATH")
            os.environ["JARVIS_VAULT_PATH"] = str(args.vault_path)
            try:
                inject_env()
            finally:
                if old is None:
                    os.environ.pop("JARVIS_VAULT_PATH", None)
                else:
                    os.environ["JARVIS_VAULT_PATH"] = old
        report = asyncio.run(run_pilot(mode=args.mode, group=args.group, profile=args.profile, route=args.route,
                                       repetitions=args.repetitions, max_calls=args.max_calls,
                                       deadline_s=args.deadline_s, timeout_s=args.timeout_s,
                                       max_output_tokens=None if args.allow_unbounded_subscription_output else args.max_output_tokens,
                                       max_input_bytes=args.max_input_bytes,
                                       max_spend_usd=args.max_spend_usd, policy_path=args.policy, registry_path=args.registry))
        if args.baseline_receipt:
            try:
                report["comparison"] = compare_receipts(json.loads(args.baseline_receipt.read_bytes()), report)
            except PilotUnavailable as exc:
                # Preserve completed model diagnostics even when their baseline
                # is incomparable. Never spend quota and then discard evidence.
                report["comparison"] = {"quality_comparison_available": False,
                                        "reason": exc.code,
                                        "stable_p95_or_rollout_acceptance_claimed": False}
            except Exception as exc:
                report["comparison"] = {"quality_comparison_available": False,
                                        "reason": "baseline_receipt_unavailable",
                                        "error_category": type(exc).__name__,
                                        "stable_p95_or_rollout_acceptance_claimed": False}
        rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
        print(rendered, end="")
        passed = (all(row["status"] == "dry_ready_unverified" for row in report["trials"])
                  if args.mode == "dry" else
                  all(row["status"] == "completed" and row["quality"]["passed"] for row in report["trials"]))
        passed = passed and report.get("storage_cleanup", {}).get("verified", True)
        return 0 if passed else 1
    except Exception as exc:
        print(json.dumps({"ok": False, "error_category": type(exc).__name__}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
