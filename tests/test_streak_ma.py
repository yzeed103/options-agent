"""Streak average (reports/conviction_ma/PREREG_STREAK.md): no look-ahead, bounded speed, planted behaviour."""
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from vzones import conviction_ma as CM  # noqa: E402
from conviction_eval import planted, side_flips  # noqa: E402

K = (5, 100, 10, 2.0)


def _walk(n=600, seed=1):
    r = np.random.default_rng(seed)
    c = 100 + np.cumsum(r.normal(0, 0.1, n)); o = np.r_[c[0], c[:-1]]
    return o, np.maximum(o, c) + 0.03, np.minimum(o, c) - 0.03, c


def test_no_lookahead():
    o, h, l, c = _walk()
    full = CM.streak_ema(o, h, l, c, *K)
    for cut in (150, 300, 599):
        part = CM.streak_ema(o[:cut], h[:cut], l[:cut], c[:cut], *K)
        assert np.allclose(full[:cut], part, equal_nan=True)


def test_inside_range_of_source():
    o, h, l, c = _walk()
    M = CM.streak_ema(o, h, l, c, *K)
    hc = CM.heikin_ashi(o, h, l, c)[3]
    assert np.nanmin(M) >= hc.min() - 1e-9 and np.nanmax(M) <= hc.max() + 1e-9


def test_fewer_sideways_flips_than_matched_ema():
    s, e = [], []
    for seed in range(30000, 30030):
        o, h, l, c, lab, meta = planted(seed)
        s.append(side_flips(CM.streak_ema(o, h, l, c, *K), lab))
        e.append(side_flips(CM.ema(CM.heikin_ashi(o, h, l, c)[3], 15), lab))
    assert np.mean(s) < 0.85 * np.mean(e)
