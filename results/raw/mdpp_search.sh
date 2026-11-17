#!/usr/bin/env bash
set -u
cd "$HOME/ChampSim"
mkdir -p search

run() {
  local name="$1" envs="$2" tr="$3"
  MPPPB_PROFILE=author1 MPPPB_STATS=1 env $envs ./bin/champsim_mpppb_mdpp -w 5000000 -i 5000000 --hide-heartbeat --json "search/${name}_${tr}.json" "traces/${tr}.champsimtrace.xz" > "search/${name}_${tr}.log" 2>&1
}

run c0_author1 "" 429.mcf-22B &
run c0_author1 "" 483.xalancbmk-127B &
run c1_nobypass "MPPPB_DT1=1000 MPPPB_DT2=1000" 429.mcf-22B &
run c1_nobypass "MPPPB_DT1=1000 MPPPB_DT2=1000" 483.xalancbmk-127B &
wait

run c2_lowbypass "MPPPB_DT1=100 MPPPB_DT2=400" 429.mcf-22B &
run c2_lowbypass "MPPPB_DT1=100 MPPPB_DT2=400" 483.xalancbmk-127B &
run c3_midbypass "MPPPB_DT1=80 MPPPB_DT2=320" 429.mcf-22B &
run c3_midbypass "MPPPB_DT1=80 MPPPB_DT2=320" 483.xalancbmk-127B &
wait

run c4_highbypass "MPPPB_DT1=30 MPPPB_DT2=150" 429.mcf-22B &
run c4_highbypass "MPPPB_DT1=30 MPPPB_DT2=150" 483.xalancbmk-127B &
run c5_prom60 "MPPPB_PROMOTE=60" 429.mcf-22B &
run c5_prom60 "MPPPB_PROMOTE=60" 483.xalancbmk-127B &
wait

run c6_prom100 "MPPPB_PROMOTE=100" 429.mcf-22B &
run c6_prom100 "MPPPB_PROMOTE=100" 483.xalancbmk-127B &
run c7_prom120 "MPPPB_PROMOTE=120" 429.mcf-22B &
run c7_prom120 "MPPPB_PROMOTE=120" 483.xalancbmk-127B &
wait

run c8_plv_low "MPPPB_PLV0T=0 MPPPB_PLV0P=0 MPPPB_PLV1T=20 MPPPB_PLV1P=12 MPPPB_PLV2T=35 MPPPB_PLV2P=15" 429.mcf-22B &
run c8_plv_low "MPPPB_PLV0T=0 MPPPB_PLV0P=0 MPPPB_PLV1T=20 MPPPB_PLV1P=12 MPPPB_PLV2T=35 MPPPB_PLV2P=15" 483.xalancbmk-127B &
run c9_plv_mid "MPPPB_PLV0T=30 MPPPB_PLV0P=0 MPPPB_PLV1T=40 MPPPB_PLV1P=12 MPPPB_PLV2T=48 MPPPB_PLV2P=15" 429.mcf-22B &
run c9_plv_mid "MPPPB_PLV0T=30 MPPPB_PLV0P=0 MPPPB_PLV1T=40 MPPPB_PLV1P=12 MPPPB_PLV2T=48 MPPPB_PLV2P=15" 483.xalancbmk-127B &
wait

run c10_plv_high "MPPPB_PLV0T=50 MPPPB_PLV0P=0 MPPPB_PLV1T=60 MPPPB_PLV1P=12 MPPPB_PLV2T=70 MPPPB_PLV2P=15" 429.mcf-22B &
run c10_plv_high "MPPPB_PLV0T=50 MPPPB_PLV0P=0 MPPPB_PLV1T=60 MPPPB_PLV1P=12 MPPPB_PLV2T=70 MPPPB_PLV2P=15" 483.xalancbmk-127B &
run c11_train96 "MPPPB_TRAIN_THRESHOLD=96" 429.mcf-22B &
run c11_train96 "MPPPB_TRAIN_THRESHOLD=96" 483.xalancbmk-127B &
wait

run c12_train160 "MPPPB_TRAIN_THRESHOLD=160" 429.mcf-22B &
run c12_train160 "MPPPB_TRAIN_THRESHOLD=160" 483.xalancbmk-127B &
run c13_theta_low "MPPPB_THETA=90 MPPPB_THETA2=120" 429.mcf-22B &
run c13_theta_low "MPPPB_THETA=90 MPPPB_THETA2=120" 483.xalancbmk-127B &
wait

run c14_theta_high "MPPPB_THETA=130 MPPPB_THETA2=160" 429.mcf-22B &
run c14_theta_high "MPPPB_THETA=130 MPPPB_THETA2=160" 483.xalancbmk-127B &
run c15_lowbypass_p60 "MPPPB_DT1=100 MPPPB_DT2=400 MPPPB_PROMOTE=60" 429.mcf-22B &
run c15_lowbypass_p60 "MPPPB_DT1=100 MPPPB_DT2=400 MPPPB_PROMOTE=60" 483.xalancbmk-127B &
wait

run c16_plvmid_train96 "MPPPB_PLV0T=30 MPPPB_PLV0P=0 MPPPB_PLV1T=40 MPPPB_PLV1P=12 MPPPB_PLV2T=48 MPPPB_PLV2P=15 MPPPB_TRAIN_THRESHOLD=96" 429.mcf-22B &
run c16_plvmid_train96 "MPPPB_PLV0T=30 MPPPB_PLV0P=0 MPPPB_PLV1T=40 MPPPB_PLV1P=12 MPPPB_PLV2T=48 MPPPB_PLV2P=15 MPPPB_TRAIN_THRESHOLD=96" 483.xalancbmk-127B &
run c17_nobypass_p60 "MPPPB_DT1=1000 MPPPB_DT2=1000 MPPPB_PROMOTE=60" 429.mcf-22B &
run c17_nobypass_p60 "MPPPB_DT1=1000 MPPPB_DT2=1000 MPPPB_PROMOTE=60" 483.xalancbmk-127B &
wait

echo SEARCH_DONE