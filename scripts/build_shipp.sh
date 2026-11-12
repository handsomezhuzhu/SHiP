#!/usr/bin/env bash
# 编译 SHiP++ 模块（源码在 champsim_modules/shipp，通过 --replacement-dir 挂进 ChampSim）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="$ROOT/env/venv/bin:$PATH"
cd "$ROOT/env/ChampSim"
./config.sh --replacement-dir "$ROOT/champsim_modules" "$ROOT/configs/champsim_shipp.json"
make -j"$(nproc)"
ls -l bin/champsim_shipp
