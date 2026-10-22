"""User's FRVP on SPY daily: 2026-08-04 .. 2026-09-10, 200 rows, VA 70%. Recompute from 5m RTH bars with
(a) the indicator's value-area rule (grow one row at a time) and (b) the classic two-rows-at-a-time rule,
with and without the breakout day (the indicator excludes it)."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import numpy as np
from vzones.intraday.data import load_csv, rth
raw = rth(load_csv(pathlib.Path(__file__).resolve().parent.parent / "data/intraday/SPY_5m.csv")); raw.index = raw.index.tz_localize(None)
def run(b, R=200, two=False):
    lo, hi = b.low.min(), b.high.max(); st = (hi - lo) / R; pv = np.zeros(R)
    for r in b.itertuples():
        for q in range(int(np.clip((r.low - lo) // st, 0, R - 1)), int(np.clip((r.high - lo) // st, 0, R - 1)) + 1):
            ql = lo + q * st; pv[q] += r.volume * max(0, min(r.high, ql + st) - max(r.low, ql)) / max(r.high - r.low, 1e-9)
    pi = int(np.argmax(pv)); a0 = a1 = pi; acc = pv[pi]; k = 2 if two else 1
    while acc < .7 * pv.sum() and (a0 > 0 or a1 < R - 1):
        u = pv[a1 + 1:a1 + 1 + k].sum() if a1 < R - 1 else -1; d = pv[max(0, a0 - k):a0].sum() if a0 > 0 else -1
        if u >= d: n = min(k, R - 1 - a1); a1 += n; acc += u
        else: n = min(k, a0); a0 -= n; acc += d
    top = np.argsort(pv)[::-1][:5]
    return dict(lo=round(lo, 2), hi=round(hi, 2), row=round(st, 3), POC=round(lo + (pi + .5) * st, 2), VAH=round(lo + (a1 + 1) * st, 2), VAL=round(lo + a0 * st, 2),
                top5_rows=[round(lo + (q + .5) * st, 2) for q in top], top5_share=[round(pv[q] / pv[pi], 2) for q in top])
for incl in (False, True):
    b = raw[(raw.index >= "2026-08-04") & (raw.index < ("2026-09-11" if incl else "2026-09-10"))]
    for two in (False, True):
        print(("مع يوم 10 سبتمبر" if incl else "بدون يوم 10 سبتمبر"), "| قاعدة صفين" if two else "| قاعدة صف واحد", run(b, two=two))
