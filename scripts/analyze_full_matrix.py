#!/usr/bin/env python3
"""Analyze the complete 28-workload x 3-prefetcher x 4-policy matrix and dual-prefetcher LOO ablations.

Exports CSV summaries into results/:
  - results/full_matrix_per_trace.csv   (all 28 traces x 3 regimes x 4 policies = 336 runs)
  - results/full_matrix_summary.csv     (geomean & MPKI breakdowns across ALL-28, OLD-8, NEW-20, suites, active subsets)
  - results/full_loo_per_trace.csv      (all 28 traces x 2 prefetchers x 6 variants [TA + 4 LOO + tduel])
  - results/full_loo_summary.csv        (module contributions, worst regressions, PTW hit impacts)
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import pathlib
import sys
from typing import Dict, List, Tuple

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from run_3groups_cloud import NEW_TRACES, OLD_TRACES  # noqa: E402

RAW = ROOT / "results" / "raw"
OUT = ROOT / "results"

OLD_NAMES = [t.name for t in OLD_TRACES]
NEW_NAMES = [t.name for t in NEW_TRACES]
ALL_NAMES = OLD_NAMES + NEW_NAMES
SIM_MAP = {t.name: t.sim for t in (OLD_TRACES + NEW_TRACES)}

POLICIES = ("lru", "ship", "mpppb", "ta_mpppb")
REGIMES = ("nopref", "ip_stride", "spp_dev")
LOO_VARIANTS = ("no_zeropc", "no_ptw_prot", "no_write_arb", "no_pref_arb", "tduel")


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


def geomean(xs: List[float]) -> float:
    return math.exp(sum(math.log(x) for x in xs) / len(xs))


def parse_json(path: pathlib.Path, expected_sim: int) -> Dict[str, float]:
    d = json.loads(path.read_text(encoding="utf-8"))[0]["roi"]
    core = d["cores"][0]
    instr = int(core["instructions"])
    cyc = int(core["cycles"])
    if not (expected_sim <= instr <= expected_sim + 100) or cyc <= 0:
        raise AssertionError(f"{path}: invalid ROI instr={instr} (exp {expected_sim}), cyc={cyc}")
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

    return {
        "instr": instr,
        "cyc": cyc,
        "ipc": instr / cyc,
        "all_mpki": all_miss * 1000.0 / instr,
        "dem_mpki": dem_miss * 1000.0 / instr,
        "lr_mpki": lr_miss * 1000.0 / instr,
        "wr_mpki": wr_miss * 1000.0 / instr,
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
    }


def matrix_json_path(regime: str, pol: str, trace: str) -> pathlib.Path:
    is_old = trace in OLD_NAMES
    if regime == "nopref":
        if is_old:
            sub = {"lru": "repro_2B/lru", "ship": "repro_2B/ship", "mpppb": "repro_2B/author1", "ta_mpppb": "ta_v3_np/ta_mpppb_np"}[pol]
        else:
            sub = {"lru": "g_new_nopref/lru", "ship": "g_new_nopref/ship", "mpppb": "g_new_nopref/mpppb", "ta_mpppb": "g_new_nopref/ta_mpppb_np"}[pol]
    elif regime == "ip_stride":
        if is_old:
            sub = {"lru": "repro_3B/lru_pref", "ship": "repro_3B/ship_pref", "mpppb": "repro_3B/mpppb_pref", "ta_mpppb": "ta_v3/ta_mpppb"}[pol]
        else:
            sub = {"lru": "g2_new_pref/lru_pref", "ship": "g2_new_pref/ship_pref", "mpppb": "g2_new_pref/mpppb_pref", "ta_mpppb": "g2_new_pref/ta_mpppb_pref"}[pol]
    elif regime == "spp_dev":
        if is_old:
            sub = {"lru": "g1_old_spp/lru_spp", "ship": "g1_old_spp/ship_spp", "mpppb": "g1_old_spp/mpppb_spp", "ta_mpppb": "g1_old_spp/ta_mpppb_spp"}[pol]
        else:
            sub = {"lru": "g3_new_spp/lru_spp", "ship": "g3_new_spp/ship_spp", "mpppb": "g3_new_spp/mpppb_spp", "ta_mpppb": "g3_new_spp/ta_mpppb_spp"}[pol]
    else:
        raise ValueError(regime)
    return RAW / sub / f"{trace}.json"


def loo_json_path(pref: str, var: str, trace: str) -> pathlib.Path:
    grp = "loo_pref" if pref == "ip_stride" else "loo_spp"
    p = RAW / grp / var / f"{trace}.json"
    if not p.exists() and pref == "ip_stride" and var == "tduel":
        alt = RAW / "v3_ablate" / "v3_c21_tduel" / f"{trace}.json"
        if alt.exists():
            return alt
    return p


def summarize_matrix_subset(
    regime_data: Dict[str, Dict[str, Dict[str, float]]], traces: List[str]
) -> Dict[str, object]:
    n = len(traces)
    if n == 0:
        return {}

    def gm(num: str, den: str) -> float:
        return (geomean([regime_data[num][t]["ipc"] / regime_data[den][t]["ipc"] for t in traces]) - 1.0) * 100.0

    def avg(pol: str, k: str) -> float:
        return sum(regime_data[pol][t][k] for t in traces) / n

    def tot(pol: str, k: str) -> int:
        return int(sum(regime_data[pol][t][k] for t in traces))

    def rate(pol: str, hit_k: str, acc_k: str) -> float:
        a = tot(pol, acc_k)
        return (tot(pol, hit_k) / a * 100.0) if a else 0.0

    def wtl(a: str, b: str, thr: float = 0.5) -> str:
        w = sum(1 for t in traces if (regime_data[a][t]["ipc"] / regime_data[b][t]["ipc"] - 1.0) * 100.0 > thr)
        l = sum(1 for t in traces if (regime_data[a][t]["ipc"] / regime_data[b][t]["ipc"] - 1.0) * 100.0 < -thr)
        ti = n - w - l
        return f"{w}/{ti}/{l}"

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
        "lr_mpki_lru": avg("lru", "lr_mpki"),
        "lr_mpki_ship": avg("ship", "lr_mpki"),
        "lr_mpki_mpppb": avg("mpppb", "lr_mpki"),
        "lr_mpki_ta": avg("ta_mpppb", "lr_mpki"),
        "tr_hit_lru_pct": rate("lru", "tr_hit", "tr_acc"),
        "tr_hit_ship_pct": rate("ship", "tr_hit", "tr_acc"),
        "tr_hit_mpppb_pct": rate("mpppb", "tr_hit", "tr_acc"),
        "tr_hit_ta_pct": rate("ta_mpppb", "tr_hit", "tr_acc"),
        "pf_hit_lru_pct": rate("lru", "pf_hit", "pf_acc"),
        "pf_hit_mpppb_pct": rate("mpppb", "pf_hit", "pf_acc"),
        "pf_hit_ta_pct": rate("ta_mpppb", "pf_hit", "pf_acc"),
        "wtl_vs_lru": wtl("ta_mpppb", "lru"),
        "wtl_vs_ship": wtl("ta_mpppb", "ship"),
        "wtl_vs_mpppb": wtl("ta_mpppb", "mpppb"),
    }


def analyze_matrix(allow_partial: bool) -> Dict[str, Dict[str, Dict[str, Dict[str, float]]]]:
    matrix: Dict[str, Dict[str, Dict[str, Dict[str, float]]]] = {}
    trace_rows: List[Dict[str, object]] = []
    summary_rows: List[Dict[str, object]] = []

    for reg in REGIMES:
        matrix[reg] = {p: {} for p in POLICIES}
        complete_traces: List[str] = []
        missing = 0
        for tr in ALL_NAMES:
            ok = True
            loaded = {}
            for pol in POLICIES:
                jp = matrix_json_path(reg, pol, tr)
                if not jp.exists():
                    if not allow_partial:
                        raise FileNotFoundError(f"Missing matrix JSON: {jp}")
                    ok = False
                    missing += 1
                    continue
                loaded[pol] = parse_json(jp, SIM_MAP[tr])
            if ok:
                complete_traces.append(tr)
                for pol in POLICIES:
                    matrix[reg][pol][tr] = loaded[pol]
                dl, ds, dm, dt = loaded["lru"], loaded["ship"], loaded["mpppb"], loaded["ta_mpppb"]
                th = lambda d: round(d["tr_hit"] / d["tr_acc"] * 100.0, 2) if d["tr_acc"] else 0.0
                trace_rows.append(
                    {
                        "regime": reg,
                        "trace": tr,
                        "suite": suite_of(tr),
                        "is_old": int(tr in OLD_NAMES),
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
                        "ta_dem_mpki": f"{dt['dem_mpki']:.4f}",
                        "lru_lr_mpki": f"{dl['lr_mpki']:.4f}",
                        "ta_lr_mpki": f"{dt['lr_mpki']:.4f}",
                        "lru_wr_mpki": f"{dl['wr_mpki']:.4f}",
                        "ta_wr_mpki": f"{dt['wr_mpki']:.4f}",
                        "lru_tr_hit_pct": th(dl),
                        "mpppb_tr_hit_pct": th(dm),
                        "ta_tr_hit_pct": th(dt),
                        "ta_tr_acc": dt["tr_acc"],
                    }
                )

        if not complete_traces:
            continue
        subsets: List[Tuple[str, List[str]]] = [
            ("ALL", complete_traces),
            ("OLD_8", [t for t in complete_traces if t in OLD_NAMES]),
            ("NEW_20", [t for t in complete_traces if t in NEW_NAMES]),
            ("AllMPKI>=5", [t for t in complete_traces if matrix[reg]["lru"][t]["all_mpki"] >= 5.0]),
            ("LR-MPKI>=2", [t for t in complete_traces if matrix[reg]["lru"][t]["lr_mpki"] >= 2.0]),
        ]
        for s in ("spec06_4xx", "dpc3_6xx", "zenodo_gap_xs", "zenodo_cvp1", "zenodo_qualcomm"):
            st = [t for t in complete_traces if suite_of(t) == s]
            if st:
                subsets.append((s, st))

        print(f"\n=== MATRIX REGIME: {reg} (complete traces: {len(complete_traces)}/28, missing files={missing}) ===")
        for label, sub in subsets:
            if not sub:
                continue
            sm = summarize_matrix_subset(matrix[reg], sub)
            summary_rows.append({"regime": reg, "subset": label, **sm})
            print(
                f"  [{label:15s} n={sm['n']:2d}] "
                f"SHiP={sm['ship_vs_lru_pct']:+.2f}% MPPPB={sm['mpppb_vs_lru_pct']:+.2f}% TA={sm['ta_vs_lru_pct']:+.2f}% | "
                f"TA/SHiP={sm['ta_vs_ship_pct']:+.2f}% TA/MP={sm['ta_vs_mpppb_pct']:+.2f}% | "
                f"LR-MPKI {sm['lr_mpki_lru']:.2f}->{sm['lr_mpki_ta']:.2f} | "
                f"TrHit {sm['tr_hit_lru_pct']:.1f}%/{sm['tr_hit_mpppb_pct']:.1f}%/{sm['tr_hit_ta_pct']:.1f}% | "
                f"W/T/L(MP)={sm['wtl_vs_mpppb']}"
            )

    if trace_rows:
        with (OUT / "full_matrix_per_trace.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(trace_rows[0].keys()))
            w.writeheader()
            w.writerows(trace_rows)
    if summary_rows:
        with (OUT / "full_matrix_summary.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(summary_rows[0].keys()))
            w.writeheader()
            for r in summary_rows:
                w.writerow({k: (f"{v:.4f}" if isinstance(v, float) else v) for k, v in r.items()})
    return matrix


def analyze_loo(allow_partial: bool, matrix: Dict[str, Dict[str, Dict[str, Dict[str, float]]]]) -> None:
    loo_rows: List[Dict[str, object]] = []
    sum_rows: List[Dict[str, object]] = []

    for pref in ("ip_stride", "spp_dev"):
        base_ta = matrix.get(pref, {}).get("ta_mpppb", {})
        if not base_ta:
            continue
        for var in LOO_VARIANTS:
            pairs: List[Tuple[str, Dict[str, float], Dict[str, float]]] = []
            for tr in ALL_NAMES:
                if tr not in base_ta:
                    continue
                jp = loo_json_path(pref, var, tr)
                if not jp.exists():
                    if not allow_partial:
                        raise FileNotFoundError(f"Missing LOO JSON: {jp}")
                    continue
                d_var = parse_json(jp, SIM_MAP[tr])
                d_base = base_ta[tr]
                pairs.append((tr, d_base, d_var))
                delta_pct = (d_var["ipc"] / d_base["ipc"] - 1.0) * 100.0
                th_b = (d_base["tr_hit"] / d_base["tr_acc"] * 100.0) if d_base["tr_acc"] else 0.0
                th_v = (d_var["tr_hit"] / d_var["tr_acc"] * 100.0) if d_var["tr_acc"] else 0.0
                loo_rows.append(
                    {
                        "prefetcher": pref,
                        "variant": var,
                        "trace": tr,
                        "suite": suite_of(tr),
                        "ta_ipc": f"{d_base['ipc']:.6f}",
                        "var_ipc": f"{d_var['ipc']:.6f}",
                        "delta_vs_ta_pct": f"{delta_pct:+.4f}",
                        "ta_lr_mpki": f"{d_base['lr_mpki']:.4f}",
                        "var_lr_mpki": f"{d_var['lr_mpki']:.4f}",
                        "ta_tr_hit_pct": f"{th_b:.2f}",
                        "var_tr_hit_pct": f"{th_v:.2f}",
                    }
                )

            if not pairs:
                continue
            for sub_label, filt in [
                ("ALL", pairs),
                ("OLD_8", [p for p in pairs if p[0] in OLD_NAMES]),
                ("NEW_20", [p for p in pairs if p[0] in NEW_NAMES]),
                ("LR-MPKI>=2", [p for p in pairs if matrix[pref]["lru"][p[0]]["lr_mpki"] >= 2.0]),
            ]:
                if not filt:
                    continue
                ratios = [v["ipc"] / b["ipc"] for _, b, v in filt]
                deltas = [(r - 1.0) * 100.0 for r in ratios]
                gm_delta = (geomean(ratios) - 1.0) * 100.0
                acc_b = sum(b["tr_acc"] for _, b, _ in filt)
                hit_b = sum(b["tr_hit"] for _, b, _ in filt)
                acc_v = sum(v["tr_acc"] for _, _, v in filt)
                hit_v = sum(v["tr_hit"] for _, _, v in filt)
                tr_b = (hit_b / acc_b * 100.0) if acc_b else 0.0
                tr_v = (hit_v / acc_v * 100.0) if acc_v else 0.0
                worse_05 = sum(1 for d in deltas if d < -0.5)
                better_05 = sum(1 for d in deltas if d > 0.5)
                worse_01 = sum(1 for d in deltas if d < -0.1)
                better_01 = sum(1 for d in deltas if d > 0.1)
                sum_rows.append(
                    {
                        "prefetcher": pref,
                        "variant": var,
                        "subset": sub_label,
                        "n": len(filt),
                        "gm_delta_vs_ta_pct": gm_delta,
                        "min_delta_pct": min(deltas),
                        "max_delta_pct": max(deltas),
                        "ta_tr_hit_pct": tr_b,
                        "var_tr_hit_pct": tr_v,
                        "wtl_05pct": f"{better_05}/{len(filt)-better_05-worse_05}/{worse_05}",
                        "wtl_01pct": f"{better_01}/{len(filt)-better_01-worse_01}/{worse_01}",
                    }
                )
        print(f"\n=== LOO ABLATIONS: {pref} ===")
        for r in sum_rows:
            if r["prefetcher"] == pref and r["subset"] in ("ALL", "LR-MPKI>=2"):
                print(
                    f"  {r['variant']:13s} [{r['subset']:10s} n={r['n']:2d}] "
                    f"geomean={r['gm_delta_vs_ta_pct']:+.3f}% (min={r['min_delta_pct']:+.2f}%, max={r['max_delta_pct']:+.2f}%) "
                    f"TrHit={r['ta_tr_hit_pct']:.2f}%->{r['var_tr_hit_pct']:.2f}% W/T/L(0.5%)={r['wtl_05pct']}"
                )

    if loo_rows:
        with (OUT / "full_loo_per_trace.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(loo_rows[0].keys()))
            w.writeheader()
            w.writerows(loo_rows)
    if sum_rows:
        with (OUT / "full_loo_summary.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(sum_rows[0].keys()))
            w.writeheader()
            for r in sum_rows:
                w.writerow({k: (f"{v:.4f}" if isinstance(v, float) else v) for k, v in r.items()})


def main() -> int:
    ap = argparse.ArgumentParser(description="Analyze full 28x3x4 matrix and 28x2x5 LOO ablations")
    ap.add_argument("--allow-partial", action="store_true", help="Skip missing JSONs while cloud jobs run")
    args = ap.parse_args()
    matrix = analyze_matrix(args.allow_partial)
    analyze_loo(args.allow_partial, matrix)
    print(f"\n[wrote CSVs into {OUT}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
