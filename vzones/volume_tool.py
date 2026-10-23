"""Volume tools, the strength score, persistence and the targets of reports/volume_tool/PREREG.md.

Everything takes a DataFrame with columns open high low close volume (regular session bars, tz America/New_York index)
and returns arrays aligned to it. Tools use past bars only (tests/test_volume_tool.py checks the prefix property);
targets use the future on purpose (evaluation only)."""
from __future__ import annotations

import numpy as np
import pandas as pd

L_DEFAULT = 20
STRONG = 1.5          # RVOL above this = strong volume (persistence runs)
N_SESS = 20           # sessions in the slot baseline


# ---------------- session / slot ----------------
def sessions_slots(index: pd.DatetimeIndex, tf_min: int):
    """session id (date) and slot id (bar position in the session) per bar."""
    sess = np.array([t.date() for t in index])
    mins = index.hour * 60 + index.minute - (9 * 60 + 30)
    slot = (np.asarray(mins) // tf_min).astype(int) if tf_min < 390 else np.zeros(len(index), int)
    return sess, slot


def slot_baseline(x: np.ndarray, sess, slot, n: int = N_SESS, stat: str = "median", min_sessions: int = 10):
    """Per bar: `stat` of x in the same slot over the previous n sessions (strictly before this session)."""
    df = pd.DataFrame({"x": x, "s": sess, "k": slot})
    piv = df.pivot_table(index="s", columns="k", values="x", aggfunc="first")
    roll = piv.rolling(n, min_periods=min_sessions)
    if stat == "median":
        base = roll.median()
    elif stat == "mad":
        med = roll.median()
        base = (piv - med).abs().rolling(n, min_periods=min_sessions).median()  # MAD about the rolling median
    else:
        raise ValueError(stat)
    base = base.shift(1)                                     # previous sessions only
    lookup = base.stack(future_stack=True)
    key = pd.MultiIndex.from_arrays([df["s"], df["k"]])
    return lookup.reindex(key).to_numpy(float)


def atr(h, l, c, n: int = 14):
    tr = np.maximum(h - l, np.maximum(np.abs(h - np.r_[c[0], c[:-1]]), np.abs(l - np.r_[c[0], c[:-1]])))
    return pd.Series(tr).ewm(alpha=1 / n, adjust=False).mean().to_numpy()


# ---------------- normalization ----------------
def rvol_set(d: pd.DataFrame, tf_min: int):
    """RVOL, logRVOL, zRVOL (slot baselines over the previous 20 sessions)."""
    v = d["volume"].to_numpy(float)
    sess, slot = sessions_slots(d.index, tf_min)
    med = slot_baseline(v, sess, slot)
    with np.errstate(invalid="ignore", divide="ignore"):
        rvol = np.where(med > 0, v / med, np.nan)
    lv = np.log(np.where(v > 0, v, np.nan))
    lmed = slot_baseline(lv, sess, slot)
    lmad = slot_baseline(lv, sess, slot, stat="mad")
    with np.errstate(invalid="ignore", divide="ignore"):
        z = (lv - lmed) / (1.4826 * np.where(lmad > 0, lmad, np.nan))
    return rvol, np.log(rvol), z


# ---------------- tools ----------------
def _ema(x, n):
    return pd.Series(x).ewm(span=n, adjust=False).mean().to_numpy()


def _sma(x, n):
    return pd.Series(x).rolling(n).mean().to_numpy()


def _rsum(x, n):
    return pd.Series(x).rolling(n).sum().to_numpy()


def tools(d: pd.DataFrame, tf_min: int, L: int = L_DEFAULT) -> dict[str, np.ndarray]:
    """Every candidate of the PREREG, aligned to d. Keys ending in '*' are signed (carry a direction)."""
    o, h, l, c, v = (d[k].to_numpy(float) for k in ("open", "high", "low", "close", "volume"))
    A = atr(h, l, c)
    rng = np.maximum(h - l, 1e-12)
    rvol, lrvol, zrvol = rvol_set(d, tf_min)
    dc = np.r_[0.0, np.diff(c)]
    clv = ((c - l) - (h - c)) / rng
    vsum = _rsum(v, L)
    vmed = pd.Series(v).rolling(L).median().to_numpy()
    out = {}
    obv = np.cumsum(np.sign(dc) * v)
    out["OBV slope*"] = (obv - np.r_[np.full(L, np.nan), obv[:-L]]) / (A * vsum)
    ad = np.cumsum(clv * v)
    out["A/D slope*"] = (ad - np.r_[np.full(L, np.nan), ad[:-L]]) / (A * vsum)
    out["CMF*"] = _rsum(clv * v, L) / vsum
    tp = (h + l + c) / 3
    dtp = np.r_[0.0, np.diff(tp)]
    pos = _rsum(np.where(dtp > 0, tp * v, 0.0), L); neg = _rsum(np.where(dtp < 0, tp * v, 0.0), L)
    with np.errstate(invalid="ignore", divide="ignore"):
        out["MFI*"] = 100 - 100 / (1 + pos / np.where(neg > 0, neg, np.nan)) - 50
    out["Force*"] = _ema(dc * v, L) / (A * vmed)
    mid = (h + l) / 2
    dmid = np.r_[0.0, np.diff(mid)]
    with np.errstate(invalid="ignore", divide="ignore"):
        eom1 = (dmid / A) * (rng / A) / np.where(rvol > 0, rvol, np.nan)
    out["EOM*"] = _sma(eom1, L)
    hlc = h + l + c
    trend = np.where(hlc > np.r_[hlc[0], hlc[:-1]], 1.0, -1.0)
    dm = h - l
    cm = np.zeros(len(c))
    for i in range(1, len(c)):
        cm[i] = cm[i - 1] + dm[i] if trend[i] == trend[i - 1] else dm[i - 1] + dm[i]
    with np.errstate(invalid="ignore", divide="ignore"):
        vf = v * np.abs(2 * (dm / np.where(cm > 0, cm, np.nan)) - 1) * trend * 100
    vf = np.nan_to_num(vf)
    out["Klinger*"] = (_ema(vf, 34) - _ema(vf, 55)) / (100 * _rsum(v, 55))
    pressure = clv * rvol
    out["pressure*"] = pressure
    out["delta*"] = _rsum(pressure, L)
    out["vol/SMA"] = v / _sma(v, L)
    out["RVOL"] = rvol
    out["logRVOL"] = lrvol
    out["zRVOL"] = zrvol
    out["vol ROC"] = v / np.r_[np.full(L, np.nan), v[:-L]] - 1
    sess, _ = sessions_slots(d.index, tf_min)
    key = pd.Series(sess)
    pv = pd.Series(tp * v).groupby(key).cumsum().to_numpy(); cv = pd.Series(v).groupby(key).cumsum().to_numpy()
    out["VWAP dist"] = np.abs(c - pv / np.where(cv > 0, cv, np.nan)) / A
    out["effort/result"] = rvol / np.maximum(rng / A, 0.1)
    out["range/ATR"] = rng / A
    body = np.abs(c - o) / rng
    S = 0.5 * zrvol + 0.25 * (rng / A - 1) + 0.25 * body
    out["STRENGTH"] = S
    out["STRENGTH*"] = S * np.sign(c - o)
    return out


# ---------------- targets (use the future; evaluation only) ----------------
def targets(d: pd.DataFrame, tf_min: int, ks=(3, 6, 12), horizon: int = 24) -> dict[str, np.ndarray]:
    o, h, l, c = (d[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    A = atr(h, l, c)
    n = len(c)
    sgn = np.sign(c - o)
    out = {}
    for k in ks:
        fut = np.r_[c[k:], np.full(k, np.nan)]
        out[f"T1_{k}_raw"] = (fut - c) / A                 # for signed tools (their own direction)
        out[f"T1_{k}"] = out[f"T1_{k}_raw"] * sgn          # for unsigned tools (the bar's direction)
    # T2: range of the next 6 bars vs the slot median of that range over the previous 20 sessions
    hh = pd.Series(h).rolling(6).max().shift(-6).to_numpy(); ll = pd.Series(l).rolling(6).min().shift(-6).to_numpy()
    fr = hh - ll
    sess, slot = sessions_slots(d.index, tf_min)
    base = slot_baseline(fr, sess, slot)
    with np.errstate(invalid="ignore", divide="ignore"):
        out["T2"] = np.log(fr / base)
    # T3: first touch of close +- 1 ATR within `horizon` bars; +1 in the bar's direction, -1 opposite, 0 neither
    up_t = np.full(n, horizon + 1); dn_t = np.full(n, horizon + 1)
    for j in range(1, horizon + 1):
        hj = np.r_[h[j:], np.full(j, np.nan)]; lj = np.r_[l[j:], np.full(j, np.nan)]
        up_t = np.where((up_t > horizon) & (hj >= c + A), j, up_t)
        dn_t = np.where((dn_t > horizon) & (lj <= c - A), j, dn_t)
    first = np.where(up_t < dn_t, 1, np.where(dn_t < up_t, -1, 0))
    first = np.where((up_t > horizon) & (dn_t > horizon), 0, first)
    out["T3_raw"] = first.astype(float)
    out["T3"] = first * sgn
    # the session must have `horizon` more bars for T3 to be defined
    out["T3_valid"] = (np.r_[sess[horizon:], np.array([None] * horizon)] == sess)
    return out


def t4_breakouts(d: pd.DataFrame, levels: pd.DataFrame, hold: int = 12, beyond: float = 0.5):
    """Closes through a level (columns of `levels`, one row per session date) and whether price held `beyond` ATR
    past it after `hold` bars without closing back. Returns (event index, success, direction, level name)."""
    o, h, l, c = (d[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    A = atr(h, l, c)
    sess = np.array([t.date() for t in d.index])
    ev = []
    for name in levels.columns:
        lv = levels[name].reindex(sess).to_numpy(float)
        prev = np.r_[np.nan, c[:-1]]
        same = np.r_[False, sess[1:] == sess[:-1]]
        up = same & (prev < lv) & (c > lv)
        dn = same & (prev > lv) & (c < lv)
        for t in np.where(up | dn)[0]:
            if t + hold >= len(c) or sess[t + hold] != sess[t]:
                continue
            dirn = 1 if up[t] else -1
            seg = c[t + 1:t + hold + 1]
            held = np.all(dirn * (seg - lv[t]) > 0) and dirn * (c[t + hold] - lv[t]) >= beyond * A[t]
            ev.append((t, bool(held), dirn, name))
    return ev


# ---------------- persistence ----------------
def runs(strong: np.ndarray, sess) -> np.ndarray:
    """Run length of strong bars ending at each bar (0 when not strong); runs do not cross sessions."""
    r = np.zeros(len(strong), int)
    for i in range(len(strong)):
        if strong[i] and i > 0 and sess[i] == sess[i - 1]:
            r[i] = r[i - 1] + 1
        elif strong[i]:
            r[i] = 1
    return r


def hazard(run: np.ndarray, sess, max_r: int = 20):
    """h(r) = P(next bar not strong | run length r), r = 1..max_r, with counts."""
    nxt = np.r_[run[1:], 0]; same = np.r_[sess[1:] == sess[:-1], False]
    h = np.full(max_r + 1, np.nan); cnt = np.zeros(max_r + 1, int)
    for r in range(1, max_r + 1):
        m = (run == r) & same
        cnt[r] = int(m.sum())
        if cnt[r] >= 20:
            h[r] = float(np.mean(nxt[m] == 0))
    return h, cnt


def persistence_score(run: np.ndarray, h: np.ndarray, cap: int = 20) -> np.ndarray:
    """Expected remaining strong bars given the run length, from the hazard curve (last known hazard carried on)."""
    hh = pd.Series(h).ffill().bfill().to_numpy()
    exp = np.zeros(len(hh))
    for r in range(len(hh) - 1, 0, -1):
        surv = 1.0; tot = 0.0
        for m in range(1, cap + 1):
            rr = min(r + m - 1, len(hh) - 1)
            surv *= 1 - hh[rr]
            tot += surv
        exp[r] = tot
    return np.where(run > 0, exp[np.minimum(run, len(hh) - 1)], 0.0)


def autocorr(x: np.ndarray, lags=range(1, 13)):
    x = np.asarray(x, float); m = np.isfinite(x)
    x = x[m] - np.nanmean(x[m]); v = np.dot(x, x)
    return {k: float(np.dot(x[k:], x[:-k]) / v) for k in lags}


# ---------------- metrics ----------------
def ic_by_block(x: np.ndarray, y: np.ndarray, block: np.ndarray):
    """Spearman per block (min 10 pairs): returns (mean IC, 95% interval over blocks, n blocks, per-block values)."""
    df = pd.DataFrame({"x": x, "y": y, "b": block}).dropna()
    df["rx"] = df.groupby("b")["x"].rank(); df["ry"] = df.groupby("b")["y"].rank()
    g = df.groupby("b")
    n = g.size()
    sx = g["rx"].sum(); sy = g["ry"].sum(); sxy = (df["rx"] * df["ry"]).groupby(df["b"]).sum()
    sxx = (df["rx"] ** 2).groupby(df["b"]).sum(); syy = (df["ry"] ** 2).groupby(df["b"]).sum()
    cov = sxy - sx * sy / n; vx = sxx - sx ** 2 / n; vy = syy - sy ** 2 / n
    with np.errstate(invalid="ignore", divide="ignore"):
        ic = (cov / np.sqrt(vx * vy))[n >= 10].dropna()
    if len(ic) == 0:
        return np.nan, (np.nan, np.nan), 0, ic
    rng = np.random.default_rng(0)
    a = ic.to_numpy()
    bs = [np.mean(a[rng.integers(0, len(a), len(a))]) for _ in range(2000)]
    return float(a.mean()), (float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))), len(a), ic


def ic_pooled(x: np.ndarray, y: np.ndarray, block: np.ndarray, sym: np.ndarray):
    """Spearman with ranks taken within each symbol over the whole period (no short-block artifact: inside a
    78-bar block a lagging tool and a leading target rank against each other, ATR alone scores -0.13 on iid data).
    Interval by resampling blocks (symbol-days) of the rank sums."""
    df = pd.DataFrame({"x": x, "y": y, "b": block, "s": sym}).dropna()
    if len(df) < 50:
        return np.nan, (np.nan, np.nan), 0
    df["rx"] = df.groupby("s")["x"].rank(); df["ry"] = df.groupby("s")["y"].rank()
    n_s = df.groupby("s")["x"].transform("size")
    df["rx"] = (df["rx"] - (n_s + 1) / 2) / n_s; df["ry"] = (df["ry"] - (n_s + 1) / 2) / n_s   # centred, scale-free
    g = pd.DataFrame({"n": 1.0, "xy": df["rx"] * df["ry"], "xx": df["rx"] ** 2, "yy": df["ry"] ** 2}).groupby(df["b"].to_numpy()).sum()
    G = g.to_numpy(float)

    def val(M):
        return M[:, 1].sum() / np.sqrt(M[:, 2].sum() * M[:, 3].sum())
    rng = np.random.default_rng(0)
    bs = [val(G[rng.integers(0, len(G), len(G))]) for _ in range(2000)]
    return float(val(G)), (float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))), len(G)


def lift(x: np.ndarray, hit: np.ndarray, block: np.ndarray, thr: float):
    """Hit rate among bars with x > thr over the hit rate of all bars (pooled); interval by resampling blocks."""
    df = pd.DataFrame({"x": x, "h": hit.astype(float), "b": block}).dropna()
    df["top"] = (df["x"] > thr).astype(float)
    g = df.groupby("b").agg(nh=("h", "sum"), n=("h", "size"), th=("top", lambda s: 0.0), tn=("top", "sum"))
    g["th"] = (df["h"] * df["top"]).groupby(df["b"]).sum()
    G = g.to_numpy(float)

    def val(M):
        base = M[:, 0].sum() / max(M[:, 1].sum(), 1); top = M[:, 2].sum() / max(M[:, 3].sum(), 1)
        return top / base if base > 0 else np.nan
    rng = np.random.default_rng(1)
    bs = [val(G[rng.integers(0, len(G), len(G))]) for _ in range(2000)]
    return float(val(G)), (float(np.nanpercentile(bs, 2.5)), float(np.nanpercentile(bs, 97.5))), int(G[:, 3].sum())


def calibration(score: np.ndarray, hit: np.ndarray, edges: np.ndarray):
    """Realized hit rate per score decile (edges from train) and the slope of hit rate on decile number."""
    df = pd.DataFrame({"s": score, "h": hit.astype(float)}).dropna()
    df["dec"] = np.clip(np.searchsorted(edges, df["s"].to_numpy()), 0, len(edges))
    tab = df.groupby("dec")["h"].agg(["mean", "size"])
    if len(tab) < 3:
        return tab, np.nan
    slope = np.polyfit(tab.index.to_numpy(float), tab["mean"].to_numpy(), 1)[0]
    return tab, float(slope)
