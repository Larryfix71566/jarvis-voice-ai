"""Host-owned contract for verifiable skill-step completion.

Natural-language success criteria and successful tool calls are not checks.
Only exact revision/step mappings in the local host policy can authorize a
controller receipt. Each mapped check must have a host-owned implementation;
the registry is intentionally sparse and does not generalize to other steps.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
import secrets
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

SKILL_STEP_CHECKS_CONFIG = Path(__file__).resolve().parents[1] / "config" / "skill_step_checks.yaml"
RECEIPT_ISSUER = "mortimer-host-controller"
MAX_RECEIPT_TTL = timedelta(minutes=2)
MAX_RECEIPT_AGE = timedelta(minutes=2)
_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_ATTEMPT = re.compile(r"^[A-Za-z0-9_-]{1,96}$")
_CHECK = re.compile(r"^[a-z][a-z0-9_.-]{0,95}$")
_HEX64 = re.compile(r"^[a-f0-9]{64}$")
_HOST_RECEIPT_KEY = secrets.token_bytes(32)
_MAX_WEATHER_AGE = timedelta(hours=3)
_MAX_WEATHER_FUTURE_SKEW = timedelta(minutes=5)


def _finite_number(value: object) -> bool:
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))


def _weather_current_and_forecast_returned(context: dict) -> bool:
    """Verify the bounded structured result of the trusted weather tool."""
    if not isinstance(context, dict) or set(context) != {
        "tool_name", "arguments", "result",
    }:
        return False
    if context["tool_name"] != "get_weather":
        return False
    arguments = context["arguments"]
    if (not isinstance(arguments, dict) or set(arguments) - {"city", "days"}
            or not isinstance(arguments.get("city"), str)
            or not arguments["city"].strip() or len(arguments["city"]) > 200
            or ("days" in arguments and type(arguments["days"]) is not int)
            or ("days" in arguments and not 1 <= arguments["days"] <= 3)):
        return False
    requested_days = arguments.get("days", 1)
    raw_result = context["result"]
    if not isinstance(raw_result, str) or len(raw_result.encode("utf-8")) > 32 * 1024:
        return False
    try:
        result = json.loads(raw_result)
    except (json.JSONDecodeError, UnicodeError):
        return False
    if not isinstance(result, dict) or "error" in result:
        return False
    requested_city = result.get("requested_city")
    if (not isinstance(result.get("city"), str) or not result["city"].strip()
            or not isinstance(requested_city, str)
            or " ".join(requested_city.split()).casefold()
            != " ".join(arguments["city"].split()).casefold()
            or result.get("source") not in {
                "weather.gov", "weather.gov-forecast", "open-meteo",
            }
            or result.get("units") not in {"imperial", "metric"}
            or not isinstance(result.get("human"), str) or not result["human"].strip()):
        return False
    current = result.get("current")
    if not isinstance(current, dict) or not isinstance(current.get("condition"), str) or not current["condition"].strip():
        return False
    if not _finite_number(current.get("temperature_f")) or not _finite_number(current.get("temperature_c")):
        return False
    if abs(current["temperature_f"] - (current["temperature_c"] * 9 / 5 + 32)) > 1.1:
        return False
    # Forecast-period fallback is not a current observation, even though it
    # remains useful to ordinary callers and is explicitly labeled as such.
    if result["source"] == "weather.gov-forecast":
        return False
    observed_at = current.get("observed_at")
    if not isinstance(observed_at, str):
        return False
    try:
        timestamp = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    if timestamp.tzinfo is None:
        return False
    age = datetime.now(timezone.utc) - timestamp.astimezone(timezone.utc)
    if age > _MAX_WEATHER_AGE or age < -_MAX_WEATHER_FUTURE_SKEW:
        return False
    daily = result.get("daily")
    if not isinstance(daily, list) or not requested_days <= len(daily) <= 3:
        return False
    for day in daily:
        if (not isinstance(day, dict) or not isinstance(day.get("date"), str)
                or not day["date"].strip()
                or not all(_finite_number(day.get(key)) for key in (
                    "max_f", "min_f", "max_c", "min_c",
                ))
                or day["max_f"] < day["min_f"]
                or day["max_c"] < day["min_c"]
                or abs(day["max_f"] - (day["max_c"] * 9 / 5 + 32)) > 1.1
                or abs(day["min_f"] - (day["min_c"] * 9 / 5 + 32)) > 1.1):
            return False
    return True


def _git_repository_status_observed(context: dict) -> bool:
    """Verify the trusted, structured result of the read-only git status tool."""
    if not isinstance(context, dict) or set(context) != {
        "tool_name", "arguments", "result",
    }:
        return False
    if context["tool_name"] != "git_status" or context["arguments"] != {}:
        return False
    raw_result = context["result"]
    if not isinstance(raw_result, str) or len(raw_result.encode("utf-8")) > 64 * 1024:
        return False
    try:
        result = json.loads(raw_result)
    except (json.JSONDecodeError, UnicodeError):
        return False
    if not isinstance(result, dict) or set(result) != {
        "repository", "branch", "upstream", "clean", "changed_files",
        "ahead", "behind",
    }:
        return False
    repository = result["repository"]
    branch = result["branch"]
    upstream = result["upstream"]
    changed_files = result["changed_files"]
    return not (
            not isinstance(repository, str) or not repository.startswith("/")
            or len(repository) > 4096 or not isinstance(branch, str)
            or not branch.strip() or len(branch) > 256
            or (upstream is not None and (
                not isinstance(upstream, str) or not upstream.strip()
                or len(upstream) > 512
            ))
            or type(result["clean"]) is not bool
            or not isinstance(changed_files, list) or len(changed_files) > 2000
            or any(not isinstance(path, str) or not path or len(path) > 4096
                   for path in changed_files)
            or result["clean"] != (not changed_files)
            or type(result["ahead"]) is not int or result["ahead"] < 0
            or type(result["behind"]) is not int or result["behind"] < 0
    )


def _git_history_observed(context: dict) -> bool:
    """Verify a bounded Git log result with stable commit identities."""
    if not isinstance(context, dict) or set(context) != {
        "tool_name", "arguments", "result",
    }:
        return False
    if context["tool_name"] != "git_log":
        return False
    arguments = context["arguments"]
    if (not isinstance(arguments, dict) or set(arguments) - {"n"}
            or ("n" in arguments and type(arguments["n"]) is not int)
            or ("n" in arguments and not 1 <= arguments["n"] <= 20)):
        return False
    limit = arguments.get("n", 5)
    raw_result = context["result"]
    if not isinstance(raw_result, str) or len(raw_result.encode("utf-8")) > 64 * 1024:
        return False
    try:
        result = json.loads(raw_result)
    except (json.JSONDecodeError, UnicodeError):
        return False
    if not isinstance(result, dict) or set(result) != {"commits", "commit_records"}:
        return False
    commits = result["commits"]
    records = result["commit_records"]
    if (not isinstance(commits, list) or not isinstance(records, list)
            or len(commits) != len(records) or len(records) > limit):
        return False
    for commit, record in zip(commits, records, strict=True):
        if (not isinstance(record, dict) or set(record) != {"sha", "date", "subject"}
                or not isinstance(record["sha"], str)
                or not re.fullmatch(r"[a-f0-9]{40}", record["sha"])
                or not isinstance(record["date"], str)
                or not isinstance(record["subject"], str)
                or not record["subject"].strip() or len(record["subject"]) > 2000
                or not isinstance(commit, str)
                or commit != f"{record['sha'][:7]} {record['date']} {record['subject']}"):
            return False
        try:
            timestamp = datetime.fromisoformat(record["date"])
        except ValueError:
            return False
        if timestamp.tzinfo is None:
            return False
    return True


# These checks are host code, not manifest or model supplied expressions.
# YAML may reference only these implementations and exact immutable revisions.
def _creator_offline_validation(context: dict) -> bool:
    from jarvis.skill_validation_activity import verify_validation_context

    return verify_validation_context(context)


HOST_CHECKS: dict[str, Callable[[dict], bool]] = {
    "weather.current_and_forecast_returned": _weather_current_and_forecast_returned,
    "repository.status_observed": _git_repository_status_observed,
    "repository.history_observed": _git_history_observed,
    "creator.offline_validation_verified": _creator_offline_validation,
}


class SkillStepReceiptError(ValueError):
    """A bounded, content-free receipt validation failure."""


@dataclass(frozen=True)
class SkillStepCheckOutcome:
    check_id: str
    passed: bool


@dataclass(frozen=True)
class SkillStepCheckReceipt:
    schema_version: int
    receipt_id: str
    issuer: str
    issued_at: str
    expires_at: str
    user_id: str
    run_id: str
    request_id: str
    skill_id: str
    skill_revision: str
    step_id: str
    attempt_id: str
    outcomes: tuple[SkillStepCheckOutcome, ...]
    signature: str

    @classmethod
    def from_mapping(cls, value: object) -> SkillStepCheckReceipt:
        fields = {
            "schema_version", "receipt_id", "issuer", "issued_at", "expires_at",
            "user_id", "run_id", "request_id", "skill_id", "skill_revision",
            "step_id", "attempt_id", "outcomes", "signature",
        }
        if not isinstance(value, dict) or set(value) != fields:
            raise SkillStepReceiptError("invalid_receipt_shape")
        raw_outcomes = value["outcomes"]
        if not isinstance(raw_outcomes, list) or len(raw_outcomes) > 32:
            raise SkillStepReceiptError("invalid_receipt_outcomes")
        outcomes = []
        for item in raw_outcomes:
            if not isinstance(item, dict) or set(item) != {"check_id", "passed"}:
                raise SkillStepReceiptError("invalid_receipt_outcome")
            if not isinstance(item["check_id"], str) or not _CHECK.fullmatch(item["check_id"]):
                raise SkillStepReceiptError("invalid_receipt_check_id")
            if type(item["passed"]) is not bool:
                raise SkillStepReceiptError("invalid_receipt_outcome")
            outcomes.append(SkillStepCheckOutcome(item["check_id"], item["passed"]))
        receipt = cls(
            schema_version=value["schema_version"],
            receipt_id=value["receipt_id"], issuer=value["issuer"],
            issued_at=value["issued_at"], expires_at=value["expires_at"],
            user_id=value["user_id"], run_id=value["run_id"],
            request_id=value["request_id"], skill_id=value["skill_id"],
            skill_revision=value["skill_revision"], step_id=value["step_id"],
            attempt_id=value["attempt_id"], outcomes=tuple(outcomes),
            signature=value["signature"],
        )
        receipt.validate_shape()
        return receipt

    def validate_shape(self) -> None:
        # bool is an int subclass in Python, so `True == 1`; requiring the
        # exact JSON integer type keeps malformed envelopes from masquerading
        # as a supported receipt schema.
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise SkillStepReceiptError("unsupported_receipt_schema")
        try:
            uuid.UUID(self.receipt_id)
        except (ValueError, TypeError, AttributeError):
            raise SkillStepReceiptError("invalid_receipt_id") from None
        if self.issuer != RECEIPT_ISSUER:
            raise SkillStepReceiptError("invalid_receipt_issuer")
        if (not isinstance(self.issued_at, str) or len(self.issued_at) > 40
                or not isinstance(self.expires_at, str) or len(self.expires_at) > 40):
            raise SkillStepReceiptError("invalid_receipt_time")
        for value in (self.user_id, self.run_id, self.request_id):
            if not isinstance(value, str) or not value or len(value) > 128:
                raise SkillStepReceiptError("invalid_receipt_identity")
        if not isinstance(self.skill_id, str) or not _SLUG.fullmatch(self.skill_id):
            raise SkillStepReceiptError("invalid_receipt_skill_id")
        if not isinstance(self.skill_revision, str) or not _HEX64.fullmatch(self.skill_revision):
            raise SkillStepReceiptError("invalid_receipt_skill_revision")
        if not isinstance(self.step_id, str) or not _SLUG.fullmatch(self.step_id):
            raise SkillStepReceiptError("invalid_receipt_step_id")
        if not isinstance(self.attempt_id, str) or not _ATTEMPT.fullmatch(self.attempt_id):
            raise SkillStepReceiptError("invalid_receipt_attempt_id")
        if len({outcome.check_id for outcome in self.outcomes}) != len(self.outcomes):
            raise SkillStepReceiptError("duplicate_receipt_checks")
        if not isinstance(self.signature, str) or not _HEX64.fullmatch(self.signature):
            raise SkillStepReceiptError("invalid_receipt_signature")

    def payload(self, *, include_signature: bool = True) -> dict:
        payload = {
            "schema_version": self.schema_version,
            "receipt_id": self.receipt_id,
            "issuer": self.issuer,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "user_id": self.user_id,
            "run_id": self.run_id,
            "request_id": self.request_id,
            "skill_id": self.skill_id,
            "skill_revision": self.skill_revision,
            "step_id": self.step_id,
            "attempt_id": self.attempt_id,
            "outcomes": [
                {"check_id": outcome.check_id, "passed": outcome.passed}
                for outcome in self.outcomes
            ],
        }
        if include_signature:
            payload["signature"] = self.signature
        return payload

    def digest(self) -> str:
        encoded = json.dumps(
            self.payload(), sort_keys=True, separators=(",", ":"),
        ).encode()
        return hashlib.sha256(encoded).hexdigest()


def issue_host_controller_receipt(
    fields: dict,
    *,
    context: dict,
) -> dict:
    """Sign an internal controller result; never expose this as a model tool.

    Callers must obtain `fields` from host-side check implementations after
    resolving the exact required-check mapping. The signature is process-local
    because receipts are short lived; a restart invalidates unaccepted receipts.
    """
    expected_fields = {
        "schema_version", "receipt_id", "issuer", "issued_at", "expires_at",
        "user_id", "run_id", "request_id", "skill_id", "skill_revision",
        "step_id", "attempt_id",
    }
    if not isinstance(fields, dict) or set(fields) != expected_fields:
        raise SkillStepReceiptError("invalid_receipt_shape")
    if not isinstance(context, dict):
        raise SkillStepReceiptError("invalid_controller_context")
    required_check_ids = load_required_check_ids(
        fields["skill_id"], fields["skill_revision"], fields["step_id"],
    )
    if not required_check_ids:
        raise SkillStepReceiptError("no_host_checks_configured")
    outcomes = []
    for check_id in required_check_ids:
        checker = HOST_CHECKS.get(check_id)
        if checker is None:
            raise SkillStepReceiptError("host_check_unavailable")
        try:
            passed = checker(context)
        except Exception:  # noqa: BLE001 — never expose check details
            raise SkillStepReceiptError("host_check_failed") from None
        if type(passed) is not bool:
            raise SkillStepReceiptError("invalid_host_check_result")
        outcomes.append({"check_id": check_id, "passed": passed})
    if not all(item["passed"] for item in outcomes):
        raise SkillStepReceiptError("required_check_failed")
    raw = {
        **fields,
        "outcomes": outcomes,
        "signature": "0" * 64,
    }
    receipt = SkillStepCheckReceipt.from_mapping(raw)
    unsigned = json.dumps(
        receipt.payload(include_signature=False),
        sort_keys=True, separators=(",", ":"),
    ).encode()
    signature = hmac.new(_HOST_RECEIPT_KEY, unsigned, hashlib.sha256).hexdigest()
    return {**receipt.payload(include_signature=False), "signature": signature}


def record_verified_tool_step(
    runlog,
    *,
    skill_id: str,
    skill_revision: str,
    step_id: str,
    attempt_id: str,
    context: dict,
) -> bool:
    """Issue and persist a pass only when an exact host check accepts context.

    `context` is transient input from the host tool executor and is never
    included in the signed receipt, skill events, or the receipt table.
    """
    try:
        required = load_required_check_ids(skill_id, skill_revision, step_id)
        if not required:
            return False
        now = datetime.now(timezone.utc)
        fields = {
            "schema_version": 1,
            "receipt_id": str(uuid.uuid4()),
            "issuer": RECEIPT_ISSUER,
            "issued_at": now.isoformat().replace("+00:00", "Z"),
            "expires_at": (now + MAX_RECEIPT_TTL).isoformat().replace("+00:00", "Z"),
            "user_id": runlog.user_id,
            "run_id": runlog.run_id,
            "request_id": runlog.run_id,
            "skill_id": skill_id,
            "skill_revision": skill_revision,
            "step_id": step_id,
            "attempt_id": attempt_id,
        }
        receipt = issue_host_controller_receipt(fields, context=context)
        return runlog.accept_skill_step_check_receipt(receipt) in {
            "accepted", "already_accepted",
        }
    except (SkillStepReceiptError, AttributeError, TypeError, ValueError):
        return False


def _parse_time(value: str) -> datetime:
    if not isinstance(value, str) or not value or len(value) > 40:
        raise SkillStepReceiptError("invalid_receipt_time")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise SkillStepReceiptError("invalid_receipt_time") from None
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise SkillStepReceiptError("receipt_time_must_be_utc")
    return parsed.astimezone(timezone.utc)


def load_required_check_ids(
    skill_id: str,
    skill_revision: str,
    step_id: str,
    *,
    path: Path | None = None,
) -> tuple[str, ...]:
    """Load the host-owned allowlist for this immutable package step."""
    policy_path = path or SKILL_STEP_CHECKS_CONFIG
    try:
        class UniqueKeyLoader(yaml.SafeLoader):
            pass

        def construct_unique_mapping(loader, node, deep=False):
            loader.flatten_mapping(node)
            mapping = {}
            for key_node, value_node in node.value:
                key = loader.construct_object(key_node, deep=deep)
                if key in mapping:
                    raise SkillStepReceiptError("duplicate_check_policy_key")
                mapping[key] = loader.construct_object(value_node, deep=deep)
            return mapping

        UniqueKeyLoader.add_constructor(
            yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, construct_unique_mapping,
        )
        data = yaml.load(policy_path.read_text(encoding="utf-8"), Loader=UniqueKeyLoader)
    except SkillStepReceiptError:
        raise
    except (OSError, UnicodeError, yaml.YAMLError, TypeError):
        raise SkillStepReceiptError("check_policy_unavailable") from None
    if not isinstance(data, dict) or set(data) != {"schema_version", "required_checks"}:
        raise SkillStepReceiptError("invalid_check_policy")
    entries = data["required_checks"]
    if (type(data["schema_version"]) is not int or data["schema_version"] != 1
            or not isinstance(entries, list) or len(entries) > 4096):
        raise SkillStepReceiptError("invalid_check_policy")
    matches = []
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {
            "skill_id", "skill_revision", "step_id", "check_ids",
        }:
            raise SkillStepReceiptError("invalid_check_policy_entry")
        key = (entry["skill_id"], entry["skill_revision"], entry["step_id"])
        if key in seen:
            raise SkillStepReceiptError("duplicate_check_policy_entry")
        seen.add(key)
        check_ids = entry["check_ids"]
        if (not isinstance(entry["skill_id"], str) or not _SLUG.fullmatch(entry["skill_id"])
                or not isinstance(entry["skill_revision"], str)
                or not _HEX64.fullmatch(entry["skill_revision"])
                or not isinstance(entry["step_id"], str) or not _SLUG.fullmatch(entry["step_id"])
                or not isinstance(check_ids, list) or not 1 <= len(check_ids) <= 32
                or any(not isinstance(check, str) or not _CHECK.fullmatch(check)
                       for check in check_ids)
                or len(set(check_ids)) != len(check_ids)):
            raise SkillStepReceiptError("invalid_check_policy_entry")
        if any(check not in HOST_CHECKS for check in check_ids):
            raise SkillStepReceiptError("unknown_host_check")
        if key == (skill_id, skill_revision, step_id):
            matches = check_ids
    return tuple(matches)


def validate_skill_step_receipt(
    receipt: SkillStepCheckReceipt,
    *,
    expected: dict[str, str],
    required_check_ids: tuple[str, ...],
    now: datetime | None = None,
) -> None:
    """Raise a safe reason code unless the controller receipt is exact/current."""
    if not isinstance(receipt, SkillStepCheckReceipt):
        raise SkillStepReceiptError("invalid_receipt_shape")
    receipt.validate_shape()
    expected_fields = {
        "user_id", "run_id", "request_id", "skill_id", "skill_revision",
        "step_id", "attempt_id",
    }
    if not isinstance(expected, dict) or set(expected) != expected_fields:
        raise SkillStepReceiptError("invalid_expected_identity")
    if (any(not isinstance(value, str) or not value or len(value) > 128
            for key, value in expected.items() if key in {
                "user_id", "run_id", "request_id",
            })
            or not isinstance(expected["skill_id"], str)
            or not _SLUG.fullmatch(expected["skill_id"])
            or not isinstance(expected["skill_revision"], str)
            or not _HEX64.fullmatch(expected["skill_revision"])
            or not isinstance(expected["step_id"], str)
            or not _SLUG.fullmatch(expected["step_id"])
            or not isinstance(expected["attempt_id"], str)
            or not _ATTEMPT.fullmatch(expected["attempt_id"])):
        raise SkillStepReceiptError("invalid_expected_identity")
    if not required_check_ids:
        raise SkillStepReceiptError("no_host_checks_configured")
    if (not isinstance(required_check_ids, tuple) or len(required_check_ids) > 32
            or any(not isinstance(check_id, str) or check_id not in HOST_CHECKS
                   for check_id in required_check_ids)
            or len(set(required_check_ids)) != len(required_check_ids)):
        raise SkillStepReceiptError("invalid_required_check_ids")
    if now is not None and not isinstance(now, datetime):
        raise SkillStepReceiptError("validation_time_must_be_utc")
    unsigned = json.dumps(
        receipt.payload(include_signature=False),
        sort_keys=True, separators=(",", ":"),
    ).encode()
    expected_signature = hmac.new(
        _HOST_RECEIPT_KEY, unsigned, hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(receipt.signature, expected_signature):
        raise SkillStepReceiptError("receipt_signature_invalid")
    for key, value in expected.items():
        if getattr(receipt, key, None) != value:
            raise SkillStepReceiptError("receipt_identity_mismatch")
    actual = [outcome.check_id for outcome in receipt.outcomes]
    if actual != list(required_check_ids):
        raise SkillStepReceiptError("receipt_check_set_mismatch")
    if not all(outcome.passed for outcome in receipt.outcomes):
        raise SkillStepReceiptError("required_check_failed")
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None or moment.utcoffset() != timedelta(0):
        raise SkillStepReceiptError("validation_time_must_be_utc")
    moment = moment.astimezone(timezone.utc)
    issued = _parse_time(receipt.issued_at)
    expires = _parse_time(receipt.expires_at)
    if issued > moment + timedelta(seconds=5) or moment - issued > MAX_RECEIPT_AGE:
        raise SkillStepReceiptError("receipt_expired")
    if expires <= moment or expires <= issued or expires - issued > MAX_RECEIPT_TTL:
        raise SkillStepReceiptError("receipt_expired")
