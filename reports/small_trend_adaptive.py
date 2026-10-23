"""Small trendlines on every timeframe: fixed 15-bar window vs adaptive (15 -> 30 -> 60 bars when no line fits).
7 stocks; 5m (Alpaca), 15m, and 1h (resampled from 15m). Same measures as small_trend_grid.py."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd
from vzones.daily_trendlines import small_lines
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from small_trend_grid import measure

ROOT = pathlib.Path(__file__).resolve().parent.parent
SYMS = ["SPY", "QQQ", "COST", "INTU", "JNJ", "UNH", "HOOD"]


def frames(s):
    m5 = pd.read_csv(ROOT / f"data/intraday/{s}_5m_alpaca.csv")
    m15 = pd.read_csv(ROOT / f"data/intraday/{s}_15m.csv")
    t = pd.to_datetime(m15["time"], utc=True).dt.tz_convert("America/New_York")
    g = m15.assign(t=t).set_index("t").groupby(pd.Grouper(freq="60min", origin="start_day", offset="30min"))
    h1 = g.agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna().reset_index()
    h1["time"] = h1["t"].astype(str)
    return {"5m": m5, "15m": m15, "1h": h1}


if __name__ == "__main__":
    data = {s: frames(s) for s in SYMS}
    print(f"{'tf':4} {'setting':22} {'on screen':>10} {'distance ATR':>13} {'touches/100':>12} {'fakeouts%':>10}")
    for tf in ("5m", "15m", "1h"):
        for name, kw in (("fixed 15 (current)", dict(k=1, window=15, widen=1)),
                         ("adaptive 15-30-60", dict(k=1, window=15, widen=3)),
                         ("adaptive 10-20-40-80", dict(k=1, window=10, widen=4))):
            D, T, S, C, NB, B, F = [], 0, 0, 0, 0, 0, 0
            for s in SYMS:
                df = data[s][tf]
                d, t, sh, cv, nb, b, f = measure(df, small_lines(df, **kw), np.ones(len(df), bool))
                D += d; T += t; S += sh; C += cv; NB += nb; B += b; F += f
            print(f"{tf:4} {name:22} {100*C/NB:9.0f}% {np.median(D):13.2f} {100*T/S:12.1f} {100*F/max(B,1):10.1f}")
