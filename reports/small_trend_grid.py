"""Best setting for SMALL trendlines (rolling window of the last N bars), 7 stocks, 5m and 15m.

Per setting (pivot bars k, window N) over every bar that shows a line:
  coverage   : share of bars with a line on screen (red or green)         - small trends should be visible most of the time
  distance   : median |close - line| in ATR                               - the line rides with price
  touches    : bars within 0.1 ATR of a line, per 100 bars with a line    - price respects it
  fakeouts%  : breaks where price closed back on the line's side within 3 bars
Score = touches - fakeouts%/10 - 2 x distance, among settings with coverage >= 50%. Both halves of the dates ranked.
"""
import sys, pathlib, itertools
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd
from vzones.daily_trendlines import small_lines, daily_lines

ROOT = pathlib.Path(__file__).resolve().parent.parent
SYMS = ["SPY", "QQQ", "COST", "INTU", "JNJ", "UNH", "HOOD"]
FILES = {"5m": "{s}_5m_alpaca.csv", "15m": "{s}_15m.csv"}
GRID = list(itertools.product((1, 2, 3), (10, 15, 20, 30, 40)))


def measure(df, lines, mask):
    h, l, c = (df[x].to_numpy(float) for x in ("high", "low", "close"))
    prev = np.r_[c[0], c[:-1]]
    atr = pd.Series(np.maximum(h - l, np.maximum(abs(h - prev), abs(l - prev)))).ewm(alpha=1 / 14, adjust=False).mean().to_numpy()
    dist, touch, shown, cov, brk, fake = [], 0, 0, 0, 0, 0
    n = len(c)
    for i in range(n):
        if not mask[i]:
            continue
        any_line = False
        for side, x, sgn in (("red", h, 1), ("green", l, -1)):
            ln = lines[side][i]
            if lines["break_" + side][i]:
                prevln = lines[side][i - 1] if i > 0 else None
                if prevln is not None:
                    brk += 1
                    for j in range(i + 1, min(i + 4, n)):
                        yj = prevln[1] + prevln[2] * (j - prevln[0])
                        if (sgn == 1 and c[j] < yj) or (sgn == -1 and c[j] > yj):
                            fake += 1; break
            if ln is None:
                continue
            any_line = True
            y = ln[1] + ln[2] * (i - ln[0])
            dist.append(abs(c[i] - y) / atr[i]); shown += 1
            touch += abs(x[i] - y) <= 0.1 * atr[i]
        cov += any_line
    return dist, touch, shown, cov, mask.sum(), brk, fake


def table(tf, part):
    rows = []
    cache = {}
    for s in SYMS:
        df = pd.read_csv(ROOT / "data/intraday" / FILES[tf].format(s=s))
        day = pd.to_datetime(df["time"], utc=True).dt.date.to_numpy()
        days = np.array(sorted(set(day))); cut = days[len(days) // 2]
        cache[s] = (df, (day < cut) if part == "A" else (day >= cut) if part == "B" else np.ones(len(df), bool))
    settings = [(f"small k{k} N{w}", (lambda d, k=k, w=w: small_lines(d, k, w))) for k, w in GRID]
    settings.append(("daily k2 (current)", lambda d: daily_lines(d, 2)))
    for name, fn in settings:
        D, T, S, C, NB, B, F = [], 0, 0, 0, 0, 0, 0
        for s, (df, m) in cache.items():
            d, t, sh, cv, nb, b, f = measure(df, fn(df), m)
            D += d; T += t; S += sh; C += cv; NB += nb; B += b; F += f
        dist = np.median(D); touches = 100 * T / max(S, 1); fk = 100 * F / max(B, 1); cov = 100 * C / NB
        rows.append({"setting": name, "coverage%": cov, "distance": dist, "touches": touches, "fakeouts%": fk,
                     "breaks/100": 100 * B / NB, "score": touches - fk / 10 - 2 * dist if cov >= 50 else np.nan})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    pd.set_option("display.width", 200)
    for tf in ("5m", "15m"):
        full, a, b = table(tf, "all"), table(tf, "A"), table(tf, "B")
        full["rank A"] = a["score"].rank(ascending=False).values
        full["rank B"] = b["score"].rank(ascending=False).values
        print(f"\n===== {tf} =====")
        print(full.sort_values("score", ascending=False).to_string(index=False, float_format=lambda v: f"{v:.2f}"))
