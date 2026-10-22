"""Simulated daily view of the current Pine logic on real SPY 15m data: every sideways range (first N days set
top/bottom, a daily close outside ends it), each range's whale columns + POC/VAH/VAL from a hidden 200-row
profile of 60m bars, rolling 120-bar POC/VAH/VAL with labels, and the buy/sell profile at the right edge."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import numpy as np, matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from vzones.intraday.data import load_csv, rth
ROOT = pathlib.Path(__file__).resolve().parent.parent
SYM, WLEN, WMULT, ROWS, PEAKS, VA = "SPY", 10, 6.0, 200, 8, 0.70
raw = rth(load_csv(ROOT / f"data/intraday/{SYM}_15m.csv"))[["open", "high", "low", "close", "volume"]]
raw.index = raw.index.tz_localize(None)
AGG = dict(open="first", high="max", low="min", close="last", volume="sum")
h1 = raw.resample("60min").agg(AGG).dropna(); day = raw.resample("1D").agg(AGG).dropna()
H, L, C, O = day.high.to_numpy(), day.low.to_numpy(), day.close.to_numpy(), day.open.to_numpy()
tr = np.maximum(H - L, np.abs(np.r_[C[0], C[:-1]] - np.r_[H[:1], H[1:]]))
atr = np.empty(len(day)); atr[0] = tr[0]
for i in range(1, len(day)): atr[i] = atr[i - 1] + (tr[i] - atr[i - 1]) / 14
# ranges, same state machine as the Pine code
ranges, r0, rh, rl = [], 0, H[0], L[0]
for n in range(1, len(day)):
    if n - r0 < WLEN:
        rh, rl = max(rh, H[n]), min(rl, L[n])
        if rh - rl > WMULT * atr[n]: r0, rh, rl = n, H[n], L[n]
    elif C[n] > rh or C[n] < rl:
        ranges.append((r0, n)); r0, rh, rl = n, H[n], L[n]
    else: rh, rl = max(rh, H[n]), min(rl, L[n])
live = (r0, len(day)) if len(day) - r0 >= WLEN else None
def profile(a, b):
    bars = h1[(h1.index >= day.index[a]) & (h1.index < (day.index[b] if b < len(day) else h1.index[-1] + np.timedelta64(1, "h")))]
    lo, hi = bars.low.min(), bars.high.max(); st = (hi - lo) / ROWS; pv = np.zeros(ROWS)
    for r in bars.itertuples():
        q0, q1 = int(np.clip((r.low - lo) // st, 0, ROWS - 1)), int(np.clip((r.high - lo) // st, 0, ROWS - 1))
        for q in range(q0, q1 + 1):
            ql = lo + q * st; ov = max(0, min(r.high, ql + st) - max(r.low, ql)); pv[q] += r.volume * ov / max(r.high - r.low, 1e-9)
    sm = np.convolve(pv, np.ones(3) / 3, "same"); nb = max(2, ROWS // 40)
    pk = [q for q in range(ROWS) if sm[q] >= 1.3 * sm.mean() and sm[q] == sm[max(0, q - nb):q + nb + 1].max()]
    pk = sorted(pk, key=lambda q: -sm[q])[:PEAKS]
    pi = int(np.argmax(pv)); a0 = a1 = pi; acc = pv[pi]
    while acc < VA * pv.sum() and (a0 > 0 or a1 < ROWS - 1):
        u = pv[a1 + 1] if a1 < ROWS - 1 else -1; d_ = pv[a0 - 1] if a0 > 0 else -1
        if u >= d_: a1 += 1; acc += u
        else: a0 -= 1; acc += d_
    return lo, hi, [lo + (q + .5) * st for q in pk], lo + (pi + .5) * st, lo + (a1 + 1) * st, lo + a0 * st
BG, GR, TX, MUT = "#0b0e14", "#2a2e39", "#d1d4dc", "#8a8f9c"
N = len(day); fig = plt.figure(figsize=(21, 10), facecolor=BG); ax = fig.add_axes([0.03, 0.06, 0.70, 0.88], facecolor=BG)
ax.tick_params(colors=MUT); [s.set_color(GR) for s in ax.spines.values()]; ax.grid(color=GR, lw=.3)
END = N + 45
shown = ranges[-2:] + ([live] if live else [])
LV, VAS = [], None
for a, b in shown:
    isl = live is not None and (a, b) == live
    lo, hi, pk, poc, vah, val = profile(a, b)
    ax.add_patch(Rectangle((a - .5, lo), b - a, hi - lo, fc="#ffb02010", ec="#ffb020", ls="--", lw=1.2, zorder=1))
    ax.text(a, hi, " منطقة قيد التكوين" if isl else " منطقة عرضية مكتملة", color="#ffb020", fontsize=10, va="bottom")
    LV += pk + [poc, vah, val]; VAS = (poc, vah, val)
    for y in pk: ax.hlines(y, a - .5, END, color="#9b5cff", lw=1, zorder=2)
    ax.hlines(poc, a - .5, END, color="#ff3b3b", lw=3, zorder=3); ax.hlines([vah, val], a - .5, END, color="#ffb020", lw=2, zorder=3)
    for y, t, c in ((poc, "POC", "#ff3b3b"), (vah, "VAH", "#ffb020"), (val, "VAL", "#ffb020")):
        ax.text(a - 1, y, f"{t} {y:.2f}", color=c, fontsize=9, ha="right", va="center", weight="bold", zorder=6)
for i in range(N):
    c = "#26a69a" if C[i] >= O[i] else "#ef5350"
    ax.vlines(i, L[i], H[i], color=c, lw=.8, zorder=4); ax.add_patch(Rectangle((i - .33, min(O[i], C[i])), .66, max(abs(C[i] - O[i]), 1e-3), color=c, zorder=4))
# rolling 120-bar profile (bars 1..120) on the last bar + buy/sell split at the right edge
LB, RW = 120, 40; s = slice(N - 1 - LB, N - 1); ph, pl = H[s].max(), L[s].min(); st = (ph - pl) / RW
rv, rb = np.zeros(RW), np.zeros(RW)
for hh, ll, oo, cc, vv in zip(H[s], L[s], O[s], C[s], day.volume.to_numpy()[s]):
    for r in range(int(np.clip((ll - pl) // st, 0, RW - 1)), int(np.clip((hh - pl) // st, 0, RW - 1)) + 1):
        rl_ = pl + r * st; add = vv * max(0, min(hh, rl_ + st) - max(ll, rl_)) / max(hh - ll, 1e-9); rv[r] += add; rb[r] += add if cc >= oo else 0
pi = int(np.argmax(rv)); a0 = a1 = pi; acc = rv[pi]
while acc < VA * rv.sum() and (a0 > 0 or a1 < RW - 1):
    u = rv[a1 + 1] if a1 < RW - 1 else -1; d_ = rv[a0 - 1] if a0 > 0 else -1
    if u >= d_: a1 += 1; acc += u
    else: a0 -= 1; acc += d_
x0 = N + 8
for r in range(RW):
    u, d_ = 40 * rb[r] / rv.max(), 40 * (rv[r] - rb[r]) / rv.max()
    cu = "#ff4d4d" if r == pi else "#2f7fd1"; cd = "#ff4d4d" if r == pi else "#c9a227"
    ax.add_patch(Rectangle((x0, pl + r * st), u, st * .95, color=cu, alpha=.8, zorder=5)); ax.add_patch(Rectangle((x0 + u, pl + r * st), d_, st * .95, color=cd, alpha=.8, zorder=5))
for y, t, c in ((pl + (pi + .5) * st, "POC", "#ff4d4d"), (pl + (a1 + 1) * st, "VAH", "#26c6da"), (pl + a0 * st, "VAL", "#26c6da")):
    ax.hlines(y, N - 40, N + 1, color=c, lw=1.5, zorder=5); ax.text(N + 2, y, t, color=c, fontsize=10, va="center", weight="bold", zorder=6)
mt = day.index; x0v = max(0, shown[0][0] - 30); ticks = range(x0v, N, 10)
ax.set_xticks(list(ticks)); ax.set_xticklabels([mt[i].strftime("%m-%d") for i in ticks], color=MUT)
ax.set_xlim(x0v - 12, END + 5); yl, yh = L[x0v:].min(), H[x0v:].max(); ax.set_ylim(yl - (yh - yl) * .08, yh + (yh - yl) * .08)
ax.set_title(f"{SYM} · يومي · محاكاة بايثون لمنطق المؤشر الحالي (ليست لقطة TradingView)", color=TX, fontsize=13, loc="right")
# ---- status panel, same rows as the Pine table
import pandas as pd
from matplotlib.patches import FancyBboxPatch
cs = pd.Series(C); e20, e50 = cs.ewm(span=20).mean().iat[-1], cs.ewm(span=50).mean().iat[-1]
up_, dn_ = np.r_[0, np.diff(H)], np.r_[0, -np.diff(L)]
pdm, mdm = np.where((up_ > dn_) & (up_ > 0), up_, 0), np.where((dn_ > up_) & (dn_ > 0), dn_, 0)
rma = lambda x: pd.Series(x).ewm(alpha=1 / 14).mean().to_numpy()
pdi, mdi = 100 * rma(pdm) / rma(tr), 100 * rma(mdm) / rma(tr); adx = rma(100 * np.abs(pdi - mdi) / np.maximum(pdi + mdi, 1e-9))[-1]
td = 1 if e20 > e50 and pdi[-1] > mdi[-1] else -1 if e20 < e50 and mdi[-1] > pdi[-1] else 0
vol = day.volume.to_numpy(); vr = vol[-1] / vol[-21:-1].mean(); cl = C[-1]
wu = min([x for x in LV if x > cl], default=np.nan); wd = max([x for x in LV if x < cl], default=np.nan)
pc, vh, vl = VAS; nd = N - r0
ptxt = "فوق VAH" if cl > vh else "تحت VAL" if cl < vl else "بين POC و VAH" if cl >= pc else "بين VAL و POC"
rtxt = "قيد التكوين" if nd < WLEN else "السعر فوق القمة" if cl > rh else "السعر تحت القاع" if cl < rl else "السعر داخل المنطقة"
dist = lambda x: f"{'+' if x >= cl else '-'}{abs(x - cl):.2f}   |   {'+' if x >= cl else '-'}{100 * abs(x - cl) / cl:.2f}%"
G_, R_, Y_, P_ = "#00e676", "#ff5252", "#f0c419", "#9b5cff"
rows = [("الاتجاه", ("صاعد" if td > 0 else "هابط" if td < 0 else "عرضي") + (" قوي" if adx >= 25 and td else ""), f"ADX {adx:.0f}", G_ if td > 0 else R_ if td < 0 else MUT),
        ("الفوليوم", "ضعيف" if vr < .8 else "قوي" if vr >= 1.5 else "عادي", f"{vr:.1f}x مقارنة بالمتوسط", Y_ if vr < .8 else G_ if vr >= 1.5 else TX),
        ("المنطقة العرضية", rtxt, f"{rl:.2f} - {rh:.2f}   |   {nd} يوم", Y_),
        ("أقرب خط حوت فوق", f"{wu:.2f}", dist(wu), P_), ("أقرب خط حوت تحت", f"{wd:.2f}", dist(wd), P_),
        ("موقع السعر من القيمة", ptxt, f"POC {pc:.2f}   VAH {vh:.2f}   VAL {vl:.2f}", G_ if cl > vh else R_ if cl < vl else TX),
        ("آخر إشارة", "لا توجد على هذه الفترة", "-", MUT)]
tp = fig.add_axes([0.745, 0.06, 0.245, 0.88], facecolor=BG); tp.axis("off"); tp.set_xlim(0, 1); tp.set_ylim(0, 1)
tp.add_patch(FancyBboxPatch((0, .02), 1, .96, boxstyle="round,pad=0.005", fc="#1e222d", ec=GR))
tp.text(.96, .95, "مناطق الفوليوم", color=TX, fontsize=13, ha="right", weight="bold"); tp.text(.04, .95, f"{SYM} · D · {cl:.2f}", color=MUT, fontsize=10)
y = .86
for lbl, v1, v2, col in rows:
    tp.text(.96, y, lbl, color=MUT, fontsize=10.5, ha="right", va="center"); tp.text(.60, y + .015, v1, color=col, fontsize=11.5, ha="right", weight="bold", va="center")
    tp.text(.60, y - .022, v2, color=MUT, fontsize=9.5, ha="right", va="center"); tp.plot([.03, .97], [y - .05, y - .05], color=GR, lw=.8); y -= .1
tp.add_patch(FancyBboxPatch((.03, .05), .94, .12, boxstyle="round,pad=0.005", fc="#25282f", ec=MUT))
tp.text(.94, .135, "الخلاصة: لا توجد إشارة. أقرب خط حوت فوق وتحت السعر:", color=TX, fontsize=10.5, ha="right", weight="bold")
tp.text(.94, .08, f"▲ {wu:.2f}   |   ▼ {wd:.2f}", color=TX, fontsize=11, ha="right")
fig.savefig(ROOT / "reports/styles/R_ranges_preview.png", dpi=100, facecolor=BG)
print(len(ranges), "ranges, live:", live, [ (str(mt[a].date()), str(mt[min(b,N-1)].date())) for a,b in shown])
