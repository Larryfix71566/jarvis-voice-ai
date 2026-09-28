# GC24-02 — mutating caller identity audit (app tools)

**Snapshot:** dirty isolated worktree `codex/isolated-20260924`, base/HEAD `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`; read-only source audit. No tool behavior was changed by this receipt.

## Reviewed caller families

| Tool/action | Existing identity and guard | Audit result |
|---|---|---|
| `app_build_start` | Registry-injected hidden `run_id`; existing SQLite action claim under `mcp-apps.app_build_start`. | Covered for retries within the owning run; does not prove unrelated app-build action families. |
| `app_build_submit` | Persisted app-build sandbox session `id`; now claimed in `mcp-apps.app_build_submit`. | Focused replay/unknown-outcome receipt: [app-build submit claim](GC24-02-appbuild-submit-session-claim-2026-09-25.md). |
| `app_create` | `confirm=false` returns a summary, then `confirm=true` accepts name/template/description again. No issued stable preview/action ID reaches the execution call or a durable claim. | Open. A repeated or changed confirm can cause external repository creation/scaffolding without a durable action identity. The preview-confirm contract needs an explicit issued ID before implementation; goal text or argument hashes are not substitutes. |
| `app_register` | Publicly exposed tool writes the app registry on the configured registry branch; no confirmation ID or durable action claim. Also called internally by `app_create`. | Open. Repeated calls may create repeated registry commits, and it is directly callable. Define whether the direct tool remains available and how an approved registration action is identified before changing behavior. |
| `app_write_file` | Retired wrapper delegates to `sandbox_required`; app changes are directed to `app_build_start`. | No active direct-write path identified in this wrapper; retain regression coverage for refusal. |

Source reviewed: `mcp_servers/mcp_apps/server.py`, `mcp_servers/mcp_apps/logic.py`, `mcp_servers/mcp_apps/skill.yaml`, `jarvis/admin/server.py`, `jarvis/db.py`, and `config/agents.yaml`. `mcp-apps` is granted to the App Builder agent. The exposed app tool inventory in `skill.yaml` includes both `app_create` and `app_register`.

## Required next action

Do not implement a guessed action identity for `app_create` or `app_register`. Extend the existing preview/confirmation contract to issue one opaque, bounded, durable approval ID and bind the exact previewed operation to it, then claim before dispatch and expose action-specific status/reconciliation. Before implementation, resolve whether `app_register` remains a directly callable action or becomes an internal-only operation. Preserve the requirement that app creation creates a private repository and that the human owns PR merge. After this contract is established, add duplicate, fresh-run replay, changed-input, claim-store failure, partial creation, process recovery, and unknown-outcome tests.

This source audit is not a completed lifecycle change. No live GitHub access or repository creation was attempted.
