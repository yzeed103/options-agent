"""Download 5-minute regular-hours bars from Alpaca into data/intraday/<SYM>_5m_alpaca.csv.

Keys are read from GEXRadar's config (C:/project/gex_radar/.env via its app.config) inside this process and are never
printed or written anywhere else. Free feed = IEX: prices are fine, volume is IEX-only (use relative volume only).

    python tools/fetch_alpaca_5m.py SPY QQQ COST INTU JNJ UNH HOOD --start 2025-04-01
"""
import argparse
import os
import sys
from datetime import datetime, timezone

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"C:\project\gex_radar")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("symbols", nargs="+")
    ap.add_argument("--start", default="2025-04-01")
    ap.add_argument("--end", default=None)
    a = ap.parse_args()
    from app import config                                    # GEXRadar's keys, read in-process only
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
    from alpaca.data.enums import DataFeed, Adjustment
    cl = StockHistoricalDataClient(config.ALPACA_API_KEY, config.ALPACA_SECRET_KEY)
    start = datetime.fromisoformat(a.start).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(a.end).replace(tzinfo=timezone.utc) if a.end else None
    for sym in a.symbols:
        res = cl.get_stock_bars(StockBarsRequest(symbol_or_symbols=sym, timeframe=TimeFrame(5, TimeFrameUnit.Minute),
                                                 start=start, end=end, feed=DataFeed.IEX, adjustment=Adjustment.SPLIT))
        df = res.df.reset_index()
        df = df[df["symbol"] == sym]
        t = pd.to_datetime(df["timestamp"], utc=True).dt.tz_convert("America/New_York")
        m = t.dt.hour * 60 + t.dt.minute
        keep = (m >= 9 * 60 + 30) & (m < 16 * 60) & (t.dt.weekday < 5)
        out = pd.DataFrame({"time": t[keep].dt.strftime("%Y-%m-%d %H:%M:%S%z").str.replace(r"(\d\d)(\d\d)$", r"\1:\2", regex=True),
                            "open": df["open"][keep], "high": df["high"][keep], "low": df["low"][keep],
                            "close": df["close"][keep], "volume": df["volume"][keep]})
        p = os.path.join(ROOT, "data", "intraday", f"{sym}_5m_alpaca.csv")
        out.to_csv(p, index=False)
        print(sym, len(out), out["time"].iloc[0][:10], "->", out["time"].iloc[-1][:10])


if __name__ == "__main__":
    main()
