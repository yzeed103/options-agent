"""Candidates and metrics of reports/hma_successor/PREREG.md: averages that keep the Hull average's calm in trends but
overshoot less at reversals. Every candidate is a pure function of past candles only (tests/test_hma_successor.py
checks the prefix property)."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from vzones import conviction_ma as CM

SHAPES = {"DHMA": [0.6, 0.7, 0.8, 0.9, 1.0], "CHMA": [3, 5, 8, 12], "HOLT": [0.8, 0.85, 0.9, 0.95, 1.0],
          "MED3": [None], "BLEND": [0.5, 1.0, 2.0, 3.0]}


# ---------------- candidates ----------------
def dhma(x, n: int, g: float = 1.0):
    """Damped Hull: WMA((2 WMA(n/2) - g WMA(n)) / (2 - g), sqrt n). g = 1 is the plain HMA."""
    half, root = max(1, n // 2), max(1, int(round(math.sqrt(n))))
    return CM.wma((2 * CM.wma(x, half) - g * CM.wma(x, n)) / (2 - g), root)


def chma(x, hi, lo, n: int, k: int = 5):
    """Hull clipped to the range of the last k candles (their highs and lows)."""
    m = CM.hma(x, n)
    top = pd.Series(hi).rolling(k, min_periods=1).max().to_numpy()
    bot = pd.Series(lo).rolling(k, min_periods=1).min().to_numpy()
    return np.clip(m, bot, top)


def holt(x, n: int, phi: float = 0.9):
    """Damped Holt: level L = a x + (1 - a)(L1 + phi T1), trend T = b (L - L1) + (1 - b) phi T1, output L + phi T.
    a = 2 / (n + 1), b = a / 5. phi < 1 damps the slope (the brake on overshoot)."""
    a = 2 / (n + 1)
    b = a / 5
    xs = list(map(float, x))
    out = [math.nan] * len(xs)
    L = T = math.nan
    for i, v in enumerate(xs):
        if math.isnan(v):
            continue
        if math.isnan(L):
            L, T = v, 0.0
        else:
            L1 = L
            L = a * v + (1 - a) * (L1 + phi * T)
            T = b * (L - L1) + (1 - b) * phi * T
        out[i] = L + phi * T
    return np.array(out)


def med3(x, n_hma: int, n_ss: int, n_alma: int):
    """Median of Hull, SuperSmoother and ALMA (each at its own length, matched to one lag)."""
    return np.nanmedian(np.vstack([CM.hma(x, n_hma), CM.supersmoother(x, n_ss), CM.alma(x, n_alma)]), axis=0)


def efficiency_ratio(x, n: int = 20):
    x = np.asarray(x, float)
    ch = np.abs(x - np.r_[np.full(n, np.nan), x[:-n]])
    vol = pd.Series(np.abs(np.diff(x, prepend=np.nan))).rolling(n).sum().to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        er = np.where(vol > 0, ch / vol, 0.0)
    return np.nan_to_num(er)


def blend(x, n_hma: int, n_ss: int, p: float = 1.0, er_n: int = 20):
    """w HMA + (1 - w) SuperSmoother, w = ER(20) ** p: Hull in trends, smoother in chop."""
    w = efficiency_ratio(x, er_n) ** p
    return w * CM.hma(x, n_hma) + (1 - w) * CM.supersmoother(x, n_ss)


# ---------------- metrics ----------------
def ha_atr(o, h, l, c, n: int = 14):
    ho, hh, hl, hc = CM.heikin_ashi(o, h, l, c)
    return CM.rma(CM.true_range(hh, hl, hc), n)


def overshoot(M, t: int, old_dir: int, turning_price: float, atr: float, horizon: int = 30) -> float:
    """Max distance M travels past the turning price in the OLD direction after the reversal bar t, in ATR (>= 0)."""
    seg = M[t:t + horizon + 1]
    seg = seg[np.isfinite(seg)]
    if len(seg) == 0 or not np.isfinite(atr) or atr <= 0:
        return np.nan
    return float(max(0.0, np.max(old_dir * (seg - turning_price))) / atr)


def turn_delay(M, t: int, new_dir: int, hold: int = 3, maxd: int = 60) -> float:
    """Bars after t until sign(dM) equals the new direction for `hold` bars in a row."""
    dm = np.sign(np.diff(M))
    for i in range(t, min(t + maxd, len(dm) - hold)):
        if np.all(dm[i:i + hold] == new_dir):
            return float(i - t)
    return np.nan


def reversals(c, atr, n: int = 20, min_len: int = 10):
    """Labelled reversals on real data (evaluation only, uses the future): bars where the forward-backward EMA(n)
    slope changes sign with a trend of >= min_len bars on both sides. Returns [(bar, old_dir)]."""
    lab = CM.trend_labels(c, atr, n=n, thr=0.0, min_len=min_len)
    out = []
    for t in range(1, len(lab)):
        if lab[t] != 0 and lab[t - 1] == -lab[t]:
            out.append((t, int(lab[t - 1])))
    return out


def turning_price(hh, hl, t: int, old_dir: int, w: int = 3) -> float:
    a, b = max(0, t - w), min(len(hh), t + w + 1)
    return float(np.nanmax(hh[a:b])) if old_dir > 0 else float(np.nanmin(hl[a:b]))
