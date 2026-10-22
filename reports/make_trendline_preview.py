"""What the Trendline Match helper draws ("two pivots" mode, several pivot lengths) on the latest INTU data we have
(15m up to 2026-10-21; the user's chart is 5m on 2026-10-22, which is not in our data)."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import numpy as np, matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from vzones.intraday.data import load_csv, rth
ROOT = pathlib.Path(__file__).resolve().parent.parent
d = rth(load_csv(ROOT / "data/intraday/INTU_15m.csv")).iloc[-130:]
H, L, O, C = (d[k].to_numpy() for k in ("high", "low", "open", "close")); N = len(d)
def pivots(x, n, hi):
    out = []
    for i in range(n, N - n):
        w = x[i - n:i + n + 1]
        if (hi and x[i] == w.max() and np.argmax(w) == n) or (not hi and x[i] == w.min() and np.argmin(w) == n): out.append(i)
    return out
BG, GR, TX, MUT = "#0b0e14", "#2a2e39", "#d1d4dc", "#8a8f9c"
fig, axs = plt.subplots(3, 1, figsize=(16, 15), facecolor=BG)
for ax, n in zip(axs, (3, 5, 7)):
    ax.set_facecolor(BG); ax.tick_params(colors=MUT); [s.set_color(GR) for s in ax.spines.values()]
    for i in range(N):
        col = "#26a69a" if C[i] >= O[i] else "#ef5350"
        ax.vlines(i, L[i], H[i], color=col, lw=.8); ax.add_patch(Rectangle((i - .3, min(O[i], C[i])), .6, max(abs(C[i] - O[i]), 1e-3), color=col))
    ph, pl = pivots(H, n, True), pivots(L, n, False)
    for p in ph: ax.plot(p, H[p], "v", color="#ff1744", ms=6)
    for p in pl: ax.plot(p, L[p], "^", color="#00e676", ms=6)
    if len(ph) >= 2 and H[ph[-1]] < H[ph[-2]]:
        a, b = ph[-2], ph[-1]; s = (H[b] - H[a]) / (b - a); ax.plot([a, N + 10], [H[a], H[a] + s * (N + 10 - a)], color="#ff1744", lw=2)
    if len(pl) >= 2 and L[pl[-1]] > L[pl[-2]]:
        a, b = pl[-2], pl[-1]; s = (L[b] - L[a]) / (b - a); ax.plot([a, N + 10], [L[a], L[a] + s * (N + 10 - a)], color="#00e676", lw=2)
    ax.set_xlim(-1, N + 10); ax.set_ylim(L.min() - 2, H.max() + 2); ax.set_xticks([])
    ax.set_title(f"طول القمة / القاع = {n}   ·   ▼ قمم   ▲ قيعان", color=TX, loc="right", fontsize=13)
fig.suptitle("Trendline Match، طريقة نقطتين، على آخر بيانات INTU عندي (15 دقيقة حتى 21 أكتوبر) · محاكاة بايثون", color=TX, fontsize=14)
fig.tight_layout(); fig.savefig(ROOT / "reports/styles/W_trendline_match.png", dpi=85, facecolor=BG); print("ok")
