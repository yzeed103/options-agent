"""What the options-level bands look like: AVGO 5m (yfinance, last 2 sessions) with the GEXRadar block levels of
2026-10-22 drawn the way the Pine code draws them (walls full band, FLIP / PIN / DFLIP half band, from today's open)."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import yfinance as yf
from vzones.gex_block import parse_block
ROOT = pathlib.Path(__file__).resolve().parent.parent

BLOCK = "DATE=2026-10-22\nAVGO: CW=340 PW=320 FLIP=342.83 PIN=340 DFLIP=346.28 MAXOI=350"
lv = parse_block(BLOCK, "AVGO")
d = yf.Ticker("AVGO").history(period="5d", interval="5m", prepost=False)
days = sorted({t.date() for t in d.index})[-2:]
d = d[[t.date() in days for t in d.index]]
dd = yf.Ticker("AVGO").history(period="1mo", interval="1d")
tr = (dd["High"] - dd["Low"]).combine((dd["High"] - dd["Close"].shift()).abs(), max).combine((dd["Low"] - dd["Close"].shift()).abs(), max)
datr = tr.ewm(alpha=1 / 14, adjust=False).mean().iloc[-1]
H, L, O, C = (d[k].to_numpy() for k in ("High", "Low", "Open", "Close")); N = len(d)
t0 = next(i for i, t in enumerate(d.index) if t.date() == days[-1])

BG, GR, TX, MUT = "#0b0e14", "#2a2e39", "#d1d4dc", "#8a8f9c"
COL = {"CW": "#00c853", "PW": "#ff1744", "FLIP": "#ffd600", "PIN": "#e0e0e0", "DFLIP": "#80d8ff", "MAXOI": "#1de9b6"}
STY = {"CW": "-", "PW": "-", "FLIP": "--", "PIN": ":", "DFLIP": ":", "MAXOI": "--"}
band = 0.10 * datr
fig, ax = plt.subplots(figsize=(16, 8), facecolor=BG)
ax.set_facecolor(BG); ax.tick_params(colors=MUT); [s.set_color(GR) for s in ax.spines.values()]
for i in range(N):
    col = "#26a69a" if C[i] >= O[i] else "#ef5350"
    ax.vlines(i, L[i], H[i], color=col, lw=.8)
    ax.add_patch(Rectangle((i - .3, min(O[i], C[i])), .6, max(abs(C[i] - O[i]), 1e-3), color=col))
right = N + 25
KEYS = ("CW", "PW", "FLIP", "PIN", "DFLIP", "MAXOI")
for i, k in enumerate(KEYS):
    x = lv[k]
    hb = (0.5 if k in ("CW", "PW") else 0.25) * band
    ax.add_patch(Rectangle((t0, x - hb), right - t0, 2 * hb, facecolor=COL[k], alpha=0.25,
                           edgecolor=COL[k], lw=1.2, ls=STY[k]))
    # same price -> one shared label (as in the Pine code)
    same = [j for j, k2 in enumerate(KEYS) if j != i and abs(lv[k2] - x) <= 0.25 * band]
    if any(j < i for j in same):
        continue
    name = " · ".join([k] + [KEYS[j] for j in same if j > i])
    ax.text(N + 3, x, f"{name} {x:g}", color=COL[k], va="center", fontsize=11, fontweight="bold")
ax.axvline(t0, color=GR, lw=1, ls="--")
ax.text(t0 + 1, max(H.max(), lv["DFLIP"], lv["MAXOI"]) + band, "today's open: bands start here", color=MUT, fontsize=10)
ax.set_xlim(-1, right); ax.set_xticks([])
ax.set_ylim(min(L.min(), lv["PW"]) - 2 * band, max(H.max(), lv["DFLIP"], lv["MAXOI"]) + 3 * band)
ax.set_title(f"AVGO 5m · options levels as bands (walls = 0.10 daily ATR = {band:.2f}$, FLIP / PIN / DFLIP = half) · "
             f"block {lv['DATE']} · Python mock-up of the Pine drawing", color=TX, fontsize=12)
fig.tight_layout(); out = ROOT / "reports/styles/gex_bands_preview.png"
fig.savefig(out, dpi=90, facecolor=BG); print(out, days, round(datr, 2))
