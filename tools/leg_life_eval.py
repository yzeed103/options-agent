"""Heavy-volume legs end sooner? reports/trend_volume/PREREG_LEGS.md.

    python tools/leg_life_eval.py        # 5m and 15m, writes reports/trend_volume/legs.json and legs.png
"""
from __future__ import annotations

import json
import os
import sys
import time

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
os.environ.setdefault("VZ_TAG", "sip")
from vzones import conviction_ma as CM  # noqa: E402
from vzones import trend_volume as TV  # noqa: E402
from vzones import volume_tool as VT  # noqa: E402
import volume_tool_eval as E  # noqa: E402

OUT = os.path.join(ROOT, "reports", "trend_volume")
CAP = 48


def leg_events(d: pd.DataFrame, tf: int, sym: str, cut):
    o, h, l, c = (d[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    M = CM.hma(c, TV.HMA_LEN[tf]); A = VT.atr(h, l, c); rvol = VT.rvol_set(d, tf)[0]
    sess, _ = VT.sessions_slots(d.index, tf); st = TV.trend_state(c, M)
    hz = TV.HORIZON_TF[tf]
    rows = []; run = 0; dr = 0
    for i in range(1, len(c)):
        if sess[i] != sess[i - 1]:
            run = 0
            continue
        if st[i] != 0 and st[i] == dr:
            run += 1
        elif st[i] != 0:
            dr, run = st[i], 1
        else:
            run = 0
            continue
        if run != 5:
            continue
        v5 = rvol[i - 4:i + 1]
        if not np.all(np.isfinite(v5)):
            continue
        # life: bars until the close is beyond M against the trend by 0.3 ATR; censored at the session end
        j, life, censored = i, 0, True
        while j + 1 < len(c) and sess[j + 1] == sess[j] and life < CAP:
            j += 1
            if dr * (c[j] - M[j]) < -TV.BEYOND * A[j]:
                censored = False
                break
            life += 1
        remain = 0
        while i + remain + 1 < len(c) and sess[i + remain + 1] == sess[i]:
            remain += 1
        fp, _ = TV.first_passage(h, l, c, A, sess, i, dr, hz)
        rows.append(dict(sym=sym, t=i, dir=dr, date=str(sess[i]), train=sess[i] < cut, V5=float(v5.mean()),
                         speed=dr * (c[i] - c[i - 4]) / A[i], extension=dr * (c[i] - M[i]) / A[i], life=life, censored=censored,
                         alive12=float(life >= 12) if (remain >= 12 and (not censored or life >= 12)) else np.nan,
                         alive24=float(life >= 24) if (remain >= 24 and (not censored or life >= 24)) else np.nan,
                         fp=fp))
    return rows


def survival(df: pd.DataFrame, max_b=36):
    """alive share by bars after the event; a censored leg counts as alive up to its censor bar then leaves the set"""
    out = []
    for b in range(1, max_b + 1):
        at_risk = df[(df["life"] >= b) | (~df["censored"] & (df["life"] < b))]      # censored before b drop out
        out.append(float((at_risk["life"] >= b).mean()) if len(at_risk) >= 30 else np.nan)
    return out


def main():
    t0 = time.time()
    from vzones.assistant import data as D
    syms = sorted(f[:-7] for f in os.listdir(D.BARS) if f.endswith("_5m.csv"))
    F = {s: E.frames(s) for s in syms}
    days = sorted(set().union(*[set(F[s][390].index.date) for s in syms]))
    cut = days[int(0.6 * len(days))]
    res = {"split": {"train_end_before": str(cut)}, "tf": {}}
    fig, axs = plt.subplots(2, 2, figsize=(13, 8))
    for col, tf in enumerate((5, 15)):
        EV = pd.DataFrame([r for s in syms for r in leg_events(F[s][tf], tf, s, cut)])
        tr = EV["train"].to_numpy(bool); te = ~tr
        blk = (EV["sym"] + "|" + EV["date"]).to_numpy()
        qv = np.nanpercentile(EV["V5"][tr], [20, 40, 60, 80]); qs = np.nanpercentile(EV["speed"][tr], [20, 40, 60, 80]); ts = np.nanpercentile(EV["speed"][tr], [33.3, 66.7])
        EV["qV"] = np.searchsorted(qv, EV["V5"]); EV["qS"] = np.searchsorted(qs, EV["speed"]); EV["tS"] = np.searchsorted(ts, EV["speed"])
        out = {"n_train": int(tr.sum()), "n_test": int(te.sum()), "n_alive12_defined": int(np.isfinite(EV["alive12"][te]).sum())}
        T = EV[te]
        death = 1 - T["alive12"].to_numpy(float)
        out["alive12_by_V5_quintile"] = [round(float(T["alive12"][T["qV"] == k].mean()), 3) for k in range(5)]
        out["alive12_by_speed_quintile"] = [round(float(T["alive12"][T["qS"] == k].mean()), 3) for k in range(5)]
        out["median_life_by_V5_quintile"] = [float(T["life"][T["qV"] == k].median()) for k in range(5)]
        out["fp_by_V5_quintile"] = [round(float((T["fp"][T["qV"] == k] > 0).mean()), 3) for k in range(5)]
        out["death_lift"] = TV.paired_lift(T["V5"].to_numpy(float), T["speed"].to_numpy(float), death, blk[te], float(qv[3]), float(qs[3]))
        # top V5 quintile inside every speed tercile
        strata = {}
        for k in range(3):
            S = T[T["tS"] == k]; top = S[S["qV"] == 4]
            strata[k] = dict(n=len(S), alive12_all=round(float(S["alive12"].mean()), 3), alive12_topV5=round(float(top["alive12"].mean()), 3) if len(top) >= 30 else None)
        out["by_speed_tercile"] = strata
        out["inside_every_stratum"] = bool(all(v["alive12_topV5"] is not None and v["alive12_topV5"] < v["alive12_all"] for v in strata.values()))
        dl = out["death_lift"]
        out["confirmed_here"] = bool(dl.get("lift_lo", 0) > 1 and dl.get("diff_lo", -1) > 0 and out["inside_every_stratum"])
        res["tf"][tf] = out
        print(tf, {k: v for k, v in out.items() if k not in ("by_speed_tercile",)}, f"{time.time() - t0:.0f}s", flush=True)
        # pictures: survival curves top vs bottom V5 quintile; alive12 by V5 quintile within speed terciles
        ax = axs[0, col]
        for k, c_, lab in ((4, "#c62828", "heaviest volume (top quintile of V5)"), (0, "#1565c0", "lightest volume (bottom quintile)")):
            ax.plot(range(1, 37), survival(T[T["qV"] == k]), color=c_, lw=2, label=lab)
        ax.plot(range(1, 37), survival(T), color="k", lw=1, ls="--", label="all legs")
        ax.set_title(f"{tf} min: share of legs still alive, by bars after the 5th leg bar ({len(T)} legs, test days)", fontsize=9); ax.set_xlabel("bars after the event"); ax.set_ylabel("alive"); ax.grid(alpha=.25); ax.legend(fontsize=8)
        ax = axs[1, col]
        w = 0.25
        for k, c_ in ((0, "#90a4ae"), (1, "#607d8b"), (2, "#37474f")):
            S = T[T["tS"] == k]
            ax.bar(np.arange(5) + (k - 1) * w, [S["alive12"][S["qV"] == q].mean() for q in range(5)], w, color=c_, label=f"speed tercile {k + 1}")
        ax.set_xticks(range(5)); ax.set_xticklabels(["light", "2", "3", "4", "heavy"]); ax.set_xlabel("V5 quintile (volume of the first 5 leg bars)"); ax.set_ylabel("alive after 12 bars"); ax.grid(alpha=.25); ax.legend(fontsize=8)
        ax.set_title(f"{tf} min: alive-after-12-bars by volume quintile inside each speed tercile", fontsize=9)
    n_ok = sum(1 for v in res["tf"].values() if v["confirmed_here"])
    res["verdict"] = "confirmed" if n_ok == 2 else "partly" if n_ok == 1 or any(v["death_lift"].get("lift_lo", 0) > 1 for v in res["tf"].values()) else "no"
    fig.suptitle(f"Heavy-volume legs end sooner? verdict: {res['verdict']}", fontsize=11); fig.tight_layout(); fig.savefig(os.path.join(OUT, "legs.png"), dpi=110)
    json.dump(res, open(os.path.join(OUT, "legs.json"), "w"), indent=1)
    print(res["verdict"], f"{time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
