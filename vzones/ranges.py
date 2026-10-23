"""Python counterpart of the current Pine indicator (pine/volume_zones.pine), used for testing its readings.

- daily sideways ranges: the first `wlen` days set top / bottom (restart if wider than `wmult` x daily ATR); the first
  daily close outside completes the range (breakout day included) and starts the next one on the breakout day.
- whale levels of a range: hidden 200-row volume profile of the source bars, tall columns + POC / VAH / VAL.
- levels per trading day: last `keep` completed ranges + the forming one, built from completed days only.
- instant trend (EMA 9/21 + DMI 7), Supertrend(10, 3), trendlines (2-bar pivots, lower-high / higher-low pair held until closed through; was replaced by every new pair).
Volume is spread evenly over each bar's high-low range, as in the Pine code.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

AGG = dict(open="first", high="max", low="min", close="last", volume="sum")


def rma(x, n: int) -> np.ndarray:
    x = np.asarray(x, float); out = np.full(len(x), np.nan); acc = np.nan
    for i, v in enumerate(x):
        if np.isnan(v): out[i] = acc; continue
        acc = v if np.isnan(acc) else acc + (v - acc) / n
        out[i] = acc
    return out


def true_range(h, l, c) -> np.ndarray:
    pc = np.r_[np.nan, c[:-1]]
    return np.where(np.isnan(pc), h - l, np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc))))


def daily_ranges(day: pd.DataFrame, wlen: int = 10, wmult: float = 6.0):
    """Return (completed, state): completed = list of (start_day_idx, end_day_idx_exclusive, completed_on_idx);
    state[i] = (range_start_idx, top, bottom) after processing day i."""
    H, L, C = day.high.to_numpy(), day.low.to_numpy(), day.close.to_numpy()
    atr = rma(true_range(H, L, C), 14)
    done, state = [], []
    r0, rh, rl = 0, H[0], L[0]
    for n in range(len(day)):
        if n == 0:
            pass
        elif n - r0 < wlen:
            rh, rl = max(rh, H[n]), min(rl, L[n])
            if rh - rl > wmult * atr[n]:
                r0, rh, rl = n, H[n], L[n]
        elif C[n] > rh or C[n] < rl:
            done.append((r0, n + 1, n))                      # breakout day included
            r0, rh, rl = n, H[n], L[n]
        else:
            rh, rl = max(rh, H[n]), min(rl, L[n])
        state.append((r0, rh, rl))
    return done, state


def range_levels(src: pd.DataFrame, t0, t1, rows: int = 200, peaks: int = 8, va: float = 0.70):
    """Whale levels of the source bars with t0 <= time < t1: (tall columns, (poc, vah, val)) or None."""
    b = src[(src.index >= t0) & (src.index < t1)]
    if len(b) <= 10: return None
    lo, hi = b.low.min(), b.high.max()
    if hi <= lo: return None
    st = (hi - lo) / rows; pv = np.zeros(rows)
    for h, l, v in zip(b.high.to_numpy(), b.low.to_numpy(), b.volume.to_numpy()):
        q0, q1 = int(np.clip((l - lo) // st, 0, rows - 1)), int(np.clip((h - lo) // st, 0, rows - 1))
        rg = max(h - l, 1e-9)
        for q in range(q0, q1 + 1):
            ql = lo + q * st
            pv[q] += v if h == l else v * max(0.0, min(h, ql + st) - max(l, ql)) / rg
    sm = np.array([(pv[max(0, q - 1)] + pv[q] + pv[min(rows - 1, q + 1)]) / 3 for q in range(rows)])
    nb = max(2, rows // 40)
    cand = [q for q in range(rows) if sm[q] >= 1.3 * sm.mean() and sm[q] >= sm[max(0, q - nb):q + nb + 1].max()]
    cand = sorted(cand, key=lambda q: -sm[q])[:peaks]
    pi = int(np.argmax(pv)); a0 = a1 = pi; acc = pv[pi]
    while acc < va * pv.sum() and (a0 > 0 or a1 < rows - 1):
        u = pv[a1 + 1] if a1 < rows - 1 else -1.0; d = pv[a0 - 1] if a0 > 0 else -1.0
        if u >= d: a1 += 1; acc += u
        else: a0 -= 1; acc += d
    return [lo + (q + .5) * st for q in cand], (lo + (pi + .5) * st, lo + (a1 + 1) * st, lo + a0 * st)


def levels_by_day(bars: pd.DataFrame, src: pd.DataFrame | None = None, wlen=10, wmult=6.0, keep=2, rows=200, peaks=8):
    """Dict trading-date -> sorted whale levels active on that date (known before its open)."""
    src = bars if src is None else src
    day = bars.resample("1D").agg(AGG).dropna()
    done, state = daily_ranges(day, wlen, wmult)
    out = {}
    for i in range(len(day) - 1):                            # levels for day i+1 use days 0..i
        t_next = day.index[i + 1]
        comp = [r for r in done if r[2] <= i][-keep:]
        lv = []
        for a, b, _ in comp:
            res = range_levels(src, day.index[a], day.index[b] if b < len(day) else t_next, rows, peaks)
            if res: lv += res[0] + list(res[1])
        r0 = state[i][0]
        if i + 1 - r0 >= wlen:
            res = range_levels(src, day.index[r0], t_next, rows, peaks)
            if res: lv += res[0] + list(res[1])
        out[t_next.date()] = sorted(set(round(x, 4) for x in lv))
    return out


def instant_trend(df: pd.DataFrame, fast=9, slow=21, adx_len=7) -> np.ndarray:
    h, l, c = (df[k].to_numpy(float) for k in ("high", "low", "close"))
    ef = pd.Series(c).ewm(span=fast, adjust=False).mean().to_numpy(); es = pd.Series(c).ewm(span=slow, adjust=False).mean().to_numpy()
    up, dn = np.r_[np.nan, np.diff(h)], np.r_[np.nan, -np.diff(l)]
    pdm = np.where((up > dn) & (up > 0), up, 0.0); mdm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = rma(true_range(h, l, c), adx_len); pdi = 100 * rma(pdm, adx_len) / tr; mdi = 100 * rma(mdm, adx_len) / tr
    return np.where((ef > es) & (pdi > mdi), 1, np.where((ef < es) & (mdi > pdi), -1, 0))


def supertrend(df: pd.DataFrame, factor=3.0, n=10):
    h, l, c = (df[k].to_numpy(float) for k in ("high", "low", "close"))
    atr = rma(true_range(h, l, c), n); src = (h + l) / 2
    up, lo = src + factor * atr, src - factor * atr
    st = np.full(len(c), np.nan); d = np.ones(len(c), int)
    for i in range(1, len(c)):
        lo[i] = lo[i] if lo[i] > lo[i - 1] or c[i - 1] < lo[i - 1] else lo[i - 1]
        up[i] = up[i] if up[i] < up[i - 1] or c[i - 1] > up[i - 1] else up[i - 1]
        if np.isnan(atr[i - 1]): d[i] = 1
        elif st[i - 1] == up[i - 1]: d[i] = -1 if c[i] > up[i] else 1
        else: d[i] = 1 if c[i] < lo[i] else -1
        st[i] = lo[i] if d[i] == -1 else up[i]
    return st, d                                               # d < 0 = up, as in Pine


def trendline_breaks(df: pd.DataFrame, k: int = 2, hold: bool = False) -> np.ndarray:
    """+1 on the first close above the current red line, -1 on the first close below the current green line.
    k = pivot bars each side; hold = a new pivot pair replaces a line only after it was closed through
    (Pine defaults since 2026-10-23: k=2, hold=True - best line quality, reports/trendline_quality.py; the original was k=2, hold=False)."""
    h, l, c = (df[x].to_numpy(float) for x in ("high", "low", "close")); n = len(c); out = np.zeros(n, int)
    lastH = lastL = None; dn = up = None; dnBroke = upBroke = True
    for i in range(2 * k, n):
        p = i - k
        if h[p] == h[p - k:p + k + 1].max() and (h[p - k:p] < h[p]).all():
            if lastH is not None and h[p] < lastH[1] and (not hold or dnBroke): dn = (lastH[0], lastH[1], (h[p] - lastH[1]) / (p - lastH[0])); dnBroke = False
            lastH = (p, h[p])
        if l[p] == l[p - k:p + k + 1].min() and (l[p - k:p] > l[p]).all():
            if lastL is not None and l[p] > lastL[1] and (not hold or upBroke): up = (lastL[0], lastL[1], (l[p] - lastL[1]) / (p - lastL[0])); upBroke = False
            lastL = (p, l[p])
        if dn and not dnBroke and c[i] > dn[1] + dn[2] * (i - dn[0]): out[i] = 1; dnBroke = True
        if up and not upBroke and c[i] < up[1] + up[2] * (i - up[0]): out[i] = -1; upBroke = True
    return out
