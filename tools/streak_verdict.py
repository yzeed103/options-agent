"""Step 3 of reports/conviction_ma/PREREG_STREAK.md: the streak average vs every baseline on real SIP bars, matched lag.

    python tools/streak_verdict.py              # lag matched by drift lag (pre-registered) -> streak_verdict.json
    python tools/streak_verdict.py --lag trend  # cross-check: lag inside trends -> streak_verdict_trend.json
"""
from __future__ import annotations

import json
import os
import sys
import time

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("VZ_TAG", "sip")
from vzones import conviction_ma as CM  # noqa: E402
from vzones.assistant import data as D  # noqa: E402

OUT = os.path.join(ROOT, "reports", "conviction_ma")
SYMS = sorted(f[:-7] for f in os.listdir(D.BARS) if f.endswith("_5m.csv"))
TUNE = ["SPY", "QQQ", "AAPL", "AMZN", "META", "NVDA", "TSLA", "AMD", "PLTR", "COIN"]
INDEX = {"SPY", "QQQ"}
MEGA = {"AAPL", "AMZN", "META", "NVDA", "AVGO", "TSLA", "LLY", "ORCL", "COST", "JNJ", "UNH", "INTU", "NOW"}
BASE = [b for b in CM.BASELINES if b != "StreakEMA"]
CHOSEN = json.load(open(os.path.join(OUT, "streak_select.json")))["chosen"]
K = (CHOSEN["L_fast"], CHOSEN["L_slow"], CHOSEN["cap"], CHOSEN["p"])


def group(s):
    return "index" if s in INDEX else "mega" if s in MEGA else "high_beta"


def frames(sym):
    d5 = D.load_bars(sym)
    d5 = d5[(d5.index.time >= pd.Timestamp("09:30").time()) & (d5.index.time < pd.Timestamp("16:00").time())]
    agg = dict(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"))
    out = {"5m": d5}
    out["15m"] = d5.groupby(d5.index.floor("15min")).agg(**agg)
    k1 = (d5.index - pd.Timedelta(minutes=30)).floor("1h") + pd.Timedelta(minutes=30)    # 09:30, 10:30, ...
    out["1h"] = d5.groupby(k1).agg(**agg)
    out["daily"] = d5.groupby(d5.index.date).agg(**agg)
    return out


def arrays(df):
    return [df[c].to_numpy(float) for c in ("open", "high", "low", "close")]


def streak(o, h, l, c):
    return CM.streak_ema(o, h, l, c, *K)


def base_f(name, n):
    fb = CM.BASELINES[name]
    return lambda o, h, l, c: fb(o, h, l, c, CM.heikin_ashi(o, h, l, c)[3], n)


def drift_lag(f, o, h, l, c, mask, rel=1e-4):
    t = np.arange(len(c), dtype=float)
    mu = rel * np.nanmean(np.abs(np.diff(c)))
    d = (mu * t - (f(o + mu * t, h + mu * t, l + mu * t, c + mu * t) - f(o, h, l, c))) / mu
    m = mask.copy()
    m[: min(200, len(c) // 10) if len(c) < 2000 else max(200, len(c) // 10)] = False                          # warm-up
    return float(np.nanmean(d[m]))


LAGMODE = "trend" if "--lag" in sys.argv and sys.argv[sys.argv.index("--lag") + 1] == "trend" else "drift"
_LAB = {}


def trend_lag_real(f, o, h, l, c, mask):
    """lag inside trends (labels and slope from a forward-backward EMA(20) of the close, evaluation only):
    sum(dir * (close - M)) / sum(|slope|) over the trend bars of the mask"""
    key = (id(c), len(c))
    if key not in _LAB:
        atr = CM.rma(CM.true_range(h, l, c), 14)
        lab = CM.trend_labels(c, atr)
        e = pd.Series(c).ewm(span=20, adjust=False).mean().to_numpy()
        fb = pd.Series(e[::-1]).ewm(span=20, adjust=False).mean().to_numpy()[::-1]
        _LAB[key] = (lab, np.abs(np.r_[np.nan, np.diff(fb)]))
    lab, sl = _LAB[key]
    M = f(o, h, l, c)
    m = mask & (lab != 0) & np.isfinite(M) & np.isfinite(sl)
    m[: min(200, len(c) // 10) if len(c) < 2000 else max(200, len(c) // 10)] = False
    return float(np.sum(lab[m] * (c[m] - M[m])) / np.sum(sl[m]))


def lag_of(f, o, h, l, c, mask):
    return trend_lag_real(f, o, h, l, c, mask) if LAGMODE == "trend" else drift_lag(f, o, h, l, c, mask)


def match_len(name, data, target, nmax):
    """smallest n whose median drift lag (train bars) reaches the target; bisection, lag rises with n"""
    def lag(n):
        return float(np.median([lag_of(base_f(name, n), *a, m) for a, m in data]))
    lo, hi = 2, nmax
    llo, lhi = lag(lo), lag(hi)
    if target >= lhi:
        return hi, lhi
    while hi - lo > 1:
        mid = (lo + hi) // 2
        lm = lag(mid)
        if lm < target:
            lo, llo = mid, lm
        else:
            hi, lhi = mid, lm
    return (lo, llo) if abs(llo - target) <= abs(lhi - target) else (hi, lhi)


def block_stats(M, P, blocks, test):
    """per test block: steps, flips, sum|d2M|, sum|dP|, crosses, bars"""
    dm = np.sign(np.diff(M, prepend=np.nan))
    d2 = np.abs(np.diff(M, 2, prepend=[np.nan, np.nan]))
    dp = np.abs(np.diff(P, prepend=np.nan))
    s = np.sign(P - M)
    rows = {}
    for b in np.unique(blocks[test]):
        i = np.where((blocks == b) & test)[0]
        a = dm[i]; a = a[np.isfinite(a) & (a != 0)]
        ss = s[i]; ok = np.isfinite(ss) & (ss != 0); ss = ss[ok]
        rows[b] = (len(a), int(np.sum(a[1:] != a[:-1])), float(np.nansum(d2[i])), float(np.nansum(dp[i])),
                   int(np.sum(ss[1:] != ss[:-1])), len(i))
    return rows


def rel_ci(sa, sb, metric, rng, draws=2000):
    """1 - metric(streak)/metric(base), paired over blocks; bootstrap interval"""
    keys = sorted(set(sa) & set(sb))
    A = np.array([sa[k] for k in keys], float); B = np.array([sb[k] for k in keys], float)

    def m(X):
        if metric == "flips":
            return 100 * X[:, 1].sum() / X[:, 0].sum()
        if metric == "noise":
            return X[:, 2].sum() / X[:, 3].sum()
        return 100 * X[:, 4].sum() / X[:, 5].sum()                  # crosses per 100 bars
    pt = 1 - m(A) / m(B)
    bs = []
    for _ in range(draws):
        j = rng.integers(0, len(keys), len(keys))
        bs.append(1 - m(A[j]) / m(B[j]))
    return dict(streak=round(m(A), 4), base=round(m(B), 4), better_share=round(pt, 4),
                lo=round(float(np.percentile(bs, 2.5)), 4), hi=round(float(np.percentile(bs, 97.5)), 4))


def main():
    t0 = time.time()
    F = {s: frames(s) for s in SYMS}
    days = sorted(set().union(*[set(F[s]["daily"].index) for s in SYMS]))
    cut = days[int(0.6 * len(days))]
    res = {"lag": LAGMODE, "chosen": CHOSEN, "split": {"train_end_before": str(cut), "days": len(days)}, "tf": {}}
    rng = np.random.default_rng(0)
    for tf in ("5m", "15m", "1h", "daily"):
        A, MASK, BLK = {}, {}, {}
        for s in SYMS:
            df = F[s][tf]
            dd = np.array([x if tf == "daily" else x.date() for x in df.index])
            A[s] = arrays(df)
            MASK[s] = dd < cut
            BLK[s] = np.array([s] * len(dd)) if tf == "daily" else np.array([f"{s}|{x}" for x in dd])
        tune = SYMS if tf == "daily" else TUNE
        tdata = [(A[s], MASK[s]) for s in tune]
        target = float(np.median([lag_of(streak, *a, m) for a, m in tdata]))
        nmax = 100 if tf == "daily" else 300
        lens = {}
        for b in BASE:
            lens[b] = match_len(b, tdata, target, nmax)
            print(tf, b, lens[b], f"target {target:.2f}", f"{time.time() - t0:.0f}s", flush=True)
        stats = {"streak": {}}
        stats.update({b: {} for b in BASE})
        grp = {}
        for s in SYMS:
            o, h, l, c = A[s]
            P = CM.heikin_ashi(o, h, l, c)[3]
            test = ~MASK[s]
            for name, f in [("streak", streak)] + [(b, base_f(b, lens[b][0])) for b in BASE]:
                st = block_stats(f(o, h, l, c), P, BLK[s], test)
                stats[name].update(st)
            for k in stats["streak"]:
                grp.setdefault(k, group(s)) if k.startswith(s + "|") or k == s else None
        tab = {}
        for b in BASE:
            tab[b] = {"len": lens[b][0], "lag": round(lens[b][1], 2)}
            for met in ("flips", "noise", "whipsaws"):
                tab[b][met] = rel_ci(stats["streak"], stats[b], met, rng)
        by_group = {}
        if tf == "5m":
            for g in ("index", "mega", "high_beta"):
                ks = [k for k in stats["streak"] if grp.get(k) == g]
                by_group[g] = {b: {met: rel_ci({k: stats["streak"][k] for k in ks}, {k: stats[b][k] for k in ks}, met, rng, 1000)
                                   for met in ("flips", "noise")} for b in BASE}
        # best baseline per metric = the one with the lowest value; verdict rule
        best_f = min(BASE, key=lambda b: tab[b]["flips"]["base"])
        best_n = min(BASE, key=lambda b: tab[b]["noise"]["base"])
        f_ok, n_ok = tab[best_f]["flips"]["lo"] > 0, tab[best_n]["noise"]["lo"] > 0
        f_bad, n_bad = tab[best_f]["flips"]["hi"] < 0, tab[best_n]["noise"]["hi"] < 0
        verdict = "better" if (f_ok and n_ok) else "worse" if (f_bad or n_bad) else "equal"
        res["tf"][tf] = dict(streak_lag=round(target, 2), baselines=tab, groups=by_group,
                             best_flips=best_f, best_noise=best_n, verdict=verdict)
        print(tf, "VERDICT", verdict, "best flips", best_f, tab[best_f]["flips"], "best noise", best_n, tab[best_n]["noise"], flush=True)
        json.dump(res, open(os.path.join(OUT, "streak_verdict.json" if LAGMODE == "drift" else "streak_verdict_trend.json"), "w"), indent=1)
    print(f"{time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
