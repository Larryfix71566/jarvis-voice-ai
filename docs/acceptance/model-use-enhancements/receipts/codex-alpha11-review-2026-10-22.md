# Review: Codex alpha.11 compatibility patch (b4ce39a2 vs 636880ea)

## Verdict
**No blocking findings.** Version admission cannot by itself enable inference; all request-time gates are preserved. Below are non-blocking findings in priority order.

## Gate trace (what the patch does and does not change)

The only production change is one string added to `CODEX_VERIFIED_VERSIONS` plus a comment edit. Path to a real child process (`_run_codex_response` / `_run_codex_response_async` in `jarvis/subscription.py`):

1. `JARVIS_CODEX_SUBSCRIPTION_NO_TOOLS_VERIFIED == "1"` — operator env gate, unchanged.
2. `validate_codex_capability_receipt(model)` — requires `JARVIS_CODEX_SUBSCRIPTION_CAPABILITY_RECEIPT` to point at a file, then checks `receipt["executable"] == codex_runtime_identity()` (resolved **path + sha256 + version**), `model`, `proof_kind`, `advertised_tools == []`, strict-bool/int proof fields, `catalog_sha256 == _json_digest(catalog)`, single-model catalog with matching slug, and `invocation_sha256 == _json_digest(_codex_argv(model, command=identity["path"]))`. Unchanged.
3. `codex_runtime_identity()` — version must be in `CODEX_VERIFIED_VERSIONS`; this is the only line the patch affects, and it is necessary-not-sufficient (step 2 still binds sha256/catalog/argv).
4. `_run_sync/_run_async` — `_ENV_ALLOWLIST`, `_temp_cwd` under `/tmp`, catalog materialized into the owned workdir, `--ephemeral --ignore-user-config --strict-config --sandbox read-only`, `CODEX_DISABLED_FEATURES`, `CODEX_ISOLATION_CONFIG` (history/analytics/otel off, `mcp_servers={}`, `web_search` disabled). Unchanged.
5. `_CodexCompletions.create` / `_AsyncCodexCompletions.create` reject `tools`; `_prompt` rejects tool history/images; `_codex_text` rejects non-text items. Unchanged.

An alpha.11 binary with no receipt, or a .10.2 receipt (different sha256/version), fails closed at step 2/3. Auto-update to a future build changes sha256 and version → fails closed.

## Findings

### 1. Medium — validator ignores `candidate_runtime_diagnostic` / `production_activation_authorized`, so admission silently upgrades a pre-admission diagnostic receipt
- **Evidence:** `scripts/verify_subscription_capability.py::probe` emits `"candidate_runtime_diagnostic": candidate_runtime` and `"production_activation_authorized": False` with the docstring "A successful fixture still cannot authorize a new runtime." `validate_codex_capability_receipt` never reads either key. The committed artifact shows `candidate_runtime_diagnostic: true`.
- **Impact:** Before this commit, the alpha.11 candidate receipt was unusable because `codex_runtime_identity()` rejected the version. After this commit, the same file (the full one with `catalog`, presumably at the original `--output` path, `runtime_receipt_sha256` suggests it exists) passes validation the moment an operator sets the two env vars — no regeneration through the verified path is forced. Not inference-by-admission (operator still sets both envs), but the "diagnostic only" marker the script writes is a no-op at the enforcement point, which contradicts the script's own claim.
- **Suggest:** reject receipts where `candidate_runtime_diagnostic is True` (forces a post-admission re-run via `codex_runtime_identity()`), and add a case to `test_receipt_rejects_model_binary_config_and_proof_drift` for it. Alternatively document explicitly that the marker is informational only.

### 2. Low — committed receipt includes fields the supplied script cannot produce; provenance unverifiable
- **Evidence:** `docs/.../codex-alpha11-offline-2026-10-22.json` contains `host_isolation`, `observed_at_utc`, `runtime_receipt_sha256`, `scope`, `focused_tests {passed: 78}`, `live_acceptance`. None are emitted by `probe()` or `main()`. The `catalog` key is removed.
- **Assessment:** The scoping language is honest and consistent with the task framing (.10.2 live evidence historical; .11 activation blocked; no new live test). Removing `catalog` is a positive property — `receipt["catalog"]` raises `KeyError` → `SubscriptionCapabilityError`, so this artifact can never be pointed at by the env var and work. But "78 passed", `external_network: denied_by_macos_sandbox`, `existing_codex_credentials: read_denied` are assertions from an unsupplied wrapper; I cannot corroborate them and did not run tests. The top-level `explicit_matching_host_refusal: false` alongside `negative_unadvertised_tool_rejected: true` is consistent with `main()` (positive probe's value survives while only the negative flag is overwritten) but reads as contradictory; consider copying the negative probe's flag or dropping the positive one.

### 3. Low — test coverage of the admission is thin but adequate
- The parametrized `test_current_loopback_verified_runtime_still_requires_exact_receipt` proves alpha.11 is admitted at `codex_runtime_identity()` and still fails on missing receipt. `test_unknown_installed_version_fails_before_provider` (0.161.0) and `test_candidate_inspection_does_not_enable_unknown_runtime` (99.0.0) still prove non-members are rejected. Exact set membership on `stdout.strip()` means `alpha.11.1`, trailing text, or multi-line `--version` output fail closed.
- Gap: no test pins the admitted set itself (a snapshot assertion on `CODEX_VERIFIED_VERSIONS` would catch accidental widening) and nothing tests Finding 1.

### 4. Info — disabled-feature/config lists carried across an alpha unchanged
- `--strict-config` plus a successful positive probe implies every `--disable` name and `-c` key is still accepted by alpha.11; the mock's `tools == []` check would catch any newly advertised built-in tool. It does not cover new non-tool behaviours (network, telemetry, caching) an alpha may add — which is exactly what the pending exact-binary workload acceptance is for. The comment change ("passed ... on 0.163.0-alpha.11") is supported by the receipt's `negative_probe` block for loopback scope only, not live scope, and the comment does not claim otherwise.

## Summary
Patch is correct and minimal; regression risk is low. The one substantive weakness (Finding 1) is pre-existing design, but this commit is the step that makes it observable: the script's "diagnostic cannot authorize" promise is not enforced by the validator.

## WS-05 disposition (author, after review)

All findings were nonblocking. Finding 1 is documented explicitly in the
offline receipt and existing plan: diagnostic markers record collection mode,
not an additional authorization mechanism. Exact version admission plus a
matching full receipt can pass the capability check only; the operator gate
and release/live acceptance remain separate and unchanged. The complete local
receipt is not installed; the published summary lacks the catalog and cannot
be a runtime receipt. No live acceptance is claimed.

At initial publication, the response to finding 2 included the local launcher
source and hash, test command, result and log hash. The later sanitation
disposition below supersedes that source-publication decision. The positive-probe refusal field is
named explicitly; the negative-probe result retains its explicit refusal.
The 182-test host rerun passed after three tool-sandbox Unix socket bind
failures; no source repair was needed. Findings 3 and 4 are retained as
limitations, with unknown versions and binary/catalog/invocation drift covered
by existing tests; no live behavior is inferred from local fixtures.

The reviewed runtime and test source at b4ce39a is unchanged by the subsequent
review/evidence publication commit. No merge, installation or activation.

## Later publication sanitation disposition (WS-05)

Independent integration readiness review identified personal absolute paths
in the embedded launcher source. The final summary removes `launcher_source`
and retains the original launcher digest with an explicit historical-byte
scope, plus a path-free collection-method description. No transformed source
is presented as matching that digest. Original review findings remain above.
This corrects the earlier author claim that publishing the exact launcher was
appropriately sanitized. It does not remove previously published Git history,
change runtime/test bytes, or establish fresh runtime/live acceptance.
