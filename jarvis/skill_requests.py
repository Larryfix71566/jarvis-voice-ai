"""Authenticated, durable request boundary for Skills authoring.

The ledger intentionally stores no task text or credentials. It binds a
user/request UUID to a canonical payload digest and safe lifecycle metadata;
the sandbox session owns the private task brief and candidate files.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import subprocess
import threading
import uuid
from pathlib import Path

from sandbox.durable import atomic_json

_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_jobs: dict[str, threading.Thread] = {}
_jobs_lock = threading.Lock()
_agents: dict[str, object] = {}
_agents_lock = threading.Lock()


class SkillRequestError(ValueError):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _root() -> Path:
    home = Path(os.environ.get(
        "MORTIMER_SANDBOX_HOME",
        str(Path.home() / "Documents/Codex/MortimerSandbox"),
    ))
    directory = home / "skill-requests"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if directory.is_symlink():
        raise SkillRequestError("skill request storage is unavailable", 503)
    os.chmod(directory, 0o700)
    return directory


def _key(user_id: str, request_id: str) -> str:
    return hashlib.sha256(f"{user_id}\0{request_id}".encode()).hexdigest()


def _job_running(user_id: str, request_id: str) -> bool:
    with _jobs_lock:
        job = _jobs.get(_key(user_id, request_id))
        return bool(job and job.is_alive())


def _paths(user_id: str, request_id: str) -> tuple[Path, Path]:
    root = _root()
    key = _key(user_id, request_id)
    return root / f"{key}.json", root / f"{key}.lock"


def _canonical_digest(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _read(path: Path) -> dict | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        raise SkillRequestError("saved request state is unavailable", 503) from None
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise SkillRequestError("saved request state is invalid", 503)
    return value


def reserve(user_id: str, payload: dict) -> tuple[dict, bool]:
    request_id = str(payload["request_id"])
    path, lock_path = _paths(user_id, request_id)
    digest = _canonical_digest(payload)
    with lock_path.open("a") as lock:
        os.chmod(lock_path, 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        previous = _read(path)
        if previous:
            if previous.get("payload_digest") != digest:
                raise SkillRequestError("request_id was already used for a different request", 409)
            return previous, False
        state = {
            "schema_version": 1, "request_id": request_id, "job_id": request_id,
            "user_id": user_id, "payload_digest": digest,
            "operation": payload["operation"], "skill_id": payload["skill_id"],
            "skill_revision": payload.get("skill_revision"),
            "state": "queued", "created_at": _now(), "updated_at": _now(),
        }
        if payload.get("operation") == "draft":
            state["bot_session_id"] = payload.get("bot_session_id")
            state["sandbox_job_id"] = str(uuid.uuid4())
        if payload.get("operation") == "test":
            state["parent_request_id"] = payload.get("job_id")
            parent = get(user_id, payload.get("job_id")) if payload.get("job_id") else None
            state["parent_job_id"] = (parent or {}).get("sandbox_job_id")
            # Snapshot only host-owned association metadata. Never accept a
            # client-supplied agent identity or infer one for older drafts.
            # This is attribution, not evidence that validation has started.
            if (parent and parent.get("operation") == "draft"
                    and parent.get("skill_id") == payload["skill_id"]
                    and isinstance(parent.get("developer_run_id"), str)
                    and parent["developer_run_id"]
                    and isinstance(parent.get("creator_revision"), str)
                    and _DIGEST.fullmatch(parent["creator_revision"])):
                state["originating_developer_run_id"] = parent["developer_run_id"]
                state["originating_creator_revision"] = parent["creator_revision"]
        elif payload.get("operation") == "request_publish":
            # Preserve only the reviewed candidate binding needed to recover a
            # crash after reserve() but before the worker claim. No task text
            # or credential data is stored here.
            state["parent_request_id"] = payload.get("review_artifact_ref")
            parent = get(user_id, payload.get("review_artifact_ref")) if payload.get("review_artifact_ref") else None
            state["parent_job_id"] = (parent or {}).get("sandbox_job_id")
            state["candidate_digest"] = payload.get("candidate_digest")
            state["candidate_revision"] = payload.get("skill_revision")
        atomic_json(path, state)
        os.chmod(path, 0o600)
        return state, True


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def update(user_id: str, request_id: str, **changes) -> dict:
    path, lock_path = _paths(user_id, request_id)
    with lock_path.open("a") as lock:
        os.chmod(lock_path, 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = _read(path)
        if state is None:
            raise SkillRequestError("request is unavailable", 404)
        state.update(changes)
        state["updated_at"] = _now()
        atomic_json(path, state)
        os.chmod(path, 0o600)
        return state


def associate_developer_run(user_id: str, request_id: str, *, session_id: str,
                            run_id: str, creator_revision: str) -> None:
    """Claim a creator request once, under its durable cross-process lock."""
    path, lock_path = _paths(user_id, request_id)
    with lock_path.open("a") as lock:
        os.chmod(lock_path, 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = _read(path)
        if (not state or state.get("operation") != "draft"
                or state.get("bot_session_id") != session_id
                or state.get("state") != "drafting"
                or not state.get("sandbox_job_id") or state.get("cancel_requested")):
            raise SkillRequestError("creator request is no longer dispatchable", 409)
        existing = state.get("developer_run_id")
        if existing and existing != run_id:
            raise SkillRequestError("creator request already belongs to another Developer run", 409)
        if existing and state.get("creator_revision") != creator_revision:
            raise SkillRequestError("creator revision changed", 409)
        state.update(developer_run_id=run_id, creator_revision=creator_revision,
                     updated_at=_now())
        atomic_json(path, state)
        os.chmod(path, 0o600)


def _update_unless_cancel_requested(user_id: str, request_id: str, **changes) -> dict:
    """Apply a worker transition atomically only if cancellation has not won."""
    path, lock_path = _paths(user_id, request_id)
    with lock_path.open("a") as lock:
        os.chmod(lock_path, 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = _read(path)
        if state is None:
            raise SkillRequestError("request is unavailable", 404)
        if state.get("cancel_requested"):
            return state
        state.update(changes)
        state["updated_at"] = _now()
        atomic_json(path, state)
        os.chmod(path, 0o600)
        return state


def _claim_queued_request(user_id: str, request_id: str, *, state_name: str,
                          changes: dict | None = None) -> tuple[dict | None, bool]:
    """Atomically claim a queued request across host processes.

    `_jobs_lock` prevents duplicate workers within this process. The request
    file lock is also required because multiple admin workers may share the
    same durable request directory while holding independent in-memory locks.
    """
    path, lock_path = _paths(user_id, request_id)
    with lock_path.open("a") as lock:
        os.chmod(lock_path, 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = _read(path)
        if state is None or state.get("state") != "queued":
            return state, False
        if changes:
            state.update(changes)
        state["state"] = state_name
        state["updated_at"] = _now()
        atomic_json(path, state)
        os.chmod(path, 0o600)
        return state, True


def _claim_parent_publication(user_id: str, parent_id: str, request_id: str,
                              payload_digest: str, candidate_digest: str,
                              candidate_revision: str) -> bool:
    """Durably allow one publication request for a reviewed creator candidate.

    Request UUID idempotency alone does not coalesce a repeated publish action
    that arrives with a fresh UUID. Claim on the owning draft record under its
    file lock before reserving/starting the publisher request.
    """
    path, lock_path = _paths(user_id, parent_id)
    with lock_path.open("a") as lock:
        os.chmod(lock_path, 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        parent = _read(path)
        if (not parent or parent.get("operation") != "draft"
                or parent.get("state") != "review_ready"
                or parent.get("candidate_digest") != candidate_digest
                or parent.get("candidate_revision") != candidate_revision):
            return False
        claimed_id = parent.get("publish_request_id")
        if claimed_id is not None:
            return (
                claimed_id == request_id
                and parent.get("publish_payload_digest") == payload_digest
            )
        parent.update(
            publish_request_id=request_id,
            publish_payload_digest=payload_digest,
            publish_candidate_digest=candidate_digest,
            publish_candidate_revision=candidate_revision,
            updated_at=_now(),
        )
        atomic_json(path, parent)
        os.chmod(path, 0o600)
        return True


def get(user_id: str, request_id: str) -> dict | None:
    try:
        parsed = str(uuid.UUID(request_id))
    except (ValueError, TypeError, AttributeError):
        raise SkillRequestError("invalid request identifier") from None
    if parsed != request_id:
        raise SkillRequestError("invalid request identifier")
    path, _ = _paths(user_id, request_id)
    state = _read(path)
    if state is None:
        return None
    # Never return the owner identifier or payload binding to the client.
    return {k: v for k, v in state.items() if k not in {"user_id", "payload_digest"}}


def list_for_skill(user_id: str, skill_id: str, *, limit: int = 50) -> list[dict]:
    """Return bounded, content-free request evidence for one owner's skill."""
    if not _SLUG.fullmatch(skill_id) or not 1 <= limit <= 100:
        raise SkillRequestError("invalid skill request query")
    root = _root()
    results = []
    try:
        paths = []
        for item in root.glob("*.json"):
            metadata = item.lstat()
            if item.is_symlink() or not item.is_file():
                continue
            paths.append((metadata.st_mtime, item))
        paths.sort(key=lambda entry: entry[0], reverse=True)
        for _modified_at, path in paths[:2000]:
            state = _read(path)
            if (not state or state.get("user_id") != user_id
                    or state.get("skill_id") != skill_id):
                continue
            if state.get("operation") not in {
                "draft", "test", "request_publish", "request_activation", "request_rollback",
            }:
                continue
            # Candidate identity is useful only when it is a validated SHA-256.
            revision = state.get("candidate_revision")
            digest = state.get("candidate_digest")
            if not isinstance(revision, str) or not _DIGEST.fullmatch(revision):
                revision = None
            if not isinstance(digest, str) or not _DIGEST.fullmatch(digest):
                digest = None
            artifact = state.get("review_artifact")
            results.append({
                "request_id": state.get("request_id"),
                "operation": state.get("operation"),
                "state": state.get("state"),
                "candidate_revision": revision,
                "candidate_digest": digest,
                "created_at": state.get("created_at"),
                "updated_at": state.get("updated_at"),
                "review_artifact_operation": (
                    artifact.get("operation") if isinstance(artifact, dict) else None
                ),
            })
            if len(results) >= limit:
                break
    except OSError:
        raise SkillRequestError("saved request state is unavailable", 503) from None
    return results


def _repository() -> str:
    root = Path(os.environ.get("JARVIS_REPO_ROOT", str(Path(__file__).resolve().parents[1])))
    try:
        remote = subprocess.run(
            ["git", "remote", "get-url", "origin"], cwd=root,
            check=True, capture_output=True, text=True, timeout=3,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        raise RuntimeError("repository origin is not configured") from None
    remote = re.sub(r"\.git$", "", remote)
    match = re.fullmatch(r"(?:https://github\.com/|git@github\.com:)([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)", remote)
    if not match:
        raise RuntimeError("repository origin is not a supported GitHub repository")
    return match.group(1)


def authoring_available() -> bool:
    """Report host prerequisites without starting a VM or returning secrets."""
    from jarvis.auth import auth_enabled
    if not auth_enabled() or not os.environ.get("GITHUB_TOKEN", "").strip():
        return False
    home = Path(os.environ.get(
        "MORTIMER_SANDBOX_HOME",
        str(Path.home() / "Documents/Codex/MortimerSandbox"),
    ))
    settings_path = home / "settings.json"
    try:
        if settings_path.is_symlink():
            return False
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        if settings.get("version") != 1 or not settings.get("images", {}).get("mortimer"):
            return False
        _repository()
        from jarvis.skill_creator_agent import skill_creator_system_prompt
        skill_creator_system_prompt()
        return True
    except Exception:
        return False


def _service(slug: str, *, expected_job_id: str | None = None):
    from jarvis.skill_authoring import SkillAuthoringService
    return SkillAuthoringService(
        slug, expected_job_id=expected_job_id,
        repository=_repository, token=lambda: os.environ.get("GITHUB_TOKEN", ""),
        base_branch=lambda: os.environ.get("JARVIS_BASE_BRANCH", "main"),
    )


def _cancel_service_session(service, expected_run_id: str) -> bool:
    """Accept cancellation only after the same sandbox run reports terminal state."""
    try:
        observed = service.status()
        if not isinstance(observed, dict) or observed.get("run_id") != expected_run_id:
            # The service is scoped to a skill, not to a request. A newer
            # request may have replaced this run while an old worker unwinds;
            # never let its stale cancellation stop the newer run.
            return False
        if observed.get("phase") == "cancelled":
            return True
        result = service.cancel()
        if not isinstance(result, dict) or result.get("ok") is not True:
            return False
        observed = service.status()
        return (
            isinstance(observed, dict)
            and observed.get("run_id") == expected_run_id
            and observed.get("phase") == "cancelled"
        )
    except Exception:
        return False


def _cancel_developer_run(user_id: str, state: dict) -> bool:
    """Cancel and confirm the exact Developer run, if one was associated."""
    developer_run_id = state.get("developer_run_id")
    if not developer_run_id:
        return True
    try:
        from jarvis.runlog.store import get_run
        detail = get_run(developer_run_id)
        run = detail.get("run") if isinstance(detail, dict) else None
        if (not run or run.get("agent") != "developer"
                or run.get("user_id") != user_id
                or run.get("session_id") != state.get("bot_session_id")):
            return False
        if run.get("status") != "running":
            return True
        import httpx
        from jarvis.auth import service_headers
        from jarvis.urls import bot_url
        response = httpx.post(
            f"{bot_url()}/internal/skills/creator/cancel",
            headers=service_headers(),
            json={
                "owner_id": user_id,
                "bot_session_id": state["bot_session_id"],
                "request_id": state["request_id"],
                "developer_run_id": developer_run_id,
            },
            timeout=60.0,
        )
        if response.status_code >= 400 or response.json().get("ok") is not True:
            return False
        detail = get_run(developer_run_id)
        run = detail.get("run") if isinstance(detail, dict) else None
        return bool(run and run.get("status") == "cancelled")
    except Exception:
        return False


def _sandbox_job_id(state: dict, request_id: str) -> str:
    """Resolve the sandbox identity, retaining compatibility with old rows."""
    value = state.get("sandbox_job_id")
    return value if isinstance(value, str) and value else request_id


def _reconcile_draft_cancellation(user_id: str, request_id: str, state: dict,
                                 service=None, result_code="creator_cancelled") -> dict:
    confirmed = _cancel_developer_run(user_id, state)
    try:
        service = service or _service(state["skill_id"])
        sandbox_confirmed = _cancel_service_session(
            service, state.get("sandbox_job_id") or request_id,
        )
        confirmed = confirmed and sandbox_confirmed
    except Exception:
        pass
    return update(
        user_id, request_id,
        state="cancelled" if confirmed else "cancel_requested",
        result_code=(result_code if confirmed else "cancellation_needs_reconciliation"),
        candidate_digest=None, candidate_revision=None,
    )


def _dispatch_developer_creator(user_id: str, state: dict, brief: str) -> dict:
    """Ask the owning live bot session to run the creator as its Developer."""
    import httpx
    from jarvis.auth import service_headers
    from jarvis.urls import bot_url

    response = httpx.post(
        f"{bot_url()}/internal/skills/creator/dispatch",
        headers=service_headers(),
        json={
            "owner_id": user_id,
            "bot_session_id": state["bot_session_id"],
            "request_id": state["request_id"],
            "task_brief": brief,
        },
        timeout=1800.0,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"developer_dispatch_http_{response.status_code}")
    result = response.json()
    if (not isinstance(result, dict) or result.get("ok") is not True
            or result.get("request_id") != state["request_id"]
            or not isinstance(result.get("developer_run_id"), str)):
        raise RuntimeError("developer_dispatch_receipt_invalid")
    return result


def _run_draft(user_id: str, request_id: str, brief: str):
    try:
        state = _update_unless_cancel_requested(user_id, request_id, state="starting")
        if state.get("cancel_requested"):
            update(user_id, request_id, state="cancelled",
                   result_code="cancelled_before_start",
                   candidate_digest=None, candidate_revision=None)
            return
        sandbox_job_id = _sandbox_job_id(state, request_id)
        service = _service(_read_request_slug(user_id, request_id))
        result = service.start_session(brief, run_id=sandbox_job_id)
        if not result.get("ok"):
            failed = _update_unless_cancel_requested(
                user_id, request_id, state="failed",
                error=result.get("error", "sandbox start failed"),
            )
            if failed.get("cancel_requested"):
                _reconcile_draft_cancellation(user_id, request_id, failed, service)
            return
        state = _update_unless_cancel_requested(
            user_id, request_id, state="drafting",
            sandbox_session_id=result.get("session_id"),
            branch=result.get("branch"), source_commit=result.get("source_commit"),
            sandbox_task_id=result.get("sandbox_task"),
        )
        if state.get("cancel_requested"):
            _reconcile_draft_cancellation(
                user_id, request_id, state, service, "cancelled_before_authoring",
            )
            return
        dispatch_result = _dispatch_developer_creator(user_id, state, brief)
        associated = get(user_id, request_id)
        developer_run_id = associated.get("developer_run_id") if associated else None
        if (not isinstance(developer_run_id, str)
                or developer_run_id != dispatch_result.get("developer_run_id")):
            raise RuntimeError("developer_run_association_mismatch")
        from jarvis.runlog.store import get_run
        developer_detail = get_run(developer_run_id)
        developer_run = developer_detail.get("run") if isinstance(developer_detail, dict) else None
        if (not developer_run or developer_run.get("agent") != "developer"
                or developer_run.get("user_id") != user_id
                or developer_run.get("session_id") != state.get("bot_session_id")
                or developer_run.get("status") == "running"):
            raise RuntimeError("developer_run_terminal_receipt_unavailable")
        live = service.status()
        latest = get(user_id, request_id) or state
        if latest.get("result_code") == "creator_declined":
            return
        if latest.get("cancel_requested") or live.get("phase") == "cancelled":
            confirmed = (
                isinstance(live, dict)
                and live.get("run_id") == sandbox_job_id
                and live.get("phase") == "cancelled"
            )
            if not confirmed:
                confirmed = _cancel_service_session(service, sandbox_job_id)
            update(
                user_id, request_id,
                state="cancelled" if confirmed else "cancel_requested",
                result_code=("creator_cancelled" if confirmed
                             else "cancellation_needs_reconciliation"),
                candidate_digest=None, candidate_revision=None,
            )
        elif not isinstance(live, dict) or live.get("run_id") != sandbox_job_id:
            # This slug-scoped service may now point at a different request's
            # VM. Never attach its validation receipt to this request.
            mismatched = _update_unless_cancel_requested(
                user_id, request_id, state="draft_needs_attention",
                result_code="sandbox_run_mismatch",
                candidate_digest=None, candidate_revision=None,
            )
            if mismatched.get("cancel_requested"):
                _reconcile_draft_cancellation(user_id, request_id, mismatched, service)
        elif live.get("validated_ok") is True and live.get("package_revision"):
            finished = _update_unless_cancel_requested(
                user_id, request_id, state="review_ready",
                candidate_digest=live.get("candidate"),
                candidate_revision=live.get("package_revision"),
                result_code="offline_candidate_validated",
            )
            if finished.get("cancel_requested"):
                _reconcile_draft_cancellation(user_id, request_id, finished, service)
        else:
            # Prose and provider claims cannot create a validation receipt.
            code = ("creator_needs_attention"
                    if developer_run.get("status") == "ok"
                    else "creator_failed")
            finished = _update_unless_cancel_requested(
                user_id, request_id, state="draft_needs_attention", result_code=code,
            )
            if finished.get("cancel_requested"):
                _reconcile_draft_cancellation(user_id, request_id, finished, service)
    except Exception as exc:
        try:
            current = get(user_id, request_id)
        except Exception:
            current = None
        if current and current.get("cancel_requested"):
            _reconcile_draft_cancellation(user_id, request_id, current)
        else:
            # start_session may have allocated the sandbox session before an
            # exception or lost response reached this worker. Keep the stable
            # run_id available for status reconciliation; calling a failure
            # terminal here would strand a live VM behind an unreplayable UUID.
            result_code = (
                "developer_dispatch_result_uncertain"
                if current.get("sandbox_session_id")
                else "sandbox_start_result_uncertain"
            )
            uncertain = _update_unless_cancel_requested(
                user_id, request_id, state="needs_reconciliation",
                result_code=result_code,
                error=f"sandbox start result uncertain ({type(exc).__name__})",
            )
            if uncertain.get("cancel_requested"):
                _reconcile_draft_cancellation(user_id, request_id, uncertain)
    finally:
        with _jobs_lock:
            _jobs.pop(_key(user_id, request_id), None)


def _read_request_slug(user_id: str, request_id: str) -> str:
    path, _ = _paths(user_id, request_id)
    state = _read(path)
    if not state:
        raise RuntimeError("request disappeared")
    return state["skill_id"]


def start_draft(user_id: str, payload: dict) -> tuple[dict, bool]:
    # Refuse creator self-modification before creating a durable request or
    # claiming work. The service applies the same invariant again at the
    # sandbox boundary for callers that bypass this request coordinator.
    from jarvis.selfedit.skill_policy import SkillAuthoringPolicy
    try:
        SkillAuthoringPolicy(payload.get("skill_id"))
    except ValueError as exc:
        raise SkillRequestError(str(exc)) from None
    _state, created = reserve(user_id, payload)
    key = _key(user_id, payload["request_id"])
    with _jobs_lock:
        current = get(user_id, payload["request_id"])
        if not current or current.get("state") != "queued":
            return current, False
        if key in _jobs and _jobs[key].is_alive():
            return get(user_id, payload["request_id"]), False
        # A queued record is safe to resume: no worker has begun. Once this
        # durable state moves to starting, a restart reconciles instead of
        # repeating an uncertain VM allocation. The file-locked compare-and-
        # set also prevents a second host process from launching the same job.
        _, did_claim = _claim_queued_request(
            user_id, payload["request_id"], state_name="starting",
        )
        if not did_claim:
            return get(user_id, payload["request_id"]), False
        worker = threading.Thread(target=_run_draft,
                                  args=(user_id, payload["request_id"], payload["task_brief"]),
                                  daemon=True)
        try:
            _jobs[key] = worker
            worker.start()
        except RuntimeError:
            _jobs.pop(key, None)
            update(user_id, payload["request_id"], state="failed", error="sandbox worker could not start")
            raise
    return get(user_id, payload["request_id"]), created


def _run_offline_validation(user_id: str, request_id: str, skill_id: str):
    try:
        initial = _update_unless_cancel_requested(user_id, request_id, state="testing")
        if initial.get("cancel_requested"):
            _reconcile_test_cancellation(user_id, request_id, skill_id, initial)
            return
        parent_run_id = initial.get("parent_job_id")
        if (initial.get("operation") != "test"
                or not isinstance(parent_run_id, str)
                or not parent_run_id):
            failed = _update_unless_cancel_requested(
                user_id, request_id, state="failed",
                result_code="offline_validation_parent_unavailable",
            )
            if failed.get("cancel_requested"):
                _reconcile_test_cancellation(user_id, request_id, skill_id, failed)
            return
        service = _service(skill_id, expected_job_id=parent_run_id)
        # Bind any post-restart recovery to an observed pre-validation state.
        # If the process dies after validate() starts, a later status receipt
        # is useful only when it is for this exact sandbox run and represents
        # a transition from the state we observed before the call.
        baseline = service.status()
        if not isinstance(baseline, dict) or baseline.get("run_id") != parent_run_id:
            _update_unless_cancel_requested(
                user_id, request_id, state="needs_reconciliation",
                result_code="offline_validation_result_uncertain",
            )
            return
        _update_unless_cancel_requested(
            user_id, request_id,
            validation_baseline_phase=baseline.get("phase"),
            validation_baseline_candidate=baseline.get("candidate"),
            validation_baseline_revision=baseline.get("package_revision"),
            validation_attempt_id=str(uuid.uuid4()),
            validation_started_at=_now(),
        )
        latest = get(user_id, request_id)
        if latest and latest.get("cancel_requested"):
            _reconcile_test_cancellation(user_id, request_id, skill_id, latest, service)
            return
        from jarvis.skill_validation_activity import sync_validation_activity
        sync_validation_activity(user_id, request_id, start=True)
        result = service.validate(validation_request_id=request_id,
                                  validation_attempt_id=latest["validation_attempt_id"])
        latest = get(user_id, request_id)
        if latest and latest.get("cancel_requested"):
            _reconcile_test_cancellation(user_id, request_id, skill_id, latest, service)
            return
        # Validation acts on whichever session is active for this slug. Bind
        # its result again after the call so a replaced session cannot lend its
        # candidate to this older request.
        try:
            validated_run = service.status()
        except Exception:
            validated_run = None
        if (not isinstance(validated_run, dict)
                or validated_run.get("run_id") != parent_run_id):
            mismatched = _update_unless_cancel_requested(
                user_id, request_id, state="needs_reconciliation",
                candidate_digest=None, candidate_revision=None,
                result_code="offline_validation_run_mismatch",
            )
            if mismatched.get("cancel_requested"):
                _reconcile_test_cancellation(user_id, request_id, skill_id, mismatched, service)
            return
        passed = result.get("ok") is True
        receipt = result.get("skill_validation") or {}
        candidate_digest = receipt.get("candidate_digest")
        package_revision = receipt.get("package_revision")
        if passed and (not isinstance(candidate_digest, str)
                       or not _DIGEST.fullmatch(candidate_digest)
                       or not isinstance(package_revision, str)
                       or not _DIGEST.fullmatch(package_revision)):
            passed = False
        if passed and (validated_run.get("validated_ok") is not True
                       or validated_run.get("validation_request_id") != request_id
                       or validated_run.get("validation_attempt_id") != latest["validation_attempt_id"]
                       or validated_run.get("candidate") != candidate_digest
                       or validated_run.get("package_revision") != package_revision):
            passed = False
        finished = _update_unless_cancel_requested(
            user_id, request_id,
            state="completed" if passed else "failed",
            candidate_digest=candidate_digest if passed else None,
            candidate_revision=package_revision if passed else None,
            result_code="offline_validation_passed" if passed else "offline_validation_failed",
        )
        if finished.get("cancel_requested"):
            _reconcile_test_cancellation(user_id, request_id, skill_id, finished, service)
    except Exception as exc:
        try:
            current = get(user_id, request_id)
        except Exception:
            current = None
        if current and current.get("cancel_requested"):
            _reconcile_test_cancellation(user_id, request_id, skill_id, current)
        else:
            failed = _update_unless_cancel_requested(
                user_id, request_id, state="failed",
                result_code=f"offline_validation_error_{type(exc).__name__}",
            )
            if failed.get("cancel_requested"):
                _reconcile_test_cancellation(user_id, request_id, skill_id, failed)
    finally:
        from jarvis.skill_validation_activity import sync_validation_activity
        sync_validation_activity(user_id, request_id)
        with _jobs_lock:
            _jobs.pop(_key(user_id, request_id), None)


def _reconcile_test_cancellation(user_id: str, request_id: str, skill_id: str,
                                 state: dict, service=None) -> dict:
    parent_run_id = state.get("parent_job_id")
    confirmed = False
    if state.get("operation") == "test" and isinstance(parent_run_id, str) and parent_run_id:
        try:
            service = service or _service(skill_id)
            confirmed = _cancel_service_session(service, parent_run_id)
        except Exception:
            confirmed = False
    return update(
        user_id, request_id,
        state="cancelled" if confirmed else "cancel_requested",
        candidate_revision=None,
        result_code=("offline_validation_cancelled" if confirmed
                     else "cancellation_needs_reconciliation"),
    )


def _start_queued_offline_validation(user_id: str, request_id: str,
                                     skill_id: str) -> tuple[dict, bool]:
    key = _key(user_id, request_id)
    with _jobs_lock:
        state = get(user_id, request_id)
        if state is None or state.get("state") != "queued":
            return state, False
        if key in _jobs and _jobs[key].is_alive():
            return state, False
        # This durable transition makes a crash before thread startup
        # conservative: testing is never replayed after an uncertain start.
        _, did_claim = _claim_queued_request(
            user_id, request_id, state_name="testing",
        )
        if not did_claim:
            return get(user_id, request_id), False
        worker = threading.Thread(
            target=_run_offline_validation,
            args=(user_id, request_id, skill_id),
            daemon=True,
        )
        try:
            _jobs[key] = worker
            worker.start()
        except RuntimeError:
            _jobs.pop(key, None)
            update(user_id, request_id, state="failed",
                   result_code="offline_validation_worker_failed")
            raise
    return get(user_id, request_id), True


def start_offline_validation(user_id: str, payload: dict) -> tuple[dict, bool]:
    state, created = reserve(user_id, payload)
    if not created and state.get("state") != "queued":
        return get(user_id, payload["request_id"]), False
    current, started = _start_queued_offline_validation(
        user_id, payload["request_id"], payload["skill_id"],
    )
    return current, created or started


def start_publish(user_id: str, payload: dict) -> tuple[dict, bool]:
    """Publish one exact, user-reviewed candidate through the host publisher."""
    # An identical owner-scoped request must replay its durable receipt even
    # after the parent candidate has transitioned to PR-open.
    if get(user_id, payload["request_id"]) is not None:
        state, _created = reserve(user_id, payload)
        if state.get("operation") == "request_publish" and state.get("state") == "queued":
            resumed, started = _start_queued_publish(user_id, payload["request_id"])
            return resumed or get(user_id, payload["request_id"]), started
        return get(user_id, payload["request_id"]), False
    parent_id = payload["review_artifact_ref"]
    parent = reconcile(user_id, parent_id)
    if (not parent or parent.get("operation") != "draft"
            or parent.get("state") != "review_ready"
            or parent.get("skill_id") != payload["skill_id"]
            or parent.get("candidate_digest") != payload["candidate_digest"]
            or parent.get("candidate_revision") != payload["skill_revision"]):
        raise SkillRequestError("matching reviewed candidate is required", 409)
    if not _claim_parent_publication(
            user_id, parent_id, payload["request_id"], _canonical_digest(payload),
            payload["candidate_digest"], payload["skill_revision"]):
        raise SkillRequestError(
            "a publication request already exists for this reviewed candidate", 409,
        )
    state, created = reserve(user_id, payload)
    if not created:
        if state.get("state") == "queued":
            resumed, started = _start_queued_publish(user_id, payload["request_id"])
            return resumed or get(user_id, payload["request_id"]), started
        return get(user_id, payload["request_id"]), False
    queued, started = _start_queued_publish(user_id, payload["request_id"])
    return queued or get(user_id, payload["request_id"]), created or started


def _start_queued_publish(user_id: str, request_id: str) -> tuple[dict | None, bool]:
    """Claim and launch only a durable queued publication request.

    A queued publication proves the host has not crossed the submit barrier.
    The parent record and payload digest must still agree before recovery.
    """
    key = _key(user_id, request_id)
    with _jobs_lock:
        state = get(user_id, request_id)
        if state is None or state.get("state") != "queued":
            return state, False
        if key in _jobs and _jobs[key].is_alive():
            return state, False
        parent_id = state.get("parent_request_id") or state.get("parent_job_id")
        parent = get(user_id, parent_id) if isinstance(parent_id, str) else None
        if not (
            parent
            and parent.get("operation") == "draft"
            and parent.get("state") == "review_ready"
            and parent.get("publish_request_id") == request_id
            and parent.get("publish_payload_digest") == _request_payload_digest(user_id, request_id)
            and parent.get("publish_candidate_digest") == state.get("candidate_digest")
            and parent.get("publish_candidate_revision") == state.get("candidate_revision")
            and parent.get("candidate_digest") == state.get("candidate_digest")
            and parent.get("candidate_revision") == state.get("candidate_revision")
            and parent.get("sandbox_job_id") == state.get("parent_job_id")
        ):
            failed = update(
                user_id, request_id, state="failed",
                result_code="publication_recovery_binding_mismatch",
            )
            return failed, False
        _claimed, did_claim = _claim_queued_request(
            user_id, request_id, state_name="publishing",
        )
        if not did_claim:
            return get(user_id, request_id), False
        worker = threading.Thread(
            target=_run_publish,
            args=(user_id, request_id, state.get("parent_job_id")),
            daemon=True,
        )
        try:
            _jobs[key] = worker
            worker.start()
        except RuntimeError:
            _jobs.pop(key, None)
            update(user_id, request_id, state="failed", result_code="publish_worker_failed")
            raise
        return get(user_id, request_id), True


def _request_payload_digest(user_id: str, request_id: str) -> str | None:
    path, _lock_path = _paths(user_id, request_id)
    state = _read(path)
    return state.get("payload_digest") if state else None


def _claim_publication_submit(user_id: str, request_id: str) -> bool:
    """Win a durable barrier before the one non-repeatable publisher call."""
    path, lock_path = _paths(user_id, request_id)
    with lock_path.open("a") as lock:
        os.chmod(lock_path, 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = _read(path)
        if (state is None or state.get("state") != "publishing"
                or state.get("cancel_requested")):
            return False
        state.update(state="publication_submitting", submit_started_at=_now())
        state["updated_at"] = _now()
        atomic_json(path, state)
        os.chmod(path, 0o600)
        return True


def _published_receipt_matches(live: dict, request: dict) -> bool:
    """Require the recovered PR receipt to identify the reviewed candidate."""
    return (
        live.get("phase") == "published"
        and live.get("run_id") == request.get("parent_job_id")
        and live.get("candidate") == request.get("candidate_digest")
        and live.get("package_revision") == request.get("candidate_revision")
        and isinstance(live.get("pr_url"), str)
        and bool(live["pr_url"])
    )


def _run_publish(user_id: str, request_id: str, draft_id: str):
    try:
        state = get(user_id, request_id)
        if state is None or state.get("state") != "publishing" or state.get("cancel_requested"):
            return
        service = _service(state["skill_id"])
        live = service.status()
        if live.get("run_id") != draft_id:
            _update_unless_cancel_requested(
                user_id, request_id, state="failed", result_code="candidate_changed_after_review",
            )
            return
        if live.get("phase") == "published":
            if not _published_receipt_matches(live, state):
                _update_unless_cancel_requested(
                    user_id, request_id, state="publication_needs_reconciliation",
                    result_code="published_candidate_mismatch",
                )
                return
            completed = _update_unless_cancel_requested(
                user_id, request_id, state="completed", result_code="review_pr_open",
                pr_url=live["pr_url"], pr_number=live.get("pr_number"),
            )
            if completed.get("state") == "completed":
                _mark_parent_pr_open(
                    user_id, state.get("parent_request_id") or draft_id,
                    live["pr_url"], live.get("pr_number"),
                )
            return
        if live.get("phase") in {"publication_pending", "publishing"}:
            _update_unless_cancel_requested(
                user_id, request_id, state="publication_needs_reconciliation",
                result_code="publication_result_uncertain",
            )
            return
        if (live.get("candidate") != state.get("candidate_digest")
                or live.get("package_revision") != state.get("candidate_revision")
                or not live.get("validated_ok")):
            _update_unless_cancel_requested(
                user_id, request_id, state="failed", result_code="candidate_changed_after_review",
            )
            return
        # A publication already recorded by the sandbox is authoritative.
        # Never retry an ambiguous publication side effect after a host restart.
        if not _claim_publication_submit(user_id, request_id):
            return
        result = service.submit()
        if (result.get("ok") is True and isinstance(result.get("pr_url"), str)
                and bool(result["pr_url"])):
            completed = _update_unless_cancel_requested(
                user_id, request_id, state="completed", result_code="review_pr_open",
                pr_url=result["pr_url"], pr_number=result.get("pr_number"),
            )
            if completed.get("state") == "completed":
                _mark_parent_pr_open(
                    user_id, state.get("parent_request_id") or draft_id,
                    result["pr_url"], result.get("pr_number"),
                )
        else:
            # Do not automatically repeat a potentially successful external
            # side effect. Reconciliation can observe a PR already recorded.
            _update_unless_cancel_requested(
                user_id, request_id, state="publication_needs_reconciliation",
                result_code="publication_result_uncertain",
            )
    except Exception as exc:
        _update_unless_cancel_requested(
            user_id, request_id, state="publication_needs_reconciliation",
            result_code=f"publication_error_{type(exc).__name__}",
        )
    finally:
        with _jobs_lock:
            _jobs.pop(_key(user_id, request_id), None)


def _mark_parent_pr_open(user_id: str, draft_id: str, url: str, number: int | None):
    parent = get(user_id, draft_id)
    if (parent and parent.get("operation") == "draft"
            and parent.get("state") in {"review_ready", "pr_open"}):
        update(user_id, draft_id, state="pr_open", result_code="review_pr_open",
               pr_url=url, pr_number=number)


def cancel_job(user_id: str, cancel_request: dict) -> tuple[dict, bool]:
    cancel_record, created = reserve(user_id, cancel_request)
    if not created:
        return get(user_id, cancel_request["request_id"]), False
    job = get(user_id, cancel_request["job_id"])
    if job is None or job.get("job_id") != cancel_request["job_id"]:
        update(user_id, cancel_request["request_id"], state="failed", error="job is unavailable")
        raise SkillRequestError("job is unavailable", 404)
    if job.get("skill_id") != cancel_request["skill_id"]:
        update(user_id, cancel_request["request_id"], state="failed", error="job is unavailable")
        raise SkillRequestError("job is unavailable", 404)
    if job.get("operation") == "request_publish":
        # Publication is cancellable only before the durable submit barrier.
        # Once submission may have begun, cancellation cannot undo or safely
        # characterize its external outcome; force reconciliation instead.
        target_path, target_lock_path = _paths(user_id, cancel_request["job_id"])
        with target_lock_path.open("a") as target_lock:
            os.chmod(target_lock_path, 0o600)
            fcntl.flock(target_lock, fcntl.LOCK_EX)
            current = _read(target_path)
            if current is None:
                raise SkillRequestError("job is unavailable", 404)
            if current.get("state") in {"queued", "publishing"} and not current.get("cancel_requested"):
                current.update(
                    state="cancelled", cancel_requested=True,
                    result_code="publication_cancelled_before_submit",
                    updated_at=_now(),
                )
                atomic_json(target_path, current)
                os.chmod(target_path, 0o600)
            elif current.get("state") == "cancelled":
                pass
            else:
                update(user_id, cancel_request["request_id"], state="failed",
                       error="publication may have started; reconcile its result before retrying")
                raise SkillRequestError(
                    "publication may have started; reconcile its result before retrying", 409,
                )
        cancel_record = update(
            user_id, cancel_request["request_id"], state="cancelled",
            target_job_id=cancel_request["job_id"],
        )
        return cancel_record, True
    if job["state"] in {"completed", "failed", "cancelled"}:
        update(user_id, cancel_request["request_id"], state="completed", target_job_id=cancel_request["job_id"])
        return get(user_id, cancel_request["request_id"]), True
    # Cancellation is a request until the VM confirms its terminal state.
    target = update(user_id, cancel_request["job_id"], cancel_requested=True, state="cancel_requested")
    # If the worker already created the VM session, issue cancellation through
    # the same host-owned Session API. During setup, leave a durable request
    # flag for the worker to observe after allocation completes.
    target_session = (
        target.get("parent_job_id") if target.get("operation") == "test"
        else _sandbox_job_id(target, cancel_request["job_id"])
    )
    if target.get("sandbox_session_id") or target_session:
        try:
            developer_cancelled = _cancel_developer_run(user_id, target)
            with _agents_lock:
                agent = _agents.get(_key(user_id, cancel_request["job_id"]))
            if agent is not None:
                agent.request_cancel()
            service = _service(target["skill_id"])
            live = service.status()
            if (live.get("run_id") == target_session
                    and (live.get("active") or live.get("phase") == "cancelled")
                    and _cancel_service_session(service, target_session)
                    and developer_cancelled):
                target = update(user_id, cancel_request["job_id"], state="cancelled")
        except Exception:
            pass
    cancel_record = update(user_id, cancel_request["request_id"],
                           state="cancelled" if target.get("state") == "cancelled" else "cancel_requested",
                           target_job_id=cancel_request["job_id"])
    return cancel_record, True


def reconcile(user_id: str, request_id: str) -> dict | None:
    state = _reconcile_request(user_id, request_id)
    if state and state.get("operation") == "test":
        from jarvis.skill_validation_activity import sync_validation_activity
        sync_validation_activity(user_id, request_id)
    return state


def _reconcile_request(user_id: str, request_id: str) -> dict | None:
    """Reconcile a host restart against the sandbox's authoritative session."""
    state = get(user_id, request_id)
    if state is None:
        return state
    if state.get("operation") == "request_publish":
        if state.get("state") == "queued":
            # reserve() is written before the worker claim. A durable queued
            # record is therefore safe to claim exactly once after restart.
            resumed, _started = _start_queued_publish(user_id, request_id)
            return resumed or state
        if state.get("state") == "cancelled":
            return state
        try:
            live = _service(state["skill_id"]).status()
        except Exception:
            # After a host restart there is no worker left to advance this
            # request. Keep an active worker's state intact during a transient
            # status failure, but surface a dead worker's ambiguous outcome so
            # polling does not leave it appearing to publish forever. A later
            # reconcile can still complete from an exact sandbox receipt.
            if state.get("state") in {"publishing", "publication_submitting"} and not _job_running(
                    user_id, request_id):
                return update(
                    user_id, request_id,
                    state="publication_needs_reconciliation",
                    result_code="publication_status_unavailable",
                )
            return state
        if live.get("run_id") == state.get("parent_job_id"):
            if live.get("phase") == "published":
                if not _published_receipt_matches(live, state):
                    return _update_unless_cancel_requested(
                        user_id, request_id,
                        state="publication_needs_reconciliation",
                        result_code="published_candidate_mismatch",
                    )
                completed = _update_unless_cancel_requested(
                    user_id, request_id, state="completed", result_code="review_pr_open",
                    pr_url=live.get("pr_url"), pr_number=live.get("pr_number"),
                )
                if completed.get("state") == "completed":
                    _mark_parent_pr_open(
                        user_id, state.get("parent_request_id") or state["parent_job_id"], live["pr_url"], live.get("pr_number"),
                    )
                return completed
            if (live.get("phase") in {"publication_pending", "publishing"}
                    and not _job_running(user_id, request_id)):
                return update(user_id, request_id, state="publication_needs_reconciliation",
                              result_code="publication_result_uncertain")
            if live.get("phase") in {"publication_pending", "publishing"}:
                return state
            if (state.get("state") == "publication_submitting"
                    and not _job_running(user_id, request_id)):
                return update(
                    user_id, request_id, state="publication_needs_reconciliation",
                    result_code="publication_result_uncertain",
                )
        return state
    if state.get("operation") == "test":
        if state.get("cancel_requested"):
            return _reconcile_test_cancellation(
                user_id, request_id, state["skill_id"], state,
            )
        if state.get("state") == "queued":
            # A durable queued state proves validate() was not started. It is
            # safe to resume this explicit request exactly once after restart.
            resumed, _started = _start_queued_offline_validation(
                user_id, request_id, state["skill_id"],
            )
            return resumed or state
        if state.get("state") != "testing" or _job_running(user_id, request_id):
            return state
        try:
            live = _service(state["skill_id"]).status()
        except Exception:
            return update(user_id, request_id, state="needs_reconciliation",
                          result_code="offline_validation_result_uncertain")
        if live.get("run_id") != state.get("parent_job_id"):
            return update(user_id, request_id, state="needs_reconciliation",
                          result_code="offline_validation_run_mismatch")
        baseline_phase = state.get("validation_baseline_phase")
        if (live.get("phase") == "validated" and live.get("validated_ok") is True
                and (not state.get("validation_attempt_id") or (
                    live.get("validation_request_id") == request_id
                    and live.get("validation_attempt_id") == state["validation_attempt_id"]))
                and isinstance(baseline_phase, str) and baseline_phase != "validated"
                and isinstance(live.get("candidate"), str)
                and _DIGEST.fullmatch(live["candidate"])
                and isinstance(live.get("package_revision"), str)
                and _DIGEST.fullmatch(live["package_revision"])
                and (state.get("validation_baseline_candidate") in (None, live["candidate"]))):
            # SkillAuthoringService.status exposes package_revision only when
            # its durable host validation receipt matches the frozen candidate.
            return update(
                user_id, request_id, state="completed",
                candidate_digest=live["candidate"],
                candidate_revision=live["package_revision"],
                result_code="offline_validation_passed",
            )
        if (live.get("phase") == "validation_failed"
                and isinstance(baseline_phase, str) and baseline_phase != "validation_failed"):
            return update(user_id, request_id, state="failed",
                          candidate_digest=None, candidate_revision=None,
                          result_code="offline_validation_failed")
        if live.get("phase") == "cancelled":
            return update(user_id, request_id, state="cancelled",
                          candidate_digest=None, candidate_revision=None,
                          result_code="offline_validation_cancelled")
        # Do not call validate() again: the previous process may have already
        # caused it to run. Surface ambiguity instead of leaving `testing`
        # forever or inferring a result from an unrelated/old receipt.
        return update(user_id, request_id, state="needs_reconciliation",
                      candidate_digest=None, candidate_revision=None,
                      result_code="offline_validation_result_uncertain")
    if state.get("operation") != "draft":
        return state
    sandbox_job_id = _sandbox_job_id(state, request_id)
    if state.get("state") == "review_ready":
        try:
            live = _service(state["skill_id"]).status()
        except Exception:
            return state
        if live.get("run_id") != sandbox_job_id:
            return state
        if live.get("phase") == "published":
            # A published sandbox record is only authoritative for this review
            # request when it still identifies the exact candidate that the
            # owner approved. Never promote a stale or mismatched PR receipt.
            if not (
                live.get("candidate") == state.get("candidate_digest")
                and live.get("package_revision") == state.get("candidate_revision")
                and isinstance(live.get("pr_url"), str)
                and bool(live["pr_url"])
            ):
                return update(
                    user_id, request_id,
                    state="publication_needs_reconciliation",
                    result_code="published_candidate_mismatch",
                )
            completed = update(
                user_id, request_id, state="pr_open", result_code="review_pr_open",
                pr_url=live["pr_url"], pr_number=live.get("pr_number"),
            )
            _mark_parent_pr_open(
                user_id, state.get("parent_request_id") or request_id,
                live["pr_url"], live.get("pr_number"),
            )
            return completed
        if (live.get("phase") in {"publishing", "publication_pending"}
                and live.get("candidate") == state.get("candidate_digest")
                and live.get("package_revision") == state.get("candidate_revision")):
            return state
        exact_receipt = (
            live.get("phase") == "validated"
            and live.get("validated_ok") is True
            and live.get("candidate") == state.get("candidate_digest")
            and live.get("package_revision") == state.get("candidate_revision")
        )
        if exact_receipt:
            return state
        if live.get("phase") == "cancelled":
            return update(user_id, request_id, state="cancelled", result_code="creator_cancelled",
                          candidate_digest=None, candidate_revision=None)
        return update(user_id, request_id, state="draft_needs_attention",
                      result_code="candidate_changed_after_review",
                      candidate_digest=None, candidate_revision=None)
    if state.get("state") not in {
        "starting", "drafting", "testing", "cancel_requested", "needs_reconciliation",
    }:
        return state
    try:
        live = _service(state["skill_id"]).status()
    except Exception:
        return state
    if live.get("run_id") != sandbox_job_id:
        return state
    if state.get("cancel_requested") and live.get("phase") not in {"published", "reverted"}:
        service = _service(state["skill_id"])
        if live.get("phase") == "cancelled" or _cancel_service_session(service, sandbox_job_id):
            return update(user_id, request_id, state="cancelled", result_code="creator_cancelled",
                          candidate_digest=None, candidate_revision=None)
        return state
    changes = {
        "sandbox_session_id": live.get("id") or state.get("sandbox_session_id"),
        "branch": live.get("branch"),
        "source_commit": live.get("ref"),
    }
    phase = live.get("phase")
    if phase in {"cancelled", "reverted"}:
        changes["state"] = "cancelled"
    elif phase in {"published", "setup_failed"}:
        changes["state"] = "completed" if phase == "published" else "failed"
    elif (phase == "validated" and live.get("validated_ok") is True
          and isinstance(live.get("package_revision"), str)):
        changes.update(
            state="review_ready", candidate_digest=live.get("candidate"),
            candidate_revision=live.get("package_revision"),
            result_code="offline_candidate_validated",
        )
    elif phase == "validation_failed":
        changes.update(state="draft_needs_attention", result_code="offline_validation_failed",
                       candidate_digest=None, candidate_revision=None)
    elif live.get("active"):
        changes["state"] = "drafting"
    # Reconciliation reads the sandbox outside the request-file lock. A cancel
    # can win while status() is in flight, so never let this stale snapshot
    # overwrite its durable cancel_requested state with drafting/review_ready.
    reconciled = _update_unless_cancel_requested(user_id, request_id, **changes)
    if reconciled.get("cancel_requested"):
        return _reconcile_draft_cancellation(
            user_id, request_id, reconciled, _service(state["skill_id"]),
        )
    return reconciled
