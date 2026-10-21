"""Whale zones test. 15m, SPY QQQ COST INTU JNJ UNH HOOD, 2025-04-01 .. 2026-10-21.

Whale bar  : relative volume vs the same time of day over the previous 20 sessions >= RV (3 by default; 2 and 5 too).
Whale zone : [low, high] of that bar.
Control    : zones from ordinary bars (relative volume 0.8-1.2), same procedure.

Claims tested (everything uses only data after the zone's bar has closed):
 1. Magnet  : share of zones revisited within 5 sessions after price first left the zone.
 2. S/R     : at the first revisit, does price HOLD (1 h later closes back on the approach side) or BREAK
              (1 h later closes beyond the far side)? Bounce size in ATR.
 3. Direction: move from next open to the session close in the whale bar's direction, minus ordinary bars at
              the same time of day (ATR units).
"""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd
from vzones.intraday.data import load_csv, rth
from vzones.intraday.features import add_features
OUT = pathlib.Path(__file__).resolve().parent; D = OUT.parent / "data" / "intraday"
SYMS = ["SPY", "QQQ", "COST", "INTU", "JNJ", "UNH", "HOOD"]
H_SESS, REACT = 5, 4            # look 5 sessions ahead; reaction measured 4 bars (1 hour) after the touch


def zone_stats(d, mask):
    o, h, l, c, atr = (d[k].to_numpy(float) for k in ("open", "high", "low", "close", "atr"))
    sess = d.session.to_numpy(); uniq = {s: i for i, s in enumerate(sorted(set(sess)))}; si = np.array([uniq[s] for s in sess])
    rows = []
    for t in np.flatnonzero(mask):
        if not np.isfinite(atr[t]) or t + 2 >= len(d): continue
        zl, zh = l[t], h[t]; a = atr[t]
        end = np.searchsorted(si, si[t] + H_SESS + 1)          # first bar after the horizon
        j = t + 1; left = False; side = 0; touch = None
        while j < min(end, len(d)):
            outside = l[j] > zh or h[j] < zl
            if not left:
                if outside: left = True
            else:
                if l[j] <= zh and h[j] >= zl:
                    side = 1 if c[j - 1] > zh else -1            # +1 approached from above (support test)
                    touch = j; break
            j += 1
        r = dict(left=left, touched=touch is not None, dir=1 if c[t] >= o[t] else -1, t=t)
        if touch is not None and touch + REACT < len(d) and si[touch + REACT] == si[touch]:
            k = touch + REACT
            if side == 1:
                r.update(hold=c[k] > zh, brk=c[k] < zl, bounce=(h[touch:k + 1].max() - zh) / a, pierce=(zl - l[touch:k + 1].min()) / a)
            else:
                r.update(hold=c[k] < zl, brk=c[k] > zh, bounce=(zl - l[touch:k + 1].min()) / a, pierce=(h[touch:k + 1].max() - zh) / a)
            r["zone_atr"] = (zh - zl) / a
        rows.append(r)
    return pd.DataFrame(rows)


def eod_move(d, idx, dirs):
    o, c, atr = d.open.to_numpy(), d.close.to_numpy(), d.atr.to_numpy(); sess = d.session.to_numpy()
    last = pd.Series(np.arange(len(d))).groupby(sess).transform("max").to_numpy()
    out = []
    for t, dr in zip(idx, dirs):
        if t + 1 > last[t] or not np.isfinite(atr[t]): out.append(np.nan); continue
        out.append(dr * (c[last[t]] - o[t + 1]) / atr[t])
    return np.array(out)


res, dirrows = [], []
for sym in SYMS:
    d = add_features(rth(load_csv(D / f"{sym}_15m.csv")))
    rv = d.rvol.to_numpy(); half = (d.session < sorted(d.session.unique())[len(d.session.unique()) // 2]).to_numpy()
    groups = {"ordinary (RVOL 0.8-1.2)": (rv >= 0.8) & (rv <= 1.2)}
    for k in (2, 3, 5):
        groups[f"whale RVOL>={k}"] = rv >= k
    for g, m in groups.items():
        z = zone_stats(d, m)
        z["symbol"], z["group"], z["half"] = sym, g, np.where(half[z.t], "1st", "2nd")
        res.append(z)
        if g.startswith("whale") or g.startswith("ordinary"):
            idx = np.flatnonzero(m); dirs = np.where(d.close.to_numpy()[idx] >= d.open.to_numpy()[idx], 1, -1)
            mv = eod_move(d, idx, dirs)
            # baseline: ordinary bars at the same minute-of-session, same direction
            mos = d.minute_of_session.to_numpy(); allidx = np.arange(len(d))
            base_up = pd.Series(eod_move(d, allidx, np.ones(len(d)))).groupby(mos).mean()
            base = np.array([base_up[mos[t]] * dr for t, dr in zip(idx, dirs)])
            dirrows.append(pd.DataFrame(dict(symbol=sym, group=g, move=mv, edge=mv - base, half=np.where(half[idx], "1st", "2nd"))))
Z = pd.concat(res, ignore_index=True); DR = pd.concat(dirrows, ignore_index=True)
Z.to_csv(OUT / "whale_zones_events.csv", index=False)

def summ(g):
    t = g[g.left]; tt = t[t.touched & t.hold.notna()]
    return pd.Series(dict(zones=len(g), revisited_5d=t.touched.mean() * 100, hold_1h=tt.hold.astype(float).mean() * 100 if len(tt) else np.nan,
                          break_1h=tt.brk.astype(float).mean() * 100 if len(tt) else np.nan, bounce_atr=tt.bounce.mean(), pierce_atr=tt.pierce.mean(),
                          zone_width_atr=tt.zone_atr.mean()))
pd.set_option("display.width", 220)
print("=== 1+2. Magnet and support/resistance (all symbols pooled)")
S = Z.groupby("group").apply(summ).round(2); print(S.to_string())
print("\n=== same, by half of the period")
print(Z.groupby(["group", "half"]).apply(summ)[["zones", "revisited_5d", "hold_1h", "break_1h"]].round(1).unstack().to_string())
print("\n=== same, by symbol (hold %)")
print(Z.groupby(["group", "symbol"]).apply(summ)["hold_1h"].round(1).unstack().to_string())
print("\n=== 3. Direction after the bar: move to session close in the bar's direction, minus same-time baseline (ATR)")
G = DR.groupby("group").agg(bars=("move", "size"), move=("move", "mean"), edge=("edge", "mean"), edge_sd=("edge", "std"))
G["t"] = G.edge / (G.edge_sd / np.sqrt(G.bars)); print(G.round(3).to_string())
print(DR.groupby(["group", "half"]).edge.mean().round(3).unstack().to_string())
S.to_csv(OUT / "whale_zones_summary.csv")

print("\n=== Width-matched control: ordinary zones re-weighted to the whale zones' width distribution")
E = Z[Z.left & Z.touched & Z.hold.notna()].copy()
E["hold"] = E.hold.astype(float); E["brk"] = E.brk.astype(float)
bins = [0, .6, .9, 1.2, 1.5, 2.0, 3.0, 99]; E["wb"] = pd.cut(E.zone_atr, bins)
ordn = E[E.group.str.startswith("ordinary")]
for g in [x for x in E.group.unique() if x.startswith("whale")]:
    wz = E[E.group == g]; w = wz.wb.value_counts(normalize=True)
    om = ordn.groupby("wb", observed=False)[["hold", "brk", "bounce"]].mean().reindex(w.index)
    ctrl = (om.mul(w, axis=0)).sum()
    n = len(wz); p = wz.hold.mean(); se = np.sqrt(ctrl.hold * (1 - ctrl.hold) / n)
    print(f"{g:14s} n={n:4d}  hold {p*100:5.1f}% vs width-matched ordinary {ctrl.hold*100:5.1f}%  (z={(p-ctrl.hold)/se:+.2f})   "
          f"break {wz.brk.mean()*100:5.1f}% vs {ctrl.brk*100:5.1f}%   bounce {wz.bounce.mean():.2f} vs {ctrl.bounce:.2f} ATR")
