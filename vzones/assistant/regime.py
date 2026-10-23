"""Regime engine (reports/invention/PREREG.md): forecast the rest-of-day range from positioning + plain features, and
map the forecast to exits. Every rule here is the pre-registered one; nothing is tuned on the test dates."""
from __future__ import annotations

import json
import os
import sqlite3

import numpy as np
import pandas as pd

from .data import GEX_DB, RUNTIME
from .eyes import group_of

TIMES = {"10:00": 25, "11:00": 85, "12:00": 145}       # minute of the last bar closed by that time
B3_COLS = ["lvix", "latr", "lmorn", "gap", "g_index", "g_mega"]
P_COLS = B3_COLS + ["side", "dflip", "dwall", "regime", "gexn"]
RIDGE = 1.0
COST_BP = 2.0                                          # per side


def net_gex_prev(sym: str, days: list) -> pd.Series:
    """Day D -> the previous market date's net GEX (basis 'oi') normalised by the mean |net GEX| of that symbol's
    previous 20 rows (past only, at least 5). Also the raw sign."""
    if not os.path.exists(GEX_DB):
        return pd.Series(dtype=float), pd.Series(dtype=float)
    c = sqlite3.connect(f"file:{GEX_DB}?mode=ro", uri=True)
    try:
        q = pd.read_sql_query("select market_date, net_gex from daily_levels where symbol=? and basis='oi' order by market_date", c, params=(sym,))
    finally:
        c.close()
    if q.empty:
        return pd.Series(dtype=float), pd.Series(dtype=float)
    q["md"] = pd.to_datetime(q.market_date).dt.date
    scale = q.net_gex.abs().shift(1).rolling(20, min_periods=5).mean()
    q["norm"] = q.net_gex / scale
    import bisect
    md = list(q.md)
    norm, sign = {}, {}
    for d in days:
        j = bisect.bisect_left(md, d) - 1
        if j >= 0 and (d - md[j]).days <= 5:
            norm[d] = q.norm.iat[j]
            sign[d] = 1.0 if q.net_gex.iat[j] > 0 else 0.0
    return pd.Series(norm, dtype=float), pd.Series(sign, dtype=float)


def rows_for_symbol(sym: str, d5: pd.DataFrame, live_day=None) -> list[dict]:
    """One row per (day, update time) with the features known at that time and, when the day is complete, the target."""
    sess = d5["session"].to_numpy()
    days = sorted(set(sess)) if live_day is None else [live_day]
    gn, gs = net_gex_prev(sym, days)
    out = []
    o, h, l, c = (d5[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    minute = d5["minute"].to_numpy()
    bounds = np.r_[0, np.flatnonzero(sess[1:] != sess[:-1]) + 1, len(d5)]
    grp = group_of(sym)
    for b0, b1 in zip(bounds[:-1], bounds[1:]):
        day = sess[b0]
        if live_day is not None and day != live_day:
            continue
        datr, F = float(d5["datr"].iat[b0]), float(d5["flip"].iat[b0])
        if not (np.isfinite(datr) and datr > 0 and np.isfinite(F)):
            continue
        vix = float(d5["vix"].iat[b0])
        walls = [float(d5[k].iat[b0]) for k in ("cw", "pw") if np.isfinite(float(d5[k].iat[b0]))]
        for name, m in TIMES.items():
            k = np.flatnonzero(minute[b0:b1] == m)
            if not len(k):
                continue
            i = b0 + int(k[0])
            rest = slice(i + 1, b1)
            complete = (b1 - i - 1) >= 10 and minute[b1 - 1] >= 385
            y = (h[rest].max() - l[rest].min()) / datr if complete else np.nan
            ct = c[i]
            out.append(dict(sym=sym, date=day, time=name, i=int(i), y=y, close=ct, datr=datr, price=ct,
                            lvix=np.log(vix) if np.isfinite(vix) and vix > 0 else np.nan,
                            latr=np.log(datr / ct), lmorn=np.log((h[b0:i + 1].max() - l[b0:i + 1].min()) / datr + 0.02),
                            gap=abs(o[b0] - (c[b0 - 1] if b0 > 0 else o[b0])) / datr,
                            g_index=float(grp == "index"), g_mega=float(grp == "mega"),
                            side=1.0 if ct > F else -1.0, dflip=abs(ct - F) / datr,
                            dwall=min(abs(ct - w) for w in walls) / datr if walls else np.nan,
                            regime=gs.get(day, np.nan), gexn=gn.get(day, np.nan)))
    return out


# ---------------- models ----------------
class Ridge:
    def __init__(self, cols, alpha=RIDGE):
        self.cols, self.alpha = cols, alpha

    def fit(self, df):
        X = df[self.cols].to_numpy(float)
        self.mu, self.sd = X.mean(0), X.std(0) + 1e-12
        Z = (X - self.mu) / self.sd
        t = np.log(df.y.to_numpy(float) + 0.02)
        self.b0 = t.mean()
        A = Z.T @ Z + self.alpha * np.eye(Z.shape[1])
        self.w = np.linalg.solve(A, Z.T @ (t - self.b0))
        return self

    def predict(self, df):
        Z = (df[self.cols].to_numpy(float) - self.mu) / self.sd
        return np.exp(self.b0 + Z @ self.w) - 0.02

    def to_dict(self):
        return dict(cols=self.cols, mu=self.mu.tolist(), sd=self.sd.tolist(), b0=float(self.b0), w=self.w.tolist())

    @classmethod
    def from_dict(cls, d):
        r = cls(d["cols"]); r.mu, r.sd, r.b0, r.w = np.array(d["mu"]), np.array(d["sd"]), d["b0"], np.array(d["w"])
        return r


def fit_all(train: pd.DataFrame) -> dict:
    """{time: {'B1': median, 'B2': {sym: median}, 'B3': Ridge, 'P': Ridge}} fitted on train rows."""
    m = {}
    for t, g in train.groupby("time"):
        b2 = {s: float(x.y.median()) for s, x in g.groupby("sym") if len(x) >= 20}
        m[t] = {"B1": float(g.y.median()), "B2": b2, "B3": Ridge(B3_COLS).fit(g), "P": Ridge(P_COLS).fit(g)}
    return m


def predict(models: dict, df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for k in ("B1", "B2", "B3", "P"):
        out[f"f_{k}"] = np.nan
    for t, g in df.groupby("time"):
        mm = models[t]
        out.loc[g.index, "f_B1"] = mm["B1"]
        out.loc[g.index, "f_B2"] = [mm["B2"].get(s, mm["B1"]) for s in g.sym]
        out.loc[g.index, "f_B3"] = mm["B3"].predict(g)
        out.loc[g.index, "f_P"] = mm["P"].predict(g)
    return out


def usable(df: pd.DataFrame) -> pd.DataFrame:
    return df.dropna(subset=["y"] + P_COLS)


def save_models(models: dict, path: str) -> None:
    json.dump({t: {"B1": m["B1"], "B2": m["B2"], "B3": m["B3"].to_dict(), "P": m["P"].to_dict()} for t, m in models.items()},
              open(path, "w", encoding="utf-8"), indent=1)


def load_models(path: str) -> dict:
    d = json.load(open(path, encoding="utf-8"))
    return {t: {"B1": m["B1"], "B2": m["B2"], "B3": Ridge.from_dict(m["B3"]), "P": Ridge.from_dict(m["P"])} for t, m in d.items()}


def boot_mae_diff(df, a, b, n=2000, seed=0):
    """MAE(a) - MAE(b) of the target y, resampling whole dates; rel = the difference as a share of MAE(a)."""
    ea, eb = (df[a] - df.y).abs().to_numpy(), (df[b] - df.y).abs().to_numpy()
    g = pd.factorize(df.date.astype(str))[0]; k = g.max() + 1
    sa, sb, cn = np.bincount(g, ea, k), np.bincount(g, eb, k), np.bincount(g, None, k)
    dr = np.random.default_rng(seed).integers(0, k, (n, k))
    bs = (sa[dr].sum(1) - sb[dr].sum(1)) / cn[dr].sum(1)
    return dict(diff=float(ea.mean() - eb.mean()), lo=float(np.percentile(bs, 2.5)), hi=float(np.percentile(bs, 97.5)),
                rel=float((ea.mean() - eb.mean()) / ea.mean()))


# ---------------- execution ----------------
def stops_for(f_range_atr: float, datr: float, price: float):
    """Pre-registered mapping: stop = 0.25 x forecast remaining range; target = 2 x stop; no trade when the round-trip
    cost exceeds 15% of the stop."""
    stop = 0.25 * f_range_atr * datr
    ok = stop > 0 and (2 * COST_BP * 1e-4 * price) <= 0.15 * stop
    return stop, ok


def simulate_arm(d5: pd.DataFrame, entries: list[int], stop_of) -> list[dict]:
    """entries: signal bar indices (side from sig_tl). stop_of(i) -> (stop distance, ok) or None for the ATR arm."""
    o, h, l, c = (d5[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    sess, sig = d5["session"].to_numpy(), d5["sig_tl"].to_numpy()
    n = len(d5)
    last = np.r_[sess[1:] != sess[:-1], True]
    out, busy = [], -1
    for i in entries:
        if i <= busy or last[i] or i + 1 >= n:
            continue
        s = int(sig[i])
        stop, ok = stop_of(i)
        if not ok:
            out.append(dict(i=i, date=sess[i], skipped=True))
            continue
        e = i + 1; entry = o[e]
        st, tg = entry - s * stop, entry + s * 2 * stop
        j = e; px = None
        while True:
            if j > e:
                if (o[j] - st) * s <= 0: px = o[j]; break
                if (o[j] - tg) * s >= 0: px = o[j]; break
            if (l[j] <= st) if s > 0 else (h[j] >= st): px = st; break
            if (h[j] >= tg) if s > 0 else (l[j] <= tg): px = tg; break
            if last[j]: px = c[j]; break
            j += 1
        busy = j
        out.append(dict(i=i, date=sess[i], skipped=False, net_bp=1e4 * s * (px - entry) / entry - 2 * COST_BP,
                        gross_bp=1e4 * s * (px - entry) / entry))
    return out
