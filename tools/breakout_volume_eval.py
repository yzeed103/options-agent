"""Tests of reports/breakout_volume/PREREG.md.

    python tools/breakout_volume_eval.py planted    # W1 (no relation) and W2 (planted) on fresh seeds 40000..40039
    python tools/breakout_volume_eval.py verdict    # real SIP data, 5m / 15m (1h robustness), every level type
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
from vzones import breakout_volume as BV  # noqa: E402
from vzones import trend_volume as TV  # noqa: E402
from vzones import volume_tool as VT  # noqa: E402
import volume_tool_eval as E  # noqa: E402

OUT = os.path.join(ROOT, "reports", "breakout_volume")
MEASURES = ["rvol", "B", "range_atr", "body", "penetration", "touches", "control"]
HZ = {5: 24, 15: 8, 60: 3}
NY = "America/New_York"


# ---------------- synthetic ----------------
def synth(seed: int, planted: bool, sessions: int = 250, nbar: int = 78, mult: float = 2.0):
    """Random walk with mean-reverting range phases (pivots and breaks occur), U-shaped persistent volume; the
    break bars' volume is set after the breaks are known: 2x with an outcome-dependent probability (W2) or not (W1)."""
    rng = np.random.default_rng(seed)
    n = sessions * nbar
    days = pd.bdate_range("2025-01-02", periods=sessions)
    idx = pd.DatetimeIndex([pd.Timestamp(f"{d.date()} 09:30") + pd.Timedelta(minutes=5 * k) for d in days for k in range(nbar)]).tz_localize(NY)
    slot = np.tile(np.arange(nbar), sessions)
    u = 1 + 1.5 * ((slot - nbar / 2) / (nbar / 2)) ** 2
    sig = 0.001
    x = np.zeros(n); i = 0; lvl = 0.0
    while i < n:
        if rng.random() < 0.5:                                   # range phase: OU around lvl
            L = int(rng.integers(30, 120))
            for j in range(i, min(n, i + L)):
                x[j] = (x[j - 1] if j else 0.0) - 0.08 * ((x[j - 1] if j else 0.0) - lvl) + rng.normal(0, sig)
            i += L
        else:                                                    # drift phase
            L = int(rng.integers(10, 60)); dr = rng.choice([-1, 1])
            for j in range(i, min(n, i + L)):
                x[j] = (x[j - 1] if j else 0.0) + dr * 0.3 * sig + rng.normal(0, sig)
            i += L; lvl = x[min(i, n) - 1]
    c = 100 * np.exp(x); o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, 0.0004, n))); l = np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.0004, n)))
    e = np.zeros(n); e[0] = rng.normal(0, 0.4)
    for k in range(1, n):
        e[k] = 0.6 * e[k - 1] + rng.normal(0, 0.4 * np.sqrt(1 - 0.36))
    vmult = np.ones(n)
    d0 = pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": 1e5 * u}, index=idx)
    Fr, ev = BV.detect(d0, 5, 2)
    planted_bar = np.zeros(n, bool)
    if len(ev):
        Y = BV.targets(Fr, ev, 24)
        hit = (Y["B1"] > 0).to_numpy(); known = np.isfinite(Y["B1"]).to_numpy()
        b_ = float(hit[known].mean()) if known.any() else 0.25
        q_hit, q_miss = (min(0.95, 0.3 * 0.45 / b_), min(0.95, 0.3 * 0.55 / (1 - b_))) if planted else (0.3, 0.3)
        for t, hh in zip(Y["t"], hit):
            if rng.random() < (q_hit if hh else q_miss):
                vmult[t] = mult; planted_bar[t] = True
    v = 1e5 * u * vmult * np.exp(e)
    d = pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": v}, index=idx)
    return d, planted_bar


# ---------------- real levels ----------------
def day_levels(d5: pd.DataFrame, sym: str | None = None) -> pd.DataFrame:
    """prior-day high / low / POC / VAH / VAL and the GEX walls, one row per session date (applied to the next day)."""
    dd = d5.groupby(d5.index.date).agg(pdh=("high", "max"), pdl=("low", "min")).shift(1)
    va = E.day_profile_levels(d5)
    out = dd.join(va, how="left")
    if sym:
        try:
            from vzones.assistant import data as D
            g = D.levels_for_days(sym, list(out.index))[["cw", "pw"]]
            out = out.join(g, how="left")
        except Exception:  # noqa: BLE001
            pass
    return out


def collect(items, tf, k, with_days, cut=None):
    rows = []
    for sym, d in items:
        dl = day_levels(d, sym if isinstance(sym, str) and not sym.isdigit() else None) if with_days else None
        Fr, ev = BV.detect(d, tf, k, dl)
        if len(ev) == 0:
            continue
        Y = BV.targets(Fr, ev, HZ[tf])
        Y["sym"] = str(sym); Y["date"] = [str(Fr["sess"][t]) for t in Y["t"]]; Y["block"] = Y["sym"] + "|" + Y["date"]
        if cut is not None:
            Y["train"] = [Fr["sess"][t] < cut for t in Y["t"]]
        rows.append(Y)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


# ---------------- evaluation ----------------
def evaluate(EV: pd.DataFrame, tr, te, target="B1"):
    y = EV[target].to_numpy(float)
    hit = np.where(np.isfinite(y), (y > 0).astype(float) if target in ("B1", "B2", "B3") else y, np.nan)
    out = {"n_test": int(np.isfinite(hit[te]).sum()), "base": round(float(np.nanmean(hit[te])), 4), "measures": {}}
    if out["n_test"] < 50:
        return out
    ec = float(np.nanpercentile(EV["control"][tr], 80))
    for m in MEASURES:
        x = EV[m].to_numpy(float); em = float(np.nanpercentile(x[tr], 80))
        pl = TV.paired_lift(x[te], EV["control"].to_numpy(float)[te], hit[te], EV["block"].to_numpy()[te], em, ec)
        ic = VT.ic_pooled(x[te], EV["B4"].to_numpy(float)[te], EV["block"].to_numpy()[te], EV["sym"].to_numpy()[te])
        q = np.nanpercentile(x[tr], [20, 40, 60, 80]); dec = np.searchsorted(q, x[te])
        byq = [round(float(np.nanmean(hit[te][dec == j])), 3) if np.isfinite(hit[te][dec == j]).sum() >= 10 else None for j in range(5)]
        out["measures"][m] = dict(edge=round(em, 4), **pl, ic_B4=round(ic[0], 4), ic_lo=round(ic[1][0], 4), ic_hi=round(ic[1][1], 4), by_quintile=byq)
    # grid: range tercile x RVOL tercile of the hit rate
    tr_r = np.nanpercentile(EV["range_atr"][tr], [33.3, 66.7]); tr_v = np.nanpercentile(EV["rvol"][tr], [33.3, 66.7])
    gr = np.searchsorted(tr_r, EV["range_atr"].to_numpy(float)); gv = np.searchsorted(tr_v, EV["rvol"].to_numpy(float))
    grid = [[None] * 3 for _ in range(3)]; inside = 0
    for a in range(3):
        row_mean = np.nanmean(hit[te & (gr == a)]) if np.isfinite(hit[te & (gr == a)]).sum() >= 20 else np.nan
        for b in range(3):
            m = te & (gr == a) & (gv == b)
            grid[a][b] = round(float(np.nanmean(hit[m])), 3) if np.isfinite(hit[m]).sum() >= 20 else None
        if grid[a][2] is not None and np.isfinite(row_mean) and grid[a][2] > row_mean:
            inside += 1
    out["grid_range_x_rvol"] = grid; out["top_rvol_above_mean_in_range_terciles"] = inside
    return out


def run_planted(seeds=range(40000, 40040)):
    t0 = time.time(); res = {}
    for mode, planted, mult in (("W1", False, 2.0), ("W2", True, 2.0), ("W2b", True, 3.0)):
        items, PB = [], {}
        for s in seeds:
            d, pb = synth(s, planted, mult=mult); items.append((str(s), d)); PB[str(s)] = pb
        EV = collect(items, 5, 2, False)
        tr = (EV["sym"].astype(int) % 2 == 1).to_numpy(); te = ~tr
        r = evaluate(EV, tr, te)
        if planted:
            hit = (EV["B1"] > 0).astype(float).where(np.isfinite(EV["B1"])).to_numpy()
            pb = np.array([PB[s][t] for s, t in zip(EV["sym"], EV["t"])]); m = te & np.isfinite(hit)
            r["planted_lift"] = round(float(np.nanmean(hit[m & pb]) / np.nanmean(hit[m])), 3)
            r["recovered_share_rvol_top_quintile"] = round((r["measures"]["rvol"]["lift"] - 1) / (r["planted_lift"] - 1), 3) if r["planted_lift"] > 1 else None
            # the plant sits on ~30% of events; the top quintile (20%) can only catch two thirds of it, so the recovery
            # is judged on the measurement that matches the plant: RVOL > 1.5 (dated in PREREG)
            cond = (EV["rvol"].to_numpy(float) > 1.5)
            r["lift_rvol_gt_1p5"] = round(float(np.nanmean(hit[m & cond]) / np.nanmean(hit[m])), 3)
            r["recovered_share_rvol"] = round((r["lift_rvol_gt_1p5"] - 1) / (r["planted_lift"] - 1), 3) if r["planted_lift"] > 1 else None
            c1, c2 = res["W1"]["measures"]["control"]["lift"], r["measures"]["control"]["lift"]
            r["control_lift_W1_vs_W2"] = [c1, c2]
            # pass on the pre-registered quintile recovery; W2b (a 3x plant) shows whether a miss is the synthetic
            # volume noise or the pipeline (dated in PREREG)
            r["pass"] = bool(r["recovered_share_rvol_top_quintile"] is not None and r["recovered_share_rvol_top_quintile"] >= 0.7 and abs(c1 - c2) < 0.01)
        else:
            # W1 gates the volume measures; price-only measures (penetration, touches, body) may carry price information
            r["broken"] = [m for m, v in r["measures"].items() if m in ("rvol", "B") and v.get("diff_lo", -1) > 0]
            r["pass"] = len(r["broken"]) == 0
        res[mode] = r
        print(mode, {k: v for k, v in r.items() if k not in ("measures", "grid_range_x_rvol")}, f"{time.time() - t0:.0f}s", flush=True)
    os.makedirs(OUT, exist_ok=True)
    json.dump(res, open(os.path.join(OUT, "planted.json"), "w"), indent=1)


def run_verdict():
    from vzones.assistant import data as D
    from vzones.assistant.eyes import group_of
    t0 = time.time()
    syms = sorted(f[:-7] for f in os.listdir(D.BARS) if f.endswith("_5m.csv"))
    F = {s: E.frames(s) for s in syms}
    days = sorted(set().union(*[set(F[s][390].index.date) for s in syms]))
    cut = days[int(0.6 * len(days))]
    res = {"split": {"train_end_before": str(cut)}, "tf": {}}
    for tf in (5, 15, 60):
        out = {}
        for k in ((2, 5) if tf == 5 else (2,)):
            EV = collect([(s, F[s][tf]) for s in syms], tf, k, True, cut)
            if len(EV) == 0:
                continue
            tr = EV["train"].to_numpy(bool); te = ~tr
            for typ in sorted(EV["type"].unique()):
                if k == 5 and not typ.startswith("swing"):
                    continue
                M = (EV["type"] == typ).to_numpy()
                sub = EV[M].reset_index(drop=True); trs = tr[M]; tes = te[M]
                key = f"{typ}_k{k}" if typ.startswith("swing") else typ
                out[key] = {"n_train": int(trs.sum()), "n_test": int(tes.sum())}
                for tgt in ("B1", "B2", "B3"):
                    out[key][tgt] = evaluate(sub, trs, tes, tgt)
                if typ.startswith("swing") and k == 2:
                    for dname, dv in (("up", 1), ("down", -1)):
                        md = (sub["dir"] == dv).to_numpy()
                        out[key][f"B1_{dname}"] = evaluate(sub[md].reset_index(drop=True), trs[md], tes[md], "B1")
                    if tf == 5:
                        grp = sub["sym"].map(group_of).to_numpy()
                        out[key]["groups"] = {g: evaluate(sub[grp == g].reset_index(drop=True), trs[grp == g], tes[grp == g], "B1") for g in ("index", "mega", "high_beta")}
                    # absorption: false-break rate with / without the flag (test), interval over symbol-days
                    ab = sub["absorption"].to_numpy(bool); b3 = sub["B3"].to_numpy(float); ok = tes & np.isfinite(b3)
                    rng = np.random.default_rng(0); blk = sub["block"].to_numpy()
                    def rate(mask):
                        bl = np.unique(blk[mask]); idx = {b: np.where((blk == b) & mask)[0] for b in bl}
                        bs = [b3[np.concatenate([idx[bl[p]] for p in rng.integers(0, len(bl), len(bl))])].mean() for _ in range(1000)] if len(bl) >= 5 else [np.nan]
                        return dict(n=int(mask.sum()), rate=round(float(b3[mask].mean()), 3) if mask.sum() else None, lo=round(float(np.nanpercentile(bs, 2.5)), 3), hi=round(float(np.nanpercentile(bs, 97.5)), 3))
                    out[key]["false_break_absorption"] = {"with_flag": rate(ok & ab), "without": rate(ok & ~ab)}
                    # H6: touches
                    tch = sub["touches"].to_numpy(); b1 = sub["B1"].to_numpy(float)
                    out[key]["B1_by_touches"] = {str(n_): round(float(np.nanmean(b1[tes & (np.minimum(tch, 3) == n_)])), 3) for n_ in (0, 1, 2, 3)}
                print(tf, key, "n", out[key]["n_test"], "B1 base", out[key]["B1"]["base"], "rvol", out[key]["B1"]["measures"].get("rvol", {}).get("lift"), "control", out[key]["B1"]["measures"].get("control", {}).get("lift"), f"{time.time() - t0:.0f}s", flush=True)
        res["tf"][tf] = out
        json.dump(res, open(os.path.join(OUT, "verdict.json"), "w"), indent=1)
    # verdict on swing levels k = 2, both directions pooled per level type: use swing_high (up-breaks) and swing_low (down-breaks)
    def ok_tf(tf):
        r = []
        for typ in ("swing_high_k2", "swing_low_k2"):
            s = res["tf"][tf].get(typ, {}).get("B1", {}).get("measures", {})
            best = max((s.get(m, {}) for m in ("rvol", "B")), key=lambda v: v.get("diff", -9), default={})
            inside = res["tf"][tf].get(typ, {}).get("B1", {}).get("top_rvol_above_mean_in_range_terciles", 0)
            r.append(bool(best.get("diff_lo", -1) > 0 and best.get("lift_lo", 0) > 1 and inside >= 2))
        return all(r), r
    w5, d5 = ok_tf(5); w15, d15 = ok_tf(15)
    size_only = all(res["tf"][tf].get(typ, {}).get("B1", {}).get("measures", {}).get("control", {}).get("lift_lo", 0) > 1 for tf in (5, 15) for typ in ("swing_high_k2", "swing_low_k2"))
    label = "works" if (w5 and w15) else "size only" if size_only else "no"
    ab = all(res["tf"][tf].get(typ, {}).get("false_break_absorption", {}).get("with_flag", {}).get("lo", 0) > res["tf"][tf].get(typ, {}).get("false_break_absorption", {}).get("without", {}).get("hi", 1) for tf in (5, 15) for typ in ("swing_high_k2", "swing_low_k2"))
    res["verdict"] = dict(label=label, detail={"5": d5, "15": d15}, absorption_warning=bool(ab))
    json.dump(res, open(os.path.join(OUT, "verdict.json"), "w"), indent=1)
    print(json.dumps(res["verdict"])); print(f"{time.time() - t0:.0f}s")


if __name__ == "__main__":
    {"planted": run_planted, "verdict": run_verdict}[sys.argv[1]]()
