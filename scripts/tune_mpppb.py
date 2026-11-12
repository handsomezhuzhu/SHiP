#!/usr/bin/env python3
"""MPPPB 阈值/位置随机搜索（论文没有给出 tau/pi 的具体数值）。

用法：
  ./scripts/tune_mpppb.py --traces traces/429.mcf-22B.champsimtrace.xz traces/483.xalancbmk-127B.champsimtrace.xz \
      --trials 30 --warmup 5000000 --sim 10000000

每次试验用环境变量覆盖 MPPPB_TAU_*，跑一遍 ChampSim，记录 IPC / LLC MPKI。
输出 results/tune_mpppb.csv，并按平均 IPC 排序打印前几名。
"""
import argparse
import csv
import json
import os
import random
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SIM = ROOT / "env/ChampSim/bin/champsim_mpppb"


def run_one(trace, warmup, sim_instr, taus):
    env = os.environ.copy()
    env.update({k: str(v) for k, v in taus.items()})
    out = Path("/tmp") / f"mpppb_{os.getpid()}_{random.randint(0, 1 << 30)}.json"
    cmd = [str(SIM), "-w", str(warmup), "-i", str(sim_instr), "--hide-heartbeat",
           "--json", str(out), str(trace)]
    subprocess.run(cmd, env=env, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    d = json.load(open(out))[0]["sim"]
    out.unlink(missing_ok=True)
    c = d["cores"][0]
    llc = d["LLC"]
    miss = sum(sum(llc[k]["miss"]) for k in ("LOAD", "RFO", "WRITE", "PREFETCH", "TRANSLATION"))
    return c["instructions"] / c["cycles"], miss * 1000.0 / c["instructions"]


def sample_taus(rng, mode):
    if mode == "grid":
        return None
    # 单调阈值：tau_bypass >= tau_p1 >= tau_p2 >= tau_p3；promote 单独
    tau0 = rng.choice([80, 120, 150, 200, 250])
    tau1 = rng.randint(20, tau0)
    tau2 = rng.randint(-40, tau1)
    tau3 = rng.randint(-120, tau2)
    promote = rng.choice([-50, -20, 0, 20, 50])
    return {"MPPPB_TAU_BYPASS": tau0, "MPPPB_TAU_P1": tau1,
            "MPPPB_TAU_P2": tau2, "MPPPB_TAU_P3": tau3,
            "MPPPB_TAU_PROMOTE": promote}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--traces", nargs="+", required=True)
    ap.add_argument("--trials", type=int, default=20)
    ap.add_argument("--warmup", type=int, default=5_000_000)
    ap.add_argument("--sim", type=int, default=10_000_000, dest="sim_instr")
    ap.add_argument("--out", default=str(ROOT / "results/tune_mpppb.csv"))
    args = ap.parse_args()

    rng = random.Random(20261112)
    rows = []
    for i in range(args.trials):
        taus = sample_taus(rng, "random")
        vals = []
        for t in args.traces:
            ipc, mpki = run_one(t, args.warmup, args.sim_instr, taus)
            vals.append((ipc, mpki))
        rows.append({**taus,
                     "mean_ipc": sum(v[0] for v in vals) / len(vals),
                     "mean_mpki": sum(v[1] for v in vals) / len(vals)})
        print(f"[{i+1}/{args.trials}] {taus} -> ipc={rows[-1]['mean_ipc']:.4f} "
              f"mpki={rows[-1]['mean_mpki']:.2f}", flush=True)

    rows.sort(key=lambda r: r["mean_ipc"], reverse=True)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\n-> {args.out}")
    for r in rows[:3]:
        print(r)


if __name__ == "__main__":
    sys.exit(main())