"""Tests of reports/trend_volume/PREREG.md.

    python tools/trend_volume_eval.py planted    # Q1 (no relation) and Q2 (planted) on fresh seeds 30000..30039
    python tools/trend_volume_eval.py verdict    # real SIP data, 5m / 15m / 1h, paired against the price-only control
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
from vzones import volume_tool as VT  # noqa: E402
import volume_tool_eval as E  # noqa: E402

OUT = os.path.join(ROOT, "reports", "trend_volume")
MEASURES = ["P", "v_res", "leg_over_pull", "udR", "delta", "obv_div", "effort_result", "control"]
NY = "America/New_York"


# ---------------- synthetic: legs, pullbacks, resumptions, with a volume regime ----------------
def synth(seed: int, planted: bool, sessions: int = 250, nbar: int = 78):
    """Prices first (legs, pullbacks, flat stretches), the detector's own events on them, then volume: every pullback
    at 0.6x, the resumption bar at 2x with a probability that depends on the event's outcome when `planted` (so that
    P(continue | strong resumption, weak pullback) = 0.70) and does not when not (Q1)."""
    rng = np.random.default_rng(seed)
    n = sessions * nbar
    days = pd.bdate_range("2025-01-02", periods=sessions)
    idx = pd.DatetimeIndex([pd.Timestamp(f"{d.date()} 09:30") + pd.Timedelta(minutes=5 * k) for d in days for k in range(nbar)]).tz_localize(NY)
    slot = np.tile(np.arange(nbar), sessions)
    u = 1 + 1.5 * ((slot - nbar / 2) / (nbar / 2)) ** 2
    sig = 0.001
    drift = np.zeros(n)
    i = 0; dr = rng.choice([-1, 1])
    while i < n:
        L = int(rng.integers(20, 80)); drift[i:min(n, i + L)] = dr * 0.3 * sig; i += L
        pl = int(rng.integers(3, 9)); drift[i:min(n, i + pl)] = -dr * 0.3 * sig; i += pl
        if int(rng.integers(0, 4)) == 0:
            F = int(rng.integers(10, 40)); drift[i:min(n, i + F)] = 0; i += F
        dr = dr if rng.random() < 0.5 else -dr
    r = drift + rng.normal(0, sig, n)
    c = 100 * np.exp(np.cumsum(r)); o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, 0.0004, n))); l = np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.0004, n)))
    e = np.zeros(n); e[0] = rng.normal(0, 0.4)
    for k in range(1, n):
        e[k] = 0.6 * e[k - 1] + rng.normal(0, 0.4 * np.sqrt(1 - 0.36))
    vmult = np.ones(n)
    d0 = pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": 1e5 * u}, index=idx)
    Fr, ev, _ = TV.detect(d0, 5)                       # events depend on price only
    planted_bar = np.zeros(n, bool)
    if len(ev):
        Y = TV.targets(Fr, ev)
        hit = (Y["R1"] > 0).to_numpy(); known = np.isfinite(Y["R1"]).to_numpy()
        b_ = float(hit[known].mean()) if known.any() else 0.5
        q_hit, q_miss = (min(0.95, 0.35 / b_), min(0.95, 0.15 / (1 - b_))) if planted else (0.5, 0.5)
        for t, ps, hh in zip(Y["t"], Y["pull_start"], hit):
            vmult[ps:t] = 0.6
            if rng.random() < (q_hit if hh else q_miss):
                vmult[t] = 2.0; planted_bar[t] = True
    v = 1e5 * u * vmult * np.exp(e)
    d = pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": v}, index=idx)
    return d, planted_bar


def collect(items, tf, sym_of, train_mask_of=None):
    """items: iterable of (name, DataFrame). Returns the event table with sym, block, train flag and targets."""
    rows = []
    for name, d in items:
        F, ev, clx = TV.detect(d, tf)
        if len(ev) == 0:
            continue
        Y = TV.targets(F, ev)
        Y["sym"] = sym_of(name); Y["date"] = [str(F["sess"][t]) for t in Y["t"]]
        Y["block"] = Y["sym"] + "|" + Y["date"]
        Y["slot"] = [int((d.index[t].hour * 60 + d.index[t].minute - 570) // tf) for t in Y["t"]]
        if train_mask_of is not None:
            Y["train"] = [train_mask_of(F["sess"][t]) for t in Y["t"]]
        rows.append(Y)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def evaluate(EV: pd.DataFrame, train: np.ndarray, test: np.ndarray, target="R1"):
    hit = np.where(np.isfinite(EV[target]), (EV[target] > 0).astype(float) if target == "R1" else EV[target], np.nan)
    out = {"n_events_test": int(np.isfinite(hit[test]).sum()), "base": round(float(np.nanmean(hit[test])), 4), "measures": {}}
    ec = float(np.nanpercentile(EV["control"][train], 80))
    for m in MEASURES:
        x = EV[m].to_numpy(float)
        em = float(np.nanpercentile(x[train], 80))
        pl = TV.paired_lift(x[test], EV["control"].to_numpy(float)[test], hit[test], EV["block"].to_numpy()[test], em, ec)
        ic = VT.ic_pooled(x[test], EV["R1_cont"].to_numpy(float)[test], EV["block"].to_numpy()[test], EV["sym"].to_numpy()[test])
        # hit rate by quintile (edges from train)
        q = np.nanpercentile(x[train], [20, 40, 60, 80]); dec = np.searchsorted(q, x[test])
        byq = [round(float(np.nanmean(hit[test][dec == k])), 3) if np.isfinite(hit[test][dec == k]).sum() >= 10 else None for k in range(5)]
        out["measures"][m] = dict(edge=round(em, 4), **pl, ic=round(ic[0], 4), ic_lo=round(ic[1][0], 4), ic_hi=round(ic[1][1], 4), by_quintile=byq)
    return out


def run_planted(seeds=range(30000, 30040)):
    t0 = time.time()
    res = {}
    for mode, planted in (("Q1", False), ("Q2", True)):
        items, PB = [], {}
        for s in seeds:
            d, pb = synth(s, planted); items.append((str(s), d)); PB[str(s)] = pb
        EV = collect(items, 5, lambda nm: nm)
        n = len(EV); tr = np.zeros(n, bool); te = np.ones(n, bool)
        # quintile edges must come from "train": use the odd seeds as train, even as test (the gate is on the even ones)
        tr = (EV["sym"].astype(int) % 2 == 1).to_numpy(); te = ~tr
        r = evaluate(EV, tr, te)
        if planted:
            hit = (EV["R1"] > 0).astype(float).where(np.isfinite(EV["R1"])).to_numpy()
            pb = np.array([PB[s][t] for s, t in zip(EV["sym"], EV["t"])])
            cond = (EV["v_res"] > 1.5) & (EV["v_pull"] < 0.8)
            m = te & np.isfinite(hit)
            r["planted_lift_generator"] = round(float(np.nanmean(hit[m & pb]) / np.nanmean(hit[m])), 3)
            r["planted_lift_condition"] = round(float(np.nanmean(hit[m & cond.to_numpy()]) / np.nanmean(hit[m])), 3)
            r["share_events_planted"] = round(float(pb[m].mean()), 3)
            got = r["measures"]["P"]["lift"]; pl_ = r["planted_lift_condition"]
            r["recovered_share_P"] = round((got - 1) / (pl_ - 1), 3) if pl_ > 1 else None
            r["recovered_share_vres"] = round((r["measures"]["v_res"]["lift"] - 1) / (pl_ - 1), 3) if pl_ > 1 else None
            # the control must not see the plant: Q1 and Q2 share the same prices and events, so its lift must be unchanged
            c1 = res["Q1"]["measures"]["control"]["lift"]; c2 = r["measures"]["control"]["lift"]
            r["control_lift_Q1_vs_Q2"] = [c1, c2]
            r["pass"] = bool(r["recovered_share_P"] is not None and r["recovered_share_P"] >= 0.7 and abs(c1 - c2) < 0.01)
        else:
            # Q1: no measure may beat (or lose to) the price-only control; the raw lift may differ from 1 because the
            # synthetic world's price pattern itself carries information (dated in PREREG)
            bad = [m for m, v in r["measures"].items() if m != "control" and v.get("diff_lo", -1) > 0]
            r["broken"] = bad; r["pass"] = len(bad) == 0
        res[mode] = r
        print(mode, {k: v for k, v in r.items() if k != "measures"}, f"{time.time() - t0:.0f}s", flush=True)
    os.makedirs(OUT, exist_ok=True)
    json.dump(res, open(os.path.join(OUT, "planted.json"), "w"), indent=1)


def run_verdict():
    from vzones.assistant import data as D
    from vzones.assistant.eyes import group_of
    import streak_verdict as SV
    t0 = time.time()
    syms = sorted(f[:-7] for f in os.listdir(D.BARS) if f.endswith("_5m.csv"))
    F = {s: E.frames(s) for s in syms}
    days = sorted(set().union(*[set(F[s][390].index.date) for s in syms]))
    cut = days[int(0.6 * len(days))]
    res = {"split": {"train_end_before": str(cut), "days": len(days)}, "tf": {}}
    for tf in (5, 15, 60):
        EV = collect([(s, F[s][tf]) for s in syms], tf, lambda nm: nm, lambda sess: sess < cut)
        tr = EV["train"].to_numpy(bool); te = ~tr
        out = {"n_events_train": int(tr.sum()), "n_events_test": int(te.sum())}
        for tgt in ("R1", "R2", "R3"):
            out[tgt] = evaluate(EV, tr, te, tgt)
        if tf == 5:
            grp = EV["sym"].map(group_of).to_numpy()
            out["groups"] = {g: evaluate(EV[(grp == g) | tr].reset_index(drop=True), tr[(grp == g) | tr], (te & (grp == g))[(grp == g) | tr]) for g in ("index", "mega", "high_beta")}
            early = EV["slot"].to_numpy() < 6
            out["first30"] = {"open30": evaluate(EV, tr, te & early), "rest": evaluate(EV, tr, te & ~early)}
        # exhaustion: volume climax vs price-only climax, reversal rate on test
        rows = []
        for s in syms:
            Fr, ev, clx = TV.detect(F[s][tf], tf)
            if len(clx):
                C = TV.climax_targets(Fr, clx); C["sym"] = s; C["train"] = [Fr["sess"][t] < cut for t in C["t"]]; C["block"] = s + "|" + pd.Series([str(Fr["sess"][t]) for t in C["t"]])
                rows.append(C)
        CL = pd.concat(rows, ignore_index=True)
        ct = CL[~CL["train"].to_numpy(bool) & np.isfinite(CL["reversal"])]
        vol, prc = ct[ct["volume"]], ct[~ct["volume"]]
        rng = np.random.default_rng(0)
        def rate_ci(df):
            if len(df) < 10:
                return None
            b = df["block"].unique(); idx = {k: np.where(df["block"].to_numpy() == k)[0] for k in b}; r = df["reversal"].to_numpy()
            bs = [r[np.concatenate([idx[b[p]] for p in rng.integers(0, len(b), len(b))])].mean() for _ in range(1000)]
            return dict(n=len(df), rate=round(float(r.mean()), 3), lo=round(float(np.percentile(bs, 2.5)), 3), hi=round(float(np.percentile(bs, 97.5)), 3))
        out["exhaustion"] = {"volume_climax": rate_ci(vol), "price_only_climax": rate_ci(prc)}
        # H4: Hull of VWMA vs Hull, 5m test, flips / noise / trend lag
        if tf == 5:
            fl, nz, lg = [], [], []
            for s in syms:
                d = F[s][5]; o, h, l, c, v = (d[k].to_numpy(float) for k in ("open", "high", "low", "close", "volume"))
                m = np.array([x.date() for x in d.index]) >= cut; m[:200] = False
                for name, M in (("HMA", TV.CM.hma(c, 67)), ("HullVWMA", TV.hull_vwma(c, v, 67))):
                    dm = np.sign(np.diff(M))[m[1:]]; dm = dm[np.isfinite(dm) & (dm != 0)]
                    fl.append((name, 100 * np.sum(dm[1:] != dm[:-1]) / len(dm))); nz.append((name, float(np.nanmean(np.abs(np.diff(M, 2))[m[2:]]) / np.nanmean(np.abs(np.diff(c))[m[1:]]))))
                    lg.append((name, SV.trend_lag_real(lambda *a, M=M: M, o, h, l, c, m)))
            out["hull_vwma_vs_hull"] = {nm: dict(flips=round(float(np.mean([x for n_, x in fl if n_ == nm])), 3), noise=round(float(np.mean([x for n_, x in nz if n_ == nm])), 4), lag=round(float(np.mean([x for n_, x in lg if n_ == nm])), 2)) for nm in ("HMA", "HullVWMA")}
        res["tf"][tf] = out
        print(tf, "events", out["n_events_test"], "R1 base", out["R1"]["base"], "P", out["R1"]["measures"]["P"], "control", out["R1"]["measures"]["control"]["lift"], f"{time.time() - t0:.0f}s", flush=True)
        json.dump(res, open(os.path.join(OUT, "verdict.json"), "w"), indent=1)
    # verdict by the rule
    def beats(tf):
        p = res["tf"][tf]["R1"]["measures"]["P"]; return p.get("diff_lo", -1) > 0 and p.get("lift_lo", 0) > 1
    g_ok = sum(1 for g, v in res["tf"][5]["groups"].items() if v["measures"]["P"].get("diff_lo", -1) > 0)
    rev1h = res["tf"][60]["R1"]["measures"]["P"].get("diff", 0) < 0
    n_tf = sum(1 for tf in (5, 15) if beats(tf))
    label = "works" if n_tf == 2 and g_ok >= 2 and not rev1h else "weak" if n_tf >= 1 or any(res["tf"][tf]["R1"]["measures"]["P"].get("diff", 0) > 0 and res["tf"][tf]["R1"]["measures"]["P"].get("lift_lo", 0) > 1 for tf in (5, 15)) else "no"
    res["verdict"] = dict(label=label, timeframes_beating_control=n_tf, groups_beating_control=g_ok, reversed_on_1h=bool(rev1h))
    json.dump(res, open(os.path.join(OUT, "verdict.json"), "w"), indent=1)
    print(json.dumps(res["verdict"])); print(f"{time.time() - t0:.0f}s")


if __name__ == "__main__":
    {"planted": run_planted, "verdict": run_verdict}[sys.argv[1]]()
