"""Full-file transport parity through real policy/execution/sandbox seams.

Providers and guest RPC are inert; editor permissions/caps are unchanged.
"""
import asyncio
from dataclasses import replace
import json
from types import SimpleNamespace

import pytest

from jarvis import model_execution as E, subscription_tools as T
from jarvis.privacy_policy import (DataPolicy, issue_tool_result, make_tool_execution_scope,
                                  tool_argument_limit, tool_result_limit, validate_tool_result)
from tests.unit.test_development_sources import workspace
from tests.unit.test_development_sources import dispatch
from tests.unit.test_model_execution import FakeClient, FakeStreamingClient, resolved_route


def reference(name='edit_propose'):
    return E.ModelToolReference(name, {'type': 'object', 'properties': {
        'path': {'type': 'string'}, 'new_content': {'type': 'string'},
        'rationale': {'type': 'string'}}, 'required': ['path', 'new_content', 'rationale'],
        'additionalProperties': False})


def arguments(content):
    return {'path': 'jarvis/app.py', 'new_content': content, 'rationale': 'public fixture'}


def request(content='', *, stream=False, tools=None):
    return E.ModelExecutionRequest('developer', 'large-task', 'large-parent', 'public fixture',
        data_policy=DataPolicy('approved_external', 'public-fixture'),
        tools=(reference(),) if tools is None else tools, stream_text=stream)


def tool_response(args, name='edit_propose'):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='', tool_calls=[
        SimpleNamespace(id='large-call', function=SimpleNamespace(name=name, arguments=json.dumps(args)))
    ]))])


@pytest.mark.parametrize('content', ['x' * 200000, '\x00' * 200000, '中' * 66666, '😀' * 50000],
                         ids=['ascii','controls','cjk','emoji'])
async def test_valid_self_edit_file_crosses_output_scope_source_and_next_history(workspace, content):
    args = arguments(content)
    output = await E.execute_chat(request(), resolved_route(capabilities=('text','tools')),
        client_factory=lambda _: FakeClient(response=tool_response(args)), admission=E.ModelAdmissionController())
    assert output.tool_calls[0].arguments == args
    policy, result, envelope = dispatch(workspace, 'edit_propose', args)
    assert policy.level == 'approved_external' and result['ok']
    assert content.encode() == workspace.guest['jarvis/app.py']
    scope = make_tool_execution_scope('large-parent', 'large-task', 'large-call', 'edit_propose',
                                     args, DataPolicy('approved_external', 'public-fixture'))
    sealed = issue_tool_result(scope, envelope.content, policy, 'public-fixture')
    assert validate_tool_result(scope, sealed)[1] == envelope.content
    history = (E.ModelContextMessage('assistant', '', DataPolicy('approved_external','public-fixture'),
               tool_calls=output.tool_calls),
               E.ModelContextMessage('tool', envelope.content, policy, name='edit_propose', tool_call_id='large-call'))
    continuation = FakeClient()
    await E.execute_chat(replace(request(), task_id='large-task:1', context=history),
        resolved_route(capabilities=('text','tools')), client_factory=lambda _: continuation,
        admission=E.ModelAdmissionController())
    assert json.loads(continuation.completions.kwargs['messages'][0]['tool_calls'][0]['function']['arguments']) == args
    assert json.loads(continuation.completions.kwargs['messages'][1]['content']) == result


def test_transport_does_not_raise_the_actual_self_edit_cap(workspace):
    content = 'x' * 200001
    policy, result, _ = dispatch(workspace, 'edit_propose', arguments(content))
    assert not result['ok'] and policy.level == 'approved_external'
    assert workspace.calls == [] and workspace.guest['jarvis/app.py'] != content.encode()


def test_argument_transport_covers_full_app_editor_and_unicode_rationale(workspace):
    from jarvis.agents.workspace import AppWorkspace
    from jarvis.development_sources import dispatch_workspace_tool
    from sandbox.durable import atomic_json
    from sandbox.session import MAX_EDITOR_BYTES
    args=arguments('\x00'*MAX_EDITOR_BYTES); args['rationale']='😀'*8000
    raw=json.dumps(args,separators=(',',':'))
    assert len(raw.encode())>6*MAX_EDITOR_BYTES+16384
    state={**workspace.state,'kind':'app-build'}
    atomic_json(workspace.directory/'session.json',state)
    record=workspace.runtime.workspaces/(workspace.runtime._key(state['repository'],'app-build')+'.json')
    atomic_json(record,{'session':state['id'],'repository':state['repository'],'kind':'app-build','profile':'mortimer'})
    app=AppWorkspace('jarvis-voice-ai',github_client=SimpleNamespace(token='unused',_owner=lambda:'Larryfix71566'),
                     runtime_factory=lambda:workspace.runtime,sandbox_profile='mortimer')
    scope=make_tool_execution_scope(workspace.parent,'task','call','edit_propose',args,
                                   DataPolicy('approved_external','public-fixture'))
    assert scope.tool_name=='edit_propose' and len(raw.encode())<=tool_argument_limit('edit_propose')
    envelope=dispatch_workspace_tool(app,'edit_propose',args,execution_scope=scope)
    policy,result=validate_tool_result(scope,envelope)
    assert policy.level=='approved_external' and json.loads(result)['ok']
    assert workspace.guest['jarvis/app.py']==args['new_content'].encode()


async def test_history_arguments_apply_same_registered_schema_before_any_client():
    args=arguments('x'*20000); args['unadvertised']=True
    call=E.ModelToolCall('large-call','edit_propose',args,json.dumps(args))
    history=(E.ModelContextMessage('assistant','',tool_calls=(call,)),
             E.ModelContextMessage('tool','{}',name='edit_propose',tool_call_id='large-call'))
    with pytest.raises(E.ModelExecutionInputError,match='registered schema'):
        await E.execute_chat(replace(request(),context=history),resolved_route(capabilities=('text','tools')),
            client_factory=lambda _:pytest.fail('bad history reached a client'),admission=E.ModelAdmissionController())


@pytest.mark.parametrize('name', ['kb_search','repo_read_file','session_validate'])
def test_unrelated_source_scope_quotas_stay_small(name):
    assert tool_argument_limit(name) == 16384 and tool_result_limit(name) == 1000000
    with pytest.raises(ValueError, match='invalid_tool_execution_scope'):
        make_tool_execution_scope('parent','task','call',name, {'query': 'x' * 20000}, DataPolicy())


async def test_large_name_is_still_required_in_the_registered_allowlist():
    with pytest.raises(E.ModelExecutionOutputError, match='outside the allowlist'):
        await E.execute_chat(request(tools=(reference('other'),)),
            resolved_route(capabilities=('text','tools')),
            client_factory=lambda _: FakeClient(response=tool_response(arguments('x'*20000))),
            admission=E.ModelAdmissionController())


async def test_large_arguments_still_require_the_exact_schema():
    args = arguments('x' * 20000); args['unadvertised'] = True
    with pytest.raises(E.ModelExecutionOutputError, match='registered schema'):
        await E.execute_chat(request(), resolved_route(capabilities=('text','tools')),
            client_factory=lambda _: FakeClient(response=tool_response(args)), admission=E.ModelAdmissionController())


def chunk(*, name=None, args=None, call_id=None, finish=None):
    calls = [] if finish else [SimpleNamespace(index=0, id=call_id,
        function=SimpleNamespace(name=name, arguments=args), model_extra={})]
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=None, tool_calls=calls),
                                                   finish_reason=finish)])


async def test_streamed_large_edit_waits_for_exact_name_and_complete_arguments():
    args=arguments('中' * 66666); raw=json.dumps(args)
    client=FakeStreamingClient([chunk(args=raw[:200000], call_id='large-call'),
        chunk(name='edit_'), chunk(name='propose',args=raw[200000:]), chunk(finish='tool_calls')])
    events=[]
    result=await E.execute_chat(request(stream=True),
        resolved_route(capabilities=('text','tools','streaming')), client_factory=lambda _: client,
        admission=E.ModelAdmissionController(), event_sink=events.append,
        event_sink_policy=DataPolicy('local_only','test-sink'))
    assert result.tool_calls[0].arguments == args
    assert [e.event_type for e in events if e.event_type == 'tool_request'] == ['tool_request']
    assert client.stream.closed


async def test_streamed_name_change_to_small_tool_refuses_before_any_tool_event():
    client=FakeStreamingClient([chunk(args=json.dumps(arguments('x'*20000)),call_id='large-call'),
        chunk(name='other'),chunk(finish='tool_calls')])
    events=[]
    with pytest.raises(E.ModelExecutionOutputError,match='oversized'):
        await E.execute_chat(request(stream=True,tools=(reference(),reference('other'))),
            resolved_route(capabilities=('text','tools','streaming')),client_factory=lambda _:client,
            admission=E.ModelAdmissionController(),event_sink=events.append,
            event_sink_policy=DataPolicy('local_only','test-sink'))
    assert not any(e.event_type == 'tool_request' for e in events) and client.stream.closed


def test_large_result_frame_is_specific_to_the_bound_editor_tool():
    content=json.dumps({'content':'\x00'*200000})
    assert len(content)>1000000
    assert json.loads(T._result_frame(content,'file_read')) == {'ok':True,'content':content}
    with pytest.raises(T.SubscriptionCapabilityError):
        T._result_frame(content,'fixture')


async def test_actual_gateway_preserves_valid_large_edit_request_and_diff(workspace):
    args=arguments('\x00'*200000)
    _,result,envelope=dispatch(workspace,'edit_propose',args)
    req=request(); route=SimpleNamespace(model='fixture')
    session=T._ClaudeNativeSession(req,route,{'messages':[{'role':'user','content':'fixture'}]},'inert')
    writer=None
    try:
        session.server=await asyncio.start_unix_server(session._gateway,path=str(session.socket_path),
                                                       limit=T._request_frame_limit(session.names))
        pending=T._Pending('large-call','edit_propose',args,asyncio.get_running_loop().create_future(),'large-task')
        session.pending['large-call']=pending; pending.result.set_result(envelope.content)
        reader,writer=await asyncio.open_unix_connection(str(session.socket_path),
                                                        limit=6*tool_result_limit('edit_propose')+128)
        packet={'nonce':session.nonce,'parent_id':session.parent_id,'task_id':session.origin_task_id,
                'request_id':'gateway-large','name':'edit_propose','arguments':args}
        frame=T._encode_frame(packet,T._request_frame_limit(session.names))
        assert len(frame)>262144
        writer.write(frame); await writer.drain()
        response=json.loads(await asyncio.wait_for(reader.readline(),3))
        assert response=={'ok':True,'content':envelope.content}
        assert pending.delivery is not None and await pending.delivery is True
    finally:
        if writer is not None:
            await T._close_writer(writer)
        await session.close()
