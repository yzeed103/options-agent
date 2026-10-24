"""Structure breaks (reports/structure_break/PREREG.md): past-only levels, event rules, targets, pseudo-entries."""
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from vzones import structure_break as SB  # noqa: E402
import structure_break_eval as E  # noqa: E402


def test_levels_use_past_only():
    d, _ = E.synth(41, False, n=1500)
    F, ev = SB.levels_and_breaks(d, "D")
    k = 1000
    F2, ev2 = SB.levels_and_breaks(d.iloc[:k], "D")
    a = ev[ev["t"] < k - 25].sort_values(["t", "cls"]).reset_index(drop=True); b = ev2[ev2["t"] < k - 25].sort_values(["t", "cls"]).reset_index(drop=True)
    assert len(a) == len(b) and np.allclose(a["L"], b["L"]) and (a["cls"].to_numpy() == b["cls"].to_numpy()).all()


def test_break_rules_and_attributes():
    d, _ = E.synth(42, False, n=2500)
    F, ev = SB.levels_and_breaks(d, "D")
    sw = ev[ev["cls"].str.startswith("swing")]
    assert len(sw) > 30 and (sw["age"] >= SB.MIN_AGE).all() and (sw["depth"] <= 4).all() and (sw["touches"] >= 0).all()
    c = F["c"]
    for t, dr, L in zip(ev["t"], ev["dir"], ev["L"]):
        assert dr * (c[int(t)] - L) > 0
    don = ev[ev["cls"] == "don20"]
    h = F["h"]
    for t, dr, L in zip(don["t"], don["dir"], don["L"]):
        if dr > 0:
            assert np.isclose(L, h[int(t) - 20:int(t)].max())


def test_targets_pseudo_and_rule():
    d, _ = E.synth(43, False, n=2000)
    F, ev = SB.levels_and_breaks(d, "D")
    e = ev.iloc[0]; t, dr, L = int(e["t"]), int(e["dir"]), float(e["L"])
    r = SB.targets_at(F, t, dr, L, 10)
    assert set(r) == {"fp", "fp2", "hold", "mfe", "mae", "false"} and r["mfe"] >= 0 and r["mae"] >= 0
    brk = np.zeros(len(F["c"]), bool); brk[ev["t"].to_numpy(int)] = True
    ps = SB.pseudo_entries(len(F["c"]), t, dr, brk, np.random.default_rng(0))
    assert len(ps) > 0 and all(not brk[max(0, j - 3):j + 4].any() for j in ps)
    R, bars = SB.trend_rule(F, t, dr, np.zeros(len(F["c"]), bool), 5.0)
    assert np.isfinite(R) and bars >= 1
