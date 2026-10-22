"""Do trendline breaks point the right way? Share of breaks where the close 8 / 26 bars later moved in the break's
direction, original lines (k=2, latest pair) vs heavy lines (k=5, held until broken). 7 symbols, 15m, all data.
A coin flip is ~50%; the drift of the period makes "up" slightly more likely, so up and down are shown apart."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd
from vzones.ranges import trendline_breaks
ROOT = pathlib.Path(__file__).resolve().parent.parent
SYMS = ["SPY", "QQQ", "COST", "INTU", "JNJ", "UNH", "HOOD"]
for k, hold in ((2, False), (5, True)):
    for hz in (8, 26):
        res = {1: [], -1: []}
        base = {1: [], -1: []}
        for s in SYMS:
            d = pd.read_csv(ROOT / f"data/intraday/{s}_15m.csv")
            c = d["close"].to_numpy(float); b = trendline_breaks(d, k=k, hold=hold)
            fwd = np.r_[c[hz:] - c[:-hz], np.full(hz, np.nan)]
            for sgn in (1, -1):
                idx = np.where(b == sgn)[0]; idx = idx[~np.isnan(fwd[idx])]
                res[sgn] += list(np.sign(fwd[idx]) == sgn)
                ok = ~np.isnan(fwd)
                base[sgn] += list(np.sign(fwd[ok]) == sgn)
        print(f"k={k} hold={hold} +{hz} bars: up breaks {np.mean(res[1])*100:.1f}% (n={len(res[1])}, base {np.mean(base[1])*100:.1f}%)"
              f" | down breaks {np.mean(res[-1])*100:.1f}% (n={len(res[-1])}, base {np.mean(base[-1])*100:.1f}%)")
