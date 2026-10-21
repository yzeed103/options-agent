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
N = len(day); fig, ax = plt.subplots(figsize=(19, 10), facecolor=BG); ax.set_facecolor(BG)
ax.tick_params(colors=MUT); [s.set_color(GR) for s in ax.spines.values()]; ax.grid(color=GR, lw=.3)
END = N + 45
shown = ranges[-2:] + ([live] if live else [])
for a, b in shown:
    isl = live is not None and (a, b) == live
    lo, hi, pk, poc, vah, val = profile(a, b)
    ax.add_patch(Rectangle((a - .5, lo), b - a, hi - lo, fc="#ffb02010", ec="#ffb020", ls="--", lw=1.2, zorder=1))
    ax.text(a, hi, " منطقة قيد التكوين" if isl else " منطقة عرضية مكتملة", color="#ffb020", fontsize=10, va="bottom")
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
fig.tight_layout(); fig.savefig(ROOT / "reports/styles/R_ranges_preview.png", dpi=100, facecolor=BG)
print(len(ranges), "ranges, live:", live, [ (str(mt[a].date()), str(mt[min(b,N-1)].date())) for a,b in shown])
