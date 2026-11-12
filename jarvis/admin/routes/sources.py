"""Admin sidecar routes: workspace and advisory source bridges (/api/development/source/*, /api/advisory/source/*).

Moved verbatim from jarvis/admin/server.py (B6). Helpers, state and imported
modules are reached as `srv.<name>` at call time, never imported here, so a
test that monkeypatches jarvis.admin.server is seen by these handlers.
Only jarvis.admin.server imports this module.
"""

from __future__ import annotations

from fastapi import Request

from jarvis.admin import server as srv
from jarvis.admin.server import (  # request bodies named in signatures
    AdvisorySourceIn,
    WorkspaceSourceAssociationIn,
    WorkspaceSourcePrepareIn,
    WorkspaceSourceToolIn,
)

# Routes register on the server's one FastAPI app (see the B6 note there).
app = srv.app


@app.post('/api/development/source/associate')
def associate_workspace_source(body: WorkspaceSourceAssociationIn, request: Request) -> dict:
    srv._workspace_source_run(body, request)
    from jarvis.development_attestation import ensure_admin_source_authority
    ensure_admin_source_authority()
    srv._workspace_source_run(body, request)
    return {'ok': True}


@app.post('/api/development/source/prepare')
def prepare_workspace_source(body: WorkspaceSourcePrepareIn, request: Request) -> dict:
    run = srv._workspace_source_run(body, request)
    _, values = srv._workspace_source_arguments(body)
    try:
        from jarvis.development_sources import retain_workspace_floor
        from jarvis.privacy_policy import DataPolicy
        retain_workspace_floor(run, DataPolicy(body.source_input_policy, 'workspace-caller-floor'))
        context = srv._workspace_source_context(body, run, values, terminal=body.tool_name.endswith(('status', 'finish', 'submit')))
        cleanup = srv._workspace_source_cleanup(body, run, values)
        srv._workspace_source_run(body, request)
        import secrets
        key = secrets.token_hex(32)
        with srv._workspace_preparation_lock:
            now = srv.time.monotonic()
            for prior, record in list(srv._workspace_preparations.items()):
                if now - record[0] >= 60:
                    srv._workspace_preparations.pop(prior, None)
            if len(srv._workspace_preparations) >= 4096:
                raise ValueError()
            srv._workspace_preparations[key] = (now, body.model_dump(), context, cleanup)
        return {'ok': True, 'source_context': context.as_metadata(), 'source_preparation_id': key}
    except Exception:
        raise srv.HTTPException(status_code=409, detail='workspace source context is unavailable') from None


@app.post('/api/development/source/tool')
def execute_workspace_source(body: WorkspaceSourceToolIn, request: Request) -> dict:
    from jarvis.development_attestation import sign_workspace_source
    from jarvis.development_sources import ordinary_context, _verify_workspace_floor_pins, published_workspace_result
    from jarvis.privacy_policy import DataPolicy, issue_tool_result, make_tool_execution_scope, strictest, validate_tool_result
    from jarvis.tenant import user_id_scope

    run = srv._workspace_source_run(body, request)
    function, values = srv._workspace_source_arguments(body)
    terminal = body.tool_name.endswith(('status', 'finish', 'submit'))
    try:
        with srv._workspace_preparation_lock:
            prepared = srv._workspace_preparations.pop(body.source_preparation_id, None)
        binding = body.model_dump(exclude={'source_context', 'source_preparation_id'})
        if prepared is None or not 0 <= srv.time.monotonic() - prepared[0] < 60 or binding != prepared[1]:
            raise ValueError()
        context = prepared[2]
        _verify_workspace_floor_pins(context)
        current_context = srv._workspace_source_context(body, run, values, terminal=terminal)
        cleanup = srv._workspace_source_cleanup(body, run, values)
        if not srv._same_cleanup(prepared[3], cleanup):
            raise ValueError()
        if (context.as_metadata() != body.source_context or current_context.as_metadata() != body.source_context
                or current_context._identity != context._identity or current_context._pins != context._pins):
            raise ValueError()
        # A host acquisition can strengthen a run after preparation. The
        # current verified floor must precede admission of any guest bytes.
        context = current_context
        scope = make_tool_execution_scope(body.developer_run_id, body.source_task_id, body.source_tool_call_id,
            body.tool_name, body.arguments, strictest(context.input_floor,
                cleanup.input_floor if cleanup is not None else context.input_floor,
                DataPolicy(body.source_input_policy, 'workspace-caller-floor')))
        from jarvis.development_sources import retain_workspace_floor
        retain_workspace_floor(run, scope.input_policy)
        retained_id = context.as_metadata().get('sandbox_job_id')
        if retained_id and retained_id != run['run_id']:
            from jarvis.runlog.store import get_run
            retained = get_run(retained_id)['run']
            if retained['user_id'] != run['user_id'] or retained['session_id'] != run['session_id']:
                raise ValueError()
            retain_workspace_floor(retained, scope.input_policy)
        if cleanup is not None:
            from jarvis.runlog.store import get_run
            retain_workspace_floor(get_run(cleanup.as_metadata()['sandbox_job_id'])['run'], scope.input_policy)
            cleanup = srv._workspace_source_cleanup(body, run, values)
        # Only the just-issued restriction update may add a missing floor
        # record. Re-pin that actual host journal before the installed tool.
        admitted = srv._workspace_source_context(body, run, values, terminal=terminal)
        if (admitted.as_metadata() != context.as_metadata() or admitted._identity != context._identity
                or admitted._pins != context._pins):
            raise ValueError()
        context = admitted
        client = srv._WorkspaceSourceClient(scope, context, run, cleanup)
        with user_id_scope(run['user_id']):
            result = function(client, **values)
        from jarvis.development_sources import refresh_workspace_floor
        latest_floor = refresh_workspace_floor(context)
        policy, source_scope, refs = strictest(context.input_floor, latest_floor), 'workspace-generated-lifecycle', ()
        if client.classified is not None:
            policy = strictest(policy, client.policy)
            source_scope, refs = client.classified.source_scope, client.classified.canonical_refs
        else:
            result = srv._workspace_lifecycle_result(body.tool_name, values, result)
        policy = strictest(policy, *(value for value in client.start_policy.values() if type(value) is DataPolicy))
        current_run = srv._workspace_source_run(body, request)
        if body.tool_name == 'selfedit_start':
            if values['confirm'] and result.get('ok'):
                expected_job = context.as_metadata().get('sandbox_job_id', body.developer_run_id)
                with srv._opening_lock, srv._run_lock:
                    if not any(slot.get('run_id') == expected_job for slot in (srv._opening_job, srv._run_job)):
                        raise ValueError()
            after = ordinary_context(None, current_run, workspace_kind='selfedit',
                                     lineage_id=context.as_metadata()['lineage_id'])
        else:
            after = srv._workspace_source_context(body, current_run, values, terminal=terminal)
            if after.as_metadata() != context.as_metadata():
                raise ValueError()
        policy = strictest(policy, after.input_floor)
        if (result.get('ok') is True and context._session is not None
                and body.tool_name in {'selfedit_status', 'selfedit_finish', 'app_build_status', 'app_build_submit'}):
            metadata = context.as_metadata()
            identities = {'selfedit_status': ('action_run_id', 'sandbox_session_id'),
                          'app_build_status': ('submission_id', 'sandbox_session_id')}
            selected = identities.get(body.tool_name)
            same = selected is None or not values.get(selected[0]) or values[selected[0]] == metadata.get(selected[1])
            if body.tool_name == 'app_build_status' and values.get('action_run_id'):
                same = same and values['action_run_id'] == metadata.get('sandbox_job_id')
            if same:
                published = published_workspace_result(context._service, execution_scope=scope, context=context)
                if published is not None:
                    pub_policy, pub_content = validate_tool_result(scope, published)
                    handle = srv.json.loads(pub_content)
                    result.update(pr_url=handle['pr_url'], pr_number=handle['pr_number'], commit=handle['commit'])
                    result['summary'] = ('Draft pull request: ' + handle['pr_url'] + '. '
                        'Review it on GitHub; approval and merging remain with you.')
                    if handle.get('human_only') is True:
                        result['human_only'] = True
                        result['summary'] = ('Human-only proposal: ' + handle['pr_url'] + '. '
                            'Ask Larry to approve and apply it himself; do not merge this proposal as it is.')
                    policy = strictest(policy, pub_policy)
                    refs += published.canonical_refs
        classified = issue_tool_result(scope, srv.json.dumps(result, sort_keys=True, separators=(',', ':'),
            ensure_ascii=True, allow_nan=False), policy, source_scope, refs)
        receipt = sign_workspace_source(scope, classified, context=context.as_metadata(), challenge=body.source_challenge)
        srv._workspace_source_run(body, request)
        if client.classified is not None:
            final = srv._workspace_source_context(body, current_run, values, terminal=terminal)
            if final.as_metadata() != context.as_metadata():
                raise ValueError()
        return {'ok': True, 'source_receipt': receipt}
    except srv.HTTPException:
        raise
    except Exception:
        raise srv.HTTPException(status_code=409, detail='workspace source binding changed') from None


@app.post('/api/advisory/source/associate')
def associate_advisory_source(body: AdvisorySourceIn, request: Request) -> dict:
    srv._advisory_source_run(body, request)
    from jarvis.development_attestation import ensure_admin_source_authority
    ensure_admin_source_authority()
    srv._advisory_source_run(body, request)
    return {'ok': True}


@app.post('/api/advisory/source/prepare')
def prepare_advisory_source(body: AdvisorySourceIn, request: Request) -> dict:
    from jarvis import advisory_sources as sources
    from jarvis.development_attestation import sign_advisory_source
    from jarvis.tenant import user_id_scope
    run = srv._advisory_source_run(body, request)
    try:
        _, values = srv._advisory_source_arguments(body)
        scope = srv._advisory_scope(body)
        with user_id_scope(run['user_id']):
            if body.tool_name in {'plan_start', 'research_compare_start'}:
                context = sources.prepare_advisory_source(scope, run,
                    owner_scope_id=body.owner_scope_id, child_scope_id=body.child_scope_id)
                if body.tool_name == 'plan_start' and values['review_path'].strip():
                    path = values['review_path'].strip()
                    acquired = srv.repo_logic.repo_read_file(path)
                    context = sources.acquire_review_source(context, srv._selfedit_service, path, acquired,
                        max_chars=srv.council_config.PLAN_REVIEW_DOC_MAX_CHARS)
            else:
                if body.owner_scope_id is not None or body.child_scope_id is not None:
                    raise ValueError()
                _, slot = srv._advisory_slot(sources.kind_for_tool(body.tool_name))
                context = sources.retained_advisory_source(scope, run, slot)
                requested = values.get('action_run_id') if body.tool_name == 'plan_status' else values.get('run_id')
                if requested and requested != context.as_metadata()['action_run_id']:
                    raise ValueError()
        key = srv.uuid.uuid4().hex + srv.uuid.uuid4().hex
        value = {'ok': True, 'preparation_id': key, 'source_context': context.as_metadata()}
        envelope = sources.issue_advisory_result(scope, context, value, pending=True)
        receipt = sign_advisory_source(scope, envelope, context=context.as_metadata(),
            challenge=body.challenge, phase='prepare')
        srv._advisory_source_run(body, request)
        with srv._advisory_preparation_lock:
            now = srv.time.monotonic()
            for old, entry in list(srv._advisory_preparations.items()):
                if now - entry['created_at'] > 600:
                    srv._advisory_preparations.pop(old, None)
            if len(srv._advisory_preparations) >= 4096:
                raise ValueError()
            srv._advisory_preparations[key] = {'created_at': now, 'binding': srv._advisory_binding(body),
                                         'context': context, 'used': False}
        return {**value, 'source_receipt': receipt}
    except srv.HTTPException:
        raise
    except Exception:
        raise srv.HTTPException(status_code=409, detail='advisory source binding changed') from None


@app.post('/api/advisory/source/tool')
def execute_advisory_source(body: AdvisorySourceIn, request: Request) -> dict:
    from jarvis import advisory_sources as sources
    from jarvis.development_attestation import sign_advisory_source
    from jarvis.tenant import user_id_scope
    run = srv._advisory_source_run(body, request)
    try:
        context = srv._prepared_advisory(body, consume=True)
        function, values = srv._advisory_source_arguments(body)
        scope = srv._advisory_scope(body)
        with user_id_scope(run['user_id']):
            context = sources.refresh_advisory_source(context, run)
            if context.cancel_event.is_set():
                raise ValueError()
            if body.tool_name == 'plan_start' and values['review_path'].strip():
                sources.prepared_review_source(context, srv._selfedit_service, values['review_path'].strip())
            if body.tool_name == 'research_status':
                values['run_id'] = context.as_metadata()['action_run_id']
            token = srv._advisory_transport_context.set(context)
            try:
                value = function(srv._AdvisorySourceClient(context), **values)
            finally:
                srv._advisory_transport_context.reset(token)
            if type(value) is not dict or value.get('ok') is not True:
                value = {'ok': False, 'error': 'advisory_operation_failed'}
            pending = body.tool_name in {'plan_start', 'research_compare_start'}
            envelope = sources.issue_advisory_result(scope, context, value, pending=pending)
        srv._advisory_source_run(body, request)
        return {'ok': True, 'source_receipt': sign_advisory_source(scope, envelope,
            context=context.as_metadata(), challenge=body.challenge, phase='execute')}
    except srv.HTTPException:
        raise
    except Exception:
        raise srv.HTTPException(status_code=409, detail='advisory source binding changed') from None


@app.post('/api/advisory/source/cancel')
def cancel_advisory_source(body: AdvisorySourceIn, request: Request) -> dict:
    from jarvis import advisory_sources as sources
    from jarvis.development_attestation import sign_advisory_source
    from jarvis.tenant import user_id_scope
    run = srv._advisory_source_run(body, request, terminal=True)
    try:
        if body.tool_name not in {'plan_start', 'research_compare_start'}:
            raise ValueError()
        context = srv._prepared_advisory(body, consume=False)
        sources.cancel_advisory_source(context)
        kind = sources.kind_for_tool(body.tool_name)
        lock, slot = srv._advisory_slot(kind)
        with user_id_scope(run['user_id']):
            with lock:
                owns_slot = (context._action.slot is slot and sources._active.get(kind) is context._action
                    and slot.get('run_id') == context.as_metadata()['action_run_id'])
            if owns_slot:
                token = srv._advisory_transport_context.set(context)
                try:
                    srv.plan_cancel() if kind == 'planning' else srv.research_cancel()
                finally:
                    srv._advisory_transport_context.reset(token)
            scope = srv._advisory_scope(body)
            envelope = sources.issue_advisory_result(scope, context, {'ok': True, 'cancelled': True,
                'action_run_id': context.as_metadata()['action_run_id']}, pending=True)
        srv._advisory_source_run(body, request, terminal=True)
        return {'ok': True, 'source_receipt': sign_advisory_source(scope, envelope,
            context=context.as_metadata(), challenge=body.challenge, phase='cancel')}
    except srv.HTTPException:
        raise
    except Exception:
        raise srv.HTTPException(status_code=409, detail='advisory source binding changed') from None
