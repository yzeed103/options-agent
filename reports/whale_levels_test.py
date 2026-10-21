"""Test whale levels (peaks of a 200-row fixed-range profile over the latest sideways range) as
respected levels and price targets, vs valley levels (thin columns of the same profile) and random levels."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd
import vzones
from vzones.whale_levels import to_tf, atr, find_ranges, profile_levels, AGG
from vzones.intraday.data import load_csv, rth
OUT = pathlib.Path(__file__).resolve().parent; ROOT = OUT.parent
rng = np.random.default_rng(7)
HOLD_DAYS = 3        # reaction window after the first touch (daily bars)
LEN = {"1D": 20, "3D": 15, "1W": 12}
MAXATR = {"1D": 6.0, "3D": 5.0, "1W": 5.0}


def evaluate(daily, intraday, sym, src):
    rows = []
    da = atr(daily).to_numpy(); dh, dl, dc = daily.high.to_numpy(), daily.low.to_numpy(), daily.close.to_numpy()
    for tf in ("1D", "3D", "1W"):
        c = to_tf(daily, tf); ranges = find_ranges(c, LEN[tf], MAXATR[tf])
        for n, (s, e, brk, hi, lo) in enumerate(ranges):
            # evaluation window: from breakout until the next range completes (max 120 trading days)
            nxt = ranges[n + 1][2] if n + 1 < len(ranges) else daily.index[-1]
            i0 = daily.index.searchsorted(brk); i1 = min(daily.index.searchsorted(nxt), i0 + 120, len(daily) - HOLD_DAYS - 1)
            if i1 - i0 < 5: continue
            end_day = c.index[c.index.get_loc(e) + 1] if c.index.get_loc(e) + 1 < len(c) else daily.index[-1]
            bars = intraday[(intraday.index >= s) & (intraday.index < end_day)]
            if len(bars) < 20: continue
            peaks, valleys, cen, prof = profile_levels(bars)
            rand = rng.uniform(lo, hi, size=max(len(peaks), 1))
            for kind, lv in (("whale (peak)", peaks), ("thin (valley)", valleys), ("random", rand)):
                for L in lv:
                    a = da[i0 - 1]
                    if not np.isfinite(a): continue
                    dist = abs(L - dc[i0 - 1]) / a
                    touch = next((j for j in range(i0, i1) if dl[j] <= L <= dh[j]), None)
                    r = dict(src=src, symbol=sym, tf=tf, kind=kind, dist_atr=dist, touched=touch is not None, range_id=f"{sym}{tf}{n}")
                    if touch is not None:
                        side = 1 if dc[touch - 1] > L else -1          # +1: came from above (support test)
                        k = touch + HOLD_DAYS
                        r["held"] = (dc[k] > L) if side == 1 else (dc[k] < L)
                        mv = (dh[touch:k + 1].max() - L) if side == 1 else (L - dl[touch:k + 1].min())
                        r["bounce_atr"] = mv / a
                        r["days_to_touch"] = touch - i0
                    rows.append(r)
    return rows


rows = []
# 1) SPY 1998-2021 hourly (consolidated volume)
h = vzones.load_lean_csv(ROOT / "data/spy_hourly_lean.csv.gz")
daily = h.resample("1D").agg(AGG).dropna()
rows += evaluate(daily, h, "SPY", "SPY 1h 1998-2021")
# 2) 7 symbols 15m 2025-2026 (BATS volume)
for sym in ["SPY", "QQQ", "COST", "INTU", "JNJ", "UNH", "HOOD"]:
    m = rth(load_csv(ROOT / f"data/intraday/{sym}_15m.csv"))
    m.index = m.index.tz_localize(None)
    d = m.resample("1D").agg(AGG).dropna()
    rows += evaluate(d, m, sym, "7 symbols 15m 2025-26")
R = pd.DataFrame(rows); R.to_csv(OUT / "whale_levels_events.csv", index=False)
R["held"] = R["held"].astype(float)
pd.set_option("display.width", 220)


def summ(g):
    t = g[g.touched]
    return pd.Series(dict(levels=len(g), ranges=g.range_id.nunique(), dist_atr=g.dist_atr.mean(), reached=g.touched.mean() * 100,
                          days_to_reach=t.days_to_touch.median(), held_3d=t.held.mean() * 100, bounce_atr=t.bounce_atr.mean()))
for src in R.src.unique():
    print(f"\n===== {src}")
    S = R[R.src == src].groupby(["tf", "kind"]).apply(summ).round(2)
    print(S.to_string())
# distance-matched comparison: reached % by distance bucket
print("\n===== Reached % by distance from price at breakout (all sources, all TFs)")
R["dist_b"] = pd.cut(R.dist_atr, [0, 1, 2, 4, 8, 99])
print(R.groupby(["dist_b", "kind"], observed=True).touched.mean().mul(100).round(1).unstack().to_string())
print("\n===== Held 3 days after first touch, by distance bucket")
print(R[R.touched].groupby(["dist_b", "kind"], observed=True).held.mean().mul(100).round(1).unstack().to_string())
