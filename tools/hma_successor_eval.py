"""Tests of reports/hma_successor/PREREG.md.

    python tools/hma_successor_eval.py select    # step 1: shape parameter per candidate on seen seeds + heat map data
    python tools/hma_successor_eval.py gate      # step 2: fresh seeds, pass / fail per candidate
    python tools/hma_successor_eval.py verdict   # step 3: real data, passing candidates, 4 timeframes
"""
from __future__ import annotations

import json
import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from vzones import conviction_ma as CM  # noqa: E402
from vzones import hma_successor as HS  # noqa: E402

OUT = os.path.join(ROOT, "reports", "hma_successor")
TARGET_LAG = 10.0


# ---------------- planted series with V reversals ----------------
def planted_v(seed: int, sig=0.1, drift=0.25):
    rng = np.random.default_rng(seed)
    segs = [("side", 200), ("up", 150), ("down", 150), ("up", 150), ("side", 150), ("down", 200)]
    c, lab = [], []
    x = 100.0
    level = x
    for kind, n in segs:
        if kind == "side":
            level = x
        for _ in range(n):
            if kind == "side":
                x += -0.08 * (x - level) + rng.normal(0, sig)
            else:
                x += (drift if kind == "up" else -drift) * sig + rng.normal(0, sig)
            c.append(x); lab.append({"side": 0, "up": 1, "down": -1}[kind])
    c = np.array(c); lab = np.array(lab)
    o = np.r_[c[0], c[:-1]] + rng.normal(0, 0.1 * sig, len(c))
    h = np.maximum(o, c) + np.abs(rng.normal(0, 0.4 * sig, len(c)))
    l = np.minimum(o, c) - np.abs(rng.normal(0, 0.4 * sig, len(c)))
    meta = {"sig": sig, "step": drift * sig, "turns": [(350, 1), (500, -1)],
            "trends": [(200, 350, 1), (350, 500, -1), (500, 650, 1), (800, 1000, -1)], "sides": [(0, 200), (650, 800)]}
    return o, h, l, c, lab, meta


def load(seeds):
    out = []
    for s in seeds:
        o, h, l, c, lab, meta = planted_v(s)
        ho, hh, hl, hc = CM.heikin_ashi(o, h, l, c)
        out.append(dict(o=o, h=h, l=l, c=c, lab=lab, meta=meta, hc=hc, hh=hh, hl=hl, atr=HS.ha_atr(o, h, l, c)))
    return out


def trend_lag_planted(M, d):
    v = []
    for a, b, sg in d["meta"]["trends"]:
        sl = slice(a + 60, b)
        v.append(np.nanmean(sg * (d["c"][sl] - M[sl])))
    return float(np.mean(v) / d["meta"]["step"])


def side_flips(M, d):
    dm = np.sign(np.diff(M))
    tot, n = 0, 0
    for a, b in d["meta"]["sides"]:
        s = dm[a:b]; s = s[s != 0]
        tot += int(np.sum(s[1:] != s[:-1])); n += len(s)
    return 100 * tot / max(n, 1)


def planted_scores(M, d):
    ov, td = [], []
    for t, old in d["meta"]["turns"]:
        tp = HS.turning_price(d["hh"], d["hl"], t, old)
        ov.append(HS.overshoot(M, t, old, tp, d["atr"][t]))
        td.append(HS.turn_delay(M, t, -old))
    return dict(overshoot=float(np.nanmean(ov)), delay=float(np.nanmean(td)), flips=side_flips(M, d))


# ---------------- candidates as f(d, length) with a shape value ----------------
def build(name, shape):
    """Returns (apply(d, n), kind). kind 'single' = one length; 'multi' = members matched one by one."""
    if name == "DHMA":
        return (lambda d, n: HS.dhma(d["hc"], n, shape)), "single"
    if name == "CHMA":
        return (lambda d, n: HS.chma(d["hc"], d["hh"], d["hl"], n, shape)), "single"
    if name == "HOLT":
        return (lambda d, n: HS.holt(d["hc"], n, shape)), "single"
    if name == "REF":
        return (lambda d, n: CM.hma(d["hc"], n)), "single"
    if name == "MED3":
        return None, "multi"
    if name == "BLEND":
        return None, "multi"
    raise ValueError(name)


MEMBERS = {"HMA": lambda d, n: CM.hma(d["hc"], n), "SS": lambda d, n: CM.supersmoother(d["hc"], n),
           "ALMA": lambda d, n: CM.alma(d["hc"], n)}


def match(apply, data, lagf, target, lo=2, hi=400):
    """Smallest length whose median lag reaches the target (bisection; lag rises with length)."""
    def lag(n):
        return float(np.median([lagf(apply(d, n), d) for d in data]))
    llo, lhi = lag(lo), lag(hi)
    if target >= lhi:
        return hi, lhi
    if target <= llo:
        return lo, llo
    while hi - lo > 1:
        mid = (lo + hi) // 2
        lm = lag(mid)
        if lm < target:
            lo, llo = mid, lm
        else:
            hi, lhi = mid, lm
    return (lo, llo) if abs(llo - target) <= abs(lhi - target) else (hi, lhi)


def matched_fn(name, shape, data, lagf, target):
    """(f(d) -> M, lengths dict, achieved lag) with every length matched to the target lag on `data`."""
    apply, kind = build(name, shape)
    if kind == "single":
        n, lg = match(apply, data, lagf, target)
        return (lambda d: apply(d, n)), {"n": n}, lg
    lens = {m: match(MEMBERS[m], data, lagf, target)[0] for m in (("HMA", "SS", "ALMA") if name == "MED3" else ("HMA", "SS"))}
    if name == "MED3":
        f = lambda d: HS.med3(d["hc"], lens["HMA"], lens["SS"], lens["ALMA"])  # noqa: E731
    else:
        f = lambda d: HS.blend(d["hc"], lens["HMA"], lens["SS"], shape)  # noqa: E731
    lg = float(np.median([lagf(f(d), d) for d in data]))
    return f, lens, lg


def score_set(f, data):
    rows = [planted_scores(f(d), d) for d in data]
    return {k: float(np.nanmedian([r[k] for r in rows])) for k in rows[0]}, rows


# ---------------- step 1 ----------------
def select():
    t0 = time.time()
    data = load(range(100))
    ref_f, ref_len, ref_lag = matched_fn("REF", None, data, trend_lag_planted, TARGET_LAG)
    ref, ref_rows = score_set(ref_f, data)
    res = {"target_lag": TARGET_LAG, "ref": {"len": ref_len, "lag": ref_lag, **ref}, "candidates": {}, "heat": {}}
    print("REF", ref_len, round(ref_lag, 2), ref, flush=True)
    for name, shapes in HS.SHAPES.items():
        rows = []
        for sh in shapes:
            f, lens, lg = matched_fn(name, sh, data, trend_lag_planted, TARGET_LAG)
            sc, _ = score_set(f, data)
            rows.append(dict(shape=sh, lens=lens, lag=round(lg, 2), **{k: round(v, 3) for k, v in sc.items()},
                             ok=bool(sc["delay"] <= ref["delay"] + 1 and sc["flips"] <= 1.10 * ref["flips"] and abs(lg - TARGET_LAG) <= 1.0)))
            print(name, rows[-1], f"{time.time() - t0:.0f}s", flush=True)
        ok = [r for r in rows if r["ok"]]
        chosen = min(ok, key=lambda r: r["overshoot"]) if ok else None
        res["candidates"][name] = {"rows": rows, "chosen": chosen}
        # heat map: shape x target lag -> overshoot reduction vs the reference at that lag
        heat = {}
        for tl in (5.0, 10.0, 15.0, 20.0):
            rf, _, _ = matched_fn("REF", None, data, trend_lag_planted, tl)
            r_sc, _ = score_set(rf, data)
            for sh in shapes:
                f, _, lg = matched_fn(name, sh, data, trend_lag_planted, tl)
                sc, _ = score_set(f, data)
                heat[f"{sh}|{tl}"] = round(1 - sc["overshoot"] / r_sc["overshoot"], 3) if r_sc["overshoot"] > 0 else None
        res["heat"][name] = heat
        print(name, "heat", heat, flush=True)
    os.makedirs(OUT, exist_ok=True)
    json.dump(res, open(os.path.join(OUT, "select.json"), "w"), indent=1)
    print(f"{time.time() - t0:.0f}s")


# ---------------- step 2 ----------------
def gate():
    sel = json.load(open(os.path.join(OUT, "select.json")))
    seen = load(range(100))                       # lengths are matched on the seen seeds, as the shape was
    fresh = load(range(10000, 10200))
    ref_f, ref_len, ref_lag = matched_fn("REF", None, seen, trend_lag_planted, TARGET_LAG)
    ref, ref_rows = score_set(ref_f, fresh)
    rng = np.random.default_rng(0)
    res = {"ref": {"len": ref_len, **ref}, "candidates": {}}
    for name, c in sel["candidates"].items():
        if not c["chosen"]:
            res["candidates"][name] = {"pass": False, "why": "no shape value met the step-1 constraints"}
            continue
        sh = c["chosen"]["shape"]
        f, lens, lg = matched_fn(name, sh, seen, trend_lag_planted, TARGET_LAG)
        sc, rows = score_set(f, fresh)
        a = np.array([r["overshoot"] for r in rows]); b = np.array([r["overshoot"] for r in ref_rows])
        m = np.isfinite(a) & np.isfinite(b) & (b > 0)
        rel = 1 - a[m] / b[m]
        bs = [np.mean(rel[rng.integers(0, len(rel), len(rel))]) for _ in range(4000)]
        lo, hi = float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))
        r = dict(shape=sh, lens=lens, lag_seen=round(lg, 2), fresh_lag=round(float(np.median([trend_lag_planted(f(d), d) for d in fresh])), 2),
                 **{k: round(v, 3) for k, v in sc.items()}, overshoot_reduction=round(float(np.mean(rel)), 3), lo=round(lo, 3), hi=round(hi, 3))
        r["pass"] = bool(r["overshoot_reduction"] >= 0.30 and lo > 0 and sc["delay"] <= ref["delay"] + 1 and sc["flips"] <= 1.10 * ref["flips"])
        res["candidates"][name] = r
        print(name, r, flush=True)
    res["any_pass"] = any(v.get("pass") for v in res["candidates"].values())
    json.dump(res, open(os.path.join(OUT, "gate.json"), "w"), indent=1)
    print(json.dumps(res["ref"]), "ANY PASS:", res["any_pass"])


# ---------------- step 3 ----------------
def verdict():
    import pandas as pd
    import streak_verdict as SV  # frames, arrays, trend_lag_real, SYMS, TUNE, group
    gt = json.load(open(os.path.join(OUT, "gate.json")))
    passing = [n for n, v in gt["candidates"].items() if v.get("pass")]
    if not passing:
        print("no passing candidate; nothing to run")
        return
    t0 = time.time()
    F = {s: SV.frames(s) for s in SV.SYMS}
    days = sorted(set().union(*[set(F[s]["daily"].index) for s in SV.SYMS]))
    cut = days[int(0.6 * len(days))]
    res = {"split": {"train_end_before": str(cut), "days": len(days)}, "passing": passing, "tf": {}}
    rng = np.random.default_rng(0)
    for tf in ("5m", "15m", "1h", "daily"):
        D, MASK, BLK = {}, {}, {}
        for s in SV.SYMS:
            df = F[s][tf]
            o, h, l, c = SV.arrays(df)
            ho, hh, hl, hc = CM.heikin_ashi(o, h, l, c)
            dd = np.array([x if tf == "daily" else x.date() for x in df.index])
            D[s] = dict(o=o, h=h, l=l, c=c, hc=hc, hh=hh, hl=hl, atr=HS.ha_atr(o, h, l, c))
            MASK[s] = dd < cut
            BLK[s] = np.array([s] * len(dd)) if tf == "daily" else np.array([f"{s}|{x}" for x in dd])
        tune = SV.SYMS if tf == "daily" else SV.TUNE
        tdata = [D[s] for s in tune]
        warm = {s: (200 if len(D[s]["c"]) >= 2000 else min(200, len(D[s]["c"]) // 10)) for s in SV.SYMS}

        def lagf_for(s):
            m = MASK[s].copy(); m[:warm[s]] = False
            return lambda M, d: SV.trend_lag_real(lambda *a: M, d["o"], d["h"], d["l"], d["c"], m)
        # lag on train bars of the tune symbols: wrap trend_lag_real so it gets the symbol's own mask
        tune_lag = lambda M, d: lagf_for(d["sym"])(M, d)  # noqa: E731
        for s in SV.SYMS:
            D[s]["sym"] = s
        fns = {}
        ref_f, ref_len, ref_lag = matched_fn("REF", None, tdata, tune_lag, TARGET_LAG)
        fns["REF"] = (ref_f, ref_len, ref_lag)
        for name in passing:
            sh = gt["candidates"][name]["shape"]
            fns[name] = matched_fn(name, sh, tdata, tune_lag, TARGET_LAG)
            print(tf, name, fns[name][1], round(fns[name][2], 2), f"{time.time() - t0:.0f}s", flush=True)
        # per block stats: flips (n, steps), noise (sum d2, sum dp), overshoot (sum, n), delay (sum, n)
        stats = {k: {} for k in fns}
        for s in SV.SYMS:
            d = D[s]; test = ~MASK[s]; test[:warm[s]] = False
            P = d["hc"]
            revs = [(t, old) for t, old in HS.reversals(d["c"], d["atr"]) if test[t]]
            for k, (f, _, _) in fns.items():
                M = f(d)
                dm = np.sign(np.diff(M, prepend=np.nan)); d2 = np.abs(np.diff(M, 2, prepend=[np.nan, np.nan])); dp = np.abs(np.diff(P, prepend=np.nan))
                sgn = np.sign(P - M)
                for b in np.unique(BLK[s][test]):
                    i = np.where((BLK[s] == b) & test)[0]
                    a = dm[i]; a = a[np.isfinite(a) & (a != 0)]
                    ss = sgn[i]; ss = ss[np.isfinite(ss) & (ss != 0)]
                    stats[k][b] = [len(a), int(np.sum(a[1:] != a[:-1])), float(np.nansum(d2[i])), float(np.nansum(dp[i])),
                                   int(np.sum(ss[1:] != ss[:-1])), len(i), 0.0, 0, 0.0, 0]
                for t, old in revs:
                    b = BLK[s][t]
                    tp = HS.turning_price(d["hh"], d["hl"], t, old)
                    ov = HS.overshoot(M, t, old, tp, d["atr"][t]); td = HS.turn_delay(M, t, -old)
                    if np.isfinite(ov):
                        stats[k][b][6] += ov; stats[k][b][7] += 1
                    if np.isfinite(td):
                        stats[k][b][8] += td; stats[k][b][9] += 1

        def metric(X, name):
            return {"flips": 100 * X[:, 1].sum() / max(X[:, 0].sum(), 1), "noise": X[:, 2].sum() / max(X[:, 3].sum(), 1e-12),
                    "whipsaws": 100 * X[:, 4].sum() / max(X[:, 5].sum(), 1), "overshoot": X[:, 6].sum() / max(X[:, 7].sum(), 1),
                    "delay": X[:, 8].sum() / max(X[:, 9].sum(), 1)}[name]

        def rel_ci(sa, sb, name, draws=2000):
            keys = sorted(set(sa) & set(sb))
            A = np.array([sa[k] for k in keys], float); B = np.array([sb[k] for k in keys], float)
            pt = 1 - metric(A, name) / metric(B, name)
            bs = []
            for _ in range(draws):
                j = rng.integers(0, len(keys), len(keys))
                bs.append(1 - metric(A[j], name) / metric(B[j], name))
            return dict(cand=round(metric(A, name), 4), ref=round(metric(B, name), 4), better_share=round(pt, 4),
                        lo=round(float(np.percentile(bs, 2.5)), 4), hi=round(float(np.percentile(bs, 97.5)), 4))
        tab = {"REF": {"len": fns["REF"][1], "lag": round(fns["REF"][2], 2), "reversals": int(sum(v[7] for v in stats["REF"].values()))}}
        for name in passing:
            t_ = {"len": fns[name][1], "lag": round(fns[name][2], 2)}
            for met in ("overshoot", "delay", "flips", "noise", "whipsaws"):
                t_[met] = rel_ci(stats[name], stats["REF"], met)
            ov, fl, nz = t_["overshoot"], t_["flips"], t_["noise"]
            not_worse = fl["lo"] >= -0.10 and nz["lo"] >= -0.10
            t_["verdict"] = "better" if (ov["lo"] > 0 and not_worse) else "equal" if (ov["lo"] <= 0 <= ov["hi"] and not_worse) else "worse"
            tab[name] = t_
            print(tf, name, "VERDICT", t_["verdict"], "overshoot", ov, "flips", fl, "noise", nz, flush=True)
        if tf == "5m":
            grp = {}
            for name in passing:
                grp[name] = {}
                for g in ("index", "mega", "high_beta"):
                    ks = [k for k in stats["REF"] if SV.group(k.split("|")[0]) == g]
                    grp[name][g] = {met: rel_ci({k: stats[name][k] for k in ks}, {k: stats["REF"][k] for k in ks}, met, 1000) for met in ("overshoot", "flips", "noise")}
            res["groups_5m"] = grp
        res["tf"][tf] = tab
        json.dump(res, open(os.path.join(OUT, "verdict.json"), "w"), indent=1)
    print(f"{time.time() - t0:.0f}s")


if __name__ == "__main__":
    {"select": select, "gate": gate, "verdict": verdict}[sys.argv[1]]()
