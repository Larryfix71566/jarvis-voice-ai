from types import SimpleNamespace

import pytest

from jarvis.model_execution import ModelExecutionRequest, execute_chat
from jarvis.model_routing import AccessRoute, ResolvedModelRoute
from jarvis.privacy_policy import DataPolicy


class FakeCompletions:
    async def create(self, **kwargs):
        return SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content="ok"))])


class FakeClient:
    chat = SimpleNamespace(completions=FakeCompletions())


@pytest.mark.asyncio
async def test_execution_preserves_parent_request_and_route_metadata():
    route = ResolvedModelRoute(
        workload="developer", profile_name="test", model="m", provider="test",
        base_url="https://example.invalid", identity="test/m",
        route=AccessRoute("saygm", "saygm_gateway", "saygm_credit", "SAYGM_API_KEY", "confidential"),
        api_key_env="SAYGM_API_KEY",
    )
    result = await execute_chat(
        ModelExecutionRequest("developer", "task-1", "parent-1", "hello"),
        route,
        client_factory=lambda _: FakeClient(),
    )
    assert result.text == "ok"
    assert result.parent_request_id == "parent-1"
    assert result.billing == "saygm_credit"
    assert result.data_policy.level == "confidential"
