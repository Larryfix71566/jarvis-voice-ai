"""The full Developer schema set uses the shared validated boundary."""

from dataclasses import replace
from types import SimpleNamespace

import pytest

from jarvis.model_execution import (
    ModelExecutionInputError, ModelExecutionRequest, ModelToolReference, execute_chat,
)
from jarvis.model_routing import AccessRoute, ResolvedModelRoute
from jarvis.privacy_policy import DataPolicy
from jarvis.storage_context import storage_scope


def request(count=40):
    return ModelExecutionRequest("developer", "surface-test", "surface-parent",
        "public synthetic tool registration", data_policy=DataPolicy("approved_external", "synthetic-case"),
        tools=tuple(ModelToolReference(f"fixture_{index}",
            {"type": "object", "properties": {}, "additionalProperties": False}) for index in range(count)))


def route():
    return ResolvedModelRoute(workload="developer", profile_name="fixture", model="fixture",
        provider="fixture", base_url="https://example.invalid", identity="fixture/model",
        route=AccessRoute("direct_api", "direct_api", "provider_api", "FIXTURE_KEY", privacy="approved_external",
                          capabilities=("text", "tools")), api_key_env="FIXTURE_KEY")


@pytest.mark.asyncio
async def test_forty_registered_schemas_reach_the_validated_adapter_unchanged(tmp_path):
    calls = []
    async def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="done", tool_calls=[]))])
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    async with storage_scope(db_path=tmp_path / "db", costs_db_path=tmp_path / "costs",
                             model_preferences_enabled=False):
        result = await execute_chat(request(), route(), client_factory=lambda resolved: client)
    assert result.text == "done"
    assert len(calls) == 1
    assert [item["function"]["name"] for item in calls[0]["tools"]] == [f"fixture_{i}" for i in range(40)]
    assert all(item["function"]["parameters"] == dict(reference.parameters)
               for item, reference in zip(calls[0]["tools"], request().tools))


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["over-cap", "duplicate", "invalid-schema"])
async def test_expanded_surface_still_refuses_invalid_input_before_adapter(tmp_path, kind):
    req = request(41 if kind == "over-cap" else 40)
    if kind == "duplicate":
        req = replace(req, tools=req.tools[:-1] + (req.tools[0],))
    if kind == "invalid-schema":
        req = replace(req, tools=req.tools[:-1] + (ModelToolReference("fixture_39", {"type": "array"}),))
    created = []
    async with storage_scope(db_path=tmp_path / "db", costs_db_path=tmp_path / "costs",
                             model_preferences_enabled=False):
        with pytest.raises(ModelExecutionInputError):
            await execute_chat(req, route(), client_factory=lambda resolved: created.append(resolved))
    assert created == []
