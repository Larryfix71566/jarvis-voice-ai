# Jarvis service inventory — one line per long-lived process.
# NOTE (2026-09-02): nothing executes this file anymore. scripts/mortimer.sh
# is the canonical launcher (hand-launches each process below, with log
# rotation and a real stop-then-start restart); scripts/start_jarvis.sh,
# which used to run this via overmind/hivemind, was removed. Kept here as
# a reference inventory -- keep it in sync with mortimer.sh by hand.
# vault: = the KNOWLEDGE-BASE service (~/mortimer-vault, :8484), not jarvis/vault.py (the secrets vault). Names collide; see CLAUDE.md 'Two vaults'.
vault: ./scripts/run_kb.sh
bot: ./scripts/wait_for.sh 127.0.0.1 8484 30 vault && ./scripts/run_bot.sh
# api: ./scripts/wait_for.sh 127.0.0.1 8484 30 vault && ./scripts/run_api.sh
# Phase 2 (MORTIMER_OPTIMIZATION_PLAN.md, "Extraction Gate"): per-exchange
# memory extraction worker. No wait_for -- only needs the sqlite db and
# the LLM API, not vault.
memory_extractor: ./scripts/run_memory_extractor.sh
costs: ./scripts/run_costs.sh
# web: (frozen 2026-09-04 -- run_web.sh by hand only; MortimerHost is the daily driver, see CLAUDE.md and web/README.md)
