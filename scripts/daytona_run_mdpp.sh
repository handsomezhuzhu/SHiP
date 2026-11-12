#!/usr/bin/env bash
set -u
cd "$HOME/ChampSim"
mkdir -p results
for t in "$@"; do
  (
    MPPPB_PROFILE=author1 MPPPB_STATS=1 \
    ./bin/champsim_mpppb_mdpp -w 50000000 -i 150000000 --hide-heartbeat \
      --json "results/$t.json" "traces/$t.champsimtrace.xz" \
      > "results/$t.log" 2>&1
  ) &
done
wait
echo ALL_DONE