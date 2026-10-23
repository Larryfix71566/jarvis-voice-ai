---
date: 2026-10-22
system: claude
rows: [WS-17]
prs: [216]
---

- 2026-10-22 (Claude cross-review of #216: request changes; both findings still on main): Claude (Cowork) reviewed #216 at 61f701d on 10-18, after Codex's subscription review timed out; #216 had already merged as 28420af. This entry records the review without editing Codex's row (C1); the full text is REVIEW_PR216_61f701d.md in Larry's Claude outputs. The UI2-24/25 repair slices match the 10-17 diagnosis and are correct. Two findings are in the roadmap view. F1, blocking: mcp_repo's roadmap snapshot refuses above ROADMAP_LOG_MAX_FILES = 255 (and the 4 MiB and 512 KiB caps), and repo_read_file turns that refusal into a failed read of ROADMAP.md itself, while Supervisor rule 8 now routes every roadmap question to that read. docs/roadmap-log held 189 files on 10-18 and 202 on main 636880e (10-22), so 53 remain; this entry adds three more. Fix: on any projection failure return the plain read without the roadmap field, and carry the newest log records with an explicit omitted count instead of refusing. F2: the Developer's model history still receives the full result (agents/base.py, content: result), Markdown plus its JSON twin, 424 KiB per read against 164 KiB before; strip the snapshot from the history message. Rechecked on 636880e: both unchanged.
