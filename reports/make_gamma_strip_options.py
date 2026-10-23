"""Four design options for showing per-strike gamma as a strip beside the price axis, on real data:
today's 5-minute MSFT candles (runtime/bars) and GEXRadar's live strike table (read-only).

    python reports/make_gamma_strip_options.py [SYMBOL]
Writes reports/styles/gamma_strip_options_<SYM>.png
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
st = st[(st.strike > spot * 0.96) & (st.strike < spot * 1.04)]
b = pd.read_csv(os.path.join(ROOT, "runtime", "bars", f"{sym}_5m.csv"))
b.index = pd.to_datetime(b["time"], utc=True).dt.tz_convert("America/New_York")
day = b.index.date.max()
b = b[b.index.date == day]
O, H, L, C = (b[k].to_numpy(float) for k in ("open", "high", "low", "close"))
N = len(b)
FLIP, CW, PW, PIN = lv["gamma_flip"], lv["call_wall"], lv["put_wall"], lv["pin"]
BG, GR, TX, MUT = "#0b0e14", "#1f2430", "#d1d4dc", "#8a8f9c"
POS, NEG, CALL, PUT = "#29b6f6", "#ef5350", "#26a69a", "#ef5350"
ylo, yhi = st.strike.min() - 1, st.strike.max() + 1
step = np.median(np.diff(np.sort(st.strike.unique()))) if len(st) > 2 else 1.0


def base(ax, title, strip_w=22):
    ax.set_facecolor(BG); ax.tick_params(colors=MUT, labelsize=9); [s.set_color(GR) for s in ax.spines.values()]
    for i in range(N):
        col = "#26a69a" if C[i] >= O[i] else "#ef5350"
        ax.vlines(i, L[i], H[i], color=col, lw=0.8)
        ax.add_patch(Rectangle((i - 0.3, min(O[i], C[i])), 0.6, max(abs(C[i] - O[i]), 1e-3), color=col))
    ax.set_xlim(-1, N + 4 + strip_w); ax.set_ylim(ylo, yhi); ax.set_xticks([]); ax.yaxis.tick_right()
    ax.axhline(spot, color="#ffa726", lw=0.8, ls=":")
    ax.set_title(title, color=TX, fontsize=11, loc="left")
    return N + 4, strip_w


def lines(ax, x0, w, label_flip=True):
    ax.hlines(FLIP, -1, x0 + w, color="#ffd600", lw=1, ls="--")
    if label_flip:
        ax.text(x0 + w, FLIP, f" انقلاب القاما {FLIP:.2f}"[::-1] if False else f" FLIP {FLIP:.2f}", color="#ffd600", fontsize=8, va="bottom", ha="right")


SINGLE = "--single" in sys.argv
if SINGLE:
    figs = [plt.subplots(figsize=(16, 9), facecolor=BG) for _ in range(4)]
    axs = np.array([[figs[0][1], figs[1][1]], [figs[2][1], figs[3][1]]])
else:
    fig, axs = plt.subplots(2, 2, figsize=(17, 12), facecolor=BG)
h = step * 0.8
mx = st.net_gex.abs().max()

# A: net gamma bars, both directions from a centre line
ax = axs[0, 0]; x0, w = base(ax, "A · net gamma per strike, right = positive (calms), left = negative (speeds up)")
cx = x0 + w / 2
ax.axvline(cx, color=GR, lw=0.8)
for _, r in st.iterrows():
    ln = (w / 2) * r.net_gex / mx
    ax.add_patch(Rectangle((cx, r.strike - h / 2), ln, h, color=POS if ln > 0 else NEG, lw=0))
lines(ax, x0, w)

# B: calls right, puts left (two sides)
ax = axs[0, 1]; x0, w = base(ax, "B · calls to the right (green), puts to the left (red), same scale")
cx = x0 + w / 2
m2 = max(st.call_gex.abs().max(), st.put_gex.abs().max())
ax.axvline(cx, color=GR, lw=0.8)
for _, r in st.iterrows():
    ax.add_patch(Rectangle((cx, r.strike - h / 2), (w / 2) * abs(r.call_gex) / m2, h, color=CALL, lw=0))
    ax.add_patch(Rectangle((cx, r.strike - h / 2), -(w / 2) * abs(r.put_gex) / m2, h, color=PUT, lw=0))
lines(ax, x0, w)

# C: thin heat column (no lengths): colour = sign, opacity = size
ax = axs[1, 0]; x0, w = base(ax, "C · narrow heat column: blue = positive, red = negative, strength = brightness", strip_w=6)
for _, r in st.iterrows():
    a = min(1.0, 0.15 + 0.85 * abs(r.net_gex) / mx)
    ax.add_patch(Rectangle((x0, r.strike - step / 2), w, step, color=POS if r.net_gex > 0 else NEG, alpha=a, lw=0))
for v, nm in ((CW, "CW"), (PW, "PW")):
    ax.text(x0 + w + 0.3, v, nm, color=TX, fontsize=8, va="center")
lines(ax, x0, w)

# D: bars from the right edge + regime tint (above flip calm, below fast) + only the 3 biggest strikes labelled
ax = axs[1, 1]; x0, w = base(ax, "D · bars from the right edge + regime background (blue calm above the flip, red fast below)")
ax.add_patch(Rectangle((-1, FLIP), N + 6 + w, yhi - FLIP, color=POS, alpha=0.05, lw=0))
ax.add_patch(Rectangle((-1, ylo), N + 6 + w, FLIP - ylo, color=NEG, alpha=0.06, lw=0))
right = x0 + w
for _, r in st.iterrows():
    ln = w * abs(r.net_gex) / mx
    ax.add_patch(Rectangle((right - ln, r.strike - h / 2), ln, h, color=POS if r.net_gex > 0 else NEG, alpha=0.85, lw=0))
for _, r in st.reindex(st.net_gex.abs().sort_values(ascending=False).index[:3]).iterrows():
    ax.text(right - w * abs(r.net_gex) / mx - 0.5, r.strike, f"{r.strike:g}", color=TX, fontsize=8, va="center", ha="right")
lines(ax, x0, w)

if SINGLE:
    for (f, a_), name in zip(figs, "ABCD"):
        f.suptitle(f"{sym} 5m {day} · real GEXRadar strike gamma · price {spot}  (orange dotted = price, yellow dashed = flip)",
                   color=TX, fontsize=12)
        f.tight_layout()
        out = os.path.join(ROOT, "reports", "styles", f"gamma_strip_{name}_{sym}.png")
        f.savefig(out, dpi=90, facecolor=BG)
        print(out)
else:
    fig.suptitle(f"{sym} 5m {day} · real GEXRadar strike gamma · price {spot}  (orange dotted = price, yellow dashed = flip)",
                 color=TX, fontsize=12)
    fig.tight_layout()
    out = os.path.join(ROOT, "reports", "styles", f"gamma_strip_options_{sym}.png")
    fig.savefig(out, dpi=80, facecolor=BG)
    print(out, len(st), "strikes")
