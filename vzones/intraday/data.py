"""Load intraday OHLCV, keep regular trading hours (09:30-16:00 New York), resample."""
from __future__ import annotations
import pandas as pd

COLS = ["open", "high", "low", "close", "volume"]


def load_csv(path, tz_in: str = "America/New_York", time_col: str = "time") -> pd.DataFrame:
    """CSV with columns time,open,high,low,close,volume. Naive times are taken as `tz_in`."""
    df = pd.read_csv(path)
    raw = df[time_col].astype(str)
    if raw.str.contains(r"[+-]\d{2}:?\d{2}$|Z$", regex=True).any():
        t = pd.to_datetime(raw, utc=True)                      # offsets present (e.g. -04:00 / -05:00 across DST)
    else:
        t = pd.to_datetime(raw).dt.tz_localize(tz_in, ambiguous="infer", nonexistent="shift_forward")
    df.index = t.dt.tz_convert("America/New_York")
    return df[COLS].astype(float).sort_index()


def rth(df: pd.DataFrame) -> pd.DataFrame:
    """Regular trading hours only. Bars are labelled by their open time."""
    t = df.index.tz_convert("America/New_York") if df.index.tz is not None else df.index
    m = (t.hour * 60 + t.minute >= 570) & (t.hour * 60 + t.minute < 960)
    return df[m]


def resample(df: pd.DataFrame, minutes: int) -> pd.DataFrame:
    """Resample within each session (bars never span two days)."""
    out = []
    for _, g in df.groupby(df.index.date):
        r = g.resample(f"{minutes}min", origin=g.index[0].normalize() + pd.Timedelta(minutes=570), label="left", closed="left").agg(
            {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
        out.append(r)
    return pd.concat(out) if out else df.iloc[:0]
