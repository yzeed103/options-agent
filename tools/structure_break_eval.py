"""Tests of reports/structure_break/PREREG.md.

    python tools/structure_break_eval.py planted   # Y1 (no relation) and Y2 (planted) on fresh seeds 60000..60039
    python tools/structure_break_eval.py verdict   # 1h, 4h (SIP symbols), daily, weekly (universe): excess over random entries, Σ, context, variants, trend rule
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
from vzones import structure_break as SB  # noqa: E402
from vzones import trend_volume as TV  # noqa: E402
import volume_tool_eval as E  # noqa: E402

OUT = os.path.join(ROOT, "reports", "structure_break")
UNI = os.path.join(ROOT, "runtime_sip", "daily_universe")
CLASSES = ["swing5", "swing10", "swing20", "don20", "don55", "pw", "pm", "52w"]


# ---------------- events with targets, pseudo-entries and the trend rule, per symbol ----------------
def evaluate_symbol(d: pd.DataFrame, tf: str, sym: str, ctx=None, spx=None, seed=0, cost_bp=5.0):
    F, Ev = SB.levels_and_breaks(d, tf, ctx, spx)
    if len(Ev) == 0:
        return pd.DataFrame()
    N = SB.N_BARS[tf]; n = len(F["c"]); rng = np.random.default_rng(seed)
    brk = np.zeros(n, bool); brk[Ev["t"].to_numpy(int)] = True
    opp = {1: np.zeros(n, bool), -1: np.zeros(n, bool)}
    for t, dr in zip(Ev["t"], Ev["dir"]):
        opp[-int(dr)][int(t)] = True                     # an opposite-direction break of any class ends a trade
    rows = []
    for _, e in Ev.iterrows():
        t, dr, L = int(e["t"]), int(e["dir"]), float(e["L"])
        base = dict(sym=sym, tf=tf, t=t, dir=dr, cls=e["cls"], L=L, age=e["age"], touches=e["touches"], depth=e["depth"], sig=e["sig"], ctx=int(e["ctx"]), spx=int(e["spx"]),
                    range_atr=e["range_atr"], rvol=e["rvol"], pen=e["pen"], date=str(d.index[t])[:10])
        # variant i
        r = dict(base, variant="i", te=t, **targets_at_safe(F, t, dr, L, N))
        r["R"], r["bars"] = SB.trend_rule(F, t, dr, opp[dr], cost_bp)
        ps = SB.pseudo_entries(n, t, dr, brk, rng)
        pt = [targets_at_safe(F, j, dr, np.nan, N) for j in ps]
        r["ps_fp"] = float(np.nanmean([x["fp"] > 0 for x in pt if np.isfinite(x["fp"])])) if any(np.isfinite(x["fp"]) for x in pt) else np.nan
        r["ps_fp2"] = float(np.nanmean([x["fp2"] > 0 for x in pt if np.isfinite(x["fp2"])])) if any(np.isfinite(x["fp2"]) for x in pt) else np.nan
        pr = [SB.trend_rule(F, j, dr, opp[dr], cost_bp)[0] for j in ps]
        r["ps_R"] = float(np.nanmean(pr)) if len(pr) else np.nan
        rows.append(r)
        # variants ii, iii, iv (same level, different event bar)
        if e["v2"]:
            rows.append(dict(base, variant="ii", te=t, **targets_at_safe(F, t, dr, L, N)))
        if e["t3"] >= 0:
            t3 = int(e["t3"]); rows.append(dict(base, variant="iii", te=t3, **targets_at_safe(F, t3, dr, L, N)))
        if e["t4"] >= 0:
            t4 = int(e["t4"]); rows.append(dict(base, variant="iv", te=t4, **targets_at_safe(F, t4, dr, L, N)))
    # micro-break control: a close above the prior bar's high / below its low, not within 3 bars of a real break
    c, h, l = F["c"], F["h"], F["l"]
    mb = []
    for i in range(1, n):
        if brk[max(0, i - 3):i + 4].any():
            continue
        if c[i] > h[i - 1]:
            mb.append(dict(sym=sym, tf=tf, t=i, dir=1, cls="micro", variant="micro", te=i, date=str(d.index[i])[:10], **targets_at_safe(F, i, 1, np.nan, N)))
        elif c[i] < l[i - 1]:
            mb.append(dict(sym=sym, tf=tf, t=i, dir=-1, cls="micro", variant="micro", te=i, date=str(d.index[i])[:10], **targets_at_safe(F, i, -1, np.nan, N)))
    mb = mb[::5]                                           # thin them, they are many
    return pd.concat([pd.DataFrame(rows), pd.DataFrame(mb)], ignore_index=True)


def targets_at_safe(F, t, dr, L, N):
    try:
        return SB.targets_at(F, t, dr, L, N)
    except Exception:  # noqa: BLE001
        return dict(fp=np.nan, fp2=np.nan, hold=np.nan, mfe=np.nan, mae=np.nan, false=np.nan)


# ---------------- statistics ----------------
def excess(df, block, draws=2000, seed=0):
    """real FP rate, pseudo rate, excess with a bootstrap interval over blocks (events carry their own pseudo mean)."""
    ok = np.isfinite(df["fp"]) & np.isfinite(df["ps_fp"])
    if ok.sum() < 30:
        return dict(n=int(ok.sum()))
    real = (df["fp"][ok] > 0).astype(float).to_numpy(); ps = df["ps_fp"][ok].to_numpy(); b = block[ok.to_numpy()]
    bl = np.unique(b); idx = {x: np.where(b == x)[0] for x in bl}; rng = np.random.default_rng(seed)
    bs = []
    for _ in range(draws):
        rows = np.concatenate([idx[bl[p]] for p in rng.integers(0, len(bl), len(bl))])
        bs.append(real[rows].mean() - ps[rows].mean())
    R = df["R"][ok].to_numpy(float); PR = df["ps_R"][ok].to_numpy(float); okR = np.isfinite(R) & np.isfinite(PR)
    bsR = []
    if okR.sum() >= 30:
        bR = b[okR]; blR = np.unique(bR); idxR = {x: np.where(bR == x)[0] for x in blR}; Rr = R[okR]; PRr = PR[okR]
        for _ in range(1000):
            rows = np.concatenate([idxR[blR[p]] for p in rng.integers(0, len(blR), len(blR))])
            bsR.append((Rr[rows].mean(), PRr[rows].mean()))
    out = dict(n=int(ok.sum()), fp=round(float(real.mean()), 4), pseudo=round(float(ps.mean()), 4), excess=round(float(real.mean() - ps.mean()), 4),
               lo=round(float(np.percentile(bs, 2.5)), 4), hi=round(float(np.percentile(bs, 97.5)), 4),
               fp2=round(float(np.nanmean(df["fp2"][ok] > 0)), 4), ps_fp2=round(float(np.nanmean(df["ps_fp2"][ok])), 4),
               hold=round(float(np.nanmean(df["hold"][ok])), 4), false=round(float(np.nanmean(df["false"][ok])), 4),
               mfe=round(float(np.nanmean(df["mfe"][ok])), 3), mae=round(float(np.nanmean(df["mae"][ok])), 3))
    if bsR:
        a = np.array(bsR)
        out["R"] = dict(real=round(float(Rr.mean()), 4), real_lo=round(float(np.percentile(a[:, 0], 2.5)), 4), real_hi=round(float(np.percentile(a[:, 0], 97.5)), 4),
                        pseudo=round(float(PRr.mean()), 4), hit=round(float((Rr > 0).mean()), 3), n=int(okR.sum()))
    return out


def variant_rate(df):
    ok = np.isfinite(df["fp"])
    return dict(n=int(ok.sum()), fp=round(float((df["fp"][ok] > 0).mean()), 4), false=round(float(np.nanmean(df["false"][ok])), 4), hold=round(float(np.nanmean(df["hold"][ok])), 4)) if ok.sum() >= 30 else dict(n=int(ok.sum()))


def analyse(EV: pd.DataFrame, train: np.ndarray, test: np.ndarray, block: np.ndarray):
    out = {}
    base = (EV["variant"] == "i").to_numpy()
    for cls in CLASSES:
        m = base & (EV["cls"] == cls).to_numpy()
        if (m & test).sum() < 30:
            out[cls] = {"n_test": int((m & test).sum())}; continue
        r = {"n_train": int((m & train).sum()), "n_test": int((m & test).sum()), "all": excess(EV[m & test], block[m & test])}
        for dn, dv in (("up", 1), ("down", -1)):
            mm = m & test & (EV["dir"] == dv).to_numpy(); r[dn] = excess(EV[mm], block[mm])
        for cn, cv in (("with_trend", 1), ("against", -1), ("no_trend", 0)):
            mm = m & test & (EV["ctx"] == cv).to_numpy(); r[cn] = excess(EV[mm], block[mm])
        for vn in ("ii", "iii", "iv"):
            mm = (EV["variant"] == vn).to_numpy() & (EV["cls"] == cls).to_numpy() & test; r[f"variant_{vn}"] = variant_rate(EV[mm])
        if cls.startswith("swing"):
            s = EV["sig"].to_numpy(float); a = EV["age"].to_numpy(float)
            q = np.nanpercentile(s[m & train], [20, 40, 60, 80]); dec = np.searchsorted(q, s)
            r["fp_by_sig_quintile"] = [round(float((EV["fp"][m & test & (dec == k)] > 0).mean()), 3) if (m & test & (dec == k)).sum() >= 20 else None for k in range(5)]
            hit = np.where(np.isfinite(EV["fp"]), (EV["fp"] > 0).astype(float), np.nan)
            r["sig_vs_age"] = TV.paired_lift(s[m & test], a[m & test], hit[m & test], block[m & test], float(np.nanpercentile(s[m & train], 80)), float(np.nanpercentile(a[m & train], 80)))
            # volume, secondary: RVOL vs bar size on FP
            r["rvol_vs_size"] = TV.paired_lift(EV["rvol"].to_numpy(float)[m & test], EV["range_atr"].to_numpy(float)[m & test], hit[m & test], block[m & test],
                                               float(np.nanpercentile(EV["rvol"][m & train], 80)), float(np.nanpercentile(EV["range_atr"][m & train], 80)))
        out[cls] = r
    mm = (EV["cls"] == "micro").to_numpy() & test
    out["micro_control"] = variant_rate(EV[mm])
    return out


# ---------------- synthetic ----------------
def synth(seed: int, planted: bool, n: int = 3000, regimes: bool = False, plant_atr: float = 0.6):
    """Y1 / Y2 world: a pure random walk (a martingale: no break can carry information unless planted). With
    `regimes`, the earlier trend / range world (its ranges mean-revert, so breaks there are negative by construction;
    kept as the Y0 sanity check)."""
    rng = np.random.default_rng(seed); sig = 0.01
    x = np.zeros(n); i = 0; lvl = 0.0
    if not regimes:
        x = np.cumsum(rng.normal(0, sig, n)); i = n
    while i < n:
        if rng.random() < 0.5:
            L = int(rng.integers(30, 120))
            for j in range(i, min(n, i + L)):
                x[j] = (x[j - 1] if j else 0.0) - 0.08 * ((x[j - 1] if j else 0.0) - lvl) + rng.normal(0, sig)
            i += L
        else:
            L = int(rng.integers(10, 60)); dr = rng.choice([-1, 1])
            for j in range(i, min(n, i + L)):
                x[j] = (x[j - 1] if j else 0.0) + dr * 0.3 * sig + rng.normal(0, sig)
            i += L; lvl = x[min(i, n) - 1]
    r = np.diff(x, prepend=0.0)
    c = 100 * np.exp(np.cumsum(r)); o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, 0.004, n))); l = np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.004, n)))
    idx = pd.bdate_range("2012-01-02", periods=n)
    d = pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": 1e6 * np.exp(rng.normal(0, 0.4, n))}, index=idx)
    planted_bar = np.zeros(n, bool)
    if planted:
        F, Ev = SB.levels_and_breaks(d, "D")
        sw = Ev[Ev["cls"].str.startswith("swing")]
        if len(sw):
            q = np.nanpercentile(sw["sig"], 80)
            for t, dr, s in zip(sw["t"], sw["dir"], sw["sig"]):
                if s >= q and rng.random() < 0.7:
                    t = int(t); a = t + 1; b = min(n, t + 11)
                    r[a:b] += dr * plant_atr * (np.nanmean(F["A"][t]) / c[t]) / 10     # plant_atr ATR of drift over the next 10 bars
                    planted_bar[t] = True
            c = 100 * np.exp(np.cumsum(r)); o = np.r_[c[0], c[:-1]]
            h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, 0.004, n))); l = np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.004, n)))
            d = pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": d["volume"].to_numpy()}, index=idx)
    return d, planted_bar


def run_planted(seeds=range(60000, 60040)):
    t0 = time.time(); res = {}
    for mode, planted, regimes in (("Y0", False, True), ("Y1", False, False), ("Y2", True, False)):
        rows, PB = [], {}
        for s in seeds:
            d, pb = synth(s, planted, regimes=regimes); PB[str(s)] = pb
            ev = evaluate_symbol(d, "D", str(s), seed=s); rows.append(ev)
        EV = pd.concat(rows, ignore_index=True)
        train = (EV["sym"].astype(int) % 2 == 1).to_numpy(); test = ~train
        block = (EV["sym"] + "|" + (EV["t"] // 5).astype(str)).to_numpy()
        r = analyse(EV, train, test, block)
        sw = {k: v for k, v in r.items() if k.startswith("swing")}
        if planted:
            base = (EV["variant"] == "i").to_numpy() & EV["cls"].str.startswith("swing").to_numpy() & test
            pb = np.array([PB[s][t] for s, t in zip(EV["sym"], EV["t"])])
            fp = EV["fp"].to_numpy(float); ps = EV["ps_fp"].to_numpy(float); ok = base & np.isfinite(fp) & np.isfinite(ps)
            planted_excess = float((fp[ok & pb] > 0).mean() - ps[ok & pb].mean())
            top = [v["fp_by_sig_quintile"][4] for v in sw.values() if v.get("fp_by_sig_quintile") and v["fp_by_sig_quintile"][4] is not None]
            top_excess = float(np.mean(top)) - float(ps[ok].mean()) if top else np.nan
            r["planted_excess"] = round(planted_excess, 4); r["top_sig_excess"] = round(top_excess, 4)
            # the plant hits 70% of the top quintile's events, so the most the quintile can show is 0.7 x the
            # planted excess; recovery is reported against the planted excess and against that achievable maximum
            r["recovered"] = round(top_excess / planted_excess, 3) if planted_excess > 0 else None
            r["recovered_vs_achievable"] = round(top_excess / (0.7 * planted_excess), 3) if planted_excess > 0 else None
            r["sig_beats_age"] = {k: v["sig_vs_age"].get("diff_lo") for k, v in sw.items() if "sig_vs_age" in v}
            r["pseudo_unchanged"] = {k: [res["Y1"][k]["all"].get("pseudo"), v["all"].get("pseudo")] for k, v in sw.items() if "all" in v and k in res["Y1"] and "all" in res["Y1"][k]}
            # gate: recovery and unchanged pseudo rates; "sig beats age" is the real-data hypothesis H2, reported here only
            r["pass"] = bool(r["recovered_vs_achievable"] is not None and r["recovered_vs_achievable"] >= 0.7 and all(abs(a - b) < 0.02 for a, b in r["pseudo_unchanged"].values() if a is not None and b is not None))
        elif mode == "Y1":
            bad = [k for k, v in r.items() if isinstance(v, dict) and "all" in v and (v["all"].get("lo", -1) > 0 or v["all"].get("hi", 1) < 0)]
            r["broken"] = bad; r["pass"] = len(bad) == 0
        else:
            r["note"] = "regime world: ranges mean-revert, so a negative excess here is expected (sanity check, not a gate)"
        res[mode] = r
        print(mode, {k: v for k, v in r.items() if k in ("broken", "pass", "planted_excess", "top_sig_excess", "recovered", "sig_beats_age")}, {k: (v["all"]["fp"], v["all"]["pseudo"], v["all"]["excess"]) for k, v in sw.items() if "all" in v}, f"{time.time() - t0:.0f}s", flush=True)
    os.makedirs(OUT, exist_ok=True)
    json.dump(res, open(os.path.join(OUT, "planted.json"), "w"), indent=1, default=lambda x: None if isinstance(x, float) and not np.isfinite(x) else (x.item() if hasattr(x, "item") else str(x)))


# ---------------- real data ----------------
def load_daily(sym):
    d = pd.read_csv(os.path.join(UNI, f"{sym}.csv"), index_col=0, parse_dates=True)
    return d[["open", "high", "low", "close", "volume"]].astype(float)


def weekly(d):
    agg = dict(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"), volume=("volume", "sum"))
    return d.groupby(pd.Grouper(freq="W-FRI")).agg(**agg).dropna()


def run_verdict():
    t0 = time.time()
    res = {"tf": {}}
    syms_d = sorted(f[:-4] for f in os.listdir(UNI) if f.endswith(".csv"))
    spx_d = load_daily("SPY"); spx_state = pd.Series(SB.hull_state(spx_d["close"].to_numpy()), index=spx_d.index)
    # ---- daily and weekly on the universe
    for tf in ("D", "W"):
        rows = []
        for i, s in enumerate(syms_d):
            d = load_daily(s)
            ctx_d = pd.Series(SB.hull_state(d["close"].to_numpy()), index=d.index)
            if tf == "W":
                dw = weekly(d)
                ctx = ctx_d.reindex(dw.index, method="ffill").fillna(0).to_numpy().astype(int); spx = spx_state.reindex(dw.index, method="ffill").fillna(0).to_numpy().astype(int)
                rows.append(evaluate_symbol(dw, "W", s, ctx, spx, seed=i, cost_bp=2.0 if s in ("SPY", "QQQ") else 5.0))
            else:
                spx = spx_state.reindex(d.index, method="ffill").fillna(0).to_numpy().astype(int)
                rows.append(evaluate_symbol(d, "D", s, ctx_d.to_numpy().astype(int), spx, seed=i, cost_bp=2.0 if s in ("SPY", "QQQ") else 5.0))
            if i % 20 == 0:
                print(tf, i, s, f"{time.time() - t0:.0f}s", flush=True)
        EV = pd.concat(rows, ignore_index=True)
        yr = EV["date"].str[:4].astype(int).to_numpy()
        train = yr <= 2019; val = (yr >= 2020) & (yr <= 2022); test = yr >= 2023
        block = (EV["sym"] + "|" + EV["date"].str[:7]).to_numpy() if tf == "W" else (EV["sym"] + "|" + pd.to_datetime(EV["date"]).dt.strftime("%G-%V")).to_numpy()
        res["tf"][tf] = {"n_events": {"train": int((train & (EV["variant"] == "i")).sum()), "val": int((val & (EV["variant"] == "i")).sum()), "test": int((test & (EV["variant"] == "i")).sum())},
                         "test": analyse(EV, train, test, block), "validation": {k: v.get("all") for k, v in analyse(EV, train, val, block).items() if isinstance(v, dict)}}
        print(tf, {k: (v["all"]["n"], v["all"]["fp"], v["all"]["pseudo"], v["all"]["excess"], v["all"].get("lo"), v["all"].get("hi")) for k, v in res["tf"][tf]["test"].items() if isinstance(v, dict) and "all" in v}, f"{time.time() - t0:.0f}s", flush=True)
        json.dump(res, open(os.path.join(OUT, "verdict.json"), "w"), indent=1, default=lambda x: None if isinstance(x, float) and not np.isfinite(x) else (x.item() if hasattr(x, "item") else str(x)))
    # ---- 1h and 4h on the SIP symbols
    from vzones.assistant import data as D
    syms = sorted(f[:-7] for f in os.listdir(D.BARS) if f.endswith("_5m.csv"))
    agg = dict(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"), volume=("volume", "sum"))
    for tf in ("1h", "4h"):
        rows = []
        for i, s in enumerate(syms):
            d5 = E.frames(s)[5]
            if tf == "1h":
                key = (d5.index - pd.Timedelta(minutes=30)).floor("1h") + pd.Timedelta(minutes=30)
            else:
                key = (d5.index - pd.Timedelta(minutes=30)).floor("4h") + pd.Timedelta(minutes=30)
            dd = d5.groupby(key).agg(**agg)
            dl = d5.groupby(d5.index.date).agg(**agg); ctx_d = pd.Series(SB.hull_state(dl["close"].to_numpy()), index=pd.DatetimeIndex(dl.index))
            ctx = ctx_d.reindex(pd.DatetimeIndex([x.date() for x in dd.index])).fillna(0).to_numpy().astype(int)
            spx = spx_state.reindex(pd.DatetimeIndex([x.date() for x in dd.index]), method="ffill").fillna(0).to_numpy().astype(int)
            rows.append(evaluate_symbol(dd, tf, s, ctx, spx, seed=i, cost_bp=2.0 if s in ("SPY", "QQQ") else 5.0))
        EV = pd.concat(rows, ignore_index=True)
        days = sorted(set(EV["date"])); cut = days[int(0.6 * len(days))]
        train = (EV["date"] < cut).to_numpy(); test = ~train
        block = (EV["sym"] + "|" + pd.to_datetime(EV["date"]).dt.strftime("%G-%V")).to_numpy()
        res["tf"][tf] = {"n_events": {"train": int((train & (EV["variant"] == "i")).sum()), "test": int((test & (EV["variant"] == "i")).sum())}, "split": str(cut), "test": analyse(EV, train, test, block)}
        print(tf, {k: (v["all"]["n"], v["all"]["fp"], v["all"]["pseudo"], v["all"]["excess"], v["all"].get("lo"), v["all"].get("hi")) for k, v in res["tf"][tf]["test"].items() if isinstance(v, dict) and "all" in v}, f"{time.time() - t0:.0f}s", flush=True)
        json.dump(res, open(os.path.join(OUT, "verdict.json"), "w"), indent=1, default=lambda x: None if isinstance(x, float) and not np.isfinite(x) else (x.item() if hasattr(x, "item") else str(x)))
    # ---- verdict per class
    verdict = {}
    for cls in CLASSES:
        tfs_ok = []
        for tf in ("1h", "4h", "D", "W"):
            a = res["tf"].get(tf, {}).get("test", {}).get(cls, {}).get("all", {})
            up = res["tf"].get(tf, {}).get("test", {}).get(cls, {}).get("up", {}); dn = res["tf"].get(tf, {}).get("test", {}).get(cls, {}).get("down", {})
            dir_ok = (up.get("excess", 0) > 0 and dn.get("excess", 0) > 0) or (up.get("lo", -1) > 0 and dn.get("hi", 1) >= 0) or (dn.get("lo", -1) > 0 and up.get("hi", 1) >= 0)
            R = a.get("R", {})
            tfs_ok.append(bool(a.get("lo", -1) > 0 and a.get("fp", 0) >= 0.55 and dir_ok and R.get("real_lo", -1) > 0))
        any_excess = any(res["tf"].get(tf, {}).get("test", {}).get(cls, {}).get("all", {}).get("lo", -1) > 0 for tf in ("1h", "4h", "D", "W"))
        verdict[cls] = dict(label="real continuation" if sum(tfs_ok) >= 2 else "weak" if any_excess else "no", timeframes_ok=int(sum(tfs_ok)))
    res["verdict"] = verdict
    json.dump(res, open(os.path.join(OUT, "verdict.json"), "w"), indent=1, default=lambda x: None if isinstance(x, float) and not np.isfinite(x) else (x.item() if hasattr(x, "item") else str(x)))
    print(json.dumps(verdict)); print(f"{time.time() - t0:.0f}s")


if __name__ == "__main__":
    {"planted": run_planted, "verdict": run_verdict}[sys.argv[1]]()
