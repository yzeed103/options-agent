"""Do the newer panel readings carry information? 15m RTH bars, 7 symbols, real data. No stops / targets.
1. Heading target: nearest whale level ahead of price in the instant-trend direction. Hit rate before the instant
   trend flips (max 26 bars) and the reaction after a touch, vs placebo levels (same levels shifted by a random
   0.5..1.5 daily-ATR, same process).
2. Supertrend(10,3) flip and 3. trendline break (2-bar pivots): forward return in the new direction, 4 / 8 bars,
   in ATR, vs every bar with the same direction.
4. Call / put whale targets hit by 12:00 ET: does the side with more hits predict 12:00 -> close?
"""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd
from vzones.intraday.data import load_csv, rth
from vzones.ranges import levels_by_day, instant_trend, supertrend, trendline_breaks, rma, true_range
OUT = pathlib.Path(__file__).resolve().parent; D = OUT.parent / "data" / "intraday"
SYMS = ["SPY", "QQQ", "COST", "INTU", "JNJ", "UNH", "HOOD"]
rng = np.random.default_rng(0)
head, flips, brks, cp = [], [], [], []
for s in SYMS:
    d = rth(load_csv(D / f"{s}_15m.csv")); idx = d.index.tz_localize(None); d.index = idx
    h, l, c = d.high.to_numpy(), d.low.to_numpy(), d.close.to_numpy(); n = len(d)
    atr = rma(true_range(h, l, c), 14); date = np.array(idx.date)
    dayatr = pd.Series(d.resample("1D").agg(dict(high="max", low="min")).dropna().pipe(lambda x: x.high - x.low).rolling(14).mean().shift(1).to_numpy(),
                       index=d.resample("1D").agg(dict(high="max")).dropna().index.date)
    LV = levels_by_day(d)
    nd = instant_trend(d)
    # 1. heading target, real and placebo
    for kind in ("whale", "placebo"):
        lvd = {k: (np.array(v) if kind == "whale" else np.array(v) + rng.choice([-1, 1], len(v)) * rng.uniform(.5, 1.5, len(v)) * np.nan_to_num(dayatr.get(k, np.nan), nan=0)) for k, v in LV.items()}
        i = 0
        while i < n - 1:
            lv = lvd.get(date[i]); dr = nd[i]
            if lv is None or len(lv) == 0 or dr == 0 or not np.isfinite(atr[i]): i += 1; continue
            edge = h[i] if dr > 0 else l[i]; ahead = lv[(lv - edge) * dr > 0]
            if len(ahead) == 0: i += 1; continue
            L = ahead[np.argmin(np.abs(ahead - edge))]; dist = abs(L - c[i]) / atr[i]; hit = None
            for j in range(i + 1, min(n, i + 27)):
                if (dr > 0 and h[j] >= L) or (dr < 0 and l[j] <= L): hit = j; break
                if nd[j] == -dr: break
            react = dr * (c[min(n - 1, hit + 8)] - L) / atr[i] if hit is not None else np.nan
            head.append(dict(sym=s, kind=kind, dist=dist, hit=hit is not None, bars=(hit - i) if hit else np.nan, react8=react))
            i = (hit or j) + 1
    # 2. supertrend flips, 3. trendline breaks
    _, sd = supertrend(d); sdir = np.where(sd < 0, 1, -1)
    tb = trendline_breaks(d, k=2, hold=False)   # the study was run on the original lines
    for k in (4, 8):
        fwd = np.r_[(c[k:] - c[:-k]), np.full(k, np.nan)] / atr
        for i in range(1, n - k):
            if sd[i] != sd[i - 1]: flips.append(dict(sym=s, k=k, ret=sdir[i] * fwd[i]))
            if tb[i]: brks.append(dict(sym=s, k=k, ret=tb[i] * fwd[i]))
        base = np.nanmean(sdir[:-k] * fwd[:-k]); flips.append(dict(sym=s, k=k, ret=np.nan, base=base))
    # 4. call / put by noon
    for dt, g in d.groupby(date):
        lv = np.array(LV.get(dt, []))
        if len(lv) == 0: continue
        o = g.open.iat[0]; am = g[g.index.hour < 12]; pm = g[g.index.hour >= 12]
        if len(am) == 0 or len(pm) == 0: continue
        ch = ((lv > o) & (lv <= am.high.max())).sum(); ph = ((lv < o) & (lv >= am.low.min())).sum()
        if ch != ph: cp.append(dict(sym=s, side=np.sign(ch - ph), ret=np.sign(ch - ph) * (pm.close.iat[-1] - pm.open.iat[0]) / pm.open.iat[0] * 100))
H = pd.DataFrame(head); F = pd.DataFrame(flips); B = pd.DataFrame(brks); P = pd.DataFrame(cp)
txt = []
g = H.groupby("kind").agg(n=("hit", "size"), hit_rate=("hit", "mean"), dist_atr=("dist", "median"), bars_med=("bars", "median"), react8_mean=("react8", "mean"))
txt.append("1) heading target (whale levels vs placebo levels)\n" + g.round(3).to_string())
txt.append("   hit rate by distance bucket\n" + H.assign(b=pd.cut(H.dist, [0, .5, 1, 2, 4, 99])).groupby(["b", "kind"], observed=True).hit.mean().unstack().round(3).to_string())
fb = F.dropna(subset=["ret"]).groupby("k").ret.agg(["size", "mean", lambda x: (x > 0).mean()]).round(3); fb.columns = ["n", "mean_ATR", "win"]
txt.append("2) Supertrend flip, return in the new direction\n" + fb.to_string() + "\n   baseline (all bars, same direction) mean_ATR: " + F.dropna(subset=["base"]).groupby("k").base.mean().round(3).to_string())
bb = B.groupby("k").ret.agg(["size", "mean", lambda x: (x > 0).mean()]).round(3); bb.columns = ["n", "mean_ATR", "win"]
txt.append("3) trendline break, return in the break direction\n" + bb.to_string())
txt.append("4) side with more whale targets hit by 12:00 -> 12:00..close return in that direction (%)\n" + f"   days {len(P)}  mean {P.ret.mean():.3f}%  win {(P.ret > 0).mean():.3f}")
out = "\n\n".join(txt); print(out); (OUT / "readings_study.txt").write_text(out)
