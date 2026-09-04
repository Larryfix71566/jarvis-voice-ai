# Mortimer Plans — Final Verification Sweep

Date: 2026-08-27
Scope: Confirmation pass over the eight revised plans in `/home/claude/plans/out/`.
Not a re-review. Confirms blocker closure, cross-plan seam consistency, the two new
plans, roadmap-edit completeness, and residual honesty. Ends with GO/NO-GO per plan
and a consolidated "Larry must decide" list.

Sandbox artifacts for the re-measurements: `/home/claude/plans/review/sandbox/`.

---

## Headline

**7 of 8 plans are GO for handoff to Sonnet.** All top-severity blockers are closed
and confirmed *in their named sections*, and the four fixes that changed runnable
code were re-extracted and re-measured against the review's own breaking inputs — all
pass. Three of four cross-plan seams are clean; the two new plans reference reality.

**SEC is CONDITIONAL GO — two shared-artifact obligations it was assigned are unfinished**
(neither is a code defect; both are completeness gaps that four sibling plans depend on):
1. `docs/plans/ALLOWLIST_SEQUENCE.md` is never actually authored — SEC inlines only its
   own row W0; SKILL/REMOTE/LOCAL cite rows W0-SKILL/W1/W2 that SEC does not consolidate.
2. The roadmap §2.2 pointer to REMOTE's R-A1…R-A4 — REMOTE explicitly delegated this to
   SEC and makes no roadmap edit itself — is absent from SEC's Roadmap-edits section.

---

## 1. Blocker closure — top-3 findings per plan, verified in-section (+ re-measured code)

For each plan I opened the named sections (not just the revision table) and confirmed
the fix is present with substance. Where a fix changed runnable code I re-ran the
measurement myself against the review's breaking inputs.

### SEC (T4a) — F1, F2, F3 all BLOCKER — CLOSED
- **F1** (flag cleared too early): D-H4 + §5 Step 6 — flag is no longer cleared on
  `UserStoppedSpeakingFrame`; cleared on `UserStartedSpeakingFrame` / `InterruptionFrame`.
  Frame order stated in-section (§lines ~699–702). ✓
- **F2** (assistant reply never scanned): D-H4/D-H6, §5 Step 6b/6f — `arm_from_text` now
  runs on the reply text in both `TranscriptLogger` and `Orchestrator.chat`. ✓
- **F3** (detector fires on ordinary English): §5 Step 3 — `_FIN_WORD_RE` given `\b`
  boundaries; `_ACCOUNT_RE` rewritten to a connector-chain; `BALANCE_MIN_AMOUNT` 100→25.
  **RE-MEASURED** (`sandbox/sec_detect.py`): against all 19 F3 breaking negatives
  (`checking build 1049322`, `he borrowed $400`, `the flowers cost $120`, …) + 7 positives
  including the F2 balance leak `$2,431.18`: **19/19 negatives clean, 7/7 positives caught,
  0 FP / 0 FN.** ✓

### REMOTE (T2) — F1, F2, F3 all BLOCKER — CLOSED
- **F1** (401 carries no CORS header): A7 fully rewritten with the `add_middleware`
  insert-at-0 rationale; CORS is outermost in both processes; measured ACAO note in §7. ✓
- **F2** (§5 Step 6(d) deletes `TAVILY_API_KEY`): table corrected to append, never replace;
  new test asserts survival. ✓
- **F3/CP-F7** (service token leaks if REMOTE lands before SEC): §0.11 hard precondition
  gate (`stop if env = dict(os.environ)` still in registry.py) + environment-level test. ✓

### MAIL (T5) — F1, F2, F3 (top 3 of 4 BLOCKER) — CLOSED
- **F1** (`UNTRUSTED_EMAIL_HEADLINES` fence not covered by `_FENCE_RE`): M5/M10 unified to
  one fence family; sanitiser adds NFKC folding, notice-replay neutralisation, newline-split
  withholding. **RE-MEASURED** (`sandbox/mail_sanitise.py`): the F1 headlines-marker attack,
  the F8 invisible-smuggling set (U+2060 / U+00AD / TAG block), the F17 `>`-in-id and
  newline-split cases, homoglyph full-width brackets, and the notice-replay case — **all 9
  neutralised, no functional `<<<…>>>` fence survives.** ✓
- **F2** (`secretary` can mutate reminders): §7.3 contradiction rewritten; residual documented
  as RM-11a (see Larry list). ✓
- **F3** (`secretary` holds `mcp-screen`): dropped → `[mcp-mail, mcp-calendar, mcp-reminders]`;
  C6/RM-1 rewritten; text-laundering residual moved to §0.10/RM-1a. ✓
- **F4** (grounding check rejects every real summary): `unsourced_proper_nouns` replaced with
  an entity-subset check. **RE-MEASURED** (`sandbox/mail_ground.py`): 0/37 opener false-positives,
  possessive-of-digest-name passes, all fabricated entities caught, faithful summary passes.
  One cosmetic nit: the code returns offender `"HQ."` (trailing period retained) where the
  plan's §7.9 table shows `"HQ"` — security property intact, a test-expectation off-by-a-period.

### LOCAL (T3) — F1, F2, F3 all BLOCKER — CLOSED
- **F1** (`whisper_mlx` cannot import): §4 + requirements add `faster-whisper~=1.2.1` (Linux-CI
  importable), MLX pins platform-gated, test #4 `importorskip`-guarded. ✓
- **F2** (barge-in degrades under Whisper): raised to explicit Larry decision **L15** with two
  fully-wired configs, default = safe. ✓ (Larry list #1)
- **F3** (smart-turn analyzer stops deciding): Correction 1/L8/L15 — recorded as deviation D-013;
  analyzer only re-decides on VAD-onset config. ✓

### NATIVE (T1.1/T1.2) — F1, F2, F3 all BLOCKER — CLOSED
- **F1** (G1(b) reads a log line never written): correction 2 + §8 V6-V7 — G1(b) redefined as
  a client-observable barge-in proposition; server-notice un-observability carried to R-N6. ✓
- **F2** (wake-word probe never terminates): §5 step 10 probe uses `--max-time 3` + echo, yields
  `WAKE_PROBE=<code>`; both W1/W2 Swift paths written. ✓
- **F3** (per-`connect()` peer rebuild undefined): §5 step 5/7 — explicit per-session lifetime;
  `testReconnectAfterDisconnectBuildsNewPeerConnection` added. ✓

### SKILL (T6a) — F1, F2 BLOCKER (+F3) — CLOSED
- **F1** (description displaces `technical-plan-document` + self-edit vocab): §3 S1 rewritten
  473→391 chars. **RE-MEASURED with the repo's real scorer** (`jarvis/agent_skills.py`
  discover/`_overlap_score`): fires on its own 2 positives (0.375/3, 0.714/5); scores
  **0.000** on both `mcp-server-authoring` negatives, 0.167/1 and 0.000/0 on the two
  `technical-plan-document` negatives (both below bounds), and **0.000 on "improve Mortimer
  itself".** Every T1 number reproduces; it displaces nothing. ✓
- **F2** (step 9 digit-for-digit against an impossible transcript): step 9 moved before
  enablement; compares only `score=`/`shared_tokens=`. ✓
- **F3** (step-1 expected block stale after allow-list move): replaced by "apply row W0-SKILL". ✓

### T1.3 (APP) / T1.4 (WEB) — newly written, no prior review
Checked against the cross-plan resolution obligations (F12, K8). See §3 below. Both sound.

**No blocker found still open.**

---

## 2. Cross-plan seams (re-verified after the edits)

**(a) Migration numbers — CLEAN.** REMOTE owns `0016_client_tokens` (§0 constraint 7, A3);
MAIL moved to `0017_brief` / `MIGRATION_0017` (M16, §0.11). Both anchor the insertion by
"append after the last tuple in `MIGRATIONS`" (locate the newest tuple by text — today
`("0015_memory_reviews", MIGRATION_0015)`), never by a line number. Both carry the reciprocal
`grep`-cross-guard ("if 0016 collision / if 0016_client_tokens absent → stop and report").
No collision. ✓

**(b) K4 OUTBOUND set — CLEAN.** SEC §7.4:
`OUTBOUND = {"mcp-web","mcp-git","mcp-apps","mcp-repo","mcp-selfedit","mcp-screen","mcp-calendar"}`
— includes `mcp-screen` + `mcp-calendar`, and `test_the_sets_have_not_been_quietly_emptied`
pins that exact set. MAIL's `secretary` = `[mcp-mail, mcp-calendar, mcp-reminders]` — `mcp-screen`
dropped (C6 header, M9). The two agree. ✓

**(c) Allow-list — PARTIAL (one gap, on SEC).**
- Referencing half is clean: SKILL cites "row W0-SKILL", REMOTE "row W1" (A14), LOCAL "the LOCAL
  row" (W2) of `docs/plans/ALLOWLIST_SEQUENCE.md` and none edits `config/self_edit_allowlist.json`. ✓
- **GAP:** SEC does **not** actually author `ALLOWLIST_SEQUENCE.md`. It is absent from SEC's
  Create manifest (8 files), and no §5 step assembles it. SEC inlines only row W0's three deny
  entries (D-H9, §8 V7); the reconciled JSON and the other three ordered rows (W0-SKILL, W1, W2)
  live only in their respective plans, never consolidated into the single-source file that all
  four cite. When Sonnet implements SEC and reaches "apply row W0 of ALLOWLIST_SEQUENCE.md," the
  file will not exist. Content is fully recoverable (CROSS_PLAN_RESOLUTION.md §A holds the JSON +
  4-row table; each plan holds its own row), but SEC must be told to create the file. **MAJOR,
  fix on SEC before handoff.**

**(d) Keychain convention — CLEAN.** REMOTE (§3 A15, §5 Step 10) and NATIVE (§3 N12,
`KeychainStore.swift`) both use service `"com.mortimer.jarviskit"`, account
`"<scheme>://<host>:<port>"` derived from the bot URL, `kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly`.
Identical item; REMOTE's `ShellAuth` and NATIVE's `KeychainStore` read/write the same entry.
NATIVE adds a token-mint step before §8 V5 (else V5 correctly fails "Token required"). ✓

---

## 3. The two new plans reference reality — CLEAN

**App-target name.** T1.4 (WEB) gates on `test -d macos/MortimerHost` (§0 precondition 2) and
names it the app rebuilt by T6/W4. T1.3 (APP) takes the `MortimerHost` G1(b) harness from NATIVE
core and "turns `MortimerHost` into the real three-window app" (§1.3, §3 P1). Both use
`macos/MortimerHost`. No mismatch. ✓

**K8 AdminAPI extension is declared additive.** T1.3 §0.1 limits writes to `macos/JarvisKit/**`
(response structs + *additive* `AdminAPI` methods) and `macos/MortimerHost/**`. §1.3/P2/§(Edit tab)
state the write routes (git prepare/commit/push; selfedit validate/submit/revert) are "**not**
among CORE's seventeen read routes, so this plan **adds** methods to `AdminAPI` (additive to K8,
declared in the header)." CORE's read routes are consumed, not changed — not a silent contract
change. ✓

---

## 4. Roadmap edits (SEC owns all of them) — 4 present, 1 missing

SEC's "Roadmap edits" section carries RE-1…RE-4:
- **§8 queue = all TEN plans, marked written/unwritten (incl. T1.3 #3, T1.4 #4)** — RE-1. ✓
- **§5 W4 KeychainStore/T4b-key clause (F13) + Xcode-rebuilds-`macos/MortimerHost` clause (F16)** —
  RE-2 (both clauses present with `SecAccessControl` user-presence wording). ✓
- **§2.3 T3.6 local-vision item + "Local vision" leaves Out-of-scope** — RE-3. ✓
- (bonus) §1 table rows corrected (RE-4). ✓

**MISSING:** the **REMOTE §2.2 pointer**. REMOTE (§4 manifest note + §6) explicitly does NOT edit
the roadmap and states "the SEC roadmap edit folds in a one-line pointer beside §2.2 to this plan's
R-A1…R-A4 corrections." No RE-block adds that pointer. **MAJOR, fix on SEC before handoff.**

---

## 5. Residual honesty — consolidated

Everything a plan now labels an accepted residual, a Larry decision, or "verifiable only on
Larry's hardware." (Actionable items rolled into the Larry-must-decide list below.)

Accepted residuals / hardware-only verification, by plan:
- **SEC R-H5** — suppression stops *storage*, not *transmission*; Deepgram/ElevenLabs/LLM vendors
  still receive a financial turn. Why the financial tier is sequenced after local models. (§2.7, V4)
- **SEC snapshot gate** — a self-edit that widens any `requires_env` or `mcp_servers.yaml` `env:`
  map turns CI red until Larry hand-edits the denied `test_requires_env_snapshot.py` in the same
  commit. Intended review gate (D-H9, R-H9 superseded).
- **SEC V4** — Deepgram Flux digit-numeralisation is not guaranteed; V4 step 0 marks absence
  "inconclusive," not "failed."
- **MAIL RM-1a / §0.10** — text-laundering: the secretary's summary of untrusted email returns to
  the Supervisor (`delegate.py:461`), which holds outbound tools + durable memory (`memory.py:782`).
  Not closed by the per-agent tool list; full closure deferred to T3.6 local-vision + a separate
  Supervisor-return-isolation fix.
- **MAIL RM-11a** — `secretary` retains `mcp-reminders` incl. `get_due_reminders` (a destructive
  read); resolution §B did not mandate a server split.
- **LOCAL R-L2** — the mini's vault master key is a `0600` plaintext file, not Keychain-protected;
  a file read = a key read. Unavoidable for headless boot (LaunchDaemon). Stated "toward exposed"
  without softening; blast radius bounded (T4b key is not in this vault).
- **LOCAL L15 / R6** — the Whisper barge-in trade (see Larry list).
- **LOCAL G3(e)** — strict-mode residual printed, not blocked.
- **SKILL R3** — `skills/**` being writable lets a self-edit weaken an already-enabled skill and
  the degraded text is LIVE at the next delegation, *before* validation/PR/merge; safety-heading
  pins fire after the brief live window; non-pinned body prose is not pinned.
- **NATIVE R-N6** — the server-side interruption notice text is not observable without a backend
  change (C1); G1(b) uses a client-observable proxy.
- **REMOTE** — no TLS inside the Tailscale tunnel; media may take a LAN path (DTLS-SRTP keys still
  travel the authenticated signalling channel). Accepted (§2.2/§10).

Hardware-only (must be run on Larry's Mac/mini; both branches written where a probe decides):
- NATIVE: Swift-SDK probe (Branch A/B), wake-word probe (W1/W2), live G1(b) barge-in, visual-ceiling
  spike (two displays, busy desktop).
- LOCAL: routing eval ≥90% on the mini's Supervisor model, RAM/`STT_GB` sizing, TTS A/B, launchd
  headless-boot G3(d).
- REMOTE: service-token mint (Step 0) + the self-401 window, Tailscale bind.
- MAIL / WEB: routing eval on Larry's hardware.

---

## GO / NO-GO for handoff to Sonnet

| Plan | Verdict | Notes |
|---|---|---|
| SEC (T4a) | **CONDITIONAL GO** | Code re-measured, 0 FP/0 FN; all 6 blockers closed. **Two must-fix shared-artifact obligations before handoff:** (A) author `docs/plans/ALLOWLIST_SEQUENCE.md` with the reconciled JSON + all four ordered rows (W0, W0-SKILL, W1, W2) + verify commands; (B) add the roadmap §2.2 pointer to REMOTE's R-A1…R-A4. Both are SEC's assigned work; sibling plans depend on them. |
| REMOTE (T2) | **GO** | F1–F3 closed in-section; migration/OUTBOUND/Keychain seams clean. Depends on SEC obligation (A) for its §8 V8 step and (B) for its roadmap pointer. |
| MAIL (T5) | **GO** | Sanitiser + grounding re-measured and pass. One cosmetic test-expectation nit (`"HQ."` vs `"HQ"`), non-blocking. |
| LOCAL (T3) | **GO** | F1–F3 closed; L15 + R-L2 are surfaced Larry decisions, not silent regressions. |
| NATIVE core (T1.1/1.2) | **GO** | F1–F3 closed; probe-decided branches both written; Keychain convention matches REMOTE. |
| SKILL (T6a) | **GO** | Description re-measured with the real scorer; displaces nothing. Depends on SEC obligation (A) for its step-1 row W0-SKILL. |
| APP (T1.3) | **GO** | Uses `macos/MortimerHost`; K8 extension declared additive; write-set fenced to `macos/**`. |
| WEB (T1.4) | **GO** | App-target name agrees with T1.3; retirement gated on G1(e); stays out of the allow-list file. |

Net: **7 GO, 1 CONDITIONAL GO (SEC).** The two SEC conditions are documentation/shared-artifact
completeness, not code — but three sibling plans (SKILL/REMOTE/LOCAL) cannot execute their
allow-list Larry-step until obligation (A) is met, and REMOTE's roadmap correction is lost until
(B) is met. Fix both in SEC, then SEC is GO.

---

## Larry must decide (consolidated)

1. **Whisper barge-in trade (LOCAL L15 / roadmap R6).** Default config keeps smart-turn (VAD-onset)
   and is safe; the Whisper-barge-in config is a measured opt-in. Accept the default — or rule that
   R6 ("no local STT without turn-detection parity") forbids shipping Whisper at all until barge-in
   parity exists (that would be a roadmap decision, recorded in LOCAL §8 A/B).
2. **Mini vault key at rest (LOCAL R-L2).** The master key becomes a `0600` plaintext file (not
   Keychain-ACL'd) because the box must boot headless via LaunchDaemon. Accept "a file read = a key
   read," bounded by the T4b tier key living on the client, not in this vault.
3. **Mail text-laundering residual (MAIL RM-1a).** Even with `mcp-screen` dropped and the fence in
   place, the secretary's prose returns to the Supervisor (outbound tools + durable memory). Accept
   this residual until T3.6 (local vision) + the separate Supervisor-return-isolation fix land.
4. **Reminders destructive-read (MAIL RM-11a).** `secretary` keeps `mcp-reminders` incl.
   `get_due_reminders`. Accept, or order a reminders read/write server split (resolution §B did not
   mandate one).
5. **Storage ≠ transmission (SEC R-H5).** A fully-suppressed financial turn is still heard by
   Deepgram/ElevenLabs/the LLM vendor. Acknowledge that T4a's claim is "Mortimer does not keep it,"
   not "nobody heard it" — which is why the financial tier (T4b) waits for local models (T3/G3).
6. **Enabled-skill self-amend window (SKILL R3).** A self-edit can weaken an already-enabled skill
   and the degraded text is live at the next delegation before the PR. Accept that the real gate is
   the human merge + `git checkout`, with safety-heading pins as a loud-but-after-the-fact backstop.
7. **Env-scoping rollback leaks the service token (REMOTE / SEC §9, CP-F6).** After REMOTE lands,
   `JARVIS_ENV_SCOPING_ENABLED=false` hands `JARVIS_SERVICE_TOKEN` to all twelve MCP children.
   Operational rule: revoke the token (or also set `JARVIS_AUTH_ENABLED=false`) before using that
   rollback, re-mint after. Documented — confirm the runbook step.
8. **No TLS inside the tunnel (REMOTE §2.2).** Media may take a LAN path; DTLS-SRTP keys still
   travel the authenticated tunnel. Accept.

(Items 1–2, 3–4, 5, 6 are accepted-residual acknowledgements; 7–8 are operational acceptances.)
