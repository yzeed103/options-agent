"""Volume Zones indicator.

Builds a rolling volume profile (volume distributed over price rows, like
TradingView's VPVR) from *past* bars only, extracts the zones where most
trading happened (HVN = high volume nodes) and the thin areas (LVN = low
volume nodes), then derives the signals the strategy needs:

* ``in_hvn`` / ``in_lvn``      - where the current close sits in the profile.
* ``weak_volume``              - traded volume is weak relative to its average.
* ``pool_active``              - a "weak volume pool": several consecutive
                                 weak-volume bars trading in a tight range.
* ``pool_break`` (+1/-1)       - the pool is broken with expanding volume.
* ``hunt`` (+1/-1)             - pool break + strong directional trend + a
                                 previous HVN sits ahead in the break direction:
                                 price is "hunting" (targeting) that zone.
* ``target``                   - the HVN price being targeted while hunting.
* ``magnet`` (+1/-1)           - while a hunt is open, price keeps moving toward
                                 the target with the trend intact.
* ``rejection`` (+1/-1)        - price probes an HVN and gets rejected from it
                                 (+1 = bullish rejection at an HVN below, -1 =
                                 bearish rejection at an HVN above).

Everything is computed without look-ahead: the profile for bar ``t`` uses bars
``t-lookback .. t-1`` and all moving averages are trailing.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import List, Tuple

import numpy as np
import pandas as pd


# --------------------------------------------------------------------------- #
# Parameters
# --------------------------------------------------------------------------- #
@dataclass
class VZParams:
    # volume profile
    lookback: int = 120          # bars in the rolling profile window
    rows: int = 40               # price rows of the profile
    value_area: float = 0.70     # share of volume inside the value area
    hvn_mult: float = 1.5        # row volume > hvn_mult * mean row volume -> HVN
    lvn_mult: float = 0.5        # row volume < lvn_mult * mean row volume -> LVN
    max_hvn: int = 6             # keep at most this many HVN zones (strongest first)
    step: int = 1                # recompute the profile every `step` bars (speed)
    # traded-volume regime
    vol_ma: int = 20             # SMA length for relative volume
    weak_ratio: float = 0.85     # volume / SMA below this -> weak bar
    weak_bars: int = 4           # bars needed to form a weak pool
    pool_max_range_atr: float = 2.5   # pool range (in ATR) must stay below this
    break_ratio: float = 1.3     # volume / SMA needed to confirm the pool break
    # trend
    adx_len: int = 14
    adx_strong: float = 22.0
    ema_fast: int = 20
    ema_slow: int = 50
    # targeting / rejection
    min_target_atr: float = 1.0  # target must be at least this far (in ATR)
    max_target_atr: float = 12.0 # and not further than this
    reject_wick: float = 0.5     # wick share of the bar range for a rejection
    atr_len: int = 14

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------- #
# Volume profile
# --------------------------------------------------------------------------- #
@dataclass
class VolumeProfile:
    edges: np.ndarray                   # rows+1 price edges
    volume: np.ndarray                  # volume per row
    poc: float                          # point of control (price)
    vah: float                          # value area high
    val: float                          # value area low
    hvn: List[Tuple[float, float, float]] = field(default_factory=list)  # (lo, hi, vol)
    lvn: List[Tuple[float, float, float]] = field(default_factory=list)

    @property
    def centers(self) -> np.ndarray:
        return (self.edges[:-1] + self.edges[1:]) / 2.0

    def row_of(self, price: float) -> int:
        i = int(np.searchsorted(self.edges, price, side="right") - 1)
        return min(max(i, 0), len(self.volume) - 1)


def distribute_volume(high: np.ndarray, low: np.ndarray, volume: np.ndarray,
                      edges: np.ndarray) -> np.ndarray:
    """Spread each bar's volume uniformly over the rows its high-low range covers."""
    lo = low[:, None]
    hi = high[:, None]
    width = np.maximum(hi - lo, 1e-12)
    overlap = np.clip(np.minimum(hi, edges[None, 1:]) - np.maximum(lo, edges[None, :-1]), 0.0, None)
    frac = overlap / width
    # a bar with zero range falls entirely into one row
    zero = (high - low) <= 0
    if zero.any():
        idx = np.clip(np.searchsorted(edges, low[zero], side="right") - 1, 0, len(edges) - 2)
        frac[zero] = 0.0
        frac[np.flatnonzero(zero), idx] = 1.0
    return (frac * volume[:, None]).sum(axis=0)


def _runs(mask: np.ndarray) -> List[Tuple[int, int]]:
    """Return [start, end] index pairs (inclusive) of consecutive True runs."""
    out, start = [], None
    for i, m in enumerate(mask):
        if m and start is None:
            start = i
        elif not m and start is not None:
            out.append((start, i - 1))
            start = None
    if start is not None:
        out.append((start, len(mask) - 1))
    return out


def build_profile(high, low, volume, rows: int = 40, value_area: float = 0.70,
                  hvn_mult: float = 1.5, lvn_mult: float = 0.5, max_hvn: int = 6) -> VolumeProfile:
    high = np.asarray(high, float); low = np.asarray(low, float); volume = np.asarray(volume, float)
    p_lo, p_hi = float(low.min()), float(high.max())
    if p_hi <= p_lo:
        p_hi = p_lo + 1e-6
    edges = np.linspace(p_lo, p_hi, rows + 1)
    vol = distribute_volume(high, low, volume, edges)
    total = vol.sum()
    poc_i = int(vol.argmax())
    # value area: grow from the POC toward the heavier neighbour
    lo_i = hi_i = poc_i
    acc = vol[poc_i]
    while acc < value_area * total and (lo_i > 0 or hi_i < rows - 1):
        up = vol[hi_i + 1] if hi_i < rows - 1 else -1.0
        dn = vol[lo_i - 1] if lo_i > 0 else -1.0
        if up >= dn:
            hi_i += 1; acc += up
        else:
            lo_i -= 1; acc += dn
    mean = total / rows if total > 0 else 0.0
    hvn, lvn = [], []
    for s, e in _runs(vol > hvn_mult * mean):
        hvn.append((float(edges[s]), float(edges[e + 1]), float(vol[s:e + 1].sum())))
    for s, e in _runs(vol < lvn_mult * mean):
        lvn.append((float(edges[s]), float(edges[e + 1]), float(vol[s:e + 1].sum())))
    hvn.sort(key=lambda z: -z[2])
    hvn = sorted(hvn[:max_hvn])
    centers = (edges[:-1] + edges[1:]) / 2.0
    return VolumeProfile(edges=edges, volume=vol, poc=float(centers[poc_i]),
                         vah=float(edges[hi_i + 1]), val=float(edges[lo_i]), hvn=hvn, lvn=lvn)


# --------------------------------------------------------------------------- #
# Classic helpers (trailing, no look-ahead)
# --------------------------------------------------------------------------- #
def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    prev = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"], (df["high"] - prev).abs(), (df["low"] - prev).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()


def adx(df: pd.DataFrame, n: int = 14) -> pd.DataFrame:
    up = df["high"].diff()
    dn = -df["low"].diff()
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    prev = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"], (df["high"] - prev).abs(), (df["low"] - prev).abs()], axis=1).max(axis=1)
    atr_ = tr.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()
    plus_di = 100 * pd.Series(plus_dm, index=df.index).ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean() / atr_
    minus_di = 100 * pd.Series(minus_dm, index=df.index).ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean() / atr_
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return pd.DataFrame({"adx": dx.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean(),
                         "plus_di": plus_di, "minus_di": minus_di})


# --------------------------------------------------------------------------- #
# Main computation
# --------------------------------------------------------------------------- #
def _nearest(zones, price, direction):
    """Nearest HVN zone strictly above (+1) / below (-1) ``price``; returns (lo, hi, vol) or None."""
    best = None
    for lo, hi, v in zones:
        if direction > 0 and lo > price and (best is None or lo < best[0]):
            best = (lo, hi, v)
        elif direction < 0 and hi < price and (best is None or hi > best[1]):
            best = (lo, hi, v)
    return best


def compute(df: pd.DataFrame, params: VZParams | None = None, keep_profiles: bool = False) -> pd.DataFrame:
    """Return ``df`` plus indicator columns. ``df`` needs open/high/low/close/volume."""
    p = params or VZParams()
    df = df.copy()
    n = len(df)
    o, h, l, c, v = (df[k].to_numpy(float) for k in ("open", "high", "low", "close", "volume"))

    out = {k: np.full(n, np.nan) for k in (
        "poc", "vah", "val", "hvn_above", "hvn_below", "hvn_above_hi", "hvn_below_lo",
        "row_vol_ratio", "target", "pool_high", "pool_low")}
    flags = {k: np.zeros(n, dtype=int) for k in (
        "in_hvn", "in_lvn", "weak_volume", "pool_active", "pool_break", "hunt", "magnet", "rejection", "strong_trend")}
    profiles = [None] * n if keep_profiles else None

    vol_sma = pd.Series(v).rolling(p.vol_ma, min_periods=p.vol_ma).mean().to_numpy()
    vol_ratio = v / vol_sma
    atr_ = atr(df, p.atr_len).to_numpy()
    dmi = adx(df, p.adx_len)
    adx_v, pdi, mdi = dmi["adx"].to_numpy(), dmi["plus_di"].to_numpy(), dmi["minus_di"].to_numpy()
    ema_f = df["close"].ewm(span=p.ema_fast, adjust=False).mean().to_numpy()
    ema_s = df["close"].ewm(span=p.ema_slow, adjust=False).mean().to_numpy()
    trend_dir = np.where((ema_f > ema_s) & (pdi > mdi), 1, np.where((ema_f < ema_s) & (mdi > pdi), -1, 0))
    strong = (adx_v >= p.adx_strong) & (trend_dir != 0)
    weak = vol_ratio < p.weak_ratio

    prof: VolumeProfile | None = None
    pool_start = None          # index where the current weak pool began
    hunt_dir, hunt_target, hunt_stop = 0, np.nan, np.nan

    for t in range(p.lookback, n):
        # ---- rolling profile from past bars only ----------------------------
        if prof is None or (t - p.lookback) % p.step == 0:
            s = t - p.lookback
            prof = build_profile(h[s:t], l[s:t], v[s:t], p.rows, p.value_area, p.hvn_mult, p.lvn_mult, p.max_hvn)
        if keep_profiles:
            profiles[t] = prof
        out["poc"][t], out["vah"][t], out["val"][t] = prof.poc, prof.vah, prof.val
        row = prof.row_of(c[t])
        mean_row = prof.volume.mean() if prof.volume.sum() > 0 else np.nan
        out["row_vol_ratio"][t] = prof.volume[row] / mean_row if mean_row else np.nan
        flags["in_hvn"][t] = int(any(lo <= c[t] <= hi for lo, hi, _ in prof.hvn))
        flags["in_lvn"][t] = int(any(lo <= c[t] <= hi for lo, hi, _ in prof.lvn))
        above = _nearest(prof.hvn, c[t], +1)
        below = _nearest(prof.hvn, c[t], -1)
        if above:
            out["hvn_above"][t], out["hvn_above_hi"][t] = above[0], above[1]
        if below:
            out["hvn_below"][t], out["hvn_below_lo"][t] = below[1], below[0]
        flags["weak_volume"][t] = int(bool(weak[t]))
        flags["strong_trend"][t] = int(bool(strong[t])) * int(trend_dir[t])

        # ---- weak volume pool ------------------------------------------------
        if np.isnan(atr_[t]):
            continue
        if pool_start is None:
            # start a pool when the last `weak_bars` bars are mostly weak and tight
            w = weak[t - p.weak_bars + 1:t + 1]
            rng = h[t - p.weak_bars + 1:t + 1].max() - l[t - p.weak_bars + 1:t + 1].min()
            if w.sum() >= p.weak_bars - 1 and rng <= p.pool_max_range_atr * atr_[t]:
                pool_start = t - p.weak_bars + 1
        if pool_start is not None:
            ph, pl = h[pool_start:t + 1].max(), l[pool_start:t + 1].min()
            broke_up = c[t] > h[pool_start:t].max() and vol_ratio[t] >= p.break_ratio
            broke_dn = c[t] < l[pool_start:t].min() and vol_ratio[t] >= p.break_ratio
            if broke_up or broke_dn:
                d = 1 if broke_up else -1
                flags["pool_break"][t] = d
                out["pool_high"][t], out["pool_low"][t] = h[pool_start:t].max(), l[pool_start:t].min()
                # candidate targets: previous HVN edges + POC + value-area edges
                cands = [z[0] for z in prof.hvn] + [z[1] for z in prof.hvn] + [prof.poc, prof.vah, prof.val]
                ahead = [x for x in cands if (x - c[t]) * d > 0
                         and p.min_target_atr <= abs(x - c[t]) / atr_[t] <= p.max_target_atr]
                ema_ok = (ema_f[t] > ema_s[t]) if d > 0 else (ema_f[t] < ema_s[t])
                if ahead and adx_v[t] >= p.adx_strong and ema_ok:
                    tgt = min(ahead, key=lambda x: abs(x - c[t]))
                    if True:
                        flags["hunt"][t] = d
                        out["target"][t] = tgt
                        hunt_dir, hunt_target = d, tgt
                        hunt_stop = out["pool_low"][t] if d > 0 else out["pool_high"][t]
                pool_start = None
            else:
                flags["pool_active"][t] = 1
                out["pool_high"][t], out["pool_low"][t] = ph, pl
                # pool widened too much or volume came back strongly -> dissolve
                if (ph - pl) > p.pool_max_range_atr * atr_[t] or vol_ratio[t] >= p.break_ratio:
                    pool_start = None
                    flags["pool_active"][t] = 0

        # ---- magnet: an open hunt that keeps progressing ----------------------
        if hunt_dir != 0 and not flags["hunt"][t]:
            reached = (c[t] >= hunt_target) if hunt_dir > 0 else (c[t] <= hunt_target)
            stopped = (c[t] < hunt_stop) if hunt_dir > 0 else (c[t] > hunt_stop)
            if reached or stopped or trend_dir[t] == -hunt_dir:
                hunt_dir = 0
            else:
                progress = (c[t] > c[t - 1]) if hunt_dir > 0 else (c[t] < c[t - 1])
                flags["magnet"][t] = hunt_dir if progress else 0
                out["target"][t] = hunt_target

        # ---- rejection at an HVN ---------------------------------------------
        rng = h[t] - l[t]
        if rng > 0:
            upper_wick = (h[t] - max(o[t], c[t])) / rng
            lower_wick = (min(o[t], c[t]) - l[t]) / rng
            # bearish: probes an HVN above (from below) and closes back under it
            for lo, hi, _ in prof.hvn:
                if l[t] < lo <= h[t] and c[t] < lo and c[t] < o[t] and upper_wick >= p.reject_wick:
                    flags["rejection"][t] = -1
                if l[t] <= hi < h[t] and c[t] > hi and c[t] > o[t] and lower_wick >= p.reject_wick:
                    flags["rejection"][t] = 1

    for k, arr in out.items():
        df[k] = arr
    for k, arr in flags.items():
        df[k] = arr
    df["vol_ratio"] = vol_ratio
    df["atr"] = atr_
    df["adx"] = adx_v
    df["trend_dir"] = trend_dir
    if keep_profiles:
        df.attrs["profiles"] = profiles
    df.attrs["params"] = p.to_dict()
    return df


def latest_state(df: pd.DataFrame) -> dict:
    """Compact JSON-friendly summary of the last bar (for the web API)."""
    last = df.iloc[-1]
    def f(x):
        return None if pd.isna(x) else round(float(x), 4)
    recent = df.tail(50)
    return {
        "time": str(df.index[-1]),
        "close": f(last["close"]),
        "poc": f(last["poc"]), "vah": f(last["vah"]), "val": f(last["val"]),
        "hvn_above": f(last["hvn_above"]), "hvn_below": f(last["hvn_below"]),
        "in_hvn": bool(last["in_hvn"]), "in_lvn": bool(last["in_lvn"]),
        "row_vol_ratio": f(last["row_vol_ratio"]),
        "vol_ratio": f(last["vol_ratio"]), "weak_volume": bool(last["weak_volume"]),
        "pool_active": bool(last["pool_active"]),
        "pool_high": f(last["pool_high"]), "pool_low": f(last["pool_low"]),
        "adx": f(last["adx"]), "trend_dir": int(last["trend_dir"]), "strong_trend": int(last["strong_trend"]),
        "pool_break": int(last["pool_break"]), "hunt": int(last["hunt"]), "magnet": int(last["magnet"]),
        "target": f(last["target"]), "rejection": int(last["rejection"]),
        "recent_signals": [
            {"time": str(i), "pool_break": int(r.pool_break), "hunt": int(r.hunt),
             "rejection": int(r.rejection), "target": f(r.target), "close": f(r.close)}
            for i, r in recent.iterrows() if r.pool_break or r.hunt or r.rejection
        ],
    }
