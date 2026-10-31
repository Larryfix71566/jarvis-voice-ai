# Mortimer Remote Access Plan — per-client bearer tokens on every endpoint, Tailscale tunnel, fail-closed binds

**Current status — 2026-10-31:** Bounded synthetic/offline admission, result synchronization, recovery and typed-card source have independent acceptance. Final typed-card source is `a121dfb06385702b82a18041d7d974ab40877ee9` / tree `10b9b68d7a27d52ca2b54d42784326b5da279f86`; [the final receipt](#typed-phone-card-bounded-source-acceptance--2026-10-31) records exact evidence and limits. Production authenticated construction, real content/transport, full contract/UI/integration validation and live release remain open. The existing phone plan's [completion audit](MORTIMER_PHONE_ACCESS_PLAN.md#19-product-completion-audit--2026-10-31) identifies the remaining foreground product path. Earlier implementation/review statuses below are dated history; normative restrictions and outstanding gates remain binding.

**Historical status snapshot (October 22–29, superseded by later bounded offline source receipts):** Documentation preparation registration, 2026-10-22, on `docs/roadmap-preparation-claims-20261022`; no provisioning implementation claim. Dormant R1 deployed at `539f8f6` on 2026-09-28; R2 guard merged as `a39136a` and deployed in `7c4637e` on 10-02, as recorded in the dated reconciliation below. As of 2026-10-29, the bounded offline phone-admission policy and S0 adapter are authored on `codex/ws04-phone-admission-core-20261029`; independent exact-source review ACCEPTED `6a4b22cbd38014b01fb2de6a35245416c20560b6`; PR checks and merge remain pending. R3-02 reservations and exact two-file R3-S1 fake-store scope below are adopted branch-locally in PR #290; no implementation or live acceptance is claimed. This does not implement onboarding or complete Stage 1.1. Token onboarding method, credential preparation and activation remain open. Remote activation remains undecided; enabled-mode acceptance is open. Original plan drafted 2026-08-26. Implements roadmap track **T2** (`docs/plans/MORTIMER_PLATFORM_ROADMAP.md` §2.2). Gate: **G2**.

**Author / origin.** Larry, quoted in the roadmap's origin block: *"ios app for remote connection to the AI Assistant via VPN tunnel for security"* and *"I want this data available to the AI and myself but secured from any intruder."* Roadmap R4 states the principle this plan implements: *"Token auth on every endpoint, even inside the tunnel. Why: a VPN authenticates devices, not callers; any app on a joined phone could otherwise call `/api/selfedit/run`."*

**Roadmap constraints this plan is bound by.**

| C | How this plan honours it |
|---|---|
| **C1** — backend contract does not change for the client migration | No route is added, removed, renamed, or given a new response body. The only change to every request is one `Authorization` header. The bot learns nothing about which client is calling: `ClientIdentity` is put on the ASGI scope and read by nobody in T2 (A9). |
| **C2** — localhost is the trust boundary until T2 lands | This plan *is* T2. Until G2 passes, `JARVIS_BIND_HOST` stays at its `127.0.0.1` default and §5 Step 9 is the only step that changes it. Steps 1–8 are safe to merge without opening anything. |
| **C3** — sensitive tier waits for G3 | Nothing here stores or classifies content. |
| **C4** — every mutation stays draft → confirm | No mutation is added. `python -m jarvis.auth add/revoke` is a CLI, not an assistant-reachable tool — there is deliberately no MCP server and no sidecar endpoint for token management (A13), which is the same rule `jarvis/vault.py` already follows. |
| **C5** — sub-agents act on data, never on windows | Untouched. |
| **C6** — untrusted content never shares an agent with an outbound channel | Untouched; no agent gains a server. |
| **C7** — routing eval ≥ 90 % | No agent, Supervisor model, or Supervisor prompt changes. The eval is re-run anyway (§8 V9) because `tests/evals/routing_eval.py` starts a `SkillRegistry`, and three `skill.yaml` files gain a `requires_env` entry (§5 Step 6). |
| **C8** — self-edit allow/deny changes are human commits | This plan adds three deny-list entries (A14). **The implementing model does not make that edit**; §8 V8 is Larry making it, and §5 Step 12's test *reports* the state rather than asserting it, so the plan merges before Larry's commit. |
| **C9** — secrets go in the vault | The service token's plaintext goes in the vault under `JARVIS_SERVICE_TOKEN` (§5 Step 6). Client token *hashes* go in `data/jarvis.db` and are not secrets (A1). No `.env` entry, no `config/` entry. |
| **C10** — degradation-proof | Every security-relevant module is given as literal, complete source in §5. Every "investigate" is a decision tree with a command and both branches (A10). Every adversarial case is a named test in §7. |

**Contracts this plan INTRODUCES (consumed by later plans).**

- **K1 — client bearer tokens.** Fully specified in A1–A9 and §5 Steps 1–5, 7–9. Consumed by `MORTIMER_NATIVE_CLIENT_PLAN.md` (T1), `MORTIMER_LOCAL_VOICE_AND_MINI_PLAN.md` (T3), `MORTIMER_MAIL_CALENDAR_BRIEF_PLAN.md` (T5). Those plans cite this document's §3 A1/A5/A6 and do not restate the token format, the header, or the verification helper. **Keychain storage convention (CP-F15), part of K1:** the client bearer token lives in a generic-password item with service `"com.mortimer.jarviskit"` and account `"<scheme>://<host>:<port>"` derived from the **bot URL**. Both this plan's `ShellAuth` (A15) and NATIVE's `KeychainStore` read and write that same item — one convention, no drift.
- **K5 — host/URL configuration.** Fully specified in A11 and §5 Step 8. `jarvis/urls.py` is the one module that knows a default host. Consumed by T1 (`JarvisConfig(botURL:adminURL:token:)`) and T3.

**Contracts this plan CONSUMES (by doc + section).**

- **K2 — per-server environment scoping**, introduced by `MORTIMER_SECURITY_HARDENING_PLAN.md` §3 D-H1/D-H2 and §5 Steps 1–2. This plan does **not** restate `build_child_env`, `BASE_ENV_KEYS`, or the missing-variable WARNING rule. It uses the mechanism exactly as specified: §5 Step 6 adds the single name `JARVIS_SERVICE_TOKEN` to the `requires_env` list of the three servers that construct an `AdminClient`. That is precisely the hand-off the hardening plan anticipates in its "Forward compatibility note" (`MORTIMER_SECURITY_HARDENING_PLAN.md` lines 57–63: *"The REMOTE_ACCESS plan adds that name to `mcp_selfedit/skill.yaml`'s `requires_env` itself."*).
- **D-H9 deny-list entries**, same document §3 D-H9. Overlap check in A14: the hardening plan adds `jarvis/skills/registry.py`, `mcp_servers/*/skill.yaml`, `config/agents.yaml`, `tests/unit/test_agent_isolation.py`. This plan adds three *different* entries and one of them (`mcp_servers/*/skill.yaml`) is **already covered by the hardening plan** — see A14, which drops it rather than duplicating it.

---

## Revision table (findings closed in this pass)

Maps each closed review/cross-plan finding to the section changed and what changed. Review findings are `F1…F22`; cross-plan resolution findings are prefixed `CP-`.

| Finding | Severity | Section(s) | What changed |
|---|---|---|---|
| F1 | BLOCKER | A7, §5 Step 4, §7 T-A17c | Sidecar adds `BearerAuthMiddleware` **before** CORS so CORS is outermost and the 401 carries `Access-Control-Allow-Origin`; measured (see §7). A7 rewritten: same ordering in both processes. New test asserts ACAO on the 401. |
| F2 | BLOCKER | §5 Step 6(d) table, §7 T-A31b | `mcp_web` row corrected: `requires_env` is `[TAVILY_API_KEY]` today, append (never replace). New test asserts `TAVILY_API_KEY` survives. |
| F3 / CP-F7 | BLOCKER | §0.11, §5 Step 6, §7 T-A32b | §0 gains a hard T4a precondition gate (stop if `env = dict(os.environ)` still in `registry.py`); new environment-level test proves the token is absent from a scoped child env. |
| F4 | MAJOR | §1.3, §3 A6, §5 Step 7, §7 T-A37 | `pipecat-ai-prebuilt==1.0.5` **is** pinned (`requirements-lock.txt:113`); bot route count raised to 17, `/client`+`GET /` marked served, docstring rewritten, T-A37 enumerates `Mount`. |
| F5 | MAJOR | §5 Step 2 (`verify_bearer`), §3 A6, §6, §10 R10 | Verdict split from bookkeeping: `SELECT` decides identity (never blocks under WAL), the `last_used_at` `UPDATE` is best-effort in its own `try/except`, throttled to 60 s, on a short-timeout connection; a lock returns 503 not 401. |
| F6 | MAJOR | §3 A8, §5 Step 9, §6, §4 manifest, §8 V5 | `BIND_WAIT_S` lowered to 20 s with the invariant `mortimer.sh` sleep (25 s) `> BIND_WAIT_S`; `check()` probes health; `scripts/mortimer.sh` added to §4. |
| F7 | MAJOR | §5 Step 7 (both branches), §3 A8, §7 T-A35 | `build_argv`/`_parse` strip caller `--host`/`--port` so no command-line argument can widen the gated bind; A8 states it; test added. |
| F8 | MAJOR | §3 A8, §6, §8 V5, §9, §10 R6 | Interface-absent case falls back to loopback with a loud ERROR under new knob `JARVIS_BIND_STRICT` (default `false`); the "no token" case keeps the hard refusal. |
| F9 | MAJOR | §5 Step 8 (`App.tsx`), §3 A12, §11 item 5 | Toast uses the real `speaker-gate-notice` class on `<span role="status">` with a `useEffect` `clearTimeout` cleanup. |
| F10 | MAJOR | §1.5, §5 Step 8, §3 A12, §8 V5c | `requestHeaders` decision tree (verify field against `@pipecat-ai/small-webrtc-transport` `.d.ts`; `?token=` fallback); network-tab check covers both `POST` and `PATCH /api/offer`. |
| F11 | MAJOR | §5 Step 0, §5 Step 6, §8 V1, §10 R5 | Service-token mint promoted to §5 Step 0 (before any code); startup guard logs `service_token_missing`; the two watchers `raise_for_status()` so a 401 is not parsed as a job. |
| F12 | MAJOR | §4 Modify table, §11 item 9 | `scripts/mortimer.sh` and `tests/unit/test_db.py` added to the manifest; count re-derived (28 modified paths). |
| F13 | MAJOR | §7 headers, §8 V10 | Test counts re-derived from the tables (50 new across 5 files); per-file headers and V10 corrected. |
| F14 | MINOR | §3 A6, §6, §7 T-A22 | 4401 annotated as ASGI-level only — uvicorn surfaces the pre-accept close to the client as HTTP 403. |
| F15 | MINOR | §7 `test_auth.py` | `test_auth_enabled_table` added with the literal `"0"`/`"no"`/`""`/`"FALSE"` cases. |
| F16 | MINOR | §3 A6, §5 Step 3, §7 T-A17d | `OPTIONS` pass-through narrowed to genuine preflight (both `Origin` and `Access-Control-Request-Method` present); test for `OPTIONS` without `Origin` → 401. |
| F17 | MINOR | §3 A14, §12 | Heading corrected to **Three**; the false `urls.py` distinction removed and the real reason stated once (no path matches an allow pattern; deny is insurance against future widening). Per CP-A, `urls.py` is **not** added (not in the reconciled allow-list). |
| F18 | MINOR | §6 opening, §5 Step 8 (`api.ts`) | §6 opening softened to "one owner per runtime"; the two web fallbacks changed to `127.0.0.1` to match `jarvis/urls.py`. |
| F19 | MINOR | §5 Step 11 (`.env.example`), §6 | `JARVIS_ADMIN_PORT`/`JARVIS_BOT_PORT` documented in `.env.example` with the URL-must-agree rule. |
| F20 | MINOR | §5 Step 7 | "add `import os`" instruction added for `spoken_acceptance.py`. |
| F21 | MINOR | §9, §3 A5 | "Rotating the service token" paragraph added; A5 notes `service_headers()` is captured once per `AdminClient` (process-lifetime). |
| F22 | MINOR | §3 A10, §5 Step 7 | Runner-app docstring range corrected to `run.py:169-183`. |
| CP-F1 | BLOCKER | §0.7, §3 A3, §5 Step 1 | Migration cross-guard added (REMOTE owns `0034_client_tokens`; MAIL reserves `0035`); `MIGRATIONS` insertion anchored by "append after the last tuple", not a line number. |
| CP-F4 | MAJOR | §4 manifest rows, §5 Step 6(d) | `mcp_selfedit`/`mcp_web` manifest rows say **append** `JARVIS_SERVICE_TOKEN` (never replace — do not delete SEC's `JARVIS_UPGRADE_PROFILE` or `TAVILY_API_KEY`). |
| CP-F6 | BLOCKER | §9, §10 R15, §7 T-A34b | Note added that `JARVIS_ENV_SCOPING_ENABLED=false` post-REMOTE leaks the token to all twelve children; `test_service_token_is_not_in_a_scoped_child_env` + CI-ordering assertion added. (SEC owns the §9 kill-switch row.) |
| CP-F15 | MAJOR | §3 A15, §5 Step 10, §6, §8 V6 | K1 Keychain convention fixed to service `"com.mortimer.jarviskit"`, account `<scheme>://<host>:<port>` from the bot URL; NATIVE uses the same item. |
| §8 allow-list | — | §8 V8 | V8 rewritten to "apply row W1 of `docs/plans/ALLOWLIST_SEQUENCE.md` and run its verify command" (SEC owns that artifact). |

---

## Corrections to the roadmap

Four. All verified against source; the plan proceeds on the corrected facts.

**R-A1 — the token CLI is `python -m jarvis.auth`, not `python -m jarvis.vault client-token add <name>`, and the store is the DB, not the vault.**
Roadmap §2.2 "In scope" says *"minted by a CLI (`python -m jarvis.vault client-token add <name>`), stored in the vault"*. The cross-plan contract K1 already corrects this and this plan implements the correction. Two reasons, both verifiable: (a) what is stored server-side is a **SHA-256 hash**, which is not a secret and therefore does not belong behind AES-256-GCM and a Keychain round-trip — `jarvis/vault.py`'s `load_secrets()` decrypts the *entire* vault on every `get_secret()` call (`jarvis/vault.py:232-233`), so putting token hashes there would decrypt every credential Mortimer owns on every HTTP request; (b) `jarvis/vault.py` is deliberately import-light and CLI-only, and `data/**` plus `*.vault` are on the self-edit deny list precisely so that machinery is never touched. The *service token's plaintext* does go in the vault (C9) — that one is a secret.

**R-A2 — the sidecar's CORS allow-list is not "replaced by token auth"; it is left in place and made irrelevant.**
Roadmap §2.2 says *"the CORS allow-list is replaced by token auth"*. `jarvis/admin/server.py:107-113` allows exactly `http://localhost:5173` and `http://127.0.0.1:5173`. Removing it would *widen* the sidecar's browser surface while the console is still alive. This plan leaves `CORSMiddleware` exactly as it is on the sidecar (A7) and deletes it when `web/` is deleted at T1.4 — not here. On the **bot** the runner's own CORS default is already `allow_origins=["*"]` (`pipecat/runner/run.py:499-505`, `args.allowed_origins or ["*"]`), so there is no allow-list there to replace.

**R-A3 — the bot's WebRTC signalling is not one route; it is up to seventeen, four of which are WebSockets that an HTTP middleware cannot see.**
Roadmap §2.2 and K1 say "the bot's WebRTC signalling route(s)". Verified enumeration in §1.3: `_configure_server_app` (search `def _configure_server_app` — `pipecat/runner/run.py:497`) registers six route families. Four of them are `@app.websocket` routes (`run.py:486, 491, 1274, 1279`). Starlette's `BaseHTTPMiddleware` — what `@app.middleware("http")` produces — only runs for `scope["type"] == "http"`. This plan therefore uses a **pure-ASGI middleware** (A6) that inspects `scope["type"]` itself and covers both. An implementer who reached for `@app.middleware("http")` would have shipped four unauthenticated WebSocket endpoints. (The count is seventeen and not fifteen because `pipecat-ai-prebuilt==1.0.5` **is** pinned in `requirements-lock.txt:113`, so `_setup_frontend_routes` mounts `/client` and registers `GET /` on Larry's machine — see §1.3.)

**R-A4 — `jarvis/config.py`'s `jarvis_webrtc_endpoint` is dead configuration, and the console does not use it.**
Roadmap §1's table and K5 imply the bot URL is configured. Verified: `grep -rn 'jarvis_webrtc_endpoint\|JARVIS_WEBRTC_ENDPOINT'` across the repo returns exactly one line — its own definition at `jarvis/config.py:80`. The console hardcodes `http://localhost:7860/api/offer` at `web/src/jarvisClient.ts:17`. This plan introduces `JARVIS_BOT_URL` (K5) as the real knob and leaves `jarvis_webrtc_endpoint` untouched and unread; deleting a `Settings` field is out of scope and would need its own `.env.example`/test sweep.

---

## §0 Binding constraints for the implementing model

1. **Do not `git commit`, `git add`, `git checkout`, or `git branch`.** Sandbox git leaves an `index.lock`. Larry commits, on branch `feat/remote-access-t2`.
2. **Do not edit `config/self_edit_allowlist.json`.** Roadmap C8. A14 lists the entries; §8 V8 is Larry making that edit.
3. **Do not edit `jarvis/vault.py`.** It is on the self-edit deny list and this plan needs nothing from it beyond `get_secret`/`set_secret`, which already exist (`jarvis/vault.py:232, 236`).
4. **Do not fork, vendor, patch, or monkey-patch Pipecat.** `/usr/local/lib/python3.11/dist-packages/pipecat` (1.4.0) is read-only reference. A10's decision tree has exactly two branches and a third "report and stop" outcome; there is no fourth.
5. **Write the code in §5 verbatim.** Where §5 gives a complete module, that module's content is the plan's content — do not "improve" the constant-time compare, do not add a cache, do not add a second verification path.
6. **Kill switches are read in exactly one place each.** `JARVIS_AUTH_ENABLED` is read only in `jarvis/auth.py:auth_enabled()`. `JARVIS_BIND_HOST` is read only in `jarvis/bind.py:resolve_bind_host()`. If you find yourself reading either name a second time, you are wrong.
7. **Migrations are append-only, and REMOTE owns `0034_client_tokens`.** Add one `MIGRATION_<n+1>` constant and **append its tuple after the last tuple in `MIGRATIONS`** (locate that tuple by searching for the newest `(".._..", MIGRATION_..)` line — today `("0033_skill_events", MIGRATION_0033_skill_events)` — not by a line number); never edit an existing migration string, never renumber. **Cross-plan guard (CP-F1):** REMOTE (W1) owns `0034_client_tokens`; `MORTIMER_MAIL_CALENDAR_BRIEF_PLAN.md` (MAIL) reserves `0035_brief`. Because `CREATE TABLE IF NOT EXISTS` makes a number collision silent, confirm before you start that no other `0034_*` exists: `grep -c 0034 jarvis/db.py` should be 0 (the existing newest is `0033`). If a `0034_*` other than `client_tokens` is already present, **stop and report** — wave order was violated.
8. **`pytest tests/unit -q` must be green before you stop.** The suite is ~1538 tests today; §5 Step 5 changes the default auth posture for the whole suite and Step 5 is where you prove nothing else broke.
9. **Every new module is stdlib-only or `jarvis.db`-only** unless §5 says otherwise. `jarvis/auth.py`, `jarvis/bind.py`, `jarvis/urls.py`, and `jarvis/authmw.py` import no third-party package — they are imported by the bot, the sidecar, the CLI, and MCP children.
10. **If a step's precondition is not true, stop and report.** Do not improvise a substitute. The two places this can happen are A10's Check B1 and constraint 11 below.
11. **This plan assumes T4a (per-server env scoping) has landed.** `MORTIMER_SECURITY_HARDENING_PLAN.md` §5 Steps 1–2 (`build_child_env`, `BASE_ENV_KEYS`) MUST be merged before §5 Step 6 of this plan. `requires_env` *scopes* a secret only once `build_child_env` exists; until then the registry copies the whole environment and the service token reaches every MCP child, including the two that handle untrusted content (`mcp_web`, `mcp_screen`). **Before Step 6, run `grep -n 'env = dict(os.environ)' jarvis/skills/registry.py`. If it matches, stop and report — T4a has not landed and the wave order was violated.** `tests/unit/test_service_token.py` encodes the same `registry.py` check as a hard assertion (T-A34b), and proves the token is absent from a scoped child env (T-A32b), so CI fails rather than shipping a leaked token.

---

## §1 What exists today (verified, path:line) and the gap

### 1.1 The sidecar has no authentication of any kind

`jarvis/admin/server.py:105` — `app = FastAPI(title="jarvis-admin", docs_url=None, redoc_url=None, openapi_url=None)`. Docs/OpenAPI routes are already off, so there is no `/docs`, `/redoc`, or `/openapi.json` to consider.

`jarvis/admin/server.py:107-113` — the only middleware that inspects a request is `CORSMiddleware`, allowing `http://localhost:5173` and `http://127.0.0.1:5173`, methods `GET`/`POST`, headers `Content-Type`. **`Authorization` is not in `allow_headers` today** — §5 Step 4 adds it, or every browser preflight for an authenticated request fails.

`jarvis/admin/server.py:133-146` — one `@app.middleware("http")` named `_log_5xx_responses`. It is a `BaseHTTPMiddleware` and it does not authenticate.

`jarvis/admin/server.py:1768-1779` — `main()` hardcodes `host, port = "127.0.0.1", 7861` and calls `uvicorn.run(app, host=host, port=port, log_level="warning")`. There is no env override and no startup check.

There is no `StaticFiles` mount anywhere in the file (`grep -n 'StaticFiles\|app.mount' jarvis/admin/server.py` → no matches), so there is no static route to exempt.

### 1.2 Sidecar source route inventory — 79 decorators

Revalidated 2026-09-28 against deployed main `539f8f6`: 79 runtime
`APIRoute` entries. `test_every_sidecar_route_requires_bearer_token` passes
for every route, including all ten integrated status/workflow routes. An
isolated actual admin server also passed enabled/dormant health checks.
No route is exempt with authentication enabled. Dormant auth forces loopback.
Line numbers below are the earlier `2e6f769` source snapshot, not current offsets.

| # | Method | Path | Line |
|---|---|---|---|
| 1 | GET | `/api/health` | 1535 |
| 2 | GET | `/api/git/status` | 1540 |
| 3 | GET | `/api/architecture` | 1545 |
| 4 | GET | `/api/git/log` | 1572 |
| 5 | GET | `/api/git/diff` | 1577 |
| 6 | GET | `/api/git/actions` | 1582 |
| 7 | POST | `/api/git/prepare-commit` | 1587 |
| 8 | POST | `/api/git/commit` | 1594 |
| 9 | POST | `/api/git/prepare-push` | 1599 |
| 10 | POST | `/api/git/push` | 1604 |
| 11 | GET | `/api/selfedit/models` | 1612 |
| 12 | GET | `/api/model-routes` | 1617 |
| 13 | POST | `/api/model-routes/stage` | 1657 |
| 14 | POST | `/api/model-routes/confirm` | 1667 |
| 15 | GET | `/api/selfedit/status` | 1675 |
| 16 | POST | `/api/selfedit/stage` | 1682 |
| 17 | POST | `/api/selfedit/run` | 1732 |
| 18 | GET | `/api/selfedit/run` | 1925 |
| 19 | GET | `/api/selfedit/file` | 2078 |
| 20 | POST | `/api/selfedit/write` | 2101 |
| 21 | POST | `/api/selfedit/finish` | 2153 |
| 22 | POST | `/api/selfedit/validate` | 2200 |
| 23 | POST | `/api/selfedit/verify-appearance` | 2214 |
| 24 | POST | `/api/selfedit/submit` | 2230 |
| 25 | POST | `/api/selfedit/cancel` | 2278 |
| 26 | POST | `/api/selfedit/revert` | 2307 |
| 27 | POST | `/api/selfedit/reject` | 2322 |
| 28 | POST | `/api/appbuild/start` | 2373 |
| 29 | GET | `/api/appbuild/job` | 2506 |
| 30 | POST | `/api/appbuild/submit` | 2608 |
| 31 | POST | `/api/appbuild/cancel` | 2674 |
| 32 | POST | `/api/research/start` | 2705 |
| 33 | GET | `/api/research/job` | 2781 |
| 34 | POST | `/api/research/save` | 2803 |
| 35 | POST | `/api/research/cancel` | 2848 |
| 36 | GET | `/api/memory` | 2873 |
| 37 | POST | `/api/skills/runtime-inventory` | 2885 |
| 38 | POST | `/api/skills/creator/associate` | 2963 |
| 39 | POST | `/api/skills/creator/tool` | 2980 |
| 40 | GET | `/api/skills` | 3040 |
| 41 | POST | `/api/skills/requests` | 3218 |
| 42 | GET | `/api/skills/requests/{request_id}` | 3315 |
| 43 | GET | `/api/skills/{skill_id}/runs` | 3363 |
| 44 | GET | `/api/skills/runs/{run_id}/events` | 3387 |
| 45 | GET | `/api/skills/{skill_id}` | 3409 |
| 46 | GET | `/api/skills/{skill_id}/versions` | 3435 |
| 47 | GET | `/api/skills/{skill_id}/examples/{example_id}` | 3488 |
| 48 | GET | `/api/knowledge` | 3550 |
| 49 | GET | `/api/workflows` | 3561 |
| 50 | GET | `/api/ambient` | 3570 |
| 51 | POST | `/api/location` | 3653 |
| 52 | GET | `/api/status/models` | 3695 |
| 53 | GET | `/api/status/services` | 3702 |
| 54 | GET | `/api/status/overview` | 3709 |
| 55 | GET | `/api/status/build` | 3716 |
| 56 | GET | `/api/status/location` | 3723 |
| 57 | GET | `/api/status/logs` | 3730 |
| 58 | GET | `/api/status/catalog` | 3739 |
| 59 | POST | `/api/status/subscription/probe` | 3756 |
| 60 | GET | `/api/status/github` | 3768 |
| 61 | POST | `/api/clipboard/clear` | 3780 |
| 62 | GET | `/api/clipboard` | 3792 |
| 63 | DELETE | `/api/memory/fact/{key}` | 3803 |
| 64 | GET | `/api/memory/reviews` | 3819 |
| 65 | POST | `/api/memory/reviews/{review_id}/resolve` | 3832 |
| 66 | GET | `/api/runs` | 3861 |
| 67 | GET | `/api/runs/{run_id}` | 3878 |
| 68 | POST | `/api/council/convene` | 3893 |
| 69 | GET | `/api/council/job` | 3936 |
| 70 | GET | `/api/council/round/{round_id}` | 3946 |
| 71 | GET | `/api/council/rounds` | 3955 |
| 72 | GET | `/api/graph/{name}` | 3972 |
| 73 | GET | `/api/graph/{name}/image.{fmt}` | 3981 |
| 74 | GET | `/api/council/roster` | 4005 |
| 75 | POST | `/api/plan/start` | 4033 |
| 76 | GET | `/api/plan/job` | 4159 |
| 77 | POST | `/api/plan/choose` | 4191 |
| 78 | POST | `/api/plan/adopt` | 4213 |
| 79 | POST | `/api/plan/cancel` | 4261 |

Three routes deserve a sentence about what an unauthenticated caller could do without the shared middleware: **POST `/api/selfedit/run`** starts an LLM edit loop against Mortimer's own repository; **POST `/api/location`** writes the user's coordinates; **GET `/api/clipboard`** returns whatever was last copied on the Mac, gated only by an in-process armed flag.

### 1.3 The bot's complete route inventory, as served by Pipecat 1.4.0

`jarvis/bot/bot.py:50-53` is the whole entrypoint: `from pipecat.runner.run import main; main()`. `main()` (`pipecat/runner/run.py:1394`) parses `sys.argv`, calls `_configure_server_app(args)` (line 1571), then `uvicorn.run(app, host=args.host, port=args.port)` (line 1573). Defaults: `--host localhost` (`run.py:161, 1433`), `--port 7860` (`run.py:162, 1434`), `-t/--transport` default `None` = **all transports** (`run.py:1441-1445`).

`_configure_server_app` (`run.py:496-537`) does, in order: `app.add_middleware(CORSMiddleware, allow_origins=args.allowed_origins or ["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])` (499-505); registers a `RequestValidationError` handler (511); then calls six setup functions (529-537).

| Setup fn (line) | Route | ASGI scope | Registered in Jarvis's configuration? |
|---|---|---|---|
| `_setup_frontend_routes` (741) | `app.mount("/client", PipecatPrebuiltUI)` (749) | http | **Yes** — `pipecat-ai-prebuilt==1.0.5` is pinned in `requirements-lock.txt:113`, so the import at `run.py:744` succeeds and `/client` is mounted on Larry's machine. (In the plan-authoring sandbox the package is absent, so the module logs an error at 743-747 and returns — but the sandbox is not the target.) |
| " | `GET /` → redirect to `/client/` (751) | http | **Yes** — same, registered whenever the prebuilt UI mounts |
| `_setup_webrtc_routes` (757) | `GET /files/{filename:path}` (776) | http | Yes |
| " | `POST /api/offer` (796) | http | Yes — **this is the WebRTC signalling route the console calls** (`web/src/jarvisClient.ts:17`) |
| " | `PATCH /api/offer` (827) | http | Yes — trickled ICE candidates |
| " | `GET/POST/PUT/PATCH/DELETE /sessions/{session_id}/{path:path}` (834-837) | http | Yes — a Pipecat-Cloud-shaped proxy that forwards to `api/offer` |
| `_setup_daily_routes` (1060) | `GET /daily` (1065) | http | Only if the `daily` extra is installed (guard at 1062-1063) |
| " | `POST /daily-dialin-webhook` (1086) | http | Only if daily deps **and** `args.dialin` (default `True`, 1084) |
| `_setup_telephony_routes` (1199) | `POST /` (1242) | http | Only when `-t twilio|telnyx|plivo|exotel` is passed — Jarvis passes none |
| " | `WS /ws` (1274) | **websocket** | Registered whenever telephony deps resolve |
| " | `WS /ws/{token}` (1279) | **websocket** | Same |
| `_setup_websocket_routes` (455) | `WS /ws-client` (486) | **websocket** | Guarded by `_transport_routes_enabled("websocket")` (467-468) |
| " | `WS /ws-client/{token}` (491) | **websocket** | Same |
| `_setup_unified_start_route` (539) | `GET /status` (552) | http | Yes |
| " | `POST /start` (572) | http | Yes |
| `_setup_whatsapp_routes` (907) | `GET /whatsapp` (941), `POST /whatsapp` (970) | http | Only with `--whatsapp` |

The runner does have a token mechanism of its own — `--ws-auth token` with `_generate_ws_token`/`_verify_and_consume_ws_token` (`run.py:251-315`) — but it is **WebSocket-only, one-time-use, and issued by `POST /start`**, which is itself unauthenticated (`run.py:708-718`). It authenticates nothing that matters here and this plan does not use it.

### 1.4 `jarvis/db.py`'s migration mechanism, as it works today

`jarvis/db.py:3-5` (module docstring): *"Stdlib sqlite3 only. WAL mode, row_factory = sqlite3.Row. Migrations are applied in order and tracked in the `migrations` table; running them twice is a no-op."*

The pattern, verbatim from source:

- Each migration is a module-level string constant named `MIGRATION_00NN` (`jarvis/db.py:17, 48, 64, 78, 98, 131, 174, 235, 253, 314, 324, 340, 376, 396, 422`). Statements are plain SQL separated by `;`, executed with `conn.executescript`.
- A comment block above each constant explains *why*, and specifically states what is and is not backfilled (e.g. `jarvis/db.py:215-234` for 0008, `jarvis/db.py:322-323` for 0011).
- The constant is appended as one `(migration_id, sql)` tuple to `MIGRATIONS: list[tuple[str, str]]` (`jarvis/db.py:794-814`), with the id shaped `NNNN_snake_name` — the newest today is `("0033_skill_events", MIGRATION_0033_skill_events)` at line 813.
- `run_migrations(conn=None)` (`jarvis/db.py:475-499`) creates the `migrations` table if absent, reads applied ids, and for each unapplied tuple runs `conn.executescript(sql)` then `INSERT INTO migrations (id, applied_at)`, committing once at the end. It closes the connection only if it opened it (`own_connection`, 477, 497-499).
- **The whole `MIGRATIONS` list runs in one transaction-less script sequence with a single commit**, which is why the codebase's own rule (comments at `jarvis/db.py:215-217`, `244-247`, `301-303`) is *one plan = one migration*, never two.

`_default_db_path()` (`jarvis/db.py:455-456`) reads `JARVIS_DB_PATH`, default `data/jarvis.db`. `now_iso()` (470-472) is UTC ISO 8601.

CLAUDE.md records that **`jarvis/db.py` migrations are deliberately human-only** with respect to the self-edit loop; that is a statement about `config/self_edit_allowlist.json`, not about this plan's implementer.

### 1.5 Every internal caller of the sidecar or the bot

| Caller | Where | Transport | Process | How it will get a token (§5 Step 6/7) |
|---|---|---|---|---|
| `AdminClient` | `mcp_servers/mcp_selfedit/logic.py:29-44`; base URL from `JARVIS_ADMIN_URL` else `http://127.0.0.1:7861` (19-20, 36) | httpx sync | in-process in the bot (`jarvis/bot/pipeline.py:419-422`) **and** in three MCP children | one `headers=` argument built by `jarvis.auth.service_headers()` |
| `mcp-selfedit` server | `mcp_servers/mcp_selfedit/server.py:21` constructs `logic.AdminClient()` | via `AdminClient` | MCP child | `JARVIS_SERVICE_TOKEN` added to its `skill.yaml` `requires_env` (K2) |
| `mcp-web` server | `mcp_servers/mcp_web/server.py:17-18`; `mcp_servers/mcp_web/logic.py:47` imports `AdminClient, OFFLINE_ERROR` | via `AdminClient` | MCP child | same |
| `mcp-apps` server | `mcp_servers/mcp_apps/server.py:15, 20, 30-33` | via `AdminClient` | MCP child | same |
| `PlanWatcher` | `jarvis/bot/plan_watcher.py:62-66` (`GET {admin_url}/api/plan/job`), url at 87 | httpx async | bot | `service_headers()` in `_default_fetch_job` |
| `ResearchWatcher` | `jarvis/bot/research_watcher.py:44-48` (`GET {admin_url}/api/research/job`), url at 69 | httpx async | bot | same |
| `ProgressWatcher` | `jarvis/bot/progress_watcher.py:156-160` (`GET {admin_url}/api/selfedit/run`), url at 202 | httpx async | bot | same |
| Bot clipboard tools | `jarvis/bot/pipeline.py:413-429` — `_clipboard_call` builds an `AdminClient()` per call | via `AdminClient` | bot | inherited from `AdminClient` |
| `ShellLocation` (Swift) | `macos/MortimerShell/Sources/MortimerShell/ShellLocation.swift:36` — `URL(string: "http://127.0.0.1:7861/api/location")!` | `URLSession` | Mac shell app | new `ShellAuth.swift` reads a Keychain generic-password item (service `com.mortimer.jarviskit`, account = bot URL; CP-F15) (A15) |
| Web console — `RunsPanel` | `web/src/components/RunsPanel.tsx:9, 116, 139` | `fetch` | browser | `localStorage['jarvis_token']` via `web/src/api.ts` (A12) |
| Web console — `EditModePanel` | `web/src/components/EditModePanel.tsx:3, 210, 220, 245, 286, 379, 389, 405, 494, 534` | `fetch` | browser | same |
| Web console — `SystemVitals` | `web/src/components/SystemVitals.tsx:3, 78` | `fetch` | browser | same |
| Web console — `GitPanel` | `web/src/components/GitPanel.tsx:3, 30, 45` | `fetch` | browser | same |
| Web console — `MemoryPanel` | `web/src/components/MemoryPanel.tsx:3, 89, 94, 102, 126, 138` | `fetch` | browser | same |
| Web console — `AmbientStrip` | `web/src/components/AmbientStrip.tsx:4, 117` | `fetch` | browser | same |
| Web console — RTVI connect | `web/src/jarvisClient.ts:17` — `client.connect({ webrtcRequestParams: { endpoint: "http://localhost:7860/api/offer" } })`; transport is `@pipecat-ai/small-webrtc-transport` (`web/package.json`) | Pipecat client-js | browser | `webrtcRequestParams.requestHeaders` **after the field is verified against the transport's `.d.ts`** (F10; `?token=` fallback if absent). Both `POST` and `PATCH /api/offer` (`run.py:796`, `run.py:827`) must carry it (A12) |
| `scripts/spoken_acceptance.py` | `--url` default `http://localhost:7860/api/offer` (search `--url`), offer `POST` (search the offer request) | httpx | dev script | `import os` + new `--token` flag defaulting to `JARVIS_SERVICE_TOKEN` (§5 Step 7, F20) |
| `scripts/mortimer.sh` | prints and (after F6) probes `http://localhost:$ADMIN_PORT/api/health` in `check()` (search `check()`), which now curls health with the token; `sleep 25` > `BIND_WAIT_S` | curl | shell | `check()` sends `Authorization: Bearer $JARVIS_SERVICE_TOKEN` (§5 Step 9, F6) |

### 1.6 Vault and env plumbing that the service token rides on

`jarvis/vault.py:232-233` `get_secret(name)`; `:236` `set_secret(name, value)` (rejects empty values); `:266` `inject_env()` copies every vault secret into `os.environ` where the env var is unset or empty. CLAUDE.md fixes the four `inject_env()` call sites: the top of `load_settings()`, the module top of `jarvis/admin/server.py` (verified at line 101), and guarded imports in `scripts/check_env.py` and `scripts/check_skills.py`. So `JARVIS_SERVICE_TOKEN` reaches `os.environ` in **both** long-lived processes with no new call site.

`scripts/check_skills.py:102-104` errors when a `requires_env` name is unset. Adding `JARVIS_SERVICE_TOKEN` to three manifests makes that script report three errors until the vault holds the value — the same behaviour `GITHUB_TOKEN` already produces on a fresh checkout. `check_skills.py` is **not** in CI (`.github/workflows/validate.yml` runs allowlist → import smoke → `pytest tests/unit` → `web/npm run build`), so nothing breaks; §5 orders the mint before the manifest edit anyway.

### 1.7 The gap, stated plainly

Two processes serve 64 sidecar routes and 16 Pipecat Starlette route entries with no notion of a caller. The only thing standing between an attacker and `POST /api/selfedit/run` is that both processes bind `127.0.0.1`. The moment a tunnel exists — which is the entire point of T2 — that guarantee is gone, and a *device*-authenticating VPN does not restore it, because every app on a joined phone shares the device's identity (roadmap R4). There is no token table, no `Authorization` parsing, no bind configuration, and no startup check.

---

## §2 Non-goals

1. **Multi-tenant accounts, sign-up, billing, rate limiting.** Roadmap §2.2 "Out of scope". The `user_id` column exists from the first migration and is hardcoded to `'larry'` (roadmap §6); nothing reads it in T2.
2. **TLS inside the tunnel.** WireGuard (what Tailscale carries) already provides confidentiality and integrity end to end between two joined devices. Adding `tailscale cert` + an HTTPS listener in T2 would add a certificate lifecycle to maintain for zero threat-model benefit. A16 states the one condition that would change this.
3. **Token expiry / rotation policy / refresh tokens.** A token lives until `revoke`. Rotation is "mint a new name, revoke the old one" (A2). An expiry column would be schema the T2 tests cannot exercise honestly.
4. **Per-route scopes or per-token permissions.** Every valid token can call everything. Roadmap §2.2 does not ask for scopes and inventing them now would fix an authorization model before there is a second principal.
5. **Auditing beyond `last_used_at`.** No per-request log of which client called which route. The existing `_log_5xx_responses` middleware is untouched.
6. **Replacing the web console.** T1 does that. A12 is the smallest change that keeps the console usable: one module, one text field, one toast.
7. **Rewriting `macos/MortimerShell`.** A15 adds one file and three lines. T1 replaces the whole app.
8. **Removing the sidecar's `CORSMiddleware`.** R-A2.
9. **Any Pipecat modification.** §0.4.
10. **The sensitive/financial tier.** C3, and it is T4b.

---

## §3 Decisions — A1…A16

### A1 — Token plaintext is `jvt_` + 43 base64url characters; the server stores only its SHA-256 hex, in `data/jarvis.db` (K1)

`mint_token()` draws `secrets.token_bytes(32)`, base64url-encodes it, strips `=` padding (43 characters for 32 bytes), and prefixes `jvt_`. Total length is exactly **47**. The plaintext is printed once on stdout by `python -m jarvis.auth add` and never written anywhere by Mortimer.

*Why a fixed prefix and a fixed length.* Both are cheap, non-secret discriminators that let `parse_bearer` reject a malformed credential **before any database access** — which is what makes the "valid prefix, wrong length" adversarial case (§7 T-A9) a pure string check rather than a hash lookup, and what keeps a flood of junk headers from becoming a flood of SQLite opens. `jvt_` also makes a leaked token greppable in a log or a paste.

*Why 32 bytes.* 256 bits of entropy from `secrets`. There is no rate limiting (§2.5), so the token must be unguessable on its own merits; 32 bytes is the same size `secrets.token_urlsafe()`'s documentation recommends for security-sensitive values, doubled from its 16-byte default.

*Why SHA-256 and not bcrypt/argon2.* Password hashes are slow deliberately because passwords are low-entropy and human-chosen. This is a 256-bit random value: there is no dictionary, no rainbow table, and no offline attack that a KDF would slow down meaningfully. A slow KDF here would add tens of milliseconds to **every request** including the voice loop's `POST /api/offer`. SHA-256 of a high-entropy secret is the correct primitive, and it is stdlib.

### A2 — `add <name>` refuses any name that already exists, revoked or not; rotation means a new name

`client_tokens.name` is `NOT NULL UNIQUE` (K1). `python -m jarvis.auth add larry-iphone` when a row named `larry-iphone` exists — active *or* revoked — prints `a token named 'larry-iphone' already exists — revoke it first, then add under a new name` to stderr and exits **2**.

*Why not reuse the name after revocation.* The name is the audit label. If `larry-iphone` can be minted twice, `list`'s `created_at`/`last_used_at`/`revoked_at` no longer describe one credential, and "revoke larry-iphone" becomes ambiguous the moment there are two rows. Deterministic rule for the implementer and for Larry: rotation is `add larry-iphone-2` then `revoke larry-iphone`.

### A3 — Migration `0034_client_tokens`, following `jarvis/db.py`'s existing mechanism exactly

One new module-level constant, one new tuple, appended after `("0033_skill_events", MIGRATION_0033_skill_events)` (`jarvis/db.py:813`). One migration for this whole plan, per the codebase's own rule (`jarvis/db.py:215-217`). No backfill and nothing to backfill: an empty `client_tokens` table means "no client may call", which is the correct fail-closed starting state, and A8's bind guard reads exactly that emptiness.

`id INTEGER PRIMARY KEY AUTOINCREMENT` rather than K1's bare `INTEGER PK` — this is the shape every other table in the file uses (`memory_reviews` at `jarvis/db.py:423-424`, `agent_runs` at 132-133) and `INTEGER PRIMARY KEY AUTOINCREMENT` *is* an `INTEGER PRIMARY KEY`. Not a deviation from K1.

### A4 — The sidecar has **zero** exempt routes, `/api/health` included

All 64 routes in §1.2 require `Authorization: Bearer <token>`. There is no `PUBLIC_PATHS` set, no path prefix check, and no loopback exemption (K1: *"Loopback is NOT exempt"*).

*Why `/api/health` is not exempt, when exempting a health check is the usual move.* Three reasons, in order of weight. (a) Roadmap gate G2(a) is literal: *"every sidecar and bot route rejects a missing/invalid token with 401"* — an exemption fails the gate as written. (b) Nothing actually calls it: the only programmatic reference in the repo is `tests/unit/test_admin_api.py:45, 145`, and `scripts/mortimer.sh:102` merely *prints* the URL inside an echo (its `check()` helper tests `kill -0 "$pid"`, never HTTP). `README.md:345` tells a human to browse to it, and a human with a token can. (c) An exempt path is a permanent invitation to grow the set — the second entry is always easier than the first. The cost of no exemption is that `README.md:345`'s troubleshooting line needs a `curl -H` form; §5 Step 11 rewrites it.

*Why there is no static/docs route to consider.* `jarvis/admin/server.py:105` already sets `docs_url=None, redoc_url=None, openapi_url=None`, and the file mounts no `StaticFiles`. The sidecar serves JSON and nothing else.

### A5 — `jarvis/auth.py` is one stdlib-plus-`jarvis.db` module and the single implementation of verification (K1)

Complete source in §5 Step 2. Public surface, member by member:

| Name | Signature | Contract |
|---|---|---|
| `ClientIdentity` | `@dataclass(frozen=True)` with `name: str`, `user_id: str` | Value object put on the ASGI scope. Frozen so a downstream handler cannot mutate it. |
| `TOKEN_PREFIX` | `str = "jvt_"` | |
| `TOKEN_BYTES` | `int = 32` | |
| `TOKEN_LEN` | `int = 47` | `len(TOKEN_PREFIX) + 43` |
| `DEFAULT_USER_ID` | `str = "larry"` | |
| `auth_enabled()` | `() -> bool` | Reads `JARVIS_AUTH_ENABLED`; default `True`; only `"false"` (case-insensitive, stripped) turns it off. **The only read of that name in the codebase.** |
| `mint_token()` | `() -> str` | A1's format. Never touches the DB. |
| `hash_token(token)` | `(str) -> str` | `hashlib.sha256(token.encode("utf-8")).hexdigest()` — 64 lowercase hex chars. |
| `parse_bearer(header_value)` | `(str \| None) -> str \| None` | Returns the token iff the header is exactly two whitespace-separated fields, field 1 lowercases to `bearer`, and field 2 has length `TOKEN_LEN` and starts with `TOKEN_PREFIX`. Otherwise `None`. **No DB access.** |
| `verify_bearer(header_value, conn=None)` | `(str \| None, sqlite3.Connection \| None) -> ClientIdentity \| None` | `None` for missing, malformed, unknown, or revoked. The **read** (a WAL `SELECT`) decides the identity and never blocks on a writer; on success it also attempts a **best-effort, throttled** `last_used_at` write in its own `try/except sqlite3.Error: pass`, so a write lock can never change the verdict (F5). Opens and closes its own connection when `conn is None` (with a short `timeout`); never closes a caller's connection. A lock/timeout on the *read* itself raises `VerifyUnavailable` (the middleware maps it to HTTP **503**, not 401); any other `sqlite3.Error` on the read returns `None` (fail closed). |
| `VerifyUnavailable` | `class(Exception)` | Raised by `verify_bearer` when the verification *read* cannot complete because SQLite was busy/locked. Signals "try again", not "unauthenticated" — the middleware answers 503 with `Retry-After: 1`. |
| `LAST_USED_THROTTLE_S` | `int = 60` | `last_used_at` is rewritten only when the stored value is more than this many seconds old, so the busy voice path does not take a write lock on every request. |
| `count_active_tokens(conn=None)` | `(sqlite3.Connection \| None) -> int` | Rows with `revoked_at IS NULL`. Returns `0` if the table does not exist. |
| `service_headers()` | `() -> dict[str, str]` | `{"Authorization": f"Bearer {tok}"}` when `JARVIS_SERVICE_TOKEN` is set and non-empty, else `{}`. **The only read of that name.** No DB access, so MCP children and the bot share one implementation. |
| `main(argv=None)` | `(list[str] \| None) -> int` | `add` / `list` / `revoke`. Exit codes: `0` success, `2` refusal (duplicate name, unknown name, missing argument). |

*Why `hmac.compare_digest` on already-hashed values.* The comparison is between two SHA-256 hex digests, and a timing leak on a digest of a 256-bit secret is not practically exploitable. It is used anyway because it costs nothing, because a reviewer should not have to reconstruct that argument, and because K1 names it.

*Why the row scan does not `break` on a match.* The loop examines every row so the number of comparisons does not depend on which token was presented. This matters less than the `compare_digest` itself, and it is free at this table size (a handful of rows). Do not "optimize" it into a `WHERE token_hash = ?` lookup: an indexed equality lookup on a *hash* is safe, but it re-opens the timing question for a reviewer and buys microseconds.

*Why there is no `WHERE token_hash = ?` index use even though `0016` creates the index.* The index exists for `count_active_tokens` and for future growth; the verify path is a full scan by design (previous paragraph). The index is harmless.

*`service_headers()` is read once per `AdminClient`, so a rotated service token is process-lifetime (F21).* `AdminClient.__init__` captures `headers=service_headers()` once into a long-lived `httpx.Client`; `mcp_selfedit/server.py:21` and `mcp_apps/server.py:30-33` cache that client for the life of the MCP child, so a rotated `JARVIS_SERVICE_TOKEN` does not take effect there until the registry restarts the child. `jarvis/bot/pipeline.py:413-429` builds a fresh `AdminClient` per clipboard call and *does* pick up a rotated token immediately — an asymmetry the "Rotating the service token" paragraph in §9 states explicitly, with the rule that both long-lived processes must be restarted after a rotation.

*A database lock is a 503, not a 401 (F5).* `verify_bearer` returns a three-state result — identity, `None` (genuinely unauthenticated), or a lock signal — and the middleware maps the lock signal to HTTP 503 with a `Retry-After`, never to 401. See §5 Step 2 for the split between the read (which decides the verdict and never blocks under WAL) and the best-effort `last_used_at` write.

### A6 — One pure-ASGI `BearerAuthMiddleware` in `jarvis/authmw.py`, used by both processes

Complete source in §5 Step 3. It is **not** `BaseHTTPMiddleware` and it is **not** a FastAPI `Depends`.

*Why not per-route `Depends`.* 64 sidecar routes plus 16 measured bot route entries means 80 protected routes, and the failure mode of forgetting one is silent. A middleware is coverage by construction; the test in §7 T-A14 enumerates `app.routes` and proves it.

*Why not `@app.middleware("http")` / `BaseHTTPMiddleware`.* R-A3. Starlette dispatches `BaseHTTPMiddleware` only for `scope["type"] == "http"`. The runner registers four `@app.websocket` routes (`pipecat/runner/run.py:486, 491, 1274, 1279`). A pure-ASGI middleware sees every scope type and is the only shape that covers both.

*Rejection responses.* HTTP: status `401`, `WWW-Authenticate: Bearer realm="jarvis"`, `Content-Type: application/json`, body `{"ok": false, "error": "unauthorized — Authorization: Bearer <token> required"}`. The `{"ok": false, "error": ...}` shape matches what every sidecar endpoint already returns on failure, so `AdminClient._call`'s existing error handling (`mcp_servers/mcp_selfedit/logic.py:47-53`) needs no change. A database lock during verification is **not** an auth failure and returns `503` (F5), not 401 — the console must never tell Larry his token is wrong because SQLite was momentarily busy. WebSocket: `{"type": "websocket.close", "code": 4401}` sent before accept — the 4000–4999 range is application-defined and 4401 is the conventional analogue of HTTP 401. **F14 note:** a close sent *before* `websocket.accept` is a handshake rejection, and uvicorn discards the application close code and answers the HTTP upgrade with `403 Forbidden`. So 4401 is an ASGI-level intent only; the client observes a failed handshake reported as HTTP 403 (indistinguishable from Pipecat's own origin/ws-token rejections, which also close before accept). Keep the 4401 — it is the correct ASGI shape and it is what T-A22 asserts at the ASGI-message level — but do not describe it as a code a client reads.

*The `OPTIONS` pass-through branch.* An HTTP `OPTIONS` request is forwarded without authentication **only when it is a genuine CORS preflight** — that is, only when it carries **both** an `Origin` header and an `Access-Control-Request-Method` header (F16). A bare `OPTIONS` with neither is rejected with the normal 401, so the branch is not a route-enumeration oracle: an unauthenticated caller cannot map which paths exist or which verbs they accept via 405-vs-404 and the `Allow` header. CORS preflight carries no `Authorization` header by specification, so authenticating a real preflight would break every browser call. Whether this branch is *reached at all* depends on middleware ordering (A7): on both processes CORS is now outermost (F1), so `CORSMiddleware` answers a real preflight itself and the branch is unreachable in normal operation — it is kept as defence so that removing `CORSMiddleware` at T1.4 cannot silently break preflight.

*No cache.* `verify_bearer`'s read hits SQLite on every request. A TTL cache would mean a revoked token keeps working for the TTL, which is the one property revocation exists to provide. The cost is one `sqlite3.connect` plus one small `SELECT` — a local WAL read, which never blocks even while another connection holds the write lock (F5), on a table with fewer than ten rows, well under a millisecond, against a workload whose busiest caller is a 3-second poll. The `last_used_at` write is separate, best-effort, and throttled (F5, §5 Step 2) so it can never turn a lock into a wrong auth verdict.

### A7 — `CORSMiddleware` is outermost in **both** processes, so a 401 always carries its CORS headers (F1)

Starlette's `add_middleware` **inserts at index 0** (`starlette/applications.py`: `self.user_middleware.insert(0, Middleware(...))`), so the **last** middleware added is the **outermost**. This plan makes both processes end in the same order: **CORS outermost, `BearerAuthMiddleware` inner.**

*Why this ordering and not the reverse.* If `BearerAuthMiddleware` were outermost, it would generate the 401 *above* `CORSMiddleware`, so the response would carry only `content-type`, `www-authenticate`, and `content-length` — **no `Access-Control-Allow-Origin`**. The console is served by vite on `http://localhost:5173` and calls the sidecar on `:7861`; that is cross-origin, and a cross-origin response with no ACAO is blocked by the browser: `fetch` **rejects with a `TypeError`** rather than resolving with `res.status === 401`. `authFetch` would then never reach its 401 branch, the toast (A12) would never fire, and §8 V3 could never pass. Measured — see §7, the F1 note under `tests/unit/test_auth_middleware.py`: auth-outermost yields `ACAO = None` on the 401; CORS-outermost yields `ACAO = http://localhost:5173`.

- **Sidecar.** `jarvis/admin/server.py` adds `BearerAuthMiddleware` **before** the existing `CORSMiddleware` block (§5 Step 4). Auth is added first, CORS last → **CORS outermost**. The 401 is wrapped by `CORSMiddleware` and carries `Access-Control-Allow-Origin`.
- **Bot.** `jarvis/bot/server.py` adds `BearerAuthMiddleware` *before* calling `main()`, and `main()` → `_configure_server_app` adds `CORSMiddleware` (search `add_middleware(CORSMiddleware` — `run.py:499`). CORS is added later → **CORS outermost** here too, by the same reasoning.

Because CORS is outermost in both, `CORSMiddleware` answers a genuine preflight itself and A6's `OPTIONS` pass-through branch is unreachable in normal operation; it is retained only as defence for when `CORSMiddleware` is deleted at T1.4 (and it is narrowed to genuine preflights per F16 so it is not an enumeration oracle even then). The one middleware behaves identically in both processes and in both orderings the 401 is browser-readable.

### A8 — `jarvis/bind.py` is the single fail-closed bind resolver, exit code 2 on refusal (K1, K5)

Complete source in §5 Step 3. `resolve_bind_host(process: str, conn=None) -> str` implements K1's rule as a decision table with no judgment left:

| `JARVIS_AUTH_ENABLED` | `JARVIS_BIND_HOST` | Unrevoked tokens | Host assigned to an interface | `JARVIS_BIND_STRICT` | Result |
|---|---|---|---|---|---|
| `false` | loopback or unset | — | — | — | `127.0.0.1` |
| `false` | non-loopback | — | — | — | `127.0.0.1`, plus one `ERROR` line `bind_forced_loopback` naming the requested host |
| `true` | loopback or unset | — | — | — | the requested host as given |
| `true` | non-loopback | `0` | — | — | `BindRefused` → caller logs and `SystemExit(2)` — a genuine security condition, never a fallback |
| `true` | non-loopback | `≥ 1` | no, within `BIND_WAIT_S` | `false` (default) | `127.0.0.1`, plus one `ERROR` line `bind_fell_back_to_loopback requested=<host> reason=interface_absent` |
| `true` | non-loopback | `≥ 1` | no, within `BIND_WAIT_S` | `true` | `BindRefused` → `SystemExit(2)` |
| `true` | non-loopback | `≥ 1` | yes | — | the requested host |

`is_loopback(h)` is true for `127.0.0.1`, any `127.` prefix, `::1`, and `localhost` (the runner's own default, `pipecat/runner/run.py:161`). Anything else — including `0.0.0.0` and `::` — is non-loopback and therefore gated.

*Why the interface-absent case falls back to loopback rather than refusing (F8).* The token check is the control that survives a token leak; binding one address is a *second, independent* control. When the requested Tailscale address is simply not present — `tailscaled` down, a logged-out node, an expired key, a Tailscale upgrade in flight, the mini booted where Tailscale cannot reach its coordination server — refusing to start takes down *local* voice too, on the one machine whose assistant is the thing that just died, and the documented recovery would be to hand-edit `.env` on that machine. Falling back to `127.0.0.1` is strictly *narrower* than the requested bind: it loses remote access, not security. So the default (`JARVIS_BIND_STRICT=false`) binds loopback and logs `bind_fell_back_to_loopback` loudly; an operator who genuinely wants the hard refusal sets `JARVIS_BIND_STRICT=true`. The **"no unrevoked token"** row keeps its hard refusal in both modes — that is a real misconfiguration (auth on, remote requested, nobody able to authenticate), not an outage.

*Why an interface-assignment check, and why a wait.* Binding to the Tailscale address (A16) rather than `0.0.0.0` is what keeps the LAN and Wi-Fi interfaces closed. But `tailscaled` may not have assigned `100.x.y.z` yet when Mortimer starts at boot, and `uvicorn` would then die with a bare `OSError: [Errno 49] Can't assign requested address` that says nothing about why. `_host_is_bindable` attempts a throwaway `bind((host, 0))` on an ephemeral port — the exact question, answered with stdlib `socket` and nothing else — and `resolve_bind_host` retries it once a second for `BIND_WAIT_S = 20` before either falling back (default) or refusing (`JARVIS_BIND_STRICT=true`) with a message that names Tailscale. **Invariant (F6):** `scripts/mortimer.sh`'s post-launch `sleep` (25 s) is strictly greater than `BIND_WAIT_S` (20 s), so the script's health probe runs *after* the bind decision has resolved, never during the wait.

*No command-line argument can widen the bind (F7).* `jarvis/bind.py` is the single resolver and it is on the self-edit deny list (A14) so the gate cannot be edited away — but the gate would be pointless if `python -m jarvis.bot.bot --host 0.0.0.0` could bypass it. §5 Step 7's `build_argv` (Branch A) **strips any caller-supplied `--host`/`--port`** (and their `=`-joined forms) from `sys.argv[1:]` before appending the resolved values, and logs an `ERROR` naming each ignored argument; Branch B's `_parse` does the same by resolving host/port itself and never reading them from argv. The resolved, gated host is the only host that can reach `uvicorn.run`. T-A35 proves `build_argv("127.0.0.1", 7860)` with `sys.argv = ["bot.py","--host","0.0.0.0"]` yields a parsed host of `127.0.0.1`.

*Why exit code 2.* K1 says so, and it is already this repo's refusal code (`jarvis/auth.py`'s CLI uses it, and `scripts/mortimer.sh:62` uses 2 for a usage error).

### A9 — `ClientIdentity` is attached to the ASGI scope and read by nothing in T2

`scope["client_identity"] = identity` on success. No handler reads it; no response contains it; no log line names it (the rejection log names the *reason*, not a token or a client). This is the seam T5's per-user digests and the eventual subscription work need, placed now because retrofitting it means touching the middleware again.

*Why put it there at all if nothing reads it.* C1 forbids the backend learning "which client is rendering", and this does not violate that — `ClientIdentity` names a *credential holder*, not a UI. The alternative (add it later) means the middleware is edited under pressure by a plan that also has to change behaviour.

### A10 — Bot integration decision tree: check first, then Branch A or Branch B, else stop

**Check B1 — run this exact command and read its single line of output:**

```bash
cd /path/to/repo && python3 - <<'PY'
try:
    from fastapi import FastAPI
    from pipecat.runner.run import app, main, _configure_server_app
except Exception as exc:
    print("STOP:", type(exc).__name__, exc); raise SystemExit(1)
print("BRANCH A" if isinstance(app, FastAPI) else
      ("BRANCH B" if callable(_configure_server_app) else "STOP: no hook"))
PY
```

- Prints `BRANCH A` → implement §5 Step 7 **Branch A** and delete nothing.
- Prints `BRANCH B` → implement §5 Step 7 **Branch B** verbatim.
- Prints anything starting `STOP:` → **stop and report to Larry**. Do not fork Pipecat, do not vendor `run.py`, do not reimplement `_configure_server_app` (it is ~1,100 lines of transport wiring across six setup functions). Report the exact printed line.

**Verified today, from source, for Pipecat 1.4.0:** Branch A holds. `pipecat/runner/run.py:168` is `app: FastAPI = FastAPI()`, and its docstring (`run.py:169-183`) says exactly what this plan relies on: *"Import this to add custom routes from other packages before calling ``main()``… `from pipecat.runner.run import app, main`"*. `_configure_server_app` exists at line 497 (search `def _configure_server_app`) and takes only `args`, using the module-global `app` for `add_middleware` (search `add_middleware(CORSMiddleware`, run.py:499) and the exception handler (511) and passing it to the six setup functions (529–537). **Re-verified in this revision's sandbox** with `fastapi` installed: importing `pipecat.runner.run` yields an `app` that `isinstance(app, FastAPI)` is `True`, and adding a middleware to it before `main()` takes effect (Starlette builds the stack lazily in `__call__`). The check is still written as a command the implementer runs on a real checkout because a future Pipecat upgrade is what could flip it. The source citations above stand on their own.

*Why the check exists at all if Branch A is verified.* A Pipecat upgrade is the one thing that can flip it, and this plan is read by an implementer who may be working months later against a different version. §7 T-A20 turns the same assertion into a permanently-running test.

### A11 — `jarvis/urls.py` is the one module that knows a default host (K5)

Two names, two defaults, two accessor functions:

```
JARVIS_ADMIN_URL   default http://127.0.0.1:7861   admin_url()
JARVIS_BOT_URL     default http://127.0.0.1:7860   bot_url()
```

`mcp_servers/mcp_selfedit/logic.py:19-20`'s `DEFAULT_ADMIN_URL` and `ADMIN_URL_ENV` become re-exports from `jarvis.urls` so the existing names keep working for `mcp_web`/`mcp_apps` and for the three watchers, which import them today. `jarvis/urls.py` imports only `os` — safe for MCP children and for `mcp_selfedit/logic.py`'s deliberate import-lightness.

*Why not `jarvis/config.py`.* It is pydantic-settings and pulls the whole `Settings` model; `mcp_selfedit/logic.py`'s own comment (line 32) records that keeping that module light is deliberate.

*What K5's "no code names a host" means concretely here.* After §5 Step 8, the only literal hosts left in the repo are: `jarvis/urls.py`'s two defaults, `jarvis/bind.py`'s `LOOPBACK`, `jarvis/config.py:80`'s unread `jarvis_webrtc_endpoint` (R-A4), and `web/src/api.ts`'s two build-time defaults (A12). Every caller in §1.5 goes through one of them.

### A12 — Web console: one `api.ts` module, one text field in the drawer's Dev section, one toast. Nothing else.

The console is being retired at T1.4, so this is scoped to the minimum that keeps it working.

- `web/src/api.ts` (new, ~45 lines, §5 Step 8) exports `ADMIN_BASE`, `BOT_OFFER_URL`, `getToken()`, `setToken(t)`, `authFetch(path, init?)`, and `subscribeAuthError(fn)`. Bases come from `import.meta.env.VITE_JARVIS_ADMIN_URL` / `VITE_JARVIS_BOT_URL` with today's literals as fallbacks. Token comes from `localStorage['jarvis_token']` (K1's key, verbatim).
- Six panels replace `const API = "http://localhost:7861"` with `import { ADMIN_BASE as API, authFetch } from "../api"` and every `fetch(` with `authFetch(`. The 20 call sites are enumerated in §1.5 and again in §5 Step 8.
- **Reverified against the locked package in this implementation:** `web/node_modules/@pipecat-ai/small-webrtc-transport/dist/index.d.ts:100` declares `webrtcRequestParams?: APIRequest`; `web/node_modules/@pipecat-ai/client-js/dist/index.d.ts:899-904` declares `APIRequest.headers?: Headers`. Use `headers: authHeaders()` where `authHeaders()` returns a `Headers` instance. No query-token fallback is needed. Both `POST /api/offer` and trickle-ICE `PATCH /api/offer` use this configured request object and must carry the header; §8 V5c checks both in the network tab.
- **Token entry lives in `AgentsTab.tsx`**, under a heading whose literal text is `Dev`. CLAUDE.md records that the drawer tab formerly called "Developer" is now **Agents** (`AgentsTab.tsx`, tab key `agents`), while K1's required toast copy is the literal string `Token required — Dev tab`. Adding one `<h4>Dev</h4>` above the field makes the copy and the UI agree without changing K1's contract string and without renaming a tab.
- The field is `<input type="password">` with a `Save` button; saving writes `localStorage['jarvis_token']` and reloads nothing. A `Clear` button removes the key. The current value is never rendered back (the input starts empty and shows `••••` placeholder text when a token is stored — literal placeholder: `stored — enter a new token to replace`).
- **One toast, no retry.** `authFetch` publishes an auth error exactly once per page load on the first `401` it sees (`let notified = false`). `App.tsx` subscribes and renders a chip **reusing the existing `speaker-gate-notice` class** (F9) — the class the speaker-gate notice actually uses (`web/src/App.tsx`, `<span className="speaker-gate-notice" role="status">`); there is no `.attn-chip` rule in `web/src`, so the chip must not invent one. It is a `<span role="status">` with the literal text `Token required — Dev tab`, held in `useState` and cleared from a `useEffect` with a `clearTimeout` cleanup (mirroring `App.tsx`'s existing timeout pattern) so a re-fire cannot leak a timer. `authFetch` returns the `Response` unchanged; callers' existing `if (!r.ok)` paths handle the rest. Nothing re-issues the request.

### A13 — Token management is CLI-only: no MCP tool, no sidecar endpoint, no console mutation

There is no `/api/tokens` route and no `mcp_*` tool that mints or revokes. Same rule and same reason as the vault (CLAUDE.md: *"Management is CLI-only… so secrets never transit the LLM or the browser"*). An assistant that can mint its own credential has no credential. `TOTAL_TOOLS` is therefore **unchanged** and no routing-eval fixture entry is added.

### A14 — Three deny-list entries (Larry's commit), reconciled against `docs/plans/ALLOWLIST_SEQUENCE.md`

Add to `config/self_edit_allowlist.json`'s `deny` array:

```json
    "jarvis/auth.py",
    "jarvis/authmw.py",
    "jarvis/bind.py",
```

These are exactly **row W1 of `docs/plans/ALLOWLIST_SEQUENCE.md`** (the SEC-owned reconciled sequence, per `CROSS_PLAN_RESOLUTION.md` §A). Three entries, not two — the earlier draft's heading said "two" while the body listed three (F17); the body was right.

**Why these three and why *not* `jarvis/urls.py` (F17).** None of `jarvis/auth.py`, `jarvis/authmw.py`, or `jarvis/bind.py` matches any *allow* pattern in the file today (the allow list has no `jarvis/**` entry — it is `web/src/**`, `web/public/**`, `config/**`, `jarvis/prompts.py`, `jarvis/skills/**`, `jarvis/services/**`, `mcp_servers/**`, `skills/**`, `tests/**`, `docs/**`, `*.md`). So the deny entry is not closing a currently-open door; it is **insurance against the allow list being widened later** (it has been widened before), which would otherwise let the assistant rewrite its own `verify_bearer` or bind gate. `jarvis/urls.py` matches no allow pattern either — so the earlier draft's distinction between it and the other three was false — but the reconciled sequence in `ALLOWLIST_SEQUENCE.md` does **not** add `urls.py`, and this plan does not cross that shared artifact's boundary. The deny set for W1 is exactly the three above.

**Cross-plan de-duplication (`CROSS_PLAN_RESOLUTION.md` §A).** Larry's arbitration keeps `config/agents.yaml` and `mcp_servers/*/skill.yaml` **editable** (reversing SEC's first-draft D-H9), guarding `requires_env` instead with a frozen snapshot test, `tests/unit/test_requires_env_snapshot.py` (SEC-owned, on the deny list). So this plan neither denies `mcp_servers/*/skill.yaml` nor relies on D-H9 denying it; the frozen snapshot is what stops a self-edit from silently changing which server receives `JARVIS_SERVICE_TOKEN`.

Per C8 the implementing model does **not** make this edit. §5 Step 12 adds a test that *reports* the current state (printing a warning, asserting nothing) so the plan merges before Larry's commit and the report goes quiet after it.

### A15 — The Mac shell reads its token from the Keychain and degrades silently without one

`macos/MortimerShell/Sources/MortimerShell/ShellAuth.swift` (new, §5 Step 10) exposes `ShellAuth.bearer: String?` — a cached `SecItemCopyMatching` lookup for a generic-password item — and `ShellAuth.adminBaseURL: URL`, read from `UserDefaults.standard.string(forKey: "JARVIS_ADMIN_URL")` with `http://127.0.0.1:7861` as the fallback (K5).

**Keychain convention (K1, CP-F15) — one convention for the K1 bearer token, shared with NATIVE.** The generic-password item is:

- `kSecAttrService = "com.mortimer.jarviskit"`
- `kSecAttrAccount = "<scheme>://<host>:<port>"` — the bot URL, e.g. `http://127.0.0.1:7860` on loopback or `http://100.x.y.z:7860` remote.

Keying the account to the endpoint means moving to the mini (a new bot URL) creates a **new** Keychain entry rather than silently reusing a stale token for a different host. `MORTIMER_NATIVE_CLIENT_CORE_PLAN.md`'s `KeychainStore` reads and writes the **same** item (`CROSS_PLAN_RESOLUTION.md` §C F15), so the shell and JarvisKit never disagree about where the token lives. `ShellAuth.bearer` derives the account string from `ShellAuth.adminBaseURL` with the admin scheme/host and the **bot** port (default `7860`), so a single `security add-generic-password` (V6) provisions both readers.

`ShellLocation.swift` changes two things: the hardcoded URL at line 36 becomes `ShellAuth.adminBaseURL.appendingPathComponent("api/location")`, and the request gains `req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")`. **If `ShellAuth.bearer` is nil, the POST is skipped entirely with one `logger.notice` line and no request is made** — location reporting is already best-effort by that file's own design (its header comment: *"a build missing the entitlement degrades instead of breaking"*), and a 401 loop from a background location callback is worse than no location.

`macos/**` is on the self-edit deny list, so this is a human-reviewed edit either way. §8 V6 is the `security add-generic-password` command Larry runs.

### A16 — Tailscale, bound to the tailnet address specifically, with `funnel` named as forbidden

Roadmap R5 / §7 O4 default. Larry's exact steps are §8 V4. Three decisions inside it:

- **Bind `JARVIS_BIND_HOST` to the tailnet IPv4 address (`100.x.y.z`), never `0.0.0.0`.** `0.0.0.0` also opens the LAN and any Wi-Fi the machine joins — a coffee-shop network becomes a listener. Binding one address is a second, independent control alongside the token, and it is the one that survives a token leak.
- **Never run `tailscale funnel` or `tailscale serve --funnel`.** Funnel publishes the service on the public internet through Tailscale's edge, which is precisely the exposure R5 exists to avoid (roadmap §7 O4 rejects "Cloudflare/other (public edge)" for the same reason). `tailscale serve` without `--funnel` is tailnet-only and harmless but unnecessary.
- **No TLS inside the tunnel** (§2.2). Media is a separate matter and an honest one: `aiortc` gathers ICE host candidates on every interface, so audio between two devices that are also on the same LAN may take the LAN path rather than the tunnel. That is not a leak — DTLS-SRTP keys are exchanged through the `POST /api/offer` signalling channel, which this plan authenticates and which travels the tunnel — but it is worth knowing before reading a packet capture and concluding something is wrong.

---

## §4 Files (create / modify / delete — complete manifest)

Every file touched by §5 appears here. Nothing else is touched.

### Create (12)

| Path | What it is | Step |
|---|---|---|
| `jarvis/auth.py` | `ClientIdentity`, `auth_enabled`, `mint_token`, `hash_token`, `parse_bearer`, `verify_bearer`, `count_active_tokens`, `service_headers`, the `add`/`list`/`revoke` CLI | 2 |
| `jarvis/authmw.py` | `BearerAuthMiddleware` (pure ASGI, http + websocket) | 3 |
| `jarvis/bind.py` | `BindRefused`, `is_loopback`, `_host_is_bindable`, `resolve_bind_host`, `resolve_port`, `BIND_WAIT_S` | 3 |
| `jarvis/urls.py` | `admin_url()`, `bot_url()`, the two env names and two defaults (K5) | 8 |
| `jarvis/bot/server.py` | The bot entrypoint that installs the middleware and the bind host before `pipecat.runner.run.main()` | 7 |
| `web/src/api.ts` | `ADMIN_BASE`, `BOT_OFFER_URL`, `getToken`, `setToken`, `authFetch`, `subscribeAuthError` | 8 |
| `macos/MortimerShell/Sources/MortimerShell/ShellAuth.swift` | Keychain token lookup + admin base URL | 10 |
| `tests/unit/test_auth.py` | Token format, hashing, `parse_bearer`, `verify_bearer`, CLI | 2 |
| `tests/unit/test_auth_middleware.py` | All 79 sidecar routes, loopback, kill switch, preflight, websocket scope | 5 |
| `tests/unit/test_bind.py` | The A8 decision table, exit code 2, the interface wait | 3 |
| `tests/unit/test_bot_server.py` | Branch-A assertion, bot route inventory, middleware registration | 7 |
| `tests/unit/test_service_token.py` | `service_headers`, `AdminClient`, the three watchers, the three manifests | 6 |

### Modify (27)

| Path | Change | Step |
|---|---|---|
| `jarvis/db.py` | `MIGRATION_0034` constant + comment block; one tuple appended to `MIGRATIONS` | 1 |
| `jarvis/admin/server.py` | `BearerAuthMiddleware` added **before** CORS block (F1); `Authorization` added to CORS `allow_headers` + `DELETE` to `allow_methods`; `main()` startup guard for missing service token (Step 0), then `resolve_bind_host`/`resolve_port`, exits 2 on refusal | 0, 4, 9 |
| `jarvis/bot/bot.py` | `__main__` block calls `jarvis.bot.server.main()` instead of `pipecat.runner.run.main()`; docstring URL updated | 7 |
| `jarvis/bot/plan_watcher.py` | `service_headers()` on the httpx GET | 6 |
| `jarvis/bot/research_watcher.py` | same | 6 |
| `jarvis/bot/progress_watcher.py` | same | 6 |
| `mcp_servers/mcp_selfedit/logic.py` | `AdminClient.__init__` passes `headers=service_headers()`; `DEFAULT_ADMIN_URL`/`ADMIN_URL_ENV` re-exported from `jarvis.urls` | 6, 8 |
| `mcp_servers/mcp_selfedit/skill.yaml` | `JARVIS_SERVICE_TOKEN` **appended** to `requires_env` (see §5 Step 6d; do **not** replace the list — that would delete SEC's `JARVIS_UPGRADE_PROFILE`, CP-F4) | 6 |
| `mcp_servers/mcp_web/skill.yaml` | `JARVIS_SERVICE_TOKEN` **appended** to `requires_env` (keeps `TAVILY_API_KEY`, F2) | 6 |
| `mcp_servers/mcp_apps/skill.yaml` | `JARVIS_SERVICE_TOKEN` **appended** to `requires_env` (keeps `GITHUB_TOKEN`) | 6 |
| `tests/conftest.py` | autouse fixture defaulting `JARVIS_AUTH_ENABLED=false` for the suite | 5 |
| `web/src/components/RunsPanel.tsx` | `api.ts` import; 2 `fetch` → `authFetch` | 8 |
| `web/src/components/EditModePanel.tsx` | `api.ts` import; 9 `fetch` → `authFetch` | 8 |
| `web/src/components/SystemVitals.tsx` | `api.ts` import; 1 `fetch` → `authFetch` | 8 |
| `web/src/components/GitPanel.tsx` | `api.ts` import; 2 `fetch` → `authFetch` | 8 |
| `web/src/components/MemoryPanel.tsx` | `api.ts` import; 5 `fetch` → `authFetch` | 8 |
| `web/src/components/AmbientStrip.tsx` | `api.ts` import; 1 `fetch` → `authFetch` | 8 |
| `web/src/components/AgentsTab.tsx` | The `Dev` heading + token field | 8 |
| `web/src/App.tsx` | `subscribeAuthError` → the existing chip | 8 |
| `web/src/jarvisClient.ts` | `requestHeaders` with the bearer token; endpoint from `api.ts` | 8 |
| `macos/MortimerShell/Sources/MortimerShell/ShellLocation.swift` | base URL from `ShellAuth`; `Authorization` header; skip when nil | 10 |
| `scripts/spoken_acceptance.py` | `import os`; `--token` flag defaulting to `JARVIS_SERVICE_TOKEN`; header on the offer POST | 7 |
| `scripts/mortimer.sh` | `ADMIN_PORT` reads `JARVIS_ADMIN_PORT`; `sleep 4`→`sleep 25` (> `BIND_WAIT_S`); `check()` probes health with the token (F6, F12) | 9 |
| `tests/unit/test_db.py` | `test_client_tokens_table_shape` (F12) | 1 |
| `.env.example` | Remote-access documentation block (F19: all four `JARVIS_*_URL`/`JARVIS_*_PORT` names + `JARVIS_BIND_STRICT`) | 11 |
| `README.md` | troubleshooting curl (anchor on `./scripts/mortimer.sh`, not a line number); a "Remote access" section | 11 |
| `CLAUDE.md` | One paragraph under Architecture describing K1/K5 | 11 |

*(The manifest is by **path**, not by edit: `jarvis/admin/server.py` carries three steps (0, 4, 9) in one row, and `mcp_servers/mcp_selfedit/logic.py` carries two (6 and 8). **27 rows, 27 distinct paths.** `docs/plans/MORTIMER_PLATFORM_ROADMAP.md` is deliberately NOT in this manifest: the roadmap is a shared artifact edited only by the SEC track (`CROSS_PLAN_RESOLUTION.md` §C F14), which folds in this plan's R-A1…R-A4 correction pointer; this plan cites the roadmap but never edits it.)*

### Delete (0)

Nothing is deleted. `web/` deletion is T1.4's, gated on G1(e).

### Larry's own commit (1)

| Path | Change | Where |
|---|---|---|
| `config/self_edit_allowlist.json` | three `deny` entries (A14) | §8 V8 |

---

## §5 Implementation steps, in order

Step 0 is Larry's and runs **before any code lands**. Steps 1–8 and 10–12 change **no** bind host and open **nothing**. Step 9 is the only step that can expose a port, and it is last on purpose (C2).

### Step 0 — mint and store the service token BEFORE the code merges (F11, Larry's action)

`JARVIS_AUTH_ENABLED` defaults to `true`. The moment this plan's code is running, every internal caller (the three watchers, `mcp-selfedit`/`mcp-web`/`mcp-apps`, the bot's clipboard tools) sends `service_headers()` — which returns `{}`, i.e. **no auth header**, until `JARVIS_SERVICE_TOKEN` is in the vault. So the window between merge and this step is not a *risk*, it is a guaranteed self-401 of the whole internal surface. The mint therefore comes first, run once on Larry's machine (also the migration must already exist — `python -m jarvis.auth add` calls `run_migrations` itself, so on a machine that has pulled this branch the table is created on first use):

```bash
cd ~/jarvis-voice-ai-clean
python scripts/init_db.py                        # applies 0034_client_tokens
python -m jarvis.auth add service-bot            # prints the jvt_… plaintext ONCE
python -m jarvis.vault set JARVIS_SERVICE_TOKEN  # paste it; value is prompted, never argv
```

`inject_env()` then places it in `os.environ` in both long-lived processes with no new call site (§1.6). This is the same commands as §8 V1; it is stated here so the ordering is unmistakable — **mint before merge**, never after.

**Startup guard (both processes).** In `jarvis/admin/server.py:main()` and `jarvis/bot/server.py:main()`, before the bind resolves, add one guard:

```python
from jarvis.auth import auth_enabled, service_headers
if auth_enabled() and not service_headers():
    logger.error(
        "service_token_missing: JARVIS_AUTH_ENABLED is true but "
        "JARVIS_SERVICE_TOKEN is unset — internal callers will 401. "
        "Run `python -m jarvis.auth add service-bot` then "
        "`python -m jarvis.vault set JARVIS_SERVICE_TOKEN`."
    )
```

It logs and continues (it does not exit): a missing service token is a degraded state, not a reason to refuse to start, and `JARVIS_AUTH_ENABLED=false` is a legitimate way to run with no token at all.

### Step 1 — migration `0034_client_tokens`

**File:** `jarvis/db.py`. (CP-F1 guard: first confirm `grep -c 0034 jarvis/db.py` is 0 — REMOTE owns `0034_client_tokens`; if a different `0034_*` is already present, stop and report, the wave order was violated.)

Insert the constant immediately after the closing `"""` of the newest migration constant (search for `MIGRATION_0033_skill_events = """` and place it after that string's closing `"""`), before the `MIGRATIONS: list[tuple[str, str]] = [` list:

```python
# K1 (MORTIMER_REMOTE_ACCESS_PLAN.md A1/A3): per-client bearer tokens.
# Only the SHA-256 hex of a token is stored — the plaintext is printed
# once by `python -m jarvis.auth add` and never persisted, so a database
# copy grants nobody access. name is UNIQUE because it is the audit label
# revocation names (A2: a name is never reused, revoked or not).
# user_id exists from the first migration per roadmap §6 (the
# subscription seam) and is hardcoded to 'larry' in this release; nothing
# reads it in T2.
# Nothing is backfilled and nothing can be: an empty table means "no
# client may call", which is the correct fail-closed starting state and
# is exactly what jarvis/bind.py's startup check reads.
# The index serves count_active_tokens(); verify_bearer() deliberately
# scans (A5) so its cost does not depend on which token was presented.
MIGRATION_0034 = """
CREATE TABLE IF NOT EXISTS client_tokens (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL DEFAULT 'larry',
  name TEXT NOT NULL UNIQUE,
  token_hash TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL,
  last_used_at TEXT,
  revoked_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_client_tokens_revoked
  ON client_tokens(revoked_at);
"""
```

Then **append one tuple after the last tuple in the `MIGRATIONS` list** (locate it by searching for the newest `(".._..", MIGRATION_..)` line — today `("0033_skill_events", MIGRATION_0033_skill_events),` — and add the new tuple immediately after it; do not target an absolute line number, since sibling plans in this wave also append here):

```python
    ("0034_client_tokens", MIGRATION_0034),
```

**Test that proves it** — `tests/unit/test_db.py`, add:

```python
def test_client_tokens_table_shape(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "t.db"))
    from jarvis.db import get_conn, run_migrations
    applied = run_migrations()
    assert "0034_client_tokens" in applied
    conn = get_conn()
    cols = {r["name"]: r for r in conn.execute("PRAGMA table_info(client_tokens)")}
    assert set(cols) == {"id", "user_id", "name", "token_hash",
                         "created_at", "last_used_at", "revoked_at"}
    assert cols["user_id"]["notnull"] == 1 and cols["user_id"]["dflt_value"] == "'larry'"
    assert cols["name"]["notnull"] == 1
    assert cols["token_hash"]["notnull"] == 1
    assert cols["created_at"]["notnull"] == 1
    assert cols["last_used_at"]["notnull"] == 0
    assert cols["revoked_at"]["notnull"] == 0
    idx = {r["name"] for r in conn.execute("PRAGMA index_list(client_tokens)")}
    assert any("name" in i or "token_hash" in i or "revoked" in i for i in idx)
    assert run_migrations() == []          # idempotent
    conn.close()
```

### Step 2 — `jarvis/auth.py`, complete

**File:** `jarvis/auth.py` (new). This is the whole file; write it as given.

```python
"""Client bearer tokens (K1) — mint, hash, verify, revoke.

Introduced by docs/plans/MORTIMER_REMOTE_ACCESS_PLAN.md §3 A1-A5, A13.

Imports: stdlib plus jarvis.db (which is itself stdlib-only). This module
is imported by the admin sidecar, by the bot's ASGI middleware, by three
MCP child processes, and by a CLI — one heavy import here lands in all
four, so there are none.

WHAT IS STORED. Only sha256(plaintext) hex. The plaintext is printed once
by `add` and never written by Mortimer to any file, log, or database. A
copy of data/jarvis.db therefore grants nobody access.

WHAT IS NOT HERE. There is no MCP tool and no HTTP endpoint that mints or
revokes (A13) — same rule and same reason as jarvis/vault.py: an
assistant that can mint its own credential has no credential.
"""

from __future__ import annotations

import argparse
import base64
import datetime as _dt
import hashlib
import hmac
import os
import secrets
import sqlite3
import sys
from dataclasses import dataclass

from jarvis.db import get_conn, now_iso, run_migrations

TOKEN_PREFIX = "jvt_"
TOKEN_BYTES = 32
# base64url of 32 bytes is 44 chars with padding, 43 without. A1 strips it.
TOKEN_BODY_LEN = 43
TOKEN_LEN = len(TOKEN_PREFIX) + TOKEN_BODY_LEN  # 47
DEFAULT_USER_ID = "larry"

ENABLED_ENV = "JARVIS_AUTH_ENABLED"
SERVICE_TOKEN_ENV = "JARVIS_SERVICE_TOKEN"

# F5: a busy database is not an auth decision. The verification READ is a
# WAL SELECT that does not block on a writer, but a checkpoint (or another
# process holding an exclusive lock) can still make it briefly unavailable;
# a short busy_timeout makes that fail fast instead of stalling the event
# loop, and the middleware answers 503 rather than 401.
VERIFY_BUSY_TIMEOUT_MS = 250
# last_used_at is bookkeeping, not correctness: only rewrite it when the
# stored value is older than this, so the busy voice path does not take a
# write lock on every request.
LAST_USED_THROTTLE_S = 60


class VerifyUnavailable(Exception):
    """Raised by verify_bearer when the verification READ cannot complete
    because SQLite was busy/locked. Means 'retry', not 'unauthenticated' —
    the middleware maps it to HTTP 503, never 401 (F5)."""


@dataclass(frozen=True)
class ClientIdentity:
    """Who presented a valid token. Frozen: a downstream handler must not
    be able to edit the identity it was handed (A9)."""

    name: str
    user_id: str


def auth_enabled() -> bool:
    """JARVIS_AUTH_ENABLED, default true.

    THE ONLY READ OF THIS NAME IN THE CODEBASE (roadmap kill-switch rule).
    Only the exact string "false" (case-insensitive, stripped) turns it
    off; a typo like "0" or "no" leaves auth ON, which is the safe
    direction for a switch whose off position also forces a loopback bind
    (jarvis/bind.py).
    """
    return os.environ.get(ENABLED_ENV, "true").strip().lower() != "false"


def service_headers() -> dict[str, str]:
    """Authorization header for Mortimer's own internal callers (K1).

    THE ONLY READ OF JARVIS_SERVICE_TOKEN. Returns {} when unset or empty
    so a caller can always splat it into httpx's headers= without a
    branch, and so a stack running with JARVIS_AUTH_ENABLED=false behaves
    exactly as it did before this plan.

    No database access: MCP children call this and must not need
    data/jarvis.db to build a header.
    """
    token = (os.environ.get(SERVICE_TOKEN_ENV) or "").strip()
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


def mint_token() -> str:
    """A1: 'jvt_' + base64url(32 random bytes), padding stripped."""
    raw = secrets.token_bytes(TOKEN_BYTES)
    body = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    return TOKEN_PREFIX + body


def hash_token(token: str) -> str:
    """sha256 hex of the plaintext. 64 lowercase hex characters."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def parse_bearer(header_value: str | None) -> str | None:
    """Extract a syntactically valid token from an Authorization header.

    Returns None — never raises — for every malformed shape. NO DATABASE
    ACCESS HAPPENS HERE: a flood of junk headers costs string comparisons,
    not SQLite opens.

    Accepted: exactly two whitespace-separated fields, field one equal to
    "bearer" case-insensitively (RFC 7235 makes the scheme
    case-insensitive), field two of length TOKEN_LEN and starting with
    TOKEN_PREFIX.

    Rejected, each returning None: None, "", "   ", a bare token with no
    scheme, "Basic <tok>", "Token <tok>", "Bearer" alone, "Bearer a b",
    and a well-prefixed token of the wrong length.
    """
    if not header_value:
        return None
    parts = header_value.split()
    if len(parts) != 2:
        return None
    scheme, token = parts
    if scheme.lower() != "bearer":
        return None
    if len(token) != TOKEN_LEN:
        return None
    if not token.startswith(TOKEN_PREFIX):
        return None
    return token


def _touch_last_used(
    conn: sqlite3.Connection, row_id: int, last_used_at: str | None
) -> None:
    """Best-effort, throttled last_used_at write (F5). A lock here can
    NEVER change the auth verdict — the caller already decided the identity
    from the read. Any sqlite error (including a busy timeout on the write
    lock) is swallowed; the worst outcome is a slightly stale last_used_at.
    """
    now = now_iso()
    if last_used_at is not None:
        try:
            # Skip the write if the stored value is fresh enough.
            prev = _dt.datetime.fromisoformat(last_used_at)
            age = (_dt.datetime.now(_dt.timezone.utc) - prev).total_seconds()
            if age < LAST_USED_THROTTLE_S:
                return
        except (ValueError, TypeError):
            pass  # unparseable stored value: fall through and rewrite it
    try:
        conn.execute(
            "UPDATE client_tokens SET last_used_at = ? WHERE id = ?",
            (now, row_id),
        )
        conn.commit()
    except sqlite3.Error:
        return  # bookkeeping only — never fail a request over this


def verify_bearer(
    header_value: str | None, conn: sqlite3.Connection | None = None
) -> ClientIdentity | None:
    """K1's single verification helper.

    Returns None for missing, malformed, unknown, or revoked tokens. The
    VERDICT is decided entirely by a WAL SELECT, which does not block on a
    writer; on success it also does a best-effort, throttled last_used_at
    write whose success or failure cannot change the verdict (F5).

    Raises VerifyUnavailable if the verification READ itself cannot
    complete because the database was busy/locked (the middleware maps that
    to HTTP 503, not 401). Any other sqlite error on the read returns None
    (fail closed — a corrupt database must not become an open door).

    Connection ownership: opens and closes its own connection when conn is
    None; never closes a connection it was handed.

    The row loop deliberately does not break on a match, so the number of
    comparisons does not depend on which token was presented. Do not
    replace it with `WHERE token_hash = ?` (A5).
    """
    token = parse_bearer(header_value)
    if token is None:
        return None
    own_connection = conn is None
    conn = conn or get_conn()
    try:
        # Fail fast instead of stalling the event loop if the db is busy.
        conn.execute(f"PRAGMA busy_timeout = {VERIFY_BUSY_TIMEOUT_MS}")
        digest = hash_token(token)
        match: sqlite3.Row | None = None
        try:
            rows = list(
                conn.execute(
                    "SELECT id, name, user_id, token_hash, revoked_at, "
                    "last_used_at FROM client_tokens"
                )
            )
        except sqlite3.OperationalError as exc:
            # "database is locked"/"database is busy" on the READ — not an
            # auth decision. Signal retry.
            raise VerifyUnavailable(str(exc)) from exc
        for row in rows:
            if hmac.compare_digest(row["token_hash"], digest):
                match = row
        if match is None or match["revoked_at"] is not None:
            return None
        _touch_last_used(conn, match["id"], match["last_used_at"])
        return ClientIdentity(name=match["name"], user_id=match["user_id"])
    except sqlite3.Error:
        return None
    finally:
        if own_connection:
            conn.close()


def count_active_tokens(conn: sqlite3.Connection | None = None) -> int:
    """Unrevoked rows. 0 when the table does not exist yet — a database
    that has never been migrated must read as 'no tokens', which is what
    jarvis/bind.py needs to refuse a non-loopback bind."""
    own_connection = conn is None
    conn = conn or get_conn()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM client_tokens WHERE revoked_at IS NULL"
        ).fetchone()
        return int(row["n"])
    except sqlite3.Error:
        return 0
    finally:
        if own_connection:
            conn.close()


# --------------------------------------------------------------------- CLI


def _cmd_add(name: str) -> int:
    name = name.strip()
    if not name:
        print("usage: python -m jarvis.auth add <name>", file=sys.stderr)
        return 2
    conn = get_conn()
    try:
        run_migrations(conn)
        token = mint_token()
        try:
            conn.execute(
                "INSERT INTO client_tokens (user_id, name, token_hash, created_at) "
                "VALUES (?, ?, ?, ?)",
                (DEFAULT_USER_ID, name, hash_token(token), now_iso()),
            )
        except sqlite3.IntegrityError:
            # A2: a name is never reused, revoked or not.
            print(
                f"a token named {name!r} already exists — revoke it first, "
                f"then add under a new name",
                file=sys.stderr,
            )
            return 2
        conn.commit()
    finally:
        conn.close()
    # The plaintext goes to stdout ALONE so `TOKEN=$(python -m jarvis.auth
    # add x)` works; everything else goes to stderr.
    print(token)
    print(
        f"# minted {name!r}. This is shown ONCE and is not stored — "
        f"copy it now.",
        file=sys.stderr,
    )
    return 0


def _cmd_list() -> int:
    conn = get_conn()
    try:
        run_migrations(conn)
        rows = list(
            conn.execute(
                "SELECT name, user_id, created_at, last_used_at, revoked_at "
                "FROM client_tokens ORDER BY id"
            )
        )
    finally:
        conn.close()
    if not rows:
        print("no client tokens — mint one with `python -m jarvis.auth add <name>`")
        return 0
    # token_hash is deliberately NOT selected and never printed.
    print(f"{'NAME':<24} {'USER':<10} {'CREATED':<28} {'LAST USED':<28} STATUS")
    for r in rows:
        status = "revoked" if r["revoked_at"] else "active"
        print(
            f"{r['name']:<24} {r['user_id']:<10} {r['created_at']:<28} "
            f"{(r['last_used_at'] or '-'):<28} {status}"
        )
    return 0


def _cmd_revoke(name: str) -> int:
    name = name.strip()
    if not name:
        print("usage: python -m jarvis.auth revoke <name>", file=sys.stderr)
        return 2
    conn = get_conn()
    try:
        run_migrations(conn)
        cur = conn.execute(
            "UPDATE client_tokens SET revoked_at = ? "
            "WHERE name = ? AND revoked_at IS NULL",
            (now_iso(), name),
        )
        conn.commit()
        changed = cur.rowcount
    finally:
        conn.close()
    if changed == 0:
        print(f"no active token named {name!r}", file=sys.stderr)
        return 2
    print(f"revoked {name}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m jarvis.auth",
        description="Client bearer tokens for the Mortimer sidecar and bot.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_add = sub.add_parser("add", help="mint a token (shown once)")
    p_add.add_argument("name")
    sub.add_parser("list", help="list tokens (never prints a hash)")
    p_rev = sub.add_parser("revoke", help="revoke a token by name")
    p_rev.add_argument("name")
    args = parser.parse_args(argv)
    if args.cmd == "add":
        return _cmd_add(args.name)
    if args.cmd == "list":
        return _cmd_list()
    return _cmd_revoke(args.name)


if __name__ == "__main__":
    raise SystemExit(main())
```

**Tests that prove it:** `tests/unit/test_auth.py`, T-A1 … T-A13 in §7.

### Step 3 — `jarvis/authmw.py` and `jarvis/bind.py`, complete

**File:** `jarvis/authmw.py` (new).

```python
"""One ASGI middleware, shared by the admin sidecar and the bot (K1, A6).

WHY PURE ASGI AND NOT BaseHTTPMiddleware. Starlette dispatches
BaseHTTPMiddleware — which is what `@app.middleware("http")` produces —
only for scope["type"] == "http". The Pipecat runner registers four
WebSocket routes (pipecat/runner/run.py:486, 491, 1274, 1279). A
middleware that cannot see a websocket scope would leave those four
unauthenticated. This class inspects scope["type"] itself.

WHY NOT PER-ROUTE Depends. 64 sidecar routes plus 16 measured bot route entries,
where forgetting one fails silently. Middleware is coverage by
construction; tests/unit/test_auth_middleware.py enumerates app.routes and
proves it.

ORDERING. Starlette's add_middleware inserts at index 0, so the LAST
middleware added is the OUTERMOST. On the sidecar this class is added
after CORSMiddleware and is therefore outermost (so the OPTIONS branch
below is reached); on the bot it is added before the runner adds CORS and
is therefore inner (so the OPTIONS branch is unreachable there). Both are
correct — see the plan's A7.
"""

from __future__ import annotations

import json
import logging

from jarvis.auth import VerifyUnavailable, auth_enabled, verify_bearer

logger = logging.getLogger(__name__)

UNAUTHORIZED_BODY = json.dumps(
    {
        "ok": False,
        "error": "unauthorized - Authorization: Bearer <token> required",
    }
).encode("utf-8")

# F5: a database lock during verification is not an auth failure.
UNAVAILABLE_BODY = json.dumps(
    {"ok": False, "error": "service unavailable - verification backend busy"}
).encode("utf-8")

# 4000-4999 is the application-defined WebSocket close range; 4401 is the
# conventional analogue of HTTP 401. F14 NOTE: a close sent before accept is
# a handshake rejection, and uvicorn surfaces it to the client as HTTP 403 —
# 4401 is an ASGI-level intent only, asserted by T-A22 at the message level,
# never something the client reads.
WS_CLOSE_UNAUTHORIZED = 4401
WS_CLOSE_UNAVAILABLE = 4503


def _header(scope, name: bytes) -> str | None:
    for key, value in scope.get("headers", []):
        if key.lower() == name:
            return value.decode("latin-1")
    return None


async def _send_http(scope, send, status: int, body: bytes, extra_headers=()) -> None:
    headers = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(body)).encode("ascii")),
        *extra_headers,
    ]
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


async def _reject(scope, send) -> None:
    if scope["type"] == "websocket":
        await send({"type": "websocket.close", "code": WS_CLOSE_UNAUTHORIZED})
        return
    await _send_http(
        scope, send, 401, UNAUTHORIZED_BODY,
        extra_headers=[(b"www-authenticate", b'Bearer realm="jarvis"')],
    )


async def _unavailable(scope, send) -> None:
    if scope["type"] == "websocket":
        await send({"type": "websocket.close", "code": WS_CLOSE_UNAVAILABLE})
        return
    await _send_http(
        scope, send, 503, UNAVAILABLE_BODY, extra_headers=[(b"retry-after", b"1")]
    )


class BearerAuthMiddleware:
    """Rejects every http and websocket request without a valid token."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            # "lifespan" and anything future. Never authenticated; there
            # is no caller.
            await self.app(scope, receive, send)
            return

        if not auth_enabled():
            await self.app(scope, receive, send)
            return

        if (
            scope["type"] == "http"
            and scope.get("method") == "OPTIONS"
            and _header(scope, b"origin") is not None
            and _header(scope, b"access-control-request-method") is not None
        ):
            # A GENUINE CORS preflight (both Origin and
            # Access-Control-Request-Method present) carries no
            # Authorization header by specification, so let it through to
            # CORSMiddleware. F16: a bare OPTIONS with neither header is NOT
            # a preflight and is authenticated like any other request, so
            # this branch is not a route-enumeration oracle (no 405/Allow
            # leak without a token). With CORS outermost (A7) this branch is
            # normally unreachable; it is retained as defence for T1.4.
            await self.app(scope, receive, send)
            return

        header = _header(scope, b"authorization")
        try:
            identity = verify_bearer(header)
        except VerifyUnavailable:
            # F5: the database was busy — a retryable condition, not an auth
            # decision. 503, never 401.
            logger.warning(
                "auth_unavailable type=%s path=%s",
                scope["type"],
                scope.get("path", ""),
            )
            await _unavailable(scope, send)
            return
        if identity is None:
            logger.warning(
                "auth_rejected type=%s path=%s reason=%s",
                scope["type"],
                scope.get("path", ""),
                "missing" if not header else "invalid",
            )
            await _reject(scope, send)
            return

        # A9: the seam later plans need. Nothing reads it in T2. The token
        # itself is never placed on the scope.
        scope["client_identity"] = identity
        await self.app(scope, receive, send)
```

**File:** `jarvis/bind.py` (new).

```python
"""Fail-closed bind-host resolution for the sidecar and the bot (K1, K5, A8).

One implementation, two callers. THE ONLY READ OF JARVIS_BIND_HOST.

The rule, from K1: a non-loopback bind requires BOTH
JARVIS_AUTH_ENABLED=true AND at least one unrevoked client token. When
JARVIS_AUTH_ENABLED is false the bind host is FORCED to loopback
regardless of what was asked for — the kill switch that turns off
authentication must never be the switch that also opens a port.
"""

from __future__ import annotations

import logging
import os
import socket
import sqlite3
import time

from jarvis.auth import auth_enabled, count_active_tokens

logger = logging.getLogger(__name__)

LOOPBACK = "127.0.0.1"
BIND_HOST_ENV = "JARVIS_BIND_HOST"
BIND_STRICT_ENV = "JARVIS_BIND_STRICT"

# How long to wait for a non-loopback host to appear on a local
# interface. Tailscale assigns 100.x.y.z asynchronously at boot, so a
# service starting from a LaunchAgent can legitimately be early. 20s is
# long enough for tailscaled to come up and short enough that
# scripts/mortimer.sh's 25s post-launch sleep is strictly greater than it
# (F6 invariant: the health probe runs after the bind decision resolves).
BIND_WAIT_S = 20.0
BIND_POLL_S = 1.0


def _bind_strict() -> bool:
    """JARVIS_BIND_STRICT, default false (F8). When false, a requested
    non-loopback host that is simply not assigned to an interface (Tailscale
    down) falls back to loopback with a loud ERROR rather than refusing to
    start — losing remote access, not security. When true, that case is a
    hard refusal (exit 2). The 'no unrevoked token' case refuses in BOTH
    modes: that is a real misconfiguration, not an outage."""
    return (os.environ.get(BIND_STRICT_ENV) or "").strip().lower() == "true"


class BindRefused(RuntimeError):
    """Raised instead of binding. Callers log it and exit 2 (K1)."""


def is_loopback(host: str) -> bool:
    h = (host or "").strip().lower()
    if h in ("localhost", "::1", "[::1]"):
        return True
    return h == "127.0.0.1" or h.startswith("127.")


def _host_is_bindable(host: str) -> bool:
    """Is this address assigned to a local interface right now?

    Asked by attempting a throwaway bind on an ephemeral port, which is
    the exact question uvicorn will ask a moment later. stdlib only.
    """
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    try:
        sock.bind((host, 0))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def _wait_for_host(host: str, timeout_s: float = BIND_WAIT_S) -> bool:
    deadline = time.monotonic() + timeout_s
    while True:
        if _host_is_bindable(host):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(BIND_POLL_S)


def resolve_bind_host(
    process: str, conn: sqlite3.Connection | None = None
) -> str:
    """Return the host to bind, or raise BindRefused.

    `process` is a label for logs only ("admin-sidecar" or "bot").
    """
    requested = (os.environ.get(BIND_HOST_ENV) or "").strip() or LOOPBACK

    if not auth_enabled():
        if not is_loopback(requested):
            logger.error(
                "bind_forced_loopback process=%s requested=%s reason=auth_disabled",
                process,
                requested,
            )
        return LOOPBACK

    if is_loopback(requested):
        return requested

    active = count_active_tokens(conn)
    if active == 0:
        raise BindRefused(
            f"refusing to bind {process} to {requested}: JARVIS_AUTH_ENABLED "
            f"is true but no unrevoked client token exists. Mint one with "
            f"`python -m jarvis.auth add <name>`, or unset JARVIS_BIND_HOST "
            f"to stay on {LOOPBACK}."
        )

    if not _wait_for_host(requested):
        # F8: the address is simply not present (Tailscale down, logged-out
        # node, expired key). This is an outage, not a security condition.
        if _bind_strict():
            raise BindRefused(
                f"refusing to bind {process} to {requested}: that address is "
                f"not assigned to any local interface after {BIND_WAIT_S:.0f}s "
                f"and JARVIS_BIND_STRICT=true. If it is a Tailscale address, "
                f"check `tailscale status` and `tailscale ip -4`."
            )
        logger.error(
            "bind_fell_back_to_loopback process=%s requested=%s "
            "reason=interface_absent after_s=%.0f (set JARVIS_BIND_STRICT=true "
            "to refuse instead)",
            process,
            requested,
            BIND_WAIT_S,
        )
        return LOOPBACK

    logger.info(
        "bind_resolved process=%s host=%s active_tokens=%d",
        process,
        requested,
        active,
    )
    return requested


def resolve_port(env_name: str, default: int) -> int:
    """Port from an env var, falling back to `default` on anything
    unparseable or out of range. A bad port is a configuration typo, not
    a reason to refuse to start on the address that is already gated."""
    raw = (os.environ.get(env_name) or "").strip()
    if not raw:
        return default
    try:
        port = int(raw)
    except ValueError:
        logger.error("bind_bad_port env=%s value=%r using=%d", env_name, raw, default)
        return default
    if not (1 <= port <= 65535):
        logger.error("bind_bad_port env=%s value=%r using=%d", env_name, raw, default)
        return default
    return port
```

**Tests:** `tests/unit/test_bind.py`, the `test_bind.py` table in §7 (T-A23 … T-A31a).

### Step 4 — install the middleware on the sidecar

**File:** `jarvis/admin/server.py`.

(a) Add the import beside the existing `from fastapi.middleware.cors import CORSMiddleware` (line 65):

```python
from jarvis.authmw import BearerAuthMiddleware
```

(b) Add `"Authorization"` to the existing CORS `allow_headers` and add the auth middleware **before** the CORS block (F1). The existing CORS block is at lines 107–113 today (search `app.add_middleware(` / `CORSMiddleware`). Because Starlette's `add_middleware` inserts at index 0, the **last** middleware added is outermost — so adding `BearerAuthMiddleware` *first* and `CORSMiddleware` *after* makes **CORS outermost** and the auth 401 is wrapped by it and carries `Access-Control-Allow-Origin` (F1). The block reads:

```python
# K1 (MORTIMER_REMOTE_ACCESS_PLAN.md A4/A6/A7): every one of this
# module's 64 routes requires `Authorization: Bearer <token>`. There are
# no exemptions — /api/health included — and loopback is not exempt.
# Added BEFORE CORSMiddleware so that CORS ends up OUTERMOST (Starlette's
# add_middleware inserts at index 0): a 401 generated here is then wrapped
# by CORSMiddleware and carries Access-Control-Allow-Origin, so the
# browser can read it and the console's toast can fire (F1). Without this
# ordering the cross-origin fetch rejects with a TypeError instead of
# resolving with status 401.
app.add_middleware(BearerAuthMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)
```

Note the third change in the CORS block: `allow_methods` gains `"DELETE"`. Route #34 (`DELETE /api/memory/fact/{key}`, search `@app.delete("/api/memory/fact/` in `jarvis/admin/server.py`) has never been reachable from a browser preflight, because `allow_methods=["GET", "POST"]` omits it — a pre-existing defect this plan fixes while it is in the file, since adding an `Authorization` header is exactly what turns that request into a preflighted one.

**Measured (F1), the plan's exact middleware and CORS config driven under `fastapi.testclient`:**

```
$ python3 mw_test.py
F1 401 no-token: status=401 ACAO='http://localhost:5173' www='Bearer realm="jarvis"'
valid token: status=200 body={"ok":true}
F16 bare OPTIONS no-Origin: status=401 (expect 401)
genuine preflight: status=200 ACAO='http://localhost:5173' (expect 200 + ACAO)
```

The 401 now carries `Access-Control-Allow-Origin` (the defect F1 identified was `ACAO=None` with auth outermost); a bare `OPTIONS` with no `Origin` is a 401 rather than a route-enumeration oracle (F16); a genuine preflight still passes with the CORS header.

**Test:** §7 T-A14 (all 64 routes 401 without a header), T-A17 (genuine preflight passes), T-A17c (401 carries ACAO — the F1 regression guard), T-A17d (bare `OPTIONS` without `Origin` → 401 — the F16 guard), T-A18 (`Authorization` is an allowed header).

### Step 5 — make the existing test suite explicit about auth, then prove coverage

`JARVIS_AUTH_ENABLED` defaults to `true`, so without this step every existing sidecar test (`tests/unit/test_admin_*.py`, ~9 files) starts returning 401.

**File:** `tests/conftest.py`. Append, after `_stub_procedures_learning`:

```python
@pytest.fixture(autouse=True)
def _auth_disabled_by_default(monkeypatch):
    """K1 (MORTIMER_REMOTE_ACCESS_PLAN.md §5 Step 5): the whole suite runs
    with JARVIS_AUTH_ENABLED=false so that ~1538 pre-existing tests keep
    exercising what they were written to exercise rather than 401.

    The files that test AUTHENTICATION re-enable it inside their own
    fixtures — tests/unit/test_auth_middleware.py, test_bind.py,
    test_bot_server.py. pytest runs autouse fixtures at a given scope
    BEFORE explicitly-requested ones, so a test's own
    monkeypatch.setenv("JARVIS_AUTH_ENABLED", "true") always wins.

    This deliberately does NOT touch JARVIS_SERVICE_TOKEN: the service
    header must be absent by default so tests/unit/test_service_token.py
    can prove both the set and unset behaviours.
    """
    monkeypatch.setenv("JARVIS_AUTH_ENABLED", "false")
```

**File:** `tests/unit/test_auth_middleware.py` (new) — §7's `test_auth_middleware.py` table (T-A14, T-A15b, T-A16b, T-A17, T-A17c, T-A17d, T-A18, T-A19, T-A20b, T-A21b, T-A22, T-A22b).

Its route-count assertion is the mechanism that keeps this plan true as the sidecar grows:

```python
EXPECTED_SIDECAR_ROUTES = 64   # §1.2. Adding a route? Add it to the count
                               # and confirm the middleware still covers it.
```

**Verification for this step:** `pytest tests/unit -q` must be green with the same test count as before plus the new files' tests. If any pre-existing test now fails with a 401, the fixture is not being applied — do not "fix" it by exempting a route.

### Step 6 — the service token reaches every internal caller

**(a) Mint and store it — already done in §5 Step 0 (F11), before this code merged.** The commands are repeated in §8 V1. `inject_env()` places it in `os.environ` in both long-lived processes with no new call site (§1.6). If Step 0 was skipped, the startup guard from Step 0 logs `service_token_missing` on boot and every internal call 401s until the vault holds the value.

**(b) `AdminClient` sends it.** `mcp_servers/mcp_selfedit/logic.py:29-44` — change only `__init__`:

```python
class AdminClient:
    """Duck-typed httpx.Client wrapper so tests can inject a fake."""

    def __init__(self, base_url: str | None = None, timeout: float = 10.0):
        import httpx  # local import: keeps module import light for tests

        # K1: Mortimer's own internal callers authenticate like everyone
        # else — loopback is not exempt. service_headers() returns {} when
        # JARVIS_SERVICE_TOKEN is unset, so a stack running with
        # JARVIS_AUTH_ENABLED=false behaves exactly as it did before.
        from jarvis.auth import service_headers

        self._client = httpx.Client(
            base_url=base_url or os.environ.get(ADMIN_URL_ENV) or DEFAULT_ADMIN_URL,
            timeout=timeout,
            headers=service_headers(),
        )
```

This covers, with no further edits: `mcp_servers/mcp_selfedit/server.py:21`, `mcp_servers/mcp_web/server.py:17-18`, `mcp_servers/mcp_apps/server.py:30-33`, and `jarvis/bot/pipeline.py:419-422`'s clipboard calls.

**(c) The three watchers send it.** In each of `jarvis/bot/plan_watcher.py:62-66`, `jarvis/bot/research_watcher.py:44-48`, `jarvis/bot/progress_watcher.py:156-160`, the `_default_fetch_*` body becomes (shown for `plan_watcher`; the other two differ only in the path and the function name):

```python
async def _default_fetch_job(admin_url: str) -> dict[str, Any] | None:
    import httpx  # local import: keeps module import light for tests

    from jarvis.auth import service_headers  # K1

    async with httpx.AsyncClient(timeout=3.0) as client:
        resp = await client.get(
            f"{admin_url}/api/plan/job", headers=service_headers()
        )
        resp.raise_for_status()   # F11: a 401 must NOT be parsed as a job
        ...
```

**F11 — the watchers must not parse a 401 body as a job.** `plan_watcher` and `research_watcher`'s `_default_fetch_*` return `resp.json()` unconditionally today, so a 401 body (`{"ok": false, "error": "unauthorized …"}`) would flow into the announcement logic as if it were a job document. Adding `resp.raise_for_status()` before `.json()` turns an auth failure into a caught exception the watcher logs and skips (each watcher's tick already tolerates a fetch exception), rather than a fabricated announcement. `progress_watcher` reads `list_runs` locally and only polls the sidecar for the self-edit job; give its sidecar GET the same `raise_for_status()`. Paths, unchanged: `plan_watcher` → `/api/plan/job`; `research_watcher` → `/api/research/job`; `progress_watcher` → `/api/selfedit/run`.

**(d) The three MCP children declare it (K2).** Only the servers that construct an `AdminClient` get the name — `mcp_time`, `mcp_notes`, `mcp_memory`, `mcp_reminders`, `mcp_system`, `mcp_git`, `mcp_repo`, `mcp_runlog`, and `mcp_screen` do **not** call the sidecar and must not receive the token.

Rule for the implementer, deterministic regardless of whether `MORTIMER_SECURITY_HARDENING_PLAN.md` has landed first: **append `JARVIS_SERVICE_TOKEN` to whatever list `requires_env` already holds; if the value is blank or `[]`, write `[JARVIS_SERVICE_TOKEN]`.**

**APPEND — never assign the whole list (F2, CP-F4).** Two of these three lists are non-empty today; the "after" column is the *result of appending*, not a value to paste over the existing one. Overwriting `mcp_web`'s list would delete `TAVILY_API_KEY` and silently drop `web_search` into degraded mode once T4a scopes envs; overwriting `mcp_selfedit`'s would delete SEC's `JARVIS_UPGRADE_PROFILE` once the hardening plan has landed. Verified today (2026-08-27) against source: `mcp_selfedit/skill.yaml` `requires_env: []`, `mcp_web/skill.yaml` `requires_env: [TAVILY_API_KEY]` (block-sequence form — line 6 is `requires_env:` and line 7 is `- TAVILY_API_KEY`), `mcp_apps/skill.yaml` `requires_env: [GITHUB_TOKEN]`.

| File | `requires_env` before (today, verified) | after appending (hardening plan not yet landed) | after appending (hardening plan landed) |
|---|---|---|---|
| `mcp_servers/mcp_selfedit/skill.yaml` (search `requires_env:`) | `[]` | `[JARVIS_SERVICE_TOKEN]` | `[JARVIS_UPGRADE_PROFILE, JARVIS_SERVICE_TOKEN]` |
| `mcp_servers/mcp_web/skill.yaml` (search `requires_env:`) | `[TAVILY_API_KEY]` | `[TAVILY_API_KEY, JARVIS_SERVICE_TOKEN]` | `[TAVILY_API_KEY, JARVIS_UNITS, JARVIS_SERVICE_TOKEN]` |
| `mcp_servers/mcp_apps/skill.yaml` (search `requires_env:`) | `[GITHUB_TOKEN]` | `[GITHUB_TOKEN, JARVIS_SERVICE_TOKEN]` | `[GITHUB_TOKEN, JARVIS_SERVICE_TOKEN]` |

Both end states are correct; T-A31 asserts `JARVIS_SERVICE_TOKEN` membership and T-A31b (F2) asserts `TAVILY_API_KEY` is **still present** in `mcp_web` after the edit, so a whole-list overwrite that dropped it fails CI rather than shipping.

Note for §8: `scripts/check_skills.py:102-104` will report `requires_env JARVIS_SERVICE_TOKEN is not set` on any machine where the vault does not hold it — the same message `GITHUB_TOKEN` already produces on a fresh checkout. That script is not in CI (`.github/workflows/validate.yml`), so nothing is blocked; step (a) removes the message on Larry's machine.

**Tests:** §7 T-A29 … T-A32.

### Step 7 — the bot (A10 decision tree)

Run **Check B1** from A10 first and record its output in the PR description.

#### Branch A — the runner exposes its app (verified true for Pipecat 1.4.0)

**File:** `jarvis/bot/server.py` (new).

```python
"""Bot entrypoint: bearer auth + a gated bind host, in front of Pipecat's
own development runner (K1, K5; plan A6/A7/A8/A10 Branch A).

WHY THIS FILE EXISTS. jarvis/bot/bot.py used to call
pipecat.runner.run.main() directly, which serves up to seventeen routes on
--host localhost with no authentication (see the plan's §1.3). Pipecat is
not forked, vendored, or patched: run.py:168 defines a module-level
`app: FastAPI`, and its own docstring (run.py:169-178) documents importing
it "to add custom routes from other packages before calling main()". That
is the seam this file uses.

ORDERING. add_middleware inserts at index 0, so the LAST added is
outermost. This file adds BearerAuthMiddleware BEFORE main() runs, and
main() -> _configure_server_app adds CORSMiddleware (run.py:499), so CORS
ends up outermost and answers preflight itself. See the plan's A7.
"""

from __future__ import annotations

import logging
import sys

from pipecat.runner.run import app as runner_app
from pipecat.runner.run import main as runner_main

from jarvis.authmw import BearerAuthMiddleware
from jarvis.bind import BindRefused, resolve_bind_host, resolve_port

logger = logging.getLogger(__name__)

BOT_PORT_ENV = "JARVIS_BOT_PORT"
DEFAULT_BOT_PORT = 7860


def install_auth() -> None:
    """Idempotent: adding the same middleware twice would double-verify.

    Starlette refuses add_middleware after startup, so this must run
    before runner_main().
    """
    for mw in runner_app.user_middleware:
        if mw.cls is BearerAuthMiddleware:
            return
    runner_app.add_middleware(BearerAuthMiddleware)


def _strip_host_port(argv: list[str]) -> list[str]:
    """Remove any caller-supplied --host/--port (and their `=`-joined forms)
    so no command-line argument can widen the gated bind (F7). The resolved,
    gated host is the ONLY host that reaches the runner."""
    out: list[str] = []
    skip = False
    for arg in argv:
        if skip:
            skip = False
            continue
        if arg in ("--host", "--port"):
            skip = True  # also drop its value token
            logger.error("bind_arg_ignored arg=%s reason=gated_bind_wins", arg)
            continue
        if arg.startswith("--host=") or arg.startswith("--port="):
            logger.error("bind_arg_ignored arg=%s reason=gated_bind_wins", arg)
            continue
        out.append(arg)
    return out


def build_argv(host: str, port: int) -> list[str]:
    """Runner arguments. The resolved --host/--port are supplied and any
    caller-supplied --host/--port are STRIPPED first (F7), so the gated bind
    can never be widened from the command line; other passed args survive.
    """
    return ["--host", host, "--port", str(port), *_strip_host_port(sys.argv[1:])]


def main() -> None:
    install_auth()
    try:
        host = resolve_bind_host("bot")
    except BindRefused as exc:
        logger.error("bind_refused process=bot %s", exc)
        print(f"bind refused: {exc}", file=sys.stderr)
        raise SystemExit(2)
    port = resolve_port(BOT_PORT_ENV, DEFAULT_BOT_PORT)
    logger.info("bot_startup host=%s port=%d", host, port)
    sys.argv = [sys.argv[0], *build_argv(host, port)]
    runner_main()


if __name__ == "__main__":
    main()
```

**File:** `jarvis/bot/bot.py` — replace the `__main__` block (lines 50–53) with:

```python
if __name__ == "__main__":
    from jarvis.bot.server import main

    main()
```

and change the docstring line 4 from `Then open http://localhost:7860/client and click Connect.` to (F4 — `pipecat-ai-prebuilt==1.0.5` **is** pinned in `requirements-lock.txt`, so `/client` is served, but it now requires a bearer token that a browser address bar cannot attach):

```
Then open the web console (http://localhost:5173) and click Connect — it
carries the bearer token. The runner's own /client page IS served
(pipecat-ai-prebuilt is installed) but now requires an Authorization header,
which a plain browser navigation to /client cannot supply, so use the
console on :5173 as the entry point.
```

#### Branch B — the runner does not expose its app (contingency; implement ONLY if Check B1 prints `BRANCH B`)

Replace `jarvis/bot/server.py`'s imports and `main()` with the following. Everything else in the file (`install_auth` is dropped, `build_argv` is dropped) is replaced too — this is the whole file for Branch B.

```python
"""Bot entrypoint, Branch B (plan A10): the installed Pipecat has no
module-level `app`, so this file builds one the way the runner does and
hands it back to the runner's own configuration function.

This is NOT a fork: _configure_server_app is called unmodified and does
all the transport wiring; only the FastAPI instance is ours, assigned to
the runner module's global before the call because the setup helpers
close over it (pipecat/runner/run.py:499, 511).
"""

from __future__ import annotations

import argparse
import logging
import sys

import uvicorn
from fastapi import FastAPI
from pipecat.runner import run as pcrun

from jarvis.authmw import BearerAuthMiddleware
from jarvis.bind import BindRefused, resolve_bind_host, resolve_port

logger = logging.getLogger(__name__)

BOT_PORT_ENV = "JARVIS_BOT_PORT"
DEFAULT_BOT_PORT = 7860


def _strip_host_port(argv: list[str]) -> list[str]:
    """Remove any caller-supplied --host/--port (and `=`-joined forms) so no
    command-line argument can widen the gated bind (F7)."""
    out: list[str] = []
    skip = False
    for arg in argv:
        if skip:
            skip = False
            continue
        if arg in ("--host", "--port"):
            skip = True
            logger.error("bind_arg_ignored arg=%s reason=gated_bind_wins", arg)
            continue
        if arg.startswith("--host=") or arg.startswith("--port="):
            logger.error("bind_arg_ignored arg=%s reason=gated_bind_wins", arg)
            continue
        out.append(arg)
    return out


def _parse(argv: list[str], host: str, port: int) -> argparse.Namespace:
    """The runner's argument surface, re-declared. main() cannot be reused
    because it also starts the server. Every default matches
    pipecat/runner/run.py's own (search the runner's own argparse defaults).
    The gated host/port are the argparse DEFAULTS and any caller --host/--port
    is stripped from argv first (F7), so the gate cannot be widened."""
    argv = _strip_host_port(argv)
    p = argparse.ArgumentParser(description="Mortimer bot runner")
    p.add_argument("--host", type=str, default=host)
    p.add_argument("--port", type=int, default=port)
    p.add_argument("-t", "--transport", type=str, default=None)
    p.add_argument("-x", "--proxy", default=None)
    p.add_argument("-d", "--direct", action="store_true", default=False)
    p.add_argument("-f", "--folder", type=str, default=None)
    p.add_argument("--runner-body", dest="runner_body", type=str, default=None)
    p.add_argument("-v", "--verbose", action="count", default=0)
    p.add_argument("--dialin", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--esp32", action="store_true", default=False)
    p.add_argument("--whatsapp", action="store_true", default=False)
    p.add_argument("--ws-auth", dest="ws_auth", type=str, default="none")
    p.add_argument(
        "--allowed-origins", dest="allowed_origins", nargs="*", default=None
    )
    return p.parse_args(argv)


def build(argv: list[str], host: str, port: int) -> tuple[FastAPI, argparse.Namespace]:
    args = _parse(argv, host, port)
    app = FastAPI()
    pcrun.app = app                 # the setup helpers use the module global
    pcrun.RUNNER_HOST = args.host
    pcrun.RUNNER_PORT = args.port
    pcrun.RUNNER_DOWNLOADS_FOLDER = args.folder
    pcrun._configure_server_app(args)
    # Added AFTER _configure_server_app's CORSMiddleware, so this is the
    # OUTERMOST middleware here and its OPTIONS branch IS reached (A7).
    app.add_middleware(BearerAuthMiddleware)
    return app, args


def main() -> None:
    try:
        host = resolve_bind_host("bot")
    except BindRefused as exc:
        logger.error("bind_refused process=bot %s", exc)
        print(f"bind refused: {exc}", file=sys.stderr)
        raise SystemExit(2)
    port = resolve_port(BOT_PORT_ENV, DEFAULT_BOT_PORT)
    app, args = build(sys.argv[1:], host, port)
    logger.info("bot_startup host=%s port=%d branch=B", args.host, args.port)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
```

`jarvis/bot/bot.py`'s change is identical in both branches.

#### Also in Step 7 (both branches)

**File:** `scripts/spoken_acceptance.py`. The script POSTs an offer to the bot (search `--url` and the offer `POST`). It does **not** import `os` today (F20 — its imports are `argparse, asyncio, fractions, json, logging, re, sys, time, wave, httpx`), so first add `import os` beside the existing stdlib imports, then add:

```python
    ap.add_argument(
        "--token",
        default=os.environ.get("JARVIS_SERVICE_TOKEN", ""),
        help="bearer token (K1); defaults to $JARVIS_SERVICE_TOKEN",
    )
```

and on the offer request pass `headers={"Authorization": f"Bearer {args.token}"} if args.token else {}`.

**Tests:** §7 T-A20, T-A33 … T-A37.

### Step 8 — `jarvis/urls.py` (K5) and the web console (A12)

**File:** `jarvis/urls.py` (new).

```python
"""The one module that knows a default host or port (K5).

Clients discover the server by ONE base URL each. No other module names a
host; jarvis/bind.py names 127.0.0.1 as the loopback constant and nothing
else does.
"""

from __future__ import annotations

import os

ADMIN_URL_ENV = "JARVIS_ADMIN_URL"
BOT_URL_ENV = "JARVIS_BOT_URL"

DEFAULT_ADMIN_URL = "http://127.0.0.1:7861"
DEFAULT_BOT_URL = "http://127.0.0.1:7860"


def admin_url() -> str:
    return (os.environ.get(ADMIN_URL_ENV) or "").strip() or DEFAULT_ADMIN_URL


def bot_url() -> str:
    return (os.environ.get(BOT_URL_ENV) or "").strip() or DEFAULT_BOT_URL
```

**File:** `mcp_servers/mcp_selfedit/logic.py` — replace lines 19–20 with a re-export, so the three watchers and `mcp_web`/`mcp_apps` keep importing the same names:

```python
# K5 (MORTIMER_REMOTE_ACCESS_PLAN.md A11): one module owns the defaults.
from jarvis.urls import ADMIN_URL_ENV, DEFAULT_ADMIN_URL  # noqa: F401
```

**File:** `web/src/api.ts` (new).

```ts
// K1/K5 (MORTIMER_REMOTE_ACCESS_PLAN.md A12). Minimal on purpose: the
// console is retired at T1.4 and replaced by JarvisKit.

// F18: the fallbacks are 127.0.0.1 (not localhost) so all four runtime
// spellings of these bases — jarvis/urls.py, api.ts, ShellAuth.swift — agree.
export const ADMIN_BASE: string =
  import.meta.env.VITE_JARVIS_ADMIN_URL ?? "http://127.0.0.1:7861";
export const BOT_OFFER_URL: string =
  (import.meta.env.VITE_JARVIS_BOT_URL ?? "http://127.0.0.1:7860") + "/api/offer";

const TOKEN_KEY = "jarvis_token";   // K1 names this key literally.

export function getToken(): string {
  try {
    return localStorage.getItem(TOKEN_KEY) ?? "";
  } catch {
    return "";
  }
}

export function setToken(token: string): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* private mode: the field simply does not persist */
  }
}

export function authHeaders(): Record<string, string> {
  const t = getToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

type AuthErrorFn = () => void;
const authErrorSubs = new Set<AuthErrorFn>();
let notified = false;              // ONE toast per page load, never a retry.

export function subscribeAuthError(fn: AuthErrorFn): () => void {
  authErrorSubs.add(fn);
  return () => authErrorSubs.delete(fn);
}

export async function authFetch(path: string, init?: RequestInit): Promise<Response> {
  const url = path.startsWith("http") ? path : `${ADMIN_BASE}${path}`;
  const headers = { ...(init?.headers ?? {}), ...authHeaders() };
  const res = await fetch(url, { ...init, headers });
  if (res.status === 401 && !notified) {
    notified = true;
    authErrorSubs.forEach((fn) => fn());
  }
  return res;
}
```

**The six panels.** In each, delete the `const API = "http://localhost:7861";` line and add `import { ADMIN_BASE as API, authFetch } from "../api";` beside the existing imports, then replace each `fetch(` with `authFetch(`. The complete call-site list (path:line as of this snapshot):

- `web/src/components/RunsPanel.tsx` — `:9` (const), `:116`, `:139`
- `web/src/components/EditModePanel.tsx` — `:3` (const), `:210`, `:220`, `:245`, `:286`, `:379`, `:389`, `:405`, `:494`, `:534`
- `web/src/components/SystemVitals.tsx` — `:3` (const), `:78`
- `web/src/components/GitPanel.tsx` — `:3` (const), `:30`, `:45`
- `web/src/components/MemoryPanel.tsx` — `:3` (const), `:89`, `:94`, `:102`, `:126`, `:138`
- `web/src/components/AmbientStrip.tsx` — `:4` (const), `:117`

**`web/src/jarvisClient.ts:17`** becomes:

```ts
  client.connect({
    webrtcRequestParams: {
      endpoint: BOT_OFFER_URL,
      requestHeaders: authHeaders(),
    },
  });
```

with `import { BOT_OFFER_URL, authHeaders } from "./api";` added.

**`web/src/components/AgentsTab.tsx`** — insert at the very top of the tab body, above the run cards:

```tsx
      <div className="dev-token">
        <h4>Dev</h4>
        <label htmlFor="jarvis-token">Access token</label>
        <input
          id="jarvis-token"
          type="password"
          value={tokenDraft}
          placeholder={
            getToken() ? "stored — enter a new token to replace" : "jvt_…"
          }
          onChange={(e) => setTokenDraft(e.target.value)}
        />
        <button onClick={() => { setToken(tokenDraft); setTokenDraft(""); }}>
          Save
        </button>
        <button onClick={() => { setToken(""); setTokenDraft(""); }}>
          Clear
        </button>
      </div>
```

with `const [tokenDraft, setTokenDraft] = useState("");` and `import { getToken, setToken } from "../api";`. The stored value is never rendered back into the field.

**`web/src/App.tsx`** — subscribe once, render the chip with the REAL class and a `clearTimeout` cleanup (F9 — there is no `.attn-chip` rule in `web/src`; the speaker-gate notice uses `speaker-gate-notice`, and the existing pattern clears its timeout to avoid a leaked timer):

```tsx
  const [authChip, setAuthChip] = useState(false);
  const authTimer = useRef<number | undefined>(undefined);
  useEffect(() => {
    const unsub = subscribeAuthError(() => {
      setAuthChip(true);
      window.clearTimeout(authTimer.current);
      authTimer.current = window.setTimeout(() => setAuthChip(false), 4000);
    });
    return () => {
      unsub();
      window.clearTimeout(authTimer.current);
    };
  }, []);
```

and, beside the existing speaker-gate chip, render it with the same class that chip uses:

```tsx
  {authChip && (
    <span className="speaker-gate-notice" role="status">Token required — Dev tab</span>
  )}
```

`Token required — Dev tab` is K1's literal copy and must not be reworded; `subscribeAuthError` and `useRef` are imported alongside the existing hooks/`../api` import.

### Step 9 — the sidecar binds through the gate (**the only step that can open a port**)

**File:** `jarvis/admin/server.py`, `main()` (lines 1768–1779) becomes:

```python
def main() -> None:
    import uvicorn

    from jarvis.bind import BindRefused, resolve_bind_host, resolve_port

    try:
        host = resolve_bind_host("admin-sidecar")
    except BindRefused as exc:
        # K1: refusal is a logged error and exit code 2, never a silent
        # fallback to loopback — an operator who asked for a tunnel bind
        # must find out that it did not happen.
        logger.error("bind_refused process=admin-sidecar %s", exc)
        print(f"bind refused: {exc}", file=sys.stderr)
        raise SystemExit(2)
    port = resolve_port("JARVIS_ADMIN_PORT", 7861)
    # D17 — at minimum, log startup with host/port/repo root.
    logger.info("admin_sidecar_startup host=%s port=%d repo_root=%s",
                host, port, REPO_ROOT)
    uvicorn.run(app, host=host, port=port, log_level="warning")
```

**File:** `scripts/mortimer.sh` (F6 — three edits; this file is in the §4 manifest).

1. `ADMIN_PORT=7861` (search `ADMIN_PORT=`) becomes `ADMIN_PORT="${JARVIS_ADMIN_PORT:-7861}"`, so the script's printed URLs match what actually bound.
2. Raise the post-launch `sleep` so it is strictly greater than `jarvis/bind.py`'s `BIND_WAIT_S` (20 s): change `sleep 4` (search `sleep 4`) to `sleep 25`. **Invariant, stated in §6 beside `BIND_WAIT_S`: `mortimer.sh` sleep (25 s) > `BIND_WAIT_S` (20 s)`** — otherwise the script reports health while the bind decision is still resolving in `_wait_for_host`, and a process about to exit 2 at t=20 s is reported "running" at t=4 s (the single most likely failure of this plan — Tailscale late at boot — narrated as success).
3. `check()` (search `kill -0`) must actually probe the port, not just test the pid, since a process can be alive at t=25 s and still have fallen back to loopback or be seconds from a strict-mode exit. Replace the `kill -0`-only body so it also curls health with the service token, e.g.:

```bash
check() {  # name pid url
  if ! kill -0 "$2" 2>/dev/null; then
    echo "  $1: FAILED to start — see logs/$1.log" >&2
    return
  fi
  if curl -fsS -H "Authorization: Bearer ${JARVIS_SERVICE_TOKEN:-}" "$3" >/dev/null 2>&1; then
    echo "  $1: running (pid $2) — $3"
  else
    echo "  $1: process up but $3 did not answer — check logs/$1.log for bind_fell_back_to_loopback / bind_refused" >&2
  fi
}
```

(The bot has no `/api/health`; keep its `check` on the pid-plus-`/status` form, or leave it pid-only — the admin health probe is the one that matters for the bind gate.)

**Tests:** §7 T-A26, T-A27.

### Step 10 — the Mac shell (A15)

**File:** `macos/MortimerShell/Sources/MortimerShell/ShellAuth.swift` (new).

```swift
// K1/K5 (MORTIMER_REMOTE_ACCESS_PLAN.md A15). The shell has no .env
// reader and no vault client, so its token comes from the login Keychain
// (Larry stores it once — see the plan's §8 V6) and its base URL from
// UserDefaults. T1's JarvisKit replaces both with KeychainStore.

import Foundation
import Security
import os

private let logger = Logger(subsystem: "com.mortimer.shell", category: "auth")

enum ShellAuth {
    // CP-F15: ONE Keychain convention for the K1 bearer token, shared with
    // NATIVE's KeychainStore. service is fixed; account is the ENDPOINT the
    // token is for, derived from the bot URL, so moving to the mini (a new
    // host) creates a new entry rather than reusing a stale token.
    private static let service = "com.mortimer.jarviskit"
    private static let defaultBotPort = 7860

    /// Account string keyed to the endpoint: "<scheme>://<host>:<port>" of
    /// the bot URL. Derived from adminBaseURL's scheme/host and the bot port.
    static var account: String {
        let base = adminBaseURL
        let scheme = base.scheme ?? "http"
        let host = base.host ?? "127.0.0.1"
        return "\(scheme)://\(host):\(defaultBotPort)"
    }

    /// Looked up once per process launch. nil means "no token stored" —
    /// callers must degrade, never retry (A15).
    static let bearer: String? = {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]
        var item: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &item)
        guard status == errSecSuccess,
              let data = item as? Data,
              let token = String(data: data, encoding: .utf8),
              !token.isEmpty
        else {
            logger.notice("no client token in Keychain (service=\(service, privacy: .public) account=\(account, privacy: .public))")
            return nil
        }
        return token
    }()

    static var adminBaseURL: URL {
        let raw = UserDefaults.standard.string(forKey: "JARVIS_ADMIN_URL")
        return URL(string: raw ?? "") ?? URL(string: "http://127.0.0.1:7861")!
    }
}
```

**File:** `macos/MortimerShell/Sources/MortimerShell/ShellLocation.swift` — replace the constant at `:36` with a computed URL and gate the POST:

```swift
private var sidecarLocationURL: URL {
    ShellAuth.adminBaseURL.appendingPathComponent("api/location")
}
```

and, at the top of whatever function builds the `URLRequest`:

```swift
guard let token = ShellAuth.bearer else {
    logger.notice("skipping location report — no client token stored")
    return
}
var req = URLRequest(url: sidecarLocationURL)
req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
```

No `swift build` is run in the sandbox (no macOS toolchain); §8 V7 is Larry compiling.

### Step 11 — documentation

- **`.env.example`** — append four commented lines, values absent so `scripts/check_env.py` does not start requiring them:

```
# Remote access (MORTIMER_REMOTE_ACCESS_PLAN.md, K1/K5)
# JARVIS_AUTH_ENABLED=true        # false = no auth AND a forced 127.0.0.1 bind
# JARVIS_BIND_HOST=127.0.0.1      # set to the Tailscale 100.x address to go remote
# JARVIS_BIND_STRICT=false        # true = refuse (exit 2) if the bind host is absent instead of falling back to loopback
# JARVIS_ADMIN_URL=http://127.0.0.1:7861
# JARVIS_BOT_URL=http://127.0.0.1:7860
# JARVIS_ADMIN_PORT=7861          # must AGREE with the port in JARVIS_ADMIN_URL (F19)
# JARVIS_BOT_PORT=7860            # must AGREE with the port in JARVIS_BOT_URL (F19)
# JARVIS_SERVICE_TOKEN lives in the vault, never here (C9).
```

F19: `JARVIS_ADMIN_PORT`/`JARVIS_BOT_PORT` move the listener; `JARVIS_ADMIN_URL`/`JARVIS_BOT_URL` tell clients where to look. They are independent knobs and must be kept consistent — a `JARVIS_BOT_PORT` that disagrees with the port inside `JARVIS_BOT_URL` points every client at nothing. All four are documented here so no knob is undiscoverable.

- **`README.md`** — the troubleshooting cell (F14/CP-F14: anchor on the row's first-cell text `./scripts/mortimer.sh`, not a line number) becomes: `` `./scripts/mortimer.sh` starts bot + admin + web together; check `logs/admin.log`; `curl -H "Authorization: Bearer $TOKEN" http://localhost:7861/api/health` ``. Add a short **Remote access** section with the §8 V1–V5 commands.
- **`CLAUDE.md`** — one paragraph under Architecture, in the house voice, naming `jarvis/auth.py` as the single verification implementation, `jarvis/authmw.py` as the one middleware covering both processes and both ASGI scope types, `jarvis/bind.py` as the one bind resolver, `JARVIS_AUTH_ENABLED` as the kill switch, and the rule that loopback is not exempt.
- **`docs/plans/MORTIMER_PLATFORM_ROADMAP.md`** — this plan does **not** edit the roadmap. The roadmap is a shared artifact edited only by the SEC track (`CROSS_PLAN_RESOLUTION.md` §C F14). The SEC roadmap edit folds in a one-line pointer beside §2.2 to this plan's "Corrections to the roadmap" (R-A1…R-A4); the implementer of THIS plan makes no roadmap change.

### Step 12 — the self-edit exposure report (informational, A14)

**File:** `tests/unit/test_auth.py`, one extra test that **reports and never fails**, so this plan can merge before Larry's commit (§8 V8):

```python
def test_report_selfedit_exposure_of_auth_modules(capsys):
    """A14/C8. Reports, does not assert: config/self_edit_allowlist.json is
    Larry's commit. This goes quiet once the three deny entries land."""
    import json, pathlib
    root = pathlib.Path(__file__).resolve().parents[2]
    cfg = json.loads((root / "config/self_edit_allowlist.json").read_text())
    deny = set(cfg.get("deny", []))
    missing = [p for p in ("jarvis/auth.py", "jarvis/authmw.py", "jarvis/bind.py")
               if p not in deny]
    if missing:
        print(f"WARNING: not yet on the self-edit deny list: {missing}")
    assert True
```

---

## §6 Tuning knobs — where every number lives, its default, its env override

Every value below has **one owner per runtime** (F18). Within a single runtime a value is defined once and a second definition is a bug; the Swift shell and the TypeScript console are separate runtimes with their own fallbacks, listed here so all four spellings of a base URL can be checked to agree (they now all use `127.0.0.1`).

| Knob | Default | Defined at | Env override | Read at (the only place) |
|---|---|---|---|---|
| Auth kill switch | `true` | `jarvis/auth.py` `ENABLED_ENV` | `JARVIS_AUTH_ENABLED` | `jarvis/auth.py:auth_enabled()` |
| Service token | unset | vault entry, not code | `JARVIS_SERVICE_TOKEN` | `jarvis/auth.py:service_headers()` |
| Token prefix | `"jvt_"` | `jarvis/auth.py` `TOKEN_PREFIX` | none (contract K1) | `mint_token`, `parse_bearer` |
| Token entropy | 32 bytes | `jarvis/auth.py` `TOKEN_BYTES` | none | `mint_token` |
| Token length | 47 | `jarvis/auth.py` `TOKEN_LEN` (derived) | none | `parse_bearer` |
| Verify busy timeout | `250 ms` | `jarvis/auth.py` `VERIFY_BUSY_TIMEOUT_MS` | none | `verify_bearer` (F5) |
| `last_used_at` throttle | `60 s` | `jarvis/auth.py` `LAST_USED_THROTTLE_S` | none | `_touch_last_used` (F5) |
| Default `user_id` | `"larry"` | `jarvis/auth.py` `DEFAULT_USER_ID` **and** the SQL `DEFAULT 'larry'` in `MIGRATION_0034` | none | `_cmd_add`; the column default is the backstop for a row inserted any other way |
| Bind host | `127.0.0.1` | `jarvis/bind.py` `LOOPBACK` | `JARVIS_BIND_HOST` | `jarvis/bind.py:resolve_bind_host()` |
| Bind strict | `false` | `jarvis/bind.py` `BIND_STRICT_ENV` | `JARVIS_BIND_STRICT` | `jarvis/bind.py:_bind_strict()` (F8) |
| Interface wait | `20.0 s` | `jarvis/bind.py` `BIND_WAIT_S` | none | `_wait_for_host` (F6 invariant: `mortimer.sh` sleep 25 s > this) |
| Interface poll | `1.0 s` | `jarvis/bind.py` `BIND_POLL_S` | none | `_wait_for_host` |
| Sidecar port | `7861` | literal argument in `jarvis/admin/server.py:main()` | `JARVIS_ADMIN_PORT` | `resolve_port("JARVIS_ADMIN_PORT", 7861)` — must AGREE with the port in `JARVIS_ADMIN_URL` (F19) |
| Bot port | `7860` | `jarvis/bot/server.py` `DEFAULT_BOT_PORT` | `JARVIS_BOT_PORT` | `resolve_port(BOT_PORT_ENV, DEFAULT_BOT_PORT)` — must AGREE with the port in `JARVIS_BOT_URL` (F19) |
| Admin base URL | `http://127.0.0.1:7861` | `jarvis/urls.py` `DEFAULT_ADMIN_URL` | `JARVIS_ADMIN_URL` | `jarvis/urls.py:admin_url()` (and the re-export `mcp_selfedit.logic` uses) |
| Bot base URL | `http://127.0.0.1:7860` | `jarvis/urls.py` `DEFAULT_BOT_URL` | `JARVIS_BOT_URL` | `jarvis/urls.py:bot_url()` |
| WS unauthorized close code | `4401` | `jarvis/authmw.py` `WS_CLOSE_UNAUTHORIZED` | none | `_reject` — ASGI-level only; uvicorn reports the pre-accept close to the client as **HTTP 403** (F14) |
| WS unavailable close code | `4503` | `jarvis/authmw.py` `WS_CLOSE_UNAVAILABLE` | none | `_unavailable` (F5) |
| Console admin base | `http://127.0.0.1:7861` | `web/src/api.ts` `ADMIN_BASE` fallback (separate runtime, F18) | `VITE_JARVIS_ADMIN_URL` (build-time) | `authFetch` |
| Console bot offer URL | `http://127.0.0.1:7860/api/offer` | `web/src/api.ts` `BOT_OFFER_URL` fallback (separate runtime) | `VITE_JARVIS_BOT_URL` | `jarvisClient.ts` |
| Console token key | `jarvis_token` | `web/src/api.ts` `TOKEN_KEY` | none (contract K1) | `getToken`/`setToken` |
| Console toast copy | `Token required — Dev tab` | `web/src/App.tsx` | none (contract K1) | one render site |
| Shell Keychain item | service `com.mortimer.jarviskit`, account `<scheme>://<host>:<port>` of the bot URL (CP-F15) | `ShellAuth.swift` (separate runtime; NATIVE's `KeychainStore` uses the same item) | none | `ShellAuth.bearer` |
| Shell admin base | `http://127.0.0.1:7861` | `ShellAuth.swift` fallback (separate runtime) | `UserDefaults["JARVIS_ADMIN_URL"]` | `ShellAuth.adminBaseURL` |
| Expected sidecar route count | `62` | `tests/unit/test_auth_middleware.py` `EXPECTED_SIDECAR_ROUTES` | none | the coverage test |
| Expected bot route count | `16` Starlette route entries (prebuilt mount included) | §1.3 enumeration | none | `test_bot_server.py` T-A37 (F4) |

---

## §7 Tests — by file and function, with inputs and expected outputs

New: **5 files, 60 tests** (recounted from the tables below — F13; the earlier "42" was wrong, and per-file headers now match their own tables). Modified: `tests/unit/test_db.py` (+1, `test_client_tokens_table_shape`), `tests/conftest.py` (fixture, no test). Per file: `test_auth.py` 23, `test_auth_middleware.py` 12, `test_bind.py` 11, `test_service_token.py` 8, `test_bot_server.py` 6.

**Re-measured 2026-08-27 (this revision).** The plan's verbatim `jarvis/auth.py` was extracted and run against a real SQLite: `py_compile` clean; token shape (200 mints all `jvt_`+47, unique); `parse_bearer` against the review's adversarial set (`None`/`""`/`"   "`/`"Basic …"`/`"Bearer t x"`/`"Bearer"`/wrong-length → `None`; `bearer`/`BEARER` case-insensitive and whitespace-tolerant → token); CLI `add`/duplicate(active)/`revoke`/duplicate(after revoke)/`revoke` unknown → exit codes `0/2/0/2/2`; and the F15 `auth_enabled` table (`unset`/`"true"`/`"0"`/`"no"`/`"off"`/`""` → `True`; `"false"`/`"False"`/`"FALSE"`/`" false "` → `False`) — all pass. The F5 lock behaviour, the F1 CORS ordering, the F16 bare-`OPTIONS`, and the F7 `build_argv` stripping were each measured separately (see §5 Step 4's block and the per-test "Measured" notes).

Shared fixture used by the first three files (define once in `tests/unit/test_auth.py` and import, or duplicate — it is four lines):

```python
@pytest.fixture
def tokendb(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "t.db"))
    from jarvis.db import run_migrations
    run_migrations()
    return tmp_path / "t.db"
```

### `tests/unit/test_auth.py` — 23 tests

| # | Function | Input | Expected |
|---|---|---|---|
| T-A1 | `test_minted_token_shape` | `mint_token()` ×100 | every value: starts `jvt_`, `len == 47`, body characters ⊆ `A-Za-z0-9-_`, no `=` |
| T-A2 | `test_mints_are_unique` | 1000 mints | 1000 distinct values |
| T-A3 | `test_hash_token_is_sha256_hex` | `hash_token("jvt_abc")` | `== hashlib.sha256(b"jvt_abc").hexdigest()`; 64 chars; all lowercase hex |
| T-A4 | `test_parse_bearer_rejects_missing` | `None`, `""`, `"   "` | all `None` |
| T-A5 | `test_parse_bearer_rejects_wrong_scheme` | `f"Basic {t}"`, `f"Token {t}"`, `t` (bare), `f"Bearer"`, `f"Bearer {t} extra"` | all `None` |
| T-A6 | `test_parse_bearer_accepts_scheme_case_insensitively` | `f"bearer {t}"`, `f"BEARER {t}"`, `f"BeArEr {t}"` | all `== t` |
| T-A7 | `test_parse_bearer_tolerates_extra_whitespace` | `f"Bearer  {t}"`, `f"  Bearer {t}  "` | both `== t` (`str.split()` collapses runs) |
| T-A8 | `test_parse_bearer_rejects_wrong_prefix` | `"xxx_" + t[4:]` | `None` |
| T-A9 | `test_parse_bearer_rejects_valid_prefix_wrong_length` | `"jvt_" + "A"*42`, `"jvt_" + "A"*44`, `"jvt_"` | all `None` |
| T-A10 | `test_verify_bearer_never_touches_db_for_malformed` | `verify_bearer("jvt_" + "A"*44, conn=RaisingConn())` where `RaisingConn.execute` raises `AssertionError` | returns `None`, no exception escapes (proves the length check precedes any query) |
| T-A11 | `test_verify_bearer_unknown_token` | mint via CLI, then verify a *different* mint | `None` |
| T-A12 | `test_verify_bearer_valid` | `add("phone")`, verify `f"Bearer {tok}"` | `ClientIdentity(name="phone", user_id="larry")` |
| T-A13 | `test_verify_bearer_updates_last_used_at` | as T-A12, then `SELECT last_used_at` | non-NULL, parses as ISO 8601, and is `>=` `created_at` |
| T-A14a | `test_verify_bearer_revoked` | `add("phone")`, `revoke("phone")`, verify | `None`, and `last_used_at` still `NULL` |
| T-A15 | `test_no_plaintext_in_database` | after `add("phone")`, read the raw file bytes of `t.db` | the token's 43-char body is **not** a substring; the hash **is** |
| T-A16 | `test_add_duplicate_name_refuses` | `main(["add","phone"])` twice; second time also after `revoke` | both second calls return `2`; row count stays `1` |
| T-A17a | `test_revoke_unknown_name_refuses` | `main(["revoke","nope"])` | `2`, stderr contains `no active token named` |
| T-A18a | `test_list_never_prints_a_hash` | `add("phone")`, `main(["list"])`, capsys | stdout contains `phone`, `larry`, `active`; does **not** contain `hash_token(tok)` nor any 64-char hex run |
| T-A19a | `test_count_active_excludes_revoked` | add 3, revoke 1 | `count_active_tokens() == 2` |
| T-A20a | `test_service_headers` | env unset → `{}`; env `""` → `{}`; env `"  jvt_x  "` → `{"Authorization": "Bearer jvt_x"}` | as stated |
| T-A21a | `test_report_selfedit_exposure_of_auth_modules` | Step 12 | always passes; prints a warning until Larry's commit |
| T-A22a | `test_auth_enabled_table` (F15) | `JARVIS_AUTH_ENABLED` = unset, `"true"`, `"false"`, `"False"`, `"FALSE"`, `" false "`, `"0"`, `"no"`, `"off"`, `""` | unset/`"true"`/`"0"`/`"no"`/`"off"`/`""` → `True`; `"false"`/`"False"`/`"FALSE"`/`" false "` → `False`. State the `""` case explicitly: an env var set to empty strips-and-lowers to `""`, which is `!= "false"`, so auth stays **on** — the safe direction, arrived at deliberately not by accident |
| T-A23a | `test_verify_bearer_lock_does_not_change_verdict` (F5) | mint a token; hold a write lock in a second connection; call `verify_bearer` for that token | returns `ClientIdentity` **quickly** (not after ~5 s, not `None`) — the WAL read decides the verdict and the throttled write is best-effort. **Measured 2026-08-27:** identity returned in 0.00 s under a held write lock (the old code blocked 5.01 s then returned `None`) |

*(numbering suffixes exist only to keep every id unique across the tables; use the function names.)*

### `tests/unit/test_auth_middleware.py` — 12 tests

All use `fastapi.testclient.TestClient(admin_server.app)` and `monkeypatch.setenv("JARVIS_AUTH_ENABLED", "true")` in their own fixture (which wins over `tests/conftest.py`'s autouse default — §5 Step 5).

| # | Function | Input | Expected |
|---|---|---|---|
| T-A14 | `test_every_sidecar_route_401s_without_a_token` | derive `paths = [r.path for r in admin_server.app.routes if isinstance(r, APIRoute)]`; assert `len(paths) == EXPECTED_SIDECAR_ROUTES` (79); for each route, issue its first declared method with path params filled by `"x"` / `"1"` | every response `status_code == 401`; every body `{"ok": false, "error": ...}`; every response carries `WWW-Authenticate: Bearer realm="jarvis"` |
| T-A15b | `test_health_is_not_exempt` | `GET /api/health`, no header | `401` (A4 — the exemption everyone expects is deliberately absent) |
| T-A16b | `test_loopback_without_token_is_401` | `TestClient(app, client=("127.0.0.1", 40000))`, `GET /api/health` | `401` (K1: loopback is not exempt) |
| T-A17 | `test_options_preflight_passes_without_token` | `OPTIONS /api/health` with `Origin: http://localhost:5173`, `Access-Control-Request-Method: GET` | `200`, and `access-control-allow-origin` present |
| T-A17c | `test_401_carries_cors_header` (F1) | `GET /api/health` with `Origin: http://localhost:5173`, no token | `401` **and** `access-control-allow-origin: http://localhost:5173` present — the regression guard for the CORS-ordering defect (a `TestClient` alone would miss it, so this test asserts the header explicitly). **Measured 2026-08-27:** `status=401 ACAO='http://localhost:5173'` with auth added before CORS; `ACAO=None` with the old auth-outermost ordering |
| T-A17d | `test_bare_options_without_origin_is_401` (F16) | `OPTIONS /api/health`, **no** `Origin` header | `401` — a bare `OPTIONS` is not a preflight and must not leak a `405`/`Allow` route-enumeration oracle. **Measured 2026-08-27:** `status=401` |
| T-A18 | `test_authorization_is_an_allowed_cors_header` | same preflight with `Access-Control-Request-Headers: authorization` | `access-control-allow-headers` contains `authorization` |
| T-A19 | `test_valid_token_reaches_the_handler` | mint into the temp DB, `GET /api/health` with the header | `200`, body `{"ok": true}` |
| T-A20b | `test_revoked_token_is_401_immediately` | valid call → `200`; `revoke`; identical call | second call `401` (proves A6's no-cache decision) |
| T-A21b | `test_kill_switch_allows_unauthenticated` | `JARVIS_AUTH_ENABLED=false`, `GET /api/health`, no header | `200` |
| T-A22 | `test_websocket_scope_is_rejected_without_a_token` | call `BearerAuthMiddleware(inner)` directly with `scope={"type":"websocket","path":"/ws","headers":[]}`, a fake `send` collecting messages, and an `inner` that sets a flag | `send` received exactly `{"type":"websocket.close","code":4401}`; the flag is **False** (the inner app was never called) — this is R-A3's regression guard. **F14:** this asserts the ASGI message only; a real uvicorn surfaces a pre-accept close to the client as HTTP 403, which the test does not (and cannot at this level) check |
| T-A22b | `test_db_lock_returns_503_not_401` (F5) | monkeypatch `verify_bearer` to raise `VerifyUnavailable`; `GET /api/health` with any header | `503`, `Retry-After: 1`, body `{"ok": false, "error": "service unavailable …"}` — a busy database is not a wrong token |

### `tests/unit/test_bind.py` — 11 tests

| # | Function | Input | Expected |
|---|---|---|---|
| T-A23 | `test_is_loopback_table` | `127.0.0.1`, `127.5.5.5`, `localhost`, `LOCALHOST`, `::1` → True; `0.0.0.0`, `100.64.1.2`, `192.168.1.10`, `""` → False | as stated (`""` is False; the empty case is handled by the default before `is_loopback` is called) |
| T-A24 | `test_default_is_loopback` | no `JARVIS_BIND_HOST`, auth on, zero tokens | `"127.0.0.1"` — **no refusal**, because loopback needs no token |
| T-A25 | `test_auth_disabled_forces_loopback` | `JARVIS_BIND_HOST=0.0.0.0`, `JARVIS_AUTH_ENABLED=false` | returns `"127.0.0.1"`; caplog contains `bind_forced_loopback` and the string `0.0.0.0`. **This is the brief's required fail-closed test.** |
| T-A26 | `test_non_loopback_without_tokens_refuses` | `JARVIS_BIND_HOST=100.64.1.2`, auth on, empty table | `BindRefused`, message contains `python -m jarvis.auth add` |
| T-A27 | `test_non_loopback_with_only_revoked_tokens_refuses` | add 1, revoke it | `BindRefused` |
| T-A28 | `test_non_loopback_with_active_token_and_assigned_host_binds` | one active token; monkeypatch `_host_is_bindable` → `True` | returns `"100.64.1.2"`; caplog has `bind_resolved` and `active_tokens=1` |
| T-A29a | `test_unassigned_host_falls_back_to_loopback_by_default` (F8) | one active token; `JARVIS_BIND_STRICT` unset; monkeypatch `_host_is_bindable` → `False`, `time.sleep` → no-op, `time.monotonic` → a fake advancing 1 s per call | returns `"127.0.0.1"` (NOT a refusal); caplog contains `bind_fell_back_to_loopback` and `reason=interface_absent`; the fake clock advanced at least `BIND_WAIT_S` |
| T-A29b | `test_unassigned_host_refuses_when_strict` (F8) | same but `JARVIS_BIND_STRICT=true` | `BindRefused`, message mentions `tailscale status` and `JARVIS_BIND_STRICT` |
| T-A29c | `test_no_token_refuses_even_when_not_strict` (F8) | `JARVIS_BIND_HOST=100.64.1.2`, auth on, empty table, `JARVIS_BIND_STRICT` unset | `BindRefused` — the "no unrevoked token" case is a security condition and refuses in both modes, never falls back |
| T-A30a | `test_sidecar_main_exits_2_on_refusal` | `JARVIS_BIND_HOST=100.64.1.2`, auth on, empty table; monkeypatch `uvicorn.run` to raise `AssertionError("must not bind")`; call `admin_server.main()` | `pytest.raises(SystemExit)` with `.code == 2`; `uvicorn.run` never called |
| T-A31a | `test_resolve_port_table` | unset → default; `"7999"` → 7999; `"abc"` → default + logged; `"0"` / `"70000"` → default + logged | as stated |

### `tests/unit/test_service_token.py` — 8 tests

| # | Function | Input | Expected |
|---|---|---|---|
| T-A29 | `test_admin_client_sends_bearer` | monkeypatch `httpx.Client` with a recorder; `JARVIS_SERVICE_TOKEN=jvt_svc`; construct `AdminClient()` | the recorder's `headers` kwarg `== {"Authorization": "Bearer jvt_svc"}` |
| T-A30 | `test_admin_client_sends_nothing_when_unset` | same, env unset | `headers == {}` |
| T-A31 | `test_the_three_admin_calling_servers_declare_the_token` | parse `mcp_servers/{mcp_selfedit,mcp_web,mcp_apps}/skill.yaml` | `"JARVIS_SERVICE_TOKEN" in requires_env` for each. Asserts **membership**, not the full list, so it passes whether or not the hardening plan has landed |
| T-A31b | `test_web_still_requires_tavily` (F2) | parse `mcp_servers/mcp_web/skill.yaml` | `"TAVILY_API_KEY" in requires_env` — a whole-list overwrite that dropped it (the F2 defect) fails here rather than silently degrading `web_search` under T4a scoping |
| T-A32 | `test_no_other_server_declares_the_token` | parse every other `mcp_servers/*/skill.yaml` | `"JARVIS_SERVICE_TOKEN" not in requires_env` — K2's whole point is that `mcp_time` never sees it (a **manifest** fact) |
| T-A32b | `test_service_token_is_not_in_a_scoped_child_env` (CP-F6/F3) | patch/spawn `SkillRegistry._start_server` (or call `build_child_env` directly) for every server outside the three, with `JARVIS_SERVICE_TOKEN=jvt_svc` in `os.environ` | `"JARVIS_SERVICE_TOKEN"` is **absent** from the child env of `mcp_time`/`mcp_screen`/… — proves the **environment**, not just the manifest, so the leak F3 describes (all twelve children inheriting the token when scoping is off) cannot ship green. If `build_child_env` does not yet exist (T4a not landed), this test is the tripwire — see T-A34b |
| T-A34b | `test_registry_scoping_precondition_holds` (CP-F7) | read `jarvis/skills/registry.py` source | assert it does **not** contain `env = dict(os.environ)` — a hard assertion that T4a landed first (§0 constraint 11). Fails CI if REMOTE is landing before SEC, rather than silently handing the token to every child |
| T-A33a | `test_each_watcher_sends_the_bearer` | parametrized over the three `_default_fetch_*`; monkeypatch `httpx.AsyncClient` with a recorder; `JARVIS_SERVICE_TOKEN=jvt_svc` | each recorded `get` carries `headers={"Authorization": "Bearer jvt_svc"}`, calls `raise_for_status()` (F11), and hits the expected path (`/api/plan/job`, `/api/research/job`, `/api/selfedit/run`) |

### `tests/unit/test_bot_server.py` — 6 tests

| # | Function | Input | Expected |
|---|---|---|---|
| T-A20 | `test_runner_still_exposes_a_module_level_app` | `from pipecat.runner.run import app; isinstance(app, FastAPI)` | `True`. **This is A10's Check B1 as a permanent test** — it turns a future Pipecat upgrade that removes the seam into a red test rather than a silently unauthenticated bot |
| T-A33 | `test_install_auth_registers_the_middleware` | `jarvis.bot.server.install_auth()` | `BearerAuthMiddleware` in `[m.cls for m in runner_app.user_middleware]` |
| T-A34 | `test_install_auth_is_idempotent` | call it three times | exactly one `BearerAuthMiddleware` entry |
| T-A35 | `test_caller_host_and_port_cannot_widen_the_bind` (F7) | `build_argv("127.0.0.1", 7860)` with `sys.argv = ["bot.py","--host","0.0.0.0"]`, then parse the result | parsed host is `127.0.0.1` (the gated value), not `0.0.0.0`; also `sys.argv=["bot.py","--host=0.0.0.0","--port=9999"]` → parsed host `127.0.0.1`, port `7860`; and `sys.argv=["bot.py","-v"]` preserves `-v`. **Measured 2026-08-27:** all three cases resolve to the gated host/port. |
| T-A36 | `test_bot_main_exits_2_on_bind_refusal` | `JARVIS_BIND_HOST=100.64.1.2`, auth on, empty token table; monkeypatch `runner_main` to raise | `SystemExit(2)`; `runner_main` never called |
| T-A37 | `test_bot_route_inventory_is_what_the_plan_says` (F4) | after a controlled `_configure_server_app` against a throwaway `FastAPI()` with `args` matching Jarvis's invocation, collect `{(method, path)}` from `app.routes` **including `starlette.routing.Mount`** (a `Mount` is not an `APIRoute`, so a naive `APIRoute`-only collection would miss `/client`) | equals the http+ws set enumerated in §1.3 for the transports installed, with an explicit expected set for `pipecat-ai-prebuilt` **present** (`/client` mount + `GET /` — the pinned state, `requirements-lock.txt:113`) and, as a parametrized variant, for it absent. Skipped with `pytest.importorskip` for any transport extra that is not installed |

### Existing suites that must stay green, unchanged

`tests/unit/test_admin_api.py` (including `:45` and `:145`, which call `/api/health` with no header) passes because of `tests/conftest.py`'s autouse `JARVIS_AUTH_ENABLED=false`. `tests/unit/test_mcp_selfedit_logic.py` passes because `AdminClient` is injected as a fake in those tests and `service_headers()` returns `{}` when the env is unset. `tests/integration/test_mcp_servers.py`'s `EXPECTED_TOOLS` and `TOTAL_TOOLS` are **unchanged** — A13 adds no tool.

---

## §8 Verification Larry runs on his hardware

The sandbox has no Keychain, no network, no Xcode, no microphone, no `fastapi`, and no second device. Everything below is Larry's.

**V1 — mint the service token and the client tokens.**
```bash
cd ~/jarvis-voice-ai-clean
python scripts/init_db.py                     # applies 0034_client_tokens
python -m jarvis.auth add service-bot         # copy the jvt_… line
python -m jarvis.vault set JARVIS_SERVICE_TOKEN   # paste it; value is prompted
python -m jarvis.auth add larry-macbook
python -m jarvis.auth add larry-iphone
python -m jarvis.auth list                    # 3 rows, all active, no hashes shown
```
Pass: `list` shows three `active` rows and prints no 64-character hex string.

**V2 — the stack still works on loopback, with auth on.**
```bash
./scripts/mortimer.sh
curl -s http://localhost:7861/api/health                          # expect 401
curl -s -H "Authorization: Bearer $TOK" http://localhost:7861/api/health   # {"ok":true}
```
Then open the console, put `larry-macbook`'s token into the drawer's **Agents → Dev → Access token** field, press Save, reload, and press Connect. Pass: a voice session starts, the Repo/Edit/Memory/Runs tabs load, and a delegation that uses `selfedit_status` returns a real answer (that proves the MCP child's `AdminClient` got the token through K2's `requires_env`).

**V3 — the negative case in the console.** Press **Clear** on the token field, reload, and press Connect. Pass: exactly **one** chip reading `Token required — Dev tab` appears and auto-dismisses after ~4s; no repeated toasts; the network tab shows no retry of the failed request.

**V4 — Tailscale (the tunnel). Run in this order.**
1. `brew install --cask tailscale` on the host; launch it; sign in with Larry's identity.
2. Install Tailscale on the iPhone and the MacBook and sign in with the **same** identity.
3. On the host: `tailscale up` (accept the defaults; do **not** pass `--advertise-exit-node`, do **not** enable Tailscale SSH — nothing here needs it).
4. `tailscale ip -4` → note the `100.x.y.z` address. `tailscale status` should list the phone and the MacBook.
5. In the Tailscale admin console, turn **MagicDNS** on. The host is then `<hostname>.<tailnet>.ts.net`.
6. **Confirm Funnel is off:** `tailscale funnel status` must print that no funnel is configured. If it prints anything else, `tailscale funnel reset`. Funnel publishes the service to the public internet, which is exactly what roadmap R5 exists to prevent (A16).
7. Confirm the tailnet ACL is the single-user default (`"acls": [{"action":"accept","src":["*"],"dst":["*:*"]}]`) and that **no** device belongs to anyone else — the ACL is the only thing standing between "a device Larry owns" and "a device on the tailnet".

**V5 — go remote, fail-closed first.**
```bash
# a) prove the refusal, with auth deliberately off
JARVIS_BIND_HOST=100.x.y.z JARVIS_AUTH_ENABLED=false .venv/bin/python -m jarvis.admin.server
#    expect: an ERROR line 'bind_forced_loopback ... requested=100.x.y.z' and a bind on 127.0.0.1

# b) prove the refusal, with auth on but no tokens (use a scratch DB)
JARVIS_DB_PATH=/tmp/empty.db JARVIS_BIND_HOST=100.x.y.z .venv/bin/python -m jarvis.admin.server; echo "exit=$?"
#    expect: 'bind refused: ... no unrevoked client token exists' and exit=2

# c) the real thing
echo 'JARVIS_BIND_HOST=100.x.y.z' >> .env
./scripts/mortimer.sh
```
Pass: (a) forces loopback with the logged reason, (b) exits **2**, (c) starts and `lsof -nP -iTCP -sTCP:LISTEN | grep -E '7860|7861'` shows the two ports bound to `100.x.y.z` and to **nothing else** — in particular not to the LAN address.

**V5b — the port-scan gate (roadmap G2(d)).** From another machine on the same **Wi-Fi** (not the tailnet): `nmap -Pn -p 7860,7861 <the host's LAN 192.168.x.x>` → both `closed`/`filtered`. From the MacBook **on the tailnet**: `nmap -Pn -p 7860,7861 100.x.y.z` → both `open`, and `curl -s http://100.x.y.z:7861/api/health` → `401`, and the same with `-H "Authorization: Bearer $LARRY_MACBOOK_TOKEN"` → `{"ok":true}`.

**V5c — the live remote session (roadmap G2(c)).** On the MacBook, set the console's `VITE_JARVIS_ADMIN_URL=http://100.x.y.z:7861` and `VITE_JARVIS_BOT_URL=http://100.x.y.z:7860`, rebuild, enter `larry-macbook`'s token, Connect. Pass: a full voice turn with barge-in, and the Runs tab loads. **Check the browser network tab shows `Authorization: Bearer …` on BOTH `POST /api/offer` and `PATCH /api/offer`** (F10 — the trickle-ICE PATCH must carry the header too, or ICE trickling 401s and the connection degrades looking like a network fault). Then `python -m jarvis.auth revoke larry-macbook` on the host and reload: every call 401s **immediately**, with no restart of either process (this is the no-cache decision, A6, verified live).

**V6 — the Mac shell's token (CP-F15 convention).**
```bash
# service is com.mortimer.jarviskit; account is the bot URL "<scheme>://<host>:<port>"
security add-generic-password -s com.mortimer.jarviskit -a "http://100.x.y.z:7860" -w   # value prompted
defaults write com.mortimer.shell JARVIS_ADMIN_URL http://100.x.y.z:7861   # optional
```
Pass: the shell posts location successfully (grep `logs/admin.log` for a 200 on `/api/location`). With the Keychain item deleted, the shell logs `skipping location report — no client token stored` and everything else still works. **NATIVE's JarvisKit reads the same item** (service `com.mortimer.jarviskit`, account = bot URL), so this single command provisions both readers.

**V7 — build the shell.** `./scripts/build_shell.sh` (macOS-only; `swift build`). Pass: compiles. Nothing in this plan was compiled in the sandbox.

**V8 — Larry's own commit (C8/A14, via `ALLOWLIST_SEQUENCE.md`).** Apply **row W1 of `docs/plans/ALLOWLIST_SEQUENCE.md`** (the SEC-owned reconciled sequence): add `"jarvis/auth.py"`, `"jarvis/authmw.py"`, `"jarvis/bind.py"` to `config/self_edit_allowlist.json`'s `deny`, then run that row's verify command. Then `pytest tests/unit/test_auth.py -q -s` and confirm the `WARNING: not yet on the self-edit deny list` line is gone.

**V9 — routing eval (C7).** `RUN_LIVE=1 python -m tests.evals.routing_eval`. Expected: unchanged from the pre-merge baseline, ≥ 90 %. It is run because the eval starts a `SkillRegistry` and three `skill.yaml` manifests changed. **Record the score in the PR description.**

**V10 — full suite.** `pytest tests/unit tests/integration -q`. Expected: previous count + **60** new unit tests (23 + 12 + 11 + 8 + 6) + 1 in `test_db.py`, all green.

**Branch:** `feat/remote-access-t2`. Larry commits; the implementer never runs git.

---

## §9 Rollback

**Kill switch.** `JARVIS_AUTH_ENABLED=false` in `.env`, then `./scripts/mortimer.sh`. Effect, all at once and by construction:
- `jarvis/authmw.py`'s `__call__` returns early before any header inspection → every route accepts unauthenticated calls exactly as before this plan.
- `jarvis/bind.py`'s `resolve_bind_host` returns `127.0.0.1` **regardless of `JARVIS_BIND_HOST`**, with a logged `bind_forced_loopback` if a remote bind was requested. Turning authentication off can never leave a port open — that is the whole point of putting both behaviours behind one switch.
- `service_headers()` still returns a header if `JARVIS_SERVICE_TOKEN` is set; a server that ignores it does not care. Nothing has to be unset.

**Partial rollback — keep auth, close the tunnel.** Remove `JARVIS_BIND_HOST` from `.env` and restart. Both processes return to `127.0.0.1`; tokens keep working.

**Rotating the service token (F21).** The service token is the one credential every internal caller shares, and A2 forbids reusing a name, so rotation is a four-step sequence — and **both long-lived processes must be restarted**, because `AdminClient.__init__` captures `service_headers()` once for the life of the process (A5); an MCP child keeps the old header until the registry restarts it:

```bash
python -m jarvis.auth add service-bot-2          # mint the replacement
python -m jarvis.vault set JARVIS_SERVICE_TOKEN  # paste the new plaintext
python -m jarvis.auth revoke service-bot         # retire the old name
./scripts/mortimer.sh                            # restart bot + sidecar so children re-read
```

Until the restart, an MCP child (`mcp-selfedit`/`mcp-web`/`mcp-apps`) sends the *old* token and 401s; `jarvis/bot/pipeline.py`'s clipboard calls build a fresh `AdminClient` per call and pick up the new one immediately — the asymmetry is expected, and the restart resolves it.

**Danger: `JARVIS_ENV_SCOPING_ENABLED=false` leaks the service token after this plan lands (CP-F6).** Once T4a's env scoping is in place, `JARVIS_SERVICE_TOKEN` reaches only the three servers that declare it. Setting `JARVIS_ENV_SCOPING_ENABLED=false` (SEC's kill switch) reverts the registry to `dict(os.environ)`, which hands the service token — a credential that authorises `POST /api/selfedit/run` — to **all twelve MCP children**, including `mcp-web` and `mcp-screen`, the two that handle untrusted external content. Before setting that switch, either revoke the service token (`python -m jarvis.auth revoke service-bot`) or set `JARVIS_AUTH_ENABLED=false` as well; re-mint after re-enabling scoping. SEC owns the kill-switch row that states this in its own §9; this note is the mirror REMOTE carries (`CROSS_PLAN_RESOLUTION.md` §C F6).

**Reverting the data change.** Migration `0031` is additive: one new table and one index, no `ALTER` on an existing table. Reverting the code leaves the table in place, unread and harmless — that is the intended revert path and requires no SQL. If Larry wants it gone:

```sql
DROP TABLE IF EXISTS client_tokens;
DELETE FROM migrations WHERE id = '0034_client_tokens';
```

(run against `data/jarvis.db` with the stack stopped; `run_migrations()` will recreate it on the next start if the code is still present). **Do not** delete the migration tuple from `jarvis/db.py` without also deleting the row — a machine that applied 0031 and then loses the constant would silently skip nothing, but a machine that has the row and not the constant is a state no other migration in this file can be in.

**Reverting the code.** `git revert` the merge commit. `jarvis/db.py`'s `MIGRATION_0034` should be left in place even then (previous paragraph); every other file in §4 reverts cleanly because nothing else in the repo imports `jarvis.auth`, `jarvis.authmw`, or `jarvis.bind` except the files this plan edits.

**The one thing that does not roll back.** Tokens Larry has already put on his phone. Revoking them (`python -m jarvis.auth revoke <name>`) is instant and needs no restart (A6, verified by V5c), but the plaintext is on the device until he deletes it there.

---

## §10 Risks

| # | Risk | Likelihood | Impact | Mitigation / detection |
|---|---|---|---|---|
| R1 | A Pipecat upgrade removes the module-level `app`, silently returning the bot to unauthenticated | Low | **Critical** | T-A20 fails loudly on upgrade; A10's Branch B is pre-written; §0.4 forbids forking as the escape hatch |
| R2 | An implementer uses `@app.middleware("http")` and leaves four WebSocket routes open | Medium (it is the obvious move) | **Critical** | R-A3 states it; A6 explains it; T-A22 fails if the middleware cannot see a websocket scope |
| R3 | A new sidecar route is added later and someone assumes middleware coverage without checking | Medium | High | T-A14 asserts the exact route count (62); adding a route fails the test until the author looks |
| R4 | `JARVIS_SERVICE_TOKEN` does not reach an MCP child, so voice self-edit breaks with a 401 that gets narrated as "the sidecar is offline" | Medium | Medium | K2's `requires_env` (Step 6d) plus T-A31/T-A32; `AdminClient`'s error text already says "looks offline", which would be a fabrication in this case — the 401 body says `unauthorized`, and `classify_tool_result` marks it failed. V2 exercises the real path |
| R5 | Larry mints a token, does not store it in the vault, and the whole stack 401s itself | Medium | Medium | `service_headers()` returns `{}` rather than raising, so the failure is a clean 401 with a clear body, not a crash; V1 orders the steps; `scripts/check_skills.py` names the missing variable |
| R6 | Tailscale is down/late, so the requested bind host is absent — refusing would brick local voice too (F8) | Medium | Medium | Default `JARVIS_BIND_STRICT=false` falls back to `127.0.0.1` with a loud `bind_fell_back_to_loopback` ERROR after `BIND_WAIT_S`=20 s, losing remote access not security; `mortimer.sh`'s health probe (F6, sleep 25 s > 20 s) surfaces the fallback. Strict operators set `JARVIS_BIND_STRICT=true` for the hard refusal. The "no unrevoked token" case still refuses in both modes |
| R7 | Someone runs `tailscale funnel` "to test from outside" | Low | **Critical** | A16 names it as forbidden; V4 step 6 checks it explicitly; there is no step in this plan that requires it |
| R8 | A token leaks (screenshot, paste, backup) | Low | High | Revocation is instant and needs no restart (V5c). No expiry exists (§2.3), which is the accepted cost of not building a rotation lifecycle in T2 |
| R9 | The console's `localStorage` token is readable by any script the console loads | Certain | Medium | Accepted: the console is retired at T1.4, it loads no third-party script, and A12 is explicitly minimal. T1's Keychain storage is the fix |
| R10 | `verify_bearer` blocks the event loop and answers 401 under write-lock contention (F5) | ~~Medium~~ Low (fixed) | ~~Medium~~ Low | The verdict is decided by a WAL `SELECT` that never blocks on a writer; the `last_used_at` write is best-effort/throttled in its own `try/except` and cannot change the answer; a `busy_timeout` of 250 ms and a `VerifyUnavailable`→503 path mean a busy database is never reported as a wrong token. **Measured:** identity returned in 0.00 s under a held write lock (the old code blocked 5.01 s then returned `None`). Still no cache — revocation stays instant (A6) |
| R11 | A "helpful" future edit exempts `/api/health` or adds a loopback bypass | Medium | **Critical** | A4 states there are zero exemptions and why; T-A15b and T-A16b fail; A14's deny-list entries keep the assistant out of the three modules |
| R12 | The autouse `JARVIS_AUTH_ENABLED=false` fixture masks a real auth regression across the suite | Medium | Medium | The three auth test files re-enable it in their own fixtures, and T-A14 exercises all 64 routes with auth ON. The fixture buys 1538 unchanged tests; the coverage lives in one file that cannot be accidentally disabled |
| R13 | `DELETE /api/memory/fact/{key}` was never CORS-preflightable and now is | Certain (Step 4) | Low | Deliberate, stated in Step 4. It was a pre-existing defect; the route already required no auth, so nothing is newly reachable that was not reachable by a non-browser client |
| R14 | Media takes the LAN path rather than the tunnel and someone reads that as a leak | Medium | None | A16 explains it: DTLS-SRTP keys come from the authenticated signalling channel; the media is encrypted regardless of path |
| R15 | After this plan lands, `JARVIS_ENV_SCOPING_ENABLED=false` hands the service token to all twelve MCP children (CP-F6) | Low | **High** | §9 states the guard: revoke the service token or also set `JARVIS_AUTH_ENABLED=false` before flipping that switch, re-mint after re-enabling scoping. SEC owns the kill-switch row that carries the same warning. `test_service_token_is_not_in_a_scoped_child_env` (T-A32b) proves the scoped case; the §0.11 precondition + T-A34b prevent shipping before T4a |
| R16 | REMOTE lands before SEC's T4a, so `requires_env` scopes nothing and the token reaches every child (F3/CP-F7) | Low | **Critical** | §0 constraint 11 is a hard stop (`grep 'env = dict(os.environ)' registry.py`); T-A34b asserts the same in CI so the ordering violation is a red test, not a silent leak |

---

## §11 Self-audit — the nine-item taxonomy, walked

1. **Multi-consumer contracts named but not typed.** K1 and K5 are the two contracts this plan introduces and both are typed member-by-member: A5's table gives every `jarvis/auth.py` symbol with its full signature, its return type, and its `None` semantics (including the F5 additions `VerifyUnavailable` and `LAST_USED_THROTTLE_S`); A6 gives the middleware's exact rejection responses (401 headers/body, the 503 lock path, the WebSocket close code and its F14 caveat); A8 gives `resolve_bind_host` as a seven-row decision table (with the `JARVIS_BIND_STRICT` column, F8) with no gaps; A11 gives K5's two env names, two defaults, two accessors. `ClientIdentity` is specified as `frozen=True` with both fields typed. The `client_tokens` schema is given as literal DDL and every column's nullability is asserted in a test (Step 1). The one thing K1 leaves ambiguous — whether `verify_bearer` closes a connection it was handed — is answered explicitly in A5 and in the code's docstring ("never closes a connection it was handed").
2. **Lifecycle left implicit.** Three lifecycles were checked. (a) *Token*: minted → active → revoked; never unrevoked; a name is never reused (A2); `last_used_at` updates only on success and specifically **not** on a revoked hit (T-A14a asserts it stays NULL). (b) *Middleware*: added before startup, refused by Starlette after; `install_auth()` is idempotent because Starlette would otherwise stack two verifications (T-A34). (c) *Console token*: survives reload (localStorage), is never rendered back into the field, and `Clear` removes the key rather than storing `""`. The toast's lifecycle is stated too: one per **page load**, not one per request, not one per session — `notified` is a module-level flag that resets only on reload.
3. **How a value is applied.** Every value has a named destination: the token is applied as the `Authorization` request header (not a cookie; the runner's own one-time `?token=` mechanism is not reused — the only place a query token appears is F10's *documented fallback* if `@pipecat-ai/small-webrtc-transport` turns out to lack a `requestHeaders` field, with the stated caveat that a query token lands in access logs); `ClientIdentity` is applied to `scope["client_identity"]` (not to `request.state`, which does not exist in a raw ASGI scope); the bind host is applied as `uvicorn.run(host=...)` on the sidecar and as `sys.argv` `--host` on the bot, with A10 Branch A explaining why argv rather than a keyword; the console base URL is applied at build time through `import.meta.env`, not at runtime.
4. **Two sections describing the same behaviour differently.** Middleware ordering was the one real hazard, and after F1 it is now the **same in both processes** — CORS outermost, auth inner — so A7 states one ordering, names Starlette's `insert(0, ...)` as the reason, and the code comments in `jarvis/authmw.py`, §5 Step 4, and `jarvis/bot/server.py` all say it the same way. The `OPTIONS` branch is described once (A6, narrowed per F16) and every mention points there. Second check: the exemption question is answered in exactly one place (A4) and every later mention (§1.2's table header, R11, T-A15b) points back to it rather than restating the reasoning. Third: `requires_env` is described only by reference to `MORTIMER_SECURITY_HARDENING_PLAN.md` §3 D-H1/D-H2 and `CROSS_PLAN_RESOLUTION.md` §A — this plan never restates `BASE_ENV_KEYS` or the missing-variable warning rule.
5. **Copy and visual states named but unspecified.** Every user-visible string is literal: the 401 body (`"unauthorized - Authorization: Bearer <token> required"`), the toast (`Token required — Dev tab`, K1 verbatim), the duplicate-name refusal, the unknown-name refusal, the `list` header row and its `active`/`revoked` values, the `-` used for a NULL `last_used_at`, the input placeholder in both states (`jvt_…` when empty, `stored — enter a new token to replace` when a token exists), the Swift `skipping location report — no client token stored`, and both `BindRefused` messages. The chip's visual state is specified by reuse of the **real** class the speaker-gate notice uses — `speaker-gate-notice` on a `<span role="status">` (F9 — there is no `.attn-chip` rule in `web/src`), with a `clearTimeout` cleanup so a re-fire cannot leak a timer.
6. **Initialization timing.** Five orderings are pinned. `inject_env()` already runs at the module top of `jarvis/admin/server.py` (search `inject_env()`), before any endpoint exists — so `JARVIS_SERVICE_TOKEN` is in `os.environ` before the first request. **The service token is minted before the code merges (§5 Step 0, F11)**, so the internal surface never 401s itself in a window between merge and mint. `app.add_middleware` must precede startup, which is why `install_auth()` runs before `runner_main()` and why Step 4 adds the sidecar's `BearerAuthMiddleware` at module scope **before** the CORS block (F1). `run_migrations` is called by each CLI subcommand before its query, so `python -m jarvis.auth add` works on a database that has never been migrated. `resolve_bind_host` runs **before** `uvicorn.run`, so a refusal costs nothing and binds nothing (T-A30a asserts `uvicorn.run` is never reached).
7. **Signatures agreeing across sections; every schema column populated; every needed value derivable.** `verify_bearer(header_value, conn=None) -> ClientIdentity | None` is identical in K1, A5, the §5 Step 2 source, and the §7 tests. Schema columns: `id` (autoincrement), `user_id` (`_cmd_add` supplies `DEFAULT_USER_ID`, plus the SQL default as a backstop), `name` (CLI argument), `token_hash` (`hash_token(mint_token())`), `created_at` (`now_iso()`), `last_used_at` (`verify_bearer`), `revoked_at` (`_cmd_revoke`) — **all seven are written by some step.** Values a step needs: the bind decision needs `count_active_tokens`, which is derivable from the same table the same plan creates; the console needs `getToken()`, which is derivable from a field the same plan adds; the Swift shell needs a Keychain item, and §8 V6 gives the exact command that creates it. `EXPECTED_SIDECAR_ROUTES = 64` is derived by enumeration in §1.2 (re-verified 2026-08-27: `grep -c '@app\.'` = 48, minus one `@app.middleware`), not asserted from memory. The measured bot inventory is **16 Starlette route entries** for Pipecat 1.4.0 with the pinned prebuilt UI: four default docs routes, seven API routes, four WebSocket routes, and the `/client` mount. `tests/unit/test_bot_server.py` protects every HTTP route and mount; middleware also protects all four WebSocket paths.
8. **Judgment left to the implementer.** Searched for all three shapes. No "use your judgment": every threshold is a named constant with its value (§6). No "investigate first": the one genuine unknown — how to reach Pipecat's app — is A10's decision tree with a runnable check, two written branches, and a "report and stop" third outcome; the second unknown — whether the hardening plan landed first — is Step 6d's append rule with both end states tabulated. No bare "be careful": `jarvis/auth.py`, `jarvis/authmw.py`, and `jarvis/bind.py` are given as complete literal source, and every rejection case is a named test with its input and expected output in §7.
9. **Plan drift.** Every file mentioned in §5 appears in §4's manifest (**12 created, 27 modified paths, 0 deleted, 1 Larry commit** — recounted by counting the table rows, F12) and every §4 row names its step. `scripts/mortimer.sh` (Step 9, F6) and `tests/unit/test_db.py` (Step 1, F12) are now both listed; `docs/plans/MORTIMER_PLATFORM_ROADMAP.md` is deliberately *not* in the manifest (a shared artifact SEC edits — `CROSS_PLAN_RESOLUTION.md` §C F14). Cross-checked the "write X" versus "X exists" hazard: §5 Step 8 replaces `mcp_servers/mcp_selfedit/logic.py`'s `DEFAULT_ADMIN_URL`/`ADMIN_URL_ENV` with a re-export, and §4 lists that file once with both edits (Step 6 headers, Step 8 re-export); `jarvis/admin/server.py` carries Steps 0, 4, 9 in one row. Checked against the sibling plans and the resolution: `MORTIMER_SECURITY_HARDENING_PLAN.md` also edits `mcp_servers/*/skill.yaml` — Step 6d is an **append** rule with both pre-states tabulated (CP-F4/F2) so the two plans cannot conflict in either merge order; A14 lists exactly the three W1 entries of `ALLOWLIST_SEQUENCE.md` and does **not** deny `mcp_servers/*/skill.yaml` (CP-A keeps it editable, guarded by SEC's frozen snapshot); the migration number is guarded against MAIL's `0032` (CP-F1). Checked against the roadmap: four claims were wrong and are corrected at the top (R-A1…R-A4); the roadmap edit itself is SEC's.

---

## §12 Approval checklist

Larry ticks each before the implementer starts.

- [ ] **A1** — token format `jvt_` + 43 base64url chars, SHA-256 hex stored in `data/jarvis.db`, plaintext shown once. *(Overrides the roadmap's "stored in the vault" — R-A1.)*
- [ ] **A2** — a token name is never reused, revoked or not; rotation means a new name.
- [ ] **A4** — **zero** exempt routes on the sidecar, `/api/health` included, loopback included. Accepts that `curl http://localhost:7861/api/health` now needs a header.
- [ ] **A6/A7** — one pure-ASGI middleware shared by both processes, covering `http` **and** `websocket` scopes; **CORS outermost in both** so a 401 is browser-readable (F1); a busy database returns 503, not 401 (F5).
- [ ] **A8** — a non-loopback bind requires auth on **and** at least one unrevoked token **and** the address actually assigned; a missing address falls back to loopback with a loud ERROR by default (`JARVIS_BIND_STRICT=true` refuses instead, F8); the "no token" case always refuses (exit 2). `JARVIS_AUTH_ENABLED=false` forces `127.0.0.1`.
- [ ] **A10** — Pipecat is not forked; the bot wraps the runner's own module-level `app`. Branch B is a contingency only.
- [ ] **A12** — the web console gets one `api.ts`, one password field under a `Dev` heading in the Agents tab, and one toast. Nothing more; the console is retired at T1.4.
- [ ] **A13** — token management stays CLI-only: no MCP tool, no HTTP endpoint, no console mutation. `TOTAL_TOOLS` unchanged.
- [ ] **A14** — Larry adds the **three** entries `jarvis/auth.py`, `jarvis/authmw.py`, `jarvis/bind.py` to the self-edit deny list (his commit, §8 V8, = row W1 of `ALLOWLIST_SEQUENCE.md`). `mcp_servers/*/skill.yaml` stays editable, guarded by SEC's frozen snapshot (CP-A).
- [ ] **A15** — the Mac shell reads its token from the login Keychain and **skips** location reporting when there is none.
- [ ] **A16** — Tailscale, bound to the `100.x.y.z` address specifically (not `0.0.0.0`), Funnel forbidden, no TLS inside the tunnel.
- [ ] **§2** — accepts the non-goals, in particular: no token expiry, no scopes, no rate limiting, no per-request audit log.
- [ ] **§5 Step 5** — accepts that the unit suite runs with `JARVIS_AUTH_ENABLED=false` by default and that auth coverage lives in three dedicated files.
- [ ] **§8** — will run V1–V10 on his own hardware, including the `nmap` gate (V5b) and the live revocation check (V5c), and will record the routing-eval score (V9) in the PR.
- [ ] Branch name `feat/remote-access-t2`; Larry commits, the implementer never runs git.

---

## Addendum R1 (2026-09-27): make T2 merge-safe against main, and dormant by default

**Status:** direction approved by Larry, 2026-09-27 ("move forward … with the recommended fixes"). **Owner:** Codex (`ROADMAP.md` WS-04). **Author:** Claude (Cowork), from a read-only review of `main` `0b76f49` and Codex's worktree `codex/isolated-20260924`. Evidence: `docs/reviews/CROSS_SYSTEM_PLAN_EVAL_2026-09-27.md` §7 and `ROADMAP.md` CX-11.

**What this addendum decides.** T2 code may merge to `main`, but only **dormant**: after the merge, Mortimer behaves exactly as it does today. Turning T2 on is a separate, undecided roadmap item for Larry, and so is how tokens get created without shell commands (R1.9). Nothing in this addendum opens a port or turns authentication on.

**Where this addendum overrides the plan above:**
- K1's "`JARVIS_AUTH_ENABLED` defaults to true" becomes **defaults to false** (R1.2).
- The §1.2 route inventory must be recounted on the merged tree (R1.6).
- The client-token migration id becomes `0034` (R1.7).

Everything else stands.

### R1.1 Preconditions

1. WS-01 has merged `origin/main` into `codex/isolated-20260924` (`ROADMAP.md` CX-01). Every step below edits the **merged** tree. None of them applies to Codex's pre-merge tree, which lacks the main files named here.
2. Record a baseline receipt before editing: `pytest tests/unit -q`, `pytest tests/integration -q` and `python -m unittest discover -s tests/ci`, with counts, on the merged tree.

### R1.2 Auth is dormant unless explicitly enabled

**Why.** In Codex's tree, `jarvis/auth.py` `auth_enabled()` returns true unless the variable is exactly `"false"`. `jarvis/authmw.py` then rejects every HTTP and WebSocket request without a valid token, loopback included, with no exempt route. `.env.example` does not set the variable, and production's `.env` has never had it. Merged as written, the first deploy would turn auth on, and the callers in R1.3–R1.4 would start failing. [certain from the code; not run]

**Change, `jarvis/auth.py`:**

```python
def auth_enabled() -> bool:
    """JARVIS_AUTH_ENABLED, default FALSE (Remote Access plan Addendum R1).

    T2 ships dormant: only the exact string "true" (case-insensitive,
    stripped) turns authentication on. Larry decides when that happens.
    Typos ("1", "yes", "ture") leave it OFF, and OFF also forces a loopback
    bind (jarvis/bind.py), so a typo can never expose a port: the safe
    direction is preserved by the bind rule, not by this default.

    THE ONLY READ OF THIS NAME IN THE CODEBASE (roadmap kill-switch rule).
    """
    return os.environ.get(ENABLED_ENV, "").strip().lower() == "true"
```

**Change, `tests/unit/test_auth.py` `test_auth_enabled_table`:** the new table is
`(None, False), ("", False), ("true", True), ("TRUE", True), (" true ", True), ("false", False), ("1", False), ("yes", False), ("on", False)`.

**Add, `tests/unit/test_bind.py`:** `test_unset_auth_forces_loopback_even_when_remote_requested`. Delete `JARVIS_AUTH_ENABLED`, set `JARVIS_BIND_HOST=100.64.1.2`, and expect `resolve_bind_host(...) == "127.0.0.1"`. This proves that the dormant default cannot expose a port.

**Unchanged:** the tests that set `JARVIS_AUTH_ENABLED=true` explicitly (`test_auth_middleware.py`, `test_bind.py`) keep passing as written.

**`.env.example`:** add a commented line under the existing service section, with no value set:
`# JARVIS_AUTH_ENABLED=true   # Remote access (T2). Off unless set to "true". Larry decides when.`

### R1.3 Service token on the internal caller that exists only on main

**Why.** `jarvis/bot/status_tool.py` came in with #86 and does not exist in Codex's tree. Its `_default_client` builds `httpx.AsyncClient(base_url=base_url, timeout=timeout)` with no headers. With auth on, `system_status` would answer "the admin sidecar is not reachable". [certain]

**Change, `jarvis/bot/status_tool.py`:**

```python
def _default_client(base_url: str, timeout: float) -> Any:
    import httpx
    from jarvis.auth import service_headers  # K1: every internal caller

    return httpx.AsyncClient(base_url=base_url, timeout=timeout,
                             headers=service_headers())
```

**Test, `tests/unit/test_service_token.py`:** add `test_status_tool_default_client_sends_service_token`. With `JARVIS_SERVICE_TOKEN=jvt_test`, `status_tool._default_client("http://x", 1.0).headers["Authorization"] == "Bearer jvt_test"`. With the variable unset, there is no `Authorization` header.

### R1.4 Keep both sides in the two callers changed on both branches

| File | Main has (keep) | Codex has (keep) |
|---|---|---|
| `jarvis/bot/progress_watcher.py` | Main's current content (changed in the 09-25 landing) | `from jarvis.auth import service_headers`, `headers=service_headers()` and `resp.raise_for_status()` in `_default_fetch_selfedit_job` |
| `mcp_servers/mcp_selfedit/logic.py` | Main's current content (31.6 KB, changed in the 09-25 landing) | `headers=service_headers()` on `AdminClient`'s `httpx.Client`, and `ADMIN_URL_ENV` / `DEFAULT_ADMIN_URL` imported from `jarvis.urls` |

`jarvis/bot/plan_watcher.py` and `jarvis/bot/research_watcher.py` are unchanged on main since August, so Codex's versions merge cleanly.

`mcp_selfedit/logic.py` must keep exporting `ADMIN_URL_ENV` and `DEFAULT_ADMIN_URL`, because main's `status_tool.py`, `plan_watcher.py`, `progress_watcher.py` and `research_watcher.py` import them from there. A re-export from `jarvis.urls` is fine.

### R1.5 A guard so future Claude or Codex code can't add an unauthenticated caller

**Add `tests/unit/test_internal_callers_authenticated.py`.** It scans `jarvis/`, `mcp_servers/` and `scripts/*.py` (tests excluded) for files that both

- name the sidecar or bot (`ADMIN_URL_ENV`, `DEFAULT_ADMIN_URL`, `admin_url(`, `bot_url(`, `127.0.0.1:7861`, `127.0.0.1:7860`), **and**
- construct an HTTP client (`httpx.Client(`, `httpx.AsyncClient(`, `urlopen(`, `urllib.request.Request(`).

Every such file must also contain `service_headers`.

One file is allow-listed, with its reason in the test: `jarvis/status/services.py`. It probes the bot by bare TCP connect and probes the vault and costs services, which T2 does not cover.

Run against main's files on 2026-09-27, this rule flags `jarvis/bot/status_tool.py`, `plan_watcher.py`, `progress_watcher.py`, `research_watcher.py`, `mcp_servers/mcp_selfedit/logic.py` and `jarvis/status/services.py` (allow-listed). After the merge and R1.3–R1.4, only the allow-listed file may match. [certain for the files checked; the rule was dry-run over the main files staged for this review, not the whole tree. The test itself covers the whole tree]

### R1.6 DEPLOY-MAIN health checks work with auth on or off

**Why.** `scripts/deploy_main.sh` phase D requires 200 from `http://127.0.0.1:7861/api/health` and 200/307 from `http://127.0.0.1:7860/`, both via plain `curl`. With auth on, both answer 401, and the deploy stops with "services did not come healthy". [certain from the script; not run]

**Add `scripts/service_health.py`** (stdlib only; prints nothing but the status code):

```python
"""Print the HTTP status of Mortimer's admin sidecar or bot, authenticated
with the service token when one exists (Remote Access plan Addendum R1.6).
Usage: python scripts/service_health.py admin|bot. Prints only the code; never
prints a header or a token. Prints 000 when the service does not answer."""
import os, sys, urllib.error, urllib.request
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from jarvis.auth import service_headers
from jarvis.vault import inject_env

TARGETS = {"admin": ("JARVIS_ADMIN_PORT", 7861, "/api/health"),
           "bot": ("JARVIS_BOT_PORT", 7860, "/")}

def main() -> None:
    env, default, path = TARGETS[sys.argv[1]]
    inject_env()
    url = f"http://127.0.0.1:{int(os.environ.get(env, default))}{path}"
    req = urllib.request.Request(url, headers=service_headers())
    # No proxy: a system proxy must never see the service token or reroute localhost.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect)
    try:
        code = opener.open(req, timeout=3).status
    except urllib.error.HTTPError as exc:
        code = exc.code
    except Exception:  # noqa: BLE001 - not listening yet
        code = 0
    print(f"{code:03d}")

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # keep the bot's 307 visible
        return None

if __name__ == "__main__":
    main()
```

**Change, `scripts/deploy_main.sh` phase D.** Keep the vault `curl` as it is, and read the admin and bot codes from the new script, run with production's interpreter from production's checkout:

```bash
a=$(cd "$C" && "$PY" scripts/service_health.py admin); v=$(hcode http://127.0.0.1:8484/health); b=$(cd "$C" && "$PY" scripts/service_health.py bot)
```

The pass condition is unchanged: admin 200, vault 200, bot 307 or 200.

**Allow-list:** `scripts/service_health.py` is human-only, like `deploy_main.sh`. Add it through a new row in `docs/plans/ALLOWLIST_SEQUENCE.md`. Rule C8 still applies: allow-list changes are human commits.

**Tests, `tests/unit/test_deploy_main.py`:**
- `test_phase_d_does_not_curl_the_sidecar_or_bot_directly` (the script text contains no `curl` of `127.0.0.1:7861` or `127.0.0.1:7860`).
- `test_service_health_prints_only_a_code`: run it against a stub HTTP server that answers 401 and 200. The output matches `^\d{3}
$`, and it never contains `Bearer`.

**Optional, same change:** have `scripts/mortimer.sh` `check_admin` call `service_health.py admin`, so there is one implementation.

`deploy_main.sh` was written by Claude (WS-07, landed). Codex edits it here under WS-04, and Larry reviews that hunk in the PR.

### R1.7 Migration id and route inventory

- **Migration:** rename the unshipped `0031_client_tokens` to reserved `0034_client_tokens` (`ROADMAP.md` §3). The cross-plan guard in §0.7 and CP-F1 is "REMOTE owns `0034_client_tokens`; MAIL reserves `0035`". This renumbering is complete and applied in production as of 2026-09-28; do not repeat it. Under the dormant default the table is created but unused, which is additive and harmless.
- **Route inventory:** after the merge, the sidecar has main's 10 routes that Codex's tree lacks (`/api/status/{build,catalog,github,location,logs,models,overview,services}`, `POST /api/status/subscription/probe`, `/api/workflows`), plus Codex's own. Recount decorators on the merged tree and update §1.2's table and `EXPECTED_SIDECAR_ROUTES` in `tests/unit/test_auth_middleware.py`. By decorator count the result is about 74 (58 shared, 10 main-only, 6 Codex-only); the test's `APIRoute` count is authoritative. Better still, replace the bare number with an explicit sorted list of `(method, path)`, so a newly added route fails the test with its name rather than a count.
- `test_every_sidecar_route_requires_bearer_token` then proves that the 10 main routes also answer 401 when auth is enabled.

### R1.8 Native app: verify only

No code change. `macos/JarvisKit/Sources/JarvisKit/JarvisHTTP.swift` already sets `Authorization: Bearer` from the Keychain on every request. `AdminAPI.swift`'s `workflows()` (the Workflow Viewer) and the status calls go through that sender. [certain, read on main]
On the Mac: `swift test --package-path macos/JarvisKit` and the MortimerHost suite on the merged tree, with counts in the receipt.

### R1.9 Deferred to Larry's T2 decision (not built here)

1. **Turning T2 on:** setting `JARVIS_AUTH_ENABLED=true` and then plan §5 Step 9 (bind).
2. **Creating tokens without shell commands.** A13 makes `python -m jarvis.auth add` CLI-only, which conflicts with the no-terminal-commands principle (Voice Workflows D-L2/D-L5). The options to put in front of Larry, not decided here:
   - (a) Keep the CLI. Mortimer shows the command only when Larry explicitly asks, which D-L5 allows.
   - (b) A pairing button in the Mac app that calls a loopback-only, one-time endpoint. This reverses A13 and needs its own threat review.
   - (c) DEPLOY-MAIN mints the service token and a device token during a supervised deploy, and stores them in the vault and the Keychain.

### R1.10 Verification: done when

1. Unit, integration and `tests/ci` are green on the merged tree, and counts are in a dated receipt under `docs/acceptance/`.
2. **Dormant proof** (flag unset, no tokens): `service_health.py admin` → `200`, `service_health.py bot` → `307` or `200`, and `system_status` answers in a voice session.
3. **Enabled proof, in a test environment and never on production** (flag `true`, service token in the environment, no client tokens): `curl` to `/api/health` → 401; `service_health.py admin` → 200; `test_internal_callers_authenticated.py` passes.
4. A DEPLOY-MAIN run of the merged `main`, with the flag unset, passes phase D. This is a Larry step.
5. JarvisKit and MortimerHost suites pass on the Mac.

### R1.11 Rollback

Revert the WS-04 commits. Because auth is dormant, the runtime is unaffected either way. Migration `0034_client_tokens` is additive, and nothing reads it while auth is off, so it stays.

### 2026-09-28 — dormant integration progress (not release acceptance)

The main merge is still open. Auth now enables only for explicit `true`, with
loopback enforced while dormant. The status tool sends `service_headers()`.
The new deployment health probe uses the vault-backed header, bypasses proxies,
refuses redirects and prints only a status code. Phase D retains its existing
health pass conditions. A source guard covers internal HTTP callers.

The source inventory is 79 sidecar decorators including all ten main status/
workflow paths. The whole-app route test is updated but has not run because
shared memory imports remain conflicted. Local auth/bind/service-token checks
pass (79 tests); native merged suites, real dormant/enabled test-environment
proof and Larry's deployment acceptance remain open. `W1-REMOTE-HEALTH` records
the required human deny-list commit; the allow-list itself was not changed.

R1 health verification: 14 deployment/internal-caller/service-token tests pass
with the temporary loopback server permitted. The separate
`test_service_health_is_human_only` correctly fails until Larry applies
W1-REMOTE-HEALTH: the current tier is `core`, required tier `denied`. This is
a tracked remaining gate, not a passing suite. The restricted runner's socket
and log-process failures disappeared on the same synthetic test under the
approved local execution permission. No production deploy was invoked.

R1 merged verification update: all 79 actual sidecar routes pass the no-token
401 coverage test when auth is enabled. The local native suites also pass
(JarvisKit 219, Host 372 executed with seven environment skips). Human-only
health-script deny protection and live dormant/enabled/deployment acceptance
remain open; remote access has not been enabled.

### 2026-09-28 — release preflight correction

PR #93 merged to main as `0316a86` before the human protection rows were
committed. Its GitHub validation failed only
the two pending human deny-list checks, while policy, sandbox-controller and
knowledge-base jobs passed. A disposable Mac verification checkout confirmed
the proposed two-entry patch clears 57 focused protection tests.

The first disposable full-suite run exposed a deployment-runner isolation gap:
Pipecat's runner imports `python-dotenv` with `override=True` while pytest
collects tests. Because DEPLOY-MAIN uses production's `.venv`, that import
found production `.env` above the interpreter package and restored runtime
flags despite `env -i`. DEPLOY-MAIN now sets `PYTHON_DOTENV_DISABLED=1` in its
minimal pytest environment; a full-collection probe confirmed the console flag
remains unset. The disposable patched candidate then passed the complete Python
suite: 4,860 passed, seven skipped, two subtests passed. The patch remains
human-only and is not part of main or the follow-up release-fix commit. No production deployment or
auth activation has occurred.


### 2026-09-28 — staged Mac deployment completed

PR #96 merged as `539f8f6`; all GitHub workflows passed. DEPLOY-MAIN then
verified that exact commit: JarvisKit 219 tests/zero failures, MortimerHost
372 tests/seven environment skips/zero failures, Python 4,860 passes/seven
skips/two subtests passed. Release measurements: Skills selection-to-layout
p95 14.480 ms wide / 7.911 ms compact; crystal orb p50/p95 4.841/13.370 ms
versus legacy p50 4.833 ms. All original performance gates pass.

At 20:19 EDT the script backed up databases, code and the prior app, installed
and opened the production app, and restarted vault/bot/extractor/admin/costs.
Production HEAD and bundle revision both equal `539f8f6`; all six processes
were independently rechecked alive with the intended production paths.
Admin/vault returned HTTP 200; bot returned the expected 307. The deployment
receipt reports `deployed` with no problems. Database migrations through
`0036_skill_step_check_receipts` are present (0035 remains reserved).

Receipt: `docs/acceptance/skills-workspace/receipts/rendering-performance-2026-09-28/deployment-receipt.json`.
Local rollback: `~/MortimerRollback/release-539f8f6-20260928-201417/ROLLBACK.sh`.
This closes staged source deployment, not live feature acceptance or activation.
No runtime feature flags or provider routes were deliberately changed by this
operation. Remote enabled-mode acceptance, provider/VM/voice/display/accessibility
and plan-specific activation/rollback gates remain open where previously open.


### 2026-09-28 — R1 revalidation after main deployment

At Larry's renewed WS-01/WS-04 instruction, fetched main, read AGENTS/ROADMAP
from `origin/main`, confirmed current work committed, and merged main (already
up to date). R1.2–R1.8 runtime implementation is already present and deployed:
explicit-true authentication, dormant loopback, service headers on all internal
callers, preserved watcher/self-edit behavior, source guard, authenticated
health helper and human deny entry, migration `0034_client_tokens`, 79-route
middleware coverage, and native shared authenticated sender.

The `.env.example` comment now matches R1's opt-in wording exactly; it remains
commented and changes no running setting. The status-tool service-token test
also checks the explicitly requested unset-token case. ROADMAP §3 now records
the actual applied migration IDs rather than instructing another renumbering.

A disposable loopback server ran the actual admin ASGI application with lifespan
disabled, a temporary database and a synthetic service token: enabled bare
health 401; enabled health helper 200; helper without token 401; dormant bare
health and helper without token both 200. Server and temporary database were
removed afterward. Production authentication, credentials and services were
untouched. Receipt: `docs/acceptance/skills-workspace/receipts/rendering-performance-2026-09-28/r1-enabled-dormant-proof.json`.

R1.10's full merged tests, native tests and dormant DEPLOY-MAIN phase D are
recorded in the deployed release receipt. The isolated enabled-mode health
proof is now recorded too. A spoken live `system_status` interaction is still
unrecorded; remote activation and token onboarding remain deferred under R1.9.

Focused R1/migration/watcher verification after the unset-token test update:
140 passed (auth, middleware, bind, service token, caller guard, deployment
helper, database upgrade/idempotency, progress watcher). The deployed runtime
source is unchanged by this revalidation; only tests, example comments and
status/evidence records changed.

## Addendum R2 (2026-09-30) — prepare local bearer authentication without remote access

**Status: guard merged in PR #149 (`a39136a`) and deployed in `7c4637e` on 2026-10-02; provisioning design only.** Larry approved preparing this WS-04 step so WS-03 can
eventually read owner-scoped Versions, runtime inventory and creator activity.
This addendum does not authorize turning on production authentication, binding
off-host, minting live credentials, or activating a skill. R1.9's remote T2
decision remains separate. The current production app/backend still run with
authentication dormant, and the Skills owner-scoped endpoints correctly fail
closed there.

### R2.1 Decision and invariant

Use R1.9 option **(c)** as an *explicit supervised preparation mode*, not as
an automatic action on every deploy. It mints two distinct existing K1 tokens:
one internal service token in the project vault under `JARVIS_SERVICE_TOKEN`,
and one local Mac client token in the login Keychain item that
`KeychainStore` already reads (service `com.mortimer.jarviskit`, account
`http://127.0.0.1:7860`). Only SHA-256 hashes and non-secret token names live
in `client_tokens` (migration `0034`). No token is returned by an HTTP/MCP
endpoint or shown in the app. R1 A13 remains intact. This chooses the path
that avoids routine terminal credential handling and an unauthenticated local
pairing endpoint. It does not change K1 token format or add scopes.

Reserve `JARVIS_REMOTE_BIND_ENABLED` in ROADMAP §3 before code. Its only read
is in `jarvis/bind.py`; the exact string `true` enables consideration of a
non-loopback `JARVIS_BIND_HOST`, and absent/false/typo forces `127.0.0.1` even
when `JARVIS_AUTH_ENABLED=true`. The existing R1 tests for auth-off loopback
remain. With the new gate true, the existing R1 requirement for auth, an
unrevoked token and a bindable interface still applies. `JARVIS_AUTH_ENABLED`
therefore controls *who may call*; the new key controls *whether a remote
listener may exist*. R2 preparation and later local activation leave the
remote key absent/false. No new migration, port or launchd label is needed.

### R2.2 Implement in this order

1. Add the `jarvis.bind.resolve_bind_host` gate and its truth table tests
   before any provisioning work: auth off/remote flag on is loopback;
   auth on/remote flag absent or false/remote host requested is loopback;
   both flags true with no active token refuses; both true with a token retain
   R1's bindable-address and strict/fallback behavior. Test invalid values
   such as `yes` and `1` as false. Keep the native client URLs at loopback.
2. Factor token creation in `jarvis.auth` into a function that inserts an
   immutable named hash row and returns the plaintext **in process**. The
   existing `python -m jarvis.auth add` CLI keeps its one-time stdout behavior
   for explicit operator use; the new supervised caller never prints it.
   Names are unique and never reused. Do not add a mint route or tool.
3. Add a small JarvisKit executable target for Keychain provisioning. It
   accepts the non-secret bot URL as an argument, reads exactly one K1 token
   from stdin, calls `KeychainStore.setToken`, reads the same item back to
   verify equality, and prints only success/failure. It must not put the token
   in argv, shell history, logs or a temporary file. It uses the existing
   `KeychainStore` implementation so accessibility and account derivation do
   not drift. The target is a local operator helper, never an agent tool.
4. Add `scripts/provision_local_auth.py` as the supervised coordinator. It
   requires the production repository, loopback bot/admin URLs, an unlocked
   vault and writable login Keychain, and refuses if the service vault entry
   or local Keychain item already exists; rotation is a separate reviewed
   operation. It creates unique `service-local-<UTC timestamp>` and
   `larry-macbook-local-<UTC timestamp>` rows, stores the service plaintext
   with `jarvis.vault.set_secret`, pipes the device plaintext to the Swift
   helper, and verifies both by readback plus `verify_bearer` without echoing
   either value. It reports only token names, storage presence and masked
   verdicts. On a handled failure, revoke newly minted rows and delete only
   storage items this invocation created. On an interrupted invocation, a
   rerun must stop with the incomplete non-secret names and a documented
   revoke/cleanup path; it must never silently mint replacements.
5. Add an **opt-in** `--prepare-local-auth` path to the human-only
   `scripts/deploy_main.sh`. It runs the normal exact-main phase A verification
   and phase B rollback snapshot first, then invokes the coordinator while
   authentication is still off. Normal DEPLOY-MAIN runs remain unchanged.
   Preparation does not write `JARVIS_AUTH_ENABLED=true`, change
   `JARVIS_BIND_HOST`, restart into enabled mode, or set the remote flag.
   The receipt records the source revision, token names and masked proof only.
6. Specify a separate, later **local activation** step in the same supervised
   deploy path. It first checks both stored tokens against the DB, all current
   internal callers, the native account URL, and an explicit loopback bind.
   Then it atomically stages `JARVIS_AUTH_ENABLED=true` with
   `JARVIS_REMOTE_BIND_ENABLED=false` in the production launch configuration,
   restarts the bot/admin and their dependent callers, and probes authenticated
   health. A failed probe restores the prior config and restarts the prior
   local behavior; it does not restore the database over newer conversations.
   This activation mode is **not** part of R2 preparation and needs Larry's
   separate go-ahead after the preparation code and receipt are reviewed.

For R2, update the `jarvis.auth` module comment that currently says Mortimer
never stores plaintext: the auth database still stores only hashes, while the
*explicit local preparation* stores the service token in the existing vault
and the Mac client token in the existing device-only Keychain. Neither goes in
`.env`, a receipt, or a PR. Keep `JARVIS_SERVICE_TOKEN` scoped to its existing
declared internal children; do not widen `BASE_ENV_KEYS` or disable env scoping.

### R2.3 Acceptance and rollback boundaries

- Unit tests cover the complete two-flag bind table, mint-once/refuse-existing,
  handled failure and interrupted retry, exact Keychain service/account,
  no token in output/argv/receipt, and production flag unchanged after
  preparation. Existing all-route 401 tests still run with auth explicitly on.
- In a disposable database, vault and Keychain namespace, run preparation
  twice: first succeeds and second refuses without another active token.
  Inject failures after DB insert, vault write and Keychain write, and verify
  only this attempt's partial state is removed. No live secret is used in CI.
- A live **preparation** receipt requires the exact source revision, verified
  vault/Keychain presence, both DB identities, auth still off and bot/admin
  listeners on loopback only. No token value or protected user content may
  appear in logs or artifacts. Passing preparation does **not** close G2 or
  WS-03 SW-L.
- Later local activation acceptance must show bare loopback admin and bot
  requests return 401; both authenticated requests succeed; native Connect,
  voice turn, `system_status`, Skills Versions and runtime inventory work;
  creator remains subject to its separate sandbox/approval gates. Check the
  actual listening sockets and an off-host probe: no LAN or Tailscale
  listener. Revoke the local device token in a controlled test and verify
  immediate 401 before rotating to a fresh named token.
- Rollback from local activation sets `JARVIS_AUTH_ENABLED=false`, keeps the
  remote-bind key false, restarts services and verifies the prior loopback
  behavior. Prepared tokens may remain inert for a retry, or be revoked and
  removed by a separate supervised cleanup; do not print or re-use a name.
  Remote activation remains a new explicit decision with G2's tunnel, port,
  revocation and physical-device tests, never a side effect of this rollout.

**Handoff:** the next implementing model must first re-read current main,
AGENTS.md, ROADMAP WS-04/CX-11 and R1.9, then land the guard separately from
the supervised provisioner. It must not infer that this addendum
is authorization to mint credentials or flip either runtime flag on Larry's
Mac.

### 2026-09-30 R2 guard checkpoint

At the 2026-09-30 checkpoint, the separate `JARVIS_REMOTE_BIND_ENABLED` gate
was implemented in `jarvis/bind.py` on the WS-04 branch, with an explicit-true
test table and updated R1 remote cases. `.env.example` documented the two
independent flags. Auth/bind/middleware/caller tests and bot/service-token/
launch-guard tests passed 109/109 combined, including both real startup entry
points' resolved loopback host arguments. The supervised provisioner, proposed
R2 stdin-to-Keychain provisioning helper, local activation and live acceptance
were not implemented, and production flags and credentials were unchanged by
that checkpoint.
These are the original checkpoint's implementation/test facts, not a new run.

The guard subsequently merged in PR #149 as `a39136a` on 2026-09-30 and was
deployed in `7c4637e` on 2026-10-02; ROADMAP records authentication and remote
binding off for that deployment. Token onboarding, local activation and any
remote-bind decision remain open.

### 2026-10-06 — R2 guard status reconciliation (Codex)

Read-only merge/receipt reconciliation confirms PR #149's merge
`a39136a4a51c3ccb85ee60b432412a032b70c28c`. The 10-02 deployment receipt
`~/MortimerRollback/logs/deployment-receipt-7c4637e.json` records `deployed`
at 15:51:04 EDT with matching main, production and bundle revision
`7c4637ede98add988079431a44d6ec965309f757` and no reported problems. The
latest recorded production receipt is
`~/MortimerRollback/logs/deployment-receipt-bde22bb.json`: `deployed` on
2026-10-03 at 16:34:04 EDT, with matching main, production and bundle revision
`bde22bb6425c6bf36a3e0d7cf53f2785c274190d` and no reported problems.

This corrects the stale branch-only status without changing the R2 design.
The authentication/remote-binding-off deployment wording comes from the
existing roadmap event; this documentation check does not remeasure effective
runtime settings or current process state. Larry's onboarding-method choice
is still pending under the authoritative WS-04 row. The supervised
provisioner and proposed R2 stdin-to-Keychain provisioning helper remain
unimplemented; credential preparation, local activation, remote binding and
live acceptance remain separate open gates. No code, test, credential,
provider or production setting changed, and no new live acceptance is claimed.

### 2026-10-22 — Bounded onboarding preparation (Codex)

Read-only analysis at `c63ecce97108787c55ef55fad73d32236694cc65` establishes the
following reusable source behavior. No auth operation, credential read, private
log inspection or application test was executed by this preparation task.

| Component | Source finding | Consequence for proposed supervised preparation |
|---|---|---|
| `jarvis/auth.py`, `_cmd_add` | Commits a token hash before printing plaintext once; duplicate names remain forbidden after revocation. | Reuse the token contract through a nonprinting in-process boundary; do not capture plaintext CLI output in logs. |
| `tests/unit/test_auth.py` | Existing assertions cover valid/unknown/revoked tokens, absent plaintext DB storage, duplicate refusal, hash-free listing, active counts, service headers and switch parsing. | These are inspected foundation tests, not newly executed proof of coordinated provisioning. |
| `jarvis/vault.py` | Encrypted temporary envelope, mode 0600, atomic replace and locking; `set_secret` overwrites a named value. | A separate precheck plus setter is not atomic create-only storage. Design concurrent-change refusal explicitly. |
| `macos/JarvisKit/Sources/JarvisKit/KeychainStore.swift` | Existing setter updates entries and returns Void; reader returns nil for unsuccessful lookup. Service/account remain the K1 convention. | Distinguish confirmed absence from locked/denied/unreadable storage; require actual readback. Log wording alone cannot prove success. |
| `jarvis/bind.py` | Auth disabled and remote-bind disabled independently force loopback; non-loopback requires both and an active token. | Local auth does not require remote exposure. Preparation must change neither flag. |

Larry still chooses supervised setup, one-time CLI or Mac pairing. The existing
R2 recommendation does not make that choice. Pairing adds a different minting
surface and requires its own design review. A standalone disposable-only first
slice is proposed if supervised preparation is chosen; installer integration
stays with WS-17 and requires explicit scope coordination.

Proposed synthetic vectors, all **unexecuted**:

1. Fresh disposable DB/vault/Keychain namespace creates two distinct identities,
   stores only hashes in DB, verifies exact readback and changes no flags.
2. Existing vault or Keychain entry refuses before creating identities and
   preserves existing values. Concurrent changes cannot be overwritten.
3. Locked, denied or unreadable Keychain fails explicitly; ambiguous nil is not
   confirmed absence.
4. Failure after DB, vault or Keychain write cleans/revokes only this attempt's
   attributable state; unrelated entries are unchanged.
5. Interrupted retry cannot silently remint; it reports nonsecret incomplete-state
   identifiers and bounded recovery instructions.
6. Secret transport uses stdin, never argv, logs, receipts or plaintext temporary
   files. Receipts contain masked/presence verdicts only.
7. Auth/remote-switch combinations retain existing loopback/refusal behavior.
8. Separately authorized later activation verifies bare-request refusal,
   authenticated paths, immediate revocation, socket binding and rollback.

Before implementation, a fresh main claim must name the selected method, branch
and exact paths. Conditional supervised paths include the reusable auth boundary,
proposed `scripts/provision_local_auth.py`, focused disposable tests and a narrow
stdin-to-Keychain helper/target. Any vault or Keychain semantic changes need
explicit scope. No installer, auth middleware, provider/model, Skills creator,
credential or live-acceptance ownership is acquired by this documentation.

WS-01 physical/live acceptance remains with existing owners. WS-10 still needs
the actual classifier, eligible dedicated memory route, effective stage and
WS-05 privacy prerequisites. Shadow cannot mutate live memory/prompts; the first
20 actual decisions and existing 100-candidate/five-model-call daily limits are
not satisfied by these synthetic vectors. No live acceptance checkbox changes.

### 2026-10-29 — WS-04 offline phone admission claim registration

PR #285 merged to main at `97ffb3bb19ce29a9c4e6768a481389ac147cd691`. The S0 model and fixture hashes remain `d00ce2d1254c04f386b455b061b45a5b1984b295a6201746d8bb6ea462e38781` and `1cf1f8a377438a5fe04d0517535eee86166c48af6decb030da249b9ae5083950`; the independent oracle accepted those exact bytes, and all three PR-triggered workflows completed successfully. This proves only the synthetic contract; no production recovery store, route, phone, or live access is verified.

Larry authorized the next bounded offline WS-04 slice for GPT-6 Luna. The registered branch `codex/ws04-phone-admission-core-20261029` was created from main `d5c9e61faa8cc91da5f7d7e67b8b2056c587de5a` after the matching docs-only claim merged. Exact source/test scope: new `jarvis/bot/phone_admission.py`; new `tests/unit/test_phone_admission.py`; `tests/unit/test_phone_admission_contract.py` wired to the module; and `tests/fixtures/phone_admission_contract/v1.json` transferred read-only with the claim. No fixture version change is included. The existing [phone plan §16](MORTIMER_PHONE_ACCESS_PLAN.md#16-approved-native-iphone-direction-and-staged-claims--revision-54-amendment-candidate-2026-10-28) remains the design authority.

The slice exercises the deterministic admission policy and all current S0 vectors without adding listeners, persistent schema, credentials or live grants. It does not complete the full 1.1 host-anchor/store/route integration; plan §6 items 0.2 and 1.1 reservations, route/sink wiring and their acceptance evidence remain open. At registration time, source edits were gated on the exact owner/branch/scope row landing on main; PR #287 registered the scope and changed no runtime state or acceptance checkbox.


### 2026-10-29 — Offline phone-admission core implementation

On branch `codex/ws04-phone-admission-core-20261029` at base
`d5c9e61faa8cc91da5f7d7e67b8b2056c587de5a`, added the deterministic in-memory
policy core in `jarvis/bot/phone_admission.py`. It requires the existing
`ClientIdentity` boundary for issue, consume, command, output and login
admission, checks that the authenticated user matches the session owner, and
refuses those operations when the explicitly supplied feature flag is off.
Fixture-derived state and intentionally faulty sensitivity variants stay in
tests; the v1 fixture is unchanged.

Local offline validation: the focused unittest run passed 9 tests, including all
70 S0 vectors, all 7 sensitivity cases and all 3 isolation probes; syntax
compilation passed. Independent review found that a restored session ID could
be reused under another grant while an old peer or ticket retained authority.
The candidate now requires each saved binding to match the session's current
grant and its current owner, with regression coverage for stale command/output
peers and tickets plus successful fresh and unrelated sessions. After that
correction, the focused unittest run passed 11 tests, including all 70 S0
vectors, all 7 sensitivity cases, all 3 isolation probes and the new boundary
tests. The full pytest gate is still pending because no pytest module or
executable is available in this environment, and no dependency was installed.
The module is not wired to a route, persistent store/host anchor, phone, tunnel,
credential or runtime service. Independent exact-source review ACCEPTED commit
`6a4b22cbd38014b01fb2de6a35245416c20560b6` against main
`5310d1a9305035f43143fcffad6161619281f475`; required PR CI and merge remain
open. Review also established a limit: without revocation, restoring and reusing
the identical session/grant/owner tuple can retain an unexpired unused ticket
in this synthetic model. The later durable host/route integration must define
and test a non-rollbackable login-incarnation fence before any general
restore-safety claim. Stage 1.1 and all live acceptance remain open.

## Addendum R3 — phone access 0.2 reservation proposal, 2026-10-29

**Status: R3-02 reservations and exact two-file R3-S1 fake-store claim adopted branch-locally, 2026-10-29; not merged to main, implemented or live-accepted.** This extends the existing WS-04 plan, not a new workstream. The normal reviewed document workflow is explicitly authorized in place of unavailable `plan_start`; this changes no security, verification, release or activation gate. Larry's one-final-merge direction permits branch-local exact claims in the existing integration PR only, as a narrow exception to intermediate main-first claim merges. All unrelated claims and ownership rules remain binding. No repository write, push or merge was performed in preparing this candidate.

### R3.1 Evidence and completion boundary

Read-only GitHub snapshot: main `5310d1a9305035f43143fcffad6161619281f475`; draft PR #290 branch `codex/ws04-phone-admission-core-20261029`, head `5cd461cfd089e8a7d9d9ad9f521311db7f02c0b1`. Independent review ACCEPT applies to source `6a4b22cbd38014b01fb2de6a35245416c20560b6`, not to this proposal or future persistence. PR metadata records later documentation-only changes. The current core owns no persistence/listener/route/provider and explicitly identifies S0 labels as synthetic, not wire names. Restoring and reusing an identical owner/grant/session tuple can preserve an unused ticket without revocation; durable integration must fence every login incarnation, not only revoke events.

Both refs' §3 still identify `0037+` as free; both `jarvis/db.py` migration lists stop at `0036_skill_step_check_receipts`, with `0035` retained for MAIL. Default-branch code search for `0037` found the free reservation and historical discussion, not a competing schema. Exact proposed store/test paths returned 404 on main and PR head. Searches for proposed config/protocol/anchor names found no main matches; the PR's existing claim reserves none. These are dated collision checks, not a permanent allocation or a complete runtime inventory. Recheck both refs and new open claims before adoption/source edits; if either moves, stop for reconciliation, never silently renumber or overwrite another reservation.

Previous read-only source inventory identified bot port 7860 with `/api/offer` and `/ws-client`, and broad admin port 7861. This is not a fresh listening-socket measurement. Neither raw service may be exposed to the phone. Mac unavailable/offline: no actual phone/OS, Keychain behavior, restore hook, tunnel/media path, process state, signing/APNs eligibility or installed build was inspected here.

Product completion requires **both directions of iPhone voice, admitted shared information, and eligible incoming calls**, with source and later real-device acceptance. Cards-only or synthetic admission is partial delivery. Phone plan §16 native-first SwiftUI/CallKit/eligible PushKit direction prevails over historical web-first steps. Mobile web, parity mutations and WS-24 task continuation remain deferred.

### R3.2 Decisions and mechanical constraints

1. Reuse the canonical SQLite database and verified `ClientIdentity`; reject a separate facade authority database, which would permit divergent revocation. Storage constraints and transactional checks, not caller JSON, own identity/scope. The feature-off path denies before reads that disclose inventory or start provider/media work.
2. Use an independently protected anchor **outside database/release rollback snapshots**, not a row or file inside a restorable application tree. A DB-only generation cannot detect a restored revoked state. An ordinary Keychain item is not claimed to be physically nonrollbackable: backup/migration/whole-host restoration or loss of its independent history requires unavailable/blocked state and trusted owner recovery. No automatic bootstrap from restored DB or silent anchor regeneration.
3. Every login creates a new server-generated login incarnation bound to the protected host generation; never derive it solely from reused session/grant IDs. Advance protected authority before enabling a replacement incarnation. A crash may strand a login, but cannot restore old authority. Host generation advancement may invalidate all sessions; ordinary session-only sign-out must remain session-scoped and must not revoke another grant/session. Grant loss/revocation fences all its sessions, tickets, calls, subscriptions and peers.
4. Use a narrow typed facade; no arbitrary URL/path proxy, admin catch-all, shell route, forwarded service token or synthetic administrative transitions. Route allowlisting, strict schemas and authenticated binding are mechanical backstops. Shared result projection stays WS-17-owned; source classification and per-sink grant checks deny unknown/protected/unprovenanced input. Phone-display permission does not authorize model/STT/TTS processing.
5. Reserve shared names before their source use but do not wire a restore caller now. WS-17 owns supported install/rollback/restore entry points and must claim the hook integration. A restore path lacking verified hook coverage blocks live activation; do not invent a generic scheduler or new restore trigger.

### R3.3 Exact proposed reservations (R3-02)

The parent coordinator adopts these reservations and the exact R3-S1 fake-store claim on the existing PR #290 branch under Larry's authorized remote-access goal and narrow one-final-merge exception. Independent review ACCEPTED the published proposal patch `044f700a849583e1379f835869405573c53ca107c55a64e048baaa93f0336af7` at commit `d2b671ee808d5fc616817ca8b6bcf94d559a6871`. The host-identity extension in R3.3a was independently documentation-reviewed and adopted branch-locally on 2026-10-29. These reservations are not on main, production implementation evidence, or authority to use real anchors/credentials/services. Historical proposal wording and dated collision evidence below remain history; this status governs branch-local adoption only.

| Kind | Exact proposed identifier and contract |
| --- | --- |
| Migration | `0037_phone_remote_authority`; append only, never reuse/rename applied IDs. `0035` remains MAIL. No migration runs in the next isolated store slice. |
| Authority tables | `phone_remote_meta(singleton_id, schema_version, host_id, host_generation, transition_id, transition_state)`; `phone_remote_devices(device_id, owner_id, public_key, key_algorithm, revoked_at)`; `phone_remote_grants(grant_id, device_id, owner_id, scopes_json, grant_generation, revoked_at)`; `phone_remote_sessions(session_id, host_id, grant_id, owner_id, login_incarnation, host_generation, session_generation, expires_at, revoked_at)`. Unique immutable IDs; foreign-key/owner consistency and strict allowed scopes are mandatory. Public key is public verification material, not plaintext private key. Timestamps/identifiers cannot supply authority. Device/grant authority is scoped by the single validated host meta row.
| Ephemeral state | Offer/update tickets, active peers, call invitations and subscriptions remain process-local and never survive restart/restore; persist no ticket bearer, SDP, media or phone content. Restart closes them and requires fresh admission. Device/grant records may survive intact restart, not automatically trusted restore. |
| Protected anchor | Keychain service `com.mortimer.phone-authority`, account `host-generation-v1`; typed contents `anchor_version`, `host_id`, `host_generation`, `transition_id`, `transition_state`, `login_counter`. Separate encrypted-vault protection-key slot `PHONE_REMOTE_STORE_KEY` (only if encrypted store fields require it) **must not reuse this anchor item or any existing service/client token item**. Do not create either during offline work. Unselected encryption/key storage is a blocking decision, not implied authority. |
| Configuration | `JARVIS_PHONE_REMOTE_ENABLED` explicit `true` only, default false. Existing `JARVIS_AUTH_ENABLED` and `JARVIS_REMOTE_BIND_ENABLED` remain independently necessary where applicable; this new gate does not broaden either bind. No new port, launchd label or allow-list row. |
| Protocol | Kind `mortimer.phone-remote.v1`; `protocol_version=1`, reject unknown/extra command fields and unsupported major versions. It is not the existing fixture event schema. |
| Restore seam | Internal contract `phone_remote_restore_v1`: `prepare_restore(operation_id, expected_host_id, expected_generation)` → nonsecret transition receipt; `complete_restore(operation_id, receipt)` → verified stable/blocked verdict. WS-17 owns its real invocation; no public HTTP/MCP method. |

### R3.3a Adopted host-identity binding amendment — 2026-10-29

The proposal version was independently documentation-reviewed and ACCEPTED at exact pre-adoption candidate hashes ROADMAP `74156c60179d8543527909e07690bd309649a88807afc472d79b95ddc57ad3d2` and this plan `8b520291f1c8e8f75f3ea0f85427758e1e5602b41e9ac11df63ec751aff5ef2e`. The coordinator adopts the narrow extension branch-locally in PR #290 on 2026-10-29. The finding that prompted it came from the independent fake-store review of source hash `4b5a190237d7dc14d111176c5364ee75dde53f39c8c7ee83568ad096e79c6df7`: replacing only fake anchor HOST-A with HOST-B at the same generation/login counter, while leaving SQLite untouched, still admitted an HOST-A ticket. This synthetic cross-host identity substitution is distinct from the documented full-host rollback limitation; it is not a production exposure or final store-source acceptance.

The adopted R3-02 schema/contract extension is effective on this integration branch only. It adds no migration execution, real Keychain operation, restore caller, or new source path:

- Add `host_id` to `phone_remote_meta(singleton_id, schema_version, host_id, host_generation, transition_id, transition_state)` and to `phone_remote_sessions(session_id, host_id, grant_id, owner_id, login_incarnation, host_generation, session_generation, expires_at, revoked_at)`. Device/grant rows remain scoped by the single validated host authority in `phone_remote_meta`; this amendment does not add redundant host columns to those tables.
- Treat the protected anchor's existing `host_id` as the independent source. Admission requires a nonempty exact match between anchor and meta; every session must match that host ID, and each in-memory ticket/peer binding must carry it and match the current validated host ID at issue, consume, command, and output. Host identity is never accepted from a client payload or reconstructed automatically from a restored database. Missing, changed, or mismatched identity fails closed; changing host identity requires trusted owner recovery/re-enrollment.
- Extend the fake-anchor matrix with equal-generation/equal-counter cross-host substitution in both directions (HOST-A anchor with HOST-B database/session and HOST-B anchor with HOST-A database/session), stale ticket/peer checks after an anchor-only host swap, and no-mutation assertions on denial. Use opaque synthetic host IDs only. This does not prove detection of a full-host rollback that restores the anchor and database together; that limitation remains fail-closed pending trusted recovery.

The exact two-file R3-S1 source path scope remains unchanged; `0037_phone_remote_authority` remains unregistered and unapplied. The amendment changes only the listed candidate columns and fake-store assertions. The source review finding hash is rationale for this contract correction, not evidence that the corrected store implementation has passed independent review.

**Anchor transition:** under one exclusive authority lock, read exact stable anchor and DB pair; refuse absent/locked/denied/unknown/mismatch/pending. Durably write pending anchor with strictly advanced generation and unique transition ID, then commit corresponding DB state, then durably finalize anchor stable. Persist and verify every write before moving on. Admission is denied throughout pending state. Recovery never decreases generation or guesses which side won; trusted owner reconciliation may advance again and revoke old sessions, never automatically accept the restored DB. Inject crashes before/after every step. A restore operation first fences authority before replacing DB files, drains peers, and only completes after restored DB is reconciled to the current protected generation with old login/ticket authority invalid. Failure leaves remote access off/blocked. Exact Keychain accessibility, atomic update/locking and whole-host recovery policy require decision D2 before real-anchor implementation.

**Login fence:** serialize login with revoke/restore; anchor-controlled monotonically advancing `login_counter` yields a never-reused `(host_id, host_generation, login_counter)` incarnation. DB session enabled only after the protected reservation is durable; issuance and consume compare the entire current binding. Counter/anchor rollback or unavailable storage denies; no random-only incarnation is claimed as a rollback detector. Every ticket/peer/event cursor binds owner/device/grant/session/incarnation/generations/process epoch and purpose. Full-host backup restoring both authority stores remains outside the proof unless independently detected and owner-recovered.

### R3.4 Shared protocol and later owner boundaries

Facade control envelope: `kind`, `protocol_version`, `request_id`, `operation`, typed `payload`; response: `request_id`, fixed `status` (`ok`, `denied`, `unavailable`, `incompatible`), fixed content-free `reason`, typed admitted `payload`. Owner identity and authority bindings are server-derived after authenticating the paired install and current login, never trusted from payload. Reject cookie-only authentication, wrong origin/identity, stale incarnation and replay; pairing/login details await D1, with no unauthenticated mint endpoint implied.

Reserve operations at contract level only: `session.status`, `voice.offer`, `voice.update`, `voice.end`, `results.snapshot`, `results.resume`, `call.state`, `call.answer`, `call.decline`. Each has a closed schema and explicit scopes; none allows arbitrary actions. An offer/update ticket is single-use, expires in 30 seconds, binds exact request/SDP digest and peer/purpose/current authority, and is atomically consumed before peer creation/update. No raw ticket in URL/logs. Five-second maximum authorization freshness/peer closure is a required target under lost notifications/store failure, not measured evidence; new commands deny immediately after revocation commit.

WS-17 result envelopes retain canonical source/result IDs, revisions, admitted classification, collection grant, generation and bounded resume cursor. They project memory-only phone collections, never a second task/result store; stale/revoked/unknown data and rendering errors disclose only neutral unavailable status. No remote automatic assets/script execution. Ending a call does not grant persistent data access or focus/move Mac windows. Providers receive only separately source-admitted context. WS-05 decides complete model/STT/TTS eligibility/readiness; absent readiness means no provider socket and honest unavailable status, not fallback.

Incoming invitation payload is only opaque call ID, schema version, expiry and neutral caller identity; never bearer/SDP/task/document/transcript. APNs is a wake-up hint, not admission. Answer authenticates private path and rechecks authoritative call state, current scopes and audio lease; duplicate/expired/revoked invitations cannot start audio. Explicit Call/Talk/Answer, OS mic permission, current admission and eligible CallKit activation are all necessary for capture. End/mute/revoke/lease loss stop capture. No always-listening phone. Incoming triggers/quiet hours/rate limits and Apple eligibility stay separately approved and disabled until tested.

### R3.5 Numbered implementation and acceptance

**Claimed next isolated source slice R3-S1:** this adoption extends only WS-04's branch-local fake-store claim in the same PR #290. Exact new files `jarvis/bot/phone_admission_store.py` and `tests/unit/test_phone_admission_store.py`; documentation only in this WS-04 block, §3 and this plan. Implement an injected transactional store/anchor contract and disposable SQLite/fake-anchor conformance tests. Do not edit `jarvis/db.py`, existing accepted core/fixture/harness, auth middleware, config, vault, Keychain, route/server, restore/install scripts, native code or other owner's paths. Do not register/run a production migration or connect the store to running code. This is a verifiable durable-store candidate, not full 1.1 integration. If the accepted core needs changes, stop for an expanded reviewed claim rather than hiding them here.

**Adopted host-identity boundary:** R3.3a is now adopted branch-locally after independent documentation review. The store author may implement the `host_id` fields and checks within the existing exact two-file S1 claim; no production migration, real Keychain operation, restore caller or extra source path is included.

Run `python3 -m unittest discover -s tests/unit -p 'test_phone_admission_store.py' -v`; require all explicitly enumerated matrix cases below, no live network/secret/provider access and a test count/command receipt tied to exact source hash. Then independently review exact source. Existing S0 fixture remains byte-identical; later adapter claim must run all 70 S0 vectors plus sensitivity/isolation checks against real admission/store boundaries. Run applicable repository CI/roadmap checks in the final integration; focused unittest is not a full-suite pass.

| Packet | Required assertions and exit evidence |
| --- | --- |
| S1-A schema/identity | Fresh/upgrade/idempotent disposable schema; uniqueness/FK/owner checks; no plaintext private credentials; cross-owner/device/grant/session denial; malformed/unknown fields/types deny without mutation. |
| S1-B rollback/incarnation | Snapshot → login → reuse identical IDs → restore denies old unused ticket; revoke/sign-out → restore; new login never reuses incarnation; unrelated session-only sign-out stays scoped. Equal-generation/equal-counter cross-host anchor/database/session substitution and stale cross-host ticket/peer use deny without mutation. Intact restart permits fresh reauthentication without re-pairing, never restores old peers/tickets. |
| S1-C crash/anchor | Crash before and after each pending-anchor/DB-commit/finalize point; concurrent login/revoke/restore; stale/absent/locked/denied/corrupt/mismatched anchor; anchor/meta/session host-ID mismatch; write/fsync/transaction failure. Every ambiguous state denies admission; no decrement, silent bootstrap or partial grant. |
| S1-D authority loss | Revoke during consume/update/output; lost notification; store unavailable; concurrent replay consumes once; expired ticket denies at boundary; fake-clock peer closure within five seconds and immediate new-command refusal. Any peer adapter absent in S1 is explicitly blocked until integration, not marked passed. |
| S2 facade + media | Separate exact route/peer/sink claim; route inventory blocks admin/raw bot; typed binding and ticket tests; feature-off/incompatible denial; only private authenticated signaling/events/media; synthetic canaries absent at every output/provider/log/cache sink. Actual listeners/ICE/DERP remain live-gated. |
| S3 native/results | WS-30 fake-host protocol/session package is implemented and independently source-reviewed under R3.7; its local package test passed, but repository CI coverage is still open. It has no result payload implementation. A separate WS-17 result contract/source claim is required before admitted cards, source revision, filters or resume cursors are implemented; simulator/build evidence is not phone acceptance. |
| S4 incoming | Separate Mac call-policy/APNs and iOS coordinator claims; fake duplicate/out-of-order/lost-ack/expiry/revoke/decline tests; no push credential or actual invitation until authorized. |
| S5 final/live | One reviewed final integration merge only when Larry authorizes. Existing release owner separately installs exact build; named iPhone/OS, Wi-Fi/cellular, bidirectional speech/barge-in/interruption, admitted cards/roadmap during/after call, eligible incoming CallKit Answer/Decline/background/lock, sleep/restart/unlock, revoke and remote-off rollback evidenced. Unexpected route/public/LAN/admin reachability blocks acceptance. No partial/untested subpart becomes a pass. |

Offline work can continue on S1 fake stores, contract schemas, fake call state, canary fixtures and independent review while live gates remain closed. Actual iOS/provider/shared-file work still needs its owner's exact claim; no concurrent editing or blanket takeover.

### R3.6 Minimal decisions and authority still needed

D1 **Pairing/authentication:** choose supervised local native per-install key enrollment + phone-side user-verified reauthentication (recommended) versus a separately reviewed synced-passkey policy. Approve device binding/synchronization/recovery semantics; neither is implemented or selected by this reservation.

D2 **Protected anchor:** approve independent device-local Keychain accessibility/serialization and loss/backup/whole-host recovery policy; recommended fail closed after reboot until unlock and after uncertain restore until owner recovery. Ratify whether `PHONE_REMOTE_STORE_KEY` is needed at all and its separate vault storage. A vault item is never the anchor. No guarantee of hardware monotonic storage is made.

D3 **Restore owner:** WS-17 identifies every supported restore/rollback/install entry point and explicitly owns the `phone_remote_restore_v1` hook integration/review. No supported invocation is currently verified; keep live remote disabled until coverage is established. R3.22 below is now an adopted, branch-local seven-file WS-04 offline prepare/pending-fence and controlled-child-shutdown claim. It does not implement a restore hook or authorize restore/deployment; completion/recovery, DB replacement and WS-17 invocation remain unimplemented.

D4 **Availability:** choose supported sleep, restart, auto-start and unlock behavior; recommend honest unavailable while sleeping and explicit local-unlock requirement after reboot initially. No power/login/service settings change follows from a decision in prose.

### R3.14 Approved starting security design — decisions in principle only (2026-10-30)

Larry approved the following starting design defaults for further review and planning. This is not implementation, enrollment, provisioning, configuration, service-start, signing, installation, network, microphone, or live-test authorization.

- Use separate device-bound enrollment and fresh user Face ID/passcode verification for reauthentication. Do not synchronize one device's enrollment key to another device by implication.
- Require an awake Mac and a manually initiated first call. Fail closed when required keys are absent and after an uncertain restore until an owner recovery path is implemented and verified.
- Expose only the restricted phone service over the private path, with authenticated TLS; keep admin interfaces private and inaccessible through the phone service.
- User also approved encrypted DERP fallback when direct connectivity fails and Mac reachability while locked. Treat these as design intent, not evidence that the tunnel or host service is implemented. The approved intent does not settle whether a locked Mac may accept a new authenticated session or only sustain a session established earlier; resolve that distinction in the D1/D2 implementation review, considering the usability and key-exposure tradeoff. D2 should evaluate supporting new authenticated sessions after first unlock through a signed-in user Data Protection Keychain process, subject to review of the exact accessibility class, local user-verification policy, and signing behavior. Until review, access before the first unlock after boot remains fail-closed; approval of locked reachability does not imply pre-first-unlock access.
- D1 still needs technical review of the exact device-bound enrollment, verifier/reauthentication, and session-creation protocol. D2 still needs reviewed typed handling of locked/denied/missing Keychain states, verified writes/readback, serialization coordinated with the protected-anchor/SQLite authority transition, and backup/loss/whole-host recovery policy. `ThisDeviceOnly` prevents migration to another device but is not rollback protection. Neither Keychain durability nor locked-session behavior has been proven by this prose decision. D3 still needs WS-17 to inventory every supported restore/downgrade entry point, including generated `ROLLBACK.sh --restore-db` and related restore paths, and verify the `phone_remote_restore_v1` invocation; no hook is yet verified. Keep access disabled until that coverage is established. The locked-reachability decision says nothing about sleep, wake, auto-start, or restart behavior; keep those under D4.
- The iOS app target and deployment minimum remain unselected until the intended iPadOS test baseline is known. No local device model or OS facts are recorded here.

No key, credential, pairing, tunnel, ACL, route, listener, service setting, app target, signing asset, install, or live access was created or changed for this decision record. Do not mark any live acceptance box complete from this approval.

Before later live stages Larry still must approve the named phone/minimum OS, Apple account/signing/entitlements/distribution/eligibility/costs, private TLS service identity/Tailscale enrollment/ACLs, exact content grants, incoming triggers/quiet hours/rate limits, and WS-05 speech route. The DERP and locked-reachability choices are design decisions only; no account, key, credential, tunnel, network, service, capture, provider/model, install or deployment action is authorized here. Harness-controller model changes always require Larry's approval.

### R3.15 native authentication-proof codec — adopted pure-source claim (2026-10-30)

**State:** coordinator adopted this pure offline source claim on 2026-10-30. Author: GPT-6 Luna. Nonauthor reviewer: `01a18584-92e2-7511-aca8-983bb3f230ef`. Keep it isolated from the client and ASGI lanes. Exact source scope: `jarvis/bot/phone_remote_auth_proof.py` and `tests/unit/test_phone_remote_auth_proof.py`; update only the local WS-04 ownership row to record the claim. Do not change any existing protocol, store, service, route, client, dependency file, fixture, or other implementation path.

**Read-only collision check (2026-10-30):** connected GitHub search found no default-branch code match for `phone_remote_auth_proof` and no open-PR search match for that path, “Mortimer phone auth proof,” or “P-256 phone authentication”; PR #290's current changed-file list does not contain either proposed path. Local current-branch and `github/main` tree lookup also found neither path. A full local `git log --all` traversal could not complete because the repository object database lacks commit `628d743efa6b23b3341840594b176f9562bcc154`; therefore this is not a claim that every remote branch is collision-free. Recheck branch/path claims before any extension or publication.

**Purpose and trust boundary:** implement a closed proof-byte decoder, canonical transcript encoder, and real P-256 signature verifier for one narrowly named purpose, `phone.session.create`. The proof demonstrates possession of the private key corresponding to a server-selected enrolled public key and binds that proof to one challenge, service, host, key identifier, current host authority generation, and expiration. The module is pure: no challenge issuance/consumption, device enrollment, owner mapping, login/session minting, persistence, route, endpoint, Keychain, key creation, network, or service construction. No verifier stub or always-true path is permitted. Caller supplies the enrolled public-key bytes and an immutable expectation built from trusted current server state. The proof is never the source of owner, device, grant, session, scope, role, or authorization.

**Closed proof JSON schema:** accept UTF-8 JSON bytes no larger than 4096 bytes and exactly these fields with exact types: `protocol` (`mortimer.phone-auth-proof.v1`), `purpose` (`phone.session.create`), `challenge_id` (canonical unpadded base64url for exactly 16 bytes), `challenge_nonce` (canonical unpadded base64url for exactly 32 bytes), `service_id`, `host_id`, and `enrolled_key_id` (each nonempty ASCII `[A-Za-z0-9._:-]`, maximum 128 bytes), `authority_generation` (integer, not boolean/float, in `1..2^63-1`), `expires_at_ms` (integer, not boolean/float, in `1..2^53-1`), and `signature` (canonical unpadded base64url containing one canonical ASN.1 DER ECDSA signature, 8–72 bytes). The top-level JSON object has exactly scalar fields at depth one; reject duplicate keys, unknown/missing keys, invalid UTF-8, nonfinite numbers, all nested values, malformed/noncanonical base64url, and additional nesting before verification. JSON member order/whitespace is not signed; duplicate members remain invalid.

**Canonical signed bytes:** construct a fixed-order binary transcript independent of JSON serialization. Start with the exact 26 unprefixed domain-separator bytes `MortimerPhoneAuthProof\0v1\0` (hex `4d6f7274696d657250686f6e654175746850726f6f6600763100`). Append protocol, purpose, decoded challenge ID, decoded nonce, service ID, host ID, and enrolled key ID in that order; each field is prefixed by its unsigned 16-bit big-endian byte length. Append authority generation and expiry as two unsigned 64-bit big-endian integers, in that order, with no additional prefixes. Use the full transcript exactly once as the message to ECDSA with SHA-256; do not prehash before calling a message-hashing API. Require the enrolled public key to be exactly a 65-byte uncompressed X9.62 point on P-256 (`SECP256R1`); reject other curves/key types. Parse DER, require re-encoding equality, and require `1 <= r,s < n` where P-256 order `n` is `FFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551`. Accept mathematically valid high-S and low-S signatures; do not normalize at verification. Different ECDSA encodings/signatures do not create new challenges: any future replay defense consumes the server challenge ID, not a signature or transcript hash. Bind proof context by exact comparison with the immutable trusted expectation before signature verification. Accept only while `now_ms < expires_at_ms`; equality is expired. Challenge lifetime is capped by the trusted challenge issuer, outside this pure codec.

**Trusted expectation/time contract:** define a frozen expectation object and validate every field even though it is server-created: exact built-in types only; 16-byte `bytes` challenge ID, 32-byte `bytes` nonce; exact constant protocol/purpose strings; bounded nonempty ASCII service/host/key IDs as above; generation exact `int` (not `bool`) in `1..2^63-1`; expiry exact `int` (not `bool`) in `1..2^53-1`. `now_ms` is a caller-supplied exact built-in `int` (not `bool` or float) in `0..2^53-1`; invalid time/expectation returns `invalid_expectation`, never an exception or success. The verifier does not establish time-source freshness, monotonicity, or rollback resistance; a later authority caller must supply trustworthy time or fail closed.

**Result contract and public API:** the only supported proof-input function is `verify_auth_proof(...)`; it returns the fixed frozen result shape `ProofVerificationResult(valid: bool, code: str)`. Parsed envelopes, signatures, field objects, and transcript helpers are private implementation details and have redacted representations. `ProofExpectation` input representation is redacted too. Public verification results may contain only the boolean and one fixed code: `ok`, `malformed`, `invalid_expectation`, `context_mismatch`, `expired`, `invalid_signature`, or `unsupported_key`. Map malformed proof bytes/schema/encoding/duplicate/depth failures to `malformed`; invalid or incomplete immutable expectation, or invalid caller time, to `invalid_expectation`; any exact expected-context mismatch to `context_mismatch`; `now_ms >= expires_at_ms` to `expired`; wrong public-key shape/curve to `unsupported_key`; and DER parse/range/canonicality or cryptographic verification failure to `invalid_signature`. Never include submitted values, signature bytes, exception text, or key material in any public result or representation. There is no wire response in this claim; any later endpoint must map every rejection to the adopted content-free protocol response and must treat authority/database failures separately as unavailable. Missing crypto support must fail closed at import/startup and can never fall through as success. Do not expose the internal code directly to a phone.

**Required adversarial tests:** generate ephemeral test-only P-256 keys in memory and prove a valid proof verifies using a test-side independent transcript assembler. Include a literal transcript hex oracle for fixed test fields and assert JSON whitespace/member reordering preserves verification. For every mutable signed field, test both (a) changing only proof bytes/value yields `context_mismatch`, and (b) changing the proof and matching expected context while retaining the old signature yields `invalid_signature`. Keep fixed protocol/purpose pinned and verify those transcript bytes against the literal oracle. Show proof signed by key B is rejected with trusted key A even when all IDs/context match, and accepted with B. Reject tampered challenge/service/host/key/generation/expiry/signature; unknown, duplicate (including escaped-equivalent names), missing, oversized, invalid UTF-8, nested/deep, nonfinite, wrong-type (including bool-as-int), empty/oversized identifier and noncanonical base64url inputs; malformed/noncanonical/out-of-range DER; wrong key length/point/curve; and expiry boundary. Explicitly verify valid high-S and low-S signatures are accepted. Invalid `now_ms` cases include bool, negative, float/NaN, and values above `2^53-1`; malformed and incomplete expected-context objects also return `invalid_expectation` without raising. Verify all public result representations expose only `valid` and fixed `code`; parsed proof helpers are not in the public API. Prove no proof-supplied owner/device/grant/scope can enter the result and malformed input never raises detailed parse/crypto errors to the caller. Use the actual cryptographic verifier with synthetic keys, never a fake-success verifier. Do not test challenge replay as if this module consumes challenges; a later replay test must consume challenge ID, not signature/hash.

**Dependency evidence:** `requirements-lock.txt` lists `cryptography==50.0.0`, while `requirements.txt` declares unpinned `cryptography`; the lock entry alone does not prove CI or runtime uses that exact version. This worktree's Python 3.12.13 lacks the package, so its earlier unittest attempt stopped at import and is not the final test receipt. The parent verified the exact transferred candidate under Python 3.12.14, cryptography 50.0.0, OpenSSL 4.0.1; no package install or workflow change was made.

**Final source and validation receipt:** exact two-path source candidate `7406dc8e1a2af89cafac71418ca89dd27941d781` (tree `075e12aea1bc7736b56eeedcdc145c4da3cf78de`) was independently ACCEPTED. The exact source hashes are `c7749602fc574c5d8b48a41b36da8ebf4ea01029e2727fd2de3cdcb010310bed` for `jarvis/bot/phone_remote_auth_proof.py` and `80e6b4d6074d403a90b216016228682b9eb2ac54c7545459af6733e28780e0d6` for `tests/unit/test_phone_remote_auth_proof.py`. Parent ran `python3.12 -m unittest tests.unit.test_phone_remote_auth_proof`: 20 tests passed, 0 failures, in 0.047 seconds under Python 3.12.14, cryptography 50.0.0, OpenSSL 4.0.1. Independent native review also passed 327 cases against the same module, including crypto/key substitution, high-S signatures, and redaction. Local `py_compile`, committed-range `git diff --check`, and roadmap check passed. Earlier candidate `dcfba65c58259c04acdfd1d11c51ac28f593c2f0` and its 19-test receipt are historical, superseded by the corrected final candidate; the earlier working-tree-only diff check is not the final committed-range evidence. The final code remains a pure verifier and establishes no production authentication, enrollment, challenge consumption, or session issuance.

**Explicitly deferred security boundary:** proof verification alone does not establish Secure Enclave use, fresh Face ID/passcode, or user presence; the native app must gate the signing operation locally, and the server cannot infer that fact from signature possession. A later authority integration must issue unpredictable expiring challenges and consume each exactly once in the same serialized stable-authority decision that rechecks enrolled key, owner/device mapping, current authority generation, and session-creation rules. A signature accepted here neither consumes a nonce nor mints a session. D1 pairing/auth/session semantics, D2 protected anchor/locked-session Keychain requirements, and D3 WS-17 restore coverage remain under technical review. R3.15 is pure offline verifier code only; production authentication, Keychain integration, challenge/session state, and endpoints remain blocked on those reviews and atomic challenge/session design.

### R3.7 Adopted WS-30 fake-host Swift package claim — 2026-10-29

The coordinator adopts this exact six-file WS-30 source claim branch-locally on `codex/ws04-phone-admission-core-20261029` in PR #290, under the one-final-merge exception. Independent documentation review ACCEPTED the pre-adoption proposal at exact ROADMAP hash `74156c60179d8543527909e07690bd309649a88807afc472d79b95ddc57ad3d2` and plan hash `8b520291f1c8e8f75f3ea0f85427758e1e5602b41e9ac11df63ec751aff5ef2e`. The source is integrated at exact candidate commit `c0a0de93d046c13a4b64f21d2b0e18cd3559a274` in PR #290, whose current published head is `66121b8c643d301e1c8e2ec616b9f9b45ac80e2d`; independent source review ACCEPTED the source commit, and local package tests passed 15/15. This does not establish repository CI coverage, an iOS app/build, device or live acceptance. WS-30 remains accountable for the phone-client slice; WS-04 owns admission, WS-17 owns result projection, and WS-05 owns speech/provider readiness.

**Exact source/test scope:**

- `ios/MortimerPhoneCore/Package.swift`
- `ios/MortimerPhoneCore/Sources/MortimerPhoneCore/PhoneRemoteProtocolV1.swift`
- `ios/MortimerPhoneCore/Sources/MortimerPhoneCore/PhoneSessionState.swift`
- `ios/MortimerPhoneCore/Tests/MortimerPhoneCoreTests/FakePhoneRemoteHost.swift`
- `ios/MortimerPhoneCore/Tests/MortimerPhoneCoreTests/PhoneRemoteProtocolTests.swift`
- `ios/MortimerPhoneCore/Tests/MortimerPhoneCoreTests/PhoneSessionStateTests.swift`

**Exact implementation receipt:** all six source blobs match the independently accepted candidate hashes:

| Path | SHA-256 |
| --- | --- |
| `Package.swift` | `e37b3036416755af2eb66cbc8c84e9201ec0848b17ef88fc40e1f4dfa0c68ab2` |
| `Sources/MortimerPhoneCore/PhoneRemoteProtocolV1.swift` | `46d1dfdcf57e1f303d9c59451bad36881f4e3eb1183789f42714911ff82e17ce` |
| `Sources/MortimerPhoneCore/PhoneSessionState.swift` | `03fbd26170b374168020319bf44467d164b9faddcb7f3879b9ea968e3b5fe8a5` |
| `Tests/MortimerPhoneCoreTests/FakePhoneRemoteHost.swift` | `25e130d2764c8e341d6029bf8ebc5751cc9edb5c804ad591d9b1f5bf1404dcce` |
| `Tests/MortimerPhoneCoreTests/PhoneRemoteProtocolTests.swift` | `f7fd9d2ce53d16d30f31f547da996c75f7610a19f75f2c24706a5a429639fa5a` |
| `Tests/MortimerPhoneCoreTests/PhoneSessionStateTests.swift` | `91d17217ad1b350bf0866dbd3f16543438d19f00955ad3e5efa7b4c056b44b15` |

**Protocol boundary and compatibility choices:** reuse only the R3.4 `mortimer.phone-remote.v1` contract: request envelope fields `kind`, `protocol_version`, `request_id`, `operation`, and typed `payload`; response fields `request_id`, fixed status (`ok`, `denied`, `unavailable`, `incompatible`), content-free `reason`, and typed admitted `payload`. The operation enum may contain only the nine R3.4 names. Model the outer envelope with generic typed payload/reason parameters; this slice defines no concrete auth, session, result, voice, or call payload schemas and invents no reason codes. Reject an unknown envelope kind, unsupported major version, unknown operation, or extra envelope key. Authentication and all owner/device/grant/session/host bindings remain server-derived; the client adds no identity or bearer fields. Per-operation closed payload schemas wait for the owning WS-04/WS-17 contract review.

The fake host is test-only, deterministic, in-memory, and injected; it opens no socket or URLSession and stores no credential. The state model represents local request/reconnect/denied/unavailable/incompatible/end states and maps only the R3.4 response statuses; `reconnecting` is local transport state, not a new wire status. The fake exercises envelope/status behavior only. It does not claim result-card behavior: `results.snapshot`/`results.resume` payloads and rendering wait for WS-17's accepted result envelope. It does not claim voice readiness: `voice.*` remain unavailable fixtures until WS-05's disposition. It does not implement calls or call invitations: `call.*`, CallKit, PushKit and APNs require a later separate claim.

Use Swift tools 6.2 to match the repository's current Swift package baseline, with Foundation-only code, no `JarvisKit`/WebRTC dependency, no SwiftUI, AVFoundation, CallKit, PushKit, Keychain or network framework import, and no explicit iOS deployment target until Larry selects the supported OS. This permits macOS-hosted package tests but proves no iOS build or app behavior. Focused command is `swift test --package-path ios/MortimerPhoneCore`; it passed locally on 2026-10-29 with Swift 6.4 on macOS (15 tests, 0 failures; the host OS version was not recorded). Existing repository CI does not run this package, and no CI workflow file is in this claim. A separate exact `.github/workflows/validate.yml` coverage claim is adopted branch-locally in R3.8; no workflow edit or CI acceptance is claimed. No Xcode app target, signing, entitlements, URL scheme, UI activation, microphone, APNs provider, tunnel or live service is included.

**Acceptance for this claim:** the listed tests cover closed envelope decoding, exact R3 operation/status names, generic fixture payload round-trip, unknown operation/version/extra-envelope rejection, deterministic fake-host responses, local reconnect/state transitions, and fail-closed non-ready states. `swift test --package-path ios/MortimerPhoneCore` passed locally, 15/15. Exact-source independent review ACCEPTED commit `c0a0de93d046c13a4b64f21d2b0e18cd3559a274`. Repository CI acceptance remains open until a separately reviewed/adopted workflow claim runs the package. No result content, authentication outcome, real session identity, call admission, provider readiness, transport reachability, or iOS compatibility is asserted. Store S1 is not needed to run this isolated fixture package; any real-host connection must wait for accepted WS-04 store/facade work. Card/result tests require WS-17's exact result DTO and classification contract; voice tests require WS-05's route disposition. These are dependencies, not WS-30 ownership transfers.

**Self-audit:** no separate plan/database; 0035 untouched; proposed 0037 collision-checked at dated refs, not assumed forever free; no anchor/vault-item reuse; independent generation, host-ID and login-incarnation checks are reserved branch-locally; whole-host limitation explicit; restore trigger left with actual owner; native direction supersedes historical web-first text only; the fake-host package is implemented at the reviewed exact commit and passed local package tests, while the branch-local CI claim is adopted but workflow implementation and CI acceptance remain open; branch-local claims exception does not waive exact-source review or live gates; no new live acceptance checkboxes closed.

### R3.8 Adopted WS-30 Swift package CI claim — 2026-10-29

The coordinator adopts this exact one-file WS-30 CI claim branch-locally on `codex/ws04-phone-admission-core-20261029` in draft PR #290 following independent documentation review at exact ROADMAP hash `f1eb80d218e1df69af72be66caf4f0216e082bce80b0758e09f23fd0aaa9f875` and plan hash `df80c620df1ecb4564790278b242360bcad5d972b4ffc6e0edf00148051cb892`. The workflow file remains unchanged. WS-30 is accountable for the phone-core test job. WS-12's Claude-owned CI-maintenance slice is accepted and closed, with no active file lock. Because this claim edits a shared workflow previously maintained under WS-12 and containing the narrow WS-20 roadmap-check step, coordinate a Claude handoff and exact-diff cross-review before editing. Preserve both prior owners' hunk and action/runner conventions; this does not reopen or transfer WS-12/WS-20 ownership.

**Exact source path:** `.github/workflows/validate.yml` only. Add one `phone-core-swift` job:

```yaml
  phone-core-swift:
    runs-on: macos-15-intel
    env:
      DEVELOPER_DIR: /Applications/Xcode_26.3.app/Contents/Developer
    steps:
      - uses: actions/checkout@v7
        with:
          persist-credentials: false
      - name: Record selected Apple toolchain
        run: |
          xcodebuild -version
          swift --version
          xcrun --version
          xcrun --find xctest
      - name: Test Mortimer phone core
        run: swift test --package-path ios/MortimerPhoneCore
```

Keep the existing `pull_request` trigger, all current jobs and steps, and workflow-level `permissions: contents: read` unchanged. The new job adds no credential, permission, package dependency, toolchain installation, signing, app build or deployment. `Package.swift` declares `swift-tools-version: 6.2`; the tests also launch `/usr/bin/xcrun xctest` for a child-process decoder regression, so a Linux runner is incompatible. The macOS 15 image's default Xcode 16.4 supplies Swift 6.1 and is too old for the package tools baseline. Set the job's `DEVELOPER_DIR` to the image's installed `/Applications/Xcode_26.3.app/Contents/Developer`; the image inventory lists that path and the Xcode command-line tools, and Apple's Xcode 26.3 release notes identify Swift 6.2.3. Record `xcodebuild -version`, `swift --version`, `xcrun --version`, and `xcrun --find xctest` so the chosen version and child-test executable are visible in each run. SwiftPM enforces the package tools baseline. The official GitHub hosted-runner reference lists `macos-15-intel` as a standard public-repository runner; standard GitHub-hosted runners are free and unlimited for public repositories.

Evidence checked 2026-10-29: [GitHub hosted-runner labels and public-repository policy](https://docs.github.com/en/actions/reference/runners/github-hosted-runners); [macOS 15 runner image inventory](https://github.com/actions/runner-images/blob/main/images/macos/macos-15-Readme.md); [Apple Xcode 26.3 release notes](https://developer.apple.com/documentation/xcode-release-notes/xcode-26_3-release-notes). Images can change; the job's toolchain receipt remains authoritative for each run. Acceptance requires this exact job to pass on the integrated source head after the workflow edit is independently reviewed and adopted. It proves only package CI, not an iOS app/build, phone, tunnel, service or live acceptance.

### R3.9 Adopted branch-local WS-04 store-backed in-process service scope — 2026-10-29

This exact branch-local WS-04 scope extension is adopted on `codex/ws04-phone-admission-core-20261029`, draft PR #290, current published PR head `628d743efa6b23b3341840594b176f9562bcc154`, based on main `5310d1a9305035f43143fcffad6161619281f475`. Independent documentation review ACCEPTED the proposal content at ROADMAP SHA-256 `68bdd5fd55735ec2282ec6b0755de574460381de3ba0eac41684b05265e8468a` and plan SHA-256 `58453a99781bee3568e3fd447ecde53a89331b8e4df0f2b619a7fa96fc4fd5ce`; coordinator adoption and the exact effective scope are recorded above. Independent source review ACCEPTED exact bounded S2 source commit `f516d73dd5028391ede2bb1f4cf30d83f10069a8`. The focused command `python3.12 -m unittest tests.unit.test_phone_admission tests.unit.test_phone_admission_contract tests.unit.test_phone_admission_store tests.unit.test_phone_remote_protocol tests.unit.test_phone_remote_service` passed 100 tests (11 S0/core tests and 89 store/protocol/service tests); the unchanged S0 contract adapter exercises all 70 frozen vectors against the legacy core. This is synthetic S2 source evidence only: it does not establish full-suite success, a real admission-boundary adapter run, production transport, or live acceptance. Historical validation receipt for earlier head `f516d73dd5028391ede2bb1f4cf30d83f10069a8`: run #535, job 124152409275 (`https://github.com/Larryfix71566/jarvis-voice-ai/actions/runs/41081754296/job/124152409275`) reported 1 failed, 7296 passed, 11 skipped, and 288 subtests passed; the failure was WS-05 capability test `tests/unit/test_claude_developer_capability.py::test_actual_new_python_worker_checks_system_marker_only[positive]`, whose no-artifact assertion found `request.parent/probe.db`. Read-only diagnosis found no phone-source change to the failing test or validator. An explicit isolated notifier tick reproduced creation of a 4096-byte SQLite file at the worker-provided `JARVIS_DB_PATH`; CI did not record the artifact-creating PID, so this reproduces a plausible mechanism but does not prove that notifier created the CI artifact. This historical CI failure is separate from the independent ACCEPT of exact S2 source. After the reviewed WS-05 fixture repair, current published head `628d743efa6b23b3341840594b176f9562bcc154` passed run #537 with 7298 unit tests, 11 skips and 288 subtests; 197 integration tests with four skips; 13 evals; and latency, frontend, policy and allowlist checks. Sandbox controller #715 and Knowledge base #719 passed. These receipts cover the published head only, not the unpublished combined R3.10 candidate. The R3.8 Swift CI handoff is independent and does not block this S2 source acceptance.

**Collision check, 2026-10-29:** the connected GitHub read showed only PR #290 open in this repository; phone-named branch results were the current integration branch and historical plan/claim documentation branches. The new protocol/service paths below are absent from the integration checkout; no competing source PR for this slice was found. Existing `phone_admission.py`, `phone_admission_store.py`, and their WS-04 tests are already within the current WS-04 branch claim, but edits to their S1 behavior require this exact extension. Recheck main, branch refs, and open PRs before source work; this dated search is not a permanent lock. WS-17 continues to own result projection and the restore hook; WS-05 owns speech/provider readiness; WS-30 owns its Swift package and later app/call implementation.

**Exact adopted source scope:**

- Modify `jarvis/bot/phone_admission_store.py` and `tests/unit/test_phone_admission_store.py` only among existing source/test files.
- Add `jarvis/bot/phone_remote_protocol.py`, `jarvis/bot/phone_remote_service.py`, `tests/unit/test_phone_remote_protocol.py`, and `tests/unit/test_phone_remote_service.py`.
- Update this WS-04 roadmap block and this existing plan only. Keep `jarvis/bot/phone_admission.py`, `tests/unit/test_phone_admission.py`, `tests/unit/test_phone_admission_contract.py`, and `tests/fixtures/phone_admission_contract/v1.json` byte-identical and read-only for this slice.

No `jarvis/db.py`, production migration, authentication middleware, config, vault/Keychain provider, restore/deployment script, `jarvis/bot/server.py` or admin route, Swift/JarvisKit, provider, mail, display, allow-list or other owner's path is included. Do not add a second authority database or copy the SQLite store into mutable admission-core dictionaries. `PhoneAdmissionCore` is a mutable S0 state machine, not a stateless predicate; no pure predicate extraction is proposed. Leave it and its original tests as the legacy oracle, preserve its S0 interface, and never expose `core.step` as a phone operation. The new service must use the store as authority without depending on the S0 core's mutable dictionaries.

**Authority and transaction boundary:** a trusted in-process request context must combine the repository's verified `ClientIdentity` with a server-authenticated device binding and current server login handle. JSON payloads cannot create or override those values. There is no production cryptographic paired-device verifier yet; tests use an explicit fake, and no real phone authentication or pairing is claimed. The store's immutable binding carried through ticket, peer, command and output checks includes owner, device, grant, session, login incarnation, host ID/generation, grant/session generations, process incarnation and granted scopes. A successful atomic check-and-consume returns that binding; create a peer only from that returned value. An update must revalidate its existing peer's full binding before consuming a purpose-bound update ticket. Revalidate authority on every command/output, not only at initial admission. Prepare media/output outside the authority lock. Then under the same short serialized authority guard used by revocation, revalidate and atomically commit peer publication or a bounded nonblocking synthetic-sink enqueue; never invoke arbitrary or blocking callbacks under the guard. If revocation wins before commit, deny and clean up prepared state. If commit wins, revocation follows it in the same order and cancels queued-but-undelivered output/peer work where possible. Bytes already dequeued or handed to the transport are irretrievable. This is an in-process synthetic linearization contract, not proof of network delivery cancellation.

**Protocol boundary:** keep the R3.4 `mortimer.phone-remote.v1` outer envelope and exact nine operation names. Preserve the four response fields exactly: `request_id`, `status`, `reason`, and `payload`. A validated nonempty request ID is echoed; if parsing fails before a trustworthy ID is available, generate a server-owned opaque UUID for the response and never echo unvalidated bytes. Reject duplicate JSON keys, extra keys, wrong/empty types, non-finite numbers and unknown operations/versions; cap a request at 1 MiB, nesting at depth 64, and a valid request ID at 128 UTF-8 bytes. Do not accept identity, grant, scope, source classification, internal ticket or path/action authority from the phone. Proposed closed operation payloads and success responses are:

- `session.status` request payload `{}` returns `status=ok`, `reason=none`, `payload={readiness: "ready"}` only when enabled and current authority is ready. Otherwise return an empty payload with the existing unavailable/denied status and a fixed reason; never enumerate owners, devices, grants, counters or credentials.
- `voice.offer` request payload `{sdp: string}` and `voice.update` `{peer_id: string, sdp: string}` use an injected fake media adapter after fresh admission; update additionally requires the current purpose-bound ticket and peer binding. Their success payload is exactly `{peer_id: string, sdp: string}` with a server-generated peer ID and fake SDP answer. SDP is ephemeral, not logged or persisted; keep ICE/path selection outside this slice.
- `voice.end` request payload `{peer_id: string}` returns success payload exactly `{peer_id: string, ended: true}` as a scoped idempotent receipt. Restart, expiry and revoke close fake media/peer authority; reconnect reservations do not authorize media.
- Recognize `results.snapshot`, `results.resume`, `call.state`, `call.answer` and `call.decline` only as unavailable operations. WS-17's result DTO/classification and WS-30's call implementation remain separate claims.

Use only the existing response envelope's fixed statuses: `ok`, `denied`, `unavailable`, and `incompatible`. The closed, content-free reason enum includes neutral success `none` and failures `feature_off`, `malformed_request`, `unsupported_protocol`, `not_authorized`, `authority_unavailable`, `voice_not_ready`, `owner_busy`, `operation_unavailable`, `request_conflict`, and `request_capacity`. Map unsupported versions to `incompatible`; authorization, malformed input and request conflicts to `denied`; unavailable authority/media/owner or not-yet-implemented operations to `unavailable`. Error payloads are exactly `{}`. Never return exception text, record existence, ticket material, or secrets.

**Replay and lease policy:** maintain a bounded process-local request ledger keyed only by the complete authorization binding plus request ID. Operation, protocol version and canonical payload digest are stored comparison data, not key partitions. Atomically reserve an `in_flight` entry before effects. A duplicate in-flight request cannot run effects; it receives `denied/request_conflict/{}`. A completed exact retry may return its stored final receipt only after current authority revalidation. Reuse of that request ID with a different operation, version or payload digest is denied as `request_conflict`. Proposed caps are 256 request IDs per live authorization binding and 4096 entries process-wide. Retain receipts/retirement markers for the binding's entire admitted lifetime; never LRU-evict history for an active binding. Remove a binding's entries only after the store proves its login incarnation terminally expired/revoked and non-reusable. At a per-binding cap, refuse new request IDs with `denied/request_capacity/{}` until explicit fresh session/login; if the process cap remains full after safe terminal cleanup, refuse new work rather than evict live history. Restart invalidates the ledger, peers and tickets and requires fresh login. A media preparation failure after reservation/consumption stores a terminal `unavailable/voice_not_ready/{}` receipt; an exact retry repeats that receipt without rerunning media. A new attempt requires a fresh ticket and new request ID. Enforce one phone lease per owner; do not preempt a live lease. Owner/Mac availability is injected and fail-closed; the lease does not represent OS microphone permission or CallKit consent.

**Output policy and revocation ordering:** require server-derived provenance/classification and destination-grant decisions before serialization; unknown, legacy, protected or malformed content is denied. Display permission never authorizes model/STT/TTS processing. Audio requires the current lease, voice scope and admitted source. Prepare media or content outside the authority guard, then revalidate and atomically commit peer publication or bounded queue insertion under the same guard that serializes revocation. A fake sink must be nonblocking and bounded; no arbitrary callback runs under the lock. A revoke arriving before commit prevents publication; after commit it cancels queued-but-undelivered items where possible. Bytes already dequeued/emitted cannot be recalled. Add deterministic interleaving tests for revoke after preparation/before final check, revoke racing with commit, and cleanup/cancellation after publication. A fake-clock test closes affected peers within five seconds and immediately denies new commands after revoke; this is synthetic evidence, not a production scheduler. No actual result content or transport is implemented in this slice.

**S0 semantic and store-conformance gate:** preserve the frozen 70-vector legacy oracle, seven sensitivity mutations, three isolation probes, `tests/unit/test_phone_admission_contract.py`, and fixture bytes unchanged. Run the existing vectors against the legacy S0 core; do not adapt their expectations or insert restore preparation into an adapter. The S0-03 `session-vs-global` vector requires grant-A revocation to invalidate live peers from grants A and B. Phone plan §4 line 149 and §13 S0-03 line 371 independently require credential registration/replacement, grant revocation, grant-scope reduction, and authorized restore to advance the protected global host generation and conservatively invalidate every live remote session; session-only sign-out remains scoped. R3.2 distinguishes session sign-out from grant revocation but does not explicitly supersede the canonical global-invalidation rule. The grant-scoped revocation behavior was a pre-S2 defect and is historical, not the current candidate behavior: exact source `f516d73dd5028391ede2bb1f4cf30d83f10069a8` implements global invalidation in the synthetic store and was independently accepted. This acceptance is limited to the fake-anchor SQLite store and synthetic service; production anchor durability, authorized restore wiring, and live global-revocation behavior remain unproven. The normative global-invalidation contract remains unchanged. Do not revise the phone plan or frozen fixture to fit the current store.

Any global security-authority mutation must be one fail-closed transition under a shared authority guard: first validate a stable anchor/database pair, caller authorization, and target without mutating state; reserve a strictly higher protected host generation with a unique pending transition; in one SQLite transaction apply the security mutation and invalidate all existing remote login sessions; finalize the protected anchor/database in the specified pending-first order; acknowledge only after both sides are stable and matching; then invalidate every cached admission/ticket and notify all affected peers to close. A failed authorization or repeated revocation is a non-mutating denial. Do not implement this as a separately locked `advance_host_generation()` followed by a second mutation. It applies to device/credential registration or replacement, grant/device revocation, and future scope reduction. Classify `add_device` as credential registration and require the same global transition. Classify `add_grant` as new grant enrollment: it may create only a new grant ID bound to an existing verified device/owner, may not rebind, re-enable or mutate an existing grant, and uses the same conservative global transition so sessions cannot observe partially changed authority. Future edits to an existing grant's scopes require the global transition too. After grant A is revoked and the global transition finalizes, an unaffected B device remains enrolled and may authenticate afresh against current grants, but no pre-transition A or B session, ticket, peer, or output authority survives.

Session-only sign-out must remain a per-session revocation-generation change and must not advance the global host generation, even across repeated adversarial stale-DB restores. The frozen snapshot→revoke→raw-old-database-restore events model adversarial stale database appearance, not an authorized restore workflow. Do not add restore preparation or synthesize expected failures in the adapter: the restored database must naturally fail closed because it cannot match the independent protected authority. Authorized restore remains a separately owned workflow and advances the host anchor before database replacement under phone plan §4/§13.

The S2 store tests must prove: grant-A revocation denies all old A and B sessions/tickets/peers while a fresh B login succeeds and A fails; session-only sign-out denies only that session and preserves unrelated live sessions, including under repeated stale-database restores; crash or failure at every pending/SQLite-commit/finalize boundary stays closed; concurrent login, revoke, and ticket consume cannot cross the transition; failed validation/mutation does not advance the protected counter; pending global authority denies operations for every grant; and fixed reason/status plus externally observable state have an independently reviewed mapping. Preserve the remaining frozen vectors too, especially consume-before-revoke, lost-notification deadline, revoke-old-snapshot, stale-then-revoke-other-grant, scope-reduction/older-broader-snapshot, crash transitions, `ignore_global`, `ignore_anchor`, and the session-fence vectors that prohibit overbroad global sign-out. Keep all 70 vectors, seven sensitivities, three isolation probes, and fixture bytes unchanged.

With R3.9 now adopted, S2 tests must additionally cover cross-owner and same-owner/different-device/grant denial; host/generation/incarnation/process/scope/session changes fencing peers, commands and output; concurrent one-time consume; stale update peer; media failure after consume; feature-off before inventory/adapter calls; strict JSON and response redaction; exact replay versus request-ID conflict/capacity; no lease preemption; revoke/prepare/check/commit/output interleavings; immediate post-revoke command denial and five-second fake-clock peer close; readiness/unavailable behavior; and canary absence at output/provider/log/cache sinks. Exercise SQLite only with the injected fake anchor, not real Keychain durability. Preserve the explicit limitation for arbitrary whole-host/anchor rollback and unhooked restores. Run focused S2 tests, repository-required checks and independent exact-source review; record exact source hashes and actual test totals.

This claim adds no public route, listener, ASGI application, login/enrollment/revocation endpoint, migration, real media, or service activation. D1 pairing/verifier, D2 protected production anchor, D3 WS-17 restore invocation, D4 Mac availability/sleep/restart behavior, WS-17 result contract, WS-05 voice readiness, TLS/tunnel, Apple signing, device, install and live acceptance remain open. These are not blockers for the offline fake-based S2 source after documentation review/adoption.

### R3.10 Coordinator-adopted branch-local WS-04 claim — default-off ASGI adapter (2026-10-30)

The parent coordinator adopted this previously reviewed proposal for the one-final-merge PR #290 integration and assigned GPT-6 Luna as author with the existing WS-04 nonauthor reviewer. The branch-local implementation candidate is `codex/ws04-phone-remote-asgi-20261030`, based on the verified published PR head `7c4ef9e4fc10998394413f029757c0916ca8abeb` (main ancestor `5310d1a9305035f43143fcffad6161619281f475`). This remains separate from R3.9 and is not an activation decision. The branch-local claim uses the coordinator-approved one-final-merge exception recorded in §3; it authorizes only the exact files and offline behavior below, subject to independent exact-source review and final integration review.

- Add `jarvis/bot/phone_remote_asgi.py` and `tests/unit/test_phone_remote_asgi.py` for a narrow WebSocket ASGI adapter that accepts only the existing `mortimer.phone-remote.v1` envelopes and delegates each request to the R3.9 `PhoneRemoteService`.
- Exact source scope is only the new `jarvis/bot/phone_remote_asgi.py` and `tests/unit/test_phone_remote_asgi.py`. The module is an in-process ASGI adapter whose service and trusted context are injected; it does not edit or mount into `jarvis/bot/server.py`, construct production dependencies, start a server, or activate a listener. `/ws/phone-remote` is only the adapter’s path identifier in its offline harness; no runtime route is allocated by this claim.
- Keep `tests/unit/test_phone_admission_contract.py` and `tests/fixtures/phone_admission_contract/v1.json` unchanged and outside this claim. R3.5 and phone-plan §13 continue to require the unchanged 70-vector, seven-sensitivity and three-isolation oracle at the later real admission/store boundary. That mapping and acceptance remain a future claim requirement; this R3.10 claim does not waive or implement it, and it is not a retroactive R3.9 S2 gate.
- Accept only an exact injected boolean `enabled=True`; the adapter reads no environment/configuration itself. Missing, false, malformed gate values or service/context dependencies make it unavailable and expose no usable route. The service and context provider must be injected by server-owned dependencies. Resolve a connection binding once, then resolve a fresh trusted context for each `voice.offer` and `voice.update`; these request contexts must preserve the exact authenticated identity object and owner/device/session/login-incarnation binding. The parsed closed envelope is only an untrusted selector for an already server-issued ticket: do not derive authority or issue a ticket from phone JSON, and never accept identity/scope/ticket fields from it. R3.9 must revalidate ticket purpose, payload digest, peer and current authority. Never construct `TrustedRequestContext` identity from phone JSON, use mutable `PhoneAdmissionCore` state as the adapter's authority, expose `core.step`, or create a second store/authority. The only available effects remain the R3.9 synthetic service operations; the reserved result/call operations remain unavailable.
- Offline tests must exercise the adapter through an in-process ASGI harness with fake service/context providers and no socket/listener. Cover default-off and malformed injected-gate behavior, absent dependencies, exact envelope forwarding/response encoding, ASGI text/bytes optional-null handling, malformed and oversized frames, disconnect/cleanup, untrusted JSON identity, exception redaction, fresh request-specific ticket context with a real S2 offer→update, event-loop progress during blocking service/context dependencies, caller `ContextVar` isolation, bounded concurrent dispatch and cancellation/drain, and adapter-local route availability. Synchronous service methods and synchronous context providers run off-loop under one shared per-event-loop four-worker limit across adapter instances; a context-provider slot remains held through any returned awaitable. Cancellation drains started work and returned provider awaitables; worker ownership and capacity persist through actual completion, including event-loop shutdown. Draining cannot force an injected synchronous or asynchronous dependency to finish: cancellation remains pending and its worker slot stays held until that dependency completes. This synthetic adapter does not provide a production timeout or scheduler. Do not claim existing bot/server route or bind integration tests under this module-only scope. Run the focused ASGI test, the complete phone suite and required repository validation; bind receipts to the exact source hashes.
- Exact paths exclude `jarvis/bot/server.py`, `tests/unit/test_bot_server.py`, `jarvis/auth.py`, `jarvis/authmw.py`, `jarvis/bind.py`, config files, migrations/`jarvis/db.py`, Keychain/vault, restore scripts, provider/media implementations, iOS/macOS UI, WS-17 result projection, and WS-30 call/invitation work. Any need to add a path requires a reviewed claim amendment before editing.

- **Branch-local adoption boundary:** This claim is not published or merged. Its source authorization is limited to the exact two new paths above and only the pre-reviewed offline ASGI adapter behavior. No code outside them, no runtime wiring, and no production route/listener follows. Reviewer and Larry integration approval remain required; the one-final-merge exception does not waive review or live/security gates.
- **2026-10-30 progress:** Parent coordinator adopted the exact R3.10 proposal for branch-local implementation in the one-final-merge integration and assigned the existing WS-04 nonauthor reviewer. Standalone ASGI source candidate `b30369c103d8412a534fdf2837d427ec67dd77e3` was independently ACCEPTED; it passed 23 focused and 123 six-module phone tests. Review-driven fixes cover ASGI optional-null text/bytes fields, fresh trusted server-issued ticket contexts per offer/update, blocking service/context providers, one-time normalization of custom awaitables, and cancellation drain. Each synchronous invocation receives a fresh copy of caller `ContextVar` context. The shared four-worker per-loop bound spans adapter instances and holds through a context provider's returned awaitable. Cancellation drain depends on injected blocking/async work eventually completing; a stuck dependency leaves the awaiting request pending and retains its worker slot. SHA-256: `jarvis/bot/phone_remote_asgi.py` `d36c06bc022a8246586c6a8a02634691805d9e0a786b4ce2d905acaf722bd885`; `tests/unit/test_phone_remote_asgi.py` `c918735920b93e66685783236b32cffac83ab9edb9ea707e99781041d156d8f2`. These source files are unchanged in the combined candidate. The local combined candidate `f3e98cae335d00fc20133a74710ddb06a2066c89` is on `codex/ws04-phone-remote-asgi-combined-20261030`, with parent current PR #290 head `628d743efa6b23b3341840594b176f9562bcc154`. It includes the accepted three-file WS-05 fixture repair and refreshes R3.10 evidence to 23/123. Independent review of the combined diff remains pending. Published-head CI run #537 (`41093137005`) and its companion checks passed; those receipts do not cover the unpublished combined candidate, which has no CI run yet. No socket, listener, bot server, production dependencies, publication, merge, or activation was used.

This offline source claim does not implement real pairing/authentication, enrollment/revocation endpoints, or production authority construction. D1 pairing/verifier, D2 protected production anchor, D3 WS-17 restore-hook invocation and D4 Mac availability/sleep/restart behavior remain owner-bound prerequisites for production wiring. The feature stays off; no route/listener is activated, no credential/anchor is created or selected, and no remote bind, tunnel/TLS, installation, deployment, microphone, provider, phone, or live test is permitted by this claim. Larry retains all production-security, configuration-enable, installation, and live-acceptance decisions.

**Current published status (2026-10-30):** the R3.10 combined source/docs candidate was independently accepted and published in PR #290 as cbba8645ceaa7ad81e83b8dce5af3f03d8ce00c5, tree 188cb06814adc03c0f17b1165c1f856189e205ef, parent 628d743efa6b23b3341840594b176f9562bcc154. Exact-head CI run #538 (41095632875) passed 7,322 unit tests, 197 integration tests, 13 evals and all other checks. This is offline integration evidence only.

### R3.11 WS-04 scoped-signout / repeated-restore boundary probe — adopted local claim

**Status: adopted locally by the parent coordinator on 2026-10-30 for the one-final-merge PR #290 integration.** GPT-6 Luna authors this single synthetic boundary test; the existing WS-04 nonauthor reviewer checks its exact result. This is not the 70-vector R3.5/phone-plan §13 conformance mapping, and it maps/passes zero fixture vectors.

- **Exact source path:** add only `tests/unit/test_phone_admission_boundary.py`. Use existing `PhoneAdmissionStore` and `PhoneRemoteService`, disposable SQLite, fake anchor/identity/clock, and bounded fake output sink. No production-source or legacy fixture/harness changes.
- **Combined scenario:** create owner sessions A and B, establish one A voice peer with a cached successful offer receipt and two queued synthetic canary outputs, then snapshot SQLite before A scoped signout. Perform the actual signout and restore the raw pre-signout snapshot twice, without restore preparation hooks. After each restore, retry A's exact offer request ID and dequeue an output: cached success/SDP must not be returned, output must return no bytes, and the sink queue must lose the stale item. In both rounds B's existing authorized `session.status` must still succeed. B is a status-only unaffected-session control, not a concurrent second owner voice lease.
- **Observations:** exact denied/not_authorized/empty-payload replay response; no output bytes at the drain boundary; one queued item removed per raw restore; B returns ok/none with `{readiness: "ready"}`; final explicit tick closes the one stale peer. These are only the assertions implemented in the test. No private ledger/DB final-state inference, artificial restore hook, or modified fixture expectation.
- **Acceptance and limits:** `python3.12 -m unittest tests.unit.test_phone_admission_boundary` passes the one combined test. Keep `tests/fixtures/phone_admission_contract/v1.json` and `tests/unit/test_phone_admission_contract.py` byte-identical. This scenario is not a vector or sensitivity pass; all 70 fixture vectors remain unmapped at the store/service boundary, and full R3.5/phone §13 conformance remains open.

### R3.12 WS-30 Foundation operation DTO and fake-host slice — adopted branch-local source claim

**Status: adopted by the parent coordinator on 2026-10-30 for this one-final-merge PR #290 integration.** The bounded design was independently accepted. Luna is the author and existing reviewer `01a18584-92e2-7511-aca8-983bb3f230ef` is the nonauthor reviewer. It proceeds independently of unresolved R3.11 mapping. It needs no iPhone model/OS decision because it adds Foundation package types and offline tests, not an app target.

- **Owner and review:** WS-30/Codex owns the phone client contract. Author: GPT-6 Luna. Nonauthor reviewer: existing reviewer `01a18584-92e2-7511-aca8-983bb3f230ef`. The parent remains sole integration coordinator. Keep author and reviewer separate.
- **Exact source paths:** add ios/MortimerPhoneCore/Sources/MortimerPhoneCore/PhoneRemoteOperationsV1.swift; ios/MortimerPhoneCore/Tests/MortimerPhoneCoreTests/FakePhoneRemoteOperationsHost.swift; and ios/MortimerPhoneCore/Tests/MortimerPhoneCoreTests/PhoneRemoteOperationsV1Tests.swift. The existing SPM manifest uses source discovery; no Package.swift change is proposed. Documentation belongs in this existing phone-access plan section and the WS-30 ROADMAP block.
- **Closed operation scope:** define Foundation Codable/Sendable request and response DTOs only for R3.9’s `session.status`, `voice.offer`, `voice.update` and `voice.end` schemas. Requests are respectively `{}`, `{sdp}`, `{peer_id,sdp}` and `{peer_id}`; success payloads are `{readiness:"ready"}`, `{peer_id,sdp}`, `{peer_id,sdp}` and `{peer_id,ended:true}`; error payloads are exactly `{}`. Preserve the R3.4 envelope fields and exact R3.9 statuses (`ok`, `denied`, `unavailable`, `incompatible`) and reasons (`none`, `feature_off`, `malformed_request`, `unsupported_protocol`, `not_authorized`, `authority_unavailable`, `voice_not_ready`, `owner_busy`, `operation_unavailable`, `request_conflict`, `request_capacity`). Reject unknown payload/envelope fields, duplicate JSON keys, wrong or empty required values, and missing fields. Nonempty `request_id` is at most 128 UTF-8 bytes; request JSON is at most 1 MiB and nesting at most 64. Do not add owner, device, grant, session, ticket, scope, path or bearer fields.
- **Checked JSON boundary and fake-host tests:** provide a checked `Data`/JSON boundary rather than relying on synthesized `Codable` alone where it cannot enforce duplicate-key, size, depth, or closed-key rules. Test exact envelope/payload key sets, all four operations, status/reason allowlists, nonempty request-ID minimum and 128-byte maximum, 1 MiB and depth-64 boundaries, duplicate/unknown keys, wrong/missing/empty values, non-finite numbers, and error payload `{}`. Fake host deterministically accepts/denies/unavailable requests and verifies the exact DTO/operation/request-ID behavior; fake peer IDs and SDP are synthetic canaries. No socket, URLSession, service connection, auth, clock, media, microphone, result/call DTO, SwiftUI, app target, signing, iOS deployment target, device-model assumption or live behavior.
- **Existing source and owner boundaries:** do not edit the frozen S0 fixture/legacy harness; R3.7’s reviewed generic protocol/session/fake-host files; R3.8 workflow; R3.10 Python ASGI adapter; WS-04 store/service/auth; WS-17 result projection; WS-05 voice readiness; WS-21 display; or WS-24 recovery. The proposed fake-host helper is a new separate file, not a modification to the accepted generic fake host.
- **Checks and evidence:** run `swift test --package-path ios/MortimerPhoneCore` with the already available toolchain, including the boundary cases above. No dependency installation or CI workflow edit. Record exact source/test paths and count; obtain independent nonauthor review. Tests prove DTO/fake behavior only, not iOS compilation, production connectivity, readiness or live access.
- **Adoption log (2026-10-30):** parent coordinator adopted R3.12 only. Luna implemented the three files on the isolated branch-local candidate. Under `swift test --package-path ios/MortimerPhoneCore`, the initial DTO source commit `38ffbc739950e670a707c24b3cdf12449f56b0ea` passed 29/29 tests; final byte-exact correlation source commit `c018e299b79a32417c448cfbacedcc9e1208f64e` passed 30/30 package tests (15 R3.12 tests and 15 pre-existing tests). Exact source awaits independent reviewer `01a18584-92e2-7511-aca8-983bb3f230ef`; no publication, merge or activation is included.
- **Unresolved production decisions:** none are needed for these test-only DTOs. Do not resolve paired-device verifier, production anchor/restore integration, route/listener construction, private service identity/TLS/tunnel, actual iPhone/OS minimum, signing/entitlements, Mac lock/availability, content grants, provider readiness, call policy, installation or live trial by implication.

### R3.13 WS-30 operation-client wrapper — adopted local source claim

**State:** adopted locally by the parent coordinator after independent proposal review, for the existing one-final-merge PR #290 integration. Final source candidate `4e2507af17be12a40d6afdf07ad8a54f9cc37716` adds only the exact two files below; independent source review by `01a18584-92e2-7511-aca8-983bb3f230ef` is pending. This follows the accepted/published R3.12 checked DTO boundary and reuses the existing local session state machine. The verified published PR #290 base was `ee510cfc8fbfd0973f1a7b7f83699f2ea11738f5` (tree `7c628d3266e9912fcee3ec57827770bc16859079`). The local source is not published and the proposal is not a live-access decision.

- **Owner and review:** WS-30/Codex owns the client contract. Author: GPT-6 Luna. Nonauthor reviewer: existing reviewer `01a18584-92e2-7511-aca8-983bb3f230ef`. Parent remains sole integration coordinator.
- **Exact source paths:** only `ios/MortimerPhoneCore/Sources/MortimerPhoneCore/PhoneRemoteOperationsClient.swift` and `ios/MortimerPhoneCore/Tests/MortimerPhoneCoreTests/PhoneRemoteOperationsClientTests.swift`. No package manifest, R3.12 DTO/parser, `PhoneSessionState.swift`, app target, workflow, or server edits.
- **Boundary and binding:** expose a small async client over an injected byte-transport protocol; only deterministic fake transport belongs to this claim. Every request and response crosses `PhoneRemoteOperationsJSON` checked `Data` APIs. A client instance is bound to its injected transport/session instance and local generation. Generate fresh UUID request IDs and correlate response IDs by exact UTF-8 bytes. Never accept owner, device, grant, session, ticket, scope, path, or bearer authority from phone JSON; any trusted session context is injected by the caller.
- **Single-exchange ownership and state semantics:** allow at most one owned exchange per client instance, with no internal request queue. Reject a new send without touching the transport while an exchange is active, draining, reconnecting, or ended. A precancelled task must not dispatch bytes. Once dispatch begins, mark the exchange as potentially effectful before awaiting transport. On interruption or close, invalidate the local generation before awaiting/draining the exchange; while it drains, reject new work and reconnect. A reconnect is explicit, occurs only after the prior exchange has actually completed, and uses a fresh request ID. Apply a response only if its captured generation and exact UTF-8 request ID are still current; late replies after invalidation neither mutate state nor return success to the caller. Use only existing `PhoneSessionStateMachine` actions and `PhoneRemoteStatus` mappings; do not invent status transitions or fabricate a server status for local cancellation, busy rejection, malformed reply, or transport failure. `voice.end` ends the peer only and must not imply the separate terminal session `.end` action.
- **Uncertain effects and draining:** never automatically replay `voice.offer`, `voice.update`, or `voice.end` after cancellation, interruption, or uncertain transport completion. Do not claim the server did not act. Retain ownership of started transport work until its actual completion even if its caller is cancelled; do not detach it or release the client for another exchange early. Cancellation/close awaits drain; a stuck injected dependency leaves the client pending/draining with no timeout promise and no new dispatch. If these semantics cannot be expressed with the existing state-machine API, stop and propose the smallest separately reviewed API adjustment rather than editing that file under this claim.
- **Offline tests:** use controllable continuations/barriers, not timing sleeps, to test all four operations through checked byte exchange and operation/exact-ID correlation; simultaneous sends (one dispatch only, second rejected); precancel before dispatch (zero bytes sent); interruption/close while bytes are in flight (generation invalidated, call remains draining until actual completion); explicit reconnect rejected during drain then accepted after drain with a fresh ID; late replies after interruption/reconnect/close neither mutate state nor report success; no automatic resend of an effectful request under any uncertainty; stale-generation and mismatched-byte-ID responses; and isolation between two client instances. Also exercise malformed responses through the checked R3.12 boundary and assert that local failures do not create invented server status. Assert only existing state/status behavior. No sockets, URLSession, listener, real service, credentials, microphone, provider, app, signing, device assumption, install, live access, or production construction.
- **Checks and acceptance:** run `swift test --package-path ios/MortimerPhoneCore` using installed tools only; record the command, exact package result and independent review of exact source. This proves only offline client/fake-transport behavior and does not close the separate Swift CI, real-admission mapping, transport, device, production-authentication, or live-acceptance gates.
- **Current collision check (2026-10-30):** fresh PR view showed only open phone-related PR #290; its verified tree does not contain either proposed path, and repository search found no existing claim naming `PhoneRemoteOperationsClient`. Recheck refs, PRs, and claims before implementation; this is not a lasting path lock. Existing WS-30 owns the client contract; WS-04 admission, WS-05 readiness, WS-17 result projection, WS-21 display, and WS-24 recovery remain separate owners.
- **Decisions:** none block this offline source claim. It does not choose transport, authentication, anchor, tunnel, device/OS minimum, signing, availability, content grants, provider readiness, call policy, incoming-call delivery, installation, or live-trial behavior. Those require their existing owner/Larry gates.
- **Implementation/check receipt (2026-10-30):** source commit `4e2507af17be12a40d6afdf07ad8a54f9cc37716` passed `swift test --package-path ios/MortimerPhoneCore` 40/40 (10 new client tests and 30 existing package tests). The cancellation gate atomically arbitrates cancellation against encoding completion, transport dispatch, and response publication; deterministic unit coverage asserts cancellation wins before dispatch/publication and publication wins if already committed. `git diff --check` and `python3 scripts/check_roadmap.py --main github/main` passed. Exact-source review remains pending; no publication or activation is included.


### Combined local source checkpoint (2026-10-30)

The accepted R3.15 proof-verifier delta and the separately accepted WS-17 generated-rollback guard are present together in local branch `codex/ws17-r315-combined-20261030`, based on current published PR #290 head `838bac7d76dd282f21ad019dd9234b693c612fc3`. Source checkpoint `6eaf6214e02bd8c6f9e3384effb7737f2266302a` (tree `626af61eb1075bd89b83bbf7522d5d70ec507ec2`) contains both accepted source deltas; ownership and scope remain separate. Combined command `python -m pytest tests/unit/test_deploy_main.py tests/unit/test_deploy_held.py tests/unit/test_phone_remote_auth_proof.py -q` passed 107 tests and 71 subtests under Python 3.12.13, cryptography 50.0.0 and OpenSSL 4.0.1. The rollback guard rejects arguments in newly generated non-held rollback scripts; proof code remains a pure verifier. This local checkpoint is for independent combined review only: no publication, merge, deployment, restore, authentication, enrollment, endpoint, or live acceptance occurred. The proof verifier still does not consume challenges or create sessions; archive sanitization and complete D3 restore coverage remain open.

### R3.16 D2 native authority owner and child-channel implementation claim (2026-10-30)

**State:** design review ACCEPTED exact commit `93f70f0be779746140083cf18a3a786b2840798f` (tree `7cd40abf861c0437580276e5b8012e72b60a4d6a`); coordinator adopted the exact six-file offline source claim on `codex/ws04-phone-authority-channel-20261030`. Independent source review ACCEPTED commit `bfe815e489e526a563ce99dde47346486341783e` (tree `80f4d4bbdd5c37c4d32a6fa65a86ebe16b6c0a57`); documentation receipt remains a local review candidate. Luna authors; `01a18584-92e2-7511-aca8-983bb3f230ef` independently reviews. Claim-record commit precedes source changes. This claim supersedes the unresolved locked-session implementation choice in R3.14: to implement the already approved Mac-while-locked reachability intent, allow a new authenticated session after first unlock while the user login session and native owner are alive. It promises no service before first unlock, after logout, during sleep, after owner death, or automatic wake/restart. It does not change credentials, Keychain items, signing, installed services, or activation.

**Owner split:** WS-04 remains accountable for admission and the native authority boundary. A signed native supervisor owns the protected anchor, authority-process singleton/lifetime, child and channel incarnations, exclusive operation grants, transition-phase state, and the channel's permission for the child to proceed. One trusted packaged Python child owns SQLite and the existing device, grant, session and ticket policy. A compromised but correctly launched Python child is explicitly inside the trust boundary; this architecture does not sandbox that authorized child or defend against same-user code that can compromise it. The first R3.16 source slice does not integrate the current fake-only `PhoneRemoteService`; its peers, receipts, leases, media, queued output and delivery are deferred to a separate claim. Channel permission alone is not claimed to gate a production listener or output sink.

**Recommended topology:** the native supervisor creates a POSIX socket pair before spawning exactly one packaged Python child. It passes only the designated endpoint with `posix_spawn` file actions and closes all unrelated descriptors. The unique endpoint is a capability tied to that spawn, not an externally reachable socket. Every frame is bound to freshly generated native-owner and child-incarnation identifiers. The channel cannot reconnect, transfer its endpoint, or be authenticated by UID, path, PID, or interpreter signature. XPC remains an alternative only if both endpoints have explicit stable signing identities and the server checks the connecting code against an exact code requirement; Python interpreter identity alone does not prove which module it executes. Prefer the owner-launched inherited capability because the supervisor controls the packaged child launch and there is no general local service endpoint.

**Provenance and launch:** verify the signed product before authority startup; run only a fixed interpreter/runtime nested in or sealed by that product, a fixed dependency bundle, and a fixed entrypoint. Use a fixed argument vector and isolated Python startup/import path (no user-site, `PYTHONPATH`, `PYTHONHOME`, `sitecustomize`/startup hooks, current-directory import, shell, or user-selected module). Close inherited unrelated file descriptors and pass a deliberately allowlisted environment with fixed working directory and locale; never pass credentials in argv or channel frames. The existing `.env`/user-venv `scripts/run_bot.sh` launch path is not accepted as provenance for this boundary. Production packaging, signing identity, designated requirement, entitlements and any existing service replacement remain separately reviewed. This design selects no Team ID, signing certificate, profile, or installed bundle. Apple references: [SecCodeCheckValidity](https://developer.apple.com/documentation/security/seccodecheckvalidity%28_%3A_%3A_%3A%29), [applying code requirements](https://developer.apple.com/documentation/security/applying-code-requirements?language=objc), [Data Protection Keychain](https://developer.apple.com/documentation/security/ksecusedataprotectionkeychain), [access groups](https://developer.apple.com/documentation/security/ksecattraccessgroup), and [synchronizable items](https://developer.apple.com/documentation/security/ksecattrsynchronizable).

**Singleton and process binding:** before any anchor read or child spawn, acquire nonblocking `flock(LOCK_EX|LOCK_NB)` on the stable per-user inode `~/Library/Application Support/com.mortimer.phone-authority/owner.lock` inside a verified user-owned directory with restrictive permissions. The child inherits both its designated socket endpoint and a duplicate of the same singleton-lock file descriptor; every other inherited descriptor is closed. Never call `LOCK_UN`, unlink or recreate the inode. A supervisor does not close its lock descriptor or permit a successor until the child is reaped. Graceful shutdown stops new grants, waits for an active grant to finish or abort, sends `owner.shutdown`, waits for `child.shutdown_ack`, then waits for child exit before closing descriptors. On supervisor crash, the child's inherited lock descriptor keeps the inode locked until that child exits. The supervisor stops issuing grants when it observes EOF, child death, invalid frame or phase failure. The child separately stops starting operations when it observes EOF or a terminal protocol failure. A SQLite transaction already running may still commit before the child observes the failure; that result is uncertain to the caller and must not be replayed. The new owner/child incarnation cannot admit operations until the fresh child reconciles the exact anchor/database pair. A commit completed before the relevant observation remains committed. A replacement must acquire the same lock and wait for child exit; a hostile same-user process can bypass this advisory lock and remains outside the declared trust boundary. R3.16 channel sessions and tickets bind to fresh owner/child incarnation IDs; peer/media/output lifecycle is out of this first slice.

**Private channel contract:** protocol identifier `mortimer.phone-authority-channel.v1`; frame is a four-byte unsigned big-endian byte length followed by 1–65,536 bytes of strict UTF-8 JSON. Reject duplicate keys, non-object top levels, non-finite numbers, unknown keys, invalid UTF-8, zero length, truncation and oversize. Every frame has exactly `{protocol, version, kind, owner_incarnation, child_incarnation, sequence, correlation_id, payload}`. `protocol` is the exact identifier above; `version` is JSON integer 1, never boolean/float; `kind` is an enum; both incarnation and correlation IDs are lowercase canonical UUID strings; `sequence` is an exact integer in `1…2^64−1`, never boolean/float; `payload` is an object validated by `kind`. Each direction starts at sequence 1 and increments by exactly one; no wrap is permitted, and the owner closes before exhaustion. Request/response pairs use the same correlation ID; no multiplexing is allowed. Before granting any operation, require an initial anchor state with `anchor_version` exactly 1, `host_generation` positive, nonblank `host_id`, `transition_state` exactly `stable`, and `transition_id` null. This is the store-compatible baseline; pending state is permitted only as a readback inside an already acquired matching grant, never as admission. The native owner creates owner/child incarnation IDs before spawn and sends the first `owner.hello` frame (sequence 1, fresh correlation ID, payload exactly `{max_frame_bytes:65536}`); the child must answer `child.ready` (its sequence 1, same correlation/incarnations, payload exactly `{}`) before any other message is accepted.

The only child request kinds and payloads are: `child.grant.acquire` `{operation}`; `child.anchor.read` `{grant_id}`; `child.anchor.advance` `{grant_id, step, state}`; `child.grant.release` `{grant_id}`; `child.grant.abort` `{grant_id}`; and, after shutdown is requested, `child.shutdown_ack` `{}`. `operation` is exactly one of `store.open`, `store.read`, `session.login`, `session.signout`, `authority.mutate`, `ticket.issue`, or `ticket.consume`. `step` is exactly `global_pending`, `global_stable`, `login_pending`, or `login_stable`. `state` has exactly `anchor_version` (integer 1…2^32−1), `host_id` (nonempty string), `host_generation` (integer 0…2^64−1), `transition_id` (null or nonempty string), `transition_state` (`stable` or `pending`), and `login_counter` (integer 0…2^64−1); integers reject booleans/floats and the whole frame remains size-bounded. `store.open` is allowed only for an already preprovisioned test schema and can read but never advance the anchor; there is no channel schema-bootstrap command.

The only owner success kinds are `owner.hello` (initial frame), `owner.grant.acquired` `{grant_id, operation}`, `owner.anchor.state` `{grant_id, state}`, `owner.anchor.verified` `{grant_id, state}`, `owner.grant.released` `{grant_id}`, `owner.grant.aborted` `{grant_id, disposition}`, and `owner.shutdown` `{reason:"requested"}`. `grant_id` is a fresh canonical UUID. `disposition` is exactly `unknown` under the conservative abort policy: abort never proves SQLite did not commit, even if no anchor advance was observed. The owner sends this terminal receipt if possible, then closes the channel and marks authority unavailable until a fresh child validates the anchor/database pair. Terminal `owner.error` has exactly `{code}` where code is one of `owner_busy`, `authority_unavailable`, `anchor_missing`, `anchor_locked`, `anchor_denied`, `anchor_corrupt`, `stale_incarnation`, `sequence_invalid`, `correlation_invalid`, `grant_invalid`, `phase_invalid`, `malformed_frame`, `unsupported_version`, or `child_exited`. No raw OSStatus, exception, Keychain value or secret is returned. Every error terminates the channel; no resynchronization is attempted. The owner grants at most one operation at a time and rejects a second acquisition. No arbitrary SQL, filesystem path, Keychain service/account, migration, enrollment, reset, schema bootstrap, or generic anchor-overwrite command exists.

**Mapping `ProtectedAnchor` to channel operations:** keep the existing `PhoneAdmissionStore` policy and `ProtectedAnchor` interface unchanged in this first source slice. Since `exclusive()` has no operation parameter, the packaged child must call an explicit adapter wrapper such as `run_store_operation(operation, callable)` around each allowlisted store method; construction uses a separate `open_store(factory)` context with operation `store.open`. The wrapper supplies the operation context directly, not by stack inspection. Missing context, nested context, concurrent context, or a method inconsistent with the selected operation is rejected before store work. The construction context is limited to opening an already preprovisioned database and stable-anchor read. `exclusive().__enter__` then sends `child.grant.acquire` with that wrapper-owned operation and waits for `owner.grant.acquired`; `read()` sends `child.anchor.read` and decodes only `owner.anchor.state`; `write(state)` sends `child.anchor.advance`, which is accepted only if the full typed state is the one legal next state for that grant, then waits for native Keychain-API abstraction write/readback success in the fake owner. The store's `_write_anchor` subsequently calls `read()` again, so it still independently compares the state. The channel does not expose an arbitrary `set_anchor` command. Normal `exclusive().__exit__` sends `child.grant.release` and returns normally only after `owner.grant.released`; this happens during the store method's internal context exit, before the wrapper returns its result to its caller. exceptional exit sends `child.grant.abort`, waits for terminal `owner.grant.aborted {disposition:"unknown"}` when possible, closes the channel and blocks authority pending reconciliation, then re-raises the original store exception. If channel acknowledgment itself fails, raise the existing neutral `StoreUnavailable` boundary, terminate the channel, and treat the effect as uncertain. The owner enforces order from observed channel messages; it trusts that the authorized child reports its own SQLite phases accurately and does not independently inspect or attest commit contents.

**Legal operation phases:** for `authority.mutate`, require initial stable anchor read → `global_pending` with unchanged host ID/anchor version/login counter and host generation exactly +1, nonempty transition ID, pending state → permit exact pending-state readback in the same grant → `global_stable` where the only differences from pending are `transition_state` changing to `stable` and `transition_id` changing to null → permit exact stable-state readback → normal grant release. The child sends the stable-anchor write only after its SQLite transaction committed the authority mutation, pending metadata, and global session invalidation; normal release occurs only after final SQLite stable metadata commit. For `session.login`, require initial stable read → `login_pending` with unchanged host ID/anchor version/host generation, login counter exactly +1, transition ID present and pending state → allow exact pending-state readback in the same grant → `login_stable` where the only differences from pending are `transition_state` changing to `stable` and `transition_id` changing to null → allow exact stable-state readback → normal release. The child reaches login-stable only after its SQLite session-row transaction committed. `store.open` grants only for construction against a preprovisioned schema, then stable anchor read and release before construction returns. `store.read` is acquire → stable anchor read → store read → release. `session.signout` is acquire → stable anchor read → scoped SQLite signout → release. `ticket.issue` and `ticket.consume` are each acquire → stable anchor read → their matching store operation → release. These operations never advance the anchor; each wrapper returns a result only after the release acknowledgment. `session.login` and `authority.mutate` use the transitions specified above. They remain serialized under the same exclusive owner grant. Operation authorization and all target/session/grant checks stay in the Python store; native phase checks do not create a second policy engine.

If an exception exits `exclusive`, the adapter sends `child.grant.abort`, never `release`. The owner applies one conservative rule: every abort is terminal with disposition `unknown`, because the protocol cannot prove that SQLite did not commit even when no anchor advance occurred. The owner closes the channel and marks authority unavailable; a fresh child must validate the exact anchor/database pair before new admission. An exception after a transaction may have committed is not translated into “nothing happened.” Since the first source claim has no `PhoneRemoteService`, it has no peer, receipt, lease or output state to close or deliver; a future service integration must separately define cancellation of queued work and acknowledge that already emitted output cannot be recalled.

**Crash, context-exit and disconnect matrix:**

| Interruption point | Required result |
|---|---|
| Before grant or anchor read | No anchor/SQLite mutation and no operation success |
| Anchor read unavailable, locked, denied, malformed or mismatched | Return only the fixed typed error if possible, observe channel termination, and deny later grants |
| Pending-anchor write/readback has an error or uncertain acknowledgement | Do not continue with SQLite mutation; mark authority unavailable and do not acknowledge success |
| Pending anchor written; channel failure observed by owner before child | Owner stops new grants. An already-running SQLite transaction may commit before child observes EOF/failure; completion is uncertain, must not be replayed, and fresh admission requires exact anchor/database reconciliation |
| SQLite pending mutation committed, stable anchor not finalized | Pending/mismatched pair blocks future authority; mutation remains committed in SQLite |
| Stable anchor write/readback completed, final SQLite stable commit not completed | Stable-anchor/pending-database mismatch blocks future authority |
| Final SQLite commit completed but release acknowledgment is lost | Caller sees uncertain completion; committed state may remain. Close channel on observed error/EOF; do not replay this effect or accept another grant on that channel |
| Normal `exclusive` exit | Send `grant.release`; return to caller only after exact release acknowledgment |
| Exceptional `exclusive` exit | Send `grant.abort`; never send normal release. Return terminal disposition `unknown` if possible, close the channel, and block authority pending fresh anchor/database reconciliation; no-anchor-advance does not prove SQLite was unchanged |
| Supervisor or child death | Owner stops issuing grants when it observes EOF/`waitpid` death/protocol failure. Child stops starting operations only when it observes EOF or terminal protocol failure; a transaction already running may commit before that child observation. The caller receives no success for uncertain completion, no effect is replayed, and fresh admission requires anchor/database reconciliation |
| Old child remains after supervisor death | Child's inherited socket and lock descriptors remain open until it exits; successor cannot acquire the flock. Never use `LOCK_UN`, close the owner's last lock reference early, or unlink/recreate the inode |

These are fail-closed cross-store transitions, not one atomic SQLite+Keychain transaction. A clean restart may serve only after it acquires the singleton, confirms the prior child has exited, validates an exact stable anchor/database pair and creates a fresh child incarnation. Pending, mismatched or unknown state remains blocked for trusted recovery. No restore operation automatically repairs or rewrites either side. This first slice tests only observable process/channel revocation and store/session/ticket behavior; it does not claim instantaneous revocation at the physical moment a process dies, nor does it test service peers, receipts, leases, output queues or already emitted media.

**Anchor policy:** the native owner uses the dedicated nonsynchronizing Data Protection Keychain access group and fixed service `com.mortimer.phone-authority`, account `host-generation-v1`; no legacy-keychain fallback. Preserve typed missing/locked/denied/unavailable/corrupt states and exact write/readback checks. `ThisDeviceOnly` and readback are not rollback protection. Whole-host backup restoration and the `phone_remote_restore_v1` fence remain D3/WS-17 obligations.

**Adopted six-file source claim:** modify only `macos/MortimerHost/Package.swift` and add `macos/MortimerHost/Sources/PhoneRemoteAuthority/PhoneRemoteAuthorityOwner.swift`, `macos/MortimerHost/Sources/PhoneRemoteAuthorityOwner/main.swift`, `macos/MortimerHost/Tests/PhoneRemoteAuthorityTests/PhoneRemoteAuthorityProcessTests.swift`, `jarvis/bot/phone_remote_authority_channel.py`, and `tests/unit/test_phone_remote_authority_channel.py`. The package adds three independent targets: a `PhoneRemoteAuthority` library; `PhoneRemoteAuthorityOwner` executable depending only on that library; and `PhoneRemoteAuthorityTests` depending only on that library. Existing `MortimerHost`, `MortimerHostTests`, `JarvisKit` dependency and existing package products remain unchanged; no new external dependency is added. The native target uses Foundation/POSIX process/socket/lock APIs with an injected fake anchor; no Security.framework call is in this claim. The Python adapter implements the existing injected `ProtectedAnchor` protocol unchanged: `exclusive` maps to grant acquire/normal release/exception abort, `read` maps to typed anchor-state request, and `write` maps to one of the four native-validated transition steps. Tests preprovision disposable SQLite schema and a test-only lock inode/configuration, then run actual owner/child processes against a fake anchor. The child receives only the socket endpoint and singleton-lock descriptor; all other inherited file descriptors are closed. No real per-user lock path, real Keychain query/write, signing, provider credential, production launch, listener or feature enablement is used. Any need to edit the store/service, `scripts/run_bot.sh`, `.env`, launchd, bundle/deploy scripts, Keychain token code, auth routes, migrations or frozen S0 files requires a separate reviewed scope amendment.

**First-slice tests and commands:** process tests cover exact handshake/envelope schemas and bounds; partial/oversized/duplicate/stale/replayed/reordered/skipped frames; sequence start, exact increment and overflow rejection; grant acquire/release/abort and only legal `ProtectedAnchor` phases; competing owners on the same temporary precreated lock inode; both inherited descriptors and unrelated-FD closure; graceful shutdown and supervisor/child death; and the existing store's global security mutation, login, scoped signout, read and one-time ticket issue/consume through actual process IPC and temporary SQLite. Inject failures/lost acknowledgments before/after each anchor step and SQLite commit. Assert owner stops issuing grants at its observation and child stops starting operations at its own observation; include a deterministic interleaving where an already-running SQLite transaction commits after owner death is observed but before the child observes EOF, then assert the caller treats completion as uncertain, never replays, and fresh admission requires reconciliation. No `PhoneRemoteService`, peer, request receipt, lease, output, queue, media or output sentinel semantics are covered; any byte sentinel used inside framing tests proves only channel framing and must be labeled channel-only. Tests use no production lock path, Keychain, private credential or live service.

Build and run the proposed Swift targets without replacing existing targets:

```sh
swift build --package-path macos/MortimerHost --product PhoneRemoteAuthorityOwner
PHONE_REMOTE_AUTHORITY_OWNER_BIN="$(swift build --package-path macos/MortimerHost --show-bin-path)/PhoneRemoteAuthorityOwner" swift test --package-path macos/MortimerHost --filter PhoneRemoteAuthorityTests
PHONE_REMOTE_AUTHORITY_OWNER_BIN="$(swift build --package-path macos/MortimerHost --show-bin-path)/PhoneRemoteAuthorityOwner" python3.12 -m unittest tests.unit.test_phone_remote_authority_channel
python3 scripts/check_roadmap.py --main github/main
```

These synthetic tests establish only actual process framing, the cooperative lock lifecycle, and the existing store's fake-anchor transition/session/ticket behavior. They do not validate code-signature trust, real Data Protection Keychain behavior, entitlements, secure hardware, rollback resistance, packaging trust, production launch/serving permission, service outputs, locked operation on a real Mac, or live access.

**Ownership and collision record:** WS-04/Codex owns this claim. Fresh read-only PR #290 changed-file inspection at head `7d8daa2c013757a178edfea91019e772e04e157f` found none of the six source paths. Local branch/claim history found no competing active owner; the existing shared `macos/MortimerHost/Package.swift` is explicitly inside this claim and has no other active claimant. Refresh collisions before integration. This does not take WS-17 restore, WS-30 iOS client, WS-05 provider readiness or WS-21 display ownership.

**Implementation boundary:** the accepted design implements already approved locked-after-first-unlock intent. The code claim does not include real code-signing identity/entitlements, production Keychain writes, real lockfile provisioning, production packaged-runtime construction, launchd/app startup changes, restore operations, credentials, installation, route/listener activation, `PhoneRemoteService` peer/receipt/lease/output integration, or live testing; these remain separate owner/authorization steps.

**Implementation acceptance receipt (2026-10-31):** independent review accepted exact source commit `bfe815e489e526a563ce99dde47346486341783e` (tree `80f4d4bbdd5c37c4d32a6fa65a86ebe16b6c0a57`). The six-path adopted claim is recorded above; the source commit's actual changed-file delta is the four implementation/test files `macos/MortimerHost/Sources/PhoneRemoteAuthority/PhoneRemoteAuthorityOwner.swift`, `macos/MortimerHost/Tests/PhoneRemoteAuthorityTests/PhoneRemoteAuthorityProcessTests.swift`, `jarvis/bot/phone_remote_authority_channel.py`, and `tests/unit/test_phone_remote_authority_channel.py`. `Package.swift` and the executable entry point were in the reviewed claim but unchanged in that final source delta. Focused Python unittest ran `tests.unit.test_phone_remote_authority_channel`, `tests.unit.test_phone_admission_store`, and `tests.unit.test_phone_admission_contract`: 79 passed (32 channel plus 47 existing). Focused Swift `PhoneRemoteAuthorityTests|DisplayPlacementPolicyTests|VoicePresentationStateTests` passed 19 tests (2 authority, 10 display, 7 voice); `PhoneRemoteAuthorityOwner` build passed. Independent native adversarial probes and roadmap checks passed. Other Swift tests and full pytest were not run.

This acceptance is limited to actual disposable owner/child process IPC and the existing SQLite store's fake-anchor transition/session/ticket behavior. It does not establish production Data Protection Keychain behavior, signing/entitlements, packaged-runtime provenance, production startup or construction, `PhoneRemoteService` production construction or production peer/receipt/lease/media/output integration (the bounded offline service/process integration is separately accepted in R3.17), network transport/listener, full 70-vector real-admission facade conformance, or D3 restore closure. No real credentials, live service, installation, restore, or phone-call acceptance is claimed. The accepted R3.16 source is included in public PR #290. The `2e53f5aae66c67a19334c593b05b397987b7ab72` (tree `1e798d6db18d52a19b3f42358ba025839ecc6ee3`) snapshot is historical; Validate #542, Sandbox #720 and Knowledge Base #724 passed for that head; associated CI reported 7,360 unit tests passed, 37 skipped, 395 subtests passed, 197 integration tests passed and 13 evaluations passed. No live behavior is accepted.

### R3.17 WS-04 service/process composition — adopted offline source claim (2026-10-31)

**Status: design accepted and source claim adopted (2026-10-31).** Independent review ACCEPTED exact design commit `d932e900f503ac118ff1d9900364a884f1c2bed0` (tree `bb953601e15c9bd45833d226a7eef038281f3acc`). The parent coordinator adopted this exact six-file offline source claim on `codex/ws04-phone-authority-channel-20261030` under the one-final-merge exception, with Luna as author and `01a18584-92e2-7511-aca8-983bb3f230ef` as nonauthor reviewer. Claim adoption was committed first at `0287c6c6d81cac18a4ca88752b9cfbd1980fabab`; this plan/log adoption record precedes source edits. The published integration base at adoption was PR #290 head `2e53f5aae66c67a19334c593b05b397987b7ab72` (tree `1e798d6db18d52a19b3f42358ba025839ecc6ee3`); exact-head Validate #542, Sandbox #720 and Knowledge Base #724 passed. Fresh PR/path/claim checks found the five existing paths in this same PR and no other open repository PR; four paths (native owner, process tests, Python channel and channel tests) were included in R3.16 while its service composition was explicitly excluded. The new end-to-end test path has no local history. Recheck branch refs and ownership before integration.

**Problem and boundary.** R3.16 proves actual native-owner/Python-child IPC around the existing SQLite store's transitions, sessions and tickets. Its explicit boundary excludes service peers, receipts, leases, media and output. R3-S2 and R3.10 separately prove the synthetic in-process service and injected ASGI wrapper. R3.17 composes those existing components inside the same controlled Python child, so the service's existing in-memory policy and store authority share one process and one owner channel. It does not claim production Keychain, signed packaging, real transport, server mounting, device enrollment or live calls.

**Preserve the policy core.** Keep the default `PhoneRemoteService(...)` constructor and all current dependency checks exact: its ordinary construction path remains restricted to `PhoneAdmissionStore`, explicit fake context/media/output dependencies, fake anchor and fake gates/clock. Do not broaden a type check or make a public constructor that accepts an arbitrary anchor. This source claim adds only a private child-bootstrap factory/capability which is obtainable only after `NativeProtectedAnchor.from_inherited_environment()` has validated the inherited channel and owner/child handshake. It admits the channel-backed anchor only on that private path; every media, context, clock, availability and output dependency in offline service tests remains an explicit deterministic fake. The verifier remains server-injected; phone JSON never chooses owner, device, session, login incarnation or ticket. No second mutable service, session, peer, lease or replay-ledger authority is introduced.

**Channel and serialized commit design.** R3.16 v1 does not include a grant that holds authority across the service's final SQLite binding check and in-memory peer/lease/receipt/output commit. Do not silently add a message to v1. The adopted source scope defines a new closed `mortimer.phone-authority-channel.v2` protocol, implemented together by the Swift owner and Python channel. Add one narrowly scoped `service.commit` grant with exact framing, fields, sequence/correlation rules, stable-anchor read verification and terminal-error behavior; no arbitrary closure, SQL, paths, anchor write, or client-selected operation is carried in a frame. In the trusted child, an explicit service-commit context enters the existing store `serialized_authority()` guard, whose anchor `exclusive()` acquires that grant and then the store's local lock. While held, service code calls only the existing `binding_current_serialized()` read and performs its bounded in-memory commit. The wrapper rejects missing, nested, concurrent or mismatched contexts. Keep the lock order `availability/readiness/time gates → channel grant → store lock → service lock`; no injected callback, blocking preparation, adapter call, or await occurs in that critical section. Existing store transition operations retain their R3.16-specific grants and phase rules.

For `voice.offer`/`voice.update`, consume the one-use ticket through the existing ticket grant before effect preparation; a later revoke may therefore consume a ticket without publishing a peer, which is fail-closed. Media preparation remains outside the authority/service guards. At final commit, acquire `service.commit`, perform the one mandatory binding/anchor read first, then evaluate feature/readiness/availability/time, verify the captured peer/resource incarnation and owner lease, and atomically stage the peer/lease/resource reference and provisional receipt in the child. The single worker means service operations do not overlap: an offer commits only if no lease exists; a later request receives the existing busy result. `voice.end` and output enqueue/dequeue use the same serialized commit point with compare-by-incarnation semantics. Cross-process overlapping service/revocation/replacement interleavings are explicitly deferred, not claimed by this slice. There is no preemption, no phone-supplied output, and no operation beyond the already enabled service surface.

**Normative v2 envelope, phases, and per-call authority mapping (review revision, 2026-10-31).** The wire envelope keeps the R3.16 exact common field set and field types, but uses the literal protocol `mortimer.phone-authority-channel.v2` and exact JSON integer `version: 2`; no v1 negotiation, fallback, or mixed-version process is allowed. Both peers must be the co-packaged v2 pair. A v1 protocol name, version 1 frame, unknown field, duplicate JSON key, fractional number, invalid sequence/correlation/incarnation, partial/oversized frame or unrecognized operation is rejected and the channel is closed. Existing frame kinds and payload schemas stay closed and unchanged: `owner.hello {max_frame_bytes}`, `child.ready {}`, `child.grant.acquire {operation}`, `owner.grant.acquired {grant_id,operation}`, `child.anchor.read {grant_id}`, `owner.anchor.state {grant_id,state}`, `child.anchor.advance {grant_id,step,state}`, `owner.anchor.verified {grant_id,state}`, `child.grant.release {grant_id}`, `owner.grant.released {grant_id}`, `child.grant.abort {grant_id}`, `owner.grant.aborted {grant_id,disposition}`, `owner.shutdown {reason}`, `child.shutdown_ack {}`, and terminal `owner.error {code}`. The envelope remains exactly `{protocol, version, kind, owner_incarnation, child_incarnation, sequence, correlation_id, payload}`. No service data, output bytes, SQL, or callback is sent over the owner channel.

The v2 operation enum is exactly the R3.16 set (`store.open`, `store.read`, `session.login`, `session.signout`, `authority.mutate`, `ticket.issue`, `ticket.consume`) plus `service.authorize` and `service.commit`. `store.read` remains status-only. Each grant requires one mandatory stable-anchor read performed as part of the existing mapped store method: `current_binding()`/`binding_current()` invoke `_check_pair()` and thereby cause `NativeProtectedAnchor.read()` inside the grant. Do not add a redundant standalone read before those methods. `service.authorize` performs exactly that one stable read and no write. `service.commit` allows exactly one stable read from the existing service call to `binding_current_serialized()` (the method invokes the store `_check_pair()`/anchor read itself); there is no separate channel pre-read in addition to the store call. It requires a state-equal stable anchor, permits no anchor advance, then normal release. It cannot start if the owner has another active grant or the anchor is pending. Normal release is legal only after the expected read count and clean operation exit. Exception/abort uses the existing exact abort exchange with disposition `unknown`, then terminates the channel; no operation is retried in that process. Frame/sequence exhaustion is terminal before integer wrap and likewise fences the channel. A local child-side concurrent/nested acquisition is rejected before any socket write and does not close or alter a healthy active grant. A deliberately invalid second acquisition received by the owner while a grant is active is a protocol violation and terminates that channel. Preserve v1 fixtures and tests as historical contract tests; add explicit versioned v2 cases rather than redefining v1 expectations.

The v2 grant phase table for the two new operations is closed: (1) child sends `child.grant.acquire` with exactly `{operation}`; (2) owner verifies the exact v2 envelope/incarnations/sequence, no active grant, and a valid stable protected anchor, then returns `owner.grant.acquired` with exactly `{grant_id,operation}`; (3) child sends one mandatory `child.anchor.read {grant_id}`, and owner returns exactly `owner.anchor.state {grant_id,state}`; (4) child verifies stable state and executes only the mapped bounded operation; the store method’s own `_check_pair()` anchor read is the required read (not an extra preceding read); `service.authorize` uses exactly one such read, while `service.commit` also uses exactly one `binding_current_serialized()` read before any gate-denied return and may mutate only child-local bounded service state; (5) child sends `child.grant.release {grant_id}` only after normal operation completion, and owner returns `owner.grant.released {grant_id}`; the child may then expose the successful result; or (6) on any exception, missing/mismatched state, invalid operation, or uncertain local result, child sends the existing abort frame if the channel remains usable, accepts only `owner.grant.aborted {grant_id,disposition:"unknown"}`, closes/fences the channel, and exposes no success. These operations never send `child.anchor.advance`; all other store operations keep the R3.16 phase table unchanged. Any wrong-phase message, second on-wire acquisition, duplicate/skipped/oversized sequence, exhausted sequence, or malformed release/abort response is terminal at both peers. A local lock rejection before writing a frame is not a wire-level second acquisition and must leave the active grant/owner usable.

Every service-originated store call must carry one explicit operation context: `handle()`'s `current_binding` and exact-retry `_reserve_request()`'s `binding_current`, plus `emit_output()`'s preflight `binding_current`, each use one `service.authorize` grant; `voice.offer`/`voice.update` ticket consumption uses the existing `ticket.consume` grant, followed by the existing post-ticket/pre-preparation `binding_current()` as a separate `service.authorize` grant; service `session.status`, `voice.end`, final offer/update peer+lease+receipt commit, cached-receipt revalidation, output enqueue/dequeue, and each `tick()` binding/peer decision use `service.commit` around `serialized_authority()` and exactly one `binding_current_serialized()` read. Place that read first inside the grant, before feature-off, owner-unavailable, readiness or expiry cleanup decisions, so even a denied operation satisfies the phase and cleanup can proceed without editing `PhoneAdmissionStore`. `binding_current_serialized()` must never acquire a second grant; it is legal only within the explicit `service.commit` scope. Store construction/status/login/signout/security mutation/ticket issue remain under their exact R3.16 `store.open`, `store.read`, `session.login`, `session.signout`, `authority.mutate`, and `ticket.issue` contexts. Revocation notification runs only after a successful mutation grant has released; it invokes service cleanup/poll with fresh `service.commit` grants and never nests a grant inside the mutation. No channel grant spans ticket-independent media/output preparation.

**Read-only authorization denial semantics (review revision, 2026-10-31).** `service.authorize` is the sole nonterminal-denial exception to the otherwise terminal channel operation rule, and it is restricted to the exact `PhoneAdmissionStore.current_binding` and `binding_current` methods under the existing exact bound-method/operation allowlist. If one of these methods raises the exact `StoreDenied` type before it enters `exclusive()` (grant count remains zero), or `binding_current()` returns false before acquiring a grant because its exact typed inputs are invalid, return the neutral authorization-denied result without writing to the channel. The v2 wrapper may accept zero grants only for these exact denial outcomes on these exact read-only methods; a normal return, truthy result, or any other exception with zero grants remains a terminal phase/programming failure. If it raises `StoreDenied` only after its `_check_pair()` read verified a stable anchor under `service.authorize`, unwind the read-only store lock, send the normal `child.grant.release`, and require the exact release acknowledgment before returning neutral `not_authorized`; the authenticated child and unrelated sessions remain usable. A `binding_current()` false result follows the ordinary acknowledged read-only release and maps to the same neutral denial. This path changes no row, ticket, peer or grant. Do not special-case `StoreDenied` from `service.commit`, ticket consumption, login, signout, mutation or any other method. Corruption, protocol/sequence errors, unexpected exceptions, a denial without proof of the required stable read after grant acquisition, mismatched/missing release acknowledgment, and uncertain mutations remain terminal and fence the whole child. If the acknowledgment for an otherwise safe A denial is lost, A must receive no `denied` success-like result; the child latches unavailable and B is fenced too until recovery. This exception is not a general catch-and-continue mechanism.

**Single-worker scope and ASGI handoff (review revision, 2026-10-31).** SQLite's connection, `NativeProtectedAnchor`, store, and all mutable service state are constructed and owned by one dedicated child service thread; create the connection on that thread with its normal `check_same_thread` protection. The private child service host exposes synchronous proxy methods (`handle`, `tick`, trusted output emit/drain, and post-mutation notification) to the existing ASGI adapter. Calls from ASGI's bounded executor are submitted nonblocking to one active child-thread work item; strictly parse the request before lane admission only to recover a valid request ID/shape, then if occupied return the closed neutral-unavailable DTO without authorizing context, sending a grant, reserving a ledger entry, consuming a ticket, or queueing/replaying the request. The active operation continues unchanged. The worker constructs dependencies and services requests on its owning thread, preserving the channel's thread-bound grant/context and SQLite affinity. No other thread reads the channel or calls the store/service internals. The child host exposes only closed owner-thread entrypoints: `read_status` → `run_store_operation("store.read", store.status)`; `login` → `session.login`/`store.login`; `issue_ticket` → `ticket.issue`/`store.issue_ticket`; `signout` → `session.signout`/`store.revoke_session`; and `mutate_authority` → `authority.mutate` with only the exact current allowlisted mutation methods. The request-facing `handle` path itself owns `current_binding`, ticket consumption and service commits on that worker. No caller obtains the SQLite connection, store, anchor, generic method dispatcher, path, SQL or arbitrary callback. Successful signout/security mutation must finish its grant and release acknowledgement first; the same serialized worker then invokes `service.notify_revocation()` before it accepts another item. If the mutation grant fails or is uncertain, the worker fences instead of notifying/continuing. This is a controlled offline composition contract using the existing test owner and injected fake anchor; it does not create a production-authenticated child API, prove trusted caller identity, or authorize production enrollment/service construction. The production capability/provenance gap remains deferred to separately reviewed signing, packaging and Keychain work.

When ASGI cancellation occurs after dispatch, its existing executor drain retains the executor slot until the synchronous proxy returns; it does not cancel or detach the child-thread work. A caller cancellation before dispatch has no child effect. A stuck dependency leaves the bounded worker busy and the request pending; no timeout is represented as completion. If a result was committed and acknowledged but the response was lost, the same request ID may later obtain the already-recorded receipt after current-gate revalidation, without repeating effects. If grant completion is uncertain, the host fences the child and no replay path remains. End-to-end tests must invoke the actual ASGI callable so its executor dispatch/cancellation ownership is exercised, not call only the child service inline.

**Receipts and uncertain outcomes.** Keep the bounded fail-closed request ledger and its binding/request-ID/digest semantics. Reserve before effect; a replay with the same operation/version/digest returns a receipt only after current authority and applicable peer/lease/readiness gates are revalidated. Changed operation or digest is denied without a second effect. Capacity exhaustion fails closed; never evict live replay history to make room. If a service commit happens but the owner grant-release acknowledgment is lost, completion is uncertain: close/fence the channel, stop new service work, clear local peers/leases/queued output on observed channel failure, return only a neutral unavailable result if a response can still be delivered, and never automatically replay an effectful request. A later process requires fresh authenticated login and exact authority reconciliation; a lost reply does not authorize a new request ID. Define receipts as process-local; do not claim crash-durable exactly-once behavior.

**Commit acknowledgement and irreversible runtime-failure latch (review revision, 2026-10-31).** A peer/lease/resource mutation, output queue mutation/dequeue and provisional ledger receipt may be staged inside the `service.commit` grant, but none is success-visible until the matching `owner.grant.released` acknowledgement is received and validated. The code must not set its final `published`/success flag before the context exits successfully; this specifically closes the current `published=True`-then-release-exception path. Mark the ledger receipt `done` only after release acknowledgement. Until then it is in flight/provisional. If the ack is absent, malformed or mismatched, mark the operation uncertain, do not finalize or return an `ok` receipt, do not return dequeued output bytes, and never retry the effect. The lost-ack failure may follow a child-side mutation that the owner cannot inspect; fail closed rather than trying to undo an unobservable state transition.

The single channel caller/reader observes EOF, malformed response or release mismatch while completing its current request. It sets a monotonic child runtime-failed latch; there is no second socket reader or background callback. After the current operation has unwound the channel grant, store lock, service lock and readiness/clock/availability guards, the child-thread host observes that latch and performs IPC-free local fencing: prevent new submissions, mark all in-flight/provisional receipts uncertain, clear peers, leases, pending/active resources and undelivered output queue, and collect only resources owned by this child for cleanup outside the state locks. The failure observer must not reacquire gates, the channel, or the store, and must never run cleanup while holding the channel scope lock; this avoids lock inversion. Any media preparation already running is fenced by the latch and its attempt-owned result is discarded when it returns. If owner EOF happens during a blocked fake preparation, the test closes the owner endpoint while preparation is paused, confirms no second reader/cleanup callback runs concurrently, releases the barrier, and proves the final grant attempt observes EOF, latches failure, discards the owned preparation, returns no success/output and rejects all later work. Detection is on the next channel operation after EOF, not immediate physical-death detection.

**Disconnect, revocation and owner loss.** Preserve the R3.10 ASGI rule: disconnect stops new reads and drops that connection's trusted context; it does not synthesize session signout or voice end. In-flight synchronous service calls remain owned/drained by the adapter; if their response is lost after dispatch, no automatic retry occurs. Explicit scoped signout for session A invalidates A's peer/output only; a separately authenticated session B must obtain and consume a fresh ticket and complete a fresh operation. A global device/grant security transition invalidates sessions A and B; after transition the service's explicit revocation notification/poll must refuse cached receipts and output, close their peers and clear queued output, and a fresh B login/ticket may then operate. Repeated raw SQLite restoration after scoped signout must not revive A's old binding, receipt or queued canary, while B's control succeeds only if the paired protected authority still validates it. No artificial restore hook is allowed.

Owner death is observed by EOF, process-death observation or protocol failure, not at an unknowable instant of physical death. On observation, child work becomes unavailable, queued but undelivered output is cleared and no new service commit starts. A SQLite transaction or bounded in-memory commit already running before the child observes EOF may have completed; caller outcome is then uncertain and no request is replayed. Already-emitted output is irreversible and cannot be recalled. No scheduler guarantee is added: explicit fake tick/notification tests may establish behavior when invoked, but cannot claim a production five-second poller or immediate death detection.

**Exact adopted source scope (2026-10-31):**

- `macos/MortimerHost/Sources/PhoneRemoteAuthority/PhoneRemoteAuthorityOwner.swift` — implement the closed v2 `service.commit` owner phase/grant while preserving v1 rejection and existing store-operation transitions.
- `macos/MortimerHost/Tests/PhoneRemoteAuthorityTests/PhoneRemoteAuthorityProcessTests.swift` — actual owner/child protocol tests for v2 grant lifetime, contention, EOF, sequence/correlation and uncertain release.
- `jarvis/bot/phone_remote_authority_channel.py` — implement v2 request/response handling and the explicit non-nestable child service-commit context.
- `jarvis/bot/phone_remote_service.py` — add only the private channel-backed child factory and route existing final peer/receipt/lease/output commit windows through the service-commit context; preserve the public fake-only constructor, operations, closed DTOs and policy.
- `tests/unit/test_phone_remote_authority_channel.py` — extend actual process tests for the child-side v2 phase/context contract.
- `tests/unit/test_phone_remote_authority_service.py` — new cross-process integration tests using actual Swift owner and controlled Python child, disposable preprovisioned SQLite, test-only fake anchor, explicit fake context/media/clock/gates/output. Invoke the existing ASGI callable with synthetic events; do not open sockets or mount a server.

No `server.py`, `phone_admission_store.py`, Swift app target, frozen S0 fixture/adapter, network transport, listener, real Keychain, signing identity, package/launch configuration, credential, migration, restore tool or live installation is in this claim. Existing S0 files remain byte-identical. The integration tests must use actual child processes and current store/service/ASGI code, not an in-process owner substitute or a synthetic sentinel that pretends to cover peers/receipts/output.

**Required acceptance evidence:** run all existing R3.16 process/store tests, all R3-S2 service tests, R3.10 ASGI tests and the unchanged S0 contract suite. Add deterministic end-to-end assertions for: offer → update → exact retry returning one validated receipt without repeating media effects; a second ASGI request rejected without side effects while barrier-controlled media preparation occupies the sole child worker, followed by exactly one completion of the active operation; session A signout, A's stale `session.status` denied with an acknowledged read-only `service.authorize` grant and no child fence, then a fresh B ticket issued and consumed and B's fresh offer succeeds in that same child; in a separate variant, lose the release acknowledgment for A's read-only denial and prove neither an A response nor a subsequent B operation is returned, the shared runtime latch fences both, and B's ticket is not consumed; scoped A signout plus repeated raw DB restore denying A's old receipt/output while B's control remains usable only if paired protected authority validates it; global grant/device revocation refusing both A and B receipts/output and closing peers/queue, followed by fresh B login/ticket success; output canaries blocked after revoke, owner-unavailable/feature-off/expiry, and queued output cancellation; owner EOF before ticket use, after ticket consumption, during a barrier-blocked media preparation and after service commit; lost/mismatched release acknowledgement after peer/receipt insertion and after output dequeue (no success DTO/output bytes, uncertain ledger, local fence); a local channel grant rejection that leaves the healthy active channel operation intact versus a malicious wire-level second acquire that closes the channel; tests that do not require the native owner binary remain outside any binary-gated test class, while only actual process cases are gated with the exact missing-binary skip reason; SQLite/service creation and calls on the one owning child thread; and actual ASGI executor cancellation/disconnect after dispatch with drain/no duplicate effect/no automatic replay. Assert neutral content-free errors and resource cleanup. Use barriers/events rather than sleeps for these cases. This bounded fully serialized composition does not claim overlapping service/revocation/replacement races; those interleavings remain a later claim. Existing R3-S2 race tests remain useful lower-layer regression evidence, not process-composition coverage. Capture exact Python/Swift test commands, runtimes and counts; distinguish focused evidence from full pytest/CI.

**Accepted design decisions and remaining gates:** the service commit is serialized by the v2 grant after one stable read; lost release acknowledgement fences the child and requires restart/reconciliation; busy worker/channel contention is rejected without queueing; EOF is observed only on the next channel operation, with no second reader or immediate-death promise; and the narrow read-only `service.authorize` denial may remain nonterminal only after the precise acknowledged release path specified above. No external authentication, device or network decision is implied. This adoption does not authorize production Keychain/signing, production packaging/service construction, server mount, live transport, enrollment or call acceptance; those remain separate later claims/gates.

**Implementation and independent source acceptance receipt (2026-10-31):** independent review ACCEPTED source commit `2eb9412849aafb63dbcdb67c445a702d07233850` (tree `6171cbbf9a49a7d5a70f9fe176304b2a0385b0e4`). The adopted claim has six paths; five claimed source/test paths differ from the published-base tree, and `macos/MortimerHost/Tests/PhoneRemoteAuthorityTests/PhoneRemoteAuthorityProcessTests.swift` remains unchanged. From the tree-equivalent published base `1e798d6db18d52a19b3f42358ba025839ecc6ee3`, the complete local candidate changes only the five source/test paths and the three claimed documentation files (ROADMAP, this plan, and the dated R3.17 log); all other paths are unchanged.

Author-run Python command (Python 3.12.13, isolated repository test venv; cached `anthropic==0.125.0` supplied through `PYTHONPATH`):

```sh
PHONE_REMOTE_AUTHORITY_OWNER_BIN=/tmp/swiftpm-r317/debug/PhoneRemoteAuthorityOwner \
PHONE_REMOTE_AUTHORITY_PYTHON=/Users/larryfix/.local/bin/python3.12 \
PYTHONPYCACHEPREFIX=/tmp/codex-pycache-r317 \
PYTHONPATH=/Users/larryfix/.cache/uv/archive-v0/x54wLC9W_lDIUBz6:. \
/Users/larryfix/Documents/jarvis-voice-ai/.venv/bin/python -m pytest -q -p no:cacheprovider \
  tests/unit/test_phone_remote_authority_service.py \
  tests/unit/test_phone_remote_authority_channel.py \
  tests/unit/test_phone_remote_service.py \
  tests/unit/test_phone_remote_asgi.py \
  tests/unit/test_phone_admission_contract.py
```

Result: 115 passed, 209 subtests passed. The independent reviewer separately ran 164 pytest tests and 254 subtests across eight modules and accepted the source. The test-only final correction enables the fake output policy and checks fencing immediately after the output-preflight lost-ack result; a temporary mutation removing the centralized closed-channel fence made that immediate assertion fail, after which the source was restored and the full focused run passed.

Author reran the focused Swift command on the final candidate using the existing `/tmp/swiftpm-r317` scratch directory: `swift test --package-path macos/MortimerHost --scratch-path /tmp/swiftpm-r317 --filter 'PhoneRemoteAuthorityTests|DisplayPlacementPolicyTests|VoicePresentationStateTests'`. It passed 19 tests (2 authority, 10 display, 7 voice). The owner executable build and an independent 19-test Swift run were completed on byte-identical Swift source before the last Python test-only commit; the author rerun is the final-candidate Swift receipt. Python compilation and `git diff --check` passed. The binary-independent `SubmissionAdmissionRaceTests` also passed with `PHONE_REMOTE_AUTHORITY_OWNER_BIN` unset. The full repository pytest suite and all Swift tests were not run.

This accepts only the bounded fully serialized offline composition against the actual disposable owner/child process, existing service/store, and ASGI executor path. Overlapping service/revocation/replacement interleavings remain deferred. No full 70-vector mapping, production Keychain/signing/packaging, server construction, credentials, installation, route/listener, live service, device, phone call, or D3 restore acceptance is established. The accepted R3.17 source and its documentation are present in current published PR #290 head `46e29c26e6a4262aa47dfa96615f3a91cc990572` (tree `2d4ceb0ad7817aebe04980c2a6983e621cfb45e5`). Exact-head Validate #543 failed on `test_model_execution_deadlines.py::test_provider_swallowing_cancellation_cannot_return_or_publish_late_result[False-True]`; its receipt reported 1 failure, 7,362 passed, 49 skipped and 398 subtests. CI #542 is historical and does not supersede that failure. The earlier R3.16 source is published at the base PR head and its exact-head CI passed as recorded above. One final merge remains the plan.





### R3.18 WS-04 offline login-proof composition (2026-10-31; source accepted, local/unpublished)

**State:** Coordinator-adopted branch-local source claim; implementation and independent source review are complete. This adoption authorizes only the ten source/test paths listed below on `codex/ws04-r3-18-login-proof-20261031`. It does not authorize publication, merge, enrollment, real credentials, production Keychain/signing, or runtime changes.

**Immutable base:** accepted combined R3.17 source/docs candidate `12865337ae9849c31e9d4d209bf12bb8d778ce56`, tree `2d4ceb0ad7817aebe04980c2a6983e621cfb45e5`. This design branch is separate and preserves that candidate unchanged.

**Fresh collision snapshot (2026-10-31):** connected GitHub read-only inspection found PR #290 open/draft/unmerged at `46e29c26e6a4262aa47dfa96615f3a91cc990572`, base `5310d1a9305035f43143fcffad6161619281f475`. The PR changed-file inventory contains the eight existing source/test paths in this claim; the proposed new `jarvis/bot/phone_remote_login.py` and `tests/unit/test_phone_remote_login.py` are absent. Repository search returned PR #290 as the only open PR. Existing paths belong to the same WS-04 integration and prior claims; the coordinator has adopted this exact follow-on scope, resolving overlap for this branch only. No Package.swift or other manifest is in scope. Recheck refs and the shared claim log before any later integration.

**Claim:** WS-04/Codex; owner Codex; GPT-6 Luna author; existing independent nonauthor WS-04 reviewer `01a18584-92e2-7511-aca8-983bb3f230ef`. The independent design review accepted commit `201a626bebdeda7b9dcfc06b6062fdbe366b8765` (tree `43d631aeea0493ed5cad6b2636f54a1e263d1aed`); the coordinator adopted this exact ten-file source scope. Independent source review ACCEPTED the implementation; publication remains pending.

## Problem and scope

The accepted `jarvis/bot/phone_remote_auth_proof.py` function `verify_auth_proof()` validates a proof against a server-derived `ProofExpectation` and enrolled P-256 key. It explicitly does not issue or consume challenges, resolve an owner/device, or create a session. The authority child already has separate `login` and ticket APIs, but not a reviewed composition from challenge to session.

The proposed offline slice connects these existing pieces using only synthetic pre-enrolled device/grant rows, synthetic test signing keys, disposable SQLite, injected fake anchor, fake clock and the actual child process. It adds no app login route or real enrollment.

## Exact possible source/test paths

1. `macos/MortimerHost/Sources/PhoneRemoteAuthority/PhoneRemoteAuthorityOwner.swift` — support the new read-only challenge-context authority operation and required channel version.
2. `macos/MortimerHost/Tests/PhoneRemoteAuthorityTests/PhoneRemoteAuthorityProcessTests.swift` — exercise its grant phases, sequence, release acknowledgement and failure cases against actual processes.
3. `jarvis/bot/phone_admission_store.py` — narrowly resolve an active device/grant/key under authority, and add a proof-context-checked login entrypoint that reuses existing protected login-counter/session transition. No arbitrary SQL API or migration.
4. `jarvis/bot/phone_remote_authority_channel.py` — implement matching child-side operation context and exact method mapping.
5. `jarvis/bot/phone_remote_login.py` (new) — challenge issuance, bounded process-local registry, use of the existing verifier, and typed result/denial mapping.
6. `jarvis/bot/phone_remote_service.py` — expose only the private owner-thread challenge/login methods to controlled child code.
7. `tests/unit/test_phone_admission_store.py` — current authority/key/grant validation and login transition outcomes.
8. `tests/unit/test_phone_remote_authority_channel.py` — operation mapping and protocol rejection.
9. `tests/unit/test_phone_remote_authority_service.py` — child-thread ownership and actual process composition.
10. `tests/unit/test_phone_remote_login.py` (new) — challenge format, single use, expiry, bounded attempts and proof outcomes.

`jarvis/bot/phone_remote_auth_proof.py` remains unchanged. The public phone protocol, ASGI route set, iOS package, server mounting, and production construction remain unchanged. Challenge/proof APIs in this slice are typed in-process methods only. Any external JSON request/response schema or route requires a separate claim.

## Challenge and proof contract

The typed challenge request is exactly `{device_id, grant_id}`. These are selectors supplied by the caller, not authority. In a stable read grant, the server resolves them to a live owner/device/grant and captures the current protected host ID/generation and enrolled P-256 public key. Unknown, revoked, mismatched, and unavailable selectors produce indistinguishable content-free failure classes. The server never accepts `owner_id`, key, scopes, host ID/generation, session, ticket, purpose, or expiry from the phone as authority. Before issuing a challenge, require the enrolled algorithm label to equal exactly `p256-sha256-sec1-v1`; require a 65-byte SEC1 uncompressed P-256 point beginning with `0x04`, parse it as a valid on-curve P-256 point, and reject every other label/encoding. Existing generic enrollment storage is not evidence that an enrollment is usable for this proof protocol.

The typed challenge response is exactly `{protocol, purpose, challenge_id, challenge_nonce, service_id, host_id, enrolled_key_id, authority_generation, expires_at_ms}` and uses the existing R3.15 proof field types/encoding. `purpose` is fixed to `phone.session.create`; `service_id` is configured by trusted host code. Derive `enrolled_key_id` as `p256-sha256:` plus lowercase SHA-256 hex of the current SEC1 key, binding it to key rotation without storing a second key ID column. Challenge ID is 16 CSPRNG bytes and nonce is 32 CSPRNG bytes. Proposed TTL is 60 seconds; expiry is selected by the server and encoded as exact integer wall-clock milliseconds. Require a process-monotonic deadline too, so wall-clock rollback during that child lifetime does not extend a challenge. No cross-reboot trusted-time claim is made.

The typed proof submission is exactly `{challenge_id, proof_bytes}`; `proof_bytes` is the existing R3.15 closed proof JSON and is capped at 4096 bytes. The existing verifier performs cryptographic validation outside store/channel/service critical sections. The same `ProofExpectation` is server-held and immutable; the caller cannot replace any of its values. Do not log proof bytes, signature, nonce, public key, or exception contents.

The registry is one strongly held object owned by the unique authority child, shared by every facade in that child and bound to its `child_incarnation`; it is not per-login-facade state. Proposed exact limits are 60 seconds, 64 entries total and four per device. Count active and terminal tombstones against capacity; do not evict live history to make room. Retain issued/consuming/consumed/retired entries until their original monotonic 60-second deadline, then remove them during bounded admission/cleanup. There is no early tombstone eviction. A known live challenge counts malformed proof framing, context mismatch and invalid signature attempts; retire on the third. Unknown IDs do not consume another entry's budget. Expiry retires the entry. A recognized but no-longer-authorized device/grant retires the challenge after a known preflight denial. A pre-dispatch busy rejection or cancellation before the operation is admitted leaves it untouched. Once dispatched, the child owns completion despite caller disconnect/cancellation; it must not replay and an uncertain result retires the challenge and fences the child. Registry reset on child restart invalidates all outstanding challenges; the protocol must not reconstruct them from SQLite or a snapshot.

## Versioning and serialized use

R3.17's v2 authority-channel operation set is closed. The challenge-context lookup therefore requires a new exact channel protocol version v3; do not append it to v2, introduce fallback, or silently change v1/v2. V3 adds only the exact read-only `session.challenge` operation and a narrowly scoped known-denial exchange for login. `session.challenge` performs one stable anchor/database check and active device/grant lookup, with no anchor advance or mutation. The store lookup returns a typed decision: either captured challenge context or the same `not_authorized` denial for unknown, revoked, mismatched or unavailable selectors. For either decision, the child completes the ordinary read-only grant release and requires the exact `owner.grant.released` acknowledgement before exposing a challenge or denial. A corruption/protocol error or missing/uncertain release acknowledgement is terminal and fences the child; never disclose row existence or return a denial before release succeeds. Preserve v1/v2 fixtures as historical/version-specific fixtures and add separate v3 cases; a v1-positive decoding fixture is not expected to pass a v3-only decoder unchanged.

The typed API uses a closed content-free result vocabulary. Challenge issuance returns either context or `not_authorized` for all unknown/revoked/mismatched/unavailable selectors, but only after the read-only release acknowledgement. Proof completion returns `challenge_unavailable` for unknown, retired or expired IDs; `proof_rejected` for malformed/oversized proof, context mismatch or invalid signature; `not_authorized` for a recognized challenge whose device/grant is no longer authorized; `busy` for pre-dispatch worker contention; `capacity` when the bounded challenge registry cannot admit another challenge; and `unavailable` for uncertain/fenced authority. These codes never reveal device/grant existence, key identity, signature validity details or internal exception text. They are typed in-process results, not a public wire schema.

The proof-to-session success DTO is exactly `{session_id, expires_at_ms}`. Generate `session_id` inside the trusted child from 16 CSPRNG bytes encoded as 32 lowercase hex characters. The caller cannot select an ID or lifetime. Proposed lifetime is exactly 12 hours and must be independently accepted with this design; derive `expires_at_ms = now_ms + 43_200_000` with checked integer arithmetic. Require `now_ms` and expiry to be exact nonnegative integers (not bool/float). Convert to the store's seconds explicitly as `now_s = now_ms / 1000.0` and `expires_at_s = expires_at_ms / 1000.0`; do not mix units or use caller time.

After verifying a proof, atomically reserve the process-local challenge state from `issued` to `in_flight`; concurrent submissions for the same ID cannot both proceed. ECDSA runs on the single child worker outside any authority grant. A busy worker rejects before dispatch and leaves the challenge usable; once dispatched, child ownership continues through completion even if the caller disconnects. Under a single owner-thread `session.login` transition, revalidate the stable pair, host ID/generation, active owner/device/grant, current exact algorithm/key fingerprint, and wall/monotonic deadline. Derive `owner_id` from the trusted enrolled device row and construct `ClientIdentity` internally from that owner; never accept either from the caller. Call a private checked-login store method which reuses the existing login-counter/SQLite/final-anchor transition. Refactor the existing public `login()` and checked-login method to share one internal transition helper; do not nest the public `login()` grant inside another grant. Generate the server session ID and lifetime in the child. Require the owner release acknowledgement before exposing the exact success DTO. Do not issue a voice ticket automatically.

For a known pre-mutation login authorization denial only, v3 permits this exact phase: after the child has completed and verified the required stable pair read, it sends `{grant_id, operation:"session.login", code:"not_authorized"}` as `child.grant.reject`; the owner replies `{grant_id, operation:"session.login", code:"not_authorized"}` as `owner.grant.rejected`. This is legal only before any pending-anchor write/advance. A challenge whose proof verified but whose wall or monotonic expiry is reached before the in-grant login preflight follows this same phase: retire the challenge, send the existing `not_authorized` rejection, and perform no login-counter, anchor or session-row write. After its exact acknowledgement, the internal typed API may map this verified expiry case to `challenge_unavailable`; it must not expose an expiry-specific wire reason. The child returns no success DTO. The owner permits the healthy channel to continue, so A's revoked or expired login denial does not prevent B's later fresh login. Any denial after a pending write, any malformed/out-of-order rejection, or any lost/uncertain acknowledgement is terminal: fence the child, return no success, and never replay. The current v2 `session.login` transition cannot express this rejection phase because it moves the protocol phase to `writeAdvance` after the read; the anchor has not necessarily been written yet, but v2 has no legal pre-mutation rejection acknowledgement there. V3 must add that explicit phase rather than weakening v2 or treating a post-advance denial as scoped.

The checked-login path must bind to the one child-owned store and worker thread. Add exact method/type mappings through `open_store`, `run_store_operation`, the channel's closed method allowlist, and the private service constructor; preserve v1/v2 mappings. Do not expose a generic dispatcher or weaken `_verified_owner`. For proof-to-session authority, derive the trusted `ClientIdentity` only after resolving the active enrolled device/grant under the authority transition; callers cannot construct trusted identity or choose owner. Known preflight denials are the only nonterminal login failure and require the v3 rejection acknowledgement above.

The challenge registry is process-local and coordinated with, but is not part of, the SQLite transaction. SQLite and protected anchor are not one atomic database. Any uncertain transition or lost acknowledgement permanently retires that challenge, fences the child under R3.17, returns no success and never replays. Process restart changes child incarnation; old challenge IDs are unknown. Do not claim that every raw SQLite restore is detected: `_check_pair` rejects a host-ID/generation mismatch and a stored login counter ahead of the anchor, but an older database counter in the same host generation can satisfy that check. Tests must distinguish generation-mismatch refusal from a same-generation older-DB restore. Process-local consumed challenge tombstones and admission revocations must prevent replay/revival while that child remains alive; this is not a universal restore detector. No durable exactly-once, rollback-proof, or atomic SQLite-plus-Keychain claim is made.

## Source acceptance and focused validation receipt (2026-10-31)

Independent source review ACCEPTED commit `35a81461f232ea3cf3fbe854d3b2af8a2d5a0776` (tree `62a21723d7865468bf9025b54fbe58f195f54dae`). The final source revision, compared with pre-fix source commit `ad1ab6073c752fd0b8f7c23bc03e143ce560b0dc`, changes four files: the owner, service, and two authority-service tests. Cumulatively, the accepted R3.18 implementation covers all ten adopted source/test paths; the remaining six are unchanged in that final revision. Author-run focused Python validation passed 175 tests and 185 subtests across the store, service, proof, login, authority-service and authority-channel modules; Python compilation and committed-diff whitespace checks passed. The selected Swift `PhoneRemoteAuthorityTests` filter passed 3 tests, including native process tests, and the owner executable built successfully. Separately, the independent reviewer reports 215 Python tests/348 subtests and 20 Swift tests across its own validation; these are independent runs, not additive to the author run. Full repository pytest and the full Swift suite were not run.

This acceptance covers synthetic offline proof-to-session composition with disposable SQLite and an injected anchor. It does not establish production Keychain/signing/package behavior, full 70-vector facade conformance, D3 restore closure, or universal same-generation rollback detection. An older database counter in the same host generation may pass `_check_pair`. No live service, enrollment, credentials, listener, phone call, or production readiness is claimed. The source has no exact-head CI result and is not published.

## Required offline tests

Use actual disposable owner/child processes for operation boundaries, synthetic enrolled keys and isolated SQLite/fake anchor. Verify success creates one session and advances the login counter once; duplicate and concurrent challenge use creates at most one session; malformed/oversized proof, duplicate JSON keys, wrong purpose, altered signed fields, wrong key, authority/key/grant changes, wrong device, host/generation mismatch, child restart, expiry and monotonic boundary fail closed. Exercise attempt/capacity/retention limits, cancellation before versus after dispatch, no replay after disconnect, every fixed neutral result code, and absence of proof material from logs. Run crash injection at pending-anchor reservation, session DB commit, final anchor write/readback and lost owner release acknowledgement; no uncertain attempt returns success or can be replayed. For A/B, make A's challenge selector invalid/revoked and verify a typed denial is exposed only after normal read-only release acknowledgement, then B obtains a fresh challenge/login on the same child. Separately prove A's known pre-mutation login denial is acknowledged while B logs in. Interpose the fake clock so a valid proof expires after signature verification but before the in-grant login preflight; assert the `not_authorized` rejection/ack, `challenge_unavailable` typed result, unchanged login counter/session rows and successful fresh B operation. In a paired case, lose that expiry-denial acknowledgement and assert no success, child fencing and B denial. Inject loss of the challenge-selector denial release acknowledgement and of the login-denial acknowledgement in separate cases, and prove each uncertain result fences the child so B is denied. Confirm global security mutation invalidates outstanding challenges, scoped signout remains scoped, and process-local consumed challenges/revocations cannot be revived by repeated raw DB restoration. Separately demonstrate that a same-generation older DB may pass `_check_pair`; do not call it detected. Never label a signature as Secure Enclave attestation, biometric proof or user-presence proof.

## Exclusions and gates

No real enrollment/key generation, client Face ID/passcode gate, public route, network transport, iOS app target, persistent challenge table, database migration registration, real Keychain, signing/package, credentials, installation, listener, service startup, phone call or live access. Production caller/package provenance, protected-anchor behavior, D3 restore hook, external login endpoint, app-side user-presence policy and actual device testing remain later reviewed gates. The exact ten-file branch-local source claim above was implemented and independently accepted. The source remains local/unpublished. Synthetic keys, disposable SQLite and injected anchor only.

### R3.19 protected-anchor adapter (2026-10-31; accepted offline source)

**Status and base:** coordinator adopted independently accepted design `bbbe3adb9e5af1e3d520a6b36b9d0fce98e4ee8b` (tree `3db49c124da36648b64a28efa892914307000b71`) for the exact offline source claim on `codex/ws04-r319-keychain-anchor-source-20261031`. Source commit `cc9f0205e2d54f67ffd41f14a0ad088553446303` (tree `75fb50db03241977a430063face357a7453f6bbf`) was independently ACCEPTED. It extends only the native owner boundary after R3.18 and preserves the prior source implementation and fixtures. No concrete Security-item client, real Security/Keychain calls, signing, provisioning, installation or activation is included. GitHub could not be refreshed because DNS resolution failed; recheck remote head and path ownership before later integration.

**Problem and exact implemented source boundary:** the current native owner uses an explicit test-only file anchor in `PhoneRemoteAuthorityOwner.runOfflineTestOwner`; its `Anchor` codec rejects duplicate keys, unknown fields, wrong types and oversized data, while the file fixtures deliberately use ordinary unsorted/whitespace JSON. The command-line entrypoint requires `--test-owner`. The existing `macos/JarvisKit/Sources/JarvisKit/KeychainStore.swift` is a legacy bearer-token helper: it uses the default Keychain query, shares the K1 service/account convention, treats failed reads as `nil`, and its setter does not require verified readback. It is not authority storage and remains unchanged. The implemented offline source paths are:

- Modify `macos/MortimerHost/Sources/PhoneRemoteAuthority/PhoneRemoteAuthorityOwner.swift` only to inject a closed typed anchor interface into owner state/transition code. Keep the current file implementation explicitly test-only and preserve its existing process fixtures byte-for-byte. Extract strict schema/type validation once and share it, but enforce canonical-byte equality only in the protected backend; existing file fixtures are not required to be canonical.
- Add `macos/MortimerHost/Sources/PhoneRemoteAuthority/PhoneRemoteAuthorityKeychainAnchor.swift` with the Data Protection Keychain adapter and a narrow injected `SecurityItemClient` interface. R3.19 deliberately does not add a concrete `SecItem*` implementation. Its canonical encoder emits compact UTF-8 JSON with fields in this exact order: `anchor_version`, `host_id`, `host_generation`, `transition_id`, `transition_state`, `login_counter`; unsigned integers are base-10 without sign or leading zeroes, stable `transition_id` is literal `null`, pending IDs are strings, strings escape quote as `\"` and backslash as `\\`, and encode only U+0000–U+001F control characters as lowercase `\u00xx`; other Unicode scalars are unnormalized raw UTF-8, and slashes are not escaped, and there is no whitespace or trailing newline. Decoding rejects duplicate/unknown keys, noncanonical bytes, non-UTF-8, oversized data, booleans/floats, invalid integer ranges, blank host IDs and inconsistent stable/pending fields. Exact string identity compares UTF-8 bytes; never normalize IDs.
- Add `macos/MortimerHost/Tests/PhoneRemoteAuthorityTests/PhoneRemoteAuthorityKeychainAnchorTests.swift`. The injected client records queries and returns synthetic Security statuses/results. Tests never call `SecItem*`, inspect a real Keychain, or use real identities. The existing SwiftPM test target discovers files in its directory, so no manifest change is proposed.

The native owner receives a synchronous, serialized, injected anchor backend; reject concurrent or reentrant calls. Preserve internal typed failures. Any failed or uncertain Security call/readback permanently latches that owner instance terminal before returning, sends no successful grant acknowledgment, and makes no further backend calls. This interface change must leave the explicit test-owner path working. Do not add a live default constructor or a production selector in this claim. A later signed production composition must require the protected adapter at construction, with no file, legacy Keychain, or best-effort fallback, under a separately reviewed claim. The fixed access-group string is entitlement configuration, not a lock or caller-authentication mechanism.

**Injected query contract implemented and exercised with fakes only:** constructed queries explicitly target the intended Data Protection Keychain with `kSecUseDataProtectionKeychain: true`; generic-password class; fixed service `com.mortimer.phone-authority`; fixed account `host-generation-v1`; configured access group; `kSecAttrSynchronizable: false`; and `kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly`. Access-group membership still requires the signed entitlement; its string is not a lock. The first query requests attributes only with `kSecMatchLimitAll`, and validation requires an array of exactly one permitted item-attribute dictionary. The second uses the exact selector with `kSecMatchLimitOne`, attributes and data, and validates the result dictionary and canonical bytes. Tests use a fake client; no `SecItemCopyMatching` call was made, and actual OS return attributes/status behavior or entitlement compatibility is not established. The two-query pattern is not atomic. Zero results means unavailable/not-visible, not physical absence. Never select arbitrary results. For applicable queries, a fresh context is passed through `kSecUseAuthenticationContext`; the default provider sets and verifies `interactionNotAllowed` before client invocation, returning a typed failure if it cannot verify the property. Fake tests cover a confirmed noninteractive context, an interactive context and provider failure. This does not verify actual Security behavior on the selected macOS version or signed product. No deprecated UI-fail control is used and interaction failure does not diagnose a locked device. The adapter exposes no concrete Security-item client in R3.19.

**Read/write and initialization rules:** ordinary reads never add, bootstrap or repair an item. An update uses only the exact fixed selector and expected next state, requests no returned attributes/data, and is followed by the same strict read sequence; require exact canonical bytes and typed state. An `errSecItemNotFound` result means unavailable/not-visible, not physical absence. Missing, duplicate, locked/interacting, denied, malformed, mismatched, failed or uncertain outcomes latch the owner terminal; issue no successful acknowledgment and make no subsequent backend call. Never delete/recreate, retry an uncertain write, or fall back to a file or legacy item. Provisioning is a separately reviewed explicit administrative operation, absent from normal read/update APIs. Keychain and SQLite are not one atomic database: existing pending/stable phase order and uncertain-completion fencing continue to apply. Readback confirms an observed value only; it gives no same-host rollback protection.

**Committed test coverage:** tests assert the constructed query keys and exercise synthetic result shapes, including duplicate/unexpected attribute results, a wrong service or access group, malformed second-query values, item-not-found, typed interaction/entitlement failures, canonical protected bytes, strict schema, existing file-fixture compatibility, update/readback behavior, terminal latching, and busy/reentrant behavior. They do not include cases for wrong accessibility in a returned item, a missing required identity attribute, or a successful empty result array; those outcomes are described by implementation rules, not claimed as tested cases. The adapter tests do not call real Keychain APIs. Owner tests reject mismatched ready correlation in protocol v1/v2/v3 and verify a typed anchor error uses the correlation of the failing request. Existing owner/child process regressions ran against the rebuilt binary with no skips.

**Identity and later user decisions:** the access-group string cannot be finalized until the signed product’s Team ID/App Identifier Prefix, bundle identifier and Keychain Sharing entitlement are selected and verified. The future native owner must run as a correctly signed user-login app-like process whose entitlement authorizes the exact group; a bare SwiftPM command-line executable is not evidence of that entitlement. No Team ID, certificate, profile, bundle ID, access-group literal or provisioning choice is selected here. Before real integration, review the packaged Python-child provenance and ensure only the intended signed native owner has access to the anchor; confirm whether the controlled child needs any Keychain entitlement (the design requires none). The approved after-first-unlock intent supports access after the first unlock through the next restart, including while the screen is subsequently locked, while the user login and owner remain alive. It does not make screen-lock state itself an admission policy, and promises nothing before first unlock, after logout, during sleep, wake/autostart or owner death. Apple references: [Data Protection Keychain](https://developer.apple.com/documentation/security/ksecusedataprotectionkeychain), [Keychain Access Groups](https://developer.apple.com/documentation/security/sharing-access-to-keychain-items-among-a-collection-of-apps), [Mac Keychain APIs and implementations (TN3137)](https://developer.apple.com/documentation/technotes/tn3137-on-mac-keychains), and [after-first-unlock accessibility](https://developer.apple.com/documentation/security/ksecattraccessibleafterfirstunlockthisdeviceonly). Verify actual OS query/result compatibility against the selected macOS SDK/deployment target before adding a concrete Security-item client or integrating the production owner; this is not a prerequisite for the already accepted offline injected-adapter source. Do not infer that a bare SwiftPM command-line executable has a valid Keychain access-group entitlement.

**Limits:** `ThisDeviceOnly`, nonsynchronizable storage, one-item readback and Keychain access groups do not prove monotonicity or prevent restoration of an older database on the same host. The existing `_check_pair` can reject host/generation mismatches and counters ahead of the anchor, but an older database within the same host generation may pass; this adapter does not resolve that case or claim it remains fail-closed. D3 must separately inventory and guard restoration/recovery paths. No real Keychain, signed package, entitlement, access-group provisioning, app install, production owner selection or live behavior is established by this proposal.

**R3.19 source acceptance and validation receipt (2026-10-31):** independent review ACCEPTED source commit `cc9f0205e2d54f67ffd41f14a0ad088553446303` (tree `75fb50db03241977a430063face357a7453f6bbf`). Author validation rebuilt `PhoneRemoteAuthorityOwner`; six focused Python modules passed 138 tests and 296 subtests; the configured Swift filter passed 39 tests with zero skips, including three actual owner-process tests; and `python3 scripts/check_roadmap.py --main github/main` reported 0 errors and 0 warnings. The independent reviewer separately reports 215 Python phone tests/348 subtests, 39 selected Swift tests with zero skips, and 40 PhoneCore tests; these are separate commands/scopes and are not additive. Independent latch, no-UI, error-correlation and wrong-ready probes passed. The default context provider fails closed before client access when `interactionNotAllowed` cannot be verified. R3.19 contains no concrete Security-item client and performs no real Security/Keychain calls. Actual OS attribute/status compatibility, signed no-UI behavior, signing/team/bundle/access-group entitlement, packaged owner provenance, provisioning and installation remain unverified. This source is local/unpublished and has no exact-head CI receipt. D3 same-generation restore remains unresolved; `ThisDeviceOnly` and readback do not establish rollback protection. These are offline adapter results, not production readiness or live access acceptance.


### R3.20 WS-30 unsigned iOS app scaffold (2026-10-31; accepted offline source)

The coordinator adopted the exact ten-path WS-30 claim on `codex/ws30-ios-app-scaffold-20261031`, amending the existing WS-30 ownership of `ios/MortimerPhoneCore/Package.swift`; the other nine paths are new. Independent review ACCEPTED source commit `d636c328312458fa101e47bddcff406626410f7f` (tree `91fece35b01f8b8217ff5d0f12874e8b6695ac6f`). The exact ten-path mapping and per-file hashes are recorded in the candidate source manifest. The implementation adds a Foundation-only preview model using the existing checked `PhoneRemoteOperationsClient` and injected synthetic byte transport, plus an unsigned SwiftUI iPhone/iPad scaffold. The app stays disconnected from Mortimer; the persistent notice is “Disconnected from Mortimer. Synthetic preview only.” and synthetic exchange requires an explicit demo action. iOS 17 is the scaffold deployment minimum, not a selected product support floor. No S0 fixture, server, transport, authentication, key, permission, or production service path was changed.

**Validation:** the historical `swift test --package-path ios/MortimerPhoneCore --scratch-path <temporary-directory> --disable-sandbox` invocation (scratch path generalized) passed 46/46. An unsigned generic iOS Simulator `build-for-testing` succeeded for the app and UI-test bundle. The persistent notice was moved into shared app chrome and the UI test asserts it remains visible during navigation. `python3 scripts/check_roadmap.py --main github/main` reported 0 errors and 0 warnings; `git diff --check` passed. UI test execution, rendered visuals and usability remain unverified because installed CoreSimulator framework 1171.7.0 is incompatible with Xcode 27.2's required 1174.21.0. No runtime was installed or changed. This local/unpublished source candidate has no exact-head CI receipt.

**Remaining gates:** compatible simulator UI execution and visual/usability review; product support-floor and bundle/signing decisions; integration/review/publication; CI on an integrated head; real transport, production authentication and protected-owner composition; user-presence and device enrollment; privacy, voice readiness, call policy, tunnel and release review. This is an offline preview scaffold, not a live iPhone/iPad client or device acceptance. No signing, installation, network, permission, enrollment, listener, or service action occurred. Preserve the one-final-merge plan.


### R3.21 Frozen-vector facade refinement relation (accepted branch-local test-only implementation)

The separate inventory at accepted audit commit `61667b9ec0f6557e06e58fe30b6312b90a86fa11` (tree `92731f18daa82f6033ba775ae731537a2fc8ae01`) records 70 frozen cases, seven sensitivity mutations, three legacy harness isolation probes, and 113 `unchanged:true` obligations across 32 cases. That audit branch remains separate and is not merged or copied here. The existing legacy harness executes all 70 traces, seven sensitivity mutations and three isolation probes in the focused suite; those are legacy-only and not v3 results. R3.21 has now run six translated refinement cases through the real v3 service in a disposable native-owner/Python-child process; exact full-vector replays remain zero. The fixture and legacy adapter remain byte-identical. The seven original sensitivity mutants and three original isolation probes have not been executed through the v3 facade.

The row-by-row event, expected decision, complete final observation, unchanged-step indices and provisional relation are in [the R3.21 refinement design log](../roadmap-log/2026-10-31-ws04-r3-21-frozen-vector-refinement-design.md). Underlying semantic classifications are 0 exact-capable, 61 needing a precise refinement, 1 harness-only and 8 requiring a missing operation/classifier implementation; none is classified unreachable. Separately, **the literal initializer in every one of the 70 rows is incompatible** with the adopted one-peer-per-owner service lease because it seeds two simultaneous owner-A peers p1/p2. This blocks exact initializer replay, not the underlying obligations. Thirteen rows additionally require p1/p2 observations; their same-owner dual-peer sub-obligation stays unmapped while a one-live-A-peer refinement is designed. Independent owner B may coexist with A. `notify:false` is not translated into delayed v3 notification, bounded wire reasons are not reverse-mapped by guess, and trusted admin operations are not exposed as phone actions.

Any future refined row must preserve its exact frozen sequence and map each legacy result to an explicit v3 status/reason/payload plus the actual state effects. All 113 unchanged steps require out-of-band read-only before/after observations of mapped SQLite authority, fake anchor/process, peer/lease/resource and receipt state, output queue/delivery and clock. The relation must account for the complete final object too; a response-only denial is insufficient. Each row’s alternative initializer and unmapped portion must be stated. No obligation is discarded because its literal state cannot be initialized.

**Accepted one-test pilot, branch-local:** the coordinator adopted the independently reviewed design commit `0105f8634becad613b5b73e73c88dfcc2cad2f1f` (tree `50fdd717658f89ee1d53d97bfa044325a4f40bc9`) for exactly `tests/unit/test_phone_remote_authority_service.py` on `codex/ws04-r321-refinement-tests-20261031`. Owner Codex; Luna authors; the existing WS-04 nonauthor reviewer reviews. No other source path is in this claim. Add one table-driven refinement test extending the actual native-owner/Python-child harness. The six `malformed-event-type-*` cases are object events with `type` values `[]`, `{}`, `null`, `true`, `7` and `""`; every case has `unchanged:true` at step 1. Preserve each value exactly as v3 request `operation` inside an otherwise valid `mortimer.phone-remote.v1` envelope. This exercises actual operation-type/allowlist dispatch; it is not raw-root parsing or exact vector replay. Require `denied/malformed_request` with `{}` payload. Five non-string operations must return a valid service-generated lowercase 32-hex UUID; the empty string must echo its submitted deterministic canonical UUID.

Initialize a disposable v3 owner, fake anchor, SQLite file, fake verifier/media and clocks. Use the existing synthetic challenge/proof login flow with a disposable P-256 test key, create a server-owned session and trusted context, and require a successful `session.status` response (`ok/none`, `{"readiness":"ready"}`) before any malformed request in both the normal and mutation processes. The existing service-status setup consumes five owner grants; malformed requests must consume zero additional owner-channel requests. A separate parser-mutant run repeats the same positive setup then coerces each invalid operation to supported `session.status`; it requires a 17-grant budget (the same five setup/status grants plus two status grants per case) and must diverge from the expected malformed response. Check observed channel counts; do not infer setup success from process exit.

A test-only wrapper around `_AuthorityChildServiceHost._invoke_owned` observes the real worker immediately before/after its direct `service.handle` call, with no preflight. Compare SQLite `phone_remote_*` rows, `store._tickets`, module `_PROCESS_ADMISSIONS`, exact fake-anchor bytes/phase, process/channel incarnation and request count, peer/lease/resource/pending-media/receipt state, `service.results is None`, output queue/canaries, service and login clocks, and proof challenge-registry records. Assert zero owner-channel calls/sequence changes per malformed request. Count worker queue submission/dequeue, dispatch and completion separately as permitted harness bookkeeping. All six step-1 unchanged projections and their named final-state projection are required. No production endpoint, runtime method, phone capability or fixture change is proposed.

The pilot’s alternative initializer has no live peers, unlike the common legacy initializer with two simultaneous A peers; it tests the dispatch no-effect property without closing that initializer mismatch or omitted same-owner peer obligations. The independently accepted pilot at source commit `5e1543059273a34c18c2abfda419f15fed2502aa` (tree `8fd9326a4292831439c41516a100fd4f05ae4152`) discharges only the six step-1 unchanged properties under this stated relation. These are six translated refinement cases, not exact vector passes; the remaining 107 unchanged markers and full S0 conformance remain open. The accepted R3.21 audit remains separate and is not merged into this candidate. The source is local/unpublished and has no exact-head CI receipt.

**Validation receipt:** author and independent reviewer each ran 258 focused phone tests with 360 subtests and zero skips; the 40-test authority-service warning-as-error module is included in that total. The six pilot cases passed the normal and parser-mutant controls with the specified response relation, zero normal owner-channel calls, six unchanged-state witnesses and successful process cleanup. Roadmap validation against main `5310d1a9305035f43143fcffad6161619281f475` reported 0 errors and 0 warnings. The frozen fixture and legacy adapter hashes are unchanged. The focused suite includes the existing legacy-harness executions of all 70 traces, seven sensitivity mutations and three isolation probes; those are legacy-only results. Through v3, the pilot covers six translated refinements and six of 113 unchanged markers, not exact vector replays; 107 unchanged markers remain open. Full repository pytest, production integration and live acceptance were not covered.
### R3.22 WS-04 / WS-17 D3 restore-owner handoff — adopted branch-local source claim

The coordinator adopted the exact seven-file WS-04 offline source claim after accepted design `d75ad6dd6180a036b839c3a1d604f731126b254b` (tree `e82c5cf7a3065f359e3ffb81bf18c8a7e5484b7c`). WS-04 retains owner/store/service transition implementation; WS-17 retains every deployment/restore invocation and its tests. A fresh local scope check found no competing D3 branch. The parent coordinator reports a GitHub connector refresh at 2026-10-31 06:53 UTC with main `5310d1a9305035f43143fcffad6161619281f475` and draft/open/unmerged PR #290 at `46e29c26e6a4262aa47dfa96615f3a91cc990572`; no new comments or claims were found. Direct `git fetch` remains unavailable due DNS. This claim changes no ownership of deployment paths.

The adopted seven-file source claim in [the R3.22 D3 handoff log](../roadmap-log/2026-10-31-ws04-ws17-d3-restore-handoff-proposal.md) is implemented locally at source tip `4d6371caf490c4a36393560b6c97f355df647223` (tree `1dca0ce9d6a8ec5dd1d27e2e094708bdd7bdfd7a`) on `codex/ws04-ws17-d3-restore-handoff-20261031`. It adds an offline internal `restore.prepare` pending fence and controlled-child shutdown using disposable SQLite and a fake anchor. The closed v3 phase contract uses a canonical UUID operation ID; `child.restore.database_pending` is one-way with `{grant_id, operation_id}`; `child.restore.fenced` carries the same fields and receives the exact prepared receipt with its correlation ID. The owner retires its grant before sending that receipt, the child retires its matching local grant on receipt, and there is no ordinary release or separate grant-retirement frame after prepare. The shutdown request uses a fresh correlation ID, its acknowledgment echoes that ID, and the owner retains its singleton lock while bounding shutdown/reap cleanup and escalating TERM to KILL for its own child when necessary. Uncertain anchor-write/readback and post-pending failures do not yield a successful prepare receipt; lock retention is based on the attempted pending write, not only a successful acknowledgment. Ordinary grant release is reserved for a well-formed pre-write denial after exact stable anchor/database verification; missing, pending, corrupt or mismatched reads retain existing fail-closed behavior. Local busy sends no wire request. A proven pre-write failure may leave stable bytes; an invoked but unverified anchor write is uncertain and must not produce an acknowledgment or external action. Only a verified pending/mismatched pair is guaranteed to fail normal startup.

Author validation on the exact source tip used Python 3.12.13/pytest 9.1.1 with the rebuilt test owner: 224 focused phone tests and 352 subtests passed with no skips. Within the 224-test/352-subtest focused phone run, eight restore-specific actual-process test methods passed, including a child that stays alive after closing its socket and a child that withholds shutdown acknowledgment; the owner escalated termination, verified reaping, and retained the singleton lock. One additional restore-specific store test is also included in that total; these nine cases are not additive. Twenty-two selected Swift tests passed with no skips in a temporary no-dependency package built from the exact owner sources. Independent review separately reproduced 224 phone tests/352 subtests and 22 isolated Swift tests, all with zero skips. `scripts/check_roadmap.py --main github/main` reported 0 errors and 0 warnings; `git diff --check` passed. The full MortimerHost package test could not resolve its external WebRTC dependency. Independent exact-source review ACCEPTED this source commit; the candidate remains branch-local and unpublished, so exact-head CI is pending.

This remains prepare-only. There is no completion, DB replacement, restore invocation, WS-17 script edit, service restart or production owner channel. It preserves the existing owner/child socketpair for this offline test scope and does not claim that the shell deployment helper can call it.

The larger completion design remains blocked: the old child is the SQLite writer and must exit, but a restricted recovery child and safe rebinding protocol are undefined; a memory-only hold cannot protect a stable DB/anchor state after a lost completion acknowledgment or owner death; DB plus WAL/SHM replacement is not atomic and requires a staged quiescence/hash/interruption design that also covers the normal checkout/build rollback path. The existing plan requirement to reconcile restored authority and invalidate stale grants/sessions remains; this proposal does not choose blanket revocation/re-pairing. Whole-host rollback of both SQLite and Keychain is not detected and requires trusted external recovery or explicit disablement. D3 remains open.

**Adopted source scope, recorded before implementation:** `macos/MortimerHost/Sources/PhoneRemoteAuthority/PhoneRemoteAuthorityOwner.swift`; `jarvis/bot/phone_remote_authority_channel.py`; `jarvis/bot/phone_admission_store.py`; `jarvis/bot/phone_remote_service.py`; `tests/unit/test_phone_admission_store.py`; `tests/unit/test_phone_remote_authority_service.py`; and `macos/MortimerHost/Tests/PhoneRemoteAuthorityTests/PhoneRemoteAuthorityProcessTests.swift`. Only offline `restore.prepare` pending fencing, service teardown, restore-specific grant retirement/shutdown and owner-lock hold are in scope. Preserve ordinary v1/v2/v3, login, challenge and service-denial behavior. Disposable SQLite, fake anchor and actual disposable owner/child processes only. Completion, recovery child/rebinding, replacement/reconciliation, WS-17 scripts, production Keychain/signing, installed services, live restore/deployment and publication remain out of scope. No archive, installed script, database, Keychain, service or real restore was accessed. No publication or merge is included.

<a id="r323-results-snapshot-resume"></a>



### R3.23 Adopted WS-04 / WS-17 / WS-30 offline results snapshot and resume claim (2026-10-31)

This design follows the reserved `results.snapshot` and `results.resume` operations in R3.4. The coordinator adopted the original 15-path offline source claim on `codex/ws04-ws17-ws30-results-snapshot-resume-20261031`, based on independently accepted design commit `92dbcc5a7d95f3f89f4c2b7312edd2bc1a9bd456` (tree `5853de654f236a3d07e636f751d0250f848f964d`); a later test-only amendment made the effective source scope 16 paths. Independent source review ACCEPTED exact candidate `b4ae7740719f45e4dd81ad3f4917c789c608f57c` (tree `88a201a809f1310c950032ee04d199fa63deeec6`). This is bounded offline synthetic behavior, not a live result feature or connected client.

#### Authority, collection grant and versions

The `PhoneResultCollectionGrantV1` proposed here is **new authority** and does not exist in the current `read` scope. For this offline claim only, a trusted test fixture constructs it directly before starting the synthetic provider; no phone request, JSON field, model output, UI selection or network message can construct, broaden, replace or revoke it. Construction names exact `owner_id`, `device_id`, current `phone_grant_id`, `collection_id` (canonical UUID), and at most 25 canonical result UUIDs selected for this synthetic collection. It is immutable. It is active only when paired with the live server binding and its exact `read` scope. An authority-owned in-process registry holds the current immutable grant version and state; revocation or an explicit membership/scope change atomically replaces the registry entry, increments its bounded integer version and rotates an opaque `collection_epoch`. Old grant objects/cursors/receipts do not become valid again. The fixture API is not a production issuance/revocation path.

Keep three kinds of change distinct:

- `generation` is the current authority-child process incarnation, encoded as a canonical lowercase UUID string. It changes on process restart.
- `collection_epoch` is a canonical lowercase UUID string for the current grant and visible membership. `grant_version`, selected-membership version, per-selected-source classification version, per-selected-source revision, and event sequence are internal exact integers in `1..2^63-1`; they advance monotonically without wrap, and exhaustion fails closed. The epoch rotates on grant revocation/replacement, selected membership changes, removal of a currently visible member, or a previously visible result becoming protected/unclassified. It does **not** change for ordinary content edits or for activity on a never-visible protected/unselected source.
- `content_watermark` is a nonnegative exact integer in `0..2^63-1`, scoped to the current collection epoch. It advances only for visible ordinary-result upserts. It does not count protected or unselected activity. Sequence exhaustion fails closed; it never wraps.

Each preparation captures an immutable snapshot of the active grant, its explicit membership, the collection epoch, the journal high-water, and per-selected-source identity/revision/classification versions. It does not use a global source-registry counter. The final preparation commit compares the captured grant/membership/epoch and the exact selected-source preparation versions with current state; if an included source changes during preparation, discard the whole candidate page before returning bytes. Changes to unselected or never-visible protected sources do not alter these versions or invalidate a selected page. Grant/provider callbacks and source reads happen outside locks. The final bounded commit uses only service-owned immutable values and nonblocking version/state checks under the established authority→result-authority→service/ledger ordering; no injected callback runs under those guards.

After a page has passed final checks and received the normal release acknowledgment, it is an immutable committed historical receipt. A later ordinary content edit alone does not invalidate that receipt or a cursor already bound to it. Exact receipt/cursor replay rechecks current session/authority, active grant version, selected membership, source identity and current classification/provenance, but does not compare a global source-registry version or require the source still to have the historical content revision. This permits an already-authorized ordinary historical page to be retried after an ordinary update while preventing a changed binding, deleted/replaced source, membership change or stricter classification from replaying it. A valid old cursor presented with a new request after its epoch is invalidated receives the content-free reset DTO. An exact cached receipt whose current visibility gate has changed is withheld with `unavailable/authority_unavailable/{}`; a revoked binding/grant receives `denied/not_authorized/{}`. New preparations still use coherent captured versions. This synthetic adapter state is ephemeral, not durable authority.

The existing Mac `WorkspaceStore` contains in-memory `WorkspaceResult` values, but its inventory revision is not a per-item revision or event journal. `ResponseResultRouter` can update a body under a stable UUID, and no reviewed native-to-Python bridge supplies trusted source revision/classification. `DisplayPayload.isProtectedLocal == false` and UI labels are not admission proofs. This proposal edits neither store/router nor claims a production bridge.

#### Closed v1 wire DTOs

Preserve the R3.4 envelope, strict UTF-8, duplicate-key/non-finite/depth rejection, closed keys, exact request-ID correlation, existing 1 MiB wire limit and R3.9 status/reason allowlist. Every added integer is exact JSON integer (booleans and floats rejected); every object has exactly its listed keys. Use these exact status/reason pairs only:

| Outcome | Wire status/reason | Payload |
| --- | --- | --- |
| Snapshot, normal resume page, or reset response | `ok/none` | Exact operation-specific success DTO below |
| Bad envelope, payload, UUID, cursor grammar, duplicate ID/key, invalid integer/string/size | `denied/malformed_request` | `{}` |
| Authenticated current binding, read scope, or active collection grant fails | `denied/not_authorized` | `{}` |
| A well-formed cursor is unknown, expired, foreign to this binding, or tied to an older generation/epoch | `ok/none` with the exact no-content reset DTO below | Reset DTO, no content |
| Same request ID with different operation/version/digest, or an in-flight duplicate | `denied/request_conflict` | `{}` |
| Existing request-ledger or live cursor-registry capacity exhausted | `denied/request_capacity` | `{}` |
| Feature disabled | `unavailable/feature_off` | `{}` |
| Current owner unavailable | `unavailable/owner_busy` | `{}` |
| Authority/store/provider/projector invariant failure, collection exceeds its bound, serialized success would exceed its byte cap, or source/current-state revalidation is uncertain | `unavailable/authority_unavailable` | `{}` |
| Source provider is temporarily unavailable while the final gate still verifies the same active grant and visibility epoch | `unavailable/operation_unavailable` | `{}` |
| Unsupported major protocol version | `incompatible/unsupported_protocol` | `{}` |

Success is always `ok/none`. Results code does not use `voice_not_ready`; once implemented it does not report these supported operations as `operation_unavailable`. Errors never contain source/result IDs, cursor values, titles, body text, grant IDs, exception text or partial DTOs. A well-formed but expired, unknown, foreign-binding, old-generation or old-epoch cursor on a fresh request is deliberately indistinguishable from any other cursor requiring resynchronization: it receives the no-content reset success variant below, not an existence-revealing error. The provider-only `operation_unavailable` result may retain already-authorized items as stale with an error indicator only because the independent final authority/visibility gate succeeded; `authority_unavailable`, `not_authorized`, `feature_off`, reset, local logout and foreground loss cause masking/clearing when observed by the client.

Request IDs retain the R3.9 rule: nonempty valid UTF-8, at most 128 bytes. Request payloads are exact: `results.snapshot` is `{}`; `results.resume` is `{"cursor":"<token>"}`. Cursor token grammar is exactly 43 ASCII characters from `[A-Za-z0-9_-]`, canonical unpadded base64url for 32 random bytes. The token is only a lookup handle; it grants no authority. No request accepts an owner/device/grant/session/scope/collection/source/classification/version selector.

A snapshot result item has exactly `{result_id, revision, source, classification, title, body, received_at_ms}`. `result_id` is a canonical lowercase UUID string and equals `source.id`; `revision` is an exact integer in `1..2^63-1`; `source` is exactly `{kind, id, revision}`, where `kind` is `synthetic.workspace_result.v1` and `source.revision == revision`; `classification` is the trusted projector's literal `ordinary`; `title` is nonempty valid UTF-8 of at most 512 bytes; `body` is nonempty valid UTF-8 of at most 8192 bytes; `received_at_ms` is an exact integer in `0..2^53-1`. Reject invalid scalar encoding and NUL; strings are rendered as plain text, never HTML/Markdown or assets. All item objects and IDs in one snapshot are unique. Snapshot items sort by the raw ASCII bytes of `result_id` ascending.

Snapshot success is exactly `{generation, collection_epoch, content_watermark, cursor, items}`. It is complete: the host-selected grant has at most 25 members. If the provider yields more than 25 selected records, duplicate IDs, or any source/projection ambiguity, fail the whole request with `unavailable/authority_unavailable`; never truncate and issue a cursor that implies a complete snapshot. Trusted protected records are omitted without IDs or metadata. Missing/malformed/conflicting/unverifiable classification fails the whole operation closed. A canonical serialized success response must be at most 512 KiB after UTF-8 JSON escaping; if it exceeds the cap, return only the mapped empty error and do not advance cursor state or send a partial page.

A normal `results.resume` success is exactly `{generation, collection_epoch, content_watermark, reset_required:false, has_more, cursor, events}`. `generation` and `collection_epoch` are the same exact types as snapshot; `content_watermark` is the captured page high-water; booleans are exact JSON booleans. Each event is exactly `{sequence, kind:"upsert", item}`, with `sequence` an exact integer in `1..2^63-1` and `item` the full exact item DTO. Sequences in a page are strictly increasing and contiguous. There are no tombstone/remove events in this version: any effective membership removal or visibility increase rotates the collection epoch, invalidates cursors and forces a no-content reset. This deliberately prevents a removal ID/revision from disclosing protected or never-visible activity.

The reset success variant is exactly `{generation, collection_epoch, reset_required:true}` and contains no cursor, content watermark, IDs, revisions, items, events or `has_more`. The client must atomically mask/clear the old collection before requesting a fresh explicit snapshot. It cannot keep showing old cards while reset is pending.

#### Snapshot, paging, visibility and cache semantics

The synthetic grant is at most 25 exact member IDs. The projector emits only those members currently classified ordinary. Records outside the grant and protected/unselected records are omitted and do not affect visible sequence, watermark, epoch, response size, page count or cursor metadata. A protected record never previously visible creates no event and no epoch change. If a visible ordinary record becomes protected, loses verifiable provenance, or disappears from the selected set, rotate the collection epoch, invalidate old cursors and cached page eligibility, and make the next old-epoch resume return the generic reset DTO. Do not send its ID, revision, prior body, classification transition or reason. After the client receives reset, it masks the old collection before requesting a fresh snapshot; a new snapshot restores only currently admitted records. Revoking the grant or authenticated session instead yields the mapped authorization denial and the client clears/masks cached content.

Ordinary edits preserve the grant/collection epoch and append an upsert with a strictly greater source revision and visible sequence; within an epoch, a result’s emitted revisions are strictly increasing, and no page repeats a sequence or result/revision pair. `content_watermark` is the highest visible sequence in a coherent source snapshot. The journal retains at most 256 events and 512 KiB; if retention has dropped a cursor's required position, return reset, never a partial history. A cursor freezes a traversal high-water on its first resume. Pages contain at most 25 events at or below that high-water; `has_more` is true exactly when more retained events at or below it remain. Events arriving while pages are read receive greater sequence numbers and appear only after the frozen traversal drains and the next resume captures a new high-water. Page order is ascending sequence. A same-epoch ordinary edit during paging may leave an earlier ordinary upsert followed by its newer upsert; both revisions remain authorized ordinary history. If an exact page was already committed before the later edit, retrying its cursor/receipt returns those same historical bytes after checking current identity, membership, authority and ordinary classification, without requiring current content revision equality. Before each page is committed, recheck the current selected source identity, current ordinary classification/provenance and current visibility epoch. If source identity changes, it disappears, or classification becomes stricter, the epoch/reset rule wins and no historical content bytes are emitted. Exact revision values are never rewritten to pretend an old event is current.

Cursor entries are random 32-byte tokens in a bounded server-owned registry, maximum 256 total and 8 per authenticated binding; stored cursor metadata is capped at 64 KiB total. Entries are bound to the complete authenticated binding, grant ID/version, collection ID/epoch, process generation, sequence position and optional frozen high-water; lifetime is 15 minutes. Expired entries may be pruned. Live entries are never evicted to make room; exhausted capacity returns `denied/request_capacity`. Same cursor + same binding + same retained history yields the same page and stable successor cursor; rereading a cursor is nondestructive. Unknown/expired/foreign/old-generation/old-epoch valid tokens all return reset without revealing which condition applied. Malformed grammar is `denied/malformed_request`.

The existing request ledger remains the request/replay authority. It reserves `(full binding, request_id)` atomically before any provider read, records operation/version/digest, rejects changed retries and in-flight duplicates, and fails closed at capacity without evicting live replay history. A cursor is not destructively consumed. At final commit, after provider work outside locks, revalidate current binding/scope, grant and membership/version, source identity/current classification, generation/epoch/cursor state, page and escaped response bounds. The child must receive the normal v3 release acknowledgment before the immutable receipt/successor cursor is committed and any response bytes are returned. At preparation commit, compare the exact captured selected-source versions for coherence. After commit, replay checks current identity, membership, authority and classification but deliberately does not compare content revisions or unrelated global/source versions; this is what preserves an authorized historical receipt across ordinary edits. A changed collection/visibility epoch with an exact cached receipt returns only `unavailable/authority_unavailable/{}`; a fresh request using an old valid cursor gets the reset DTO. Receipt finalization runs on the serialized owner worker before it accepts another request. If release acknowledgment is lost or uncertain, mark the request uncertain, withhold all success/content bytes, fence the service and do not replay. Exact retry after successful finalization returns the same retained immutable receipt only after current authority, active-grant, selected-membership, source-identity and current-classification gates pass. Later ordinary revisions and excluded-source changes do not invalidate an authorized historical receipt; revocation, membership/source-identity change or stricter classification withholds the bytes using the existing neutral mapping. No snapshot/resume advances source state, and failed/cancelled/uncertain work never advances the client cursor.

The Swift client uses its existing one-exchange cancellation/drain behavior. Cancellation before dispatch produces no request. Once dispatched, the request remains owned until response drain; no overlapping selection/request is sent while busy, and no automatic replay occurs after uncertain completion. The model validates the whole checked response before publication and applies a page/reset atomically. Ordinary data that remains authorized may be retained with a stale/error indicator during a transient source-unavailable response, matching phone-plan §5/A08. Client masking is promised only when an event is observable locally or received: local logout/foreground loss, or a received reset/denial/authority failure. There is no push, polling, remote cache erasure, or recall of bytes already emitted. While offline, an old screen may remain visible but is inert and has no command authority, as phone-plan §5 permits. Once the server observes revocation, stricter classification or lost authority, it refuses further output under its authority gate; the client clears/masks when that denial/reset reaches it.

#### Adopted paths, owner split and exact test scope

The existing WS-04, WS-17 and WS-30 Scope/Where records are amended by this adoption for this exact slice. Owner Codex; Luna author; existing independent reviewer `01a18584-92e2-7511-aca8-983bb3f230ef`.

- **WS-17:** add `jarvis/bot/phone_remote_results.py` and `tests/unit/test_phone_remote_results.py` for the immutable synthetic grant/provider/projector, trusted classification, bounded visible journal/cursor state and page formation.
- **WS-04:** modify `jarvis/bot/phone_remote_protocol.py`, `jarvis/bot/phone_remote_service.py`, `tests/unit/test_phone_remote_protocol.py`, `tests/unit/test_phone_remote_service.py`, and `tests/unit/test_phone_remote_authority_service.py`. The final path is the actual-process service/authority harness; it must test results using the real disposable owner/child and SQLite store, not an in-process substitute. These paths are already in WS-04 scope and this proposal does not seize them.
- **WS-30:** modify `ios/MortimerPhoneCore/Sources/MortimerPhoneCore/PhoneRemoteOperationsV1.swift`, `ios/MortimerPhoneCore/Sources/MortimerPhoneCore/PhoneAppPreviewModel.swift`, `ios/MortimerPhoneApp/MortimerPhoneApp/PhonePreviewFakeTransport.swift`, and `ios/MortimerPhoneApp/MortimerPhoneApp/PhonePreviewRootView.swift`; modify exactly `ios/MortimerPhoneCore/Tests/MortimerPhoneCoreTests/PhoneRemoteOperationsV1Tests.swift`, `ios/MortimerPhoneCore/Tests/MortimerPhoneCoreTests/PhoneRemoteOperationsClientTests.swift`, `ios/MortimerPhoneCore/Tests/MortimerPhoneCoreTests/PhoneAppPreviewModelTests.swift`, and `ios/MortimerPhoneApp/MortimerPhoneAppTests/PhonePreviewUITests.swift` for checked DTO, client, atomic model and visible-reset behavior. Reuse `PhoneRemoteOperationsClient`, its checked bytes and the persistent disconnected banner; no second parser/client or real transport.

The source branch is `codex/ws04-ws17-ws30-results-snapshot-resume-20261031`, based on this accepted design candidate. Fresh local source/branch checks found exactly the two WS-17 projector paths absent and the other 13 existing paths already claimed by their respective WS-04/WS-30 rows; the coordinator-approved adoption amends those owners only for this feature. Do not edit frozen `tests/fixtures/phone_admission_contract/v1.json`, its original adapter, `phone_admission.py`, authority owner/channel, `WorkspaceStore.swift`, `ResponseResultRouter.swift`, JarvisKit, `server.py`, startup/configuration, migrations/persistence schema, WS-21 display paths, deployment scripts or real app transport.

**Coordinator-adopted test-only amendment (2026-10-31, recorded before source edit):** add the already-WS-04-owned `tests/unit/test_phone_remote_asgi.py` to the effective R3.23 scope for the single operation-forwarding case that covers `results.resume`. Its fixture must supply a canonical 43-character cursor so the test exercises a valid request and continues to assert service forwarding. Add an adjacent missing-cursor assertion that verifies strict ASGI/protocol rejection occurs before the service is called. No change to `jarvis/bot/phone_remote_asgi.py` or its runtime behavior is authorized. This one-file amendment changes the effective source-path total from 15 to 16; the original eight WS-30 and two WS-17 paths and five other WS-04 paths are unchanged.

#### Required offline acceptance

Use synthetic records and grants, disposable SQLite/fake anchor, the actual v3 owner/child/service path, and the existing checked Swift client. Include:

1. Positive complete 0/1/25-item snapshots, explicit 26-item overflow with zero partial bytes/cursor, stable sort, exact UUID/revision/watermark boundaries, duplicate IDs, field/integer/UTF-8/control/JSON escape bounds, and response-byte overflow.
2. Snapshot → at least two resume pages → ordinary update during paging; assert frozen high-water, ordering, exact `has_more`, exact same-cursor page/successor on repeat, new events after drain, journal gap reset, cursor expiry/foreign binding/process restart/reset, token grammar and total/per-binding capacity without live eviction.
3. Grant construction only from trusted test setup; phone-supplied selectors ignored/rejected; collection membership/version/revoke, phone `read` scope, binding substitutions, exact selected-source revision coherence during preparation, and current identity/classification checks on cached receipts; prove cached historical bytes still replay after a later ordinary revision. Use actual process harness `tests/unit/test_phone_remote_authority_service.py` for owner/child admission and service path.
4. Never-visible protected canaries and mutations to excluded sources do not change the selected grant versions, epoch/watermark/sequence/response length and never disclose IDs/revisions; prove this both during preparation and cached-page replay. A later ordinary edit preserves a previously committed page replay, while a change racing the original preparation forces that uncommitted page to be discarded. Ordinary→protected and ordinary→unprovenanced transitions invalidate cached receipt/cursor, force reset, mask/clear the phone cache and never return old content. Ordinary same-epoch edits may yield ordered historical/current upserts only while current source remains ordinary and the grant remains active.
5. Scoped A signout denies/masks A while B obtains a fresh ticket/session and continues snapshot/resume on the same healthy child; global generation/security mutation invalidates both old bindings, with fresh B login required. Revoke or source/visibility mutation during outside-lock preparation wins at final commit and produces no bytes.
6. Actual release-ack loss after page/cursor preparation withholds success and content, fences child/service, retains no replayable success, and prevents cursor advancement; successful-ack exact retries remain nondestructive and revalidate live gates. Cancellation before dispatch does no provider call; cancellation after dispatch drains without second request or stale Swift publication. Busy rejects before dispatch until drain.
7. Exact Python/Swift status-reason-payload mapping table above, closed operation/request/response shapes, duplicate/deep/oversized/nonfinite JSON, request-ID correlation, generation/epoch UUID canonical form, safe integer maxima, cursor base64url canonical form, atomic page apply/reset and persistent disconnected/synthetic preview notice. Mutations that bypass collection grant/version checks, classification invalidation, current-source checks, receipt gating or client masking must make the corresponding test fail.

The frozen legacy 70-vector, 7-mutant and 3-isolation oracle stays unchanged and has zero exact R3.23 replays. Its 113 `unchanged:true` obligations remain separately unclaimed; no analogue substitutes for that audit. The separate accepted R3.21 audit branch is not integrated into this candidate.

#### Limits

This is an offline synthetic results refinement through the existing v3 facade and disconnected client. It does not connect real `WorkspaceStore`/native data, establish production source provenance/classification, provide a production collection-grant UI/API, persist result history, use real user content, start a listener, add TLS/networking, change protected-anchor/restore behavior, enroll/sign/install a device or establish live acceptance. WS-24 persistence and the production bridge require later coordinated claims. The published PR #290 base remains `46e29c26e6a4262aa47dfa96615f3a91cc990572` (tree `2d4ceb0ad7817aebe04980c2a6983e621cfb45e5`); Validate #543 failed on that published head. The accepted R3.23 candidate is local and unpublished, so it has no exact-head CI receipt.

#### Independent source acceptance and validation receipt (2026-10-31)

Independent review ACCEPTED source commit `b4ae7740719f45e4dd81ad3f4917c789c608f57c` (tree `88a201a809f1310c950032ee04d199fa63deeec6`). The review verified the effective 16-path source scope, including the adopted ASGI test amendment. Author and reviewer phone test runs each reported 257 tests and 360 subtests with zero skips; the reviewer used unittest discovery with a subtest-counting runner. The separate 39-test actual-process warning-as-error run is included in that total, not additive. The reviewer also ran all 58 Swift package tests and built the unsigned generic app/UI-test bundle including the fake-transport snapshot→resume test. The author independently compiled/typechecked the Core sources/tests and exercised the app fake transport through a checked snapshot→resume round trip. The author’s `xcrun swift test` could not start in this sandbox because SwiftPM was denied access to the user-specific Clang module-cache directory; the independent reviewer used the normal approved Mac test workflow. Roadmap validation reported 0 errors and 0 warnings. UI execution, rendered appearance/usability, simulator behavior, live transport, real source integration, credentials, signing, service activation and production acceptance remain unverified. No R3.21 audit material is included.

## R3.24 D3 recovery-completion (adopted offline source claim)

The coordinator adopted the independently accepted design `e7eb2176f54f5c004be2bd16e159ce905080699a` (tree `b2b67ddfd4fbd4ab9960e93f11a6ce9aae5a7d67`) for exactly twelve source/test paths, recorded in the WS-04 row before implementation. Source branch: `codex/ws04-ws17-d3-recovery-20261031`; owner Codex, Luna author, existing independent WS-04 reviewer `01a18584-92e2-7511-aca8-983bb3f230ef`. Fresh local worktree/path checks found no competing dirty edits; parent GitHub refresh at 11:38 UTC reported public PR #290 and main unchanged with no published-path conflict. This local clone has no `origin/main` ref (only `origin/HEAD` to the D3 handoff branch), so the required main merge could not be performed; source work proceeds only on the accepted-design descendant and integration must reconcile current main first. WS-04 owns the protected owner/channel/store/recovery and service fence; WS-17 retains every backup/restore/deploy invocation and script. The scope is offline synthetic only: injected trusted authorization, fake protected storage, disposable SQLite and controlled processes. Preserve all accepted v1/v2/v3 and R3.15/R3.18/R3.19/R3.22/R3.23 behavior and frozen fixtures. No production controller, real Keychain, signing, installation, live database, old archive/script execution, listener, deployment or restore is included.

### Trust boundary and compatibility

Only an explicit local, user-authorized recovery controller may initiate this operation through a future authenticated native-owner interface. Phone/HTTP/MCP requests, shell arguments, caller-selected paths, IDs, UIDs/PIDs, executable paths, or code-signing identity alone do not authenticate that controller. The production controller channel, signed packaging and entitlements are not implemented. Offline tests inject a trusted authorization capability; this is not production caller authentication. The native owner remains protected-anchor owner, singleton supervisor, final state-transition authority, and keeper of the admission fence. A compromised authorized recovery child is inside the trust boundary.

R3.22 stays prepare-only. Its current `prepare_restore(expected_host_id, expected_generation)` writes a six-field anchor-v1 pending state with a canonical bare-UUID transition ID and matching pending database metadata, but does not capture a pre-restore authority checkpoint or bind a source manifest. A future owner classifies `legacy_pending_unbound` only when that bare UUID and pending DB metadata match the known R3.22 restore shape; it keeps service denied and retains the hold. Labeled ordinary pending IDs such as `login:<hex>` or `<label>:<hex>` are not relabeled as restores; they follow existing exact-transition validation and otherwise remain fail-closed. Unknown or mismatched pending states are generic transition failures. No automatic v1-pending conversion is proposed. This is offline test state, not evidence of a production restore.

The future implementation preserves current anchor-v1's exact six keys and canonical behavior. It introduces protected anchor-v2 only in a new owner/store build. Old v1/v2/v3 owner/store executables must reject the v2 exact-key protected shape and never serve it. The new owner uses the closed v4 channel for both recovery and normal-child supervision; existing v1/v2/v3 bytes and behavior remain unchanged. For ordinary phone-service operations, v4 carries the existing v3 operation names, payload schemas, and six-field `AnchorState` projection (`anchor_version:1`, byte-exact host, generation, transition ID/state and protected login counter). The projection is only a compatibility view; it does not claim that the protected item is v1. The owner validates every projected read/advance against the complete current protected-v2 object and preserves `pending_restore:null` and the exact `last_completed_restore` tombstone. Ordinary operations remain exactly `store.open`, `store.read`, `session.login`, `session.signout`, `authority.mutate`, `ticket.issue`, `ticket.consume`, v2 `service.authorize`/`service.commit`, and v3 `session.challenge`; no restore operation is exposed in normal service. `phone_remote_meta.schema_version` is the SQLite schema marker and may be 2; it is distinct from protected `anchor_version` and the six-field projection marker. Compatible pairs are protected-v1/store-schema-v1 before first recovery, or protected-v2/store-schema-v2 in the new build; cross-version/mismatched pairs fail closed. No implicit migration or startup bootstrap is permitted.

### Executable ownership and transition

The native owner opens and locks the existing stable inode, with no-follow and ownership/mode checks, before reading any anchor or launching a child. The same exclusive lock remains held across the normal child, restore preparation, recovery child, replacement, and restarted normal child. The owner never drops the lock while a normal child lives. Each controlled child inherits the lock descriptor and must keep it open for its entire lifetime. On owner replacement, the old owner stops and reaps its child before exiting while the authority is pending. A replacement opens the same file, verifies its stable identity, then acquires the exclusive lock before inspecting state. If an old child survives owner death, its inherited descriptor keeps the lock held; the new owner refuses/waits and never signals an unowned process. The child treats observed EOF/protocol failure as terminal and performs no later operation; a SQLite transaction already in progress may commit before the child observes EOF, so its outcome is uncertain until the next owner inspects actual anchor, DB and journal state. This proof depends on mechanically retaining the inherited descriptor in every child. The lock file is never unlinked/recreated. If identity or prior-child exclusion is uncertain, do not admit service.

The owner lifecycle has two distinct continuations. While the original owner remains alive after `restore.prepare`, it stays in its recovery-held state and services `continue(operation_id)` by launching only the recovery child; after verified completion it may launch the normal child and retains the same singleton lock for that child's lifetime. The recovery hold is not ended by releasing the lock. If the owner process dies, a replacement may continue only after acquiring the same lock inode; if an inherited old child still holds it, replacement is refused until that child exits and the lock can be acquired. No new owner kills or adopts an unowned child. Ending recovery hold never means dropping singleton exclusion while a normal child is alive.

A new supported prepare has a checkpointed pre-pending sequence. These phases define the actor and ordering; in particular, no SQLite writer is stopped and then implicitly expected to continue across a process shutdown:

1. The authenticated local controller selects an owner-catalogued backup object. The native owner creates the canonical operation UUID for this new recovery request; a caller cannot choose it. If a prior tombstone exists, this new ID must differ from its `last_completed_restore.operation_id`. The owner validates the catalog descriptor, preliminary source digest/size and exact supported application-schema catalog before any authority mutation. The source schema identifier is separate from the phone-store schema version.
2. After caller/source identity and catalog preflight, the owner starts quiescence for this exact new operation ID. At the instant quiescence starts, record one absolute monotonic deadline five seconds later; the deadline never resets or extends. It first closes admission for new logical operations and freezes their accepted operation IDs, so no new operation can extend the set. Only a continuation bound to a frozen operation may finish its already-authorized work and remaining authority exchanges, including `service.commit` after that operation’s accepted `service.authorize`, plus terminal output/completion bookkeeping. The continuation must match the existing authorization/receipt and cannot create new admission. Grants may be issued only for these bound continuations. Queued `_AuthorityChildServiceHost._submit` items with no completed authorization/receipt are not admitted into the frozen set: remove them from the queue and settle their callers locally with a typed `quiescing`/cancellation result, without authority IPC or any claim about remote state. Caller cancellation before authorization has the same local removal behavior. A caller cancelling after authorization is settled locally as cancelled, but the operation remains owned and tracked through its terminal outcome; cancellation does not undo effects. If an accepted operation cannot reach its defined terminal outcome before the single monotonic deadline, quiescence fails closed and recovery does not proceed. After the set is terminal, all its grants are finished, and output bookkeeping is complete, the owner permanently stops grant issuance and sends v4 `owner.shutdown` with `{operation_id:<new recovery UUID>,reason:"restore_quiesce"}` and a fresh correlation. This ID is the requested restore operation, never the prior tombstone ID; the same rule applies before the first recovery when there is no tombstone. The activated normal child validates this terminal phase, acknowledges only after in-flight work has completed and owned service resources are closed, then closes its channel and exits. The owner verifies the echoed ID/correlation, reaps that exact child, and retains the singleton lock. If an accepted operation stalls or a commit/release acknowledgment is lost, or if drain/shutdown acknowledgment is lost or malformed, no `drained:true` or recovery mutation is permitted. At the deadline (or immediately when a terminal acknowledgment failure is observed), settle every still-waiting caller with terminal `authority_unavailable`/uncertain completion, without claiming effects were undone; stop dispatch and close the channel. Send TERM to only the owned child, wait at most 250 ms using monotonic time, then send KILL if needed and wait at most 2 seconds for that exact child to be reaped. Retain the singleton lock throughout. If reaping is not confirmed within that bound, remain unavailable with the lock held. After confirmed reaping, inspect actual protected-anchor and DB state under the lock before any later admission; already completed normal-operation effects are not rolled back. This v4 `restore_quiesce` exchange does not alter existing v1/v2/v3 shutdown frames or their byte-level behavior. With no SQLite child alive, the owner verifies the exact protected-v1/store-v1 or protected-v2/store-v2 stable logical pair. It runs `PRAGMA wal_checkpoint(TRUNCATE)` and requires zero busy frames; switches to DELETE journal mode; closes all handles; verifies no live WAL/SHM; fsyncs the live DB and parent directory. Only after this canonicalization does it compute `base_database_sha256`, the byte digest of the quiescent live main file. It then uses SQLite's backup API to create a closed immutable checkpoint and hashes that distinct image as `checkpoint_sha256`; it does not assume backup-image bytes equal live-main-file bytes. The checkpoint DB host/generation and exact device/grant projection must logically match the verified live DB and anchor; the protected anchor separately supplies the login-counter floor, since `phone_remote_meta` has no login-counter column. Capture device/grant/key/revocation/scope state from this checkpoint, not from the restore source. Compute and fsync the checkpoint and containing directory; compute the source digest and canonical manifest with the separate source/checkpoint/base digests; fsync the manifest and directory. The target generation remains exactly `G+1`; preserve the protected login-counter floor and never import a lower counter from the source. Recheck the stable logical pair after normalization. A pre-quiescence caller/source denial leaves all bytes unchanged; a post-normalization integrity failure is a storage failure, not a policy denial, and may not claim byte-for-byte unchanged files.
3. The owner starts one controlled v4 `prepare` child with no listener or normal service construction. It validates the source catalog/schema, checkpoint digest/projection, normalized base DB digest, exact stable pair and manifest. A verified preflight block sends no protected or SQLite mutation; the owner requires the correlated denial and shutdown acknowledgements, rechecks the stable logical pair and the unchanged live-base digest, then starts a normal child and gates admission on the full readiness protocol below. On successful preflight, the prepare child stays alive and idle under the owner lock. The owner writes and reads back protected anchor-v2 pending with target generation `G+1` and hashes binding operation, source manifest and checkpoint, then sends `owner.restore.commit_pending`; the child runs one SQLite transaction that explicitly upgrades store schema v1 to v2 if needed, sets matching pending metadata, and revokes/clears all sessions. If anchor write/readback is uncertain, the owner sends no `commit_pending`; it terminates/reaps only this owned child and classifies the persisted state from actual protected/database bytes under the same lock. If the verified pending anchor remains with exact base DB, continuation uses `prepare_resume` as defined below; if the matching pending DB transaction already committed, continuation enters `recover`. A verified pending anchor can never be undone by denial. The owner returns a prepared receipt only after matching DB-pending commit, service fence, child shutdown acknowledgment and reaping; it then remains in pending hold. Authority rows in the eventual installed DB come from the bound checkpoint, never from the selected backup: preserve device identities/public keys, grant scope/generation/revocation fields exactly; set DB meta host generation to target `G+1`; retain protected login-counter floor; never lower a counter. Reconciliation ambiguity blocks completion.
4. On recovery, either the still-live owner continues under the same lock after its prepare child has exited, or a replacement owner first acquires that same lock inode. It independently hashes the fixed checkpoint file and requires equality with the digest bound by the protected pending anchor and immutable manifest; it verifies the checkpoint authority projection against `authority_sha256` without deriving identity from the restore source or current restored database. It then launches a different-incarnation v4 `prepare_resume` or `recover` child according to the durable DB phase. No normal service or listener starts while anchor, journal, manifest, database and receipt are pending or uncertain.
5. After verified database completion, the recovery child exits and is reaped before the owner writes stable anchor-v2. The owner performs recovery-artifact cleanup while holding the singleton lock and with no service child. Only after cleanup has a durable complete journal state does it launch a normal v4 child, passing the full protected anchor-v2 snapshot in the authenticated local owner channel. `child.ready` is only a transport handshake. The child opens the store under the normal `store.open` grant, compares the DB receipt using the exact receipt-to-tombstone map defined below (including the retained-manifest check for `authority_sha256`, but never comparing historical `database_sha256` to current bytes), and emits `child.service.ready` only after successful `store.open` release acknowledgment and strict receipt/schema checks. The owner compares this ready receipt tuple with the protected tombstone it still holds, then sends `owner.service.activate`; the child returns `child.service.activated`. No service operation is accepted before activation. In offline tests, the harness gates the service API on this activation acknowledgment; no listener is created or specified by this design. The owner acknowledges completion to the local controller only after cleanup and activation; it remains supervisor and retains the lock for the normal child lifetime.

A crash before the protected pending write leaves the prior stable logical anchor/database state; quiescent WAL normalization may already have changed live-file bytes, but no source replacement or authority mutation has occurred. A later ordinary start is permitted only after verifying the stable logical pair and the exact normalized `base_database_sha256`. Once anchor pending is verified, no denial or error can restore stable state, release the owner hold, or start normal service. A blocked recovery response is diagnostic only and contains no private data. Uncertain protected/database writes or file renames receive no success acknowledgment; restart reads the actual persisted state and only resumes the same operation if all bound evidence matches.

The protocol distinguishes pre-pending denial, pending-operation continuation, and a stable completed-operation retry. Before the pending anchor is written, the v4 prepare child returns a correlated `preflight_result` denial and then a correlated `shutdown_ack`; the owner rechecks the stable logical anchor/DB pair and exact normalized `base_database_sha256` before restarting the normal child. This v4 preflight holds no ordinary v3 grant, so there is no v3 grant-release message. After the pending anchor is verified, phase-2 denial, capacity failure, child error, or lost acknowledgment cannot invoke ordinary `grant.release`, restore the old stable anchor, or relinquish the recovery hold. It returns no prepared/completed success and remains blocked for that operation. A pending retry can continue only the same `operation_id` after revalidating its bound checkpoint, manifest, journal and current files. To enter `prepare_resume` after a lost commit acknowledgment, the owner first closes and reaps the previous prepare child (or observes confirmed exit), then starts one new child incarnation under the still-held singleton; no two children overlap. An owner that remains alive retains its incarnation and lock. A child that actually exited is never treated as reusable. Any other operation is rejected without replacement effects. A completed retry is permitted only when a stable anchor-v2 tombstone and matching DB receipt prove that the same operation, target generation, manifest and checkpoint match under the explicit receipt map below, the cleanup journal is `complete`, and the normal child is currently healthy. While those gates are incomplete, return `pending` or `blocked`, never cached `completed`. A retry handled by the still-live owner/child uses a fresh request correlation but the same process incarnations and does not restart a healthy child; only an actual process restart creates new incarnations. It returns the recorded completion result and performs zero checkpoint, staging, rename, DB, anchor or service-replacement effects. Only the latest retained tombstone is retryable; after a later recovery supersedes it, the older ID is a retired no-op. The stable tombstone is preserved across ordinary login, signout and security-revocation transitions, so those transitions cannot erase current retry identity.

### Closed v4 recovery protocol

The future owner/child recovery channel uses `mortimer.phone-authority-channel.v4`; existing v1/v2/v3 bytes and behavior remain unchanged. Frame format is a four-byte unsigned big-endian length followed by UTF-8 JSON, 1–65,536 bytes. The envelope has exactly `{protocol,version,kind,owner_incarnation,child_incarnation,sequence,correlation_id,payload}`. Version is exact integer 4; UUID fields are canonical lowercase UUIDs; sequence is exact uint64 in `1..2^64-1`, starts at 1 in each direction, never wraps, and cannot skip/replay. JSON rejects duplicate keys, non-finite numbers, unknown fields and non-object payloads. Each request/reply pair uses a fresh correlation UUID and the reply echoes it. The operation UUID remains constant for the transaction. No SQL, arbitrary method, reset, initialization, migration, generic anchor overwrite or file path crosses the channel. File bytes use owner-opened fixed descriptors; frames carry bounded metadata and hashes only.

The exact owner→child and child→owner frame pairs are:

| Request → reply | Exact payload contract |
|---|---|
| `owner.hello` → `child.ready` | Modes are exactly `prepare`, `prepare_resume`, `recover`, or `normal`. Restore modes use `{mode,operation_id,host_id,target_generation,manifest_sha256}`; ready echoes those values plus `maximum_store_schema_version:2`. Normal mode uses `{mode:"normal",store_schema_version:<integer 1 or 2>,protected_anchor:<exact protected-v1 six-field or protected-v2 eight-field object>}`; ready is `{mode:"normal",store_schema_version:<integer 1 or 2>}`. Hello correlation is echoed. `child.ready` proves transport only. |
| `owner.restore.preflight` → `child.restore.preflight_result` | Fresh `prepare` only. Request `{operation_id,manifest_sha256}`. Success `{operation_id,status:"ok",manifest_sha256,checkpoint_sha256,authority_sha256,base_database_sha256,checkpoint_size_bytes}`. A blocked result is `{operation_id,status:"blocked",code}`. |
| `owner.restore.resume_preflight` → `child.restore.resume_preflight_result` | `prepare_resume` only. Request `{operation_id,manifest_sha256,base_database_sha256}`. Success `{operation_id,status:"ok",database_state,base_database_sha256}`; `database_state` is exactly `base` or `pending`. Only exact `base` may be followed by `commit_pending`; matching `pending` must not mutate again. |
| `owner.restore.commit_pending` → `child.restore.pending_result` | Legal only after fresh-prepare preflight success or `prepare_resume` result `base`; never after resume result `pending`, and never in `recover`. Request `{operation_id,manifest_sha256,checkpoint_sha256,authority_sha256,target_generation}`. Success `{operation_id,status:"ok",host_id,target_generation,transition_state:"pending"}`; blocked uses the common blocked shape. Owner sends this only after pending anchor-v2 is verified. |
| `owner.restore.inspect` → `child.restore.inspect_result` | Request `{operation_id,manifest_sha256}`. Success `{operation_id,status:"ok",phase,database_state,checkpoint_sha256,authority_sha256,base_database_sha256,staged_database_sha256,installed_database_sha256}`; nullable staged/installed hashes are JSON null. `database_state` is `base`, `pending`, or `committed`. |
| `owner.restore.stage` → `child.restore.stage_result` | Request `{operation_id,manifest_sha256,checkpoint_sha256}`. Success `{operation_id,status:"ok",staged_database_sha256,staged_size_bytes,store_schema_version:2}`. |
| `owner.restore.install` → `child.restore.install_result` | Request `{operation_id,manifest_sha256,checkpoint_sha256,staged_database_sha256}`. Success `{operation_id,status:"ok",installed_database_sha256,phase:"installed"}`. |
| `owner.restore.commit_database` → `child.restore.database_committed` | Request `{operation_id,manifest_sha256,checkpoint_sha256,installed_database_sha256,target_generation}`. Success `{operation_id,status:"ok",receipt_version:1,database_sha256,phase:"database_committed"}`; hash is computed after final DB close/fsync. |
| `child.service.ready` → `owner.service.activate` → `child.service.activated` | Activation `operation_id` is the tombstone operation for v2 and null for pre-recovery v1. After normal `store.open` and its release acknowledgment, the child validates the exact store schema. For v1, ready is `{host_id,host_generation,store_schema_version:1,last_completed_restore:null}` and no restore receipt must exist. For v2, ready is `{host_id,host_generation,store_schema_version:2,last_completed_restore:<exact tombstone>}` after applying the exact receipt-to-tombstone map defined below: compare shared operation, target generation, manifest digest and checkpoint digest; obtain host from the enclosing protected anchor; require receipt version 1; validate `authority_sha256` against the canonical retained manifest whose exact bytes hash to the tombstone manifest digest and whose operation/target/host/checkpoint fields match. Do not compare the tombstone's historical `database_sha256` with the DB receipt (which has no such field) or with current live DB bytes. The owner compares every available field to its current protected anchor and retained manifest and replies `{host_id,host_generation,store_schema_version,operation_id}`; child echoes that exact object. No normal operation is admitted before the activated acknowledgment. |
| `owner.shutdown` → `child.shutdown_ack` | Restore-mode requests use `{operation_id,reason}` where reason is exactly `preflight_denied`, `prepare_complete`, `prepare_resume_complete`, or `recovery_complete`; replies are `{operation_id}`. Normal-mode quiescence uses `{operation_id:<fresh recovery UUID>,reason:"restore_quiesce"}` and replies `{operation_id,drained:true}` only after admission of new logical operations is closed, the accepted-operation set is frozen, only bound continuations have completed, all grants and output/completion bookkeeping are finished, and owned resources are drained. It is legal in v4 normal mode only, before any restore mutation. The operation ID is the new recovery operation, not the previous tombstone ID, and is also used before the first recovery when no tombstone exists. All requests use a fresh correlation. Existing v1/v2/v3 shutdown frames remain byte-compatible. The owner validates the echoed operation ID/correlation and retains the singleton lock until the exact child is reaped. |

`owner.hello` is required for every v4 child. `prepare_resume` uses `owner.restore.resume_preflight`; its reply is correlated and contains exact `database_state` `base` or `pending`. `owner.restore.commit_pending` is legal only in fresh `prepare` after successful preflight or in `prepare_resume` after a `base` result; it is forbidden after a `pending` result and in `recover`. Restore-mode legal sequences are: `prepare`: hello/ready, preflight/result; verified denial then shutdown/ack/reap; success leaves the child alive, followed by owner pending-anchor write/readback, `commit_pending`/result, then shutdown/ack/reap. `prepare` cannot inspect, stage, install or commit the final database. `prepare_resume` is admitted only when the protected anchor binds this operation and the DB is either the exact normalized base (`base_database_sha256`) or already has matching pending metadata. It runs a read-only preflight that returns `{operation_id,status:"ok",database_state,base_database_sha256}`; the state is exactly `base` or `pending`. For `base`, it may execute the same idempotent `commit_pending` transaction once; for `pending`, it must not mutate or replay that transaction. Then it shuts down and the owner switches to `recover`. It never requires a stable anchor/DB pair and never writes the anchor. `recover` starts with hello/ready, then read-only inspect calls followed by only the phase-legal stage/install/commit_database request. `commit_pending` is forbidden in `recover`; after final DB commit, the recovery child is acknowledged and reaped before stable anchor write. Any lost `commit_pending` acknowledgment is resolved by a fresh `prepare_resume` read: exact base permits same-operation retry; exact matching pending means already applied; any third state is terminally blocked. A normal child also uses v4 hello, then transport `child.ready`, but service remains gated until the full `store.open`/receipt/activate exchange in the table. A fresh prepare preflight block may return to normal mode only after the stable logical pair and normalized live-base hash are revalidated. No mode permits overlapping children or concurrent requests.

The normal-child sequence begins with `owner.hello`/`child.ready` and the admitted v1/v2 `store.open`/release and `child.service.ready`/activation exchange. A trusted local recovery request then creates a fresh operation UUID (it must differ from the latest tombstone ID, if one exists); before the first recovery the same rule applies with no tombstone. Quiescence starts one absolute monotonic five-second drain deadline that is never extended, then uses a bounded admission barrier: reject all new logical operations and freeze the already accepted operation IDs. Permit only continuations bound to a frozen operation to finish already-authorized work and remaining authority exchanges (including `service.commit` after that operation’s accepted `service.authorize`) and terminal output/completion bookkeeping. A continuation must match existing authorization/receipt and cannot create new admission. No new operation may join the frozen set, and grants may be issued only for these bound continuations. Queued `_AuthorityChildServiceHost._submit` items without completed authorization/receipt are locally removed and their callers receive typed `quiescing` or cancellation, with zero authority IPC; they do not join the frozen set. Cancellation before authorization removes queued work. Cancellation after authorization settles the caller locally but does not cancel ownership or roll back effects; the accepted operation remains tracked until terminal completion. If a member cannot finish before the single deadline, fail quiescence closed. After every frozen operation is terminal, all associated grants are finished, and no grant remains active, permanently stop grant issuance and send `owner.shutdown {operation_id:<new recovery UUID>,reason:"restore_quiesce"}` with a fresh correlation. The child returns `child.shutdown_ack {operation_id,drained:true}` only after that bounded set and owned resources are complete, closes the channel and exits. The owner verifies operation ID/correlation, reaps that child and retains the singleton lock before any checkpoint normalization or recovery mutation. No quiescence exchange is sent for a completed retry. A stalled continuation or lost commit/release/shutdown acknowledgment forbids `drained:true` and all recovery mutation. At the deadline (or immediately on an observed terminal acknowledgment failure), settle waiting callers with terminal `authority_unavailable`/uncertain completion without claiming rollback; stop dispatch and close the channel. TERM only the owned child, wait at most 250 ms on a monotonic clock, then KILL if needed and wait at most 2 seconds for that exact child to be reaped, retaining the singleton lock throughout. If reaping is unconfirmed, remain unavailable with the lock held. After confirmed reaping, inspect actual anchor/DB state under the lock; completed normal-operation effects remain, and no new operation is admitted until the stable pair is revalidated and normal service is safely restored. This v4-only exchange leaves existing v1/v2/v3 shutdown bytes unchanged.

Every success/failure frame has exact declared keys/types; operation, host, target, manifest, incarnation, sequence and correlation match the phase. Block codes are the closed set `legacy_pending_unbound`, `operation_mismatch`, `manifest_invalid`, `source_unavailable`, `source_integrity`, `schema_unsupported`, `checkpoint_mismatch`, `authority_conflict`, `transaction_mismatch`, `storage_uncertain`, `owner_busy`, `health_unavailable`. No exception text, path, row identity or source content is returned. A source/caller policy denial happens before quiescence and changes no bytes. A v4 preflight `blocked` response after normalization is a technical pre-pending result, not a claim that DB bytes stayed unchanged; after acknowledged shutdown the owner rechecks the stable logical pair and exact `base_database_sha256`. Only that exact normalized base may restart normal service, and it must pass activation. `prepare_resume` never accepts a denial as permission to undo pending state. After pending, any operation denial, malformed/replayed frame, wrong incarnation/correlation, illegal phase, or uncertain acknowledgment retains the hold and closes/reaps only owned children; no ordinary grant release, stable rollback or service admission is permitted. Local busy is rejected before dispatch and preserves the active operation.

Normal service runs inside the v4-supervised child lifecycle, while each authority operation retains the existing v3 operation, request/reply and six-field projection schemas. The normal-mode hello passes the exact protected-v1 or protected-v2 anchor snapshot; the owner retains and validates the full object, while normal per-call grant/read/advance exchanges use the six-field projection. On v2 it preserves `pending_restore:null` and `last_completed_restore` byte-for-byte. The exact allowlist remains `store.open`, `store.read`, `session.login`, `session.signout`, `authority.mutate`, `ticket.issue`, `ticket.consume`, v2 `service.authorize`/`service.commit`, and v3 `session.challenge`. The source implementation must update the existing exact protocol-version/type guards in `phone_remote_authority_channel.py`, `phone_remote_service.py` and the native owner for the v4 normal envelope; adding a normal-mode child class alone is insufficient. Regressions must prove v4 normal login/challenge/service.authorize/service.commit succeed, malformed or wrong-version envelopes reject, and existing v1/v2/v3 fixtures remain byte-compatible. `child.ready` is not application readiness. The child is not admitted until `store.open` has completed with a successful release acknowledgment, DB schema 1 or 2 matches the anchor version, and any v2 DB receipt matches the protected tombstone by this exact map: receipt operation ID, target generation, manifest digest and checkpoint digest equal the tombstone; receipt host ID equals the enclosing protected anchor host ID; receipt version is exactly 1; receipt authority digest equals the digest in the retained canonical manifest whose bytes hash to the tombstone manifest digest and whose operation, target generation, host and checkpoint fields match. The tombstone's historical database digest is not a DB-receipt field and is never compared with current DB bytes, which may change under ordinary service mutations. The owner independently compares `child.service.ready` with its anchor/manifest snapshot, and owner/child activation acknowledgments must match. Missing/mismatched receipt or manifest, failed `store.open`, release uncertainty, or activation mismatch terminates the child and keeps the owner fence closed. This design changes no listener, route, production service construction, or public response schema.

The authenticated controller API itself remains an unimplemented local boundary, not a wire endpoint. Its proposed typed calls are `begin(source_id, expected_host_id, expected_generation)` and `continue(operation_id)`; each requires a trusted capability, never accepts a filesystem path or anchor contents, and `begin` returns the owner-generated canonical operation ID. Result shapes are `pending(operation_id,target_generation,manifest_sha256)`, `completed(operation_id,target_generation,manifest_sha256,checkpoint_sha256,database_sha256)`, or `blocked(code)` from the closed code set above. `completed` is returned only after the stable tombstone, durable cleanup `complete`, and the normal v4-supervised child has passed store.open release, full applicable receipt/tombstone comparison and activation. During pending recovery, incomplete cleanup or child-health retry, the owner returns only `pending` or `blocked`, never a cached completed result. This is a typed local proposal, not a public endpoint; tests inject the capability and verify caller fields cannot choose authority. Owner-generated operation ID and every response are checked in tests.

### Exact durable formats and database rules

**Source/recovery manifest v1:** canonical duplicate-free UTF-8 JSON, max 16,384 bytes, exact keys `{manifest_version,operation_id,host_id,base_generation,target_generation,source_id,source_schema_version,source_size_bytes,source_sha256,checkpoint_size_bytes,checkpoint_sha256,authority_sha256,base_database_sha256}`. Integers are exact uint64 (not booleans/floats); target is base+1; IDs are canonical UUIDs; host is byte-exact UTF-8, nonempty and at most 256 bytes; every digest is lowercase 64-hex; source/checkpoint sizes are `1..1,073,741,824`; `source_schema_version` is exact integer 1 only (2 is reserved and rejected until a separate catalog is reviewed). It identifies the application restore source, not phone-store schema. Catalog v1 admits only the application tables `actions`, `agent_events`, `agent_runs`, `client_tokens`, `conversations`, `council_rounds`, `council_scores`, `execution_action_claims`, `memories`, `memory_admission_jobs`, `memory_admission_shadow`, `memory_classification_budget_reservations`, `memory_classification_shadow`, `memory_extraction_cursor`, `memory_extraction_pending`, `memory_maintenance`, `memory_recall_events`, `memory_reviews`, `migrations`, `model_route_drafts`, `model_route_preferences`, `notes`, `notices`, `notices_0027`, `observations`, `procedures`, `reminders`, `skill_events`, `skill_step_check_receipts`, `llm_calls`, `model_call_budget_reservation_scopes`, `model_call_budget_reservations`, `model_task_budget_links`, and `model_task_budgets`, as emitted by the pinned `jarvis/db.py` and `jarvis/usage_ledger.py` migration set. `phone_remote_meta`, `phone_remote_devices`, `phone_remote_grants`, `phone_remote_sessions` and `phone_remote_restore_receipt` may exist only with the exact versioned authority DDL included in the pinned catalog; their rows are never imported from the source and are reconciled separately. SQLite internal objects are accepted only when present in the exact catalog generated from pinned application and phone-authority DDL. That inventory includes `sqlite_sequence` only where AUTOINCREMENT requires it and exactly these six phone-schema implicit indexes, each with `type=index` and `sql=NULL`: `sqlite_autoindex_phone_remote_devices_1`, `_2`; `sqlite_autoindex_phone_remote_grants_1`, `_2`; and `sqlite_autoindex_phone_remote_sessions_1`, `_2`. Their `tbl_name` is respectively `phone_remote_devices`, `phone_remote_grants`, or `phone_remote_sessions`; no autoindex is generated for `phone_remote_meta` or the integer-primary-key restore receipt. SQL NULL is not encoded as an empty string: each inventory field is `0x00` for NULL, or `0x01` followed by a four-byte big-endian UTF-8 byte length and exact bytes. Objects are sorted by UTF-8 bytes of `(type,name,tbl_name)` and the catalog pins the complete inventory digest and migration vector. No wildcard for autoindex names is allowed; an unlisted internal object, changed DDL, table, view or trigger is rejected. A positive disposable-database test executes the actual pinned DDL, observes the six NULL-SQL autoindexes, and matches the catalog; mutations adding an unknown object or changing a declaration fail. The owner opens a catalogued source read-only without following symlinks and passes the descriptor; child verifies `fstat`, complete byte hash, exact catalog digest, schema constraints, `quick_check`, foreign keys and host binding. Larger or unsupported databases fail closed. The manifest hash is SHA-256 of exact canonical bytes and is the identity bound into anchor v2. The checkpoint is a closed SQLite-backup API image of the current stable DB before pending prepare, stored at a fixed owner-derived location and independently hashed. `base_database_sha256` is the digest of the live pre-restore DB, distinct from `checkpoint_sha256` and `source_sha256`. The authority digest is over a fixed canonical projection of device and grant rows, including device public-key bytes, revoked flags, scopes and grant generations; there is no separate key table in the current store schema.

The authority projection has its own fixed byte encoding: domain bytes `MortimerPhoneAuthorityCheckpoint\0v1\0`; then a big-endian uint32 device-row count and device rows sorted by bytewise UTF-8 `device_id`; then a big-endian uint32 grant-row count and grant rows sorted by bytewise UTF-8 `grant_id`. Each record starts with a one-byte table tag (`0x01` device, `0x02` grant). Each text/blob value is a big-endian uint32 length followed by exact bytes; nullable `revoked_at` is marker `0x00`, otherwise marker `0x01` followed by finite nonnegative IEEE-754 binary64 big-endian seconds. Device field order is `device_id,owner_id,public_key,key_algorithm,revoked_at`; grant field order is `grant_id,device_id,owner_id,scopes,grant_generation,revoked_at`. `scopes` is parsed as a duplicate-free array of the exact allowed strings, sorted by UTF-8 bytes and encoded as compact UTF-8 JSON; malformed or noncanonical stored scopes block. `grant_generation` is exact nonnegative SQLite signed-64 range encoded as uint64 big-endian. Host ID/generation and transition state are separately checked against `phone_remote_meta` and the protected anchor; protected login counter is separately bound by the anchor. `authority_sha256` is SHA-256 over the complete described byte stream, including zero counts, so empty authority is unambiguous.

**Protected anchor v1:** exactly the existing six keys `{anchor_version,host_id,host_generation,transition_id,transition_state,login_counter}` and existing codec semantics. **Protected anchor v2:** exactly those six plus `pending_restore` and `last_completed_restore`. In v2, ordinary authority transitions use the existing stable/pending semantics and ordinary transition IDs (including existing `login:<hex>` and `<label>:<hex>` values) with `pending_restore:null`; they preserve `last_completed_restore` exactly. A restore-pending v2 record alone has non-null `pending_restore` exactly `{operation_id,target_generation,manifest_sha256,checkpoint_sha256}`, with canonical operation UUID equal to `transition_id` and target equal to `host_generation`. Thus ordinary pending is not misclassified as restore pending. Stable v2 has null transition ID/state stable and `pending_restore:null`, and always requires a non-null `last_completed_restore` exactly `{operation_id,target_generation,manifest_sha256,checkpoint_sha256,database_sha256}`. In restore-pending v2 only, `last_completed_restore` may be null if no recovery has ever completed; a stable v2 anchor with null tombstone is invalid. The prior completion object is preserved in restore-pending state and across ordinary login/signout/revoke/generation mutations. Protected `login_counter` is the only stored counter; `phone_remote_meta` has no login-counter column. Keep it unchanged while setting restored DB host generation to target `G+1`; future login reserves the next protected value using existing semantics. All IDs/digests/bounds follow the manifest rules. V2 protected encoding is canonical and rejects extra/missing/duplicate keys; v1 encoding remains unchanged. `PhoneRemoteAuthorityKeychainAnchorTests.swift` must test v1 compatibility and exact v2 encoding/decoding, duplicate keys, ordinary-pending versus restore-pending discriminants, tombstone preservation and boundary failures using injected storage only.

**SQLite store schema v2:** explicit transaction, not implicit startup migration. Its `phone_remote_meta.schema_version` is exactly 2 after migration. The only schema migration is creation of the receipt table below and setting that schema marker inside the same pending transaction; application database schema and migration rows remain catalog-validated and are not implicitly advanced. It preserves the existing `phone_remote_meta` shape `{singleton_id,schema_version,host_id,host_generation,transition_id,transition_state}`; there is no DB login-counter column. Stable means transition ID null/state stable; pending means operation UUID/state pending. It adds one singleton `phone_remote_restore_receipt` with exact DDL `CREATE TABLE phone_remote_restore_receipt(singleton_id INTEGER PRIMARY KEY CHECK(singleton_id=1),operation_id TEXT NOT NULL,host_id TEXT NOT NULL CHECK(length(host_id)>0),target_generation INTEGER NOT NULL CHECK(target_generation>0),manifest_sha256 TEXT NOT NULL CHECK(length(manifest_sha256)=64),checkpoint_sha256 TEXT NOT NULL CHECK(length(checkpoint_sha256)=64),authority_sha256 TEXT NOT NULL CHECK(length(authority_sha256)=64),receipt_version INTEGER NOT NULL CHECK(receipt_version=1))`; canonical UUID and lowercase-hex validation is additionally enforced by the strict store codec. One latest receipt is retained. The exact receipt comparison map is: receipt `operation_id`, `target_generation`, `manifest_sha256` and `checkpoint_sha256` equal the corresponding tombstone fields; receipt `host_id` equals the enclosing protected anchor host; `receipt_version` is constant 1; and `authority_sha256` comes from a retained canonical manifest whose exact bytes hash to the tombstone manifest digest and whose operation, target, host and checkpoint fields match. Tombstone `database_sha256` is absent from the DB receipt and is never compared to current DB bytes after normal service mutations. Retain the referenced manifest as read-only completion evidence until a later tombstone supersedes it; it is not a cleanup artifact. The prior receipt stays unchanged through checkpointing, pending metadata and file replacement, and is replaced only in the new completion transaction. Before the DB completion transaction, a pending anchor preserves `last_completed_restore`, and the DB receipt must equal that prior tombstone (or both are absent before the first recovery). After the DB completion transaction but before stable-anchor write, the pending anchor's `pending_restore` identifies the operation and the DB receipt must instead equal that operation through its retained manifest; the older `last_completed_restore` remains preserved in the pending anchor but is not compared to the now-new DB row. Stable anchor-v2 is written only after the new receipt and final digest verify; then its `last_completed_restore` and DB receipt must match. Device/grant rows come only from the bound checkpoint, never from the restore source. Copy device IDs/owners/public keys/key-algorithm labels and grant IDs/device/owner/scopes/grant generations/revocation values exactly; set only `phone_remote_meta.host_generation` to target `G+1`, transition ID/op to pending, and later stable/null. Protected login counter remains in the anchor and is held at its checkpoint value throughout recovery. Sessions are exceptional: do not import any source or checkpoint session as active; clear the session table in the pending transition and again in final reconciliation, and fence process-local tickets, challenges, service receipts, peers, leases and queued output. If any authority row is missing or conflicting, refuse rather than merge. The final DB transaction sets meta stable/null transition and writes the exact receipt. Ordinary auth transitions preserve that receipt. Stable protected-v1/store-v1 startup before the first recovery requires no receipt; stable protected-v2/store-v2 startup requires its non-null tombstone and matching receipt. Receipt target generation must match the tombstone target and may be lower than current host generation after later ordinary security transitions. Cross-version pairs, or any v2 tombstone/receipt mismatch, refuse.

The DB receipt deliberately does not contain its own whole-file digest. After the final DB transaction, close every handle, require successful WAL checkpoint with zero busy frames, set DELETE journal mode, close, fsync DB and directory, require no live WAL/SHM sidecars, hash exact final main DB bytes, reopen read-only, and verify integrity/schema/meta/receipt without writes. The recovery journal durably records this digest in `database_finalized`; then, and only then, the owner writes/reads back stable anchor-v2 with the same completion-time digest. The digest first becomes protected authority evidence in `last_completed_restore.database_sha256` on that stable anchor write. This avoids a self-referential hash. If the process stops after the DB receipt transaction but before the digest is journaled, restart verifies the receipt and current DB, repeats only close/checkpoint/fsync/hash/read-only verification, and does not repeat authority reconciliation or the receipt transaction. If a journaled digest exists, recompute and require equality before writing the anchor. Normal service later changes DB bytes, so subsequent startup compares tombstone with durable receipt fields and current stable host/generation, not with the historical file digest. That hash is evidence of bytes at the commit boundary only; it is not ongoing integrity or anti-rollback protection.

**Mutable transaction journal v1:** canonical duplicate-free JSON, max 65,536 bytes, exact keys `{journal_version,operation_id,manifest_sha256,phase,rename_step,files,staged_database_sha256,installed_database_sha256,final_database_sha256,cleanup_artifacts}`. Phases are ordered `checkpoint_bound`, `staged`, `quiesced`, `installing`, `installed`, `database_committed`, `database_finalized`, `anchor_committed`, `cleaning`, `complete`; `checkpoint_bound` means only that the immutable checkpoint/manifest and journal are durable, not that the protected anchor is pending. The separate protected anchor/DB state is exactly stable or pending and binds the operation as described above. Inspect returns exactly the journal phase enum and DB state `base`, `pending`, or `committed`. Hash fields are lowercase SHA-256 or null; `final_database_sha256` remains null until database finalization succeeds. `rename_step` is null or exact `{name,action,expected_sha256,state}`; name is `wal`, `shm`, `database`, or `staged_database`; action is `move_to_quarantine` or `install`; state is `intent` or `done`. `files` has exactly database/wal/shm, each `{present,size_bytes,sha256}`; absent means size 0/hash null. When WAL or SHM was absent at quiescence, the ordered step is recorded as `move_to_quarantine`, `expected_sha256:null`, `state:done` only after confirming both fixed paths are absent; no rename is issued. `cleanup_artifacts` has exactly `checkpoint`, `staged_database`, `old_database`, `old_wal`, and `old_shm`; each value is `{state,sha256}`, where state is `absent`, `pending`, `intent`, or `done`, and `absent` has null digest. The journal temporary is not a cleanup artifact and must not survive into later restore phases. Before each journal update, `journal.next.tmp` must be absent. If it remains after an interrupted write, it is never authoritative: validate the fixed directory, regular-file type, owner, mode, size bound and current canonical same-operation `journal.json`; unlink only that validated temp and fsync the directory before a new exclusive creation. If the canonical journal is missing/invalid or identities disagree, retain the hold. The anchor binds the immutable manifest/checkpoint, not this mutable journal digest. Journal phases and cleanup entries are checked against actual file identities; any ambiguity fails closed. Journal/checkpoint paths are fixed owner-derived locations in a protected authority directory, never supplied by the caller. At most one recovery may be pending. Keep checkpoint, stage and quarantined files through DB/anchor completion and recovery-child exit. With no child alive and singleton lock held, clean only the listed recovery-owned files: before each unlink durably record `intent`; unlink; fsync both source and destination directories for any cross-directory rename, and fsync the containing directory for deletion; record `done` in the journal and fsync its directory. For cross-directory rename, fsync both affected parent directories after the rename before recording `done`. If a crash follows unlink before `done`, absent-at-exact-fixed-path plus matching operation, `intent`, and committed anchor/receipt proves that one cleanup item is done; update the journal and continue. Present with exact digest permits the unlink to resume; unexpected identity or any source/catalog path in the cleanup set blocks. Journal and receipt tombstone are not cleanup artifacts. Mark `complete` only after all five entries are `absent` or `done` and directory fsyncs succeed. Cleanup is performed before starting the normal child; if incomplete, retain the lock and pending service fence and retry cleanup only, never repeat DB reconciliation or file replacement. No later restore begins until cleanup and normal-child readiness succeed. Preflight reserves enough free space for checkpoint, staged DB, quarantined DB/sidecars and journal before entering pending; each source/checkpoint/database is capped at 1 GiB.

### File replacement, commit order, and crash table

Fixed same-filesystem paths only: live `jarvis.db`, `jarvis.db-wal`, `jarvis.db-shm`; candidate `.phone-restore/<operation_uuid>/staged.db`; quarantined old files `.phone-restore/<operation_uuid>/old.db`, `old.wal`, `old.shm`; mutable journal `.phone-restore/<operation_uuid>/journal.json` and exclusive temporary `.phone-restore/<operation_uuid>/journal.next.tmp`. After every writer is stopped/reaped, checkpoint WAL and require zero busy frames, switch to DELETE journal mode, close all DB handles, verify live WAL/SHM absent, fsync the live DB and parent directory, and only then hash the normalized live main DB as `base_database_sha256`. The SQLite backup API creates a separate immutable checkpoint, hashed as `checkpoint_sha256`; do not assume its bytes/hash equal the live-main digest. Their logical authority projection and relevant metadata must match. Staged DB is standalone DELETE journal mode. For a journal update, require `journal.next.tmp` absent, create it using `O_CREAT|O_EXCL|O_NOFOLLOW` mode 0600, write the complete bounded canonical journal, fsync the file, atomically rename it over `journal.json`, then fsync the containing directory. The rename consumes the temporary. If interrupted before rename and the temp remains, validate the canonical journal and exact fixed-path temporary; unlink the temporary and fsync the directory before another update. Missing/invalid canonical journal means hold. If power fails after rename but before directory fsync, inspect the actual canonical journal and file identities; never infer phase from a temporary. Test partial temp creation, complete temp before rename, rename before directory fsync, and interrupted reclamation. For each DB move, durably record `intent`, perform one same-filesystem atomic rename, fsync both source/destination parent directories (once if identical), verify destination digest, then record `done`. Quarantine WAL, SHM, database in fixed order; install staged DB only after old live files are quarantined and verified. Install is `staged.db` to `jarvis.db`. Source expected plus target absent permits only that exact rename; source absent plus target exact permits recording done; both, neither or unexpected digest retains pending for operator recovery. Existence alone never proves success. Old files/checkpoint remain until completion; no automatic rollback or cleanup guess. Fsync checkpoint/stage before journal references and fsync every created directory entry.

| Interruption | Restart evidence | Allowed action |
|---|---|---|
| Before quiescence | Exact stable anchor/store pair | A verified caller/source denial leaves bytes unchanged; a later authorized attempt may begin |
| After WAL normalization, before checkpoint | Stable logical anchor/store pair, normalized live DB, WAL/SHM absent; checkpoint may not exist | Revalidate logical authority and schema, then create a new checkpoint; do not claim original live bytes were preserved |
| Checkpoint/journal durable, anchor still stable v1/v2 | Exact stable logical pair and normalized live hash equals `base_database_sha256`; checkpoint image separately matches `checkpoint_sha256` | Treat this operation as uncommitted; normal start may proceed after validation. A new operation must revalidate and create a new manifest/checkpoint |
| Anchor pending write/readback fails or is uncertain before a verified pending read | Re-read protected bytes under the same owner lock; do not assume either stable or pending | No prepared acknowledgment or DB pending mutation has been issued. If exact stable anchor plus exact normalized `base_database_sha256` are verified and no replacement occurred, stop/reap the prepare child and normal startup may proceed through activation. If the exact bound pending anchor is present, start `prepare_resume` to distinguish exact base from already committed pending; otherwise retain hold |
| Anchor pending-v2 verified, before DB pending transaction | Exact pending anchor binds operation/manifest/checkpoint; normalized live DB hash equals `base_database_sha256`; checkpoint independently matches `checkpoint_sha256` | Start `prepare_resume`, not fresh `prepare`; verify the bound manifest and base DB, then issue the same-operation pending transaction once. Hold lock and service fence |
| DB pending transaction acknowledgment lost | Read-only inspection reports either exact base or matching pending meta under the same operation | Matching pending is already committed: do not repeat mutation. Exact base permits retrying that same idempotent transaction only. Any third state is uncertain: retain hold, no service |
| Service fence or prepare-child shutdown/reap acknowledgment lost | Owner-held lock; child process state and exact anchor/DB phase inspected | No prepared receipt and no normal child. Reap only the owner-created child; resume the same operation after confirmed child exit and state verification |
| Prepared receipt delivery lost after verified prepare and child reap | Pending anchor, matching DB pending state, owner still holds singleton | Same-operation retry returns pending status with a fresh correlation and the same live incarnations if the owner remains alive; if a child actually exited, a new child gets a new incarnation. No additional authority mutation occurs; another operation is rejected |
| Anchor pending-v2, DB still exact base | Protected manifest/checkpoint matches and normalized live-main hash equals `base_database_sha256`; `checkpoint_sha256` separately verifies the immutable backup image | `prepare_resume` validates the exact base and may commit pending once; it does not require a stable-pair preflight; normal start denied |
| Anchor pending-v2, DB schema-v1 stable base | Normalized live-main hash equals `base_database_sha256`; schema/host and logical authority match the bound checkpoint; checkpoint bytes separately match `checkpoint_sha256` | `prepare_resume` validates this exact base, then applies only the reviewed v1→v2 migration and same-op pending transaction; normal start denied |
| `commit_pending` acknowledgment lost | Protected pending plus DB inspection returns exact base or matching pending metadata | `prepare_resume` returns `base` and retries the same transaction once, or returns `pending` and skips mutation; any third state blocks |
| Anchor pending-v2, DB pending matching op | Anchor/manifest/checkpoint and journal match | Skip pending mutation and continue the same operation in `recover` only |
| Stage exists before any live rename | Exact source/stage hashes | Reverify or recreate stage for same operation |
| Rename intent durable, rename not run | Exact expected source present and target absent | Repeat the exact rename, then fsync directory and record `done` |
| Rename ran but `done` missing | Exact target present and source absent | Verify target digest, fsync directory and record `done`; never repeat rename |
| DB/WAL/SHM set partial or ambiguous | No unique journal-matching placement | No service, cleanup or new operation; retain hold for operator recovery |
| Installed DB verified, meta/receipt still pending | Installed hash/schema/reconciliation match | Commit stable meta plus receipt once |
| DB stable+receipt transaction committed, journal not yet `database_committed` | DB contains the exact new operation receipt and stable target metadata; pending anchor still binds operation | Do not rerun reconciliation or DB transaction. Record `database_committed`, then perform only final close/checkpoint/fsync/hash/read-only verification |
| DB transaction committed; checkpoint/close/WAL checkpoint/journal-mode/fsync/read-only verification interrupted | Pending anchor, stable DB receipt, actual SQLite files and current journal evidence | No replacement or authority transaction. Reopen only under the held recovery owner, finish the idempotent finalization sequence, reject busy frames/unexpected sidecars, and compute the digest again |
| Final DB digest recorded in journal, protected anchor still pending | Recomputed main-file digest equals `final_database_sha256`; DB receipt/meta match same operation | Write/read back stable anchor-v2 with that digest; if the digest differs, retain hold and refuse |
| DB stable+receipt committed, anchor still pending-v2 | Receipt and completion digest match same bound operation | Write/readback stable tombstone; do not replace files again |
| Anchor final write/readback uncertain | Inspect exact anchor, DB receipt and journal | Exact stable tombstone match means committed; exact bound pending means retry only that stable write; otherwise block |
| Stable tombstone written/readback uncertain before cleanup | Exact anchor tombstone, matching DB receipt and `database_finalized` journal; singleton still held | If all match, record `anchor_committed` and start/continue exact cleanup; never replace again. If not, retain hold and block |
| Cleanup interrupted after unlink but before journal `done` | Stable tombstone/receipt, cleanup intent and exact fixed path absent | Record that cleanup item done and continue; unexpected present digest/path blocks. No normal child yet |
| Cleanup incomplete or journal `complete` write uncertain | Stable tombstone/receipt, exact cleanup entries and journal | Retry only cleanup reconciliation/journal fsync under the same owner lock. Do not launch normal child or return completed |
| Cleanup complete, before normal service readiness | Stable tombstone/receipt, durable `complete` journal, no recovery artifacts | Start/retry normal child; `child.ready` alone is insufficient. Require store.open release, full receipt/tombstone comparison and activation before admission |
| Child healthy but controller acknowledgment lost | Stable pair, durable cleanup `complete`, child remains healthy, lock held | Same-operation retry returns the same completion receipt with a fresh request correlation but the same live owner/child incarnations; it does not restart the child or replace files |
| Stable anchor/receipt mismatch, or stable anchor with pending DB | Contradictory/unreachable ordering state | Refuse service; operator recovery only |

Ordering is fixed: source validation and caller denial before mutation; close normal admission, drain and reap normal child under retained singleton; verify stable logical pair; checkpoint WAL with zero busy frames, switch to DELETE mode, close handles, verify no sidecars, fsync and hash normalized live main DB as `base_database_sha256`; create/fsync independent SQLite backup checkpoint and hash as `checkpoint_sha256`; compare logical authority projection without equating byte hashes; fsync manifest and initial journal; start `prepare` and preflight. On verified fresh denial, shutdown/reap, revalidate stable pair and base live hash, then start normal mode and require store.open release, receipt comparison using the exact field map below and activation before returning denial. On success keep `prepare` alive, write/read back protected pending anchor, commit DB pending, fence sessions, shutdown/reap, and hold. Recovery starts `prepare_resume` if DB is exact base or matching pending: it never requires a stable pair, and skips a matching pending mutation. Then `recover` inspects, stages, verifies and journals each file move, fsyncing both directories. Reconcile installed DB and commit stable metadata/receipt once; close/checkpoint/DELETE/close/fsync, verify no sidecars, hash final main DB, reopen read-only for integrity/schema/receipt checks, shutdown/reap recovery child, independently rehash and persist `database_finalized`, then write/read back protected stable-v2 tombstone. Persist `anchor_committed`; remove the five listed artifacts with durable intent/unlink/fsync/done; persist `complete`. Start normal child only after cleanup: hello/transport ready, store.open grant and release acknowledgment, schema and full tombstone/receipt comparison, child.service.ready, owner field comparison and activation, child.service.activated; only then acknowledge completion. A pre-first-recovery v1/store-v1 pair uses the same activation barrier but requires no receipt. Journal update uses consumed O_EXCL `journal.next.tmp`; validated orphan temp is reclaimed and directory-synced before a later write and is not a cleanup artifact. DB and protected anchor are not one atomic store: DB stable+receipt commits before anchor, so restart can only resume same-operation finalization. Once stable tombstone is written, do not replace files or rewrite DB. Cleanup/activation failure retains owner lock and withholds completion; retries only finish cleanup/startup, never repeat reconciliation/replacement. Same-operation retry uses fresh correlation, preserves live incarnations unless a process restarts, and has zero replacement effects. Whole-host restoration of DB and anchor together remains undetectable.

### Restore-class limits, ownership, and acceptance

`scripts/backup_db.py` currently creates WAL-safe backups of `data/jarvis.db` and `data/costs.db` with SQLite `Connection.backup` and `quick_check`; it is not a restore protocol or authority manifest. `scripts/deploy_main.sh --restore-local` currently restores costs/vault, not `jarvis.db`, and has no authenticated owner hook. The generated legacy rollback argument guard does not make old already-generated artifacts safe. This proposal changes none of those paths. WS-04 owns owner/anchor/channel/store/recovery child/service fence; WS-17 retains every backup/restore/deploy entrypoint and artifact inventory; WS-30 gains no restore authority. The adopted offline WS-04 source paths are `macos/MortimerHost/Sources/PhoneRemoteAuthority/PhoneRemoteAuthorityOwner.swift`, `macos/MortimerHost/Sources/PhoneRemoteAuthority/PhoneRemoteAuthorityKeychainAnchor.swift`, `jarvis/bot/phone_remote_authority_channel.py`, `jarvis/bot/phone_admission_store.py`, new `jarvis/bot/phone_remote_recovery.py`, `jarvis/bot/phone_remote_service.py`, and tests `macos/MortimerHost/Tests/PhoneRemoteAuthorityTests/PhoneRemoteAuthorityKeychainAnchorTests.swift`, `macos/MortimerHost/Tests/PhoneRemoteAuthorityTests/PhoneRemoteAuthorityProcessTests.swift`, `tests/unit/test_phone_admission_store.py`, `tests/unit/test_phone_remote_authority_channel.py`, `tests/unit/test_phone_remote_authority_service.py`, new `tests/unit/test_phone_remote_recovery.py`. This exact twelve-path claim is adopted; independent exact-source review is required before integration. WS-17 invocation is separate; candidate integration paths are `scripts/deploy_main.sh` and `tests/unit/test_deploy_main.py`, only after the authenticated owner caller contract is designed. Every supported database restore and normal checkout/build rollback must invoke the gate before replacing code/data or remain explicitly unsupported; old generated artifacts are not retroactively covered. `scripts/backup_db.py`, frozen fixtures, old installed/generated artifacts and production service construction are not included. No source acceptance, production readiness or live restore authorization is implied.

Offline acceptance uses injected authorization, fake protected storage, disposable SQLite/files, actual owner/child processes and fake service commands.

Additional deterministic design regressions are mandatory: a crash after verified pending-anchor write but before DB commit resumes through `prepare_resume` against exact normalized base; verify first-recovery quiescence without a tombstone, a later recovery operation ID differing from the previous tombstone, and that a completed retry sends no quiescence request; queue an `_AuthorityChildServiceHost._submit` item with no authorization/receipt and prove local bounded rejection/cancellation with zero authority IPC; cancel once before authorization and once after authorization, proving queue removal in the first case and continued operation ownership without claimed rollback in the second; pause an accepted request after `service.authorize` and before its `service.commit` grant, begin quiescence, assert a new logical operation is rejected while the already authorized `service.commit` continuation for the frozen operation remains admissible, then prove that operation reaches its defined terminal outcome before `drained:true`, shutdown/reap, checkpoint or recovery mutation; assert no grant is issued outside the frozen set, and that an accepted request unable to finish prevents drain acknowledgment; use a monotonic fake clock to reach the fixed five-second drain deadline during a stalled continuation; inject lost commit/release/shutdown acknowledgments and prove immediate terminal handling when observed; assert callers settle no later than the drain deadline, dispatch stops, TERM/KILL/reap use the 250-ms/2-second monotonic bounds and affect only the owned child (or retain the lock and unavailable state if unreaped), actual state is inspected, and no recovery mutation or false `drained:true` occurs; require `drained:true` only after accepted work/output/resource cleanup, and show a lost quiescence acknowledgment causes no recovery-induced anchor/DB mutation while the owned child is reaped and the lock retained; account separately for already completed normal operations drained before the acknowledgment. Test exact receipt mapping independently at startup, completed retry and both sides of the new completion transaction, including retained-manifest hash/authority binding and the rule that historical `database_sha256` is never compared to the normally mutated current DB. Exercise v4 normal login, challenge, `service.authorize` and `service.commit` through exact existing channel/service version/type guards; reject wrong-version/type frames and prove v1/v2/v3 fixtures remain byte-compatible. Adding a new owner mode without updating those existing guards must fail these tests; lost commit acknowledgment with matching pending DB skips mutation, while any third DB state remains held. Build the source catalog from the actual pinned DDL and assert exactly `sqlite_autoindex_phone_remote_devices_1`, `_2`, `sqlite_autoindex_phone_remote_grants_1`, `_2`, and `sqlite_autoindex_phone_remote_sessions_1`, `_2` with SQL NULL using the tagged nullable-field encoding. Force journal temp creation/write/rename/directory-sync/reclamation interruption at each boundary and prove no next update reuses a present temp. For normal startup, prove `child.ready` alone never opens admission; reject v2 schema/receipt/tombstone mismatch and lost store.open release acknowledgment; accept only after the full child-service-ready/owner-activate/child-activated sequence, including the pre-first-recovery v1/store-v1 no-receipt case. Exercise WAL normalization before `base_database_sha256`, assert checkpoint and live-file hashes are independently checked rather than assumed equal, and verify pre-quiescence policy denial leaves bytes untouched while post-normalization technical failure does not claim byte identity. These are proposed test requirements, not tests already run. Cover v1/v2 anchor codec compatibility; legacy v1-pending refusal; checkpoint/manifest binding before pending; restart verification independent of restored bytes; preservation of current device/grant/revocation state and fencing every restored session/process artifact; wrong host/schema/generation/UUID/manifest/hash; corrupt DB/foreign keys; symlink/owner/mode/size bounds; WAL/SHM; each rename-before/after-journal boundary; every table row; DB-stable-before-anchor combinations; receipt survival across login/revoke; exact retry with fresh request correlation, unchanged live incarnations, and zero replacement effects; after actual restart, new incarnations still match the same operation; wrong/older ID no-op; lost ack; normal-child health retry while lock held; owner/child death and surviving-child lock exclusion; preflight denial before pending; injected denial after pending that proves no ordinary release, stable rollback or hold release; and ordinary login/signout/revoke/ticket/service-denial regressions over the v3 six-field projection while protected-v2 tombstone bytes remain preserved. Never run deployment, `launchctl`, old scripts, actual restore, real Keychain, signing, enrollment, listener or live service.


### R3.24 review clarification: queued work, cancellation, and bounded drain failure

This paragraph restates the queue/cancellation/deadline behavior already present in the independently accepted R3.24 design `e7eb2176f54f5c004be2bd16e159ce905080699a`; it adds no invariant or acceptance gate. The R3.24 source branch has partial, unreviewed WIP checkpoint `c44e852e25a45087a8e2646a07e5f5b0aa55029c` (tree `bcc4c64cb5fbed14b902ab704de9f824e7c7774d`); it is incomplete and unpublished. The design remains offline and does not authorize a restore.

### R3.24 implementation checkpoint (2026-10-31)

Local WIP source checkpoint `c44e852e25a45087a8e2646a07e5f5b0aa55029c` (tree `bcc4c64cb5fbed14b902ab704de9f824e7c7774d`) on `codex/ws04-ws17-d3-recovery-20261031` contains eight changed paths within the adopted twelve-path claim. It adds bounded manifest/receipt/journal helpers, private-file checks, SQLite live-DB normalization and backup checkpoint helpers, protected-anchor-v2 parsing, and v4 normal-operation compatibility over the existing six-field projection. A real controlled-process test exercises v4 login, challenge read, service authorization and service commit while checking that login-counter advancement preserves the protected-v2 restore tombstone. These are partial primitives, not an executable restore path.

Validation on this checkpoint: nine focused phone modules passed 238 tests and 154 subtests with zero skips; the focused Swift authority suite passed 24 tests with zero failures; the `PhoneRemoteAuthorityOwner` product build passed; `git diff --check` passed; and `scripts/check_roadmap.py --main 5310d1a9305035f43143fcffad6161619281f475` reported 0 errors and 0 warnings. The normal SwiftPM sandbox initially failed to access the user's clang module cache; rerunning through the already authorized focused test workflow with module caches redirected to an isolated temporary directory succeeded. No full repository test suite was run.

The remaining adopted implementation is substantial: source-catalog validation for the pinned application migrations, a complete v4 recovery protocol/owner state machine, normal-child drain integration, schema-v2 receipt/store validation, staging and journaled DB/WAL/SHM replacement, durable cleanup/retry handling, and the accepted crash/uncertainty matrix are not complete. No real Keychain, controller, signing, installation, source-content bridge, database restore, deployment script, live service or publication work occurred. This WIP checkpoint is not independently reviewed or accepted; the recovery remains unsupported and must not be described as complete.

At quiescence start, the owner freezes the set of already-authorized logical operation IDs and closes admission for new IDs. An `_AuthorityChildServiceHost._submit` item that is queued but has not completed `service.authorize` and has no matching durable/in-memory receipt is outside that frozen set: remove it from the local queue, settle its caller with the typed local `quiescing`/cancellation outcome, and perform zero authority IPC, receipt creation, or service effect. A caller cancelled before authorization receives the same local outcome and its queued item is removed. Once authorization has completed, caller cancellation may settle that caller locally as cancelled, but it does not cancel or forget the accepted operation: the operation remains owned in the frozen set through its existing `service.commit` continuation and terminal output/completion bookkeeping. Do not claim that cancellation undoes an already dispatched effect. The only continuation authority allowed during drain is the remaining exchange for an operation ID frozen at quiescence; no new authorization, unrelated commit, or later request may extend the set.

The owner establishes one monotonic deadline exactly five seconds after quiescence begins and never resets it. Before the deadline, every accepted operation must reach its defined terminal outcome and release its grant; only then may the owner stop grants and begin the `restore_quiesce` shutdown exchange. The child may report `drained:true` only in its post-shutdown acknowledgment. If an accepted continuation is still stalled at the deadline, stop dispatch and further grants, settle every waiter by the deadline with terminal `authority_unavailable`/uncertain completion, and do not represent the work as undone or drained. `drained:true` is legal only in the child's `child.shutdown_ack`, after it receives the owner's `owner.shutdown` and verifies the frozen work set is terminal; it is not an owner pre-shutdown report. A commit, release, or shutdown acknowledgment that is malformed or lost becomes terminal as soon as that failure is observed; do not wait out the remainder of the drain interval or send a compensating mutation. No checkpoint, pending-anchor write, pending-DB transaction, replacement, or prepared receipt may follow a drain failure. A later normal-child start is not automatic: only after the owned child is confirmed reaped and the owner inspects actual protected-anchor/DB bytes under the retained lock may the ordinary startup validator run; admission requires that exact supported stable pair and the full normal activation protocol, otherwise the owner remains unavailable.

Terminal cleanup affects only the child created by this owner. Close its channel, send TERM, wait at most 250 ms against the same monotonic clock, then send KILL if required and wait at most two seconds for that exact child to be reaped. Keep the singleton lock throughout. If reap is not confirmed, remain unavailable with the lock held and do not inspect/recover through a second child. After confirmed reap, inspect actual anchor and database state under the lock; never infer that in-flight SQLite work was rolled back. A lost child `drained:true`/shutdown acknowledgment likewise yields no recovery mutation; the child is reaped and state inspected, with the lock retained. These bounds govern caller settlement, child cleanup, and admission separately; a caller timeout is not evidence of operation rollback.

Required deterministic regressions are: (a) enqueue an unauthenticated `_submit` item, begin quiescence, then prove local bounded settlement, queue removal, zero owner-channel frames and zero receipt/service effect; (b) cancellation before authorization removes the queued item and sends no frame; (c) cancellation after authorization promptly settles the caller but retains the frozen operation until its exact commit continuation completes; (d) stall that continuation under a fake monotonic clock, advance to five seconds, and prove all waiters settle, no later grant/dispatch occurs, no false drain or recovery mutation is emitted, and TERM/KILL/reap stays within bounds while the lock remains held; (e) inject lost commit, release, and shutdown acknowledgments and assert terminal settlement on observation, no compensating/recovery writes, owned-child cleanup and retained lock. Include positive evidence that an already-authorized operation may finish its exact commit continuation while new logical operations remain rejected. Existing v1/v2/v3 frame fixtures and normal service behavior remain byte-compatible.

`_check_pair` does not detect every same-generation older DB image. SQLite-only restoration may be detected by a generation/transition mismatch, but universal detection is not claimed. Restoring both DB and Keychain anchor together is not detectable without independent trusted state; whole-host rollback stays unsupported unless such state is separately designed. Hashes, readback, `ThisDeviceOnly`, file permissions and a local journal are not anti-rollback. No blanket revoke/re-pair policy is introduced: preserve only authority proven current by the bound checkpoint; otherwise refuse. Production controller authentication, signing/entitlements, real Keychain behavior, supported archive inventory/invocation, ordinary app-checkout rollback, and whole-host rollback handling remain open. This design records no completed implementation and does not authorize a live restore.

### R3.24 replacement implementation — 2026-10-31 (WIP; scope amendment pending)

Codex continued from immutable helper WIP `d1b616b92fb52b5597cb1b54eb8eedd605b178ce`
(tree `d0979c80ff1bc78d80faacbd7a9b4bbbda34397f`) in the authorized Mac checkout
on branch
`codex/ws04-ws17-d3-recovery-20261031`. Existing commits are preserved. This is
unfinished source, not acceptance or a complete review candidate.

The replacement WIP connects the closed recovery sequencer to the inherited
v4 channel and fixed-path SQLite executor; adds native-owner checkpoint,
pending-anchor, prepare/resume/recover child, database finalization, stable
anchor, cleanup and normal-child activation sequencing; and replaces the old
v4 cross-version fixture's false success assertion with fail-closed behavior.
The normal child now requires exact protected/store versions, retained manifest
and receipt mapping, cleanup completion, and the explicit activation exchange.
The owner keeps the singleton descriptor through child replacement and bounded
owned-child reaping. A local service-host quiescence/cancellation barrier is
present but is not accepted or fully process-validated.

The independent helper findings were addressed: explicit `BEGIN IMMEDIATE`
covers DDL, metadata, session clearing and receipt writes in both SQLite
isolation modes; the sequencer permits repeated inspection and phase-driven
crash continuation; illegal/reentrant/uncertain calls latch terminal failure;
and verified hashes plus exact integer types are checked before mutation.
New statement-failure, reentrancy, hash/type and crash-sequencing regressions
exercise those cases.

**New concrete scope blocker:** `PhoneRemoteLogin.__init__` in
`jarvis/bot/phone_remote_login.py` line 204 accepts only exact
`NativeProtectedAnchorV3`. The required full v4 `_AuthorityChildServiceHost`
therefore fails startup with `unsupported offline login dependencies`. That
module is outside the adopted twelve paths. No type spoofing, monkeypatch,
legacy-channel fallback, or omission of proof login is an acceptable fix.
A narrow amendment for that module and its existing login tests was requested;
no response or amendment is assumed, and neither file has been edited.
The prior store-only native-process recovery smoke is not full-service proof.

Validation of this WIP before the scope amendment:

- Existing v1/v2/v3 phone regression batch: 195 tests and 263 subtests passed
  in the isolated temporary Python environment, using the actual directly compiled native owner.
- Current recovery helper tests: 35 passed, nine subtests passed; the three
  blocked full-service process tests were explicitly deselected for this
  helper-only run, not counted as passes.
- Scoped Swift authority tests: 24 passed, zero failures, using an isolated
  temporary Swift package with symlinks to the actual source/test files,
  SwiftPM sandbox enabled and temporary caches. Direct `xcrun swiftc` also
  compiled the owner. This is not the full MortimerHost/JarvisKit suite.
- Before switching the recovery fixture to the full service host, 37 recovery
  tests/eight subtests passed, including actual native-owner/Python-child
  recovery, same-incarnation completed retry, completed restart, four lost
  mutation-ack restarts, and stable-anchor/cleanup restart. Those results cover
  the store-only child at that earlier working state, not current full-service
  startup or the whole accepted interruption/drain matrix.
- The subsequent current full-service combined run had 75 passes/four passing
  subtests and six failures (two tests plus four subtests) at the scope blocker.
  These failures are retained, not skipped or relabeled as passes.
- The normal package build was stopped while downloading the pinned WebRTC
  artifact; no package/toolchain/security setting was changed. The isolated
  authority package supplied the focused Swift result above.

The accepted design is unchanged. The full drain/durability/crash matrix,
complete controller retry/second-recovery behavior, independent exact-source
review and aggregate validation remain unfinished. No source acceptance,
publication, PR action, merge, real Keychain, live database, app installation,
WS-17 script or controller-model change occurred. `origin` remains the local
handoff clone without `origin/main`; GitHub DNS failed inside the ordinary
sandbox. Current-main reconciliation is still required before integration.

### R3.24 adopted scope extension — 2026-10-31

The coordinator independently verified and adopted adding only
`jarvis/bot/phone_remote_login.py` to the existing twelve source/test paths,
for thirteen effective paths on `codex/ws04-ws17-d3-recovery-20261031`.
Fresh local inspection found that target unchanged and no dirty target edit;
its last change is accepted R3.18 integration `860835238ab5ed3b138703ef738cc2f6982a2218`.
The registered local worktrees remain the prior results/design/refinement
lanes; none is a second recovery implementation. The parent retains the
independent immutable WIP review. This amendment is recorded before editing
that source file and is technical claim adoption, not product or source acceptance.

The new module change is limited to importing V4, annotating the two supported
concrete anchor types, and accepting exactly V3 or V4. All other exact
dependency, store-anchor identity, ownership, signature, expiry, replay and
login-proof checks remain binding. The existing claimed channel must remove
its proofless V4 `store.login` allowance: V4 uses `login_proof` exactly like V3.
Regressions belong in the already claimed authority channel/service test
modules; `test_phone_remote_login.py` is read/run unchanged. No additional
source or test path is added. The full recovery/drain/crash matrix and
independent source review remain open. No live action or publication is authorized.

### R3.24 proof-login and continuation slice — 2026-10-31 (unreviewed)

Implemented the adopted exact V3/V4 login guard amendment and removed V4
proofless login. Actual owner/child proof-success, replay, failed-proof-limit,
expiry and service-authorize/commit assertions pass with v4. New local tests
cover exact dependency/subclass rejection, queue cancellation/removal, retained
authorized ownership, nonextending deadline settlement and failed-resource-close
refusal. Fixed terminal admission publication before caller wakeup. Native v4
shutdown now validates the exact drained acknowledgment while v1/v2/v3 bytes
remain unchanged. Native recovery validates all inspect/stage/install/pending
reply shapes and bindings, supports a fresh second recovery after a tombstone,
and resumes the exact base after a pending-anchor interruption.

Validation: recovery, authority-service and unchanged proof-login modules passed
91 tests and 31 subtests using the directly compiled native executable and
isolated Python environment; the focused log is retained locally. This is
focused evidence, not full acceptance: remaining actual-process drain and
durability/receipt matrices, aggregate checks and independent source review
remain in progress. No public writes, live actions or scope expansion occurred.

### R3.24 offline recovery implementation candidate — 2026-10-31 (independent review pending)

The adopted thirteen-path offline implementation is connected end to end. The
native owner retains singleton supervision through normal v4 activation, a
fixed five-second admission/drain barrier, bounded owned-child TERM/KILL/reap,
checkpointed prepare, prepare-resume, recovery, stable-anchor readback, durable
cleanup and normal-child reactivation. The injected offline controller can
continue the same pending operation in the same owner after uncertain child
completion; other operation IDs and retired completion IDs have no replacement
effects. Completed retries retain healthy process identities, use fresh request
correlations and do not require the old backup source or send quiescence. A
new recovery preserves the previous receipt until its own completion and gets
a fresh owner-generated operation ID. Test-controller mailboxes and teardown
are confined to the disposable fixture; they do not implement production caller
authentication or expose a phone endpoint.

The candidate includes explicit atomic SQLite DDL/data transactions, strict
manifest/receipt and integer bindings, terminal uncertain/reentrant protocol
handling, actual-phase restart, independent native checkpoint verification,
private no-follow file checks, WAL-aware recovery reads, journaled renames and
cleanup, canonical source IDs, and exact v4 proof-login dependency guards.
Native SQLite opens account for macOS system path aliases while retaining
NOFOLLOW on the database. Ordinary v4 proof login, service authorization/commit,
signout and security revocation preserve the protected completion tombstone;
readiness compares receipt/manifest fields rather than the historical live-DB
digest. Legacy unbound pending state remains held without implicit conversion.

Final validation on the candidate source: all thirteen `test_phone*.py` modules
passed **322 tests and 425 subtests**, with no skips, using
the isolated temporary Python interpreter and the directly compiled actual native owner.
The isolated authority Swift package, referencing the real source/test paths
and retaining normal SwiftPM sandboxing, passed **24 tests, zero failures**.
Coverage includes actual happy paths, repeated/lost acknowledgments, same-owner
and replacement-owner continuation, second recovery, source/preflight denial,
rename/commit/finalization/cleanup interruption, partial journal temp recovery,
receipt-field mismatches, activation uncertainty, queued cancellation, frozen
service continuation, fixed-deadline failure, forced KILL/reap, and a surviving
v4 child's inherited singleton exclusion after owner death. Existing proof,
results snapshot/resume, six-case refinement and v1/v2/v3 regressions remain in
the aggregate run. Final Python and Swift logs are retained locally;
the source review manifest records their hashes.

This is a source candidate, not independent source acceptance, production
readiness or live-restore authorization. Full repository pytest and the full
MortimerHost application package were not run in this slice; the earlier full
package attempt stopped during its pinned WebRTC artifact download. The scoped
Swift result is not represented as a full application build. Current-main
reconciliation and independent exact-source review remain integration gates.
The parent reports published WS05-only PR290 head
`39208d18d8c6fde0a9a0539e4d7c3aa68de5610f`, tree
`e31cdf9531908b0186d71d7af573da877e7b7eec`, parent `46e29c`; the cumulative
local branch already includes equivalent WS05 work through `4e2152`, so no
reset/rebase was performed. The parent owns CI544 and later reconciliation.
No public writes, PR approval, merge, live database, real Keychain, app install,
signing, controller-model change, WS17 script edit or production action occurred.

### R3.24 independent-review corrections — 2026-10-31

Addressed both findings against `7dc80e0093a0921f8c110e898180d8576bdb2d74`.
Cancellation is checked before queue insertion, retained on the owned request,
and observed by the worker before dispatch and at the authority boundary. The
worker also observes cancellation before publishing a successful terminal
result. Authorized work retains ownership and finishes its continuation; no
rollback is inferred. The deterministic fast-worker regression prevents the
caller cancellation poll from running until the worker settles and exercises
pre-submit, queued, pre-authorization and post-authorization cancellation plus
an uncancelled control. Running this regression against the original candidate
fails all four cancellation cases, while the corrected source passes. The
pending-anchor validator now checks the nested target generation's exact integer
type before dictionary comparison; floats, booleans and strings are rejected.

Validation: all thirteen phone modules pass **323 tests and 434 subtests**, zero
skips, with Python warnings treated as errors and the pytest-asyncio function
fixture-loop scope explicitly configured. A fresh native build using only
permitted temporary module caches succeeds, and the scoped Swift suite passes
**24 tests** with normal SwiftPM sandboxing enabled. The delivered reproduction
script independently creates a second fresh temporary build, redirects Swift,
Clang, SwiftPM manifest/cache/config/security paths there, builds the actual
native owner, and passes the same 24 tests. No sandbox-disabling flag or user
cache write is used. `r324-review-correction-artifacts/build-and-test-native.sh`
in the task artifact directory contains the exact commands; the corrected
source manifest binds that script, build artifacts and validation logs. The
earlier Python warning-as-error invocation stopped during pytest-asyncio
configuration before tests ran; specifying its existing function fixture scope
resolved that environment configuration issue without suppressing warnings.

Independent re-review is still required; full application/repository and live
validation remain outside these focused receipts. Source edits for this fix are
limited to the already claimed service/recovery modules and their two test
modules. No public write, merge, live action, new scope or model change occurred.

### R3.24 bounded source acceptance and final evidence — 2026-10-31

The coordinator reports independent acceptance of the bounded offline
source/process implementation at `04afff4c4a4594c9bd1182a10ba45bb6a1fc0986`,
tree `78ebb547f1e67ac7962dcf93e14a3cdceba08ef5`. Both cancellation-admission
and nested-integer findings are resolved. This supersedes the pending-review
status above; historical checkpoints remain historical. The reviewer compared
15 changed and 2,151 unchanged paths against the accepted design. The reserved
Keychain adapter source remains unchanged. This finalization changes only the
three already claimed documentation paths and preserves all accepted source.

| Evidence | Exact scope and disposition |
| --- | --- |
| Independent native build | Actual owner rebuilt with temporary caches; executable SHA256 `64cfe906ff8f2f1bc9d58bdb615edb3ff033cef71fc5fbc7267877a66572dacd`. |
| Independent Python execution | 323 phone tests and 434 subtests, zero skips, warnings as errors, using that independently rebuilt owner; actual disposable owner/child process coverage is included, not additive. |
| Author Swift execution | 24 scoped authority tests passed with normal SwiftPM sandboxing and temporary caches. A second fresh author reproduction ran the same 24 tests; these are not 48 distinct tests or an independent reviewer execution. |
| Independent Swift execution | Test startup denied at `sandbox_apply`; reviewer verified the author receipt but did not independently execute the Swift tests. This remains a reproducibility gate, not a test failure or a passing independent suite. |
| Wider validation | Full repository tests and full MortimerHost app build were not completed for this source. No exact-head CI, signed app, UI execution, production controller/Keychain, installation, live restore, real content bridge, listener or phone acceptance is established. |

The exact source manifest and reproducible temporary-cache build/test script are
retained in the task artifact directory `r324-review-04afff4c/`. The manifest
SHA256 is `cc5fde0323fed952c317f23e1f7edb1347752d06417920e6854a159df4231f47`.
Its logs distinguish the build and focused Python/Swift commands. The earlier
word “independently” describing the author's second fresh build means a separate
clean build directory, not independent review; the table above is authoritative.
No sandbox-disabling workaround is adopted.

For cumulative integration, the parent reports public WS05-only commit
`39208d18d8c6fde0a9a0539e4d7c3aa68de5610f`, tree
`e31cdf9531908b0186d71d7af573da877e7b7eec`. Local commit
`4e2152ec1b890e5383c42ac39d5605d57875886a` has exactly that tree and parent
`46e29c26e6a4262aa47dfa96615f3a91cc990572`. The public commit object is absent
locally, so the cumulative manifest compares the verified equivalent tree,
without asserting public-commit ancestry. The docs commit/tree and generated
path/mode/blob/SHA256 manifest are delivered separately after commit, avoiding a
self-referential hash in committed documentation. Parent owns CI544, fresh
remote/main reconciliation and later publication. This receipt neither reports
new CI results nor authorizes another merge; the one-final-merge plan remains.

### Next implementation proposal after R3.24 — not adopted

**Historical pre-adoption proposal:** the typed-card gap described below is now closed in the accepted synthetic/offline source `a121dfb0`. Its production-construction prerequisite remains open. This heading and proposal are retained for provenance, not as the current implementation status.

The offline recovery path now has bounded source acceptance, but the phone
protocol still has only the reserved session/voice/results/call operations;
`call.state`, `call.answer` and `call.decline` return `operation_unavailable`.
There is no typed phone workspace-command adapter or production service/source
construction. The existing console action enum includes broad Mac display,
sharing and input actions; forwarding that entire enum would exceed the phone
plan's mobile-view-only contract. Full 70-vector facade/store mapping also
remains open: the separate accepted R3.21 pilot has six translated cases, zero
exact full-vector replays, and 107 of 113 unchanged markers unexercised.

**Recommended next source slice, subject to coordinated claim adoption:** a
small typed phone workspace-command adapter for selecting, pinning/unpinning
and closing/reopening already admitted result cards. Target only the mobile
view workspace described in phone-plan §3 and item 1.3; retain canonical result
IDs/revisions, and never interpret selection as Mac window control or source
mutation. First review and reserve an explicit closed operation/payload/reason
contract and capability mapping; no new operation names or shared numbers are
reserved by this proposal. Require server-owned peer/session identity, current
authority and collection classification at dispatch and output, exact argument
types, bounded request/receipt storage, and revision-bound references. Use
synthetic admitted collections and an injected mobile-workspace executor, with
an actual owner/child service path. No general text, shell, arbitrary console
action, source-open/share, task execution or remote Mac control enters this slice.

Proposed ownership is WS-04 for the protocol/service adapter and process tests,
WS-17 for mobile projection/workspace semantics, and WS-30 for matching typed
DTO/client state. Before edits, list exact files and refresh those owners' active
claims; no existing source claim is widened here. Exit evidence should show an
admitted card command changes only the synthetic mobile view, exact duplicate
requests do not repeat effects, changed arguments conflict, stale revision and
unknown/extra fields deny, cross-owner/protected/unselected targets disclose
nothing, and revocation/quiescence/cancellation/lost acknowledgments cannot
create new authority or false completion. Preserve the existing proof, results,
recovery and six-case refinement regressions. Remote task cancellation or other
side-effecting actions remain the separately selected prepare/confirm/receipt
work in phone-plan item 3.2; the local console allowlist alone does not admit them.

**Production prerequisite to design in parallel, not implement under this
claim:** a concrete authenticated local-controller/service-construction boundary.
R3.24's injected authorization and private test mailboxes are test fixtures.
Specify who creates/holds the trusted capability, how the owner authenticates
and binds each controller connection, how capability loss/replay is handled,
and how normal service startup and catalogued recovery selection are separated.
`begin(source_id,expected_host_id,expected_generation)` and
`continue(operation_id)` remain the proposed typed recovery calls; caller paths,
UID/PID or code-signing identity alone must not supply authority. Inventory
concrete protected-storage APIs, noninteractive locked/denied behavior, signed
package/entitlements, owned-child provenance and WS-17 archive/invocation
responsibilities before a separately claimed production adapter. Preserve
single-owner supervision and explicit unavailable states. Real Keychain,
credentials, app install, network activation, live data and restore require
their existing separate gates. WS-05 voice readiness and the controller-model
approval rule remain unchanged. This proposal enables a reviewable next slice;
it does not establish product readiness or authorization to activate it.

## Typed mobile result-card commands — isolated design proposal, 2026-10-31

### Status, ownership and the product gap

**Historical design checkpoint:** subsequently accepted as `ffb1b1cc`, adopted by effective source claim `4bb67a50dc766f39905077020eb77cb6b77b36e8`, and implemented in independently bounded-accepted source `a121dfb0`. The no-source/reservation and pending-review statements in this design record describe the earlier stage; the contract below remains binding. The final receipt supersedes its status.

Design only, dispatched by the coordinator after bounded R3.24 source acceptance.
Documentation claim `2a8ca04c` precedes these edits on
`codex/ws04-ws17-ws30-phone-card-design-20261031`. Its base is immutable docs
`8797891d`; the subsequent historical-status correction `c40b9cc2` is carried
as cherry-pick `82cbfa76`, without changing accepted runtime source. Independent
design review and a fresh coordinated source claim are required before code.
No R3 identifier, wire operation or shared configuration is reserved here.
WS-04 owns admission/protocol/receipts, WS-17 mobile view and projection semantics,
and WS-30 checked phone state/UI. Existing console, source-policy, provider,
display, recovery and release owners retain their scopes.

R3.23 can show and refresh admitted synthetic cards, but cannot select, pin,
close or reopen them through the checked service/client path. The proposed
smallest complete slice adds five card actions and one bounded view-state read,
with a real disposable native-owner/Python-child path and checked Swift client.
It remains disconnected from Mortimer and uses synthetic sources exclusively.
It does not implement voice/data-channel commands, task execution, remote Mac
window control or production source/controller construction.

### Closed action map and concrete domain semantics

Existing domain anchors are `ConsoleActionCoordinator`'s `.resultSelect`,
`.resultReopen`, `.resultPin`, `.resultUnpin`, `.resultClose`, and
`WorkspaceStore.select`, `pin`, `unpin`, `close`. These are references, not
callable privileges: the Mac coordinator's select/reopen both call `select` on
an existing result, while Mac `close` removes its local retained entry and can
change focus. Calling those methods on the Mac's live workspace would violate
phone-plan §3. The new synthetic mobile view implements the narrowly mapped
semantics below, without importing/dispatching the whole console allowlist.

| Proposed phone operation | Existing domain operation | Exact synthetic mobile-view effect |
| --- | --- | --- |
| `results.select` | `result_select` → `WorkspaceStore.select(id)` | Require open target; set selected ID to target. Same selected ID is a no-op. No opening of a closed card, source fetch or Mac focus. |
| `results.pin` | `result_pin` → `WorkspaceStore.pin(id)` | Require open target; set pinned true. Already pinned is a no-op. Limit is 20 pins, matching the existing default domain limit; full capacity denies without changing any card. |
| `results.unpin` | `result_unpin` → `WorkspaceStore.unpin(id)` | Require open target; set pinned false. Already unpinned is a no-op. No source eviction or history trimming. |
| `results.close` | `result_close` → `WorkspaceStore.close(id)` | Set open and pinned false; clear selected ID only if it names this target. Do not auto-select another card. Already closed is a no-op. Keep the underlying admitted source result and closed-card entry for explicit reopen. |
| `results.reopen` | `result_reopen` → selection of a retained result | Set open true and select target; preserve an existing pin if already open, otherwise remain unpinned. No fetch/re-execution or resurrection of removed/protected results. |
| `results.view` | Read-only mobile view state (no existing Mac inventory forwarding) | Return the complete bounded view described below. Requires read authorization, not action authorization. Never exposes global Mac inventory. |

There is no `action` string argument, arbitrary operation name, text-to-command
parser, subject/Recents-number resolver, URL/path, shell, attachment, source-open,
share/export, task-cancel or generic executor endpoint. UUIDs address only an
already admitted source. The app displays a separate closed-card list with
Reopen controls; closing is not deletion. State is per full login binding, not
shared across devices or login sessions. A successful initial view has all
currently admitted ordinary cards open, none pinned and no selected card.
New ordinary cards are added open but never steal selection. These mobile
semantics intentionally differ from Mac close/focus/trim behavior and require
review/adoption as specified here, rather than silently claiming reuse of Mac
state ownership.

### Authority and classification, before effects and before output

Use the exact `TrustedRequestContext` and current `PhoneAdmissionStore` binding;
no owner/device/grant/session, scope, peer identity or classification is accepted
from phone JSON. The full key is the existing tuple `(owner_id, device_id,
grant_id, session_id, login_incarnation, host_id, host_generation,
grant_generation, session_generation, process_epoch, sorted(scopes))` plus the
results provider generation and collection grant identity/version. A view is
never found by caller `view_id` alone. Missing/stale/pending/unavailable protected
authority denies before effect. No stale five-second command authorization cache
is introduced; commands revalidate current binding at the commit boundary.

Every action requires both existing scopes `read` and `action`, an active
`PhoneResultCollectionGrantV1` matching owner/device/phone grant, and the active capability in the shared runtime's server-owned command registry,
as defined below. Only trusted fixture setup/control mutates this registry;
it is not a DTO, not inferred from `read`, and not minted by login, an app tap,
an LLM or a supplied result ID. `results.view` requires `read` and the existing
collection grant; it returns the currently authorized action subset (empty
without an active matching capability) as display hints. Recheck the exact
registry identity/version on every action, first publication and cached receipt
release. Facades do not hold independent authoritative capability snapshots.

The source must prove target membership, canonical identity, current ordinary
classification and valid provenance, with the exact observed result revision.
Use the R3.23 trusted synthetic provider and selected-source versions, never
`isProtectedLocal == false`, caller labels, UI visibility or title matching.
Unknown/conflicting classification or invalid provenance in the selected
collection fails the complete preparation closed. Protected and unselected
activity never changes a visible revision/counter or reveals an ID, count,
title, denial detail or cursor. Previously visible removal/reclassification or
grant/membership change rotates the existing collection epoch and invalidates
the view and all command publication. A protected/unselected/missing target
gets the same content-free denial as an unauthorized target. Each response's
entire referenced card set, not just the target, passes the current visibility
and output gate. Ordinary revision changes preserve collection epoch but make
a fresh action carrying the old revision conflict; a new view read reconciles
ordinary source revisions. No provider/model/audio sink is enabled by this grant.

### Capability owner, lifecycle and shared-facade registration

The existing shared `_AuthorityRuntime` is the authoritative owner of a single
command registry, the views and the request ledger. A registry slot belongs to
one exact registered `PhoneRemoteResults` object, its results-generation UUID,
and its owner/device/phone-grant identity. There is one trusted fixture-control
handle for this registry; application requests never receive it. Registering a
second facade for that slot requires the identical runtime/registry handle and
projector/source objects. It attaches to the existing slot, never replaces it
or combines/intersects action sets. A different projector, capability controller,
collection binding or conflicting initial definition fails construction before
that facade can serve requests. Distinct legitimate A/B slots share the runtime
lock but not capability/view/ledger identities.

Each slot contains an immutable current record, replaced atomically by its
owner: `{capability_id, version, active, allowed_operations, results_generation,
collection_grant_identity, collection_grant_version, owner_id, device_id,
phone_grant_id}`. The identity is a server-generated canonical UUID; version is
an exact integer in `1..2^63-1`. The collection-grant identity includes the exact
registered object and its collection UUID, not just equal caller fields. Active
records have a nonempty sorted subset of the five operation enums. Inactive
records have an empty subset. An immutable record is a snapshot, not a promise
that the slot cannot change. Preparations and receipts bind both capability ID
and version, or a distinguished absent-capability token when the slot has never
been registered. A revoked/inactive record still binds its ID/version even
though the view exposes an empty operation list; it is not treated as absence.

Only the trusted owner can perform these compare-and-swap transitions; every
transition is conditional on the exact expected current ID/version (or absence
for first registration). Stale/reentrant/invalid updates fail without effects:

| Transition | New record and view/receipt consequence |
| --- | --- |
| First register | New UUID, version 1, active subset and exact current collection binding; no implicit retroactive grant to a prepared request. |
| Expand/narrow subset | Same UUID, version +1, nonempty new subset; an empty subset is revoke. An exactly identical update is a no-op and does not advance version. |
| Revoke | Same UUID, version +1, inactive/empty; repeated revoke is a no-op. Keep the tombstone while the slot/runtime exists. No action may reactivate it. |
| Replace | Fresh UUID never previously used in this slot, prior version +1, active subset and explicitly revalidated current collection binding. This is the only way to regrant after revoke. Version does not reset. |
| Collection grant replacement/revocation or results generation change | Exact binding fails immediately, even if an old registry record says active. No automatic rebinding. Retire the old view; only explicit trusted replacement/registration can authorize the new collection. |
| Version exhaustion/runtime end | Fail closed without wrapping. Runtime end destroys the ephemeral registry and views; a replacement runtime has a new results generation and fresh identities, not a continuation of old authority. |

All effective capability transitions invalidate eligibility of every earlier
view/action receipt bound to that slot's old ID/version, including expansion
where the original operation remains allowed. Narrowing also invalidates old
receipts for still-allowed operations. Replacement never inherits prior receipt
authority; regranting the same subset cannot revive a withheld receipt. Exact
no-op updates preserve the existing version and receipt eligibility. On replay,
an action whose capability changed returns `denied/not_authorized/{}`; an old
view-read receipt with an outdated capability-list token returns
`unavailable/authority_unavailable/{}`. Existing binding/collection denials
retain precedence. No replay mutates the view or refreshes the stored receipt.

A capability change marks existing view synchronization stale by token mismatch;
it does not itself increment a view revision or change open/pinned/selected
state. A fresh `results.view` reconciles its allowed list/token and increments
the view revision once. Even expansion cannot make a fresh action valid against
an old view: it conflicts until that view read. Revoked/unavailable action
capability leaves authorized read-only view access with an empty list. This is
an additional gate; `action` scope never bypasses the current subset.

The registry uses the existing shared runtime lock R, not a new lock or a
per-facade mutex. Register/expand/narrow/revoke/replace take R then projector
lock P to validate collection identity; no callback or source read occurs there.
They cannot interleave with an action's effect or first receipt publication,
which hold R across both and the intervening ACK. A competing transition waits:
if it obtains R before the action, the action observes its new version; if the
action obtains R first, its completed first-publication linearization precedes
the transition, and subsequent replays see invalidation. A paused preparation
holds neither lock and must recheck its token. All future source-state locks
and the precise publication order are specified below.

### Exact proposed wire and view state

Extend the closed operation enum under the existing v1 envelope only after
review/reservation; existing operations and schemas remain byte-compatible.
Old hosts reject the new operations. A new client starts this feature only after
a successful explicit `results.view`, and treats its checked allowed-operation
list as a UI hint rather than authority. Keep duplicate-key, strict UTF-8,
1 MiB request, depth-64, protocol-version and 1..128 UTF-8-byte request-ID rules.

`results.view` payload has exactly `{generation, collection_epoch}`, obtained
from an accepted results snapshot. Each action payload has exactly
`{generation, collection_epoch, view_id, view_revision, result_id,
result_revision}`. UUID fields are canonical lowercase UUID strings. Result
revision is an exact integer in `1..2^63-1`; view revision is an exact integer
in `0..2^63-1`. Booleans, floats, numeric strings and extra/missing fields fail
before authority IPC or view creation. The `generation` is R3.23's opaque
results-process UUID, never a caller-selected host generation or capability.

All six successes have exactly this payload:
`{generation, collection_epoch, view_id, view_revision, selected_result_id,
allowed_operations, cards}`. `selected_result_id` is null or a member with
`open:true`. `allowed_operations` is a sorted, duplicate-free subset of the
five action operation names. `cards` is sorted by canonical result ID, unique,
complete for the current admitted ordinary collection, at most 25 entries.
Each entry is exactly `{result_id, result_revision, open, pinned}`; booleans
are exact, pinned implies open, and at most 20 are pinned. No titles, bodies,
source paths or hidden identities are copied into view receipts. Checked total
response maximum is 16 KiB. Existing content remains solely in checked R3.23
snapshot/resume items, joined by identity and revision on the client.

A fresh server-generated view ID starts at revision 0. Only `results.view` creates or reconciles source/card/revision/capability
state; it increments revision once if any such field changes, otherwise returns
the existing revision. An action never performs reconciliation. Its one atomic
transaction applies only the selected mobile-view operation, incrementing the
revision once if that operation changes state; a no-op keeps the same revision.
Require exact view ID/revision, target revision and the complete visible
collection fingerprint (sorted ordinary member IDs/revisions, classification/
visibility versions, collection and capability tokens) saved by the last view
read. If any other ordinary card changes revision or an ordinary card appears,
even while the target revision stays current, deny `request_conflict/{}` with
zero action effect and no view mutation/revision increment. A source/epoch or
visibility denial uses the earlier authority/classification rules instead.
Unselected or never-visible protected changes are excluded from this fingerprint.
Capacity and all preconditions are checked before mutation. A subsequent fresh
view read reconciles all visible rows, preserving mobile state on surviving
ordinary IDs, adding new IDs open/unpinned without selecting them, and applying
the epoch-reset rule for removal/reclassification. This is strictly view-first;
there is no combined reconciliation-plus-action path. Exhaustion fails closed,
never wraps. A collection epoch change discards the old view; only a new view
read with a freshly accepted results generation/epoch may create its replacement.
No action creates a missing view. View capacity is one per full binding and
collection, at most 128 views per authority runtime, each at most 25 cards.
Capacity exhaustion denies new views without evicting a live view or receipt.
Retire views on binding end, collection invalidation or runtime shutdown; no
persistence, file writes, new database or restart restoration is included.

| Response status/reason | Exact interpretation for these operations |
| --- | --- |
| `ok/none` | Full checked view payload; historical committed receipt on an exact retry, never an unvalidated optimistic effect. |
| `denied/malformed_request` | Bad schema/type/enum; payload `{}`. |
| `incompatible/unsupported_protocol` | Unsupported version; payload `{}`. |
| `denied/not_authorized` | Invalid/revoked binding, absent scope/capability, disallowed action or inaccessible target; payload `{}`. |
| `denied/request_conflict` | Changed request-ID reuse, duplicate still running, stale view/source revision, or an operation requiring open state targets a closed card; payload `{}`. |
| `denied/request_capacity` | Ledger/view/pin capacity; payload `{}`. |
| `unavailable/feature_off`, `owner_busy`, `operation_unavailable` | Existing feature/owner/injected-component gates; payload `{}`. Voice readiness is irrelevant to cards. |
| `unavailable/authority_unavailable` | Authority uncertainty, generation/epoch mismatch, unverifiable selected source, overflow or failed output revalidation; payload `{}`. No success or rollback claim. |

No new reason/status vocabulary is required. The exact per-operation matrix
must be implemented in Python and Swift together. Error precedence: structural
validation; current binding/feature gates; ledger conflict/capacity; capability
and selected-source authorization; observed view/revision preconditions;
mutation and output gates. An unauthorized caller cannot learn view existence
or revision from the conflict/capacity branches: ledger keys are binding-scoped,
and target/view conflict checks occur only after content authorization.

### Execution, receipts, cancellation and races

Retain the existing request ledger key `(full binding, request_id)`, canonical
request digest and bounded default capacities (256 per binding, 4,096 overall).
Reserve before provider reads. Different operation/version/payload under the
same ID conflicts; an in-flight duplicate conflicts without another execution.
Do not key deduplication by result ID or treat set-like effects as permission
to execute again. No terminal/uncertain entry is evicted while its binding is
usable. View capacity is an additional bound, not a second request ledger.

Preparation reads/callbacks occur outside authority/commit locks and return an
immutable candidate containing the full selected ordinary-source fingerprint,
capability token and observed view token. Neither action preparation nor a
failed action updates the saved view. A fresh action whose capture already
differs from the last reconciled view conflicts, including an unrelated visible
card's edit/addition. The same full comparison repeats at the atomic effect,
so changes between preparation and effect conflict too. An action proceeds
only if both comparisons match. An unavailable/unverifiable selected source or
classification/epoch change takes the fail-closed output/authority path rather
than being mislabeled an ordinary revision conflict.

The mutation is an exact, service-owned bounded in-memory state transition,
not an injected executor callback. The concrete lock order is:

1. A: existing owner-availability guard; T: existing clock guard.
2. R: existing `_AuthorityRuntime.lock`, shared by service, ledger, views and
   the new capability registry.
3. G: `_service_commit`'s existing native grant/store serialization.
4. P: this `PhoneRemoteResults._lock`; S: its exact
   `SyntheticResultsSource._lock`, in that order.

The effect compares binding/feature/current clock, current capability ID/version,
collection grant/generation/epoch and the complete saved/captured/current source
and view tokens while R/G/P/S are held. A passing action atomically records its
new view state, effect outcome and provisional receipt. Release S/P before
exiting G and waiting for the matching normal grant-release ACK; retain A/T/R
through that ACK and terminal publication bookkeeping. No network call, clock
callback, provider callback or injected mutation runs while P/S are held.
Source access here is a bounded, noncallback comparison of the exact registered
synthetic source's immutable records/versions.

This is compatible with the existing projector's P→S snapshot/cache guards.
Existing result reads under the shared service use R→G then R→P→S after ACK;
they must never acquire R while holding P or S. Source replacements acquire S
only and do not call projector/service code. An unregistered projector's collection replacement and projector revoke acquire
P only. Once registered, collection replacement enters the sole registry's R
before P, atomically collision-checks/moves its logical slot and retires the old
view; it never calls R while holding P. Capability authority is not rebound:
the new grant identity/epoch requires explicit capability replacement. Revoke's
new epoch is detected by the next R→P validation.
Capability-owner transitions acquire R→P, without G or S. Registration and
teardown likewise use R→P. There is no P→R, S→P, callback-to-service, or
per-facade lock inversion. Precomputed test barriers pause outside guards;
tests holding a guard deliberately must release it without invoking an API
that acquires an earlier guard. This order is a required design contract; any
concrete inability to preserve it requires a focused amendment before edits.

**First publication after ACK:** while A/T/R still exclude service authority
mutations and capability changes, reacquire P→S and compare the full source
fingerprint, collection identity/epoch and capability token again. First
publication requires the exact source revisions/visible membership captured at
effect; it may not use the more permissive historical-replay rule. An ordinary
edit/addition to any visible card during ACK wait withholds success as
`unavailable/authority_unavailable/{}` even if the target is unchanged. The local
effect may have occurred; keep the view marked unsynchronized and do not undo or
re-execute it. Source removal/stricter classification/collection replacement
also withholds output and invalidates the applicable view. A competing capability
transition cannot run during ACK wait because it needs R; it linearizes either
before the effect or after this first publication. Check deadline/expiry against
the trusted clock and retained verified authority continuation at publication;
if that continuation cannot establish current eligibility, settle unavailable,
not a new unbound grant or success. No additional logical request joins drain.

On success, install the immutable done receipt and hand its checked bytes to
the response-return path under this publication guard; that handoff is the
first-publication linearization point, not acknowledgment of phone receipt.
Later changes cannot recall bytes already released. No candidate receipt is
cached as done merely because G's ACK arrived. Even a no-op action goes through
the same ACK and publication checks. A `results.view` read uses coherent capture
and guarded reconciliation, and similarly refuses its first success if selected
source state changed before first publication; it never publishes a mixed view.

Use explicit states reserved/prepared/applying/applied-awaiting-ack/done,
terminal-withheld or terminal-uncertain. Set applying before effects. Any
possibly effectful raise, reentrancy or uncertain channel/ACK outcome latches
terminal-uncertain and fences authority under the existing lifecycle. A known
applied effect with valid ACK but a failed first-publication source gate becomes
terminal-withheld: preserve its internal outcome but never expose the provisional
view receipt or rerun that request. These terminal entries return the same
content-free unavailable outcome on an authorized exact retry; a later source
or capability repair cannot promote them to done. Failed authorization still
wins on a revoked retry. A later authorized fresh `results.view` can reconcile
current state only if authority is healthy; it cannot bypass an authority fence.
A definitely pre-effect conflict/denial uses normal terminal denial receipts
and never changes view state. No exception path returns to reserved.

**Historical replay:** only a request that reached done at an earlier successful
first-publication handoff is eligible. A lost transport reply after that handoff
is a historical retry, even if the phone never displayed it. Recheck current
binding, exact capability ID/version (or absent token for a read-only view),
collection identity/epoch, source identity and current visibility/provenance for
all referenced IDs under the same authority/R→P→S publication guards. Unlike
fresh preparation/first publication, do not demand old ordinary source revisions
or the old current-view revision: later ordinary edits/additions and mobile-view
edits may coexist with the original immutable receipt. Do not append newly
appeared cards, alter the old receipt, advance revision or execute again. A newly
unverifiable selected source still fails closed; hidden/unselected activity does
not invalidate it. Capability changes, source removal or stricter classification
withhold the old receipt as specified above. The model's exact content-join and
view monotonicity rules prevent historical success from rolling back its screen.

In-flight duplicates and terminal-withheld/uncertain retries never invoke the
transition. A process restart loses this explicitly ephemeral view and ledger
and changes results generation/view ID, so an old request cannot execute against
the new view even after fresh login. No durable exactly-once promise is made.

Revocation before the atomic action denies without effects. An action that
wins the serialized boundary may finish its local effect; later revocation
prevents new commands and further successful output, and does not recall bytes
already emitted. Ordinary source edit/classification changes before commit
invalidate preparation; a change after commit triggers the output rule above.
Session sign-out affects only that binding; existing global-revocation semantics
are unchanged. Command A must not change B's view or receipts; a legitimate
global authority transition may fence both and is tested as such.

Preserve R3.24 cancellation/drain: cancellation before enqueue, while queued,
or at worker preauthorization yields no authority acquisition/effect; deterministic
fast-worker probes must prevent the caller poller from hiding races. After
authorization, caller cancellation stops publication but retains owned continuation
through commit/terminal bookkeeping. During quiescence only frozen authorized
work can continue; new/queued work is rejected locally. The same nonextending
five-second drain and owned-child terminate/reap bounds apply. No false drained
ACK or recovery mutation after an uncertain continuation. Cancellation never
means “the card operation was rolled back.”

### Checked Swift model and disconnected UI

Extend `PhoneRemoteOperation` in `PhoneRemoteProtocolV1.swift` and its exact
operation-inventory assertion in `PhoneRemoteProtocolTests.swift` alongside
the closed request/response enums in `PhoneRemoteOperationsV1`; reject unknown
fields/actions, invalid UUIDs/exact integer types, duplicate cards/operations,
closed+ pinned cards, absent selected IDs, over-25 cards, over-20 pins, excessive
bytes and response/operation/request-ID mismatch before model publication.
No dynamic dictionary reaches the UI. Keep `PhoneRemoteOperationsClient`'s
single owned exchange, cancellation linearization and response drain unchanged;
it generates a fresh ID for each explicit send and never silently retries an
action. Exact-byte server retry coverage is exercised through test transport
and raw process requests, not by adding a generic resend API to the app.

The model first loads a complete checked results snapshot, then explicitly
reads a checked view. Before enabling any action, require an exact complete-set
join: generation/collection epoch match; every view card ID has checked content
at exactly its result revision; the view's card set equals the full accepted
ordinary snapshot/resume collection. A view arriving with a new ID, newer or
older source revision, missing content or a mismatched set leaves all controls
disabled, even if one target still matches. Keep the visible prior content inert
under the existing stale-content rule and display “Results changed. Refresh to
sync.” Do not synthesize content from view metadata or implicitly act on it.

An explicit Refresh performs one bounded read-only synchronization attempt:
complete fresh snapshot followed by a fresh `results.view` request. If a source
changes between those reads, retain the stale/disabled state and await another
explicit Refresh; there is no automatic retry loop or action resend. A previously
started checked resume traversal must reach its complete watermark before its
content can substitute for a snapshot in a view join. A source upsert after a
successful join invalidates command readiness until another explicit view/read
synchronization; it does not retarget a pending action. A view-revision conflict
also disables commands until explicit read reconciliation.
Disable actions while busy, stale, detached, draining, offline, reset or masked.
Publish selection/pin/open changes only after a fully checked successful response;
no optimistic success animation. Apply strictly newer view revisions only after the complete content join, allow
an identical equal revision with the same joined content, and refuse
equal-revision conflicting data or older responses. A historical replay may be
a valid server receipt while remaining ineligible for client publication because
its content revisions no longer match; do not treat that as authority to fetch
or replay an action automatically. Keep per-view history bounded to the last accepted view and one
pending publication identity. New generation/epoch/view ID requires a completed
fresh snapshot/view synchronization, never automatic acceptance from an action
response. Ordinary content upserts preserve phone selection without opening a
closed card. No new source or notification steals focus.

Use visible Open cards and Closed cards sections; selected detail is a phone
view only. Buttons say Select, Pin/Unpin, Close on phone and Reopen on phone,
with stateful accessibility labels/identifiers and keyboard/VoiceOver actions.
A deliberate tap is the user intent for these reversible mobile-view changes;
there is no destructive/source-delete confirmation because this slice cannot
delete source content. Success means only this synthetic phone view changed.
On interrupted/uncertain exchange show “View change could not be confirmed.
Refresh to check.” A new action requires explicit intent after reconciliation.
On authorization/feature/reset/failure masking, foreground loss or local logout,
clear cards, view state and pending publication immediately when observable.
While disconnected, previously displayed content may remain under the existing
R3.23 stale-content rules but is inert; no unseen revocation notification is
promised. Preserve the persistent disconnected/synthetic-preview banner and
make no claim of live connectivity or production permission.

### Required tests and frozen-contract relationship

The first implementation must include actual byte-level Swift-client → owned
Python test bridge → disposable native owner/v4 service child → typed synthetic
view transition → checked Swift response/model evidence. The bridge belongs
only to test code: bounded length-prefixed stdin/stdout, single exchange, trusted
synthetic setup separate from request bytes, private temporary fixture mailboxes,
no listener, no caller-selected executable/path or authority fields. Reuse the
existing `--test-owner` and test child routing; the new v4 scenario forwards from
the already-owned channel test module into the service test helper, without
native owner protocol/source changes. Test setup creates disposable DB/fake
anchor and synthetic enrolled keys, performs proof login, and retains/reaps only
its owned processes with bounded timeouts. Run the same checked model with the
in-process fake transport for deterministic UI states. Missing binary/toolchain
is a recorded unrun prerequisite, never a successful test or substitute fake.

| Test family | Required positive and negative evidence |
| --- | --- |
| Domain/end-to-end | Each of five actions plus view read; target identity/revision preserved; close/reopen round trip retains source; repeated no-ops do not advance revision; pin-20 limit; source additions do not select; no Mac mutation, provider, source write or extra subprocess. |
| Authorization | Read-only can read view but cannot act; action-only cannot read/act; both scopes without server capability deny; capability subset/foreign object/version/revocation deny; exact A/B ownership, two devices and two logins, forged JSON identities, stale incarnation/host/grant/session/process generations. |
| Source/classification | Missing/protected/unselected/unknown/conflicting/unprovenanced targets and selected-source failures; canaries absent from response, errors, diagnostics and retained view receipts; unrelated hidden activity leaves visible results/counters unchanged; old ordinary body cannot authorize new protected state. |
| Races | Pauses before/after source capture, authorization, atomic effect, release ACK and publication; both orders of source edit, classification tightening, capability change, sign-out/revoke and feature-off; complete view/receipt/authority observations before/after. |
| Repetition/uncertainty | Concurrent identical request executes once; changed payload conflicts; same IDs in A/B do not alias; exact done replay after later ordinary edits returns historical receipt without effect; uncertain/effect-then-raise/reentrant/lost-ACK paths stay terminal; restart with old view/generation cannot repeat. |
| Cancellation/drain | Pre-submit/queued/preauthorization fast-worker probes; after-authorization owned completion; client before-dispatch zero bytes, after-dispatch no late publication and no overlapping exchange; pending action during quiesce, deadline/no-extension, withheld ACK and child death with no recovery mutation. |
| Wire/model/UI | Cross-language canonical requests/successes/all error tuples; integer/UUID/schema/limits/duplicate keys; out-of-order/equal-conflicting views; old response after foreground/logout reset; stale content join; open/closed/pinned/selection accessibility and persistent synthetic banner; unsigned app build and separately reported UI execution. |
| Existing isolation | R3.23 A/B collection/cursor/receipt isolation, R3.17 peers/leases/sink isolation, unchanged seven S0 sensitivity mutations and three network/process/runtime isolation probes; no production providers/network/Keychain/live content. New owned-process tests are explicit exceptions to the pure S0 harness's process prohibition, not changes to that harness. |

The following interleavings are mandatory additions to the matrix. Use explicit
barriers and complete effect/view/ledger/output observations; elapsed sleeps
are not proof of ordering. Exercise both the target and a different visible
card, plus a newly appearing ordinary card in the existing selected membership.

| Boundary/interleaving | Expected result and invariant |
| --- | --- |
| Ordinary edit/appearance before fresh action preparation | `request_conflict`, no action effect and unchanged saved view/revision. A subsequent fresh view read reconciles once; only a new explicit action using its exact tokens can proceed. |
| Edit/appearance after capture, before effect | Same conflict/no-effect outcome, even when the target ID/revision is unchanged. Hidden/unselected activity is a positive control that does not conflict. |
| Edit/appearance after effect, during ACK wait, or after ACK before first publication | Effect may have occurred; first success is withheld, ledger terminal-withheld, content-free unavailable; exact retry never executes/promotes it. New authorized view read reveals the reconciled current state. No rollback claim. |
| Edit/appearance after done/first-publication handoff | Exact historical retry returns original receipt only if current visibility/binding/capability remain valid; no second effect or receipt rewriting. Fresh actions still require a reconciled view. Swift ignores/rejects stale/incompletely joined historical view publication. |
| Capability expansion/narrowing/revoke/replacement before capture or between capture/effect | New registry token is observed: removed operation denies not-authorized; still-allowed operation with stale view token conflicts until view read. Old cached action receipt denies not-authorized even after pure expansion or narrowing that retains that operation. Test new UUID on replacement and no-op update preserving eligibility. |
| Capability change scheduled during effect/ACK/first publication | Change blocks on R, cannot update midway, then advances once after the action's first-publication handoff. The first action may succeed; subsequent old receipts are withheld. A separate ordering where transition obtains R first must produce the pre-effect outcome. No concurrent facade owns a second registry. |
| Source/collection visibility tightening around each boundary | Before effect: no effect; after effect: no successful first output; after done: old receipt withheld. Check all returned card IDs and canaries, not just target. Collection replacement cannot auto-rebind an old capability. |
| Snapshot at S1 then view at S2 with new ID/revision | Checked DTO is accepted structurally but whole-view content join fails; all controls remain disabled. One explicit snapshot→view refresh can succeed if stable; repeated concurrent updates keep it disabled without an automatic loop/action resend. |
| Action response after source upsert, newer view, logout or foreground reset | No stale selection/pin/open publication. Equal-revision conflict, older view and a valid historical receipt with mismatched content are rejected for publication without replay. |
| Shared facade registration/CAS lifecycle | Same trusted handles reuse registry/view identity; contradictory handle/projector/initial subset is rejected. Stale expected version and invalid/overflow updates change nothing. Revoke→replace with same subset cannot revive old receipt. A's slot/version/view changes leave B unchanged. |

Run every lifecycle transition against in-flight action preparation, first
publication, cached action receipt and cached view-read receipt. Include an
ordinary-content-only positive replay, effective capability-change negative
replay, immutable record alias/subclass rejection where exact concrete types
are required, and A/B concurrent requests with identical request/result IDs.
Preserve ordinary R3.23 projection behavior and the original native recovery
ACK/cancellation tests unchanged. The two added Swift protocol paths must pin
the complete operation inventory and reject unknown operations in addition to
the DTO-level payload checks.

Frozen fixture `tests/fixtures/phone_admission_contract/v1.json` SHA256 remains
`1cf1f8a377438a5fe04d0517535eee86166c48af6decb030da249b9ae5083950`;
legacy adapter `tests/unit/test_phone_admission_contract.py` remains
`28936b4b3a00ed0bc6af4114493d6bbeffe1d40d66e6968221e33b41d9615720`.
Neither is in the implementation scope. Read their expectations and retain the
existing A/B setup and complete unchanged-state comparisons. Map the following
as new translated obligations, not exact fixture replays:

- `spoof-command`, `malformed-command`, `missing-action-scope`: trusted binding,
  closed typed action and mandatory action scope, translated to a specific card
  operation with explicit observed revision and admitted collection.
- `stale-peer`, `session-revoke-old-snapshot-command`,
  `session-fence-advances-after-stale-restore`: preserve and test stale authority
  denial, but record peer-based fixture steps separately. Card requests use the
  authenticated facade binding and need no voice peer/microphone lease; they do
  not prove the fixture's peer lifecycle or implement data-channel commands.
- `classification-event` and `classification-text`: test ordinary/provenance/
  source-grant gating on state IDs and displayed card content. Audio-symbol and
  provider egress remain outside this slice; `display-not-provider` remains a
  prohibition, not a newly implemented provider path.

The fixture permits `fixture-action` only inside its test model; it is never a
wire operation or a production alias. Malformed input must leave the complete
service/ledger/view/source/authority observation unchanged and perform zero
channel operations. Later authorized-request denials may reserve a ledger entry;
record that difference rather than weakening a frozen unchanged assertion.
Keep R3.21's six accepted translated malformed-event-type cases unchanged. Exact
full-vector replay count stays zero until separately proven; the common two-A-peer
initializer mismatch, 107 remaining unchanged markers and unimplemented oracle
obligations are not closed by this design or by a green new-command suite.

### Exact proposed source/test claim, for later adoption only

**Historical proposed inventory:** all 22 paths below were subsequently adopted in claim `4bb67a50dc766f39905077020eb77cb6b77b36e8` before implementation. This is the accepted source scope; further source changes still require coordinated authority. The following pre-adoption wording is retained as history.

Twenty-two paths; two new Python files and one new Swift test file, all other paths
already exist. This list is not current editing authority. Refresh current main,
active owners and path collisions again immediately before adoption. No native
owner/channel implementation, login, store schema, frozen adapter, production
server, Mac console/store, project manifest, workflow or shared fixture edit is
included. If the test-only bridge or build needs another path, coordinate the
exact amendment before edits rather than expanding this list implicitly.

| Owner | Exact paths |
| --- | --- |
| WS-04 (7) | `jarvis/bot/phone_remote_protocol.py`; `jarvis/bot/phone_remote_service.py`; `tests/unit/test_phone_remote_protocol.py`; `tests/unit/test_phone_remote_service.py`; `tests/unit/test_phone_remote_authority_service.py`; `tests/unit/test_phone_remote_authority_channel.py`; `tests/unit/test_phone_remote_asgi.py` |
| WS-17 (4) | `jarvis/bot/phone_remote_results.py`; `tests/unit/test_phone_remote_results.py`; new `jarvis/bot/phone_remote_result_commands.py`; new `tests/unit/test_phone_remote_result_commands.py` |
| WS-30 (11) | `ios/MortimerPhoneCore/Sources/MortimerPhoneCore/PhoneRemoteProtocolV1.swift`; `ios/MortimerPhoneCore/Tests/MortimerPhoneCoreTests/PhoneRemoteProtocolTests.swift`; `ios/MortimerPhoneCore/Sources/MortimerPhoneCore/PhoneRemoteOperationsV1.swift`; `ios/MortimerPhoneCore/Sources/MortimerPhoneCore/PhoneAppPreviewModel.swift`; `ios/MortimerPhoneApp/MortimerPhoneApp/PhonePreviewFakeTransport.swift`; `ios/MortimerPhoneApp/MortimerPhoneApp/PhonePreviewRootView.swift`; `ios/MortimerPhoneCore/Tests/MortimerPhoneCoreTests/PhoneRemoteOperationsV1Tests.swift`; `ios/MortimerPhoneCore/Tests/MortimerPhoneCoreTests/PhoneRemoteOperationsClientTests.swift`; `ios/MortimerPhoneCore/Tests/MortimerPhoneCoreTests/PhoneAppPreviewModelTests.swift`; new `ios/MortimerPhoneCore/Tests/MortimerPhoneCoreTests/PhoneResultCommandsProcessTests.swift`; `ios/MortimerPhoneApp/MortimerPhoneAppTests/PhonePreviewUITests.swift` |

Required later validation: all `tests/unit/test_phone*.py` with warnings as
errors and a freshly built actual owner; the whole PhoneCore suite including
new process bridge; existing scoped authority Swift tests and unchanged R3.24
recovery/process regressions; unsigned generic app/UI-test bundle build;
actual UI test execution only on a working compatible runner, otherwise report
unrun; roadmap/diff/source-preservation checks and independent immutable-source
review. Full repository/app/integration CI and live release gates remain their
own requirements. No test execution or implementation acceptance is claimed
by this documentation slice.

### Decisions for independent review and later production gates

Review must explicitly adopt or revise: (1) five named operations plus view
read, exact wire/error matrix and mobile close/reopen/selection semantics;
(2) `read`+`action` plus server-created subset capability, with no grant widening;
(3) per-login ephemeral view, bounds and historical-receipt/restart semantics;
(4) the proposed lock/ACK/publication ordering and test bridge within the exact
22 paths. These are concrete design decisions for review, not requests for
Larry to approve routine coding steps. No source work begins before coordinator
adoption of the reviewed contract and claims. There is no newly discovered
contradiction in accepted R3.24; it remains unchanged.

Eventual real mobile actions require an authenticated production facade and
trusted read-only source bridge providing stable IDs, revisions and classification,
plus a distinct mobile workspace executor. The broad Mac console allowlist,
filesystem presence or a code-signing identity alone supplies none of these.
Production enrollment/action-capability choice, native owner construction,
protected storage, controller authentication, signing and WS-17 restore invocation
remain separately designed/claimed. This slice does not change those security
boundaries or the Mortimer controller model. A later real Delete, Share/Send,
Export, Run or Cancel task action must select an existing domain executor and
its prepare/confirm/receipt boundary under phone-plan item 3.2, with target,
arguments, policy and any external side effects visible before confirmation.
The five reversible mobile-view actions do not preauthorize that future work.

### Independent-review revision — 2026-10-31

This revision addresses all three design findings against `1d75a2a2`: the
proposed source inventory is 22 paths including the actual Swift operation enum
and its exact inventory test; immutable capability records now have an explicit
runtime-owned identity/version/CAS lifecycle and R→P synchronization; and the
contract is strictly view-first with separate fresh-preparation, first-publication
and historical-replay rules. The interleaving matrix includes other-card changes,
ordinary appearances, capability transitions and snapshot/view content gaps.
These technical corrections require independent review, not a new product/user
choice. Documentation scope is unchanged; no runtime/source adoption or edits.

### Typed phone-card source adoption — 2026-10-31

**Historical checkpoint:** superseded by the final bounded source acceptance below; retain the original findings, counts and pending-review disposition as dated evidence.

Coordinator adopts independently accepted design `ffb1b1ccb4582bd38bd8ca426e9835a99a4e2ce9`, tree `1a6f090afd231766f32a44eb45e2a53824e7d280`, for the exact 22-path implementation map. Source branch is `codex/ws04-ws17-ws30-phone-card-source-20261031`; the effective WS-04/17/30 claims and six wire operation reservations are recorded before source edits. Fresh local inspection verifies all 19 existing blobs and absence of the three new files against the accepted manifest, with no uncommitted collision. Coordinator's 14:52 remote refresh reports unchanged main `5310d1a`/PR290 `39208d18`, green CI544 and no new conflict. Local handoff history/main limitations and the existing branch-local exception remain explicit. Complete offline implementation and independent source review are pending; design acceptance is not runtime acceptance. All accepted capability, source-reconciliation, first-publication/history, cancellation/drain, content-join and A/B isolation rules remain binding. No production/live/public action is included.


### Typed phone-card offline source candidate — 2026-10-31

**Historical checkpoint:** superseded by the final bounded source acceptance below; retain the original findings, counts and pending-review disposition as dated evidence.

Completed the adopted 22-path synthetic slice: six closed wire operations, runtime-owned CAS capabilities and per-binding mobile views, exact scope/source checks, view-first reconciliation, ACK-gated first publication, immutable historical receipts, terminal uncertainty/withholding, and checked Swift DTO/model/UI states. All five actions affect only synthetic phone selection/pinning/open state. The test-only bounded byte bridge exercises the checked Swift client/model through proof login and the actual native v4 owner/service child. No production controller, real content, Keychain, signing, live setup, external action, frozen fixture/adapter or publication changes are included.

Validation: the complete `tests/unit/test_phone*.py` suite passes 359 tests and 489 subtests with warnings as errors and no skips, using a freshly compiled native owner. PhoneCore passes 66 tests with no failures/skips, including the real process bridge. Exact copies of the unchanged native authority sources/tests in an isolated temporary Swift package pass all 24 authority tests with no skips. The unsigned generic iOS Simulator app and UI-test bundle build succeeds. UI test execution remains unrun: Xcode reports installed CoreSimulator 1171.7.0 older than required 1174.21.0; no compatible runner was available, and the inventory probe was bounded/stopped. This is build evidence, not UI runtime acceptance. The broader repository/app/integration CI, production usability and live release gates remain open.

The suite includes ordinary target/other-card edits and appearances around capture/effect/ACK/history, capability no-op/effective lifecycle and cached read/action invalidation, source classification gates, immutable receipt aliases, A/B and separate-login identity, pin/view capacity, preauthorization cancellation and postauthorization continuation/drain, actual-process repeated requests and lost release ACK, full-content joins and stale/reset response rejection. Existing R3.23/R3.24 and frozen S0 sensitivity/isolation regressions are included unchanged; exact full-vector replay count remains zero. Native source files and frozen fixture/adapter are preserved byte-for-byte.

Status: offline source candidate complete, pending independent immutable-source review; this is not source acceptance or permission to merge. The final commit/tree, exact path/mode/blob/SHA256 manifest, reproducible commands, scoped-copy hashes and complete logs are retained in the external `phone-card-source-<commit>` evidence directory. Next step: independent review of this immutable candidate, followed by coordinator-managed current-main reconciliation and remaining release gates. No public writes or merge were performed.


### Independent source-review corrections — 2026-10-31

**Historical checkpoint:** superseded by the final bounded source acceptance below; retain the original findings, counts and pending-review disposition as dated evidence.

Candidate `99341e11` was not accepted: independent review found five defects despite its green tests. The corrected candidate addresses all five within the same adopted 22-path scope, with failing regressions recorded before runtime fixes. (1) Standalone v4 tick/revocation/feature-disable dispatch obtains one owning authorization before polling commits, preserving queued cancellation and one frozen continuation during drain. (2) Shared terminal/reentry state is rechecked after ACK and after the publication gate, including historical replay; swallowed reentry produces terminal uncertainty/fencing and no success. (3) A registered projector's collection replacement atomically validates/moves its logical slot under R→P, rejects collisions before changing the grant/view, and retains the old capability's grant binding until explicit replacement. Same-projector reattachment reuses its single slot; another runtime cannot acquire it. (4) Context retirement includes the exact login incarnation, so denial of a stale reused session ID cannot remove the surviving new login's view. (5) Checked malformed/correlation/terminal Swift client failures mask content and view state; only transport failure retains inert content for explicit refresh.

The new regression evidence includes first and historical native ACK reentry, real v4 tick/notify/feature-toggle success controls, queued cancellation without authority frames, authorized poll drain, both collection-collision orders, stale-login survivor unpin, swallowed publication reentry, and malformed action/refresh masking versus transport-retention controls. The older boundary-only drain mock now explicitly declares its empty view/peer inventory; its cancellation observations and assertions are unchanged. Frozen fixture/adapter and all native sources/tests remain byte-identical.

Corrected validation: complete Python phone suite 367 tests / 495 subtests, warnings as errors, zero skips; full PhoneCore 67 tests, zero failures/skips; 24 scoped native tests, zero failures/skips; unsigned generic simulator app/UI-test bundle build succeeds. UI runtime remains unrun for the recorded CoreSimulator 1171.7.0/1174.21.0 incompatibility. This supersedes the earlier candidate's completeness/validation evidence, not the independent review gate: corrected source acceptance remains pending. Full-repository/integration CI, current-main reconciliation and production/live release gates remain open. No public writes, merge, signing, Keychain, controller or live action occurred. The immutable corrected manifest retains failing/passing review probes, complete logs, exact scope/blob/mode/SHA256 comparisons, and the unchanged native binary/source evidence.


### Terminal-denial precedence correction — 2026-10-31

**Historical checkpoint:** superseded by the final bounded source acceptance below; retain the original findings, counts and pending-review disposition as dated evidence.

Independent review of `8c2e49f0` confirmed the original five reproductions fixed but found a combined terminal path: publication reentry latched failure, then a source-change `CommandDenied` returned as ordinary withholding before the terminal check. New failing local and actual-native regressions cover first publication with ordinary revision change and historical replay with visibility denial. The correction gives the shared terminal latch precedence over publication-denial exits and funnels terminal denials through the same uncertain/no-receipt/fence path as other uncertain failures. The ordinary-change-only positive control remains terminal-withheld without fencing; subsequent native session status still succeeds. No effect is rolled back or retried.

Validation: full Python phone suite 369 tests / 501 subtests, warnings as errors and zero skips; full PhoneCore 67 tests, zero failures/skips; scoped native authority 24 tests, zero failures/skips. Two combined regression tests / six subtests are included in the Python total. The previous unsigned app/UI bundle build receipt is carried forward because all Swift/app/UI files remain byte-identical to `8c2e49f0`; UI execution remains unrun for the recorded CoreSimulator incompatibility. Full-repository/integration/live gates remain open.

The prior external manifest's claim_commit field contained a transcription error. The corrected manifest resolves and validates the claim directly from Git as the parent of the first source commit: `4bb67a50dc766f39905077020eb77cb6b77b36e8`. Its four-document diff and ancestry precede all implementation. Immutable prior review artifacts are retained; the new manifest supersedes their incorrect claim metadata. This correction changes only the service and its two existing test files plus the four claimed docs, within the original adoption. Corrected source acceptance remains pending independent review; no publication, merge or live action occurred.


### Typed phone-card bounded source acceptance — 2026-10-31

Independent review accepted exact source `a121dfb06385702b82a18041d7d974ab40877ee9`, tree `10b9b68d7a27d52ca2b54d42784326b5da279f86`, on `codex/ws04-ws17-ws30-phone-card-source-20261031`. There is no remaining actionable finding in the adopted synthetic/offline scope. The effective claim `4bb67a50dc766f39905077020eb77cb6b77b36e8` is resolved from Git as the parent of first source `99341e11`, not transcribed. The 22 source/test paths (WS-04/17/30: 7/4/11) and four claimed docs remain the complete typed-card delta from accepted design `ffb1b1cc`. No native owner or frozen fixture/adapter bytes changed.

The final independent actual-v4-owner probe combines publication reentry with an ordinary source revision change: empty-payload `unavailable` / `authority_unavailable`, ledger `uncertain`, host fenced, later status/retry denied, and no successful receipt. The earlier pin effect remains without rollback or retry. The ordinary-change-only control remains withheld without fencing; status works and explicit snapshot/view reconciliation reveals the retained pin. Earlier polling authorization, cancellation/drain, reentry, collection-slot collision, exact-incarnation retirement, malformed-response masking, five-action process, history/A-B, proof, recovery and frozen-regression controls remain green.

| Independent evidence | Exact result and boundary |
| --- | --- |
| Full `tests/unit/test_phone*.py` | 369 tests / 501 subtests, warnings as errors, zero skips; focused regression subsets are included. Standalone independent probes are recorded separately and are not added to these totals |
| PhoneCore | 67 tests, zero failures/skips, including checked five-action native proof-session bridge; byte-identical reviewed package with test root pointed at `a121dfb0` |
| Scoped native authority | 24 tests, zero failures/skips against this candidate's Python fixtures; five copied native inputs verified exactly |
| Native owner | Independently built unchanged owner SHA256 `ceed685e7495ed5dbeeac6b4c9c82f3df33e2d6aaf2d33540ed1ec4fa22a2360`; normal sandbox retained |
| Unsigned app/UI bundle | Independent successful build at `8c2e49f0` applies because all iOS/macOS bytes are unchanged; no new app build claimed at `a121dfb0` |
| UI execution | Unrun: installed CoreSimulator 1171.7.0 versus required 1174.21.0; compilation is not UI/usability acceptance |
| Broader gates | Full repository/integration CI, fresh public-main reconciliation, real controller/storage/content/transport, release and live acceptance remain open; exact frozen full-vector facade replay count remains **zero** |

Independent acceptance of `a121dfb06385702b82a18041d7d974ab40877ee9`, the Python/Swift/native logs and the carried `8c2e49f0` unsigned-build receipt are retained in the local review evidence. The immutable local source manifest has SHA256 `ce2f5141d9a91c78642b6a5812c3eeabc6b14b3f2f3eaba639ed1cc52d25f2aa`. Review verified all 2,186 distinct blobs, 12 artifact receipts and exact tree reconstruction. Source-versus-design counts are 3 added / 23 modified / 2,144 unchanged; source-versus-public-equivalent counts are 27 added / 21 modified / 2,122 unchanged, no deletions.

This finalization changes four documentation files only and preserves all accepted source. Its external `phone-card-final-<commit>` manifest records the docs commit/tree, complete path/mode/blob/SHA256 comparisons, evidence copies and local documentation checks. The published PR290 commit `39208d18d8c6fde0a9a0539e4d7c3aa68de5610f` is absent locally; cumulative comparison uses local `4e2152`'s verified equivalent tree `e31cdf9531908b0186d71d7af573da877e7b7eec`, without claiming public ancestry or freshness. Parent handles reconciliation and any later publication. No runtime tests are claimed anew for this docs-only finalization; no public write, merge or live action occurred.

The remaining product implementation and validation gates, their smallest next steps and genuine user/security prerequisites are audited in [phone-plan §19](MORTIMER_PHONE_ACCESS_PLAN.md#19-product-completion-audit--2026-10-31). That audit adds no runtime claim or new product scope. WS-17 source/release, WS-05 voice readiness, WS-24 durable-task recovery and live activation retain their existing ownership and boundaries.

## Offline proof-bound connection/context adapter — design candidate, 2026-10-31

**Historical design text:** revision `1db3ce4580273d1e576dd2c08b8eea025e1b1510` was independently accepted and its nine paths adopted before claim `f99e261b7d9e1afc4e3d7ba9ac5bf25ef79124b3`. Statements below about pending design review/source adoption describe that checkpoint. Current implementation evidence follows this accepted contract.

### Evidence, claim and intended exit

This is the next bounded implementation proposal identified by the independently reviewed phone-plan §19 completion audit. Documentation claim `507485720c9e7762d99df538a6ca8bc9ead618c8` precedes this appendix on `codex/ws04-phone-connection-design-20261031`, based on the separate wording correction `4deb20630196fecd7e6d8593c9597e69d8289d6d`. Accepted source remains `a121dfb06385702b82a18041d7d974ab40877ee9`; no runtime file changes in this design. The exact proposed nine-path inventory below is not editing authority. Independent design review and coordinator source adoption must precede implementation. This revision addresses the review of `6516a230`: atomic monotonic expiry, activation/timer arbitration and an explicit new-path recovery test driver. Correction `4deb2063` was accepted separately; the earlier design verdict was REVISE, not source adoption.

| Inspected accepted source | Concrete gap/reuse boundary |
| --- | --- |
| `phone_remote_login.py`, `PhoneRemoteLogin.complete_login` | Verifies the enrolled P-256 proof and calls exact `store.login_proof` through `session.login`; currently discards its returned login incarnation and exposes only `LoginSession(session_id, expires_at_ms)` to the trusted caller. Preserve this existing API and proof semantics. |
| `phone_admission_store.py`, `login_proof`, `current_binding`, `binding_current` | The first returns the actual committed incarnation. The latter two verify the complete session/owner/device/grant/generation/process-epoch/scope binding. Reuse unchanged; do not reconstruct an incarnation from counter fields or query by a client-provided session ID. |
| `phone_remote_service.py`, `TrustedRequestContext`, constructor, `_AuthorityChildServiceHost` | Context is currently a server-injected dataclass accepted only by exact `FakeContextVerifier`; one worker owns SQLite/native grants. The v4 observer distinguishes preauthorization cancellation from frozen authorized continuation and enforces the existing recovery drain. |
| `phone_remote_asgi.py`, `PhoneRemoteASGI` | Requires injected context provider before WebSocket acceptance and uses bounded off-loop service calls. It has no proof handshake, retained connection registry or authenticated construction. Its injected path and tests remain supported exactly. |
| `test_phone_remote_authority_service.py`, `_authority_child_card_entrypoint` | Completes a real proof, then reads fixture `anchor.json` and manufactures `TrustedRequestContext` from fixture owner/device plus host-generation/login-counter. That is a valid existing test seam, not an authenticated connection construction path. |
| Native owner / v4 channel | Native entry remains `--test-owner`; exact method allowlist permits proof-backed `session.login`, not direct `store.login`. The new adapter can use existing grants without a native/channel/schema change. Recovery-owned shutdown/reap has the accepted five-second drain; normal test-owner exit is not a new connection shutdown guarantee. |

**Exit:** an in-memory ASGI client supplies only enrolled device/grant selectors and a signed challenge proof; the child derives the complete context from verified admission, then serves status and synthetic snapshot/view/five-action requests through the actual native v4 owner. No fixture supplies a context, identity, incarnation, session token or anchor-file-derived binding to this new path. A revoked, expired, foreign, retired or substituted connection cannot execute or receive a successful result. This closes the proof-to-request binding seam, not production controller authentication, protected storage, enrollment, real transport or content readiness.

### Decisions and boundaries

1. **One proof login per transport lifetime; no reconnect token.** A connection owns a fresh random server challenge and one admitted login. Reconnect requires a new proof, new server-generated session ID and new incarnation. A bearer session-ID endpoint or transferable post-login token would introduce custody, replay and recovery obligations outside this slice, so neither is added. Loss of a login reply never authorizes automatic login/action retry.
2. **Separate private constructor/factory; preserve exact fake constructors.** Add an owner-controlled proof-connection composition for the exact v4 child. Do not replace `type(verifier) is FakeContextVerifier` with a protocol/duck-type or public union accepting arbitrary callers. The existing public fake constructors, v1/v2/v3 behavior, injected ASGI provider and old tests retain their behavior. The new private branch accepts only its exact concrete registry/verifier and unexported construction capability, with identical store/anchor/coordinator ownership checked. Subclasses and a registry from another child are rejected.
3. **No context comes from ASGI scope or phone bytes.** `scope.state`, headers, cookies, query strings, remote address, claimed client identity and request payload cannot supply an owner, grant authority, session/incarnation, ticket, binding or connection handle. Device/grant strings in the challenge request are selectors only; the existing authority resolves owner/key/scopes. A validated public-key proof is the only new login path. Python object capability checks protect the trusted application seam; they do not authenticate hostile code executing inside the child process.
4. **A distinct preauthentication envelope on an unmounted factory.** Reuse `/ws/phone-remote` only in an explicitly constructed in-memory proof adapter. Existing `mortimer.phone-remote.v1` operations and parse/response schemas stay unchanged. Accepting a WebSocket for the bounded proof exchange grants no data-session privilege. The existing injected adapter still requires context before its accept. No bot mount, HTTP endpoint, TCP listener, TLS setting, origin policy or client credential store is added.
5. **Cards/status only for the new end-to-end proof.** Reuse the existing synthetic projector/capability registration. Do not add card actions or content authority. This adapter never issues a voice ticket: `voice.offer`/`voice.update` receive existing content-free `denied/not_authorized`, and no media is prepared. Other valid existing operations use their existing service dispositions (including unavailable call operations); no new voice/call readiness is asserted. Existing injected-context voice tests remain unchanged.

### Concrete trust objects and clock ownership

`phone_remote_connection.py` will contain the exact private registry, opaque lease, verifier and handshake codec. The owner creates one registry for one `_AuthorityChildServiceHost`/v4 anchor/`PhoneRemoteLogin`/service runtime. It is never constructed from a request. At most **64 total live records**, including unauthenticated, activating, active and retiring records, exist per host; no active record is evicted to make space. Existing login caps of 64 challenges and four per device remain independent and unchanged. Their tombstones/failed-proof budgets are not reset by closing a transport.

Opening an ASGI invocation creates two nonserializable identity objects: a registry-issued `ConnectionLease` and a transport-owner token retained only by that invocation. Registry membership must point to the exact lease object, issuer and token; copied dataclass values, equality lookalikes, foreign-host handles and A's handle with B's token fail. Claiming an already claimed lease for another invocation fails. No handle/nonce used for this local capability crosses the phone wire, appears in a returned DTO or is accepted from scope. Tests may observe redacted state/counters through trusted fixture code; neither fixture controls nor arbitrary host methods enter the handshake dispatch map.

The private host API is closed: `open_connection(transport_token)` returns only a registered lease; `connection_challenge(lease, transport_token, device_id, grant_id, _cancel_event)` returns a checked challenge or local failure; `connection_prove(lease, transport_token, challenge_id, proof_bytes, _cancel_event)` returns only a local phase-complete marker after registering the sealed admission; `activate_connection(lease, transport_token, _cancel_event)` returns the checked authentication DTO; `handle_connection(lease, transport_token, raw, _cancel_event)` returns a private one-use `ConnectionReply` containing the validated business response and its captured permit/deadlines; `claim_connection_reply(lease, transport_token, reply)` returns its already validated encoded bytes only after the final egress guard; `close_connection(lease, transport_token)` retires local state and signals its owned call. No admission descriptor or context is returned by these methods. `ConnectionReply` is a server-only registry-issued identity object, not a phone DTO: copies, foreign/reused replies, modified bytes or a reply from another lease/request fail. The activation DTO also uses this egress claim; its handshake bytes use the new codec, while business bytes use the unchanged protocol codec. Token/lease identity is checked before queue admission and again on the worker. The ASGI object invokes prove then activate explicitly; no wire operation can select an internal method. Local open/close and reply claim are bounded registry operations (reply claim also holds the proof clock guard); challenge/prove/activate/handle are serialized worker submissions. The close signal does not wait while holding a lock; the invocation separately joins its owned dispatch completion.

Each admitted record retains: issuer/coordinator/owner-child incarnations by identity; the exact current `SessionBinding` tuple (owner, device, grant, session, login incarnation, host ID/generation, grant generation, session generation, process epoch, immutable scopes); one canonical `ClientIdentity` and one canonical `TrustedRequestContext` with `ticket_id=None`; login expiry and monotonic expiry; record state; its active owned-request reference/cancellation signal. All are server-only. Registry membership alone never supersedes current store authorization.

The factory owns a concrete synthetic clock pair, rather than using the current service's default monotonic seconds as a login wall clock. It creates exact `LoginClockGate` and exact `FakeClockGate` objects and one private immutable clock image `(wall_ms, monotonic_ms, version)`, protected by the **service-clock lock F**. The fixture updater acquires **login-clock L → service-clock F**, then updates both gates and replaces that image in one critical section, with service seconds equal to `wall_ms / 1000`. An updater waiting for F has not committed a clock advance. It calls no host/store/registry/user code. Inputs are exact nonnegative integers within the proof time bound; monotonic time cannot decrease. Direct `FakeClockGate.set_time` or inconsistent injection in this proof composition is unsupported: mismatch between F's wall value/version and the private image fails closed, rather than silently dropping the monotonic check. Legacy fake-mode clock behavior is unchanged.

Service-side proof guards acquire **F only** and read the image already protected by F; they never acquire L or call `LoginClockGate.snapshot/commit_guard` from an F-held path. The updater's L→F order therefore has no F→L inverse. The sealed proof admission retains the commit wall/monotonic values and immutable exact-integer wall/monotonic expiry. Active eligibility requires both `image.wall_ms < expires_at_ms` and `image.monotonic_ms < monotonic_deadline_ms`, where the latter is commit-monotonic plus the existing 12-hour lifetime. Wall rollback cannot extend that deadline. Store wall-time checks remain an additional unchanged condition, not the implementation of monotonic expiry. There is no request-accessible clock control, store schema change or production clock integration.


### Closed handshake framing and outcomes

Proposed protocol name **`mortimer.phone-connection.v1`** and operations **`auth.challenge`**, **`auth.prove`** are design candidates, not current reservations. On source adoption record them in ROADMAP §3 before code. They are not added to the `mortimer.phone-remote.v1` inventory. No new setting, port, migration or native operation name is proposed.

Every handshake request has exactly `{protocol, request_id, operation, payload}`. `protocol` is the exact new name; `request_id` is a nonempty valid UTF-8 string of at most 128 bytes. IDs for challenge and prove must differ. One text frame with exact `str` or one binary frame with exact `bytes` is allowed, never both. UTF-8 is strict, no BOM, duplicate keys at any level, NaN/Infinity, invalid scalars, unknown keys or trailing JSON. Entire preauth frame is at most **8,192 UTF-8 bytes**, maximum JSON nesting depth four. No coercion, trimming, case folding or float-to-int conversion. Validation completes before any host submission.

| Frame | Exact payload and result |
| --- | --- |
| `auth.challenge` request | `{device_id, grant_id}`; each is an exact nonempty UTF-8 string, at most 128 bytes, equal to its stripped value. They select an existing enrollment/grant only. Unknown, revoked or mismatched selectors disclose no owner or key. |
| Successful challenge response | The response payload is exactly the existing nine `ChallengeResponse` fields: `protocol`, `purpose`, `challenge_id`, `challenge_nonce`, `service_id`, `host_id`, `enrolled_key_id`, `authority_generation`, `expires_at_ms`. The nested protocol/purpose remain `mortimer.phone-auth-proof.v1` / `phone.session.create`; canonical base64url/integer/identifier rules and signature transcript are unchanged. The connection records the exact challenge ID before output. |
| `auth.prove` request | `{challenge_id, proof}`; ID is canonical unpadded base64url for 16 bytes and must equal this connection's issued ID. `proof` is canonical unpadded base64url encoding of **1–4,096 original proof bytes**, decoded without JSON reserialization and passed to the unchanged verifier. Encoded length is at most 5,462 characters. Extra identity/context/owner/scope/session/credential/ticket fields reject. |
| Successful prove response | Exactly `{authenticated: true, expires_at_ms: <exact integer>}`. No session ID, context, login incarnation, scopes, owner or bearer credential. This acknowledges a completed proof admission/binding at its verified activation boundary; it does not promise future authority or delivery of later operations. |

Responses have exactly `{protocol, request_id, status, reason, payload}`. Success is `ok/none`; errors have empty `{}` payload. Error pairs are only `denied/invalid_request`, `denied/not_authorized`, `unavailable/capacity`, `unavailable/authority_unavailable`. A safely validated request ID is echoed; otherwise it is JSON null, allowed only for an error. Challenge and proof outputs are validated before encoding. Existing numeric bounds apply: booleans/floats are not integers, authority generation is 1…2^63−1 and expiry is 1…2^53−1. Do not log selectors, challenges, proofs, raw frames, session IDs, context or exceptions.

Only one challenge request and one proof attempt are accepted per connection. Invalid proof, replay, expired challenge, selector rejection, wrong phase or malformed frame yields at most one content-free error and terminal close; no handshake success cache or repeated mutation. Other existing private login callers keep their current three-failure behavior. Map `LoginFailure(proof_rejected/challenge_unavailable/not_authorized)` to `denied/not_authorized`; `capacity` to `unavailable/capacity`; `busy/unavailable` and authority exceptions to `unavailable/authority_unavailable`. Do not reveal which selector or proof field failed.

Before accept: HTTP still returns 404; wrong path, non-exact enabled flag, foreign/unprepared host, disabled/quiescing/fenced authority or no capacity closes with 1008 without reading login payload. After accept: policy/framing/authentication/capacity failure closes 1008; internal/authority/busy/deadline failure closes 1011. No exception text is sent. Unknown version or a business request before authentication is terminal, not a protocol downgrade. An authentication envelope after activation is also terminal; malformed ordinary operation frames retain the existing content-free protocol response behavior.

### State machine: proof receipt is not a reusable context

| State | Allowed transition and exact failure behavior |
| --- | --- |
| `opened` | Server has reserved a lease, checked exact gates, and accepted only the handshake transport. A **60-second monotonic deadline from lease creation** covers the whole handshake; issue/retry/busy waits never extend it. One valid challenge request enters `challenging`. |
| `challenging` → `challenged` | Owned worker calls existing `session.challenge`; only a verified successful release and exact `ChallengeResponse` permit storing its ID and output. If transport closes first, retire the local record and challenge, emit no late response; no session exists. |
| `challenged` → `proving` | Validate same-lease challenge and frame. Reserve the proof attempt once before verification or any await. Existing signature/context/deadline validation and `session.login` mutation run exactly once. A duplicate/reentrant attempt is terminal for that lease and never invokes login twice. |
| `proving` → `binding_pending` | Capture the actual incarnation returned by `run_store_operation("session.login", store.login_proof, …)` only after its verified release ACK. Keep a private sealed admission with coordinator/child identity, challenge-derived owner/device/grant/key/generations/scopes, generated session ID, returned incarnation and commit/expiry times. A private common login helper supports this path while public `complete_login` still returns the unchanged `LoginSession`; there is no second proof execution. |
| `binding_pending` → `active` | A **separate owned submission**, admitted afresh, consumes that exact coordinator-issued admission once for this lease. Call existing `service.authorize/current_binding` using server-derived values. Require full current binding and agreement with the admission's owner/device/grant/host/grant-generation/scopes, current process and child. After verified release, apply the activation/expiry guard and timer arbitration below: require the existing concrete owner-availability gate ready for the derived owner, then F → H → C for exact clock, terminal, feature/quiescence, transport and preauth-state checks. In this local critical section install canonical context/full binding, change to `active`, invalidate the handshake timer epoch and create the one-use activation reply. No native/store call occurs under H/C. No client success is sent between proof commit and activation. |
| `active` | Sequential business dispatch through the connection host only. No reauthentication or handle transfer. Each operation revalidates store authority and the complete captured binding before reserving/effecting a request. Existing service authority, receipt, source-classification and result-capability checks remain required; the proof-mode lifetime guard below is an additional condition at authorization, effect, publication and replay. The original fake path remains unchanged. |
| `retiring` → `closed` | Immediately refuse new/queued work and suppress new output, retain any owned continuation until its terminal bookkeeping, then remove exact-lease state and drop sensitive references. Closed handles never become valid again, even if Python object IDs, session IDs or fixture selectors are reused. |

The private sealed admission is not exported by the legacy `complete_phone_login` API, returned over ASGI or accepted from callers. It is registered by exact object identity with the issuing coordinator and bound to one lease before use; copies, reuse, a descriptor from another coordinator or a legacy `LoginSession` fail. Capture the actual returned incarnation as an opaque string: do not split it, concatenate host/generation/counter, inspect an anchor file, trust a `read_status` counter, or recover a context by looking up an untrusted session ID.

If login commits but its native ACK is lost, there is no sealed admission; existing terminal uncertainty/fencing applies, with no activation or claimed rollback. If login succeeds but the fresh activation is cancelled, quiesced, denied or unavailable, the transport remains unauthenticated and closes. The committed session may remain unused until expiry/revocation; no compensating database mutation or automatic proof retry is invented. Native authority failure is terminal; ordinary current-binding denial retires only that lease. A lost ASGI success send retires the lease and does not export a reconnect credential. A new connection must prove a fresh challenge.

Activation's verified current-binding release is its authority read boundary; the later F→H→C state transition is the activation-versus-timer linearization point, and the one-use reply claim is its egress boundary. All three must succeed before a success can be sent. A later revocation can race the transport send; the acknowledgement attests the completed admission, not an enduring grant. The first and every later business request must reauthorize. Tests must cover revocation before the read, after verified release and before send, and immediately after send; no data/effect may rely on the handshake acknowledgement alone. Already emitted bytes cannot be recalled.

### Request verification, lock order and transport lifetime

The new factory in `phone_remote_asgi.py` requires the exact private connection-enabled host and exact `enabled=True`; both factory/host modes default disabled. It does not accept a `context_provider`. Internally it reuses the existing bounded off-loop machinery (four shared dispatch slots per event loop), but invokes a closed host API with its lease and transport token instead of taking a context from scope. Wire operations cannot select `_AuthorityChildServiceHost._METHODS`, issue tickets, mutate authority, set clocks/feature flags, trigger recovery or select fixture controls.

For `handle_connection`, the worker creates a one-use request permit tied to the exact `_OwnedCompletion`, lease, canonical context and immutable full binding. The exact proof verifier accepts only that context object while this owned request is current; hand-constructed equal contexts, public `host.handle(raw, context)` on the proof-mode host, subclasses and calls outside that permit deny before authority. After existing `current_binding` returns, the service compares **every field** with the captured `SessionBinding` before ledger reservation. The original fake path is unchanged. The permit is cleared in `finally` after actual worker bookkeeping, never merely when a cancelled caller is settled. For a request rejected before enqueue or removed from the queue, the worker-finished observation is settled explicitly as never-started; it must not wait for a worker that will never consume it. A removed queue item cannot retain a valid permit. A frozen authorized continuation uses its captured permit; it cannot be borrowed by another submission.

### Atomic lifetime guards and lock order

The immutable request permit includes the exact wall and monotonic deadlines plus the clock-controller identity. Implement one concrete internal proof-lifetime predicate in the service/connection paths; it reads only the F-protected clock image and permit, not callbacks or registry-derived replacement values. Apply it at every boundary below, including read-only successes. Missing, inconsistent or foreign clock/permit state is authority uncertainty; a valid clock reaching a known deadline is ordinary expiry.

| Boundary | Atomic check and result |
| --- | --- |
| Dispatch/authorization | Check both deadlines under F before acquiring authority and again after the current-binding read/release, before ledger reservation. This blocks already expired work without a mutation. Clock advancement after this guard is possible, so this check never substitutes for commit guards. |
| Fresh effect or view reconciliation | Inside the existing `service.clock.commit_guard()` **after its pre-commit barrier and before any view reconciliation/effect**, compare the current F image against the captured deadlines, then perform the existing binding/capability/classification checks. Hold F through the effect's atomic interval and existing terminal bookkeeping. An expired permit produces content-free `denied/not_authorized`, no effect and no successful receipt, without fencing unrelated B. |
| First successful receipt publication after native ACK | Recheck deadlines under F before making a candidate eligible/`done`. The existing card path already holds F across effect, native ACK and first publication; preserve that coverage and recheck explicitly at publication. A paired clock update cannot linearize while that F interval is held. If a future refactoring separates these intervals, it must reacquire F **outside** existing authority/runtime/projector locks and repeat all publication predicates; no source-lock-order change is authorized by this design. |
| Historical successful receipt replay | Check deadlines under F at replay revalidation and again at response publication, alongside the existing current binding and historical visibility rules. Expired replay gives no payload/effect and cannot restore receipt eligibility; retain the original historical record rather than rewriting or reexecuting it. |
| Final egress of status, snapshot/resume, view/action or activation success | After the owned service work, `claim_connection_reply` takes F → H → C, checks both deadlines against the current image, exact live lease/reply membership, host terminal state and transport cancellation, and atomically consumes the one-use reply for egress. It invokes no codec/callback/send under these locks: bytes were validated/encoded before the claim. A clock advance after service receipt publication but before this claim suppresses success even if wall time was rolled back. Error/retirement bookkeeping follows after locks release. |

**After-effect outcomes are explicit.** Known expiry before the first successful receipt is published keeps any already completed effect, marks a fresh request `withheld` with content-free `unavailable/authority_unavailable`, and retires that lease; it does not roll back, retry or globally fence. If a `done` receipt already exists and expiry wins before egress/replay, retain that historical receipt internally but discard this delivery and close/deny the expired lease; no successful bytes are claimed. A lost native ACK, malformed clock image, reentry or latched authority failure instead keeps the existing `uncertain`/fence behavior, which takes precedence over expiry/ordinary withholding. Exact effect count and independent B behavior must distinguish these cases.

The egress claim is the response-publication linearization point: no new successful egress claim may occur at/after either deadline. ASGI suppresses delivery if transport cancellation is observed before starting send. If expiry/revocation happens **after** a successful claim, that already admitted response may be in flight; no promise to recall bytes or atomically lock an asynchronous network send is made. Subsequent requests/claims still fail. This is not permission to reuse a dispatch-time clock snapshot or queue an unclaimed success past expiry. A reply is consumed once and cannot be retained as a reusable publication capability.

Let H be the host admission lock, C the registry lock, L/F the paired clock locks, A/S the existing authority/store locks, R the runtime lock and P/source the projector/source locks. The allowed new nesting is **L→F** for clock update, **H→C** for local enqueue/open checks, and **F→H→C** for local activation/egress checks. H/C sections never acquire F, L or authority/service locks, wait for a worker, or call receive/send/user code. Ordinary registry capture takes C alone and releases it before service work. Service-side lifetime predicates use F and captured immutable values only: they never acquire L or C while in existing effect/ACK/publication blocks. F remains outside the existing service/authority/runtime/projector critical sections; keep each existing branch's internal order (in particular card F→R around its authority transaction, and R→P→source publication). The existing authority observer's brief H check does not enter C/F/L or wait for work. New cleanup/registry mutation is deferred until those service locks release. Reentry latches failure before any outer success; terminal failure still overrides ordinary denial. These rules prevent both F→L inversion and C→F/H cycles.

### Handshake timer arbitration and transport lifetime

At lease creation capture both a real event-loop monotonic deadline (`loop.time()+60 seconds`, with the corresponding system-monotonic comparison used by the worker) and the synthetic monotonic deadline, plus a unique handshake epoch. The real timer is armed once, never extended by challenge/proof/busy activity. It prevents a frozen fixture clock from retaining an idle preauth connection. Neither timer is an active-session idle timer.

After verified activation authorization, the worker's F→H→C activation section requires `binding_pending`, the same lease/transport/handshake epoch, both preauth deadlines still strictly in the future, both session deadlines valid and no cancellation/terminal state. It then atomically changes state to `active` and invalidates the handshake epoch. Schedule cancellation/disarming of the event-loop timer outside the locks. Cancellation alone is insufficient: a callback already queued captures the old epoch and, under C, may retire/signal cancellation **only** if the lease still has that epoch and a preauth state (`opened`, `challenging`, `challenged`, `proving`, `binding_pending`). `active`, retired/closed and epoch mismatch are no-ops; a stale callback must not set the connection cancellation event or close its transport.

If the timer wins C first, it retires preauth state and signals the owned request; later activation cannot publish success. If activation wins strictly before both deadlines, a queued callback cannot undo it. Activation at or beyond a real/synthetic deadline fails even if the timer callback has not run yet. Synthetic preauth expiry obeys the same state/epoch rule; after activation only the independent wall/12-hour monotonic session deadlines apply. An authenticated connection remains usable after 60 seconds while its session is valid. There is no active idle timeout in this slice.

Preauth expiry during an already owned login mutation suppresses output and joins the worker; it cannot undo that mutation. Active expiry is checked at the guards above, not by reusing the handshake timer. Pruning retires expired records but retains capacity and references for any unfinished owned continuation.


Each ASGI invocation owns a sole receive task, one pending-frame slot, a dispatch task and the lease. The receive task observes disconnect even during a blocking service operation, sets the connection cancellation signal, discards queued input and stops new output. One queued frame may wait for the preceding response; a second queued frame closes 1008, preventing unbounded pipelining. This permits a legitimate client to send its next frame as the previous send completes. Authentication and operation size limits apply before queueing. No concurrent `receive` calls or overlapping business dispatch on one connection. Cancellation of the invocation owns and joins/cancels its helper tasks; it does not abandon thread work or release a shared dispatch slot while that worker still owns a continuation.

Wire disconnect/task cancellation signals the same exact `threading.Event` observed by `_submit` and worker preauthorization. Before enqueue, while queued or before authorization: remove/deny locally with **zero authority acquisition and zero effects**, including deterministic fast-worker races. After verified authorization: suppress new transport publication but let the owned continuation settle under existing commit/ACK/uncertainty rules; do not relabel it rolled back or rerun it. Add an explicit worker-finished completion observation separate from early caller settlement, so the new ASGI adapter retains its dispatch slot and retiring lease until the actual worker finishes. The host remains the owner even if the caller has already received cancellation. A done receipt may exist internally although its network send was lost; identical retries on the same still-live connection retain existing receipt behavior, while a retired connection cannot retrieve it.

Disconnect is local transport retirement, **not** session sign-out, global quiesce or a recovery request. It drops only this connection's registry/permit references after work finishes; it does not delete another incarnation's mobile view, revoke a grant or clean a newer login sharing a session ID. Existing bounded view/receipt registries retain their authority-owned entries and normal limits; they are not migrated onto a reconnect. Known expiry/revocation denies further dispatch and retires the affected lease; feature-off closes all proof leases for this host. There is no new heartbeat/push erasure guarantee; inactive closed/expired records are pruned on local registry operations, and transport-retained private state is dropped on terminal close.

Owner-triggered R3.24 quiescence still closes new admission and queued work, permits only already authorized continuations, and uses the existing **single nonextending five-second deadline**. The proof and activation phases do not count as one frozen authorization: activation is fresh work and must be rejected if quiescence won after login. No connection timer resets that deadline or invokes restore. Unknown/overdeadline work settles callers without a drained ACK; the existing recovery owner performs bounded owned-child termination/reap and no recovery mutation follows uncertain drain. Ordinary disconnect introduces no separate five-second shutdown promise: the normal test-owner exit path is not equivalent to recovery-owner reap. Test cancellations use finite controlled operations, while the actual overdeadline/reap matrix runs under the existing recovery-owner harness. A blocked worker must remain owned, never reported drained just because its caller returned.

### Explicit recovery-owned driver for the new proof/card path

C12 must exercise this new adapter under the **actual recovery-owned lifecycle**, not merely rerun existing recovery tests. Native `spawnChild` hardcodes `python -m tests.unit.test_phone_remote_recovery --recovery-child <database>` for recovery configuration; the existing normal-mode entry point constructs a fake-context host. Preserve both files unchanged. Implement the following private test route entirely in the already proposed `tests/unit/test_phone_remote_authority_service.py`:

1. The test creates an owned mode-0700 temporary launcher from a fixed, hashed Python script template, with the exact isolated interpreter in its shebang, and passes its path through the existing `--test-owner` **python executable argument**. The launcher accepts only the exact native-generated `-m tests.unit.test_phone_remote_recovery --recovery-child <owned disposable database>` argument shape. It validates the owner-supplied recovery config and inherited channel/lock descriptors 3/4 (and source descriptor 5 where applicable). No arbitrary module, shell command, phone selector or production path is accepted. It runs in the same native-owned child PID with the same descriptors and cwd: no proxy process, subprocess respawn, fd release or lock bypass.
2. For every config except the explicitly targeted `mode == "normal"` **and** exact `exercise_drain == true`, call the **unchanged** `_recovery_child_entrypoint` from `tests.unit.test_phone_remote_recovery` in that same process, including the final post-recovery normal activation. For that targeted normal config, dispatch to a fixed new test function in `test_phone_remote_authority_service` that constructs the proof-enabled host and in-memory ASGI client, using the proposed paired clock and disposable key. Select existing `r324-drain-*` test failpoints so the native owner actually services proof/card grants until the `.activity` marker and then enters its real drain loop; do not issue new test grants in a final normal activation where the owner is not running that exercise loop. This is local test routing only, not a new native/config/wire mode or production factory privilege. The driver writes a content-free marker with its PID, mode, proof-adapter route and case; assert its PID equals the native owner's `.pid`/reap record. Run the original recovery module separately unchanged as a positive compatibility control.
3. Reuse the existing recovery fixture preparation, adding `action` to the **disposable preprovisioned** current grant before the owner starts, with an ephemeral fixture public/private key pair and synthetic ordinary collection/capabilities. No live grant changes. The client conducts the actual new challenge/prove/activation handshake and snapshot/view requests, then a typed card action. It neither constructs a context nor reads an incarnation/counter from fixture storage. Test controls live in a private fixed-schema fixture file, never in ASGI bytes or context.
4. For the authorized-continuation cases, pause the **new card request** at the existing pre-commit boundary after verified authorization and write the existing content-free `.activity` marker that lets the native recovery owner proceed. Read its exact `quiesce-*.request` operation ID/deadline; invoke the existing `host.quiesce(..., _owner_deadline=...)`. Observe quiescing before releasing the card barrier. Emit `.outcome`/`.terminal` only from actual worker/host completion, and use the unchanged `host.shutdown()` handshake. Keep inherited fd4 open until the native owner confirms reap. Stalled/lost-ACK/lost-shutdown cases suppress those success markers and preserve the owner's existing bounded failure/reap evidence.
5. Use separate fresh owner runs for queued/preauthorization work and the **proof-committed but activation-not-submitted** gap. These are controlled on the new ASGI/host path; after the actual owner drain begins, release the pending attempt and verify it is refused with no new authority grant/activation/effect. A test-only `.activity` coordination marker for these cases records `authorized:false` and the exact phase rather than falsely claiming an authorized continuation. The new dispatcher consumes no extra native authority protocol names. Repeated quiesce calls carry the same operation ID and cannot move its deadline.

Required case outcomes: timely authorized pin finishes exactly once before successful drain/recovery; queued action and post-login activation never enter the frozen set; stalled/ACK-loss/child-failure cases have no false terminal/drained success and no restore mutation, with singleton lock retention and **the actual new-path child PID** confirmed reaped. Cover ordinary successful proof/card operation in the recovery-owned normal child as a positive control before inducing failure. Timeouts or fallback to the old fake-context child cannot be counted as coverage. If the fixed launcher cannot preserve the native argument/fd/PID contract on the approved test environment, report that concrete blocker and request a test-path amendment before code; do not edit native authority or weaken C12.

### Positive, adversarial and process acceptance matrix

| ID | Required regression and observable result |
| --- | --- |
| C01 construction | Exact fake constructors/providers still pass existing suites. New mode rejects wrong anchor versions, subclass/duck verifiers, wrong store/anchor/coordinator, foreign registries/leases, truthy non-bool gates and unprepared hosts; default-disabled path touches no authority beyond already authorized fixture startup. |
| C02 native happy path | Actual v4 owner plus disposable DB/file protected anchor, ephemeral P-256 key and in-memory ASGI: challenge → signed proof → verified activation → status → synthetic snapshot/view → each of five actions. Server-derived owner/device/grant/incarnation/full binding match admitted store state. No test creates `TrustedRequestContext` or reads anchor counters for this path. Assert existing proof-only native grant methods and no real socket listener. |
| C03 parser/schema | Byte/depth/identifier/base64 boundaries, duplicate keys, BOM/invalid UTF-8, nonfinite/floating/bool integers, changed protocol, extra identity/ticket fields, text+bytes, binary/text positives. Validly signed proof bytes are preserved exactly; invalid input causes no login/effect and no content/exception echo. |
| C04 phase/replay | Prove-before-challenge, repeated challenge, repeated/proving reentry, mismatched challenge ID, A proof on B, post-auth handshake, replay after success/close, invalid signature/key/service/host/generation/expiry. One attempt at most per connection; native counter does not advance twice; retain existing standalone three-failure/login tests unchanged. |
| C05 activation gap | Cancel/close/feature-off/revoke/quiesce between proof commit and fresh activation. No authenticated success or usable context; known denial leaves unrelated B usable. Lost native login or activation ACK fences with no context; no automatic retry/compensating mutation. Separately test lost ASGI acknowledgement after successful activation and fresh-proof reconnect. |
| C06 full identity | Mutate each expected binding component independently; substitute equal-valued context/identity, copy lease/permit, cross host/store/child/process, transfer A handle with B token. Deny before effect. Same textual session ID reused after prior retirement must not let old lease retire, inspect or change the new incarnation's view. Test same owner/two logins and different owner/device/grant. |
| C07 revocation and time | Device/grant/session revocation, scope/generation change, child restart, feature-off, owner unavailable and expiry. Deterministically pause after authorization/preparation at the existing pre-commit barrier, roll wall time back while advancing the F-protected monotonic image to/beyond session expiry, then release: zero effect/receipt/output, B remains usable. Same race at one millisecond before expiry succeeds exactly once. Repeat for first publication, historical replay and final egress. While the existing effect→ACK→publication F guard is held, prove an updater blocks (no F→L inversion); advance immediately after release and before egress: effect/history retained, no new success claim. Cover known post-effect withholding versus lost-ACK uncertainty/fencing, forward-wall expiry, exact boundaries, nondecreasing monotonic and inconsistent-image rejection. Legacy fake-clock behavior stays unchanged. |
| C08 cancellation | Pre-submit and queued fast-worker signals, worker preauthorization, after authorization, after effect and ACK/send loss. Assert authority-frame/effect counts, original effect/uncertain receipt semantics, no late transport publication begun after cancellation, no detached worker or early slot release. Cancellation does not imply rollback. |
| C09 transport ownership | Two ASGI connections, bounded queue/overflow, blocking receive/send, disconnect during proof/activation/action, repeated cancellation and loop shutdown; no detached task/worker, early slot release or stale permit. Timer cases: activation strictly before deadline; old callback already queued when activation wins; callback wins before activation; activation at deadline before callback runs; stale callback after active; authenticated status/card still usable after 60 seconds. Assert epoch/state, cancellation flag, close count and native grant/effect counts. Ignore spoofed scope/header/cookie/query authority. |
| C10 capacity/isolation | 64 global records, existing 64 challenge/four-device limits, closed-record cleanup and nonreused handles. Busy rejection is content-free and not a host fence. Unknown selector failure does not disturb B; callback/reentry errors do not turn outer failures into success. No new unbounded registry, response cache or transcript log. |
| C11 results receipts | Existing snapshot/view content join, view-first conflict, capability lifecycle, classification, historical replay and A/B card controls run through the new proof path. Repeated request ID/same payload within a live lease has one effect; changed payload conflicts. Reconnect is a new login/mobile view, never implicit action replay. Source change alone withholds without fencing; combined terminal reentry still fences/uncertain. |
| C12 drain/recovery process | Actual recovery-owned v4 process: authorized card work during quiesce completes within the original deadline; queued/preauthorization and post-login activation rejected. Repeated drain does not extend deadline; overdeadline/lost ACK/child failure gives no false drained ACK or restore mutation, with owned-child reap evidence. Use the explicit same-PID temporary launcher/new normal-child proof→ASGI→card driver above with the unchanged recovery owner. Assert the targeted initial normal child's new-path route marker and owned PID against its native quiescence/reap records; later unchanged recovery/final-activation children are identified separately. Old fake-context recovery tests alone do not satisfy this row. Normal disconnect still does not activate recovery. |
| C13 preservation | Full existing proof, v1/v2/v3/v4 channel, store, recovery, results, card, ASGI cancellation, six-case refinement and A/B regressions. Frozen oracle/adapter/native/Swift bytes unchanged. Existing 70-vector fixture remains frozen; this new matrix is not exact full-vector conformance. |

Standalone independent probes are reported separately from pytest test/subtest totals. Run all `tests/unit/test_phone*.py` with warnings as errors and a fresh independently verifiable native owner, then the existing PhoneCore and scoped native authority tests against exact unchanged copied sources and this candidate's Python fixtures. Record commands, environment/dependency provenance, counts/skips/failures and owned-process cleanup evidence. Use the isolated approved temporary Python environment and normal sandbox/temporary Swift caches. No new iOS runtime/UI claim follows from Python tests; existing iOS 17 deployment minimum is unchanged. Full repository/integration CI and source-current-main reconciliation remain aggregate gates, not closed by this slice.

### Exact proposed source scope, work order and open review points

Nine source/test paths: **seven existing, two new**, all WS-04. No source is adopted by this document.

| Path | Bounded proposed edit |
| --- | --- |
| new `jarvis/bot/phone_remote_connection.py` | Closed handshake codec, exact owner registry/leases/verifier, sealed binding orchestration and concrete paired fixture-clock controller; no network client/server mount. |
| `jarvis/bot/phone_remote_login.py` | Private common proof-completion path retains actual returned incarnation and sealed admission provenance/times; unchanged public `LoginSession` API and proof behavior; exact challenge retirement. |
| `jarvis/bot/phone_remote_service.py` | Private proof-mode construction, closed connection-owned methods/permit/full binding, F-only atomic lifetime checks at authorization/effect/publication/replay, worker-finished observation and lifecycle integration; preserve fake constructors and authority/cancellation/drain. |
| `jarvis/bot/phone_remote_asgi.py` | Separate exact-host proof factory, epoch-qualified/disarmed handshake timer, one-use egress claim and bounded receive/dispatch lifecycle; preserve original injected adapter contract. |
| new `tests/unit/test_phone_remote_connection.py` | Closed schemas, registry/clock/identity/state and deterministic race matrix. |
| `tests/unit/test_phone_remote_login.py` | Returned-incarnation provenance, sealed admission isolation and public API regressions; reuse ephemeral proof signing helper. |
| `tests/unit/test_phone_remote_service.py` | Exact constructor/full-binding/permit/terminal-denial controls and fake-path compatibility. |
| `tests/unit/test_phone_remote_asgi.py` | In-memory handshake, spoofing, capacity, cancellation, task/slot/send/receive lifetime tests. |
| `tests/unit/test_phone_remote_authority_service.py` | Actual native proof→ASGI→synthetic-results fixture; fixed temporary same-PID recovery launcher and new normal-child proof/card route; actual new-path drain/reap assertions. No fabricated contexts or edits to the old recovery module/native launcher. |

Read-only dependencies: store/schema, proof cryptographic codec, authority channel/native sources, result projector/command registry, R3.21 oracle/adapter, Swift app/DTOs, real server mounts/auth, WS-17 source/release and WS-05 provider code. If the existing process harness cannot exercise a required transition without another path, report the concrete gap for coordinator amendment before editing; do not silently drop the test or broaden constructors/native authority. No existing external executor, arbitrary command dispatch, device enrollment, OS Keychain, real credential, production controller authentication, network configuration/listener, live content, signing/install or model change enters this scope.

Implementation order after independent design acceptance and effective claim/reservation: (1) pin exact input paths and write C01/C03/C04/C06 failures, add sealed login/registry/clock contracts; (2) implement owned activation/request permits and C05/C07/C08 without changing fake APIs; (3) implement the separate ASGI lifecycle and C09/C10; (4) actual native/process C02/C11/C12, preserve C13, full affected suites and independent exact-source review. Freeze source/tree/path/mode/blob/hash manifest; separately reconcile aggregate CI/public main. No intermediate merge.

**Open technical review points, not new user choices:** the reviewer must independently validate the proposed preauth envelope and phase limits; sealed-admission/full-binding provenance; paired clock and monotonic expiry semantics; lock/permit/worker-finished ownership; and disconnect versus recovery-drain distinction against actual source. The proposal makes those decisions concrete rather than delegating them to implementation. A real contradiction requires a documented revision before source adoption. No broader product direction or live-security decision is needed for these disposable offline tests. Actual production controller credentials, transport integrity/TLS, device/signing and real source grants remain their existing separate prerequisites.

**Design self-audit:** public legacy login returns no new authority; the private descriptor is neither a token nor a substitute for current binding. Handshake success is not ongoing authorization. Fresh activation does not inherit a login grant during quiescence. Closing a lease does not sign out or delete another incarnation; postauthorization work remains owned. Clock domains do not mix wall milliseconds with monotonic seconds; service guards read the F-protected monotonic image without acquiring L, and cover effects, receipt publication/replay and final egress. Successful activation invalidates the handshake epoch, so a queued 60-second callback cannot become an active-session timeout. C12 explicitly enters the new proof/card path through the same native-owned recovery child. Only the recovery owner supplies its accepted bounded shutdown/reap guarantee. Proposed names are not yet reserved and no source has changed. The initially accepted product direction and iOS 17 minimum remain settled; ordinary offline work is not serialized behind device/voice/live prerequisites.


### Offline proof-bound connection implementation candidate — 2026-10-31

**Historical candidate `19bbede65b801ac128e73b56cac46663366f1952`:** independent review required three corrections despite the passing tests below. The correction receipt immediately following this section is current; these earlier totals and preliminary outcomes remain historical evidence.

The adopted nine-path slice is implemented on `codex/ws04-phone-connection-source-20261031`, after effective claim `f99e261b7d9e1afc4e3d7ba9ac5bf25ef79124b3`. Independent **source** review is pending. The immutable commit/tree, generated exact path/mode/blob/SHA256 manifest, cumulative public-equivalent comparison and complete validation logs are retained in the external `phone-connection-source-<commit>` artifact. No source beyond those nine paths changed; documentation changes remain this plan, the WS-04 ROADMAP block/reservation and the existing connection-design log.

The separate default-disabled, unmounted adapter accepts only the closed challenge/proof envelope. Its native-owned worker captures the actual `login_proof` return after acknowledgement, consumes a private one-use admission under a fresh activation submission, and installs the exact server-owned context/full binding. Each request has an exact current-worker permit; phone scope/header/payload fields supply no context or bearer authority. Legacy fake constructors/providers and public login results retain their contracts. Voice negotiation/ticket issuance is unavailable through this new composition.

A paired fixture-clock image supplies F-only wall/monotonic guards for authorization, commit/reconciliation, publication/history and one-use final egress. The clock updater uses L→F; no service guard acquires L. Known expiry denies without globally fencing; the commit still performs its required protected-state read so a normal denial does not become a malformed native grant. Terminal failure retains precedence. Active expiry does not roll back an effect or rewrite an existing done receipt. Activation invalidates the handshake epoch; stale queued callbacks cannot cancel active transports. Expired idle records are reclaimed, while an owned retiring record keeps its capacity until worker terminal bookkeeping. Local close opportunistically invalidates idle admission/challenge seals without waiting on a login lock; any contended cleanup stays with the owned worker.

Cancellation retains the original event at pre-enqueue and preauthorization boundaries. A known proof-mode refusal before any native acquisition does not fence unrelated work. Once authorized, the worker completes the frozen continuation, withholds new transport publication after local retirement, and signals actual worker completion separately from early caller settlement. The ASGI task retains the shared dispatch slot until that signal. The single receive task detects disconnect/overflow during execution, with one queued frame and the existing four shared off-loop slots. No connection event starts recovery or signs out another incarnation.

The fixed hashed launcher uses the existing offline owner's Python-executable argument, preserves its PID and descriptors 3/4 (and 5 where supplied), and enters the **new proof→ASGI→card path** only for the initial normal `exercise_drain=true` child. Other modes, including final normal activation, call the unchanged recovery entry point. All nine recovery cases assert the new route/PID against the native quiescence/reap evidence. Timely pin completes once before restore; queued work and proof-committed/fresh-activation work are rejected; repeated drain preserves its deadline. Stalled work, ignored TERM, lost commit/release/shutdown and child failure leave no restore mutation and reap the exact owned child. Fixture markers use the owner's existing canonical JSON requirements.

| Contract rows | Candidate evidence (included in the complete Python total) |
| --- | --- |
| C01, C03 | Exact-constructor, sealed-admission identity/issuer/child/one-use tests; default-disabled/unprepared adapter and spoofed scope tests; closed codec/byte/depth/duplicate/BOM/UTF-8/base64/output checks. Existing proof parser/dependency regressions remain unchanged. |
| C02, C04–C06 | Actual native owner plus disposable P-256 credentials: proof→fresh activation→status→snapshot/view→all five actions; invalid/cross-connection/replayed/reentrant proof, changed proof identity/deadline and unknown selectors; close/feature/revocation/timer/deadline/send-loss activation gaps and native login/activation ACK loss; every captured binding field, equal-valued forged context and reused textual session ID with a new incarnation. |
| C07–C10 | Wall rollback plus exact monotonic-expiry precommit race and one-ms-before positive control with surviving B; first publication protected against a blocked clock updater, subsequent egress/history suppression with effect/done receipt retained; queued and pregrant cancellation send zero authority acquisitions, authorized cancellation sends only its authorized continuation; repeated task cancellation, overflow/send loss, 64-record capacity, expired-record reclamation and retained owned capacity; active use beyond 60 seconds and both timer/activation winners. Shared legacy dispatch/clock/cancellation tests also run. |
| C11 | New-path five-action/history replay, changed-payload conflict, new-login view isolation, capability revocation/protected classification, ordinary source-change withholding and combined reentry/denial terminal fencing; existing complete result/card/capability/six-case refinement regressions remain unchanged. |
| C12 | Nine real recovery-owner runs through the explicit new-path launcher: timely, queued, activation gap, stall, ignored TERM, lost commit, lost release, lost shutdown and child failure. Original recovery process matrix separately runs unchanged. |
| C13 | All `tests/unit/test_phone*.py`; exact unchanged native and PhoneCore suites; frozen oracle/adapter/native/Swift tree preservation checked by manifest. No new full-vector conformance or UI execution claim. |

**Final validation:** 394 Python tests and 605 subtests, warnings as errors, zero skips; 24 scoped native authority tests and 67 PhoneCore tests, zero failures/skips. Focused regressions are included in the Python total, not additional counts; no separate independent reviewer probe is claimed. Python uses the existing isolated environment (3.12.13, SQLite 3.53.1, cryptography 50.0.0, pytest 9.1.1); no dependency was installed. Fresh exact-source `PhoneRemoteAuthorityOwner` executable, SHA256 `d522abfaf7b94c6e9c64cf907b33e421a8fb94a60fc8bb1a741ae7a6cc1b8a0b`. Native/PhoneCore sources were copied and hash-verified from this candidate. The final Python run also includes explicit timeout-teardown coverage for normal fixture children. A preliminary cleanup run exposed a non-reentrant login-lock deadlock; the nested acquisition was replaced by one nonblocking seal-retirement method, a real-lock regression was added, and the exact six orphaned disposable fixture children from that failed run were verified and terminated. The fixture now records its own native-child PID/parent and proves timeout cleanup; that failed run is retained separately and is not passing evidence. The initial restricted SwiftPM manifest startup failed at `sandbox_apply`; approved execution with normal SwiftPM sandboxing and temporary caches then built and ran both suites. The first native test invocation lacked the owner variable and skipped three process tests; the final invocation sets it and runs all 24 with zero skips. Both preliminary outcomes remain in the artifact, separate from final evidence. Roadmap validation against explicit main `5310d1a9305035f43143fcffad6161619281f475` and `git diff --check` pass.

**Remaining gates:** independent source review, aggregate current-public-main reconciliation and full repository/integration CI; actual transport/production controller authentication, enrollment/credential custody, real source grants/content, signing/install and live device acceptance remain separate. Swift source is unchanged; this slice adds no UI-runtime or app-install evidence. The existing simulator-runtime mismatch and iOS 17 minimum remain as previously recorded. Local origin is the handoff repository without `origin/main`; public `39208d18` is absent locally, so the cumulative comparison uses verified equivalent local tree `e31cdf9531908b0186d71d7af573da877e7b7eec`, without invented public ancestry/freshness. No public write, merge, Keychain/security setting, production database/content, listener/network configuration or controller/model change occurred.


### Connection source review corrections — 2026-10-31

**Historical correction `906cb35927c7a15c6a2a6e87e557372a8772a188`:** independent review confirmed the original three fixes, but identified one remaining send-admission outcome gap. The lifecycle correction below is current.

Independent review of `19bbede65b801ac128e73b56cac46663366f1952` (tree `66d1298de2c958e6bb48d3081f7fc830b05d7cd8`) required three corrections. The reviewed manifest, nine-path claim, frozen/native/Swift preservation and C12 process evidence were verified, but passing 394/605 Python and 24/67 Swift tests did not cover these gaps. This correction changes six paths within the existing nine-path source scope, plus the same three documentation paths; no new source adoption, protocol reservation or user/security decision is introduced. Independent acceptance of the corrected source remains pending.

1. **Paired clock derivation and identity.** Both concrete gates are bound to their owning controller. Direct login/service setters on paired gates latch an inconsistent-clock failure; they cannot extend or silently repair the image. Login snapshots and proof commit guards validate both exact gate identities and both time values under L→F, retaining F throughout the proof commit interval. Service guards still read only F. A direct login API entered from F without already owning L is rejected before acquiring L; standalone legacy gates retain their prior behavior. Native regressions cover the reviewer’s direct login mutation and verification-barrier divergence, plus a valid paired update whose session succeeds one millisecond before, and fails exactly at, its correctly derived deadline. Unit controls cover swapped gate identities, raw divergence, failed repair and F→L rejection.
2. **Owned asynchronous sends and teardown.** Accept, handshake/error and active response sends are explicit owned tasks. Retirement cancels a pending cooperative send and joins its cleanup, including repeated caller cancellation, before releasing its registry capacity. A pending-send count retains the exact retiring lease separately from worker continuation ownership. The receive task starts before acceptance, so disconnect can settle a blocked accept. An owned lightweight cancellation watcher covers retirement initiated by the owner worker without invoking callbacks under registry/service locks or consuming blocking executor slots. Send admission takes H→C and rejects a terminal/disabled host before retaining capacity, closing the worker-terminal versus registry-cleanup gap. A deterministic actual-native regression pauses registry cleanup after drain signals completion and proves no further application send starts; the same probe failed before the guard. Owner drain waits for actual send completion within its original nonextending deadline; a settled caller or stopped worker alone cannot claim drain while send cleanup remains pending. Tests pause cancellation cleanup and prove the lease/drain are retained, then release it and assert no late delivery. Disconnect, timer, overflow, caller cancellation, owner-local close and drain are exercised, along with a successful blocked-send release control. Already emitted bytes remain outside any recall guarantee, and an uncooperative send remains owned/uncertain until the existing deadline/reap boundary.
3. **Terminal authentication phase.** A bounded classification predicate recognizes the reserved top-level handshake protocol or `auth.` operation namespace independently of payload validation. It retains duplicate top-level key pairs, so a malformed duplicate cannot hide an earlier reserved protocol. A valid or malformed authentication envelope after activation closes that transport; nested business content is not classified as an envelope. Actual-native tests cover valid challenge/prove, malformed challenge/prove, namespace-only and duplicate-key attempts. Malformed ordinary business requests remain nonterminal and a subsequent status request succeeds; an unrelated authenticated transport remains usable.

**Validation:** after the Mac reconnect, retained logs verified the interrupted run actually passed 400/632 Python plus 24 native/67 PhoneCore; the final terminal-send guard and two additional tests follow that verified checkpoint. The new native regression class first reproduced **13 failing negative subcases** against the reviewed implementation, while its positive controls passed. Corrected final discovery passes **402 Python tests / 635 subtests**, warnings as errors, zero skips. Exact unchanged scoped native authority tests pass **24**, and PhoneCore passes **67**, zero failures/skips. Focused regressions are included in those Python totals; the reviewer’s earlier three standalone probes are separate historical evidence and are not added to this count. The same exact-source native owner SHA256 `d522abfaf7b94c6e9c64cf907b33e421a8fb94a60fc8bb1a741ae7a6cc1b8a0b` is reused after verifying unchanged native source/test copies. Normal SwiftPM sandboxing and temporary caches remain enabled. No dependency installation, security setting, native/frozen fixture or Swift edit occurred. Roadmap validation against main `5310d1a9305035f43143fcffad6161619281f475` and `git diff --check` pass.

The external immutable correction artifact includes exact commit/tree, generated path/mode/blob/size/SHA256 mappings, parent/design/claim/public-equivalent comparisons, before/after regression logs, full-suite receipts and reproducible commands. Process evidence for this correction consists of the existing owned PID/parent, normal timeout teardown and recovery reap assertions; no global process census or global no-child claim is made. Existing source acceptance, aggregate current-main/full-repository CI, UI runtime and production transport/controller/credential/content/signing/live gates remain open. No publication, merge or live action occurred.


### Terminal send-admission outcome correction — 2026-10-31

**Historical pre-review receipt; independently accepted at bd908848 as recorded below.**

Independent review of `906cb35927c7a15c6a2a6e87e557372a8772a188`, tree `4d2a0454063d6aedc34cfe964b9ceaa8f2d28241`, confirmed the original clock/send-cancellation/phase fixes and exact scope/manifest, but found one remaining lifecycle race. If real owner drain completed after a successful reply claim and before `begin_send`, H→C correctly refused admission; the adapter discarded the Boolean result and waited for another inbound frame. No late successful output was observed, but the request was stranded. The same gap existed before acceptance.

This correction changes only the already adopted ASGI source and authority-service test file, plus the existing three docs. Failed nonterminal send admission now retires local transport state immediately. Accept and response callers consume the Boolean outcome and leave the receive loop; the error-send helper also returns on refusal. The existing owned terminal-close path then settles the invocation without another phone frame. A prior disconnect still suppresses redundant close output, and pending sends/authorized workers retain their established cancellation and drain ownership. No protocol, authorization, runtime dependency or scope expansion is introduced.

A deterministic actual-native regression performs genuine proof/activation and invokes real `host.quiesce` after the successful status reply claim, before returning its encoded bytes to ASGI. Separate cases drain after activation reply claim and between open and accept. **All three cases timed out before the fix**, requiring controlled disconnect for fixture cleanup; the normal send control passed. After the fix, each finishes within the bounded test wait, sends exactly one close without another inbound frame, leaves no retained lease, and emits neither the refused payload nor a refused accept. The normal positive control and previous begin-send-wins, blocked-send cleanup, cancellation, timer, authorized continuation and C12 recovery tests remain passing.

Final affected validation: **403 Python tests / 639 subtests**, warnings as errors, zero skips; **24 native authority tests / 67 PhoneCore tests**, zero failures/skips. Focused regressions are included in those totals. Reviewer standalone probes remain separate uncounted evidence. The exact unchanged native owner/source/test copies and PhoneCore copies are verified in the manifest; normal SwiftPM sandboxing and temporary caches remain enabled. Roadmap explicit main `5310d1a9305035f43143fcffad6161619281f475` and `git diff --check` pass. Before/after regression logs, final receipts, exact parent/commit/tree/path hashes and cumulative public-equivalent comparison are retained in the external correction artifact.

Independent corrected-source acceptance remains pending. Process evidence remains the owned PID/parent, exit/reap and timeout assertions; no global process census is claimed. Native/frozen/Swift inputs and legacy fake/proof/result/recovery contracts are preserved. Full repository/integration/current-main, UI/runtime and production/live prerequisites remain separate. No publication, merge, real credential/content/Keychain, network/controller/model or live action occurred.


### Independent offline connection acceptance — 2026-10-31

The independent reviewer bounded-accepted source `bd90884830b47e26a1b90ba8b8971b73eedbc728`, tree `0ccff1aa204c3b1cd5c1ce61741c60ac7383ec35`, against accepted design `1db3ce4580273d1e576dd2c08b8eea025e1b1510`. No remaining actionable finding was reported in this scope. The current source status supersedes the candidate/pending-review wording in the historical implementation receipts above; it does not claim public landing or live acceptance. The source is unchanged by this documentation finalization.

Independent evidence: **403 Python tests / 639 subtests**, warnings as errors, zero skips; **24 native / 67 PhoneCore tests**, zero failures/skips. Six standalone reviewer native-process probes passed separately and are not added to suite totals. The real-owner status-claim, activation-claim and pre-accept drain probes close without another inbound frame, refused output or retained lease. Original paired-clock, blocked-send cancellation and malformed-authentication fixes remain verified. C12 same-PID recovery-owned proof/ASGI/card cases are included in Python discovery, alongside legacy proof/fake/results/history/A-B/cancellation/drain regressions. No new lock inversion was found.

The independent acceptance receipt and Python/native/PhoneCore/probe logs for `bd908848` are retained locally. Reviewer used its independently built owner SHA256 `ceed685e7495ed5dbeeac6b4c9c82f3df33e2d6aaf2d33540ed1ec4fa22a2360`; the five native source/test copies match the accepted source. Normal SwiftPM sandboxing and temporary caches remained enabled. The reviewer verified 2,173 Git blobs, 26 artifact receipts, exact modes/paths/sizes/SHA256, five native/fourteen PhoneCore copies and reconstructed tree. Accepted local source manifest, SHA256 `5ecbbb9bfeeafb76da300a5d32e23a3810a83d994e3f4848a10e27e990a1156b`.

The effective claim `f99e261b7d9e1afc4e3d7ba9ac5bf25ef79124b3` precedes source. Source-versus-design scope remains exactly nine runtime/test paths plus three docs, two added / ten modified / 2,161 unchanged. Public-equivalent comparison is against local `4e2152ec1b890e5383c42ac39d5605d57875886a`, whose tree equals supplied public `39208d18d8c6fde0a9a0539e4d7c3aa68de5610f` tree `e31cdf9531908b0186d71d7af573da877e7b7eec`: 30 added / 22 modified / 2,121 unchanged, no deletions. This establishes tree equivalence only, not public ancestry or fresh remote reconciliation. The external docs artifact preserves exact commit/tree and cumulative mappings.

Remaining gates: existing aggregate unit/integration/eval/frontend/full Swift validation on the cumulative tree; current-main/public reconciliation and full-vector conformance; UI runtime/device compatibility; eventual real transport/controller authentication, credentials/Keychain, content, signing/install and live activation. Next authorized step is aggregate validation in a separate clean worktree with isolated dependencies and no live external traffic. Any failures outside adopted claims require a minimal scope proposal before fixes. No new feature or model change is authorized. Process evidence remains exact owned PID/exit/reap and cleanup assertions, not a global census. No publication, merge or live action occurred.


<a id="ws04-roadmap-history-1901e6ec"></a>
### WS-04 roadmap history at 1901e6ec — 2026-10-31 (private path generalized)

This is a historical record, moved out of the current card to restore complete bounded snapshot reading. Old status, assignments, branch names, claimed scopes and pending-review language describe their original checkpoints. The current WS-04 card and later acceptance receipts govern current status. No evidence or prior authorization is deleted or retroactively changed; this archive grants no new source, publication, merge or live authority.

Original commit `1901e6ec0edd051fa2cd5b8ae01d7d7cd0dde7c7`, tree `ec33a221843ea34e8934b4e7e649704644580002`. Exact original UTF-8 block: 52484 bytes, SHA256 `39a0541c79a2f053e181d5df9424ab57ed24bb747fb8e0d98f32ba72fc30467a`. At accepted integration `669026f17a4a884567df70f63a68350622e34b8c`, the fenced block matched those original bytes. This publication rendering generalizes its one temporary acceptance-receipt path; technical content is unchanged. The size and hash above identify the original block, not this path-generalized rendering. Effective consolidation claim `7fe5cd00f5675effab685385be2021e42bda3496` precedes this move.

``````markdown
<details id="ws-04">
<summary>WS-04 — Remote access · Codex; Larry decides activation</summary>

### Acceptance checklist — remaining

R1 foundation and the remote-bind guard are merged. Local preparation, local activation and remote binding remain separate gates.

The WS-30 synthetic session-revocation repair merged in PR #285 as `97ffb3bb19ce29a9c4e6768a481389ac147cd691`; the S0 source and three PR-triggered workflows are complete. This is synthetic contract evidence only, not a production admission fix or accepted phone access.

- [ ] **Codex · offline phone admission core:** Implemented on the registered branch and locally verified against all 70 S0 v1 vectors, 7 sensitivity mutations and 3 isolation probes. Independent review found a restored-session-ID reuse binding gap; commit `6a4b22cbd38014b01fb2de6a35245416c20560b6` now checks the session's current grant and owner, with regression coverage for stale peers/tickets, fresh login and unrelated sessions. Exact-source review ACCEPTED this commit; required PR checks remain open before merge. The synthetic slice does not wire a request route or establish durable host-anchor behavior. It also does not establish login-incarnation fencing when an unrevoked restore reintroduces the identical session/grant/owner tuple; require that property in the separately claimed durable integration scope before making general restore-safety claims.
- [ ] **Larry · prerequisite decision:** Choose supervised setup, one-time CLI or Mac pairing for local token onboarding. The R2 recommendation is not a substitute for the unresolved roadmap decision.
- [ ] **Codex · implementation prerequisite:** Build and validate the chosen vault/Keychain onboarding path. Under the proposed supervised path: mint once, pass secrets through stdin, verify vault/Keychain readback, refuse existing storage and clean only this attempt's partial state. No token appears in argv/logs/temp files/receipts; preparation changes no auth or remote flag.
- [ ] **Codex · disposable acceptance:** Verify first-run success, repeat refusal without another active identity, interrupted retry and failures after DB/vault/Keychain writes. Check the exact Keychain service/account, both-flag combinations and unauthenticated 401 behavior using disposable credentials.
- [ ] **Larry / Codex · live preparation:** With separate authorization, record exact source, presence/readback and both database identities; authentication stays off and bot/admin listeners stay loopback-only. Preparation alone does not close enabled-mode or Skills acceptance.
- [ ] **Larry / Codex · local activation, if approved:** Bare bot/admin requests return 401; authenticated Connect, voice/status and Skills Versions/inventory work. Verify actual sockets/no off-host listener, immediate device revocation and rollback to prior loopback behavior with remote binding false.
- [ ] **Larry · spoken check:** Record the still-unverified real `system_status` answer on the chosen frozen setup; health probes and native tests alone do not close this spoken gate.
- [ ] **Larry / Codex · remote mode only if separately chosen:** Record the remote-bind decision. If activated, complete G2/§8 tunnel/ACL/Funnel, LAN and tailnet socket, authenticated voice/barge-in/Runs, POST/PATCH offer, Keychain and immediate-revocation checks. If deferred, record that limitation rather than claiming remote access accepted.

Source: [remote-access plan Addenda R1/R2 and §8](docs/plans/MORTIMER_REMOTE_ACCESS_PLAN.md). This checklist grants no credential-minting or activation authority.

**Workstream:** Remote access T2: bearer tokens, fail-closed bind, Tailscale

- **Owner:** `codex` for this bounded WS-04 admission slice; GPT-6 Luna is the assigned implementation model. Larry retains activation and live acceptance decisions.
- **Status:** in-progress; bounded R3.24 offline source/process independently accepted 2026-10-31 at `04afff4c4a4594c9bd1182a10ba45bb6a1fc0986`, tree `78ebb547f1e67ac7962dcf93e14a3cdceba08ef5`. Both independent findings are resolved. Reviewer independently rebuilt the native owner and passed 323 phone tests/434 subtests, zero skips, with warnings as errors. Author scoped Swift evidence is 24 passing tests; independent Swift test startup was denied at `sandbox_apply`, so those tests were not independently executed. Full repository/app, current-main reconciliation, publication and live gates remain open. Parent reports draft PR #290 at WS05-only `39208d18d8c6fde0a9a0539e4d7c3aa68de5610f`; local `4e2152ec1b890e5383c42ac39d5605d57875886a` has exactly its reported tree `e31cdf9531908b0186d71d7af573da877e7b7eec`. The public commit object is unavailable locally; equivalent trees do not establish commit ancestry. Historical receipts remain in the canonical plan and dated log.
- **Implemented by:** GPT-6 Luna authored the in-memory policy core, S0 contract adapter, and separately claimed offline store candidate on `codex/ws04-phone-admission-core-20261029`. The review-driven session-reuse and host-ID binding findings were addressed in their bounded synthetic/source candidates; this evidence does not describe a deployed vulnerability or prove production restore safety.
- **Remaining work / acceptance:** Full real-admission/store-boundary mapping of the frozen 70-vector oracle remains open; R3.11 maps/passes none. R3.16's bounded offline native-owner/child-channel and existing-store transition/session/ticket slice was accepted at source commit `bfe815e489e526a563ce99dde47346486341783e` (tree `80f4d4bbdd5c37c4d32a6fa65a86ebe16b6c0a57`) and is published in PR #290. R3.17 adds an independently accepted bounded, fully serialized offline composition of the actual service peers, receipts, leases, media/output handling, process authority and ASGI executor; source commit `2eb9412849aafb63dbcdb67c445a702d07233850` (tree `6171cbbf9a49a7d5a70f9fe176304b2a0385b0e4`) is included in current PR #290 head `46e29c26e6a4262aa47dfa96615f3a91cc990572`. Validate #543 failed as recorded above. Production service construction, protected-anchor/restore-hook integration, packaged/signature provenance, overlapping service/revocation/replacement races, readiness, route/listener activation, credentials, remote binding, phone calls and release acceptance remain separate gates. Full facade conformance and production D3 restore integration remain open; bounded offline R3.24 completion/recovery source is accepted as recorded above. The accepted R3.23 offline synthetic results snapshot/resume source is at `b4ae7740719f45e4dd81ad3f4917c789c608f57c` (tree `88a201a809f1310c950032ee04d199fa63deeec6`); independent review verified 257 phone tests/360 subtests with zero skips, 39 warning-as-error process tests included in that total, all 58 Swift tests, and an unsigned generic app/UI-test bundle build. These results are not additive. The candidate is local/unpublished and exact-head CI remains pending. UI execution, production source bridge, protected-owner construction and live behavior are unverified. The separate R3.21 audit branch is not integrated. R3.22 is an adopted branch-local seven-file WS-04 source claim on `codex/ws04-ws17-d3-restore-handoff-20261031`, recorded before implementation under the one-final-merge exception. It covers only offline prepare/pending fencing and child shutdown; it does not authorize restore/deployment or change WS-17 script ownership. The parent coordinator refreshed remote ownership through GitHub at 2026-10-31 06:53 UTC (main `5310d1a`, PR #290 `46e29c26`, draft/open/unmerged, no new collision).
- **Model version:** GPT-6 Luna implementation assignment, per Larry's direction; exact runtime build not recorded.
- **Where:** Accepted R3.24 source is on `codex/ws04-ws17-d3-recovery-20261031` at `04afff4c4a4594c9bd1182a10ba45bb6a1fc0986`, tree `78ebb547f1e67ac7962dcf93e14a3cdceba08ef5`, descended from accepted design `e7eb2176f54f5c004be2bd16e159ce905080699a`. Effective adopted scope is thirteen source/test paths after the recorded exact V3/V4 login amendment. This finalization edits only this WS-04 row, the existing remote-access plan and dated proposal log. Local origin has no main ref; integration must reconcile current main under the existing coordinator exception. No reset, rebase, publication or merge is performed.
- **Registration history:** This claim was registered by draft PR #287 on `docs/ws04-phone-admission-claim-20261029`; that documentation branch is not the implementation branch.
- **Plan:** [Canonical WS-04 plan](docs/plans/MORTIMER_REMOTE_ACCESS_PLAN.md); approved phone-admission stage in [phone plan §16](docs/plans/MORTIMER_PHONE_ACCESS_PLAN.md#16-approved-native-iphone-direction-and-staged-claims--revision-54-amendment-candidate-2026-10-28).
- **Scope:** `jarvis/bot/phone_admission.py`; `jarvis/bot/phone_admission_store.py`; `jarvis/bot/phone_remote_protocol.py`; `jarvis/bot/phone_remote_service.py`; `tests/unit/test_phone_admission.py`; `tests/unit/test_phone_admission_store.py`; `tests/unit/test_phone_remote_protocol.py`; `tests/unit/test_phone_remote_service.py`; `tests/unit/test_phone_admission_contract.py`; and read-only `tests/fixtures/phone_admission_contract/v1.json`, plus this WS-04 block and the existing remote-access plan. R3-S1 remains disposable SQLite/fake-anchor only. Adopted R3-S2 may modify the store and store tests and add only the protocol/service modules and their two tests listed here; keep the S0 core, its original tests, contract adapter, and frozen fixture byte-identical. No production migration, config, auth middleware, vault/Keychain, restore/deploy script, route/server, provider, media, tunnel, credential, installation or deployment change. The pre-S2 grant-scoped revocation mismatch is historical: f516d73dd5028391ede2bb1f4cf30d83f10069a8 implements global invalidation in the synthetic store and that exact bounded source was independently accepted. Production anchor durability, authorized restore wiring, and live global-revocation behavior remain unproven. R3.10 is a separately coordinator-adopted branch-local claim limited to the two new files `jarvis/bot/phone_remote_asgi.py` and `tests/unit/test_phone_remote_asgi.py`, plus this row and the existing plan. It accepts only injected service and server-owned trusted context and performs offline in-process ASGI tests; no `jarvis/bot/server.py` mounting or production construction, runtime route, server, or listener is included. The frozen fixture and contract adapter remain unchanged. Adopted local R3.11 adds only `tests/unit/test_phone_admission_boundary.py`; it keeps the fixture and legacy adapter read-only and tests the combined scoped-signout/repeated-restore interaction. It does not map or pass any of the 70 vectors. The exact claim is in R3.11 of the existing remote-access plan; documentation stays in the WS-04 block, that plan, and the dated proposal log. R3.22 adds the exact seven paths below as a separate adopted branch-local slice; it does not widen earlier claims or change WS-17 invocation ownership. R3.23's original coordinator-adopted scope contains 15 paths: WS-17 owns the two projector paths, WS-04 the five Python protocol/service/harness paths, and WS-30 the eight checked Swift DTO/client/preview paths listed in R3.23. A later coordinator-adopted test-only amendment adds the existing `tests/unit/test_phone_remote_asgi.py` path for one valid `results.resume` cursor fixture and one malformed missing-cursor rejection assertion; no ASGI implementation changes. Its effective scope is 16 paths, solely for this synthetic results slice. The source branch is `codex/ws04-ws17-ws30-results-snapshot-resume-20261031`; no `WorkspaceStore`, authority owner/channel, S0 fixture, production source bridge, listener, or real user content is in scope. R3.24 is a separate adopted twelve-path WS-04 claim on `codex/ws04-ws17-d3-recovery-20261031`: `macos/MortimerHost/Sources/PhoneRemoteAuthority/PhoneRemoteAuthorityOwner.swift`; `macos/MortimerHost/Sources/PhoneRemoteAuthority/PhoneRemoteAuthorityKeychainAnchor.swift`; `jarvis/bot/phone_remote_authority_channel.py`; `jarvis/bot/phone_admission_store.py`; new `jarvis/bot/phone_remote_recovery.py`; `jarvis/bot/phone_remote_service.py`; `macos/MortimerHost/Tests/PhoneRemoteAuthorityTests/PhoneRemoteAuthorityKeychainAnchorTests.swift`; `macos/MortimerHost/Tests/PhoneRemoteAuthorityTests/PhoneRemoteAuthorityProcessTests.swift`; `tests/unit/test_phone_admission_store.py`; `tests/unit/test_phone_remote_authority_channel.py`; `tests/unit/test_phone_remote_authority_service.py`; and new `tests/unit/test_phone_remote_recovery.py`. Preserve prior R3.15/R3.18/R3.19/R3.22/R3.23 behavior and all fixtures. The coordinator-adopted 2026-10-31 extension adds only `jarvis/bot/phone_remote_login.py`, for thirteen effective paths, limited to exact V3/V4 dependency compatibility with all proof checks preserved. Existing channel/service tests cover the amendment; the separate login test module is run unchanged. No WS-17 deployment/restore invocation, scripts, live database, real Keychain, signing, credential, installation, listener or production controller changes.
- **R3.15 adopted local source scope (2026-10-30):** only `jarvis/bot/phone_remote_auth_proof.py` and `tests/unit/test_phone_remote_auth_proof.py`, plus this WS-04 ownership row and R3.15 in the existing remote-access plan/dated claim log. Luna authors; `01a18584-92e2-7511-aca8-983bb3f230ef` independently reviews. This is pure proof decoding/transcript/signature verification with synthetic test keys; no challenge issue/consume, key enrollment, owner mapping, session creation, persistence, endpoint, auth middleware, Keychain, dependency, or workflow changes.
- **R3.16 adopted source claim (2026-10-30):** exact six paths are `macos/MortimerHost/Package.swift`, `macos/MortimerHost/Sources/PhoneRemoteAuthority/PhoneRemoteAuthorityOwner.swift`, `macos/MortimerHost/Sources/PhoneRemoteAuthorityOwner/main.swift`, `macos/MortimerHost/Tests/PhoneRemoteAuthorityTests/PhoneRemoteAuthorityProcessTests.swift`, `jarvis/bot/phone_remote_authority_channel.py`, and `tests/unit/test_phone_remote_authority_channel.py`. Design review ACCEPTED commit `93f70f0be779746140083cf18a3a786b2840798f`; coordinator adopted this bounded offline claim. Luna authors; `01a18584-92e2-7511-aca8-983bb3f230ef` independently reviews. Actual processes and the existing disposable SQLite store are required; injected fake anchor only. `PhoneRemoteService` peers, receipts, leases, media, output queues/delivery are excluded and need a separate claim. No store/service edits, Keychain, signing, credential, restore, startup, route/listener, deployment or live acceptance.
- **R3.17 adopted service/process composition source claim (2026-10-31):** The coordinator adopted exact independently accepted design `d932e900f503ac118ff1d9900364a884f1c2bed0` (tree `bb953601e15c9bd45833d226a7eef038281f3acc`) for the one-final-merge PR #290 under Larry's exception. Owner Codex; Luna authors; existing independent WS-04 reviewer `01a18584-92e2-7511-aca8-983bb3f230ef` reviews. Source branch: `codex/ws04-phone-authority-channel-20261030`, based on published PR head `2e53f5aae66c67a19334c593b05b397987b7ab72` (tree `1e798d6db18d52a19b3f42358ba025839ecc6ee3`). Exact six source paths: `macos/MortimerHost/Sources/PhoneRemoteAuthority/PhoneRemoteAuthorityOwner.swift`, `macos/MortimerHost/Tests/PhoneRemoteAuthorityTests/PhoneRemoteAuthorityProcessTests.swift`, `jarvis/bot/phone_remote_authority_channel.py`, `jarvis/bot/phone_remote_service.py`, `tests/unit/test_phone_remote_authority_channel.py`, and new `tests/unit/test_phone_remote_authority_service.py`. Fresh read-only inspection found these five existing paths in the same open PR #290 and no other open repository PR; the new test path has no local history. Four existing paths were included in accepted R3.16; service composition was explicitly excluded there. Recheck refs/claims before integrating. This adoption is limited to the fully serialized offline composition in R3.17: closed v2 channel grants, same-child service/store ownership, ASGI executor proxy, busy rejection, release-ack gating, terminal cleanup and expected read-only authorization denial. Preserve default fake-only `PhoneRemoteService` constructor/policy, unchanged `PhoneAdmissionStore`, S0 files and deferred overlapping service/revocation/replacement races. No production Keychain, signing, packaging, server construction, network/listener, credentials, install, live use, or acceptance claim.
- **R3.16 path collision check (2026-10-30, historical snapshot):** open PR #290 head `7d8daa2c013757a178edfea91019e772e04e157f` changed-file list contained none of the six source paths. Read-only local branch/claim history found no active claim for these paths; `Package.swift` is an existing shared manifest explicitly included in this claim with no conflicting current owner. Recheck before integration/publication.
- **R3.16 source acceptance receipt (2026-10-31):** independent review accepted source commit `bfe815e489e526a563ce99dde47346486341783e` (tree `80f4d4bbdd5c37c4d32a6fa65a86ebe16b6c0a57`). Focused Python unittest command passed 79 tests (32 channel and 47 existing store/contract tests). Focused Swift filter passed 19 tests (2 authority, 10 display, 7 voice); owner executable build passed. Native adversarial probes and roadmap checks passed per independent reviewer. Other Swift tests and full pytest were not run. This validates only the bounded offline process/store scope. That R3.16 source was subsequently published in PR #290; its published-base CI receipt is recorded in the status above.
- **Remaining acceptance gates:** no production Data Protection Keychain integration, signing/packaging/provenance, startup or production service construction; no production `PhoneRemoteService` construction or production peer/receipt/lease/media/output integration (the bounded offline process/service composition is accepted in R3.17); no real transport, listener, credentials, phone call, full 70-vector facade conformance, or production D3 restore closure (bounded offline R3.24 source is accepted). No live access acceptance is claimed. Existing S0 tests/fixtures remain unchanged.
- **R3.22 source acceptance:** the exact seven-file offline prepare/pending-fence implementation is at source commit `4d6371caf490c4a36393560b6c97f355df647223` (tree `1dca0ce9d6a8ec5dd1d27e2e094708bdd7bdfd7a`). Independent source review ACCEPTED this bounded prepare-only change. Author validation rebuilt the test owner and passed 224 focused phone tests/352 subtests with no skips, 22 selected Swift tests with no skips in a temporary package built from the exact owner sources, and `scripts/check_roadmap.py --main github/main` (0 errors, 0 warnings). Independent review separately reproduced 224 phone tests/352 subtests and 22 isolated Swift tests, all with zero skips. The full MortimerHost package could not resolve its external WebRTC dependency. The branch-local candidate is not published; exact-head CI is therefore pending. R3.18 integration and publication remain separately pending. No completion/recovery, production signing/Keychain, installation, startup, service activation or live action is authorized by these offline claims.
- **Next step:** codex/coordinator: reconcile the cumulative manifest against published WS05 tree `e31cdf9531908b0186d71d7af573da877e7b7eec`, retain the independent Swift startup blocker, and obtain applicable full repository/app and integration evidence before the one planned merge. The existing plan proposes a bounded typed phone workspace-command adapter using synthetic sources, with separately designed production local-controller construction/authentication prerequisites. Proposal only: no new claim, operation reservation or source edits. Preserve the separate R3.21 pilot: six translated malformed-event-type cases and six of 113 unchanged markers, zero exact full-vector replays; 107 markers, the two-simultaneous-A-peer initializer mismatch and full frozen-oracle mapping remain open. Parent owns CI544 and publication/current-main coordination; no new CI result is inferred here.
- **R3.19 adopted branch-local source claim and acceptance (2026-10-31):** coordinator adopted independently accepted design `bbbe3adb9e5af1e3d520a6b36b9d0fce98e4ee8b` (tree `3db49c124da36648b64a28efa892914307000b71`) for exactly three paths: modify `macos/MortimerHost/Sources/PhoneRemoteAuthority/PhoneRemoteAuthorityOwner.swift`; add `macos/MortimerHost/Sources/PhoneRemoteAuthority/PhoneRemoteAuthorityKeychainAnchor.swift`; add `macos/MortimerHost/Tests/PhoneRemoteAuthorityTests/PhoneRemoteAuthorityKeychainAnchorTests.swift`. Owner Codex; Luna author; existing independent reviewer `01a18584-92e2-7511-aca8-983bb3f230ef`. Source commit `cc9f0205e2d54f67ffd41f14a0ad088553446303` (tree `75fb50db03241977a430063face357a7453f6bbf`) was independently ACCEPTED for the bounded offline injected adapter. Author validation rebuilt `PhoneRemoteAuthorityOwner`; focused Python modules reported 138 passed and 296 subtests; focused Swift suites reported 39 tests with zero skips, including three actual owner-process tests against the rebuilt binary; `python3 scripts/check_roadmap.py --main github/main` reported 0 errors and 0 warnings. Independent reviewer separately reported 215 phone tests/348 subtests, 39 selected Swift tests with zero skips, and 40 PhoneCore tests; all review probes passed. These counts describe different commands/scopes, not a combined total. The default noninteractive context provider verifies `LAContext.interactionNotAllowed` and rejects before its injected client if the property cannot be confirmed; fake tests exercise configured, interactive and provider-failure cases. R3.19 contains no concrete `SecItem*` client and makes no Security/Keychain calls. The source is local/unpublished with no exact-head CI receipt. The design, test, validation and source acceptance establish neither actual OS attribute compatibility nor entitlements, signing/package provenance, provisioning, installation or production service construction. Those remain separately reviewed gates. Existing fixtures/protocols and legacy KeychainStore remain unchanged. The earlier local-only collision observation and inability to refresh GitHub due DNS are historical; recheck remote head and ownership before later integration. After-first-unlock intent is not a screen-lock admission rule. `ThisDeviceOnly`/readback is not rollback protection: an older same-generation database may pass `_check_pair`; D3 restore/recovery coverage remains open. This offline acceptance is not production readiness.
- **R3.22 adopted branch-local source claim (2026-10-31):** exactly seven paths on `codex/ws04-ws17-d3-restore-handoff-20261031`: `macos/MortimerHost/Sources/PhoneRemoteAuthority/PhoneRemoteAuthorityOwner.swift`; `jarvis/bot/phone_remote_authority_channel.py`; `jarvis/bot/phone_admission_store.py`; `jarvis/bot/phone_remote_service.py`; `tests/unit/test_phone_admission_store.py`; `tests/unit/test_phone_remote_authority_service.py`; and `macos/MortimerHost/Tests/PhoneRemoteAuthorityTests/PhoneRemoteAuthorityProcessTests.swift`. The coordinator adopted accepted D3 design `d75ad6dd6180a036b839c3a1d604f731126b254b` (tree `e82c5cf7a3065f359e3ffb81bf18c8a7e5484b7c`); this claim was recorded before code. Owner/author: Codex; independent exact-source review ACCEPTED exact source commit `4d6371caf490c4a36393560b6c97f355df647223`. Local scope checks and parent-reported GitHub connector refresh at 06:53 UTC found no collision; direct fetch still fails DNS. Scope is offline `restore.prepare` pending fencing, service teardown, special grant retirement/shutdown and owner lock hold using disposable DB/fake anchor and actual test processes. No completion, recovery child, database replacement, scripts, production integration or live restore.
- **Updated:** 10-31: independently accepted bounded R3.24 offline source/process `04afff4c`; recorded independent native/Python receipts, author-only scoped Swift execution and independent sandbox startup denial. Finalization preserves accepted source and proposes the next slice without adopting or implementing it.
- **Historical R3.24 D3 recovery-completion design proposal (superseded by bounded offline source acceptance):** Codex/Luna recorded the design on `codex/ws04-ws17-d3-recovery-design-20261031`, based on the actual R3.21 evidence-correction ancestor `56e51be3f727dcfa68147ff2e5c150716b239fdc`. The documentation-only scope is this WS-04 block, the existing remote-access plan, and the existing R3.22 D3 log; WS-04 owns the protected-owner/store contract and WS-17 retains restore-entrypoint/invocation ownership. The revised proposal defines checkpoint preparation only after WAL normalization and live-base hashing, a distinct backup-image hash, `prepare_resume` for the exact base-versus-already-pending restart decision, a recovery-only v4 child protocol plus a normal v4-supervised service lifecycle carrying unchanged v3 operation schemas, and an explicit store.open readiness gate with an exact DB-receipt/tombstone/retained-manifest comparison map. Normal v4 recovery entry also has a fresh operation-ID-bound `restore_quiesce` shutdown/drain acknowledgment before any mutation, with new operations rejected while only already-authorized, operation-bound continuations may finish, queued unauthorised work settled locally, and a fixed five-second monotonic drain deadline with bounded owned-child termination/reaping on uncertainty; existing v1/v2/v3 shutdown frames remain unchanged. The source scope must update existing channel/service/native exact version/type guards, not merely add a new child mode. It also specifies pinned SQLite implicit autoindex inventory with NULL-aware encoding, consumed `journal.next.tmp` reclamation, lock lifetime across owner replacement, DB/WAL/SHM rename and cleanup journal, and a restart/retry matrix. It distinguishes pre-quiescence policy denial from post-normalization technical failure, pending continuation and completed-tombstone retry; no completion is acknowledged before cleanup and activated normal-child readiness. Existing R3.22 v1 pending state lacks a bound pre-restore checkpoint and is explicitly refused for completion. At that historical proposal checkpoint, independent design review and source adoption were pending. The later adopted thirteen-path implementation now has independent bounded offline source/process acceptance at `04afff4c4a4594c9bd1182a10ba45bb6a1fc0986`, tree `78ebb547f1e67ac7962dcf93e14a3cdceba08ef5`, including synthetic recovery, durable completion and disposable SQLite replacement. Production controller authentication, real protected storage, WS-17 invocation, archive-script safety, whole-host rollback handling and live restore remain open; offline acceptance grants no live restore authorization.

- **R3.18 adopted branch-local offline login-composition source claim (2026-10-31):** coordinator adopted independently accepted design `201a626bebdeda7b9dcfc06b6062fdbe366b8765` (tree `43d631aeea0493ed5cad6b2636f54a1e263d1aed`). Source commit `35a81461f232ea3cf3fbe854d3b2af8a2d5a0776` (tree `62a21723d7865468bf9025b54fbe58f195f54dae`) was independently accepted. Owner Codex; Luna author; existing independent WS-04 reviewer. The v3 challenge/read-release and pre-mutation login-denial/ack phases preserve closed v1/v2; session identity/lifetime are server-derived and expiry, key format, challenge bounds, no-replay and restore limitations are explicit. Focused offline test receipts and limits are in the plan. This source remains local/unpublished with no exact-head CI. Synthetic keys, disposable SQLite and injected anchor only; no enrollment, real Keychain/signing or runtime changes.
- **R3.18 exact adopted paths:** `macos/MortimerHost/Sources/PhoneRemoteAuthority/PhoneRemoteAuthorityOwner.swift`; `macos/MortimerHost/Tests/PhoneRemoteAuthorityTests/PhoneRemoteAuthorityProcessTests.swift`; `jarvis/bot/phone_admission_store.py`; `jarvis/bot/phone_remote_authority_channel.py`; `jarvis/bot/phone_remote_login.py` (new); `jarvis/bot/phone_remote_service.py`; `tests/unit/test_phone_admission_store.py`; `tests/unit/test_phone_remote_authority_channel.py`; `tests/unit/test_phone_remote_authority_service.py`; `tests/unit/test_phone_remote_login.py` (new). Fresh check at PR #290 head `46e29c26e6a4262aa47dfa96615f3a91cc990572` found the eight existing paths in that PR and the two new login paths absent; repository search returned no other open PR. Claim is branch-local, not publication authority. See [R3.18 claim/design log](docs/roadmap-log/2026-10-31-ws04-r3-18-login-composition-design.md).

### D2 native owner claim (2026-10-30; design and bounded offline source accepted)

At R3.16 design adoption, public PR #290 was at `7d8daa2c013757a178edfea91019e772e04e157f` (tree `bf4842b6e0553ddf07e89e82ce6f452c02592be1`); that snapshot is historical. The accepted design is `93f70f0be779746140083cf18a3a786b2840798f` (tree `7cd40abf861c0437580276e5b8012e72b60a4d6a`); the source claim is adopted on `codex/ws04-phone-authority-channel-20261030`. The dated GitHub inspection found none of its six paths in PR #290 at `7d8daa2c013757a178edfea91019e772e04e157f`; local claim history found no competing owner, including for the shared package manifest. This collision evidence is historical; recheck before integration.

- **Owner boundary:** WS-04 owns the D2 authority boundary. A future signed native supervisor owns the protected anchor, singleton lifetime, child/channel incarnation, one-outstanding-operation grants, transition-phase enforcement and serving permission. One trusted packaged Python child owns SQLite and the existing device/grant/session/ticket policy. `PhoneRemoteService` peer/receipt/lease/media/output behavior is excluded from this first IPC slice and requires a separate claim. The native process does not reimplement that policy. A compromised but correctly launched Python child is inside the declared trust boundary; the native gate is not a sandbox against that authorized child. Because `PhoneAdmissionStore.exclusive()` has no operation argument, the child must select an explicit allowlisted operation context through a wrapper; stack inference is prohibited.
- **Adopted source scope:** exactly `macos/MortimerHost/Package.swift`; `macos/MortimerHost/Sources/PhoneRemoteAuthority/PhoneRemoteAuthorityOwner.swift`; `macos/MortimerHost/Sources/PhoneRemoteAuthorityOwner/main.swift`; `macos/MortimerHost/Tests/PhoneRemoteAuthorityTests/PhoneRemoteAuthorityProcessTests.swift`; `jarvis/bot/phone_remote_authority_channel.py`; and `tests/unit/test_phone_remote_authority_channel.py`. The existing store runs through actual owner/child processes with disposable SQLite and injected fake anchor. The explicit wrapper-owned operation context is required because `exclusive()` has no operation argument; reject missing/nested/concurrent/mismatched contexts without stack inference. `PhoneRemoteService` integration and all peer/receipt/lease/media/output behavior are excluded. Any store/service edits or additional paths require a reviewed claim amendment.
- **Launch and provenance contract:** the supervisor verifies its own signed product and launches only the fixed packaged Python runtime, sealed dependency bundle and entrypoint with a fixed argument vector, isolated Python startup/import path and sanitized allowlisted environment. No shell, user-site, `PYTHONPATH`, `PYTHONHOME`, startup hooks, arbitrary executable, caller-chosen module, or inherited unrelated file descriptors. It creates a socket pair before spawn, passes only the designated endpoint through a fixed descriptor, closes every unrelated descriptor, and binds the channel to fresh in-memory owner and child incarnation IDs. No reconnect, descriptor transfer, generic listener, or authentication by UID/path/PID/interpreter signature. The signed product/package manifest and actual distribution identity still need a separate exact signing/package design; no signing identity is selected here.
- **Singleton and lifetime:** the exact proposed stable lock inode and two inherited descriptors are specified in remote-plan R3.16. The owner stops granting when it observes EOF, child exit or protocol failure; the child stops starting operations when it separately observes the failure. A transaction already running may commit between those observations; report completion as uncertain, never replay it, and reconcile anchor/database before future admission. Never `LOCK_UN`, unlink, or replace the inode while a child can still hold it. The shared child is trusted and no same-user adversary containment is claimed.
- **Framed protocol reservation:** `mortimer.phone-authority-channel.v1` is a private socket-pair contract only (no network endpoint); R3.16 defines exact envelope, message kinds, state types, sequence/correlation rules, legal grants/phases, replies and terminal errors. Initial anchor validation, stable-only admission, in-grant pending readback, exact two-field stable finalization and terminal unknown abort are specified in R3.16. No arbitrary SQL, path, Keychain account/service, schema bootstrap, migration, reset or generic anchor overwrite command; no port or launchd label.
- **Transition enforcement:** global security mutation: stable pair check; typed pending-anchor write and exact readback; SQLite security mutation plus pending metadata/session invalidation commit; typed stable-anchor write and exact readback; final SQLite stable-state commit; then release the grant and return the store-method result. This claim wires no production listener permission. Login: reserve a higher login counter in a pending anchor and verify it; commit the session row; finalize/read back the stable anchor; only then release and return the store-method result. Scoped signout: existing store session-only SQLite mutation, without advancing global host generation. This first slice covers store/session/ticket behavior only through the process channel; `PhoneRemoteService` peers, receipts, leases, media, output queues, and output delivery are explicitly deferred and untested. Native phase validation is a protocol-order check; it trusts the authorized child’s phase acknowledgment and does not independently prove SQLite commit contents.
- **Crash and uncertain completion:** loss before a transition begins leaves prior stable state eligible only after a fresh owner validates the complete pair. A pending-anchor write with missing/unknown acknowledgment, DB failure before/after commit, stable-anchor write/readback failure, final DB commit failure, child death, supervisor death or lost response never triggers automatic repair or replay. Pending anchor or DB metadata, mismatch, or unknown write outcome blocks new channel grants until trusted owner recovery; output behavior is outside this claim. Stable anchor plus pending DB after anchor finalization also blocks. After a clean owner restart, old child-incarnation tickets are never resumed; service receipts, peers, queued output and leases are outside this claim. A new owner/child incarnation is required, and uncertain effectful store requests are not retried. Scoped signout remains scoped when its commit is known; ambiguous signout closes the affected session locally and fails closed for that session pending fresh authenticated login, without global generation advance. These are fail-closed cross-store transitions, not an atomic SQLite+Keychain transaction claim.
- **Locked policy and limits:** implement the approved locked-reachability intent by allowing new authenticated sessions after first unlock while the user login session and native owner remain alive. Before first unlock, after logout, sleep, owner death, or unavailable protected data, deny service; this adds no wake/autostart/restart promise. Use the dedicated nonsynchronizing Data Protection Keychain access group and fixed `com.mortimer.phone-authority` / `host-generation-v1` slot; no legacy-keychain fallback. `ThisDeviceOnly` and readback are not rollback protection. D3 restore fencing/recovery remains separately WS-17-owned. Apple references: [Data Protection Keychain](https://developer.apple.com/documentation/security/ksecusedataprotectionkeychain), [access groups](https://developer.apple.com/documentation/security/ksecattraccessgroup), [synchronizable items](https://developer.apple.com/documentation/security/ksecattrsynchronizable), [dynamic code validation](https://developer.apple.com/documentation/security/seccodecheckvalidity%28_%3A_%3A_%3A%29), and [code requirements](https://developer.apple.com/documentation/security/applying-code-requirements?language=objc).
- **Test boundary:** spawn disposable native-owner and Python-child processes; exercise actual frames, sequencing/correlation/incarnations, one-grant exclusion, competing-owner startup, inherited descriptors, graceful/crash shutdown, and the existing SQLite store global-mutation/login/scoped-signout/read/ticket transitions with injected anchor and temporary lock/database fixtures. Test a deterministic in-flight SQLite commit after owner failure observation but before child EOF observation; require uncertain completion, no replay, and reconciliation before fresh admission. This claim does not adapt or test `PhoneRemoteService` peers, receipts, leases, media, output queues/delivery, or service output permission. It does not validate signing, real Keychain, production packaging/startup, rollback resistance, or live service.
- **Review and authorization:** design review ACCEPTED exact commit `93f70f0be779746140083cf18a3a786b2840798f`; coordinator adopted the exact six-file source claim. Independent source review accepted commit `bfe815e489e526a563ce99dde47346486341783e` (tree `80f4d4bbdd5c37c4d32a6fa65a86ebe16b6c0a57`); focused actual-process validation and the owner build passed as recorded in the implementation acceptance receipt above. The R3.16 documentation receipt was reviewed and published in PR #290; its #542 CI receipt applies to the historical `2e53f5aae66c67a19334c593b05b397987b7ab72` head. R3.17 source/documentation are published in the current PR head; R3.18 source/documentation remain local and unpublished. Real signing, entitlements, Keychain writes, migration registration, launchd/app startup changes, restore, credentials, installation, service/listener activation and live access are outside the claim.


### Prior ownership/intake checkpoint (preserved history)

- **Previous Owner:** `codex` (Larry, 09-27)
- **Previous Status:** landed foundation: R2 local-only design and separate remote-bind guard merged in PR #149 (`a39136a`) after the 09-30 `39fc6f9` deployment; the guard was deployed in `7c4637e` on 10-02 with authentication and remote binding still off. Its factual R2 status/header/checkpoint is reconciled via this PR after documentation claim #187 (`9be5dab`). Token provisioning and enabled-mode acceptance remain open
- **Previous Where:** main (R1 foundation `539f8f6`; R2 guard PR #149 `a39136a`; documentation claim #187 merged as `9be5dab`). R2 status correction publication: `docs/ws04-guard-status-20261006`, via this PR. Later provisioning requires its own fresh claim after the method decision.
- **Previous Scope:** Historical/inactive foundation scope: `jarvis/auth.py`, `jarvis/authmw.py`, `jarvis/bind.py`, `jarvis/urls.py`, `jarvis/bot/server.py`, auth middleware and bind in `jarvis/admin/server.py`. Plus the integration points in CX-11: `jarvis/bot/status_tool.py`, `scripts/deploy_main.sh` health checks, `mcp_servers/mcp_selfedit/logic.py` headers. The R2 design proposes `scripts/provision_local_auth.py`, a small JarvisKit stdin-to-Keychain executable, its `Package.swift` target, and tests; no provisioner is implemented.
- **Previous Next step:** larry: select the local token-onboarding method (supervised deploy setup, one-time CLI, or Mac pairing). codex: after that decision, claim a fresh provisioning slice before implementing and validating the chosen vault/Keychain path. Local activation and any remote bind remain separate decisions; the R2 guard status documentation is reconciled.
- **Previous Updated:** 10-06 (R2 guard status reconciled after claimed docs slice; no new live acceptance)


**R3.23 Scope/Where amendment (2026-10-31):** The five WS-04 implementation/test paths are `jarvis/bot/phone_remote_protocol.py`, `jarvis/bot/phone_remote_service.py`, `tests/unit/test_phone_remote_protocol.py`, `tests/unit/test_phone_remote_service.py`, and `tests/unit/test_phone_remote_authority_service.py`, on `codex/ws04-ws17-ws30-results-snapshot-resume-20261031`. A coordinator-adopted test-only amendment adds the already-WS-04-owned `tests/unit/test_phone_remote_asgi.py` for the valid `results.resume` cursor fixture and an explicit missing-cursor rejection assertion; no ASGI implementation change is included. This branch-local scope covers synthetic result snapshot/resume integration through the existing service and actual-process harness only.

**R3.23 adopted offline service integration (2026-10-31):** The coordinator adopted the original 15-path source scope on `codex/ws04-ws17-ws30-results-snapshot-resume-20261031`, based on independently accepted design commit `92dbcc5a7d95f3f89f4c2b7312edd2bc1a9bd456` (tree `5853de654f236a3d07e636f751d0250f848f964d`). Before the additional ASGI test edit, the coordinator adopted one narrow existing-test amendment, making the effective source scope 16 paths: WS-04's five Python protocol/service/harness paths plus `tests/unit/test_phone_remote_asgi.py` for one valid-cursor fixture and one malformed missing-cursor boundary assertion; the eight WS-30 and two WS-17 paths remain unchanged. No ASGI implementation, owner/channel or frozen fixture edits are included. This is synthetic offline integration only: no live source, transport, service or remote-erasure claim. See [remote plan R3.23](docs/plans/MORTIMER_REMOTE_ACCESS_PLAN.md#r323-results-snapshot-resume).

**Historical typed phone-card design documentation claim (2026-10-31; superseded by the adopted source claim below):** Parent coordinator dispatches Codex to prepare this isolated docs-only design on `codex/ws04-ws17-ws30-phone-card-design-20261031`, based on immutable R3.24 finalization `8797891d48bbd4a7e1b9d755ac23d6bc9a2c2470`. Status: design prepared for independent review; source adoption remains pending. WS-04 owns the proposed checked protocol, admission/receipt and process-test contract. Effective documentation Scope/Where amendment: only the WS-04/WS-17/WS-30 blocks in `ROADMAP.md`, dated appendices in existing `docs/plans/MORTIMER_REMOTE_ACCESS_PLAN.md` and `docs/plans/MORTIMER_PHONE_ACCESS_PLAN.md`, and `docs/roadmap-log/2026-10-31-ws04-ws17-ws30-phone-card-command-design.md`. This claim is recorded before plan edits. Fresh read-only GitHub refresh confirms main `5310d1a9305035f43143fcffad6161619281f475` and draft/open/unmerged PR #290 at `39208d18d8c6fde0a9a0539e4d7c3aa68de5610f`; main ROADMAP blob matches local `5310d1a` exactly. Local origin has no main ref and ancestor traversal encounters a missing historical commit; retain the existing coordinator-authorized branch-local exception and require current-main reconciliation before integration. Fresh checkout is clean; active owners and source scopes stay intact. No runtime/source edit, frozen fixture/adapter change, identifier reservation, production controller/security, publication or live action is authorized. Next step: codex independent reviewer evaluates the exact design and proposed 22-path source/test map; coordinator adopts any later implementation claim separately. The completed documentation is in the existing remote plan and phone-plan §18; no implementation or test acceptance is claimed.


**Adopted typed phone-card source claim (2026-10-31):** Coordinator adopts independently accepted design `ffb1b1ccb4582bd38bd8ca426e9835a99a4e2ce9`, tree `1a6f090afd231766f32a44eb45e2a53824e7d280`, for complete synthetic offline implementation. Owner: `codex`; status: independently bounded-accepted synthetic/offline source `a121dfb06385702b82a18041d7d974ab40877ee9` / tree `10b9b68d7a27d52ca2b54d42784326b5da279f86`; Where: `codex/ws04-ws17-ws30-phone-card-source-20261031`. Effective source Scope for this row is exactly: `jarvis/bot/phone_remote_protocol.py`; `jarvis/bot/phone_remote_service.py`; `tests/unit/test_phone_remote_protocol.py`; `tests/unit/test_phone_remote_service.py`; `tests/unit/test_phone_remote_authority_service.py`; `tests/unit/test_phone_remote_authority_channel.py`; `tests/unit/test_phone_remote_asgi.py`. Across WS-04/17/30 this is exactly 22 paths (7/4/11), 19 existing and three new, matching the verified design manifest. Documentation remains limited to these three roadmap blocks/shared reservation, existing remote/phone plans and the typed-card design log. Fresh local checks found all targets match accepted blobs and no dirty work; coordinator remote refresh at 14:52 reports main `5310d1a`, PR290 `39208d18`, green CI544 and no comments/other-PR/published collision. Local handoff origin lacks main and complete historical ancestry; the existing branch-local exception continues, with current-main reconciliation before integration. This amendment precedes all source edits. Preserve frozen fixture/adapter, R3.23 historical receipts and R3.24 recovery/proof/cancellation invariants. No production content/controller/Keychain/signing/network/live/external action or publication/merge is included. Next step: coordinator-managed current-public-main reconciliation and complete integration/validation packet; remaining foreground product construction and live prerequisites are enumerated in [phone-plan §19](docs/plans/MORTIMER_PHONE_ACCESS_PLAN.md#19-product-completion-audit--2026-10-31), without a new source claim. Independent final validation: 369 Python tests/501 subtests with warnings as errors, 67 PhoneCore tests and 24 scoped native tests, zero skips; earlier unsigned app/UI bundle build at `8c2e49f0` applies to unchanged Swift/native bytes. UI execution remains unrun because CoreSimulator 1171.7.0 is older than required 1174.21.0. Full-repository/integration CI, exact full-vector facade replay, production construction/content/transport and live release remain open. Final combined reentry/source-denial probe records uncertain and fences; healthy ordinary withholding stays unfenced. Claim metadata is Git-resolved. Dated verdict, exact artifact hashes and finalization evidence are in the existing remote/phone plans and typed-card log. This final slice updates four claimed docs only; accepted source/frozen/native bytes are preserved. No publication, merge or live acceptance is claimed.

**Historical offline proof-bound connection design claim (2026-10-31; superseded by source adoption below):** Coordinator task `01a18d51-6c8a-73e5-8c86-83fbf017e036` dispatches this bounded docs-only next step after accepted typed-card source and its separately corrected documentation. Owner: `codex`; status: revised docs-only design candidate after `6516a230` review; independent review and source adoption pending; Where: `codex/ws04-phone-connection-design-20261031`. Effective documentation Scope: only this WS-04 block, a dated appendix in existing `docs/plans/MORTIMER_REMOTE_ACCESS_PLAN.md`, and new dated log `docs/roadmap-log/2026-10-31-ws04-phone-connection-design.md`. Source is not adopted: proposed login/service/ASGI/context and test paths require independent design review and coordinated source adoption. Existing WS-17/WS-30 result/client source claims are preserved. Fresh local checks show a clean isolated worktree from correction `4deb20630196fecd7e6d8593c9597e69d8289d6d`; seven proposed existing paths match accepted `a121dfb0`, two new paths are absent. Local `git fetch origin` succeeds against the handoff repository, which still has no main ref; retain the established coordinator branch-local exception, with no invented merge/ancestry or current-public freshness claim. Conflict-register provider/release work is outside this docs scope. Next step: independently review the [complete connection design](docs/plans/MORTIMER_REMOTE_ACCESS_PLAN.md#offline-proof-bound-connectioncontext-adapter--design-candidate-2026-10-31), nine proposed source/test paths (seven existing/two new), and C01–C13 acceptance map; coordinator adopts source separately. The design binds proof-derived contexts to one transport, preserves exact fake constructors and full-incarnation authorization, and distinguishes transport retirement from owner recovery drain. Review corrections specify F-only monotonic commit/publication/replay/egress guards, state/epoch-qualified handshake timer disarming, and an explicit same-PID recovery-owned test-driver route through the new proof/card path; the nine proposed source paths remain unchanged. Dated evidence is in the existing remote plan and connection-design log. No runtime edit, wire reservation, production credentials/controller/Keychain/network/content, publication or live action is authorized by this claim.

**Adopted proof-bound phone connection source claim (2026-10-31):** Coordinator adopts independently accepted design `1db3ce4580273d1e576dd2c08b8eea025e1b1510`, tree `a05a38ad1c3d4cb21740bb8dacaf5651c86ac3bf`. Owner: `codex`; status: independently accepted synthetic/offline source bd908848; aggregate validation pending; Where: `codex/ws04-phone-connection-source-20261031`. Exact source Scope: new `jarvis/bot/phone_remote_connection.py`; `jarvis/bot/phone_remote_login.py`; `jarvis/bot/phone_remote_service.py`; `jarvis/bot/phone_remote_asgi.py`; new `tests/unit/test_phone_remote_connection.py`; `tests/unit/test_phone_remote_login.py`; `tests/unit/test_phone_remote_service.py`; `tests/unit/test_phone_remote_asgi.py`; `tests/unit/test_phone_remote_authority_service.py`. Fresh isolated local checks verify all seven existing paths against the accepted manifest and both new paths absent; no dirty collision. Coordinator's 16:57 remote check reports unchanged PR290 `39208d18`/main `5310d1`, green checks and no new collision; no additional remote freshness is claimed here. The established handoff-history/current-main exception remains. Documentation Scope is this WS-04 block/shared reservation, existing remote plan and connection-design log. Next step: codex runs existing aggregate repository validation in a separate clean worktree of the accepted cumulative tree; report failures and minimal scope proposals before edits outside the claims. Current-main reconciliation, UI/device and production/live gates remain separate. Effective claim `f99e261b7d9e1afc4e3d7ba9ac5bf25ef79124b3` and the protocol-name reservation preceded runtime edits. The completed candidate derives context from actual proof admission, uses fresh activation and F-protected dual lifetime checks, retains owned work after cancellation and exercises the new path through the actual recovery owner. Review of `19bbede65b801ac128e73b56cac46663366f1952` required three corrections: paired-clock divergence, blocked-send ownership and post-activation authentication phase enforcement. Those corrections and the H→C terminal guard are preserved. Review of `906cb359` found a remaining successful-reply-claim→drain→failed-send-admission lifecycle gap; the adapter now treats refusal as terminal and consumes the send outcome at accept/response callers. Actual-native fail-before/positive controls cover reply claim, pre-accept and activation claim. The corrected slice is independently accepted within its synthetic/offline scope at `bd90884830b47e26a1b90ba8b8971b73eedbc728`, tree `0ccff1aa204c3b1cd5c1ce61741c60ac7383ec35`. Final correction evidence is recorded in the existing remote plan and connection-design log; the independent acceptance receipt retained locally records: 403 Python tests / 639 subtests, 24 native and 67 PhoneCore tests, zero skips; six standalone native probes are separate uncounted evidence. Preserve F-only monotonic guards, timer epoch arbitration, same-PID recovery driver, constructor/proof/incarnation/cancellation/drain/card history and fake-path compatibility. Native/frozen inputs and production/controller/Keychain/network/content/signing/publication/live scopes remain excluded.

</details>
``````


### WS-04 complete-snapshot size repair validation — 2026-10-31

Effective docs-only claim `7fe5cd00f5675effab685385be2021e42bda3496` precedes implementation candidate `82b9f78b2852c44e16989e523c3075c1976a65c4`, tree `be3b706368bd4dfe4d6aaff4ffefd7defacfb36d`. The original WS-04 block from independently accepted docs `1901e6ec` is retained verbatim in the archive above (52,484 bytes; SHA256 `39a0541c79a2f053e181d5df9424ab57ed24bb747fb8e0d98f32ba72fc30467a`). Every byte outside WS-04 in ROADMAP and every accepted runtime/test/native/frozen path is unchanged. All eight unchecked gates remain open; 11 current/archived links and their fragment targets resolve. Historical exact claims/scopes/evidence remain authoritative at their recorded checkpoints, not new implementation authority.

On a clean detached worktree of `82b9f78b`, normal complete snapshot reading returns **32 cards / 250 log records / 483,141 UTF-8 JSON bytes**, leaving **41,147 bytes** below the unchanged **524,288-byte** ceiling. The unchanged 600 KiB event projection also passes the existing full-content regression. Focused reader/event/repository/checker discovery passes **126 tests** (two existing dependency warnings), including both original failures. The final docs receipt has its own measured snapshot/headroom and focused/checker receipts in the external immutable manifest.

One complete clean unit run at that exact candidate passes **7,618 tests, 11 skips, 731 subtests**, zero failures, 19 existing-suite warnings, in 273.17 seconds including runner overhead. This is a single full-suite run, distinct from the prior `1901e6ec` initial/targeted aggregate evidence. Focused tests are included in full discovery and are not added to its count; repeat focused checks of final documentation are separate. The isolated Python environment retains the repository-pinned dependencies. Disposable state, RUN_LIVE=0, offline model flags and the external Python socket-denial guard remain; approved execution supplies the permissions required by disposable local-socket and owned-child checks. No dependency, runtime, limit or security-setting change was needed for this docs repair.

This closes the two ROADMAP-size unit failures, not all product gates. Independent docs review and current-main/public reconciliation remain; earlier integration/eval/frontend/Swift receipts retain their original counts, selections and exclusions. The independent reviewer accepted `1901e6ec` documentation/aggregate accounting and initially found the Mac locked (`CGSSessionScreenIsLocked=true`; occlusion 8192 lacks the visible bit). At that checkpoint the five cases awaited an unlocked desktop. The separately received unlocked verification below supersedes that pending state; the author did not rerun visibility or change its source/settings/bounds. No public write, merge, credential/content operation or live activation occurred.


### Independent unlocked-desktop aggregate closure — 2026-10-31

After manual unlock, the independent reviewer tested the unchanged clean aggregate worktree at `1901e6ec0edd051fa2cd5b8ae01d7d7cd0dde7c7`, tree `ec33a221843ea34e8934b4e7e649704644580002` (same accepted runtime source as this docs repair). Pre-run, between-run and post-run diagnostics no longer reported the locked flag. Actual fixture occlusion was **8194**, including visible bit **2**, with one active/awake display. The full-run fixture reported `active=false` while visible and passing, so no forced-activation or source fix was justified.

**Six focused visibility cases passed, zero failures/skips. Full MortimerHost: 590 app cases, 587 passed, zero failed, three external-display skips; native authority: 24 passed, zero failures/skips.** The full distinct-target total is 611 passes/three skips; the focused six are a repeated subset, not additional aggregate coverage. All five prior failing cases and their 23 assertions now pass with identical source and unchanged wait bounds/assertions. The remaining skips are the external-display topology and two supporting-display journeys; none is represented as run.

The local independent visibility receipt for `1901e6ec` and its evidence manifest were read and all eight artifact size/SHA256 entries verified before recording this result. They are copied into the final docs artifact. SwiftPM sandboxing and temporary caches remained; no persistent OS/app/security setting or production source changed. This closes the five visibility failures alongside this separate docs repair of the two snapshot failures. Current-main/public reconciliation, independent docs review, external-display and phone simulator/device coverage, excluded Keychain/hardware tests and production/live gates remain separate. No author visibility rerun, public write, merge or live activation followed.

### Publication-path cleanup prepared — 2026-10-31

Effective claim `2112da1eeac100202f7e6b5dadbb5b1ce1893223` precedes the seven-document cleanup. Thirty-three newly added lines contained personal host paths or temporary worktree/cache/evidence references; their locations are now described without exposing the host paths. Technical history, command flags, source/artifact hashes, test counts, failures, review outcomes and all acceptance limits remain intact. Detailed receipts and the exact before/after mapping remain local; no unavailable public artifact is invented. The historical archive differs from its original immutable bytes only in one temporary receipt reference and is explicitly labelled accordingly. Earlier unrelated public material is unchanged.

All source/test/native/build-input/frozen bytes are identical to accepted integration `669026f17a4a884567df70f63a68350622e34b8c`; its aggregate and Swift evidence remains applicable, with existing exclusions. Current ROADMAP preserves all eight open WS-04 gates and every other row. Static review finds no personal absolute host or temporary path in this cumulative added documentation payload. Roadmap validation reports zero errors/warnings. Final focused snapshot/checker results and the exact docs-only/cumulative manifests accompany the separate local review packet. No Git identity, dependency, runtime, size limit, security setting, publication or live action changed. Independent review of this cleanup is pending.
