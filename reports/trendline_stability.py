"""How "heavy" are the trendlines? Line replacements per day, line lifetime and touches before the break,
for pivot size k (bars each side) and two replacement rules:
  latest : every new qualifying pivot pair replaces the line (the indicator before 2026-10-23)
  sticky : a new pair replaces the line only after price has CLOSED through it (the line holds until broken)
Data: data/intraday/*_15m.csv (7 symbols). Touch = the bar reaches within 0.1 ATR(14) of the line without closing through.
"""
import sys, pathlib, statistics as st
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
SYMS = ["SPY", "QQQ", "COST", "INTU", "JNJ", "UNH", "HOOD"]


def run(df, k, sticky):
    h, l, c = (df[x].to_numpy(float) for x in ("high", "low", "close")); n = len(c)
    tr = np.maximum(h - l, np.abs(np.r_[np.nan, c[:-1]] - h), )
    atr = pd.Series(np.maximum(h - l, np.abs(h - np.r_[c[0], c[:-1]]))).ewm(alpha=1 / 14).mean().to_numpy()
    stats = {"changes": 0, "life": [], "touches": []}
    for side in ("dn", "up"):
        x = h if side == "dn" else l
        last = None; line = None; born = 0; broke = True; touch = 0
        for i in range(2 * k, n):
            p = i - k
            w = x[p - k:p + k + 1]
            piv = (x[p] == w.max() and (x[p - k:p] < x[p]).all()) if side == "dn" else (x[p] == w.min() and (x[p - k:p] > x[p]).all())
            if piv:
                ok = last is not None and (x[p] < last[1] if side == "dn" else x[p] > last[1])
                if ok and (not sticky or broke or line is None):
                    if line is not None:
                        stats["life"].append(i - born); stats["touches"].append(touch)
                    line = (last[0], last[1], (x[p] - last[1]) / (p - last[0])); born = i; broke = False; touch = 0
                    stats["changes"] += 1
                last = (p, x[p])
            if line is not None and not broke:
                y = line[1] + line[2] * (i - line[0])
                if (side == "dn" and c[i] > y) or (side == "up" and c[i] < y):
                    broke = True
                elif abs((h[i] if side == "dn" else l[i]) - y) <= 0.1 * atr[i]:
                    touch += 1
    return stats


rows = []
for k in (2, 3, 5):
    for sticky in (False, True):
        ch, life, touch, days = 0, [], [], 0
        for s in SYMS:
            df = pd.read_csv(ROOT / f"data/intraday/{s}_15m.csv")
            days += pd.to_datetime(df["time"], utc=True).dt.date.nunique()
            r = run(df, k, sticky)
            ch += r["changes"]; life += r["life"]; touch += r["touches"]
        rows.append((k, "sticky" if sticky else "latest", ch / days, st.median(life), np.mean(touch),
                     100 * np.mean(np.array(touch) >= 2)))
print(f"{'k':>2} {'rule':7} {'line changes/day':>17} {'median life (bars)':>19} {'avg touches':>12} {'lines with 2+ touches':>22}")
for r in rows:
    print(f"{r[0]:>2} {r[1]:7} {r[2]:17.2f} {r[3]:19.0f} {r[4]:12.2f} {r[5]:21.0f}%")
