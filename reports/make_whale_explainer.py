"""Explainer: how a whale bar / whale zone is defined and tested (held vs broken). Real SPY 15m examples."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd, matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from vzones.intraday.data import load_csv, rth
from vzones.intraday.features import add_features
ROOT = pathlib.Path(__file__).resolve().parent.parent
d = add_features(rth(load_csv(ROOT / "data/intraday/SPY_15m.csv")))
E = pd.read_csv(ROOT / "reports/whale_zones_events.csv")
E = E[(E.symbol == "SPY") & (E.group == "whale RVOL>=3") & E.left & E.touched & E.hold.notna()]
o, h, l, c = (d[k].to_numpy() for k in ("open", "high", "low", "close"))
slot = d.index.hour * 60 + d.index.minute
avg = d.volume.groupby(slot).transform(lambda x: x.shift(1).rolling(20, min_periods=5).mean()).to_numpy()

def find_touch(t):
    zl, zh = l[t], h[t]; left = False
    for j in range(t + 1, min(t + 140, len(d))):
        out = l[j] > zh or h[j] < zl
        if not left and out: left = True
        elif left and l[j] <= zh and h[j] >= zl: return j, (1 if c[j - 1] > zh else -1)
    return None, 0

def pick(kind):
    best = None
    for t in E.t:
        j, side = find_touch(int(t))
        if j is None or j - t > 45 or j - t < 6 or j + 6 >= len(d): continue
        k = j + 4; zl, zh = l[t], h[t]
        held = (c[k] > zh) if side == 1 else (c[k] < zl); broke = (c[k] < zl) if side == 1 else (c[k] > zh)
        if (kind == "hold" and held) or (kind == "break" and broke):
            span = j - t
            if best is None or abs(span - 18) < abs(best[2] - 18): best = (int(t), j, span, side)
    return best

BG, GR, TX, MUT, UP, DN, WH = "#131722", "#2a2e39", "#d1d4dc", "#8a8f9c", "#26a69a", "#ef5350", "#ffb020"
fig = plt.figure(figsize=(18, 10), facecolor=BG)
fig.text(.5, .965, "كيف عرّفت منطقة الحوت وكيف اختبرتها", color=TX, fontsize=17, ha="center", weight="bold")
fig.text(.5, .93, "شمعة الحوت = فوليوم 3 أضعاف المعتاد في نفس الوقت من الجلسة   |   منطقة الحوت = من أدنى الشمعة إلى أعلاها   |   النتيجة تُقاس بعد ساعة من أول رجوع",
         color=MUT, fontsize=11, ha="center")
for col, (kind, title, verdict, vcol) in enumerate((("hold", "مثال ١: المنطقة ثبتت", "ثبتت: بعد ساعة رجع السعر من نفس الجهة", "#00e676"),
                                                     ("break", "مثال ٢: المنطقة انكسرت", "انكسرت: بعد ساعة أغلق السعر من الجهة الأخرى", "#ff5252"))):
    t, j, span, side = pick(kind)
    a, b = t - 6, j + 8
    w = d.iloc[a:b]; x = np.arange(len(w)); ti, ji = t - a, j - a
    ax = fig.add_axes([0.04 + col * 0.49, 0.30, 0.45, 0.56], facecolor=BG)
    av = fig.add_axes([0.04 + col * 0.49, 0.08, 0.45, 0.19], facecolor=BG, sharex=ax)
    for z in (ax, av):
        z.tick_params(colors=MUT); [s.set_color(GR) for s in z.spines.values()]; z.grid(color=GR, lw=.4)
    ax.set_title(title, color=vcol, fontsize=15, loc="right", pad=14)
    zl, zh = l[t], h[t]
    ax.add_patch(Rectangle((ti - .5, zl), len(w) - ti, zh - zl, color=WH, alpha=.13, zorder=0))
    ax.hlines([zl, zh], ti - .5, len(w) - .5, color=WH, lw=1.2, ls="--")
    for i, r in enumerate(w.itertuples()):
        cc = UP if r.close >= r.open else DN
        ax.vlines(i, r.low, r.high, color=cc, lw=1, zorder=3)
        ax.add_patch(Rectangle((i - .33, min(r.open, r.close)), .66, max(abs(r.close - r.open), 1e-3), color=cc, zorder=3,
                               ec=WH if i == ti else cc, lw=2 if i == ti else 0))
    yr = w.high.max() - w.low.min()
    ax.annotate("١ شمعة الحوت", xy=(ti, h[t]), xytext=(ti, w.high.max() + .06 * yr), color=WH, fontsize=12, ha="center",
                arrowprops=dict(arrowstyle="->", color=WH), weight="bold")
    ax.text(len(w) - .6, zh, "منطقة الحوت ", color=WH, fontsize=10, ha="right", va="bottom")
    # price leaves the zone
    lv = next(i for i in range(ti + 1, ji) if l[a + i] > zh or h[a + i] < zl)
    ax.annotate("٢ السعر يبتعد عن المنطقة", xy=(lv, c[a + lv]), xytext=(lv - 1, w.high.max() + .17 * yr), ha="right",
                color=TX, fontsize=11, arrowprops=dict(arrowstyle="->", color=MUT))
    ax.annotate("٣ أول رجوع", xy=(ji, c[j]), xytext=(ji + 1.2, w.low.min() - .08 * yr if side == 1 else w.high.max() + .06 * yr), color=TX, fontsize=11, ha="left",
                arrowprops=dict(arrowstyle="->", color=MUT))
    ax.axvspan(ji - .5, ji + 4.5, color=vcol, alpha=.07)
    ax.annotate("٤ " + verdict, xy=(ji + 4, c[j + 4]), xytext=(ji + 4, w.low.min() - .2 * yr), ha="right",
                color=vcol, fontsize=11, weight="bold", arrowprops=dict(arrowstyle="->", color=vcol), bbox=dict(fc=BG, ec=vcol, boxstyle="round"))
    ax.set_ylim(w.low.min() - .28 * yr, w.high.max() + .26 * yr); ax.set_xticks([])
    ax.text(.01, .97, f"SPY · 15m · {d.index[t]:%Y-%m-%d %H:%M}", transform=ax.transAxes, color=MUT, fontsize=9, va="top")
    av.bar(x, w.volume, color=[WH if i == ti else "#4a4e5a" for i in x], width=.7)
    av.plot(x, avg[a:b], color="#5c8dff", lw=1.5)
    av.text(ti + .6, w.volume.iat[ti], f"{w.volume.iat[ti] / avg[t]:.1f}× المعتاد", color=WH, fontsize=11, va="top", weight="bold")
    av.text(.99, .9, "الخط الأزرق = فوليوم نفس الوقت في آخر 20 يوما", transform=av.transAxes, color="#5c8dff", fontsize=9, ha="right", va="top")
    av.set_yticks([]); av.set_xticks([])
fig.savefig(ROOT / "reports/styles/N_whale_explainer.png", dpi=100, facecolor=BG); print("ok")
