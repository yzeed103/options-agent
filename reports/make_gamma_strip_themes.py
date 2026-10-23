"""Theme variants of design D (bars from the right edge + regime) on real data, for the user to choose.

    python reports/make_gamma_strip_themes.py [SYMBOL]
Writes reports/styles/gamma_theme_<1..3>_<SYM>.png
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
from matplotlib.colors import LinearSegmentedColormap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sym = sys.argv[1] if len(sys.argv) > 1 else "MSFT"
c = sqlite3.connect("file:C:/project/gex_radar/data/snapshots.db?mode=ro", uri=True)
d = json.loads(c.execute("select payload from latest where symbol=? and basis='oi'", (sym,)).fetchone()[0])
spot, lv = d["spot"], d["levels"]
st = pd.DataFrame(d["strikes"])
st = st[(st.strike > spot * 0.96) & (st.strike < spot * 1.04)].reset_index(drop=True)
b = pd.read_csv(os.path.join(ROOT, "runtime", "bars", f"{sym}_5m.csv"))
b.index = pd.to_datetime(b["time"], utc=True).dt.tz_convert("America/New_York")
day = b.index.date.max()
b = b[b.index.date == day]
O, H, L, C = (b[k].to_numpy(float) for k in ("open", "high", "low", "close"))
N = len(b)
FLIP = lv["gamma_flip"]
step = float(np.median(np.diff(np.sort(st.strike.unique()))))
mx = st.net_gex.abs().max()
ylo, yhi = st.strike.min() - step, st.strike.max() + step
W = 26                                    # strip width in bars
BG, GR, TX, MUT = "#0b0e14", "#1c212b", "#d1d4dc", "#7d8592"


def frame(title):
    fig, ax = plt.subplots(figsize=(16, 9), facecolor=BG)
    ax.set_facecolor(BG); ax.tick_params(colors=MUT, labelsize=9); [s.set_color(GR) for s in ax.spines.values()]
    for i in range(N):
        col = "#26a69a" if C[i] >= O[i] else "#ef5350"
        ax.vlines(i, L[i], H[i], color=col, lw=0.8)
        ax.add_patch(Rectangle((i - 0.3, min(O[i], C[i])), 0.6, max(abs(C[i] - O[i]), 1e-3), color=col))
    ax.set_xlim(-1, N + 6 + W); ax.set_ylim(ylo, yhi); ax.set_xticks([]); ax.yaxis.tick_right()
    ax.set_title(title, color=TX, fontsize=12, loc="left")
    return fig, ax, N + 6 + W                                   # right edge


def price_tag(ax, right, color="#ffa726"):
    ax.hlines(spot, -1, right, color=color, lw=0.8, ls=":")
    ax.text(right - 0.2, spot, f" {spot:.2f} ", color="#0b0e14", fontsize=8, va="center", ha="right",
            bbox=dict(boxstyle="round,pad=0.2", fc=color, ec="none"))


def save(fig, n):
    fig.suptitle(f"{sym} 5m {day} · real GEXRadar strike gamma", color=MUT, fontsize=10, y=0.995)
    fig.tight_layout()
    out = os.path.join(ROOT, "reports", "styles", f"gamma_theme_{n}_{sym}.png")
    fig.savefig(out, dpi=90, facecolor=BG); plt.close(fig); print(out)


# ---- 1 · Glass: opacity follows size, gaps between bars, soft flip band, tint only behind the strip
fig, ax, right = frame("1 · Glass: brightness = size, gaps between bars, regime tint only behind the strip (candles stay clean)")
x_strip = right - W
ax.add_patch(Rectangle((x_strip, FLIP), W, yhi - FLIP, color="#29b6f6", alpha=0.07, lw=0))
ax.add_patch(Rectangle((x_strip, ylo), W, FLIP - ylo, color="#ef5350", alpha=0.09, lw=0))
ax.add_patch(Rectangle((-1, FLIP - step * 0.12), right + 1, step * 0.24, color="#ffd600", alpha=0.25, lw=0))
ax.text(x_strip + 0.3, FLIP + step * 0.2, "FLIP", color="#ffd600", fontsize=8, va="bottom")
for _, r in st.iterrows():
    k = abs(r.net_gex) / mx
    col = "#29b6f6" if r.net_gex > 0 else "#ff5c5c"
    ln = W * k
    ax.add_patch(Rectangle((right - ln, r.strike - step * 0.32), ln, step * 0.64, fc=col, alpha=0.30 + 0.65 * k, ec=col, lw=0.8))
ax.text(x_strip + 0.3, yhi - step * 0.4, "calm", color="#29b6f6", fontsize=9, alpha=0.8)
ax.text(x_strip + 0.3, ylo + step * 0.3, "fast", color="#ff5c5c", fontsize=9, alpha=0.8)
price_tag(ax, right)
save(fig, 1)

# ---- 2 · Minimal lollipops: thin stems + dot, values on the 3 biggest, nothing else
fig, ax, right = frame("2 · Minimal: thin stems with a dot, the 3 biggest strikes labelled with their size, flip as a thin line")
x_strip = right - W
ax.vlines(right, ylo, yhi, color=GR, lw=1)
top3 = set(st.net_gex.abs().sort_values(ascending=False).index[:3])
for i, r in st.iterrows():
    k = abs(r.net_gex) / mx
    col = "#4fc3f7" if r.net_gex > 0 else "#ff6b6b"
    x1 = right - W * k
    ax.hlines(r.strike, x1, right, color=col, lw=2.2, alpha=0.9)
    ax.plot(x1, r.strike, "o", color=col, ms=5)
    if i in top3:
        ax.text(x1 - 0.5, r.strike, f"{r.strike:g}  {r.net_gex / 1e6:+.0f}M", color=col, fontsize=8, va="center", ha="right")
ax.hlines(FLIP, -1, right, color="#ffd600", lw=0.9, ls="--")
ax.text(x_strip, FLIP, "FLIP ", color="#ffd600", fontsize=8, va="bottom", ha="left")
price_tag(ax, right)
save(fig, 2)

# ---- 3 · Heat gradient: colour deepens with size (blue->cyan, orange->red), tint behind the strip, label column
fig, ax, right = frame("3 · Heat: colour deepens with size, strike labels in a column, regime tint behind the strip only")
x_strip = right - W
pos_map = LinearSegmentedColormap.from_list("p", ["#14324a", "#1e88e5", "#80deea"])
neg_map = LinearSegmentedColormap.from_list("n", ["#3a1717", "#e65100", "#ff1744"])
ax.add_patch(Rectangle((x_strip, FLIP), W, yhi - FLIP, color="#1e88e5", alpha=0.06, lw=0))
ax.add_patch(Rectangle((x_strip, ylo), W, FLIP - ylo, color="#e65100", alpha=0.07, lw=0))
for _, r in st.iterrows():
    k = abs(r.net_gex) / mx
    col = (pos_map if r.net_gex > 0 else neg_map)(0.25 + 0.75 * k)
    ln = (W - 4) * k
    ax.add_patch(Rectangle((right - ln, r.strike - step * 0.36), ln, step * 0.72, fc=col, ec="none"))
    ax.text(x_strip + 0.2, r.strike, f"{r.strike:g}", color=MUT if k < 0.3 else TX, fontsize=7, va="center")
ax.hlines(FLIP, -1, right, color="#ffd600", lw=1, ls=(0, (4, 3)))
ax.text(right, FLIP, "FLIP ", color="#ffd600", fontsize=8, va="bottom", ha="right")
price_tag(ax, right)
save(fig, 3)
