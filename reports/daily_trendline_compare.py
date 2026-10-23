"""Daily trendlines vs the long ones: does the line stay with today's price?

For every bar that shows a line (red and green separately), on 7 stocks, 5m and 15m:
  distance : |close - line| in ATR(14)                      (smaller = the line moves with price)
  age      : bars since the line's first anchor              (smaller = built from today's swing)
  from today: share of lines whose first anchor is in the same session as the bar
  touches  : bars within 0.1 ATR of the line, per 100 bars with a line
Modes: long-hold (k=2, held until broken - the current default), long-latest (k=2, the original),
daily (vzones/daily_trendlines.py, k=2 and k=3).
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd
from vzones.daily_trendlines import daily_lines

ROOT = pathlib.Path(__file__).resolve().parent.parent
SYMS = ["SPY", "QQQ", "COST", "INTU", "JNJ", "UNH", "HOOD"]
FILES = {"5m": "{s}_5m_alpaca.csv", "15m": "{s}_15m.csv"}


def long_lines(df, k, hold):
    h, l, c = (df[x].to_numpy(float) for x in ("high", "low", "close")); n = len(c)
    out = {"red": [None] * n, "green": [None] * n}
    for side, x, sgn in (("red", h, 1), ("green", l, -1)):
        last = None; line = None; broke = True
        for i in range(2 * k, n):
            p = i - k; w = x[p - k:p + k + 1]
            piv = (x[p] == w.max() and (x[p - k:p] < x[p]).all()) if sgn == 1 else (x[p] == w.min() and (x[p - k:p] > x[p]).all())
            if piv:
                ok = last is not None and (x[p] < last[1] if sgn == 1 else x[p] > last[1])
                if ok and (not hold or broke or line is None):
                    line = (last[0], last[1], (x[p] - last[1]) / (p - last[0])); broke = False
                last = (p, x[p])
            out[side][i] = line
            if line is not None and not broke:
                y = line[1] + line[2] * (i - line[0])
                if (sgn == 1 and c[i] > y) or (sgn == -1 and c[i] < y):
                    broke = True
    return out


def stats(df, lines):
    h, l, c = (df[x].to_numpy(float) for x in ("high", "low", "close"))
    prev = np.r_[c[0], c[:-1]]
    atr = pd.Series(np.maximum(h - l, np.maximum(abs(h - prev), abs(l - prev)))).ewm(alpha=1 / 14, adjust=False).mean().to_numpy()
    day = pd.to_datetime(df["time"], utc=True).dt.tz_convert("America/New_York").dt.date.to_numpy()
    dist, age, today, touch, shown = [], [], [], 0, 0
    for side, x in (("red", h), ("green", l)):
        for i, ln in enumerate(lines[side]):
            if ln is None:
                continue
            y = ln[1] + ln[2] * (i - ln[0])
            dist.append(abs(c[i] - y) / atr[i]); age.append(i - ln[0]); today.append(day[ln[0]] == day[i])
            touch += abs(x[i] - y) <= 0.1 * atr[i]; shown += 1
    return dist, age, today, touch, shown


if __name__ == "__main__":
    for tf in ("5m", "15m"):
        print(f"\n===== {tf} =====")
        print(f"{'mode':16} {'median distance (ATR)':>22} {'median age (bars)':>18} {'from today':>11} {'touches/100':>12} {'bars with a line':>17}")
        for name, fn in (("long-latest k2", lambda d: long_lines(d, 2, False)), ("long-hold k2", lambda d: long_lines(d, 2, True)),
                         ("daily k2", lambda d: daily_lines(d, 2)), ("daily k3", lambda d: daily_lines(d, 3))):
            D, A, T, tc, sh, nb = [], [], [], 0, 0, 0
            for s in SYMS:
                df = pd.read_csv(ROOT / "data/intraday" / FILES[tf].format(s=s))
                d, a, t, touch, shown = stats(df, fn(df))
                D += d; A += a; T += t; tc += touch; sh += shown; nb += 2 * len(df)
            print(f"{name:16} {np.median(D):22.2f} {np.median(A):18.0f} {100*np.mean(T):10.0f}% {100*tc/sh:12.1f} {100*sh/nb:16.0f}%")
