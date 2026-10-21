"""Multi-symbol 15m test (SPY, QQQ, COST, INTU, JNJ, UNH, HOOD), 2025-04-01 .. 2026-10-21.
A) pre-registered rules unchanged on the 5 new stocks.
B) pooled search: choose on the first 60% of sessions (all 7 symbols), require the rule to work on most
   symbols, freeze the top 3, evaluate once on the last 40%."""
import sys, pathlib, json; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd
from vzones.intraday.data import load_csv, rth
from vzones.intraday.features import add_features
from vzones.intraday.signals import SETUPS, apply_filters
from vzones.intraday.engine import Exec, run, metrics
OUT = pathlib.Path(__file__).resolve().parent; D = OUT.parent / "data" / "intraday"
SYMS = ["SPY", "QQQ", "COST", "INTU", "JNJ", "UNH", "HOOD"]
COST = 0.0001
data = {s: add_features(rth(load_csv(D / f"{s}_15m.csv"))) for s in SYMS}
pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 60)

print("=== A) pre-registered rules on the 5 new stocks (full period, unchanged)")
RULES = [("ORB 2h RVOL1.2 trail2", "orb", dict(trend="any", window="first2h", rvol_min=1.2), dict(stop_atr=0.75, target="atr", target_atr=10.0, trail_atr=2.0)),
         ("ORB 2h RVOL1.2 tgt6", "orb", dict(trend="any", window="first2h", rvol_min=1.2), dict(stop_atr=0.75, target="atr", target_atr=6.0)),
         ("POC reclaim trend trail2", "poc_reclaim", dict(trend="with", window="all", rvol_min=0.0), dict(stop_atr=0.75, target="atr", target_atr=10.0, trail_atr=2.0)),
         ("VWAP reclaim 2h trail2", "vwap_reclaim", dict(trend="any", window="first2h", rvol_min=0.0), dict(stop_atr=0.75, target="atr", target_atr=10.0, trail_atr=2.0))]
ra = []
for s in SYMS[2:]:
    d = data[s]; wk = (d.index[-1] - d.index[0]).days / 7
    for name, st, f, e in RULES:
        m = metrics(run(d, apply_filters(d, SETUPS[st](d), **f), Exec(**e, cost=COST)), wk)
        ra.append(dict(symbol=s, rule=name, trades=m.get("trades"), per_week=m.get("per_week"), pf=m.get("pf"), exp_r=m.get("expectancy_r")))
ra = pd.DataFrame(ra); print(ra.pivot_table(index="rule", columns="symbol", values="pf").round(2).to_string())

print("\n=== B) pooled search")
FILTERS = [dict(trend=t, window=w, rvol_min=r) for t in ("any", "with") for w in ("all", "first2h", "after11") for r in (0.0, 1.2)]
EXECS = []
for st in (0.75, 1.0, 1.5):
    for k in (2.5, 4.0, 6.0): EXECS.append(dict(stop_atr=st, target="atr", target_atr=k))
    for mr in (2.0, 3.0): EXECS.append(dict(stop_atr=st, target="levels", min_target_r=mr))
    for tr in (2.0, 3.0): EXECS.append(dict(stop_atr=st, target="atr", target_atr=10.0, trail_atr=tr))
    EXECS.append(dict(stop_atr=st, target="atr", target_atr=4.0, partial_r=1.0, partial_frac=0.5))
sess = sorted(set().union(*[set(d.session.unique()) for d in data.values()]))
cut = sess[int(len(sess) * 0.6)]
dev = {s: d[d.session < cut] for s, d in data.items()}; test = {s: d[d.session >= cut] for s, d in data.items()}
print(f"dev: {sess[0]} .. {sess[int(len(sess)*0.6)-1]}   test: {cut} .. {sess[-1]}")
rows = []
for sname, fn in SETUPS.items():
    bases = {s: fn(dev[s]) for s in SYMS}
    for fi, f in enumerate(FILTERS):
        sigs = {s: apply_filters(dev[s], bases[s], **f) for s in SYMS}
        for ei, e in enumerate(EXECS):
            per = [run(dev[s], sigs[s], Exec(**e, cost=COST)) for s in SYMS]
            exps = [p.r.mean() if len(p) else np.nan for p in per]
            pooled = pd.concat(per) if any(len(p) for p in per) else pd.DataFrame()
            if pooled.empty: continue
            w, l = pooled.r[pooled.r > 0].sum(), -pooled.r[pooled.r <= 0].sum()
            rows.append(dict(setup=sname, fi=fi, ei=ei, **f, **{f"x_{k}": v for k, v in e.items()}, trades=len(pooled),
                             pf=w / l if l > 0 else np.inf, exp_r=pooled.r.mean(), avg_win=pooled.r[pooled.r > 0].mean(),
                             pos_symbols=int(np.nansum(np.array(exps) > 0)), median_sym_exp=np.nanmedian(exps)))
G = pd.DataFrame(rows); G.to_csv(OUT / "multi_symbol_grid.csv", index=False)
dev_weeks = (pd.Timestamp(cut) - pd.Timestamp(sess[0])).days / 7
G["per_week_per_symbol"] = G.trades / dev_weeks / len(SYMS)
elig = G[(G.pos_symbols >= 5) & (G.per_week_per_symbol >= 1.0) & (G.avg_win >= 2.0)].sort_values("median_sym_exp", ascending=False)
print(f"configs tested: {len(G)} | eligible (>=5/7 symbols positive, >=1 trade/week/symbol, avg win>=2R): {len(elig)}")
cols = ["setup", "trend", "window", "rvol_min", "x_stop_atr", "x_target", "x_target_atr", "x_min_target_r", "x_trail_atr", "x_partial_r", "trades", "per_week_per_symbol", "pf", "exp_r", "avg_win", "pos_symbols", "median_sym_exp"]
print(elig.head(10)[cols].round(3).to_string(index=False))
frozen = elig.head(3)
print("\n=== Frozen top 3 -> TEST period (touched once)")
res = []
for _, c in frozen.iterrows():
    f, e = FILTERS[int(c.fi)], EXECS[int(c.ei)]
    for mult in (1, 2):
        per = {s: run(test[s], apply_filters(test[s], SETUPS[c.setup](test[s]), **f), Exec(**e, cost=COST * mult)) for s in SYMS}
        pooled = pd.concat(per.values())
        w, l = pooled.r[pooled.r > 0].sum(), -pooled.r[pooled.r <= 0].sum()
        row = dict(rule=f"{c.setup} {f['trend']} {f['window']} rvol{f['rvol_min']} stop{e['stop_atr']} {e['target']} {e.get('target_atr', '')} trail{e.get('trail_atr', '-')} minR{e.get('min_target_r', '-')} part{e.get('partial_r', '-')}",
                   cost=f"{mult}x", trades=len(pooled), pooled_pf=round(w / l, 2) if l > 0 else np.inf, pooled_exp_r=round(pooled.r.mean(), 3),
                   avg_win=round(pooled.r[pooled.r > 0].mean(), 2), win=round((pooled.r > 0).mean(), 3),
                   **{s: round(per[s].r.mean(), 2) if len(per[s]) else None for s in SYMS})
        res.append(row)
R = pd.DataFrame(res); print(R.to_string(index=False)); R.to_csv(OUT / "multi_symbol_test.csv", index=False)
print("\n(per-symbol columns = expectancy in R per trade on the test period)")
