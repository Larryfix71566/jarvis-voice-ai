# Adversarial review — `MORTIMER_REMOTE_ACCESS_PLAN.md` (track T2)

Reviewed against `/home/claude/repo` (snapshot 2026-08-26), Pipecat 1.4.0 at
`/usr/local/lib/python3.11/dist-packages/pipecat`, Starlette 1.0.0, uvicorn 0.46.0.
Where the plan gives runnable code I extracted it and ran it (`jarvis/auth.py`
verbatim, the ASGI middleware verbatim under a real uvicorn, the migration, the
conftest fixture-ordering claim, `build_argv`'s argparse behaviour).

**Counts: 4 BLOCKER, 9 MAJOR, 9 MINOR.**

---

### F1 — On the sidecar the 401 carries no CORS headers, so the browser never sees it: A12's toast, and acceptance V3, cannot work [BLOCKER]

**Where:** §3 A7, §5 Step 4, §5 Step 8 (`web/src/api.ts`), §8 V3.

**What the plan says:** A7 — *"Sidecar. … Auth is added later → **auth is outermost**, CORS inner."* and *"Both are stated … The one middleware behaves identically in both."* §5 Step 8 — `authFetch` fires the toast on `if (res.status === 401 && !notified)`. §8 V3 — *"Pass: exactly **one** chip reading `Token required — Dev tab` appears."*

**Why it's wrong:** With `BearerAuthMiddleware` outermost, the 401 is generated *above* `CORSMiddleware`, so it is emitted with only `content-type`, `www-authenticate` and `content-length` — no `Access-Control-Allow-Origin`. The console is served by vite on `http://localhost:5173` and calls the sidecar on `:7861`; that is cross-origin. A cross-origin response with no ACAO is blocked by the browser: `fetch` **rejects with a TypeError**, it does not resolve with `res.status === 401`. So `authFetch` never reaches its 401 branch, `subscribeAuthError` never fires, the chip never renders, and every panel falls into its network-error path instead. The asymmetry A7 waves away is not cosmetic — the bot's ordering (CORS outermost) produces a *readable* 401, the sidecar's does not, so the two orderings are not "both correct".

**Evidence:** built both orderings with the plan's exact middleware and CORS config and drove them as raw ASGI:

```
==================== sidecar (auth outermost)
 preflight: 200 {... 'access-control-allow-origin': 'http://localhost:5173'}
 401 no token: status 401 | ACAO = None | all: ['content-type', 'www-authenticate', 'content-length']
 200 good token: status 200 | ACAO = http://localhost:5173
==================== bot (cors outermost)
 401 no token: status 401 | ACAO = http://localhost:5173 | all: ['content-type', 'www-authenticate', 'content-length', 'access-control-allow-origin', 'vary']
```

The plan's own middleware tests never check this: T-A17/T-A18 test the *preflight*, T-A14 asserts the 401 status and body from a same-origin `TestClient` (which has no CORS enforcement). This is a verification that cannot catch the defect it is nearest to.

**Fix:** On the sidecar, add `BearerAuthMiddleware` **before** the `CORSMiddleware` block (§5 Step 4), so CORS ends up outermost and wraps the 401 with `Access-Control-Allow-Origin` — the same ordering the bot gets. Rewrite A7 to say the ordering is the same in both processes and that the `OPTIONS` branch is therefore unreachable in both (keep the branch as defence for T1.4). Add a test: `GET /api/health` with `Origin: http://localhost:5173` and no token → `401` **and** `access-control-allow-origin: http://localhost:5173` present.

---

### F2 — §5 Step 6(d)'s table deletes `TAVILY_API_KEY` from `mcp_web/skill.yaml` [BLOCKER]

**Where:** §5 Step 6(d) table, row `mcp_servers/mcp_web/skill.yaml:6`.

**What the plan says:** `| mcp_servers/mcp_web/skill.yaml:6 | requires_env before (today) = **blank** | after (hardening not landed) = **[JARVIS_SERVICE_TOKEN]** | …`

**Why it's wrong:** It is not blank today. The prescribed "after" value therefore *removes* `TAVILY_API_KEY`. Once `MORTIMER_SECURITY_HARDENING_PLAN.md`'s K2 scoping lands, `TAVILY_API_KEY` is not in `BASE_ENV_KEYS`, so mcp-web stops receiving it and `web_search` drops into degraded mode — silently, because K2's rule for a missing `requires_env` name is a WARNING, not a failure. The table also contradicts the deterministic rule stated two lines above it (*"append … to whatever list `requires_env` already holds"*) and its own third column, which lists `TAVILY_API_KEY` in the hardening-landed end state. A Sonnet implementer given a rule and a table will follow the table.

**Evidence:**

```
$ sed -n '5,9p' /home/claude/repo/mcp_servers/mcp_web/skill.yaml
requires_env: 
  - TAVILY_API_KEY
requires_keychain: []
```

(Block-sequence form, not flow form — which is probably how "blank" was misread: line 6 ends after the colon.)

**Fix:** Correct the row to `before = [TAVILY_API_KEY]`, `after (hardening not landed) = [TAVILY_API_KEY, JARVIS_SERVICE_TOKEN]`. Add to §7 a test asserting `TAVILY_API_KEY` is still in `mcp_web`'s `requires_env` after the edit (T-A31 currently asserts membership of `JARVIS_SERVICE_TOKEN` only, so it passes while the deletion ships).

---

### F3 — If this plan lands before SECURITY_HARDENING, the service token is handed to every MCP child, and T-A32 passes anyway [BLOCKER]

**Where:** §5 Step 6(d); §7 T-A32; "Contracts this plan CONSUMES" (K2).

**What the plan says:** *"Only the servers that construct an `AdminClient` get the name — `mcp_time`, `mcp_notes`, `mcp_memory`, `mcp_reminders`, `mcp_system`, `mcp_git`, `mcp_repo`, `mcp_runlog`, and `mcp_screen` do **not** call the sidecar and must not receive the token."* T-A32: *"`test_no_other_server_declares_the_token` … K2's whole point is that `mcp_time` never sees it."*

**Why it's wrong:** `requires_env` only *scopes* anything once K2's `build_child_env` exists. Today the registry copies the whole environment:

```
$ grep -n 'env = dict(os.environ)' /home/claude/repo/jarvis/skills/registry.py
192:        env = dict(os.environ)
```

The plan explicitly supports landing in either order (*"Rule for the implementer, deterministic regardless of whether `MORTIMER_SECURITY_HARDENING_PLAN.md` has landed first"*), and §5 declares no ordering dependency. In the "hardening not landed" order, `inject_env()` puts `JARVIS_SERVICE_TOKEN` into `os.environ` and all twelve children — including `mcp_screen` and `mcp_web`, the two that handle untrusted external content — inherit a credential that authorises `POST /api/selfedit/run`. T-A32 asserts a *manifest* fact, not an *environment* fact, so it is green throughout. That is precisely the "test that passes for the wrong reason" shape this project has already shipped twice.

It is compounded by the self-edit allowlist: `mcp_servers/**` is on the **allow** list today, so the assistant can add `JARVIS_SERVICE_TOKEN` to any `skill.yaml`'s `requires_env` itself. A14 deliberately drops that deny entry on the assumption D-H9 lands — which is the same assumption that fails in this ordering.

```
$ python3 -c "import json;print(json.load(open('/home/claude/repo/config/self_edit_allowlist.json'))['allow'])"
['web/src/**', 'web/public/**', 'config/**', 'jarvis/prompts.py', 'jarvis/skills/**', 'jarvis/services/**', 'mcp_servers/**', 'tests/**', 'docs/**', '*.md']
```

**Fix:** Make the dependency explicit and hard: §0 gains *"`MORTIMER_SECURITY_HARDENING_PLAN.md` §5 Steps 1–2 (`build_child_env`) MUST be merged before §5 Step 6 of this plan. If `jarvis/skills/registry.py` still contains `env = dict(os.environ)`, stop and report."* Add a test that proves the environment, not the manifest: spawn/patch `_start_server` and assert `JARVIS_SERVICE_TOKEN` is absent from the child env for every server outside the three. Keep `mcp_servers/*/skill.yaml` in A14's deny list rather than de-duplicating it away.

---

### F4 — `pipecat-ai-prebuilt` **is** a pinned dependency, so §1.3's bot route inventory, T-A37 and the docstring this plan writes are all wrong [MAJOR]

**Where:** §1.3 table rows for `_setup_frontend_routes`; §5 Step 7 (`jarvis/bot/bot.py` docstring); §7 T-A37; §3 A6 ("up to 15 bot routes").

**What the plan says:** *"`app.mount("/client", PipecatPrebuiltUI)` … **No** — `pipecat_ai_prebuilt` is not installed in this environment (verified: `ModuleNotFoundError`)"*, and the new `bot.py` docstring the plan asks the implementer to write: *"The runner's own /client page is not served here (pipecat_ai_prebuilt is not installed) and would require a bearer token if it were."*

**Why it's wrong:** The claim is about the *authoring sandbox*, not the target machine. Larry's lockfile pins it:

```
$ grep -n -i 'prebuilt' /home/claude/repo/requirements*.txt
requirements-lock.txt:113:pipecat-ai-prebuilt==1.0.5
```

So on Larry's Mac `_setup_frontend_routes` (`pipecat/runner/run.py:741-754`) does mount `/client` and register `GET /`. Consequences: (a) the route inventory is 17, not 15; (b) T-A37 — *"collect `{(method, path)}` … equals the http+ws set enumerated in §1.3"* — fails on the machine that matters, and a `Mount` is not an `APIRoute` so a naive collection misses it entirely; (c) the plan instructs the implementer to commit a false statement into `bot.py`'s docstring; (d) `http://localhost:7860/client`, which the *current* docstring tells users to open, now returns raw 401 JSON, and there is no way to attach a bearer header from a browser address bar — the plan never says what replaces it.

**Fix:** Correct §1.3 (mark both rows "Yes — `pipecat-ai-prebuilt==1.0.5` is in `requirements-lock.txt:113`"), raise the bot route count to 17, rewrite the docstring text to say `/client` is served but now requires a token so the web console on `:5173` is the entry point, and make T-A37 enumerate `app.routes` including `starlette.routing.Mount` with an explicit expected set for `pipecat-ai-prebuilt` present *and* absent.

---

### F5 — `verify_bearer` writes on every request; under write-lock contention it blocks 5.01 s and then answers 401 [MAJOR]

**Where:** §5 Step 2 (`verify_bearer`), §3 A6 ("No cache"), §10 R10.

**What the plan says:** R10 — *"`verify_bearer`'s per-request SQLite read blocks the event loop under load | Low | Low | Local WAL read on a <10-row table."*

**Why it's wrong:** It is not a read. Every successful verification does `UPDATE client_tokens SET last_used_at = ?` plus `conn.commit()`, i.e. it takes SQLite's single write lock on `data/jarvis.db` — the same database the sidecar writes for runs, memory, actions and council rounds. `jarvis/db.py:get_conn` never sets a busy timeout, so Python's default `timeout=5.0` applies. When another connection holds the write lock, `verify_bearer` blocks for five seconds and then falls into `except sqlite3.Error: return None` — which the middleware turns into a **401**. A transient lock is therefore indistinguishable from a bad token: the console shows `Token required — Dev tab`, `AdminClient` gets `{"ok": false, "error": "unauthorized …"}`, and a five-second synchronous stall lands on the bot's event loop mid-voice-turn.

**Evidence** (plan's `jarvis/auth.py` verbatim, plan's migration applied):

```
token ok: True
verify_bearer while another writer holds the lock -> None after 5.01s
after release: True
```

and, for contrast, the read-only half of the same work under the same held lock:

```
read-only SELECT under write lock: 1 rows in 0.000s
count_active_tokens -> 1 in 0.000s
```

WAL readers never block. It is only the plan's own `last_used_at` write that creates the failure mode.

**Fix:** Split the verdict from the bookkeeping. Do the `SELECT` (never blocks), decide the identity, then attempt the `UPDATE` inside its own `try/except sqlite3.Error: pass` so a lock can never change the answer. Additionally: only write `last_used_at` when the stored value is more than 60 s old (state the constant in §6), and open the verification connection with an explicit short timeout. If a lock *does* prevent verification, return **503**, not 401 — a database problem is not an authentication decision, and the console must not tell Larry his token is wrong.

---

### F6 — `scripts/mortimer.sh` declares success 4 s after launch, but `resolve_bind_host` can block for 30 s and then exit 2 [MAJOR]

**Where:** §3 A8 (`BIND_WAIT_S = 30.0`), §5 Step 9, §8 V5(c), §10 R6.

**What the plan says:** A8 — *"`resolve_bind_host` retries it once a second for `BIND_WAIT_S = 30` before refusing"*; V5(c) — *"`./scripts/mortimer.sh` … Pass: (c) starts and `lsof …` shows the two ports bound."*

**Why it's wrong:** `mortimer.sh` starts the three components, sleeps 4 seconds, and then reports health with `kill -0 "$pid"` only:

```
$ sed -n '93,102p' /home/claude/repo/scripts/mortimer.sh
sleep 4
check() {  # name pid url
  if kill -0 "$2" 2>/dev/null; then
    echo "  $1: running (pid $2) — $3"
  else
    echo "  $1: FAILED to start — see logs/$1.log" >&2
  fi
}
check bot   "$BOT_PID"   "http://localhost:$BOT_PORT"
check admin "$ADMIN_PID" "http://localhost:$ADMIN_PORT/api/health"
```

At t=4 s a process stuck in `_wait_for_host` is very much alive, so the script prints `admin: running`. At t=30 s it raises `BindRefused` and exits 2, into a log file nobody is watching. The single most likely failure of this whole plan — Tailscale late at boot, wrong `100.x` address after a re-auth — is reported as success. §8 V5(c)'s pass criterion (`lsof`) is a manual step Larry may run before t=30 s and see nothing bound, or after and see nothing bound, with no signal which.

**Fix:** Either raise `mortimer.sh`'s `sleep` above `BIND_WAIT_S` and make `check()` actually probe (`curl -fsS -H "Authorization: Bearer $JARVIS_SERVICE_TOKEN" .../api/health`), or drop `BIND_WAIT_S` to a value below the script's sleep and retry at the process-manager level. Whichever is chosen, put the number in §6 next to `BIND_WAIT_S` and state the relationship as an invariant (`mortimer.sh` sleep > `BIND_WAIT_S`). Add `scripts/mortimer.sh` to the §4 manifest (see F12).

---

### F7 — `build_argv` lets a command-line `--host` override the gated bind host, and the plan says so approvingly [MAJOR]

**Where:** §5 Step 7 Branch A, `build_argv`; §7 T-A35.

**What the plan says:** *"Any argument the caller passed on the command line is preserved and wins, because argparse takes the LAST occurrence of an option."*

**Why it's wrong:** A8 is described as *"the single fail-closed bind resolver"* and A14 puts `jarvis/bind.py` on the deny list precisely so the gate cannot be edited away. But the gate is bypassable without editing anything: `python -m jarvis.bot.bot --host 0.0.0.0` binds `0.0.0.0` with `JARVIS_BIND_HOST` unset and zero tokens in the table, because the resolved host is prepended and the user's is appended.

**Evidence:**

```
argv: ['--host', '127.0.0.1', '--port', '7860', '--host', '0.0.0.0'] -> Namespace(host='0.0.0.0', port=7860)
```

Branch B has the same hole by a different route: `_parse` gives `--host` a `default=host` but still accepts an explicit `--host`.

**Fix:** Strip `--host`/`--port` (and their `=`-joined forms) out of `sys.argv[1:]` before appending, or append the resolved values *after* the user's so the gate wins, and log an ERROR naming the ignored argument. State in A8 that no command-line argument can widen the bind. Add a test: `build_argv("127.0.0.1", 7860)` with `sys.argv = ["bot.py", "--host", "0.0.0.0"]` → parsed host is `127.0.0.1`.

---

### F8 — The fail-closed bind bricks the whole local stack whenever Tailscale is down [MAJOR]

**Where:** §3 A8 decision table; §8 V5(c) (`echo 'JARVIS_BIND_HOST=100.x.y.z' >> .env`); §9 Rollback.

**What the plan says:** A8's table, row 5: *"`true` | non-loopback | `≥ 1` | no, within `BIND_WAIT_S` | `BindRefused` → `SystemExit(2)`"*. §9: *"Partial rollback — keep auth, close the tunnel. Remove `JARVIS_BIND_HOST` from `.env` and restart."*

**Why it's wrong:** V5(c) makes `JARVIS_BIND_HOST=100.x.y.z` a persistent `.env` entry, and `scripts/run_bot.sh` / `run_admin.sh` export `.env` into the environment (`set -a; . ./.env; set +a`). So from that point on, *any* condition that removes the tailnet address — `tailscaled` not running, a logged-out node, an expired key, a Tailscale upgrade, the mini booted on a network where Tailscale can't reach the coordination server — makes both processes exit 2 after 30 s. Not degraded: **gone**, including for someone sitting at the machine who only wants local voice. There is no fallback row in A8's table, no "fall back to loopback and log loudly" option, and the documented recovery is to hand-edit `.env` — on a machine whose assistant is the thing that is down.

The threat model does not require this. The token check is the control that survives a token leak; binding one address is the second, independent control. Falling back to `127.0.0.1` (which is strictly narrower than the requested bind) loses remote access, not security.

**Fix:** Add a third state to A8 for the *interface-missing* case only (keep the refusal for "no unrevoked token", which is a genuine security condition): when auth is on, a token exists, and the requested non-loopback host is still unassigned after `BIND_WAIT_S`, bind `127.0.0.1` and log `ERROR bind_fell_back_to_loopback requested=<host> reason=interface_absent` — and put that behind a knob `JARVIS_BIND_STRICT` (default stated explicitly in §6) so an operator who wants the hard refusal can have it. Update §9 and the risk table; R6 currently rates this "Medium/Medium — `_wait_for_host` retries for 30 s", which is the mitigation for a boot race, not for an outage.

---

### F9 — The toast renders with a CSS class that does not exist [MAJOR]

**Where:** §5 Step 8 (`web/src/App.tsx`); §3 A12; §11 item 5.

**What the plan says:** literal code `{authChip && <div className="attn-chip">Token required — Dev tab</div>}`, described as *"the existing 4-second auto-dismissing chip pattern (`--attn` colour, the same one the speaker-gate 'Voice not recognized' chip uses)"*, and §11 item 5: *"The chip's visual state is specified by reuse … not a new component."*

**Why it's wrong:** There is no `.attn-chip` rule anywhere in `web/src`. The speaker-gate chip the plan cites uses a different class:

```
$ grep -rn 'attn-chip' /home/claude/repo/web/src        # no matches
$ sed -n '630,634p' /home/claude/repo/web/src/App.tsx
          {speakerGateNotice && (
            <span className="speaker-gate-notice" role="status">
              {speakerGateNotice}
            </span>
          )}
```

So the chip ships unstyled — plain black text in the flow of `.stage-row` — and §8 V3's pass criterion ("a chip … appears and auto-dismisses") is judged on something that does not look like a chip. The plan's snippet also drops the `useEffect` cleanup the existing pattern has (`App.tsx:292-296` clears its timeout), so a re-fire leaks a timer.

**Fix:** Use `className="speaker-gate-notice"` on a `<span role="status">`, or add an explicit `.attn-chip` rule to `web/src/App.css` and quote it in the plan. Mirror the existing timeout pattern: hold `authChip` in state and clear it from a `useEffect` with a `clearTimeout` cleanup, rather than calling `setTimeout` inside the subscription callback.

---

### F10 — `webrtcRequestParams.requestHeaders` is asserted with no citation, and the trickle-ICE `PATCH /api/offer` is never covered [MAJOR]

**Where:** §3 A12, §5 Step 8 (`web/src/jarvisClient.ts`), §1.5 row "Web console — RTVI connect".

**What the plan says:** *"`web/src/jarvisClient.ts:17` gains `requestHeaders: { Authorization: … }` alongside `endpoint`."*

**Why it's wrong:** Every other third-party API in this plan is cited to `path:line` (the brief's rule, and §0.4's). This one is not, and it cannot be — the snapshot has no `web/node_modules`, so the field name was not verified against `@pipecat-ai/small-webrtc-transport@^1.10.6`. It is also the one client-side claim CI will fail on: `web/npm run build` runs `tsc -b`, so a wrong field name is a red build with no Branch-B contingency (contrast A10, which writes a whole fallback for the *server* seam).

Separately, the runner registers **two** signalling routes and the plan only addresses one. `pipecat/runner/run.py:827` is `@app.patch("/api/offer")` (trickled ICE candidates), issued by the same transport after the initial POST. The plan nowhere establishes that `requestHeaders` is applied to the PATCH as well. If it is not, ICE trickling 401s and the connection degrades or fails in a way that looks like a network problem, not an auth problem.

**Fix:** Before Step 8, run `npm ls @pipecat-ai/small-webrtc-transport` and open its `.d.ts`; quote the exact `path:line` of the params type in §1.5. Write the decision tree A10-style: if the type has `requestHeaders`, use it; if it does not, state the fallback (e.g. pass the token as a `?token=` query parameter on `endpoint` and have `BearerAuthMiddleware` accept it for that one path — with the security note that a query token lands in access logs). Add to §8 a check that the browser network tab shows `Authorization` on **both** `POST /api/offer` and `PATCH /api/offer`.

---

### F11 — Merging the code breaks the running stack until Larry mints the service token, and §5 orders it the other way [MAJOR]

**Where:** §5 Step 6(a) (*"Mint and store it (Larry's action; §8 V1 gives the commands)"*), §8 V1, §10 R5.

**What the plan says:** R5 — *"Larry mints a token, does not store it in the vault, and the whole stack 401s itself | Medium | Medium | `service_headers()` returns `{}` rather than raising, so the failure is a clean 401."*

**Why it's wrong:** This is not a risk that *might* happen, it is the guaranteed state between merge and V1. `JARVIS_AUTH_ENABLED` defaults to `true`; `JARVIS_SERVICE_TOKEN` lives only in the vault and only reaches `os.environ` via `inject_env()`; on a fresh clone or a machine whose vault does not yet hold it, `service_headers()` returns `{}` and *every* internal caller 401s: the three watchers, `mcp-selfedit`, `mcp-web`, `mcp-apps`, and the bot's clipboard tools. The plan puts the mint inside §5 as "Larry's action" but the commands only appear in §8, which is the post-implementation verification section. The implementer cannot run it, and nothing in the plan tells Larry that the merge itself is the trigger.

Worse, the failure is narrated wrongly. `mcp_servers/mcp_selfedit/logic.py:20-26`'s `OFFLINE_ERROR` — *"the admin sidecar looks offline … Start the stack with ./scripts/mortimer.sh"* — is what `_call` returns on a transport exception; a 401 returns the JSON body instead, so R4 is right that the text differs, but the *watchers* have no such handling at all: `plan_watcher._default_fetch_job` and `research_watcher._default_fetch_job` return `resp.json()` unconditionally, so a 401 body flows into the announcement logic as if it were a job document.

**Fix:** Promote the mint to **§5 Step 0**, before any code change, with the exact commands (and note that `python -m jarvis.vault set JARVIS_SERVICE_TOKEN` is correct — verified at `jarvis/vault.py:554-556`). Add a one-line startup guard in each process: if `auth_enabled()` and `service_headers() == {}`, log `ERROR service_token_missing …` naming `python -m jarvis.auth add service-bot`. Add a `resp.raise_for_status()`-equivalent to the two watchers so a 401 is logged as an auth failure rather than parsed as a job.

---

### F12 — §4's manifest omits two files that §5 modifies, and §11's own count disagrees with §4 [MAJOR]

**Where:** §4 ("Every file touched by §5 appears here. Nothing else is touched."), §5 Step 9, §5 Step 1, §11 item 9.

**What the plan says:** §4 Modify table, 26 rows; §11 item 9 — *"Every file mentioned in §5 appears in §4's manifest (12 created, **22 modified paths**, 0 deleted, 1 Larry commit)."*

**Why it's wrong:** Two files are modified by §5 and absent from §4:
- `scripts/mortimer.sh` — §5 Step 9: *"`scripts/mortimer.sh:25` — `ADMIN_PORT=7861` becomes `ADMIN_PORT="${JARVIS_ADMIN_PORT:-7861}"`"*.
- `tests/unit/test_db.py` — §5 Step 1's *"**Test that proves it** — `tests/unit/test_db.py`, add: …"* (§7 mentions it under "Modified", §4 does not list it).

And §4's table has 26 rows while §11's self-audit, which claims to have cross-checked exactly this, says 22. Self-audit item 9 is the one item that was supposed to catch this and it reported a number it did not derive.

**Fix:** Add both rows to §4's Modify table (bringing it to 28), correct §11 item 9's count, and re-derive it by counting rather than restating.

---

### F13 — §7's test counts do not match §7's own tables, and §8 V10's pass criterion is built on the wrong number [MAJOR]

**Where:** §7 header, per-file headers, §8 V10.

**What the plan says:** §7 — *"New: **5 files, 42 tests**."*; `tests/unit/test_auth.py` — *"18 tests"*; `tests/unit/test_bind.py` — *"8 tests"*. §8 V10 — *"Expected: previous count + **42** new unit tests, all green."*

**Why it's wrong:** Counting the rows in §7's own tables: `test_auth.py` 21 (T-A1…T-A13, T-A14a, T-A15, T-A16, T-A17a, T-A18a, T-A19a, T-A20a, T-A21a), `test_auth_middleware.py` 9, `test_bind.py` 9 (T-A23…T-A28, T-A29a, T-A30a, T-A31a), `test_service_token.py` 5, `test_bot_server.py` 6 — **50**, not 42. Two per-file headers also contradict their own tables (18 vs 21, 8 vs 9). V10's acceptance is a literal arithmetic check, so it fails on a correct implementation. §5 Step 5 also mis-cites the middleware file's range as *"§7 T-A14 … T-A20"* when the table runs T-A14…T-A22 and T-A20 belongs to `test_bot_server.py`.

**Fix:** Recount, fix the three headers and V10's number, and give every test a unique id (drop the `a`/`b` suffix scheme — T-A14/T-A14a, T-A20/T-A20a/T-A20b and T-A29/T-A29a currently collide across tables, which is what let the counts drift).

---

### F14 — The WebSocket close code 4401 never reaches the client; it is delivered as an HTTP 403, and T-A22 cannot tell the difference [MINOR]

**Where:** §3 A6 (*"WebSocket: `{"type": "websocket.close", "code": 4401}` … 4401 is the conventional analogue of HTTP 401"*), §6 knob table, §7 T-A22.

**Why it's wrong:** A close sent before `websocket.accept` is a *handshake rejection*: uvicorn discards the application close code and answers the HTTP upgrade with `403 Forbidden`. So 4401 is unobservable, and a client cannot distinguish "no token" from Pipecat's own origin/ws-token rejections at `run.py:477, 481` (which also close with an application code before accept, and also surface as 403). T-A22 asserts the ASGI message the middleware *sent*, so it is green either way — it verifies the plan's intent, not the client's experience.

**Evidence** (plan's middleware verbatim, real uvicorn 0.46, `websockets` client):

```
WS no token -> InvalidStatus(Response(status_code=403, reason_phrase='Forbidden', ...))
WS good    -> hello
INFO:     127.0.0.1:40580 - "WebSocket /ws-client" 403
```

**Fix:** Keep the close (it is the correct ASGI shape) but stop describing 4401 as something a client sees. Either drop it from §6's knob table or annotate it *"ASGI-level only; uvicorn reports the rejection to the client as HTTP 403"*. If a distinguishable signal matters, send `websocket.http.response.start` with status 401 and the `WWW-Authenticate` header (ASGI's `websocket.http.response` extension, supported by uvicorn) and say so explicitly.

---

### F15 — `auth_enabled()`'s parsing rule — the whole kill switch — has no test [MINOR]

**Where:** §3 A5 table, §5 Step 2, §7 `tests/unit/test_auth.py`.

**What the plan says:** *"Only the exact string `"false"` (case-insensitive, stripped) turns it off; a typo like `"0"` or `"no"` leaves auth ON."*

**Why it's wrong:** None of `test_auth.py`'s 21 listed tests exercises `auth_enabled()`. The only coverage is T-A21b, which sets `"false"` and expects a 200 — the happy path. The rule that actually matters (`"0"`, `"no"`, `"False "`, `"FALSE"`, `""`, unset) is untested, in a codebase whose two most recent escaped defects were both untested string rules that read correctly.

**Fix:** Add `test_auth_enabled_table` with the literal cases: unset → True; `"true"` → True; `"false"`/`"False"`/`"FALSE"`/`" false "` → False; `"0"`/`"no"`/`"off"`/`""` → **True**. State the `""` case explicitly — `os.environ.get(ENABLED_ENV, "true")` returns `""` for an env var set to empty, which strips-and-lowers to `""`, which is `!= "false"`, so auth stays on. That is the right answer but it is arrived at accidentally and nothing pins it.

---

### F16 — Unauthenticated `OPTIONS` is a route-enumeration oracle [MINOR]

**Where:** §3 A6 (*"The `OPTIONS` pass-through branch"*).

**What the plan says:** *"It is not a hole: `OPTIONS` on a FastAPI app with no `OPTIONS` handler returns `405` from the router."*

**Why it's wrong:** 405-vs-404 is itself information, and the 405 carries an `Allow` header naming the methods. An unauthenticated caller inside the tunnel can map the sidecar's entire surface — which paths exist and which verbs they take — without a token. Given A4's insistence that not even `/api/health` may leak, this is inconsistent with the plan's own posture.

**Evidence** (plan's middleware + the plan's CORS config, sidecar ordering):

```
 bare OPTIONS (no auth):        405 Allow: HEAD, GET   b'Method Not Allowed'
 bare OPTIONS unknown path:     404                     b'Not Found'
```

**Fix:** Narrow the branch to genuine preflights: pass through only when the request has **both** an `Origin` header and an `Access-Control-Request-Method` header; reject everything else with the normal 401. Add a test for `OPTIONS /api/health` with no `Origin` → 401.

---

### F17 — A14 is internally inconsistent: heading says two entries, body lists three, and its stated reason contradicts the reason it gives for excluding `jarvis/urls.py` [MINOR]

**Where:** §3 A14, §5 Step 12, §8 V8, §12.

**What the plan says:** heading *"A14 — **Two** deny-list entries"*; body lists `jarvis/auth.py`, `jarvis/authmw.py`, `jarvis/bind.py`; *"`jarvis/urls.py` needs no entry for the same reason D-H9 gives for `jarvis/sensitive.py`: it matches no allow pattern. The three above **do** need entries because the self-edit allowlist includes `jarvis/services/**` and `tests/**` and has historically been widened."*

**Why it's wrong:** Both halves are about the same allowlist, and neither `jarvis/auth.py` nor `jarvis/authmw.py` nor `jarvis/bind.py` matches any allow pattern either — the allow list has no `jarvis/**` entry at all (`web/src/**`, `web/public/**`, `config/**`, `jarvis/prompts.py`, `jarvis/skills/**`, `jarvis/services/**`, `mcp_servers/**`, `tests/**`, `docs/**`, `*.md`). So the distinction drawn between `urls.py` and the other three is not a real one. (Adding the three anyway is defensible as defence-in-depth against future widening — but then `urls.py` should be added too, since a self-editable `bot_url()`/`admin_url()` redirects every internal caller.)

**Fix:** Fix the heading to "Three", state the real reason once ("none of these match an allow pattern today; the deny entry is insurance against the allow list being widened"), and add `jarvis/urls.py` to the list for the same reason. Update §8 V8, §12's checklist line, and Step 12's `missing` tuple to the same four paths.

---

### F18 — §6 claims every value lives in exactly one place; the sidecar port and the admin base URL each live in four, in two different spellings [MINOR]

**Where:** §6 opening (*"Every value below is defined in exactly **one** place. If you find a second definition, that is the bug."*), A11.

**Why it's wrong:** `7861` is defined in `jarvis/urls.py` (`DEFAULT_ADMIN_URL`), as a literal argument in `jarvis/admin/server.py:main()` (`resolve_port("JARVIS_ADMIN_PORT", 7861)`), in `web/src/api.ts`'s fallback, and in `ShellAuth.swift`'s fallback — §6's own table lists all four. Worse, they disagree on host: `jarvis/urls.py` says `http://127.0.0.1:7861`, `web/src/api.ts` says `http://localhost:7861`. A11's *"the only literal hosts left in the repo are …"* then enumerates five places, which is the same admission.

**Fix:** Soften §6's opening to what is actually true ("every value has one owner per runtime; the Swift and TypeScript fallbacks are separate runtimes and are listed here"), and make the two web fallbacks `127.0.0.1` so all four spellings match `jarvis/urls.py`. Have `admin/server.py:main()` derive its default port from `jarvis.urls` rather than repeating `7861`.

---

### F19 — `JARVIS_BOT_PORT` / `JARVIS_ADMIN_PORT` are introduced but not documented, and nothing keeps them in sync with `JARVIS_BOT_URL` / `JARVIS_ADMIN_URL` [MINOR]

**Where:** §5 Step 7 (`BOT_PORT_ENV`), §5 Step 9 (`resolve_port("JARVIS_ADMIN_PORT", 7861)`), §6, §5 Step 11 (`.env.example`).

**Why it's wrong:** §6 lists both as knobs with env overrides, but Step 11's `.env.example` block documents only `JARVIS_AUTH_ENABLED`, `JARVIS_BIND_HOST`, `JARVIS_ADMIN_URL`, `JARVIS_BOT_URL`. A knob that exists and is undiscoverable is a knob nobody can use safely. And they are independently settable from the URLs they must agree with: setting `JARVIS_BOT_PORT=7999` moves the listener while `JARVIS_BOT_URL` still says `:7860`, so every client silently points at nothing. K5's premise is one base URL per client; two more independent port knobs undercut it.

**Fix:** Either drop the port env vars (derive both ports by parsing `admin_url()` / `bot_url()` in `jarvis/urls.py`, which is the module K5 makes responsible for this) or add all four names to `.env.example` with a stated rule that the URL and the port must agree, plus a startup WARNING when they do not.

---

### F20 — The `spoken_acceptance.py` snippet uses `os` in a file that does not import it [MINOR]

**Where:** §5 Step 7 "Also in Step 7 (both branches)"; §0.5 (*"Write the code in §5 verbatim"*).

**What the plan says:** `default=os.environ.get("JARVIS_SERVICE_TOKEN", "")`.

**Why it's wrong:** `scripts/spoken_acceptance.py` imports `argparse, asyncio, fractions, json, logging, re, sys, time, wave, httpx` — no `os`. Written verbatim, the parser construction raises `NameError` and the script is dead. §0.5 forbids the implementer from "improving" §5's code, so a literal reading produces a broken script.

**Fix:** Say "add `import os` beside the existing stdlib imports" in the same step.

---

### F21 — Service-token rotation is undocumented and A2 makes it awkward; MCP children cache the header for the life of the process [MINOR]

**Where:** §3 A2, §5 Step 6(b), §9.

**Why it's wrong:** §9 covers revoking *client* tokens and says revocation is instant. Nothing covers rotating the **service** token, which is the one credential every internal caller shares. A2 forbids reusing the name, so rotation is `add service-bot-2` → `vault set` → `revoke service-bot` → restart. And `AdminClient.__init__` captures `headers=service_headers()` once into a long-lived `httpx.Client`; `mcp_selfedit/server.py:21` and `mcp_apps/server.py:30-33` cache that client for the process lifetime, so a rotated token does not take effect in an MCP child until the registry restarts it. `jarvis/bot/pipeline.py:413-429` builds a fresh `AdminClient` per call and *does* pick it up — an asymmetry nothing states.

**Fix:** Add a "Rotating the service token" paragraph to §9 with the exact four-step sequence and the explicit note that both long-lived processes must be restarted. State in A5 that `service_headers()` is read once per `AdminClient` and is therefore process-lifetime.

---

### F22 — Two citation slips [MINOR]

**Where:** §3 A10; §4's Modify count note.

- A10 and §5 Step 7 cite the runner-app docstring as `run.py:169-178`. It runs **169-183** (`app: FastAPI = FastAPI()` is line 168; the docstring closes at 183). The substance of the citation is correct — the docstring does say *"Import this to add custom routes from other packages before calling `main()`"* — only the range is short.
- §4's note *"26 rows, 26 distinct paths"* is right for the table as written but contradicts §11 item 9's "22" (see F12).

**Fix:** Correct the range; reconcile the counts.

---

## What I verified and found correct

- **Branch A holds.** `pipecat/runner/run.py:168` is exactly `app: FastAPI = FastAPI()`; its docstring documents importing it before `main()`; `main()` (line 1394) ends with `_configure_server_app(args)` at 1570 and `uvicorn.run(app, host=args.host, port=args.port)` at 1573 — the **same module global**, never a fresh instance. Starlette 1.0.0's `add_middleware` inserts at index 0 (`applications.py:101`) and the stack is built lazily in `__call__` (`applications.py:86-90`), so middleware added before `main()` does take effect and the "last added is outermost" claim is exact.
- **The `BaseHTTPMiddleware` claim is true.** `starlette/middleware/base.py:101-104` — `if scope["type"] != "http": await self.app(...); return`. Four `@app.websocket` routes exist at `run.py:486, 491, 1274, 1279`. An implementer reaching for `@app.middleware("http")` really would ship them unauthenticated. R-A3 is correct and R2 is a real risk correctly rated.
- **The pure-ASGI middleware works.** Ran it verbatim under uvicorn 0.46 with a real WebSocket client: unauthenticated HTTP → 401 with `www-authenticate: Bearer realm="jarvis"` and the exact JSON body; authenticated HTTP → 200; unauthenticated WS → handshake rejected, inner app never called; authenticated WS → connects and receives. Only the *close code's* visibility is wrong (F14).
- **47 sidecar routes, zero exemptions, and nothing the decorator grep misses.** `grep -c '@app\.' jarvis/admin/server.py` → 48, of which one is `@app.middleware("http")` at 133 (`_log_5xx_responses`), leaving exactly 47 routes; every line number in §1.2's table matches. `grep -n 'include_router\|StaticFiles\|app.mount\|add_api_route\|add_websocket_route\|@app.websocket\|add_route\|APIRouter' jarvis/admin/server.py` → **no matches**, so there is no router, mount, or sub-app to miss. `docs_url=None, redoc_url=None, openapi_url=None` at line 105 is confirmed, so `[r for r in app.routes if isinstance(r, APIRoute)]` really does yield 47.
- **`jarvis/auth.py` as written is correct.** Ran the module verbatim against the plan's migration: token shape (`jvt_` + 43 chars from `[A-Za-z0-9_-]`, length 47, unique); `parse_bearer` accepts `bearer`/`BEARER`, collapses whitespace runs and leading/trailing space, and rejects `None`, `"   "`, three-field headers and wrong lengths; `verify_bearer` returns `None` for a malformed token **without touching the connection** (a `RaisingConn` is never called); valid → `ClientIdentity(name="phone", user_id="larry")` with `last_used_at >= created_at`; revoked → `None` **and** `last_used_at` stays `NULL`; duplicate `add` returns 2 both before and after `revoke` and the row count stays 1; `list` prints no 64-hex run; `count_active_tokens` excludes revoked and returns 0 on a database that has never been migrated; `service_headers()` handles unset/empty/whitespace exactly as A5's table says. 11/11 passed.
- **No plaintext in the database.** T-A15's premise holds despite WAL: after `_cmd_add`, the token body is absent from `t.db`'s bytes and the SHA-256 hex is present (the connection close checkpoints).
- **Revocation is immediate, with no restart.** Verified in-process: valid → identity, `revoke` → `None` on the very next call. A6's no-cache decision does deliver the property it claims.
- **The conftest fixture-ordering claim is true.** Built the two-level fixture arrangement and ran it: a conftest-level autouse fixture setting `false` runs first and a module-level autouse fixture (or an explicitly-requested one) setting `true` wins. Both shapes pass.
- **`python -m jarvis.vault set <NAME>` is real** (`jarvis/vault.py:554-556`, value via `getpass`, never argv) — §8 V1's command is correct.
- **`.env` does reach `os.environ`.** `scripts/run_bot.sh` and `scripts/run_admin.sh` both do `set -a; . ./.env; set +a`, so `JARVIS_BIND_HOST` / `JARVIS_AUTH_ENABLED` placed in `.env` (V5c) are visible to `os.environ.get`. pydantic-settings alone would not have done this; the plan is right not to worry.
- **Bot-function discovery survives the new entrypoint.** `_get_bot_module()` (`run.py:386-396`) resolves `sys.modules["__main__"]` and checks `hasattr(main_module, "bot")`. Because `scripts/run_bot.sh` still runs `python -m jarvis.bot.bot` and `bot.py` still defines `async def bot(...)`, routing the `__main__` block through `jarvis.bot.server.main()` does not break discovery. (It *would* break if anyone ran `python -m jarvis.bot.server`, which the plan's own `if __name__ == "__main__"` block in that file invites — worth a one-line warning comment, but no route in the plan takes it.)
- **`_wait_for_host` terminates.** The loop checks `time.monotonic() >= deadline` before each sleep; it cannot hang indefinitely. (Its *consequence* is F8, not its termination.)
- **Line citations spot-checked and correct:** `jarvis/admin/server.py:105` (FastAPI ctor), `:107-113` (CORS, `allow_headers=["Content-Type"]` — `Authorization` genuinely absent), `:133-146` (`_log_5xx_responses`), `:1768` (`def main`), `:101` (`inject_env()` at module top); `jarvis/db.py:451` (`("0015_memory_reviews", MIGRATION_0015)` is the newest tuple), `:455-456`, `:470-472`, `:475-499`; `jarvis/bot/bot.py:50-53` (the `__main__` block, file is 53 lines) and docstring line 4; `jarvis/skills/registry.py:192`; `mcp_servers/mcp_selfedit/logic.py:19-20, 29-44`; `mcp_servers/mcp_selfedit/skill.yaml:18` (`requires_env: []`) and `mcp_apps/skill.yaml:7` (`[GITHUB_TOKEN]`); `scripts/mortimer.sh:25` (`ADMIN_PORT=7861`), `:94-100` (`check()` uses `kill -0`), `:102`; `README.md:345`; `web/src/components/*.tsx` `const API` lines at 9/3/3/3/3/4; `pipecat/runner/run.py:161-162, 251-315, 455-537, 741-757, 796, 827, 1060-1086, 1199-1279, 1394, 1570-1573`.
- **`jarvis/config.py:80`'s `jarvis_webrtc_endpoint` really is dead** — the only reference in the repo is its own definition. R-A4 is correct.
- **CI will not be blocked by the allowlist gate.** `scripts/check_allowlist.py:36-39` exempts any branch not starting `jarvis/self-edit`, so `feat/remote-access-t2` touching `jarvis/**` is fine. `scripts/check_skills.py` is genuinely absent from `.github/workflows/validate.yml`, as §1.6 claims.
- **The migration is well-formed and idempotent.** Applied `MIGRATION_0016` to a copy of `jarvis/db.py` and ran `run_migrations()` twice: `0016_client_tokens` applied once, second run returns `[]`, column shape and nullability match §5 Step 1's assertions. Append-only, one migration for the plan, matching the file's own rule.
- **`DELETE /api/memory/fact/{key}` really was un-preflightable** (`allow_methods=["GET","POST"]` today). Step 4's addition of `"DELETE"` is a genuine pre-existing-defect fix, correctly flagged as R13.
