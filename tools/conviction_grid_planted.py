"""Exploratory, after the gate failed: every law and grid point of PREREG on the planted series, each against an EMA
of HA close at its own drift lag. Not a second chance for the gate; it answers "is the failure the defaults or the idea"."""
from __future__ import annotations

import itertools
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from vzones import conviction_ma as CM  # noqa: E402
from conviction_eval import planted, side_flips, OUT  # noqa: E402

SEEDS = 60
data = [planted(s) for s in range(SEEDS)]
ha_c = [CM.heikin_ashi(*d[:4])[3] for d in data]
_ema_cache = {}


def ema_flips(n):
    if n not in _ema_cache:
        _ema_cache[n] = float(np.mean([side_flips(CM.ema(ha_c[i], n), data[i][4]) for i in range(SEEDS)]))
    return _ema_cache[n]


rows = []
grid = list(itertools.product("ABC", (0.15, 0.3, 0.5), (0.4, 0.6, 0.8), (1.0, 2.0)))
grid += [("A", 0.3, 0.6, 1.0, lf, ls) for lf in (5, 8, 12) for ls in (40, 60, 100)]
seen = set()
for g in grid:
    law, gg, keep, p = g[:4]
    lf, ls = (g[4], g[5]) if len(g) > 4 else (8, 60)
    if law == "C" and keep != 0.6:
        continue                                  # C ignores keep
    key = (law, gg, keep, p, lf, ls)
    if key in seen:
        continue
    seen.add(key)
    kw = dict(law=law, g=gg, keep=keep, p=p, L_fast=lf, L_slow=ls)
    f = lambda o, h, l, c: CM.conviction_ma(o, h, l, c, **kw)[0]  # noqa: E731
    lag = float(np.median([CM.lag_drift(f, *data[i][:4]) for i in range(20)]))
    fl = float(np.mean([side_flips(f(*data[i][:4]), data[i][4]) for i in range(SEEDS)]))
    n = max(2, int(round(2 * lag + 1)))
    ef = ema_flips(n)
    rows.append(dict(**kw, lag=round(lag, 2), ema_len=n, flips=round(fl, 2), ema_flips=round(ef, 2),
                     fewer_share=round((ef - fl) / ef, 3)))
    print(rows[-1], flush=True)
sf = lambda o, h, l, c: CM.streak_ema(o, h, l, c, 8, 60)  # noqa: E731
lag = float(np.median([CM.lag_drift(sf, *data[i][:4]) for i in range(20)]))
n = max(2, int(round(2 * lag + 1)))
fl = float(np.mean([side_flips(sf(*data[i][:4]), data[i][4]) for i in range(SEEDS)]))
streak = dict(lag=round(lag, 2), ema_len=n, flips=round(fl, 2), ema_flips=round(ema_flips(n), 2),
              fewer_share=round((ema_flips(n) - fl) / ema_flips(n), 3))
rows.sort(key=lambda r: -r["fewer_share"])
res = {"seeds": SEEDS, "n_points": len(rows), "best": rows[:5], "worst": rows[-3:], "streak_ema": streak,
       "any_point_25pct_fewer": any(r["fewer_share"] >= 0.25 for r in rows),
       "any_point_fewer": any(r["fewer_share"] > 0 for r in rows), "all": rows}
json.dump(res, open(os.path.join(OUT, "planted_grid.json"), "w"), indent=1)
print(json.dumps({k: v for k, v in res.items() if k != "all"}, indent=1))
