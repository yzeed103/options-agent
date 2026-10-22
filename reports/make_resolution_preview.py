"""Same range, same 200 rows: reference profile from 5m bars (stands in for TradingView FRVP) vs the indicator's
POC/VAH/VAL built from 60m bars (old default) and 15m bars (new default). Real SPY data."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import numpy as np, matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from vzones.intraday.data import load_csv, rth
ROOT = pathlib.Path(__file__).resolve().parent.parent
AGG = dict(open="first", high="max", low="min", close="last", volume="sum")
raw = rth(load_csv(ROOT / "data/intraday/SPY_5m.csv"))[["open", "high", "low", "close", "volume"]]; raw.index = raw.index.tz_localize(None)
days = raw.resample("1D").agg(AGG).dropna().index
seg = raw[(raw.index >= days[-25]) & (raw.index < days[-5])]; lo, hi = seg.low.min(), seg.high.max(); R = 200; st = (hi - lo) / R
def prof(b):
    pv = np.zeros(R)
    for r in b.itertuples():
        for q in range(int(np.clip((r.low - lo) // st, 0, R - 1)), int(np.clip((r.high - lo) // st, 0, R - 1)) + 1):
            ql = lo + q * st; pv[q] += r.volume * max(0, min(r.high, ql + st) - max(r.low, ql)) / max(r.high - r.low, 1e-9)
    pi = int(np.argmax(pv)); a0 = a1 = pi; acc = pv[pi]
    while acc < .7 * pv.sum() and (a0 > 0 or a1 < R - 1):
        u = pv[a1 + 1] if a1 < R - 1 else -1; d = pv[a0 - 1] if a0 > 0 else -1
        if u >= d: a1 += 1; acc += u
        else: a0 -= 1; acc += d
    return pv, lo + (pi + .5) * st, lo + (a1 + 1) * st, lo + a0 * st
BG, TX, MUT = "#0b0e14", "#d1d4dc", "#8a8f9c"
ref = prof(seg); res = {"60min": prof(seg.resample("60min").agg(AGG).dropna()), "15min": prof(seg.resample("15min").agg(AGG).dropna())}
fig, axs = plt.subplots(1, 2, figsize=(18, 10), facecolor=BG, sharey=True)
for ax, (tf, name) in zip(axs, (("60min", "قبل: البروفايل من شموع الساعة"), ("15min", "بعد: البروفايل من شموع 15 دقيقة"))):
    ax.set_facecolor(BG); ax.tick_params(colors=MUT); [s.set_color("#2a2e39") for s in ax.spines.values()]
    y = lo + (np.arange(R) + .5) * st
    ax.barh(y, ref[0] / ref[0].max(), height=st * .9, color="#9598a1", alpha=.55, label="FRVP مرجعي (شموع 5 دقائق)")
    for k, (t, c) in enumerate((("POC", "#ff3b3b"), ("VAH", "#ffb020"), ("VAL", "#ffb020"))):
        yr, ym = ref[k + 1], res[tf][k + 1]
        ax.axhline(yr, color="white", lw=1, ls=":"); ax.axhline(ym, color=c, lw=2.5)
        dr = (ym - yr) / st
        ax.text(1.02, ym, f"{t} {ym:.2f}   إزاحة {dr:+.0f} صف", color=c, fontsize=12, va="bottom", weight="bold", bbox=dict(fc=BG, ec="none", pad=1))
    ax.set_xlim(0, 1.6); ax.set_xticks([])
    ax.set_title(name, color=TX, fontsize=15)
axs[0].text(.02, .02, "الخط المنقط الأبيض = مكان الخط في FRVP المرجعي\nالخط الملوّن = مكان الخط في المؤشر", color=TX, fontsize=11, transform=axs[0].transAxes)
fig.suptitle(f"SPY · نفس الفترة ({days[-25].date()} إلى {days[-5].date()}) · 200 صف · بيانات حقيقية", color=TX, fontsize=14)
fig.tight_layout(); fig.savefig(ROOT / "reports/styles/T_resolution_check.png", dpi=95, facecolor=BG)
print({tf: [round((res[tf][k + 1] - ref[k + 1]) / st) for k in range(3)] for tf in res})
