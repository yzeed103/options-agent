"""Does "volume supporting the direction" improve the two kept signals? 15m, 7 symbols, no stops/targets.
Signals: trend alert (2 closes outside prior-day value with EMA trend) and whale bounce; also every bar in the
EMA-trend direction as a reference. Split each by:
  UD  : up-volume / down-volume over the last 50 completed bars, oriented to the signal (>1 = supports it)
  WAE : Waddah Attar t1 = d(MACD20/40)*150 in the signal direction above the BB(20,2) width and the dead zone
Measured: next-bar-open entry, return to +1h / +2h / session close in ATR (direction study engine)."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd
from vzones.intraday.data import load_csv, rth
from vzones.intraday.features import add_features
from vzones.intraday.signals import va_accept, apply_filters
from vzones.intraday.whale_features import add_whale_levels, whale_bounce
from direction_study import measure
OUT = pathlib.Path(__file__).resolve().parent; D = OUT.parent / "data" / "intraday"
SYMS = ["SPY", "QQQ", "COST", "INTU", "JNJ", "UNH", "HOOD"]
rows = []
for s in SYMS:
    d = add_whale_levels(add_features(rth(load_csv(D / f"{s}_15m.csv"))), specs=(("1D", 20, 6.0),))
    c, o, v = d.close, d.open, d.volume
    upv = (v * (c > o)).rolling(50).sum(); dnv = (v * (c < o)).rolling(50).sum(); ud = (upv / dnv.replace(0, np.nan)).to_numpy()
    macd = c.ewm(span=20, adjust=False).mean() - c.ewm(span=40, adjust=False).mean(); t1 = (macd.diff() * 150).to_numpy()
    e1 = (4 * c.rolling(20).std()).to_numpy()
    trr = pd.concat([d.high - d.low, (d.high - c.shift()).abs(), (d.low - c.shift()).abs()], axis=1).max(axis=1)
    dz = (trr.ewm(alpha=1 / 100, adjust=False).mean() * 3.7).to_numpy()
    m = measure(d); half = np.where(np.arange(len(d)) < len(d) // 2, "H1", "H2")
    trend = np.where(d.ema_f > d.ema_s, 1, -1)
    sigs = {"trend_alert": apply_filters(d, va_accept(d), trend="with"), "whale_bounce": whale_bounce(d), "all_bars_trend": trend}
    for name, sg in sigs.items():
        for i in np.flatnonzero(sg):
            dr = int(np.sign(sg[i])); r = m[dr].iloc[i]
            if not np.isfinite(r.ret_1h): continue
            udo = ud[i] if dr > 0 else 1 / ud[i] if ud[i] else np.nan
            wae = dr * t1[i] > e1[i] and e1[i] > dz[i]
            rows.append(dict(sym=s, sig=name, half=half[i], ud_sup=bool(udo > 1), wae=bool(wae), r1h=r.ret_1h, r2h=r.ret_2h, reod=r.ret_eod))
df = pd.DataFrame(rows); df.to_csv(OUT / "volume_support_study.csv", index=False)
def tab(g):
    return pd.Series(dict(n=len(g), win_1h=(g.r1h > 0).mean(), r1h=g.r1h.mean(), r2h=g.r2h.mean(), reod=g.reod.mean(), win_eod=(g.reod > 0).mean()))
out = []
for key in ("ud_sup", "wae"):
    t = df.groupby(["sig", key]).apply(tab).round(3); out.append(f"\n=== split by {key} ===\n{t}")
    t2 = df.groupby(["sig", key, "half"]).apply(tab)[["n", "r2h", "reod"]].round(3); out.append(f"\n--- by half ---\n{t2}")
txt = "\n".join(out); print(txt); (OUT / "volume_support_study.txt").write_text(txt)
