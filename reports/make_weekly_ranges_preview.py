"""Weekly whale ranges exactly as the Pine code draws them (section G_WK): first 4 weekly candles set top / bottom unless
wider than 5x weekly ATR, the first weekly close outside ends the range (breakout week included), hidden 200-row
profile of 15m bars -> tall columns (blue), POC (red), VAH / VAL (cyan), dashed box. Real SPY data (Alpaca 5m)."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import numpy as np, matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from vzones.intraday.data import load_csv, rth
from vzones.ranges import AGG, daily_ranges, range_levels
ROOT = pathlib.Path(__file__).resolve().parent.parent
raw = rth(load_csv(ROOT / "data/intraday/SPY_5m_alpaca.csv")); raw.index = raw.index.tz_localize(None)
h60 = raw.resample("15min").agg(AGG).dropna(); day = raw.resample("1D").agg(AGG).dropna()
wk = raw.resample("W-MON", label="left", closed="left").agg(AGG).dropna()
BG, GR, TX, MUT = "#0b0e14", "#2a2e39", "#d1d4dc", "#8a8f9c"
def candles(ax, df, x0=0):
    for i, r in enumerate(df.itertuples()):
        col = "#26a69a" if r.close >= r.open else "#ef5350"
        ax.vlines(x0 + i, r.low, r.high, color=col, lw=.8); ax.add_patch(Rectangle((x0 + i - .32, min(r.open, r.close)), .64, max(abs(r.close - r.open), 1e-3), color=col, zorder=3))
def style(ax, t):
    ax.set_facecolor(BG); ax.tick_params(colors=MUT); [s.set_color(GR) for s in ax.spines.values()]; ax.set_title(t, color=TX, fontsize=13, loc="right")
# ---------- 1) weekly ranges on a daily chart ----------
done, state = daily_ranges(wk, 4, 5.0)
r0 = state[-1][0]; ranges = [(a, b, False) for a, b, _ in done][-2:] + ([(r0, len(wk), True)] if len(wk) - r0 >= 4 else [])
fig, ax = plt.subplots(figsize=(19, 10), facecolor=BG); style(ax, "١) مناطق الحيتان الأسبوعية على شارت يومي · SPY · محاكاة بايثون (ليست لقطة TradingView)")
dix = {d.normalize(): i for i, d in enumerate(day.index)}; candles(ax, day); N = len(day)
for a, b, live in ranges:
    t0 = wk.index[a]; t1 = wk.index[b] if b < len(wk) else day.index[-1] + np.timedelta64(1, "D")
    res = range_levels(h60, t0, t1)
    if not res: continue
    pk, (poc, vah, val) = res; x0 = min(i for d, i in dix.items() if d >= t0); x1 = max(i for d, i in dix.items() if d < t1)
    lo, hi = h60[(h60.index >= t0) & (h60.index < t1)].low.min(), h60[(h60.index >= t0) & (h60.index < t1)].high.max()
    ax.add_patch(Rectangle((x0 - .5, lo), x1 - x0 + 1, hi - lo, fc="#00bcd410", ec="#00bcd4", ls="--", lw=1.4, zorder=1))
    ax.text(x0, hi, " منطقة أسبوعية قيد التكوين" if live else " منطقة أسبوعية مكتملة", color="#00bcd4", fontsize=10, va="bottom")
    for y in pk: ax.hlines(y, x0 - .5, N + 8, color="#1e88e5", lw=1, zorder=2)
    ax.hlines(poc, x0 - .5, N + 8, color="#ff3b3b", lw=3, zorder=2); ax.hlines([vah, val], x0 - .5, N + 8, color="#00bcd4", lw=2, zorder=2)
    for y, t, c in ((poc, "POC", "#ff3b3b"), (vah, "VAH", "#00bcd4"), (val, "VAL", "#00bcd4")): ax.text(x0 - 1, y, f"{t} {y:.2f}", color=c, fontsize=9, ha="right", va="center", weight="bold")
ticks = list(range(0, N, 21)); ax.set_xticks(ticks); ax.set_xticklabels([day.index[i].strftime("%Y-%m") for i in ticks], color=MUT)
xs = min(i for d, i in dix.items() if d >= wk.index[ranges[0][0]]) - 15; ax.set_xlim(max(-1, xs), N + 10)
lo_, hi_ = day.low.iloc[max(0, xs):].min(), day.high.iloc[max(0, xs):].max(); ax.set_ylim(lo_ - (hi_ - lo_) * .05, hi_ + (hi_ - lo_) * .05)
ax.text(.01, .02, "أزرق = أعمدة الحيتان الأسبوعية · سماوي = VAH / VAL الأسبوعي · أحمر عريض = POC الأسبوعي\n(لون مختلف عن اليومي البنفسجي/البرتقالي حتى تفرّق بينهم)", color=TX, fontsize=10, transform=ax.transAxes, bbox=dict(fc="#1e222d", ec=GR))
fig.tight_layout(); fig.savefig(ROOT / "reports/styles/Z1_weekly_ranges.png", dpi=90, facecolor=BG)
print("weekly ranges:", [(str(wk.index[a].date()), live) for a, b, live in ranges])
