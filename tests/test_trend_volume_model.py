"""Trend-volume model (reports/trend_volume_model/PREREG.md): past-only quantities, level mass is causal, targets."""
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from vzones import trend_volume_model as TM  # noqa: E402
import trend_volume_model_eval as ME  # noqa: E402


def _d(seed=31, sessions=40):
    d, _, _ = ME.synth(seed, True, sessions=sessions)
    return d


def test_bars_and_events_use_past_only():
    d = _d()
    r = TM.run(d, 5); k = 2000
    r2 = TM.run(d.iloc[:k], 5)
    for col in ("I", "J", "J0", "S", "S0"):
        assert np.allclose(r["bars"][col].to_numpy()[:k], r2["bars"][col].to_numpy(), equal_nan=True), col
    a = r["breaks"][r["breaks"]["t"] < k - 3]; b = r2["breaks"][r2["breaks"]["t"] < k - 3]
    assert len(a) == len(b) and np.allclose(a["mass"].fillna(-9).to_numpy(), b["mass"].fillna(-9).to_numpy())


def test_mass_is_causal_and_twin_sane():
    d = _d()
    v2 = d.copy(); r = TM.run(d, 5); br = r["breaks"]
    t = int(br["t"].iloc[len(br) // 2])
    v2.iloc[t + 1:, v2.columns.get_loc("volume")] *= 5            # volume AFTER the break must not change its mass
    r2 = TM.run(v2, 5); br2 = r2["breaks"]
    m1 = br[br["t"] == t]["mass"].iloc[0]; m2 = br2[br2["t"] == t]["mass"].iloc[0]
    assert np.isclose(m1, m2)
    assert (br["time"] >= 1).all() and (br["mass"].dropna() >= 0).all()


def test_targets_and_retest():
    d = _d()
    r = TM.run(d, 5); Y = TM.targets(r)
    br = Y["breaks"]
    ok = np.isfinite(br["hold"]) & np.isfinite(br["false"])
    assert not ((br["hold"][ok] > 0) & (br["false"][ok] > 0)).any()      # a held break was never a false break
    rt = br[np.isfinite(br["retest_t"])]
    assert (rt["retest_t"] > rt["t"]).all() and (rt["ratio_r"] > 0).all()
    tr = Y["trend"]
    assert (tr["t"].diff().dropna() != 0).all() and set(tr["dir"].unique()) <= {1, -1}
