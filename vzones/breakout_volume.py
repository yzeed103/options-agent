"""Level breaks with a strong bar (reports/breakout_volume/PREREG.md): levels (swing pivots, prior-day high / low,
value area, GEX walls), break events, the measures at the breaking bar, the size-only control, and the targets.
Detection and measures use past bars only; targets use the future (evaluation only)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from vzones import trend_volume as TV
from vzones import volume_tool as VT

MIN_AGE = 10          # bars a level must have been respected before a break counts
FIRST = 5             # no event in the first bars of a session
HOLD = 12
FALSE_N = 3
BEYOND = 0.5
STRONG, SMALL = 1.5, 0.7      # absorption flag: RVOL > STRONG and range/ATR < SMALL


def detect(d: pd.DataFrame, tf_min: int, k: int = 2, day_levels: pd.DataFrame | None = None):
    """Break events. day_levels: one row per session date with columns such as pdh, pdl, poc, vah, val, cw, pw.
    Returns (frames dict, events DataFrame)."""
    o, h, l, c, v = (d[k_].to_numpy(float) for k_ in ("open", "high", "low", "close", "volume"))
    A = VT.atr(h, l, c)
    rvol, _, zr = VT.rvol_set(d, tf_min)
    sess, _ = VT.sessions_slots(d.index, tf_min)
    rng = np.maximum(h - l, 1e-12)
    tp = (h + l + c) / 3
    key = pd.Series(sess)
    vwap = pd.Series(tp * v).groupby(key).cumsum().to_numpy() / np.maximum(pd.Series(v).groupby(key).cumsum().to_numpy(), 1e-9)
    n = len(c)
    ev = []
    live = []                      # dicts: L, origin, side (+1 price above the level, -1 below), type
    s_start = 0
    for i in range(n):
        if i == 0 or sess[i] != sess[i - 1]:
            s_start = i
            live = []
            if day_levels is not None and sess[i] in day_levels.index:
                row = day_levels.loc[sess[i]]
                for name, L in row.items():
                    if np.isfinite(L) and L > 0:
                        live.append(dict(L=float(L), origin=i, side=0, type=name))      # side set by the first close
        # confirm swing pivots: pivot at p = i - k
        p = i - k
        if p - k >= s_start and p >= 1:
            if h[p] > h[p - k:p].max() and h[p] > h[p + 1:i + 1].max():
                live.append(dict(L=float(h[p]), origin=p, side=-1, type="swing_high"))
            if l[p] < l[p - k:p].min() and l[p] < l[p + 1:i + 1].min():
                live.append(dict(L=float(l[p]), origin=p, side=1, type="swing_low"))
        # day levels: price side from the session's first close
        for lv in live:
            if lv["side"] == 0 and lv["origin"] == i:
                lv["side"] = 1 if c[i] > lv["L"] else -1 if c[i] < lv["L"] else 0
        broken = []
        cand = {}
        for lv in live:
            if lv["side"] == 0 or i == lv["origin"]:
                continue
            crossed = (lv["side"] < 0 and c[i] > lv["L"]) or (lv["side"] > 0 and c[i] < lv["L"])
            if not crossed:
                continue
            broken.append(lv)
            if i - lv["origin"] < MIN_AGE or i - s_start < FIRST:
                continue
            dist = abs(c[i - 1] - lv["L"])
            if lv["type"] not in cand or dist < cand[lv["type"]][0]:
                cand[lv["type"]] = (dist, lv)
        for lv in broken:
            live.remove(lv)
        for typ, (_, lv) in cand.items():
            dr = 1 if lv["side"] < 0 else -1
            L = lv["L"]
            a = max(s_start, i - 60)
            near = (np.abs((h if dr > 0 else l)[a:i] - L) <= 0.1 * A[i])
            touches = int(np.sum(near[1:] & ~near[:-1]) + (1 if len(near) and near[0] else 0))
            r_atr = rng[i] / A[i]
            ev.append(dict(t=i, dir=dr, type=typ, L=L, origin=lv["origin"], rvol=rvol[i], zrvol=zr[i], range_atr=r_atr, body=abs(c[i] - o[i]) / rng[i],
                           B=0.5 * zr[i] + 0.25 * (r_atr - 1) + 0.25 * abs(c[i] - o[i]) / rng[i], penetration=dr * (c[i] - L) / A[i],
                           absorption=bool(rvol[i] > STRONG and r_atr < SMALL), touches=touches, vwap_dist=abs(L - vwap[i]) / A[i], control=r_atr))
    frames = dict(o=o, h=h, l=l, c=c, A=A, rvol=rvol, sess=sess)
    return frames, pd.DataFrame(ev)


def targets(frames: dict, ev: pd.DataFrame, horizon: int) -> pd.DataFrame:
    h, l, c, A, sess = (frames[k] for k in ("h", "l", "c", "A", "sess"))
    b1, b2, b3, b4 = [], [], [], []
    for t, dr, L in zip(ev["t"], ev["dir"], ev["L"]):
        t = int(t); dr = int(dr)
        remain = 0
        while t + remain + 1 < len(c) and sess[t + remain + 1] == sess[t]:
            remain += 1
        if remain >= HOLD:
            back = any(dr * (c[t + j] - L) <= 0 for j in range(1, HOLD + 1))
            b1.append(float((not back) and dr * (c[t + HOLD] - L) >= BEYOND * A[t]))
            mfe = max(dr * ((h if dr > 0 else l)[t + j] - c[t]) for j in range(1, HOLD + 1)) / A[t]
            b4.append(float(mfe))
        else:
            b1.append(np.nan); b4.append(np.nan)
        b3.append(float(any(dr * (c[t + j] - L) <= 0 for j in range(1, FALSE_N + 1))) if remain >= FALSE_N else np.nan)
        fp, _ = TV.first_passage(h, l, c, A, sess, t, dr, horizon)
        b2.append(fp)
    out = ev.copy()
    out["B1"], out["B2"], out["B3"], out["B4"] = b1, b2, b3, b4
    return out
