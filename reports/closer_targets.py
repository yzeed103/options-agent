"""Closer targets + new VA re-entry signal + ADX 20. Same exit engine for all; select nothing on test."""
import sys, pathlib, itertools; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import pandas as pd, numpy as np, vzones
from vzones.research import signals, backtest, summarize
pd.set_option("display.width", 250)
D = pathlib.Path(__file__).resolve().parent.parent / "data"
SETS = {"SPY 1h": ("spy_hourly_lean.csv.gz", dict(lookback=120, weak_ratio=0.8, break_ratio=1.5, adx_strong=25, step=4)),
        "SPY 1d": ("spy_daily_lean.csv.gz", dict(lookback=120, weak_ratio=0.8, break_ratio=1.3, adx_strong=20)),
        "QQQ 1d": ("qqq_daily_lean.csv.gz", dict(lookback=120, weak_ratio=0.8, break_ratio=1.3, adx_strong=20))}
VAR = [("HUNT now", "pool", "adx25", 25, None),
       ("HUNT target<=2ATR", "pool", "adx25", 25, 2.0),
       ("HUNT target<=1.5ATR", "pool", "adx25", 25, 1.5),
       ("HUNT ADX20 target<=2ATR", "pool", "adx25", 20, 2.0),
       ("HUNT ADX20 target<=1.5ATR", "pool", "adx25", 20, 1.5),
       ("VA re-entry, no filter", "va_reentry", "none", 0, None),
       ("VA re-entry target<=2ATR", "va_reentry", "none", 0, 2.0),
       ("VA re-entry + EMA trend", "va_reentry", "ema_only", 0, None)]
rows = []
for name, (f, P) in SETS.items():
    r = vzones.compute(vzones.load_lean_csv(D / f), vzones.VZParams(**P)); sp = int(len(r) * .6)
    for part, rr in (("train", r.iloc[:sp]), ("test", r.iloc[sp:])):
        yrs = (rr.index[-1] - rr.index[0]).days / 365.25
        for lab, trig, filt, adxm, cap in VAR:
            for stop in (1.0, 1.5):
                s = signals(rr, trig, filt, br=P["break_ratio"], cap_atr=cap, adx_min=adxm, min_atr=0.5)
                tr = backtest(rr, s, stop_atr=stop)
                dist = (s.target - rr.close).abs() / rr.atr
                rows.append(dict(data=name, part=part, variant=lab, stop=stop, avg_target_atr=round(dist[s.sig != 0].mean(), 2),
                                 **summarize(tr, yrs)))
res = pd.DataFrame(rows); res.to_csv(pathlib.Path(__file__).resolve().parent / "closer_targets.csv", index=False)
cols = ["per_year", "avg_target_atr", "win", "pf", "avg_r"]
w = res.pivot_table(index=["variant", "stop"], columns=["data", "part"], values=["pf"]).round(2)
print("PROFIT FACTOR by data/part\n", w.to_string())
print("\nSIGNALS PER YEAR\n", res.pivot_table(index=["variant", "stop"], columns=["data", "part"], values="per_year").round(1).to_string())
print("\nAVG TARGET DISTANCE (ATR)\n", res.pivot_table(index=["variant", "stop"], columns=["data", "part"], values="avg_target_atr").round(2).to_string())
print("\nWIN RATE\n", res.pivot_table(index=["variant", "stop"], columns=["data", "part"], values="win").round(2).to_string())
