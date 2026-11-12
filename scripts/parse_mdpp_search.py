#!/usr/bin/env python3
"""Parse the mcf+xalan tau/pi search results (5M+5M)."""
import csv
import glob
import json
import math
import os

ROOT = r"results\raw\mdpp_search\search"
OUT_CSV = r"results\mdpp_search.csv"
SUFFIX = {"429.mcf-22B": "_429.mcf-22B.json", "483.xalancbmk-127B": "_483.xalancbmk-127B.json"}
# 5M+5M LRU baselines from the ablation (same window).
LRU = {"429.mcf-22B": (0.5042, 17.742), "483.xalancbmk-127B": (0.2506, 28.654)}


def load(path):
    sim = json.load(open(path))[0]["sim"]
    c = sim["cores"][0]
    miss = sum(sum(sim["LLC"][k]["miss"]) for k in
               ("LOAD", "RFO", "WRITE", "PREFETCH", "TRANSLATION"))
    return c["instructions"] / c["cycles"], miss * 1000 / c["instructions"]


rows = {}
for f in glob.glob(os.path.join(ROOT, "*.json")):
    base = os.path.basename(f)
    for tr, suf in SUFFIX.items():
        if base.endswith(suf):
            cfg = base[: -len(suf)]
            rows.setdefault(cfg, {})[tr] = load(f)
            break

geo = lambda v: math.exp(sum(math.log(x) for x in v) / len(v)) if v else 0
out = []
for cfg, d in rows.items():
    if len(d) != 2:
        continue
    sp = [d[t][0] / LRU[t][0] for t in SUFFIX]
    mp = [d[t][1] / LRU[t][1] for t in SUFFIX]
    out.append({
        "config": cfg,
        "mcf_ipc": round(d["429.mcf-22B"][0], 4),
        "xalan_ipc": round(d["483.xalancbmk-127B"][0], 4),
        "geo_ipc_vs_lru": round(geo(sp), 4),
        "mcf_mpki": round(d["429.mcf-22B"][1], 3),
        "xalan_mpki": round(d["483.xalancbmk-127B"][1], 3),
        "geo_mpki_vs_lru": round(geo(mp), 4),
    })

out.sort(key=lambda r: r["geo_ipc_vs_lru"], reverse=True)
fields = ["config", "mcf_ipc", "xalan_ipc", "geo_ipc_vs_lru", "mcf_mpki", "xalan_mpki", "geo_mpki_vs_lru"]
with open(OUT_CSV, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    w.writerows(out)
print("wrote", OUT_CSV, len(out), "configs")
print("| config | mcf IPC | xalan IPC | geo IPC/LRU | mcf MPKI | xalan MPKI | geo MPKI/LRU |")
print("|---|---|---|---|---|---|---|")
for r in out:
    print("| {config} | {mcf_ipc} | {xalan_ipc} | {geo_ipc_vs_lru} | {mcf_mpki} | {xalan_mpki} | {geo_mpki_vs_lru} |".format(**r))