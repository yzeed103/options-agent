import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd, matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from vzones.intraday.data import load_csv, rth
from vzones.intraday.features import add_features
from vzones.intraday.engine import Exec, run
from vzones.intraday.whale_features import add_whale_levels, whale_bounce, K
from vzones.whale_levels import find_ranges, profile_levels, AGG
ROOT = pathlib.Path(__file__).resolve().parent.parent
LV = tuple(f"wl_{k}" for k in range(K))
best = None
for sym in ("UNH", "HOOD", "INTU"):
    d = add_whale_levels(add_features(rth(load_csv(ROOT / f"data/intraday/{sym}_15m.csv"))), specs=(("1D", 20, 6.0),))
    sig = whale_bounce(d)
    tr = run(d, sig, Exec(stop_atr=1.0, target="levels", level_cols=LV, min_target_r=3.0, overnight=True, max_bars=130, cost=0.0001))
    w = tr[(tr.r > 2.5) & (tr.bars < 60)]
    if len(w):
        t = w.iloc[-1]; best = (sym, d, sig, t); break
sym, d, sig, t = best
e = d.index.get_loc(t.entry_time); x = d.index.get_loc(t.exit_time); s_i = e - 1
lv = sorted(v for v in d.loc[d.index[s_i], list(LV)].to_numpy() if np.isfinite(v))
# find the range that produced these levels
raw = d[["open", "high", "low", "close", "volume"]].copy(); raw.index = raw.index.tz_localize(None)
daily = raw.resample("1D").agg(AGG).dropna()
rgs = [r for r in find_ranges(daily, 20, 6.0) if r[2] < d.index[s_i].tz_localize(None).normalize()]
s0, e0, brk, hi, lo = rgs[-1]
bars = raw[(raw.index >= s0) & (raw.index < daily.index[daily.index.get_loc(e0) + 1])]
_, _, cen, prof = profile_levels(bars); poc = cen[int(np.argmax(prof))]
a = d.index.get_indexer([d.index[d.index.tz_localize(None) >= s0][0]])[0]
w = d.iloc[a:x + 25]; X = np.arange(len(w)); si, ei, xi = s_i - a, e - a, x - a
bi = len(bars)
BG, GR, TX, MUT, UP, DN = "#131722", "#2a2e39", "#d1d4dc", "#8a8f9c", "#26a69a", "#ef5350"
fig = plt.figure(figsize=(18, 9.5), facecolor=BG)
ax = fig.add_axes([0.04, 0.07, 0.86, 0.84], facecolor=BG)
ax.tick_params(colors=MUT); [q.set_color(GR) for q in ax.spines.values()]; ax.grid(color=GR, lw=.3)
ax.add_patch(Rectangle((-.5, lo), bi, hi - lo, fill=True, fc="#ffb020", alpha=.04, ec="#ffb020", ls="--", lw=1.3))
ax.text(1, hi, " آخر منطقة عرضية على اليومي", color="#ffb020", fontsize=11, va="bottom")
for i, r in enumerate(w.itertuples()):
    cc = UP if r.close >= r.open else DN
    ax.vlines(i, r.low, r.high, color=cc, lw=.6)
    ax.add_patch(Rectangle((i - .35, min(r.open, r.close)), .7, max(abs(r.close - r.open), 1e-3), color=cc, lw=0))
for L in lv:
    isp = abs(L - poc) <= (cen[1] - cen[0]) * 3
    ax.hlines(L, -.5, len(w) + 40, color="#ff3b3b" if isp else "#9b5cff", lw=2 if isp else 1, zorder=2)
    ax.text(len(w) + 41, L, f"{L:.2f}" + (" POC" if isp else ""), color="#ff3b3b" if isp else "#9b5cff", fontsize=9, va="center")
dr = int(t.dir); col = "#00e5ff" if dr > 0 else "#ff9100"
y0 = w.low.iat[si] if dr > 0 else w.high.iat[si]; yr = w.high.max() - w.low.min()
ax.annotate("حوت ↑" if dr > 0 else "حوت ↓", xy=(si, y0), xytext=(si, y0 + (-1 if dr > 0 else 1) * .07 * yr), ha="center",
            va="top" if dr > 0 else "bottom", fontsize=11, weight="bold", color="black", bbox=dict(boxstyle="round,pad=.35", fc=col, ec=col),
            arrowprops=dict(arrowstyle="-|>", color=col), zorder=7)
stop = t.entry - dr * 1.0 * d.atr.iat[s_i]; tgt = t.exit
ax.hlines(tgt, si, si + 30, color=col, lw=2.2, ls="--", zorder=5); ax.text(si - 2, tgt + .015 * yr, f"هدف الحوت {tgt:.2f} ", color=col, fontsize=11, va="bottom", ha="right", weight="bold", bbox=dict(fc=BG, ec="none", pad=1))
ax.hlines(stop, si, si + 30, color="#9aa0ad", lw=1.2, ls=":", zorder=5); ax.text(si + 31, stop, f" الوقف {stop:.2f}", color="#9aa0ad", fontsize=9, va="center")
ax.scatter(xi, tgt, s=90, color=col, zorder=8, marker="*"); ax.text(xi + 2, tgt + (.05 if dr > 0 else -.05) * yr, "وصل الهدف", color=col, fontsize=10, ha="center")
ax.set_xlim(-2, len(w) + 52); ax.set_ylim(w.low.min() - .12 * yr, w.high.max() + .1 * yr)
ticks = [0, bi, si, len(w) - 1]; ax.set_xticks(ticks); ax.set_xticklabels([f"{w.index[k]:%m-%d}" for k in ticks], color=MUT)
ax.set_title(f"{sym} · 15m · مستويات الحيتان وإشارة ارتداد الحوت", color=TX, fontsize=14, loc="right")
ax.text(.01, .97, "الأحمر = أعلى فوليوم POC    البنفسجي = باقي الأعمدة الطويلة    الخط المتقطع = الهدف    المنقط = الوقف",
        transform=ax.transAxes, color=MUT, fontsize=10, va="top")
fig.savefig(ROOT / "reports/styles/P_whale_bounce_preview.png", dpi=100, facecolor=BG); print("ok", sym, t.entry_time, round(t.r, 2))
