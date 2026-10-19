#!/usr/bin/env python3
"""Backtest the Volume Zones indicator on SPY (S&P 500) and QQQ (Nasdaq-100).

    python run_backtest.py                 # bundled Lean data, writes reports/
    python run_backtest.py --source yahoo  # live Yahoo Finance download

Splits each series 60/40 into train/test (parameters were chosen on SPY 1h train only).
"""
import argparse
from pathlib import Path
import pandas as pd
import vzones
from vzones.backtest import run, stats

HOURLY = vzones.VZParams(lookback=120, weak_ratio=0.8, break_ratio=1.5, adx_strong=25, step=4)
DAILY = vzones.VZParams(lookback=120, weak_ratio=0.8, break_ratio=1.3, adx_strong=20)
VARIANTS = {"hunt": dict(signals=("hunt",)),
            "hunt_long": dict(signals=("hunt",), long_only=True),
            "rejection": dict(signals=("rejection",)),
            "rejection_trend": dict(signals=("rejection",), with_trend=True),
            "rejection_trend_long": dict(signals=("rejection",), with_trend=True, long_only=True)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="lean", choices=["lean", "yahoo", "auto"])
    ap.add_argument("--out", default="reports")
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(exist_ok=True)
    sets = [("SPY", "1h", HOURLY, "2y"), ("SPY", "1d", DAILY, "max"), ("QQQ", "1d", DAILY, "max")]
    rows = []
    for sym, iv, P, period in sets:
        try:
            df = vzones.load_ohlcv(sym, a.source, period=period if iv == "1d" else "730d", interval=iv)
        except Exception as e:
            print(f"skip {sym} {iv}: {e}"); continue
        sp = int(len(df) * 0.6)
        for part, d in (("train", df.iloc[:sp]), ("test", df.iloc[sp:])):
            r = vzones.compute(d, P)
            bh = round((d.close.iat[-1] / d.close.iat[P.lookback] - 1) * 100, 1)
            for name, kw in VARIANTS.items():
                tr = run(d, computed=r, **kw)
                if not tr.empty:
                    tr.to_csv(out / f"trades_{sym}_{iv}_{part}_{name}.csv", index=False)
                rows.append(dict(symbol=sym, interval=iv, part=part, start=str(d.index[0].date()),
                                 end=str(d.index[-1].date()), variant=name, buy_hold_pct=bh, **stats(tr, len(d))))
    res = pd.DataFrame(rows)
    res.to_csv(out / "summary.csv", index=False)
    (out / "summary.md").write_text(res.to_markdown(index=False))
    print(res.to_string(index=False))


if __name__ == "__main__":
    main()
