#!/usr/bin/env bash


set -euo pipefail


TRACE=./traces/qwen_p7_n12_trace1.xz

declare -A BIN=(
  [lru]=./bin/hashed_perceptron-no-no-no-no-no-no-no-lru-lru-lru-lru-lru-lru-lru-lru-1core-lru
  [srrip]=./bin/hashed_perceptron-no-no-no-no-no-no-no-lru-lru-lru-lru-srrip-lru-lru-lru-1core-srrip
  [hawkeye]=./bin/hashed_perceptron-no-no-no-no-no-no-no-lru-lru-lru-lru-hawkeye-lru-lru-lru-1core-hawkeye
  [mockingjay]=./bin/hashed_perceptron-no-no-no-no-no-no-no-lru-lru-lru-lru-mockingjay-lru-lru-lru-1core-mockingjay
)

W=290000000
S=1405000000

W3_LIST="290000000 290000001 291000000 295000000 300000000"
S3=560000000

OUT=results/exp


MODE=${1:-}

[ -z "$MODE" ] && {
  sed -n '2,13p' "$0"
  exit 1
}


for p in "${!BIN[@]}"; do
  [ -x "${BIN[$p]}" ] || {
    echo "ERROR: binary for '$p' not found: ${BIN[$p]}"
    exit 1
  }
done


[ -f "$TRACE" ] || {
  echo "ERROR: trace not found: $TRACE"
  exit 1
}

mkdir -p "$OUT"


run_job() {
  local tag=$1
  local pol=$2
  local w=$3
  local s=$4
  local ideal=$5

  local logfile="$OUT/${tag}_${pol}.txt"

  echo ""
  echo "=================================================="
  echo "STARTING: $tag | $pol"
  echo "Warmup: $w | Simulation: $s"
  echo "Ideal DRAM writes: $ideal"
  echo "Log: $logfile"
  echo "=================================================="

  env IDEAL_DRAM_WRITES="$ideal" \
    "${BIN[$pol]}" \
    -warmup_instructions "$w" \
    -simulation_instructions "$s" \
    -traces "$TRACE" \
    > "$logfile" 2>&1

  echo "FINISHED: $tag | $pol"
  echo "=================================================="
}

case "$MODE" in

  check)
    run_job check lru 10000000 20000000 0
    ;;

  e1)
    for p in lru srrip hawkeye mockingjay; do
      run_job e1 "$p" "$W" "$S" 0
    done
    ;;

  e2)
    for p in lru srrip hawkeye mockingjay; do
      run_job e2 "$p" "$W" "$S" 1
    done
    ;;

  e3)
    for w in $W3_LIST; do
      for p in lru hawkeye; do
        run_job "e3_w${w}" "$p" "$w" "$S3" 0
      done
    done
    ;;

  *)
    echo "Unknown mode: $MODE"
    exit 1
    ;;
esac

echo ""
echo "=================================================="
echo "ALL JOBS COMPLETED SUCCESSFULLY ($MODE)"
echo "=================================================="

echo "Next: python3 analyze_dram.py $OUT/${MODE}_*.txt"
