"""Walk-forward runner, hold-out split and a within-day permutation test."""
from __future__ import annotations
import itertools, numpy as np, pandas as pd
from .engine import Exec, run, metrics


def holdout_split(d: pd.DataFrame, frac: float = 0.2):
    days = sorted(d.session.unique()); cut = days[int(len(days) * (1 - frac))]
    return d[d.session < cut], d[d.session >= cut]


def walk_forward(d: pd.DataFrame, make_signal, grid: dict, exec_grid: dict, train_months: int = 12, test_months: int = 3,
                 score: str = "expectancy_r", min_trades: int = 30):
    """Optimise on each train window, apply the best config to the next test window, stitch test trades."""
    t0, t1 = d.index[0], d.index[-1]; start = t0; all_tr, chosen = [], []
    combos = [dict(zip(grid, v)) for v in itertools.product(*grid.values())]
    ecombos = [dict(zip(exec_grid, v)) for v in itertools.product(*exec_grid.values())]
    n_tested = len(combos) * len(ecombos)
    while True:
        tr_end = start + pd.DateOffset(months=train_months); te_end = tr_end + pd.DateOffset(months=test_months)
        if tr_end >= t1: break
        train, test = d[(d.index >= start) & (d.index < tr_end)], d[(d.index >= tr_end) & (d.index < te_end)]
        best, best_s = None, -np.inf
        for p in combos:
            sig = make_signal(train, **p)
            for ep in ecombos:
                m = metrics(run(train, sig, Exec(**ep)))
                if m.get("trades", 0) >= min_trades and m[score] > best_s:
                    best, best_s = (p, ep), m[score]
        if best is not None:
            t = run(test, make_signal(test, **best[0]), Exec(**best[1]))
            all_tr.append(t); chosen.append(dict(train_start=start, test_start=tr_end, **best[0], **best[1]))
        start = start + pd.DateOffset(months=test_months)
    trades = pd.concat(all_tr, ignore_index=True) if all_tr else pd.DataFrame()
    return trades, pd.DataFrame(chosen), n_tested


def permutation_test(d: pd.DataFrame, sig: np.ndarray, ex: Exec, n: int = 200, seed: int = 0) -> dict:
    """Shuffle signal bars within each session (keeps signals per day and direction mix)."""
    rng = np.random.default_rng(seed); real = metrics(run(d, sig, ex)).get("expectancy_r", np.nan)
    sess = d.session.to_numpy(); idx_by = pd.Series(np.arange(len(d))).groupby(sess).apply(np.array)
    better = 0
    for _ in range(n):
        ps = np.zeros_like(sig)
        for s, ix in idx_by.items():
            k = ix[sig[ix] != 0]
            if len(k): ps[rng.choice(ix, len(k), replace=False)] = sig[k]
        better += metrics(run(d, ps, ex)).get("expectancy_r", -np.inf) >= real
    return dict(real_expectancy_r=real, p_value=round((better + 1) / (n + 1), 4), permutations=n)
