"""Trend-volume events (reports/trend_volume/PREREG.md): no look-ahead in detection, event rules, first passage."""
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from vzones import trend_volume as TV  # noqa: E402
import trend_volume_eval as E  # noqa: E402


def test_detection_uses_past_only():
    d, _ = E.synth(11, True, sessions=40)
    F, ev, clx = TV.detect(d, 5)
    k = 2000
    F2, ev2, _ = TV.detect(d.iloc[:k], 5)
    a = ev[ev["t"] < k - 1].reset_index(drop=True); b = ev2[ev2["t"] < k - 1].reset_index(drop=True)
    assert len(a) == len(b) and np.allclose(a["P"].fillna(-9), b["P"].fillna(-9))


def test_event_rules():
    d, _ = E.synth(12, True, sessions=60)
    F, ev, clx = TV.detect(d, 5)
    assert len(ev) > 20
    assert (ev["leg_len"] >= TV.MIN_LEG).all() and (ev["pull_len"] >= 2).all() and (ev["pull_len"] <= TV.MAX_PULL).all()
    # the resumption close is beyond the leg's extreme in the trend direction
    c = F["c"]
    for t, dr, ls, ps in zip(ev["t"], ev["dir"], ev["leg_start"], ev["pull_start"]):
        ext = F["h"][ls:ps].max() if dr > 0 else F["l"][ls:ps].min()
        assert dr * (c[t] - ext) > 0
    if len(clx):
        assert (clx["leg_len"] >= 8).all()


def test_first_passage_and_planted_direction():
    c = np.r_[np.full(10, 100.0), 100 + np.arange(1, 30) * 0.2]       # a clean ramp after bar 9
    h = c + 0.05; l = c - 0.05; A = np.full(len(c), 1.0); sess = np.zeros(len(c), int)
    fp, k = TV.first_passage(h, l, c, A, sess, 9, 1)
    assert fp == 1.0 and k == 5                                         # +1 ATR reached on the 5th bar
    fp, k = TV.first_passage(h, l, c, A, sess, 9, -1)
    assert fp == -1.0                                                   # against a down "trend" it is the stop
    assert np.isnan(TV.first_passage(h, l, c, A, sess, 30, 1)[0])       # not enough bars left
