"""Simulated full-indicator view (same logic in Python) on real UNH 15m data: 3-colour heat ribbons, rolling
POC/VAH/VAL, prior-day value area, whale levels (POC red / others purple), signals and the Arabic status panel."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd, matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyBboxPatch
import vzones
from vzones.intraday.data import load_csv, rth
from vzones.intraday.features import add_features
from vzones.intraday.signals import va_accept, apply_filters
from vzones.intraday.whale_features import add_whale_levels, whale_bounce, K
from vzones.whale_levels import find_ranges, profile_levels, AGG
ROOT = pathlib.Path(__file__).resolve().parent.parent
SYM = "UNH"
d = add_whale_levels(add_features(rth(load_csv(ROOT / f"data/intraday/{SYM}_15m.csv"))), specs=(("1D", 20, 6.0),))
vz = vzones.compute(d[["open", "high", "low", "close", "volume"]], vzones.VZParams(lookback=120, rows=40, weak_ratio=0.8, break_ratio=1.5, adx_strong=25))
N = 26 * 9; w = d.iloc[-N:]; v = vz.iloc[-N:]; off = len(d) - N
lo, hi = w.low.min(), w.high.max(); yr = hi - lo
edges = np.linspace(lo - .05 * yr, hi + .05 * yr, 81)
g, _ = vzones.heatmap(d.iloc[off - 120:][["open", "high", "low", "close", "volume"]], 120, edges=edges); g = np.nan_to_num(g[120:])
BG, GR, TX, MUT, UP, DN = "#131722", "#2a2e39", "#d1d4dc", "#8a8f9c", "#26a69a", "#ef5350"
fig = plt.figure(figsize=(19, 10), facecolor=BG)
ax = fig.add_axes([0.03, 0.06, 0.70, 0.88], facecolor=BG)
ax.tick_params(colors=MUT); [q.set_color(GR) for q in ax.spines.values()]; ax.grid(color=GR, lw=.3)
hb = edges[1] - edges[0]
for k in range(len(edges) - 1):        # ribbons: merge equal levels
    lvl = np.where(g[:, k] >= .8, 2, np.where(g[:, k] >= .6, 1, np.where(g[:, k] >= .4, 0, -1)))
    i = 0
    while i < N:
        if lvl[i] < 0: i += 1; continue
        j = i
        while j + 1 < N and lvl[j + 1] == lvl[i]: j += 1
        ax.add_patch(Rectangle((i - .5, edges[k] + hb * .12), j - i + 1, hb * .76, color=["#1a2a6c", "#7b3fbf", "#ff4fa3"][lvl[i]], alpha=.55, lw=0, zorder=1))
        i = j + 1
x = np.arange(N)
ax.step(x, v.poc, where="mid", color="#ff4d4d", lw=1, alpha=.9, zorder=3)
ax.step(x, v.vah, where="mid", color="#9598a1", lw=.8, alpha=.6, zorder=3); ax.step(x, v.val, where="mid", color="#9598a1", lw=.8, alpha=.6, zorder=3)
ax.step(x, w.pd_vah, where="mid", color="#5c8dff", lw=1, ls="--", zorder=3); ax.step(x, w.pd_val, where="mid", color="#5c8dff", lw=1, ls="--", zorder=3)
# whale levels
raw = d[["open", "high", "low", "close", "volume"]].copy(); raw.index = raw.index.tz_localize(None)
daily = raw.resample("1D").agg(AGG).dropna(); rgs = find_ranges(daily, 20, 6.0)
s0, e0, brk, rh, rl = rgs[-1]
bars = raw[(raw.index >= s0) & (raw.index < daily.index[daily.index.get_loc(e0) + 1])]
pk, _, cen, prof = profile_levels(bars); poc_w = cen[int(np.argmax(prof))]
for L in pk:
    if lo - .05 * yr <= L <= hi + .05 * yr:
        isp = abs(L - poc_w) <= 3 * (cen[1] - cen[0])
        ax.hlines(L, -.5, N + 6, color="#ff3b3b" if isp else "#9b5cff", lw=2 if isp else 1, zorder=4)
        ax.text(N + 6.5, L, f"{L:.2f}" + (" POC" if isp else ""), color="#ff3b3b" if isp else "#9b5cff", fontsize=8, va="center")
# candles (volume-regime colours)
vr = v.vol_ratio.to_numpy()
for i, r in enumerate(w.itertuples()):
    cc = ("#00e676" if r.close >= r.open else "#ff1744") if vr[i] >= 1.5 else ("#4a4e5a" if vr[i] < .8 else (UP if r.close >= r.open else DN))
    ax.vlines(i, r.low, r.high, color=cc, lw=.8, zorder=5)
    ax.add_patch(Rectangle((i - .33, min(r.open, r.close)), .66, max(abs(r.close - r.open), 1e-3), color=cc, zorder=5))
# signals
def lab(i, y, txt, col, up):
    ax.annotate(txt, xy=(i, y), xytext=(i, y + (-1 if up else 1) * .05 * yr), ha="center", va="top" if up else "bottom", fontsize=8, weight="bold",
                color="black", bbox=dict(boxstyle="round,pad=.25", fc=col, ec=col), arrowprops=dict(arrowstyle="-", color=col), zorder=7)
ta = apply_filters(d, va_accept(d), trend="with")[-N:]; wb = whale_bounce(d)[-N:]
c = d.close.to_numpy(); vah_r, val_r = vz.vah.to_numpy(), vz.val.to_numpy()
vas = np.zeros(len(d), int); vas[1:] = np.where((c[:-1] < val_r[:-1]) & (c[1:] > val_r[1:]) & (c[1:] < vah_r[1:]), 1,
                                                np.where((c[:-1] > vah_r[:-1]) & (c[1:] < vah_r[1:]) & (c[1:] > val_r[1:]), -1, 0)); vas = vas[-N:]
pb, hu = v.pool_break.to_numpy(), v.hunt.to_numpy()
def gate(sig, tgt_fn, stop_fn, maxb):
    out = np.zeros_like(sig); st = 0; T = S = B = None
    hh, ll = w.high.to_numpy(), w.low.to_numpy()
    for i in range(N):
        if st:
            if (st > 0 and (hh[i] >= T or ll[i] <= S)) or (st < 0 and (ll[i] <= T or hh[i] >= S)) or i - B >= maxb: st = 0
            continue
        if sig[i]:
            T, S = tgt_fn(i, sig[i]), stop_fn(i, sig[i])
            if T is None: continue
            out[i] = sig[i]; st, B = sig[i], i
    return out
atr_w = w.atr.to_numpy(); cw = w.close.to_numpy(); WL = w[[f"wl_{k}" for k in range(K)]].to_numpy()
def wb_t(i, dr):
    lv = WL[i][np.isfinite(WL[i])]; lv = lv[(lv - cw[i]) * dr >= 3 * atr_w[i]]
    return lv[np.argmin(np.abs(lv - cw[i]))] if len(lv) else None
wb = gate(wb, wb_t, lambda i, dr: cw[i] - dr * atr_w[i], 130)
vas = gate(vas, lambda i, dr: cw[i] + dr * 2 * atr_w[i], lambda i, dr: cw[i] - dr * 1.5 * atr_w[i], 20)
for i in range(N):
    lw_, hw_ = w.low.iat[i], w.high.iat[i]
    if hu[i]: lab(i, lw_ if hu[i] > 0 else hw_, "HUNT", "lime" if hu[i] > 0 else "red", hu[i] > 0)
    elif ta[i]: lab(i, lw_ if ta[i] > 0 else hw_, "اتجاه ↑" if ta[i] > 0 else "اتجاه ↓", "#00e676" if ta[i] > 0 else "#ff5252", ta[i] > 0)
    elif wb[i]: lab(i, lw_ if wb[i] > 0 else hw_, "حوت ↑" if wb[i] > 0 else "حوت ↓", "#00e5ff" if wb[i] > 0 else "#ff9100", wb[i] > 0)
    elif pb[i]: lab(i, hw_ if pb[i] > 0 else lw_, "انعكاس؟", "#ffb020", pb[i] < 0)
    elif vas[i]: lab(i, lw_ if vas[i] > 0 else hw_, "عودة", "#40c4ff" if vas[i] > 0 else "#ffab40", vas[i] > 0)
sess = w.session.to_numpy(); starts = np.r_[0, np.flatnonzero(sess[1:] != sess[:-1]) + 1]
for s_ in starts: ax.axvline(s_ - .5, color=GR, lw=.6)
ax.set_xticks(starts); ax.set_xticklabels([str(sess[s_])[5:] for s_ in starts], color=MUT, fontsize=8)
ax.set_xlim(-1, N + 14); ax.set_ylim(lo - .08 * yr, hi + .08 * yr)
ax.set_title(f"{SYM} · 15m · Volume Zones (محاكاة)", color=TX, loc="left", fontsize=12)
# legend strip
for k_, (cc, nm) in enumerate((("#1a2a6c", "منخفض"), ("#7b3fbf", "متوسط"), ("#ff4fa3", "عالي"))):
    fig.add_artist(Rectangle((.30 + k_ * .055, .015), .012, .014, transform=fig.transFigure, color=cc)); fig.text(.315 + k_ * .055, .016, nm, color=MUT, fontsize=8)
# panel
last = len(d) - 1; vlast = vz.iloc[-1]
tp = fig.add_axes([0.745, 0.06, 0.245, 0.88], facecolor=BG); tp.axis("off"); tp.set_xlim(0, 1); tp.set_ylim(0, 1)
tp.add_patch(FancyBboxPatch((0, 0.02), 1, .96, boxstyle="round,pad=0.005", fc="#1e222d", ec=GR))
adxv = vlast.adx; td = int(vlast.trend_dir)
trend = ("صاعد" if td > 0 else "هابط" if td < 0 else "عرضي") + (" قوي" if adxv >= 25 and td else "")
vrl = vlast.vol_ratio; vtxt = "ضعيف" if vrl < .8 else "قوي" if vrl >= 1.5 else "عادي"
up_ = vlast.hvn_above; dn_ = vlast.hvn_below; cl = d.close.iat[-1]
rows = [("الاتجاه", trend, f"ADX {adxv:.0f}", "#00e676" if td > 0 else "#ff5252" if td < 0 else MUT),
        ("الفوليوم", vtxt, f"{vrl:.1f}x", "#f0c419" if vrl < .8 else "#00e676" if vrl >= 1.5 else TX),
        ("موقع السعر", "داخل منطقة فوليوم" if vlast.in_hvn else "خارج المناطق", "-", TX),
        ("أقرب مقاومة", f"{up_:.2f}" if np.isfinite(up_) else "-", f"+{up_ - cl:.2f}   |   +{100 * (up_ - cl) / cl:.2f}%" if np.isfinite(up_) else "", "#ff9800"),
        ("أقرب دعم", f"{dn_:.2f}" if np.isfinite(dn_) else "-", f"-{cl - dn_:.2f}   |   -{100 * (cl - dn_) / cl:.2f}%" if np.isfinite(dn_) else "", "#00bcd4")]
tp.text(.96, .95, "مناطق الفوليوم", color=TX, fontsize=13, ha="right", weight="bold"); tp.text(.04, .95, f"{SYM} · 15 · {cl:.2f}", color=MUT, fontsize=10)
y = .86
for lbl, val, sub, col in rows:
    tp.text(.96, y, lbl, color=MUT, fontsize=10, ha="right", va="center"); tp.text(.62, y + .012, val, color=col, fontsize=11, ha="right", weight="bold", va="center")
    tp.text(.62, y - .025, sub, color=MUT, fontsize=9, ha="right", va="center"); tp.plot([.03, .97], [y - .055, y - .055], color=GR, lw=.8); y -= .1
tp.text(.96, y, "جاهزية إشارة HUNT", color=TX, fontsize=11, ha="right", weight="bold"); tp.text(.06, y, "1 / 4", color="#f0c419", fontsize=11, weight="bold"); y -= .06
for a_, b_ in (("✗ تجمع فوليوم ضعيف", "✓ هدف أمام السعر"), ("✗ كسر بفوليوم قوي", "✗ ترند قوي")):
    tp.text(.96, y, a_, color=MUT, fontsize=10, ha="right"); tp.text(.5, y, b_, color=MUT if "✗" in b_ else "#00e676", fontsize=10, ha="right"); y -= .05
tp.add_patch(FancyBboxPatch((.03, .05), .94, .14, boxstyle="round,pad=0.005", fc="#2b2610", ec="#f0c419"))
tp.text(.94, .15, "الخلاصة: حياد. أقرب مقاومة وأقرب دعم:", color="#f0c419", fontsize=10.5, ha="right", weight="bold")
tp.text(.94, .09, f"▲ {up_:.2f}   |   ▼ {dn_:.2f}" if np.isfinite(up_) and np.isfinite(dn_) else "-", color=TX, fontsize=10.5, ha="right")
fig.savefig(ROOT / "reports/styles/Q_full_preview.png", dpi=100, facecolor=BG); print("ok")
