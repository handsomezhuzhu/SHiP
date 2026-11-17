#!/usr/bin/env bash
set -u
cd "$HOME/ChampSim"
mkdir -p val

run() {
  local name="$1" envs="$2" tr="$3"
  MPPPB_PROFILE=author1 MPPPB_STATS=1 env $envs ./bin/champsim_mpppb_mdpp -w 50000000 -i 150000000 --hide-heartbeat --json "val/${name}_${tr}.json" "traces/${tr}.champsimtrace.xz" > "val/${name}_${tr}.log" 2>&1
}

run c4_highbypass "MPPPB_DT1=30 MPPPB_DT2=150" 437.leslie3d-134B &
run c4_highbypass "MPPPB_DT1=30 MPPPB_DT2=150" 410.bwaves-945B &
run c14_theta_high "MPPPB_THETA=130 MPPPB_THETA2=160" 437.leslie3d-134B &
run c14_theta_high "MPPPB_THETA=130 MPPPB_THETA2=160" 410.bwaves-945B &
wait

echo VAL_DONE