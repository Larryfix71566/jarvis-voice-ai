# Jarvis service inventory — one line per long-lived process.
# TODO: replace run_vault.sh with the real vault start command (grep -rn "8484" to find it).
vault: ./scripts/run_kb.sh
bot: ./scripts/wait_for.sh 127.0.0.1 8484 30 vault && ./scripts/run_bot.sh
# api: ./scripts/wait_for.sh 127.0.0.1 8484 30 vault && ./scripts/run_api.sh
