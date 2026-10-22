"""Before / after: every trendline the indicator drew over the last 260 INTU 15m bars (each from the bar it appeared
until it was replaced). Top: original (2-bar pivots, every new pair replaces the line). Bottom: heavy (5-bar pivots,
held until price closes through it). Python mirror of the Pine logic."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

ROOT = pathlib.Path(__file__).resolve().parent.parent
d = pd.read_csv(ROOT / "data/intraday/INTU_15m.csv").iloc[-260:].reset_index(drop=True)
H, L, O, C = (d[k].to_numpy(float) for k in ("high", "low", "open", "close")); N = len(d)


def segments(k, hold):
    out = []
    for side, x in (("dn", H), ("up", L)):
        last = line = None; born = 0; broke = True
        for i in range(2 * k, N):
            p = i - k; w = x[p - k:p + k + 1]
            piv = (x[p] == w.max() and (x[p - k:p] < x[p]).all()) if side == "dn" else (x[p] == w.min() and (x[p - k:p] > x[p]).all())
            if piv:
                ok = last is not None and (x[p] < last[1] if side == "dn" else x[p] > last[1])
                if ok and (not hold or broke or line is None):
                    if line: out.append((side, line, born, i))
                    line = (last[0], last[1], (x[p] - last[1]) / (p - last[0])); born = i; broke = False
                last = (p, x[p])
            if line and not broke:
                y = line[1] + line[2] * (i - line[0])
                if (side == "dn" and C[i] > y) or (side == "up" and C[i] < y):
                    broke = True
        if line: out.append((side, line, born, N - 1))
    return out


BG, GR, TX, MUT = "#0b0e14", "#2a2e39", "#d1d4dc", "#8a8f9c"
fig, axs = plt.subplots(2, 1, figsize=(16, 12), facecolor=BG)
for ax, (k, hold, title) in zip(axs, ((2, False, "before: 2-bar pivots, every new pair replaces the line"),
                                       (5, True, "after: 5-bar pivots, line held until price closes through it"))):
    ax.set_facecolor(BG); ax.tick_params(colors=MUT); [s.set_color(GR) for s in ax.spines.values()]
    for i in range(N):
        col = "#26a69a" if C[i] >= O[i] else "#ef5350"
        ax.vlines(i, L[i], H[i], color=col, lw=.7)
        ax.add_patch(Rectangle((i - .3, min(O[i], C[i])), .6, max(abs(C[i] - O[i]), 1e-3), color=col))
    segs = segments(k, hold)
    for side, (a, y0, s), b0, b1 in segs:
        xs = np.array([max(a, b0 - 40), b1]); ys = y0 + s * (xs - a)
        ax.plot(xs, ys, color="#ff1744" if side == "dn" else "#00e676", lw=1.6, alpha=.85)
    ax.set_xlim(-1, N + 2); ax.set_ylim(L.min() * .995, H.max() * 1.005); ax.set_xticks([])
    ax.set_title(f"INTU 15m · {title} · {len(segs)} lines in {N} bars", color=TX, fontsize=13)
fig.tight_layout(); out = ROOT / "reports/styles/trendline_heavy_preview.png"
fig.savefig(out, dpi=85, facecolor=BG); print(out)
