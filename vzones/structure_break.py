"""Structure breaks of significant swings (reports/structure_break/PREREG.md): levels of several classes with age,
touches, depth and the significance score, break events and their variants, targets, pseudo-entries and the trend
rule. Levels and events use past bars only; targets, pseudo-entries and the rule use the future (evaluation)."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from vzones import conviction_ma as CM
from vzones import volume_tool as VT

N_BARS = {"1h": 24, "4h": 12, "D": 10, "W": 8}
MIN_AGE, TOUCH_BAND, HOLD_BAND, RETEST_WIN = 10, 0.25, 0.5, 20
SWING_K = (5, 10, 20)


def hull_state(c: np.ndarray, n: int = 67) -> np.ndarray:
    M = CM.hma(c, n)
    s = np.r_[np.nan, np.diff(M)]; s1 = np.r_[np.nan, s[:-1]]; s2 = np.r_[np.nan, s1[:-1]]
    return np.where((c > M) & (s > 0) & (s1 > 0) & (s2 > 0), 1, np.where((c < M) & (s < 0) & (s1 < 0) & (s2 < 0), -1, 0))


def levels_and_breaks(d: pd.DataFrame, tf: str, context: np.ndarray | None = None, spx: np.ndarray | None = None):
    """Break events (variant i) with level attributes; variants ii-iv derived afterwards. d: OHLCV bars of the timeframe."""
    o, h, l, c, v = (d[k].to_numpy(float) for k in ("open", "high", "low", "close", "volume"))
    n = len(c); A = VT.atr(h, l, c)
    vmed = pd.Series(v).rolling(20).median().to_numpy()
    rng = np.maximum(h - l, 1e-12)
    # Donchian and calendar levels (price only, previous bars only)
    don20h = pd.Series(h).rolling(20).max().shift(1).to_numpy(); don20l = pd.Series(l).rolling(20).min().shift(1).to_numpy()
    don55h = pd.Series(h).rolling(55).max().shift(1).to_numpy(); don55l = pd.Series(l).rolling(55).min().shift(1).to_numpy()
    cal = {}
    if tf == "D":
        idx = pd.DatetimeIndex(d.index)
        wk = pd.Series(np.arange(n), index=idx).groupby([idx.isocalendar().year, idx.isocalendar().week]).agg(["first", "last"])
        mo = pd.Series(np.arange(n), index=idx).groupby([idx.year, idx.month]).agg(["first", "last"])
        for name, grp in (("pw", wk), ("pm", mo)):
            hi = np.full(n, np.nan); lo = np.full(n, np.nan)
            prev = None
            for _, (a, b) in grp.iterrows():
                if prev is not None:
                    hi[a:b + 1] = h[prev[0]:prev[1] + 1].max(); lo[a:b + 1] = l[prev[0]:prev[1] + 1].min()
                prev = (a, b)
            cal[name] = (hi, lo)
        cal["52w"] = (pd.Series(h).rolling(252).max().shift(1).to_numpy(), pd.Series(l).rolling(252).min().shift(1).to_numpy())
    ev = []
    # ---- swing levels per k
    for k in SWING_K:
        live = []
        for i in range(n):
            p = i - k
            if p - k >= 0:
                if h[p] > h[p - k:p].max() and h[p] > h[p + 1:i + 1].max():
                    live.append(dict(L=h[p], p=p, side=-1, touches=0, last=i, holdc=0, ext=l[p:i + 1].min()))
                if l[p] < l[p - k:p].min() and l[p] < l[p + 1:i + 1].min():
                    live.append(dict(L=l[p], p=p, side=1, touches=0, last=i, holdc=0, ext=h[p:i + 1].max()))
            best = None
            for lv in list(live):
                if i <= lv["p"] + k:
                    continue
                L = lv["L"]; sd = lv["side"]
                crossed = c[i] > L if sd < 0 else c[i] < L
                if crossed:
                    live.remove(lv)
                    if i - lv["p"] < MIN_AGE or not np.isfinite(A[i]):
                        continue
                    depth = min(abs(L - lv["ext"]) / A[i], 4.0)
                    age = i - lv["p"]
                    sig = math.log(1 + age / k) + 0.5 * lv["touches"] + 0.5 * depth
                    cand = dict(t=i, dir=1 if sd < 0 else -1, cls=f"swing{k}", L=L, age=age, touches=lv["touches"], depth=depth, holdc=lv["holdc"], sig=sig, dist=abs(c[i - 1] - L))
                    if best is None or cand["sig"] > best["sig"] or (cand["sig"] == best["sig"] and cand["dist"] < best["dist"]):
                        best = cand
                    continue
                # the extreme of the move away from the level, frozen at the first return (the swing that formed it)
                near = abs((h[i] if sd < 0 else l[i]) - L) <= TOUCH_BAND * A[i]
                if not lv.get("frozen"):
                    lv["ext"] = min(lv["ext"], l[i]) if sd < 0 else max(lv["ext"], h[i])
                    if near and i - lv["p"] > k:
                        lv["frozen"] = True
                if near and i - lv["last"] >= 3:
                    lv["touches"] += 1; lv["last"] = i
                if abs(c[i] - L) <= HOLD_BAND * A[i]:
                    lv["holdc"] += 1
            if best is not None:
                ev.append(best)
    # ---- Donchian and calendar classes: break = first close beyond the previous window's extreme after >= 10 bars inside
    for cls, (hi, lo) in {"don20": (don20h, don20l), "don55": (don55h, don55l), **cal}.items():
        inside_h = inside_l = 0
        for i in range(1, n):
            if not (np.isfinite(hi[i]) and np.isfinite(lo[i]) and np.isfinite(A[i])):
                continue
            if c[i] > hi[i]:
                if inside_h >= MIN_AGE:
                    ev.append(dict(t=i, dir=1, cls=cls, L=hi[i], age=inside_h, touches=0, depth=np.nan, holdc=0, sig=np.nan, dist=abs(c[i - 1] - hi[i])))
                inside_h = 0
            else:
                inside_h += 1
            if c[i] < lo[i]:
                if inside_l >= MIN_AGE:
                    ev.append(dict(t=i, dir=-1, cls=cls, L=lo[i], age=inside_l, touches=0, depth=np.nan, holdc=0, sig=np.nan, dist=abs(c[i - 1] - lo[i])))
                inside_l = 0
            else:
                inside_l += 1
    E = pd.DataFrame(ev)
    if len(E) == 0:
        return dict(o=o, h=h, l=l, c=c, v=v, A=A, rng=rng, vmed=vmed), E
    E = E.sort_values(["t", "cls"]).reset_index(drop=True)
    t = E["t"].to_numpy(int); dr = E["dir"].to_numpy(int)
    E["range_atr"] = rng[t] / A[t]; E["rvol"] = v[t] / np.where(vmed[t] > 0, vmed[t], np.nan)
    E["pen"] = dr * (c[t] - E["L"].to_numpy()) / A[t]
    E["ctx"] = (context[t] * dr) if context is not None else 0            # +1 with-trend, -1 against, 0 none
    E["spx"] = (spx[t] * dr) if spx is not None else 0
    # variants: ii (>= 0.25 ATR beyond), iii (second consecutive close beyond), iv (retest then close on the far side)
    v2 = (E["pen"] >= 0.25).to_numpy()
    t3 = np.full(len(E), -1); t4 = np.full(len(E), -1)
    for j, (ti, di, L) in enumerate(zip(t, dr, E["L"].to_numpy())):
        if ti + 1 < n and di * (c[ti + 1] - L) > 0:
            t3[j] = ti + 1
        for m in range(ti + 1, min(n, ti + RETEST_WIN + 1)):
            if di * (c[m] - L) <= 0:
                break
            if (di > 0 and l[m] <= L + TOUCH_BAND * A[m]) or (di < 0 and h[m] >= L - TOUCH_BAND * A[m]):
                t4[j] = m; break
    E["v2"] = v2; E["t3"] = t3; E["t4"] = t4
    return dict(o=o, h=h, l=l, c=c, v=v, A=A, rng=rng, vmed=vmed), E


def first_passage(h, l, c, A, t, dr, N, mult=1.0):
    if t + N >= len(c):
        return np.nan, np.nan
    up, dn = c[t] + mult * A[t], c[t] - mult * A[t]
    for k in range(1, N + 1):
        hu = h[t + k] >= up; hd = l[t + k] <= dn
        if hu and hd:
            return 0.0, k
        if hu:
            return (1.0 if dr > 0 else -1.0), k
        if hd:
            return (-1.0 if dr > 0 else 1.0), k
    return 0.0, N + 1


def targets_at(F, t, dr, L, N):
    h, l, c, A = F["h"], F["l"], F["c"], F["A"]
    out = {}
    out["fp"], _ = first_passage(h, l, c, A, t, dr, N)
    out["fp2"], _ = first_passage(h, l, c, A, t, dr, 2 * N, 2.0)
    if t + N < len(c):
        out["hold"] = float(all(dr * (c[t + j] - L) > 0 for j in range(1, N + 1)) and dr * (c[t + N] - L) >= 0.5 * A[t]) if np.isfinite(L) else np.nan
        seg_h = h[t + 1:t + N + 1]; seg_l = l[t + 1:t + N + 1]
        out["mfe"] = float(max(dr * ((seg_h if dr > 0 else seg_l) - c[t])) / A[t]); out["mae"] = float(max(-dr * ((seg_l if dr > 0 else seg_h) - c[t])) / A[t])
    else:
        out["hold"] = np.nan; out["mfe"] = np.nan; out["mae"] = np.nan
    out["false"] = float(any(dr * (c[t + j] - L) <= 0 for j in range(1, 4))) if (t + 3 < len(c) and np.isfinite(L)) else np.nan
    return out


def trend_rule(F, t, dr, opp_breaks: np.ndarray, cost_bp: float, max_bars: int = 200):
    """enter at the event close, exit at a 2-ATR trailing stop on closes or at the first opposite break; R in ATR."""
    c, A = F["c"], F["A"]; a0 = A[t]
    if not np.isfinite(a0) or a0 <= 0:
        return np.nan, np.nan
    best = c[t]; stop = c[t] - dr * 2 * a0
    for k in range(t + 1, min(len(c), t + max_bars)):
        if dr * (c[k] - best) > 0:
            best = c[k]; stop = best - dr * 2 * a0
        if dr * (c[k] - stop) <= 0 or opp_breaks[k]:
            return (dr * (c[k] - c[t]) / a0) - 2 * cost_bp / 1e4 * c[t] / a0, k - t
    k = min(len(c), t + max_bars) - 1
    return (dr * (c[k] - c[t]) / a0) - 2 * cost_bp / 1e4 * c[t] / a0, k - t


def pseudo_entries(n: int, t: int, dr: int, break_bars: np.ndarray, rng, m: int = 20, span: int = 0):
    """random bars of the same series, not within 3 bars of any break, same direction as the real event. They are
    drawn from the whole series: a window around the break would be conditioned on the move that caused the break
    (bars just before an up-break sit inside the rally), which biased the first version by +5 points."""
    out = []
    lo, hi = 1, n - 2
    tries = 0
    while len(out) < m and tries < 400:
        j = int(rng.integers(lo, hi + 1)); tries += 1
        if not break_bars[max(0, j - 3):j + 4].any():
            out.append(j)
    return out
