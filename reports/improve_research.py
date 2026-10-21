import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd, vzones
from vzones.research2 import lvn_speed, naked_poc, htf_filter, confirm_next
from vzones.research import signals, backtest, summarize
from vzones.backtest import run, stats
pd.set_option("display.width", 220)
D = pathlib.Path(__file__).resolve().parent.parent / "data"
hourly = vzones.load_lean_csv(D / "spy_hourly_lean.csv.gz")
H = dict(lookback=120, weak_ratio=0.8, break_ratio=1.5, adx_strong=25, step=4)
r = vzones.compute(hourly, vzones.VZParams(**H)); sp = int(len(r) * .6)
yrs = lambda x: (x.index[-1] - x.index[0]).days / 365.25

print("=== 1. Speed: inside HVN vs LVN (SPY 1h, next 5 bars, |move| in ATR)")
for part, rr in (("train", r.iloc[:sp]), ("test", r.iloc[sp:])):
    print(part); print(lvn_speed(rr))
dl = vzones.compute(vzones.load_lean_csv(D / "spy_daily_lean.csv.gz"), vzones.VZParams(lookback=120))
print("SPY 1d all"); print(lvn_speed(dl))

print("\n=== 2. Naked POC magnet (block POC vs mirrored level, same distance)")
print("SPY 1h, 1-day blocks (7 bars), next 5 days:", naked_poc(hourly, 7, 35, r.atr.to_numpy()))
print("SPY 1h, 1-week blocks (35 bars), next 2 weeks:", naked_poc(hourly, 35, 70, r.atr.to_numpy()))
print("SPY 1d, 1-week blocks, next 4 weeks:", naked_poc(vzones.load_lean_csv(D / "spy_daily_lean.csv.gz"), 5, 20, dl.atr.to_numpy()))

print("\n=== 3. Time-of-day volume (RVOL by hour) vs plain SMA volume, SPY 1h")
rt = vzones.compute(hourly, vzones.VZParams(**H, vol_mode="tod"))
for name, rr0 in (("sma", r), ("time-of-day", rt)):
    for part, rr in (("train", rr0.iloc[:sp]), ("test", rr0.iloc[sp:])):
        for sig in ("hunt", "rejection"):
            st = stats(run(rr, signals=(sig,), computed=rr), len(rr))
            print(f"{name:12s} {part:5s} {sig:9s}", {k: st.get(k) for k in ("trades", "win_rate", "profit_factor", "avg_r", "total_ret_pct")})
        print(f"{name:12s} {part:5s} pool breaks/yr={ (rr.pool_break!=0).sum()/yrs(rr):.1f}  weak bars share={rr.weak_volume.mean():.2f}")

print("\n=== 4. Higher-timeframe (daily EMA50) filter, SPY 1h")
for part, rr in (("train", r.iloc[:sp]), ("test", r.iloc[sp:])):
    for trig, f, br in (("pool", "adx25", 1.5), ("range", "ema_only", 1.2)):
        s = signals(rr, trig, f, br=br, rng_n=5, rng_max_atr=None)
        base = summarize(backtest(rr, s), yrs(rr))
        s2 = s.copy(); s2["sig"] = htf_filter(rr, s.sig.to_numpy())
        filt = summarize(backtest(rr, s2), yrs(rr))
        print(f"{part:5s} {trig:5s} no filter:", {k: base.get(k) for k in ("trades", "per_year", "win", "pf", "avg_r")})
        print(f"{part:5s} {trig:5s} HTF filter:", {k: filt.get(k) for k in ("trades", "per_year", "win", "pf", "avg_r")})
    st0 = stats(run(rr, signals=("rejection",), computed=rr), len(rr))
    rr2 = rr.copy(); rr2["rejection"] = htf_filter(rr, rr.rejection.to_numpy())
    st1 = stats(run(rr2, signals=("rejection",), computed=rr2), len(rr))
    print(f"{part:5s} rejection no filter:", {k: st0.get(k) for k in ("trades", "win_rate", "profit_factor", "avg_r")})
    print(f"{part:5s} rejection HTF filter:", {k: st1.get(k) for k in ("trades", "win_rate", "profit_factor", "avg_r")})

print("\n=== 5. Rejection with next-bar confirmation")
for name, rr0 in (("SPY 1h", r), ("SPY 1d", dl)):
    s0 = int(len(rr0) * .6)
    for part, rr in (("train", rr0.iloc[:s0]), ("test", rr0.iloc[s0:])):
        a = stats(run(rr, signals=("rejection",), computed=rr), len(rr))
        cf = confirm_next(rr, "rejection")
        b = stats(run(cf, signals=("rejection",), computed=cf), len(rr))
        print(f"{name} {part:5s} raw      ", {k: a.get(k) for k in ("trades", "win_rate", "profit_factor", "avg_r")})
        print(f"{name} {part:5s} confirmed", {k: b.get(k) for k in ("trades", "win_rate", "profit_factor", "avg_r")})
