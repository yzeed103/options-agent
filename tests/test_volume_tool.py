"""Volume tools (reports/volume_tool/PREREG.md): no look-ahead, slot normalization, hazard fit, clean IC on iid data."""
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from vzones import volume_tool as VT  # noqa: E402
import volume_tool_eval as E  # noqa: E402


def test_no_lookahead_every_tool():
    d, _ = E.synth(5, True, sessions=60)
    T = VT.tools(d, 5)
    for k in (2000, 4000):
        T2 = VT.tools(d.iloc[:k], 5)
        for name in T:
            assert np.allclose(T[name][:k], T2[name], equal_nan=True), name


def test_slot_normalization_removes_u_shape():
    d, _ = E.synth(6, False, sessions=80)
    rvol = VT.tools(d, 5)["RVOL"]
    slot = np.tile(np.arange(78), 80)
    ok = np.isfinite(rvol)
    raw = d["volume"].to_numpy()
    assert np.mean(raw[slot < 5]) > 1.5 * np.mean(raw[(slot > 35) & (slot < 43)])          # the raw profile is U-shaped
    assert abs(np.mean(rvol[ok & (slot < 5)]) - np.mean(rvol[ok & (slot > 35) & (slot < 43)])) < 0.15   # RVOL is flat


def test_hazard_recovers_planted_constant():
    d, strong = E.synth(7, True, sessions=150)
    sess, _ = VT.sessions_slots(d.index, 5)
    run = VT.runs(strong, sess)                      # the true regime, no estimator noise
    h, cnt = VT.hazard(run, sess)
    assert np.all(np.abs(h[1:6] - 0.35) < 0.06)
    ps = VT.persistence_score(run, h)
    assert 1.0 < ps[run == 1][0] < 3.0                # expected remaining strong bars ~ (1 - h) / h = 1.86


def test_pooled_ic_clean_on_iid_and_targets_future_only():
    d, _ = E.synth(8, False, sessions=120)
    T = VT.tools(d, 5); Y = VT.targets(d, 5)
    sess, _ = VT.sessions_slots(d.index, 5)
    B = np.array([str(s) for s in sess]); S = np.array(["x"] * len(sess))
    ic = VT.ic_pooled(T["range/ATR"], Y["T2"], B, S)
    assert abs(ic[0]) < 0.02
    d2 = d.copy(); d2.iloc[:500, d2.columns.get_loc("volume")] *= 3          # the past must not change a target
    Y2 = VT.targets(d2, 5)
    assert np.allclose(Y["T1_6"], Y2["T1_6"], equal_nan=True)
