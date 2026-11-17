#!/usr/bin/env python3
"""Analyze the 2x2 generalization matrix across g0..g3 (224 runs total).

Exports:
  - results/g1_old_spp_comparison.csv
  - results/g2_new_pref_comparison.csv
  - results/g3_new_spp_comparison.csv
  - results/generalization_summary.csv
"""

from __future__ import annotations

import csv
import json
import math
import pathlib
import re
from typing import Dict, List, Tuple

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW_ROOT = ROOT / "results" / "raw"
RESULTS_DIR = ROOT / "results"

BAD_WORDS = ("panic", "deadlock", "error", "abort", "out_of_range")

GROUPS: List[Tuple[str, str, Dict[str, pathlib.Path]]] = [
    (
        "g0_old_pref",
        "SPEC06-4xx (8) + next_line + ip_stride",
        {
            "lru": RAW_ROOT / "mdpp_pref" / "lru_pref",
            "ship": RAW_ROOT / "mdpp_pref" / "ship_pref",
            "mpppb": RAW_ROOT / "mdpp_pref" / "mpppb_pref",
            "ta_mpppb": RAW_ROOT / "ta_v3" / "ta_mpppb",
        },
    ),
    (
        "g1_old_spp",
        "SPEC06-4xx (8) + next_line + spp_dev",
        {
            "lru": RAW_ROOT / "g1_old_spp" / "lru_spp",
            "ship": RAW_ROOT / "g1_old_spp" / "ship_spp",
            "mpppb": RAW_ROOT / "g1_old_spp" / "mpppb_spp",
            "ta_mpppb": RAW_ROOT / "g1_old_spp" / "ta_mpppb_spp",
        },
    ),
    (
        "g2_new_pref",
        "Unseen-20 + next_line + ip_stride",
        {
            "lru": RAW_ROOT / "g2_new_pref" / "lru_pref",
            "ship": RAW_ROOT / "g2_new_pref" / "ship_pref",
            "mpppb": RAW_ROOT / "g2_new_pref" / "mpppb_pref",
            "ta_mpppb": RAW_ROOT / "g2_new_pref" / "ta_mpppb_pref",
        },
    ),
    (
        "g3_new_spp",
        "Unseen-20 + next_line + spp_dev",
        {
            "lru": RAW_ROOT / "g3_new_spp" / "lru_spp",
            "ship": RAW_ROOT / "g3_new_spp" / "ship_spp",
            "mpppb": RAW_ROOT / "g3_new_spp" / "mpppb_spp",
            "ta_mpppb": RAW_ROOT / "g3_new_spp" / "ta_mpppb_spp",
        },
    ),
]


def suite_of(trace: str) -> str:
    if len(trace) > 3 and trace[0] == "4" and trace[3] == ".":
        return "spec06_4xx"
    if len(trace) > 3 and trace[0] == "6" and trace[3] == ".":
        return "dpc3_6xx"
    if trace.startswith(("bfs.", "pr.", "sssp.", "xs.")):
        return "zenodo_gap_xs"
    if trace.startswith("cvp1_"):
        return "zenodo_cvp1"
    if trace.startswith("qc_"):
        return "zenodo_qualcomm"
    return "unknown"


def expected_sim_of(trace: str) -> int:
    s = suite_of(trace)
    if s in ("spec06_4xx", "dpc3_6xx", "zenodo_gap_xs"):
        return 150_000_000
    if s == "zenodo_cvp1":
        return 25_000_000
    if s == "zenodo_qualcomm":
        return 60_000_000
    raise ValueError(f"Unknown suite for trace: {trace}")


def geomean(xs: List[float]) -> float:
    return math.exp(sum(math.log(x) for x in xs) / len(xs))


def parse_json(path: pathlib.Path) -> Dict[str, float]:
    d = json.loads(path.read_text())[0]["roi"]
    core = d["cores"][0]
    instr = int(core["instructions"])
    cyc = int(core["cycles"])
    llc = d["LLC"]

    def hit(k: str) -> int:
        return int(sum(llc[k]["hit"]))

    def miss(k: str) -> int:
        return int(sum(llc[k]["miss"]))

    def acc(k: str) -> int:
        return hit(k) + miss(k)

    lr_acc, lr_miss = acc("LOAD") + acc("RFO"), miss("LOAD") + miss("RFO")
    pf_acc, pf_hit, pf_miss = acc("PREFETCH"), hit("PREFETCH"), miss("PREFETCH")
    tr_acc, tr_hit, tr_miss = acc("TRANSLATION"), hit("TRANSLATION"), miss("TRANSLATION")
    wr_acc, wr_hit, wr_miss = acc("WRITE"), hit("WRITE"), miss("WRITE")
    dem_miss = lr_miss + pf_miss + tr_miss
    all_miss = dem_miss + wr_miss
    all_acc = lr_acc + pf_acc + tr_acc + wr_acc

    return {
        "instr": instr,
        "cyc": cyc,
        "ipc": instr / cyc,
        "all_acc": all_acc,
        "all_miss": all_miss,
        "all_mpki": all_miss * 1000.0 / instr,
        "dem_mpki": dem_miss * 1000.0 / instr,
        "lr_mpki": lr_miss * 1000.0 / instr,
        "lr_acc": lr_acc,
        "lr_miss": lr_miss,
        "pf_acc": pf_acc,
        "pf_hit": pf_hit,
        "pf_miss": pf_miss,
        "tr_acc": tr_acc,
        "tr_hit": tr_hit,
        "tr_miss": tr_miss,
        "wr_acc": wr_acc,
        "wr_hit": wr_hit,
        "wr_miss": wr_miss,
        "llc_pf_use": int(llc.get("useful prefetch", 0)),
        "llc_pf_usl": int(llc.get("useless prefetch", 0)),
    }


def parse_probe_stats(json_path: pathlib.Path) -> Dict[str, int]:
    """Parse final ROI mpppb/mpppb_ta/mpppb_detail line from .err (or .log)."""
    for suffix in (".err", ".log"):
        p = json_path.with_suffix(suffix)
        if not p.exists():
            continue
        res: Dict[str, int] = {}
        for line in p.read_text(errors="ignore").splitlines():
            s = line.strip()
            if s.startswith(("mpppb:", "mpppb_ta:", "mpppb_detail:")):
                for m in re.finditer(r"([a-zA-Z0-9_]+)=(-?\d+)", s):
                    res[m.group(1)] = int(m.group(2))
        if res:
            return res
    return {}


def verify_raw_group(gname: str, pdirs: Dict[str, pathlib.Path]) -> None:
    """Validate instruction windows and error logs for each group."""
    for pol, pdir in pdirs.items():
        for jp in sorted(pdir.glob("*.json")):
            trace = jp.stem
            exp = expected_sim_of(trace)
            m = parse_json(jp)
            if not (exp <= m["instr"] <= exp + 50):
                raise AssertionError(f"{gname}/{pol}/{trace}: instr={m['instr']} not in [{exp}, {exp+50}]")
            if m["cyc"] <= 0:
                raise AssertionError(f"{gname}/{pol}/{trace}: cyc={m['cyc']}")
            for suf in (".err", ".log"):
                lp = jp.with_suffix(suf)
                if lp.exists():
                    txt = lp.read_text(errors="ignore").lower()
                    for w in BAD_WORDS:
                        if w in txt:
                            raise AssertionError(f"{gname}/{pol}/{trace}{suf}: bad word {w!r}")


def summarize_subset(data: Dict[str, Dict[str, Dict[str, float]]], traces: List[str]) -> Dict[str, float]:
    n = len(traces)

    def gm(num_pol: str, den_pol: str) -> float:
        return (geomean([data[num_pol][t]["ipc"] / data[den_pol][t]["ipc"] for t in traces]) - 1.0) * 100.0

    def avg(pol: str, k: str) -> float:
        return sum(data[pol][t][k] for t in traces) / n

    def tot(pol: str, k: str) -> int:
        return int(sum(data[pol][t][k] for t in traces))

    def tr_rate(pol: str) -> float:
        acc = tot(pol, "tr_acc")
        return (tot(pol, "tr_hit") / acc * 100.0) if acc else 0.0

    def pf_rate(pol: str) -> float:
        acc = tot(pol, "pf_acc")
        return (tot(pol, "pf_hit") / acc * 100.0) if acc else 0.0

    wtl = lambda a, b: (
        sum(1 for t in traces if (data[a][t]["ipc"] / data[b][t]["ipc"] - 1.0) * 100.0 > 0.5),
        sum(1 for t in traces if abs((data[a][t]["ipc"] / data[b][t]["ipc"] - 1.0) * 100.0) <= 0.5),
        sum(1 for t in traces if (data[a][t]["ipc"] / data[b][t]["ipc"] - 1.0) * 100.0 < -0.5),
    )

    w_l, t_l, l_l = wtl("ta_mpppb", "lru")
    w_s, t_s, l_s = wtl("ta_mpppb", "ship")
    w_m, t_m, l_m = wtl("ta_mpppb", "mpppb")

    return {
        "n": n,
        "ship_vs_lru_pct": gm("ship", "lru"),
        "mpppb_vs_lru_pct": gm("mpppb", "lru"),
        "ta_vs_lru_pct": gm("ta_mpppb", "lru"),
        "ta_vs_ship_pct": gm("ta_mpppb", "ship"),
        "ta_vs_mpppb_pct": gm("ta_mpppb", "mpppb"),
        "dem_mpki_lru": avg("lru", "dem_mpki"),
        "dem_mpki_ship": avg("ship", "dem_mpki"),
        "dem_mpki_mpppb": avg("mpppb", "dem_mpki"),
        "dem_mpki_ta": avg("ta_mpppb", "dem_mpki"),
        "dem_mpki_delta_pct": (avg("ta_mpppb", "dem_mpki") / avg("lru", "dem_mpki") - 1.0) * 100.0,
        "lr_mpki_lru": avg("lru", "lr_mpki"),
        "lr_mpki_ship": avg("ship", "lr_mpki"),
        "lr_mpki_mpppb": avg("mpppb", "lr_mpki"),
        "lr_mpki_ta": avg("ta_mpppb", "lr_mpki"),
        "lr_mpki_delta_pct": (avg("ta_mpppb", "lr_mpki") / avg("lru", "lr_mpki") - 1.0) * 100.0,
        "tr_hit_rate_lru_pct": tr_rate("lru"),
        "tr_hit_rate_ship_pct": tr_rate("ship"),
        "tr_hit_rate_mpppb_pct": tr_rate("mpppb"),
        "tr_hit_rate_ta_pct": tr_rate("ta_mpppb"),
        "tr_hit_ta": tot("ta_mpppb", "tr_hit"),
        "tr_acc_ta": tot("ta_mpppb", "tr_acc"),
        "pf_hit_rate_lru_pct": pf_rate("lru"),
        "pf_hit_rate_mpppb_pct": pf_rate("mpppb"),
        "pf_hit_rate_ta_pct": pf_rate("ta_mpppb"),
        "wtl_vs_lru": f"{w_l}/{t_l}/{l_l}",
        "wtl_vs_ship": f"{w_s}/{t_s}/{l_s}",
        "wtl_vs_mpppb": f"{w_m}/{t_m}/{l_m}",
    }


def write_group_comparison_csv(
    gname: str,
    traces: List[str],
    data: Dict[str, Dict[str, Dict[str, float]]],
    stats_mp: Dict[str, Dict[str, int]],
    stats_ta: Dict[str, Dict[str, int]],
) -> pathlib.Path:
    out_csv = RESULTS_DIR / f"{gname}_comparison.csv"
    fields = [
        "trace", "suite", "sim_instr",
        "lru_ipc", "ship_ipc", "mpppb_ipc", "ta_ipc",
        "ship_vs_lru_pct", "mpppb_vs_lru_pct", "ta_vs_lru_pct",
        "ta_vs_ship_pct", "ta_vs_mpppb_pct",
        "lru_all_mpki", "lru_dem_mpki", "ship_dem_mpki", "mpppb_dem_mpki", "ta_dem_mpki",
        "lru_lr_mpki", "ship_lr_mpki", "mpppb_lr_mpki", "ta_lr_mpki",
        "lru_tr_acc", "lru_tr_hit", "ship_tr_hit", "mpppb_tr_hit", "ta_tr_acc", "ta_tr_hit",
        "lru_tr_hit_pct", "ship_tr_hit_pct", "mpppb_tr_hit_pct", "ta_tr_hit_pct",
        "mp_pref_bypass", "mp_trans_bypass",
        "ta_demand_bypass", "ta_pref_bypass", "ta_trans_bypass",
        "ta_psel", "ta_wsel", "ta_pfsel",
    ]
    with out_csv.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for t in traces:
            dl, ds, dm, dt = data["lru"][t], data["ship"][t], data["mpppb"][t], data["ta_mpppb"][t]
            sm, st = stats_mp.get(t, {}), stats_ta.get(t, {})
            th = lambda d: f"{(d['tr_hit']/d['tr_acc']*100.0):.2f}" if d["tr_acc"] else ""
            w.writerow({
                "trace": t,
                "suite": suite_of(t),
                "sim_instr": dt["instr"],
                "lru_ipc": f"{dl['ipc']:.6f}",
                "ship_ipc": f"{ds['ipc']:.6f}",
                "mpppb_ipc": f"{dm['ipc']:.6f}",
                "ta_ipc": f"{dt['ipc']:.6f}",
                "ship_vs_lru_pct": f"{(ds['ipc']/dl['ipc']-1)*100:+.4f}",
                "mpppb_vs_lru_pct": f"{(dm['ipc']/dl['ipc']-1)*100:+.4f}",
                "ta_vs_lru_pct": f"{(dt['ipc']/dl['ipc']-1)*100:+.4f}",
                "ta_vs_ship_pct": f"{(dt['ipc']/ds['ipc']-1)*100:+.4f}",
                "ta_vs_mpppb_pct": f"{(dt['ipc']/dm['ipc']-1)*100:+.4f}",
                "lru_all_mpki": f"{dl['all_mpki']:.4f}",
                "lru_dem_mpki": f"{dl['dem_mpki']:.4f}",
                "ship_dem_mpki": f"{ds['dem_mpki']:.4f}",
                "mpppb_dem_mpki": f"{dm['dem_mpki']:.4f}",
                "ta_dem_mpki": f"{dt['dem_mpki']:.4f}",
                "lru_lr_mpki": f"{dl['lr_mpki']:.4f}",
                "ship_lr_mpki": f"{ds['lr_mpki']:.4f}",
                "mpppb_lr_mpki": f"{dm['lr_mpki']:.4f}",
                "ta_lr_mpki": f"{dt['lr_mpki']:.4f}",
                "lru_tr_acc": dl["tr_acc"],
                "lru_tr_hit": dl["tr_hit"],
                "ship_tr_hit": ds["tr_hit"],
                "mpppb_tr_hit": dm["tr_hit"],
                "ta_tr_acc": dt["tr_acc"],
                "ta_tr_hit": dt["tr_hit"],
                "lru_tr_hit_pct": th(dl),
                "ship_tr_hit_pct": th(ds),
                "mpppb_tr_hit_pct": th(dm),
                "ta_tr_hit_pct": th(dt),
                "mp_pref_bypass": sm.get("pref_bypass", ""),
                "mp_trans_bypass": sm.get("trans_bypass", ""),
                "ta_demand_bypass": st.get("demand_bypass", ""),
                "ta_pref_bypass": st.get("pref_bypass", ""),
                "ta_trans_bypass": st.get("trans_bypass", ""),
                "ta_psel": st.get("psel", ""),
                "ta_wsel": st.get("wsel", ""),
                "ta_pfsel": st.get("pfsel", ""),
            })
    return out_csv


def main() -> None:
    summary_rows = []
    for gname, desc, pdirs in GROUPS:
        verify_raw_group(gname, pdirs)
        traces = sorted(p.stem for p in pdirs["lru"].glob("*.json"))
        data = {pol: {t: parse_json(pdir / f"{t}.json") for t in traces} for pol, pdir in pdirs.items()}
        stats_mp = {t: parse_probe_stats(pdirs["mpppb"] / f"{t}.json") for t in traces}
        stats_ta = {t: parse_probe_stats(pdirs["ta_mpppb"] / f"{t}.json") for t in traces}

        if gname != "g0_old_pref":
            out_csv = write_group_comparison_csv(gname, traces, data, stats_mp, stats_ta)
            print(f"[wrote] {out_csv.relative_to(ROOT)}")

        subsets: List[Tuple[str, List[str]]] = [
            ("ALL", traces),
            ("AllMPKI>=5", [t for t in traces if data["lru"][t]["all_mpki"] >= 5.0]),
            ("LR-MPKI>=2", [t for t in traces if data["lru"][t]["lr_mpki"] >= 2.0]),
        ]
        seen_suites = []
        for t in traces:
            s = suite_of(t)
            if s not in seen_suites:
                seen_suites.append(s)
        if len(seen_suites) > 1:
            for s in seen_suites:
                subsets.append((s, [t for t in traces if suite_of(t) == s]))

        print(f"\n=== {gname}: {desc} ===")
        for label, sub in subsets:
            sm = summarize_subset(data, sub)
            summary_rows.append({"group": gname, "subset": label, **sm})
            print(
                f"  [{label:14s} n={sm['n']:2d}] "
                f"SHiP={sm['ship_vs_lru_pct']:+.2f}% MPPPB={sm['mpppb_vs_lru_pct']:+.2f}% TA={sm['ta_vs_lru_pct']:+.2f}% | "
                f"TA/SHiP={sm['ta_vs_ship_pct']:+.2f}% TA/MPPPB={sm['ta_vs_mpppb_pct']:+.2f}% | "
                f"DemMPKI {sm['dem_mpki_lru']:.2f}->{sm['dem_mpki_ta']:.2f} ({sm['dem_mpki_delta_pct']:+.2f}%) | "
                f"TrHit {sm['tr_hit_rate_lru_pct']:.2f}%/{sm['tr_hit_rate_ship_pct']:.2f}%/{sm['tr_hit_rate_mpppb_pct']:.2f}%/{sm['tr_hit_rate_ta_pct']:.2f}% | "
                f"W/T/L vs LRU={sm['wtl_vs_lru']} vs SHiP={sm['wtl_vs_ship']} vs MPPPB={sm['wtl_vs_mpppb']}"
            )

    sum_csv = RESULTS_DIR / "generalization_summary.csv"
    fields = list(summary_rows[0].keys())
    with sum_csv.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in summary_rows:
            fmt = {}
            for k, v in r.items():
                fmt[k] = f"{v:.4f}" if isinstance(v, float) else v
            w.writerow(fmt)
    print(f"\n[wrote] {sum_csv.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
