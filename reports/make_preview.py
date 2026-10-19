"""Render a TradingView-style preview of the Volume Zones indicator with the heatmap."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import numpy as np, matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Rectangle
import vzones

ROOT = pathlib.Path(__file__).resolve().parent.parent
df = vzones.load_lean_csv(ROOT / "data/spy_hourly_lean.csv.gz").iloc[-30000:]
P = vzones.VZParams(lookback=120, weak_ratio=0.8, break_ratio=1.5, adx_strong=25)
r = vzones.compute(df, P)
t0 = np.flatnonzero(r.hunt.to_numpy() != 0)[-1]
s, e = t0 - 110, t0 + 45
ctx = r.iloc[s - P.lookback:e]                      # history needed for the heatmap
w = r.iloc[s:e].reset_index(drop=True)
lo, hi = w.low.min() * 0.97, w.high.max() * 1.02
edges = np.linspace(lo, hi, 71)
grid, _ = vzones.heatmap(ctx, P.lookback, edges=edges)
grid = grid[P.lookback:]
grid = np.where(grid < 0.30, np.nan, grid)          # only show meaningful liquidity

BG, GR, UP, DN = "#131722", "#2a2e39", "#26a69a", "#ef5350"
cmap = LinearSegmentedColormap.from_list("heat", ["#1e3a5f", "#2a6f97", "#3d8b5a", "#8bbf3c", "#e8c547", "#e8432d"])
cmap.set_bad(alpha=0)
fig = plt.figure(figsize=(16, 9), facecolor=BG)
ax = fig.add_axes([0.03, 0.25, 0.78, 0.68], facecolor=BG)
axv = fig.add_axes([0.03, 0.06, 0.78, 0.17], facecolor=BG, sharex=ax)
axp = fig.add_axes([0.81, 0.25, 0.10, 0.68], facecolor=BG, sharey=ax)
for a in (ax, axv, axp):
    a.tick_params(colors="#b2b5be"); [sp.set_color(GR) for sp in a.spines.values()]
ax.grid(color=GR, lw=.4)
ax.imshow(grid.T, origin="lower", aspect="auto", cmap=cmap, vmin=.3, vmax=1, alpha=.55,
          extent=(-.5, len(w) - .5, lo, hi), interpolation="nearest", zorder=0)
for i in range(len(w)):
    if w.pool_active[i]:
        ax.axvspan(i - .5, i + .5, color="#ffffff", alpha=.06, lw=0)
for i, row in w.iterrows():
    col = "#9598a1" if row.weak_volume else (UP if row.close >= row.open else DN)
    ax.vlines(i, row.low, row.high, color=col, lw=1, zorder=3)
    ax.add_patch(Rectangle((i - .32, min(row.open, row.close)), .64, max(abs(row.close - row.open), .02), color=col, zorder=3))
    axv.bar(i, row.volume, color=col, alpha=.85, width=.7)
axv.plot(range(len(w)), w.volume / w.vol_ratio, color="#f7c948", lw=1); axv.set_yticks([])
axv.text(1, w.volume.max() * .85, "Volume  (gray = WEAK)  ·  yellow = SMA20", color="#b2b5be", fontsize=9)
ax.step(range(len(w)), w.poc, where="mid", color="#ff4d4d", lw=1.6, label="POC", zorder=4)
# up/down split profile at the last bar (like VPVR Up/Down)
k = len(w) - 1
pu, pd_ = vzones.split_profile(r.iloc[s + k - P.lookback:s + k], edges)
mx = (pu + pd_).max(); c = (edges[:-1] + edges[1:]) / 2; hgt = edges[1] - edges[0]
axp.barh(c, pu / mx, height=hgt * .9, color="#2f7fd1")
axp.barh(c, pd_ / mx, left=pu / mx, height=hgt * .9, color="#c9a227")
axp.set_xticks([]); axp.tick_params(labelleft=False)
axp.set_title("VP  Up / Down", color="#b2b5be", fontsize=9)
yr = w.high.max() - w.low.min()
for i, row in w.iterrows():
    if row.hunt:
        d = row.hunt; clr = "#00e676" if d > 0 else "#ff5252"
        ax.annotate("HUNT", (i, row.low - yr * .04 if d > 0 else row.high + yr * .04), color="black", ha="center",
                    fontsize=9, weight="bold", bbox=dict(boxstyle="round", fc=clr, ec="none"), zorder=5)
        ax.hlines(row.target, i, min(i + 30, len(w) - 1), color=clr, ls="--", lw=1.5, zorder=4)
        ax.text(min(i + 30, len(w) - 1), row.target, f"  TARGET {row.target:.2f}", color=clr, va="center", fontsize=9)
    elif row.pool_break:
        ax.scatter(i, row.low - yr * .02 if row.pool_break > 0 else row.high + yr * .02,
                   marker="^" if row.pool_break > 0 else "v", color=UP if row.pool_break > 0 else DN, s=40, zorder=5)
    if row.rejection:
        ax.scatter(i, row.low - yr * .015 if row.rejection > 0 else row.high + yr * .015,
                   color="#00bcd4" if row.rejection > 0 else "#ff9800", s=30, zorder=5)
ax.set_ylim(lo, hi); ax.set_xlim(-.5, len(w) - .5); ax.set_xticks([])
ax.legend(loc="upper left", facecolor=BG, edgecolor=GR, labelcolor="#d1d4dc", fontsize=9)
ax.set_title("SPY · 1H · Volume Zones + Heatmap", color="#d1d4dc", loc="left", fontsize=12)
ax.text(.99, .02, "heatmap: blue→green→yellow→red = more volume traded at that price (last 120 bars)\n"
        "▲▼ weak-pool break   HUNT = break + strong trend + previous zone ahead   ● rejection   gray candles = weak volume",
        transform=ax.transAxes, ha="right", color="#b2b5be", fontsize=8.5, bbox=dict(fc=BG, ec=GR), zorder=6)
fig.savefig(ROOT / "reports/volume_zones_preview.png", dpi=110, facecolor=BG)
