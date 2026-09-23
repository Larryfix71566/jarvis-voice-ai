# Full Python acceptance receipt — September 18, 2026

Command:

```sh
UV_CACHE_DIR=/private/tmp/jarvis-uv-cache \
  /Users/larryfix/jarvis-voice-ai-clean/.venv/bin/python -m pytest -q
```

Result: **2611 passed, 4 skipped, 11 warnings, 2 subtests passed** in
111.78 seconds in the recorded run. A fresh rerun on the same date completed
in **87.71 seconds** with the same result; no tests were deselected and no
failure was masked. The warnings are dependency deprecations and the expected
missing `TAVILY_API_KEY` degraded-mode warning; no test failed. This is a
current sandbox run from the release-review worktree, not a claim that the
Mac staged rollout or live provider journey is complete.
