#!/usr/bin/env bash

set -euo pipefail

TRACE=./traces/qwen_p7_n12_trace1.xz
declare -A BIN=(
  [lru]=./bin/hashed_perceptron-no-no-no-no-no-no-no-lru-lru-lru-lru-lru-lru-lru-lru-1core-lru
  [srrip]=./bin/hashed_perceptron-no-no-no-no-no-no-no-lru-lru-lru-lru-srrip-lru-lru-lru-1core-srrip
  [hawkeye]=./bin/hashed_perceptron-no-no-no-no-no-no-no-lru-lru-lru-lru-hawkeye-lru-lru-lru-1core-hawkeye
  [mockingjay]=./bin/hashed_perceptron-no-no-no-no-no-no-no-lru-lru-lru-lru-mockingjay-lru-lru-lru-1core-mockingjay
  [srrip_wb]=./bin/hashed_perceptron-no-no-no-no-no-no-no-lru-lru-lru-lru-srrip_wb-lru-lru-lru-1core-srrip_wb      # only needed for e5
)
W=290000000
S=1405000000
W3_LIST="290000000 290000001 291000000 295000000 300000000"
S3=560000000
OUT=results/exp


MODE=${1:-}
JOBS=${2:-4}
[ -z "$MODE" ] && { sed -n '2,16p' "$0"; exit 1; }
[ -f "$TRACE" ] || { echo "ERROR: trace not found: $TRACE"; exit 1; }
mkdir -p "$OUT"

JOBFILE=$(mktemp)

add_job() {
  local name=$1 pol=$2 w=$3 s=$4 ideal=$5 noidle=$6
  [ -x "${BIN[$pol]}" ] || { echo "ERROR: binary for '$pol' not found/executable: ${BIN[$pol]}  (edit the BIN table; see: ls bin/)"; exit 1; }
  echo "env IDEAL_DRAM_WRITES=$ideal DRAM_NO_IDLE_WRITES=$noidle ${BIN[$pol]} -warmup_instructions $w -simulation_instructions $s -traces $TRACE > $OUT/${name}.txt 2>&1" >> "$JOBFILE"
}

case "$MODE" in
  check) add_job check_lru lru 10000000 20000000 0 0 ;;
  e1) for p in lru srrip hawkeye mockingjay; do add_job e1_$p $p $W $S 0 0; done ;;
  e2) for p in lru srrip hawkeye mockingjay; do add_job e2_$p $p $W $S 1 0; done ;;
  e3) for w in $W3_LIST; do for p in lru hawkeye; do add_job "e3_w${w}_$p" $p $w $S3 0 0; done; done ;;
  e4) for p in lru srrip hawkeye mockingjay; do add_job e4_$p $p $W $S 0 1; done ;;
  e5) add_job e1_srrip_wb srrip_wb $W $S 0 0 ;;
  *) echo "unknown mode: $MODE"; exit 1;;
esac

echo "Running $(wc -l < "$JOBFILE") job(s), $JOBS in parallel. Output dir: $OUT"
cat "$JOBFILE"
xargs -d '\n' -P "$JOBS" -I{} bash -c "{}" < "$JOBFILE"
rm -f "$JOBFILE"
echo "DONE ($MODE)."