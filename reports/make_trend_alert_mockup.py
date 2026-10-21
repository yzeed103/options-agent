"""Mockup: (1) acceptance outside prior-day value with trend = direction alert; (2) weak-pool break as reversal warning.
Real SPY 15m examples."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd, matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyBboxPatch
from vzones.intraday.data import load_csv, rth
from vzones.intraday.features import add_features
from vzones.intraday.signals import va_accept, apply_filters
import vzones
ROOT = pathlib.Path(__file__).resolve().parent.parent
d = add_features(rth(load_csv(ROOT / "data/intraday/SPY_15m.csv")))
BG, GR, TX, MUT, UP, DN = "#131722", "#2a2e39", "#d1d4dc", "#8a8f9c", "#26a69a", "#ef5350"
plt.rcParams["font.family"] = "DejaVu Sans"

def candles(ax, w):
    for i, r in enumerate(w.itertuples()):
        c = UP if r.close >= r.open else DN
        ax.vlines(i, r.low, r.high, color=c, lw=1, zorder=3)
        ax.add_patch(Rectangle((i - .32, min(r.open, r.close)), .64, max(abs(r.close - r.open), 1e-3), color=c, zorder=3))

def style(ax, title):
    ax.set_facecolor(BG); ax.tick_params(colors=MUT); [s.set_color(GR) for s in ax.spines.values()]
    ax.grid(color=GR, lw=.4); ax.set_xticks([]); ax.set_title(title, color=TX, fontsize=14, loc="right", pad=10)

fig = plt.figure(figsize=(17, 10), facecolor=BG)
# ---------- panel 1: acceptance with trend (pick a long that worked)
sig = apply_filters(d, va_accept(d), trend="with")
c, atr = d.close.to_numpy(), d.atr.to_numpy()
best = None
for i in np.flatnonzero(sig == 1):
    s = d.session.iat[i]; day = np.flatnonzero(d.session.to_numpy() == s)
    if i - day[0] < 3 or day[-1] - i < 8: continue
    gain = (c[day[-1]] - d.open.iat[i + 1]) / atr[i]
    if best is None or gain > best[1]: best = (i, gain)
i = best[0]; s = d.session.iat[i]
prev_day = sorted(d.session.unique()); ps = prev_day[prev_day.index(s) - 1]
w = d[(d.session == ps) | (d.session == s)]; k = w.index.get_loc(d.index[i]); n0 = (w.session == ps).sum()
ax = fig.add_axes([0.04, 0.53, 0.92, 0.40]); style(ax, "١) تنبيه اتجاه: ثبات السعر خارج منطقة قيمة اليوم السابق مع الترند")
candles(ax, w)
ax.plot(range(len(w)), w.ema_f.to_numpy(), color="#f7c948", lw=1.2, label="EMA 20")
ax.plot(range(len(w)), w.ema_s.to_numpy(), color="#7e57c2", lw=1.2, label="EMA 50")
vah, val, poc = d.pd_vah.iat[i], d.pd_val.iat[i], d.pd_poc.iat[i]
ax.add_patch(Rectangle((n0 - .5, val), len(w) - n0, vah - val, color="#2962ff", alpha=.10, zorder=0))
for y, nm, col in ((vah, "أعلى منطقة قيمة الأمس", "#5c8dff"), (val, "أدنى منطقة قيمة الأمس", "#5c8dff"), (poc, "أعلى تداول أمس", "#ff4d4d")):
    ax.hlines(y, n0 - .5, len(w) - .5, color=col, lw=1.3, ls="--" if col != "#ff4d4d" else "-", zorder=2)
    ax.text(len(w) - .6, y, nm + " ", color=col, fontsize=10, va="bottom" if col != "#5c8dff" or y == vah else "top", ha="right",
            bbox=dict(fc=BG, ec="none", alpha=.8, pad=1))
ax.axvline(n0 - .5, color=MUT, lw=.8, ls=":"); ax.text(n0 - 1, ax.get_ylim()[1], "بداية اليوم", color=MUT, fontsize=9, ha="right", va="top")
for j in (k - 1, k):
    ax.scatter(j, w.close.iat[j], s=60, facecolor="none", edgecolor="#00e676", lw=1.6, zorder=5)
ax.annotate("تنبيه اتجاه صاعد\nإغلاقان فوق منطقة القيمة\nوالمتوسط 20 فوق 50", xy=(k, w.low.iat[k]), xytext=(k + 3, w.low.iat[k] - 1.2 * atr[i]),
            color="#00e676", fontsize=11, ha="left", arrowprops=dict(arrowstyle="->", color="#00e676"),
            bbox=dict(boxstyle="round", fc="#0d2a1c", ec="#00e676"), zorder=6)
ax.add_patch(Rectangle((k + .5, ax.get_ylim()[0]), len(w) - k - 1, ax.get_ylim()[1] - ax.get_ylim()[0], color="#00e676", alpha=.05, zorder=0))
ax.text(len(w) - 1, ax.get_ylim()[0], "خلفية خضراء خفيفة = الاتجاه صاعد حتى ينكسر  ", color="#00e676", fontsize=9, ha="right", va="bottom")
ax.legend(loc="upper left", facecolor=BG, edgecolor=GR, labelcolor=TX, fontsize=9)
ax.text(.99, -.07, f"SPY · 15m · {s}", transform=ax.transAxes, color=MUT, ha="right", fontsize=9)

# ---------- panel 2: weak-pool break shown as possible reversal
vz = vzones.compute(d[["open", "high", "low", "close", "volume"]], vzones.VZParams(lookback=120, weak_ratio=0.8, break_ratio=1.5, step=4))
pb = vz.pool_break.to_numpy(); cand = []
for j in np.flatnonzero(pb != 0):
    if j < 20 or j + 10 >= len(d) or d.session.iat[j] != d.session.iat[j + 8]: continue
    rev = -pb[j] * (c[j + 8] - c[j]) / atr[j]
    cand.append((rev, j))
rev, j = max(cand)
w2 = d.iloc[j - 16:j + 12]; kk = 16; dr = pb[j]
ax2 = fig.add_axes([0.04, 0.07, 0.92, 0.38]); style(ax2, "٢) كسر التجمع الضعيف يُعرض كتحذير انعكاس، وليس كإشارة استمرار")
candles(ax2, w2)
ph, pl = vz.pool_high.iat[j], vz.pool_low.iat[j]
ps_i = kk - 1
while ps_i > 0 and vz.pool_active.iat[j - (kk - ps_i) - 1]: ps_i -= 1
ax2.add_patch(Rectangle((ps_i - .5, pl), kk - ps_i, ph - pl, fill=False, ec=MUT, ls=":", lw=1.4, zorder=4))
ax2.text(ps_i - .3, ph, "تجمع فوليوم ضعيف", color=MUT, fontsize=9, va="bottom")
yk = w2.high.iat[kk] if dr > 0 else w2.low.iat[kk]
ax2.annotate("كسر بفوليوم قوي\n⚠ احتمال انعكاس", xy=(kk, yk), xytext=(kk + 2, yk + (1 if dr > 0 else -1) * 1.0 * atr[j]),
             color="#ffb020", fontsize=11, arrowprops=dict(arrowstyle="->", color="#ffb020"), bbox=dict(boxstyle="round", fc="#2b2310", ec="#ffb020"), zorder=6)
ax2.scatter(kk, yk + (1 if dr > 0 else -1) * .15 * atr[j], marker="v" if dr > 0 else "^", s=120, color="#ffb020", zorder=6)
end = min(kk + 8, len(w2) - 1)
ax2.annotate("", xy=(end, w2.close.iat[end]), xytext=(kk, w2.close.iat[kk]), arrowprops=dict(arrowstyle="->", color="#ff4d4d" if dr > 0 else "#00e676", lw=2, ls="--"))
ax2.text((kk + end) / 2, w2.close.iat[end] + (-1 if dr > 0 else 1) * 1.3 * atr[j] * 0 + (w2.high.max() - w2.close.iat[end]) * .55, "الحركة التالية عكس اتجاه الكسر",
         color=TX, fontsize=11, ha="center", bbox=dict(fc=BG, ec=GR, pad=3))
ax2.text(.99, -.08, f"SPY · 15m · {w2.index[kk]:%Y-%m-%d %H:%M}", transform=ax2.transAxes, color=MUT, ha="right", fontsize=9)

# legend box with the tested numbers
fig.text(.04, .965, "من اختبار 7 رموز على 15 دقيقة لسنة ونصف:  الثبات خارج القيمة مع الترند صح الاتجاه 52% (أفضل من العادي بقليل)   |   بعد كسر التجمع الضعيف استمر الاتجاه 46% فقط",
         color=MUT, fontsize=10)
fig.savefig(ROOT / "reports/styles/L_trend_alert_reversal.png", dpi=100, facecolor=BG)
print("ok", s, w2.index[kk])
