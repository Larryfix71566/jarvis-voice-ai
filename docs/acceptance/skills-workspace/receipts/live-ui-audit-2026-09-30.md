# WS-03 live Skills UI audit — 2026-09-30

This is partial target-Mac evidence, not acceptance of an SW-A–SW-L gate.
Observer: Codex, using the running native MortimerHost app and read-only
service checks at 20:33–20:38 EDT. Production checkout and app bundle both
reported revision `39fc6f9f08cbed2b4a460c05e8bf336d95f9d381`; the admin
health endpoint returned 200 and the bot root returned its expected 307.
No provider evaluation, creator draft, registry change, or activation occurred.

## Observed

- The production app connected to the running stack. Skills opened within the
  Command Console, with six installed packages: five enabled and Skill Creator
  disabled. Each enabled card showed `Unknown` readiness and explained that
  digest-pinned loading is off; the disabled creator showed `Blocked`.
- Selecting Git history and status review opened Overview. Its Process tab
  showed three reviewed steps. Selecting the first step exposed inputs, output,
  tool, approval and success criteria; Next selected the second step.
- Activity said `No skill trace recorded` rather than inferring completion from
  the intended process. No recorded live run was exercised.
- In the disconnected app, searching for `git` narrowed the library to the
  single matching Git skill. A keyboard-only attempt did not open its card,
  but the host's Full Keyboard Access setting was not checked; this does not
  establish either a keyboard pass or a product defect.
- Versions displayed a generic connection failure. A direct read of the same
  local endpoint returned HTTP 503 with `Skills requests require bearer
  authentication`. The server intentionally requires an authenticated caller
  before returning owner-scoped candidate history. The admin log also showed
  recurring 503 responses from `/api/skills/runtime-inventory` while remote
  bearer auth is dormant. These responses do not establish a network outage.
- The voice session later disconnected after roughly 339 seconds while the bot
  service remained running. The cause was not established; this observation is
  not counted as a Skills navigation regression or as continuity acceptance.

## Bounded follow-up on this branch

`SkillsWorkspaceView` now gives a specific, truthful explanation for that exact
503 response. It does not change authentication, return candidate history to an
unauthenticated caller, enable digest-pinned loading, or activate the creator.
The focused `SkillsWorkspaceRenderingTests` suite passed 20/20 on this branch.
The changed UI has not been deployed or visually retested in production.

## Still unverified

SW-A and SW-D through SW-L remain open. This audit did not exercise a real
skill run, live spoken navigation, VoiceOver, keyboard-only or large-text
operation, a physical second-display move, a Tart creator lifecycle, provider
evaluation, paired voice latency, memory soak, or activation/rollback. The
accepted SW-B/SW-C receipts are prior candidate-bound evidence and must be
reconciled against the frozen release before final SW-L acceptance.
The release-evidence verifier correctly rejected the current WS-03 branch's
2026-09-28 receipts as stale (candidate HEAD, branch, tree and bundle differ).
The installed Tart/Softnet doctor reports `ready_to_boot: true` and the cached
Xcode image exists, but no guest was launched in this audit.
