"""Execution engine with the rules from the research prompt.

* entry at the NEXT bar's open; one position per symbol at a time
* stop / target filled at the level, except gap-through -> filled at the bar open
* stop and target inside the same bar -> stop first
* optional partial exit at `partial_r` (fraction `partial_frac`), runner to target or trailing ATR stop
* time stop: flat at the session close (no overnight) unless `overnight=True`
* costs: `cost` = fraction of price per side (ETF) or absolute points per side (futures, `cost_points`)
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np, pandas as pd


@dataclass
class Exec:
    stop_atr: float = 1.0
    target: str = "atr"            # "atr" or a column name holding a price level (e.g. "pd_vah")
    target_atr: float = 3.0
    trail_atr: float | None = None
    partial_r: float | None = None
    partial_frac: float = 0.5
    cost: float = 0.0001           # per side, fraction of price (0.0001 = 0.01%, i.e. 0.02% round trip)
    cost_points: float = 0.0       # per side, absolute (futures tick)
    overnight: bool = False


def run(d: pd.DataFrame, sig: np.ndarray, ex: Exec) -> pd.DataFrame:
    o, h, l, c, atr = (d[k].to_numpy(float) for k in ("open", "high", "low", "close", "atr"))
    sess = d.session.to_numpy(); n = len(d); trades = []; i = 0
    last_bar = np.r_[sess[1:] != sess[:-1], True]
    while i < n - 1:
        s = sig[i]
        if s == 0 or not np.isfinite(atr[i]) or (not ex.overnight and last_bar[i]):
            i += 1; continue
        e = i + 1; entry = o[e]; risk = ex.stop_atr * atr[i]
        stop = entry - s * risk
        tgt = entry + s * ex.target_atr * atr[i] if ex.target == "atr" else d[ex.target].iat[i]
        if not np.isfinite(tgt) or (tgt - entry) * s <= 0:
            i += 1; continue
        size_left, pnl_r, part_done, j, best = 1.0, 0.0, False, e, entry
        exit_px = None
        while True:
            # gap through stop or target at the open
            if j > e:
                if (o[j] - stop) * s <= 0: exit_px = o[j]; break
                if (o[j] - tgt) * s >= 0: exit_px = o[j]; break
            hit_stop = (l[j] <= stop) if s > 0 else (h[j] >= stop)
            hit_tgt = (h[j] >= tgt) if s > 0 else (l[j] <= tgt)
            if hit_stop: exit_px = stop; break                     # stop first
            if ex.partial_r and not part_done:
                pl = entry + s * ex.partial_r * risk
                if (h[j] >= pl) if s > 0 else (l[j] <= pl):
                    pnl_r += ex.partial_frac * ex.partial_r; size_left -= ex.partial_frac; part_done = True
                    stop = entry                                     # runner at break-even
            if hit_tgt: exit_px = tgt; break
            if ex.trail_atr:
                best = max(best, h[j]) if s > 0 else min(best, l[j])
                ns = best - s * ex.trail_atr * atr[j]
                stop = max(stop, ns) if s > 0 else min(stop, ns)
            if (not ex.overnight and last_bar[j]) or j == n - 1:
                exit_px = c[j]; break
            j += 1
        pnl_r += size_left * s * (exit_px - entry) / risk
        cost_r = (2 * (ex.cost * entry + ex.cost_points)) / risk
        trades.append(dict(entry_time=d.index[e], exit_time=d.index[j], dir=s, entry=entry, exit=exit_px,
                           r=pnl_r - cost_r, bars=j - e + 1))
        i = j + 1
    return pd.DataFrame(trades)


def metrics(tr: pd.DataFrame, weeks: float | None = None) -> dict:
    if tr.empty:
        return dict(trades=0)
    w, ls = tr.r[tr.r > 0], tr.r[tr.r <= 0]
    eq = tr.r.cumsum(); dd = (eq - eq.cummax()).min()
    out = dict(trades=len(tr), win_rate=round((tr.r > 0).mean(), 3), pf=round(w.sum() / -ls.sum(), 2) if ls.sum() < 0 else np.inf,
               expectancy_r=round(tr.r.mean(), 3), avg_win_r=round(w.mean(), 2) if len(w) else 0, avg_loss_r=round(ls.mean(), 2) if len(ls) else 0,
               max_dd_r=round(dd, 2), total_r=round(tr.r.sum(), 1))
    if weeks: out["per_week"] = round(len(tr) / weeks, 2)
    yr = tr.groupby(pd.to_datetime(tr.entry_time).dt.year).r
    out["worst_year_pf"] = round(min((g[g > 0].sum() / -g[g <= 0].sum()) if g[g <= 0].sum() < 0 else np.inf for _, g in yr), 2)
    return out
