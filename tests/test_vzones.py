import numpy as np, pandas as pd, pytest
import vzones
from vzones.indicator import build_profile, distribute_volume
from vzones.backtest import run, stats


def test_distribute_conserves_volume():
    h = np.array([10., 12., 11.]); l = np.array([9., 10., 11.]); v = np.array([100., 50., 30.])
    edges = np.linspace(9, 12, 7)
    assert distribute_volume(h, l, v, edges).sum() == pytest.approx(180.)


def test_profile_poc_and_hvn():
    # heavy trading at 100, light elsewhere
    h = np.r_[np.full(50, 100.5), np.linspace(101, 110, 20)]
    l = np.r_[np.full(50, 99.5), np.linspace(100, 109, 20)]
    v = np.r_[np.full(50, 1000.), np.full(20, 10.)]
    p = build_profile(h, l, v, rows=20)
    assert 99.5 <= p.poc <= 100.5
    assert p.val <= p.poc <= p.vah
    assert any(lo <= 100 <= hi for lo, hi, _ in p.hvn)


def _synthetic(n=600, seed=0):
    rng = np.random.default_rng(seed)
    c = 100 + np.cumsum(rng.normal(0, 1, n))
    o = c + rng.normal(0, .3, n)
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) + .5, "low": np.minimum(o, c) - .5,
                         "close": c, "volume": rng.uniform(1e5, 2e5, n)},
                        index=pd.date_range("2020-01-01", periods=n, freq="D"))


def test_no_lookahead():
    df = _synthetic()
    full = vzones.compute(df)
    part = vzones.compute(df.iloc[:400])
    cols = ["poc", "vah", "val", "pool_break", "hunt", "rejection", "weak_volume"]
    pd.testing.assert_frame_equal(full[cols].iloc[:400], part[cols], check_dtype=False)


def test_weak_pool_then_break_detected():
    df = _synthetic(400)
    # quiet tight pool then a high-volume breakout
    df.iloc[300:310, df.columns.get_loc("volume")] = 2e4
    base = df["close"].iat[299]
    for k in ["open", "high", "low", "close"]:
        df.iloc[300:310, df.columns.get_loc(k)] = base + {"high": .2, "low": -.2}.get(k, 0)
    df.iloc[310, :] = [base, base + 5, base, base + 4.5, 5e5]
    r = vzones.compute(df)
    assert r["pool_active"].iloc[303:310].any()
    assert r["pool_break"].iat[310] == 1


def test_backtest_runs_on_bundled_data():
    df = vzones.load_lean_csv(vzones.data.DATA_DIR / "qqq_daily_lean.csv.gz")
    assert df.close.between(10, 1000).all()
    tr = run(df.iloc[-1500:], signals=("rejection",))
    s = stats(tr)
    assert s["trades"] > 0 and 0 <= s["win_rate"] <= 1
    assert set(vzones.indicator.latest_state(vzones.compute(df.iloc[-300:])))>={"poc","hunt","weak_volume"}
