#!/usr/bin/env python3
"""Recreate the quantitative paper panels (fig2-fig6) with the CjC-style backend.

All numbers are recomputed from results/*.csv and results/raw/*; nothing is typed in.
Run: python scripts/paper_figs/plot_figs.py
"""
from __future__ import annotations

import csv
import json
import pathlib
import sys

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from matplotlib_backend import (  # noqa: E402
    C_AMB,
    C_IND,
    C_LRU,
    C_MP,
    C_MUTE,
    C_SHIP,
    C_TA,
    GRID,
    INK,
    INK2,
    PAPER,
    FIG_DIR,
    gm,
    hairline_frame,
    pct,
    save,
    value_label,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]
RES = ROOT / "results"
RAW = RES / "raw"


def load_csv(name, key_fields):
    with open(RES / name, newline="", encoding="utf-8") as f:
        out = {}
        for r in csv.DictReader(f):
            out.setdefault(tuple(r[k] for k in key_fields), r)
        return out


def ipc_by_policy(name):
    with open(RES / name, newline="", encoding="utf-8") as f:
        d = {}
        for r in csv.DictReader(f):
            d.setdefault(r["policy"], {})[r["trace"]] = float(r["ipc"])
        return d


# ----------------------------------------------------------------------------
# Fig 2  reproduction alignment + single-variable attribution
# ----------------------------------------------------------------------------
def fig2():
    by_np = ipc_by_policy("ta_mpppb_v3_nopref_comparison.csv")
    by_p = ipc_by_policy("ta_mpppb_v3_pref_comparison.csv")
    by_pt = ipc_by_policy("point1_attribution.csv")
    by_m1 = ipc_by_policy("matrix1_results.csv")
    traces = sorted(by_np["lru"])

    def rel(by, pol, ref):
        return pct([by[pol][t] for t in traces], [by[ref][t] for t in traces])

    ship_np = rel(by_np, "ship", "lru")
    steps_np = [
        ("SRRIP 底座", pct([by_m1["mpppb"][t] for t in traces], [by_m1["lru"][t] for t in traces]), C_MUTE),
        ("SHiP-PC", ship_np, C_SHIP),
        ("MPPPB author1", rel(by_np, "author1", "lru"), C_MP),
        ("TA-v2 ta_nopref", rel(by_np, "ta_nopref", "lru"), C_AMB),
        ("TA-v2 ta_c4", rel(by_np, "ta_c4", "lru"), C_AMB),
        ("TA-v3 ta_mpppb_np", rel(by_np, "ta_mpppb_np", "lru"), C_TA),
    ]

    lru_p = by_p["lru_pref"]
    ship_p = pct([by_p["ship_pref"][t] for t in traces], [lru_p[t] for t in traces])
    attr = [
        ("MPPPB author2", pct([by_pt["mpppb_pref"][t] for t in traces], [lru_p[t] for t in traces])),
        ("+ 放宽 dt2 → 256", pct([by_pt["p1_dt256"][t] for t in traces], [lru_p[t] for t in traces])),
        ("+ 零 PC 预取解耦", pct([by_pt["p1_pref_pc"][t] for t in traces], [lru_p[t] for t in traces])),
        ("+ 页表清理", pct([by_pt["p1_trans_clean"][t] for t in traces], [lru_p[t] for t in traces])),
        ("+ 写回隔离", pct([by_pt["p1_write_iso"][t] for t in traces], [lru_p[t] for t in traces])),
        ("+ 页表 MRU 保护", pct([by_pt["p1_trans_mru"][t] for t in traces], [lru_p[t] for t in traces])),
        ("+ 静态组合 (v1)", pct([by_pt["p1_comb"][t] for t in traces], [lru_p[t] for t in traces])),
        ("TA-v2 ta_pref", rel(by_p, "ta_pref", "lru_pref")),
        ("TA-v3 ta_mpppb", rel(by_p, "ta_mpppb", "lru_pref")),
    ]

    fig, (ax1, ax2) = plt.subplots(
        1, 2, figsize=(7.05, 2.55), gridspec_kw={"width_ratios": [1.0, 1.18], "wspace": 0.42}
    )

    # (a) ladder
    y = np.arange(len(steps_np))[::-1]
    vals = [v for _, v, _ in steps_np]
    cols = [c for _, _, c in steps_np]
    ax1.axvline(ship_np, color=C_SHIP, lw=0.8, ls=(0, (4, 2)), zorder=1)
    ax1.barh(y, vals, height=0.62, color=cols, edgecolor=PAPER, linewidth=0.8, zorder=3)
    for yi, v, (name, _, c) in zip(y, vals, steps_np):
        bold = c == C_TA
        ax1.text(v + 0.07, yi, f"{v:+.2f}%", va="center", ha="left", fontsize=6.6,
                 fontweight="bold" if bold else "normal", color=INK)
    ax1.set_yticks(y)
    ax1.set_yticklabels([s[0] for s in steps_np], fontsize=6.8)
    ax1.set_xlim(0, 5.35)
    ax1.set_xlabel("几何平均 IPC 增益 vs. LRU (%)")
    ax1.set_title("(a) 无预取：复现对齐与改进演进", loc="left", pad=6)
    ax1.text(ship_np + 0.04, -0.62, f"SHiP-PC {ship_np:+.2f}%", fontsize=6.0, color=C_SHIP, ha="left", va="top")
    ax1.set_ylim(-0.85, len(steps_np) - 0.35)
    hairline_frame(ax1, "x")

    # (b) waterfall attribution
    labels = [a[0] for a in attr]
    vals_b = [a[1] for a in attr]
    yb = np.arange(len(attr))[::-1]
    ax2.axvline(ship_p, color=C_SHIP, lw=0.8, ls=(0, (4, 2)), zorder=1)
    for i, (yi, v, lab) in enumerate(zip(yb, vals_b, labels)):
        col = C_TA if lab.startswith("TA-v3") else C_AMB if lab.startswith("TA-v2") else C_IND if "静态组合" in lab else C_LRU
        if i == 0:
            col = C_MP
        ax2.plot([0, v], [yi, yi], color=col, lw=1.25, solid_capstyle="butt", zorder=2, alpha=0.5)
        ax2.scatter([v], [yi], s=16, color=col, edgecolors=PAPER, linewidths=0.7, zorder=4)
        ax2.text(v + 0.05, yi, f"{v:+.2f}%", va="center", ha="left", fontsize=6.5,
                 fontweight="bold" if lab.startswith("TA-v3") else "normal", color=INK)
    ax2.set_yticks(yb)
    ax2.set_yticklabels(labels, fontsize=6.8)
    ax2.set_xlim(1.2, 3.95)
    ax2.set_xlabel("几何平均 IPC 增益 vs. LRU_pref (%)")
    ax2.set_title("(b) 开预取：单变量因果归因（ip_stride）", loc="left", pad=6)
    ax2.text(ship_p + 0.02, -0.62, f"SHiP_pref {ship_p:+.2f}%", fontsize=6.0, color=C_SHIP, ha="left", va="top")
    ax2.set_ylim(-0.85, len(attr) - 0.35)
    hairline_frame(ax2, "x")

    save(fig, "fig2_repro_attr")
    return dict(ship_np=ship_np, ship_p=ship_p, ta_np=vals[-1], ta_p=vals_b[-1])


# ----------------------------------------------------------------------------
# Fig 3  2x2 generalisation matrix
# ----------------------------------------------------------------------------
def fig3():
    rows = {}
    with open(RES / "generalization_summary.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["subset"] == "ALL":
                rows[r["group"]] = r
    groups = ["g0_old_pref", "g1_old_spp", "g2_new_pref", "g3_new_spp"]
    tick = ["G0\nSPEC06 · ip_stride", "G1\nSPEC06 · spp_dev", "G2\n新 20 条 · ip_stride", "G3\n新 20 条 · spp_dev"]
    x = np.arange(len(groups))

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.05, 2.6), gridspec_kw={"wspace": 0.3})

    w = 0.26
    series = [
        ("MPPPB", "mpppb_vs_lru_pct", C_MP, -w),
        ("SHiP-PC", "ship_vs_lru_pct", C_SHIP, 0.0),
        ("TA-MPPPB v3", "ta_vs_lru_pct", C_TA, w),
    ]
    ax1.axhline(0, color=INK2, lw=0.6, zorder=1)
    for name, key, col, off in series:
        vals = [float(rows[g][key]) for g in groups]
        ax1.bar(x + off, vals, width=w * 0.94, color=col, edgecolor=PAPER, linewidth=0.7, zorder=3, label=name)
        for xi, v in zip(x + off, vals):
            value_label(ax1, f"{v:+.1f}", xi, v + (0.16 if v >= 0 else -0.16), fs=5.9,
                        va="bottom" if v >= 0 else "top", bold=name.startswith("TA"))
    ax1.set_xticks(x)
    ax1.set_xticklabels(tick, fontsize=6.4)
    ax1.set_ylim(-3.2, 8.4)
    ax1.set_ylabel("几何平均 IPC 增益 vs. LRU (%)")
    ax1.set_title("(a) 2×2 矩阵整体性能", loc="left", pad=6)
    ax1.legend(loc="upper left", frameon=False, ncol=3, handlelength=1.1, columnspacing=0.9, borderaxespad=0.2)
    hairline_frame(ax1, "y")

    w2 = 0.19
    tr = [
        ("LRU", "tr_hit_rate_lru_pct", C_LRU, -1.5 * w2, False),
        ("SHiP-PC", "tr_hit_rate_ship_pct", C_SHIP, -0.5 * w2, False),
        ("MPPPB", "tr_hit_rate_mpppb_pct", C_MP, 0.5 * w2, False),
        ("TA-MPPPB v3", "tr_hit_rate_ta_pct", C_TA, 1.5 * w2, True),
    ]
    for name, key, col, off, emph in tr:
        vals = [float(rows[g][key]) for g in groups]
        ax2.bar(x + off, vals, width=w2 * 0.92, color=col, edgecolor=PAPER, linewidth=0.6, zorder=3, label=name)
        for xi, v in zip(x + off, vals):
            value_label(ax2, f"{v:.0f}", xi, v + 1.4, fs=5.6, bold=emph)
    ax2.set_xticks(x)
    ax2.set_xticklabels(tick, fontsize=6.4)
    ax2.set_ylim(0, 88)
    ax2.set_ylabel("PTW TRANSLATION 命中率 (%)")
    ax2.set_title("(b) 页表游走命中率恢复", loc="left", pad=6)
    ax2.legend(loc="upper left", frameon=False, ncol=4, handlelength=1.1, columnspacing=0.8, borderaxespad=0.2)
    hairline_frame(ax2, "y")

    save(fig, "fig3_matrix_2x2")
    return {g: (float(rows[g]["mpppb_vs_lru_pct"]), float(rows[g]["ta_vs_lru_pct"])) for g in groups}


# ----------------------------------------------------------------------------
# Fig 4  per-trace zero-shot gains on 20 unseen workloads
# ----------------------------------------------------------------------------
FIG4_ORDER = [
    ("DPC-3 6xx", [
        "605.mcf_s-1554B", "623.xalancbmk_s-10B", "607.cactuBSSN_s-2421B", "620.omnetpp_s-874B",
        "619.lbm_s-2676B", "657.xz_s-2302B", "654.roms_s-1390B", "600.perlbench_s-210B",
        "602.gcc_s-734B", "649.fotonik3d_s-1176B"]),
    ("GAP / XS", ["bfs.twitter-10B", "pr.web-16B", "sssp.web-1185B", "xs.XL64unionized-66B"]),
    ("CVP-1", ["cvp1_compute_int_38", "cvp1_compute_fp_8", "cvp1_srv_40"]),
    ("Qualcomm", ["qc_srv0_ap", "qc_srv106_ap", "qc_srv115_ap"]),
]


def short_name(t):
    keep = {"605.mcf_s", "623.xalancbmk_s", "607.cactuBSSN_s", "619.lbm_s", "657.xz_s",
            "654.roms_s", "600.perlbench_s", "602.gcc_s", "649.fotonik3d_s"}
    base = t.split("-")[0]
    return base if base in keep else base


def fig4():
    def comp(name):
        with open(RES / name, newline="", encoding="utf-8") as f:
            return {r["trace"]: r for r in csv.DictReader(f)}

    g2, g3 = comp("g2_new_pref_comparison.csv"), comp("g3_new_spp_comparison.csv")
    # top-down: last suite first so DPC-3 sits on top
    order = [(suite, t) for suite, ts in FIG4_ORDER for t in ts]
    order = list(reversed(order))
    y = np.arange(len(order))
    cap = 26.0

    fig, axes = plt.subplots(1, 2, figsize=(7.05, 4.35), sharey=True, gridspec_kw={"wspace": 0.08})
    h = 0.36
    for ax, data, title in [
        (axes[0], g2, "(a) G2：新负载 + ip_stride"),
        (axes[1], g3, "(b) G3：新负载 + spp_dev"),
    ]:
        vs_mp = [float(data[t]["ta_vs_mpppb_pct"]) for _, t in order]
        vs_sh = [float(data[t]["ta_vs_ship_pct"]) for _, t in order]
        ax.axvline(0, color=INK2, lw=0.6, zorder=4)
        for yi, v, col, yy in zip(y, vs_mp, [C_TA] * len(y), y + h / 2):
            cv = min(max(v, -5.0), cap)
            ax.barh(yy, cv, height=h * 0.92, color=col, edgecolor=PAPER, linewidth=0.5, zorder=3)
            if v > cap - 1.5:
                ax.text(cap - 0.4, yy, f"{v:+.1f} ▸", va="center", ha="right", fontsize=5.4,
                        color=PAPER, fontweight="bold", zorder=6)
            elif abs(v) >= 1.2:
                ax.text(v + (0.4 if v >= 0 else -0.4), yy, f"{v:+.1f}", va="center",
                        ha="left" if v >= 0 else "right", fontsize=5.3, color=C_TA, zorder=6)
        for yi, v, yy in zip(y, vs_sh, y - h / 2):
            cv = min(max(v, -5.0), cap)
            ax.barh(yy, cv, height=h * 0.92, color=C_AMB, edgecolor=PAPER, linewidth=0.5, zorder=3)
            if v > cap - 1.5:
                ax.text(cap - 0.4, yy, f"{v:+.1f} ▸", va="center", ha="right", fontsize=5.4,
                        color=PAPER, fontweight="bold", zorder=6)
            elif abs(v) >= 1.2:
                ax.text(v + (0.4 if v >= 0 else -0.4), yy, f"{v:+.1f}", va="center",
                        ha="left" if v >= 0 else "right", fontsize=5.3, color="#8A5A1B", zorder=6)
        # suite separators
        acc = 0
        for _, ts in FIG4_ORDER[:-1]:
            acc += len(ts)
            ax.axhline(acc - 0.5, color=GRID, lw=0.7, zorder=1)
        ax.set_xlim(-4.0, cap + 4.2)
        ax.set_xlabel("TA-MPPPB v3 IPC 增益 (%)")
        ax.set_title(title, loc="left", pad=6)
        hairline_frame(ax, "x")

    axes[0].set_yticks(y)
    axes[0].set_yticklabels([short_name(t) for _, t in order], fontsize=6.3)
    axes[0].set_ylim(-0.6, len(order) - 0.4)
    handles = [Patch(color=C_TA, label="vs. MPPPB (author2)"), Patch(color=C_AMB, label="vs. SHiP-PC")]
    axes[1].legend(handles=handles, loc="lower right", frameon=False, handlelength=1.0, borderaxespad=0.3)

    acc = 0
    for suite, ts in FIG4_ORDER:
        mid = acc + len(ts) / 2 - 0.5
        axes[1].text(cap + 3.9, mid, suite, rotation=270, va="center", ha="center",
                     fontsize=5.8, color=INK2, style="italic")
        acc += len(ts)
    save(fig, "fig4_pertrace")
    return dict(n=len(order))


# ----------------------------------------------------------------------------
# Fig 5  duel counters & blocking/non-blocking MPKI decoupling
# ----------------------------------------------------------------------------
def fig5():
    pts = {}
    for g, name in [("G2", "g2_new_pref_comparison.csv"), ("G3", "g3_new_spp_comparison.csv")]:
        rows = []
        with open(RES / name, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if float(r["lru_all_mpki"]) >= 5.0:
                    rows.append((r["trace"].split("-")[0], int(r["ta_wsel"]), int(r["ta_pfsel"]),
                                 float(r["ta_vs_mpppb_pct"])))
        pts[g] = rows

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.05, 2.75),
                                   gridspec_kw={"width_ratios": [1.0, 1.12], "wspace": 0.33})

    # quadrants
    ax1.fill_between([0, 560], 0, 560, color=C_TA, alpha=0.05, zorder=0)
    ax1.fill_between([-560, 0], 0, 560, color=C_AMB, alpha=0.05, zorder=0)
    ax1.fill_between([-560, 0], -560, 0, color=C_MP, alpha=0.055, zorder=0)
    ax1.fill_between([0, 560], -560, 0, color=C_SHIP, alpha=0.05, zorder=0)
    ax1.axhline(0, color=INK2, lw=0.6, zorder=1)
    ax1.axvline(0, color=INK2, lw=0.6, zorder=1)
    ax1.scatter([p[1] for p in pts["G2"]], [p[2] for p in pts["G2"]], s=22, c=C_TA, marker="o",
                edgecolors=PAPER, linewidths=0.6, label="G2 (ip_stride)", zorder=4)
    ax1.scatter([p[1] for p in pts["G3"]], [p[2] for p in pts["G3"]], s=24, c=C_SHIP, marker="^",
                edgecolors=PAPER, linewidths=0.6, label="G3 (spp_dev)", zorder=4)
    for tx, ty, lbl, ha, va in [
        (545, 545, "保留写回 · 保留预取\n(插入 PLRU=8)", "right", "top"),
        (-545, 545, "释放写回 · 保留预取", "left", "top"),
        (-545, -545, "释放写回 · 释放预取\n(推至 PLRU=15)", "left", "bottom"),
        (545, -545, "保留写回 · 释放预取", "right", "bottom"),
    ]:
        ax1.text(tx, ty, lbl, fontsize=5.7, color=INK2, ha=ha, va=va, zorder=2, linespacing=1.25)
    ax1.set_xlim(-600, 600)
    ax1.set_ylim(-620, 620)
    ax1.set_xlabel("写回决斗计数 $w_{sel}$")
    ax1.set_ylabel("预取决斗计数 $pf_{sel}$")
    ax1.set_title("(a) 决斗计数四象限自适应（活跃轨迹）", loc="left", pad=6)
    ax1.legend(loc="center", frameon=True, framealpha=0.9, edgecolor=GRID, borderpad=0.35,
               handletextpad=0.3, bbox_to_anchor=(0.5, 0.5))
    for side in ("top", "right"):
        ax1.spines[side].set_visible(False)

    # (b) blocking vs non-blocking MPKI
    samples = [
        ("429.mcf\nG1", "g1_old_spp", "mpppb_spp", "ta_mpppb_spp", "429.mcf-22B"),
        ("470.lbm\nG1", "g1_old_spp", "mpppb_spp", "ta_mpppb_spp", "470.lbm-1274B"),
        ("605.mcf_s\nG2", "g2_new_pref", "mpppb_pref", "ta_mpppb_pref", "605.mcf_s-1554B"),
        ("619.lbm_s\nG3", "g3_new_spp", "mpppb_spp", "ta_mpppb_spp", "619.lbm_s-2676B"),
    ]

    def mpki(group, pol, tr):
        roi = json.loads((RAW / group / pol / f"{tr}.json").read_text())[0]["roi"]
        ins = roi["cores"][0]["instructions"]
        llc = roi["LLC"]
        lr = (sum(llc["LOAD"]["miss"]) + sum(llc["RFO"]["miss"])) * 1000.0 / ins
        wr = sum(llc["WRITE"]["miss"]) * 1000.0 / ins
        return ins / roi["cores"][0]["cycles"], lr, wr

    xs = np.arange(len(samples))
    w = 0.36
    for i, (_, g, pm, pt, tr) in enumerate(samples):
        im, lrm, wrm = mpki(g, pm, tr)
        it, lrt, wrt = mpki(g, pt, tr)
        for off, lr, wr, c_block, c_non, hatch, alpha in [
            (-w / 2, lrm, wrm, C_MUTE, C_MUTE, "", 0.95),
            (w / 2, lrt, wrt, C_TA, C_TA, "///", 0.95),
        ]:
            ax2.bar(xs[i] + off, lr, width=w * 0.92, color=c_block, edgecolor=PAPER, linewidth=0.6,
                    zorder=3, alpha=alpha)
            ax2.bar(xs[i] + off, wr, bottom=lr, width=w * 0.92, color=PAPER, edgecolor=c_non, linewidth=0.7,
                    hatch=hatch, zorder=4)
        d = (it / im - 1) * 100
        top = max(lrm + wrm, lrt + wrt)
        value_label(ax2, f"LR {lrt:.1f} / WR {wrt:.1f}", xs[i] + w / 2, top + 3.0, fs=5.4, color=C_TA)
        value_label(ax2, f"{d:+.1f}%", xs[i] + w / 2, top + 8.6, fs=6.0, color=C_TA, bold=True)

    ax2.set_xticks(xs)
    ax2.set_xticklabels([s[0] for s in samples], fontsize=6.4)
    ax2.set_ylim(0, 118)
    ax2.set_ylabel("LLC MPKI（缺失 / 千指令）")
    ax2.set_title("(b) 阻塞型 LR 与后台 WR 的权衡（左 MPPPB / 右 TA）", loc="left", pad=6)
    handles = [
        Patch(facecolor=C_MUTE, edgecolor=PAPER, label="MPPPB 阻塞 LR"),
        Patch(facecolor=PAPER, edgecolor=C_MUTE, hatch="", label="MPPPB 后台 WR"),
        Patch(facecolor=C_TA, edgecolor=PAPER, label="TA 阻塞 LR"),
        Patch(facecolor=PAPER, edgecolor=C_TA, hatch="///", label="TA 后台 WR"),
    ]
    ax2.legend(handles=handles, loc="upper left", frameon=False, ncol=2, handlelength=1.2,
               columnspacing=0.8, borderaxespad=0.2)
    hairline_frame(ax2, "y")
    save(fig, "fig5_mechanism")
    return {k: len(v) for k, v in pts.items()}


# ----------------------------------------------------------------------------
# Fig 6  ablation trade-offs & effective_ip probe
# ----------------------------------------------------------------------------
def fig6():
    tduel_dir = RAW / "v3_ablate" / "v3_c21_tduel"
    ta_dir = RAW / "ta_v3" / "ta_mpppb"
    traces6 = sorted(p.stem for p in tduel_dir.glob("*.json"))
    deltas6 = []
    for t in traces6:
        a = json.loads((tduel_dir / f"{t}.json").read_text())[0]["roi"]["cores"][0]
        b = json.loads((ta_dir / f"{t}.json").read_text())[0]["roi"]["cores"][0]
        deltas6.append(((a["instructions"] / a["cycles"]) / (b["instructions"] / b["cycles"]) - 1) * 100)

    cfg_file = pathlib.Path(__file__).resolve().parent / "effip_paths.json"
    eff_items, eff_deltas = [], []
    if cfg_file.exists():
        eff_dir = pathlib.Path(json.loads(cfg_file.read_text())["effip_dir"])
        for label, group, pol, tr in [
            ("649.fotonik3d_s\nG2 ip_stride", "g2_new_pref", "ta_mpppb_pref", "649.fotonik3d_s-1176B"),
            ("649.fotonik3d_s\nG3 spp_dev", "g3_new_spp", "ta_mpppb_spp", "649.fotonik3d_s-1176B"),
            ("623.xalancbmk_s\nG3 spp_dev", "g3_new_spp", "ta_mpppb_spp", "623.xalancbmk_s-10B"),
            ("623.xalancbmk_s\nG2 ip_stride", "g2_new_pref", "ta_mpppb_pref", "623.xalancbmk_s-10B"),
        ]:
            base = json.loads((RAW / group / pol / f"{tr}.json").read_text())[0]["roi"]["cores"][0]
            new = json.loads((eff_dir / group / pol / f"{tr}.json").read_text())[0]["roi"]["cores"][0]
            eff_items.append(label)
            eff_deltas.append(((new["instructions"] / new["cycles"]) /
                               (base["instructions"] / base["cycles"]) - 1) * 100)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.05, 2.35),
                                   gridspec_kw={"wspace": 0.3, "width_ratios": [1.0, 0.92]})
    x1 = np.arange(len(traces6))
    ax1.axhline(0, color=INK2, lw=0.6, zorder=1)
    for xi, d in zip(x1, deltas6):
        col = C_TA if d >= 0 else C_MP
        ax1.bar(xi, d, width=0.5, color=col, edgecolor=PAPER, linewidth=0.7, zorder=3)
        value_label(ax1, f"{d:+.2f}%", xi, d + (0.035 if d >= 0 else -0.035), fs=6.0,
                    va="bottom" if d >= 0 else "top")
    ax1.set_xticks(x1)
    ax1.set_xticklabels([t.split("-")[0] for t in traces6], fontsize=6.3, rotation=12, ha="right")
    ax1.set_ylim(-1.3, 1.1)
    ax1.set_ylabel("相对固定 PLRU=8 的 IPC 差 (%)")
    ax1.set_title("(a) 消融：动态页表决斗的收益—方差", loc="left", pad=6)
    hairline_frame(ax1, "y")

    if eff_items:
        x2 = np.arange(len(eff_items))
        ax2.axhline(0, color=INK2, lw=0.6, zorder=1)
        for xi, d in zip(x2, eff_deltas):
            col = C_SHIP if d >= 0 else C_MP
            ax2.bar(xi, d, width=0.46, color=col, edgecolor=PAPER, linewidth=0.7, zorder=3)
            value_label(ax2, f"{d:+.3f}%", xi, d + (0.008 if d >= 0 else -0.008), fs=6.0,
                        va="bottom" if d >= 0 else "top")
        ax2.set_xticks(x2)
        ax2.set_xticklabels(eff_items, fontsize=6.0)
        ax2.set_ylim(-0.06, 0.30)
        ax2.set_ylabel("相对主版本 v3 的 IPC 差 (%)")
        ax2.set_title("(b) 实证：启用 effective_ip 页号哈希", loc="left", pad=6)
        hairline_frame(ax2, "y")
    else:
        ax2.axis("off")
        ax2.text(0.5, 0.5, "effip 原始 JSON 不可用", ha="center", va="center", fontsize=7)

    save(fig, "fig6_ablation_effip")
    return dict(traces=traces6, eff=eff_deltas)


if __name__ == "__main__":
    out = {}
    for fn in (fig2, fig3, fig4, fig5, fig6):
        out[fn.__name__] = fn()
    for k, v in out.items():
        print(f"{k}: {v}")
