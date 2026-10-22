"""Simulated 5m SPY chart of the current Pine logic: whale levels (every daily sideways range, 200-row profile from
15m bars), the thick line on the level price is heading to (instant trend EMA 9/21 + DMI 7), Supertrend(10,3)
trend-hold line, and the status panel rows incl. today's call / put whale targets hit. Real data."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd, matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyBboxPatch
from vzones.intraday.data import load_csv, rth
ROOT = pathlib.Path(__file__).resolve().parent.parent
AGG = dict(open="first", high="max", low="min", close="last", volume="sum")
WLEN, WMULT, ROWS, PEAKS = 10, 6.0, 200, 8
raw = rth(load_csv(ROOT / "data/intraday/SPY_5m.csv"))[["open", "high", "low", "close", "volume"]]; raw.index = raw.index.tz_localize(None)
m15 = raw.resample("15min").agg(AGG).dropna(); day = raw.resample("1D").agg(AGG).dropna()
H, L, C = day.high.to_numpy(), day.low.to_numpy(), day.close.to_numpy()
tr = np.maximum(H - L, np.abs(np.r_[C[0], C[:-1]] - H)); atr = pd.Series(tr).ewm(alpha=1 / 14).mean().to_numpy()
ranges, r0, rh, rl = [], 0, H[0], L[0]
for n in range(1, len(day) - 1):                        # completed days only (today is the chart day)
    if n - r0 < WLEN:
        rh, rl = max(rh, H[n]), min(rl, L[n])
        if rh - rl > WMULT * atr[n]: r0, rh, rl = n, H[n], L[n]
    elif C[n] > rh or C[n] < rl: ranges.append((r0, n + 1)); r0, rh, rl = n, H[n], L[n]
    else: rh, rl = max(rh, H[n]), min(rl, L[n])
shown = ranges[-2:] + [(r0, len(day) - 1)]
def levels(a, b):
    bars = m15[(m15.index >= day.index[a]) & (m15.index < day.index[b])]
    lo, hi = bars.low.min(), bars.high.max(); st = (hi - lo) / ROWS; pv = np.zeros(ROWS)
    for r in bars.itertuples():
        for q in range(int(np.clip((r.low - lo) // st, 0, ROWS - 1)), int(np.clip((r.high - lo) // st, 0, ROWS - 1)) + 1):
            ql = lo + q * st; pv[q] += r.volume * max(0, min(r.high, ql + st) - max(r.low, ql)) / max(r.high - r.low, 1e-9)
    sm = np.convolve(pv, np.ones(3) / 3, "same"); nb = max(2, ROWS // 40)
    pk = sorted([q for q in range(ROWS) if sm[q] >= 1.3 * sm.mean() and sm[q] == sm[max(0, q - nb):q + nb + 1].max()], key=lambda q: -sm[q])[:PEAKS]
    pi = int(np.argmax(pv)); a0 = a1 = pi; acc = pv[pi]
    while acc < .7 * pv.sum() and (a0 > 0 or a1 < ROWS - 1):
        u = pv[a1 + 1] if a1 < ROWS - 1 else -1; d = pv[a0 - 1] if a0 > 0 else -1
        if u >= d: a1 += 1; acc += u
        else: a0 -= 1; acc += d
    return [lo + (q + .5) * st for q in pk], (lo + (pi + .5) * st, lo + (a1 + 1) * st, lo + a0 * st)
LV, VA = [], None
for a, b in shown:
    pk, VA = levels(a, b); LV += pk
LV = sorted(set(np.round(LV + list(VA), 2)))
# chart: last 2 sessions of 5m
w = raw[raw.index >= day.index[-2]].copy(); full = raw.copy()
c = full.close; ef, es = c.ewm(span=9, adjust=False).mean(), c.ewm(span=21, adjust=False).mean()
up_, dn_ = full.high.diff(), -full.low.diff()
pdm = np.where((up_ > dn_) & (up_ > 0), up_, 0); mdm = np.where((dn_ > up_) & (dn_ > 0), dn_, 0)
trr = pd.concat([full.high - full.low, (full.high - c.shift()).abs(), (full.low - c.shift()).abs()], axis=1).max(axis=1)
rma = lambda x, n: pd.Series(np.asarray(x, float), index=full.index).ewm(alpha=1 / n, adjust=False).mean()
pdi, mdi = 100 * rma(pdm, 7) / rma(trr, 7), 100 * rma(mdm, 7) / rma(trr, 7); adx = rma(100 * (pdi - mdi).abs() / (pdi + mdi), 7)
nowDir = np.where((ef > es) & (pdi > mdi), 1, np.where((ef < es) & (mdi > pdi), -1, 0))
# supertrend 10,3
at = rma(trr, 10).to_numpy(); hl2 = ((full.high + full.low) / 2).to_numpy(); cc = c.to_numpy()
ub, lb = hl2 + 3 * at, hl2 - 3 * at; st = np.zeros(len(full)); sd = np.ones(len(full))
for i in range(1, len(full)):
    lb[i] = lb[i] if lb[i] > lb[i - 1] or cc[i - 1] < lb[i - 1] else lb[i - 1]
    ub[i] = ub[i] if ub[i] < ub[i - 1] or cc[i - 1] > ub[i - 1] else ub[i - 1]
    sd[i] = (-1 if cc[i] > ub[i - 1] else 1) if st[i - 1] == ub[i - 1] else (1 if cc[i] < lb[i - 1] else -1)
    st[i] = lb[i] if sd[i] < 0 else ub[i]
off = len(full) - len(w)
# heading level state machine
hDir, hL, hLast, heads = 0, np.nan, "", []; hh_, ll_ = full.high.to_numpy(), full.low.to_numpy()
for i in range(off, len(full)):
    if hDir:
        if (hDir > 0 and hh_[i] >= hL) or (hDir < 0 and ll_[i] <= hL): hLast = f"وصل {hL:.2f} ✓"; hDir = 0
        elif nowDir[i] == -hDir: hLast = f"انعكس قبل {hL:.2f}"; hDir = 0
    if not hDir and nowDir[i]:
        cand = [x for x in LV if (x - cc[i]) * nowDir[i] > 0]
        if cand: hDir = int(nowDir[i]); hL = min(cand, key=lambda x: abs(x - cc[i]))
    heads.append((hDir, hL))
BG, GR, TX, MUT = "#0b0e14", "#2a2e39", "#d1d4dc", "#8a8f9c"
fig = plt.figure(figsize=(21, 10.5), facecolor=BG); ax = fig.add_axes([0.03, 0.06, 0.66, 0.88], facecolor=BG)
ax.tick_params(colors=MUT); [s.set_color(GR) for s in ax.spines.values()]; ax.grid(color=GR, lw=.3)
N = len(w); lo, hi = w.low.min(), w.high.max(); pad = (hi - lo) * .15
for x in LV:
    if lo - pad < x < hi + pad:
        isva = np.isclose(x, np.round(VA, 2)).any(); col = "#ff3b3b" if np.isclose(x, round(VA[0], 2)) else "#ffb020" if isva else "#9b5cff"
        ax.hlines(x, -1, N + 6, color=col, lw=2 if isva else 1, zorder=2); ax.text(N + 7, x, f"{x:.2f}", color=col, fontsize=8, va="center")
for i, r in enumerate(w.itertuples()):
    col = "#26a69a" if r.close >= r.open else "#ef5350"
    ax.vlines(i, r.low, r.high, color=col, lw=.8, zorder=4); ax.add_patch(Rectangle((i - .33, min(r.open, r.close)), .66, max(abs(r.close - r.open), 1e-3), color=col, zorder=4))
stw, sdw = st[off:], sd[off:]
for i in range(1, N):
    if sdw[i] == sdw[i - 1]: ax.plot([i - 1, i], [stw[i - 1], stw[i]], color="#00e676" if sdw[i] < 0 else "#ff5252", lw=1.3, alpha=.8, zorder=3)
hd, hl = heads[-1]
if hd:
    ax.hlines(hl, -1, N + 6, color="#9b5cff", lw=5, zorder=5)
    ax.text(N - 2, hl, ("▲ " if hd > 0 else "▼ ") + f"متجه إلى {hl:.2f}", color="#b98cff", fontsize=11, weight="bold", ha="right", va="bottom", zorder=6)
sess = w.index.normalize(); starts = np.r_[0, np.flatnonzero(sess[1:] != sess[:-1]) + 1]
for s_ in starts: ax.axvline(s_ - .5, color=MUT, lw=.8, ls=":")
ticks = list(range(0, N, 12)); ax.set_xticks(ticks); ax.set_xticklabels([w.index[i].strftime("%m-%d %H:%M") for i in ticks], color=MUT, fontsize=8)
ax.set_xlim(-2, N + 14); ax.set_ylim(lo - pad, hi + pad)
ax.set_title("SPY · 5 دقائق · محاكاة بايثون لمنطق المؤشر (ليست لقطة TradingView)", color=TX, loc="right", fontsize=13)
ax.text(.01, .02, "الخط الأخضر/الأحمر المتعرج = خط كسر الترند (Supertrend)، مطفأ افتراضياً في المؤشر", color=MUT, fontsize=9, transform=ax.transAxes)
# panel
today = w[w.index.normalize() == sess[-1]]; dO, dH, dL, cl = today.open.iat[0], today.high.max(), today.low.min(), cc[-1]
cT = [x for x in LV if x > dO]; pT = [x for x in LV if x < dO]; cH = sum(dH >= x for x in cT); pH = sum(dL <= x for x in pT)
nd = int(nowDir[-1]); ax_ = adx.iat[-1]; flip = int(np.argmax(sd[::-1] != sd[-1])); up = sd[-1] < 0
G_, R_, Y_ = "#00e676", "#ff5252", "#ffeb3b"
dist = lambda x: f"{'+' if x >= cl else '-'}{abs(x - cl):.2f}   |   {'+' if x >= cl else '-'}{100 * abs(x - cl) / cl:.2f}%"
rows = [("الاتجاه", ("صاعد" if nd > 0 else "هابط" if nd < 0 else "عرضي") + (" قوي" if ax_ >= 25 and nd else ""), f"ADX {ax_:.0f}   |   متوسط 9 و 21", G_ if nd > 0 else R_ if nd < 0 else MUT),
        ("أهداف الحيتان اليوم", f"كول {cH} من {len(cT)}   |   بوت {pH} من {len(pT)}", f"الافتتاح {dO:.2f}   أعلى {dH:.2f}   أدنى {dL:.2f}", G_ if cH > pH else R_ if pH > cH else TX),
        ("متجه إلى", ("▲ صاعد إلى " if hd > 0 else "▼ هابط إلى ") + f"{hl:.2f}" if hd else "لا يوجد", (dist(hl) if hd else "") + (f"   السابق: {hLast}" if hLast else ""), "#b98cff"),
        ("صمود الترند", ("الترند الصاعد صامد" if up else "الترند الهابط صامد") if flip > 2 else ("انكسر الهابط، بدأ صعود" if up else "انكسر الصاعد، بدأ هبوط"),
         f"ينكسر إذا أغلق {'تحت' if up else 'فوق'} {st[-1]:.2f}   |   منذ {flip} شمعة", G_ if up else R_)]
tp = fig.add_axes([0.705, 0.25, 0.285, 0.69], facecolor=BG); tp.axis("off"); tp.set_xlim(0, 1); tp.set_ylim(0, 1)
tp.add_patch(FancyBboxPatch((0, .02), 1, .96, boxstyle="round,pad=0.005", fc="#1e222d", ec=GR))
tp.text(.96, .93, "الصفوف الجديدة في الجدول", color=TX, fontsize=13, ha="right", weight="bold"); tp.text(.04, .93, f"SPY · 5 · {cl:.2f}", color=MUT, fontsize=10)
y = .78
for lbl, v1, v2, col in rows:
    tp.text(.96, y, lbl, color=MUT, fontsize=11, ha="right", va="center"); tp.text(.66, y + .03, v1, color=col, fontsize=12, ha="right", weight="bold", va="center")
    tp.text(.66, y - .035, v2, color=MUT, fontsize=9.5, ha="right", va="center"); tp.plot([.03, .97], [y - .09, y - .09], color=GR, lw=.8); y -= .19
fig.savefig(ROOT / "reports/styles/U_intraday_targets.png", dpi=95, facecolor=BG)
print(dict(levels=len(LV), call=f"{cH}/{len(cT)}", put=f"{pH}/{len(pT)}", head=(hd, hl), last=hLast, st=round(st[-1], 2), up=up, flip=flip))
