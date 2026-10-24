"""Volatility engine v2: shared machinery for reports/vol_engine_dev/PREREG.md.

A "frame" is a dict of numpy arrays for one symbol (real or synthetic): o h l c v, sess (session id per bar),
slot (bar index inside the session), tod (time-of-day bin), r (session log returns), s2 (EWMA variance), move (24-bar
expected move in price), A (ATR14), comp (ATR14/ATR100), heat (percent rank), hb (heat bin), sq (squeeze state),
sq_in (bars inside), st (Hull state), S0, conf (damped line confirms), rvol, train (bool), and per-session arrays.
Every tool below works on a frame, so the planted tests and the real data share one code path."""
from __future__ import annotations

import numpy as np
import pandas as pd

from vzones import regimes as RG
from vzones import vol_engine as VE
from vzones import volume_tool as VT

K = 24
LAM = 0.99
NBAR = 78
HEAT_N = 500
COST = 5e-4


# ---------------- frame building ----------------
def ewma_s2(r: np.ndarray, lam: float = LAM) -> np.ndarray:
    return VE.ewma_var(r, lam)


def comp_ratio(h, l, c):
    tr = np.r_[h[0] - l[0], np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))]
    a14 = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().to_numpy(); a100 = pd.Series(tr).ewm(alpha=1 / 100, adjust=False).mean().to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(a100 > 0, a14 / a100, np.nan), a14


def forward(c, k):
    f = np.full(len(c), np.nan); f[:-k] = c[k:] - c[:-k]; return f


def fwd_range(h, l, k):
    """log(max high / min low) over the next k bars (t+1..t+k)"""
    hh = pd.Series(h).shift(-1)[::-1].rolling(k).max()[::-1].to_numpy(); ll = pd.Series(l).shift(-1)[::-1].rolling(k).min()[::-1].to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.log(hh / ll)


def base_frame(o, h, l, c, v, sess, slot, tod, train, sq_thr=RG.SQZ_THR[5]):
    """everything that does not need the trend model"""
    n = len(c)
    new = np.r_[True, sess[1:] != sess[:-1]]
    with np.errstate(invalid="ignore", divide="ignore"):
        r = np.where(new, np.log(c / o), np.log(c / np.r_[np.nan, c[:-1]]))
    s2 = ewma_s2(r); move = np.sqrt(K * s2) * c
    comp, A = comp_ratio(h, l, c)
    with np.errstate(invalid="ignore", divide="ignore"):
        heat = RG.percent_rank(move / c, HEAT_N)
    hb = RG.heat_bin(heat); sq, sq_in = RG.squeeze_state(comp, sq_thr)
    F = dict(o=o, h=h, l=l, c=c, v=v, sess=sess, slot=slot, tod=tod, new=new, r=r, s2=s2, move=move, A=A, comp=comp, heat=heat, hb=hb, sq=sq, sq_in=sq_in, train=train, n=n)
    F["z24"] = forward(c, K) / move
    F["R24"] = fwd_range(h, l, 24); F["R12"] = fwd_range(h, l, 12)
    # session-level: open, s2 at the first bar, m_day, running high/low, fuel
    s_open = np.full(n, np.nan); s2o = np.full(n, np.nan); hi = np.full(n, np.nan); lo = np.full(n, np.nan)
    starts = np.where(new)[0]; ends = np.r_[starts[1:], n]
    for a, b in zip(starts, ends):
        s_open[a:b] = o[a]; s2o[a:b] = s2[a]; hi[a:b] = np.maximum.accumulate(h[a:b]); lo[a:b] = np.minimum.accumulate(l[a:b])
    m_day = np.sqrt(NBAR * s2o) * s_open
    gap = np.full(n, np.nan)
    for j, a in enumerate(starts):
        if j > 0:
            gap[a:ends[j]] = np.log(o[a] / c[starts[j] - 1])
    F["gap"] = gap
    F.update(s_open=s_open, s2o=s2o, m_day=m_day, run_hi=hi, run_lo=lo, fuel=(hi - lo) / (2 * m_day), day_hi=s_open + m_day, day_lo=s_open - m_day)
    return F


def add_trend(F, bars: pd.DataFrame | None, rvol=None):
    n = F["n"]
    if bars is None:
        F["st"] = np.zeros(n, int); F["S0"] = np.full(n, np.nan); F["conf"] = np.zeros(n, bool)
    else:
        F["st"] = bars["state"].to_numpy().astype(int); F["S0"] = bars["S0"].to_numpy(float); F["conf"] = bars["confirmed"].to_numpy().astype(bool)
    F["rvol"] = rvol if rvol is not None else np.full(n, np.nan)
    return F


# ---------------- bootstrap helpers ----------------
def boot_mean(x, block, draws=1000, seed=0):
    """mean of x with a bootstrap interval over blocks"""
    ok = np.isfinite(x); x = x[ok]; bl = np.asarray(block)[ok]
    if len(x) == 0:
        return dict(mean=np.nan, lo=np.nan, hi=np.nan, n=0, blocks=0)
    u, inv = np.unique(bl, return_inverse=True); sums = np.bincount(inv, weights=x); cnt = np.bincount(inv).astype(float)
    rng = np.random.default_rng(seed); m = len(u)
    bs = []
    for _ in range(draws):
        p = rng.integers(0, m, m); bs.append(sums[p].sum() / cnt[p].sum())
    return dict(mean=round(float(x.mean()), 5), lo=round(float(np.percentile(bs, 2.5)), 5), hi=round(float(np.percentile(bs, 97.5)), 5), n=int(len(x)), blocks=int(m))


def boot_diff(a, b, block, draws=1000, seed=0):
    return boot_mean(np.asarray(a, float) - np.asarray(b, float), block, draws, seed)


def excludes0(d):
    return bool(np.isfinite(d["lo"]) and (d["lo"] > 0 or d["hi"] < 0))


def pinball(y, q, tau):
    e = y - q
    return np.where(e >= 0, tau * e, (tau - 1) * e)


# ---------------- T1 fan ----------------
def fan_quantiles(z_train):
    z = z_train[np.isfinite(z_train)]
    from scipy import stats
    df, loc, sc = stats.t.fit(z, floc=0)
    return dict(q025=float(np.percentile(z, 2.5)), q16=float(np.percentile(z, 16)), q84=float(np.percentile(z, 84)), q975=float(np.percentile(z, 97.5)), t_df=float(df), t_scale=float(sc), n=int(len(z)))


def band_stats(z, q_lo, q_hi, block, tau=(0.16, 0.84)):
    """coverage of [q_lo, q_hi] and the pinball loss at tau for a standardized move z (per bar)"""
    ok = np.isfinite(z)
    cov = np.where(ok, (z >= q_lo) & (z <= q_hi), np.nan).astype(float)
    pb = np.where(ok, pinball(z, q_lo, tau[0]) + pinball(z, q_hi, tau[1]), np.nan)
    return cov, pb


def slot_profile(F, nslots=NBAR):
    """train slot factors f_j = median over sessions of r_j^2 / mean_session(r^2), normalized to mean 1"""
    r2 = F["r"] ** 2; tr = F["train"]
    df = pd.DataFrame({"r2": r2, "sess": F["sess"], "slot": F["slot"]})[tr]
    df["m"] = df.groupby("sess")["r2"].transform("mean"); df = df[df["m"] > 0]; df["x"] = df["r2"] / df["m"]
    prof = df.groupby("slot")["x"].median().reindex(range(nslots)).interpolate().bfill().ffill().to_numpy()
    prof = prof / prof.mean()
    return prof


def seasonal_var(F, prof, k=K):
    """EWMA on deseasonalized r^2, forecast = s2_deseason x sum of the next k slot factors (wrapping into the next session)"""
    f = prof[np.clip(F["slot"], 0, len(prof) - 1)]
    rd = F["r"] / np.sqrt(f)
    s2d = ewma_s2(rd)
    ext = np.r_[prof, prof]; cs = np.cumsum(np.r_[0.0, ext])
    sl = np.clip(F["slot"], 0, len(prof) - 1); nxt = cs[sl + 1 + k] - cs[sl + 1]
    return s2d * nxt / k, s2d


def horizon_alpha(F, ks=(3, 6, 12, 24, 48)):
    """per symbol-day block: slope of log mean|move_k / sqrt(s2)| vs log k; returns the per-block slopes"""
    c, s2 = F["c"], F["s2"]; rows = {}
    for k in ks:
        m = np.abs(forward(c, k)) / (np.sqrt(s2) * c); rows[k] = m
    df = pd.DataFrame(rows); df["b"] = F["sess"]; df = df[F["train"]]
    g = df.groupby("b").mean(); g = g[(g > 0).all(axis=1)]
    lk = np.log(np.array(ks, float)); lk = lk - lk.mean()
    slopes = (np.log(g.to_numpy()) * lk).sum(axis=1) / (lk ** 2).sum()
    return slopes


# ---------------- T2 exits ----------------
def exits(F):
    c, move = F["c"], F["move"]; n = F["n"]
    up = np.zeros(n, bool); dn = np.zeros(n, bool)
    up[K:] = c[K:] > c[:-K] + move[:-K]; dn[K:] = c[K:] < c[:-K] - move[:-K]
    ok = np.isfinite(move)
    return up & ok, dn & ok


# ---------------- random matched control ----------------
def matched_random(F, t, pool_by_slot, rng, m=20):
    p = pool_by_slot.get(int(F["slot"][t]))
    if p is None or len(p) < 30:
        return None
    return p[rng.integers(0, len(p), m)]


def pools_by_slot(F, mask):
    idx = np.where(mask)[0]; sl = F["slot"][idx]
    return {int(s): idx[sl == s] for s in np.unique(sl)}


# ---------------- trades ----------------
def sim_trade(F, t, dr, stop, target, horizon, trail=None, cost=COST):
    """entry at close[t]; stop/target are price distances; trail = distance for a trailing stop (None = fixed).
    Returns (pnl fraction after costs, outcome: 1 target, -1 stop, 0 horizon, mae fraction, bars)."""
    h, l, c = F["h"], F["l"], F["c"]; e = c[t]; n = F["n"]
    sl = e - dr * stop; tg = e + dr * target; best = e; mae = 0.0
    for j in range(t + 1, min(n, t + horizon + 1)):
        if trail is not None:
            best = max(best, h[j]) if dr > 0 else min(best, l[j]); sl = max(sl, best - trail) if dr > 0 else min(sl, best + trail)
        adverse = (e - l[j]) if dr > 0 else (h[j] - e); mae = max(mae, adverse)
        hit_s = l[j] <= sl if dr > 0 else h[j] >= sl
        hit_t = h[j] >= tg if dr > 0 else l[j] <= tg
        if hit_s:
            return dr * (sl - e) / e - 2 * cost, -1, mae / e, j - t
        if hit_t:
            return dr * (tg - e) / e - 2 * cost, 1, mae / e, j - t
    j = min(n - 1, t + horizon)
    return dr * (c[j] - e) / e - 2 * cost, 0, mae / e, j - t


def trend_entries(F, mask, gap=K):
    """one entry per symbol per `gap` bars where the Hull state is non-zero and confirmed"""
    st, conf = F["st"], F["conf"]; out = []; last = -10 ** 9
    for t in np.where(mask & (st != 0) & conf & np.isfinite(F["move"]))[0]:
        if t - last >= gap and F["slot"][t] < NBAR - 2:
            out.append((int(t), int(st[t]))); last = t
    return out


def nearest_adverse_level(levels: dict, e: float, dr: int):
    """distance to the nearest level beyond the entry on the adverse side (below for longs)"""
    best = np.nan
    for L in levels.values():
        if not np.isfinite(L):
            continue
        d = (e - L) if dr > 0 else (L - e)
        if d > 0 and (not np.isfinite(best) or d < best):
            best = d
    return best


# ---------------- T5 squeeze definitions ----------------
def squeeze_defs(F, thr_bb=None, thr_rv=None):
    h, l, c, r = F["h"], F["l"], F["c"], F["r"]
    ma = pd.Series(c).rolling(20).mean().to_numpy(); sd = pd.Series(c).rolling(20).std().to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        bbw = 4 * sd / ma
    tr = np.r_[h[0] - l[0], np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))]
    kc = pd.Series(tr).rolling(20).mean().to_numpy() * 1.5
    kin = (sd * 2 < kc)                                     # Bollinger (20,2) inside Keltner (20,1.5)
    r2 = np.where(np.isfinite(r), r ** 2, np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        rv = pd.Series(r2).rolling(14).sum().to_numpy() / pd.Series(r2).rolling(100).sum().to_numpy() * (100 / 14)
    out = dict(atr=F["comp"] < RG.SQZ_THR[5], bbw=bbw, kin=kin, rv=rv)
    if thr_bb is not None:
        out["bb"] = bbw < thr_bb
    if thr_rv is not None:
        out["rvr"] = rv < thr_rv
    return out


def first_bars(mask):
    """indices where a boolean run starts"""
    m = np.asarray(mask, bool); return np.where(m & ~np.r_[False, m[:-1]])[0]


# ---------------- synthetic frames for the planted tests ----------------
def synth_frame(seed, world, sessions=300, nbar=NBAR):
    """worlds: gauss (iid normal), t4 (Student-t df 4), season (U-shaped slot variance), revert (pull back toward the
    open once the day range is used up), momo (continuation after band exits), garch (clustered variance),
    sqz (planted compressions followed by expansions), trendodds (targets hit more often with the planted drift)."""
    rng = np.random.default_rng(seed); n = sessions * nbar
    sess = np.repeat(np.arange(sessions), nbar); slot = np.tile(np.arange(nbar), sessions)
    sig = np.full(n, 0.0012)
    if world == "season":
        prof = 1.0 + 1.2 * np.cos(np.linspace(0, 2 * np.pi, nbar)) ** 2; prof /= prof.mean(); sig = sig * np.sqrt(prof[slot])
    if world == "t4":                                     # fat tails at the 24-bar horizon: a scale mixture the slow EWMA cannot track
        eps = rng.normal(0, 1, n); i = 0
        while i < n:
            L = int(rng.integers(30, 80)); eps[i:i + L] *= rng.choice([0.45, 1.0, 2.0]); i += L
    else:
        eps = rng.normal(0, 1, n)
    drift = np.zeros(n); mult = np.ones(n); st = np.zeros(n, int)
    if world == "garch":
        s = np.full(n, 1.0); e2 = eps ** 2
        for t in range(1, n):
            s[t] = 0.05 + 0.10 * e2[t - 1] * s[t - 1] + 0.85 * s[t - 1]
        mult = np.sqrt(s)
    if world == "sqz":
        i = 500
        while i + 120 < n:
            mult[i:i + 14] = 0.4                            # ATR14 crosses the squeeze line ~10-14 bars in; the expansion then falls inside the next 12 bars
            if rng.random() < 0.8:
                mult[i + 14:i + 38] = 2.0
            i += int(rng.integers(150, 250))
    if world == "trendodds":
        S0p = np.zeros(n)
        for k in range(sessions // 4):
            a = k * 4 * nbar; sg = 1 if k % 2 == 0 else -1; st[a:a + 2 * nbar] = sg
            drift[a:a + nbar] = 0.0008 * sg; S0p[a:a + nbar] = 0.8          # first half: strong, drifts
            drift[a + nbar:a + 2 * nbar] = 0.0; S0p[a + nbar:a + 2 * nbar] = 0.3   # second half: weak, no drift
    r = drift + sig * mult * eps
    c = np.zeros(n); o = np.zeros(n); lvl = 100.0
    for t in range(n):
        if slot[t] == 0:
            o[t] = lvl
        else:
            o[t] = c[t - 1]
        if world == "revert" and slot[t] > 0:
            a = t - slot[t]; m_day = np.sqrt(nbar) * 0.0012 * o[a]; used = (c[a:t].max() - c[a:t].min()) / (2 * m_day) if t > a else 0
            if used > 1.0:
                r[t] -= 0.25 * (c[t - 1] - o[a]) / o[a]
        if world == "momo" and t >= K and slot[t] >= 1:
            mv = np.sqrt(K) * sig[t] * c[t - K]
            if c[t - 1] > c[t - K] + mv:
                r[t] += 0.0006
            elif c[t - 1] < c[t - K] - mv:
                r[t] -= 0.0006
        c[t] = o[t] * np.exp(r[t])
        if slot[t] == nbar - 1:
            lvl = c[t] * np.exp(rng.normal(0, 0.002))
    wig = np.abs(rng.normal(0, 0.5, n)) * sig * mult
    h = np.maximum(o, c) * (1 + wig); l = np.minimum(o, c) * (1 - wig); v = rng.lognormal(10, 0.3, n)
    tod = np.where(slot < 6, 0, np.where(slot < 30, 1, np.where(slot < 48, 2, np.where(slot < 69, 3, 4))))
    train = sess < int(0.6 * sessions)
    F = base_frame(o, h, l, c, v, sess, slot, tod, train)
    F = add_trend(F, None)
    if world == "trendodds":
        F["st"] = st; F["conf"] = np.ones(n, bool); F["S0"] = S0p + rng.normal(0, 0.02, n)
    F["sym"] = f"S{seed}"; F["date"] = np.array([f"{world}{seed}|{s}" for s in sess])
    return F
