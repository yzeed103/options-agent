"""Session-aware features. Every value at bar t uses bars <= t only; prior-session levels use
completed sessions only."""
from __future__ import annotations
import numpy as np, pandas as pd
from ..indicator import distribute_volume


def _profile_levels(h, l, v, rows=40, va=0.70):
    e = np.linspace(l.min(), h.max() + 1e-9, rows + 1)
    p = distribute_volume(h, l, v, e)
    poc_i = int(p.argmax()); lo = hi = poc_i; acc = p[poc_i]; tot = p.sum()
    while acc < va * tot and (lo > 0 or hi < rows - 1):
        up = p[hi + 1] if hi < rows - 1 else -1; dn = p[lo - 1] if lo > 0 else -1
        if up >= dn: hi += 1; acc += up
        else: lo -= 1; acc += dn
    return (e[poc_i] + e[poc_i + 1]) / 2, e[hi + 1], e[lo]


def add_features(df: pd.DataFrame, or_minutes: int = 15, atr_len: int = 14, ema_fast: int = 20, ema_slow: int = 50,
                 rvol_days: int = 20) -> pd.DataFrame:
    d = df.copy()
    day = pd.Series(d.index.date, index=d.index)
    d["session"] = day.values
    # ATR / EMA (continuous across sessions, trailing)
    pc = d.close.shift(1)
    tr = pd.concat([d.high - d.low, (d.high - pc).abs(), (d.low - pc).abs()], axis=1).max(axis=1)
    d["atr"] = tr.ewm(alpha=1 / atr_len, adjust=False, min_periods=atr_len).mean()
    d["ema_f"] = d.close.ewm(span=ema_fast, adjust=False).mean()
    d["ema_s"] = d.close.ewm(span=ema_slow, adjust=False).mean()
    # session VWAP and 1/2 sigma bands (cumulative within the session, includes bar t)
    tp = (d.high + d.low + d.close) / 3
    g = d.groupby("session")
    cv = g.volume.cumsum(); cpv = (tp * d.volume).groupby(d.session).cumsum(); cp2v = (tp * tp * d.volume).groupby(d.session).cumsum()
    d["vwap"] = cpv / cv
    sd = np.sqrt(np.maximum(cp2v / cv - d.vwap ** 2, 0))
    for k in (1, 2):
        d[f"vwap_up{k}"] = d.vwap + k * sd; d[f"vwap_dn{k}"] = d.vwap - k * sd
    # opening range: known only once its last bar has closed
    mins = d.index.hour * 60 + d.index.minute - 570
    bar_min = int(round((d.index[1] - d.index[0]).total_seconds() / 60)) if len(d) > 1 else 5
    in_or = mins < or_minutes
    orh = d.high.where(in_or).groupby(d.session).transform("max"); orl = d.low.where(in_or).groupby(d.session).transform("min")
    known = mins >= or_minutes            # bar opening at/after the OR end -> OR fully known
    d["or_high"] = orh.where(known); d["or_low"] = orl.where(known)
    # prior-session profile levels (completed sessions only)
    lv = {}
    for s, gg in d.groupby("session"):
        lv[s] = _profile_levels(gg.high.to_numpy(), gg.low.to_numpy(), gg.volume.to_numpy()) + (gg.high.max(), gg.low.min(), gg.close.iloc[-1])
    sessions = sorted(lv)
    prev = {sessions[i]: lv[sessions[i - 1]] for i in range(1, len(sessions))}
    for j, name in enumerate(["pd_poc", "pd_vah", "pd_val", "pd_high", "pd_low", "pd_close"]):
        d[name] = d.session.map(lambda s: prev.get(s, (np.nan,) * 6)[j])
    # relative volume vs the same time-of-day over the previous `rvol_days` sessions
    slot = d.index.hour * 60 + d.index.minute
    d["rvol"] = d.volume / d.volume.groupby(slot).transform(lambda x: x.shift(1).rolling(rvol_days, min_periods=5).mean())
    d["minute_of_session"] = mins
    d["bar_minutes"] = bar_min
    return d
