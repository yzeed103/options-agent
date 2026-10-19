"""Render alternative display styles for the Volume Zones indicator (A-D)."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import numpy as np, matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Rectangle, FancyBboxPatch
import vzones
from vzones.indicator import build_profile

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "reports/styles"
df = vzones.load_lean_csv(ROOT / "data/spy_hourly_lean.csv.gz").iloc[-30000:]
P = vzones.VZParams(lookback=120, weak_ratio=0.8, break_ratio=1.5, adx_strong=25)
r = vzones.compute(df, P)
t0 = np.flatnonzero(r.hunt.to_numpy() != 0)[-1]
s, e = t0 - 110, t0 + 45
w = r.iloc[s:e].reset_index(drop=True); N = len(w)
lo, hi = w.low.min() * .97, w.high.max() * 1.02
BG, GR, UP, DN, TX = "#131722", "#2a2e39", "#26a69a", "#ef5350", "#d1d4dc"
yr = w.high.max() - w.low.min()


def base(title, profile_panel=False):
    fig = plt.figure(figsize=(16, 9), facecolor=BG)
    ax = fig.add_axes([0.04, 0.08, 0.82 if profile_panel else 0.90, 0.84], facecolor=BG)
    ax.tick_params(colors="#b2b5be"); [sp.set_color(GR) for sp in ax.spines.values()]
    ax.grid(color=GR, lw=.4); ax.set_xlim(-.5, N + 8); ax.set_ylim(lo, hi); ax.set_xticks([])
    ax.set_title(title, color=TX, loc="left", fontsize=13)
    return fig, ax


def candles(ax, color_fn):
    for i, row in w.iterrows():
        col = color_fn(row)
        ax.vlines(i, row.low, row.high, color=col, lw=1, zorder=3)
        ax.add_patch(Rectangle((i - .32, min(row.open, row.close)), .64, max(abs(row.close - row.open), .02), color=col, zorder=3))


def std_color(row):
    return "#787b86" if row.weak_volume else (UP if row.close >= row.open else DN)


def signals(ax, labels=True):
    for i, row in w.iterrows():
        if row.hunt:
            d = row.hunt; c = "#00e676" if d > 0 else "#ff5252"
            ax.annotate("HUNT ▲" if d > 0 else "HUNT ▼", (i, row.low - yr * .045 if d > 0 else row.high + yr * .045),
                        color="black", ha="center", fontsize=9, weight="bold", bbox=dict(boxstyle="round", fc=c, ec="none"), zorder=6)
            ax.annotate("", xy=(i + 25, row.target), xytext=(i, row.close), zorder=5,
                        arrowprops=dict(arrowstyle="->", color=c, lw=1.6, ls="--"))
            ax.text(i + 26, row.target, f" TARGET {row.target:.2f}", color=c, va="center", fontsize=9, weight="bold")
        elif row.pool_break and labels:
            ax.scatter(i, row.low - yr * .02 if row.pool_break > 0 else row.high + yr * .02,
                       marker="^" if row.pool_break > 0 else "v", color=UP if row.pool_break > 0 else DN, s=45, zorder=5)
        if row.rejection and labels:
            ax.scatter(i, row.low - yr * .015 if row.rejection > 0 else row.high + yr * .015,
                       color="#00bcd4" if row.rejection > 0 else "#ff9800", s=30, zorder=5)


def pools_as_boxes(ax, color="#9598a1"):
    i = 0
    while i < N:
        if w.pool_active[i]:
            j = i
            while j + 1 < N and w.pool_active[j + 1]:
                j += 1
            ph, pl = w.high[i:j + 1].max(), w.low[i:j + 1].min()
            ax.add_patch(Rectangle((i - .5, pl), j - i + 1, ph - pl, fill=False, ec=color, ls=":", lw=1.2, zorder=4))
            ax.text(i - .3, ph, "weak pool", color=color, fontsize=7, va="bottom")
            i = j + 1
        else:
            i += 1


# ------------------------------------------------------------------ A: clean zones
fig, ax = base("A · Clean Zones: top-3 volume zones only, ranked, with strength %")
prof = build_profile(r.high.iloc[t0 - 120:e], r.low.iloc[t0 - 120:e], r.volume.iloc[t0 - 120:e], 40, .7, 1.5, .5, 6)
prof_old = build_profile(r.high.iloc[s - 120:s + 60], r.low.iloc[s - 120:s + 60], r.volume.iloc[s - 120:s + 60], 40, .7, 1.5, .5, 6)
zones = sorted(set(prof.hvn + prof_old.hvn), key=lambda z: -z[2])[:3]
tot = sum(z[2] for z in zones)
for rank, (zl, zh, zv) in enumerate(zones, 1):
    c = ["#e8432d", "#e8a33d", "#e8d547"][rank - 1]
    ax.add_patch(Rectangle((-.5, zl), N + 8, zh - zl, color=c, alpha=.13, lw=0, zorder=1))
    ax.hlines([zl, zh], -.5, N + 8, color=c, lw=.8, alpha=.7, zorder=1)
    ax.text(N + 7.5, (zl + zh) / 2, f"#{rank}  {zv / tot * 100:.0f}%\n{zl:.1f}-{zh:.1f}", color=c, ha="right",
            va="center", fontsize=9, weight="bold")
candles(ax, std_color); signals(ax)
ax.plot(range(N), w.poc, color="#ff4d4d", lw=1.2, ls="-", label="POC", zorder=4)
ax.legend(loc="upper left", facecolor=BG, edgecolor=GR, labelcolor=TX)
fig.savefig(OUT / "A_clean_zones.png", dpi=100, facecolor=BG); plt.close(fig)

# ------------------------------------------------------------------ B: liquidity lines (Bookmap-like)
fig, ax = base("B · Liquidity Lines: thin heat strips per bar (like the BTC reference), only strong levels", True)
edges = np.linspace(lo, hi, 90)
ctx = r.iloc[s - 120:e]
g, _ = vzones.heatmap(ctx, 120, edges=edges); g = g[120:]
cmap = LinearSegmentedColormap.from_list("h", ["#163a4a", "#1f6f6f", "#3f9a3f", "#a6c63a", "#f0c419", "#e8432d"])
hgt = edges[1] - edges[0]
for i in range(N):
    for k in np.flatnonzero(g[i] >= .35):
        ax.add_patch(Rectangle((i - .45, edges[k] + hgt * .15), .9, hgt * .7, color=cmap((g[i, k] - .35) / .65), alpha=.85, lw=0, zorder=1))
candles(ax, lambda row: "#9598a1" if row.weak_volume else ("#3ddc97" if row.close >= row.open else "#ff5a5f")); signals(ax)
axp = fig.add_axes([0.86, 0.08, 0.10, 0.84], facecolor=BG, sharey=ax); axp.axis("off")
pu, pd_ = vzones.split_profile(r.iloc[e - 120:e], edges); mx = (pu + pd_).max(); c = (edges[:-1] + edges[1:]) / 2
axp.barh(c, pu / mx, height=hgt * .85, color="#2f7fd1"); axp.barh(c, pd_ / mx, left=pu / mx, height=hgt * .85, color="#c9a227")
fig.savefig(OUT / "B_liquidity_lines.png", dpi=100, facecolor=BG); plt.close(fig)

# ------------------------------------------------------------------ C: signal dashboard
fig, ax = base("C · Signal Dashboard: volume-regime candles + zone boxes + status table")
for lo_, hi_, v_ in prof.hvn:
    ax.add_patch(Rectangle((-.5, lo_), N + 8, hi_ - lo_, fill=True, fc="#2962ff", alpha=.08, ec="#2962ff", lw=.8, zorder=1))
def regime_color(row):
    if row.vol_ratio >= 1.5: return "#00e676" if row.close >= row.open else "#ff1744"
    if row.weak_volume: return "#4a4e5a"
    return UP if row.close >= row.open else DN
candles(ax, regime_color); pools_as_boxes(ax); signals(ax, labels=True)
last = w.iloc[t0 - s + 1]
rows_ = [("Trend", "STRONG UP" if last.strong_trend > 0 else "UP" if last.trend_dir > 0 else "DOWN" if last.trend_dir < 0 else "RANGE", "#00e676"),
         ("ADX", f"{last.adx:.0f}", TX), ("Volume", f"{last.vol_ratio:.2f}x  " + ("WEAK" if last.weak_volume else "OK"), "#f0c419"),
         ("In zone", "HVN" if last.in_hvn else "LVN (fast move)" if last.in_lvn else "-", TX),
         ("Zone above", f"{last.hvn_above:.2f}", "#ff9800"), ("Zone below", f"{last.hvn_below:.2f}", "#00bcd4"),
         ("Signal", "HUNT → %.2f" % w.target[t0 - s], "#00e676")]
x0, y0 = .80, .97
ax.add_patch(FancyBboxPatch((x0 - .01, y0 - .045 * len(rows_) - .01), .2, .045 * len(rows_) + .02, transform=ax.transAxes,
                            boxstyle="round,pad=0.005", fc="#1e222d", ec=GR, zorder=7))
for k, (a, b, c) in enumerate(rows_):
    ax.text(x0, y0 - .045 * k - .03, a, transform=ax.transAxes, color="#9598a1", fontsize=9, zorder=8)
    ax.text(x0 + .185, y0 - .045 * k - .03, b, transform=ax.transAxes, color=c, fontsize=9, ha="right", weight="bold", zorder=8)
ax.text(.01, .02, "bright candle = volume ≥1.5x avg   dark candle = weak volume   dotted box = weak pool",
        transform=ax.transAxes, color="#9598a1", fontsize=9)
fig.savefig(OUT / "C_dashboard.png", dpi=100, facecolor=BG); plt.close(fig)

# ------------------------------------------------------------------ D: session profiles
fig, ax = base("D · Session Profiles: one mini volume profile per block of 20 bars + naked POCs extended")
blk = 20; edges = np.linspace(lo, hi, 50); hgt = edges[1] - edges[0]; c = (edges[:-1] + edges[1:]) / 2
naked = []
for b0 in range(0, N, blk):
    seg = w.iloc[b0:b0 + blk]
    pu, pd_ = vzones.split_profile(seg, edges); tot = pu + pd_
    if tot.max() == 0: continue
    sc = (blk * .8) / tot.max()
    for k in np.flatnonzero(tot > 0):
        ax.add_patch(Rectangle((b0 - .5, edges[k]), pu[k] * sc, hgt * .9, color="#2f7fd1", alpha=.35, lw=0, zorder=1))
        ax.add_patch(Rectangle((b0 - .5 + pu[k] * sc, edges[k]), pd_[k] * sc, hgt * .9, color="#c9a227", alpha=.35, lw=0, zorder=1))
    poc = c[tot.argmax()]; naked.append((b0, poc))
    ax.axvline(b0 - .5, color=GR, lw=.8)
for b0, poc in naked:
    later = w.iloc[b0 + blk:]
    touched = ((later.low <= poc) & (later.high >= poc)).to_numpy()
    end = b0 + blk + (np.argmax(touched) if touched.any() else N + 8 - b0 - blk)
    ax.hlines(poc, b0, end, color="#ff4d4d", lw=1.2, ls="-" if not touched.any() else ":", zorder=2)
    if not touched.any(): ax.text(N + 7.5, poc, f"naked POC {poc:.1f}", color="#ff4d4d", ha="right", va="bottom", fontsize=8)
candles(ax, std_color); signals(ax)
fig.savefig(OUT / "D_session_profiles.png", dpi=100, facecolor=BG); plt.close(fig)
print("ok")
