#!/usr/bin/env python3
"""Compare the c4/c14 full 8-trace validation with author1 / LRU / SHiP."""
import csv
import glob
import json
import math
import os

ROOT = r"results\raw\mdpp_validate"
AUTHOR1 = r"results\raw\mdpp_author1\mpppb"
MATRIX1 = r"results\raw\matrix1"
TRACES = [
    "400.perlbench-41B", "403.gcc-16B", "410.bwaves-945B", "429.mcf-22B",
    "437.leslie3d-134B", "450.soplex-92B", "470.lbm-1274B", "483.xalancbmk-127B",
]
CONFIGS = ["c4_highbypass", "c14_theta_high"]
SUFFIX = {t: f"_{t}.json" for t in TRACES}


def load(path):
    sim = json.load(open(path))[0]["sim"]
    c = sim["cores"][0]
    miss = sum(sum(sim["LLC"][k]["miss"]) for k in
               ("LOAD", "RFO", "WRITE", "PREFETCH", "TRANSLATION"))
    return c["instructions"], c["cycles"], miss


def ipc_mpki(path):
    ins, cyc, miss = load(path)
    return ins / cyc, miss * 1000 / ins


data = {cfg: {} for cfg in CONFIGS}
for f in glob.glob(os.path.join(ROOT, "*", "val", "*.json")):
    base = os.path.basename(f)
    for cfg in CONFIGS:
        for tr, suf in SUFFIX.items():
            if base == cfg + suf:
                data[cfg][tr] = ipc_mpki(f)

print("found", {k: len(v) for k, v in data.items()})
geo = lambda v: math.exp(sum(math.log(x) for x in v) / len(v)) if v else 0

base = {}
for tr in TRACES:
    base[tr] = {
        "lru": ipc_mpki(os.path.join(MATRIX1, "lru", tr + ".json")),
        "ship": ipc_mpki(os.path.join(MATRIX1, "ship", tr + ".json")),
        "srrip": ipc_mpki(os.path.join(MATRIX1, "mpppb", tr + ".json")),
        "author1": ipc_mpki(os.path.join(AUTHOR1, tr + ".json")),
    }

for cfg in CONFIGS:
    print()
    print("##", cfg)
    print("| trace | author1 IPC | c IPC | c/author1 | c/LRU | author1 MPKI | c MPKI |")
    print("|---|---|---|---|---|---|---|")
    sp_a, sp_l, mp_a = [], [], []
    for tr in TRACES:
        if tr not in data[cfg]:
            print("| MISSING", tr, "| | | | | | |")
            continue
        ipc, mpki = data[cfg][tr]
        a_ipc, a_mpki = base[tr]["author1"]
        l_ipc, _ = base[tr]["lru"]
        print(f"| {tr} | {a_ipc:.4f} | {ipc:.4f} | {ipc/a_ipc:.4f} | {ipc/l_ipc:.4f} | {a_mpki:.2f} | {mpki:.2f} |")
        sp_a.append(ipc / a_ipc)
        sp_l.append(ipc / l_ipc)
        mp_a.append(mpki / a_mpki)
    print(f"geomean c/author1 = {geo(sp_a):.4f}; c/LRU = {geo(sp_l):.4f}; MPKI c/author1 = {geo(mp_a):.4f}")

# CSV
with open(r"results\mdpp_validate.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["config", "trace", "ipc", "mpki", "ipc_vs_author1", "ipc_vs_lru", "mpki_vs_author1"])
    for cfg in CONFIGS:
        for tr in TRACES:
            if tr not in data[cfg]:
                continue
            ipc, mpki = data[cfg][tr]
            a_ipc, a_mpki = base[tr]["author1"]
            l_ipc, _ = base[tr]["lru"]
            w.writerow([cfg, tr, round(ipc, 4), round(mpki, 4), round(ipc / a_ipc, 4), round(ipc / l_ipc, 4), round(mpki / a_mpki, 4)])
print("wrote results\\mdpp_validate.csv")