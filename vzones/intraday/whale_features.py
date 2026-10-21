"""Attach active whale levels (peaks of the 200-row profile of the latest completed sideways range on daily and
weekly candles) to intraday bars as columns wl_0..wl_{K-1}. A range's levels become active from the session AFTER
its breakout day (so the breakout close is known) until a newer range of the same timeframe becomes active."""
from __future__ import annotations
import numpy as np, pandas as pd
from ..whale_levels import to_tf, find_ranges, profile_levels, AGG

K = 10


def add_whale_levels(d: pd.DataFrame, specs=(("1D", 20, 6.0), ("1W", 12, 5.0)), kind: str = "peak", seed: int = 0) -> pd.DataFrame:
    """kind: 'peak' (whale levels), 'valley' (thin columns of the same profile), 'random' (uniform in the same range)."""
    rng = np.random.default_rng(seed)
    d = d.copy()
    idx = d.index.tz_localize(None) if d.index.tz is not None else d.index
    raw = pd.DataFrame(d[["open", "high", "low", "close", "volume"]].to_numpy(), index=idx, columns=["open", "high", "low", "close", "volume"])
    daily = raw.resample("1D").agg(AGG).dropna()
    days = list(daily.index)
    active = {}                                         # tf -> list of (activate_day, levels)
    for tf, L, mx in specs:
        c = to_tf(daily, tf); ev = []
        for s, e, brk, hi, lo in find_ranges(c, L, mx):
            end_day = c.index[c.index.get_loc(e) + 1] if c.index.get_loc(e) + 1 < len(c) else daily.index[-1]
            bars = raw[(raw.index >= s) & (raw.index < end_day)]
            if len(bars) < 20: continue
            pk, vl, _, _ = profile_levels(bars)
            if kind == "valley":
                vv = sorted(vl, key=lambda x: 0)
                pk = list(np.array(vv)[np.linspace(0, len(vv) - 1, min(len(pk), len(vv))).astype(int)]) if len(vv) else []
            elif kind == "random":
                pk = list(rng.uniform(bars.low.min(), bars.high.max(), size=len(pk)))
            bday = daily.index[daily.index.searchsorted(brk)] if brk in daily.index or daily.index.searchsorted(brk) < len(daily) else None
            if bday is None: continue
            k = days.index(bday)
            if k + 1 < len(days): ev.append((days[k + 1], list(pk)))
        active[tf] = ev
    per_day = {}
    for day in days:
        lv = []
        for tf, ev in active.items():
            cur = [x for x in ev if x[0] <= day]
            if cur: lv += cur[-1][1]
        per_day[day] = sorted(lv)[:K] if len(lv) <= K else sorted(lv)
    sess_day = pd.Series(idx.normalize(), index=d.index)
    mat = np.full((len(d), K), np.nan)
    for i, day in enumerate(sess_day):
        lv = per_day.get(day, [])
        # keep the K levels closest to the session's first price
        if len(lv) > K:
            p0 = d.open.iat[i]; lv = sorted(sorted(lv, key=lambda x: abs(x - p0))[:K])
        mat[i, :len(lv)] = lv
    for k in range(K):
        d[f"wl_{k}"] = mat[:, k]
    return d


def whale_bounce(d: pd.DataFrame) -> np.ndarray:
    """Touch of an active whale level and close back on the side it came from -> trade toward the next level."""
    c, l, h = d.close.to_numpy(), d.low.to_numpy(), d.high.to_numpy(); pc = np.r_[np.nan, c[:-1]]
    W = d[[f"wl_{k}" for k in range(K)]].to_numpy(); sig = np.zeros(len(d), int)
    for i in range(1, len(d)):
        for L in W[i][np.isfinite(W[i])]:
            if pc[i] > L and l[i] <= L and c[i] > L: sig[i] = 1; break
            if pc[i] < L and h[i] >= L and c[i] < L: sig[i] = -1; break
    return sig
