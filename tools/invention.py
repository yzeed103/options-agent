"""Invention phase 2: the pre-registered tests of reports/invention/PREREG.md.

    python tools/invention.py
Writes reports/invention/results.json, the pictures, and runtime/regime_model.json (fitted on all data, for live use).
"""
from __future__ import annotations

import json
import os
import pickle
import sys
import time

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from vzones.assistant import data, eyes, regime as R  # noqa: E402
from vzones.assistant.eyes import boot_two_sets  # noqa: E402

OUT = os.path.join(ROOT, "reports", "invention")
CACHE = os.path.join(data.RUNTIME, "invention_frames.pkl")


boot_mae_diff = R.boot_mae_diff


def boot_mean(x: pd.DataFrame, col: str, n=2000, seed=0):
    g = pd.factorize(x.date.astype(str))[0]; k = g.max() + 1
    v = x[col].to_numpy(float)
    s, cn = np.bincount(g, v, k), np.bincount(g, None, k)
    dr = np.random.default_rng(seed).integers(0, k, (n, k))
    bs = s[dr].sum(1) / cn[dr].sum(1)
    return dict(n=len(v), mean=float(v.mean()), lo=float(np.percentile(bs, 2.5)), hi=float(np.percentile(bs, 97.5)))


def main():
    t0 = time.time()
    syms = sorted(f[:-7] for f in os.listdir(data.BARS) if f.endswith("_5m.csv"))
    frames, rows = {}, []
    for s in syms:
        b = data.load_bars(s)
        if len(b) < 2000:
            continue
        d5 = eyes.build(s, b, tfs=(5,), paths=False)[5]
        frames[s] = d5[["open", "high", "low", "close", "atr", "datr", "session", "minute", "sig_tl", "flip", "cw", "pw", "vix"]]
        rows += R.rows_for_symbol(s, d5)
        print(f"{s:6} rows {len(rows):6}  {time.time() - t0:.0f}s", flush=True)
    pickle.dump(frames, open(CACHE, "wb"))
    df = R.usable(pd.DataFrame(rows))
    dates = sorted(df.date.unique())
    cut = dates[int(len(dates) * 0.6)]
    train, test = df[df.date < cut].reset_index(drop=True), df[df.date >= cut].reset_index(drop=True)
    models = R.fit_all(train)
    pt = R.predict(models, test)
    res = {"rows": len(df), "symbols": int(df.sym.nunique()), "dates": [str(dates[0]), str(dates[-1])], "cut": str(cut),
           "train_rows": len(train), "test_rows": len(test), "test_days": int(test.date.nunique())}

    # ---- claim 1: forecast ----
    c1 = []
    for t, g in pt.groupby("time"):
        mae = {k: float((g[f"f_{k}"] - g.y).abs().mean()) for k in ("B1", "B2", "B3", "P")}
        d = boot_mae_diff(g, "f_B3", "f_P")
        c1.append(dict(time=t, n=len(g), **{f"mae_{k}": v for k, v in mae.items()}, b3_minus_p=d["diff"], lo=d["lo"], hi=d["hi"], rel=d["rel"],
                       median_y=float(g.y.median())))
    grp = []
    for (t, gname), g in pt.assign(group=pt.sym.map(eyes.group_of)).groupby(["time", "group"]):
        d = boot_mae_diff(g, "f_B3", "f_P")
        grp.append(dict(time=t, group=gname, n=len(g), mae_B3=float((g.f_B3 - g.y).abs().mean()), mae_P=float((g.f_P - g.y).abs().mean()),
                        b3_minus_p=d["diff"], lo=d["lo"], hi=d["hi"]))
    coef = {t: dict(zip(m["P"].cols, [round(float(x), 4) for x in m["P"].w])) for t, m in models.items()}
    r10 = next(r for r in c1 if r["time"] == "10:00")
    claim1 = (r10["mae_P"] < min(r10["mae_B1"], r10["mae_B2"], r10["mae_B3"]) and r10["lo"] > 0 and r10["rel"] >= 0.02)
    res.update(claim1=bool(claim1), forecast=c1, forecast_groups=grp, coef_P=coef)

    # ---- claim 2: execution ----
    fc = {(r.sym, r.date, r.time): (r.f_B3, r.f_P) for r in pt.itertuples()}
    upd = sorted(R.TIMES.items(), key=lambda kv: kv[1])
    arms = {"A": [], "B": [], "C": []}
    test_dates = set(test.date)
    for s, d5 in frames.items():
        sess, minute, sig = d5.session.to_numpy(), d5.minute.to_numpy(), d5.sig_tl.to_numpy()
        atr, datr, close = d5.atr.to_numpy(float), d5.datr.to_numpy(float), d5.close.to_numpy(float)
        ent = [i for i in np.flatnonzero(sig) if sess[i] in test_dates and 25 <= minute[i] <= 325]

        def latest(i, which):
            tname = [n for n, m in upd if m <= minute[i]]
            if not tname:
                return None
            f = fc.get((s, sess[i], tname[-1]))
            return None if f is None else f[which]
        ent = [i for i in ent if latest(i, 0) is not None]
        arms["A"] += [dict(x, sym=s) for x in R.simulate_arm(d5, ent, lambda i: (atr[i], np.isfinite(atr[i])))]
        for arm, which in (("B", 0), ("C", 1)):
            arms[arm] += [dict(x, sym=s) for x in R.simulate_arm(
                d5, ent, lambda i, w=which: R.stops_for(max(latest(i, w), 0.0), datr[i], close[i]))]
    c2 = {}
    for arm, tr in arms.items():
        t_ = pd.DataFrame(tr)
        taken = t_[~t_.skipped]
        bm = boot_mean(taken, "net_bp")
        per_day = taken.groupby("date").net_bp.sum()
        c2[arm] = dict(trades=len(taken), skipped=int(t_.skipped.sum()), net_bp=bm["mean"], lo=bm["lo"], hi=bm["hi"],
                       gross_bp=float(taken.gross_bp.mean()), win=float((taken.net_bp > 0).mean()), net_per_day_bp=float(per_day.mean()))
    tb, tc = pd.DataFrame(arms["B"]), pd.DataFrame(arms["C"])
    d = boot_two_sets(tc[~tc.skipped], tb[~tb.skipped], "net_bp", cluster=("date",))
    c2["C_minus_B"] = dict(diff=d["diff"], lo=d["lo"], hi=d["hi"])
    claim2 = c2["C"]["net_bp"] >= 0 and d["lo"] > 0
    res.update(claim2=bool(claim2), execution=c2)
    res["verdict"] = "clears the bar" if claim1 and claim2 else "does not clear the bar"
    os.makedirs(OUT, exist_ok=True)
    json.dump(res, open(os.path.join(OUT, "results.json"), "w", encoding="utf-8"), indent=1, default=str)

    # live model: the same specification fitted on all rows (the test above used train only)
    R.save_models(R.fit_all(df), os.path.join(data.RUNTIME, "regime_model.json"))
    pictures(pt, res)
    print(json.dumps({k: res[k] for k in ("claim1", "claim2", "verdict")}, indent=1))
    print(pd.DataFrame(c1).round(4).to_string())
    print(pd.DataFrame({k: v for k, v in c2.items() if k != "C_minus_B"}).T.round(2).to_string(), c2["C_minus_B"])


def pictures(pt, res):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    BG, GR, TX, MUT = "#0b0e14", "#2a2e39", "#d1d4dc", "#8a8f9c"
    fig, axs = plt.subplots(1, 2, figsize=(15, 6), facecolor=BG)
    g = pt[pt.time == "10:00"]
    for ax, k, col in ((axs[0], "f_B3", "#8a8f9c"), (axs[0], "f_P", "#4fc3f7")):
        q = pd.qcut(g[k], 10, labels=False, duplicates="drop")
        xs = g.groupby(q)[k].median(); ys = g.groupby(q).y.median()
        ax.plot(xs, ys, "o-", color=col, label=k[2:])
    lim = [0, max(g.y.quantile(0.95), 1)]
    axs[0].plot(lim, lim, color=GR, ls="--"); axs[0].legend(facecolor=BG, labelcolor=TX)
    axs[0].set_xlabel("forecast (daily ATR)", color=MUT); axs[0].set_ylabel("realised median", color=MUT)
    axs[0].set_title("Calibration at 10:00, test dates (deciles)", color=TX, loc="left")
    c1 = pd.DataFrame(res["forecast"])
    x = np.arange(len(c1))
    for j, k in enumerate(("B1", "B2", "B3", "P")):
        axs[1].bar(x + (j - 1.5) * 0.2, c1[f"mae_{k}"], 0.2, label=k, color=["#5d6472", "#7d8592", "#9ea5b0", "#4fc3f7"][j])
    axs[1].set_xticks(x); axs[1].set_xticklabels(c1.time, color=MUT)
    axs[1].set_ylim(c1[[f"mae_{k}" for k in ("B1", "B2", "B3", "P")]].min().min() * 0.9, c1[[f"mae_{k}" for k in ("B1", "B2", "B3", "P")]].max().max() * 1.03)
    axs[1].legend(facecolor=BG, labelcolor=TX); axs[1].set_title("Test MAE of the rest-of-day range (lower is better)", color=TX, loc="left")
    for ax in axs:
        ax.set_facecolor(BG); ax.tick_params(colors=MUT); [s.set_color(GR) for s in ax.spines.values()]
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "forecast.png"), dpi=80, facecolor=BG); plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 5), facecolor=BG)
    ex = res["execution"]
    arms = ["A", "B", "C"]
    v = np.array([ex[a]["net_bp"] for a in arms]); lo = np.array([ex[a]["lo"] for a in arms]); hi = np.array([ex[a]["hi"] for a in arms])
    ax.bar(arms, v, color=["#5d6472", "#9ea5b0", "#4fc3f7"])
    ax.errorbar(arms, v, yerr=[v - lo, hi - v], fmt="none", ecolor=TX, capsize=4)
    ax.axhline(0, color=MUT, lw=0.8)
    ax.set_xticklabels(["A: ATR exits", "B: plain-forecast exits", "C: positioning-forecast exits"], color=MUT)
    ax.set_title("Net return per trade after costs, test dates (bp, 95% CI)", color=TX, loc="left")
    ax.set_facecolor(BG); ax.tick_params(colors=MUT); [s.set_color(GR) for s in ax.spines.values()]
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "execution.png"), dpi=80, facecolor=BG); plt.close(fig)


if __name__ == "__main__":
    main()
