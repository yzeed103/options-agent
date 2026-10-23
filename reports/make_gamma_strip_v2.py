"""Improved gamma-strip designs (after the user found v25 too sparse): real MSFT candles + live GEXRadar strike gamma.
All four use square-root scaling (small strikes stay visible), +-3% of price, thick bars, and are buildable in Pine
(boxes, lines, labels only).

    python reports/make_gamma_strip_v2.py [SYMBOL]
"""
import json
import os
import sqlite3
import sys

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sym = sys.argv[1] if len(sys.argv) > 1 else "MSFT"
c = sqlite3.connect("file:C:/project/gex_radar/data/snapshots.db?mode=ro", uri=True)
d = json.loads(c.execute("select payload from latest where symbol=? and basis='oi'", (sym,)).fetchone()[0])
spot, lv = d["spot"], d["levels"]
st = pd.DataFrame(d["strikes"])
st = st[(st.strike > spot * 0.97) & (st.strike < spot * 1.03)].sort_values("strike").reset_index(drop=True)
st["v"] = st.net_gex / 1e6
b = pd.read_csv(os.path.join(ROOT, "runtime", "bars", f"{sym}_5m.csv"))
b.index = pd.to_datetime(b["time"], utc=True).dt.tz_convert("America/New_York")
days = sorted(set(b.index.date))[-2:]
b = b[[t.date() in days for t in b.index]]
O, H, L, C = (b[k].to_numpy(float) for k in ("open", "high", "low", "close"))
N = len(b)
FLIP = lv["gamma_flip"]
step = float(np.median(np.diff(st.strike.to_numpy())))
mx = st.v.abs().max()
sq = lambda x: np.sqrt(abs(x) / mx)  # noqa: E731
ylo, yhi = st.strike.min() - step, st.strike.max() + step
BG, PANEL, GR, TX, MUT = "#0b0e14", "#141821", "#232836", "#d1d4dc", "#7d8592"
GREEN, RED, GOLD = "#00c853", "#ff1744", "#ffd600"


def frame(title, strip_w=40, gap=3):
    fig, ax = plt.subplots(figsize=(16, 9), facecolor=BG)
    ax.set_facecolor(BG); ax.tick_params(colors=MUT, labelsize=9); [s.set_color(GR) for s in ax.spines.values()]
    for i in range(N):
        col = "#26a69a" if C[i] >= O[i] else "#ef5350"
        ax.vlines(i, L[i], H[i], color=col, lw=0.7)
        ax.add_patch(Rectangle((i - 0.3, min(O[i], C[i])), 0.6, max(abs(C[i] - O[i]), 1e-3), color=col))
    x0 = N + gap
    ax.set_xlim(N - 120, x0 + strip_w + 2); ax.set_ylim(ylo, yhi); ax.set_xticks([]); ax.yaxis.tick_right()
    ax.set_title(title, color=TX, fontsize=12, loc="left")
    ax.hlines(spot, N - 120, x0 + strip_w, color="#ffa726", lw=0.8, ls=":")
    return fig, ax, x0, strip_w


def flip_line(ax, x_end, text_x):
    ax.hlines(FLIP, N - 120, x_end, color=GOLD, lw=1, ls="--")
    ax.text(text_x, FLIP, " انقلاب القاما "[::-1] if False else f" FLIP {FLIP:.2f}", color=GOLD, fontsize=8, va="bottom")


def save(fig, n):
    fig.suptitle(f"{sym} 5m · real GEXRadar strike gamma · ±3% of price · square-root scale", color=MUT, fontsize=10, y=0.995)
    fig.tight_layout()
    out = os.path.join(ROOT, "reports", "styles", f"gamma_v2_{n}_{sym}.png")
    fig.savefig(out, dpi=90, facecolor=BG); plt.close(fig); print(out)


top = set(st.v.abs().sort_values(ascending=False).index[:5])

# 1 · panel of thick bars right next to the candles, every strike numbered, top 5 values
fig, ax, x0, w = frame("1 · Panel: thick bars right next to the candles, every strike numbered, the 5 biggest with their size")
ax.add_patch(Rectangle((x0 - 1, ylo), w + 2, yhi - ylo, color=PANEL, lw=0))
for i, r in st.iterrows():
    ln = (w - 8) * sq(r.v)
    col = GREEN if r.v > 0 else RED
    ax.add_patch(Rectangle((x0 + 7, r.strike - step * 0.38), ln, step * 0.76, color=col, alpha=0.85, lw=0))
    ax.text(x0, r.strike, f"{r.strike:g}", color=TX if i in top else MUT, fontsize=7, va="center")
    if i in top:
        ax.text(x0 + 7 + ln + 0.4, r.strike, f"{r.v:+.0f}M", color=col, fontsize=8, va="center", fontweight="bold")
flip_line(ax, x0 + w, x0 + 7)
save(fig, 1)

# 2 · mirror around a centre line (calls dominate -> right, puts -> left), panel, values on top 5
fig, ax, x0, w = frame("2 · Mirror: centre line, green to the right where calls dominate, red to the left where puts do")
ax.add_patch(Rectangle((x0 - 1, ylo), w + 2, yhi - ylo, color=PANEL, lw=0))
cx = x0 + w / 2
ax.vlines(cx, ylo, yhi, color=GR, lw=1)
for i, r in st.iterrows():
    ln = (w / 2 - 3) * sq(r.v) * (1 if r.v > 0 else -1)
    col = GREEN if r.v > 0 else RED
    ax.add_patch(Rectangle((cx, r.strike - step * 0.38), ln, step * 0.76, color=col, alpha=0.85, lw=0))
    if i in top:
        ax.text(cx + ln + (0.4 if ln > 0 else -0.4), r.strike, f"{r.strike:g} {r.v:+.0f}M", color=col, fontsize=8, va="center",
                ha="left" if ln > 0 else "right", fontweight="bold")
flip_line(ax, x0 + w, x0)
save(fig, 2)

# 3 · heat bars: one colour scale by size (pale -> deep), thicker for the top 5, strikes on the left of the panel
fig, ax, x0, w = frame("3 · Heat: colour deepens with size, the 5 biggest drawn brighter with their size")
ax.add_patch(Rectangle((x0 - 1, ylo), w + 2, yhi - ylo, color=PANEL, lw=0))
for i, r in st.iterrows():
    k = sq(r.v)
    ln = (w - 8) * k
    base = np.array([0, 200, 83]) if r.v > 0 else np.array([255, 23, 68])
    col = tuple(np.clip((0.25 + 0.75 * k) * base + (1 - (0.25 + 0.75 * k)) * np.array([20, 24, 33]), 0, 255) / 255)
    ax.add_patch(Rectangle((x0 + 7, r.strike - step * 0.4), ln, step * 0.8, color=col, lw=0))
    ax.text(x0, r.strike, f"{r.strike:g}", color=TX if i in top else MUT, fontsize=7, va="center")
    if i in top:
        ax.text(x0 + 7 + ln + 0.4, r.strike, f"{r.v:+.0f}M", color=GREEN if r.v > 0 else RED, fontsize=8, va="center", fontweight="bold")
flip_line(ax, x0 + w, x0 + 7)
save(fig, 3)

# 4 · thick lollipops, no panel, every value printed small, flip as a band
fig, ax, x0, w = frame("4 · Thick lollipops: every strike with its value, flip as a soft band, no panel")
ax.add_patch(Rectangle((N - 120, FLIP - step * 0.15), x0 + w - (N - 120), step * 0.3, color=GOLD, alpha=0.2, lw=0))
right = x0 + w
for i, r in st.iterrows():
    ln = (w - 10) * sq(r.v)
    col = GREEN if r.v > 0 else RED
    ax.hlines(r.strike, right - ln, right, color=col, lw=3.5)
    ax.plot(right - ln, r.strike, "o", color=col, ms=6)
    ax.text(right - ln - 0.6, r.strike, f"{r.strike:g}  {r.v:+.1f}M", color=TX if i in top else MUT, fontsize=7, va="center", ha="right")
ax.text(x0, FLIP, " FLIP", color=GOLD, fontsize=8, va="bottom")
save(fig, 4)
