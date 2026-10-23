"""Which trendline settings draw the BEST lines (not the most profitable): lines the market actually respects.

Per setting (pivot bars k, hold-until-broken), over every line drawn:
  touches   : bars that came within 0.1 ATR(14) of the line WITHOUT closing through it, before it broke  (more = better)
  respected : share of lines touched at least twice before breaking                                     (more = better)
  fakeouts  : share of breaks where price closed back on the line's side within 3 bars                  (fewer = better)
  life      : median bars a line lives (until replaced)                                                  (longer = calmer)
  changes   : new lines per session                                                                      (fewer = calmer)
Score = respected% - fakeouts% (both in %, equal weight) - the two things that make a line "right".
Checked on both halves of the dates separately: a winner must win on both.
Data: data/intraday/<SYM>_15m.csv and <SYM>_5m_alpaca.csv, 7 stocks, 2025-04-01 .. 2026-10-22.
"""
import sys, pathlib, itertools
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
SYMS = ["SPY", "QQQ", "COST", "INTU", "JNJ", "UNH", "HOOD"]
FILES = {"5m": "{s}_5m_alpaca.csv", "15m": "{s}_15m.csv"}
GRID = list(itertools.product((2, 3, 4, 5, 6, 7, 8, 10, 12), (False, True)))


def load(tf, s):
    d = pd.read_csv(ROOT / "data/intraday" / FILES[tf].format(s=s))
    t = pd.to_datetime(d["time"], utc=True).dt.tz_convert("America/New_York")
    h, l, c = (d[x].to_numpy(float) for x in ("high", "low", "close"))
    prev = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(np.abs(h - prev), np.abs(l - prev)))
    atr = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().to_numpy()
    return h, l, c, atr, t.dt.date.to_numpy()


def lines(h, l, c, atr, k, hold):
    """Every line the indicator would draw: (birth bar, end bar, touches, broke?, fakeout?)."""
    n = len(c); out = []
    for side, x in ((1, h), (-1, l)):
        last = None; line = None; broke = True; touch = 0; born = 0
        for i in range(2 * k, n):
            p = i - k
            w = x[p - k:p + k + 1]
            piv = (x[p] == w.max() and (x[p - k:p] < x[p]).all()) if side == 1 else \
                  (x[p] == w.min() and (x[p - k:p] > x[p]).all())
            if piv:
                ok = last is not None and (x[p] < last[1] if side == 1 else x[p] > last[1])
                if ok and (not hold or broke or line is None):
                    if line is not None and not broke:
                        out.append((born, i, touch, False, False))
                    line = (last[0], last[1], (x[p] - last[1]) / (p - last[0])); born = i; broke = False; touch = 0
                last = (p, x[p])
            if line is not None and not broke:
                y = line[1] + line[2] * (i - line[0])
                if (side == 1 and c[i] > y) or (side == -1 and c[i] < y):
                    broke = True
                    back = False
                    for j in range(i + 1, min(i + 4, n)):
                        yj = line[1] + line[2] * (j - line[0])
                        if (side == 1 and c[j] < yj) or (side == -1 and c[j] > yj):
                            back = True; break
                    out.append((born, i, touch, True, back))
                elif abs((h[i] if side == 1 else l[i]) - y) <= 0.1 * atr[i]:
                    touch += 1
    return out


def measure(tf, part):
    rows = []
    data = {s: load(tf, s) for s in SYMS}
    for k, hold in GRID:
        L, sessions = [], 0
        for s, (h, l, c, atr, day) in data.items():
            days = np.array(sorted(set(day)))
            cut = days[len(days) // 2]
            m = (day < cut) if part == "A" else (day >= cut) if part == "B" else np.ones(len(day), bool)
            sessions += len(set(day[m]))
            for born, end, touch, broke, back in lines(h, l, c, atr, k, hold):
                if m[born]:
                    L.append((end - born, touch, broke, back))
        a = np.array(L, float)
        brk = a[a[:, 2] == 1]
        resp = 100 * np.mean(brk[:, 1] >= 2) if len(brk) else np.nan
        fake = 100 * np.mean(brk[:, 3]) if len(brk) else np.nan
        rows.append({"k": k, "hold": hold, "lines": len(a), "changes/session": len(a) / sessions,
                     "life": np.median(a[:, 0]), "touches": brk[:, 1].mean(), "respected%": resp,
                     "fakeouts%": fake, "score": resp - fake})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    pd.set_option("display.width", 200)
    for tf in ("5m", "15m"):
        full = measure(tf, "all").sort_values("score", ascending=False)
        a, b = measure(tf, "A"), measure(tf, "B")
        full["rank first half"] = full.apply(lambda r: int(a.score.rank(ascending=False)[(a.k == r.k) & (a.hold == r.hold)].iloc[0]), axis=1)
        full["rank second half"] = full.apply(lambda r: int(b.score.rank(ascending=False)[(b.k == r.k) & (b.hold == r.hold)].iloc[0]), axis=1)
        print(f"\n===== {tf} =====")
        print(full.to_string(index=False, float_format=lambda v: f"{v:.2f}"))
