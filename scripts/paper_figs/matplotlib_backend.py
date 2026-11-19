#!/usr/bin/env python3
"""Matplotlib CAD-style backend for paper figures.

Pure plotting only: no shapes that pretend to be hardware.  All panels follow
the CjC-journal look (serif, 8pt base, hair-line axes, no chart junk) and are
emitted as vector PDF, then rasterised to PNG for the visual review loop.
"""
from __future__ import annotations

import pathlib

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
FIG_DIR = ROOT / "paper" / "figures"
PREVIEW_DIR = ROOT / "notes" / "fig_preview"

# Jalali palette: warm white paper, muted ink, restrained data colours.
INK = "#1E2328"
INK2 = "#4A5560"
GRID = "#D8DDE2"
PAPER = "#FFFFFF"

C_LRU = "#9AA3AB"
C_SHIP = "#4C7FA8"
C_MP = "#B4534A"
C_TA = "#2E7D6E"
C_AMB = "#C08A3E"
C_IND = "#6E638F"
C_MUTE = "#C9CED4"

SERIF = ["Times New Roman", "DejaVu Serif"]
CJK = ["SimSun", "Songti SC", "Noto Serif CJK SC", "Source Han Serif SC", "Microsoft YaHei"]

plt.rcParams.update(
    {
        "font.family": "serif",
        "font.serif": SERIF,
        "font.sans-serif": CJK,
        "mathtext.fontset": "stix",
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "font.size": 7.6,
        "axes.titlesize": 7.8,
        "axes.labelsize": 7.4,
        "xtick.labelsize": 7.0,
        "ytick.labelsize": 7.0,
        "legend.fontsize": 6.8,
        "axes.linewidth": 0.6,
        "axes.edgecolor": INK2,
        "axes.labelcolor": INK,
        "xtick.color": INK2,
        "ytick.color": INK2,
        "xtick.major.width": 0.6,
        "ytick.major.width": 0.6,
        "xtick.major.size": 2.6,
        "ytick.major.size": 2.6,
        "text.color": INK,
        "figure.facecolor": PAPER,
        "savefig.facecolor": PAPER,
    }
)


def gm(xs):
    xs = list(xs)
    return float(np.exp(np.mean(np.log(xs))))


def pct(num, den):
    return (gm([n / d for n, d in zip(num, den)]) - 1.0) * 100.0


def hairline_frame(ax, grid_axis="y"):
    """Open frame: keep only left/bottom spines, add a whisper of grid."""
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    if grid_axis:
        ax.grid(axis=grid_axis, color=GRID, linewidth=0.45, alpha=0.9, zorder=0)
    ax.set_axisbelow(True)
    ax.tick_params(length=2.4, pad=2.0)


def value_label(ax, text, x, y, *, color=INK, bold=False, fs=6.6, va="bottom", ha="center"):
    ax.text(
        x,
        y,
        text,
        ha=ha,
        va=va,
        fontsize=fs,
        color=color,
        fontweight="bold" if bold else "normal",
        zorder=6,
        path_effects=[pe.withStroke(linewidth=1.6, foreground=PAPER)],
    )


def save(fig, stem: str):
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    pdf = FIG_DIR / f"{stem}.pdf"
    png = PREVIEW_DIR / f"{stem}.png"
    # PNG previews use a CJK-capable family so the review images show Chinese;
    # the PDF keeps the journal serif and lets xeCJK in main.tex handle glyphs.
    fig.savefig(pdf, bbox_inches="tight", pad_inches=0.02)
    with plt.rc_context({"font.family": "sans-serif", "font.sans-serif": CJK}):
        fig.savefig(png, dpi=220, bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)
    return pdf
