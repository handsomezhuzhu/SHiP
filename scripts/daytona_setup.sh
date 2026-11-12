#!/usr/bin/env bash
# Daytona container setup for the single-core MDPP run.
set -euo pipefail
cd "$HOME"

sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
  build-essential git cmake liblzma-dev zlib1g-dev libbz2-dev libfmt-dev \
  libcli11-dev nlohmann-json3-dev xz-utils >/dev/null

rm -rf ChampSim
git clone --depth 80 https://github.com/ChampSim/ChampSim.git
cd ChampSim
git checkout -q 410cee62d9c429c043ea611325ce00e6c303be2a

cp "$HOME/cache.cc" src/cache.cc
mkdir -p vcpkg_installed/x64-linux/include
ln -sfn /usr/lib/x86_64-linux-gnu vcpkg_installed/x64-linux/lib
sed -i 's/-lCLI11 -llzma -lz -lbz2 -lfmt/-llzma -lz -lbz2 -lfmt/' Makefile

./config.sh --replacement-dir "$HOME/champsim_modules" "$HOME/configs/champsim_mpppb_mdpp.json" >/dev/null
make -j4 >/dev/null 2>&1
ls -l bin/champsim_mpppb_mdpp

mkdir -p traces results
BASE=https://dpc3.compas.cs.stonybrook.edu/champsim-traces/speccpu
for t in "$@"; do
  if [ ! -s "traces/$t.champsimtrace.xz" ]; then
    echo "download $t"
    curl -sL --retry 3 -o "traces/$t.champsimtrace.xz" "$BASE/$t.champsimtrace.xz"
  fi
done
du -sh traces
find traces -name '*.xz' | wc -l