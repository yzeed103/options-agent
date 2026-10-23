"""Daily trendlines: lines built from TODAY's swings that move with the intraday trend (Pine: "يومي" mode).

Per side, on every bar i (only information up to bar i-1 picks the line; bar i can only break it):
  window   = pivots (k bars each side, confirmed) since max(session start, this side's last break)
  red      : A = the highest pivot high in the window; B = the most recent later pivot high below A such that no
             close between A and i-1 is above the line A->B. Falling resistance of today's swing.
  green    : A = the lowest pivot low in the window; B = the most recent later pivot low above A such that no close
             between A and i-1 is below the line A->B. Rising support of today's swing.
  break    : close beyond the line -> the line ends there and that side's window restarts from the break bar.
A new pivot re-picks B, so the line follows the trend as it develops; a new session starts empty.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _pivots(x: np.ndarray, k: int, high: bool) -> np.ndarray:
    """Boolean: bar p is a pivot (confirmed k bars later), same rule as ta.pivothigh / pivotlow on real bars."""
    n = len(x); out = np.zeros(n, bool)
    for p in range(k, n - k):
        w = x[p - k:p + k + 1]
        if high:
            out[p] = x[p] == w.max() and (x[p - k:p] < x[p]).all()
        else:
            out[p] = x[p] == w.min() and (x[p - k:p] > x[p]).all()
    return out


def small_lines(df: pd.DataFrame, k: int = 2, window: int = 20, widen: int = 1) -> dict:
    """SMALL trends: the same line rule as daily_lines, but over the last `window` bars only (rolling), re-picked every
    bar, no session reset and no waiting after a break - lines for every small swing. widen=n: when no line fits,
    retry with 2x, 4x ... the window (n tries) so a line is on screen far more often.

    red   : A = highest pivot high among pivots of the last `window` bars; B = most recent later lower pivot high
            with no close above the line A->B since A.  green mirrored.
    """
    h, l, c = (df[x].to_numpy(float) for x in ("high", "low", "close")); n = len(c)
    ph, pl = _pivots(h, k, True), _pivots(l, k, False)
    out = {"red": [None] * n, "green": [None] * n,
           "break_red": np.zeros(n, bool), "break_green": np.zeros(n, bool)}
    line = {"red": None, "green": None}
    for i in range(n):
        for side, x, piv, sgn in (("red", h, ph, 1), ("green", l, pl, -1)):
            ln = line[side]
            if ln is not None:
                y = ln[1] + ln[2] * (i - ln[0])
                if (sgn == 1 and c[i] > y) or (sgn == -1 and c[i] < y):
                    out["break_" + side][i] = True
                    ln = None
            out[side][i] = ln
            best = None
            w = window
            for _ in range(widen):          # adaptive: no line in the last `window` bars -> try 2x, 4x ...
                lo = max(0, i - w + 1)
                cand = [p for p in range(lo, i - k + 1) if piv[p]]
                best = _pick(cand, x, c, i, sgn)
                if best is not None:
                    break
                w *= 2
            line[side] = best
    return out


def _pick(cand, x, c, i, sgn):
    """Line from the extreme pivot to the most recent later pivot on the trend side with no close through it."""
    if len(cand) < 2:
        return None
    a = max(cand, key=lambda p: x[p]) if sgn == 1 else min(cand, key=lambda p: x[p])
    for b in reversed([p for p in cand if p > a]):
        if (sgn == 1 and x[b] >= x[a]) or (sgn == -1 and x[b] <= x[a]):
            continue
        s = (x[b] - x[a]) / (b - a)
        js = np.arange(a + 1, i + 1)
        if (sgn == 1 and (c[js] <= x[a] + s * (js - a)).all()) or            (sgn == -1 and (c[js] >= x[a] + s * (js - a)).all()):
            return (a, x[a], s)
    return None


def daily_lines(df: pd.DataFrame, k: int = 2) -> dict:
    """Per bar the active line of each side as (anchor bar, anchor price, slope) or None, plus break bars.

    Returns {"red": [...], "green": [...], "break_red": bool array, "break_green": bool array}.
    """
    h, l, c = (df[x].to_numpy(float) for x in ("high", "low", "close")); n = len(c)
    t = pd.to_datetime(df["time"], utc=True).dt.tz_convert("America/New_York")
    day = t.dt.date.to_numpy()
    ph, pl = _pivots(h, k, True), _pivots(l, k, False)
    out = {"red": [None] * n, "green": [None] * n,
           "break_red": np.zeros(n, bool), "break_green": np.zeros(n, bool)}
    start = {"red": 0, "green": 0}
    sess0 = 0
    line = {"red": None, "green": None}
    for i in range(n):
        if i == 0 or day[i] != day[i - 1]:
            sess0 = i; start = {"red": i, "green": i}; line = {"red": None, "green": None}
        for side, x, piv, sgn in (("red", h, ph, 1), ("green", l, pl, -1)):
            # 1) can the current line (picked with data to i-1) be broken by this bar's close?
            ln = line[side]
            if ln is not None:
                y = ln[1] + ln[2] * (i - ln[0])
                if (sgn == 1 and c[i] > y) or (sgn == -1 and c[i] < y):
                    out["break_" + side][i] = True
                    start[side] = i; line[side] = None
                    out[side][i] = None
                    continue
            out[side][i] = line[side]
            # 2) re-pick the line for the next bar with pivots confirmed up to now (pivot p is known at p + k)
            lo = max(start[side], sess0)
            cand = [p for p in range(lo, i - k + 1) if piv[p]]
            if len(cand) < 2:
                line[side] = None
                continue
            a = max(cand, key=lambda p: x[p]) if sgn == 1 else min(cand, key=lambda p: x[p])
            best = None
            for b in reversed([p for p in cand if p > a]):
                if (sgn == 1 and x[b] >= x[a]) or (sgn == -1 and x[b] <= x[a]):
                    continue
                s = (x[b] - x[a]) / (b - a)
                js = np.arange(a + 1, i + 1)
                ys = x[a] + s * (js - a)
                if (sgn == 1 and (c[js] <= ys).all()) or (sgn == -1 and (c[js] >= ys).all()):
                    best = (a, x[a], s); break
            line[side] = best
    return out
