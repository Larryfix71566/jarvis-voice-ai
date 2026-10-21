"""Synthetic-only proof: direct APIs off, explicitly admitted OpenRouter on."""
from dataclasses import replace
from contextvars import copy_context
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import openai
import pytest

from jarvis import llm_client
from jarvis.model_execution import ModelContextMessage, ModelExecutionRequest, execute_chat
from jarvis.model_routing import AccessRoute, ResolvedModelRoute, ModelRouteError
from jarvis.privacy_policy import DataPolicy
from jarvis.provider_access import (
    ProviderAccessError, require_api_access, require_api_request,
    require_route_access, require_voice_readiness, validated_api_request,
)

URL = 'https://openrouter.ai/api/v1'


def route():
    return ResolvedModelRoute('developer', 'synthetic', 'openai/synthetic', 'openrouter',
        URL, AccessRoute('direct_api', 'openai_compatible', 'provider_api',
        'OPENROUTER_API_KEY', 'approved_external', base_url=URL),
        'OPENROUTER_API_KEY', 'synthetic/fixture')


@pytest.fixture(autouse=True)
def selective(monkeypatch, fresh_db):
    monkeypatch.setenv('JARVIS_LLM_ACCESS_MODE', 'direct_apis_disabled')
    monkeypatch.setenv('OPENROUTER_API_KEY', 'synthetic-offline-key')
    monkeypatch.setenv('JARVIS_MODEL_PREFERENCES_ENABLED', '0')


@pytest.mark.parametrize('url', [None, 'https://api.openai.com/v1',
    'https://api.anthropic.com/v1', 'https://unknown.invalid/v1',
    'https://openrouter.ai.evil.invalid/api/v1', 'http://openrouter.ai/api/v1',
    'https://user@openrouter.ai/api/v1', 'https://openrouter.ai:443/api/v1',
    URL+'?redirect=api.openai.com', URL+'#fragment', URL+'/../v1'])
@pytest.mark.parametrize('factory', [llm_client.make_async_client,llm_client.make_sync_client])
def test_direct_and_spoofed_endpoints_refused_before_construction(monkeypatch, url, factory):
    ctor=Mock(side_effect=AssertionError('constructed disallowed SDK'))
    monkeypatch.setattr(openai,'OpenAI',ctor);monkeypatch.setattr(openai,'AsyncOpenAI',ctor)
    with pytest.raises(ProviderAccessError):
        factory(api_key='synthetic',base_url=url,provider='openrouter')
    ctor.assert_not_called()


def test_provider_label_cannot_redirect_to_native_anthropic():
    with pytest.raises(ProviderAccessError):
        require_api_access(provider='anthropic',base_url=URL)


def test_no_fallback_or_voice_private_context_bypass():
    with pytest.raises(ProviderAccessError):
        require_route_access('direct_api',fallback_routes=('subscription',))
    with pytest.raises(ProviderAccessError):
        require_voice_readiness()


def test_exact_request_scope_resets_and_rejects_mutation():
    args={'model':'synthetic','messages':[{'role':'user','content':'public fixture'}]}
    with validated_api_request(route(),DataPolicy('approved_external','synthetic'),args):
        require_api_request(args,provider='openrouter',base_url=URL)
        with pytest.raises(ProviderAccessError):
            require_api_request({**args,'messages':[]},provider='openrouter',base_url=URL)
    with pytest.raises(ProviderAccessError):
        require_api_request(args,provider='openrouter',base_url=URL)


def test_copied_context_cannot_keep_admission_after_exit():
    args={'model':'synthetic','messages':[]}
    with validated_api_request(route(),DataPolicy('approved_external','synthetic'),args):
        copied=copy_context()
    with pytest.raises(ProviderAccessError):
        copied.run(require_api_request,args,provider='openrouter',base_url=URL)


def test_admission_is_single_use_and_resets_on_failure():
    args={'model':'synthetic','messages':[]}
    with pytest.raises(RuntimeError):
        with validated_api_request(route(),DataPolicy('approved_external','synthetic'),args):
            require_api_request(args,provider='openrouter',base_url=URL)
            with pytest.raises(ProviderAccessError):
                require_api_request(args,provider='openrouter',base_url=URL)
            raise RuntimeError('synthetic')
    with pytest.raises(ProviderAccessError):
        require_api_request(args,provider='openrouter',base_url=URL)


@pytest.mark.parametrize('privacy',['confidential','local_only'])
@pytest.mark.asyncio
async def test_protected_source_refused_before_client_creation(privacy):
    ctor=Mock(side_effect=AssertionError('private source reached client'))
    with pytest.raises(ModelRouteError):
        await execute_chat(ModelExecutionRequest('developer','private-task','private-parent',
            'synthetic protected fixture',data_policy=DataPolicy(privacy,'synthetic')),
            route(),client_factory=ctor)
    ctor.assert_not_called()


@pytest.mark.asyncio
async def test_real_sdk_mock_transport_allows_only_validated_public_openrouter(monkeypatch):
    seen=[]
    async def respond(request):
        seen.append(request.url.host)
        return httpx.Response(200,json={'id':'synthetic','object':'chat.completion',
            'created':0,'model':'openai/synthetic','choices':[{'index':0,
            'message':{'role':'assistant','content':'synthetic result'},'finish_reason':'stop'}]})
    original=openai.AsyncOpenAI
    def make(**kwargs):
        return original(**kwargs,http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)))
    monkeypatch.setattr(openai,'AsyncOpenAI',make)
    client=llm_client.make_async_client(api_key='synthetic',base_url=URL,provider='openrouter')
    req=ModelExecutionRequest('developer','public-task','public-parent','public fixture',
        data_policy=DataPolicy('approved_external','synthetic'))
    try:
        result=await execute_chat(req,route(),client_factory=lambda _:client)
        assert result.text=='synthetic result'
        assert result.billing=='provider_api'
        assert seen==['openrouter.ai']
        with pytest.raises(ProviderAccessError):
            await client.chat.completions.create(model='synthetic',messages=[])
        client._client.base_url='https://api.openai.com/v1'
        with pytest.raises(ProviderAccessError):
            await execute_chat(req,route(),client_factory=lambda _:client)
        assert seen==['openrouter.ai']
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_retained_direct_route_refused_even_with_injected_client():
    r=replace(route(),provider='anthropic',base_url='https://api.anthropic.com/v1')
    ctor=Mock(side_effect=AssertionError('direct factory reached'))
    with pytest.raises(ProviderAccessError):
        await execute_chat(ModelExecutionRequest('developer','t','p','synthetic'),r,client_factory=ctor)
    ctor.assert_not_called()


def test_retained_direct_client_is_blocked_after_policy_change(monkeypatch):
    call=Mock(return_value=SimpleNamespace());call._mortimer_measured=False
    client=SimpleNamespace(base_url='https://api.openai.com/v1',
        chat=SimpleNamespace(completions=SimpleNamespace(create=call)))
    monkeypatch.setenv('JARVIS_LLM_ACCESS_MODE','legacy')
    llm_client._instrument_completion(client,'openai',asynchronous=False)
    monkeypatch.setenv('JARVIS_LLM_ACCESS_MODE','direct_apis_disabled')
    with pytest.raises(ProviderAccessError):
        client.chat.completions.create(model='synthetic',messages=[])
    call.assert_not_called()


@pytest.mark.asyncio
async def test_local_history_cannot_fallback_from_public_current_turn():
    ctor=Mock(side_effect=AssertionError('history reached provider'))
    req=ModelExecutionRequest('developer','history-task','history-parent','public fixture',
        data_policy=DataPolicy('approved_external','synthetic'),
        context=(ModelContextMessage(role='user',content='synthetic local history',
            data_policy=DataPolicy('local_only','synthetic')),))
    with pytest.raises(ModelRouteError):
        await execute_chat(req,route(),client_factory=ctor)
    ctor.assert_not_called()


def test_policy_from_settings_cannot_be_relaxed_by_legacy_environment(monkeypatch):
    monkeypatch.setenv('JARVIS_LLM_ACCESS_MODE','legacy')
    with pytest.raises(ProviderAccessError):
        require_api_access('direct_apis_disabled',provider='openai',
                           base_url='https://api.openai.com/v1')
    require_api_access('direct_apis_disabled',provider='openrouter',base_url=URL)


def test_subscription_only_still_prohibits_openrouter(monkeypatch):
    monkeypatch.setenv('JARVIS_LLM_ACCESS_MODE','subscription_only')
    with pytest.raises(ProviderAccessError):
        require_api_access(provider='openrouter',base_url=URL)


def test_selective_diagnostics_cannot_make_paid_probe(monkeypatch):
    from scripts import check_env
    probe=Mock(side_effect=AssertionError('provider contacted'))
    monkeypatch.setattr(check_env.urllib.request,'urlopen',probe)
    assert check_env.model_key_probe(URL,'synthetic','synthetic')[0]=='blocked'
    probe.assert_not_called()
