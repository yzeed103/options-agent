"""Trend legs, pullbacks and resumptions on the Hull average, the volume measures along them, the price-only control,
and the targets of reports/trend_volume/PREREG.md. Event detection and measures use past bars only; targets use the
future (evaluation only)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from vzones import conviction_ma as CM
from vzones import volume_tool as VT

HMA_LEN = {5: 67, 15: 66, 60: 56}       # 10-bar trend lag per timeframe (reports/hma_successor)
BEYOND = 0.3                             # ATR beyond M that ends the trend
MAX_PULL = 12
MIN_LEG = 5
HORIZON = 24
HORIZON_TF = {5: 24, 15: 8, 60: 3}         # the same two hours in bars (a 15m session has 26 bars, a 1h session 7)


def trend_state(c: np.ndarray, M: np.ndarray) -> np.ndarray:
    """+1 up-trend bar, -1 down, 0 none: close on one side of M with M's slope of that sign on this and the 2 previous bars."""
    s = np.r_[np.nan, np.diff(M)]
    s1 = np.r_[np.nan, s[:-1]]; s2 = np.r_[np.nan, s1[:-1]]
    up = (c > M) & (s > 0) & (s1 > 0) & (s2 > 0)
    dn = (c < M) & (s < 0) & (s1 < 0) & (s2 < 0)
    return np.where(up, 1, np.where(dn, -1, 0))


def hull_vwma(c, v, n: int):
    """Hull formula on volume-weighted averages: WMA(2 VWMA(n/2) - VWMA(n), sqrt n)."""
    import math
    def vwma(k):
        return pd.Series(c * v).rolling(k).sum().to_numpy() / pd.Series(v).rolling(k).sum().to_numpy()
    half, root = max(1, n // 2), max(1, int(round(math.sqrt(n))))
    return CM.wma(2 * vwma(half) - vwma(n), root)


def detect(d: pd.DataFrame, tf_min: int, hma_len: int | None = None):
    """Resumption events and climax events. Returns (frame arrays dict, events DataFrame, climax DataFrame)."""
    o, h, l, c, v = (d[k].to_numpy(float) for k in ("open", "high", "low", "close", "volume"))
    n = hma_len or HMA_LEN.get(tf_min, 67)
    M = CM.hma(c, n)
    A = VT.atr(h, l, c)
    rvol = VT.rvol_set(d, tf_min)[0]
    sess, _ = VT.sessions_slots(d.index, tf_min)
    st = trend_state(c, M)
    rng = h - l
    clv = ((c - l) - (h - c)) / np.maximum(rng, 1e-12)
    obv = np.cumsum(np.sign(np.r_[0.0, np.diff(c)]) * v)
    ev, clx = [], []
    phase, dr, run = "none", 0, 0
    leg_start = leg_len = 0; leg_ext = np.nan; prev_leg_len = np.nan
    pull_start = 0; pull_ext = np.nan; fail = 0
    for i in range(1, len(c)):
        if sess[i] != sess[i - 1] or not np.isfinite(M[i]):
            phase, run = "none", 0
            continue
        s = st[i]
        if phase == "none":
            if s != 0:
                if s == dr:
                    run += 1
                else:
                    dr, run, leg_start = s, 1, i
                if run >= MIN_LEG:
                    phase, leg_len = "leg", run
                    leg_ext = h[leg_start:i + 1].max() if dr > 0 else l[leg_start:i + 1].min()
            else:
                run = 0
            continue
        if phase == "leg":
            against = (dr > 0 and c[i] < c[i - 1]) or (dr < 0 and c[i] > c[i - 1])
            if s == -dr or dr * (c[i] - M[i]) < -BEYOND * A[i]:
                phase, run = "none", 0
                continue
            if against:
                if leg_len < MIN_LEG:                       # a leg that is not yet 5 bars long cannot have a pullback
                    phase, run = "none", 0
                    continue
                phase, pull_start, fail = "pull", i, 0
                pull_ext = l[i] if dr > 0 else h[i]
                continue
            leg_len += 1
            leg_ext = max(leg_ext, h[i]) if dr > 0 else min(leg_ext, l[i])
            # climax: leg >= 8, last three bars shrinking ranges; volume version adds RVOL > 2 on all three
            if leg_len >= 8 and rng[i] < rng[i - 1] < rng[i - 2]:
                r3 = rvol[i - 2:i + 1]
                vol_ok = bool(np.all(r3 > 2)) if np.all(np.isfinite(r3)) else False
                clx.append(dict(t=i, dir=dr, leg_len=leg_len, volume=vol_ok, rvol3=float(r3.mean()) if np.all(np.isfinite(r3)) else np.nan))
            continue
        # phase == "pull"
        plen = i - pull_start + 1
        pull_ext = min(pull_ext, l[i]) if dr > 0 else max(pull_ext, h[i])
        if dr * (c[i] - M[i]) < -BEYOND * A[i]:
            fail += 1
            if fail >= 2:
                phase, run = "none", 0
                continue
        if plen > MAX_PULL:
            phase, run = "none", 0
            continue
        if i - pull_start >= 2 and dr * (c[i] - leg_ext) > 0:
            # resumption
            la, lb = max(leg_start, pull_start - 20), pull_start           # last 20 bars of the leg
            leg_bars = np.arange(la, lb)
            trend_bars = leg_bars[(np.sign(c[leg_bars] - o[leg_bars]) == dr)]
            pull_bars = np.arange(pull_start, i)
            with np.errstate(all="ignore"):
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    v_leg = float(np.nanmean(rvol[trend_bars])) if len(trend_bars) else np.nan
                    v_pull = float(np.nanmean(rvol[pull_bars]))
            v_res = float(rvol[i])
            upv = v[la:i][np.sign(c[la:i] - o[la:i]) > 0].sum(); dnv = v[la:i][np.sign(c[la:i] - o[la:i]) < 0].sum()
            udr = (upv / dnv if dnv > 0 else np.nan) if dr > 0 else (dnv / upv if upv > 0 else np.nan)
            delta = float(np.nansum(clv[leg_bars] * rvol[leg_bars]) * dr)
            obv_div = float(dr * (obv[i - 1] - obv[pull_start - 1]) / max(v[pull_start:i].sum(), 1.0))
            er = v_res / max(rng[i] / A[i], 0.1) if np.isfinite(v_res) else np.nan
            depth = dr * (leg_ext - pull_ext) / A[i]
            ev.append(dict(t=i, dir=dr, leg_start=leg_start, pull_start=pull_start, leg_len=leg_len, pull_len=plen - 1,
                           v_leg=v_leg, v_pull=v_pull, v_res=v_res,
                           P=np.log(v_leg / v_pull) + np.log(v_res / v_pull) if v_leg > 0 and v_pull > 0 and v_res > 0 else np.nan,
                           leg_over_pull=np.log(v_leg / v_pull) if v_leg > 0 and v_pull > 0 else np.nan,
                           udR=udr, delta=delta, obv_div=obv_div, effort_result=er, control=-depth - 0.1 * (plen - 1),
                           depth=depth))
            prev_leg_len = leg_len
            ev[-1]["prev_leg_len"] = prev_leg_len
            phase, leg_start, leg_len = "leg", i, 1
            leg_ext = h[i] if dr > 0 else l[i]
            continue
    frames = dict(o=o, h=h, l=l, c=c, v=v, M=M, A=A, rvol=rvol, sess=sess, st=st)
    return frames, pd.DataFrame(ev), pd.DataFrame(clx)


def first_passage(h, l, c, A, sess, t: int, dr: int, horizon: int = HORIZON):
    """(+1 target first, -1 stop first, 0 neither, nan = not enough bars in the session), bars to the first touch."""
    if t + horizon >= len(c) or sess[t + horizon] != sess[t]:
        return np.nan, np.nan
    up, dn = c[t] + A[t], c[t] - A[t]
    for k in range(1, horizon + 1):
        hit_up = h[t + k] >= up; hit_dn = l[t + k] <= dn
        if hit_up and hit_dn:
            return 0.0, k
        if hit_up:
            return (1.0 if dr > 0 else -1.0), k
        if hit_dn:
            return (-1.0 if dr > 0 else 1.0), k
    return 0.0, horizon + 1


def targets(frames: dict, ev: pd.DataFrame, horizon: int = HORIZON) -> pd.DataFrame:
    """R1 first passage in the trend direction, its continuous form, R2 next leg >= previous leg, R3 alive after 24 bars."""
    h, l, c, A, M, sess = (frames[k] for k in ("h", "l", "c", "A", "M", "sess"))
    r1, cont, r2, r3 = [], [], [], []
    for t, dr, pl in zip(ev["t"], ev["dir"], ev["prev_leg_len"]):
        fp, k = first_passage(h, l, c, A, sess, int(t), int(dr), horizon)
        r1.append(fp)
        cont.append(np.nan if not np.isfinite(fp) else (horizon + 1 - k) * fp if fp != 0 else 0.0)
        # next leg length: bars from t until the close is beyond M against the trend by BEYOND ATR (same session, cap 100)
        j, L = int(t), 0
        while j + 1 < len(c) and sess[j + 1] == sess[j] and L < 100:
            j += 1
            if dr * (c[j] - M[j]) < -BEYOND * A[j]:
                break
            L += 1
        r2.append(float(L >= pl) if np.isfinite(pl) else np.nan)
        r3.append(np.nan if not np.isfinite(fp) else float(dr * (c[int(t) + horizon] - M[int(t) + horizon]) > 0))
    out = ev.copy()
    out["R1"], out["R1_cont"], out["R2"], out["R3"] = r1, cont, r2, r3
    return out


def climax_targets(frames: dict, clx: pd.DataFrame, horizon: int = HORIZON) -> pd.DataFrame:
    h, l, c, A, sess = (frames[k] for k in ("h", "l", "c", "A", "sess"))
    rev = []
    for t, dr in zip(clx["t"], clx["dir"]):
        fp, _ = first_passage(h, l, c, A, sess, int(t), int(dr), horizon)
        rev.append(np.nan if not np.isfinite(fp) else float(fp < 0))      # reversal = the stop side came first
    out = clx.copy(); out["reversal"] = rev
    return out


# ---------------- metrics on events ----------------
def quintile_lift(x: np.ndarray, hit: np.ndarray, edge: float):
    """top-quintile hit rate / all-events hit rate (edge = train 80th percentile of x)."""
    ok = np.isfinite(x) & np.isfinite(hit)
    if ok.sum() < 20:
        return np.nan
    base = hit[ok].mean(); top = hit[ok & (x > edge)]
    return float(top.mean() / base) if len(top) >= 10 and base > 0 else np.nan


def paired_lift(x, cx, hit, block, edge_x, edge_c, draws=2000, seed=0):
    """lift(measure) and lift(control) on the same events, their difference, intervals by resampling symbol-days."""
    df = pd.DataFrame({"x": x, "cx": cx, "h": hit, "b": block}).dropna()
    if len(df) < 20:
        return dict(n=len(df))
    blocks = df["b"].unique(); idx = {b: np.where(df["b"].to_numpy() == b)[0] for b in blocks}
    X, CX, H = df["x"].to_numpy(), df["cx"].to_numpy(), df["h"].to_numpy()

    def lifts(rows):
        base = H[rows].mean()
        lx = H[rows][X[rows] > edge_x].mean() / base if (X[rows] > edge_x).sum() >= 5 and base > 0 else np.nan
        lc = H[rows][CX[rows] > edge_c].mean() / base if (CX[rows] > edge_c).sum() >= 5 and base > 0 else np.nan
        return lx, lc
    lx, lc = lifts(np.arange(len(df)))
    rng = np.random.default_rng(seed)
    bs = []
    for _ in range(draws):
        pick = rng.integers(0, len(blocks), len(blocks))
        rows = np.concatenate([idx[blocks[p]] for p in pick])
        bs.append(lifts(rows))
    bs = np.array(bs, float)
    d = bs[:, 0] - bs[:, 1]
    return dict(n=len(df), base=round(float(H.mean()), 4), lift=round(lx, 3), lift_lo=round(float(np.nanpercentile(bs[:, 0], 2.5)), 3), lift_hi=round(float(np.nanpercentile(bs[:, 0], 97.5)), 3),
                control=round(lc, 3), control_lo=round(float(np.nanpercentile(bs[:, 1], 2.5)), 3), control_hi=round(float(np.nanpercentile(bs[:, 1], 97.5)), 3),
                diff=round(float(lx - lc), 3), diff_lo=round(float(np.nanpercentile(d, 2.5)), 3), diff_hi=round(float(np.nanpercentile(d, 97.5)), 3))
