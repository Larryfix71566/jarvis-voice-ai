---
date: 2026-11-26
system: claude
rows: [WS-40]
prs: []
---

# 2026-11-26: WS-40 spoken password guard, off by default (Claude)

- **System:** Claude (Claude Code cloud session, Opus 5.5 planning; implementation by a Sonnet 5.5 helper, reviewed by Opus 5.5).
- **Why:** Larry, 2026-11-24: "the only text that should be banned from outside the machine would include account or password info." PR 422 keeps typed passwords and key literals on the Mac; a password said in a sentence ("my password is hunter2") still went to the Claude subscription and the conversations table. Design: `spoken-password-guard-2026-11-25.md` (project files), option A.
- **Change:** `jarvis/sensitive.py` finds a spoken credential value after a cue (password, passcode, passphrase, PIN, door/security/access codes, and "the code is 4729") and returns spans only. `subscription_llm._withhold_account_details` replaces just the value with `[secret kept on this Mac]`, so the rest of the request still reaches the model. The user turn is armed with kind `credential`, so it is not persisted and sub-agents and external tools stop for that turn, through the PR 422 gates unchanged. A cue with no value ("my password is…"), or Mortimer asking "what's the PIN?", lets the next short user turn's bare value be redacted, for one turn. Typed turns get the same rules.
- **Flag:** `JARVIS_SPOKEN_CREDENTIAL_GUARD_ENABLED`, off by default; with it off nothing changes. `JARVIS_SENSITIVE_GUARD_ENABLED=false` still turns every sensitive detector off.
- **Larry's open decisions (design §7), not decided here:** (1) Deepgram still hears the audio; no STT code touched. (2) A redacted turn is not written to the transcript, as PR 422 does today; persisting the redacted text instead would be a code change. (3) `JARVIS_SPOKEN_CREDENTIAL_WORD_VALUES`, default on (the design's recommendation): "the wifi password is bluefish" counts. (4) `JARVIS_SPOKEN_CREDENTIAL_BARE_CODE`, default on (the option A rule): "the code is 4729" counts.
- **Not tested here:** live speech. How Deepgram Flux writes spoken digits and spelled letters is unmeasured; the rules accept digits, digit words and single letters.
- **Next actor:** Larry: merge; to try it, set `JARVIS_SPOKEN_CREDENTIAL_GUARD_ENABLED=1` and redeploy, then answer decisions 1 to 4.
