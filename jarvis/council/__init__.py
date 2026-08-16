"""LLM Council: peer-reviewed multi-model proposals for the self-edit loop.

MORTIMER_LLM_COUNCIL_PLAN.md. A council may rank, review, and advise; it may
NEVER author a merged artifact (§0.1.1) — every diff that reaches
session_validate is written whole by exactly one model. This package only
ever produces a prose brief (the winning proposal's content), never a diff.

Transport-free (D1): scoring.py and agreement.py import nothing from
openai/jarvis.selfedit/jarvis.agents, so the selection and metrics logic is
unit-testable without network.
"""
