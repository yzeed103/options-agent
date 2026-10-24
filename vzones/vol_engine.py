"""Volatility engine (reports/vol_engine/PREREG.md): forecasts (EWMA, GARCH(1,1), HAR-RV) with controls (ATR, slot
range), expected-move bands and their coverage, squeeze events, vol-managed sizing, stop odds, the fear regime.
Forecasts and events use past bars only; the targets use the future (evaluation only)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from vzones import volume_tool as VT


# ---------------- returns and realized targets ----------------
def session_returns(d: pd.DataFrame, sess) -> np.ndarray:
    """log returns of closes inside a session; the first bar of a session uses its own open (no overnight jump)."""
    c = d["close"].to_numpy(float); o = d["open"].to_numpy(float)
    r = np.r_[np.nan, np.diff(np.log(c))]
    first = np.r_[True, sess[1:] != sess[:-1]]
    r[first] = np.log(c[first] / o[first])
    return r


def forward_var(r: np.ndarray, k: int) -> np.ndarray:
    """sum of the next k squared returns (t+1 .. t+k)"""
    s = pd.Series(r ** 2)
    return s[::-1].rolling(k).sum()[::-1].shift(-1).to_numpy()


def forward_move(c: np.ndarray, k: int) -> np.ndarray:
    return np.r_[np.log(c[k:] / c[:-k]), np.full(k, np.nan)]


# ---------------- forecasts ----------------
def ewma_var(r: np.ndarray, lam: float) -> np.ndarray:
    r2 = np.where(np.isfinite(r), r ** 2, np.nan)
    out = np.full(len(r2), np.nan); s = np.nan
    for i, x in enumerate(r2):
        if not np.isfinite(x):
            out[i] = s; continue
        s = x if not np.isfinite(s) else lam * s + (1 - lam) * x
        out[i] = s
    return out


def garch_fit(r: np.ndarray, iters: int = 300):
    """Gaussian QML GARCH(1,1) on a 1-d return series (NaNs skipped); returns (omega, alpha, beta).
    Fitted in a transformed space (omega = v e^a, alpha = sigmoid(b), beta = (1 - alpha) sigmoid(c)) so that the
    stationarity constraint holds everywhere and a gradient optimiser can be used."""
    from scipy.optimize import minimize
    x = r[np.isfinite(r)]; v = float(x.var()); x2 = x * x

    def unpack(p):
        w = v * np.exp(p[0]); a = 1 / (1 + np.exp(-p[1])); b = (1 - a) / (1 + np.exp(-p[2])) * 0.999
        return w, a, b

    def nll(p):
        w, a, b = unpack(p)
        s = v; tot = 0.0
        for xi2 in x2:                       # the variance of this return is built from the PREVIOUS ones
            tot += np.log(s) + xi2 / s
            s = w + a * xi2 + b * s
        return tot / len(x2)
    best = None
    for a0, b0 in ((0.05, 0.90), (0.10, 0.85), (0.03, 0.95), (0.2, 0.7)):
        p0 = [np.log(max(1e-6, 1 - a0 - b0)), np.log(a0 / (1 - a0)), np.log((b0 / (1 - a0)) / (1 - b0 / (1 - a0)))]
        res = minimize(nll, p0, method="Nelder-Mead", options={"maxiter": iters, "xatol": 1e-4, "fatol": 1e-7})
        if best is None or res.fun < best.fun:
            best = res
    return tuple(float(z) for z in unpack(best.x))


def garch_var(r: np.ndarray, params, k: int) -> np.ndarray:
    """k-step-ahead cumulative variance forecast at each bar"""
    w, a, b = params; r2 = np.where(np.isfinite(r), r ** 2, np.nan)
    lt = w / max(1e-12, 1 - a - b); phi = a + b
    out = np.full(len(r2), np.nan); s = np.nan
    for i, x in enumerate(r2):
        if not np.isfinite(x):
            continue
        s = lt if not np.isfinite(s) else w + a * x + b * s          # variance of the next bar given this bar
        # E[s_{t+j}] = lt + phi^(j-1) (s_{t+1} - lt); the k-step cumulative forecast is their sum
        tot = 0.0; e = s
        for j in range(k):
            tot += e; e = lt + phi * (e - lt)
        out[i] = tot
    return out


def har_fit(r2: np.ndarray, k: int, lags=(1, 12, 78)):
    """OLS of the next-k realized variance on the 1-, m-, l-bar means of r² (train); returns the coefficient vector."""
    X = har_design(r2, lags); y = pd.Series(r2)[::-1].rolling(k).sum()[::-1].shift(-1).to_numpy()
    ok = np.isfinite(X).all(1) & np.isfinite(y)
    A = np.c_[np.ones(ok.sum()), X[ok]]
    coef, *_ = np.linalg.lstsq(A, y[ok], rcond=None)
    return coef


def har_design(r2, lags):
    return np.c_[[pd.Series(r2).rolling(m, min_periods=max(1, m // 2)).mean().to_numpy() for m in lags]].T


def har_var(r2: np.ndarray, coef, lags=(1, 12, 78)) -> np.ndarray:
    X = har_design(r2, lags)
    v = coef[0] + X @ coef[1:]
    return np.where(v > 0, v, np.nan)


# ---------------- metrics ----------------
def qlike(V, Vhat):
    ok = np.isfinite(V) & np.isfinite(Vhat) & (V > 0) & (Vhat > 0)
    return float(np.mean(np.log(Vhat[ok]) + V[ok] / Vhat[ok])), int(ok.sum())


def mse_log(V, Vhat):
    ok = np.isfinite(V) & np.isfinite(Vhat) & (V > 0) & (Vhat > 0)
    return float(np.mean((np.log(V[ok]) - np.log(Vhat[ok])) ** 2))


def coverage(move, Vhat, z):
    ok = np.isfinite(move) & np.isfinite(Vhat) & (Vhat > 0)
    return float(np.mean(np.abs(move[ok]) <= z * np.sqrt(Vhat[ok]))), int(ok.sum())


# ---------------- squeeze ----------------
def bb_width(c, n=20, k=2.0):
    s = pd.Series(c); m = s.rolling(n).mean(); sd = s.rolling(n).std(ddof=0)
    return (2 * k * sd / m).to_numpy()


def squeeze_events(h, l, c, A, thr_atr: float, thr_bb: float):
    """first bars where ATR(14)/ATR(100) or the Bollinger width ratio crosses below its threshold"""
    A100 = pd.Series(np.maximum(h - l, 0)).ewm(alpha=1 / 100, adjust=False).mean().to_numpy()
    comp = A / np.where(A100 > 0, A100, np.nan)
    w = bb_width(c); wr = w / pd.Series(w).rolling(100).median().to_numpy()
    ev = []
    for name, x, thr in (("atr", comp, thr_atr), ("bb", wr, thr_bb)):
        below = x < thr
        for i in range(1, len(x)):
            if below[i] and not below[i - 1]:
                ev.append((i, name))
    return ev, comp, wr


# ---------------- stops ----------------
def first_touch(h, l, c, t, dr, up_d, dn_d, k):
    """which of the target (+up_d) or stop (-dn_d) distances is reached first within k bars; also the MAE before"""
    up = c[t] + dr * up_d; dn = c[t] - dr * dn_d; mae = 0.0
    for j in range(1, k + 1):
        if t + j >= len(c):
            return 0, mae
        adverse = dr * (c[t] - (l[t + j] if dr > 0 else h[t + j])); mae = max(mae, adverse)
        hit_up = (h[t + j] >= up) if dr > 0 else (l[t + j] <= up); hit_dn = (l[t + j] <= dn) if dr > 0 else (h[t + j] >= dn)
        if hit_up and hit_dn:
            return 0, mae
        if hit_up:
            return 1, mae
        if hit_dn:
            return -1, mae
    return 0, mae
