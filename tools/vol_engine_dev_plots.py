"""Figures for reports/vol_engine_dev: band_heat.png, season.png, remaining.png, ladder.png, exits.png, heat.png, squeeze.png, regime_map.png"""
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
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tools"))
os.environ.setdefault("VZ_TAG", "sip")
from vzones import regimes as RG  # noqa: E402

OUT = os.path.join(ROOT, "reports", "vol_engine_dev")
V = json.load(open(os.path.join(OUT, "verdict.json")))
BG, TXT, GRID = "#131722", "#d1d4dc", "#2a2e39"
plt.rcParams.update({"figure.facecolor": BG, "axes.facecolor": BG, "axes.edgecolor": GRID, "axes.labelcolor": TXT, "xtick.color": TXT, "ytick.color": TXT, "text.color": TXT, "grid.color": GRID, "font.size": 9})


def err(ax, x, d, color, label=None, w=0.6):
    ax.bar(x, d["mean"], width=w, color=color, alpha=.85, label=label); ax.plot([x, x], [d["lo"], d["hi"]], color="white", lw=1.2)


# 1 band coverage by heat
h = V["H1.1"]; fig, ax = plt.subplots(figsize=(9, 4.5)); names = list(h["by_heat"].keys()); x = np.arange(len(names))
for i, nm in enumerate(names):
    c = h["by_heat"][nm]
    if "not_enough_data" in c:
        continue
    err(ax, i - 0.2, c["inner_emp"], "#42a5f5", "empirical quantiles" if i == 0 else None, 0.38); err(ax, i + 0.2, c["inner_gauss"], "#ef5350", "Gaussian ±1σ" if i == 0 else None, 0.38)
ax.axhline(0.683, color="#ffd600", ls="--", lw=1); ax.axhspan(0.663, 0.703, color="#ffd600", alpha=.08); ax.set_xticks(x); ax.set_xticklabels(names); ax.set_ylim(0.5, 0.85); ax.legend(loc="upper left")
ax.set_title(f"H1.1 inner-band coverage by heat bin (test). Overall: empirical {h['test']['empirical']['inner']['mean']:.3f}, Gaussian {h['test']['gaussian']['inner']['mean']:.3f}. Verdict: {'PASS' if h['pass'] else 'FAIL (cold under-covers, extreme over-covers)'}", fontsize=9)
ax.grid(alpha=.3); fig.tight_layout(); fig.savefig(os.path.join(OUT, "band_heat.png"), dpi=110)

# 2 seasonality: pooled profile and QLIKE gains
P = json.load(open(os.path.join(OUT, "h13_pooled.json"))); R = json.load(open(os.path.join(OUT, "h13_rolling.json")))
fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.2), gridspec_kw={"width_ratios": [2, 1]})
prof = np.array(P["profile"]); a1.bar(np.arange(78), prof, color="#42a5f5"); a1.set_yscale("log"); a1.set_xlabel("5m slot of the session (0 = 09:30)"); a1.set_ylabel("variance factor (log)"); a1.set_title("H1.3 pooled slot variance profile from train (30 symbols): the open carries 13x the average bar variance, lunch 0.4x", fontsize=9); a1.grid(alpha=.3)
for i, (nm, d) in enumerate((("per-symbol train", V["H1.3"]["qlike_seasonal_minus_plain"]), ("pooled static (ships)", P["qlike_pooled_seasonal_minus_plain"]), ("rolling 20 sessions", R["qlike_rolling_seasonal_minus_plain"]))):
    err(a2, i, d, "#26a69a")
a2.set_xticks(range(3)); a2.set_xticklabels(["per-symbol", "pooled", "rolling"]); a2.axhline(0, color="white", lw=.8); a2.set_title("QLIKE seasonal − plain (test; negative = better)", fontsize=9); a2.grid(alpha=.3)
a2.text(0.02, 0.05, f"coverage ±1σ: per-symbol {V['H1.3']['coverage_1sigma_seasonal']['mean']:.3f}, pooled {P['coverage_1sigma']['mean']:.3f}, rolling {R['coverage_1sigma']['mean']:.3f} (rolling fails the ±3 rule)", transform=a2.transAxes, fontsize=8)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "season.png"), dpi=110)

# 3 remaining range decay and gap
h32 = V["H3"]["H3.2_remaining"]; fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.2))
g = np.array(h32["g_by_slot"]); slots = np.arange(0, 78, 6)[:len(g)]; a1.plot(slots, g, "o-", color="#42a5f5", label="empirical 68.3th pct of |remaining move| / σ (train)"); a1.plot(slots, np.sqrt(77 - slots), "--", color="#ef5350", label="√(remaining bars)")
a1.set_xlabel("slot"); a1.set_title(f"H3.2 remaining move to the close: √(remaining) over-covers ({h32['cov_sqrt']:.3f}) vs empirical {h32['cov_empirical']:.3f}. PASS", fontsize=9); a1.legend(); a1.grid(alpha=.3)
h33 = V["H3"]["H3.3_gap"]; err(a2, 0, h33["qlike_gap_minus_plain_test"], "#26a69a"); a2.axhline(0, color="white", lw=.8); a2.set_xticks([0]); a2.set_xticklabels([f"λ = {h33['lambda_best_train']}"]); a2.set_title(f"H3.3 first-bar variance s2 + λ·gap²: QLIKE over the next 12 bars (test). PASS", fontsize=9); a2.grid(alpha=.3)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "remaining_gap.png"), dpi=110)

# 4 ladder: odds by S0 quintile and the stop variants
H4 = V["H4"]; fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.5))
cells = H4["H4.3_odds"]["cells"]; names = [k for k in cells if "p_1x" in cells[k]]
for i, k in enumerate(names):
    err(a1, i, cells[k]["p_1x"], "#26a69a" if cells[k]["pass_1x"] else "#5d606b")
a1.axhline(H4["H4.3_odds"]["pooled_1x"]["mean"], color="#ffd600", ls="--", label=f"pooled {H4['H4.3_odds']['pooled_1x']['mean']:.3f}"); a1.set_xticks(range(len(names))); a1.set_xticklabels(names, rotation=45, ha="right", fontsize=7); a1.legend(); a1.grid(alpha=.3)
a1.set_title("H4.3 P(target 1× before stop 0.75×, 24 bars) by trend side × S0 quintile (green = interval excludes pooled)", fontsize=8.5)
items = [("trailing − fixed (H4.5)", H4["H4.5_trailing"]["exp_trail_minus_fixed"]), ("24 bars − rest of day (H4.4)", H4["H4.4_timestop"]["exp_24_minus_rest"]), ("structure − fixed (H4.2)", H4["H4.2_struct"]["exp_struct_minus_base"])]
for i, (nm, d) in enumerate(items):
    err(a2, i, d, "#26a69a" if d["lo"] > 0 else "#ef5350")
a2.axhline(0, color="white", lw=.8); a2.set_xticks(range(3)); a2.set_xticklabels([x[0] for x in items], fontsize=8); a2.set_title(f"stop variants: expectancy difference per trade (test, 5 bp costs). Base rule itself: {H4['base_expectancy_test']['mean'] * 100:.3f}% per trade", fontsize=8.5); a2.grid(alpha=.3)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "ladder.png"), dpi=110)

# 5 exits: range lift by heat, direction nothing
H2 = V["H2"]; fig, ax = plt.subplots(figsize=(9, 4.2)); names = [k for k in H2["H2.1_cells"] if "range_R24" in H2["H2.1_cells"][k]]
for i, k in enumerate(names):
    err(ax, i - 0.2, H2["H2.1_cells"][k]["range_R24"], "#42a5f5", "range R24 − random" if i == 0 else None, 0.38); err(ax, i + 0.2, H2["H2.1_cells"][k]["signed_r12"], "#ef5350", "signed 12-bar return − random" if i == 0 else None, 0.38)
ax.axhline(0, color="white", lw=.8); ax.set_xticks(range(len(names))); ax.set_xticklabels([k.split("|")[0] for k in names]); ax.legend(); ax.grid(alpha=.3)
ax.set_title(f"H2.1 after a band exit (test, {H2['n_exits_test']} exits): range expands with heat, direction is nothing. Clustering ic {H2['H2.2_clustering']['ic']:.3f} (negative: many recent exits → smaller next range)", fontsize=8.5)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "exits.png"), dpi=110)

# 6 heat normalization
H6 = V["H6"]; fig, ax = plt.subplots(figsize=(8, 4)); ics = H6["H6.1_normalization"]["ics"]
for i, (k, d) in enumerate(ics.items()):
    ax.bar(i, d["ic"], color="#26a69a" if d["lo"] > 0 else "#ef5350"); ax.plot([i, i], [d["lo"], d["hi"]], color="white")
ax.bar(3, H6["H6.2_acceleration"]["ic"], color="#26a69a"); ax.plot([3, 3], [H6["H6.2_acceleration"]["lo"], H6["H6.2_acceleration"]["hi"]], color="white")
ax.axhline(0, color="white", lw=.8); ax.set_xticks(range(4)); ax.set_xticklabels(["rank over 500 bars", "same-slot rank (20 sessions)", "VIX-conditioned rank", "acceleration Δ12"]); ax.set_ylabel("ic_pooled with next-24-bar range"); ax.grid(alpha=.3)
ax.set_title("H6.1/H6.2 heat normalization: the same-slot rank predicts the next range (ic 0.15); the 500-bar rank is slightly NEGATIVE. Acceleration adds (ic 0.08)", fontsize=8.5)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "heat.png"), dpi=110)

# 7 squeeze
H5 = V["H5"]; fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.2))
defs = [("ATR14/ATR100", "H5.1_atr"), ("Bollinger width", "H5.1_bb"), ("Keltner-in-BB", "H5.1_kin"), ("realized var ratio", "H5.1_rvr")]
for i, (nm, k) in enumerate(defs):
    err(a1, i, H5[k]["lift"], "#ab47bc")
a1.axhline(0, color="white", lw=.8); a1.set_xticks(range(4)); a1.set_xticklabels([d[0] for d in defs], fontsize=8); a1.set_title("H5.1 expansion within 12 bars minus random (test): every definition says calm persists", fontsize=8.5); a1.grid(alpha=.3)
rates = H5["H5.2_duration"]["rates"]; names = list(rates.keys())
for i, k in enumerate(names):
    err(a2, i, rates[k], "#ab47bc")
a2.axhline(H5["H5.1_atr"]["expansion_random"], color="#ffd600", ls="--", label=f"random {H5['H5.1_atr']['expansion_random']:.3f}")
ex = H5["H5.3_exit"]; a2.text(0.02, 0.9, f"lunch {H5['H5.5_lunch']['lunch']['mean']:.3f} vs other {H5['H5.5_lunch']['other']['mean']:.3f}\nlow RVOL {H5['H5.6_low_rvol']['low']['mean']:.3f} vs normal {H5['H5.6_low_rvol']['normal']['mean']:.3f}\nafter exit: {ex['expansion12_minus_random']['mean']:+.3f} vs random; P(up) {ex['p_up_12']['mean']:.3f}\nfade rule: {H5['H5.4_fade']['expectancy']['mean'] * 100:+.3f}% per trade (fail)", transform=a2.transAxes, fontsize=8, va="top")
a2.set_xticks(range(4)); a2.set_xticklabels(names); a2.legend(loc="lower right"); a2.set_title("H5.2 expansion rate by bars inside the squeeze (rises slowly, stays below random)", fontsize=8.5); a2.grid(alpha=.3)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "squeeze.png"), dpi=110)

# 8 regime map heatmap
mp = os.path.join(OUT, "regime_map.json")
if os.path.exists(mp):
    M = json.load(open(mp)); tools = ["T1_fan", "T2_exits", "T3_fuel", "T4_ladder", "T5_squeeze", "T6_heat"]; rows = []
    for dim, cells in M.items():
        for name, cell in cells.items():
            rows.append((f"{dim}:{name}", [cell.get(t) for t in tools]))
    def code(v):
        if isinstance(v, dict):
            val = v.get("value", ""); return 2 if val.startswith("value") else 1
        return 0 if (v is None or "not enough" in str(v) or "no entries" in str(v)) else 1
    Z = np.array([[code(v) for v in r[1]] for r in rows]); fig, ax = plt.subplots(figsize=(8, 0.32 * len(rows) + 1.5))
    ax.imshow(Z, cmap=matplotlib.colors.ListedColormap(["#2a2e39", "#5d3a3a", "#1f6f4a"]), aspect="auto", vmin=0, vmax=2)
    ax.set_yticks(range(len(rows))); ax.set_yticklabels([r[0] for r in rows], fontsize=7); ax.set_xticks(range(len(tools))); ax.set_xticklabels(tools, fontsize=8)
    for i, r in enumerate(rows):
        for j, v in enumerate(r[1]):
            if isinstance(v, dict):
                key = [k for k in ("cov_emp", "range_lift", "reversal_lift", "expectancy", "expansion_lift", "ic") if k in v]
                if key:
                    x = v[key[0]]; ax.text(j, i, f"{(x['mean'] if isinstance(x, dict) else x):+.3f}" if key[0] != "cov_emp" else f"{x:.2f}", ha="center", va="center", fontsize=6.5, color="white")
    ax.set_title("regime map: green = value (interval excludes the control), red = no value, grey = not enough data", fontsize=9)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "regime_map.png"), dpi=110)
print("ok")
