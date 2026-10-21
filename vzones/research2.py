"""Five improvement ideas, each tested on bundled SPY/QQQ data (no look-ahead)."""
from __future__ import annotations
import numpy as np, pandas as pd
from .indicator import VZParams, compute, distribute_volume
from .backtest import run, stats


def lvn_speed(r: pd.DataFrame, fwd: int = 5) -> pd.DataFrame:
    """Idea 1: forward |move| (in ATR) when price sits in HVN vs LVN vs neither."""
    c, atr = r.close.to_numpy(), r.atr.to_numpy()
    f = np.r_[np.abs(c[fwd:] - c[:-fwd]), np.full(fwd, np.nan)] / atr
    zone = np.where(r.in_hvn == 1, "inside HVN", np.where(r.in_lvn == 1, "inside LVN", "between"))
    d = pd.DataFrame({"zone": zone, "move_atr": f}).dropna()
    g = d.groupby("zone").move_atr.agg(["count", "mean", "median"])
    g["p_big(>2ATR)"] = d.groupby("zone").move_atr.apply(lambda x: (x > 2).mean())
    return g.round(3)


def naked_poc(df: pd.DataFrame, block: int, horizon: int, atr: np.ndarray, rows: int = 30) -> dict:
    """Idea 2: block POCs not yet revisited vs a mirrored control level at the same distance."""
    h, l, v, c = (df[k].to_numpy(float) for k in ("high", "low", "volume", "close"))
    hit_poc = hit_ctrl = n = 0
    for b0 in range(0, len(df) - block - horizon, block):
        b1 = b0 + block
        e = np.linspace(l[b0:b1].min(), h[b0:b1].max() + 1e-9, rows + 1)
        prof = distribute_volume(h[b0:b1], l[b0:b1], v[b0:b1], e)
        poc = (e[:-1] + e[1:])[prof.argmax()] / 2
        t0 = b1                     # first bar after the block
        if not np.isfinite(atr[t0]) or l[t0] <= poc <= h[t0]:
            continue
        dist = poc - c[t0 - 1]
        if abs(dist) < 0.5 * atr[t0]:
            continue
        ctrl = c[t0 - 1] - dist     # same distance, opposite side
        hh, ll = h[t0:t0 + horizon], l[t0:t0 + horizon]
        hit_poc += ((ll <= poc) & (hh >= poc)).any(); hit_ctrl += ((ll <= ctrl) & (hh >= ctrl)).any(); n += 1
    return dict(samples=n, p_touch_naked_poc=round(hit_poc / n, 3), p_touch_mirror_level=round(hit_ctrl / n, 3))


def htf_filter(r: pd.DataFrame, sig: np.ndarray) -> np.ndarray:
    """Idea 4: keep a signal only if yesterday's daily close is on the same side of the daily EMA50."""
    d = r.close.resample("1D").last().dropna()
    bias = np.sign(d - d.ewm(span=50, adjust=False).mean()).shift(1)        # known before today opens
    b = bias.reindex(r.index.normalize()).to_numpy()
    return np.where(np.sign(sig) == b, sig, 0)


def confirm_next(r: pd.DataFrame, col: str) -> pd.DataFrame:
    """Idea 5: move a signal to the next bar only if that bar closes in the signal direction."""
    out = r.copy(); s = r[col].to_numpy(); c, o = r.close.to_numpy(), r.open.to_numpy()
    new = np.zeros_like(s)
    for t in np.flatnonzero(s[:-1]):
        if (c[t + 1] - o[t + 1]) * s[t] > 0:
            new[t + 1] = s[t]
    out[col] = new
    if col == "rejection":       # keep the original wick as the stop: low/high of the signal bar
        out["low"] = r.low.where(new == 0, np.minimum(r.low, r.low.shift(1)))
        out["high"] = r.high.where(new == 0, np.maximum(r.high, r.high.shift(1)))
    return out
