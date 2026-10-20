"""HUNT signal research: why it is rare and which relaxed variants keep their edge.

Every variant: trigger x trend filter, target = nearest volume level ahead (HVN edge, POC, VAH, VAL)
1..12 ATR away. Same exit for all: entry next open, take-profit at target, stop 1.5 ATR, 20-bar time stop.
Also measures *recall*: share of strong moves (|close[t+10]-close[t]| >= 3 ATR) that had a
same-direction signal in bars t-2..t.
"""
from __future__ import annotations
import numpy as np, pandas as pd
from .indicator import VZParams, compute

TRIGGERS = ("pool", "range", "va")
FILTERS = ("adx25", "adx_rising", "ema_only")


def signals(r: pd.DataFrame, trigger: str, filt: str, br: float = 1.5, rng_n: int = 10, rng_max_atr: float | None = 4.0,
            min_atr: float = 1.0, max_atr: float = 12.0, fallback_atr: float | None = None) -> pd.DataFrame:
    """fallback_atr: if no volume level is ahead (price in thin air), target = close +/- fallback_atr * ATR."""
    c, h, l = r.close.to_numpy(), r.high.to_numpy(), r.low.to_numpy()
    atr, vr, adx = r.atr.to_numpy(), r.vol_ratio.to_numpy(), r.adx.to_numpy()
    ema_f = r.close.ewm(span=20, adjust=False).mean().to_numpy(); ema_s = r.close.ewm(span=50, adjust=False).mean().to_numpy()
    n = len(r); d = np.zeros(n, int)
    if trigger == "pool":
        d = r.pool_break.to_numpy().astype(int)
    elif trigger == "range":
        hh = pd.Series(h).rolling(rng_n).max().shift(1).to_numpy(); ll = pd.Series(l).rolling(rng_n).min().shift(1).to_numpy()
        tight = np.ones(n, bool) if rng_max_atr is None else (hh - ll) <= rng_max_atr * atr
        up = (c > hh) & tight & (vr >= br); dn = (c < ll) & tight & (vr >= br)
        d = np.where(up, 1, np.where(dn, -1, 0))
    elif trigger == "va":
        vah, val = r.vah.to_numpy(), r.val.to_numpy()
        pc = np.r_[np.nan, c[:-1]]; inside = (pc <= np.r_[np.nan, vah[:-1]]) & (pc >= np.r_[np.nan, val[:-1]])
        up = inside & (c > vah) & (vr >= br); dn = inside & (c < val) & (vr >= br)
        d = np.where(up, 1, np.where(dn, -1, 0))
    ema_up, ema_dn = ema_f > ema_s, ema_f < ema_s
    if filt == "adx25":
        ok_up, ok_dn = ema_up & (adx >= 25), ema_dn & (adx >= 25)
    elif filt == "adx_rising":
        rising = (adx > np.r_[np.full(3, np.nan), adx[:-3]]) & (adx >= 15)
        ok_up, ok_dn = ema_up & rising, ema_dn & rising
    else:
        ok_up, ok_dn = ema_up, ema_dn
    d = np.where((d > 0) & ok_up, 1, np.where((d < 0) & ok_dn, -1, 0))
    # target: nearest level ahead within [min_atr, max_atr] ATR
    lv = np.vstack([r[k].to_numpy() for k in ("hvn_above", "hvn_above_hi", "hvn_below", "hvn_below_lo", "poc", "vah", "val")]).T
    tgt = np.full(n, np.nan)
    for t in np.flatnonzero(d):
        cand = lv[t][np.isfinite(lv[t])]
        dist = (cand - c[t]) * d[t] / atr[t]
        ok = cand[(dist >= min_atr) & (dist <= max_atr)]
        if len(ok):
            tgt[t] = ok[np.argmin(np.abs(ok - c[t]))]
        elif fallback_atr:
            tgt[t] = c[t] + d[t] * fallback_atr * atr[t]
        else:
            d[t] = 0
    return pd.DataFrame({"sig": d, "target": tgt}, index=r.index)


def backtest(r: pd.DataFrame, s: pd.DataFrame, stop_atr: float = 1.5, max_hold: int = 20, cost_bps: float = 1.0):
    o, h, l, c, atr = (r[k].to_numpy() for k in ("open", "high", "low", "close", "atr"))
    sig, tgt = s.sig.to_numpy(), s.target.to_numpy()
    out, busy = [], -1
    for t in np.flatnonzero(sig):
        if t <= busy or t + 1 >= len(r):
            continue
        d = sig[t]; e = t + 1; entry = o[e]; sl = entry - d * stop_atr * atr[t]; tp = tgt[t]
        if (tp - entry) * d <= 0:
            continue
        px, xi = None, None
        for j in range(e, min(e + max_hold, len(r))):
            if (l[j] <= sl) if d > 0 else (h[j] >= sl):
                px, xi = sl, j; break
            if (h[j] >= tp) if d > 0 else (l[j] <= tp):
                px, xi = tp, j; break
        if px is None:
            xi = min(e + max_hold, len(r)) - 1; px = c[xi]
        risk = abs(entry - sl)
        out.append(dict(t=t, dir=d, ret=d * (px - entry) / entry - 2 * cost_bps / 1e4, r=d * (px - entry) / risk, hit=px == tp))
        busy = xi
    return pd.DataFrame(out)


def recall(r: pd.DataFrame, s: pd.DataFrame, horizon: int = 10, move_atr: float = 3.0, lead: int = 2, lag: int = 3) -> float:
    c, atr = r.close.to_numpy(), r.atr.to_numpy()
    fwd = np.r_[c[horizon:] - c[:-horizon], np.full(horizon, np.nan)] / atr
    big = np.flatnonzero(np.abs(fwd) >= move_atr)
    # de-duplicate overlapping moves: keep first bar of each cluster
    big = big[np.r_[True, np.diff(big) > horizon]] if len(big) else big
    sig = s.sig.to_numpy(); hit = 0
    for t in big:
        d = np.sign(fwd[t]); w = sig[max(0, t - lead):t + 1 + lag]
        hit += int((w == d).any())
    return hit / len(big) if len(big) else np.nan


def summarize(tr: pd.DataFrame, years: float) -> dict:
    if tr.empty:
        return dict(trades=0, per_year=0.0)
    wins, losses = tr.ret[tr.ret > 0].sum(), -tr.ret[tr.ret <= 0].sum()
    return dict(trades=len(tr), per_year=round(len(tr) / years, 1), win=round((tr.ret > 0).mean(), 3),
                pf=round(wins / losses, 2) if losses > 0 else np.inf, avg_r=round(tr.r.mean(), 3),
                hit_target=round(tr.hit.mean(), 3), total_pct=round(((1 + tr.ret).prod() - 1) * 100, 1))


def run_grid(df: pd.DataFrame, params: VZParams, label: str, br: float = 1.5) -> pd.DataFrame:
    r = compute(df, params)
    sp = int(len(r) * 0.6); rows = []
    for part, rr in (("train", r.iloc[:sp]), ("test", r.iloc[sp:])):
        years = (rr.index[-1] - rr.index[0]).days / 365.25
        for trig in TRIGGERS:
            for f in FILTERS:
                s = signals(rr, trig, f, br=br)
                rows.append(dict(data=label, part=part, trigger=trig, filter=f, recall=round(recall(rr, s), 3),
                                 **summarize(backtest(rr, s), years)))
    return pd.DataFrame(rows)
