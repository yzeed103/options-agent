"""OHLCV loaders: Yahoo Finance (yfinance) or QuantConnect Lean CSV snapshots.

The Lean files in ``data/`` are public daily/hourly bars of SPY (S&P 500 ETF)
and QQQ (Nasdaq-100 ETF) from https://github.com/QuantConnect/Lean, prices are
stored multiplied by 10,000.
"""
from __future__ import annotations

import gzip
import os
from pathlib import Path

import pandas as pd

COLS = ["open", "high", "low", "close", "volume"]
DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load_lean_csv(path: str | os.PathLike, tz: str = "America/New_York") -> pd.DataFrame:
    """Read a Lean equity CSV (``yyyyMMdd HH:mm,o,h,l,c,v`` with prices x10000)."""
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt") as fh:
        df = pd.read_csv(fh, header=None, names=["time", *COLS])
    df["time"] = pd.to_datetime(df["time"], format="%Y%m%d %H:%M")
    df = df.set_index("time").sort_index()
    df[["open", "high", "low", "close"]] = df[["open", "high", "low", "close"]] / 10_000.0
    df["volume"] = df["volume"].astype(float)
    return df[COLS]


def load_yahoo(symbol: str, period: str = "2y", interval: str = "1d") -> pd.DataFrame:
    """Download OHLCV via yfinance and normalise column names."""
    import yfinance as yf

    raw = yf.download(symbol, period=period, interval=interval, auto_adjust=True, progress=False)
    if raw is None or len(raw) == 0:
        raise RuntimeError(f"yfinance returned no data for {symbol}")
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    df = raw.rename(columns=str.lower)[COLS].astype(float)
    df.index.name = "time"
    return df.dropna()


def load_ohlcv(symbol: str, source: str = "auto", period: str = "2y", interval: str = "1d") -> pd.DataFrame:
    """``source``: 'yahoo', 'lean' (bundled snapshot) or 'auto' (yahoo, then lean)."""
    sym = symbol.lower().lstrip("^")
    lean_name = {"1d": "daily", "1h": "hourly", "60m": "hourly"}.get(interval, interval)
    lean_path = DATA_DIR / f"{sym}_{lean_name}_lean.csv.gz"
    if source in ("yahoo", "auto"):
        try:
            return load_yahoo(symbol, period=period, interval=interval)
        except Exception as exc:  # network blocked, bad symbol, ...
            if source == "yahoo":
                raise
            print(f"[vzones] yahoo failed ({exc.__class__.__name__}); falling back to {lean_path.name}")
    if not lean_path.exists():
        raise FileNotFoundError(f"no bundled data for {symbol} {interval}: {lean_path}")
    return load_lean_csv(lean_path)
