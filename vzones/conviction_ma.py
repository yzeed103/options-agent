"""Conviction moving average for Heikin Ashi candles (reports/conviction_ma/PREREG.md), its baselines and metrics.

Formula
-------
    candle      body = |c-o|, rng = h-l, atr = Wilder ATR(14) of the same candles
                d = +1 green, -1 red, 0 doji (body < 0.10 atr)
                q = clip(0.4 body/rng + 0.3 (1 - wrongWick/rng) + 0.3 min(1, body/atr), 0, 1)
                    wrongWick = upper wick of a red candle, lower wick of a green one
    conviction  S in [-1, 1]; sign = side, size = conviction
        law A   same side (or S = 0): S += g q d;   opposite: S -= (1-keep) q sign(S)   (may cross zero)
        law B   same side: S += g q d (1-|S|);       opposite: S *= 1 - (1-keep) q;  |S| < 0.05 -> S = g q d
        law C   S = (1-g) S + g q d
                doji (A, B): S *= 0.9
    speed       a = a_slow + (a_fast - a_slow) |S|^p,   a_x = 2 / (L_x + 1)
    average     M_t = M_{t-1} + a_t (src_t - M_{t-1}),  seeded with the SMA of the first L_slow sources

In words: every candle of the running colour adds conviction, more for a big body with no wick against it; an
opposite candle takes back only part of it; the more conviction, the faster the average follows the price; with
little conviction it is as slow as an EMA(L_slow).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd


# ---------------- candles ----------------
def heikin_ashi(o, h, l, c):
    o, h, l, c = (np.asarray(x, float) for x in (o, h, l, c))
    n = len(c)
    hc = (o + h + l + c) / 4
    ho = np.empty(n)
    if n:
        ho[0] = (o[0] + c[0]) / 2
    for i in range(1, n):
        ho[i] = (ho[i - 1] + hc[i - 1]) / 2
    hh = np.maximum(np.maximum(h, ho), hc)
    hl = np.minimum(np.minimum(l, ho), hc)
    return ho, hh, hl, hc


def rma(x, n: int) -> np.ndarray:
    """Pine ta.rma: SMA seed over the first n values, then Wilder smoothing."""
    x = np.asarray(x, float)
    out = np.full(len(x), np.nan)
    if len(x) < n:
        return out
    acc = float(np.mean(x[:n]))
    out[n - 1] = acc
    for i in range(n, len(x)):
        acc += (x[i] - acc) / n
        out[i] = acc
    return out


def true_range(h, l, c):
    pc = np.r_[np.nan, c[:-1]]
    return np.where(np.isnan(pc), h - l, np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc))))


def strength(o, h, l, c, atr):
    """(d, q) per candle (see the module docstring). Bars without ATR get q = 0."""
    body = np.abs(c - o)
    rng = h - l
    green = c > o
    wrong = np.where(green, np.minimum(o, c) - l, h - np.maximum(o, c))
    with np.errstate(divide="ignore", invalid="ignore"):
        bf = np.where(rng > 0, body / rng, 0.0)
        nw = np.where(rng > 0, 1 - wrong / rng, 0.0)
        sz = np.where(atr > 0, np.minimum(1.0, body / atr), 0.0)
    q = np.clip(0.4 * bf + 0.3 * nw + 0.3 * sz, 0, 1)
    q = np.where(np.isfinite(atr), q, 0.0)
    d = np.where(c > o, 1, np.where(c < o, -1, 0))
    d = np.where(np.isfinite(atr) & (body < 0.10 * np.nan_to_num(atr, nan=np.inf)), 0, d)
    return d.astype(int), q


def conviction(d, q, law: str = "A", g: float = 0.3, keep: float = 0.6) -> np.ndarray:
    d, q = list(map(int, d)), list(map(float, q))
    n = len(d)
    out = [0.0] * n
    s = 0.0
    for i in range(n):
        di, qi = d[i], q[i]
        if law == "C":
            s = (1 - g) * s + g * qi * di
        elif di == 0:
            s *= 0.9
        elif law == "A":
            if s == 0 or (s > 0) == (di > 0):
                s += g * qi * di
            else:
                s -= (1 - keep) * qi * (1 if s > 0 else -1)
            s = max(-1.0, min(1.0, s))
        else:  # B
            if s == 0 or (s > 0) == (di > 0):
                s += g * qi * di * (1 - abs(s))
            elif abs(s) < 0.05:
                s = g * qi * di
            else:
                s *= 1 - (1 - keep) * qi
        out[i] = s
    return np.array(out)


def adaptive(src, speed) -> np.ndarray:
    """M_t = M_{t-1} + a_t (src_t - M_{t-1}); a given per bar. Starts at the first finite source."""
    src, speed = list(map(float, src)), list(map(float, speed))
    out = [math.nan] * len(src)
    m = math.nan
    for i, (x, a) in enumerate(zip(src, speed)):
        if math.isnan(x):
            continue
        m = x if math.isnan(m) else m + a * (x - m)
        out[i] = m
    return np.array(out)


def conviction_ma(o, h, l, c, *, law="A", g=0.3, keep=0.6, p=1.0, L_fast=8, L_slow=60, use_ha=True, source="ha"):
    """Returns (M, S). Candles for the conviction: Heikin Ashi (use_ha) or the given ones. source: 'ha' (HA close),
    'close' (real close) or 'hl2'."""
    o, h, l, c = (np.asarray(x, float) for x in (o, h, l, c))
    co, ch, cl, cc = heikin_ashi(o, h, l, c) if use_ha else (o, h, l, c)
    atr = rma(true_range(ch, cl, cc), 14)
    d, q = strength(co, ch, cl, cc, atr)
    S = conviction(d, q, law, g, keep)
    af, as_ = 2 / (L_fast + 1), 2 / (L_slow + 1)
    a = as_ + (af - as_) * np.abs(S) ** p
    src = {"ha": heikin_ashi(o, h, l, c)[3], "close": c, "hl2": (h + l) / 2}[source]
    # seed like a Pine EMA: SMA of the first L_slow sources at bar L_slow-1, nothing before
    M = np.full(len(src), np.nan)
    if len(src) >= L_slow:
        m = float(np.mean(src[:L_slow]))
        M[L_slow - 1] = m
        s_, a_ = list(map(float, src)), list(map(float, a))
        for i in range(L_slow, len(src)):
            m += a_[i] * (s_[i] - m)
            M[i] = m
    return M, S


# ---------------- baselines ----------------
def ema(x, n):
    x = np.asarray(x, float)
    out = np.full(len(x), np.nan)
    if len(x) < n:
        return out
    a = 2 / (n + 1)
    m = float(np.mean(x[:n]))
    out[n - 1] = m
    xs = list(map(float, x))
    for i in range(n, len(x)):
        m += a * (xs[i] - m)
        out[i] = m
    return out


def sma(x, n):
    return pd.Series(x).rolling(n).mean().to_numpy()


def wma(x, n):
    w = np.arange(1, n + 1, dtype=float)
    return pd.Series(x).rolling(n).apply(lambda v: np.dot(v, w) / w.sum(), raw=True).to_numpy()


def hma(x, n):
    half, root = max(1, n // 2), max(1, int(round(math.sqrt(n))))
    return wma(2 * wma(x, half) - wma(x, n), root)


def alma(x, n, offset=0.85, sigma=6.0):
    m = offset * (n - 1)
    s = n / sigma
    w = np.exp(-((np.arange(n) - m) ** 2) / (2 * s * s))
    w /= w.sum()
    return pd.Series(x).rolling(n).apply(lambda v: np.dot(v, w), raw=True).to_numpy()


def kama(x, n=10, fast=2, slow=30):
    x = np.asarray(x, float)
    fs, ss = 2 / (fast + 1), 2 / (slow + 1)
    ch = np.abs(x - np.r_[np.full(n, np.nan), x[:-n]])
    vol = pd.Series(np.abs(np.diff(x, prepend=np.nan))).rolling(n).sum().to_numpy()
    er = np.where(vol > 0, ch / vol, 0)
    sc = (er * (fs - ss) + ss) ** 2
    sc = np.where(np.isfinite(sc), sc, ss * ss)
    return adaptive(x, sc)


def vidya(x, n=14, cmo_n=9):
    x = np.asarray(x, float)
    dx = np.diff(x, prepend=np.nan)
    up = pd.Series(np.where(dx > 0, dx, 0)).rolling(cmo_n).sum().to_numpy()
    dn = pd.Series(np.where(dx < 0, -dx, 0)).rolling(cmo_n).sum().to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        cmo = np.abs((up - dn) / (up + dn))
    a = 2 / (n + 1) * np.nan_to_num(cmo)
    return adaptive(x, a)


def mcginley(x, n):
    x = list(map(float, x))
    out = [math.nan] * len(x)
    m = math.nan
    for i, v in enumerate(x):
        if math.isnan(v):
            continue
        if math.isnan(m):
            m = v
        else:
            r = v / m if m else 1.0
            m = m + (v - m) / max(1e-9, n * r ** 4)
        out[i] = m
    return np.array(out)


def supersmoother(x, n):
    x = list(map(float, x))
    a1 = math.exp(-1.414 * math.pi / n)
    b1 = 2 * a1 * math.cos(1.414 * math.pi / n)
    c2, c3 = b1, -a1 * a1
    c1 = 1 - c2 - c3
    out = [math.nan] * len(x)
    for i in range(len(x)):
        if i < 2 or math.isnan(x[i - 1]) or math.isnan(out[i - 1]) or math.isnan(out[i - 2]):
            out[i] = x[i]
            continue
        out[i] = c1 * (x[i] + x[i - 1]) / 2 + c2 * out[i - 1] + c3 * out[i - 2]
    return np.array(out)


def streak_ema(o, h, l, c, L_fast=8, L_slow=60):
    """Speed by the Heikin Ashi colour-streak length only: |S| = min(streak, 10) / 10."""
    ho, hh, hl, hc = heikin_ashi(o, h, l, c)
    d = np.sign(hc - ho)
    streak = np.zeros(len(d))
    for i in range(1, len(d)):
        streak[i] = streak[i - 1] + 1 if d[i] == d[i - 1] and d[i] != 0 else 0
    s = np.minimum(streak, 10) / 10
    af, as_ = 2 / (L_fast + 1), 2 / (L_slow + 1)
    return adaptive(hc, as_ + (af - as_) * s)


BASELINES = {
    "EMA": lambda o, h, l, c, src, n: ema(src, n),
    "SMA": lambda o, h, l, c, src, n: sma(src, n),
    "HMA": lambda o, h, l, c, src, n: hma(src, n),
    "ALMA": lambda o, h, l, c, src, n: alma(src, n),
    "KAMA": lambda o, h, l, c, src, n: kama(src, max(2, n // 3), 2, max(10, n)),
    "VIDYA": lambda o, h, l, c, src, n: vidya(src, n),
    "McGinley": lambda o, h, l, c, src, n: mcginley(src, n),
    "SuperSmoother": lambda o, h, l, c, src, n: supersmoother(src, n),
    "StreakEMA": lambda o, h, l, c, src, n: streak_ema(o, h, l, c, max(2, n // 7), n),
}


# ---------------- metrics ----------------
def lag_drift(f, o, h, l, c, rel: float = 1e-4) -> float:
    """Lag in bars (PREREG change of 2026-10-23): run the filter f(o, h, l, c) on the candles and on the candles plus a
    tiny drift mu*t; lag = mean(mu*t - (M2 - M1)) / mu after the warm-up. Exact for linear filters: EMA(n) gives
    (n-1)/2 and SMA(n) gives (n-1)/2 (checked); for adaptive filters it is the local response to a slow trend."""
    o, h, l, c = (np.asarray(x, float) for x in (o, h, l, c))
    t = np.arange(len(c), dtype=float)
    mu = rel * np.nanmean(np.abs(np.diff(c)))
    m1 = np.asarray(f(o, h, l, c), float)
    m2 = np.asarray(f(o + mu * t, h + mu * t, l + mu * t, c + mu * t), float)
    d = (mu * t - (m2 - m1)) / mu
    d = d[np.isfinite(d)]
    return float(np.mean(d[len(d) // 5:])) if len(d) else np.nan


def lag(M, P, kmax=80) -> float:
    """DEPRECATED (the original pre-registered metric): bars k maximising corr(dM_t, dP_{t-k}). It scores 0 for every
    EMA length, so it cannot match lags; kept only to document why it was replaced."""
    dm, dp = np.diff(M), np.diff(P)
    ok = np.isfinite(dm) & np.isfinite(dp)
    dm, dp = dm[ok], dp[ok]
    if len(dm) < kmax * 3:
        return np.nan
    cs = []
    for k in range(kmax + 1):
        a, b = dm[k:], dp[:len(dp) - k]
        cs.append(np.corrcoef(a, b)[0, 1])
    cs = np.array(cs)
    k = int(np.nanargmax(cs))
    if 0 < k < kmax:
        y0, y1, y2 = cs[k - 1], cs[k], cs[k + 1]
        den = y0 - 2 * y1 + y2
        if den != 0:
            return k + 0.5 * (y0 - y2) / den
    return float(k)


def noise(M, P) -> float:
    d2 = np.abs(np.diff(M, 2))
    dp = np.abs(np.diff(P))
    return float(np.nanmean(d2) / np.nanmean(dp))


def flips(M) -> float:
    dm = np.sign(np.diff(M))
    dm = dm[np.isfinite(dm) & (dm != 0)]
    return float(100 * np.sum(dm[1:] != dm[:-1]) / max(len(dm), 1))


def whipsaws(M, P, sess) -> float:
    s = np.sign(P - M)
    ok = np.isfinite(s)
    cross = (s[1:] != s[:-1]) & ok[1:] & ok[:-1] & (s[1:] != 0)
    nd = len(set(sess))
    return float(cross.sum() / max(nd, 1))


def commit_dir(M, atr, thr=0.03):
    dm = np.r_[np.nan, np.diff(M)]
    with np.errstate(invalid="ignore"):
        return np.where(dm > thr * atr, 1, np.where(dm < -thr * atr, -1, 0))


def trend_labels(P, atr, n=20, thr=0.05, min_len=10):
    """Evaluation only (uses the future): forward-backward EMA slope; +1 / -1 trend, 0 sideways."""
    f = pd.Series(P).ewm(span=n, adjust=False).mean().to_numpy()
    fb = pd.Series(f[::-1]).ewm(span=n, adjust=False).mean().to_numpy()[::-1]
    sl = np.r_[np.nan, np.diff(fb)]
    with np.errstate(invalid="ignore"):
        lab = np.where(sl > thr * atr, 1, np.where(sl < -thr * atr, -1, 0))
    out = np.zeros_like(lab)
    i = 0
    while i < len(lab):
        j = i
        while j < len(lab) and lab[j] == lab[i]:
            j += 1
        if lab[i] != 0 and j - i >= min_len:
            out[i:j] = lab[i]
        i = j
    return out
