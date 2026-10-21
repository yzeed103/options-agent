import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd, matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from vzones.whale_levels import find_ranges, profile_levels, AGG
from vzones.intraday.data import load_csv, rth
ROOT = pathlib.Path(__file__).resolve().parent.parent
m = rth(load_csv(ROOT / "data/intraday/SPY_15m.csv")); m.index = m.index.tz_localize(None)
d = m.resample("1D").agg(AGG).dropna()
rs = find_ranges(d, 20, 6.0); s, e, brk, hi, lo = rs[-1]
bars = m[(m.index >= s) & (m.index <= e + pd.Timedelta(days=1))]
peaks, valleys, cen, prof = profile_levels(bars)
w = d[d.index >= s - pd.Timedelta(days=20)]
BG, GR, TX, MUT, UP, DN = "#131722", "#2a2e39", "#d1d4dc", "#8a8f9c", "#26a69a", "#ef5350"
fig = plt.figure(figsize=(17, 9), facecolor=BG)
ax = fig.add_axes([0.04, 0.08, 0.78, 0.82], facecolor=BG); ap = fig.add_axes([0.82, 0.08, 0.15, 0.82], facecolor=BG, sharey=ax)
for z in (ax, ap): z.tick_params(colors=MUT); [q.set_color(GR) for q in z.spines.values()]
ax.grid(color=GR, lw=.4)
x = np.arange(len(w)); i0 = w.index.get_loc(s); i1 = w.index.get_loc(e)
ax.add_patch(Rectangle((i0 - .5, lo), i1 - i0 + 1, hi - lo, fill=False, ec="#ffb020", lw=1.5, ls="--"))
ax.text(i0, hi, " آخر منطقة عرضية: أعلى قمة وأدنى قاع", color="#ffb020", fontsize=11, va="bottom")
for i, r in enumerate(w.itertuples()):
    cc = UP if r.close >= r.open else DN
    ax.vlines(i, r.low, r.high, color=cc, lw=1)
    ax.add_patch(Rectangle((i - .33, min(r.open, r.close)), .66, max(abs(r.close - r.open), 1e-3), color=cc))
for k, L in enumerate(sorted(peaks)):
    ax.hlines(L, i0 - .5, len(w) - .5, color="#ff4fa3", lw=1.3)
    ax.text(len(w) - .4, L, f" {L:.2f}", color="#ff4fa3", fontsize=9, va="center")
hb = cen[1] - cen[0]; mx = prof.max()
ap.barh(cen, prof / mx, height=hb, color=["#ff4fa3" if np.isclose(cc_, peaks).any() else "#4a5568" for cc_ in cen])
ap.set_xticks([]); ap.tick_params(labelleft=False); ap.set_title("فوليوم بروفايل 200 صف", color=TX, fontsize=11)
ax.set_xlim(-1, len(w) + 4); ax.set_xticks([0, i0, i1, len(w) - 1]); ax.set_xticklabels([f"{w.index[j]:%Y-%m-%d}" for j in (0, i0, i1, len(w) - 1)], color=MUT)
ax.set_title("مستويات الحيتان: الأعمدة الطويلة في بروفايل آخر منطقة عرضية، ممتدة حتى آخر سعر  ·  SPY يومي", color=TX, fontsize=13, loc="right")
fig.savefig(ROOT / "reports/styles/O_whale_levels.png", dpi=100, facecolor=BG); print("ok", s, e, len(peaks))
