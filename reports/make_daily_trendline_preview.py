"""Daily trendlines on the last 3 SPY 5m sessions: every line as it existed (anchor -> the bar it broke or the session
ended), current one dotted to the right. Top: the long held lines (previous default) for contrast."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from vzones.daily_trendlines import daily_lines
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from daily_trendline_compare import long_lines

ROOT = pathlib.Path(__file__).resolve().parent.parent
sym = sys.argv[1] if len(sys.argv) > 1 else "SPY"
d = pd.read_csv(ROOT / f"data/intraday/{sym}_5m_alpaca.csv")
day = pd.to_datetime(d["time"], utc=True).dt.tz_convert("America/New_York").dt.date
keep = day.isin(sorted(day.unique())[-3:])
d = d[keep].reset_index(drop=True); day = day[keep].reset_index(drop=True)
H, L, O, C = (d[k].to_numpy(float) for k in ("high", "low", "open", "close")); N = len(d)


def segments(lines):
    segs = []
    for side in ("red", "green"):
        cur = None; s0 = None
        for i, ln in enumerate(lines[side] + [None]):
            if ln != cur:
                if cur is not None:
                    segs.append((side, cur, s0, i - 1))
                cur, s0 = ln, i
    return segs


BG, GR, TX, MUT = "#0b0e14", "#2a2e39", "#d1d4dc", "#8a8f9c"
fig, axs = plt.subplots(2, 1, figsize=(16, 12), facecolor=BG)
for ax, (title, lines) in zip(axs, (("before: long lines held until broken", long_lines(d, 2, True)),
                                    ("after: DAILY lines - today's swing only, re-picked as the trend develops", daily_lines(d, 2)))):
    ax.set_facecolor(BG); ax.tick_params(colors=MUT); [s.set_color(GR) for s in ax.spines.values()]
    for i in range(N):
        col = "#26a69a" if C[i] >= O[i] else "#ef5350"
        ax.vlines(i, L[i], H[i], color=col, lw=.6)
        ax.add_patch(Rectangle((i - .3, min(O[i], C[i])), .6, max(abs(C[i] - O[i]), 1e-3), color=col))
    for i in range(1, N):
        if day[i] != day[i - 1]:
            ax.axvline(i - .5, color=GR, lw=1, ls="--")
    for side, (a, y0, s), b0, b1 in segments(lines):
        xs = np.array([a, b1 + 1]); ys = y0 + s * (xs - a)
        ax.plot(xs, ys, color="#ff1744" if side == "red" else "#00e676", lw=1.6, alpha=.9)
    ax.set_xlim(-1, N + 3); ax.set_ylim(L.min() * .998, H.max() * 1.002); ax.set_xticks([])
    ax.set_title(f"{sym} 5m · last 3 sessions · {title}", color=TX, fontsize=13)
fig.tight_layout(); out = ROOT / f"reports/styles/daily_trendlines_{sym}.png"
fig.savefig(out, dpi=85, facecolor=BG); print(out)
