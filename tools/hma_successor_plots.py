"""Pictures for reports/hma_successor/RESULTS.md: heat map (step 1), side-by-side on SPY 5m, reversal close-up."""
from __future__ import annotations

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
from vzones import conviction_ma as CM  # noqa: E402
from vzones import hma_successor as HS  # noqa: E402
import hma_successor_eval as E  # noqa: E402
import streak_verdict as SV  # noqa: E402

OUT = E.OUT
sel = json.load(open(os.path.join(OUT, "select.json")))
ver = json.load(open(os.path.join(OUT, "verdict.json")))

# ---- heat map: shape x target lag, overshoot reduction vs HMA at the same lag (planted, seen seeds)
names = [n for n in ("DHMA", "CHMA", "HOLT", "BLEND") if n in sel["heat"]]
fig, axs = plt.subplots(1, len(names), figsize=(4.2 * len(names), 3.6))
for ax, n in zip(np.atleast_1d(axs), names):
    heat = sel["heat"][n]
    shapes = [str(s) for s in E.HS.SHAPES[n]]
    lags = ["5.0", "10.0", "15.0", "20.0"]
    Z = np.array([[heat.get(f"{s}|{l}") if heat.get(f"{s}|{l}") is not None else np.nan for l in lags] for s in shapes], float)
    im = ax.imshow(Z, vmin=0, vmax=1, cmap="viridis", aspect="auto")
    ax.set_xticks(range(len(lags))); ax.set_xticklabels([l[:-2] for l in lags]); ax.set_yticks(range(len(shapes))); ax.set_yticklabels(shapes)
    ax.set_xlabel("target lag (bars)"); ax.set_ylabel({"DHMA": "g (damping)", "CHMA": "k (candles)", "HOLT": "phi", "BLEND": "p"}[n]); ax.set_title(f"{n}: overshoot cut vs HMA")
    for i in range(len(shapes)):
        for j in range(len(lags)):
            if np.isfinite(Z[i, j]):
                ax.text(j, i, f"{Z[i, j]:.2f}", ha="center", va="center", color="white" if Z[i, j] < 0.6 else "black", fontsize=8)
fig.suptitle("Planted V reversals, seen seeds: share of HMA's overshoot removed (1.0 = all of it). A plateau, not a spike.")
fig.tight_layout(); fig.savefig(os.path.join(OUT, "heatmap.png"), dpi=110)

# ---- side-by-side and close-up on SPY 5m (test data), lengths from the 5m verdict
t5 = ver["tf"]["5m"]
df = SV.frames("SPY")["5m"]
o, h, l, c = SV.arrays(df); ho, hh, hl, hc = CM.heikin_ashi(o, h, l, c)
d = dict(o=o, h=h, l=l, c=c, hc=hc, hh=hh, hl=hl, atr=HS.ha_atr(o, h, l, c))
lines = {f"HMA({t5['REF']['len']['n']})": CM.hma(hc, t5["REF"]["len"]["n"])}
if "DHMA" in t5:
    lines[f"Damped HMA g0.6 ({t5['DHMA']['len']['n']})"] = HS.dhma(hc, t5["DHMA"]["len"]["n"], 0.6)
if "HOLT" in t5:
    lines[f"Holt phi0.8 ({t5['HOLT']['len']['n']})"] = HS.holt(hc, t5["HOLT"]["len"]["n"], 0.8)
if "MED3" in t5:
    L = t5["MED3"]["len"]; lines["Median of 3"] = HS.med3(hc, L["HMA"], L["SS"], L["ALMA"])
if "BLEND" in t5:
    L = t5["BLEND"]["len"]; lines["Blend p3"] = HS.blend(hc, L["HMA"], L["SS"], 3.0)
days = sorted(set(df.index.date)); pick = days[-12:-10]
idx = np.where(np.isin(df.index.date, pick))[0]; x = np.arange(len(idx))
fig, axs = plt.subplots(1, len(lines), figsize=(4.6 * len(lines), 4.4), sharey=True)
for ax, (name, M) in zip(np.atleast_1d(axs), lines.items()):
    for j, i in enumerate(idx):
        col = "#26a69a" if hc[i] >= ho[i] else "#ef5350"
        ax.vlines(j, hl[i], hh[i], color=col, lw=.6, alpha=.5); ax.vlines(j, min(ho[i], hc[i]), max(ho[i], hc[i]), color=col, lw=2.2, alpha=.5)
    m = M[idx]; up = np.r_[False, np.diff(m) > 0]
    ax.plot(x, m, color="#111", lw=1, alpha=.35); ax.scatter(x, m, c=np.where(up, "#1565c0", "#e65100"), s=5, zorder=3)
    key = name.split("(")[0].strip()
    k = {"HMA": "REF", "Damped HMA g0.6": "DHMA", "Holt phi0.8": "HOLT", "Median of 3": "MED3", "Blend p3": "BLEND"}[key]
    sub = "" if k == "REF" else f"  overshoot {100 * t5[k]['overshoot']['better_share']:+.0f}%  flips {100 * t5[k]['flips']['better_share']:+.0f}%  noise {100 * t5[k]['noise']['better_share']:+.0f}%"
    ax.set_title(name + sub, fontsize=9, color="#2e7d32" if k == "REF" else "black"); ax.grid(alpha=.25)
    ticks = [j for j, i in enumerate(idx) if df.index[i].minute == 30 and df.index[i].hour in (10, 12, 14)]
    ax.set_xticks(ticks); ax.set_xticklabels([df.index[idx[t]].strftime("%m-%d %H:%M") for t in ticks], fontsize=7)
fig.suptitle(f"SPY 5m Heikin Ashi, {pick[0]} and {pick[1]} (test data), every line at the same ~10-bar lag in trends. Numbers = vs HMA over 30 symbols, + is better.", fontsize=10)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "side_by_side.png"), dpi=100)

# close-up: the first labelled reversal of the first picked day
revs = [(t, old) for t, old in HS.reversals(c, d["atr"]) if df.index[t].date() == pick[0]]
if revs:
    t, old = revs[0]
    a, b = max(0, t - 45), min(len(c), t + 45)
    fig, ax = plt.subplots(figsize=(10, 5))
    for i in range(a, b):
        col = "#26a69a" if hc[i] >= ho[i] else "#ef5350"
        ax.vlines(i, hl[i], hh[i], color=col, lw=.8, alpha=.6); ax.vlines(i, min(ho[i], hc[i]), max(ho[i], hc[i]), color=col, lw=3, alpha=.6)
    cols = ["#2e7d32", "#c62828", "#6a1b9a", "#ef6c00", "#1565c0"]
    for (name, M), col in zip(lines.items(), cols):
        ax.plot(range(a, b), M[a:b], color=col, lw=2 if name.startswith(("HMA", "Damped")) else 1.2, label=name)
    tp = HS.turning_price(hh, hl, t, old)
    ax.axhline(tp, color="gray", ls="--", lw=1); ax.axvline(t, color="gray", ls=":", lw=1)
    ax.text(t + 1, tp, f"turning price {tp:.2f}", va="bottom" if old > 0 else "top", color="gray", fontsize=8)
    ax.set_title(f"Reversal close-up, SPY 5m HA, {df.index[t].strftime('%Y-%m-%d %H:%M')}: the overshoot is how far a line keeps going past the turning price", fontsize=10)
    ax.legend(fontsize=8, loc="best"); ax.grid(alpha=.25)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "reversal_closeup.png"), dpi=110)
print("ok", pick, revs[:1])
