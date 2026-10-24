"""Tests of reports/trend_volume_model/PREREG.md.

    python tools/trend_volume_model_eval.py planted   # Z1 (no relation) and Z2 (planted) on fresh seeds 50000..50039
    python tools/trend_volume_model_eval.py verdict   # real SIP data, 5m main, 15m robustness; per-component verdicts
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
from vzones import trend_volume as TV  # noqa: E402
from vzones import trend_volume_model as TM  # noqa: E402
from vzones import volume_tool as VT  # noqa: E402
import breakout_volume_eval as BE  # noqa: E402
import volume_tool_eval as E  # noqa: E402

OUT = os.path.join(ROOT, "reports", "trend_volume_model")
NY = "America/New_York"


# ---------------- helpers ----------------
def paired(df, x, twin, hit, tr, te, q=80):
    """top-quantile lift of x vs its twin on the same events (edges from train), paired by symbol-day"""
    X = df[x].to_numpy(float); Tw = df[twin].to_numpy(float); H = df[hit].to_numpy(float)
    if np.isfinite(X[tr]).sum() < 30 or np.isfinite(H[te]).sum() < 50:
        return {"n": int(np.isfinite(H[te]).sum())}
    ex, et = float(np.nanpercentile(X[tr], q)), float(np.nanpercentile(Tw[tr], q))
    r = TV.paired_lift(X[te], Tw[te], H[te], df["block"].to_numpy()[te], ex, et)
    qs = np.nanpercentile(X[tr], [20, 40, 60, 80]); dec = np.searchsorted(qs, X[te])
    r["by_quintile"] = [round(float(np.nanmean(H[te][dec == j])), 3) if np.isfinite(H[te][dec == j]).sum() >= 10 else None for j in range(5)]
    r["edge"] = round(ex, 4); r["twin_edge"] = round(et, 4)
    return r


def label(r):
    if "lift" not in r:
        return "drop (too few events)"
    if r["diff_lo"] > 0 and r["lift_lo"] > 1:
        return "ship"
    if r["control_lo"] > 1 and r["diff_lo"] <= 0:
        return "ship price-only"
    return "drop"


def collect(items, tf, with_days, cut=None):
    T, C, B = [], [], []
    for sym, d in items:
        dl = BE.day_levels(d, sym if (isinstance(sym, str) and not sym.isdigit()) else None) if with_days else None
        res = TM.run(d, tf, dl); Y = TM.targets(res); sess = res["frames"]["sess"]
        for name, df in Y.items():
            if len(df) == 0:
                continue
            df = df.copy(); df["sym"] = str(sym); df["date"] = [str(sess[t]) for t in df["t"]]; df["block"] = df["sym"] + "|" + df["date"]
            if cut is not None:
                df["train"] = [sess[t] < cut for t in df["t"]]
            {"trend": T, "touches": C, "breaks": B}[name].append(df)
    cat = lambda L: pd.concat(L, ignore_index=True) if L else pd.DataFrame()  # noqa: E731
    return cat(T), cat(C), cat(B)


# ---------------- synthetic ----------------
def synth(seed: int, planted: bool, sessions: int = 250, nbar: int = 78):
    """prices as in breakout_volume_eval.synth; then volume by outcome: (i) break bars that will hold at 2.5x with an
    outcome-dependent probability, (ii) bars near levels that are never broken in the session at 2x (planted) or at
    random (Z1)."""
    rng = np.random.default_rng(seed)
    d0, _ = BE.synth(seed, False, sessions=sessions, nbar=nbar)   # prices (and a plain volume we replace below)
    o, h, l, c = (d0[k].to_numpy() for k in ("open", "high", "low", "close"))
    n = len(c); slot = np.tile(np.arange(nbar), sessions); u = 1 + 1.5 * ((slot - nbar / 2) / (nbar / 2)) ** 2
    e = np.zeros(n); e[0] = rng.normal(0, 0.4)
    for k in range(1, n):
        e[k] = 0.6 * e[k - 1] + rng.normal(0, 0.4 * np.sqrt(1 - 0.36))
    base = pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": 1e5 * u}, index=d0.index)
    res = TM.run(base, 5); Y = TM.targets(res)
    vmult = np.ones(n); planted_break = np.zeros(n, bool); planted_level = np.zeros(n, bool)
    br = Y["breaks"]
    if len(br):
        hit = (br["hold"] > 0).to_numpy(); known = np.isfinite(br["hold"]).to_numpy(); b_ = float(hit[known].mean()) if known.any() else 0.25
        qh, qm = (min(0.95, 0.3 * 0.45 / b_), min(0.95, 0.3 * 0.55 / (1 - b_))) if planted else (0.3, 0.3)
        for t, hh in zip(br["t"], hit):
            if rng.random() < (qh if hh else qm):
                vmult[t] *= 2.5; planted_break[t] = True
    # levels never broken in the session: all touch bars of such levels at 2x (planted) or of random levels (Z1)
    tc = Y["touches"]
    if len(tc):
        broken_ids = set(br["level_id"]) if len(br) else set()
        for lid, g in tc.groupby("level_id"):
            respected = lid not in broken_ids
            if (respected if planted else rng.random() < 0.5):
                for t in g["t"]:
                    vmult[int(t)] *= 2.0; planted_level[int(t)] = True
    v = 1e5 * u * vmult * np.exp(e)
    d = pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": v}, index=d0.index)
    return d, planted_break, planted_level


def run_planted(seeds=range(50000, 50040)):
    t0 = time.time(); res = {}
    for mode, planted in (("Z1", False), ("Z2", True)):
        items = []; PB = {}
        for s in seeds:
            d, pb, pl = synth(s, planted); items.append((str(s), d)); PB[str(s)] = (pb, pl)
        T, C, B = collect(items, 5, False)
        for df in (T, C, B):
            df["train"] = (df["sym"].astype(int) % 2 == 1)
        trT, teT = T["train"].to_numpy(bool), ~T["train"].to_numpy(bool)
        trC, teC = C["train"].to_numpy(bool), ~C["train"].to_numpy(bool)
        trB, teB = B["train"].to_numpy(bool), ~B["train"].to_numpy(bool)
        r = {"n": {"trend": int(teT.sum()), "touches": int(teC.sum()), "breaks": int(teB.sum())},
             "J_vs_J0": paired(T, "J", "J0", "alive12", trT, teT), "S_vs_S0": paired(T, "S", "S0", "alive12", trT, teT),
             "mass_vs_time_respect": paired(C, "mass", "time", "respect", trC, teC, 66.7),
             "E_vs_E0_hold": paired(B, "E", "E0", "hold", trB, teB), "retest_quiet_vs_small": None}
        bb = B.copy(); bb["neg_rv"] = -bb["ratio_v"]; bb["neg_rr"] = -bb["ratio_r"]
        r["retest_quiet_vs_small"] = paired(bb, "neg_rv", "neg_rr", "retest_hold", trB, teB)
        if planted:
            hit = (B["hold"] > 0).astype(float).where(np.isfinite(B["hold"])).to_numpy()
            pb = np.array([PB[s][0][t] for s, t in zip(B["sym"], B["t"])]); m = teB & np.isfinite(hit)
            r["planted_hold_lift"] = round(float(np.nanmean(hit[m & pb]) / np.nanmean(hit[m])), 3)
            r["recovered_E"] = round((r["E_vs_E0_hold"]["lift"] - 1) / (r["planted_hold_lift"] - 1), 3) if r["planted_hold_lift"] > 1 else None
            resp = C["respect"].to_numpy(float); pl = np.array([PB[s][1][t] for s, t in zip(C["sym"], C["t"])]); mc = teC & np.isfinite(resp)
            r["planted_respect_lift"] = round(float(np.nanmean(resp[mc & pl]) / np.nanmean(resp[mc])), 3)
            r["recovered_mass"] = round((r["mass_vs_time_respect"]["lift"] - 1) / (r["planted_respect_lift"] - 1), 3) if r["planted_respect_lift"] > 1 else None
            z1 = res["Z1"]
            r["twins_unchanged"] = bool(abs(z1["E_vs_E0_hold"]["control"] - r["E_vs_E0_hold"]["control"]) < 0.01 and abs(z1["mass_vs_time_respect"]["control"] - r["mass_vs_time_respect"]["control"]) < 0.01)
            r["pass"] = bool((r["recovered_E"] or 0) >= 0.7 and (r["recovered_mass"] or 0) >= 0.7 and r["twins_unchanged"])
        else:
            # broken = the volume quantity itself shows information (own lift > 1) and beats its twin; beating a twin
            # that is itself negative (small retest bars fail) is not information (dated in PREREG)
            r["broken"] = [k for k in ("J_vs_J0", "S_vs_S0", "mass_vs_time_respect", "E_vs_E0_hold", "retest_quiet_vs_small") if r[k].get("diff_lo", -1) > 0 and r[k].get("lift_lo", 0) > 1]
            r["pass"] = len(r["broken"]) == 0
        res[mode] = r
        print(mode, {k: v for k, v in r.items() if k in ("n", "broken", "pass", "planted_hold_lift", "recovered_E", "planted_respect_lift", "recovered_mass", "twins_unchanged")}, f"{time.time() - t0:.0f}s", flush=True)
    os.makedirs(OUT, exist_ok=True)
    json.dump(res, open(os.path.join(OUT, "planted.json"), "w"), indent=1)


# ---------------- HMM check (two states, diagonal Gaussians, EM) ----------------
def hmm_fit(X, iters=40, seed=0):
    rng = np.random.default_rng(seed); n, dmn = X.shape
    mu = X[rng.choice(n, 2, replace=False)]; var = np.tile(X.var(0) + 1e-6, (2, 1)); pi = np.array([.5, .5]); Atr = np.array([[.95, .05], [.05, .95]])
    def logB(X):
        return np.stack([-0.5 * np.sum((X - mu[k]) ** 2 / var[k] + np.log(2 * np.pi * var[k]), 1) for k in range(2)], 1)
    for _ in range(iters):
        lb = logB(X); la = np.zeros((n, 2)); la[0] = np.log(pi) + lb[0]
        for t in range(1, n):
            la[t] = lb[t] + np.logaddexp(la[t - 1, 0] + np.log(Atr[0]), la[t - 1, 1] + np.log(Atr[1]))
        lbw = np.zeros((n, 2))
        for t in range(n - 2, -1, -1):
            lbw[t] = np.logaddexp(np.log(Atr[:, 0]) + lb[t + 1, 0] + lbw[t + 1, 0], np.log(Atr[:, 1]) + lb[t + 1, 1] + lbw[t + 1, 1])
        lg = la + lbw; lg -= lg.max(1, keepdims=True); g = np.exp(lg); g /= g.sum(1, keepdims=True)
        xi = np.zeros((2, 2))
        for t in range(n - 1):
            m = la[t][:, None] + np.log(Atr) + (lb[t + 1] + lbw[t + 1])[None, :]; m = np.exp(m - m.max()); xi += m / m.sum()
        Atr = xi / xi.sum(1, keepdims=True); pi = g[0]
        for k in range(2):
            w = g[:, k][:, None]; mu[k] = (w * X).sum(0) / w.sum(); var[k] = (w * (X - mu[k]) ** 2).sum(0) / w.sum() + 1e-6
    return dict(mu=mu, var=var, pi=pi, A=Atr)


def hmm_decode(model, X):
    mu, var, pi, Atr = model["mu"], model["var"], model["pi"], model["A"]; n = len(X)
    lb = np.stack([-0.5 * np.sum((X - mu[k]) ** 2 / var[k] + np.log(2 * np.pi * var[k]), 1) for k in range(2)], 1)
    V = np.zeros((n, 2)); bp = np.zeros((n, 2), int); V[0] = np.log(pi) + lb[0]
    for t in range(1, n):
        for k in range(2):
            cand = V[t - 1] + np.log(Atr[:, k]); bp[t, k] = int(np.argmax(cand)); V[t, k] = cand[bp[t, k]] + lb[t, k]
    path = np.zeros(n, int); path[-1] = int(np.argmax(V[-1]))
    for t in range(n - 2, -1, -1):
        path[t] = bp[t + 1, path[t + 1]]
    trending = int(np.argmax(mu[:, 0]))          # the state with the higher inertia
    return (path == trending).astype(int)


# ---------------- calibration ----------------
def calib(train_key, train_hit, test_key, test_hit):
    tab = pd.DataFrame({"k": train_key, "h": train_hit}).dropna().groupby("k")["h"].agg(["mean", "size"])
    p = pd.Series(test_key).map(tab["mean"]).to_numpy(float); ok = np.isfinite(p) & np.isfinite(test_hit)
    if ok.sum() < 50:
        return {"n": int(ok.sum())}
    base = float(np.nanmean(train_hit)); y = test_hit[ok]; pp = p[ok]
    bins = np.clip((pp * 10).astype(int), 0, 9); rel = [(round(float(pp[bins == b].mean()), 3), round(float(y[bins == b].mean()), 3), int((bins == b).sum())) for b in range(10) if (bins == b).sum() >= 30]
    slope = float(np.polyfit(pp, y, 1)[0]) if pp.std() > 1e-6 else np.nan
    return dict(n=int(ok.sum()), brier=round(float(np.mean((pp - y) ** 2)), 4), brier_base=round(float(np.mean((base - y) ** 2)), 4), slope=round(slope, 3), reliability=rel, table={str(k): [round(float(v["mean"]), 3), int(v["size"])] for k, v in tab.iterrows()})


# ---------------- real data ----------------
def run_verdict():
    from vzones.assistant import data as D
    from vzones.assistant.eyes import group_of
    t0 = time.time()
    syms = sorted(f[:-7] for f in os.listdir(D.BARS) if f.endswith("_5m.csv"))
    F = {s: E.frames(s) for s in syms}
    days = sorted(set().union(*[set(F[s][390].index.date) for s in syms]))
    cut = days[int(0.6 * len(days))]
    res = {"split": {"train_end_before": str(cut)}, "tf": {}}
    for tf in (5, 15):
        T, C, B = collect([(s, F[s][tf]) for s in syms], tf, True, cut)
        out = {"n_test": {"trend": int((~T["train"]).sum()), "touches": int((~C["train"]).sum()), "breaks": int((~B["train"]).sum())}}
        trT, teT = T["train"].to_numpy(bool), ~T["train"].to_numpy(bool)
        trC, teC = C["train"].to_numpy(bool), ~C["train"].to_numpy(bool)
        trB, teB = B["train"].to_numpy(bool), ~B["train"].to_numpy(bool)
        # (a) trend strength
        a = {"J_vs_J0_alive12": paired(T, "J", "J0", "alive12", trT, teT), "S_vs_S0_alive12": paired(T, "S", "S0", "alive12", trT, teT),
             "S_vs_S0_alive24": paired(T, "S", "S0", "alive24", trT, teT), "I_alone_alive12": paired(T, "I", "I", "alive12", trT, teT)}
        hitfp = np.where(np.isfinite(T["fp"]), (T["fp"] > 0).astype(float), np.nan); T["fp_hit"] = hitfp
        a["S_vs_S0_fp"] = paired(T, "S", "S0", "fp_hit", trT, teT)
        # survival by S quintile (test)
        qs = np.nanpercentile(T["S"][trT], [20, 40, 60, 80]); T["qS"] = np.searchsorted(qs, T["S"])
        surv = {}
        for qq in range(5):
            sub = T[teT & (T["qS"] == qq)]
            surv[qq] = [round(float(((sub["life"] >= b) | (~sub["censored"] & (sub["life"] < b))).pipe(lambda m: (sub["life"][m] >= b).mean())), 3) if len(sub) >= 50 else None for b in (3, 6, 12, 24)]
        a["survival_by_S_quintile_at_3_6_12_24"] = surv
        out["a_trend"] = {k: (dict(v, label=label(v)) if "lift" in v else v) for k, v in a.items()}
        # (b) mass
        b = {"mass_vs_time_respect": paired(C, "mass", "time", "respect", trC, teC, 66.7)}
        C2 = C[C["n_touch"] >= 2].reset_index(drop=True)
        b["mass_vs_time_respect_2nd_touch_plus"] = paired(C2, "mass", "time", "respect", C2["train"].to_numpy(bool), ~C2["train"].to_numpy(bool), 66.7)
        bb = B.copy(); bb["neg_mass"] = -bb["mass"]; bb["neg_time"] = -bb["time"]
        b["low_mass_vs_low_time_hold"] = paired(bb, "neg_mass", "neg_time", "hold", trB, teB, 66.7)
        out["b_mass"] = {k: dict(v, label=label(v)) if "lift" in v else v for k, v in b.items()}
        # (c) breaks
        c = {"E_vs_E0_hold": paired(B, "E", "E0", "hold", trB, teB), "E_vs_E0_false": None}
        bb["not_false"] = 1 - bb["false"]
        c["E_vs_E0_not_false"] = paired(bb, "E", "E0", "not_false", trB, teB)
        # activation energy rule vs the twin rule
        held = trB & (B["hold"] > 0) & np.isfinite(B["mass"]) & (B["mass"] > 0)
        cst = float(np.nanmedian((B["E"] / B["mass"])[held])); e0q = float(np.nanpercentile(B["E0"][trB], 60))
        powered = (B["E"] > cst * B["mass"]).to_numpy(); twin = (B["E0"] > e0q).to_numpy()
        hold = B["hold"].to_numpy(float); ok = teB & np.isfinite(hold)
        c["activation_rule"] = dict(c=round(cst, 4), share_powered=round(float(powered[ok].mean()), 3), hold_powered=round(float(np.nanmean(hold[ok & powered])), 3), hold_not=round(float(np.nanmean(hold[ok & ~powered])), 3),
                                    share_twin=round(float(twin[ok].mean()), 3), hold_twin=round(float(np.nanmean(hold[ok & twin])), 3), hold_twin_not=round(float(np.nanmean(hold[ok & ~twin])), 3))
        # grid E tercile x mass tercile
        te_e = np.nanpercentile(B["E"][trB], [33.3, 66.7]); te_m = np.nanpercentile(B["mass"][trB], [33.3, 66.7])
        ge = np.searchsorted(te_e, B["E"]); gm = np.searchsorted(te_m, B["mass"])
        c["grid_E_x_mass_hold"] = [[round(float(np.nanmean(hold[ok & (ge == i) & (gm == j)])), 3) if np.isfinite(hold[ok & (ge == i) & (gm == j)]).sum() >= 20 else None for j in range(3)] for i in range(3)]
        # flags on the false-break rate
        false = B["false"].to_numpy(float); okf = teB & np.isfinite(false)
        iq = float(np.nanpercentile(B["I"][trB], 20)); B["exhausted"] = B["I"] < iq; B["abs_or_counter"] = B["absorption"] | B["counter"]
        rng = np.random.default_rng(0); blk = B["block"].to_numpy()
        def rate(mask):
            if mask.sum() < 10:
                return dict(n=int(mask.sum()))
            bl = np.unique(blk[mask]); idx = {x: np.where((blk == x) & mask)[0] for x in bl}
            bs = [false[np.concatenate([idx[bl[p]] for p in rng.integers(0, len(bl), len(bl))])].mean() for _ in range(1000)]
            return dict(n=int(mask.sum()), rate=round(float(false[mask].mean()), 3), lo=round(float(np.percentile(bs, 2.5)), 3), hi=round(float(np.percentile(bs, 97.5)), 3))
        c["flags_false_break"] = {fl: {"with": rate(okf & B[fl].to_numpy(bool)), "without": rate(okf & ~B[fl].to_numpy(bool))} for fl in ("absorption", "wick", "counter", "exhausted", "abs_or_counter")}
        for fl, v in c["flags_false_break"].items():
            v["ships"] = bool(v["with"].get("lo", 0) > v["without"].get("hi", 1))
        # retest
        bb["neg_rv"] = -bb["ratio_v"]; bb["neg_rr"] = -bb["ratio_r"]
        c["retest_quiet_vs_small"] = paired(bb, "neg_rv", "neg_rr", "retest_hold", trB, teB)
        c["retest_n"] = int(np.isfinite(B["retest_hold"][teB]).sum()); c["retest_hold_base"] = round(float(np.nanmean(B["retest_hold"][teB])), 3)
        c["E_vs_E0_hold"]["label"] = label(c["E_vs_E0_hold"]); c["E_vs_E0_not_false"]["label"] = label(c["E_vs_E0_not_false"]); c["retest_quiet_vs_small"]["label"] = label(c["retest_quiet_vs_small"])
        c.pop("E_vs_E0_false")
        # up / down and groups for E and S
        if tf == 5:
            c["by_direction"] = {dn: dict(paired(B[B["dir"] == dv].reset_index(drop=True), "E", "E0", "hold", trB[(B["dir"] == dv).to_numpy()], teB[(B["dir"] == dv).to_numpy()])) for dn, dv in (("up", 1), ("down", -1))}
            grp = B["sym"].map(group_of).to_numpy(); gT = T["sym"].map(group_of).to_numpy()
            c["groups_E"] = {g: paired(B[grp == g].reset_index(drop=True), "E", "E0", "hold", trB[grp == g], teB[grp == g]) for g in ("index", "mega", "high_beta")}
            a["groups_S"] = {g: paired(T[gT == g].reset_index(drop=True), "S", "S0", "alive12", trT[gT == g], teT[gT == g]) for g in ("index", "mega", "high_beta")}
            out["a_trend"]["groups_S"] = a["groups_S"]
        out["c_breaks"] = c
        # (d) HMM check on 5m: fit on train bars of 10 tune symbols, decode test, agreement with |state| and Brier add
        if tf == 5:
            Xtr, Xte, rows = [], [], []
            for s in E.SYMS if hasattr(E, "SYMS") else syms[:10]:
                pass
            tune = ["SPY", "QQQ", "AAPL", "AMZN", "META", "NVDA", "TSLA", "AMD", "PLTR", "COIN"]
            for s in tune:
                r_ = TM.run(F[s][5], 5); bars = r_["bars"]; sess = r_["frames"]["sess"]
                X = np.c_[bars["I"].to_numpy(), np.log(np.where(bars["rvol"] > 0, bars["rvol"], np.nan))]; okb = np.isfinite(X).all(1)
                trm = np.array([x < cut for x in sess]) & okb; tem = ~np.array([x < cut for x in sess]) & okb
                Xtr.append(X[trm][::5]); rows.append((s, X, tem, bars["state"].to_numpy(), sess))
            model = hmm_fit(np.vstack(Xtr)[:20000])
            agree, keys = [], []
            for s, X, tem, state, sess in rows:
                okb = np.isfinite(X).all(1); z = np.full(len(X), -1); z[okb] = hmm_decode(model, X[okb])
                agree.append(float(np.mean((z[tem] == 1) == (np.abs(state[tem]) == 1))))
            out["d_hmm"] = dict(agreement_with_hull_state=round(float(np.mean(agree)), 3), mu=model["mu"].round(3).tolist(), note="agreement = share of test bars where HMM 'trending' matches |Hull state| = 1")
        # (e) calibration tables
        T["key"] = T["dir"].astype(str) + "|" + T["qS"].astype(str)
        hit12 = T["alive12"].to_numpy(float)
        qs0 = np.nanpercentile(T["S0"][trT], [20, 40, 60, 80]); T["key0"] = T["dir"].astype(str) + "|" + pd.Series(np.searchsorted(qs0, T["S0"])).astype(str)
        B["key"] = pd.Series(ge).astype(str) + "|" + pd.Series(gm).astype(str) + "|" + B["dir"].astype(str)
        te0 = np.nanpercentile(B["E0"][trB], [33.3, 66.7]); B["key0"] = pd.Series(np.searchsorted(te0, B["E0"])).astype(str) + "|" + B["dir"].astype(str)
        B["fkey"] = B["absorption"].astype(int).astype(str) + B["counter"].astype(int).astype(str) + B["wick"].astype(int).astype(str)
        out["e_calibration"] = {"alive12_by_S": calib(T["key"][trT], hit12[trT], T["key"][teT], hit12[teT]), "alive12_by_S0": calib(T["key0"][trT], hit12[trT], T["key0"][teT], hit12[teT]),
                                "hold_by_E_mass": calib(B["key"][trB], hold[trB], B["key"][teB], hold[teB]), "hold_by_E0": calib(B["key0"][trB], hold[trB], B["key0"][teB], hold[teB]),
                                "false_by_flags": calib(B["fkey"][trB], false[trB], B["fkey"][teB], false[teB])}
        res["tf"][tf] = out
        print(tf, json.dumps({k: (v.get("label"), v.get("lift"), v.get("control"), v.get("diff")) for k, v in out["a_trend"].items() if isinstance(v, dict) and "lift" in v}), flush=True)
        print(tf, "mass", {k: (v.get("label"), v.get("lift"), v.get("control")) for k, v in out["b_mass"].items() if isinstance(v, dict)}, flush=True)
        print(tf, "breaks", {k: (v.get("label"), v.get("lift"), v.get("control"), v.get("diff")) for k, v in c.items() if isinstance(v, dict) and "lift" in v}, c["activation_rule"], f"{time.time() - t0:.0f}s", flush=True)
        json.dump(res, open(os.path.join(OUT, "verdict.json"), "w"), indent=1, default=lambda x: None if isinstance(x, float) and not np.isfinite(x) else (x.item() if hasattr(x, "item") else str(x)))
    print(f"{time.time() - t0:.0f}s")


if __name__ == "__main__":
    {"planted": run_planted, "verdict": run_verdict}[sys.argv[1]]()
