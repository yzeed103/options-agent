"""Reverse-engineering the user's green / red trendlines on INTU 5m (2026-10-22, TradingView export).
Measured from the screenshot: red passes 358.08 (18:55) and ~357.05 (19:25), slope ~-0.17/bar; green passes 354.81
(18:40) and ~355.54 (19:10), slope ~+0.12/bar. This script tests rules and prints which pair each rule picks."""
import pandas as pd, numpy as np, pathlib
d = pd.read_csv(pathlib.Path(__file__).resolve().parent.parent / "data/intraday/INTU_5m_tv.csv", usecols=range(5))
H, L, C, O = d.high.values, d.low.values, d.close.values, d.open.values; T = d.time.str[11:16].values; n = len(d)
def piv(x, k, hi):
    return [i for i in range(k, n - k) if (x[i] == x[i - k:i + k + 1].max() if hi else x[i] == x[i - k:i + k + 1].min())]
def pick(ph, pl, crossCheck):
    red = green = None
    for a, b in zip(ph[:-1], ph[1:]):
        if H[b] < H[a]:
            s = (H[b] - H[a]) / (b - a)
            if not crossCheck or all(H[j] <= H[a] + s * (j - a) + 1e-9 for j in range(a + 1, b)): red = (a, b, s)
    for a, b in zip(pl[:-1], pl[1:]):
        if L[b] > L[a]:
            s = (L[b] - L[a]) / (b - a)
            if not crossCheck or all(L[j] >= L[a] + s * (j - a) - 1e-9 for j in range(a + 1, b)): green = (a, b, s)
    return red, green
fmt = lambda p: None if p is None else f"{T[p[0]]} -> {T[p[1]]}  slope {p[2]:+.3f}"
for src in ("close", "body", "highlow"):
    xh, xl = (C, C) if src == "close" else (np.maximum(O, C), np.minimum(O, C)) if src == "body" else (H, L)
    for k in (1, 2, 3, 4):
        for cc in (False, True):
            r, g = pick(piv(xh, k, True), piv(xl, k, False), cc)
            ok = r and g and T[r[0]] == "18:55" and T[r[1]] == "19:25" and T[g[0]] == "18:40" and T[g[1]] == "19:10"
            print(f"{src:8s} L={k} no-wick-cross={cc!s:5s} red {fmt(r)} | green {fmt(g)} {'<== MATCH' if ok else ''}")

# ---- picture: the matched rule (pivots on high / low, 2 bars each side) on the same day as the user's chart
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
r, g = pick(piv(H, 2, True), piv(L, 2, False), False)
s0 = int(np.where(d.time.str[:10].values == "2026-10-22")[0][0]); s0 = max(s0, n - 80); N = n - s0
BG, GR, TX, MUT = "#0b0e14", "#2a2e39", "#d1d4dc", "#8a8f9c"
fig, ax = plt.subplots(figsize=(16, 9), facecolor=BG); ax.set_facecolor(BG); ax.tick_params(colors=MUT); [q.set_color(GR) for q in ax.spines.values()]
for i in range(s0, n):
    col = "#26a69a" if C[i] >= O[i] else "#ef5350"; x = i - s0
    ax.vlines(x, L[i], H[i], color=col, lw=.8); ax.add_patch(Rectangle((x - .3, min(O[i], C[i])), .6, max(abs(C[i] - O[i]), 1e-3), color=col))
for (a, b, sl), col, P in ((r, "#ff1744", H), (g, "#00e676", L)):
    xe = N + 40; ax.plot([a - s0, xe], [P[a], P[a] + sl * (xe - (a - s0) - 0 + s0 - s0) if False else P[a] + sl * (xe + s0 - a)], color=col, lw=2.2)
    for q in (a, b): ax.plot(q - s0, P[q], "o", color=col, ms=9, mfc="none", mew=2); ax.text(q - s0, P[q] + (0.5 if col == "#ff1744" else -0.9), f"{T[q]}  {P[q]:.2f}", color=col, fontsize=10, ha="center")
ticks = list(range(0, N, 6)); ax.set_xticks(ticks); ax.set_xticklabels([T[s0 + t] for t in ticks], color=MUT)
ax.set_xlim(-2, N + 40); ax.set_ylim(L[s0:].min() - 3, H[s0:].max() + 6)
ax.set_title("INTU · 5 دقائق · 22 أكتوبر · القاعدة المطابقة: قمم وقيعان بشمعتين يمين ويسار، آخر قمتين نازلتين وآخر قاعين صاعدين", color=TX, fontsize=12, loc="right")
fig.tight_layout(); fig.savefig(pathlib.Path(__file__).resolve().parent / "styles/X_trendline_found.png", dpi=90, facecolor=BG)
