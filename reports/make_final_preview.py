"""Simulated SPY 5m view of the fixed indicator (Python port vzones/ranges.py): whale levels known before each day,
today's developing session POC/VAH/VAL, heading line, trendlines and the fixed panel rows. Real data."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd, matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyBboxPatch
from vzones.intraday.data import load_csv, rth
from vzones.ranges import AGG, daily_ranges, range_levels, instant_trend, supertrend, rma, true_range
ROOT = pathlib.Path(__file__).resolve().parent.parent
raw = rth(load_csv(ROOT / "data/intraday/SPY_5m.csv")); raw.index = raw.index.tz_localize(None)
m15 = raw.resample("15min").agg(AGG).dropna(); day = raw.resample("1D").agg(AGG).dropna()
done, state = daily_ranges(day.iloc[:-1]); i = len(day) - 2; today = day.index[-1]
comp = [r for r in done if r[2] <= i][-2:]; LV = []; VA = None; vaName = ""
for a, b, _ in comp:
    res = range_levels(m15, day.index[a], day.index[b] if b < len(day) else today); LV += res[0] + list(res[1]); VA, vaName = res[1], "آخر منطقة مكتملة"
r0, rh, rl = state[i]; nd_ = i + 1 - r0
if nd_ >= 10:
    res = range_levels(m15, day.index[r0], today); LV += res[0] + list(res[1]); VA, vaName = res[1], "المنطقة الحالية"
LV = sorted(set(np.round(LV, 2)))
w = raw[raw.index >= today]; o, h, l, c, v = (w[k].to_numpy() for k in ("open", "high", "low", "close", "volume")); N = len(w); cl = c[-1]
# developing session value area (40 rows, today's bars)
lo, hi = l.min(), h.max(); st = (hi - lo) / 40; pv = np.zeros(40)
for hh, ll, vv in zip(h, l, v):
    for q in range(int(np.clip((ll - lo) // st, 0, 39)), int(np.clip((hh - lo) // st, 0, 39)) + 1):
        ql = lo + q * st; pv[q] += vv * max(0, min(hh, ql + st) - max(ll, ql)) / max(hh - ll, 1e-9)
pi = int(np.argmax(pv)); a0 = a1 = pi; acc = pv[pi]
while acc < .7 * pv.sum() and (a0 > 0 or a1 < 39):
    u = pv[a1 + 1] if a1 < 39 else -1; d_ = pv[a0 - 1] if a0 > 0 else -1
    if u >= d_: a1 += 1; acc += u
    else: a0 -= 1; acc += d_
sPoc, sVah, sVal = lo + (pi + .5) * st, lo + (a1 + 1) * st, lo + a0 * st
full = raw[raw.index >= day.index[-6]]; nd = instant_trend(full)[-1]; stl, sd = supertrend(full); up = sd[-1] < 0
edge = h[-1] if nd > 0 else l[-1]; ahead = [x for x in LV if (x - edge) * nd > 0]; tgt = min(ahead, key=lambda x: abs(x - edge)) if nd and ahead else None
BG, GR, TX, MUT = "#0b0e14", "#2a2e39", "#d1d4dc", "#8a8f9c"
fig = plt.figure(figsize=(20, 10), facecolor=BG); ax = fig.add_axes([0.03, 0.06, 0.64, 0.88], facecolor=BG)
ax.tick_params(colors=MUT); [q.set_color(GR) for q in ax.spines.values()]
pad = (hi - lo) * .6
for x in LV:
    if lo - pad < x < hi + pad: ax.hlines(x, -1, N + 4, color="#9b5cff", lw=1)
if VA is not None:
    for y, col, lw in ((VA[0], "#ff3b3b", 3), (VA[1], "#ffb020", 2), (VA[2], "#ffb020", 2)):
        if lo - pad < y < hi + pad: ax.hlines(y, -1, N + 4, color=col, lw=lw)
if tgt: ax.hlines(tgt, -1, N + 4, color="#9b5cff", lw=5); ax.text(N + 1, tgt, f"{'▲' if nd > 0 else '▼'} متجه إلى {tgt:.2f}", color="#b98cff", fontsize=10, va="bottom", weight="bold")
for y, t, col in ((sPoc, "POC", "#ff4d4d"), (sVah, "VAH", "#26c6da"), (sVal, "VAL", "#26c6da")):
    ax.hlines(y, 0, N - 1, color=col, lw=1.2, ls="--"); ax.text(N + 1, y, t + " اليوم", color=col, fontsize=9, va="top")
for k in range(N):
    col = "#26a69a" if c[k] >= o[k] else "#ef5350"
    ax.vlines(k, l[k], h[k], color=col, lw=.8); ax.add_patch(Rectangle((k - .3, min(o[k], c[k])), .6, max(abs(c[k] - o[k]), 1e-3), color=col))
ax.set_xlim(-2, N + 14); ax.set_ylim(lo - pad, hi + pad); ticks = list(range(0, N, 6)); ax.set_xticks(ticks); ax.set_xticklabels([w.index[t].strftime("%H:%M") for t in ticks], color=MUT)
ax.set_title(f"SPY · 5 دقائق · {today.date()} · محاكاة بايثون للمؤشر بعد الإصلاحات (ليست لقطة TradingView)", color=TX, loc="right", fontsize=12)
where = "السعر فوق القمة" if cl > rh else "السعر تحت القاع" if cl < rl else "السعر داخل المنطقة"
rtxt = ("قيد التكوين · " if nd_ < 10 else "") + where
ptxt = ("فوق VAH" if cl > VA[1] else "تحت VAL" if cl < VA[2] else "بين POC و VAH" if cl >= VA[0] else "بين VAL و POC") if VA else "-"
rows = [("الاتجاه", "صاعد" if nd > 0 else "هابط" if nd < 0 else "عرضي", "متوسط 9 و 21"),
        ("المنطقة العرضية", rtxt, f"{rl:.2f} - {rh:.2f}   |   {nd_} يوم"),
        ("موقع السعر من القيمة", ptxt, f"{vaName}:  POC {VA[0]:.2f}\nVAH {VA[1]:.2f}   |   VAL {VA[2]:.2f}" if VA else "-"),
        ("منطقة قيمة اليوم", f"POC {sPoc:.2f}", f"VAH {sVah:.2f}   |   VAL {sVal:.2f}   (من افتتاح الجلسة)"),
        ("متجه إلى", f"{'▲ صاعد' if nd > 0 else '▼ هابط'} إلى {tgt:.2f}" if tgt else "لا يوجد", ""),
        ("صمود الترند", "الترند الصاعد صامد" if up else "الترند الهابط صامد", f"ينكسر إذا أغلق {'تحت' if up else 'فوق'} {stl[-1]:.2f}")]
tp = fig.add_axes([0.69, 0.18, 0.30, 0.76], facecolor=BG); tp.axis("off"); tp.set_xlim(0, 1); tp.set_ylim(0, 1)
tp.add_patch(FancyBboxPatch((0, .02), 1, .96, boxstyle="round,pad=0.005", fc="#1e222d", ec=GR))
tp.text(.96, .93, "مناطق الفوليوم (صفوف مختارة)", color=TX, fontsize=13, ha="right", weight="bold")
y = .82
for lbl, v1, v2 in rows:
    tp.text(.96, y, lbl, color=MUT, fontsize=10.5, ha="right", va="center"); tp.text(.62, y + .025, v1, color=TX, fontsize=11.5, ha="right", weight="bold", va="center")
    tp.text(.62, y - .035, v2, color=MUT, fontsize=9, ha="right", va="center"); tp.plot([.03, .97], [y - .075, y - .075], color=GR, lw=.8); y -= .135
fig.savefig(ROOT / "reports/styles/Y_after_fixes.png", dpi=90, facecolor=BG); print(rtxt, ptxt, vaName, tgt)
