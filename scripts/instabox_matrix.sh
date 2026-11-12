#!/usr/bin/env bash
set -u
cd ~/ChampSim
W=50000000
I=150000000
OUT=/data/home/results
mkdir -p "$OUT"

runone() {
  local spec="$1"
  local pol="${spec%%:*}"
  local tr="${spec##*:}"
  mkdir -p "$OUT/$pol"
  local json="$OUT/$pol/$tr.json"
  if [ -s "$json" ]; then echo "skip $pol $tr"; return 0; fi
  echo "start $pol $tr $(date -u +%H:%M:%S)"
  local start
  start=$(date +%s)
  if [ "$pol" = "mpppb" ]; then
    MPPPB_TAU_BYPASS=250 MPPPB_TAU_P1=150 MPPPB_TAU_P2=75 MPPPB_TAU_P3=0 \
    MPPPB_TAU_PROMOTE=100 MPPPB_POS1=3 MPPPB_POS2=3 MPPPB_POS3=2 \
    "bin/champsim_mpppb" -w $W -i $I --hide-heartbeat --json "$json" "traces/$tr.champsimtrace.xz" \
      > /dev/null 2> "$OUT/$pol/$tr.err"
  else
    "bin/champsim_$pol" -w $W -i $I --hide-heartbeat --json "$json" "traces/$tr.champsimtrace.xz" \
      > /dev/null 2> "$OUT/$pol/$tr.err"
  fi
  local rc=$?
  local elapsed=$(( $(date +%s) - start ))
  echo "$elapsed" > "$OUT/$pol/$tr.time"
  echo "done $pol $tr rc=$rc ${elapsed}s"
}

pids=()
for spec in "$@"; do
  runone "$spec" &
  pids+=("$!")
  if (( ${#pids[@]} >= 4 )); then
    wait "${pids[0]}"
    pids=("${pids[@]:1}")
  fi
done
wait
echo "BOX DONE $(hostname)"