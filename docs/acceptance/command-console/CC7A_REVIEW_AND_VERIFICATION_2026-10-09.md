# WS-17 exact-source cross-review and offline comparison

Recorded by Codex, 2026-10-09, under the existing
[Command Console plan §7.2](../../plans/MORTIMER_COMMAND_CONSOLE_ATLAS_PLAN.md).
This evidence closes only the explicitly evidenced review/verification subgates.
It is not deployment or Larry’s UI2-22…25 acceptance.

## Authorized, separate Claude static reviews

Larry approved baseline `a5b6f884c317c74a1d2b4c2a1d7e334920a55d51` for
the offline comparison, and read-only Claude subscription reviews of exactly the following source diffs,
excluding secrets, runtime logs and later source. Release remains separate;
WS-13 revision 4 must land before #198 merges.

- **#197:** `bd1803348fc0029b1dfe00832066b2f5713b170c` →
  `065d50058534d6e16e0c59cae0100d0b9bbb5406`, six source/test files.
  Verdict: **“No high-confidence blocking defects.”** This is a post-merge
  review: #197 had already merged as `51dcdee89a9dc5235c77e72e18c9150f31d52e8f`.
- **#198:** `352ec6904c7e0ae1067980d5d851de0d18b02085` →
  `748b1e5ab7a00cf208b775816355fe339abbe879`, 25 source/test files.
  Verdict: **“no blocking defects found.”** Those files match the frozen
  comparison candidate `ce6cde86c56e4793f133f8b7d80ea55ea1754198`.

Both requests completed successfully on the Mac through Claude Code **2.1.290**,
model **claude-sonnet-5**, authenticated by `claude.ai` / Max. They used fresh
private temporary working directories, empty tools and MCP, no session
persistence, empty setting sources and stripped API/vault/service environment.
This is a restricted CLI review, not filesystem isolation inside Tart. Actual
account quota, paid-overage settings and billing were not verified; reported
list costs are not billing proof. The earlier joint 300-second timeout returned
no verdict; the successful separate requests supplied the same approved patches.

The reviewer saw only its supplied diff, could not inspect unchanged surrounding
code or execute tests, and gives **no joint integration verdict**. These are
attributed model-review records, not formal GitHub APPROVED reviews. An
independent Codex audit reconstructed both exact patch hashes and byte counts
from owned Git objects. Full reports, execution identity, limitations and local
dispositions are in [the cross-review receipt](CC7A_CROSS_REVIEW_2026-10-09.json).

## Observation dispositions

Codex separately checked the reported observations in surrounding source at
`ce6cde8`; no source repair was warranted by those checks.

- **#197 F1:** No reachable current inventory encoding failure was found:
  numeric values are integer counts/indexes or finite-validated freshness,
  and production publication uses the typed getter.
- **#197 F2:** The capacity test’s dependent ordering oracle is a valid local
  limitation; existing independent Recents tests explicitly pin pinned/newest
  and Older order.
- **#197 F3:** Every current production waiter producer uses the shared sender,
  which binds action/scope before its first transport await. Untagged future
  producers remain a hardening observation without a present trigger.
- **#197 F4:** The separate `repr` ceiling is an existing validator contract.
  Conservative projection preserves numbered rows or refuses, labels omitted
  data, and does not replace the model-observed list with passive updates.
- **#198 observation 1:** Local weather adds bounded source metadata even
  with the console bridge off. This compatibility difference is documented in
  the existing plan. Protected-turn guards and explicit public-policy cache
  checks remain; no additional fetch or feature activation is implied.
- **#198 observation 2:** Foundation’s default JSONEncoder rejects nested
  nonfinite numbers through recursive JSONValue encoding. This disposition
  uses static semantics; no dedicated nested-nonfinite execution proof was added.
- **#198 observation 3:** Four-decimal local identity matches actual
  Weather.gov points/alerts URL precision and the approved contract.
- **#198 observation 4:** One reference per originating run, including two
  different subjects, is an explicit tested UX tradeoff. The second cache
  reply still completes.

## Offline comparison

**Passed:** all twelve exact ordered Mortimer-profile checks, with their
original argv and budgets, in the independently allocated offline VM.
Approved Git baseline is `a5b6f884c317c74a1d2b4c2a1d7e334920a55d51`;
frozen Git candidate is `ce6cde86c56e4793f133f8b7d80ea55ea1754198`.
The receipt’s baseline/candidate values are canonical source-content
fingerprints, not Git SHAs. The 28 runtime/test deltas match the approved
065d500/748b1e5 sources; the two #200 fixture files and modes are identical
on baseline and candidate. No installed runner/profile/configuration change
or test waiver was used.

- Baseline Python: **6,257 passed / 11 skips / two subtests / zero failures**.
- Candidate Python: **6,366 passed / 11 skips / two subtests / zero failures**.
- Candidate JarvisKit: **232 executed / zero skips or failures**.
- Candidate MortimerHost: **551 executed / eight skips / zero failures**.
- Baseline native: **JarvisKit 226; MortimerHost 512 / seven skips;
  zero failures**.
- Import smoke, scripted evaluations, latency, both knowledge-base suites and
  web build all passed. These unit-profile counts have a different scope from
  the earlier local unit-plus-integration Python count.

All twelve log hashes match the receipt. The worker identity was actually
measured as UID 502; the desktop probe found that worker’s Aqua session and
unlocked disposable keychain. Candidate source remained unchanged. The pinned
image, profile and runner identities match; sandbox settings and the image
record remained byte-identical. Both owned tasks (`6cc1cb6a9ff3`, independent
child `268e47f8d847`) stopped, zero VMs remain running, and the final caller’s
clean-success boundary is true.

The VM’s eight app skips are two Screen Recording captures, three physical
multi-display tests and three window-activation tests. They are **skips**, not
privacy/display acceptance. The two actual window captures passed earlier on
the frozen `748b1e5` local Mac source, as separately recorded in
[local evidence](CC7A4_REUSE_2026-10-07.md); live gates remain open.

The original fee4ac0 comparison’s 7 baseline failures and 84 setup errors remain
historical failures. This authorized a5b6f88 comparison supersedes that release
block with positive evidence; it does not rewrite the failed receipt.
See [machine-readable offline verification](CC7A_OFFLINE_VERIFICATION_2026-10-09.json)
for fixed pins, exact checks, fingerprints, source bindings, skip names and
cleanup. No production deployment or live outcome is inferred.

## Remaining release and acceptance

- Land WS-13 revision 4 first; it was still open as PR #196 head `4994861`
  in the 2026-10-09 GitHub status read after the reviews, independently of their
reports. This receipt does not approve its plan or run
  Claude’s landing scripts.
- Larry separately approves #198 merge/release and deployment of the reviewed
  build, with its rollback identity. Production remains the authoritative
  roadmap receipt; no production file, provider route or account setting changed.
- On that identified deployed build, record UI2-22’s protected/focus/scroll/size
  tail, UI2-23’s arrival/New/background/card and physical supporting-display
  cases, UI2-24’s voice/pointer Recents and ambiguity/stale targeting, and
  UI2-25’s fresh no-fetch / stale same-ID weather reuse.
- Reuse unaffected #191 evidence. Remove the temporary conversation-thread
  switch only after all four live gates pass; then finish dependent WS-09/11
  UI2-04/09/13. WS-21 retains its separate physical-transfer acceptance.

No live acceptance checkbox is closed by this receipt.
