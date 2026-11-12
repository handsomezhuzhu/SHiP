#!/usr/bin/env bash
# 批量运行 轻量 LLC 模拟器（快速策略对比，不含流水线）
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/results"
mkdir -p "$OUT"
CSV="$OUT/llc_sim_results.csv"
WARMUP=${WARMUP:-50000000}
MAXINSTR=${MAXINSTR:-150000000}
POLICIES=${POLICIES:-"lru srrip ship"}

[[ -f "$CSV" ]] || echo "trace,policy,instr,memops,l2_miss,llc_miss,llc_mpki" > "$CSV"

for t in "$ROOT"/traces/*.champsimtrace.xz; do
  name="$(basename "$t" .champsimtrace.xz)"
  for p in $POLICIES; do
    echo "run $name / $p"
    line=$(xz -dc "$t" | "$ROOT/sim/llc_sim" --policy "$p" --warmup "$WARMUP" --max-instr "$MAXINSTR" | tail -1)
    echo "$name,${line#*,}" >> "$CSV"
  done
done
echo "-> $CSV"