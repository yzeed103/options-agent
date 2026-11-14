"""Two proposals for approval, drawn on real SPY data (Alpaca 5m, Apr 2025 - Oct 2026):
the current week's candle and today's candle, each in 4 equal parts from open to close."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import numpy as np, matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from vzones.intraday.data import load_csv, rth
from vzones.ranges import AGG, daily_ranges, range_levels
ROOT = pathlib.Path(__file__).resolve().parent.parent
raw = rth(load_csv(ROOT / "data/intraday/SPY_5m_alpaca.csv")); raw.index = raw.index.tz_localize(None)
h60 = raw.resample("60min").agg(AGG).dropna(); day = raw.resample("1D").agg(AGG).dropna()
wk = raw.resample("W-MON", label="left", closed="left").agg(AGG).dropna()
BG, GR, TX, MUT = "#0b0e14", "#2a2e39", "#d1d4dc", "#8a8f9c"
def candles(ax, df, x0=0):
    for i, r in enumerate(df.itertuples()):
        col = "#26a69a" if r.close >= r.open else "#ef5350"
        ax.vlines(x0 + i, r.low, r.high, color=col, lw=.8); ax.add_patch(Rectangle((x0 + i - .32, min(r.open, r.close)), .64, max(abs(r.close - r.open), 1e-3), color=col, zorder=3))
def style(ax, t):
    ax.set_facecolor(BG); ax.tick_params(colors=MUT); [s.set_color(GR) for s in ax.spines.values()]; ax.set_title(t, color=TX, fontsize=13, loc="right")
# ---------- every day and every week, each in 4 equal parts (open -> close), on a 15m chart ----------
m15 = raw.resample("15min").agg(AGG).dropna()
wk0 = m15.index[-1].normalize() - np.timedelta64(m15.index[-1].weekday() + 14, "D")   # three weeks
w = m15[m15.index >= wk0]; N = len(w)
fig, ax = plt.subplots(figsize=(20, 10), facecolor=BG)
style(ax, "كل يوم وكل أسبوع مقسوم 4 أجزاء متساوية (تاريخي) · SPY · 15 دقيقة · محاكاة (ليست لقطة TradingView)")
candles(ax, w)
def segs(key, cEnd, cMid, cQ, lwm, z):
    grp = np.array([key(t) for t in w.index]); starts = np.r_[0, np.flatnonzero(grp[1:] != grp[:-1]) + 1]; ends = np.r_[starts[1:], N]
    for k_, (a_, b_) in enumerate(zip(starts, ends)):
        g = w.iloc[a_:b_]; o, c = g.open.iat[0], g.close.iat[-1]; live = k_ == len(starts) - 1
        for q in range(5):
            y = o + (c - o) * q / 4; col = cMid if q == 2 else cEnd if q in (0, 4) else cQ
            ax.hlines(y, a_ - .5, (N + 3) if live else b_ - .5, color=col, lw=lwm if q == 2 else 1.1, ls="--" if q in (1, 3) else "-", zorder=z)
    return starts
ws = segs(lambda t: (t - np.timedelta64(t.weekday(), "D")).date(), "#90caf9", "#00e5ff", "#4dd0e1", 2.6, 2)
ds = segs(lambda t: t.date(), "#ffffff", "#e040fb", "#ffb020", 1.8, 4)
for s_ in ds: ax.axvline(s_ - .5, color=GR, lw=.6)
for s_ in ws: ax.axvline(s_ - .5, color="#4dd0e1", lw=1.2, ls=":"); ax.text(s_ + 1, w.high.max() + .5, "أسبوع " + w.index[s_].strftime("%m-%d"), color="#4dd0e1", fontsize=10)
ax.set_xlim(-2, N + 6); ticks = list(ds); ax.set_xticks(ticks); ax.set_xticklabels([w.index[t].strftime("%a\n%m-%d") for t in ticks], color=MUT, fontsize=8)
ax.set_ylim(w.low.min() - 1, w.high.max() + 2)
ax.text(.01, .02, "كل يوم له خطوطه الخمسة على مداه فقط (أبيض / بنفسجي / برتقالي) · كل أسبوع له خطوطه على مداه (أزرق / سماوي)\nالأيام والأسابيع السابقة بإغلاقها النهائي · الحالي بآخر سعر ويمتد لليمين",
        color=TX, fontsize=10, transform=ax.transAxes, bbox=dict(fc="#1e222d", ec=GR))
fig.tight_layout(); fig.savefig(ROOT / "reports/styles/Z3_quarters_history.png", dpi=90, facecolor=BG)
