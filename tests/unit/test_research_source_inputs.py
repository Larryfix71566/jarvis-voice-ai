"""Host policy is checked before real inert crawler HTTP, not only models."""
import json
import httpx
import pytest
from jarvis.admin import server as admin
from jarvis.research import crawl
from tests.unit.test_advisory_source_bridge import advisory, immediate_workers
from tests.unit.test_council_budget_ownership import transport_env

@pytest.mark.parametrize('level', ['local_only', 'confidential'])
def test_protected_focus_refuses_before_actual_tavily_transport(advisory, immediate_workers, monkeypatch, level):
    monkeypatch.setenv('TAVILY_API_KEY', 'synthetic-unused-crawl-key')
    real_client = httpx.Client
    created, sent = [], []
    def handler(request):
        sent.append(json.loads(request.content))
        return httpx.Response(400, json={'detail': {'error': 'synthetic fixture refusal'}})
    def factory(**kwargs):
        created.append(True)
        return real_client(transport=httpx.MockTransport(handler), timeout=kwargs['timeout'], trust_env=False)
    monkeypatch.setattr(crawl.httpx, 'Client', factory)
    logger = advisory.caller('analyst')
    scope, body = advisory.body_for(logger, 'research_compare_start', args={'urls': ['https://a.invalid', 'https://b.invalid'], 'focus': 'PRIVATE_CRAWL_FOCUS_428a', 'confirm': True}, level=level)
    pin, prepared, _ = advisory.prepare(scope, body)
    policy, result, _ = advisory.execute(scope, body, pin, prepared)
    assert result['started'] and policy.level == level
    assert created == [] and sent == [], 'protected input crossed actual Tavily client boundary before model privacy check'
    assert admin._research_job['state'] == 'error' and admin._research_job['error'] == 'model_policy_refused'
    assert advisory.state.clients == [] and advisory.state.sent == []


def test_public_packet_reaches_both_sites_before_unknown_pages_protect_model_sink(
    advisory, immediate_workers, monkeypatch,
):
    monkeypatch.setenv('TAVILY_API_KEY', 'synthetic-unused-crawl-key')
    real_client = httpx.Client
    sent, clients = [], []
    def handler(request):
        packet = json.loads(request.content)
        sent.append(packet)
        return httpx.Response(200, json={'results': [{'url': packet['url'],
            'raw_content': 'UNKNOWN_ACQUIRED_PAGE_43bb'}], 'usage': {'credits': 1}})
    def factory(**kwargs):
        client = real_client(transport=httpx.MockTransport(handler), timeout=kwargs['timeout'], trust_env=False)
        clients.append(client)
        return client
    monkeypatch.setattr(crawl.httpx, 'Client', factory)
    try:
        logger = advisory.caller('analyst')
        urls = ['https://a.invalid', 'https://b.invalid']
        scope, body = advisory.body_for(logger, 'research_compare_start',
            args={'urls': urls, 'focus': 'public comparison', 'confirm': True})
        pin, prepared, _ = advisory.prepare(scope, body)
        policy, result, _ = advisory.execute(scope, body, pin, prepared)
        assert result['started'] and [packet['url'] for packet in sent] == urls
        assert all(packet['instructions'] == 'public comparison' for packet in sent)
        assert all('UNKNOWN_ACQUIRED_PAGE' not in json.dumps(packet) for packet in sent)
        assert policy.level == 'confidential'
        assert admin._research_job['error'] == 'model_policy_refused'
        assert advisory.state.clients == [] and advisory.state.sent == []
    finally:
        for client in clients:
            client.close()


def test_later_caller_restriction_stops_second_crawl_before_http(
    advisory, immediate_workers, monkeypatch,
):
    from jarvis.development_sources import retain_workspace_floor
    from jarvis.privacy_policy import DataPolicy
    from jarvis.runlog.store import get_run
    monkeypatch.setenv('TAVILY_API_KEY', 'synthetic-unused-crawl-key')
    real_client = httpx.Client
    sent, clients = [], []
    logger = advisory.caller('analyst')
    def handler(request):
        packet = json.loads(request.content)
        sent.append(packet)
        retain_workspace_floor(get_run(logger.run_id)['run'], DataPolicy('local_only', 'new-host-restriction'))
        return httpx.Response(200, json={'results': [{'url': packet['url'], 'raw_content': 'unknown page'}]})
    def factory(**kwargs):
        client = real_client(transport=httpx.MockTransport(handler), timeout=kwargs['timeout'], trust_env=False)
        clients.append(client)
        return client
    monkeypatch.setattr(crawl.httpx, 'Client', factory)
    try:
        scope, body = advisory.body_for(logger, 'research_compare_start',
            args={'urls': ['https://a.invalid', 'https://b.invalid'], 'focus': 'public comparison', 'confirm': True})
        pin, prepared, _ = advisory.prepare(scope, body)
        policy, result, _ = advisory.execute(scope, body, pin, prepared)
        assert result['started'] and policy.level == 'local_only'
        assert len(sent) == 1 and sent[0]['url'] == 'https://a.invalid'
        assert admin._research_job['error'] == 'model_policy_refused'
        assert advisory.state.clients == [] and advisory.state.sent == []
    finally:
        for client in clients:
            client.close()
