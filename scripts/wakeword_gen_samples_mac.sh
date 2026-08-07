#!/bin/bash
# Generate local wake-word training samples with macOS built-in tools only.
# Positives: "Mortimer" spoken by every installed English voice at varied rates.
# Negatives: similar-sounding words + unrelated phrases (hard negatives).
#
# Output: data/wakeword/positive/*.wav and data/wakeword/negative/*.wav
#         (16 kHz mono PCM WAV, exactly what jarvis/wakeword/train.py expects)
#
# Usage:  ./scripts/wakeword_gen_samples_mac.sh [positive_repeats] [negative_repeats]
#         defaults: 6 repeats each (≈ voices × phrases × repeats clips)
set -euo pipefail
cd "$(dirname "$0")/.."

POS_REPEATS="${1:-6}"
NEG_REPEATS="${2:-6}"
OUT="data/wakeword"
mkdir -p "$OUT/positive" "$OUT/negative"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# All installed English voices (name is field 1 of `say -v '?'`).
mapfile -t VOICES < <(say -v '?' | awk '$2 ~ /^en_/ {print $1}')
if [ ${#VOICES[@]} -eq 0 ]; then
  echo "no English voices found — install some in System Settings > Accessibility > Spoken Content" >&2
  exit 1
fi
echo "using ${#VOICES[@]} English voices"

POS_PHRASES=("Mortimer" "Mortimer." "hey Mortimer" "Hey Mortimer" "Mortimer, are you there")
NEG_PHRASES=(
  "mortar" "mortician" "mortgage" "martyr" "mister" "motor" "marmot" "morpheme"
  "Mortimer's" "more timid" "more timber" "or timer"
  "what time is it" "set a reminder for tomorrow" "tell me a joke"
  "search the web for news" "what's the weather today" "hello there"
  "play some music" "how are you doing" "cancel that" "never mind"
)
RATES=(150 175 200 225 250)

speak_set() {
  local dir="$1" tag="$2" repeats="$3"; shift 3
  local phrases=("$@")
  local n=0
  for ((r=0; r<repeats; r++)); do
    for voice in "${VOICES[@]}"; do
      for phrase in "${phrases[@]}"; do
        local rate=${RATES[$RANDOM % ${#RATES[@]}]}
        local aiff="$TMP/clip.aiff"
        say -v "$voice" -r "$rate" -o "$aiff" "$phrase" 2>/dev/null || continue
        afconvert -f WAVE -d LEI16@16000 "$aiff" "$dir/${tag}_${voice// /_}_${r}_$((n++)).wav"
      done
    done
  done
  echo "$n"
}

echo "generating positive clips ..."
NPOS=$(speak_set "$OUT/positive" pos "$POS_REPEATS" "${POS_PHRASES[@]}")
echo "generating negative clips ..."
NNEG=$(speak_set "$OUT/negative" neg "$NEG_REPEATS" "${NEG_PHRASES[@]}")

echo "done: $NPOS positive, $NNEG negative WAVs under $OUT/"
echo "next: python -m jarvis.wakeword.train --data-dir $OUT"
