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


# ------------------------------------------------------------------ E: combined A + C (+ optional B heat)
def combined(with_heat, fname):
    fig, ax = base("SPY · 1H · Volume Zones" + ("  ·  heatmap ON" if with_heat else ""))
    if with_heat:
        for i in range(N):
            for k in np.flatnonzero(g[i] >= .45):
                ax.add_patch(Rectangle((i - .45, edges_b[k] + hgt_b * .15), .9, hgt_b * .7,
                                       color=cmap((g[i, k] - .35) / .65), alpha=.45, lw=0, zorder=1))
    for rank, (zl, zh, zv) in enumerate(zones, 1):
        c = ["#e8432d", "#e8a33d", "#e8d547"][rank - 1]
        ax.add_patch(Rectangle((-.5, zl), N + 8, zh - zl, color=c, alpha=.05 if with_heat else .11, lw=0, zorder=1))
        ax.hlines([zl, zh], -.5, N + 8, color=c, lw=.9, alpha=.8, zorder=2)
        ax.text(N + 7.5, zh, f"#{rank}  {zv / tot * 100:.0f}%  {zl:.1f}-{zh:.1f}", color=c, ha="right",
                va="bottom", fontsize=9, weight="bold", zorder=6)
    candles(ax, regime_color); pools_as_boxes(ax); signals(ax)
    pc = w.poc.to_numpy().copy(); pc[1:][np.abs(np.diff(pc)) > yr * .1] = np.nan
    ax.step(range(N), pc, where="mid", color="#ff4d4d", lw=1, alpha=.8, zorder=4)
    x0, y0 = .80, .36
    ax.add_patch(FancyBboxPatch((x0 - .01, y0 - .045 * len(rows_) - .01), .2, .045 * len(rows_) + .02, transform=ax.transAxes,
                                boxstyle="round,pad=0.005", fc="#1e222d", ec=GR, zorder=7))
    for k, (a, b, c) in enumerate(rows_):
        ax.text(x0, y0 - .045 * k - .03, a, transform=ax.transAxes, color="#9598a1", fontsize=9, zorder=8)
        ax.text(x0 + .185, y0 - .045 * k - .03, b, transform=ax.transAxes, color=c, fontsize=9, ha="right", weight="bold", zorder=8)
    ax.text(.01, .965, "bright candle = volume ≥1.5x   dark = weak   dotted box = weak pool   #1-#3 = strongest volume zones   red line = POC",
            transform=ax.transAxes, color="#9598a1", fontsize=9, zorder=8, bbox=dict(fc=BG, ec=GR, alpha=.9))
    fig.savefig(OUT / fname, dpi=100, facecolor=BG); plt.close(fig)


edges_b = np.linspace(lo, hi, 90); hgt_b = edges_b[1] - edges_b[0]
g, _ = vzones.heatmap(r.iloc[s - 120:e], 120, edges=edges_b); g = g[120:]
tot = sum(z[2] for z in zones)
combined(False, "E_combined.png")
combined(True, "E_combined_heat.png")
print("ok2")


# ------------------------------------------------------------------ F: heatmap themes
from scipy.ndimage import gaussian_filter
from matplotlib.colors import to_rgba
THEMES = {
    "F1_thermal":   dict(name="Thermal (inferno)", colors=["#1b0c41", "#6a176e", "#c73e4c", "#f98c0a", "#fcffa4"], mode="smooth"),
    "F2_ice":       dict(name="Ice / Bookmap blue", colors=["#0b1f3a", "#0f4c75", "#1fa2c7", "#7fe3ff", "#ffffff"], mode="smooth"),
    "F3_tv_vpvr":   dict(name="TradingView VPVR (teal → gold)", colors=["#1d4f5a", "#2b7a78", "#3aa59a", "#c9a227", "#f2d16b"], mode="strips"),
    "F4_contours":  dict(name="Contours only (outline of liquidity)", colors=["#5d6aa8", "#9b7ff2", "#f2c14e", "#ff5d5d"], mode="contour"),
    "F5_purple":    dict(name="Mono purple fade (alpha = volume)", colors=["#b388ff"], mode="alpha"),
    "F6_dots":      dict(name="Liquidity dots (size + color = volume)", colors=["#2a6f97", "#3d8b5a", "#e8c547", "#e8432d"], mode="dots"),
}
edges_f = np.linspace(lo, hi, 120); hgt_f = edges_f[1] - edges_f[0]
gf, _ = vzones.heatmap(r.iloc[s - 120:e], 120, edges=edges_f); gf = np.nan_to_num(gf[120:])


def themed(key, th):
    fig, ax = base(f"Heatmap theme · {th['name']}")
    cm = LinearSegmentedColormap.from_list(key, th["colors"] if len(th["colors"]) > 1 else ["#000000", th["colors"][0]])
    ext = (-.5, N - .5, lo, hi)
    if th["mode"] == "smooth":
        sm = gaussian_filter(gf, (1.0, 1.2)); img = cm(sm.T); img[..., 3] = np.clip((sm.T - .25) / .75, 0, 1) * .75
        ax.imshow(img, origin="lower", aspect="auto", extent=ext, interpolation="bilinear", zorder=0)
    elif th["mode"] == "strips":
        for i in range(N):
            for k in np.flatnonzero(gf[i] >= .4):
                ax.add_patch(Rectangle((i - .45, edges_f[k] + hgt_f * .2), .9, hgt_f * .6, color=cm((gf[i, k] - .4) / .6), alpha=.6, lw=0, zorder=1))
    elif th["mode"] == "contour":
        X, Y = np.meshgrid(np.arange(N), (edges_f[:-1] + edges_f[1:]) / 2)
        ax.contour(X, Y, gaussian_filter(gf, 1.2).T, levels=[.4, .6, .8, .95], colors=th["colors"], linewidths=[.8, 1, 1.3, 1.8], zorder=1)
    elif th["mode"] == "alpha":
        rgba = np.zeros((*gf.T.shape, 4)); rgba[..., :3] = to_rgba(th["colors"][0])[:3]
        rgba[..., 3] = np.clip((gaussian_filter(gf, .8).T - .3) / .7, 0, 1) ** 1.5 * .7
        ax.imshow(rgba, origin="lower", aspect="auto", extent=ext, interpolation="bilinear", zorder=0)
    elif th["mode"] == "dots":
        for i in range(0, N, 2):
            ks = np.flatnonzero(gf[i] >= .5)[::2]
            ax.scatter(np.full(len(ks), i), edges_f[ks] + hgt_f / 2, s=(gf[i, ks] ** 3) * 28, c=[cm((v - .5) / .5) for v in gf[i, ks]], alpha=.75, lw=0, zorder=1)
    for rank, (zl, zh, zv) in enumerate(zones, 1):
        c = ["#e8432d", "#e8a33d", "#e8d547"][rank - 1]
        ax.hlines([zl, zh], -.5, N + 8, color=c, lw=.9, alpha=.8, zorder=2)
        ax.text(N + 7.5, zh, f"#{rank}  {zv / tot * 100:.0f}%", color=c, ha="right", va="bottom", fontsize=9, weight="bold", zorder=6)
    candles(ax, regime_color); signals(ax, labels=False)
    # colour scale legend
    cax = fig.add_axes([0.06, 0.885, 0.18, 0.012]); cax.imshow(np.linspace(0, 1, 256)[None], aspect="auto", cmap=cm); cax.set_axis_off()
    fig.text(0.06, 0.902, "low volume", color="#9598a1", fontsize=8); fig.text(0.24, 0.902, "high", color="#9598a1", fontsize=8, ha="right")
    fig.savefig(OUT / f"{key}.png", dpi=100, facecolor=BG); plt.close(fig)


for k, th in THEMES.items():
    themed(k, th)
# contact sheet
from matplotlib.image import imread
fig, axs = plt.subplots(3, 2, figsize=(16, 13.5), facecolor=BG)
for a, k in zip(axs.flat, THEMES):
    a.imshow(imread(OUT / f"{k}.png")[30:860, 40:1520]); a.set_axis_off()
    a.set_title(f"{k.split('_')[0]} · {THEMES[k]['name']}", color=TX, fontsize=12)
fig.tight_layout(); fig.savefig(OUT / "F_all_themes.png", dpi=90, facecolor=BG)
print("ok3")


# ------------------------------------------------------------------ G: ten more heatmap styles
ctxg = r.iloc[s - 120:e]
upm = (ctxg.close >= ctxg.open).astype(float)
def _raw(dfx):
    gg, _ = vzones.heatmap(dfx, 120, edges=edges_f); return gg
# un-normalised buy / sell heat (normalise jointly)
cu = ctxg.assign(volume=ctxg.volume * upm); cd = ctxg.assign(volume=ctxg.volume * (1 - upm))
hb = np.nan_to_num(_raw(cu))[120:]; hs = np.nan_to_num(_raw(cd))[120:]
# rescale both to joint max per bar using raw ratio
tot_b = hb + hs
G = {
    "G01_neon":      dict(name="Neon (magenta → cyan)", colors=["#2b0b3f", "#8a1c7c", "#ff2bd6", "#36e2ff", "#e8fdff"], mode="smooth"),
    "G02_fire":      dict(name="Fire blocks", colors=["#3a0d0d", "#8c1c13", "#e2481b", "#ffa630", "#fff1a8"], mode="cells"),
    "G03_emerald":   dict(name="Emerald mono", colors=["#062a1e", "#0b6e4f", "#21c48b", "#b8ffe0"], mode="smooth"),
    "G04_viridis":   dict(name="Viridis pixel grid", colors=["#440154", "#3b528b", "#21918c", "#5ec962", "#fde725"], mode="cells"),
    "G05_lines":     dict(name="Thickness lines (Pine-friendly)", colors=["#4f6d8f", "#8fb3d9", "#ffd166"], mode="lines"),
    "G06_ridge":     dict(name="Ridge: top 3 rows per bar only (POC trail)", colors=["#7f5af0", "#ff8906", "#f25f4c"], mode="ridge"),
    "G07_buysell":   dict(name="Buy / Sell dominance (blue buy, orange sell)", colors=[], mode="buysell"),
    "G08_delta":     dict(name="Delta heat (green = buyers, red = sellers)", colors=[], mode="delta"),
    "G09_fog":       dict(name="White fog (minimal grayscale)", colors=["#131722", "#3a3f4f", "#9aa0ad", "#ffffff"], mode="smooth"),
    "G10_shadow":    dict(name="Shadow profile (current VP projected left, fading)", colors=["#2962ff"], mode="shadow"),
}


def themed2(key, th):
    fig, ax = base(f"Heatmap · {key.split('_')[0]} · {th['name']}")
    ext = (-.5, N - .5, lo, hi); cm = None
    if th["colors"]:
        cm = LinearSegmentedColormap.from_list(key, th["colors"] if len(th["colors"]) > 1 else ["#000", th["colors"][0]])
    m = th["mode"]; yc = (edges_f[:-1] + edges_f[1:]) / 2
    if m == "smooth":
        sm = gaussian_filter(gf, (1.0, 1.2)); img = cm(sm.T); img[..., 3] = np.clip((sm.T - .25) / .75, 0, 1) * .75
        ax.imshow(img, origin="lower", aspect="auto", extent=ext, interpolation="bilinear", zorder=0)
    elif m == "cells":
        q = gf.reshape(N, 30, 4).mean(axis=2) if gf.shape[1] % 4 == 0 else gf
        img = cm(q.T); img[..., 3] = np.where(q.T >= .35, .7, 0)
        ax.imshow(img, origin="lower", aspect="auto", extent=ext, interpolation="nearest", zorder=0)
        for xg in range(0, N, 3): ax.axvline(xg - .5, color=BG, lw=.6, zorder=0.5)
        for yg in np.linspace(lo, hi, 31): ax.axhline(yg, color=BG, lw=.6, zorder=0.5)
    elif m == "lines":
        for k in range(0, len(yc), 2):
            col = gf[:, k]
            for i in range(N - 1):
                if col[i] >= .4:
                    ax.plot([i - .5, i + .5], [yc[k], yc[k]], color=cm((col[i] - .4) / .6), lw=.5 + 3.5 * (col[i] - .4) / .6, alpha=.8, solid_capstyle="butt", zorder=1)
    elif m == "ridge":
        for i in range(N):
            top = np.argsort(gf[i])[-3:]
            for rank_, k in enumerate(top):
                ax.add_patch(Rectangle((i - .5, edges_f[k]), 1, hgt_f * 1.6, color=th["colors"][rank_], alpha=.55, lw=0, zorder=1))
    elif m in ("buysell", "delta"):
        tot_ = hb + hs; mx = tot_.max(axis=1, keepdims=True); mx[mx == 0] = 1
        inten = gaussian_filter(tot_ / mx, (1, 1)); share = np.where(tot_ > 0, hb / np.maximum(tot_, 1e-9), .5)
        share = gaussian_filter(share, (1, 1.5))
        if m == "buysell":
            cmb = LinearSegmentedColormap.from_list("bs", ["#ff9f1c", "#5a5a6a", "#2f7fd1"])
        else:
            cmb = LinearSegmentedColormap.from_list("dl", ["#ff1744", "#3a3f4f", "#00e676"])
        img = cmb(np.clip((share.T - .5) * 2.5 + .5, 0, 1)); img[..., 3] = np.clip((inten.T - .3) / .7, 0, 1) * .8
        ax.imshow(img, origin="lower", aspect="auto", extent=ext, interpolation="bilinear", zorder=0)
        cm = cmb
    elif m == "shadow":
        vp = gf[-1]
        for k in np.flatnonzero(vp >= .25):
            ln = vp[k] * N * .9
            xs = np.linspace(N - .5 - ln, N - .5, 40)
            for a0, a1 in zip(xs[:-1], xs[1:]):
                frac = (a1 - xs[0]) / ln
                ax.add_patch(Rectangle((a0, edges_f[k]), a1 - a0, hgt_f * .85, color="#2962ff" if vp[k] < .8 else "#ff4d4d", alpha=.05 + .45 * frac * vp[k], lw=0, zorder=1))
        cm = LinearSegmentedColormap.from_list("sh", ["#131722", "#2962ff", "#ff4d4d"])
    for rank, (zl, zh, zv) in enumerate(zones, 1):
        c = ["#e8432d", "#e8a33d", "#e8d547"][rank - 1]
        ax.hlines([zl, zh], -.5, N + 8, color=c, lw=.9, alpha=.8, zorder=2)
        ax.text(N + 7.5, zh, f"#{rank}  {zv / tot * 100:.0f}%", color=c, ha="right", va="bottom", fontsize=9, weight="bold", zorder=6)
    candles(ax, regime_color); signals(ax, labels=False)
    cax = fig.add_axes([0.06, 0.885, 0.18, 0.012]); cax.imshow(np.linspace(0, 1, 256)[None], aspect="auto", cmap=cm); cax.set_axis_off()
    lab = ("sellers", "buyers") if m in ("buysell", "delta") else ("low volume", "high")
    fig.text(0.06, 0.902, lab[0], color="#9598a1", fontsize=8); fig.text(0.24, 0.902, lab[1], color="#9598a1", fontsize=8, ha="right")
    fig.savefig(OUT / f"{key}.png", dpi=100, facecolor=BG); plt.close(fig)


for k, th in G.items():
    themed2(k, th)
for part, keys in (("G_sheet_1.png", list(G)[:6]), ("G_sheet_2.png", list(G)[6:])):
    rows_n = (len(keys) + 1) // 2
    fig, axs = plt.subplots(rows_n, 2, figsize=(16, 4.5 * rows_n), facecolor=BG)
    for a in axs.flat: a.set_axis_off()
    for a, k in zip(axs.flat, keys):
        a.imshow(imread(OUT / f"{k}.png")[30:860, 40:1520]); a.set_title(f"{k.split('_')[0]} · {G[k]['name']}", color=TX, fontsize=12)
    fig.tight_layout(); fig.savefig(OUT / part, dpi=90, facecolor=BG); plt.close(fig)
print("ok4")


# ------------------------------------------------------------------ H: recommended = viridis strips, no smoothing
def recommended(with_delta, fname):
    fig, ax = base("SPY · 1H · Volume Zones  ·  heatmap: Viridis strips (no smoothing)" + ("  +  delta layer" if with_delta else ""))
    vir = LinearSegmentedColormap.from_list("vir", ["#440154", "#3b528b", "#21918c", "#5ec962", "#fde725"])
    thr = .40
    for i in range(N):
        for k in np.flatnonzero(gf[i] >= thr):
            ax.add_patch(Rectangle((i - .45, edges_f[k] + hgt_f * .18), .9, hgt_f * .64,
                                   color=vir((gf[i, k] - thr) / (1 - thr)), alpha=.40 if with_delta else .70, lw=0, zorder=1))
    if with_delta:
        tot_ = hb + hs; mx = tot_.max(axis=1, keepdims=True); mx[mx == 0] = 1
        inten = tot_ / mx; share = np.where(tot_ > 0, hb / np.maximum(tot_, 1e-9), .5)
        for i in range(N):
            for k in np.flatnonzero(inten[i] >= .55):
                d = share[i, k] - .5
                if abs(d) < .12: continue
                ax.add_patch(Rectangle((i - .45, edges_f[k] + hgt_f * .18), .9, hgt_f * .64,
                                       color="#00e676" if d > 0 else "#ff1744", alpha=min(.75, abs(d) * 2), lw=0, zorder=1.5))
    for rank, (zl, zh, zv) in enumerate(zones, 1):
        c = ["#e8432d", "#e8a33d", "#e8d547"][rank - 1]
        ax.hlines([zl, zh], -.5, N + 8, color=c, lw=.9, alpha=.85, zorder=2)
        ax.text(N + 7.5, zh, f"#{rank}  {zv / tot * 100:.0f}%  {zl:.1f}-{zh:.1f}", color=c, ha="right", va="bottom", fontsize=9, weight="bold", zorder=6)
    candles(ax, regime_color); pools_as_boxes(ax); signals(ax)
    pc = w.poc.to_numpy().copy(); pc[1:][np.abs(np.diff(pc)) > yr * .1] = np.nan
    ax.step(range(N), pc, where="mid", color="#ff4d4d", lw=1, alpha=.8, zorder=4)
    x0, y0 = .80, .36
    ax.add_patch(FancyBboxPatch((x0 - .01, y0 - .045 * len(rows_) - .01), .2, .045 * len(rows_) + .02, transform=ax.transAxes,
                                boxstyle="round,pad=0.005", fc="#1e222d", ec=GR, zorder=7))
    for k, (a, b, c) in enumerate(rows_):
        ax.text(x0, y0 - .045 * k - .03, a, transform=ax.transAxes, color="#9598a1", fontsize=9, zorder=8)
        ax.text(x0 + .185, y0 - .045 * k - .03, b, transform=ax.transAxes, color=c, fontsize=9, ha="right", weight="bold", zorder=8)
    # legend in empty lower-left area
    lx, ly = .015, .03
    ax.add_patch(FancyBboxPatch((lx - .005, ly - .01), .30 if not with_delta else .36, .13 if not with_delta else .17, transform=ax.transAxes,
                                boxstyle="round,pad=0.005", fc="#1e222d", ec=GR, zorder=7))
    cax = fig.add_axes([0.04 + lx * .9 + .005, 0.08 + (ly + .085) * .84, 0.18, 0.012]); cax.imshow(np.linspace(0, 1, 256)[None], aspect="auto", cmap=vir); cax.set_axis_off(); cax.set_zorder(9)
    ax.text(lx, ly + .065, "less volume  →  more volume (last 120 bars)", transform=ax.transAxes, color="#b2b5be", fontsize=8.5, zorder=8)
    ax.text(lx, ly + .025, "bright candle = strong vol   dark = weak   dotted = weak pool", transform=ax.transAxes, color="#9598a1", fontsize=8, zorder=8)
    if with_delta:
        ax.text(lx, ly + .105, "■", transform=ax.transAxes, color="#00e676", fontsize=10, zorder=8)
        ax.text(lx + .015, ly + .105, "buyers dominate", transform=ax.transAxes, color="#b2b5be", fontsize=8.5, zorder=8)
        ax.text(lx + .14, ly + .105, "■", transform=ax.transAxes, color="#ff1744", fontsize=10, zorder=8)
        ax.text(lx + .155, ly + .105, "sellers dominate", transform=ax.transAxes, color="#b2b5be", fontsize=8.5, zorder=8)
    fig.savefig(OUT / fname, dpi=110, facecolor=BG); plt.close(fig)


recommended(False, "H_recommended.png")
recommended(True, "H_recommended_delta.png")
print("ok5")
