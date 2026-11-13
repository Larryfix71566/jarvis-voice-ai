---
date: 2026-11-13
system: kimi
rows: [WS-36]
prs: [364]
---

# WS-36 C2: approved AppTheme palette tokens

Draft PR #364 into `next`, based on `b17842c2b772e195dcb4ac4f1555f6494e738fa5`. Source head before this status entry: `2dffde50b3fe5dc06c0f60573f23c92942807947`. Independent reviewer: Codex.

## Implemented

- Added `AppTheme.listening` `#6673FF`, `user` `#2DD4BF`, `mortimer` `#E07020`, `ok` `#A6FFC1`, `approval` `#FFD84A`, and `error` `#FF598B`.
- `user` and `mortimer` reference `AudioPresentationTuning.userColor` and `assistantColor`; the existing `userRGB` and `assistantRGB` definitions remain the single source.
- Preserved `amber` `#FFB454`, `green` `#3DDC97`, `red` `#FF5F56`, and `attn = amber`.
- Corrected the stale Mortimer comment from `#FFB454` to `#E07020`.
- Added focused tests for exact values, unchanged legacy colors, shared speaker colors, and contrast on glass and opaque accessibility fallbacks.

No C5/C7a call-site migration, contract, roadmap, closure-plan, checklist, deployment, service, provider, live-call, credential, or acceptance change. No interface-capability fact in Mortimer's long-term memory conflicts with these additive visual tokens; no memory database was accessed or changed.

## Verification

Independent WCAG sRGB calculations checked all six tokens on five surfaces: glass over the app background, regular glass tint, heavy glass tint, glass-off fallback, and the opaque Reduce Transparency / Increase Contrast fallback. All 30 combinations pass the 3:1 non-text minimum.

| Token | Minimum ratio across checked surfaces |
|---|---:|
| listening | 4.068:1 |
| user | 8.404:1 |
| mortimer | 4.848:1 |
| ok | 13.182:1 |
| approval | 11.303:1 |
| error | 5.254:1 |

`listening` remains restricted to the orb and icons; no small-text call site is introduced. `python3 scripts/check_roadmap.py` passed with 0 errors and 0 warnings. `git diff --check` passed.

The local environment has no Swift toolchain, so `swift test --package-path macos/MortimerHost` was not run locally. Hosted macOS execution and Codex's independent review remain required before merge. No merge or live acceptance is claimed.
