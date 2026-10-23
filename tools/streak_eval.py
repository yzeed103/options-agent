"""Tests of reports/conviction_ma/PREREG_STREAK.md.

    python tools/streak_eval.py select     # step 1: grid on seeds 0..199
    python tools/streak_eval.py gate       # step 2: chosen point on fresh seeds 10000..10199
"""
from __future__ import annotations

import itertools
import json
import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from vzones import conviction_ma as CM  # noqa: E402
from conviction_eval import planted, side_flips, commit_delay, OUT  # noqa: E402


def segs(meta):
    return [(slice(meta["up0"] + 60, meta["up0"] + 150), 1), (slice(meta["down0"] + 60, meta["down0"] + 150), -1)]


def load(seeds, inject):
    out = []
    for s in seeds:
        o, h, l, c, lab, meta = planted(s, inject=inject)
        out.append((o, h, l, c, lab, meta, CM.heikin_ashi(o, h, l, c)[3]))
    return out


def stats(D, D_lag, f):
    """per-seed false flips (injected series) and median trend lag (clean series)"""
    fl = np.array([side_flips(f(*d[:4]), d[4]) for d in D])
    lg = float(np.median([CM.trend_lag(f(*d[:4]), d[3], segs(d[5]), 0.25 * d[5]["sig"]) for d in D_lag]))
    return fl, lg


def ema_table(D, D_lag):
    return {n: stats(D, D_lag, lambda o, h, l, c, n=n: CM.ema(CM.heikin_ashi(o, h, l, c)[3], n)) for n in range(2, 61)}


def match(tab, lag):
    return min(tab, key=lambda n: abs(tab[n][1] - lag))


def select():
    D, DL = load(range(200), True), load(range(200), False)
    tab = ema_table(D, DL)
    rows = []
    for cap, p, lf, ls in itertools.product((5, 10, 15), (1.0, 2.0), (5, 8, 12), (40, 60, 100)):
        f = lambda o, h, l, c, k=(lf, ls, cap, p): CM.streak_ema(o, h, l, c, *k)  # noqa: E731
        fl, lg = stats(D, DL, f)
        n = match(tab, lg)
        rows.append(dict(cap=cap, p=p, L_fast=lf, L_slow=ls, lag=round(lg, 2), ema_len=n,
                         flips=round(float(fl.mean()), 2), ema_flips=round(float(tab[n][0].mean()), 2),
                         fewer=round(float((tab[n][0].mean() - fl.mean()) / tab[n][0].mean()), 3)))
        print(rows[-1], flush=True)
    ok = [r for r in rows if r["lag"] <= 8]
    best = max(ok, key=lambda r: r["fewer"])
    json.dump({"chosen": best, "all": rows}, open(os.path.join(OUT, "streak_select.json"), "w"), indent=1)
    print("CHOSEN", best)


def gate():
    best = json.load(open(os.path.join(OUT, "streak_select.json")))["chosen"]
    k = (best["L_fast"], best["L_slow"], best["cap"], best["p"])
    f = lambda o, h, l, c: CM.streak_ema(o, h, l, c, *k)  # noqa: E731
    seeds = range(10000, 10200)
    D, DL = load(seeds, True), load(seeds, False)
    fl, lg = stats(D, DL, f)
    tab = ema_table(D, DL)
    n = match(tab, lg)
    e = tab[n][0]
    rel = (e - fl) / np.where(e > 0, e, np.nan)
    rng = np.random.default_rng(0)
    bs = [np.nanmean(rel[rng.integers(0, len(rel), len(rel))]) for _ in range(4000)]
    ef = lambda o, h, l, c: CM.ema(CM.heikin_ashi(o, h, l, c)[3], n)  # noqa: E731
    extra = {}
    for name, g in (("streak", f), ("ema", ef)):
        du, dd, dent = [], [], []
        for d in D:
            M = g(*d[:4]); dm = np.diff(M); m = d[5]
            du.append(commit_delay(M, m["up0"], 1)); dd.append(commit_delay(M, m["down0"], -1))
            dent.append((np.nanmedian(dm[m["up0"] + 20:m["inj"] - 2]) - dm[m["inj"]]) / m["sig"])
        extra[name] = dict(delay_up=float(np.nanmedian(du)), delay_down=float(np.nanmedian(dd)), dent=float(np.nanmedian(dent)))
    nz = []
    for s in range(20000, 20200):
        r = np.random.default_rng(s)
        c = 100 + np.cumsum(r.normal(0, 0.1, 750)); o = np.r_[c[0], c[:-1]]
        h, l = np.maximum(o, c) + np.abs(r.normal(0, 0.04, 750)), np.minimum(o, c) - np.abs(r.normal(0, 0.04, 750))
        atr = CM.rma(CM.true_range(h, l, c), 14)
        nz.append((np.mean(CM.commit_dir(f(o, h, l, c), atr) != 0), np.mean(CM.commit_dir(ef(o, h, l, c), atr) != 0)))
    nz = np.array(nz).mean(0)
    res = dict(chosen=best, trend_lag=lg, ema_len=n, ema_lag=tab[n][1],
               lag_within_10pct=bool(abs(lg - tab[n][1]) <= 0.1 * tab[n][1]),
               flips=float(fl.mean()), ema_flips=float(e.mean()), fewer=float(np.nanmean(rel)),
               lo=float(np.percentile(bs, 2.5)), hi=float(np.percentile(bs, 97.5)), shape=extra,
               noise=dict(streak=float(nz[0]), ema=float(nz[1]), pass_=bool(nz[0] <= 1.1 * nz[1])))
    res["pass"] = bool(res["lag_within_10pct"] and res["fewer"] >= 0.25 and res["lo"] > 0 and res["noise"]["pass_"])
    json.dump(res, open(os.path.join(OUT, "streak_gate.json"), "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    t0 = time.time()
    {"select": select, "gate": gate}[sys.argv[1]]()
    print(f"{time.time() - t0:.0f}s")
