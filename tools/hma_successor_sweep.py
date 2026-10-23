"""Exploratory, after the verdict (not pre-registered): the damping sweep g = 0.6..1.0 of the damped Hull on real 5m
test data at matched lag, to show the trade-off curve overshoot vs flips. Writes reports/hma_successor/sweep_5m.json."""
from __future__ import annotations

import json
import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from vzones import conviction_ma as CM  # noqa: E402
from vzones import hma_successor as HS  # noqa: E402
import hma_successor_eval as E  # noqa: E402
import streak_verdict as SV  # noqa: E402

t0 = time.time()
F = {s: SV.frames(s)["5m"] for s in SV.SYMS}
days = sorted(set().union(*[set(x.date() for x in F[s].index) for s in SV.SYMS]))
cut = days[int(0.6 * len(days))]
D, MASK = {}, {}
for s in SV.SYMS:
    o, h, l, c = SV.arrays(F[s]); ho, hh, hl, hc = CM.heikin_ashi(o, h, l, c)
    D[s] = dict(o=o, h=h, l=l, c=c, hc=hc, hh=hh, hl=hl, atr=HS.ha_atr(o, h, l, c), sym=s)
    MASK[s] = np.array([x.date() for x in F[s].index]) < cut
    MASK[s][:200] = False


def lagf(M, d):
    return SV.trend_lag_real(lambda *a: M, d["o"], d["h"], d["l"], d["c"], MASK[d["sym"]])


tdata = [D[s] for s in SV.TUNE]


def score(f):
    ov, td, st, nz, dp = [], [], [0, 0], 0.0, 0.0
    for s in SV.SYMS:
        d = D[s]; test = ~MASK[s]; test[:200] = False
        M = f(d)
        dm = np.sign(np.diff(M, prepend=np.nan))[test]; dm = dm[np.isfinite(dm) & (dm != 0)]
        st[0] += len(dm); st[1] += int(np.sum(dm[1:] != dm[:-1]))
        nz += float(np.nansum(np.abs(np.diff(M, 2, prepend=[np.nan, np.nan]))[test])); dp += float(np.nansum(np.abs(np.diff(d["hc"], prepend=np.nan))[test]))
        for t, old in HS.reversals(d["c"], d["atr"]):
            if test[t]:
                ov.append(HS.overshoot(M, t, old, HS.turning_price(d["hh"], d["hl"], t, old), d["atr"][t])); td.append(HS.turn_delay(M, t, -old))
    return dict(overshoot=float(np.nanmean(ov)), delay=float(np.nanmean(td)), flips=100 * st[1] / st[0], noise=nz / dp)


rows = []
for g in (1.0, 0.95, 0.9, 0.85, 0.8, 0.7, 0.6):
    f, lens, lg = E.matched_fn("DHMA", g, tdata, lagf, E.TARGET_LAG)
    rows.append(dict(g=g, **lens, lag=round(lg, 2), **{k: round(v, 4) for k, v in score(f).items()}))
    print(rows[-1], f"{time.time() - t0:.0f}s", flush=True)
ref = rows[0]
for r in rows:
    r["vs_hma"] = {k: round(1 - r[k] / ref[k], 3) for k in ("overshoot", "delay", "flips", "noise")}
json.dump(rows, open(os.path.join(E.OUT, "sweep_5m.json"), "w"), indent=1)
print(json.dumps(rows, indent=1))
