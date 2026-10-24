"""The constants the indicator needs for the shipped (price-only) components, from TRAIN days only:
S0 quintile edges per direction, P(alive12 | dir, S0 quintile), E0 tercile edges, P(hold | E0 tercile, dir),
inertia p20 (exhausted flag), false-break rates by flag set. Writes reports/trend_volume_model/ship.json."""
from __future__ import annotations

import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
os.environ.setdefault("VZ_TAG", "sip")
import trend_volume_model_eval as ME  # noqa: E402
import volume_tool_eval as E  # noqa: E402

OUT = ME.OUT


def main():
    from vzones.assistant import data as D
    syms = sorted(f[:-7] for f in os.listdir(D.BARS) if f.endswith("_5m.csv"))
    F = {s: E.frames(s) for s in syms}
    days = sorted(set().union(*[set(F[s][390].index.date) for s in syms]))
    cut = days[int(0.6 * len(days))]
    T, C, B = ME.collect([(s, F[s][5]) for s in syms], 5, True, cut)
    tr = T["train"].to_numpy(bool); trB = B["train"].to_numpy(bool)
    q = np.nanpercentile(T["S0"][tr], [20, 40, 60, 80]); T["q"] = np.searchsorted(q, T["S0"])
    alive = {}
    for dr in (1, -1):
        for k in range(5):
            m = tr & (T["dir"] == dr) & (T["q"] == k) & np.isfinite(T["alive12"])
            alive[f"{dr}|{k}"] = [round(float(T["alive12"][m].mean()), 3), int(m.sum())]
    e3 = np.nanpercentile(B["E0"][trB], [33.3, 66.7]); B["e"] = np.searchsorted(e3, B["E0"])
    hold = {}
    for dr in (1, -1):
        for k in range(3):
            m = trB & (B["dir"] == dr) & (B["e"] == k) & np.isfinite(B["hold"])
            hold[f"{k}|{dr}"] = [round(float(B["hold"][m].mean()), 3), int(m.sum())]
    ip20 = float(np.nanpercentile(B["I"][trB], 20))
    B["exh"] = B["I"] < ip20
    flags = {}
    for name, m in (("none", ~B["absorption"] & ~B["wick"] & ~B["exh"]), ("absorption", B["absorption"]), ("wick", B["wick"]), ("exhausted", B["exh"]), ("any", B["absorption"] | B["wick"] | B["exh"])):
        mm = trB & m.to_numpy() & np.isfinite(B["false"])
        flags[name] = [round(float(B["false"][mm].mean()), 3), int(mm.sum())]
    ship = dict(train_end_before=str(cut), S0_edges=[round(float(x), 4) for x in q], alive12_by_dir_q=alive, E0_edges=[round(float(x), 4) for x in e3], hold_by_e_dir=hold,
                I_p20=round(ip20, 4), false_by_flag=flags, base=dict(alive12=round(float(T["alive12"][tr].mean()), 3), hold=round(float(B["hold"][trB].mean()), 3), false=round(float(B["false"][trB].mean()), 3)))
    json.dump(ship, open(os.path.join(OUT, "ship.json"), "w"), indent=1)
    print(json.dumps(ship, indent=1))


if __name__ == "__main__":
    main()
