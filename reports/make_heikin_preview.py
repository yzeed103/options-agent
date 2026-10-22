"""Normal candles vs Heikin Ashi on the same SPY 5m data: the indicator measures the real candles, so the whale
lines, the heading target and the panel numbers are identical on both charts. Reuses make_intraday_preview."""
import runpy, pathlib, numpy as np, matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
ROOT = pathlib.Path(__file__).resolve().parent.parent
g = runpy.run_path(str(ROOT / "reports/make_intraday_preview.py"))
w, LV, VA, heads, rows = g["w"], g["LV"], g["VA"], g["heads"], g["rows"]
o, h, l, c = (w[k].to_numpy() for k in ("open", "high", "low", "close"))
hc = (o + h + l + c) / 4; ho = np.empty_like(hc); ho[0] = (o[0] + c[0]) / 2
for i in range(1, len(hc)): ho[i] = (ho[i - 1] + hc[i - 1]) / 2
hh, hl_ = np.maximum.reduce([h, ho, hc]), np.minimum.reduce([l, ho, hc])
BG, GR, TX, MUT = "#0b0e14", "#2a2e39", "#d1d4dc", "#8a8f9c"
fig, axs = plt.subplots(2, 1, figsize=(18, 13), facecolor=BG)
N = len(w); lo, hi = w.low.min(), w.high.max(); pad = (hi - lo) * .15; hd, hlv = heads[-1]
txt = "  |  ".join(f"{r[0]}: {r[1]}" for r in rows)
for ax, (O, H, L, C, name) in zip(axs, ((o, h, l, c, "شموع عادية"), (ho, hh, hl_, hc, "هيكن آشي"))):
    ax.set_facecolor(BG); ax.tick_params(colors=MUT); [s.set_color(GR) for s in ax.spines.values()]
    for x in LV:
        if lo - pad < x < hi + pad: ax.hlines(x, -1, N + 2, color="#9b5cff", lw=1)
    if hd: ax.hlines(hlv, -1, N + 2, color="#9b5cff", lw=5); ax.text(N - 2, hlv, f"▲ متجه إلى {hlv:.2f}", color="#b98cff", ha="right", va="bottom", fontsize=11, weight="bold")
    for i in range(N):
        col = "#26a69a" if C[i] >= O[i] else "#ef5350"
        ax.vlines(i, L[i], H[i], color=col, lw=.8); ax.add_patch(Rectangle((i - .33, min(O[i], C[i])), .66, max(abs(C[i] - O[i]), 1e-3), color=col))
    ax.set_xlim(-2, N + 4); ax.set_ylim(lo - pad, hi + pad); ax.set_xticks([])
    ax.set_title(f"SPY · 5 دقائق · {name}", color=TX, fontsize=14, loc="right")
    ax.text(.99, .03, txt, color=TX, fontsize=10, ha="right", transform=ax.transAxes, bbox=dict(fc="#1e222d", ec=GR, boxstyle="round,pad=.5"))
fig.suptitle("نفس الخطوط ونفس أرقام الجدول على الشارتين، لأن المؤشر يحسب من الشموع الحقيقية (محاكاة بايثون)", color=TX, fontsize=14)
fig.tight_layout(); fig.savefig(ROOT / "reports/styles/V_heikin_ashi_check.png", dpi=90, facecolor=BG); print("ok")
