# Jarvis service inventory — one line per long-lived process.
# NOTE (2026-09-02): nothing executes this file anymore. scripts/mortimer.sh
# is the canonical launcher (hand-launches each process below, with log
# rotation and a real stop-then-start restart); scripts/start_jarvis.sh,
# which used to run this via overmind/hivemind, was removed. Kept here as
# a reference inventory -- keep it in sync with mortimer.sh by hand.
# TODO: replace run_vault.sh with the real vault start command (grep -rn "8484" to find it).
vault: ./scripts/run_kb.sh
bot: ./scripts/wait_for.sh 127.0.0.1 8484 30 vault && ./scripts/run_bot.sh
# api: ./scripts/wait_for.sh 127.0.0.1 8484 30 vault && ./scripts/run_api.sh
# Phase 2 (MORTIMER_OPTIMIZATION_PLAN.md, "Extraction Gate"): per-exchange
# memory extraction worker. No wait_for -- only needs the sqlite db and
# the LLM API, not vault.
memory_extractor: ./scripts/run_memory_extractor.sh
costs: ./scripts/run_costs.sh
