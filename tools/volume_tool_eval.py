"""Tests of reports/volume_tool/PREREG.md.

    python tools/volume_tool_eval.py planted     # P1 (no relation) and P2 (planted relation), fresh seeds
    python tools/volume_tool_eval.py verdict     # real SIP data: train thresholds / hazard, test IC, lift, groups, ...
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import time

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("VZ_TAG", "sip")
from vzones import volume_tool as VT  # noqa: E402

OUT = os.path.join(ROOT, "reports", "volume_tool")
TARGETS = ["T1_3", "T1_6", "T1_12", "T2", "T3"]
RAW = ["T1_3_raw", "T1_6_raw", "T1_12_raw", "T3_raw"]
NOISE_BAND = 0.01      # P1: |IC| below this is noise even when the interval excludes 0 (dated in PREREG)
NY = "America/New_York"


def dir_eval(name, x, Y, tgt):
    """What to feed the direction targets with. Unsigned tool: the tool as is, against the bar-signed target (strong
    volume -> continuation in the bar's direction). Signed tool: its magnitude for the lift, the raw target signed by
    the tool's own sign for the hit, and (x, raw target) for the IC. Returns (x_ic, y_ic, x_lift, y_lift)."""
    raw = Y[tgt + "_raw"]
    if name.endswith("*"):
        return x, raw, np.abs(x), raw * np.sign(x)
    return x, Y[tgt], x, Y[tgt]


def mag_form(name, x):
    return np.abs(x) if name.endswith("*") else x


# ---------------- synthetic ----------------
def synth(seed: int, planted: bool, sessions: int = 250, nbar: int = 78):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2025-01-02", periods=sessions)
    idx = pd.DatetimeIndex([pd.Timestamp(f"{d.date()} 09:30") + pd.Timedelta(minutes=5 * k) for d in days for k in range(nbar)]).tz_localize(NY)
    n = len(idx)
    slot = np.tile(np.arange(nbar), sessions)
    u = 1 + 1.5 * ((slot - nbar / 2) / (nbar / 2)) ** 2                   # U-shaped seasonality
    # volume noise: AR(1) in log (P1) or a Markov strong / normal regime with hazard 0.35 (P2)
    if not planted:
        e = np.zeros(n); e[0] = rng.normal(0, 0.5)
        for i in range(1, n):
            e[i] = 0.5 * e[i - 1] + rng.normal(0, 0.5 * np.sqrt(1 - 0.25))
        mult = np.exp(e); strong_true = np.zeros(n, bool)
    else:
        strong_true = np.zeros(n, bool); s = False
        for i in range(n):
            s = (rng.random() > 0.35) if s else (rng.random() < 0.062)
            if slot[i] == 0:
                s = rng.random() < 0.15
            strong_true[i] = s
        mult = np.where(strong_true, 2.2 * np.exp(rng.normal(0, 0.15, n)), np.minimum(np.exp(rng.normal(-0.1, 0.3, n)), 1.3))
    v = 1e5 * u * mult
    r = rng.normal(0, 0.001, n)
    if planted:                                                             # next-6-bar sign follows the bar on strong bars with p = 0.65
        last = -10                                                           # one plant per 6-bar window, so plants do not undo each other
        for t in np.where(strong_true)[0]:
            if t + 6 >= n or t - last < 7:
                continue
            last = t
            want = np.sign(r[t]) if rng.random() < 0.65 else -np.sign(r[t])
            if np.sign(r[t + 1:t + 7].sum()) != want:
                r[t + 1:t + 7] *= -1
    c = 100 * np.exp(np.cumsum(r))
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, 0.0004, n))); l = np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.0004, n)))
    d = pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": v}, index=idx)
    return d, strong_true


def run_planted(seeds=range(20000, 20040)):
    t0 = time.time()
    res = {"P1": {}, "P2": {}}
    for mode, planted in (("P1", False), ("P2", True)):
        X = {}; Y = {}; B = []; STRONG = []; SGN = []; RUN = []; SESS = []; SYM = []
        for s in seeds:
            d, strong_true = synth(s, planted)
            T = VT.tools(d, 5); Yd = VT.targets(d, 5)
            sess, _ = VT.sessions_slots(d.index, 5)
            sgn = np.sign(d["close"].to_numpy() - d["open"].to_numpy())
            for k, x in T.items():
                X.setdefault(k, []).append(x)
            for k in TARGETS + RAW:
                Y.setdefault(k, []).append(Yd[k])
            B.append(np.array([f"{s}|{x}" for x in sess])); STRONG.append(strong_true); SGN.append(sgn); SESS.append(np.array([f"{s}|{x}" for x in sess])); SYM.append(np.array([str(s)] * len(sess)))
        X = {k: np.concatenate(v) for k, v in X.items()}; Y = {k: np.concatenate(v) for k, v in Y.items()}
        B = np.concatenate(B); STRONG = np.concatenate(STRONG); SGN = np.concatenate(SGN); SESS = np.concatenate(SESS); SYM = np.concatenate(SYM)
        hit1 = Y["T1_6"] > 0
        base = float(np.nanmean(hit1))
        tab = {}
        for k, x in X.items():
            xi, yi, xl, yl = dir_eval(k, x, Y, "T1_6"); xm = mag_form(k, x)
            ic1 = VT.ic_pooled(xi, yi, B, SYM); ic2 = VT.ic_pooled(xm, Y["T2"], B, SYM)
            lf = VT.lift(xl, yl > 0, B, float(np.nanpercentile(xl, 90)))
            tab[k] = dict(ic_T1=round(ic1[0], 4), ic_T1_lo=round(ic1[1][0], 4), ic_T1_hi=round(ic1[1][1], 4),
                          ic_T2=round(ic2[0], 4), ic_T2_lo=round(ic2[1][0], 4), ic_T2_hi=round(ic2[1][1], 4),
                          lift_T1=round(lf[0], 3), lift_lo=round(lf[1][0], 3), lift_hi=round(lf[1][1], 3))
            if mode == "P1":
                tab[k]["clean"] = bool((ic1[1][0] <= 0 <= ic1[1][1] or abs(ic1[0]) < NOISE_BAND) and (ic2[1][0] <= 0 <= ic2[1][1] or abs(ic2[0]) < NOISE_BAND)
                                       and (lf[1][0] <= 1 <= lf[1][1] or abs(lf[0] - 1) < 0.02))
        res[mode]["tools"] = tab
        if mode == "P1":
            res["P1"]["pass"] = all(v["clean"] for v in tab.values())
            res["P1"]["broken"] = [k for k, v in tab.items() if not v["clean"]]
        else:
            m = np.isfinite(Y["T1_6"])
            planted_lift = float(np.mean(hit1[STRONG & m]) / np.mean(hit1[m]))
            got = tab["STRENGTH*"]["lift_T1"]
            rv = X["RVOL"]
            lf_rvol = VT.lift(rv, hit1, B, float(np.nanpercentile(rv, 90)))
            run = VT.runs(rv > VT.STRONG, SESS); h, cnt = VT.hazard(run, SESS)
            res["P2"]["planted_lift"] = round(planted_lift, 3)
            res["P2"]["strength_lift"] = got
            res["P2"]["rvol_lift"] = round(lf_rvol[0], 3)
            res["P2"]["recovered_share"] = round((got - 1) / (planted_lift - 1), 3) if planted_lift > 1 else None
            res["P2"]["hazard_r1_5"] = [None if not np.isfinite(x) else round(float(x), 3) for x in h[1:6]]
            res["P2"]["hazard_counts"] = [int(x) for x in cnt[1:6]]
            # r = 1 carries the single false-strong bars of the estimator (ends at once), so the check is r = 2..5 (dated in PREREG)
            res["P2"]["hazard_ok"] = bool(all(np.isfinite(h[2:6])) and np.all(np.abs(h[2:6] - 0.35) <= 0.08))
            res["P2"]["pass"] = bool(res["P2"]["recovered_share"] is not None and res["P2"]["recovered_share"] >= 0.7 and res["P2"]["hazard_ok"])
        print(mode, {k: v for k, v in res[mode].items() if k != "tools"}, f"{time.time() - t0:.0f}s", flush=True)
    os.makedirs(OUT, exist_ok=True)
    json.dump(res, open(os.path.join(OUT, "planted.json"), "w"), indent=1)


# ---------------- real data ----------------
def frames(sym):
    from vzones.assistant import data as D
    d5 = D.load_bars(sym)
    d5 = d5[(d5.index.time >= dt.time(9, 30)) & (d5.index.time < dt.time(16, 0))]
    agg = dict(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"), volume=("volume", "sum"))
    out = {5: d5, 15: d5.groupby(d5.index.floor("15min")).agg(**agg)}
    k1 = (d5.index - pd.Timedelta(minutes=30)).floor("1h") + pd.Timedelta(minutes=30)
    out[60] = d5.groupby(k1).agg(**agg)
    dd = d5.groupby(d5.index.date).agg(**agg)
    dd.index = pd.DatetimeIndex([pd.Timestamp(f"{x} 09:30") for x in dd.index]).tz_localize(NY)
    out[390] = dd
    return out


def day_profile_levels(d5: pd.DataFrame):
    """Prior-day POC / VAH / VAL (70% value area) from the day's 5m bars, one row per session date (for T4)."""
    rows = {}
    for day, g in d5.groupby(d5.index.date):
        lo, hi = g["low"].min(), g["high"].max()
        if hi <= lo:
            continue
        edges = np.linspace(lo, hi, 41); vol = np.zeros(40)
        for h_, l_, v_ in zip(g["high"], g["low"], g["volume"]):
            a = np.searchsorted(edges, l_, "right") - 1; b = max(a, np.searchsorted(edges, h_, "right") - 1)
            vol[a:b + 1] += v_ / (b - a + 1)
        poc = int(np.argmax(vol)); a = b = poc; tot = vol.sum()
        while vol[a:b + 1].sum() < 0.7 * tot and (a > 0 or b < 39):
            if a == 0 or (b < 39 and vol[b + 1] >= vol[a - 1]):
                b += 1
            else:
                a -= 1
        rows[day] = dict(poc=(edges[poc] + edges[poc + 1]) / 2, vah=edges[b + 1], val=edges[a])
    df = pd.DataFrame(rows).T.sort_index()
    return df.shift(1)                                   # prior day's levels apply to today


def run_verdict():
    from vzones.assistant import data as D
    from vzones.assistant.eyes import group_of
    t0 = time.time()
    syms = sorted(f[:-7] for f in os.listdir(D.BARS) if f.endswith("_5m.csv"))
    F = {s: frames(s) for s in syms}
    days = sorted(set().union(*[set(F[s][390].index.date) for s in syms]))
    cut = days[int(0.6 * len(days))]
    res = {"split": {"train_end_before": str(cut), "days": len(days), "symbols": len(syms)}, "tf": {}}
    for tf in (5, 15, 60, 390):
        X = {}; Y = {}; B = []; TR = []; SGN = []; SESS = []; SYM = []; SLOT = []
        for s in syms:
            d = F[s][tf]
            T = VT.tools(d, tf); Yd = VT.targets(d, tf)
            sess, slot = VT.sessions_slots(d.index, tf)
            for k, x in T.items():
                X.setdefault(k, []).append(x)
            for k in TARGETS + RAW:
                Y.setdefault(k, []).append(np.where(Yd["T3_valid"], Yd[k], np.nan) if k.startswith("T3") else Yd[k])
            wk = np.array([f"{s}|{x.isocalendar()[0]}-{x.isocalendar()[1]}" for x in sess])
            B.append(np.array([f"{s}|{x}" for x in sess]) if tf <= 15 else wk if tf == 60 else np.array([s] * len(sess)))
            TR.append(sess < cut); SGN.append(np.sign(d["close"].to_numpy() - d["open"].to_numpy()))
            SESS.append(np.array([f"{s}|{x}" for x in sess])); SYM.append(np.array([s] * len(sess))); SLOT.append(slot)
        X = {k: np.concatenate(v) for k, v in X.items()}; Y = {k: np.concatenate(v) for k, v in Y.items()}
        B = np.concatenate(B); TR = np.concatenate(TR); SGN = np.concatenate(SGN); SESS = np.concatenate(SESS); SYM = np.concatenate(SYM); SLOT = np.concatenate(SLOT)
        TE = ~TR
        hits = {"T1_6": Y["T1_6"] > 0, "T1_3": Y["T1_3"] > 0, "T1_12": Y["T1_12"] > 0, "T2": Y["T2"] > 0, "T3": Y["T3"] > 0}
        hits = {k: np.where(np.isfinite(Y[k]), v, np.nan) for k, v in hits.items()}

        def evaluate(k, x, tgt, m):
            """IC and lift of tool k on target tgt over the bars in mask m (threshold = train p90 of the lift form)"""
            if tgt == "T2":
                xm = mag_form(k, x); thr = float(np.nanpercentile(xm[TR], 90))
                return VT.ic_pooled(xm[m], Y["T2"][m], B[m], SYM[m]), VT.lift(xm[m], hits["T2"][m], B[m], thr), thr
            xi, yi, xl, yl = dir_eval(k, x, Y, tgt); thr = float(np.nanpercentile(xl[TR], 90))
            hit = np.where(np.isfinite(yl), yl > 0, np.nan)
            return VT.ic_pooled(xi[m], yi[m], B[m], SYM[m]), VT.lift(xl[m], hit[m], B[m], thr), thr
        tab = {}
        for k, x in X.items():
            row = {"thr_mag_p90": round(float(np.nanpercentile(mag_form(k, x)[TR], 90)), 4)}
            for tgt in TARGETS:
                ic, lf, thr = evaluate(k, x, tgt, TE)
                row["thr_dir_p90"] = round(thr, 4) if tgt == "T1_6" else row.get("thr_dir_p90")
                row[tgt] = dict(ic=round(ic[0], 4), ic_lo=round(ic[1][0], 4), ic_hi=round(ic[1][1], 4), blocks=ic[2],
                                lift=round(lf[0], 3), lift_lo=round(lf[1][0], 3), lift_hi=round(lf[1][1], 3), n_top=lf[2])
            tab[k] = row
            print(tf, k, "T1_6", row["T1_6"]["ic"], row["T1_6"]["lift"], "T2", row["T2"]["ic"], "T3", row["T3"]["lift"], f"{time.time() - t0:.0f}s", flush=True)
        out = {"tools": tab}
        # groups and first 30 minutes on 5m
        if tf == 5:
            grp = np.array([group_of(s) for s in SYM])
            out["groups"] = {}
            for g in ("index", "mega", "high_beta"):
                m = TE & (grp == g); out["groups"][g] = {}
                for k, x in X.items():
                    ic, lf, _ = evaluate(k, x, "T1_6", m); ic3, lf3, _ = evaluate(k, x, "T3", m)
                    out["groups"][g][k] = dict(ic=round(ic[0], 4), ic_lo=round(ic[1][0], 4), ic_hi=round(ic[1][1], 4), lift=round(lf[0], 3), lift_lo=round(lf[1][0], 3), lift_hi=round(lf[1][1], 3),
                                               ic3=round(ic3[0], 4), ic3_lo=round(ic3[1][0], 4), ic3_hi=round(ic3[1][1], 4), lift3=round(lf3[0], 3), lift3_lo=round(lf3[1][0], 3), lift3_hi=round(lf3[1][1], 3))
            out["first30"] = {}
            for part, m in (("open30", TE & (SLOT < 6)), ("rest", TE & (SLOT >= 6))):
                out["first30"][part] = {}
                for k in ("STRENGTH", "RVOL", "zRVOL", "vol/SMA", "pressure*", "delta*", "effort/result"):
                    ic, lf, _ = evaluate(k, X[k], "T1_6", m); ic2, _, _ = evaluate(k, X[k], "T2", m)
                    out["first30"][part][k] = dict(ic_T1=round(ic[0], 4), lo=round(ic[1][0], 4), hi=round(ic[1][1], 4), lift=round(lf[0], 3), lift_lo=round(lf[1][0], 3), lift_hi=round(lf[1][1], 3), ic_T2=round(ic2[0], 4))
            # lift curve over vol/SMA(20) (H6) and over RVOL
            out["lift_curve"] = {}
            for k in ("vol/SMA", "RVOL"):
                curve = []
                for q in (0.5, 0.8, 1.0, 1.2, 1.5, 2.0, 2.5, 3.0):
                    m = TE & (X[k] > q) & np.isfinite(hits["T1_6"]) & np.isfinite(Y["T2"])
                    base1 = np.nanmean(hits["T1_6"][TE]); base2 = np.nanmean(hits["T2"][TE])
                    curve.append(dict(above=q, n=int(m.sum()), T1_cont=round(float(np.nanmean(hits["T1_6"][m]) / base1), 3) if m.sum() > 100 else None,
                                      T2_expansion=round(float(np.nanmean(hits["T2"][m]) / base2), 3) if m.sum() > 100 else None))
                out["lift_curve"][k] = curve
            # calibration of the strength score on T1_6 and the fitted ceiling
            sd = X["STRENGTH"]                                     # unsigned score vs the bar-signed target
            edges = np.nanpercentile(sd[TR], np.arange(10, 100, 10))
            cal, slope = VT.calibration(sd[TE], hits["T1_6"][TE], edges)
            out["calibration"] = {"deciles": {int(i): [round(float(r["mean"]), 4), int(r["size"])] for i, r in cal.iterrows()}, "slope": round(slope, 5)}
            out["ceiling"] = fitted_ceiling(X, SGN, Y, hits, TR, TE, B)
            out["T4"] = t4_eval(F, syms, X, SGN, SESS, SYM, TR, TE, tab)
        # persistence (every tf): hazard from train, Brier on test, autocorrelation per symbol
        rv = X["RVOL"]; strong = rv > VT.STRONG
        run = VT.runs(np.where(np.isfinite(rv), strong, False), SESS)
        h, cnt = VT.hazard(run[TR], SESS[TR])
        nxt = np.r_[run[1:], 0] > 0; same = np.r_[SESS[1:] == SESS[:-1], False]
        m = TE & (run > 0) & same
        pred = 1 - pd.Series(h).ffill().bfill().to_numpy()[np.minimum(run[m], len(h) - 1)]
        base = float(np.mean(nxt[TR & (run > 0) & np.r_[SESS[1:] == SESS[:-1], False]]))
        brier = float(np.mean((pred - nxt[m]) ** 2)); brier0 = float(np.mean((base - nxt[m]) ** 2))
        # persistence vs one strong bar for T1 (H4): lift of run == 1 vs run >= 3 on T1_6 (directional: strong bar in its own direction)
        h1 = hits["T1_6"]; ok = TE & np.isfinite(h1)
        base1 = float(np.nanmean(h1[ok]))
        l_run1 = float(np.nanmean(h1[ok & (run == 1)]) / base1); l_run3 = float(np.nanmean(h1[ok & (run >= 3)]) / base1)
        ac = {}
        for s in syms:
            ms = SYM == s
            ac[s] = VT.autocorr(X["logRVOL"][ms], lags=(1, 2, 3, 6, 12))
        ac_mean = {k: round(float(np.mean([v[k] for v in ac.values()])), 3) for k in (1, 2, 3, 6, 12)}
        out["persistence"] = dict(hazard=[None if not np.isfinite(x) else round(float(x), 3) for x in h[1:11]], counts=[int(x) for x in cnt[1:11]],
                                  base_next_strong=round(base, 3), brier=round(brier, 4), brier_base=round(brier0, 4), n_test=int(m.sum()),
                                  autocorr_mean=ac_mean, autocorr_lag1_min=round(float(min(v[1] for v in ac.values())), 3),
                                  lift_T1_run1=round(l_run1, 3), lift_T1_run3plus=round(l_run3, 3), n_run3plus=int((ok & (run >= 3)).sum()))
        res["tf"][tf] = out
        print(tf, "persistence", out["persistence"], flush=True)
        json.dump(res, open(os.path.join(OUT, "verdict.json"), "w"), indent=1)
    # verdict per tool across timeframes and groups
    res["verdict"] = {}
    for k in res["tf"][5]["tools"]:
        tfs_ok = []
        for tf in (5, 15, 60):
            r = res["tf"][tf]["tools"][k]
            ok = any((r[t]["lift_lo"] > 1 or r[t]["lift_hi"] < 1) and (r[t]["ic_lo"] > 0 or r[t]["ic_hi"] < 0) for t in ("T1_6", "T3"))
            tfs_ok.append(ok)
        g_ok = sum(1 for g, v in res["tf"][5]["groups"].items() if (v[k]["lift_lo"] > 1 or v[k]["lift_hi"] < 1 or v[k]["lift3_lo"] > 1 or v[k]["lift3_hi"] < 1)
                   and (v[k]["ic_lo"] > 0 or v[k]["ic_hi"] < 0 or v[k]["ic3_lo"] > 0 or v[k]["ic3_hi"] < 0))
        ics = [res["tf"][tf]["tools"][k]["T1_6"]["ic"] for tf in (5, 15, 60)]
        stable = all(np.sign(i) == np.sign(ics[0]) and i != 0 for i in ics)
        t2_ok = sum(1 for tf in (5, 15, 60) if (res["tf"][tf]["tools"][k]["T2"]["ic_lo"] > 0 or res["tf"][tf]["tools"][k]["T2"]["ic_hi"] < 0)
                    and (res["tf"][tf]["tools"][k]["T2"]["lift_lo"] > 1 or res["tf"][tf]["tools"][k]["T2"]["lift_hi"] < 1))
        label = "useful" if sum(tfs_ok) >= 2 and g_ok >= 2 else "descriptive only" if stable else "noise"
        res["verdict"][k] = dict(label=label, tfs_ok=int(sum(tfs_ok)), groups_ok=int(g_ok), mean_ic_T1=round(float(np.mean(ics)), 4),
                                 mean_ic_T2=round(float(np.mean([res["tf"][tf]["tools"][k]["T2"]["ic"] for tf in (5, 15, 60)])), 4), useful_for_range_tfs=int(t2_ok))
    json.dump(res, open(os.path.join(OUT, "verdict.json"), "w"), indent=1)
    print(json.dumps(res["verdict"], indent=1)); print(f"{time.time() - t0:.0f}s")


def fitted_ceiling(X, SGN, Y, hits, TR, TE, B):
    """Logistic on train (zRVOL, range/ATR, body/range, each times the bar direction) for T1_6: the ceiling of a
    fitted strength score. Reported only, never shipped."""
    from scipy.optimize import minimize
    body = (X["STRENGTH"] - 0.5 * X["zRVOL"] - 0.25 * (X["range/ATR"] - 1)) * 4
    f = np.vstack([X["zRVOL"], X["range/ATR"] - 1, body]).T                 # unsigned inputs, bar-signed target
    y = hits["T1_6"]
    ok = np.isfinite(f).all(1) & np.isfinite(y)
    tr = ok & TR; te = ok & TE
    Xtr = np.c_[np.ones(tr.sum()), f[tr]]; ytr = y[tr]

    def nll(w):
        z = Xtr @ w; return float(np.mean(np.logaddexp(0, -z) * ytr + np.logaddexp(0, z) * (1 - ytr)))
    w = minimize(nll, np.zeros(4), method="L-BFGS-B").x
    p = 1 / (1 + np.exp(-(np.c_[np.ones(te.sum()), f[te]] @ w)))
    thr = float(np.percentile(1 / (1 + np.exp(-(Xtr @ w))), 90))
    lf = VT.lift(p, y[te], B[te], thr); ic = VT.ic_by_block(p, Y["T1_6"][te], B[te])
    return dict(weights=[round(float(x), 4) for x in w], lift=round(lf[0], 3), lift_lo=round(lf[1][0], 3), lift_hi=round(lf[1][1], 3), ic=round(ic[0], 4), ic_lo=round(ic[1][0], 4), ic_hi=round(ic[1][1], 4))


def t4_eval(F, syms, X, SGN, SESS, SYM, TR, TE, tab):
    """Breakouts through prior-day POC / VAH / VAL and the GEX walls (when stored): success rate when the tool at the
    breakout bar is above its train p90, over the success rate of all breakouts (test days, 5m)."""
    from vzones.assistant import data as D
    ev = []
    off = 0
    for s in syms:
        d5 = F[s][5]
        lv = day_profile_levels(d5)
        try:
            days = sorted(set(d5.index.date)); g = D.levels_for_days(s, days)[["cw", "pw"]]
            lv = lv.join(g, how="outer")
        except Exception:  # noqa: BLE001
            pass
        for t, held, dirn, name in VT.t4_breakouts(d5, lv):
            ev.append((off + t, held, name))
        off += len(d5)
    if not ev:
        return {}
    idx = np.array([e[0] for e in ev]); held = np.array([e[1] for e in ev], float); names = np.array([e[2] for e in ev])
    te = TE[idx]
    out = {"n_events_test": int(te.sum()), "success_rate": round(float(held[te].mean()), 3), "by_level": {}}
    for nm in sorted(set(names)):
        m = te & (names == nm); out["by_level"][nm] = dict(n=int(m.sum()), success=round(float(held[m].mean()), 3) if m.sum() else None)
    out["tools"] = {}
    for k in ("STRENGTH", "RVOL", "zRVOL", "vol/SMA", "effort/result", "pressure*", "delta*", "range/ATR"):
        x = mag_form(k, X[k])[idx]
        thr = tab[k]["thr_mag_p90"]
        m = te & np.isfinite(x)
        top = m & (x > thr)
        blk = SESS[idx]
        lf = VT.lift(x[m], held[m], blk[m], thr)
        out["tools"][k] = dict(n_top=int(top.sum()), lift=round(lf[0], 3), lo=round(lf[1][0], 3), hi=round(lf[1][1], 3))
    return out


if __name__ == "__main__":
    {"planted": run_planted, "verdict": run_verdict}[sys.argv[1]]()
