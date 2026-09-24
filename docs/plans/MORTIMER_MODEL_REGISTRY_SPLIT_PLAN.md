# Model registry split — endpoints stay human-only, the model pool becomes routine

Status: **plan, awaiting Larry's review.** Nothing implemented. Written 2026-09-13 after a live session in which the developer sub-agent was refused twice while trying to add new models ("The registry file is still locked to human review — it's in the deny list, so self-edits can't touch it", 17:01:45).

*Reconciled 2026-09-22 against main `88b206f`:* still nothing implemented —
no `config/model_endpoints.yaml`/`model_profiles.yaml`, and
`config/upgrade_models.yaml` is still denied. #80 (`88b206f`) changed the
ground the §2 inventory describes, without doing the split:
- `config/model_access.yaml` (new) is a workload → route/profile policy layer
  that names `upgrade_models.yaml` profiles; it is not the endpoint/profile
  split.
- `jarvis/model_routing.py` (new) parses `upgrade_models.yaml` directly
  (`_load_model_registry`, `yaml.safe_load`, honouring `JARVIS_UPGRADE_MODELS`)
  rather than through `load_model_registry()` — one more direct-parse site
  that §2's "six sites", §5's changed-file list and §6 step 3 do not include.
- The registry now has **14** profiles, not 13: `codex-subscription` was added
  with no `base_url` or `api_key_env` (reachable only via the
  `codex_subscription` route). The 13 endpoint-bearing profiles still span the
  same 3 endpoints (8/3/2). The "13 profiles/models" in §2, §6 step 8 and §8,
  and the endpoint map, must account for a profile with no endpoint.

## §0 Why this exists

Sub-agent models go stale on the timescale of weeks, and today the only way to add one is Larry hand-editing a 258-line YAML file. The self-development loop cannot prepare that change, so the models the developer, analyst and librarian run on drift behind whatever shipped this month.

The wall is real but it is in the wrong place. `config/upgrade_models.yaml` is Tier 0 in `config/self_edit_allowlist.json`, and the reason written in `jarvis/selfedit/allowlist.py` is that Tier 0 holds "files whose corruption the loop CANNOT recover from because they ARE the loop … the model registry it plans with". The file's own header says it plainly: "the agent cannot re-point its own brain."

That reasoning covers one part of the file and not the rest. Two observations, both verified below:

1. **Deny is not what protects `main`.** Every self-edit lands as a PR on a sandbox branch the loop can never merge; the human merge is the last gate on all of them. Denying the file does not stop a bad change reaching production — review does. What it stops is the loop *preparing* the diff, which is exactly the clerical work worth automating for a file that churns.
2. **The genuinely dangerous part is two lines per profile.** Each profile carries `base_url` and `api_key_env` — `claude-opus` maps to `https://api.anthropic.com/v1/` and `ANTHROPIC_API_KEY`. Nothing in the codebase validates that a profile's host is a known provider (searched: no host allowlist exists). An edit that keeps the profile name and the key variable but swaps the host sends that key to someone else's endpoint on the next run, and it reads as a one-line change inside a large YAML diff. That is a credential boundary, and it is a stronger reason for Tier 0 than the one currently written down.

So: split the file along the boundary that matters, rather than opening or keeping the whole thing.

## §1 Scope

In: splitting the registry into a denied endpoint/credential map, a **generated upstream catalogue** and a routine model-profile pool; making the join happen in one loader; the invariants that make the credential boundary structural rather than a matter of review attention; migrating every direct-parse site; the allowlist entry.

Out: adding providers (still human-only, by construction); which sub-agent uses which profile (`config/agents.yaml` is already routine); council tier policy; the supervisor's own selection semantics; anything about C6/C7. **The daily sync job itself is a follow-on plan** — but its shape is fixed here (§4a, §6 step 8), because a split that ignores it would have to be redone.

## §2 What exists today (verified 2026-09-13)

- **Allowlist classification**, from `Allowlist.load('config/self_edit_allowlist.json').classify([...])`: denied — `config/upgrade_models.yaml`, `config/upgrade_agent.yaml`; routine — `config/agents.yaml`, `config/model_prices.yaml`, `config/model_aliases.yaml`; core — `jarvis/model_catalog.py`, `jarvis/agents/delegate.py`. **The sub-agent assignment side is already open**: `agents.yaml` names profiles (`model_profile: claude-sonnet-5` ×4, `claude-opus` ×2) and is routine. Only the pool is walled off.
- **13 profiles across 3 endpoints**: `https://openrouter.ai/api/v1` (8), `https://api.anthropic.com/v1/` (3), `https://api.moonshot.ai/v1` (2). Profiles: kimi-k3, kimi-k2, claude-opus, claude-fable-5, claude-sonnet-5, or-gpt-5-mini, or-gemini-flash, or-deepseek, or-gpt-5.1, or-grok-4.3, or-codex-max, or-grok-4.6, or-deepseek-v4-pro.
- **One real loader**: `load_model_registry()` (`jarvis/agents/upgrade_agent.py:251`), path precedence explicit > `JARVIS_UPGRADE_MODELS` > `config/upgrade_models.yaml`, returning `{"default", "profiles": {name: profile}}`; `resolve_profile()` and `available_models()` build on it. `jarvis/admin/server.py:1090` serves `available_models()` to the console.
- **Six sites parse the YAML directly instead**: `jarvis/model_catalog.py:36`, `jarvis/skills/registry.py:137`, `jarvis/vault.py:427`, `scripts/check_env.py:212, 334, 414`, `scripts/check_keys.py:74`, plus `scripts/voice_model_bench.py`. Each would need the joined view.
- **Existing invariants**: `tests/unit/test_model_registry.py` already enforces nine (identity required, unique, vendor-qualified; every council tier has ≥2 profiles; no single key owns a tier; every profile named by an agent exists; the default exists; the council partition is deterministic and rotates).
- **No host validation anywhere.** A profile's `base_url` is used as given (`upgrade_agent.py:365, 382, 418`).

## §3 VERIFY FIRST — settle these in step 1, before writing the split

1. **Admin API shape.** `available_models()` feeds the console picker. Does the joined profile dict keep every key the console reads (`name`, `label`, `provider`, `model`, `key_env`, `key_present`, `tier`, `vision`)? If the console reads `base_url`, it must still see it post-join.
2. **CI and test fixtures.** Tests point `JARVIS_UPGRADE_MODELS` at temporary single-file registries (`test_admin_plan_review.py:205, 243, 276`, `test_council_config.py:56, 204`, `test_check_env_model_registry.py`). Decide the compatibility rule: the loader must accept a legacy single file (profiles carrying `base_url`) so those fixtures keep working, or every fixture is rewritten. Prefer the former, with the legacy shape allowed only when it is the *whole* registry.
3. **Sandbox worktree.** The self-edit loop runs in an isolated worktree; confirm both config files are present there (nothing in `jarvis/agents/workspace.py` copies config explicitly — check how the worktree is created). A missing endpoints file must fail loudly, not silently produce keyless profiles.
4. **`jarvis/vault.py:427`** reads the registry to group credential checks by (key, endpoint). It needs endpoints specifically — confirm it consumes the joined view rather than the profile file.

**Answers (step 1, 2026-09-23, from the code at `impl/p1-recovery`):**

1. **Admin API shape — the join must supply `provider` and `api_key_env`; the console reads neither `base_url` nor `vision`.** `available_models()` (`jarvis/agents/upgrade_agent.py`) emits exactly eight keys per profile: `name`, `label`, `provider`, `model`, `key_env` (from `api_key_env`), `key_present`, `default`, `tier`. It never emitted `vision` or `base_url`, and no console reads them: MortimerHost's `SelfEditModel` (`macos/JarvisKit/Sources/JarvisKit/AdminAPI.swift`) decodes the same eight, and the frozen web `EditModePanel.tsx` reads `name`/`label`/`default`/`key_present`. Two of the eight (`provider`, `key_env`) come from the endpoint after the split, so the join merges them; `base_url` is merged too because `/api/model-routes`, `UpgradeAgent`, `SubAgent`, the council and `mcp_screen` read it. `codex-subscription` reports `key_env: ""`, `key_present: false` before and after. Pinned by `tests/unit/test_model_registry_split.py::test_available_models_is_byte_identical`, written against the pre-split file before any code moved.
2. **Fixtures — legacy single-file acceptance, not a fixture rewrite.** 25 test files point `JARVIS_UPGRADE_MODELS` (16 `setenv` sites) or a `registry_path` argument at a temporary single-file registry whose profiles carry `base_url`/`api_key_env`. The loader keeps accepting that shape when the file *is* the whole registry: no `endpoints:` section, no profile naming an `endpoint:`, and not a file named `model_profiles.yaml`. The default resolution never reaches the legacy shape while either split file exists (see the implementation record after §6), so a routine edit cannot smuggle a credential-bearing registry back in by recreating `config/upgrade_models.yaml`.
3. **Sandbox worktree — both files are present, because the sandbox checks out the whole tracked tree.** The historical `git worktree add` path is gone (2026-09-10). `sandbox/source.py` (`GitSource.fetch`) fetches a pinned commit and `sandbox/control.py` archives every blob in that commit's tree into the VM; nothing copies config selectively, and `jarvis/agents/workspace.py`'s `AppWorkspace` is for foreign app repos, not Mortimer's config. A missing endpoints file fails loudly: the loader raises `ModelRegistryError` when `config/model_profiles.yaml` exists without `config/model_endpoints.yaml`, when a profile names an endpoint id that does not exist, or when a split-shape profiles file has no sibling endpoints file. It never produces keyless profiles.
4. **`jarvis/vault.py` — it read the raw file, so it would have silently broken.** `verify` parsed `config/upgrade_models.yaml` with `yaml.safe_load` and grouped by `(api_key_env, base_url)` from each raw profile. Against the split profiles file every profile would have collapsed into one `("OPENAI_API_KEY", "")` group and probed nothing real. Step 3 converts it to `load_model_registry()` (the joined view); a test asserts the (key, endpoint) groups it prints are unchanged.

## §4 Design decisions (made — the implementer does not choose)

- **D1. Three layers, by who writes them.** The daily sync (§4a) is the reason this is three files rather than two: what a provider offers, what Mortimer chooses to use, and where the keys go are written by three different authors at three different rates.
  - `config/model_endpoints.yaml` — **deny**, written by Larry, changes when a provider is added. `endpoints:` id → `provider`, `base_url`, `api_key_env`; plus `supervisor:` pinning the planner's own brain by `identity` and `endpoint`.
  - `config/generated/model_catalog.<endpoint>.json` — **generated**, written by the sync job, daily. What each provider currently offers: `identity`, provider model string, context window, pricing, modality flags, deprecation, and per-entry `fetched_at` + `source`. Never hand-edited; a PR that changes it by hand is a mistake, and the header says so.
  - `config/model_profiles.yaml` — **routine**, written by Larry or by the loop, changes when the pool changes. Each profile names an `endpoint:` id and an `identity`, plus the choices that are ours and not the provider's: `name`, `label`, `tier`, `vision`, `temperature`, `effort`. Catalogue facts are joined in, not copied.
- **D2. The join happens once, in `load_model_registry()`.** It returns exactly today's shape with `base_url`/`api_key_env`/`provider` merged in from the endpoint, so no caller changes semantics. The six direct-parse sites are converted to call the loader; that conversion is most of the work.
- **D3. The credential boundary is structural.** A profile that declares `base_url`, `api_key_env` or any host-bearing key is a **load error**, not a warning, and a test asserts it. A profile naming an endpoint id that does not exist is a load error. A routine self-edit therefore cannot express "send the Anthropic key somewhere else" — the vocabulary is not available in the file it can write.
- **D4. The supervisor's brain stays pinned in the denied file.** `supervisor: {identity: …, endpoint: …}`. A test asserts the resolved planner profile matches the pin, so a routine edit cannot quietly re-point the planner by rewriting a profile's `model` string. Changing the planner is a human PR against the denied file, exactly as today.
- **D5. Allowlist change**: add `config/model_endpoints.yaml` to `deny`; drop `config/upgrade_models.yaml` (the file is gone). `config/model_profiles.yaml` needs no entry — `config/**` already makes it routine. This edit is itself Tier 0, so Larry merges it.
- **D6. Migration is mechanical and provably lossless.** A one-shot script renders the two files from today's one; a test asserts the joined registry equals the pre-split registry profile-for-profile, key-for-key.
- **D7. No behaviour change.** Same profiles, same defaults, same council tiers, same console picker, same `check_env` output. The only observable difference is which file a diff touches.

## §4a Designed for the daily sync (near roadmap)

The sync job fetches each provider's model list — OpenRouter's `/api/v1/models`, Anthropic's `/v1/models`, OpenAI's `/v1/models`, one fetcher per endpoint — writes `config/generated/model_catalog.<endpoint>.json`, and opens a PR when the content changes. Five consequences for *this* plan, all cheap now and expensive later:

1. **The join key is `identity`.** The existing invariants already require it to be present, unique and vendor-qualified (`tests/unit/test_model_registry.py`), which makes it the natural foreign key between a profile and a catalogue entry. Profiles must therefore carry `identity` as the authoritative field and the provider's model string becomes joinable rather than authoritative — a rename upstream shows up as a catalogue diff, not a silent 404 at run time.
2. **Provenance is per entry, not per file.** `fetched_at` and `source` on each catalogue entry, so a partial fetch (one provider down) ages only its own entries. `check_env` reports the oldest entry per endpoint and warns past a threshold; a stale catalogue must be visible, never silently trusted.
3. **Deprecation becomes a signal the loop can act on.** When a catalogue entry carries a retirement date or disappears while a profile still references it, that is a warning in `check_env` and a failing invariant in CI once the model is actually gone. This is the payoff: the loop proposes "or-grok-4.3 retires on the 30th, here is 4.6 on the same endpoint" as a routine PR against `model_profiles.yaml`, with the catalogue diff as its evidence.
4. **The sync job is not the self-edit loop and must not become it.** It runs on a schedule (launchd beside the other services, or CI), reads keys from the vault to list models, and its PRs touch **only** `config/generated/**`. It never writes `model_endpoints.yaml`, never writes `model_profiles.yaml`, and needs no self-edit machinery. Open question for review: whether `scripts/sync_models.py` should itself be Tier 0 (it holds keys and feeds routing) or stay `scripts/**` core — I lean Tier 0, on the same logic as `scripts/check_allowlist.py`.
5. **Pricing stops being hand-maintained where the provider publishes it.** `config/model_prices.yaml` is routine today and manual; once the catalogue carries prices, that file should shrink to the entries no provider publishes, with the rest joined from the catalogue. Not this plan's work, but the catalogue schema must carry price fields from the start so the migration is a deletion rather than a re-fetch.

What this means concretely for the steps below: `config/generated/` exists from day one with the current 13 models' facts written into it by hand-off from the split script, so the sync job's first run is a *diff* against a real baseline rather than an import of everything at once.

## §5 Files

New: `config/model_endpoints.yaml`, `config/model_profiles.yaml`, `config/generated/model_catalog.<endpoint>.json` (three, seeded from today's registry), `scripts/split_model_registry.py` (one-shot, deleted after), `tests/unit/test_model_registry_split.py`.
Changed: `jarvis/agents/upgrade_agent.py` (loader join, legacy acceptance), `jarvis/model_catalog.py`, `jarvis/skills/registry.py`, `jarvis/vault.py`, `scripts/check_env.py`, `scripts/check_keys.py`, `scripts/voice_model_bench.py`, `config/self_edit_allowlist.json`, `tests/unit/test_model_registry.py` (path + two new invariants), `docs/` (this plan's outcome, DEVIATIONS if any).
Deleted: `config/upgrade_models.yaml`.

## §6 Implementation steps, in order

1. **Answer §3.** Record the four answers in this document before touching code.
2. **Loader first, one file still.** Teach `load_model_registry()` to join endpoints into profiles, accepting both shapes (legacy single file; split pair). Tests pass unchanged — nothing else has moved yet.
3. **Convert the six direct-parse sites** to the loader. Still one file. `tests/unit` green, `check_env` output identical (diff the before/after text).
4. **Split the file** with the one-shot script; add the equality test from D6; delete the legacy file. Everything still green.
5. **Add the invariants** (D3, D4) as failing-first tests, then make them pass.
6. **Allowlist and docs**: the `deny` entry, the header comments in both new files explaining which tier each is and why.
7. **Prove the point**: have the loop itself open a sandbox PR adding one new profile on an existing endpoint. That PR is the acceptance evidence — it is the thing that is impossible today.
8. **Seed the catalogue** (`config/generated/`) from the split script with the 13 current models, including `fetched_at: null` and `source: seeded`, so the sync job's first run reads as a diff. Wire `check_env` to report catalogue age. The sync job itself is the follow-on plan, and it starts against a populated baseline rather than an empty directory.

## §7 Tests

Existing nine invariants keep passing against the joined view. New: profile-declares-no-endpoint-keys is a load error; unknown endpoint id is a load error; supervisor pin matches the resolved planner profile; joined registry equals the pre-split registry (D6); legacy single-file registries still load (fixtures); `available_models()` output is byte-identical before and after for the console contract.

## §8 Verification Larry runs

`scripts/check_env.py` shows the same model-registry and screen-vision verdicts as before; a live voice session with a sub-agent delegation (developer or analyst) behaves identically; the console model picker lists the same 13 profiles; and the step-7 PR appears on GitHub with a new profile in it, authored by the loop.

## §9 Rollback

Revert the allowlist entry and concatenate the two files back into `config/upgrade_models.yaml`; the loader accepts that shape throughout (D2), so rollback is one commit and no code change. Keep legacy acceptance for at least one release after the split.

## §10 Risks

The credential boundary is the whole point: if D3's invariants are weak or a reader bypasses the loader, the split makes things worse than the status quo by *appearing* safe. Mitigation: step 3 lands before step 4, so by the time the file splits there is exactly one reader. Secondary: drift between the two files (mitigated by the unknown-endpoint load error); CI fixtures (§3 item 2); a worktree missing the denied file (§3 item 3, must fail loudly).

## §11 Non-goals

Adding a provider or endpoint without human review. Automatic model *selection* changes — which sub-agent runs on what stays a human or routine-PR decision in `agents.yaml`, and no catalogue entry ever re-points a running agent by itself. Writing the sync job (§4a fixes its shape and its boundaries; the job is the next plan). Automatic merging of anything.
