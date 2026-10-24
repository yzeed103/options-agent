"""Pictures for reports/structure_break/RESULTS.md: continuation vs random per timeframe and level class, the
significance-quintile curves, context and variants, and a real-chart example on daily."""
from __future__ import annotations

import json
import os
import sys

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
os.environ.setdefault("VZ_TAG", "sip")
from vzones import structure_break as SB  # noqa: E402
import structure_break_eval as E  # noqa: E402

OUT = E.OUT
R = json.load(open(os.path.join(OUT, "verdict.json")))
TFS = [tf for tf in ("1h", "4h", "D", "W") if tf in R["tf"]]
NAMES = {"1h": "1 hour", "4h": "4 hours", "D": "daily", "W": "weekly"}

# ---- 1) real vs pseudo continuation per timeframe x class
fig, axs = plt.subplots(1, len(TFS), figsize=(4.6 * len(TFS), 4.6), sharey=True)
for ax, tf in zip(np.atleast_1d(axs), TFS):
    t = R["tf"][tf]["test"]; cls = [c for c in E.CLASSES if "all" in t.get(c, {})]
    y = np.arange(len(cls))
    real = [t[c]["all"]["fp"] for c in cls]; ps = [t[c]["all"]["pseudo"] for c in cls]
    lo = [t[c]["all"]["fp"] - (t[c]["all"]["excess"] - t[c]["all"]["lo"]) for c in cls]; hi = [t[c]["all"]["fp"] + (t[c]["all"]["hi"] - t[c]["all"]["excess"]) for c in cls]
    ax.barh(y + 0.2, real, 0.4, color="#c62828", label="real breaks"); ax.barh(y - 0.2, ps, 0.4, color="#90a4ae", label="random entries (same symbol, direction, time)")
    ax.errorbar(real, y + 0.2, xerr=[np.array(real) - np.array(lo), np.array(hi) - np.array(real)], fmt="none", ecolor="k", lw=1)
    for i, c in enumerate(cls):
        ax.text(max(real[i], ps[i]) + 0.01, i, f"n {t[c]['all']['n']}", va="center", fontsize=7)
    ax.set_yticks(y); ax.set_yticklabels(cls); ax.axvline(0.5, color="k", lw=.6, ls=":"); ax.set_xlim(0.3, 0.75); ax.grid(alpha=.25, axis="x")
    ax.set_title(f"{NAMES[tf]}: share reaching +1 ATR before -1 ATR", fontsize=9); ax.set_xlabel("continuation rate (test)")
axs_ = np.atleast_1d(axs); axs_[0].legend(fontsize=7, loc="lower right")
fig.suptitle("Does a break continue beyond chance? Red = after a real break, grey = random bars nearby; bars = 95% interval of the excess", fontsize=10)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "real_vs_random.png"), dpi=110)

# ---- 2) significance quintiles (swing classes) and context
fig, axs = plt.subplots(1, 2, figsize=(12, 4.4))
for tf, col in zip(TFS, ("#90a4ae", "#607d8b", "#c62828", "#6a1b9a")):
    t = R["tf"][tf]["test"]
    for c, ls in (("swing10", "-"), ("swing20", "--")):
        q = t.get(c, {}).get("fp_by_sig_quintile")
        if q:
            axs[0].plot(range(1, 6), [np.nan if x is None else x for x in q], ls, marker="o", color=col, label=f"{NAMES[tf]} {c}")
axs[0].set_xlabel("significance quintile (age, touches, depth)"); axs[0].set_ylabel("continuation rate"); axs[0].axhline(0.5, color="k", lw=.6, ls=":"); axs[0].grid(alpha=.25); axs[0].legend(fontsize=7); axs[0].set_title("H2: does continuation rise with significance?", fontsize=9)
labels, vals, cols = [], [], []
for tf in TFS:
    t = R["tf"][tf]["test"]
    for c in ("swing10", "don55"):
        for ctx, cc in (("with_trend", "#2e7d32"), ("against", "#c62828")):
            v = t.get(c, {}).get(ctx, {})
            if "fp" in v:
                labels.append(f"{NAMES[tf]} {c} {ctx} (n {v['n']})"); vals.append(v["excess"]); cols.append(cc)
y = np.arange(len(labels)); axs[1].barh(y, vals, color=cols); axs[1].set_yticks(y); axs[1].set_yticklabels(labels, fontsize=7); axs[1].axvline(0, color="k", lw=.8); axs[1].grid(alpha=.25, axis="x")
axs[1].set_xlabel("excess continuation over random"); axs[1].set_title("H3: with the daily Hull trend (green) vs against it (red)", fontsize=9)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "significance_context.png"), dpi=110)

# ---- 3) daily example: the latest test-period swing20 break on SPY with the level, the break and the outcome
d = E.load_daily("SPY"); F, Ev = SB.levels_and_breaks(d, "D")
sw = Ev[(Ev["cls"] == "swing20")]
e = sw.iloc[-3]; t = int(e["t"])
a, b = max(0, t - 80), min(len(d), t + 25)
o, h, l, c = (F[k][a:b] for k in ("o", "h", "l", "c")); x = np.arange(a, b)
fig, ax = plt.subplots(figsize=(13, 5.5))
for j in range(len(x)):
    col = "#26a69a" if c[j] >= o[j] else "#ef5350"
    ax.vlines(x[j], l[j], h[j], color=col, lw=.8); ax.vlines(x[j], min(o[j], c[j]), max(o[j], c[j]), color=col, lw=4)
ax.axhline(e["L"], color="#fb8c00", ls="--", lw=1.4, label=f"swing20 {'high' if e['dir'] > 0 else 'low'} {e['L']:.2f}: age {int(e['age'])} days, touches {int(e['touches'])}, depth {e['depth']:.1f} ATR, score {e['sig']:.2f}")
ax.axvline(t, color="#c62828", lw=1.5, label="break bar")
tg = SB.targets_at(F, t, int(e["dir"]), float(e["L"]), 10)
ax.axhline(F["c"][t] + F["A"][t], color="#2e7d32", ls=":", lw=1); ax.axhline(F["c"][t] - F["A"][t], color="#c62828", ls=":", lw=1)
ax.set_title(f"SPY daily, break on {str(d.index[t])[:10]}: +1 ATR first? {'yes' if tg['fp'] > 0 else 'no'}; held 10 days? {'yes' if tg['hold'] > 0 else 'no'}; false break? {'yes' if tg['false'] > 0 else 'no'}", fontsize=10)
ax.legend(fontsize=8); ax.grid(alpha=.25)
ticks = list(range(a, b, 10)); ax.set_xticks(ticks); ax.set_xticklabels([str(d.index[i])[:10] for i in ticks], rotation=30, fontsize=7)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "example_SPY_daily.png"), dpi=110)
print("ok")
