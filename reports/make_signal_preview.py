"""TradingView-style preview of the new trend alert + reversal warning on a real SPY 15m day."""
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
vz = vzones.compute(d[["open", "high", "low", "close", "volume"]], vzones.VZParams(lookback=120, weak_ratio=0.8, break_ratio=1.5, step=4))
ta = apply_filters(d, va_accept(d), trend="with"); pb = vz.pool_break.to_numpy()
sess = d.session.to_numpy(); days = sorted(d.session.unique())
pick = None
for s in days[1:]:
    ix = np.flatnonzero(sess == s); t = ix[ta[ix] != 0]; p = ix[pb[ix] != 0]
    if len(t) and len(p) and p.min() > t.min():
        pick = s; break
pick = pick or d.session.iat[np.flatnonzero(ta)[0]]
prev = days[days.index(pick) - 1]
w = d[(d.session == prev) | (d.session == pick)].reset_index()
n0 = int((w.session == prev).sum()); idx0 = d.index.get_loc(w.time.iat[0]) if "time" in w else None
off = np.flatnonzero(sess == prev)[0]
TA = ta[off:off + len(w)]; PB = pb[off:off + len(w)]
BG, GR, TX, MUT, UP, DN = "#131722", "#2a2e39", "#d1d4dc", "#8a8f9c", "#26a69a", "#ef5350"
fig = plt.figure(figsize=(17, 9), facecolor=BG)
ax = fig.add_axes([0.03, 0.08, 0.72, 0.86], facecolor=BG)
ax.tick_params(colors=MUT); [s_.set_color(GR) for s_ in ax.spines.values()]; ax.grid(color=GR, lw=.4)
yr = w.high.max() - w.low.min()
# trend background (from first alert until close back inside value / EMA flip / session end)
t0 = np.flatnonzero(TA != 0); dr = TA[t0[0]] if len(t0) else 0
if len(t0):
    vah, val = w.pd_vah.iat[t0[0]], w.pd_val.iat[t0[0]]; j = t0[0]
    while j + 1 < len(w) and w.session.iat[j + 1] == pick:
        cc = w.close.iat[j + 1]
        if (dr > 0 and (cc < vah or w.ema_f.iat[j + 1] < w.ema_s.iat[j + 1])) or (dr < 0 and (cc > val or w.ema_f.iat[j + 1] > w.ema_s.iat[j + 1])): break
        j += 1
    ax.axvspan(t0[0] - .5, j + .5, color="#00e676" if dr > 0 else "#ff5252", alpha=.08, lw=0)
for i, r in w.iterrows():
    c = UP if r.close >= r.open else DN
    ax.vlines(i, r.low, r.high, color=c, lw=1, zorder=3)
    ax.add_patch(Rectangle((i - .33, min(r.open, r.close)), .66, max(abs(r.close - r.open), 1e-3), color=c, zorder=3))
x = np.arange(len(w))
ax.step(x[n0:], w.pd_vah[n0:], where="mid", color="#5c8dff", lw=1.2); ax.step(x[n0:], w.pd_val[n0:], where="mid", color="#5c8dff", lw=1.2)
ax.step(x[n0:], w.pd_poc[n0:], where="mid", color="#ff4d4d", lw=1.2)
ax.plot(x, w.ema_f, color="#f7c948", lw=1, alpha=.8); ax.plot(x, w.ema_s, color="#7e57c2", lw=1, alpha=.8)
ax.axvline(n0 - .5, color=MUT, lw=.7, ls=":")
def tv_label(i, y, text, col, up):
    off_ = (-1 if up else 1) * .06 * yr
    ax.annotate(text, xy=(i, y), xytext=(i, y + off_), ha="center", va="top" if up else "bottom", fontsize=10, weight="bold", color="black",
                bbox=dict(boxstyle="round,pad=0.35", fc=col, ec=col), arrowprops=dict(arrowstyle="-|>", color=col, lw=1.2), zorder=7)
for i in np.flatnonzero(TA != 0):
    tv_label(i, w.low.iat[i] if TA[i] > 0 else w.high.iat[i], "اتجاه ↑" if TA[i] > 0 else "اتجاه ↓", "#00e676" if TA[i] > 0 else "#ff5252", TA[i] > 0)
for i in np.flatnonzero(PB != 0):
    tv_label(i, w.high.iat[i] if PB[i] > 0 else w.low.iat[i], "انعكاس؟", "#ffb020", PB[i] < 0)
ax.set_xlim(-1, len(w) + 6); ax.set_ylim(w.low.min() - .12 * yr, w.high.max() + .12 * yr)
ax.set_xticks([n0 // 2, n0 + (len(w) - n0) // 2]); ax.set_xticklabels([str(prev), str(pick)], color=MUT)
for y, nm, col in ((w.pd_vah.iat[-1], "أعلى منطقة قيمة الأمس", "#5c8dff"), (w.pd_poc.iat[-1], "أعلى تداول أمس", "#ff4d4d"), (w.pd_val.iat[-1], "أدنى منطقة قيمة الأمس", "#5c8dff")):
    ax.text(len(w) + .2, y, nm, color=col, fontsize=9, va="center")
ax.set_title(f"SPY · 15m · Volume Zones", color=TX, loc="left", fontsize=12)
# side legend explaining the marks
lx = fig.add_axes([0.77, 0.08, 0.21, 0.86], facecolor=BG); lx.axis("off"); lx.set_xlim(0, 1); lx.set_ylim(0, 1)
lx.add_patch(FancyBboxPatch((0.02, 0.02), .96, .96, boxstyle="round,pad=0.01", fc="#1e222d", ec=GR))
items = [("اتجاه ↑", "#00e676", "تنبيه اتجاه صاعد: إغلاقان فوق\nمنطقة قيمة الأمس والمتوسط 20 فوق 50"),
         ("اتجاه ↓", "#ff5252", "تنبيه اتجاه هابط: إغلاقان تحت\nمنطقة قيمة الأمس والمتوسط 20 تحت 50"),
         ("انعكاس؟", "#ffb020", "كسر تجمع فوليوم ضعيف\nالسعر ينعكس بعده أكثر مما يستمر")]
y = .9
for tx, col, ex in items:
    lx.text(.9, y, tx, ha="right", va="center", fontsize=11, weight="bold", color="black", bbox=dict(boxstyle="round,pad=0.35", fc=col, ec=col))
    lx.text(.9, y - .07, ex, ha="right", va="top", fontsize=9.5, color=TX); y -= .19
lx.add_patch(Rectangle((.62, y - .02), .28, .05, color="#00e676", alpha=.15)); lx.text(.9, y - .05, "خلفية خفيفة = الاتجاه ما زال قائما\nتختفي عند العودة داخل منطقة القيمة", ha="right", va="top", fontsize=9.5, color=TX)
y -= .15
lx.plot([.62, .9], [y, y], color="#5c8dff", lw=1.5); lx.text(.9, y - .03, "حدود منطقة قيمة الأمس", ha="right", va="top", fontsize=9.5, color=TX)
y -= .09
lx.plot([.62, .9], [y, y], color="#ff4d4d", lw=1.5); lx.text(.9, y - .03, "أعلى تداول أمس", ha="right", va="top", fontsize=9.5, color=TX)
fig.savefig(ROOT / "reports/styles/M_signal_preview.png", dpi=100, facecolor=BG); print("ok", prev, pick)
