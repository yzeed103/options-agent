"""Event backtest for Volume Zones signals.

Entry at the NEXT bar's open after a signal (no look-ahead).
* hunt     : long/short toward `target`; take-profit at target, stop at the far
             side of the broken pool, time stop after `max_hold` bars.
* rejection: fade from the HVN; take-profit = `rr` x risk, stop beyond the wick.
Costs: `cost_bps` per side.
"""
from __future__ import annotations
import numpy as np, pandas as pd
from .indicator import VZParams, compute


def run(df: pd.DataFrame, params: VZParams | None = None, signals=("hunt",), max_hold: int = 20,
        rr: float = 1.5, cost_bps: float = 1.0, computed: pd.DataFrame | None = None,
        long_only: bool = False, with_trend: bool = False) -> pd.DataFrame:
    r = computed if computed is not None else compute(df, params)
    o, h, l, c = (r[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    trades, busy_until = [], -1
    for t in range(len(r) - 1):
        if t <= busy_until:
            continue
        sig = None
        if "hunt" in signals and r["hunt"].iat[t]:
            d = int(r["hunt"].iat[t]); tp = r["target"].iat[t]
            sl = r["pool_low"].iat[t] if d > 0 else r["pool_high"].iat[t]
            sig = ("hunt", d, tp, sl)
        elif "rejection" in signals and r["rejection"].iat[t]:
            d = int(r["rejection"].iat[t])
            sl = l[t] if d > 0 else h[t]
            sig = ("rejection", d, None, sl)
        if sig is None:
            continue
        kind, d, tp, sl = sig
        if long_only and d < 0:
            continue
        if with_trend and int(r["trend_dir"].iat[t]) != d:
            continue
        e = t + 1; entry = o[e]
        risk = (entry - sl) * d
        if not np.isfinite(risk) or risk <= 0:
            continue
        if tp is None:
            tp = entry + d * rr * risk
        if (tp - entry) * d <= 0:
            continue
        exit_px, exit_i, why = None, None, "time"
        for j in range(e, min(e + max_hold, len(r))):
            hit_sl = l[j] <= sl if d > 0 else h[j] >= sl
            hit_tp = h[j] >= tp if d > 0 else l[j] <= tp
            if hit_sl:                       # conservative: stop first if both
                exit_px, exit_i, why = sl, j, "stop"; break
            if hit_tp:
                exit_px, exit_i, why = tp, j, "target"; break
        if exit_px is None:
            exit_i = min(e + max_hold, len(r)) - 1; exit_px = c[exit_i]
        ret = d * (exit_px - entry) / entry - 2 * cost_bps / 1e4
        trades.append(dict(kind=kind, dir=d, entry_time=r.index[e], exit_time=r.index[exit_i],
                           entry=entry, exit=exit_px, target=tp, stop=sl, reason=why,
                           ret=ret, r_mult=(d * (exit_px - entry)) / risk, bars=exit_i - e + 1))
        busy_until = exit_i
    return pd.DataFrame(trades)


def stats(tr: pd.DataFrame, n_bars: int | None = None) -> dict:
    if tr is None or tr.empty:
        return dict(trades=0)
    eq = (1 + tr["ret"]).cumprod()
    dd = (eq / eq.cummax() - 1).min()
    wins, losses = tr.ret[tr.ret > 0], tr.ret[tr.ret <= 0]
    pf = wins.sum() / -losses.sum() if losses.sum() < 0 else np.inf
    out = dict(trades=len(tr), win_rate=round((tr.ret > 0).mean(), 3), avg_ret_pct=round(tr.ret.mean() * 100, 3),
               profit_factor=round(pf, 2), total_ret_pct=round((eq.iat[-1] - 1) * 100, 2),
               max_dd_pct=round(dd * 100, 2), avg_r=round(tr.r_mult.mean(), 2),
               target_hit=round((tr.reason == "target").mean(), 3))
    if n_bars:
        out["exposure"] = round(tr.bars.sum() / n_bars, 3)
    return out
