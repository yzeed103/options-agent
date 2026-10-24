"""Breakout events (reports/breakout_volume/PREREG.md): past-only detection, event rules, targets."""
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from vzones import breakout_volume as BV  # noqa: E402
import breakout_volume_eval as E  # noqa: E402


def test_detection_uses_past_only():
    d, _ = E.synth(21, True, sessions=40)
    F, ev = BV.detect(d, 5, 2)
    k = 2000
    F2, ev2 = BV.detect(d.iloc[:k], 5, 2)
    a = ev[ev["t"] < k - 3].reset_index(drop=True); b = ev2[ev2["t"] < k - 3].reset_index(drop=True)
    assert len(a) == len(b) and np.allclose(a["rvol"].fillna(-9), b["rvol"].fillna(-9))


def test_break_rules():
    d, _ = E.synth(22, True, sessions=60)
    F, ev = BV.detect(d, 5, 2)
    assert len(ev) > 50
    c = F["c"]; sess = F["sess"]
    for t, dr, L, org in zip(ev["t"], ev["dir"], ev["L"], ev["origin"]):
        assert t - org >= BV.MIN_AGE and sess[t] == sess[org]
        assert dr * (c[t] - L) > 0                                    # the breaking close is beyond the level
        assert all(dr * (c[j] - L) <= 0 for j in range(org + 1, t))  # every close since the origin on the other side


def test_targets_hold_and_false_break():
    c = np.r_[np.full(20, 100.0), 101.0, 101.2, 101.4, 101.6, 101.8, 102.0, 102.2, 102.4, 102.6, 102.8, 103.0, 103.2, 103.4, 103.6]
    h = c + 0.05; l = c - 0.05; A = np.full(len(c), 1.0); sess = np.zeros(len(c), int)
    import pandas as pd
    ev = pd.DataFrame([dict(t=20, dir=1, L=100.5)])
    Y = BV.targets(dict(h=h, l=l, c=c, A=A, sess=sess), ev, 24)
    assert Y["B1"][0] == 1.0 and Y["B3"][0] == 0.0 and Y["B4"][0] > 2
    c2 = c.copy(); c2[22] = 100.0                                    # closes back across the level on the 2nd bar
    Y2 = BV.targets(dict(h=c2 + 0.05, l=c2 - 0.05, c=c2, A=A, sess=sess), ev, 24)
    assert Y2["B1"][0] == 0.0 and Y2["B3"][0] == 1.0
