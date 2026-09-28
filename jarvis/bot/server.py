"""Authenticated, fail-closed entrypoint for Pipecat's bot runner."""

from __future__ import annotations

import asyncio
import importlib
import logging
import sys
import threading
from typing import Any

from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from jarvis.auth import auth_enabled, service_headers
from jarvis.authmw import BearerAuthMiddleware
from jarvis.bind import BindRefused, resolve_bind_host, resolve_port
from jarvis.bot.bot import _runner_main_preserving_env
from jarvis.vault import inject_env

# Vault credentials must be available before startup checks and child client
# construction; the bot's first settings load happens after the listener starts.
inject_env()

# Pipecat's runner loads dotenv with override=True. Retain the established
# exported-environment precedence before reading its app or invoking main.
runner_main = _runner_main_preserving_env()
runner_app = importlib.import_module("pipecat.runner.run").app

BOT_PORT_ENV = "JARVIS_BOT_PORT"
DEFAULT_BOT_PORT = 7860

logger = logging.getLogger(__name__)
_creator_tasks: set[asyncio.Task] = set()
_creator_runs: dict[str, tuple[str, str, str, asyncio.Task]] = {}
_creator_runs_lock = threading.RLock()


class SkillCreatorDispatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    owner_id: str = Field(min_length=1, max_length=64)
    bot_session_id: str = Field(min_length=36, max_length=36)
    request_id: str = Field(min_length=36, max_length=36)
    task_brief: str = Field(min_length=1, max_length=12000)


class SkillCreatorCancelIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    owner_id: str = Field(min_length=1, max_length=64)
    bot_session_id: str = Field(min_length=36, max_length=36)
    request_id: str = Field(min_length=36, max_length=36)
    developer_run_id: str = Field(min_length=36, max_length=36)


def _safe_creator_event(event: dict) -> dict | None:
    """Forward lifecycle metadata while keeping briefs and draft contents private."""
    if not isinstance(event, dict):
        return None
    kind = event.get("type")
    if kind not in {"agent_start", "agent_tool", "agent_tool_result", "agent_done"}:
        return None
    safe = {"type": kind}
    for key in ("agent", "run_id", "tool", "ok", "latency_ms", "display_name"):
        value = event.get(key)
        if isinstance(value, (str, bool, int, float)):
            safe[key] = value
    if kind == "agent_start":
        safe["task"] = "Authoring a skill in the scoped sandbox."
    return safe


def _internal_bot_request(request: Request) -> None:
    if not auth_enabled():
        raise HTTPException(status_code=503, detail="internal creator dispatch requires bearer authentication")
    identity = request.scope.get("client_identity")
    if identity is None or getattr(identity, "name", None) != "service-bot":
        raise HTTPException(status_code=403, detail="creator dispatch requires service-bot identity")


async def _dispatch_creator(body: SkillCreatorDispatchIn, request: Request) -> dict[str, Any]:
    _internal_bot_request(request)
    import os

    import httpx

    from jarvis.auth import service_headers
    from jarvis.bot.skill_creator_dispatch import active_session, dispatch_creator
    from jarvis.skill_creator_agent import (
        creator_tool_specs,
        skill_creator_prompt_for_task,
    )
    from jarvis.tenant import user_id_scope
    from jarvis.urls import ADMIN_URL_ENV, DEFAULT_ADMIN_URL

    active = active_session(body.bot_session_id)
    if active is None or active.owner_id != body.owner_id:
        raise HTTPException(status_code=409, detail="creator requires the owner's live Developer session")
    if active.sensitive_turn is None or active.sensitive_turn.is_armed():
        raise HTTPException(status_code=409, detail="creator requires an ordinary live session")
    try:
        with user_id_scope(body.owner_id):
            system_prompt, _revision = skill_creator_prompt_for_task(body.task_brief)
        tools = creator_tool_specs()
    except Exception as exc:
        logger.warning("skill_creator_dispatch_unavailable error_type=%s", type(exc).__name__[:64])
        raise HTTPException(status_code=503, detail="reviewed creator package is unavailable") from None

    admin_url = os.environ.get(ADMIN_URL_ENV) or DEFAULT_ADMIN_URL
    client = httpx.AsyncClient(base_url=admin_url, timeout=600.0, headers=service_headers())
    created_run: asyncio.Future[str] = asyncio.get_running_loop().create_future()
    context = {
        "owner_id": body.owner_id,
        "bot_session_id": body.bot_session_id,
        "request_id": body.request_id,
        "creator_revision": _revision,
    }

    async def _post(path: str, payload: dict) -> dict:
        response = await client.post(path, json={**context, **payload})
        if response.status_code >= 400:
            raise RuntimeError(f"admin_creator_http_{response.status_code}")
        result = response.json()
        if not isinstance(result, dict) or result.get("ok") is not True:
            raise RuntimeError("admin_creator_request_refused")
        return result

    async def associate(run_id: str) -> bool:
        await _post("/api/skills/creator/associate", {"developer_run_id": run_id})
        from jarvis.runlog.context import get_run_logger
        runlog = get_run_logger()
        if runlog is None or runlog.run_id != run_id:
            raise RuntimeError("developer_run_context_missing")
        runlog.skill_event("skill-creator", _revision, "skill_selected")
        current_task = dispatch_task_ref.get("task")
        if current_task is None:
            raise RuntimeError("developer_dispatch_task_missing")
        with _creator_runs_lock:
            _creator_runs[run_id] = (
                body.owner_id, body.bot_session_id, body.request_id, current_task,
            )
        if not created_run.done():
            created_run.set_result(run_id)
        return True

    async def execute_tool(tool_name: str, arguments: dict) -> dict:
        envelope = await _post("/api/skills/creator/tool", {
            "developer_run_id": created_run.result(),
            "tool_name": tool_name,
            "arguments": arguments,
        })
        result = envelope.get("result")
        if not isinstance(result, dict):
            raise RuntimeError("admin_creator_tool_receipt_invalid")
        return result

    async def execute() -> None:
        try:
            await dispatch_creator(
                body.bot_session_id, body.owner_id,
                task=body.task_brief,
                system_prompt=system_prompt,
                tool_specs=tools,
                tool_executor=execute_tool,
                on_run_created=associate,
                event_filter=_safe_creator_event,
            )
            if not created_run.done():
                created_run.set_exception(RuntimeError("developer_run_not_created"))
        except Exception as exc:
            if not created_run.done():
                created_run.set_exception(exc)
            logger.warning("skill_creator_run_failed error_type=%s", type(exc).__name__[:64])
        finally:
            if created_run.done() and not created_run.cancelled():
                try:
                    with _creator_runs_lock:
                        entry = _creator_runs.get(created_run.result())
                        if entry is not None and entry[3] is asyncio.current_task():
                            _creator_runs.pop(created_run.result(), None)
                except Exception:
                    pass
            await client.aclose()

    task = asyncio.create_task(execute(), name=f"skill-creator:{body.request_id}")
    dispatch_task_ref = {"task": task}
    _creator_tasks.add(task)
    task.add_done_callback(_creator_tasks.discard)
    try:
        run_id = await asyncio.wait_for(asyncio.shield(created_run), timeout=45.0)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=503, detail="Developer run could not be durably started") from None
    except Exception:
        raise HTTPException(status_code=503, detail="Developer run could not be durably associated") from None
    # Keep the internal admin worker attached until this actual Developer
    # run reaches a terminal state; the native client polls its durable
    # request receipt independently and remains non-blocking.
    try:
        await asyncio.shield(task)
    except asyncio.CancelledError:
        raise HTTPException(status_code=409, detail="Developer creator run was cancelled") from None
    return {"ok": True, "developer_run_id": run_id, "request_id": body.request_id}


async def _cancel_creator(body: SkillCreatorCancelIn, request: Request) -> dict:
    _internal_bot_request(request)
    from jarvis.bot.skill_creator_dispatch import active_session

    active = active_session(body.bot_session_id)
    if active is None or active.owner_id != body.owner_id:
        raise HTTPException(status_code=409, detail="creator Developer session is no longer active")
    with _creator_runs_lock:
        entry = _creator_runs.get(body.developer_run_id)
    expected = (body.owner_id, body.bot_session_id, body.request_id)
    if entry is None or entry[:3] != expected:
        raise HTTPException(status_code=404, detail="creator Developer run is unavailable")
    task = entry[3]
    if not task.done():
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    return {"ok": True, "developer_run_id": body.developer_run_id, "cancelled": True}


def install_creator_routes() -> None:
    route_path = "/internal/skills/creator/dispatch"
    if not any(getattr(route, "path", None) == route_path for route in runner_app.routes):
        runner_app.add_api_route(route_path, _dispatch_creator, methods=["POST"], status_code=202)
    cancel_path = "/internal/skills/creator/cancel"
    if not any(getattr(route, "path", None) == cancel_path for route in runner_app.routes):
        runner_app.add_api_route(cancel_path, _cancel_creator, methods=["POST"])


def install_auth() -> None:
    """Install auth once before Pipecat configures its CORS middleware."""
    if not any(middleware.cls is BearerAuthMiddleware for middleware in runner_app.user_middleware):
        runner_app.add_middleware(BearerAuthMiddleware)
    install_creator_routes()


def _strip_host_port(argv: list[str]) -> list[str]:
    filtered: list[str] = []
    skip_value = False
    for arg in argv:
        if skip_value:
            skip_value = False
            continue
        if arg in ("--host", "--port"):
            skip_value = True
            logger.error("bind_arg_ignored arg=%s reason=gated_bind_wins", arg)
            continue
        if arg.startswith("--host=") or arg.startswith("--port="):
            logger.error("bind_arg_ignored arg=%s reason=gated_bind_wins", arg)
            continue
        filtered.append(arg)
    return filtered


def build_argv(host: str, port: int, argv: list[str] | None = None) -> list[str]:
    supplied = sys.argv[1:] if argv is None else argv
    return ["--host", host, "--port", str(port), *_strip_host_port(supplied)]


def main() -> None:
    if auth_enabled() and not service_headers():
        logger.warning("bot_service_token_missing internal_clients_will_fail_auth")
    install_auth()
    try:
        host = resolve_bind_host("bot")
    except BindRefused as exc:
        logger.error("bind_refused process=bot %s", exc)
        print(f"bind refused: {exc}", file=sys.stderr)
        raise SystemExit(2)
    port = resolve_port(BOT_PORT_ENV, DEFAULT_BOT_PORT)
    logger.info("bot_startup host=%s port=%d", host, port)
    sys.argv = [sys.argv[0], *build_argv(host, port)]
    runner_main()
