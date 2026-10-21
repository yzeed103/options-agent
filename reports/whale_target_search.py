"""Search an entry that catches price BEFORE it reaches the next whale level (target = nearest whale level ahead).
Stocks only: COST, INTU, JNJ, UNH, HOOD (15m, 2025-04-01 .. 2026-10-21).
Choose on the first 60% of sessions (pooled, must be positive on >= 4/5 stocks), freeze top 3, test once on the last 40%."""
import sys, pathlib, itertools; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd
from vzones.intraday.data import load_csv, rth
from vzones.intraday.features import add_features
from vzones.intraday.signals import SETUPS, apply_filters
from vzones.intraday.engine import Exec, run
from vzones.intraday.whale_features import add_whale_levels, whale_bounce, K
OUT = pathlib.Path(__file__).resolve().parent; D = OUT.parent / "data" / "intraday"
STOCKS = ["COST", "INTU", "JNJ", "UNH", "HOOD"]; COST = 0.0001
LV = tuple(f"wl_{k}" for k in range(K))
data = {s: add_whale_levels(add_features(rth(load_csv(D / f"{s}_15m.csv")))) for s in STOCKS}
setups = dict(SETUPS); setups["whale_bounce"] = whale_bounce
FILTERS = [dict(trend=t, window=w, rvol_min=r) for t in ("any", "with") for w in ("all", "first2h") for r in (0.0, 1.2)]
EXECS = [dict(stop_atr=st, target="levels", level_cols=LV, min_target_r=mr, overnight=on, max_bars=26 * 5 if on else None)
         for st in (0.75, 1.0, 1.5) for mr in (1.5, 2.0, 3.0) for on in (False, True)]
sess = sorted(set().union(*[set(d.session.unique()) for d in data.values()])); cut = sess[int(len(sess) * .6)]
dev = {s: d[d.session < cut] for s, d in data.items()}; test = {s: d[d.session >= cut] for s, d in data.items()}
print("coverage: share of bars with >=1 active whale level:", {s: round(d.wl_0.notna().mean(), 2) for s, d in data.items()})
print(f"dev {sess[0]}..{sess[int(len(sess)*.6)-1]}  test {cut}..{sess[-1]}")


def pool(per):
    p = pd.concat([x for x in per if len(x)]) if any(len(x) for x in per) else pd.DataFrame(columns=["r"])
    w, l = p.r[p.r > 0].sum(), -p.r[p.r <= 0].sum()
    return p, (w / l if l > 0 else np.inf)


rows = []
for sname, fn in setups.items():
    base = {s: fn(dev[s]) for s in STOCKS}
    for fi, f in enumerate(FILTERS):
        sig = {s: apply_filters(dev[s], base[s], **f) for s in STOCKS}
        for ei, e in enumerate(EXECS):
            per = [run(dev[s], sig[s], Exec(**e, cost=COST)) for s in STOCKS]
            p, pf = pool(per)
            if len(p) == 0: continue
            rows.append(dict(setup=sname, fi=fi, ei=ei, **f, stop=e["stop_atr"], min_r=e["min_target_r"], overnight=e["overnight"],
                             trades=len(p), pf=pf, exp_r=p.r.mean(), win=(p.r > 0).mean(), avg_win=p.r[p.r > 0].mean(),
                             pos_stocks=sum((x.r.mean() > 0) for x in per if len(x)), hit_target=None))
G = pd.DataFrame(rows); G.to_csv(OUT / "whale_target_grid.csv", index=False)
wk = (pd.Timestamp(cut) - pd.Timestamp(sess[0])).days / 7
G["per_week_per_stock"] = G.trades / wk / len(STOCKS)
elig = G[(G.pos_stocks >= 4) & (G.per_week_per_stock >= 0.5) & (G.trades >= 60)].sort_values("exp_r", ascending=False)
pd.set_option("display.width", 230)
print(f"configs tested: {len(G)}   eligible: {len(elig)}")
print(elig.head(10)[["setup", "trend", "window", "rvol_min", "stop", "min_r", "overnight", "trades", "per_week_per_stock", "win", "pf", "exp_r", "avg_win", "pos_stocks"]].round(3).to_string(index=False))
print("\nFROZEN TOP 3 -> TEST (once)")
res = []
for _, c in elig.head(3).iterrows():
    f, e = FILTERS[int(c.fi)], EXECS[int(c.ei)]
    for m in (1, 2):
        per = {s: run(test[s], apply_filters(test[s], setups[c.setup](test[s]), **f), Exec(**e, cost=COST * m)) for s in STOCKS}
        p, pf = pool(per.values())
        res.append(dict(rule=f"{c.setup} | {f['trend']} {f['window']} rvol{f['rvol_min']} | stop {e['stop_atr']} | target >= {e['min_target_r']}R | overnight {e['overnight']}",
                        cost=f"{m}x", trades=len(p), win=round((p.r > 0).mean(), 3), pf=round(pf, 2), exp_r=round(p.r.mean(), 3),
                        avg_win=round(p.r[p.r > 0].mean(), 2), **{s: round(per[s].r.mean(), 2) if len(per[s]) else None for s in STOCKS}))
R = pd.DataFrame(res); R.to_csv(OUT / "whale_target_test.csv", index=False); print(R.to_string(index=False))
