#!/usr/bin/env bash
set -euo pipefail
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
  build-essential git cmake liblzma-dev zlib1g-dev libbz2-dev libfmt-dev \
  libcli11-dev nlohmann-json3-dev xz-utils >/dev/null
cd /data/home
if [ ! -d ChampSim/.git ]; then
  rm -rf ChampSim
  git clone --depth 80 https://github.com/ChampSim/ChampSim.git
fi
cd ChampSim
git checkout -q 410cee62d9c429c043ea611325ce00e6c303be2a
cp /data/home/cache.cc src/cache.cc
mkdir -p vcpkg_installed/x64-linux/include
ln -sfn /usr/lib/x86_64-linux-gnu vcpkg_installed/x64-linux/lib
sed -i 's/-lCLI11 -llzma -lz -lbz2 -lfmt/-llzma -lz -lbz2 -lfmt/' Makefile
for cfg in lru ship mpppb; do
  ./config.sh --replacement-dir /data/home/champsim_modules /data/home/configs/champsim_$cfg.json >/dev/null
  make -j4 >/dev/null 2>&1
done
ls -l bin/champsim_lru bin/champsim_ship bin/champsim_mpppb
mkdir -p traces
BASE=https://dpc3.compas.cs.stonybrook.edu/champsim-traces/speccpu
for t in 400.perlbench-41B 403.gcc-16B 410.bwaves-945B 429.mcf-22B 437.leslie3d-134B 450.soplex-92B 470.lbm-1274B 483.xalancbmk-127B; do
  if [ ! -s "traces/$t.champsimtrace.xz" ]; then
    ( curl -sL --retry 3 -o "traces/$t.champsimtrace.xz" "$BASE/$t.champsimtrace.xz" ) &
  fi
done
wait
du -sh traces
ls -1 traces/*.xz | wc -l