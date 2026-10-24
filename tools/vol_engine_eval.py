"""Tests of reports/vol_engine/PREREG.md.

    python tools/vol_engine_eval.py planted     # V1 constant-volatility world, V2 GARCH world with planted regimes
    python tools/vol_engine_eval.py verdict     # 5m and daily: forecasts, bands, squeeze, stops; sizing; fear regime
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
sys.path.insert(0, os.path.join(ROOT, "tools"))
os.environ.setdefault("VZ_TAG", "sip")
from vzones import vol_engine as VE  # noqa: E402
from vzones import volume_tool as VT  # noqa: E402
import volume_tool_eval as E  # noqa: E402

OUT = os.path.join(ROOT, "reports", "vol_engine")
UNI = os.path.join(ROOT, "runtime_sip", "daily_universe")
KS = {"5m": (6, 24), "D": (1, 5, 20)}
LAGS = {"5m": (1, 12, 78), "D": (1, 5, 22)}
NSQ = {"5m": 12, "D": 5}


def boot_diff(a, b, block, draws=2000, seed=0):
    """mean(a - b) with a bootstrap interval over blocks"""
    ok = np.isfinite(a) & np.isfinite(b)
    d = (a - b)[ok]; bl = block[ok]; u = np.unique(bl); idx = {x: np.where(bl == x)[0] for x in u}
    rng = np.random.default_rng(seed)
    bs = [d[np.concatenate([idx[u[p]] for p in rng.integers(0, len(u), len(u))])].mean() for _ in range(draws)]
    return dict(mean=round(float(d.mean()), 5), lo=round(float(np.percentile(bs, 2.5)), 5), hi=round(float(np.percentile(bs, 97.5)), 5), n=int(ok.sum()))


# ---------------- per-series forecasts ----------------
def forecasts(r, k, lam, gparams, hcoef, lags, A=None, c_atr=None, slot_var=None):
    out = {"EWMA": k * VE.ewma_var(r, lam), "GARCH": VE.garch_var(r, gparams, k), "HAR": VE.har_var(np.where(np.isfinite(r), r ** 2, np.nan), hcoef, lags)}
    if A is not None and c_atr is not None:
        out["ATR"] = c_atr * A ** 2
    if slot_var is not None:
        out["slot"] = slot_var
    return out


def fit_models(train_r_list, k, lags, lam_grid):
    """pooled, standardized fits: EWMA lambda by train QLIKE, GARCH params, HAR coefficients"""
    std = [np.nanstd(r) for r in train_r_list]
    Z = [r / s for r, s in zip(train_r_list, std) if s > 0]
    pooled = np.concatenate(Z)
    # a CONTIGUOUS subsample: the GARCH recursion needs the time order (a random subsample destroys the clustering)
    sub = pooled[np.isfinite(pooled)]; sub = sub[:60000]
    g = VE.garch_fit(sub)
    best = None
    for lam in lam_grid:
        q = np.nanmean([VE.qlike(VE.forward_var(z, k), k * VE.ewma_var(z, lam))[0] for z in Z[:10]])
        if best is None or q < best[1]:
            best = (lam, q)
    r2 = np.concatenate([np.where(np.isfinite(z), z ** 2, np.nan) for z in Z[:30]])
    h = VE.har_fit(r2, k, lags)
    return dict(lam=best[0], garch=g, har=[float(x) for x in h], std_note="fits on standardized returns; applied per symbol after rescaling")


def apply_fits(r, fits, k, lags):
    s = np.nanstd(r); z = r / s if s > 0 else r
    g = fits["garch"]; w, a, b = g
    e = k * VE.ewma_var(z, fits["lam"]) * s * s
    gv = VE.garch_var(z, (w, a, b), k) * s * s
    hv = VE.har_var(np.where(np.isfinite(z), z ** 2, np.nan), np.array(fits["har"]), lags) * s * s
    return {"EWMA": e, "GARCH": gv, "HAR": hv}


# ---------------- synthetic ----------------
def synth(seed, world, n=6000):
    rng = np.random.default_rng(seed)
    if world == "V1":
        sig = np.full(n, 0.01); r = rng.normal(0, 1, n) * sig; true_v = sig ** 2; regimes = np.zeros(n, int)
    else:
        w, a, b = 1e-6, 0.07, 0.90; s = np.full(n, w / (1 - a - b)); r = np.zeros(n); mult = np.ones(n); regimes = np.zeros(n, int)
        i = 400
        while i + 75 < n:                              # planted: 30 bars at 0.4x volatility, then 45 bars at 2x with p 0.8
            mult[i:i + 30] = 0.4; regimes[i:i + 30] = 1   # (ATR14 needs ~15-20 bars to cross the squeeze line, so the crossing lands shortly before the expansion)
            if rng.random() < 0.8:
                mult[i + 30:i + 75] = 2.0; regimes[i + 30:i + 75] = 2
            i += int(rng.integers(300, 500))
        for t in range(1, n):
            s[t] = w + a * r[t - 1] ** 2 + b * s[t - 1]
            r[t] = rng.normal(0, 1) * np.sqrt(s[t]) * mult[t]
        true_v = s * mult ** 2
    c = 100 * np.exp(np.cumsum(r)); o = np.r_[c[0], c[:-1]]
    hh = np.maximum(o, c) * (1 + np.abs(rng.normal(0, 0.3, n)) * np.sqrt(true_v)); ll = np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.3, n)) * np.sqrt(true_v))
    return r, c, hh, ll, true_v, regimes


def run_planted(seeds=range(70000, 70040)):
    t0 = time.time(); res = {}
    for world in ("V1", "V2"):
        S = [synth(s, world) for s in seeds]; k = 6
        train = [x[0] for x in S[::2]]
        fits = fit_models(train, k, (1, 12, 78), (0.90, 0.94, 0.97, 0.99))
        q = {"EWMA": [], "GARCH": [], "HAR": []}; cov1 = []; cov2 = []; r2s = []; sq_real = []; sq_rand = []; dirs = []; blocks = []
        sqN = {24: ([], []), 48: ([], [])}; sq_planted = ([], [])
        thr = None
        for i, (r, c, h, l, tv, reg) in enumerate(S):
            if i % 2 == 0:
                continue
            V = VE.forward_var(r, k); F = apply_fits(r, fits, k, (1, 12, 78)); mv = VE.forward_move(c, k)
            for m in q:
                q[m].append(VE.qlike(V, F[m])[0])
            cov1.append(VE.coverage(mv, F["EWMA"], 1)[0]); cov2.append(VE.coverage(mv, F["EWMA"], 2)[0])
            if world == "V2":
                tvk = pd.Series(tv)[::-1].rolling(k).sum()[::-1].shift(-1).to_numpy(); ok = np.isfinite(tvk) & np.isfinite(F["GARCH"]); ok[:200] = False
                r2s.append(float(np.corrcoef(np.log(tvk[ok]), np.log(F["GARCH"][ok]))[0, 1] ** 2))
            A = VT.atr(h, l, c)
            if thr is None:
                tr_h, tr_l, tr_c = S[0][2], S[0][3], S[0][1]; _, comp, wr = VE.squeeze_events(tr_h, tr_l, tr_c, VT.atr(tr_h, tr_l, tr_c), 0, 0)
                thr = (float(np.nanpercentile(comp, 10)), float(np.nanpercentile(wr, 10)))
            ev, comp, wr = VE.squeeze_events(h, l, c, A, *thr)
            N = 12; fr = pd.Series(h).rolling(N).max().shift(-N).to_numpy() - pd.Series(l).rolling(N).min().shift(-N).to_numpy(); med = np.nanmedian(fr)
            rng = np.random.default_rng(i)
            frN = {NN: pd.Series(h).rolling(NN).max().shift(-NN).to_numpy() - pd.Series(l).rolling(NN).min().shift(-NN).to_numpy() for NN in sqN}
            medN = {NN: np.nanmedian(frN[NN]) for NN in sqN}
            for t, _ in ev:
                if t + N < len(c) and np.isfinite(fr[t]):
                    sq_real.append(float(fr[t] > med)); dirs.append(float(c[t + N] > c[t]))
                    sq_rand.append(float(np.mean(fr[rng.integers(100, len(c) - N - 1, 20)] > med)))
                    blocks.append(f"{i}|{t // 200}")
                    for NN in sqN:
                        if t + NN < len(c) and np.isfinite(frN[NN][t]):
                            sqN[NN][0].append(float(frN[NN][t] > medN[NN])); sqN[NN][1].append(float(np.mean(frN[NN][rng.integers(100, len(c) - NN - 1, 20)] > medN[NN])))
                            if NN == 48 and reg[t] == 1:                        # events that fired inside a planted compression
                                sq_planted[0].append(float(frN[NN][t] > medN[NN])); sq_planted[1].append(float(np.mean(frN[NN][rng.integers(100, len(c) - NN - 1, 20)] > medN[NN])))
        r = {"fits": fits, "qlike": {m: round(float(np.mean(v)), 5) for m, v in q.items()},
             "garch_minus_ewma": boot_diff(np.array(q["GARCH"]), np.array(q["EWMA"]), np.arange(len(q["GARCH"]))),
             "har_minus_ewma": boot_diff(np.array(q["HAR"]), np.array(q["EWMA"]), np.arange(len(q["HAR"]))),
             "coverage_z1": round(float(np.mean(cov1)), 4), "coverage_z2": round(float(np.mean(cov2)), 4),
             "squeeze": {"n": len(sq_real), "expansion_real": round(float(np.mean(sq_real)), 4) if sq_real else None, "expansion_random": round(float(np.mean(sq_rand)), 4) if sq_rand else None,
                         "lift": boot_diff(np.array(sq_real), np.array(sq_rand), np.array(blocks)) if sq_real else None, "direction_up": round(float(np.mean(dirs)), 4) if dirs else None}}
        r["squeeze"]["by_window"] = {str(NN): dict(n=len(a_), real=round(float(np.mean(a_)), 4), random=round(float(np.mean(b_)), 4), diff=round(float(np.mean(a_) - np.mean(b_)), 4)) for NN, (a_, b_) in sqN.items() if a_}
        if world == "V2":
            r["garch_r2_vs_true"] = round(float(np.mean(r2s)), 3)
            # the planted expansion starts 30 bars after the compression starts and lasts 45; the 48-bar window after the crossing sees it
            w48 = r["squeeze"]["by_window"].get("48", {})
            # most synthetic squeeze crossings are noise (1,700 events for ~300 plants), which dilutes the pooled lift;
            # the gate reads the events that fired inside a planted compression (dated in PREREG)
            r["squeeze"]["planted_events_48"] = dict(n=len(sq_planted[0]), real=round(float(np.mean(sq_planted[0])), 4), random=round(float(np.mean(sq_planted[1])), 4)) if sq_planted[0] else None
            pe = r["squeeze"]["planted_events_48"] or {}
            r["pass"] = bool(r["garch_r2_vs_true"] >= 0.5 and abs(r["coverage_z1"] - 0.683) <= 0.03 and (pe.get("real", 0) - pe.get("random", 1)) > 0.1)
        else:
            # constant world: the fit must find no clustering (alpha ~ 0), the band must be nominal, the squeeze must show nothing
            sq = r["squeeze"]["lift"] or {}
            r["garch_alpha"] = round(float(fits["garch"][1]), 4)
            r["pass"] = bool(fits["garch"][1] < 0.05 and abs(r["coverage_z1"] - 0.683) <= 0.03 and (sq.get("lo", -1) <= 0 <= sq.get("hi", 1)))
        res[world] = r
        print(world, {k_: v for k_, v in r.items() if k_ != "fits"}, f"{time.time() - t0:.0f}s", flush=True)
    os.makedirs(OUT, exist_ok=True)
    json.dump(res, open(os.path.join(OUT, "planted.json"), "w"), indent=1, default=lambda x: None if isinstance(x, float) and not np.isfinite(x) else (x.item() if hasattr(x, "item") else str(x)))


# ---------------- real data ----------------
def load_daily(sym):
    d = pd.read_csv(os.path.join(UNI, f"{sym}.csv"), index_col=0, parse_dates=True)
    return d[["open", "high", "low", "close"] + (["volume"] if "volume" in d else [])].astype(float)


def series_5m(sym):
    d = E.frames(sym)[5]; sess, _ = VT.sessions_slots(d.index, 5)
    return d, sess, VE.session_returns(d, sess)


def tf_block(tf):
    kk = KS[tf]; lags = LAGS[tf]; N = NSQ[tf]
    if tf == "5m":
        from vzones.assistant import data as D
        syms = sorted(f[:-7] for f in os.listdir(D.BARS) if f.endswith("_5m.csv"))
        S = {}
        for s in syms:
            d, sess, r = series_5m(s); S[s] = dict(d=d, sess=sess, r=r, c=d["close"].to_numpy(), h=d["high"].to_numpy(), l=d["low"].to_numpy(), date=np.array([str(x) for x in sess]))
        days = sorted(set(np.concatenate([S[s]["date"] for s in syms]))); cut = days[int(0.6 * len(days))]
        for s in syms:
            S[s]["train"] = S[s]["date"] < cut
        lam_grid = (0.90, 0.94, 0.97, 0.99)
    else:
        syms = sorted(f[:-4] for f in os.listdir(UNI) if f.endswith(".csv") and not f.startswith("_"))
        S = {}
        for s in syms:
            d = load_daily(s); c = d["close"].to_numpy(); r = np.r_[np.nan, np.diff(np.log(c))]
            S[s] = dict(d=d, r=r, c=c, h=d["high"].to_numpy(), l=d["low"].to_numpy(), date=np.array([x.strftime("%Y-%m-%d") for x in d.index]), train=np.array([x.year <= 2019 for x in d.index]), test=np.array([x.year >= 2023 for x in d.index]))
        lam_grid = (0.94,)
    out = {}
    for k in kk:
        fits = fit_models([S[s]["r"][S[s]["train"]] for s in syms], k, lags, lam_grid)
        # control scale c for ATR and the slot-range control (5m)
        num = den = 0.0
        for s in syms:
            A = VT.atr(S[s]["h"], S[s]["l"], S[s]["c"]); V = VE.forward_var(S[s]["r"], k); tr = S[s]["train"]
            ok = tr & np.isfinite(V) & np.isfinite(A); num += np.nansum(V[ok]); den += np.nansum(A[ok] ** 2)
        c_atr = num / den
        rows = {m: [] for m in ("EWMA", "GARCH", "HAR", "ATR")}; cov = {m: {1: [], 2: []} for m in rows}; blocks = []; Vs = []; grp = []
        from vzones.assistant.eyes import group_of
        for s in syms:
            A = VT.atr(S[s]["h"], S[s]["l"], S[s]["c"]); V = VE.forward_var(S[s]["r"], k); mv = VE.forward_move(S[s]["c"], k)
            F = apply_fits(S[s]["r"], fits, k, lags); F["ATR"] = c_atr * A ** 2
            te = (~S[s]["train"]) if tf == "5m" else S[s]["test"]; te = te & np.isfinite(V) & (V > 0)
            te[:300] = False
            for m in rows:
                x = F[m]; ok = te & np.isfinite(x) & (x > 0)
                q = np.full(len(x), np.nan); q[ok] = np.log(x[ok]) + V[ok] / x[ok]; rows[m].append(q[te])
                cov[m][1].append(np.where(ok, np.abs(mv) <= 1 * np.sqrt(np.where(ok, x, np.nan)), np.nan)[te]); cov[m][2].append(np.where(ok, np.abs(mv) <= 2 * np.sqrt(np.where(ok, x, np.nan)), np.nan)[te])
            blk = (s + "|" + (S[s]["date"] if tf == "5m" else np.array([x[:7] for x in S[s]["date"]])))[te]; blocks.append(blk); grp.append(np.array([group_of(s)] * int(te.sum())))
        B = np.concatenate(blocks); G = np.concatenate(grp)
        res = {"fits": fits, "c_atr": round(float(c_atr), 6), "n_test": int(len(B)), "qlike": {}, "coverage": {}, "vs_ATR": {}, "coverage_by_group": {}}
        for m in rows:
            Q = np.concatenate(rows[m]); res["qlike"][m] = round(float(np.nanmean(Q)), 5)
            res["coverage"][m] = {z: round(float(np.nanmean(np.concatenate(cov[m][z]))), 4) for z in (1, 2)}
            if m != "ATR":
                res["vs_ATR"][m] = boot_diff(Q, np.concatenate(rows["ATR"]), B, draws=1000)
            res["coverage_by_group"][m] = {g: round(float(np.nanmean(np.concatenate(cov[m][1])[G == g])), 4) for g in ("index", "mega", "high_beta")}
        out[f"k{k}"] = res
        print(tf, k, "qlike", res["qlike"], "cov z1", {m: v[1] for m, v in res["coverage"].items()}, "vsATR", {m: (v["mean"], v["lo"], v["hi"]) for m, v in res["vs_ATR"].items()}, flush=True)
    # ---- squeeze (thresholds from train) with random control, and stops with the best forecast
    best = min(("EWMA", "GARCH", "HAR"), key=lambda m: out[f"k{kk[1] if tf == '5m' else 5}"]["qlike"][m])
    kstop = 24 if tf == "5m" else 5; fits_s = fit_models([S[s]["r"][S[s]["train"]] for s in syms], kstop, lags, lam_grid)
    comp_tr, wr_tr = [], []
    for s in syms[:10]:
        A = VT.atr(S[s]["h"], S[s]["l"], S[s]["c"]); _, comp, wr = VE.squeeze_events(S[s]["h"], S[s]["l"], S[s]["c"], A, 0, 0); tr = S[s]["train"]
        comp_tr.append(comp[tr]); wr_tr.append(wr[tr])
    thr = (float(np.nanpercentile(np.concatenate(comp_tr), 10)), float(np.nanpercentile(np.concatenate(wr_tr), 10)))
    sq = {"atr": {"real": [], "rand": [], "size": [], "dir": [], "blk": []}, "bb": {"real": [], "rand": [], "size": [], "dir": [], "blk": []}}
    st = {d_: {"noise": [], "n": 0} for d_ in (0.5, 0.75, 1.0, 1.25, 1.5, 2.0)}; st_atr = {"noise": [], "n": 0}; rr = {m: [] for m in (0.5, 1.0, 1.5, 2.0, 3.0)}
    for i, s in enumerate(syms):
        c, h, l = S[s]["c"], S[s]["h"], S[s]["l"]; A = VT.atr(h, l, c); te = (~S[s]["train"]) if tf == "5m" else S[s]["test"]
        ev, comp, wr = VE.squeeze_events(h, l, c, A, *thr)
        FR, MED = {}, {}
        for NN in (N, 2 * N, 4 * N):
            FR[NN] = pd.Series(h).rolling(NN).max().shift(-NN).to_numpy() - pd.Series(l).rolling(NN).min().shift(-NN).to_numpy()
            MED[NN] = VT.slot_baseline(FR[NN], S[s]["sess"], VT.sessions_slots(S[s]["d"].index, 5)[1]) if tf == "5m" else np.full(len(c), np.nanmedian(FR[NN][S[s]["train"]]))
        fr, med = FR[N], MED[N]
        rng = np.random.default_rng(i); pool = np.where(te & np.isfinite(fr) & np.isfinite(med))[0]
        for t, name in ev:
            if not te[t] or t + 4 * N >= len(c) or not (np.isfinite(fr[t]) and np.isfinite(med[t])) or len(pool) < 50:
                continue
            sq[name]["real"].append(float(fr[t] > med[t])); sq[name]["size"].append(float(fr[t] / A[t])); sq[name]["dir"].append(float(c[t + N] > c[t]))
            j = pool[rng.integers(0, len(pool), 20)]; sq[name]["rand"].append(float(np.mean(fr[j] > med[j]))); sq[name]["blk"].append(s + "|" + S[s]["date"][t][:10 if tf == "5m" else 7])
            for NN in (2 * N, 4 * N):
                ok_ = np.isfinite(FR[NN][t]) and np.isfinite(MED[NN][t]) and np.isfinite(FR[NN][j]).all() and np.isfinite(MED[NN][j]).all()
                sq[name].setdefault(f"real{NN}", []).append(float(FR[NN][t] > MED[NN][t]) if ok_ else np.nan); sq[name].setdefault(f"rand{NN}", []).append(float(np.mean(FR[NN][j] > MED[NN][j])) if ok_ else np.nan)
        # stops: random entries on test bars
        F = apply_fits(S[s]["r"], fits_s, kstop, lags)[best]
        cand = np.where(te & np.isfinite(F) & (F > 0))[0]
        if len(cand) == 0:
            continue
        pick = rng.choice(cand, min(len(cand), 600 if tf == "5m" else 300), replace=False)
        for t in pick:
            dr = 1 if rng.random() < 0.5 else -1; sd = np.sqrt(F[t]) * c[t]
            hit, mae = VE.first_touch(h, l, c, t, dr, sd, sd, kstop)
            if hit == 1:
                for d_ in st:
                    st[d_]["noise"].append(float(mae > d_ * sd)); st[d_]["n"] += 1
                st_atr["noise"].append(float(mae > A[t])); st_atr["n"] += 1
            for m in rr:
                for d_ in (1.0,):
                    hm, _ = VE.first_touch(h, l, c, t, dr, m * sd, d_ * sd, kstop); rr[m].append(float(hm == 1))
    sq_out = {}
    for name, v in sq.items():
        if len(v["real"]) >= 30:
            sq_out[name] = dict(n=len(v["real"]), expansion_real=round(float(np.mean(v["real"])), 4), expansion_random=round(float(np.mean(v["rand"])), 4),
                                lift=round(float(np.mean(v["real"]) / max(np.mean(v["rand"]), 1e-9)), 3), diff=boot_diff(np.array(v["real"]), np.array(v["rand"]), np.array(v["blk"]), 1000),
                                size_atr=round(float(np.mean(v["size"])), 3), direction_up=round(float(np.mean(v["dir"])), 4), direction_n=len(v["dir"]),
                                longer_windows={str(NN): dict(real=round(float(np.nanmean(v[f"real{NN}"])), 4), random=round(float(np.nanmean(v[f"rand{NN}"])), 4)) for NN in (2 * N, 4 * N) if f"real{NN}" in v})
        else:
            sq_out[name] = {"n": len(v["real"])}
    out["squeeze"] = {"thresholds": thr, **sq_out}
    out["stops"] = {"forecast": best, "k": kstop, "noise_stopout_by_d": {str(d_): round(float(np.mean(v["noise"])), 4) for d_, v in st.items() if v["n"]}, "n_right_trades": st[1.0]["n"],
                    "fixed_1ATR_noise_stopout": round(float(np.mean(st_atr["noise"])), 4) if st_atr["n"] else None,
                    "target_hit_rate_with_stop_1sigma": {str(m): round(float(np.mean(v)), 4) for m, v in rr.items()}, "breakeven_rate": {str(m): round(1 / (1 + m), 4) for m in rr}}
    print(tf, "squeeze", sq_out, "stops", out["stops"], flush=True)
    return out


def sizing():
    syms = sorted(f[:-4] for f in os.listdir(UNI) if f.endswith(".csv") and not f.startswith("_"))
    px = pd.DataFrame({s: load_daily(s)["close"] for s in syms}).sort_index()
    r = np.log(px).diff()
    ev = (r ** 2).ewm(alpha=0.06, adjust=False).mean() ** 0.5 * np.sqrt(252)
    target = ev[ev.index.year <= 2019].median()
    me = r.index.to_period("M"); months = sorted(set(me)); ret = {"equal": [], "vol_managed": []}; turn = {"equal": [], "vol_managed": []}
    w_prev = {k: None for k in ret}
    for m in months:
        if m.year < 2023:
            continue
        idx = r.index[me == m]; prev_day = r.index[r.index < idx[0]]
        if len(prev_day) == 0:
            continue
        last = prev_day[-1]; alive = px.loc[last].notna() & ev.loc[last].notna()
        w_eq = alive.astype(float); w_eq /= w_eq.sum()
        scale = (target / ev.loc[last]).clip(upper=2.0).where(alive, 0.0)
        w_vm = w_eq * scale
        for name, w in (("equal", w_eq), ("vol_managed", w_vm)):
            rm = (np.exp(r.loc[idx].fillna(0)) - 1)
            port = (rm * w).sum(axis=1)
            t = float((w - (w_prev[name] if w_prev[name] is not None else 0)).abs().sum()); turn[name].append(t)
            port.iloc[0] -= t * 5e-4
            ret[name].append(port); w_prev[name] = w
    out = {}
    for name in ret:
        s = pd.concat(ret[name]); eq = (1 + s).cumprod()
        out[name] = dict(ann_mean=round(float(s.mean() * 252), 4), ann_vol=round(float(s.std() * np.sqrt(252)), 4), sharpe=round(float(s.mean() / s.std() * np.sqrt(252)), 3),
                         max_dd=round(float((eq / eq.cummax() - 1).min()), 4), turnover_per_month=round(float(np.mean(turn[name])), 3), months=len(ret[name]))
        out[name]["series"] = s
    # Sharpe difference, bootstrap over months
    a = pd.concat(ret["vol_managed"]); b = pd.concat(ret["equal"]); mon = a.index.to_period("M"); um = sorted(set(mon)); rng = np.random.default_rng(0); bs = []
    for _ in range(2000):
        pick = [um[i] for i in rng.integers(0, len(um), len(um))]
        sa = pd.concat([a[mon == p] for p in pick]); sb = pd.concat([b[mon == p] for p in pick])
        bs.append(sa.mean() / sa.std() - sb.mean() / sb.std())
    out["sharpe_diff"] = dict(mean=round(float(np.mean(bs)) * np.sqrt(252), 3), lo=round(float(np.percentile(bs, 2.5)) * np.sqrt(252), 3), hi=round(float(np.percentile(bs, 97.5)) * np.sqrt(252), 3))
    eqc = {name: (1 + out[name].pop("series")).cumprod() for name in ("equal", "vol_managed")}
    pd.DataFrame(eqc).to_csv(os.path.join(OUT, "equity.csv"))
    return out


def fear():
    vix = pd.read_csv(os.path.join(UNI, "_VIX.csv"), index_col=0, parse_dates=True)["close"]
    v3 = pd.read_csv(os.path.join(UNI, "_VIX3M.csv"), index_col=0, parse_dates=True)["close"]
    out = {}
    for sym in ("SPY", "QQQ"):
        c = load_daily(sym)["close"]; df = pd.DataFrame({"c": c}).join(vix.rename("vix")).join(v3.rename("v3")).dropna()
        df["pct"] = df["vix"].rolling(500).rank(pct=True); df["ts"] = df["vix"] / df["v3"]
        for h in (20, 60):
            df[f"f{h}"] = np.log(df["c"].shift(-h) / df["c"])
        res = {}
        for per, m in (("test", df.index.year >= 2023), ("validation", (df.index.year >= 2020) & (df.index.year <= 2022))):
            sub = df[m].dropna(); q = np.clip((sub["pct"] * 5).astype(int), 0, 4)
            r_ = {"n": len(sub)}
            for h in (20, 60):
                base = float(sub[f"f{h}"].mean()); byq = [round(float(sub[f"f{h}"][q == k].mean()), 4) for k in range(5)]
                top = sub[f"f{h}"][q == 4]; mon = top.index.to_period("M"); um = sorted(set(mon)); rng = np.random.default_rng(0)
                bs = [pd.concat([top[mon == um[i]] for i in rng.integers(0, len(um), len(um))]).mean() - base for _ in range(1000)] if len(um) >= 5 else [np.nan]
                r_[f"f{h}"] = dict(base=round(base, 4), by_vix_quintile=byq, top_minus_base=round(float(np.mean(top) - base), 4), lo=round(float(np.nanpercentile(bs, 2.5)), 4), hi=round(float(np.nanpercentile(bs, 97.5)), 4),
                                   backwardation_minus_contango=round(float(sub[f"f{h}"][sub["ts"] > 1].mean() - sub[f"f{h}"][sub["ts"] <= 1].mean()), 4) if (sub["ts"] > 1).sum() >= 20 else None)
            res[per] = r_
        out[sym] = res
    return out


def run_verdict():
    t0 = time.time(); res = {}
    for tf in ("5m", "D"):
        res[tf] = tf_block(tf); print(tf, "done", f"{time.time() - t0:.0f}s", flush=True)
        json.dump(res, open(os.path.join(OUT, "verdict.json"), "w"), indent=1, default=lambda x: None if isinstance(x, float) and not np.isfinite(x) else (x.item() if hasattr(x, "item") else str(x)))
    res["sizing"] = sizing(); print("sizing", res["sizing"], flush=True)
    res["fear"] = fear(); print("fear", json.dumps(res["fear"])[:600], flush=True)
    json.dump(res, open(os.path.join(OUT, "verdict.json"), "w"), indent=1, default=lambda x: None if isinstance(x, float) and not np.isfinite(x) else (x.item() if hasattr(x, "item") else str(x)))
    print(f"{time.time() - t0:.0f}s")


if __name__ == "__main__":
    {"planted": run_planted, "verdict": run_verdict}[sys.argv[1]]()
