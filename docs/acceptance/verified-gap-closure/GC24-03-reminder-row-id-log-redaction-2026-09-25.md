# GC24-03 receipt — reminder row-ID log redaction

**Date:** 2026-09-25  
**Worktree:** `codex/isolated-20260924`  
**Base snapshot:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`  
**Scope:** residual diagnostic slice F22 only.

Reminder notification post and mark-notified failures now retain their stable
event and bounded exception class without logging the reminder row ID. The
retry, notification, and database mark behavior remain unchanged. Tests inject
post and mark failures, verify canary details and the row ID stay out of logs,
and verify retry/mark state behavior.

Validation on this dirty isolated snapshot:

- `./.venv/bin/python -m pytest tests/unit/test_reminder_notifier.py -q --tb=short` — **7 passed**.
- `./.venv/bin/ruff check --select F,I jarvis/admin/reminder_notifier.py tests/unit/test_reminder_notifier.py` — passed.
- `./.venv/bin/python -m compileall -q jarvis/admin/reminder_notifier.py tests/unit/test_reminder_notifier.py` — passed.
- `git diff --check -- jarvis/admin/reminder_notifier.py tests/unit/test_reminder_notifier.py` — passed.

This closes only the reminder row-ID fields in the two failure logs. The
broader privacy source-to-sink audit remains open. The worktree contains many
concurrent dirty changes; this is not a clean-commit, live Mac, provider,
deployment, or release acceptance.
