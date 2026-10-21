"""Full 5m/15m strategy search on data/intraday/SPY_5m.csv (see prompts/intraday_strategy_search.md).

Pre-declared protocol:
  1. hold-out = last 20% of sessions, untouched until step 5
  2. full grid on the development part (in-sample, all configs logged)
  3. walk-forward on the development part: train 8 weeks -> test next 4 weeks, roll 4 weeks, stitch tests
  4. within-day permutation test of the walk-forward winner's signals
  5. freeze ONE config per timeframe (best walk-forward expectancy with >= 3 trades/week) -> run once on hold-out
"""
import sys, pathlib, itertools, json; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd
from vzones.intraday.data import load_csv, rth, resample
from vzones.intraday.features import add_features
from vzones.intraday.signals import SETUPS, apply_filters
from vzones.intraday.engine import Exec, run, metrics
from vzones.intraday.validate import holdout_split, permutation_test

OUT = pathlib.Path(__file__).resolve().parent
raw = rth(load_csv(OUT.parent / "data" / "intraday" / "SPY_5m.csv"))
FILTERS = [dict(trend=t, window=w, rvol_min=r) for t in ("any", "with") for w in ("all", "first2h", "after11") for r in (0.0, 1.2)]
EXECS = []
for st in (0.75, 1.0, 1.5):
    for k in (2.5, 4.0, 6.0):
        EXECS.append(dict(stop_atr=st, target="atr", target_atr=k))
    for mr in (2.0, 3.0):
        EXECS.append(dict(stop_atr=st, target="levels", min_target_r=mr))
    for tr in (2.0, 3.0):
        EXECS.append(dict(stop_atr=st, target="atr", target_atr=10.0, trail_atr=tr))
    EXECS.append(dict(stop_atr=st, target="atr", target_atr=4.0, partial_r=1.0, partial_frac=0.5))
COST = 0.0001                     # 0.01% per side = 0.02% round trip


def weeks(d): return max((d.index[-1] - d.index[0]).days / 7, 1e-9)


def grid(d, tag):
    rows, cache = [], {}
    for sname, fn in SETUPS.items():
        base = fn(d)
        for fi, f in enumerate(FILTERS):
            sig = apply_filters(d, base, **f)
            if not sig.any():
                continue
            for ei, e in enumerate(EXECS):
                m = metrics(run(d, sig, Exec(**e, cost=COST)), weeks(d))
                rows.append(dict(tf=tag, setup=sname, fi=fi, ei=ei, **f, **{f"x_{k}": v for k, v in e.items()}, **m))
    return pd.DataFrame(rows)


def walk_forward(d, tag, train_w=8, test_w=4, min_trades=12):
    sess = np.array(sorted(d.session.unique())); per_w = 5
    tr_n, te_n = train_w * per_w, test_w * per_w
    stitched, picks = [], []
    for s0 in range(0, len(sess) - tr_n - 1, te_n):
        trs, tes = sess[s0:s0 + tr_n], sess[s0 + tr_n:s0 + tr_n + te_n]
        if len(tes) == 0: break
        tr, te = d[d.session.isin(trs)], d[d.session.isin(tes)]
        best, bs = None, -np.inf
        for sname, fn in SETUPS.items():
            b_tr = fn(tr)
            for fi, f in enumerate(FILTERS):
                sg = apply_filters(tr, b_tr, **f)
                if sg.sum() == 0 and not sg.any(): continue
                for ei, e in enumerate(EXECS):
                    m = metrics(run(tr, sg, Exec(**e, cost=COST)))
                    if m.get("trades", 0) >= min_trades and m["expectancy_r"] > bs:
                        best, bs = (sname, fi, ei), m["expectancy_r"]
        if best is None: continue
        sname, fi, ei = best
        t = run(te, apply_filters(te, SETUPS[sname](te), **FILTERS[fi]), Exec(**EXECS[ei], cost=COST))
        stitched.append(t); picks.append(dict(tf=tag, train_from=str(trs[0]), test_from=str(tes[0]), test_to=str(tes[-1]),
                                              setup=sname, **FILTERS[fi], **EXECS[ei], train_expectancy=round(bs, 3),
                                              test_trades=len(t), test_r=round(t.r.sum(), 2) if len(t) else 0))
    st = pd.concat(stitched, ignore_index=True) if stitched else pd.DataFrame()
    return st, pd.DataFrame(picks)


report = {}
all_grid, all_picks = [], []
for tag, mins in (("5m", 5), ("15m", 15)):
    d = add_features(raw if mins == 5 else resample(raw, mins))
    dev, hold = holdout_split(d, 0.2)
    g = grid(dev, tag); all_grid.append(g)
    st, picks = walk_forward(dev, tag); all_picks.append(picks)
    wf_weeks = (picks.test_to.map(pd.Timestamp).max() - picks.test_from.map(pd.Timestamp).min()).days / 7 if len(picks) else 1
    wf = metrics(st, wf_weeks) if len(st) else dict(trades=0)
    # freeze ONE config for the hold-out: best in-sample dev config that also passes the activity floor
    elig = g[(g.trades >= 3 * weeks(dev)) & (g.avg_win_r >= 2.5)].sort_values("expectancy_r", ascending=False)
    frozen = elig.iloc[0] if len(elig) else g.sort_values("expectancy_r", ascending=False).iloc[0]
    f = FILTERS[int(frozen.fi)]; e = EXECS[int(frozen.ei)]
    dev_sig = apply_filters(dev, SETUPS[frozen.setup](dev), **f)
    perm = permutation_test(dev, dev_sig, Exec(**e, cost=COST), n=200)
    hold_m = metrics(run(hold, apply_filters(hold, SETUPS[frozen.setup](hold), **f), Exec(**e, cost=COST)), weeks(hold))
    hold_2x = metrics(run(hold, apply_filters(hold, SETUPS[frozen.setup](hold), **f), Exec(**e, cost=2 * COST)), weeks(hold))
    report[tag] = dict(dev_sessions=int(dev.session.nunique()), hold_sessions=int(hold.session.nunique()),
                       configs_tested=int(len(g)), walk_forward=wf,
                       frozen=dict(setup=frozen.setup, **f, **e), frozen_dev=json.loads(frozen[["trades", "per_week", "win_rate", "pf", "expectancy_r", "avg_win_r", "avg_loss_r", "max_dd_r"]].to_json()),
                       permutation_dev=perm, holdout=hold_m, holdout_2x_cost=hold_2x)
G = pd.concat(all_grid); G.to_csv(OUT / "intraday_grid.csv", index=False)
P = pd.concat(all_picks); P.to_csv(OUT / "intraday_walkforward_picks.csv", index=False)
(OUT / "intraday_search.json").write_text(json.dumps(report, indent=2, default=str))
pd.set_option("display.width", 250)
print(json.dumps(report, indent=2, default=str))
top = G[G.trades >= 30].sort_values("expectancy_r", ascending=False).head(15)
print("\nTop in-sample dev configs (>=30 trades) - NOT validated:\n", top[["tf", "setup", "trend", "window", "rvol_min", "x_stop_atr", "x_target", "x_target_atr", "x_min_target_r", "x_trail_atr", "x_partial_r", "trades", "per_week", "win_rate", "pf", "expectancy_r", "avg_win_r"]].to_string(index=False))
print("\nWalk-forward picks:\n", P.to_string(index=False))
