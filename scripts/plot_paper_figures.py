#!/usr/bin/env python3
"""Generate clean, publication-grade vector PDF figures for the unified TA-MPPPB paper.

Outputs into paper/figures/:
  - fig1_arch.pdf        : Baseline MPPPB vs. TA-MPPPB four-channel architecture
  - fig2_repro_attr.pdf  : SPEC06 prefetcher inversion + single-factor attribution
  - fig3_matrix_3x28.pdf : Complete 28x3x4 dual-prefetcher matrix & PTW recovery
  - fig4_highlights.pdf  : Curated representative benchmarks across all 5 suites
  - fig5_mechanism.pdf   : Adaptive duel quadrant (wsel vs pfsel) & LR/WR trade-off
  - fig6_loo_ablation.pdf: Full 28-trace dual-prefetcher LOO + PTW duel ablation
"""

from __future__ import annotations

import csv
import json
import math
import pathlib
import sys
from typing import Dict, List

import matplotlib as mpl
import matplotlib.patches as patches
import matplotlib.pyplot as plt
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent
RES = ROOT / "results"
RAW = RES / "raw"
FIG_DIR = ROOT / "paper" / "figures"

mpl.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["DejaVu Sans", "Arial", "Helvetica"],
        "font.size": 8.5,
        "axes.titlesize": 9.5,
        "axes.titleweight": "bold",
        "axes.labelsize": 8.5,
        "xtick.labelsize": 7.8,
        "ytick.labelsize": 7.8,
        "legend.fontsize": 7.5,
        "figure.titlesize": 10.5,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    }
)

C_LRU = "#7f8c8d"
C_SHIP = "#3b82f6"
C_MPPPB = "#f59e0b"
C_TA = "#10b981"
C_BAD = "#ef4444"
C_DARK = "#1e293b"
C_MUTED = "#64748b"


def read_csv(path: pathlib.Path) -> List[Dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _box(ax, x, y, w, h, text, fc="#f8fafc", ec="#334155", lw=1.0, fs=7.5, bold=False, tc="#0f172a"):
    rect = patches.FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle="round,pad=0.012,rounding_size=0.015",
        facecolor=fc,
        edgecolor=ec,
        linewidth=lw,
    )
    ax.add_patch(rect)
    ax.text(
        x + w / 2.0,
        y + h / 2.0,
        text,
        ha="center",
        va="center",
        fontsize=fs,
        fontweight="bold" if bold else "normal",
        color=tc,
        linespacing=1.18,
    )


def _arrow(ax, x1, y1, x2, y2, color="#475569", lw=1.2, ls="-", rad=0.0):
    ax.annotate(
        "",
        xy=(x2, y2),
        xytext=(x1, y1),
        arrowprops=dict(
            arrowstyle="-|>",
            color=color,
            lw=lw,
            linestyle=ls,
            shrinkA=1,
            shrinkB=1,
            connectionstyle=f"arc3,rad={rad}",
        ),
    )


def fig1_architecture() -> None:
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.2, 4.1))
    for ax in (ax1, ax2):
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis("off")

    # Panel (a): Baseline MPPPB
    ax1.set_title("(a) Baseline MPPPB: Shared Funnel & ip=0 Aliasing", pad=6)
    _box(ax1, 0.02, 0.77, 0.23, 0.14, "LOAD / RFO\n(pc != 0)", "#dbeafe", "#2563eb", fs=7.3, bold=True)
    _box(ax1, 0.02, 0.56, 0.23, 0.14, "PREFETCH\n(ip = 0)", "#fee2e2", "#dc2626", fs=7.3)
    _box(ax1, 0.02, 0.35, 0.23, 0.14, "WRITEBACK\n(ip = 0)", "#ffedd5", "#ea580c", fs=7.3)
    _box(ax1, 0.02, 0.14, 0.23, 0.14, "TRANSLATION\n(PTW, ip = 0)", "#fef3c7", "#d97706", fs=7.3)

    _box(ax1, 0.34, 0.42, 0.28, 0.42, "Shared Perceptron +\npc_ring[32]\n\nBucket-0 Aliasing\n& Ring Flushing", "#fef2f2", "#b91c1c", lw=1.3, fs=7.4, bold=True)
    _box(ax1, 0.34, 0.13, 0.28, 0.22, "1/32 Sampler\n(18-way LRU)\nPolluted Updates", "#fff7ed", "#c2410c", lw=1.1, fs=7.2)

    _box(ax1, 0.70, 0.56, 0.27, 0.28, "True Bypass & plv_\n\nFalse PTW Bypass\nPrefetch Throttling", "#fef2f2", "#dc2626", lw=1.2, fs=7.3)
    _box(ax1, 0.70, 0.17, 0.27, 0.28, "15-bit Tree-PLRU\n\nHot Writes Evict\nDemand & PTW", "#f1f5f9", "#475569", lw=1.1, fs=7.3)

    for yy in (0.84, 0.63, 0.42, 0.21):
        _arrow(ax1, 0.25, yy, 0.34, 0.60 if yy > 0.5 else 0.50, "#b91c1c" if yy < 0.75 else "#2563eb")
    _arrow(ax1, 0.48, 0.42, 0.48, 0.35, "#c2410c")
    _arrow(ax1, 0.62, 0.66, 0.70, 0.70, "#dc2626")
    _arrow(ax1, 0.83, 0.56, 0.83, 0.45, "#475569")

    # Panel (b): TA-MPPPB
    ax2.set_title("(b) TA-MPPPB: 4-Channel Decoupling (+20b, 0 Extra SRAM)", pad=6)
    _box(ax2, 0.02, 0.77, 0.22, 0.14, "LOAD / RFO\n(pc != 0)", "#dbeafe", "#2563eb", fs=7.3, bold=True)
    _box(ax2, 0.02, 0.56, 0.22, 0.14, "TRANSLATION\n(PTW)", "#d1fae5", "#059669", fs=7.3, bold=True)
    _box(ax2, 0.02, 0.35, 0.22, 0.14, "WRITEBACK\n(L2 Evict)", "#fef3c7", "#d97706", fs=7.3, bold=True)
    _box(ax2, 0.02, 0.14, 0.22, 0.14, "PREFETCH\n(L1 / L2)", "#e0e7ff", "#4f46e5", fs=7.3, bold=True)

    _box(ax2, 0.30, 0.72, 0.31, 0.21, "Zero-PC Shielded Perceptron\nClean pc_ring + Sampler\nScore Bypass & plv_ Place", "#eff6ff", "#2563eb", lw=1.2, fs=7.0)
    _box(ax2, 0.30, 0.52, 0.31, 0.15, "PTW Guard: Zero Bypass\nPLRU=8 Insert, Hit->Promote", "#ecfdf5", "#059669", lw=1.2, fs=7.0)
    _box(ax2, 0.30, 0.31, 0.31, 0.17, "Dual-Mode Write Protocol\nNo-Pref: Preserve | Pref: Isolate\nwsel_ Duel {8, 15} (10b)", "#fffbeb", "#d97706", lw=1.2, fs=6.9)
    _box(ax2, 0.30, 0.10, 0.31, 0.17, "Prefetch Isolation\nZero Bypass, Sampler Off\npfsel_ Duel {8, 15} (10b)", "#eef2ff", "#4f46e5", lw=1.2, fs=6.9)

    _box(ax2, 0.72, 0.25, 0.26, 0.54, "15-bit Static MDPP\nTree-PLRU Array\n\n+ Demand Miss\nFeedback\n(wsel_, pfsel_)\n\nUnconditional\nkVecMdpp Hit Prom.", "#f0fdf4", "#15803d", lw=1.4, fs=7.2, bold=True)

    for src_y, dst_y, col in [(0.84, 0.82, "#2563eb"), (0.63, 0.60, "#059669"), (0.42, 0.40, "#d97706"), (0.21, 0.19, "#4f46e5")]:
        _arrow(ax2, 0.24, src_y, 0.30, dst_y, col)
    for src_y, dst_y, col in [(0.82, 0.70, "#2563eb"), (0.60, 0.58, "#059669"), (0.40, 0.44, "#d97706"), (0.19, 0.32, "#4f46e5")]:
        _arrow(ax2, 0.61, src_y, 0.72, dst_y, col)

    # Demand-miss feedback routed cleanly inside the open gap corridor (x=0.61..0.67)
    ax2.plot([0.61, 0.665, 0.665], [0.76, 0.76, 0.22], color="#2563eb", lw=1.0, ls="--")
    _arrow(ax2, 0.665, 0.44, 0.61, 0.44, "#2563eb", lw=1.0, ls="--")
    _arrow(ax2, 0.665, 0.22, 0.61, 0.22, "#2563eb", lw=1.0, ls="--")
    ax2.text(0.67, 0.04, "Dashed: LOAD/RFO miss supervision", fontsize=6.8, color="#2563eb", ha="center")

    fig.tight_layout(w_pad=1.6)
    fig.savefig(FIG_DIR / "fig1_arch.pdf", bbox_inches="tight")
    plt.close(fig)


def fig2_repro_attr() -> None:
    sum_rows = { (r["regime"], r["subset"]): r for r in read_csv(RES / "full_matrix_summary.csv") }

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.0, 3.85), gridspec_kw={"width_ratios": [1.0, 1.35]})

    # Panel (a): SPEC06 Inversion across 3 regimes
    regimes = ["nopref", "ip_stride", "spp_dev"]
    rlabels = ["No-Prefetch", "next_line +\nip_stride", "next_line +\nspp_dev"]
    x = np.arange(len(regimes))
    w = 0.25
    ship_v = [float(sum_rows[(rg, "OLD_8")]["ship_vs_lru_pct"]) for rg in regimes]
    mp_v = [float(sum_rows[(rg, "OLD_8")]["mpppb_vs_lru_pct"]) for rg in regimes]
    ta_v = [float(sum_rows[(rg, "OLD_8")]["ta_vs_lru_pct"]) for rg in regimes]

    b1 = ax1.bar(x - w, ship_v, w, label="SHiP-PC", color=C_SHIP, edgecolor="white")
    b2 = ax1.bar(x, mp_v, w, label="MPPPB", color=C_MPPPB, edgecolor="white")
    b3 = ax1.bar(x + w, ta_v, w, label="TA-MPPPB", color=C_TA, edgecolor="white")
    ax1.axhline(0, color="#334155", lw=0.8)
    for bars in (b1, b2, b3):
        for bar in bars:
            val = bar.get_height()
            va = "bottom" if val >= 0 else "top"
            off = 0.14 if val >= 0 else -0.18
            ax1.text(bar.get_x() + bar.get_width() / 2, val + off, f"{val:+.2f}%", ha="center", va=va, fontsize=6.7)
    ax1.set_xticks(x)
    ax1.set_xticklabels(rlabels)
    ax1.set_ylim(-3.2, 6.0)
    ax1.set_ylabel("Geomean IPC vs. LRU (%)")
    ax1.set_title("(a) SPEC CPU2006 (n=8): Prefetcher Inversion")
    ax1.legend(loc="upper right", frameon=False)
    ax1.grid(axis="y", linestyle=":", alpha=0.4)

    # Panel (b): Forward Causal Attribution under ip_stride (SPEC06 n=8)
    pt1_rows = read_csv(RES / "point1_attribution.csv")
    by_pol: Dict[str, Dict[str, float]] = {}
    for r in pt1_rows:
        by_pol.setdefault(r["policy"], {})[r["trace"]] = float(r["ipc"])
    lru_map = {}
    for p in sorted((RAW / "repro_3B" / "lru_pref").glob("*.json")):
        d = json.loads(p.read_text())[0]["roi"]["cores"][0]
        lru_map[p.stem] = d["instructions"] / d["cycles"]

    def gm_pt1(pol: str) -> float:
        return (math.exp(sum(math.log(by_pol[pol][t] / lru_map[t]) for t in lru_map) / len(lru_map)) - 1.0) * 100.0

    steps = [
        ("MPPPB", gm_pt1("mpppb_pref"), C_MPPPB),
        ("+Pref NoBp\n(Foil)", gm_pt1("p1_pref_nobp"), C_BAD),
        ("+dt2=256", gm_pt1("p1_dt256"), "#60a5fa"),
        ("+Pref Clean", gm_pt1("p1_pref_pc"), "#60a5fa"),
        ("+PTW Clean", gm_pt1("p1_trans_clean"), "#3b82f6"),
        ("+Write Iso", gm_pt1("p1_write_iso"), "#3b82f6"),
        ("+PTW MRU", gm_pt1("p1_trans_mru"), "#2563eb"),
        ("Static Comb", gm_pt1("p1_comb"), "#1d4ed8"),
        ("SHiP-PC", gm_pt1("ship_pref"), C_SHIP),
        ("TA-MPPPB", float(sum_rows[("ip_stride", "OLD_8")]["ta_vs_lru_pct"]), C_TA),
    ]
    sx = np.arange(len(steps))
    vals = [s[1] for s in steps]
    cols = [s[2] for s in steps]
    bars = ax2.bar(sx, vals, 0.66, color=cols, edgecolor="white")
    for bar, v in zip(bars, vals):
        ax2.text(bar.get_x() + bar.get_width() / 2, v + 0.08, f"{v:+.2f}%", ha="center", va="bottom", fontsize=6.6)
    ax2.set_xticks(sx)
    ax2.set_xticklabels([s[0] for s in steps], rotation=24, ha="right", fontsize=7.0)
    ax2.set_ylim(0, 4.0)
    ax2.set_ylabel("Geomean IPC vs. LRU (%)")
    ax2.set_title("(b) Single-Factor Attribution under ip_stride (SPEC06)")
    ax2.grid(axis="y", linestyle=":", alpha=0.4)

    fig.tight_layout(w_pad=1.8)
    fig.savefig(FIG_DIR / "fig2_repro_attr.pdf", bbox_inches="tight")
    plt.close(fig)


def fig3_matrix_3x28() -> None:
    sum_rows = { (r["regime"], r["subset"]): r for r in read_csv(RES / "full_matrix_summary.csv") }
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.2, 4.0))

    # Panel (a): 3 regimes x {ALL-28, LR-MPKI>=2} Geomean IPC
    cats = [
        ("nopref", "ALL", "No-Pref\n(All 28)"),
        ("nopref", "LR-MPKI>=2", "No-Pref\n(LR>=2, n=20)"),
        ("ip_stride", "ALL", "ip_stride\n(All 28)"),
        ("ip_stride", "LR-MPKI>=2", "ip_stride\n(LR>=2, n=15)"),
        ("spp_dev", "ALL", "spp_dev\n(All 28)"),
        ("spp_dev", "LR-MPKI>=2", "spp_dev\n(LR>=2, n=15)"),
    ]
    x = np.arange(len(cats))
    w = 0.25
    ship_v = [float(sum_rows[(rg, sub)]["ship_vs_lru_pct"]) for rg, sub, _ in cats]
    mp_v = [float(sum_rows[(rg, sub)]["mpppb_vs_lru_pct"]) for rg, sub, _ in cats]
    ta_v = [float(sum_rows[(rg, sub)]["ta_vs_lru_pct"]) for rg, sub, _ in cats]

    b1 = ax1.bar(x - w, ship_v, w, label="SHiP-PC", color=C_SHIP, edgecolor="white")
    b2 = ax1.bar(x, mp_v, w, label="MPPPB", color=C_MPPPB, edgecolor="white")
    b3 = ax1.bar(x + w, ta_v, w, label="TA-MPPPB", color=C_TA, edgecolor="white")
    ax1.axhline(0, color="#334155", lw=0.8)
    for bars in (b1, b2, b3):
        for bar in bars:
            v = bar.get_height()
            va = "bottom" if v >= 0 else "top"
            off = 0.22 if v >= 0 else -0.25
            ax1.text(bar.get_x() + bar.get_width() / 2, v + off, f"{v:+.1f}%", ha="center", va=va, fontsize=6.4)
    ax1.set_xticks(x)
    ax1.set_xticklabels([c[2] for c in cats], fontsize=7.2)
    ax1.set_ylim(-3.8, 12.8)
    ax1.set_ylabel("Geomean IPC vs. LRU (%)")
    ax1.set_title("(a) Complete 28x3x4 Matrix Performance")
    ax1.legend(loc="upper right", frameon=False, ncol=3)
    ax1.grid(axis="y", linestyle=":", alpha=0.4)

    # Panel (b): Translation (PTW) Hit Rate Recovery across all 3 regimes (All 28 + Old 8 + New 20)
    ptw_cats = [
        ("nopref", "ALL", "No-Pref\n(All 28)"),
        ("ip_stride", "ALL", "ip_stride\n(All 28)"),
        ("ip_stride", "NEW_20", "ip_stride\n(New 20)"),
        ("spp_dev", "ALL", "spp_dev\n(All 28)"),
        ("spp_dev", "NEW_20", "spp_dev\n(New 20)"),
    ]
    px = np.arange(len(ptw_cats))
    w2 = 0.19
    l_tr = [float(sum_rows[(rg, sub)]["tr_hit_lru_pct"]) for rg, sub, _ in ptw_cats]
    s_tr = [float(sum_rows[(rg, sub)]["tr_hit_ship_pct"]) for rg, sub, _ in ptw_cats]
    m_tr = [float(sum_rows[(rg, sub)]["tr_hit_mpppb_pct"]) for rg, sub, _ in ptw_cats]
    t_tr = [float(sum_rows[(rg, sub)]["tr_hit_ta_pct"]) for rg, sub, _ in ptw_cats]

    for off_i, (arr, lbl, col) in enumerate([(l_tr, "LRU", C_LRU), (s_tr, "SHiP-PC", C_SHIP), (m_tr, "MPPPB", C_MPPPB), (t_tr, "TA-MPPPB", C_TA)]):
        bars = ax2.bar(px + (off_i - 1.5) * w2, arr, w2, label=lbl, color=col, edgecolor="white")
        if lbl in ("MPPPB", "TA-MPPPB"):
            for bar, v in zip(bars, arr):
                ax2.text(bar.get_x() + bar.get_width() / 2, v + 1.0, f"{v:.1f}", ha="center", va="bottom", fontsize=6.2)

    ax2.set_xticks(px)
    ax2.set_xticklabels([c[2] for c in ptw_cats], fontsize=7.4)
    ax2.set_ylim(0, 86)
    ax2.set_ylabel("LLC PTW Translation Hit Rate (%)")
    ax2.set_title("(b) Page-Table Walk (TRANSLATION) Hit Rate")
    ax2.legend(loc="upper left", frameon=False, ncol=2)
    ax2.grid(axis="y", linestyle=":", alpha=0.4)

    fig.tight_layout(w_pad=1.6)
    fig.savefig(FIG_DIR / "fig3_matrix_3x28.pdf", bbox_inches="tight")
    plt.close(fig)


def fig4_highlights() -> None:
    rows = read_csv(RES / "full_matrix_per_trace.csv")
    by_key = {(r["regime"], r["trace"]): r for r in rows}

    # Curated non-cherry-picked representative active benchmarks across all 5 suites
    picks = [
        ("429.mcf-22B", "429.mcf"),
        ("450.soplex-92B", "450.soplex"),
        ("470.lbm-1274B", "470.lbm"),
        ("483.xalancbmk-127B", "483.xalanc"),
        ("605.mcf_s-1554B", "605.mcf_s*"),
        ("607.cactuBSSN_s-2421B", "607.cactu"),
        ("619.lbm_s-2676B", "619.lbm_s"),
        ("620.omnetpp_s-874B", "620.omnet"),
        ("623.xalancbmk_s-10B", "623.xalanc"),
        ("649.fotonik3d_s-1176B", "649.foto"),
        ("bfs.twitter-10B", "bfs.twit"),
        ("sssp.web-1185B", "sssp.web"),
        ("cvp1_compute_int_38", "cvp1_int"),
        ("qc_srv115_ap", "qc_srv115"),
    ]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11.4, 6.2), sharex=True)
    x = np.arange(len(picks))
    w = 0.25

    for ax, reg, title in [
        (ax1, "ip_stride", "(a) Highlight Workloads under next_line + ip_stride (IPC vs. LRU; *605.mcf_s TA=+105.8%, SHiP=+59.2%)"),
        (ax2, "spp_dev", "(b) Highlight Workloads under next_line + spp_dev (IPC vs. LRU)"),
    ]:
        sh = [float(by_key[(reg, tr)]["ship_vs_lru_pct"]) for tr, _ in picks]
        mp = [float(by_key[(reg, tr)]["mpppb_vs_lru_pct"]) for tr, _ in picks]
        ta = [float(by_key[(reg, tr)]["ta_vs_lru_pct"]) for tr, _ in picks]

        cap = 45.0 if reg == "ip_stride" else 28.0
        sh_c = [max(-20, min(cap, v)) for v in sh]
        mp_c = [max(-20, min(cap, v)) for v in mp]
        ta_c = [max(-20, min(cap, v)) for v in ta]

        b1 = ax.bar(x - w, sh_c, w, label="SHiP-PC", color=C_SHIP, edgecolor="white")
        b2 = ax.bar(x, mp_c, w, label="MPPPB", color=C_MPPPB, edgecolor="white")
        b3 = ax.bar(x + w, ta_c, w, label="TA-MPPPB", color=C_TA, edgecolor="white")
        ax.axhline(0, color="#334155", lw=0.8)

        for bars, raw_arr, bname in [(b1, sh, "SH"), (b2, mp, "MP"), (b3, ta, "TA")]:
            for bar, rv in zip(bars, raw_arr):
                if abs(rv) >= 5.0 or rv > cap:
                    y_pos = bar.get_height() + (0.8 if rv >= 0 else -0.9)
                    va = "bottom" if rv >= 0 else "top"
                    lbl = f"{rv:+.1f}%"
                    ax.text(
                        bar.get_x() + bar.get_width() / 2,
                        y_pos,
                        lbl,
                        ha="center",
                        va=va,
                        rotation=90,
                        fontsize=6.2,
                    )

        ax.set_ylim(-32.5 if reg == "ip_stride" else -18.5, cap + 16.5)
        ax.set_ylabel("IPC vs. LRU (%)")
        ax.set_title(title)
        ax.legend(loc="upper right", frameon=False, ncol=3)
        ax.grid(axis="y", linestyle=":", alpha=0.4)

    ax2.set_xticks(x)
    ax2.set_xticklabels([lbl for _, lbl in picks], rotation=22, ha="right", fontsize=7.6)
    fig.tight_layout(h_pad=1.2)
    fig.savefig(FIG_DIR / "fig4_highlights.pdf", bbox_inches="tight")
    plt.close(fig)


def fig5_mechanism() -> None:
    # Load all wsel_/pfsel_ probe stats from g1_old_spp, g2_new_pref, g3_new_spp
    pts_pref = read_csv(RES / "g2_new_pref_comparison.csv")
    pts_spp = read_csv(RES / "g3_new_spp_comparison.csv")
    pts_g1 = read_csv(RES / "g1_old_spp_comparison.csv")

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.2, 4.1))

    # Panel (a): Adaptive duel scatter (wsel vs pfsel)
    def extract_pts(rows):
        xs, ys, lbs = [], [], []
        for r in rows:
            if not r.get("ta_wsel") or float(r["lru_all_mpki"]) < 5.0:
                continue
            xs.append(int(r["ta_wsel"]))
            ys.append(int(r["ta_pfsel"]))
            lbs.append(r["trace"].split("-")[0])
        return xs, ys, lbs

    x2, y2, l2 = extract_pts(pts_pref)
    x3, y3, l3 = extract_pts(pts_spp + pts_g1)
    ax1.axhline(0, color="#64748b", lw=0.8, ls="--")
    ax1.axvline(0, color="#64748b", lw=0.8, ls="--")
    ax1.scatter(x2, y2, c=C_SHIP, s=34, alpha=0.85, label="ip_stride (New-20 active)", zorder=3)
    ax1.scatter(x3, y3, c=C_TA, marker="^", s=40, alpha=0.85, label="spp_dev (All active)", zorder=4)

    # Annotate key illustrative regimes cleanly without collision
    ann = {
        ("605.mcf_s", True): (-470, -370, "605.mcf_s"),
        ("607.cactuBSSN_s", True): (95, 445, "607.cactu"),
        ("620.omnetpp_s", False): (200, -340, "620.omnet (spp)"),
        ("sssp.web", True): (120, -455, "sssp.web"),
        ("470.lbm", False): (-310, 60, "470.lbm (spp)"),
        ("623.xalancbmk_s", True): (-340, -250, "623.xalanc"),
    }
    for rows, is_pref in [(pts_pref, True), (pts_spp + pts_g1, False)]:
        for r in rows:
            nm = r["trace"].split("-")[0]
            if (nm, is_pref) in ann and r.get("ta_wsel"):
                tx, ty, tag = ann[(nm, is_pref)]
                ax1.annotate(
                    tag,
                    xy=(int(r["ta_wsel"]), int(r["ta_pfsel"])),
                    xytext=(tx, ty),
                    fontsize=6.7,
                    arrowprops=dict(arrowstyle="-", color="#94a3b8", lw=0.6),
                )

    ax1.text(-565, 565, "Evict WB / Keep Pref", fontsize=6.8, color=C_MUTED, va="top")
    ax1.text(565, 565, "Keep Both (PLRU=8)", fontsize=6.8, color=C_MUTED, ha="right", va="top")
    ax1.text(-565, -590, "Evict Both (PLRU=15)", fontsize=6.8, color=C_MUTED, va="bottom")
    ax1.text(565, -590, "Keep WB / Evict Pref", fontsize=6.8, color=C_MUTED, ha="right", va="bottom")
    ax1.set_xlim(-590, 590)
    ax1.set_ylim(-610, 600)
    ax1.set_xlabel("Write-Back Duel Counter (wsel_)")
    ax1.set_ylabel("Prefetch Duel Counter (pfsel_)")
    ax1.set_title("(a) Orthogonal Set-Dueling Adaptation")
    ax1.legend(loc="center left", bbox_to_anchor=(0.01, 0.72), frameon=True, framealpha=0.92)
    ax1.grid(linestyle=":", alpha=0.35)

    # Panel (b): LR-MPKI reduction vs WR-MPKI shift under spp_dev
    mrows = {(r["regime"], r["trace"]): r for r in read_csv(RES / "full_matrix_per_trace.csv")}
    t_list = [
        ("429.mcf-22B", "429.mcf"),
        ("470.lbm-1274B", "470.lbm"),
        ("483.xalancbmk-127B", "483.xalanc"),
        ("605.mcf_s-1554B", "605.mcf_s"),
        ("619.lbm_s-2676B", "619.lbm_s"),
        ("623.xalancbmk_s-10B", "623.xalanc_s"),
        ("sssp.web-1185B", "sssp.web"),
    ]
    bx = np.arange(len(t_list))
    bw = 0.20
    dlr = [float(mrows[("spp_dev", t)]["ta_lr_mpki"]) - float(mrows[("spp_dev", t)]["lru_lr_mpki"]) for t, _ in t_list]
    dwr = [float(mrows[("spp_dev", t)]["ta_wr_mpki"]) - float(mrows[("spp_dev", t)]["lru_wr_mpki"]) for t, _ in t_list]
    dipc = [float(mrows[("spp_dev", t)]["ta_vs_lru_pct"]) for t, _ in t_list]

    ax2.bar(bx - bw, dlr, bw, label="Delta LR-MPKI (Blocking)", color=C_TA)
    ax2.bar(bx, dwr, bw, label="Delta WR-MPKI (Non-Blocking)", color=C_MPPPB)
    ax2.bar(bx + bw, dipc, bw, label="IPC Gain vs. LRU (%)", color=C_SHIP)
    ax2.axhline(0, color="#334155", lw=0.8)
    for idx_i, (lr_v, ipc_v) in enumerate(zip(dlr, dipc)):
        if abs(lr_v) >= 0.3:
            ax2.text(
                idx_i - bw,
                lr_v - 0.8 if lr_v < 0 else lr_v + 0.6,
                f"{lr_v:+.1f}",
                ha="center",
                va="top" if lr_v < 0 else "bottom",
                fontsize=6.0,
            )
        ax2.text(idx_i + bw, ipc_v + 0.6, f"{ipc_v:+.1f}%", ha="center", va="bottom", fontsize=6.0)

    ax2.set_xticks(bx)
    ax2.set_xticklabels([lbl for _, lbl in t_list], rotation=20, ha="right", fontsize=7.3)
    ax2.set_ylim(-54, 30)
    ax2.set_ylabel("Delta MPKI / IPC Change (%)")
    ax2.set_title("(b) Blocking Demand vs. Writeback Trade-Off (spp_dev)")
    ax2.legend(loc="lower right", frameon=True, framealpha=0.9)
    ax2.grid(axis="y", linestyle=":", alpha=0.4)

    fig.tight_layout(w_pad=1.6)
    fig.savefig(FIG_DIR / "fig5_mechanism.pdf", bbox_inches="tight")
    plt.close(fig)


def fig6_loo_ablation() -> None:
    loo_rows = {(r["prefetcher"], r["variant"], r["subset"]): r for r in read_csv(RES / "full_loo_summary.csv")}

    variants = [
        ("no_zeropc", "w/o Zero-PC\nShield"),
        ("no_ptw_prot", "w/o PTW\nProtection"),
        ("no_write_arb", "w/o Write\nArbitration"),
        ("no_pref_arb", "w/o Prefetch\nArbitration"),
        ("tduel", "+PTW\nSet-Duel"),
    ]
    x = np.arange(len(variants))
    w = 0.20

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.2, 4.0))

    # Panel (a): LOO Delta IPC relative to Full TA-MPPPB across ALL-28 & LR>=2
    s_ip_all = [float(loo_rows[("ip_stride", v, "ALL")]["gm_delta_vs_ta_pct"]) for v, _ in variants]
    s_ip_act = [float(loo_rows[("ip_stride", v, "LR-MPKI>=2")]["gm_delta_vs_ta_pct"]) for v, _ in variants]
    s_sp_all = [float(loo_rows[("spp_dev", v, "ALL")]["gm_delta_vs_ta_pct"]) for v, _ in variants]
    s_sp_act = [float(loo_rows[("spp_dev", v, "LR-MPKI>=2")]["gm_delta_vs_ta_pct"]) for v, _ in variants]

    series = [
        (s_ip_all, "ip_stride (All 28)", "#60a5fa"),
        (s_ip_act, "ip_stride (LR>=2)", "#2563eb"),
        (s_sp_all, "spp_dev (All 28)", "#34d399"),
        (s_sp_act, "spp_dev (LR>=2)", "#059669"),
    ]
    for i, (arr, lbl, col) in enumerate(series):
        bars = ax1.bar(x + (i - 1.5) * w, arr, w, label=lbl, color=col, edgecolor="white")
        for bar, val in zip(bars, arr):
            if abs(val) >= 0.25:
                va = "bottom" if val >= 0 else "top"
                off = 0.08 if val >= 0 else -0.09
                ax1.text(
                    bar.get_x() + bar.get_width() / 2,
                    val + off,
                    f"{val:+.2f}",
                    ha="center",
                    va=va,
                    rotation=90,
                    fontsize=6.0,
                )

    ax1.axhline(0, color="#334155", lw=0.9)
    ax1.set_xticks(x)
    ax1.set_xticklabels([lbl for _, lbl in variants], fontsize=7.5)
    ax1.set_ylim(-4.95, 1.15)
    ax1.set_ylabel("Geomean IPC Delta vs. Full TA-MPPPB (%)")
    ax1.set_title("(a) Full 28-Trace Dual-Prefetcher LOO & PTW-Duel Ablation")
    ax1.legend(loc="lower left", frameon=False, ncol=2)
    ax1.grid(axis="y", linestyle=":", alpha=0.4)

    # Panel (b): PTW Translation Hit Rate across Full TA-MPPPB + 5 Ablation Variants
    ptw_vars = [("FULL", "Full\nTA-MPPPB")] + variants
    px = np.arange(len(ptw_vars))
    w2 = 0.34
    ip_tr = [float(loo_rows[("ip_stride", "no_ptw_prot", "ALL")]["ta_tr_hit_pct"])] + [
        float(loo_rows[("ip_stride", v, "ALL")]["var_tr_hit_pct"]) for v, _ in variants
    ]
    sp_tr = [float(loo_rows[("spp_dev", "no_ptw_prot", "ALL")]["ta_tr_hit_pct"])] + [
        float(loo_rows[("spp_dev", v, "ALL")]["var_tr_hit_pct"]) for v, _ in variants
    ]
    b_ip = ax2.bar(px - w2 / 2, ip_tr, w2, label="ip_stride (All 28)", color=C_SHIP, edgecolor="white")
    b_sp = ax2.bar(px + w2 / 2, sp_tr, w2, label="spp_dev (All 28)", color=C_TA, edgecolor="white")
    for bars in (b_ip, b_sp):
        for bar in bars:
            v = bar.get_height()
            ax2.text(bar.get_x() + bar.get_width() / 2, v + 1.0, f"{v:.1f}%", ha="center", va="bottom", fontsize=6.3)

    ax2.set_xticks(px)
    ax2.set_xticklabels([lbl for _, lbl in ptw_vars], fontsize=7.2)
    ax2.set_ylim(0, 82)
    ax2.set_ylabel("Aggregate PTW Hit Rate (%)")
    ax2.set_title("(b) PTW Hit Rate Preservation vs. Collapse")
    ax2.legend(loc="upper right", frameon=False)
    ax2.grid(axis="y", linestyle=":", alpha=0.4)

    fig.tight_layout(w_pad=1.6)
    fig.savefig(FIG_DIR / "fig6_loo_ablation.pdf", bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig1_architecture()
    fig2_repro_attr()
    fig3_matrix_3x28()
    fig4_highlights()
    fig5_mechanism()
    fig6_loo_ablation()
    for p in sorted(FIG_DIR.glob("*.pdf")):
        print(f"[wrote] {p.relative_to(ROOT)} ({p.stat().st_size} B)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
