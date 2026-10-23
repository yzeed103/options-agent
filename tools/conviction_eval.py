"""Tests of reports/conviction_ma/PREREG.md.

    python tools/conviction_eval.py planted      # test 1 + 2 (the gate)
    python tools/conviction_eval.py tune         # grid on train (10 symbols, 5m)
    python tools/conviction_eval.py verdict      # matched-lag comparison on test, all symbols and timeframes
"""
from __future__ import annotations

import json
import os
import sys
import time

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from vzones import conviction_ma as CM  # noqa: E402

OUT = os.path.join(ROOT, "reports", "conviction_ma")
DEFAULT = dict(law="A", g=0.3, keep=0.6, p=1.0, L_fast=8, L_slow=60)


# ---------------- synthetic ----------------
def planted(seed: int, sig=0.1, drift=0.25, inject=True):
    rng = np.random.default_rng(seed)
    segs = [("side", 300), ("up", 150), ("side", 150), ("down", 150)]
    c, lab = [], []
    x = 100.0
    level = x
    for kind, n in segs:
        if kind == "side":
            level = x
        for _ in range(n):
            if kind == "side":
                x += -0.08 * (x - level) + rng.normal(0, sig)
            else:
                x += (drift if kind == "up" else -drift) * sig + rng.normal(0, sig)
            c.append(x); lab.append({"side": 0, "up": 1, "down": -1}[kind])
    c = np.array(c); lab = np.array(lab)
    up0 = 300
    inj = up0 + 75
    if inject:                                   # one strong opposite (red) candle inside the up-trend
        c[inj:] -= 0.0
        c[inj] -= 2.5 * sig
    o = np.r_[c[0], c[:-1]] + rng.normal(0, 0.1 * sig, len(c))
    h = np.maximum(o, c) + np.abs(rng.normal(0, 0.4 * sig, len(c)))
    l = np.minimum(o, c) - np.abs(rng.normal(0, 0.4 * sig, len(c)))
    return o, h, l, c, lab, {"up0": up0, "down0": 600, "inj": inj, "sig": sig}


def commit_delay(M, start, sign, hold=5, maxd=150):
    dm = np.sign(np.diff(M))
    for t in range(start, min(start + maxd, len(dm) - hold)):
        if np.all(dm[t:t + hold] == sign):
            return t - start
    return np.nan


def side_flips(M, lab):
    dm = np.sign(np.diff(M))
    side = lab[1:] == 0
    a = dm[side]
    a = a[a != 0]
    return 100 * np.sum(a[1:] != a[:-1]) / max(len(a), 1)


def run_planted(seeds=200):
    res = {}
    ha_close = lambda o, h, l, c: CM.heikin_ashi(o, h, l, c)[3]  # noqa: E731
    # the conviction MA's drift lag on the planted series (median over seeds); EMA(n) lags exactly (n-1)/2, so the
    # matched EMA length is round(2 lag + 1)
    filters = {"CMA-A": lambda o, h, l, c: CM.conviction_ma(o, h, l, c, **DEFAULT)[0],
               "CMA-B": lambda o, h, l, c: CM.conviction_ma(o, h, l, c, **{**DEFAULT, "law": "B"})[0],
               "CMA-C": lambda o, h, l, c: CM.conviction_ma(o, h, l, c, **{**DEFAULT, "law": "C"})[0],
               "StreakEMA": lambda o, h, l, c: CM.streak_ema(o, h, l, c, 8, 60)}
    target = float(np.median([CM.lag_drift(filters["CMA-A"], *planted(1000 + s)[:4]) for s in range(30)]))
    best_n = max(2, int(round(2 * target + 1)))
    filters["EMA"] = lambda o, h, l, c, n=best_n: CM.ema(ha_close(o, h, l, c), n)
    res["matched"] = {"cma_lag": target, "ema_len": best_n, "ema_lag": (best_n - 1) / 2}
    rows = []
    for s in range(seeds):
        o, h, l, c, lab, meta = planted(s)
        for name, f in filters.items():
            M = f(o, h, l, c)
            dm = np.diff(M)
            inj = meta["inj"]
            trend_step = np.nanmedian(dm[meta["up0"] + 20:inj - 2])
            rows.append(dict(seed=s, name=name, side_flips=side_flips(M, lab),
                             delay_up=commit_delay(M, meta["up0"], 1), delay_down=commit_delay(M, meta["down0"], -1),
                             dent=float((trend_step - dm[inj]) / meta["sig"]) if np.isfinite(dm[inj]) else np.nan,
                             lag=CM.lag_drift(f, o, h, l, c) if s < 30 else np.nan))
    df = pd.DataFrame(rows)
    res["table"] = df.groupby("name")[["side_flips", "delay_up", "delay_down", "dent", "lag"]].median().round(3).to_dict("index")
    # gate: CMA-A vs matched EMA, paired by seed
    a = df[df.name == "CMA-A"].set_index("seed").side_flips
    e = df[df.name == "EMA"].set_index("seed").side_flips
    rel = (e - a) / e
    rng = np.random.default_rng(0)
    bs = [rel.sample(len(rel), replace=True, random_state=int(rng.integers(1e9))).mean() for _ in range(2000)]
    res["gate"] = {"fewer_false_flips_share": float(rel.mean()), "lo": float(np.percentile(bs, 2.5)), "hi": float(np.percentile(bs, 97.5)),
                   "lag_within_10pct": bool(abs(df[df.name == 'CMA-A'].lag.median() - df[df.name == 'EMA'].lag.median())
                                             <= 0.1 * df[df.name == 'EMA'].lag.median())}
    res["gate"]["pass"] = bool(res["gate"]["lag_within_10pct"] and res["gate"]["fewer_false_flips_share"] >= 0.25 and res["gate"]["lo"] > 0)
    # test 2: pure noise, commit share
    nz = []
    for s in range(seeds):
        r = np.random.default_rng(5000 + s)
        c = 100 + np.cumsum(r.normal(0, 0.1, 750))
        o = np.r_[c[0], c[:-1]]
        h, l = np.maximum(o, c) + np.abs(r.normal(0, 0.04, 750)), np.minimum(o, c) - np.abs(r.normal(0, 0.04, 750))
        atr = CM.rma(CM.true_range(h, l, c), 14)
        M = CM.conviction_ma(o, h, l, c, **DEFAULT)[0]
        E = CM.ema(CM.heikin_ashi(o, h, l, c)[3], best_n)
        nz.append(dict(cma=np.mean(CM.commit_dir(M, atr) != 0), ema=np.mean(CM.commit_dir(E, atr) != 0)))
    nz = pd.DataFrame(nz)
    res["noise_test"] = {"cma_commit": float(nz.cma.mean()), "ema_commit": float(nz.ema.mean()),
                         "pass": bool(nz.cma.mean() <= 1.10 * nz.ema.mean())}
    os.makedirs(OUT, exist_ok=True)
    json.dump(res, open(os.path.join(OUT, "planted.json"), "w"), indent=1, default=float)
    print(json.dumps(res, indent=1, default=float))
    return res


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "planted"
    t0 = time.time()
    if cmd == "planted":
        run_planted()
    print(f"{time.time() - t0:.0f}s")
