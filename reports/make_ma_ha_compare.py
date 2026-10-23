"""Moving averages on regular vs Heikin Ashi candles, real MSFT 5m bars (runtime/bars), last two sessions.

    python reports/make_ma_ha_compare.py [SYMBOL]
"""
import os
import sys

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sym = sys.argv[1] if len(sys.argv) > 1 else "MSFT"
b = pd.read_csv(os.path.join(ROOT, "runtime", "bars", f"{sym}_5m.csv"))
b.index = pd.to_datetime(b["time"], utc=True).dt.tz_convert("America/New_York")
O, H, L, C = (b[k].to_numpy(float) for k in ("open", "high", "low", "close"))
n = len(b)
hc = (O + H + L + C) / 4
ho = np.empty(n); ho[0] = (O[0] + C[0]) / 2
for i in range(1, n):
    ho[i] = (ho[i - 1] + hc[i - 1]) / 2
hh, hl = np.maximum.reduce([H, ho, hc]), np.minimum.reduce([L, ho, hc])
sma = lambda x, k: pd.Series(x).rolling(k).mean().to_numpy()  # noqa: E731
r20, r100, h20, h100 = sma(C, 20), sma(C, 100), sma(hc, 20), sma(hc, 100)
days = sorted(set(b.index.date))[-2:]
keep = np.flatnonzero([t.date() in days for t in b.index])
s = slice(keep[0], keep[-1] + 1)
x = np.arange(s.stop - s.start)
BG, GR, TX, MUT = "#0b0e14", "#1f2430", "#d1d4dc", "#8a8f9c"
C20, C100 = "#29b6f6", "#ff9100"


def candles(ax, o, h, l, c):
    for i in range(len(o)):
        col = "#26a69a" if c[i] >= o[i] else "#ef5350"
        ax.vlines(i, l[i], h[i], color=col, lw=0.7)
        ax.add_patch(Rectangle((i - 0.3, min(o[i], c[i])), 0.6, max(abs(c[i] - o[i]), 1e-3), color=col))


def style(ax, title):
    ax.set_facecolor(BG); ax.tick_params(colors=MUT, labelsize=9); [sp.set_color(GR) for sp in ax.spines.values()]
    ax.set_title(title, color=TX, fontsize=12, loc="left"); ax.set_xticks([]); ax.yaxis.tick_right()
    ax.legend(facecolor=BG, labelcolor=TX, fontsize=9, loc="upper left")


fig, axs = plt.subplots(3, 1, figsize=(16, 15), facecolor=BG, gridspec_kw={"height_ratios": [1, 1, 0.8]})
ax = axs[0]
candles(ax, O[s], H[s], L[s], C[s])
ax.plot(x, r20[s], color=C20, lw=1.6, label="SMA 20 (real close)")
ax.plot(x, r100[s], color=C100, lw=1.6, label="SMA 100 (real close)")
style(ax, f"1 Â· Regular candles: averages from the real close")
ax = axs[1]
candles(ax, ho[s], hh[s], hl[s], hc[s])
ax.plot(x, h20[s], color=C20, lw=1.6, label="SMA 20 (Heikin Ashi close)")
ax.plot(x, h100[s], color=C100, lw=1.6, label="SMA 100 (Heikin Ashi close)")
style(ax, f"2 Â· Heikin Ashi candles: the same averages from the Heikin Ashi close")
ax = axs[2]
ax.plot(x, C[s], color="#5d6472", lw=0.8, label="real price")
ax.plot(x, r20[s], color=C20, lw=1.6, label="SMA 20 real")
ax.plot(x, h20[s], color=C20, lw=1.6, ls="--", label="SMA 20 Heikin Ashi")
ax.plot(x, r100[s], color=C100, lw=1.6, label="SMA 100 real")
ax.plot(x, h100[s], color=C100, lw=1.6, ls="--", label="SMA 100 Heikin Ashi")
d20, d100 = np.abs(r20[s] - h20[s]), np.abs(r100[s] - h100[s])
style(ax, f"3 Â· Both on one chart: solid = real, dashed = Heikin Ashi   Â·   average gap: SMA 20 {np.nanmean(d20):.2f} (max {np.nanmax(d20):.2f}),  SMA 100 {np.nanmean(d100):.2f} (max {np.nanmax(d100):.2f})")
fig.suptitle(f"{sym} 5m Â· {days[0]} and {days[1]} Â· real bars", color=MUT, fontsize=11)
fig.tight_layout()
out = os.path.join(ROOT, "reports", "styles", f"ma_regular_vs_ha_{sym}.png")
fig.savefig(out, dpi=85, facecolor=BG)
print(out, f"SMA20 gap mean {np.nanmean(d20):.3f} max {np.nanmax(d20):.3f} | SMA100 gap mean {np.nanmean(d100):.3f} max {np.nanmax(d100):.3f}")

