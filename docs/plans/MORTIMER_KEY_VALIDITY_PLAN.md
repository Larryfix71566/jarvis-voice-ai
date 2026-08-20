# Mortimer — API Key Validity

**Status: APPROVED by Larry 2026-08-19 — IMPLEMENTED**
Author: Claude, 2026-08-19. Requested by Larry.

---

## 0. The one-sentence problem

Every credential check in this system asks *"is the variable set?"* — and the
only check that asks *"does the credential work?"* is `github_probe`, which
exists because `check_env.py` reported PASS for two days against a dead
`GITHUB_TOKEN`. That lesson was never carried to a single LLM key.

Verified 2026-08-19, every LLM key check in the repo:

```
jarvis/agents/base.py:200            if not os.environ.get(key_env)
jarvis/agents/upgrade_agent.py:306   not os.environ.get(self._api_key_env)
jarvis/council/council.py:223        raise RuntimeError(f"{api_key_env} is not set")
scripts/check_env.py:202,230,279,285 bool(os.environ.get(key_env,"").strip())
```

Three keys cover five profiles:

| env var | profiles | lost when invalid-but-present |
|---|---|---|
| `MOONSHOT_API_KEY` | kimi-k3 *(registry default + developer's profile)*, kimi-k2 | developer sub-agent, self-edit planner default, council economy proposers |
| `ANTHROPIC_API_KEY` | claude-opus, claude-fable-5 *(both frontier, both `vision: true`)* | council tier-2 proposers **and** judges, shadow judging, all screen vision |
| `OPENAI_API_KEY` | gpt-4.1-mini, plus the voice model and every fallback client | the voice loop, and the destination everything else falls back to |

---

## K1 — One live probe per key, reusing the pattern that already works

New in `scripts/check_env.py`, beside `github_probe`:

```python
def model_key_probe(base_url: str, api_key: str) -> tuple[str, str]:
    """Return (outcome, detail); outcome is "ok" | "rejected" | "unreachable"."""
```

Non-negotiable properties, all inherited deliberately from `github_probe`:

- **`rejected` and `unreachable` stay distinct.** A dead key and a blocked
  network both stop the request and call for opposite responses. Collapsing
  them is the invent-a-cause error `AGENT_DISCIPLINE` exists to prevent.
- **Never returns `ok` for something not actually reached.**
- **Never logs, prints, or returns the key**, not even a prefix. The value
  appears in exactly one place: the `Authorization` header of the request.

Probe **once per distinct `api_key_env`**, not once per profile — three
calls, not five. Profiles sharing a key are reported together so a single
`MOONSHOT_API_KEY` rejection reads as one problem, not two.

**Endpoint: `chat.completions.create`, NOT `GET /models`.** This is settled
by measurement, not preference.

The first cut of `scripts/check_keys.py` probed `GET /v1/models` because it
is free and read-only. Run on Larry's machine 2026-08-19, it reported
`ANTHROPIC_API_KEY` and `OPENAI_API_KEY` as **REJECTED (401)** — while
Mortimer was answering questions by voice on that exact key. Anthropic's
OpenAI-compatibility layer authenticates `/chat/completions` with a Bearer
token but does not serve `/models` the same way, so a valid credential
returns 401.

The rule this establishes, and the one K1 must not break: **a probe has to
exercise the same call the consumers make.** `SubAgent`, `UpgradeAgent` and
the council all issue `chat.completions.create`; a verdict drawn from any
other endpoint answers a different question than the one asked. Auth is
evaluated before request validity, so any status other than 401/403 means
the key was accepted — even a 400 — and must be reported as OK with the
reason attached, never as a failure.

The plan's own guard said *"do not ship a probe whose `ok` has never been
observed against a working key."* It said nothing about `REJECTED`, and
that omission is what produced a false "renew this key" against a live
credential. **Both verdicts need observation against a known state before
this ships.**

`check_env.py` gains one line per key env: profiles covered, outcome,
detail.

## K2 — Say where each secret came from

The nastiest gap and the cheapest fix. The vault's precedence rule is that
**a non-empty environment variable beats the vault**. So rotating a key
correctly in the vault while a stale `export` sits in the shell produces
permanent, silent failure — and nothing anywhere reports which source won.

`check_env.py` records `os.environ` **before** `inject_env()` and reports
each key's source as `env` / `vault` / `.env`. When the source is `env`
and a vault entry also exists, that shadowing is called out explicitly —
it is a misconfiguration, not a preference.

Same rule as K1: names and sources only, never values.

## K3 — `python -m jarvis.vault verify`

A new read-only subcommand: for every stored secret whose name maps to a
profile's `api_key_env`, run K1's probe and print name / source / outcome.
Never prints values, writes nothing, and joins `status`/`list` as the third
non-mutating verb.

Deliberately **not** wired into `set`: a probe at write time would make
storing a key fail when the network is down, and the vault must stay usable
offline. Verification is a separate act you invoke.

## K4 — A key that doesn't work must not read as healthy on screen

The 2026-08-19 model chip shows `SubAgent.model` and an amber `⚠` for
`model_is_fallback`. A present-but-invalid key sets **neither** — profile
resolution succeeds, so the card shows `kimi-k3` in normal styling while
every call 401s. The chip is currently capable of lying, and this is the
gap that closes it.

At bot startup, beside the run-log prune and orphan reconciliation, probe
each distinct `api_key_env` referenced by a configured profile:

- **Best-effort and non-blocking.** Short timeout, failures logged, boot
  never prevented. An unreachable network at boot must not stop the voice
  loop — it yields `unreachable`, which is not `rejected` and must not be
  rendered as a dead key.
- Result held in a module-level map, consulted by `SubAgent` to set a new
  `model_unusable` flag alongside `model_is_fallback`.
- Travels the same `delegate_start` → `pipeline.py` → `agentRuns.ts` path
  the model chip already uses; renders red (not amber — amber means
  *needs your confirmation*, per the engagement layer's semantic colors),
  titled with the probe's own detail string.

## K5 — Decide `on_profile_fallback` instead of inheriting it

Verified 2026-08-19: the key is set **nowhere** in `config/`, so every
agent runs the `warn` default and H1's refuse mode — built for exactly
this class of problem — is armed for nothing.

This step is a decision, not code: set it explicitly for `developer`.
Recommendation `refuse`, because a build-grade task silently executed by
the voice dispatcher produces plausible-looking work from the wrong model,
which is harder to catch than a refusal. Larry decides; either way the
value stops being implicit.

Separately, `on_profile_fallback` covers *missing*, not *invalid*. K4's
flag is what extends it, and the two must agree — a refusing agent should
refuse for both reasons or the setting means half of what it says.

## K6 — Council must report who dropped out

[likely — the raise is verified, the fan-out exception handling is not]
`council.py:223` raises on a missing key. On an invalid one, members fail
mid-fan-out. With `ANTHROPIC_API_KEY` dead, tier 2 loses both frontier
proposers *and* both frontier judges, while `COUNCIL_JUDGE_TARGET`'s
backfill walks upward from mid into the same broken tier.

First step is to **read the fan-out error handling and record what
actually happens** before writing a fix. Then: a round records which
members were attempted and which failed, and `--agreement` reports rounds
that ran short-handed rather than averaging them in silently. A round
decided by one surviving judge is not the same evidence as one decided by
three, and today the difference is invisible.

## K7 — Screen vision needs an auth heuristic, not just a permission one

`MIN_SCREENSHOT_BYTES` exists specifically because macOS Screen Recording
denial fails *silently* into a wallpaper-only image. There is no equivalent
for a dead key — and since both `vision: true` profiles are Anthropic, one
bad `ANTHROPIC_API_KEY` kills vision entirely while `_resolve_vision_profile`
reports success, because the key is present.

`screen_view` distinguishes an auth failure from every other error and says
so — *"the vision model rejected the credential"*, never a generic error
that reads like a capture problem. Same reasoning as `mcp_apps`' 401/403
message: a 401 reported as "the sidecar may be offline" is the original
sin this codebase keeps correcting.

---

## What this deliberately does not do

- **No probe at `vault set` time** (K3) — the vault must work offline.
- **No probe per delegation.** K4 probes once at startup. A key that dies
  mid-session is caught by the call failing, not by polling.
- **No key values anywhere** — not in logs, not in errors, not truncated,
  not prefixed. Every step states this because it is the one property that
  cannot be added later.
- **No new secret storage path.** Everything reads through `inject_env()`.

## Acceptance

1. `python scripts/check_env.py` reports outcome **and source** for all
   three key envs, with `rejected` distinct from `unreachable`.
2. K1's `ok` observed against a real working key before merge (§K1).
3. Deliberately break one key in a scratch env → `check_env.py` says
   `rejected`, the Agents tab chip renders red, and no key value appears
   anywhere in output or logs.
4. Disconnect the network → same key reports `unreachable`, not
   `rejected`, and the bot still boots.
5. `python -m jarvis.vault verify` runs read-only and prints no values.
6. `pytest tests/unit tests/integration -q` green; probes are injected
   seams so no test makes a network call.

## Approval

- [x] K1 — live probe, one per distinct (key, ENDPOINT) pair
- [x] K2 — report secret source (env vs vault shadowing)
- [x] K3 — `python -m jarvis.vault verify`
- [x] K4 — startup probe (`jarvis/keyhealth.py`) + red `model_unusable` chip
- [x] K5 — refuse mode IMPLEMENTED, then set on developer
- [x] K6 — migration 0014 + short-handed/single-proposer lines in `--agreement`
- [x] K7 — screen-vision auth failure named

## Deviations from the plan as written

**K1 grouped by (key, ENDPOINT), not by key.** The plan said "one probe per
distinct `api_key_env`". Wrong: `OPENAI_API_KEY` holds an ANTHROPIC key in
this deployment (`OPENAI_BASE_URL` points at Anthropic), so one probe per key
tested it against whichever endpoint won the grouping and produced a false
`REJECTED`. The endpoint is part of the question.

**K1's `unfunded` verdict was not in the plan.** Observed live: OpenRouter
returned HTTP 402 — a genuinely valid key with no balance. Reported as `ok`
it promises a model that will never answer; reported as `rejected` it sends
you to rotate a good key. Neither neighbour is honest, so it gets its own
verdict.

**K5 was not "a decision, not code".** `on_profile_fallback` was read by
`scripts/check_env.py` and by NOTHING in `jarvis/`. The preflight printed
"on_profile_fallback=refuse" and warned that such an agent refuses every
delegation, while `SubAgent` fell back to the voice model silently. The mode
had to be built before it could be set. Every other gap found this day was a
silent failure; this was a silent *reassurance*, which is worse.
