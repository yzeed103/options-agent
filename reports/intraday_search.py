"""Full 5m/15m strategy search. Needs data in data/intraday/ (see README there)."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import pandas as pd
from vzones.intraday.data import load_csv, rth
from vzones.intraday.features import add_features
from vzones.intraday.signals import SETUPS
from vzones.intraday.engine import Exec, run, metrics
from vzones.intraday.validate import walk_forward, holdout_split, permutation_test

D = pathlib.Path(__file__).resolve().parent.parent / "data" / "intraday"
files = sorted(D.glob("*_*m.csv"))
if not files:
    sys.exit("No intraday data in data/intraday/. See data/intraday/README.md.")
GRIDS = {"orb": {"rvol_min": [0.8, 1.0, 1.3], "last_entry_min": [60, 120]},
         "va_reentry": {},
         "vwap_reclaim": {"trend": [True, False]}}
EXEC = {"stop_atr": [0.75, 1.0, 1.5], "target_atr": [2.5, 3.5, 5.0], "trail_atr": [None, 2.0], "partial_r": [None, 1.0],
        "cost": [0.0001]}
rows = []
for f in files:
    d = add_features(rth(load_csv(f)))
    dev, hold = holdout_split(d)
    for name, fn in SETUPS.items():
        tr, chosen, n = walk_forward(dev, fn, GRIDS[name], EXEC)
        weeks = (dev.index[-1] - dev.index[0]).days / 7
        rows.append(dict(file=f.name, setup=name, configs_tested=n, **metrics(tr, weeks)))
res = pd.DataFrame(rows)
(pathlib.Path(__file__).resolve().parent / "intraday_search.csv").write_text(res.to_csv(index=False))
print(res.to_string(index=False))
print("\nHold-out has NOT been touched. Freeze rules first, then evaluate them once on the hold-out.")
