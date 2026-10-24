"""Pictures for reports/breakout_volume/RESULTS.md: the range x RVOL grid of hold rates, hit rate by quintile
(volume vs size), and a real-chart example of a swing break."""
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
os.environ.setdefault("VZ_TAG", "sip")
from vzones import breakout_volume as BV  # noqa: E402
import breakout_volume_eval as BE  # noqa: E402
import volume_tool_eval as E  # noqa: E402

OUT = BE.OUT
R = json.load(open(os.path.join(OUT, "verdict.json")))

# ---- grids: range tercile x RVOL tercile, B1 hold rate, swing highs and lows, 5m and 15m
cells = [(tf, typ) for tf in ("5", "15") for typ in ("swing_high_k2", "swing_low_k2") if "grid_range_x_rvol" in R["tf"].get(tf, {}).get(typ, {}).get("B1", {})]
fig, axs = plt.subplots(1, len(cells), figsize=(4.4 * len(cells), 4.2))
for ax, (tf, typ) in zip(np.atleast_1d(axs), cells):
    g = np.array([[np.nan if v is None else v for v in row] for row in R["tf"][tf][typ]["B1"]["grid_range_x_rvol"]], float)
    im = ax.imshow(g, cmap="viridis", vmin=0.1, vmax=0.5)
    for a in range(3):
        for b in range(3):
            if np.isfinite(g[a, b]):
                ax.text(b, a, f"{100 * g[a, b]:.0f}%", ha="center", va="center", color="white" if g[a, b] < 0.35 else "black", fontsize=11)
    ax.set_xticks(range(3)); ax.set_xticklabels(["low", "mid", "high"]); ax.set_yticks(range(3)); ax.set_yticklabels(["small", "mid", "big"])
    ax.set_xlabel("RVOL of the breaking bar (tercile)"); ax.set_ylabel("size of the breaking bar (range/ATR tercile)")
    name = "swing high (up-break)" if "high" in typ else "swing low (down-break)"
    ax.set_title(f"{tf} min, {name}: {R['tf'][tf][typ]['B1']['n_test']} breaks, hold {100 * R['tf'][tf][typ]['B1']['base']:.0f}%", fontsize=9)
fig.suptitle("Share of breaks that hold 12 bars (close stays beyond the level, ends >= 0.5 ATR past it). Read down a column: size. Read across a row: volume.", fontsize=9)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "grid.png"), dpi=110)

# ---- quintile curves: RVOL vs size (control) vs B, swing k2, 5m
fig, axs = plt.subplots(1, 2, figsize=(12, 4.2), sharey=True)
for ax, typ in zip(axs, ("swing_high_k2", "swing_low_k2")):
    m = R["tf"]["5"][typ]["B1"]["measures"]; base = R["tf"]["5"][typ]["B1"]["base"]
    for k, col, lab in (("rvol", "#c62828", "RVOL (volume)"), ("control", "#607d8b", "range/ATR (bar size, control)"), ("B", "#ef6c00", "B (volume + size + body)")):
        q = [np.nan if x is None else x for x in m[k]["by_quintile"]]
        ax.plot(range(1, 6), q, "-o", color=col, label=f"{lab}: top-quintile lift {m[k]['lift']:.2f} [{m[k]['lift_lo']:.2f}, {m[k]['lift_hi']:.2f}]")
    ax.axhline(base, color="k", ls="--", lw=.8); ax.set_xticks(range(1, 6)); ax.set_xlabel("quintile of the measure (train edges)"); ax.grid(alpha=.25); ax.legend(fontsize=7, loc="upper left")
    ax.set_title(("swing high (up-break)" if "high" in typ else "swing low (down-break)") + f", 5m, {R['tf']['5'][typ]['B1']['n_test']} breaks", fontsize=9)
axs[0].set_ylabel("hold rate (12 bars)")
fig.tight_layout(); fig.savefig(os.path.join(OUT, "quintiles.png"), dpi=110)

# ---- example on SPY 5m: the last test-day swing break with a strong bar
d = E.frames("SPY")[5]
F, ev = BV.detect(d, 5, 2, BE.day_levels(d, "SPY"))
Y = BV.targets(F, ev, 24)
Y = Y[(Y["type"].str.startswith("swing")) & np.isfinite(Y["B1"]) & (Y["rvol"] > 1.5)]
e = Y.iloc[-1]; t = int(e["t"]); org = int(e["origin"])
a, b = max(0, org - 8), min(len(d), t + 14)
o, h, l, c = (F[k][a:b] for k in ("o", "h", "l", "c")); x = np.arange(a, b); rv = F["rvol"][a:b]
fig, (ax, ax2) = plt.subplots(2, 1, figsize=(12, 6.5), sharex=True, gridspec_kw={"height_ratios": [3, 1]})
for j in range(len(x)):
    col = "#26a69a" if c[j] >= o[j] else "#ef5350"
    ax.vlines(x[j], l[j], h[j], color=col, lw=.8); ax.vlines(x[j], min(o[j], c[j]), max(o[j], c[j]), color=col, lw=4)
ax.axhline(e["L"], color="#fb8c00", lw=1.5, ls="--", label=f"level {e['L']:.2f} ({'swing high' if e['dir'] > 0 else 'swing low'}, pivot at bar {org})")
ax.axvline(t, color="#c62828", lw=1.5, label=f"breaking bar: RVOL {e['rvol']:.2f}, range {e['range_atr']:.2f} ATR, hold = {'yes' if e['B1'] > 0 else 'no'}, false break = {'yes' if e['B3'] > 0 else 'no'}")
ax.set_title(f"SPY 5m {d.index[t].strftime('%Y-%m-%d %H:%M')}: a swing break on a strong-volume bar", fontsize=10); ax.legend(fontsize=8); ax.grid(alpha=.25)
ax2.bar(x, rv, color=np.where(rv > 1.5, "#c62828", "#90a4ae")); ax2.axhline(1.5, color="k", ls="--", lw=.8); ax2.set_ylabel("RVOL"); ax2.grid(alpha=.25)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "example_SPY.png"), dpi=110)
print("ok")
