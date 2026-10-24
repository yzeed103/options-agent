"""Pictures for reports/trend_volume_model/RESULTS.md: break grid (energy x mass), survival by strength quintile,
reliability diagrams, and a real-chart example with state, levels (mass), a break and a false break."""
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
from vzones import trend_volume_model as TM  # noqa: E402
import breakout_volume_eval as BE  # noqa: E402
import volume_tool_eval as E  # noqa: E402

OUT = os.path.join(ROOT, "reports", "trend_volume_model")
R = json.load(open(os.path.join(OUT, "verdict.json")))
t5 = R["tf"]["5"]

# ---- 1) grid E tercile x mass tercile, hold rate
fig, ax = plt.subplots(figsize=(5.5, 4.4))
g = np.array([[np.nan if v is None else v for v in row] for row in t5["c_breaks"]["grid_E_x_mass_hold"]], float)
ax.imshow(g, cmap="viridis", vmin=0.1, vmax=0.5)
for a in range(3):
    for b in range(3):
        if np.isfinite(g[a, b]):
            ax.text(b, a, f"{100 * g[a, b]:.0f}%", ha="center", va="center", color="white" if g[a, b] < 0.35 else "black", fontsize=11)
ax.set_xticks(range(3)); ax.set_xticklabels(["light", "mid", "heavy"]); ax.set_yticks(range(3)); ax.set_yticklabels(["low", "mid", "high"])
ax.set_xlabel("mass of the level (volume traded at it, tercile)"); ax.set_ylabel("energy of the breaking bar (range x RVOL, tercile)")
ax.set_title(f"Hold rate of breaks, 5m test days ({t5['n_test']['breaks']} breaks)", fontsize=10)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "break_grid.png"), dpi=110)

# ---- 2) survival by strength quintile
fig, ax = plt.subplots(figsize=(7, 4.4))
sv = t5["a_trend"]["survival_by_S_quintile_at_3_6_12_24"]
for q, col in zip(range(5), ("#90a4ae", "#78909c", "#546e7a", "#ef6c00", "#c62828")):
    y = [np.nan if x is None else x for x in sv[str(q)]]
    ax.plot([3, 6, 12, 24], y, "-o", color=col, label=f"strength quintile {q + 1}" + (" (strongest)" if q == 4 else " (weakest)" if q == 0 else ""))
ax.set_xlabel("bars after the event"); ax.set_ylabel("share of trends still alive"); ax.grid(alpha=.25); ax.legend(fontsize=8)
ax.set_title("Trend survival by strength S (inertia + volume-weighted impulse), 5m test days", fontsize=10)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "survival.png"), dpi=110)

# ---- 3) reliability diagrams
cal = t5["e_calibration"]
fig, axs = plt.subplots(1, 2, figsize=(11, 4.4))
for ax, (k1, k2, title) in zip(axs, (("alive12_by_S", "alive12_by_S0", "P(trend alive after 12 bars)"), ("hold_by_E_mass", "hold_by_E0", "P(break holds)"))):
    for k, col, lab in ((k1, "#c62828", "with volume"), (k2, "#607d8b", "price only")):
        c = cal.get(k, {})
        if "reliability" in c:
            pts = c["reliability"]
            ax.plot([p[0] for p in pts], [p[1] for p in pts], "-o", color=col, label=f"{lab}: slope {c['slope']:.2f}, Brier {c['brier']:.3f} (base {c['brier_base']:.3f})")
    ax.plot([0, 1], [0, 1], "k--", lw=.8); ax.set_xlabel("predicted (train table)"); ax.set_ylabel("realized (test)"); ax.set_title(title, fontsize=10); ax.grid(alpha=.25); ax.legend(fontsize=7)
    lim = (0, 0.8) if "alive" in k1 else (0, 0.6); ax.set_xlim(lim); ax.set_ylim(lim)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "reliability.png"), dpi=110)

# ---- 4) real-chart example: SPY 5m, a test day with a held break and a false break
d = E.frames("SPY")[5]
res = TM.run(d, 5, BE.day_levels(d, "SPY")); Y = TM.targets(res); br = Y["breaks"]; bars = res["bars"]; f = res["frames"]
sw = br[br["type"].str.startswith("swing") & np.isfinite(br["hold"]) & np.isfinite(br["false"])]
days = sorted(set(d.index.date)); pick = None
for day in days[::-1][:30]:
    m = np.array([d.index[int(t)].date() == day for t in sw["t"]])
    if (sw["hold"][m] > 0).any() and (sw["false"][m] > 0).any():
        pick = day; break
idx = np.where(np.array([x == pick for x in d.index.date]))[0]; a, b = idx[0], idx[-1] + 1
o, h, l, c, M = (f[k][a:b] for k in ("o", "h", "l", "c", "M")); D = bars["D"].to_numpy()[a:b]; st = bars["state"].to_numpy()[a:b]; S = bars["S"].to_numpy()[a:b]
x = np.arange(a, b)
fig, (ax, ax2) = plt.subplots(2, 1, figsize=(14, 8), sharex=True, gridspec_kw={"height_ratios": [3.2, 1]})
for j in range(len(x)):
    col = "#26a69a" if c[j] >= o[j] else "#ef5350"
    ax.vlines(x[j], l[j], h[j], color=col, lw=.8); ax.vlines(x[j], min(o[j], c[j]), max(o[j], c[j]), color=col, lw=4)
ax.plot(x, M, color="#fb6500", lw=1.5, label="Hull (confirming)"); ax.plot(x, D, color="#fb6500", lw=1, ls="--", label="damped Hull (early)")
for j in range(len(x)):
    if st[j] != 0:
        ax.axvspan(x[j] - .5, x[j] + .5, color="#2e7d32" if st[j] > 0 else "#c62828", alpha=0.05 + 0.15 * (S[j] if np.isfinite(S[j]) else 0))
ev = sw[(sw["t"] >= a) & (sw["t"] < b)]
for _, e in ev.iterrows():
    t = int(e["t"]); col = "#2e7d32" if e["hold"] > 0 else "#c62828" if e["false"] > 0 else "#9e9e9e"
    ax.hlines(e["L"], max(a, int(e["origin"])), t, color="#ffd600", lw=1.2, ls=":")
    ax.annotate(f"{'held' if e['hold'] > 0 else 'false' if e['false'] > 0 else 'faded'}  E {e['E']:.1f}  mass {e['mass']:.1f}" + ("  absorption" if e["absorption"] else "") + ("  counter" if e["counter"] else ""),
                (t, e["L"]), xytext=(0, 18 if e["dir"] > 0 else -22), textcoords="offset points", fontsize=7, color=col, ha="center", arrowprops=dict(arrowstyle="-", color=col, lw=.8))
ax.set_title(f"SPY 5m {pick}: shaded = Hull trend state (darker = stronger S), dotted = the level each break crossed, label = outcome, energy, mass", fontsize=9)
ax.legend(fontsize=8, loc="best"); ax.grid(alpha=.25)
ax2.plot(x, S, color="#c62828", lw=1.2, label="strength S (volume)"); ax2.plot(x, bars["S0"].to_numpy()[a:b], color="#607d8b", lw=1, label="S0 (price only)"); ax2.plot(x, bars["I"].to_numpy()[a:b], color="#9e9e9e", lw=.8, ls=":", label="inertia I")
ax2.set_ylim(0, 1); ax2.grid(alpha=.25); ax2.legend(fontsize=8)
ticks = [j for j in x if d.index[j].minute == 0 and d.index[j].hour % 2 == 0]; ax2.set_xticks(ticks); ax2.set_xticklabels([d.index[t].strftime("%H:%M") for t in ticks])
fig.tight_layout(); fig.savefig(os.path.join(OUT, "example_SPY.png"), dpi=110)
print("ok", pick)
