"""Robustness checks for the frozen rule: whale_bounce, any trend, all day, stop 1 ATR, target = nearest whale level
>= 3R ahead, hold up to 5 sessions. Test period only (2026-03-10 .. 2026-10-21), 5 stocks."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd
from vzones.intraday.data import load_csv, rth
from vzones.intraday.features import add_features
from vzones.intraday.engine import Exec, run
from vzones.intraday.whale_features import add_whale_levels, whale_bounce, K
D = pathlib.Path(__file__).resolve().parent.parent / "data" / "intraday"
STOCKS = ["COST", "INTU", "JNJ", "UNH", "HOOD"]; CUT = "2026-03-10"
LV = tuple(f"wl_{k}" for k in range(K))
EX = dict(stop_atr=1.0, target="levels", level_cols=LV, min_target_r=3.0, overnight=True, max_bars=130, cost=0.0001)
base = {s: add_features(rth(load_csv(D / f"{s}_15m.csv"))) for s in STOCKS}


def evaluate(kind, seed=0, perm=False, rng=None):
    per = []
    for s in STOCKS:
        d = add_whale_levels(base[s], kind=kind, seed=seed)
        t = d[d.session >= pd.Timestamp(CUT).date()]
        sig = whale_bounce(t)
        if perm:
            ps = np.zeros_like(sig); sess = t.session.to_numpy()
            for day in np.unique(sess):
                ix = np.flatnonzero(sess == day); k = ix[sig[ix] != 0]
                if len(k): ps[rng.choice(ix, len(k), replace=False)] = sig[k]
            sig = ps
        tr = run(t, sig, Exec(**EX)); tr["symbol"] = s; per.append(tr)
    return pd.concat(per, ignore_index=True)


def summ(tr):
    w, l = tr.r[tr.r > 0].sum(), -tr.r[tr.r <= 0].sum()
    return dict(trades=len(tr), win=round((tr.r > 0).mean(), 3), pf=round(w / l, 2) if l else np.inf, exp_r=round(tr.r.mean(), 3))


real = evaluate("peak"); print("WHALE levels (peaks):", summ(real))
print("  longs :", summ(real[real.dir > 0]), "\n  shorts:", summ(real[real.dir < 0]))
print("  by stock:", {s: summ(g)["exp_r"] for s, g in real.groupby("symbol")})
print("THIN levels (valleys, same profiles):", summ(evaluate("valley")))
rnd = [summ(evaluate("random", seed=k))["exp_r"] for k in range(10)]
print("RANDOM levels (10 draws) expectancy R:", rnd, "mean", round(np.mean(rnd), 3))
rng = np.random.default_rng(1); pr = [evaluate("peak", perm=True, rng=rng).r.mean() for _ in range(60)]
print("PERMUTATION (signal times shuffled within the day, 60x): mean", round(np.mean(pr), 3), " p =", round((np.sum(np.array(pr) >= real.r.mean()) + 1) / 61, 3))

print("\n=== Independent check on the DEV period (2025-04-01 .. 2026-03-09); thin levels were never used there")
def evaluate_period(kind, lo, hi, seed=0):
    per = []
    for s in STOCKS:
        d = add_whale_levels(base[s], kind=kind, seed=seed)
        t = d[(d.session >= pd.Timestamp(lo).date()) & (d.session < pd.Timestamp(hi).date())]
        tr = run(t, whale_bounce(t), Exec(**EX)); tr["symbol"] = s; per.append(tr)
    return pd.concat(per, ignore_index=True)
for kind in ("peak", "valley"):
    tr = evaluate_period(kind, "2025-04-01", CUT)
    print(f"{kind:7s}", summ(tr), {s: summ(g)["exp_r"] for s, g in tr.groupby("symbol")})
rd = [summ(evaluate_period("random", "2025-04-01", CUT, seed=k))["exp_r"] for k in range(10)]
print("random  (10 draws):", rd, "mean", round(np.mean(rd), 3))
