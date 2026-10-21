"""Whale levels: fixed-range volume profile (200 rows) over the LATEST sideways range on daily / half-weekly /
weekly candles. Tall columns (local peaks) = whale levels, extended to the latest price.

No look-ahead: a range is only used after it has COMPLETED (price closed outside it), and only bars after that
are evaluated.
"""
from __future__ import annotations
import numpy as np, pandas as pd
from .indicator import distribute_volume

AGG = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}


def to_tf(daily: pd.DataFrame, tf: str) -> pd.DataFrame:
    if tf == "1D":
        return daily.copy()
    if tf == "3D":                                   # "half-week": groups of 3 trading days
        g = np.arange(len(daily)) // 3
        out = daily.groupby(g).agg(AGG); out.index = daily.index[np.r_[0, np.flatnonzero(np.diff(g)) + 1]]
        return out
    if tf == "1W":
        return daily.resample("W-FRI").agg(AGG).dropna()
    raise ValueError(tf)


def atr(df, n=14):
    pc = df.close.shift(1)
    tr = pd.concat([df.high - df.low, (df.high - pc).abs(), (df.low - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def find_ranges(c: pd.DataFrame, length: int, max_atr: float):
    """Sideways range = `length` candles whose high-low span <= max_atr x ATR. Returns completed ranges as
    (start_time, end_time, breakout_time, hi, lo) - breakout = first close outside the range afterwards."""
    a = atr(c).to_numpy(); h, l, cl = c.high.to_numpy(), c.low.to_numpy(), c.close.to_numpy()
    out, i = [], length
    while i < len(c):
        s = i - length
        hi, lo = h[s:i].max(), l[s:i].min()
        if np.isfinite(a[i - 1]) and hi - lo <= max_atr * a[i - 1]:
            # extend the range while candles stay inside it
            e = i
            while e < len(c) and lo <= cl[e] <= hi:
                hi, lo = max(hi, h[e]), min(lo, l[e]); e += 1
            if e < len(c):
                out.append((c.index[s], c.index[e - 1], c.index[e], hi, lo))
            i = e + 1
        else:
            i += 1
    return out


def profile_levels(bars: pd.DataFrame, rows: int = 200, peak_win: int = 5, peak_mult: float = 1.3, max_peaks: int = 8):
    """Volume profile with `rows` rows from intraday bars; returns (peaks, valleys, centers, volume)."""
    h, l, v = bars.high.to_numpy(float), bars.low.to_numpy(float), bars.volume.to_numpy(float)
    e = np.linspace(l.min(), h.max() + 1e-9, rows + 1); cen = (e[:-1] + e[1:]) / 2
    p = distribute_volume(h, l, v, e)
    sm = np.convolve(p, np.ones(3) / 3, mode="same"); m = sm.mean()
    pk, vl = [], []
    for k in range(rows):
        lo_, hi_ = max(0, k - peak_win), min(rows, k + peak_win + 1)
        if sm[k] == sm[lo_:hi_].max() and sm[k] >= peak_mult * m: pk.append(k)
        if sm[k] == sm[lo_:hi_].min() and sm[k] <= 0.7 * m and 0 < k < rows - 1: vl.append(k)
    pk = sorted(pk, key=lambda k: -sm[k])[:max_peaks]
    return cen[pk], cen[vl], cen, p
