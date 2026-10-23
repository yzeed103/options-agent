"""Mock-up of the de-cluttering proposals on real SPY 5m candles (last 2 sessions, Alpaca) and the real 2026-10-22
GEXRadar block. Top: every layer on, roughly as the indicator draws today. Bottom: proposals 1-3
(a "clean" display mode, levels closer than 0.15 daily ATR merged into one line, only levels within 1 daily ATR).
Python mock-up, not a TradingView screenshot.

    python reports/make_declutter_preview.py
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from vzones.gex_block import parse_block

ROOT = pathlib.Path(__file__).resolve().parent.parent
SYM = "SPY"
BLOCK = (ROOT / "runtime/gex_block.txt").read_text(encoding="utf-8")
lv = parse_block(BLOCK, SYM)

d = pd.read_csv(ROOT / f"data/intraday/{SYM}_5m_alpaca.csv")
t = pd.to_datetime(d["time"], utc=True).dt.tz_convert("America/New_York")
d["day"] = t.dt.date
days = sorted(d["day"].unique())
daily = d.groupby("day").agg(h=("high", "max"), l=("low", "min"), c=("close", "last"))
tr = np.maximum(daily.h - daily.l, np.maximum((daily.h - daily.c.shift()).abs(), (daily.l - daily.c.shift()).abs()))
datr = tr.ewm(alpha=1 / 14, adjust=False).mean().iloc[-2]

hist = d[d["day"].isin(days[-12:-2])]          # 10 days before the shown window: the "whale" range
w = d[d["day"].isin(days[-2:])].reset_index(drop=True)
O, H, L, C, V = (w[k].to_numpy() for k in ("open", "high", "low", "close", "volume"))
N = len(w); last = C[-1]
t0 = int(np.argmax(w["day"].to_numpy() == days[-1]))


def profile(df, rows):
    lo, hi = df["low"].min(), df["high"].max(); edges = np.linspace(lo, hi, rows + 1); vol = np.zeros(rows)
    for h_, l_, v_ in zip(df["high"], df["low"], df["volume"]):
        a = np.searchsorted(edges, l_, "right") - 1; b = np.searchsorted(edges, h_, "right") - 1
        a, b = max(a, 0), min(b, rows - 1); vol[a:b + 1] += v_ / (b - a + 1)
    mid = (edges[:-1] + edges[1:]) / 2; poc = int(vol.argmax()); lo_i = hi_i = poc; s = vol[poc]
    while s < 0.7 * vol.sum():
        up = vol[hi_i + 1] if hi_i + 1 < rows else -1; dn = vol[lo_i - 1] if lo_i > 0 else -1
        if up >= dn: hi_i += 1; s += up
        else: lo_i -= 1; s += dn
    return edges, vol, mid[poc], edges[hi_i + 1], edges[lo_i]


s_edges, s_vol, s_poc, s_vah, s_val = profile(w.iloc[t0:], 40)
w_edges, w_vol, w_poc, w_vah, w_val = profile(hist, 200)
pk = [w_edges[i] for i in np.argsort(w_vol)[::-1][:60]]
peaks = []
for p in pk:                                    # 8 separated peaks, as the whale layer draws them
    if all(abs(p - q) > 0.08 * datr for q in peaks): peaks.append(p)
    if len(peaks) == 8: break


def trendlines():
    out = []
    ph = [i for i in range(2, N - 2) if H[i] == max(H[i - 2:i + 3])]
    pl = [i for i in range(2, N - 2) if L[i] == min(L[i - 2:i + 3])]
    for piv, arr, side in ((ph, H, "red"), (pl, L, "green")):
        for a, b in zip(piv[-6:], piv[-5:]):
            if (side == "red" and arr[b] < arr[a]) or (side == "green" and arr[b] > arr[a]):
                out.append((side, a, arr[a], b, arr[b]))
        out = out[-2:] if side == "green" else out
    last_r = [x for x in out if x[0] == "red"][-1:]; last_g = [x for x in out if x[0] == "green"][-1:]
    return last_r + last_g


BG, GR, TX, MUT = "#0b0e14", "#2a2e39", "#d1d4dc", "#8a8f9c"
GCOL = {"CW": "#00c853", "PW": "#ff1744", "FLIP": "#ffd600", "PIN": "#e0e0e0", "DFLIP": "#80d8ff",
        "MAXOI": "#1de9b6", "CWOI": "#69f0ae", "PWOI": "#ff8a80"}
RIGHT = N + 45


def candles(ax, colored):
    vma = pd.Series(V).rolling(20, min_periods=1).mean().to_numpy()
    for i in range(N):
        up = C[i] >= O[i]
        col = ("#26a69a" if up else "#ef5350")
        if colored and V[i] > 1.5 * vma[i]: col = "#00e5ff" if up else "#ff9100"
        ax.vlines(i, L[i], H[i], color=col, lw=.8, zorder=3)
        ax.add_patch(Rectangle((i - .3, min(O[i], C[i])), .6, max(abs(C[i] - O[i]), 1e-3), color=col, zorder=3))


def tlines(ax):
    for side, a, ya, b, yb in trendlines():
        s = (yb - ya) / (b - a); xs = np.array([a, N + 5])
        ax.plot(xs, ya + s * (xs - a), color="#ff1744" if side == "red" else "#00e676", lw=2, zorder=4)


def frame(ax, title, ylo, yhi):
    ax.set_facecolor(BG); ax.tick_params(colors=MUT, labelsize=9); [s.set_color(GR) for s in ax.spines.values()]
    ax.set_xlim(-1, RIGHT); ax.set_ylim(ylo, yhi); ax.set_xticks([]); ax.yaxis.tick_right()
    ax.axvline(t0 - .5, color=GR, lw=1, ls="--")
    ax.set_title(title, color=TX, fontsize=13, loc="left")


fig, (a1, a2) = plt.subplots(2, 1, figsize=(16, 15), facecolor=BG)

# ---------------- BEFORE: every layer ----------------
allp = [lv[k] for k in GCOL if lv.get(k)] + [w_vah, w_val, H.max(), L.min()] + peaks
frame(a1, f"BEFORE  ·  {SYM} 5m  ·  every layer on (heat map, profile, top-3 zones, POC/VAH/VAL, whale range + 8 peaks, "
          f"8 options levels, colored bars, legend, table)", min(allp) - 1, max(allp) + 1)
rows = len(s_edges) - 1
for i in range(t0, N):                            # heat map: session volume-at-price up to this bar
    _, vv, *_ = profile(w.iloc[t0:i + 1], 40)
    q = vv / vv.max()
    for r in range(len(q)):
        if q[r] > .25:
            e = np.linspace(w.iloc[t0:i + 1]["low"].min(), w.iloc[t0:i + 1]["high"].max(), 41)
            col = "#1565c0" if q[r] < .5 else ("#f9a825" if q[r] < .8 else "#d50000")
            a1.add_patch(Rectangle((i - .5, e[r]), 1, e[r + 1] - e[r], color=col, alpha=.35, lw=0, zorder=1))
for r in np.argsort(s_vol)[::-1][:3]:              # top-3 zones
    a1.add_patch(Rectangle((t0, s_edges[r]), RIGHT - t0, s_edges[r + 1] - s_edges[r], facecolor="#7c4dff", alpha=.18,
                           edgecolor="#7c4dff", lw=1, zorder=1))
for y, c, n in ((s_poc, "#ffeb3b", "POC"), (s_vah, "#29b6f6", "VAH"), (s_val, "#29b6f6", "VAL")):
    a1.hlines(y, t0, RIGHT, color=c, lw=1.2, zorder=2); a1.text(RIGHT - 1, y, n, color=c, fontsize=8, ha="right", va="bottom")
a1.add_patch(Rectangle((0, w_val), RIGHT, w_vah - w_val, facecolor="#90a4ae", alpha=.08, edgecolor="#b0bec5", lw=1, zorder=0))
for y, n, lw_ in ((w_poc, "whale POC", 3), (w_vah, "whale VAH", 2), (w_val, "whale VAL", 2)):
    a1.hlines(y, 0, RIGHT, color="#ff6d00", lw=lw_, zorder=2); a1.text(2, y, n, color="#ff6d00", fontsize=8, va="bottom")
for p in peaks:
    a1.hlines(p, 0, RIGHT, color="#ffab40", lw=.8, ls=":", zorder=2)
band = .10 * datr
for k, c in GCOL.items():
    if lv.get(k) is None: continue
    hb = (.5 if k in ("CW", "PW", "CWOI", "PWOI") else .25) * band
    a1.add_patch(Rectangle((t0, lv[k] - hb), RIGHT - t0, 2 * hb, facecolor=c, alpha=.25, edgecolor=c, lw=1, zorder=2))
    a1.text(N + 8, lv[k], f"{k} {lv[k]:g}", color=c, fontsize=9, fontweight="bold", va="center")
mx = s_vol.max()                                   # right-hand profile
for r in range(rows):
    a1.add_patch(Rectangle((RIGHT - 2 - 30 * s_vol[r] / mx, s_edges[r]), 30 * s_vol[r] / mx, s_edges[r + 1] - s_edges[r],
                           color="#26a69a" if r % 2 else "#ef5350", alpha=.35, lw=0, zorder=1))
candles(a1, True); tlines(a1)
a1.text(.01, .97, "legend: low / mid / high volume  ·  buy / sell  ·  zones", transform=a1.transAxes, color=TX,
        fontsize=9, va="top", bbox=dict(facecolor="#1e222d", edgecolor=GR))
tbl = "\n".join(["trend      up", "now        up", "ADX        23", "vol dir    1.12", "vs POC     above",
                 "yday VA    inside", "whale      ->VAH", "options    PIN 760"])
a1.text(.99, .03, tbl, transform=a1.transAxes, color=TX, fontsize=9, family="monospace", ha="right", va="bottom",
        bbox=dict(facecolor="#1e222d", edgecolor=GR))

# ---------------- AFTER: clean mode + merge + near price ----------------
levels = [(lv[k], k, GCOL[k], 3 if k in ("CW", "PW") else 2) for k in GCOL if lv.get(k) is not None]
levels += [(w_poc, "W.POC", "#ff6d00", 2), (w_vah, "W.VAH", "#ff6d00", 1), (w_val, "W.VAL", "#ff6d00", 1),
           (s_poc, "POC", "#ffeb3b", 1), (s_vah, "VAH", "#29b6f6", 1), (s_val, "VAL", "#29b6f6", 1)]
near = sorted([x for x in levels if abs(x[0] - last) <= datr], key=lambda x: x[0])
hidden = len(levels) - len(near)
merged = []
for x in near:
    if merged and x[0] - merged[-1][-1][0] <= .15 * datr: merged[-1].append(x)
    else: merged.append([x])
lo_ = min([L.min()] + [g[0][0] for g in merged]); hi_ = max([H.max()] + [g[-1][0] for g in merged])
frame(a2, f"AFTER  ·  display mode \"clean\"  ·  {len(near)} near levels merged into {len(merged)} lines  ·  "
          f"{hidden} levels farther than 1 daily ATR ({datr:.1f}$) hidden", lo_ - .6, hi_ + .6)
for g in merged:
    y = float(np.mean([x[0] for x in g])); top = max(g, key=lambda x: x[3])
    a2.hlines(y, t0, RIGHT - 18, color=top[2], lw=top[3], alpha=.9, zorder=2)
    a2.text(RIGHT - 17, y, " · ".join(x[1] for x in g) + f"  {y:.2f}", color=top[2], fontsize=10, fontweight="bold",
            va="center")
candles(a2, False); tlines(a2)
a2.text(.99, .97, "trend   up\nnow     up\nnext    PIN 760", transform=a2.transAxes, color=TX, fontsize=10,
        family="monospace", ha="right", va="top", bbox=dict(facecolor="#1e222d", edgecolor=GR))
a2.text(.01, .97, "display mode: [ full ]  [ clean ]  [ options only ]", transform=a2.transAxes, color="#80d8ff",
        fontsize=10, va="top", bbox=dict(facecolor="#1e222d", edgecolor="#80d8ff"))

fig.tight_layout(); out = ROOT / "reports/styles/declutter_preview.png"
fig.savefig(out, dpi=85, facecolor=BG); print(out, "datr", round(datr, 2), "near", len(near), "merged", len(merged),
                                              "hidden", hidden, [[x[1] for x in g] for g in merged])
