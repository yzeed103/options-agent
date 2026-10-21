"""Direction study: no stop, no target. For every signal measure what price does next, vs a baseline of ordinary
bars at the same time of day in the same direction. 15m bars, 7 symbols, 2025-04-01 .. 2026-10-21.

Per signal (direction d = +1 long / -1 short, entry = next bar open):
  ret_15m / ret_1h / ret_2h / ret_eod : d * (close at horizon - entry) / ATR       (same session only)
  hold_entry_min : minutes until the first close on the wrong side of the entry price (capped at session end)
  hold_ema_min   : minutes until the first close on the wrong side of EMA20
  mfe / mae      : best / worst move in the signal direction until the session close, in ATR
Baseline: every bar at the same minute-of-session, given the same direction, same measurements.
"""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd
from vzones.intraday.data import load_csv, rth
from vzones.intraday.features import add_features
from vzones.intraday.signals import SETUPS, apply_filters
import vzones
OUT = pathlib.Path(__file__).resolve().parent; D = OUT.parent / "data" / "intraday"
SYMS = ["SPY", "QQQ", "COST", "INTU", "JNJ", "UNH", "HOOD"]
BAR = 15


def measure(d: pd.DataFrame):
    """Return arrays of forward measurements for EVERY bar in both directions: dict[dir] -> DataFrame."""
    o, c, h, l, atr, ema = (d[k].to_numpy(float) for k in ("open", "close", "high", "low", "atr", "ema_f"))
    sess = d.session.to_numpy(); n = len(d)
    end = np.zeros(n, int)                                  # index of the last bar of each bar's session
    last = n - 1
    for i in range(n - 1, -1, -1):
        if i < n - 1 and sess[i] != sess[i + 1]: last = i
        end[i] = last
    out = {}
    for dr in (1, -1):
        rows = np.full((n, 8), np.nan)
        for i in range(n - 1):
            e = i + 1
            if e > end[i] or not np.isfinite(atr[i]): continue
            ent, a, j1 = o[e], atr[i], end[i]
            seg_c = c[e:j1 + 1]
            def fwd(k):
                j = e + k - 1
                return dr * (c[j] - ent) / a if j <= j1 else np.nan
            bad = np.flatnonzero(dr * (seg_c - ent) < 0)
            hold_e = (bad[0] if len(bad) else len(seg_c)) * BAR
            bad2 = np.flatnonzero(dr * (seg_c - ema[e:j1 + 1]) < 0)
            hold_m = (bad2[0] if len(bad2) else len(seg_c)) * BAR
            mfe = (np.max(h[e:j1 + 1]) - ent) / a if dr > 0 else (ent - np.min(l[e:j1 + 1])) / a
            mae = (ent - np.min(l[e:j1 + 1])) / a if dr > 0 else (np.max(h[e:j1 + 1]) - ent) / a
            rows[i] = [fwd(1), fwd(4), fwd(8), dr * (c[j1] - ent) / a, hold_e, hold_m, mfe, mae]
        out[dr] = pd.DataFrame(rows, index=d.index, columns=["ret_15m", "ret_1h", "ret_2h", "ret_eod", "hold_entry_min", "hold_ema_min", "mfe", "mae"])
    return out


def summarize(df: pd.DataFrame) -> dict:
    df = df.dropna(subset=["ret_15m"])
    return dict(n=len(df), up_1h=(df.ret_1h > 0).mean(), up_eod=(df.ret_eod > 0).mean(),
                ret_1h=df.ret_1h.mean(), ret_2h=df.ret_2h.mean(), ret_eod=df.ret_eod.mean(),
                hold_entry_med=df.hold_entry_min.median(), hold_ema_med=df.hold_ema_min.median(),
                mfe=df.mfe.mean(), mae=df.mae.mean())


VZ = vzones.VZParams(lookback=120, weak_ratio=0.8, break_ratio=1.5, adx_strong=25, step=4)
recs = []
for sym in SYMS:
    d = add_features(rth(load_csv(D / f"{sym}_15m.csv")))
    m = measure(d)
    mos = d.minute_of_session.to_numpy()
    vz = vzones.compute(d[["open", "high", "low", "close", "volume"]], VZ)
    sigs = {name: fn(d) for name, fn in SETUPS.items()}
    sigs.update({"pool_break (indicator)": vz.pool_break.to_numpy(), "hunt (indicator)": vz.hunt.to_numpy(),
                 "rejection (indicator)": vz.rejection.to_numpy()})
    half = d.session < sorted(d.session.unique())[len(d.session.unique()) // 2]
    for name, s in sigs.items():
        for filt in ("any", "with"):
            ss = apply_filters(d, s, trend=filt) if filt == "with" else s
            for dr in (1, -1):
                idx = np.flatnonzero(ss == dr)
                if len(idx) == 0: continue
                sig_df = m[dr].iloc[idx].copy()
                # baseline: all bars, same direction, at the same minutes-of-session as the signals (weighted)
                base_df = m[dr][np.isin(mos, mos[idx])]
                w = pd.Series(mos[idx]).value_counts(normalize=True)
                bs = m[dr].assign(mos=mos).dropna(subset=["ret_15m"]).groupby("mos").mean().reindex(w.index)
                base = (bs.mul(w, axis=0)).sum()
                for part, mask in (("all", np.ones(len(idx), bool)), ("1st half", half.to_numpy()[idx]), ("2nd half", ~half.to_numpy()[idx])):
                    sm = sig_df[mask]
                    if len(sm) == 0: continue
                    recs.append(dict(symbol=sym, setup=name, filter=filt, dir=dr, part=part, **{k: sm[k].to_numpy() for k in sm.columns},
                                     **{f"base_{k}": base[k] for k in ("ret_1h", "ret_2h", "ret_eod", "hold_entry_min", "hold_ema_min", "mfe", "mae")}))

# pool all symbols & both directions per setup/filter/part (trade-weighted), compare to baseline
rows = []
R = pd.DataFrame(recs)
for (setup, filt, part), g in R.groupby(["setup", "filter", "part"]):
    cat = {k: np.concatenate(g[k].to_list()) for k in ("ret_15m", "ret_1h", "ret_2h", "ret_eod", "hold_entry_min", "hold_ema_min", "mfe", "mae")}
    nn = np.array([len(x) for x in g.ret_1h]); w = nn / nn.sum()
    base = {k: float(np.dot(w, g[f"base_{k}"])) for k in ("ret_1h", "ret_2h", "ret_eod", "hold_entry_min", "hold_ema_min", "mfe", "mae")}
    ok = ~np.isnan(cat["ret_1h"])
    eod = cat["ret_eod"][~np.isnan(cat["ret_eod"])]
    se = np.nanstd(cat["ret_eod"]) / np.sqrt(max(len(eod), 1))
    rows.append(dict(setup=setup, filter=filt, part=part, signals=len(cat["ret_15m"]),
                     pct_right_1h=round(np.mean(cat["ret_1h"][ok] > 0) * 100, 1), pct_right_eod=round(np.mean(eod > 0) * 100, 1),
                     move_1h_atr=round(np.nanmean(cat["ret_1h"]), 3), base_1h=round(base["ret_1h"], 3),
                     move_eod_atr=round(np.nanmean(cat["ret_eod"]), 3), base_eod=round(base["ret_eod"], 3),
                     edge_eod=round(np.nanmean(cat["ret_eod"]) - base["ret_eod"], 3), t_stat=round((np.nanmean(cat["ret_eod"]) - base["ret_eod"]) / se, 2) if se > 0 else np.nan,
                     held_above_entry_min=round(np.nanmean(cat["hold_entry_min"]), 0), base_held_entry=round(base["hold_entry_min"], 0),
                     held_with_ema_min=round(np.nanmean(cat["hold_ema_min"]), 0), base_held_ema=round(base["hold_ema_min"], 0),
                     best_move_atr=round(np.nanmean(cat["mfe"]), 2), worst_move_atr=round(np.nanmean(cat["mae"]), 2)))
T = pd.DataFrame(rows); T.to_csv(OUT / "direction_study.csv", index=False)
pd.set_option("display.width", 260)
allp = T[T.part == "all"].sort_values("edge_eod", ascending=False)
print("ALL DATA (7 symbols, longs+shorts pooled). edge_eod = signal move to session close minus baseline, in ATR\n")
print(allp.drop(columns="part").to_string(index=False))
print("\nCONSISTENCY: edge_eod in 1st half vs 2nd half of the period")
cons = T[T.part != "all"].pivot_table(index=["setup", "filter"], columns="part", values=["edge_eod", "signals"]).round(3)
print(cons.to_string())
