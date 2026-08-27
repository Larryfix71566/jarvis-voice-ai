# Mortimer Remote Access Plan — per-client bearer tokens on every endpoint, Tailscale tunnel, fail-closed binds

**Status:** DRAFT for Larry's approval, 2026-08-26. Implements roadmap track **T2** (`docs/plans/MORTIMER_PLATFORM_ROADMAP.md` §2.2). Gate: **G2**.

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
| CP-F1 | BLOCKER | §0.7, §3 A3, §5 Step 1 | Migration cross-guard added (REMOTE owns `0016_client_tokens`; MAIL moves to `0017`); `MIGRATIONS` insertion anchored by "append after the last tuple", not a line number. |
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
7. **Migrations are append-only, and REMOTE owns `0016_client_tokens`.** Add one `MIGRATION_<n+1>` constant and **append its tuple after the last tuple in `MIGRATIONS`** (locate that tuple by searching for the newest `(".._..", MIGRATION_..)` line — today `("0015_memory_reviews", MIGRATION_0015)` — not by a line number); never edit an existing migration string, never renumber. **Cross-plan guard (CP-F1):** REMOTE (W1) owns `0016_client_tokens`; `MORTIMER_MAIL_CALENDAR_BRIEF_PLAN.md` (MAIL) moves its brief migration to `0017_brief`. Because `CREATE TABLE IF NOT EXISTS` makes a number collision silent, confirm before you start that no other `0016_*` exists: `grep -c 0016 jarvis/db.py` should be 0 (the existing newest is `0015`). If a `0016_*` other than `client_tokens` is already present, **stop and report** — wave order was violated.
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

### 1.2 The sidecar's complete route inventory — 47 routes

Every route decorator in `jarvis/admin/server.py`, in file order. **All 47 are covered by the middleware in A6; none is exempt** (A4 justifies the absence of exemptions, including for `/api/health`).

| # | Method | Path | Line |
|---|---|---|---|
| 1 | GET | `/api/health` | 707 |
| 2 | GET | `/api/git/status` | 712 |
| 3 | GET | `/api/git/log` | 717 |
| 4 | GET | `/api/git/diff` | 722 |
| 5 | GET | `/api/git/actions` | 727 |
| 6 | POST | `/api/git/prepare-commit` | 732 |
| 7 | POST | `/api/git/commit` | 737 |
| 8 | POST | `/api/git/prepare-push` | 742 |
| 9 | POST | `/api/git/push` | 747 |
| 10 | GET | `/api/selfedit/models` | 755 |
| 11 | GET | `/api/selfedit/status` | 760 |
| 12 | POST | `/api/selfedit/stage` | 767 |
| 13 | POST | `/api/selfedit/run` | 795 |
| 14 | GET | `/api/selfedit/run` | 878 |
| 15 | POST | `/api/selfedit/validate` | 910 |
| 16 | POST | `/api/selfedit/verify-appearance` | 924 |
| 17 | POST | `/api/selfedit/submit` | 940 |
| 18 | POST | `/api/selfedit/revert` | 949 |
| 19 | POST | `/api/selfedit/reject` | 958 |
| 20 | POST | `/api/appbuild/start` | 1009 |
| 21 | GET | `/api/appbuild/job` | 1063 |
| 22 | POST | `/api/appbuild/submit` | 1072 |
| 23 | POST | `/api/appbuild/cancel` | 1085 |
| 24 | POST | `/api/research/start` | 1104 |
| 25 | GET | `/api/research/job` | 1136 |
| 26 | POST | `/api/research/save` | 1143 |
| 27 | POST | `/api/research/cancel` | 1190 |
| 28 | GET | `/api/memory` | 1214 |
| 29 | GET | `/api/knowledge` | 1226 |
| 30 | GET | `/api/ambient` | 1324 |
| 31 | POST | `/api/location` | 1406 |
| 32 | POST | `/api/clipboard/clear` | 1422 |
| 33 | GET | `/api/clipboard` | 1434 |
| 34 | DELETE | `/api/memory/fact/{key}` | 1445 |
| 35 | GET | `/api/memory/reviews` | 1461 |
| 36 | POST | `/api/memory/reviews/{review_id}/resolve` | 1473 |
| 37 | GET | `/api/runs` | 1501 |
| 38 | GET | `/api/runs/{run_id}` | 1518 |
| 39 | POST | `/api/council/convene` | 1533 |
| 40 | GET | `/api/council/job` | 1576 |
| 41 | GET | `/api/council/round/{round_id}` | 1586 |
| 42 | GET | `/api/council/rounds` | 1595 |
| 43 | POST | `/api/plan/start` | 1617 |
| 44 | GET | `/api/plan/job` | 1679 |
| 45 | POST | `/api/plan/choose` | 1686 |
| 46 | POST | `/api/plan/adopt` | 1706 |
| 47 | POST | `/api/plan/cancel` | 1755 |

Three of these deserve a sentence about what an unauthenticated caller can do today, because they are what makes G2 a gate and not a nicety: **#13 `POST /api/selfedit/run`** starts an LLM edit loop against Mortimer's own repository; **#31 `POST /api/location`** writes the user's coordinates; **#33 `GET /api/clipboard`** returns whatever was last copied on Larry's Mac (`jarvis/clipboard.py`, `pbpaste`), gated only by an in-process armed flag.

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
- The constant is appended as one `(migration_id, sql)` tuple to `MIGRATIONS: list[tuple[str, str]]` (`jarvis/db.py:436-452`), with the id shaped `NNNN_snake_name` — the newest today is `("0015_memory_reviews", MIGRATION_0015)` at line 451.
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

Two processes serve 47 + up to 17 routes with no notion of a caller. The only thing standing between an attacker and `POST /api/selfedit/run` is that both processes bind `127.0.0.1`. The moment a tunnel exists — which is the entire point of T2 — that guarantee is gone, and a *device*-authenticating VPN does not restore it, because every app on a joined phone shares the device's identity (roadmap R4). There is no token table, no `Authorization` parsing, no bind configuration, and no startup check.

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

### A3 — Migration `0016_client_tokens`, following `jarvis/db.py`'s existing mechanism exactly

One new module-level constant, one new tuple, appended after `("0015_memory_reviews", MIGRATION_0015)` (`jarvis/db.py:451`). One migration for this whole plan, per the codebase's own rule (`jarvis/db.py:215-217`). No backfill and nothing to backfill: an empty `client_tokens` table means "no client may call", which is the correct fail-closed starting state, and A8's bind guard reads exactly that emptiness.

`id INTEGER PRIMARY KEY AUTOINCREMENT` rather than K1's bare `INTEGER PK` — this is the shape every other table in the file uses (`memory_reviews` at `jarvis/db.py:423-424`, `agent_runs` at 132-133) and `INTEGER PRIMARY KEY AUTOINCREMENT` *is* an `INTEGER PRIMARY KEY`. Not a deviation from K1.

### A4 — The sidecar has **zero** exempt routes, `/api/health` included

All 47 routes in §1.2 require `Authorization: Bearer <token>`. There is no `PUBLIC_PATHS` set, no path prefix check, and no loopback exemption (K1: *"Loopback is NOT exempt"*).

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

*Why not per-route `Depends`.* 47 sidecar routes plus up to 17 bot routes means 64 decorator edits, and the failure mode of forgetting one is silent. A middleware is coverage by construction; the test in §7 T-A14 enumerates `app.routes` and proves it.

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
- `web/src/jarvisClient.ts:17` gains `requestHeaders: authHeaders()` alongside `endpoint` — **but only after the field name is verified (F10).** The client library is `@pipecat-ai/small-webrtc-transport` (`web/package.json`); the snapshot has no `web/node_modules`, so before §5 Step 8 the implementer runs `npm ls @pipecat-ai/small-webrtc-transport`, opens the resolved package's `.d.ts`, and quotes the exact `path:line` of the connect-params type in §1.5. **Decision tree:** if the params type declares `requestHeaders` (a `Record<string,string>`), use it; if it does not, fall back to appending the token as a `?token=` query parameter on `endpoint` and have `BearerAuthMiddleware` accept it for the `POST`/`PATCH /api/offer` paths only — with the explicit security note that a query token lands in access logs, so this is the second choice. This matters because `web/npm run build` runs `tsc -b`, so a wrong field name is a red CI build with no server-side contingency. **Both `POST /api/offer` and `PATCH /api/offer` must carry the header** (`run.py:796` and `run.py:827`): the same transport issues the trickle-ICE `PATCH` after the initial `POST`, and if it is unauthenticated ICE trickling 401s and the connection degrades in a way that looks like a network fault. §8 V5c checks the browser network tab shows `Authorization` on both.
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
| `tests/unit/test_auth_middleware.py` | All 47 sidecar routes, loopback, kill switch, preflight, websocket scope | 5 |
| `tests/unit/test_bind.py` | The A8 decision table, exit code 2, the interface wait | 3 |
| `tests/unit/test_bot_server.py` | Branch-A assertion, bot route inventory, middleware registration | 7 |
| `tests/unit/test_service_token.py` | `service_headers`, `AdminClient`, the three watchers, the three manifests | 6 |

### Modify (27)

| Path | Change | Step |
|---|---|---|
| `jarvis/db.py` | `MIGRATION_0016` constant + comment block; one tuple appended to `MIGRATIONS` | 1 |
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
python scripts/init_db.py                        # applies 0016_client_tokens
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

### Step 1 — migration `0016_client_tokens`

**File:** `jarvis/db.py`. (CP-F1 guard: first confirm `grep -c 0016 jarvis/db.py` is 0 — REMOTE owns `0016_client_tokens`; if a different `0016_*` is already present, stop and report, the wave order was violated.)

Insert the constant immediately after the closing `"""` of the newest migration constant (search for `MIGRATION_0015 = """` and place it after that string's closing `"""`), before the `MIGRATIONS: list[tuple[str, str]] = [` list:

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
MIGRATION_0016 = """
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

Then **append one tuple after the last tuple in the `MIGRATIONS` list** (locate it by searching for the newest `(".._..", MIGRATION_..)` line — today `("0015_memory_reviews", MIGRATION_0015),` — and add the new tuple immediately after it; do not target an absolute line number, since sibling plans in this wave also append here):

```python
    ("0016_client_tokens", MIGRATION_0016),
```

**Test that proves it** — `tests/unit/test_db.py`, add:

```python
def test_client_tokens_table_shape(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "t.db"))
    from jarvis.db import get_conn, run_migrations
    applied = run_migrations()
    assert "0016_client_tokens" in applied
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

WHY NOT PER-ROUTE Depends. 47 sidecar routes plus up to 17 bot routes,
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
# module's 47 routes requires `Authorization: Bearer <token>`. There are
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

**Test:** §7 T-A14 (all 47 routes 401 without a header), T-A17 (genuine preflight passes), T-A17c (401 carries ACAO — the F1 regression guard), T-A17d (bare `OPTIONS` without `Origin` → 401 — the F16 guard), T-A18 (`Authorization` is an allowed header).

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
EXPECTED_SIDECAR_ROUTES = 47   # §1.2. Adding a route? Add it to the count
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
| Default `user_id` | `"larry"` | `jarvis/auth.py` `DEFAULT_USER_ID` **and** the SQL `DEFAULT 'larry'` in `MIGRATION_0016` | none | `_cmd_add`; the column default is the backstop for a row inserted any other way |
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
| Expected sidecar route count | `47` | `tests/unit/test_auth_middleware.py` `EXPECTED_SIDECAR_ROUTES` | none | the coverage test |
| Expected bot route count | `17` (prebuilt present) | §1.3 enumeration | none | `test_bot_server.py` T-A37 (F4) |

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
| T-A14 | `test_every_sidecar_route_401s_without_a_token` | derive `paths = [r.path for r in admin_server.app.routes if isinstance(r, APIRoute)]`; assert `len(paths) == EXPECTED_SIDECAR_ROUTES` (47); for each route, issue its first declared method with path params filled by `"x"` / `"1"` | every response `status_code == 401`; every body `{"ok": false, "error": ...}`; every response carries `WWW-Authenticate: Bearer realm="jarvis"` |
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
python scripts/init_db.py                     # applies 0016_client_tokens
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

**Reverting the data change.** Migration `0016` is additive: one new table and one index, no `ALTER` on an existing table. Reverting the code leaves the table in place, unread and harmless — that is the intended revert path and requires no SQL. If Larry wants it gone:

```sql
DROP TABLE IF EXISTS client_tokens;
DELETE FROM migrations WHERE id = '0016_client_tokens';
```

(run against `data/jarvis.db` with the stack stopped; `run_migrations()` will recreate it on the next start if the code is still present). **Do not** delete the migration tuple from `jarvis/db.py` without also deleting the row — a machine that applied 0016 and then loses the constant would silently skip nothing, but a machine that has the row and not the constant is a state no other migration in this file can be in.

**Reverting the code.** `git revert` the merge commit. `jarvis/db.py`'s `MIGRATION_0016` should be left in place even then (previous paragraph); every other file in §4 reverts cleanly because nothing else in the repo imports `jarvis.auth`, `jarvis.authmw`, or `jarvis.bind` except the files this plan edits.

**The one thing that does not roll back.** Tokens Larry has already put on his phone. Revoking them (`python -m jarvis.auth revoke <name>`) is instant and needs no restart (A6, verified by V5c), but the plaintext is on the device until he deletes it there.

---

## §10 Risks

| # | Risk | Likelihood | Impact | Mitigation / detection |
|---|---|---|---|---|
| R1 | A Pipecat upgrade removes the module-level `app`, silently returning the bot to unauthenticated | Low | **Critical** | T-A20 fails loudly on upgrade; A10's Branch B is pre-written; §0.4 forbids forking as the escape hatch |
| R2 | An implementer uses `@app.middleware("http")` and leaves four WebSocket routes open | Medium (it is the obvious move) | **Critical** | R-A3 states it; A6 explains it; T-A22 fails if the middleware cannot see a websocket scope |
| R3 | A new sidecar route is added later and someone assumes middleware coverage without checking | Medium | High | T-A14 asserts the exact route count (47); adding a route fails the test until the author looks |
| R4 | `JARVIS_SERVICE_TOKEN` does not reach an MCP child, so voice self-edit breaks with a 401 that gets narrated as "the sidecar is offline" | Medium | Medium | K2's `requires_env` (Step 6d) plus T-A31/T-A32; `AdminClient`'s error text already says "looks offline", which would be a fabrication in this case — the 401 body says `unauthorized`, and `classify_tool_result` marks it failed. V2 exercises the real path |
| R5 | Larry mints a token, does not store it in the vault, and the whole stack 401s itself | Medium | Medium | `service_headers()` returns `{}` rather than raising, so the failure is a clean 401 with a clear body, not a crash; V1 orders the steps; `scripts/check_skills.py` names the missing variable |
| R6 | Tailscale is down/late, so the requested bind host is absent — refusing would brick local voice too (F8) | Medium | Medium | Default `JARVIS_BIND_STRICT=false` falls back to `127.0.0.1` with a loud `bind_fell_back_to_loopback` ERROR after `BIND_WAIT_S`=20 s, losing remote access not security; `mortimer.sh`'s health probe (F6, sleep 25 s > 20 s) surfaces the fallback. Strict operators set `JARVIS_BIND_STRICT=true` for the hard refusal. The "no unrevoked token" case still refuses in both modes |
| R7 | Someone runs `tailscale funnel` "to test from outside" | Low | **Critical** | A16 names it as forbidden; V4 step 6 checks it explicitly; there is no step in this plan that requires it |
| R8 | A token leaks (screenshot, paste, backup) | Low | High | Revocation is instant and needs no restart (V5c). No expiry exists (§2.3), which is the accepted cost of not building a rotation lifecycle in T2 |
| R9 | The console's `localStorage` token is readable by any script the console loads | Certain | Medium | Accepted: the console is retired at T1.4, it loads no third-party script, and A12 is explicitly minimal. T1's Keychain storage is the fix |
| R10 | `verify_bearer` blocks the event loop and answers 401 under write-lock contention (F5) | ~~Medium~~ Low (fixed) | ~~Medium~~ Low | The verdict is decided by a WAL `SELECT` that never blocks on a writer; the `last_used_at` write is best-effort/throttled in its own `try/except` and cannot change the answer; a `busy_timeout` of 250 ms and a `VerifyUnavailable`→503 path mean a busy database is never reported as a wrong token. **Measured:** identity returned in 0.00 s under a held write lock (the old code blocked 5.01 s then returned `None`). Still no cache — revocation stays instant (A6) |
| R11 | A "helpful" future edit exempts `/api/health` or adds a loopback bypass | Medium | **Critical** | A4 states there are zero exemptions and why; T-A15b and T-A16b fail; A14's deny-list entries keep the assistant out of the three modules |
| R12 | The autouse `JARVIS_AUTH_ENABLED=false` fixture masks a real auth regression across the suite | Medium | Medium | The three auth test files re-enable it in their own fixtures, and T-A14 exercises all 47 routes with auth ON. The fixture buys 1538 unchanged tests; the coverage lives in one file that cannot be accidentally disabled |
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
7. **Signatures agreeing across sections; every schema column populated; every needed value derivable.** `verify_bearer(header_value, conn=None) -> ClientIdentity | None` is identical in K1, A5, the §5 Step 2 source, and the §7 tests. Schema columns: `id` (autoincrement), `user_id` (`_cmd_add` supplies `DEFAULT_USER_ID`, plus the SQL default as a backstop), `name` (CLI argument), `token_hash` (`hash_token(mint_token())`), `created_at` (`now_iso()`), `last_used_at` (`verify_bearer`), `revoked_at` (`_cmd_revoke`) — **all seven are written by some step.** Values a step needs: the bind decision needs `count_active_tokens`, which is derivable from the same table the same plan creates; the console needs `getToken()`, which is derivable from a field the same plan adds; the Swift shell needs a Keychain item, and §8 V6 gives the exact command that creates it. `EXPECTED_SIDECAR_ROUTES = 47` is derived by enumeration in §1.2 (re-verified 2026-08-27: `grep -c '@app\.'` = 48, minus one `@app.middleware`), not asserted from memory. The bot route inventory is **17** (F4), because `pipecat-ai-prebuilt==1.0.5` is pinned so `/client` + `GET /` are served.
8. **Judgment left to the implementer.** Searched for all three shapes. No "use your judgment": every threshold is a named constant with its value (§6). No "investigate first": the one genuine unknown — how to reach Pipecat's app — is A10's decision tree with a runnable check, two written branches, and a "report and stop" third outcome; the second unknown — whether the hardening plan landed first — is Step 6d's append rule with both end states tabulated. No bare "be careful": `jarvis/auth.py`, `jarvis/authmw.py`, and `jarvis/bind.py` are given as complete literal source, and every rejection case is a named test with its input and expected output in §7.
9. **Plan drift.** Every file mentioned in §5 appears in §4's manifest (**12 created, 27 modified paths, 0 deleted, 1 Larry commit** — recounted by counting the table rows, F12) and every §4 row names its step. `scripts/mortimer.sh` (Step 9, F6) and `tests/unit/test_db.py` (Step 1, F12) are now both listed; `docs/plans/MORTIMER_PLATFORM_ROADMAP.md` is deliberately *not* in the manifest (a shared artifact SEC edits — `CROSS_PLAN_RESOLUTION.md` §C F14). Cross-checked the "write X" versus "X exists" hazard: §5 Step 8 replaces `mcp_servers/mcp_selfedit/logic.py`'s `DEFAULT_ADMIN_URL`/`ADMIN_URL_ENV` with a re-export, and §4 lists that file once with both edits (Step 6 headers, Step 8 re-export); `jarvis/admin/server.py` carries Steps 0, 4, 9 in one row. Checked against the sibling plans and the resolution: `MORTIMER_SECURITY_HARDENING_PLAN.md` also edits `mcp_servers/*/skill.yaml` — Step 6d is an **append** rule with both pre-states tabulated (CP-F4/F2) so the two plans cannot conflict in either merge order; A14 lists exactly the three W1 entries of `ALLOWLIST_SEQUENCE.md` and does **not** deny `mcp_servers/*/skill.yaml` (CP-A keeps it editable, guarded by SEC's frozen snapshot); the migration number is guarded against MAIL's `0017` (CP-F1). Checked against the roadmap: four claims were wrong and are corrected at the top (R-A1…R-A4); the roadmap edit itself is SEC's.

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
