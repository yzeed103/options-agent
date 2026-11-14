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
# ---------- current day and current week, each in 4 equal parts (open -> close), on a 5m chart ----------
w = raw[raw.index >= raw.index[-1].normalize() - np.timedelta64(raw.index[-1].weekday(), "D")]
today = w[w.index.normalize() == w.index[-1].normalize()]; N = len(w); c = w.close.iat[-1]
fig, ax = plt.subplots(figsize=(19, 10), facecolor=BG)
style(ax, "شمعة الأسبوع وشمعة اليوم، كل وحدة 4 أجزاء متساوية من الافتتاح للإغلاق · SPY · 5 دقائق · محاكاة (ليست لقطة TradingView)")
candles(ax, w)
names = ("الافتتاح", "ربع", "النصف", "ثلاثة أرباع", "الإغلاق الحالي")
def quarters(o, x0, tag, cEnd, cMid, cQ, dy):
    for k in range(5):
        y = o + (c - o) * k / 4; col = cMid if k == 2 else cEnd if k in (0, 4) else cQ
        ax.hlines(y, x0, N + 2, color=col, lw=2.2 if k == 2 else 1.3, ls="--" if k in (1, 3) else "-", zorder=4)
        ax.text(N + 3 + dy, y, f"{tag} {names[k]} {y:.2f}", color=col, fontsize=9, va="center", zorder=5)
quarters(w.open.iat[0], 0, "أسبوع", "#90caf9", "#00e5ff", "#4dd0e1", 0)
quarters(today.open.iat[0], N - len(today), "يوم", "#ffffff", "#e040fb", "#ffb020", 42)
days = w.index.normalize(); st = np.r_[0, np.flatnonzero(days[1:] != days[:-1]) + 1]
for s_ in st: ax.axvline(s_ - .5, color=GR, lw=1); ax.text(s_ + 2, w.high.max() + .3, w.index[s_].strftime("%a %m-%d"), color=MUT, fontsize=10)
ax.set_xlim(-2, N + 80); ax.set_xticks([])
ax.text(.01, .02, "أزرق / سماوي = شمعة الأسبوع (من افتتاح الاثنين) · أبيض / بنفسجي / برتقالي = شمعة اليوم\nالنصف = (الافتتاح + الإغلاق) ÷ 2، ثم كل نصف ÷ 2 · الإغلاق = آخر سعر، فالخطوط تتحرك لين تقفل الشمعة",
        color=TX, fontsize=10, transform=ax.transAxes, bbox=dict(fc="#1e222d", ec=GR))
fig.tight_layout(); fig.savefig(ROOT / "reports/styles/Z2_daily_quarters.png", dpi=90, facecolor=BG)
