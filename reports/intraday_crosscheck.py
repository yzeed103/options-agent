"""Apply the rules frozen on SPY (and the SPY near-miss) to QQQ, a symbol never used in the SPY search."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from vzones.intraday.data import load_csv, rth, resample
from vzones.intraday.features import add_features
from vzones.intraday.signals import SETUPS, apply_filters
from vzones.intraday.engine import Exec, run, metrics
D = pathlib.Path(__file__).resolve().parent.parent / "data" / "intraday"
RULES = [("SPY frozen 5m: IB break, first 2h, stop 1 ATR, target 6 ATR", 5, "ib_break", dict(trend="any", window="first2h", rvol_min=0.0), dict(stop_atr=1.0, target="atr", target_atr=6.0)),
         ("SPY frozen 15m: POC reclaim with trend, stop 0.75 ATR, trail 2 ATR", 15, "poc_reclaim", dict(trend="with", window="all", rvol_min=0.0), dict(stop_atr=0.75, target="atr", target_atr=10.0, trail_atr=2.0)),
         ("SPY near-miss 15m: ORB first 2h, RVOL>=1.2, stop 0.75, target 6 ATR", 15, "orb", dict(trend="any", window="first2h", rvol_min=1.2), dict(stop_atr=0.75, target="atr", target_atr=6.0)),
         ("SPY near-miss 15m: ORB first 2h, RVOL>=1.2, stop 0.75, trail 2 ATR", 15, "orb", dict(trend="any", window="first2h", rvol_min=1.2), dict(stop_atr=0.75, target="atr", target_atr=10.0, trail_atr=2.0))]
for sym in ("QQQ", "SPY"):
    raw = rth(load_csv(D / f"{sym}_5m.csv"))
    for name, tf, setup, filt, ex in RULES:
        d = add_features(raw if tf == 5 else resample(raw, tf)); wk = (d.index[-1] - d.index[0]).days / 7
        sig = apply_filters(d, SETUPS[setup](d), **filt)
        print(sym, "|", name, "|", {k: v for k, v in metrics(run(d, sig, Exec(**ex, cost=0.0001)), wk).items() if k in ("trades", "per_week", "win_rate", "pf", "expectancy_r", "avg_win_r", "max_dd_r")})
