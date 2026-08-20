# Mortimer — `.env` is not `os.environ`

**Status: APPROVED by Larry 2026-08-19 — IMPLEMENTED**
Author: Claude, 2026-08-19. Requested by Larry.

---

## 0. The bug, and the class it belongs to

`RUN_LIVE=1 python -m tests.evals.routing_eval` crashed every `set_reminder`
call with:

```
ZoneInfoNotFoundError: 'No time zone found with key ${JARVIS_TIMEZONE}'
```

The literal seven characters `${JARVIS_TIMEZONE}` reached the child process
as its timezone.

**Reminders are NOT broken in production**, and my first report that they
were was wrong. Verified 2026-08-19:

| entrypoint | calls `bridge_settings_to_env`? | reminders |
|---|---|---|
| `jarvis/bot/pipeline.py:509` (the bot) | yes | work |
| `jarvis/cli.py:38` (text REPL) | yes | work |
| `tests/integration/test_orchestrator_live.py:28` | yes | work |
| **`tests/evals/routing_eval.py`** | **no** | **crash** |

`.env` line 32 does set `JARVIS_TIMEZONE=America/New_York`, and
`ZoneInfo('America/New_York')` resolves fine on this machine — `tzdata` is
a red herring, also mine. The single difference is the bridge call.

### Why this matters more than one missing line

`.env` is a FILE. `os.environ` is a PROCESS. pydantic-settings reads the
file into a `Settings` object; nothing puts those values into the
environment unless something explicitly does. `bridge_settings_to_env`
(`jarvis/cli.py:26`) is that something, and it must be called before
`SkillRegistry.start()` or MCP children inherit nothing.

I made this exact mistake three times on 2026-08-19 alone:

1. `scripts/check_keys.py` grouped probes by key name and read
   `OPENAI_BASE_URL` from `os.environ`, which defaulted to
   api.openai.com and produced a false REJECTED on a live key.
2. `scripts/check_env.py`'s `check_model_keys` repeated it — same variable,
   same default, this time a required-check FAIL on a healthy system.
3. This one, reported to Larry as "reminders are broken in production."

Three instances, one root cause, and in every case the symptom pointed
somewhere other than the cause. That is the argument for a structural fix
rather than a fourth careful call site.

---

## E1 — Move the bridge inside `SkillRegistry.start()`

`jarvis/skills/registry.py`'s `start()` calls `bridge_settings_to_env`
itself, before spawning any child.

This is the same "one call site, not a convention" move `inject_env()`
already made by living at the top of `load_settings()` rather than being
remembered at four places. Any future entrypoint that starts a registry
gets a correct child environment without knowing this rule exists.

Properties that must hold:

- **Idempotent.** `bridge_settings_to_env` already uses
  `os.environ.setdefault`, so an explicit env var still wins and calling it
  twice changes nothing. The three existing call sites therefore stay
  exactly as they are — this plan REMOVES no call, because a caller that
  bridges before doing other work is not wrong, and deleting those lines
  would be an unrelated change riding along.
- **No import cycle.** `registry.py` importing from `jarvis.cli` would be
  backwards (the CLI is a consumer). `bridge_settings_to_env` moves to
  `jarvis/config.py`, beside `load_settings` and `expand_env_vars` — the
  module that already owns "where configuration comes from". `jarvis/cli.py`
  re-exports it so existing imports keep working.
- **Best-effort, never fatal.** A `Settings` that cannot be constructed
  must not turn "one server has a stale env entry" into "the bot will not
  start". Log and continue.

## E2 — A literal `${VAR}` is a configuration ERROR, not a value

`expand_env_vars` (`jarvis/config.py`) leaves an unresolved `${VAR}` as
literal text by design, and that design is load-bearing elsewhere. But
handing a child process the string `"${JARVIS_TIMEZONE}"` is never correct
— it is always a misconfiguration, and today it surfaced as a
`ZoneInfoNotFoundError` from inside a subprocess, five frames deep, with
nothing naming the actual problem.

`SkillRegistry._start_server` logs one WARNING per unresolved variable:

```
mcp_server_env_unresolved server=mcp-reminders var=JARVIS_TIMEZONE
```

**A warning, not a refusal.** Refusing to start the server would convert a
degraded reminder into a dead voice loop, and CLAUDE.md already records the
precedent — `mcp_git`/`mcp_repo` defend by *ignoring* `"${"`-containing
values rather than raising. This makes the condition visible at the moment
it happens, in the parent, with the variable named.

`mcp_reminders/logic.py`'s `_tz()` gains the same defence those two already
have: a value containing `"${"` is treated as unset and falls back to UTC,
with a warning. Wrong-but-running beats a stack trace, and the warning is
what makes it findable.

## E3 — Fix the eval

`tests/evals/routing_eval.py` gets the bridge for free from E1. No change
needed there, and that is the point — the fix is the absence of a fourth
thing to remember.

## E4 — The test that would have caught it

`tests/unit/test_registry_env.py`:

| test | pins |
|---|---|
| `test_start_bridges_settings_into_the_environment` | E1 — a registry started with no prior bridge call still gives children `JARVIS_TIMEZONE` |
| `test_an_explicit_env_var_still_wins` | `setdefault` semantics; the CI/override channel is unaffected |
| `test_an_unresolved_var_is_logged_with_its_name` | E2 — the warning names the server AND the variable |
| `test_an_unresolved_var_does_not_prevent_startup` | degraded, never dead |
| `test_tz_treats_a_literal_placeholder_as_unset` | `mcp_reminders._tz()` returns UTC rather than raising |

No child processes are spawned: `_start_server` is stubbed, and `_tz` is
called directly.

---

## What this plan deliberately does not do

- **No change to `expand_env_vars`' behaviour.** Leaving unknown `${VAR}`
  literal is documented and relied upon. This plan makes the consequence
  visible; it does not change the rule.
- **No removal of the three existing `bridge_settings_to_env` calls.**
  Idempotent, harmless, and deleting them is an unrelated edit.
- **No `tzdata` dependency.** Verified 2026-08-19:
  `ZoneInfo('America/New_York')` resolves on Larry's machine. The
  `ModuleNotFoundError` in the traceback was `zoneinfo`'s last-resort
  lookup for a zone that does not exist under any name.
- **Nothing about the 89% routing eval.** Unrelated: `SUPERVISOR_PROMPT` is
  byte-identical to HEAD (5,503 chars) and the cases file is untouched, so
  the six misses are not caused by anything in this plan or by the
  2026-08-19 work. Re-running is the way to tell variance from regression.

## Acceptance

1. `RUN_LIVE=1 python -m tests.evals.routing_eval` produces **no**
   `ZoneInfoNotFoundError` — the scheduler cases' tool calls succeed rather
   than merely routing correctly.
2. Deliberately break it: add `FOO: "${NOT_SET_ANYWHERE}"` to a server's
   env in `config/mcp_servers.yaml` → one WARNING naming `mcp-<server>` and
   `NOT_SET_ANYWHERE`, and the bot still starts.
3. `pytest tests/unit tests/integration -q` green.
4. `./scripts/mortimer.sh` → set a reminder by voice, confirm it lands at
   the right local time. This is the one that matters: the bug was
   invisible from the eval's own report, which scored those cases `ok`
   because it measures routing and the tool failed behind it.

## Approval

- [x] E1 — bridge inside `SkillRegistry.start()`, moved to `jarvis/config.py`
- [x] E2 — warn on unresolved `${VAR}`; `_tz()` treats it as unset
- [x] E4 — tests (9, in `tests/unit/test_registry_env.py`)

## Deviation from the plan as written

**E1 needed a `.env` fallback the plan did not anticipate.** As specified,
the bridge called `load_settings()` — which FAILS without OPENAI_API_KEY,
DEEPGRAM_API_KEY and ELEVENLABS_API_KEY, none of which it needs. On a fresh
checkout or in CI it therefore logged a warning and bridged nothing, leaving
children with the literal `${VAR}`: the original bug surviving in a
different form, and caught only because
`test_start_bridges_settings_into_the_environment` failed in the sandbox.

`_dotenv_values()` now parses the three names directly from `.env` when
Settings cannot be built. Same `setdefault` precedence. It is deliberately
NOT a second configuration system — it exists so this one function can do
its one job when full validation is impossible.
