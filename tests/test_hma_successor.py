"""HMA successor candidates (reports/hma_successor/PREREG.md): no look-ahead, bounds, identities."""
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from vzones import conviction_ma as CM  # noqa: E402
from vzones import hma_successor as HS  # noqa: E402
import hma_successor_eval as E  # noqa: E402


def _d(seed=3):
    return E.load([seed])[0]


def _cut(d, k):
    return {kk: (v[:k] if isinstance(v, np.ndarray) else v) for kk, v in d.items()}


def test_no_lookahead_every_candidate():
    d = _d()
    fns = [lambda d: HS.dhma(d["hc"], 40, 0.8), lambda d: HS.chma(d["hc"], d["hh"], d["hl"], 40, 5),
           lambda d: HS.holt(d["hc"], 40, 0.9), lambda d: HS.med3(d["hc"], 40, 20, 25), lambda d: HS.blend(d["hc"], 40, 20, 1.0)]
    for f in fns:
        full = f(d)
        for k in (300, 700, 999):
            assert np.allclose(full[:k], f(_cut(d, k)), equal_nan=True)


def test_dhma_g1_is_hma_and_damping_reduces_extrapolation():
    d = _d()
    assert np.allclose(HS.dhma(d["hc"], 40, 1.0), CM.hma(d["hc"], 40), equal_nan=True)
    # on a straight ramp the plain HMA lags 4/3 bar (2 * 19/3 - 39/3 + 5/3); damping lags more (less extrapolation)
    x = np.arange(400, dtype=float)
    assert abs(CM.hma(x, 40)[-1] - (x[-1] - 4 / 3)) < 1e-6
    assert HS.dhma(x, 40, 0.7)[-1] < CM.hma(x, 40)[-1] - 1


def test_clamp_inside_candle_range():
    d = _d()
    M = HS.chma(d["hc"], d["hh"], d["hl"], 40, 5)
    import pandas as pd
    top = pd.Series(d["hh"]).rolling(5, min_periods=1).max().to_numpy()
    bot = pd.Series(d["hl"]).rolling(5, min_periods=1).min().to_numpy()
    ok = np.isfinite(M)
    assert np.all(M[ok] <= top[ok] + 1e-9) and np.all(M[ok] >= bot[ok] - 1e-9)


def test_overshoot_and_delay_on_a_clean_v():
    # a clean V: price rises 100 bars, then falls; a lagging SMA overshoots the top, a zero-lag line does not
    up = np.arange(100, dtype=float); c = np.r_[up, up[::-1]]
    hh, hl = c + 0.1, c - 0.1
    atr = np.full(len(c), 1.0)
    sma = CM.sma(c, 10)
    tp = HS.turning_price(hh, hl, 100, 1)
    assert HS.overshoot(sma, 100, 1, tp, 1.0) == 0.0          # a lagging average never passes the top
    assert HS.overshoot(c + 5, 100, 1, tp, 1.0) > 4           # a line 5 above price does
    assert HS.turn_delay(sma, 100, -1) >= 4 and HS.turn_delay(c, 100, -1) <= 1
