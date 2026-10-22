"""Wide grid of relaxed HUNT variants. Selection on TRAIN only, then read TEST."""
import sys, pathlib, itertools; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import pandas as pd, numpy as np, vzones
from vzones.research import signals, backtest, recall, summarize
D = pathlib.Path(__file__).resolve().parent.parent / "data"
SETS = {"SPY 1h": (D / "spy_hourly_lean.csv.gz", vzones.VZParams(lookback=120, weak_ratio=0.8, break_ratio=1.5, adx_strong=25, step=4)),
        "SPY 1d": (D / "spy_daily_lean.csv.gz", vzones.VZParams(lookback=120, weak_ratio=0.8, break_ratio=1.3, adx_strong=20)),
        "QQQ 1d": (D / "qqq_daily_lean.csv.gz", vzones.VZParams(lookback=120, weak_ratio=0.8, break_ratio=1.3, adx_strong=20))}
GRID = dict(trigger=["pool", "range"], filt=["adx25", "adx_rising", "ema_only"], br=[1.0, 1.2, 1.5],
            rng_n=[5, 10, 20], tight=[4.0, None], fallback=[None, 2.0])
rows = []
for name, (path, P) in SETS.items():
    r = vzones.compute(vzones.load_lean_csv(path), P); sp = int(len(r) * .6)
    for part, rr in (("train", r.iloc[:sp]), ("test", r.iloc[sp:])):
        yrs = (rr.index[-1] - rr.index[0]).days / 365.25
        for trig, f, br, n, tight, fb in itertools.product(*GRID.values()):
            if trig == "pool" and (n != 10 or tight is not None):
                continue
            s = signals(rr, trig, f, br=br, rng_n=n, rng_max_atr=tight, fallback_atr=fb)
            rows.append(dict(data=name, part=part, trigger=trig, filt=f, br=br, rng_n=n, tight=tight, fallback=fb,
                             recall=round(recall(rr, s), 3), **summarize(backtest(rr, s), yrs)))
res = pd.DataFrame(rows); res.to_csv(pathlib.Path(__file__).resolve().parent / "hunt_research2.csv", index=False)
key = ["trigger", "filt", "br", "rng_n", "tight", "fallback"]
w = res.pivot_table(index=key, columns=["data", "part"], values=["per_year", "pf", "avg_r", "recall"], dropna=False)
# robust score: pass on ALL three TRAIN sets (pf>1.1), rank by min train signals/year
tr = res[res.part == "train"].groupby(key, dropna=False).agg(pf_min=("pf", "min"), n_min=("per_year", "min"), rec=("recall", "mean")).reset_index()
cand = tr[(tr.pf_min > 1.1)].sort_values(["n_min"], ascending=False).head(12)
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40)
print("TOP candidates chosen on TRAIN (pf>1.1 on all 3 sets):\n", cand.to_string(index=False))
te = res[res.part == "test"]
print("\nTEST results for those candidates:")
for _, c in cand.iterrows():
    m = te
    for k in key:
        m = m[(m[k].isna()) if pd.isna(c[k]) else (m[k] == c[k])]
    print(dict(c[key]), "\n", m[["data", "per_year", "win", "pf", "avg_r", "recall", "total_pct"]].to_string(index=False))
