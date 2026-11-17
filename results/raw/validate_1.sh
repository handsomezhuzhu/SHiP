#!/usr/bin/env bash
set -u
cd "$HOME/ChampSim"
mkdir -p val

run() {
  local name="$1" envs="$2" tr="$3"
  MPPPB_PROFILE=author1 MPPPB_STATS=1 env $envs ./bin/champsim_mpppb_mdpp -w 50000000 -i 150000000 --hide-heartbeat --json "val/${name}_${tr}.json" "traces/${tr}.champsimtrace.xz" > "val/${name}_${tr}.log" 2>&1
}

run c4_highbypass "MPPPB_DT1=30 MPPPB_DT2=150" 429.mcf-22B &
run c4_highbypass "MPPPB_DT1=30 MPPPB_DT2=150" 483.xalancbmk-127B &
run c4_highbypass "MPPPB_DT1=30 MPPPB_DT2=150" 450.soplex-92B &
run c14_theta_high "MPPPB_THETA=130 MPPPB_THETA2=160" 429.mcf-22B &
wait

run c14_theta_high "MPPPB_THETA=130 MPPPB_THETA2=160" 483.xalancbmk-127B &
run c14_theta_high "MPPPB_THETA=130 MPPPB_THETA2=160" 450.soplex-92B &
wait

echo VAL_DONE