"""Pre-registered test: rules fixed in earlier runs (before this data existed) applied UNCHANGED to the unseen
period 2025-04-01 .. 2026-04-10 on 15m SPY and QQQ. No parameter is chosen here."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import pandas as pd
from vzones.intraday.data import load_csv, rth
from vzones.intraday.features import add_features
from vzones.intraday.signals import SETUPS, apply_filters
from vzones.intraday.engine import Exec, run, metrics
D = pathlib.Path(__file__).resolve().parent.parent / "data" / "intraday"
CUT = "2026-04-11"   # earlier searches only saw data from 2026-04-13 onward
RULES = [("ORB first 2h, RVOL>=1.2, stop 0.75, trail 2 ATR (best cross-symbol idea)", "orb", dict(trend="any", window="first2h", rvol_min=1.2), dict(stop_atr=0.75, target="atr", target_atr=10.0, trail_atr=2.0)),
         ("ORB first 2h, RVOL>=1.2, stop 0.75, target 6 ATR", "orb", dict(trend="any", window="first2h", rvol_min=1.2), dict(stop_atr=0.75, target="atr", target_atr=6.0)),
         ("POC reclaim with trend, stop 0.75, trail 2 ATR (SPY frozen 15m)", "poc_reclaim", dict(trend="with", window="all", rvol_min=0.0), dict(stop_atr=0.75, target="atr", target_atr=10.0, trail_atr=2.0)),
         ("VWAP reclaim, first 2h, stop 0.75, trail 2 ATR (QQQ frozen 15m)", "vwap_reclaim", dict(trend="any", window="first2h", rvol_min=0.0), dict(stop_atr=0.75, target="atr", target_atr=10.0, trail_atr=2.0))]
rows = []
for sym in ("SPY", "QQQ"):
    d = add_features(rth(load_csv(D / f"{sym}_15m.csv")))
    u = d[d.index < pd.Timestamp(CUT, tz="America/New_York")]
    wk = (u.index[-1] - u.index[0]).days / 7
    for name, setup, filt, ex in RULES:
        for cmult in (1, 2):
            sig = apply_filters(u, SETUPS[setup](u), **filt)
            m = metrics(run(u, sig, Exec(**ex, cost=0.0001 * cmult)), wk)
            rows.append(dict(symbol=sym, rule=name, cost=f"{cmult}x", **{k: m.get(k) for k in ("trades", "per_week", "win_rate", "pf", "expectancy_r", "avg_win_r", "avg_loss_r", "max_dd_r", "total_r")}))
res = pd.DataFrame(rows); pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 70)
print(f"Unseen period: {u.index[0].date()} .. {u.index[-1].date()} ({u.session.nunique()} sessions)\n")
print(res.to_string(index=False))
res.to_csv(pathlib.Path(__file__).resolve().parent / "intraday_unseen_test.csv", index=False)
