"""Pictures for reports/volume_tool/RESULTS.md: ranking, calibration, hazard, lift curve, score painted on candles."""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
os.environ.setdefault("VZ_TAG", "sip")
from vzones import volume_tool as VT  # noqa: E402
import volume_tool_eval as E  # noqa: E402

OUT = E.OUT
R = json.load(open(os.path.join(OUT, "verdict.json")))
tools = list(R["tf"]["5"]["tools"].keys())
COL = {"useful": "#2e7d32", "descriptive only": "#f9a825", "noise": "#9e9e9e"}

# ---- ranking: IC on T1 (continuation) and T2 (range expansion), 5m test, with intervals
fig, axs = plt.subplots(1, 3, figsize=(17, 6.5), sharey=True)
order = sorted(tools, key=lambda k: R["tf"]["5"]["tools"][k]["T2"]["ic"])
y = np.arange(len(order))
for ax, tgt, title in zip(axs, ("T1_6", "T2", "T3"), ("T1: continuation (next 6 bars)", "T2: range expansion (next 6 bars)", "T3: +1 ATR before -1 ATR (24 bars)")):
    for i, k in enumerate(order):
        r = R["tf"]["5"]["tools"][k][tgt]; v = R["verdict"].get(k, {}).get("label", "noise")
        ax.plot([r["ic_lo"], r["ic_hi"]], [i, i], color=COL[v], lw=2); ax.plot(r["ic"], i, "o", color=COL[v])
        ax.text(r["ic_hi"] + 0.002, i, f"lift {r['lift']:.2f} [{r['lift_lo']:.2f},{r['lift_hi']:.2f}]", va="center", fontsize=7)
    ax.axvline(0, color="k", lw=.8); ax.set_yticks(y); ax.set_yticklabels(order, fontsize=8); ax.set_title(title, fontsize=10); ax.grid(alpha=.25); ax.set_xlabel("IC (Spearman), 5m test days")
fig.suptitle("Volume tools, 30 symbols, test days. Green = useful by the rule, yellow = descriptive only, grey = noise. Lift = hit rate above the train p90 / base rate", fontsize=10)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "ranking.png"), dpi=110)

# ---- calibration of the strength score and the lift curve over vol/SMA(20) and RVOL
fig, axs = plt.subplots(1, 2, figsize=(13, 4.5))
cal = R["tf"]["5"]["calibration"]["deciles"]
dec = sorted(int(k) for k in cal)
axs[0].bar(dec, [cal[str(k)][0] for k in dec], color="#1565c0")
axs[0].axhline(np.mean([cal[str(k)][0] for k in dec]), color="k", ls="--", lw=1)
axs[0].set_xlabel("strength score decile (edges from train)"); axs[0].set_ylabel("share of bars that continued (T1, 6 bars)")
axs[0].set_title(f"Strength score calibration, 5m test: slope {R['tf']['5']['calibration']['slope']:.4f} per decile", fontsize=10); axs[0].grid(alpha=.25)
for k, col in (("vol/SMA", "#9e9e9e"), ("RVOL", "#c62828")):
    c = R["tf"]["5"]["lift_curve"][k]
    axs[1].plot([x["above"] for x in c], [x["T2_expansion"] or np.nan for x in c], "-o", color=col, label=f"{k}: range expansion")
    axs[1].plot([x["above"] for x in c], [x["T1_cont"] or np.nan for x in c], "--s", color=col, alpha=.7, label=f"{k}: continuation")
axs[1].axhline(1, color="k", lw=.8); axs[1].axvline(0.8, color="#9e9e9e", ls=":", lw=1); axs[1].axvline(1.5, color="#9e9e9e", ls=":", lw=1)
axs[1].set_xlabel("volume above x times its baseline"); axs[1].set_ylabel("lift over the base rate"); axs[1].set_title("Lift curve (dotted: the indicator's 0.80 / 1.5 thresholds)", fontsize=10); axs[1].legend(fontsize=8); axs[1].grid(alpha=.25)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "calibration_lift.png"), dpi=110)

# ---- hazard curves per timeframe
fig, ax = plt.subplots(figsize=(8, 4.5))
for tf, col in (("5", "#1565c0"), ("15", "#2e7d32"), ("60", "#ef6c00"), ("390", "#6a1b9a")):
    p = R["tf"][tf]["persistence"]; h = [np.nan if x is None else x for x in p["hazard"]]
    ax.plot(range(1, 11), h, "-o", color=col, label=f"{tf} min: next-bar strong Brier {p['brier']:.3f} vs base {p['brier_base']:.3f}, autocorr lag1 {p['autocorr_mean']['1']:.2f}")
ax.set_xlabel("strong bars in a row so far (RVOL > 1.5)"); ax.set_ylabel("probability the run ends on the next bar"); ax.set_ylim(0, 1); ax.grid(alpha=.25); ax.legend(fontsize=8)
ax.set_title("Volume persistence: hazard of a strong-volume run (train), 30 symbols", fontsize=10)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "hazard.png"), dpi=110)

# ---- the score painted on real candles: SPY and a high-beta name, 5m, last test day with data
for sym in ("SPY", "COIN"):
    d = E.frames(sym)[5]
    T = VT.tools(d, 5)
    days = sorted(set(d.index.date)); pick = days[-8]
    idx = np.where(np.array([x == pick for x in d.index.date]))[0]
    o, h, l, c = (d[k].to_numpy()[idx] for k in ("open", "high", "low", "close"))
    rv = T["RVOL"][idx]; S = T["STRENGTH"][idx]
    sess, _ = VT.sessions_slots(d.index, 5); run = VT.runs(T["RVOL"] > VT.STRONG, sess)[idx]
    fig, axs = plt.subplots(2, 1, figsize=(14, 7), sharex=True, gridspec_kw={"height_ratios": [3, 1.2]})
    x = np.arange(len(idx))
    for j in range(len(idx)):
        col = "#26a69a" if c[j] >= o[j] else "#ef5350"
        axs[0].vlines(j, l[j], h[j], color=col, lw=.8); axs[0].vlines(j, min(o[j], c[j]), max(o[j], c[j]), color=col, lw=4)
    strong = rv > VT.STRONG
    axs[0].scatter(x[strong], h[strong] * 1.0005, marker="v", c=np.clip(S[strong], -1, 3), cmap="inferno", s=40, zorder=3)
    axs[0].set_title(f"{sym} 5m {pick}: triangles = strong volume (RVOL > 1.5), colour = strength score (dark low, bright high)", fontsize=10); axs[0].grid(alpha=.25)
    axs[1].bar(x, rv, color=np.where(strong, "#c62828", "#90a4ae")); axs[1].axhline(1.5, color="k", ls="--", lw=.8); axs[1].axhline(1.0, color="k", lw=.5)
    for j in np.where(run >= 3)[0]:
        axs[1].text(j, rv[j] + 0.1, str(run[j]), ha="center", fontsize=7)
    axs[1].set_ylabel("RVOL (vs same slot, 20 sessions)"); axs[1].grid(alpha=.25)
    ticks = [j for j, i in enumerate(idx) if d.index[i].minute == 0 and d.index[i].hour % 2 == 0] + [j for j, i in enumerate(idx) if d.index[i].strftime("%H:%M") == "09:30"]
    axs[1].set_xticks(sorted(ticks)); axs[1].set_xticklabels([d.index[idx[t]].strftime("%H:%M") for t in sorted(ticks)])
    fig.tight_layout(); fig.savefig(os.path.join(OUT, f"chart_{sym}.png"), dpi=110)
print("ok")
