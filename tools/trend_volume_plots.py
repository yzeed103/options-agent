"""Pictures for reports/trend_volume/RESULTS.md: hit rate by quintile (measure vs control), an example on real candles."""
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
from vzones import trend_volume as TV  # noqa: E402
import volume_tool_eval as E  # noqa: E402

OUT = os.path.join(ROOT, "reports", "trend_volume")
R = json.load(open(os.path.join(OUT, "verdict.json")))

# ---- hit rate by quintile, 5m / 15m / 1h, pattern score vs v_res vs control
TFS = [tf for tf in ("5", "15", "60") if "R1" in R["tf"].get(tf, {})]
fig, axs = plt.subplots(1, len(TFS), figsize=(5.2 * len(TFS), 4.3), sharey=True)
for ax, tf in zip(np.atleast_1d(axs), TFS):
    m = R["tf"][tf]["R1"]["measures"]; base = R["tf"][tf]["R1"]["base"]
    for k, col, lab in (("P", "#c62828", "pattern score (strong-weak-strong)"), ("v_res", "#ef6c00", "resumption-bar RVOL"), ("control", "#607d8b", "price only (shallow, short pullback)")):
        q = [np.nan if x is None else x for x in m[k]["by_quintile"]]
        ax.plot(range(1, 6), q, "-o", color=col, label=f"{lab}: top-quintile lift {m[k]['lift']:.2f} [{m[k]['lift_lo']:.2f}, {m[k]['lift_hi']:.2f}]")
    ax.axhline(base, color="k", ls="--", lw=.8); ax.set_xticks(range(1, 6)); ax.set_xlabel("quintile of the measure (train edges)"); ax.grid(alpha=.25)
    ax.set_title(f"{tf} min: {R['tf'][tf]['R1']['n_events_test']} resumptions (test), base hit {base:.2f}", fontsize=10); ax.legend(fontsize=7, loc="lower right")
axs[0].set_ylabel("share reaching +1 ATR before -1 ATR (24 bars)")
fig.suptitle("Trend resumptions on the Hull average: does the volume pattern beat the price pattern? (30 symbols, test days)", fontsize=10)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "quintiles.png"), dpi=110)

# ---- example: a leg / pullback / resumption on real SPY candles (5m), the last test day with an event
d = E.frames("SPY")[5]
F, ev, clx = TV.detect(d, 5)
Y = TV.targets(F, ev)
Y = Y[np.isfinite(Y["R1"]) & np.isfinite(Y["P"])]
e = Y.iloc[-1]
t, ls, ps = int(e["t"]), int(e["leg_start"]), int(e["pull_start"])
a, b = max(0, ls - 10), min(len(d), t + 26)
fig, (ax, ax2) = plt.subplots(2, 1, figsize=(13, 7), sharex=True, gridspec_kw={"height_ratios": [3, 1.2]})
o, h, l, c, M, rv = (F[k][a:b] for k in ("o", "h", "l", "c", "M", "rvol"))
x = np.arange(a, b)
for j in range(len(x)):
    col = "#26a69a" if c[j] >= o[j] else "#ef5350"
    ax.vlines(x[j], l[j], h[j], color=col, lw=.8); ax.vlines(x[j], min(o[j], c[j]), max(o[j], c[j]), color=col, lw=4)
ax.plot(x, M, color="#fb6500", lw=1.5, label="HMA(67)")
ax.axvspan(ls - 0.5, ps - 0.5, color="#2e7d32", alpha=.12, label=f"leg ({int(e['leg_len'])} bars), mean RVOL {e['v_leg']:.2f}")
ax.axvspan(ps - 0.5, t - 0.5, color="#f9a825", alpha=.18, label=f"pullback ({int(e['pull_len'])} bars), mean RVOL {e['v_pull']:.2f}")
ax.axvline(t, color="#c62828", lw=1.5, label=f"resumption bar, RVOL {e['v_res']:.2f}, pattern score {e['P']:.2f}")
ax.axhline(F["c"][t] + F["A"][t], color="#2e7d32", ls=":", lw=1); ax.axhline(F["c"][t] - F["A"][t], color="#c62828", ls=":", lw=1)
ax.set_title(f"SPY 5m {d.index[t].strftime('%Y-%m-%d %H:%M')}: outcome R1 = {int(e['R1']):+d} (+1 = reached +1 ATR first, dotted lines)", fontsize=10)
ax.legend(fontsize=8, loc="best"); ax.grid(alpha=.25)
ax2.bar(x, rv, color=np.where(rv > 1.5, "#c62828", "#90a4ae")); ax2.axhline(1.5, color="k", ls="--", lw=.8); ax2.axhline(0.8, color="k", ls=":", lw=.8)
ax2.set_ylabel("RVOL"); ax2.grid(alpha=.25)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "example_SPY.png"), dpi=110)
print("ok", d.index[t])
