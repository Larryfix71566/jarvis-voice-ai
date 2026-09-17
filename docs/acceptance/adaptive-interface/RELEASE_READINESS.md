# Adaptive interface release readiness

Updated 2026-09-17. Source reviewed: `5faa2e639918075413c8962eafbbc466770f8111`.
This checklist distinguishes implementation, merge, verification, deployment
and user acceptance. A pass in one category never implies the others.

## Source and merge

- [x] Main identified as `25ab904d0371a752295e7f9cd3fea39eaf334b0c`.
- [x] PRs #65–75 merged; native audio and adaptive foundation are present.
- [x] PR #76 head identified as `5faa2e6`; allowlist, knowledge-base,
  controller-tests, policy-tests and validate all report success.
- [ ] Review and merge PR #76's code scope: waveform tuning/default change,
  delegation teardown, interruption deduplication and extraction fixes.
- [ ] Publish and merge the status reconciliation after independent checks.

## Independent verification

- [x] Existing receipt `a56c192c20704ab5a7d59366a9e52d43` passes all 12 checks
  and desktop probe at `8c1fb5a`, with unchanged source. This is historical.
- [x] Prepared image dependencies match `5faa2e6`; controller doctor passes;
  no other VM was running before this release task started.
- [ ] Obtain a fresh full-profile receipt for the frozen release candidate.
- [ ] Resolve or characterize reported graphical timing/focus variability
  without disabling checks or relaxing the 33 ms frame-time gate.

## Implementation and hardware

- [x] Adaptive workspace, sidecar header, graph and placement code exists.
- [x] Native capture/playout observation drives distinct user/AI feedback.
- [x] Native audio live conversation, output switching, muted wake word and
  WebRTC rollback have recorded evidence (C6/C7).
- [ ] Earbud-removal rebuild-churn investigation.
- [ ] Echo benches: AirPods both ways; AirPods output + built-in input.
- [ ] Audio-report minimum sample floor and explicit coverage field.
- [ ] Complete C8's five requirements and all P0 preservation rows. Existing
  known-limitations acceptance enabled the default flip; it did not run C8.
- [ ] Complete T1.3 V3–V8: tabs/workflows, output/log, display/multi-display
  and visual/accessibility acceptance. Record test case and evidence.
- [ ] Complete T1.3 V9's five-day daily-driver period begun September 15.

C8 needs legacy/adaptive preservation, five viewport sizes, compact notices,
workspace pins/comparison/reading state, graph interactions, keyboard and
accessibility behavior, physical audio/device scenarios, monitor recovery,
synthetic-state rollback and an exact-candidate independent receipt. Unit
fixtures do not by themselves establish physical-device behavior.

## Deployment

- [x] Current topology inspected: candidate app and bot on 7870 coexist
  with launchd bot/admin on 7860/7861 from `~/jarvis-voice-ai-clean`.
- [ ] Reconcile five production patches using the inventory in
  `production-local-patches/README.md`; preserve them until the release
  contains the chosen behavior. Do not reset or discard user changes.
- [ ] Build a version-identifiable bundle from the verified source.
- [ ] Deploy coordinated bot/admin/app versions, verify intended DB path,
  retain rollback, and record health plus a successful live journey.
- [ ] Record the actual loaded versions after restart; a source checkout
  alone is not proof of the running process's version.

## Decisions and follow-on work

- [ ] Decide whether to replay 28 missed extraction exchanges (C6 item 12b,
  estimated ~149 LLM calls). Do not rewind the live cursor implicitly.
- [ ] Settle model-registry split decisions before implementation (#71 is
  a merged plan, not delivered code).
- [ ] Speaker-gate labeled effectiveness protocol; keep gate off until met.
- [ ] Security V2–V6 acceptance; V7 deny entries are already on main.
- [ ] Routing/evaluation floors and current denominator reconciliation.

Remote access, local models/Mac mini, financial-data handling, mail/calendar
and advanced skill authoring retain their own roadmap gates. Web retirement
waits for native acceptance and daily-driver completion. Native WebRTC is
still needed for remote/rollback operation after web-console retirement.

## Evidence rules

For each newly checked item record date, source commit or candidate digest,
scenario, result, and evidence path. Keep historical failures. A source fix
is not a test result; accepted risk is not a pass; a listener is not a live
conversation; an old receipt is not current-head verification.
