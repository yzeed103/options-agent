"""Volatility engine (reports/vol_engine/PREREG.md): past-only forecasts, GARCH recovery, coverage, first touch."""
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from vzones import vol_engine as VE  # noqa: E402
import vol_engine_eval as E  # noqa: E402


def test_forecasts_use_past_only():
    r, c, h, l, tv, reg = E.synth(3, "V2", n=2500)
    full = VE.garch_var(r, (1e-6, 0.07, 0.90), 6); part = VE.garch_var(r[:1500], (1e-6, 0.07, 0.90), 6)
    assert np.allclose(full[:1500], part, equal_nan=True)
    e_full = VE.ewma_var(r, 0.94); e_part = VE.ewma_var(r[:1500], 0.94)
    assert np.allclose(e_full[:1500], e_part, equal_nan=True)


def test_garch_fit_recovers_persistence():
    r, *_ = E.synth(4, "V2", n=6000)
    w, a, b = VE.garch_fit(r / np.nanstd(r))
    assert 0.9 < a + b <= 1.0 and 0.02 < a < 0.3      # the V2 world adds regime multipliers on top of GARCH, which inflates alpha


def test_coverage_nominal_on_constant_vol():
    r, c, h, l, tv, reg = E.synth(5, "V1", n=8000)
    k = 6; V = k * VE.ewma_var(r, 0.97); mv = VE.forward_move(c, k)
    cov, n = VE.coverage(mv[300:], V[300:], 1)
    assert abs(cov - 0.683) < 0.03 and n > 5000


def test_first_touch():
    c = np.r_[100.0, 100.5, 101.0, 101.6, 102.0]; h = c + 0.1; l = c - 0.1
    hit, mae = VE.first_touch(h, l, c, 0, 1, 1.5, 1.0, 4)
    assert hit == 1 and mae <= 0.1 + 1e-9
    hit, mae = VE.first_touch(h, l, c, 0, -1, 1.5, 1.0, 4)
    assert hit == -1
