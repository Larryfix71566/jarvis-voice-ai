# Captured sidecar fixtures (APP plan §8 V0)

Captured from the RUNNING sidecar, never hand-authored — a hand-authored
fixture cannot catch a shape drift, which is the whole point of typing
the response structs. With `./scripts/mortimer.sh start` running, from
the repo root:

```bash
F=macos/JarvisKit/Tests/JarvisKitTests/admin-fixtures
curl -s localhost:7861/api/git/status        > $F/git_status.json
curl -s localhost:7861/api/selfedit/models   > $F/selfedit_models.json
curl -s localhost:7861/api/selfedit/status   > $F/selfedit_status.json
curl -s localhost:7861/api/memory            > $F/memory.json
curl -s localhost:7861/api/memory/reviews    > $F/memory_reviews.json
curl -s localhost:7861/api/knowledge         > $F/knowledge.json
curl -s localhost:7861/api/runs              > $F/runs.json
curl -s localhost:7861/api/council/roster    > $F/council_roster.json
curl -s localhost:7861/api/workflows         > $F/workflows.json
curl -s localhost:7861/api/runs/$(curl -s localhost:7861/api/runs | python3 -c 'import sys,json;print(json.load(sys.stdin)["runs"][0]["run_id"])') > $F/run_detail.json
```

Until a fixture exists its decode test SKIPS (with this capture command
in the skip message); after capture, commit the JSON files and the tests
become real. Recapture whenever a sidecar response shape might have
changed (R-A2).

`workflows.json` (MORTIMER_WORKFLOW_VIEWER_PLAN.md piece 4) was captured on
2026-09-25 through the sidecar app itself (`TestClient(jarvis.admin.server.app)
.get("/api/workflows")`) over the repo's `config/workflows`, pretty-printed.
`tests/unit/test_workflows_viewer.py` fails if the endpoint's field set
drifts from it.
