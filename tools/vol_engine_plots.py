"""Pictures for reports/vol_engine/RESULTS.md: the expected-move band on real candles with the realized path, a squeeze
example, the two equity curves, the stop-out curve, the VIX quintile bars."""
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
from vzones import vol_engine as VE  # noqa: E402
from vzones import volume_tool as VT  # noqa: E402
import vol_engine_eval as E  # noqa: E402

OUT = E.OUT
R = json.load(open(os.path.join(OUT, "verdict.json")))

# ---- 1) band on SPY 5m: GARCH (or the best) k = 24 expected move, drawn every 24 bars with the realized path
d, sess, r = E.series_5m("SPY"); c = d["close"].to_numpy(); h = d["high"].to_numpy(); l = d["low"].to_numpy(); o = d["open"].to_numpy()
fits = R["5m"]["k24"]["fits"]; best = min(("EWMA", "GARCH", "HAR"), key=lambda m: R["5m"]["k24"]["qlike"][m])
F = E.apply_fits(r, fits, 24, (1, 12, 78))[best]
days = sorted(set(sess)); pick = days[-3]; idx = np.where(sess == pick)[0]; x = np.arange(len(idx))
fig, ax = plt.subplots(figsize=(13, 5.5))
for j, i in enumerate(idx):
    col = "#26a69a" if c[i] >= o[i] else "#ef5350"
    ax.vlines(j, l[i], h[i], color=col, lw=.8); ax.vlines(j, min(o[i], c[i]), max(o[i], c[i]), color=col, lw=4)
for j0 in range(0, len(idx) - 24, 24):
    i = idx[j0]; s1 = np.sqrt(F[i]) * c[i]
    ax.fill_between([j0, j0 + 24], [c[i] - s1] * 2, [c[i] + s1] * 2, color="#1565c0", alpha=.12)
    ax.fill_between([j0, j0 + 24], [c[i] - 2 * s1] * 2, [c[i] + 2 * s1] * 2, color="#1565c0", alpha=.05)
    ax.plot([j0, j0 + 24], [c[i], c[i]], color="#1565c0", lw=.8, ls=":")
cov = R["5m"]["k24"]["coverage"][best]
ax.set_title(f"SPY 5m {pick}: expected-move band for the next 24 bars from {best} (dark = +-1 sigma, measured coverage {100 * cov['1']:.0f}%; light = +-2 sigma, {100 * cov['2']:.0f}%)", fontsize=10)
ax.grid(alpha=.25); ticks = [j for j, i in enumerate(idx) if d.index[i].minute == 0 and d.index[i].hour % 2 == 0]; ax.set_xticks(ticks); ax.set_xticklabels([d.index[idx[t]].strftime("%H:%M") for t in ticks])
fig.tight_layout(); fig.savefig(os.path.join(OUT, "band_SPY.png"), dpi=110)

# ---- 2) squeeze example on SPY 5m: the last ATR-squeeze on a test day and the next 12 bars
A = VT.atr(h, l, c); thr = R["5m"]["squeeze"]["thresholds"]; ev, comp, wr = VE.squeeze_events(h, l, c, A, *thr)
ev = [t for t, nm in ev if nm == "atr" and t < len(c) - 30 and sess[t] >= days[-60]]
t = ev[-1]; a, b = max(0, t - 60), min(len(c), t + 30)
fig, (ax, ax2) = plt.subplots(2, 1, figsize=(13, 7), sharex=True, gridspec_kw={"height_ratios": [3, 1]})
for i in range(a, b):
    col = "#26a69a" if c[i] >= o[i] else "#ef5350"
    ax.vlines(i, l[i], h[i], color=col, lw=.8); ax.vlines(i, min(o[i], c[i]), max(o[i], c[i]), color=col, lw=4)
ax.axvline(t, color="#ef6c00", lw=1.5, label="squeeze detected (ATR14 / ATR100 below the train 10th percentile)"); ax.axvspan(t, t + 12, color="#ef6c00", alpha=.08, label="next 12 bars")
sq = R["5m"]["squeeze"]["atr"]
ax.set_title(f"SPY 5m {str(sess[t])}: a squeeze; measured: range of the next 12 bars above its usual size {100 * sq['expansion_real']:.0f}% of the time vs {100 * sq['expansion_random']:.0f}% at random, direction up {100 * sq['direction_up']:.0f}%", fontsize=9)
ax.legend(fontsize=8); ax.grid(alpha=.25)
ax2.plot(range(a, b), comp[a:b], color="#ef6c00"); ax2.axhline(thr[0], color="k", ls="--", lw=.8); ax2.set_ylabel("ATR14 / ATR100"); ax2.grid(alpha=.25)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "squeeze_SPY.png"), dpi=110)

# ---- 3) equity curves
eq = pd.read_csv(os.path.join(OUT, "equity.csv"), index_col=0, parse_dates=True)
fig, ax = plt.subplots(figsize=(10, 4.5))
for col, c_ in (("equal", "#607d8b"), ("vol_managed", "#c62828")):
    s = R["sizing"][col]; ax.plot(eq.index, eq[col], color=c_, label=f"{col}: Sharpe {s['sharpe']:.2f}, mean {100 * s['ann_mean']:.1f}%/y, max DD {100 * s['max_dd']:.0f}%, turnover {s['turnover_per_month']:.2f}/month")
ax.set_title(f"177-stock long-only portfolio, monthly rebalance, 2023-now, 5 bp costs; Sharpe difference {R['sizing']['sharpe_diff']['mean']:+.2f} [{R['sizing']['sharpe_diff']['lo']:+.2f}, {R['sizing']['sharpe_diff']['hi']:+.2f}]", fontsize=9)
ax.legend(fontsize=8); ax.grid(alpha=.25)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "equity.png"), dpi=110)

# ---- 4) stop-out curve and VIX quintiles
fig, axs = plt.subplots(1, 2, figsize=(12, 4.4))
for tf, col in (("5m", "#c62828"), ("D", "#1565c0")):
    st = R[tf]["stops"]; ds = sorted(float(k) for k in st["noise_stopout_by_d"])
    axs[0].plot(ds, [st["noise_stopout_by_d"][str(k) if str(k) in st["noise_stopout_by_d"] else f"{k:.1f}"] for k in ds], "-o", color=col, label=f"{tf}: stop at d x expected move ({st['forecast']}); fixed 1 ATR = {100 * st['fixed_1ATR_noise_stopout']:.0f}%")
axs[0].axhline(0.2, color="k", ls="--", lw=.8); axs[0].set_xlabel("stop distance d (multiples of the expected move)"); axs[0].set_ylabel("share of RIGHT trades stopped by noise first"); axs[0].grid(alpha=.25); axs[0].legend(fontsize=7); axs[0].set_title("Where does a stop survive noise?", fontsize=9)
f = R["fear"]["SPY"]["test"]["f60"]; v = R["fear"]["SPY"]["validation"]["f60"]
xq = np.arange(5); axs[1].bar(xq - 0.2, [100 * x for x in f["by_vix_quintile"]], 0.4, color="#c62828", label=f"test 2023-now (base {100 * f['base']:.1f}%)"); axs[1].bar(xq + 0.2, [100 * x for x in v["by_vix_quintile"]], 0.4, color="#90a4ae", label=f"validation 2020-22 (base {100 * v['base']:.1f}%)")
axs[1].set_xticks(xq); axs[1].set_xticklabels(["calm", "2", "3", "4", "fear"]); axs[1].set_ylabel("SPY next-60-day return, %"); axs[1].grid(alpha=.25, axis="y"); axs[1].legend(fontsize=7)
axs[1].set_title(f"VIX quintile (2-year percentile): top minus base {100 * f['top_minus_base']:+.1f} [{100 * f['lo']:+.1f}, {100 * f['hi']:+.1f}] on test", fontsize=9)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "stops_fear.png"), dpi=110)
print("ok")
