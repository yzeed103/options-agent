import numpy as np, pandas as pd, pytest
from vzones.intraday.features import add_features
from vzones.intraday.signals import SETUPS
from vzones.intraday.engine import Exec, run, metrics
from vzones.intraday.validate import permutation_test, holdout_split


def synth(days=30, seed=1):
    """Synthetic 5m bars - for MECHANICS tests only, never for strategy evaluation."""
    rng = np.random.default_rng(seed); idx = []
    for d in pd.bdate_range("2024-01-02", periods=days):
        idx += list(pd.date_range(d + pd.Timedelta(minutes=570), periods=78, freq="5min", tz="America/New_York"))
    n = len(idx); c = 100 + np.cumsum(rng.normal(0, .2, n)); o = np.r_[c[0], c[:-1]]
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) + .1, "low": np.minimum(o, c) - .1, "close": c,
                         "volume": rng.uniform(1e4, 3e4, n)}, index=pd.DatetimeIndex(idx))


def test_features_no_lookahead():
    df = synth(); full = add_features(df); cut = len(df) * 2 // 3
    part = add_features(df.iloc[:cut])
    cols = ["atr", "vwap", "vwap_up2", "or_high", "or_low", "pd_poc", "pd_vah", "pd_val", "ema_f"]
    pd.testing.assert_frame_equal(full[cols].iloc[:cut], part[cols], check_dtype=False)


@pytest.mark.parametrize("name", list(SETUPS))
def test_signals_no_lookahead(name):
    df = synth(); full = SETUPS[name](add_features(df)); cut = len(df) * 2 // 3
    assert (full[:cut] == SETUPS[name](add_features(df.iloc[:cut]))).all()


def _bars(rows):
    idx = pd.date_range("2024-01-02 09:30", periods=len(rows), freq="5min", tz="America/New_York")
    d = pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx)
    d["volume"] = 1.0; d["atr"] = 1.0; d["session"] = idx.date
    return d


def test_stop_first_when_both_hit():
    d = _bars([[100, 100, 100, 100], [100, 104, 98, 100], [100, 100, 100, 100]])
    t = run(d, np.array([1, 0, 0]), Exec(stop_atr=1, target_atr=3, cost=0))
    assert t.r.iat[0] == pytest.approx(-1.0)


def test_gap_through_stop_fills_at_open():
    d = _bars([[100, 100, 100, 100], [100, 100.5, 99.5, 100], [97, 97.5, 96, 97]])
    t = run(d, np.array([1, 0, 0]), Exec(stop_atr=1, target_atr=3, cost=0))
    assert t.exit.iat[0] == 97 and t.r.iat[0] == pytest.approx(-3.0)


def test_target_and_costs():
    d = _bars([[100, 100, 100, 100], [100, 103.5, 99.5, 103], [103, 103, 103, 103]])
    t = run(d, np.array([1, 0, 0]), Exec(stop_atr=1, target_atr=3, cost=0.0001))
    assert t.r.iat[0] == pytest.approx(3 - 2 * 0.01, abs=1e-6)


def test_partial_then_breakeven():
    d = _bars([[100, 100, 100, 100], [100, 101.2, 99.8, 101], [101, 101, 99.9, 100]])
    t = run(d, np.array([1, 0, 0]), Exec(stop_atr=1, target_atr=3, partial_r=1, partial_frac=.5, cost=0))
    assert t.r.iat[0] == pytest.approx(0.5)


def test_permutation_and_holdout_run():
    d = add_features(synth(40)); a, b = holdout_split(d)
    assert a.session.max() < b.session.min()
    res = permutation_test(a, SETUPS["vwap_reclaim"](a), Exec(stop_atr=1, target_atr=2), n=20)
    assert 0 < res["p_value"] <= 1
