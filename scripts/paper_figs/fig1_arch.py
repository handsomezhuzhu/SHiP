#!/usr/bin/env python3
"""Fig.1 architecture plates, drawn with real primitives.

Panel (a)  baseline MPPPB: five request classes funnel into one prediction engine;
           the three ip == 0 classes alias onto weight bucket 0 and flush pc_ring.
Panel (b)  TA-MPPPB v3: four semantic lanes, Zero-PC shielding, PTW mid-tree
           protection and the two orthogonal demand-weighted set duelers.

One colour per request class, identical in both panels.
Outputs paper/figures/fig1_arch.pdf (LaTeX) and notes/fig_src/fig1_{a,b}.svg/png.
"""
from __future__ import annotations

import pathlib
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mp
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch, Rectangle

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from matplotlib_backend import CJK, INK, PAPER, save  # noqa: E402

SRC_DIR = pathlib.Path(r"E:\并行计算\notes\fig_src")

INK2 = "#4B5563"
HAIR = "#8B95A1"
SOFT = "#F3F6F8"
CH_DEMAND = "#2F5D8A"
CH_TRANS = "#1F7A6E"
CH_WRITE = "#A9722A"
CH_PREF = "#6E5A8E"
ERR = "#A33A31"

# (y, name, pc visibility, colour)
LANES = [
    (5.62, "LOAD / RFO", "ip ≠ 0", CH_DEMAND),
    (4.30, "TRANSLATION", "ip = 0", CH_TRANS),
    (2.98, "WRITE", "ip = 0", CH_WRITE),
    (1.66, "PREFETCH", "ip = 0", CH_PREF),
]
H = 0.86


def box(ax, x, y, w, h, *, ec=HAIR, fc=PAPER, lw=0.85, ls="-", z=3, rounding=0.0):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={rounding}",
                                facecolor=fc, edgecolor=ec, linewidth=lw, linestyle=ls, zorder=z))


def txt(ax, x, y, s, *, fs=6.0, color=INK, bold=False, ha="left", va="center", z=7, ls=1.45):
    ax.text(x, y, s, fontsize=fs, color=color, ha=ha, va=va, zorder=z, linespacing=ls,
            fontweight="bold" if bold else "normal")


def arrow(ax, p0, p1, *, color=INK2, lw=0.8, ls="-", z=2, head=3.4, style="-|>"):
    spec = f"{style},head_length={head},head_width={head * 0.62}" if style != "-" else "-"
    ax.add_patch(FancyArrowPatch(p0, p1, arrowstyle=spec, color=color, linewidth=lw,
                                 linestyle=ls, zorder=z, shrinkA=0, shrinkB=0, capstyle="butt"))


def unit_box(ax, x, y, w, h, name, sub, col, fs=6.2):
    box(ax, x, y, w, h, ec=col, lw=0.95, rounding=0.05)
    ax.add_patch(Rectangle((x, y), 0.06, h, facecolor=col, edgecolor="none", zorder=4))
    txt(ax, x + w / 2 + 0.03, y + h * 0.64, name, fs=fs, color=col, bold=True, ha="center")
    txt(ax, x + w / 2 + 0.03, y + h * 0.25, sub, fs=fs - 0.35, color=INK2, ha="center")


# ---------------------------------------------------------------- panel (a)
def panel_a(ax, W=4.95):
    for y, name, sub, col in LANES:
        unit_box(ax, 0.10, y, W, H, name, sub, col)

    # convergence funnel into the single engine
    ax.add_patch(mp.Polygon([[W + 0.14, 6.48], [W + 0.14, 1.66], [W + 1.30, 3.10], [W + 1.30, 4.55]],
                            closed=True, facecolor=SOFT, edgecolor="none", zorder=1))
    for y, _, _, col in LANES:
        arrow(ax, (W + 0.10, y + H / 2), (W + 1.26, 3.82), color=col, lw=0.8, z=1.6)

    # prediction engine
    ex = W + 1.30
    ew = 2.55
    box(ax, ex, 2.34, ew, 3.00, ec=INK, lw=1.0, rounding=0.10)
    txt(ax, ex + ew / 2, 5.02, "共享预测引擎", fs=6.7, bold=True, ha="center")
    for i, t in enumerate(["感知机 16 表 × 6-bit", "1/32 影子采样器", "pc_ring[32]"]):
        yy = 4.44 - i * 0.56
        ax.add_patch(Rectangle((ex + 0.14, yy - 0.18), ew - 0.28, 0.36, facecolor=PAPER,
                               edgecolor=HAIR, linewidth=0.6, zorder=5))
        txt(ax, ex + ew / 2, yy, t, fs=5.9, color=INK2, ha="center", z=6)

    # bucket-0 aliasing
    ax.add_patch(Rectangle((ex + 0.14, 2.52), 0.62, 0.36, facecolor="#FBEDEB", edgecolor=ERR,
                           linewidth=0.75, zorder=6))
    txt(ax, ex + 0.45, 2.70, "桶 0", fs=5.8, color=ERR, bold=True, ha="center", z=7)
    arrow(ax, (ex + 0.80, 2.70), (ex + 0.92, 2.70), color=ERR, lw=0.7)
    txt(ax, ex + 0.96, 2.70, "三类零 PC 请求\n共占同一权重点", fs=5.4, color=ERR, ls=1.3)

    # output side
    ox = ex + ew + 0.34
    arrow(ax, (ex + ew + 0.02, 4.66), (ox + 0.16, 5.26), color=CH_DEMAND, lw=0.85)
    txt(ax, ox + 0.18, 5.02, "置信度打分", fs=5.6, color=INK2)
    box(ax, ox + 0.16, 4.98, 2.28, 1.10, ec=CH_DEMAND, lw=0.9)
    txt(ax, ox + 0.26, 5.74, "真旁路 / 分级插入", fs=6.0, color=CH_DEMAND, bold=True)
    txt(ax, ox + 0.26, 5.28, "15-bit 树状 PLRU，16 路", fs=5.7, color=INK2)

    arrow(ax, (ex + ew + 0.02, 3.30), (ox + 0.12, 3.86), color=ERR, lw=0.85, ls=(0, (3, 1.6)))
    box(ax, ox + 0.16, 2.66, 2.28, 1.50, ec=ERR, fc="#FBEDEB", lw=0.9)
    txt(ax, ox + 0.26, 3.86, "页表块被误旁路", fs=6.0, color=ERR, bold=True)
    txt(ax, ox + 0.26, 3.34, "写回与预取挤占容量\n需求块 16 路被冲刷", fs=5.6, color=ERR, ls=1.35)

    # pc_ring flush
    arrow(ax, (ex + ew / 2, 2.30), (ex + ew / 2, 1.92), color=ERR, lw=0.85, ls=(0, (3, 1.6)))
    txt(ax, ex + ew / 2 + 0.12, 2.04, "32 格控制流历史环被清零", fs=5.7, color=ERR)


# ---------------------------------------------------------------- panel (b)
def panel_b(ax):
    W = 1.98
    for y, name, sub, col in LANES:
        unit_box(ax, 0.10, y, W, H, name, sub, col, fs=5.9)

    gx = W + 0.30
    ax.add_patch(Rectangle((gx, 1.60), 0.18, 4.88, facecolor="#E9EFF3", edgecolor=HAIR,
                           linewidth=0.6, zorder=2))
    txt(ax, gx + 0.09, 1.16, "零 PC\n屏蔽", fs=5.4, color=INK2, ha="center", ls=1.3)

    lx = gx + 0.38
    lw_ = 3.30
    bx = lx + lw_ + 0.18
    bw = 1.72

    # lane A: cleaned perceptron + bypass dueler
    box(ax, lx, 5.58, lw_, 1.22, ec=CH_DEMAND, lw=0.95, rounding=0.05)
    txt(ax, lx + 0.12, 6.36, "净化后的感知机 + 采样器", fs=6.0, color=CH_DEMAND, bold=True)
    txt(ax, lx + 0.12, 5.95, "pc_ring 只记录真实指令轨迹", fs=5.6, color=INK2)
    box(ax, bx, 5.58, bw, 1.22, ec=CH_DEMAND, lw=0.95, rounding=0.05)
    txt(ax, bx + bw / 2, 6.34, "psel_ 决斗", fs=6.0, color=CH_DEMAND, bold=True, ha="center")
    txt(ax, bx + bw / 2, 5.95, "旁路 / 插入", fs=5.6, color=INK2, ha="center")

    # lane B: PTW hard rules, full width (no dueler)
    box(ax, lx, 4.24, lw_ + 0.18 + bw, 1.00, ec=CH_TRANS, lw=0.95, rounding=0.05)
    txt(ax, lx + 0.12, 4.98, "永不旁路 · 不进采样器", fs=6.0, color=CH_TRANS, bold=True)
    txt(ax, lx + 0.12, 4.55, "固定插入 PLRU = 8，命中按 kVecMdpp 晋升", fs=5.6, color=INK2)

    # lanes C/D
    lane_info = [
        (2.92, "WRITE", "双模采样：预取隔离 / 无预取回传", CH_WRITE, "wsel_"),
        (1.60, "PREFETCH", "不旁路、不采样，杜绝表污染", CH_PREF, "pfsel_"),
    ]
    for y, name, sub, col, dname in lane_info:
        box(ax, lx, y, lw_, 0.92, ec=col, lw=0.95, rounding=0.05)
        txt(ax, lx + 0.12, y + 0.64, name, fs=6.0, color=col, bold=True)
        txt(ax, lx + 0.12, y + 0.26, sub, fs=5.5, color=INK2)
        box(ax, bx, y, bw, 0.92, ec=col, lw=0.95, rounding=0.05)
        txt(ax, bx + bw / 2, y + 0.64, f"{dname} 决斗", fs=6.0, color=col, bold=True, ha="center")
        txt(ax, bx + bw / 2, y + 0.26, "PLRU 8 ⇄ 15", fs=5.6, color=INK2, ha="center")

    # lane arrows through the shield
    entry = [(6.19, CH_DEMAND), (4.74, CH_TRANS), (3.38, CH_WRITE), (2.06, CH_PREF)]
    for yy, col in entry:
        arrow(ax, (W + 0.12, yy), (gx + 0.09, yy), color=col, head=0, lw=0.75)
        arrow(ax, (gx + 0.20, yy), (lx - 0.03, yy), color=col, lw=0.75)
    arrow(ax, (lx + lw_ + 0.01, 6.19), (bx - 0.03, 6.19), color=CH_DEMAND, lw=0.75)
    for y in (3.38, 2.06):
        arrow(ax, (lx + lw_ + 0.01, y), (bx - 0.03, y), color=CH_WRITE if y > 2.5 else CH_PREF, lw=0.75)

    # demand-miss supervision of both duelers
    sx = bx + bw
    xline = sx + 0.16
    ax.plot([xline, xline], [2.06, 3.38], color=INK2, lw=0.65, ls=(0, (2.5, 1.8)), zorder=2)
    ax.plot([xline, bx + bw + 0.02], [3.38, 3.38], color=INK2, lw=0.65, ls=(0, (2.5, 1.8)), zorder=2)
    ax.plot([xline, bx + bw + 0.02], [2.06, 2.06], color=INK2, lw=0.65, ls=(0, (2.5, 1.8)), zorder=2)
    ax.plot([xline, xline], [3.38, 2.06], color=INK2, lw=0.65, ls=(0, (2.5, 1.8)), zorder=2)
    txt(ax, xline + 0.10, 2.72, "核需求\n缺失监督", fs=5.2, color=INK2, ls=1.3)

    # shared Tree-PLRU
    tx = xline + 0.86
    tw = 10.0 - tx - 0.04
    box(ax, tx, 1.60, tw, 5.20, ec=CH_TRANS, lw=1.05, rounding=0.10)
    cx = tx + tw / 2
    txt(ax, cx, 6.42, "15-bit", fs=6.0, color=CH_TRANS, bold=True, ha="center")
    txt(ax, cx, 6.14, "树状 PLRU", fs=6.0, color=CH_TRANS, bold=True, ha="center")
    txt(ax, cx, 5.84, "16 路 · 最小扰动", fs=5.3, color=INK2, ha="center")

    r = 0.13
    levels = [(5.34, [0.0]), (4.86, [-0.62, 0.62]), (4.38, [-0.93, -0.31, 0.31, 0.93])]
    for li, (yy, xs) in enumerate(levels):
        for xx in xs:
            ax.add_patch(Circle((cx + xx, yy), r * (1 - 0.1 * li), facecolor="#DCEAE6",
                                edgecolor=CH_TRANS, linewidth=0.55, zorder=6))
    for (y0, xs0), (y1, xs1) in zip(levels, levels[1:]):
        for i, x0 in enumerate(xs0):
            for j in (2 * i, 2 * i + 1):
                ax.plot([cx + x0, cx + xs1[j]], [y0 - r * 0.9, y1 + r * 0.9], color=CH_TRANS,
                        lw=0.5, zorder=5)

    txt(ax, cx, 3.72, "PLRU 8：页表观察位", fs=5.5, color=CH_TRANS, ha="center")
    ax.plot([cx, cx], [3.88, 4.22], color=CH_TRANS, lw=0.55, zorder=5)
    txt(ax, cx, 2.98, "PLRU 15：冷插入位", fs=5.4, color=INK2, ha="center")
    txt(ax, cx, 2.62, "（写回 / 预取）", fs=5.2, color=INK2, ha="center")
    ax.plot([cx, cx], [3.22, 3.50], color=INK2, lw=0.55, ls=(0, (2, 1.5)), zorder=5)

    # all lanes converge into the tree
    for yy, col in [(6.19, CH_DEMAND), (4.74, CH_TRANS), (3.38, CH_WRITE), (2.06, CH_PREF)]:
        ax.plot([sx + 0.30, tx - 0.02], [yy, yy], color=col, lw=0.7, zorder=1.8,
                ls=(0, (1, 1.6)))
        arrow(ax, (tx - 0.30, yy), (tx - 0.02, yy), color=col, lw=0.7, head=3.0)


def build():
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.1, 2.5), gridspec_kw={"wspace": 0.05})
    for ax in (a1, a2):
        ax.set_xlim(0, 10)
        ax.set_ylim(0, 6.95)
        ax.axis("off")
    panel_a(a1)
    panel_b(a2)
    a1.set_title("(a) 原版 MPPPB：五类请求共用一个预测引擎", loc="left", fontsize=7.3, pad=3)
    a2.set_title("(b) TA-MPPPB v3：四通道解耦与正交双决斗", loc="left", fontsize=7.3, pad=3)
    save(fig, "fig1_arch")

    for name, fn, title in [
        ("fig1_a", panel_a, "(a) 原版 MPPPB：五类请求共用一个预测引擎"),
        ("fig1_b", panel_b, "(b) TA-MPPPB v3：四通道解耦与正交双决斗"),
    ]:
        f, ax = plt.subplots(figsize=(3.55, 2.5))
        ax.set_xlim(0, 10)
        ax.set_ylim(0, 6.95)
        ax.axis("off")
        fn(ax)
        ax.set_title(title, loc="left", fontsize=7.8, pad=3)
        f.savefig(SRC_DIR / f"{name}.svg", bbox_inches="tight", pad_inches=0.03)
        f.savefig(SRC_DIR / f"{name}.png", dpi=200, bbox_inches="tight", pad_inches=0.03)
        plt.close(f)


if __name__ == "__main__":
    SRC_DIR.mkdir(parents=True, exist_ok=True)
    with plt.rc_context({"font.family": "sans-serif", "font.sans-serif": CJK}):
        build()
    print("fig1_arch done")
