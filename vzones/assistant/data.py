"""Bars, options levels and VIX for the assistant. Everything is cached under runtime/ (git-ignored).

- 5-minute regular-hours bars from Alpaca (IEX feed, split-adjusted), one CSV per symbol in runtime/bars/.
  Keys come from GEXRadar's config inside this process only; they are never printed, logged or written.
- Options levels per day from GEXRadar's SQLite (read-only). The levels used for day D are the LAST row of the
  previous market date, so nothing computed during day D leaks into day D.
- VIX daily closes from Yahoo; day D uses the close of the previous trading day.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RUNTIME = os.path.join(ROOT, "runtime")
BARS = os.path.join(RUNTIME, "bars")
GEX_DB = r"C:/project/gex_radar/data/snapshots.db"
GEX_RADAR = r"C:\project\gex_radar"
HISTORY_START = "2025-04-01"
NY = "America/New_York"


def watchlist(base: str = "http://127.0.0.1:8000") -> list[str]:
    """GEXRadar's symbols that Alpaca can trade-print (indices such as ^SPX have no stock bars: skipped)."""
    import json
    import urllib.request
    try:
        with urllib.request.urlopen(f"{base}/api/symbols", timeout=20) as r:
            syms = [s["symbol"] for s in json.loads(r.read())["symbols"] if s.get("ok")]
    except Exception:  # noqa: BLE001 - GEXRadar down: fall back to what is cached
        syms = sorted(f[:-7] for f in os.listdir(BARS) if f.endswith("_5m.csv")) if os.path.isdir(BARS) else []
    return [s for s in syms if s.isalnum()]


def _client():
    if GEX_RADAR not in sys.path:
        sys.path.insert(0, GEX_RADAR)
    from app import config                                    # keys read in-process only
    from alpaca.data.historical import StockHistoricalDataClient
    return StockHistoricalDataClient(config.ALPACA_API_KEY, config.ALPACA_SECRET_KEY)


def _fetch(cl, syms: list[str], start: datetime, end: datetime | None) -> dict[str, pd.DataFrame]:
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
    from alpaca.data.enums import DataFeed, Adjustment
    res = cl.get_stock_bars(StockBarsRequest(symbol_or_symbols=syms, timeframe=TimeFrame(5, TimeFrameUnit.Minute),
                                             start=start, end=end, feed=DataFeed.IEX, adjustment=Adjustment.SPLIT))
    df = res.df
    out = {}
    if df is None or df.empty:
        return out
    df = df.reset_index()
    for sym, g in df.groupby("symbol"):
        t = pd.to_datetime(g["timestamp"], utc=True).dt.tz_convert(NY)
        m = t.dt.hour * 60 + t.dt.minute
        keep = ((m >= 570) & (m < 960) & (t.dt.weekday < 5)).to_numpy()
        b = pd.DataFrame({"open": g["open"].to_numpy(), "high": g["high"].to_numpy(), "low": g["low"].to_numpy(),
                          "close": g["close"].to_numpy(), "volume": g["volume"].to_numpy()}, index=pd.DatetimeIndex(t))[keep]
        b.index.name = "time"
        out[sym] = b
    return out


def path(sym: str) -> str:
    return os.path.join(BARS, f"{sym}_5m.csv")


def load_bars(sym: str) -> pd.DataFrame:
    p = path(sym)
    if not os.path.exists(p):
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    d = pd.read_csv(p)
    d.index = pd.to_datetime(d["time"], utc=True).dt.tz_convert(NY)
    d.index.name = "time"
    return d[["open", "high", "low", "close", "volume"]].astype(float)


def update_bars(syms: list[str], now: datetime | None = None, batch: int = 10) -> dict[str, int]:
    """Append new CLOSED 5m bars for each symbol (re-fetching the last stored day, so a partial day is completed).
    Returns symbol -> rows added. A bar is kept only once its 5 minutes have passed."""
    os.makedirs(BARS, exist_ok=True)
    now = now or datetime.now(timezone.utc)
    cl = _client()
    old = {s: load_bars(s) for s in syms}
    groups: dict[str, list[str]] = {}
    for s in syms:
        start = (old[s].index[-1].normalize().tz_convert("UTC").to_pydatetime() if len(old[s])
                 else datetime.fromisoformat(HISTORY_START).replace(tzinfo=timezone.utc))
        groups.setdefault(start.isoformat(), []).append(s)
    added = {}
    for start_iso, ss in groups.items():
        start = datetime.fromisoformat(start_iso)
        for i in range(0, len(ss), batch):
            part = ss[i:i + batch]
            got = _fetch(cl, part, start, None)
            for s in part:
                new = got.get(s)
                if new is None or new.empty:
                    added[s] = 0
                    continue
                new = new[new.index + pd.Timedelta(minutes=5) <= pd.Timestamp(now)]      # closed bars only
                merged = pd.concat([old[s][old[s].index < new.index[0]] if len(old[s]) else old[s], new])
                merged = merged[~merged.index.duplicated(keep="last")].sort_index()
                added[s] = len(merged) - len(old[s])
                out = merged.copy()
                out.insert(0, "time", out.index.strftime("%Y-%m-%d %H:%M:%S%z"))
                out.to_csv(path(s) + ".tmp", index=False)
                os.replace(path(s) + ".tmp", path(s))
    return added


def resample15(d5: pd.DataFrame) -> pd.DataFrame:
    """15-minute bars from 5-minute bars, within each session (09:30, 09:45, ...)."""
    if d5.empty:
        return d5
    key = d5.index.floor("15min")
    return d5.groupby(key).agg(open=("open", "first"), high=("high", "max"), low=("low", "min"),
                               close=("close", "last"), volume=("volume", "sum")).rename_axis("time")


# ---------------- official daily bars ----------------
def daily_bars(sym: str, days: list) -> pd.DataFrame | None:
    """Official daily high / low / close from Yahoo (split-adjusted, not dividend-adjusted, like the Alpaca bars),
    for the whale ranges: the indicator builds them from TradingView's daily bars, and those official values differ
    slightly from daily bars built out of IEX 5-minute bars (tools/paper_parity.py). Cached in runtime/daily/, refreshed
    every 6 hours. Days Yahoo lacks fall back to the intraday aggregate (caller). None if unavailable."""
    p = os.path.join(RUNTIME, "daily", f"{sym}.csv")
    v = None
    if os.path.exists(p) and datetime.now().timestamp() - os.path.getmtime(p) < 6 * 3600:
        v = pd.read_csv(p, index_col=0)
    if v is None:
        try:
            import yfinance as yf
            h = yf.Ticker(sym).history(start=HISTORY_START, interval="1d", auto_adjust=False, actions=False)
            v = pd.DataFrame({"high": h["High"], "low": h["Low"], "close": h["Close"]})
            v.index = [t.date().isoformat() for t in h.index]
            os.makedirs(os.path.dirname(p), exist_ok=True)
            v.to_csv(p)
        except Exception:  # noqa: BLE001
            v = pd.read_csv(p, index_col=0) if os.path.exists(p) else None
    if v is None or v.empty:
        return None
    v.index = [pd.Timestamp(x).date() for x in v.index]
    return v.reindex(days)


# ---------------- options levels ----------------
def gex_levels(sym: str) -> pd.DataFrame:
    """Per trading date D: the options levels known before D's open (= the previous market date's row, basis 'oi').
    Columns: cw, pw, flip, pin, dflip. Index: date of use."""
    if not os.path.exists(GEX_DB):
        return pd.DataFrame()
    c = sqlite3.connect(f"file:{GEX_DB}?mode=ro", uri=True)
    try:
        q = pd.read_sql_query("select market_date, call_wall cw, put_wall pw, gamma_flip flip, pin, delta_flip dflip "
                              "from daily_levels where symbol=? and basis='oi' order by market_date", c, params=(sym,))
    finally:
        c.close()
    if q.empty:
        return q
    q["market_date"] = pd.to_datetime(q["market_date"]).dt.date
    q = q.set_index("market_date")
    q.index = [d for d in q.index]
    return q


LEVEL_COLS = ["cw", "pw", "flip", "pin", "dflip", "maxoi", "cwoi", "pwoi"]


def _decode(blob):
    import gzip
    import json
    import zlib
    raw = bytes(blob)
    for f in (lambda b: b, zlib.decompress, gzip.decompress):
        try:
            return json.loads(f(raw))
        except Exception:  # noqa: BLE001
            continue
    return None


def gex_levels_full(sym: str) -> pd.DataFrame:
    """All stored market dates (basis 'oi') with CW PW FLIP PIN DFLIP MAXOI and the open-interest walls CWOI / PWOI
    rebuilt from the row's strike table (vzones.gex_block.oi_walls, as the GEX block does). Cached in
    runtime/cache/gex_<SYM>.csv; rebuilt when GEXRadar has a newer or different set of rows."""
    if not os.path.exists(GEX_DB):
        return pd.DataFrame(columns=LEVEL_COLS)
    c = sqlite3.connect(f"file:{GEX_DB}?mode=ro", uri=True)
    try:
        sig = c.execute("select count(*), max(market_date), max(updated_at) from daily_levels where symbol=? and basis='oi'",
                        (sym,)).fetchone()
        cp = os.path.join(RUNTIME, "cache", f"gex_{sym}.csv")
        tag = f"{sig[0]}|{sig[1]}|{sig[2]}"
        if os.path.exists(cp):
            cached = pd.read_csv(cp, index_col=0)
            if "tag" in cached and len(cached) and str(cached["tag"].iloc[0]) == tag:
                cached.index = [pd.Timestamp(x).date() for x in cached.index]
                return cached[LEVEL_COLS]
        from vzones.gex_block import oi_walls
        rows = {}
        for md, cw, pw, fl, pin, dfl, blob in c.execute(
                "select market_date, call_wall, put_wall, gamma_flip, pin, delta_flip, payload from daily_levels "
                "where symbol=? and basis='oi' order by market_date", (sym,)):
            p = _decode(blob) or {}
            lv = p.get("levels") or {}
            st = p.get("strikes") or []
            spot = p.get("spot") or 0.0
            cwoi, pwoi = oi_walls(st, spot) if st and spot else (None, None)
            rows[md] = dict(cw=cw, pw=pw, flip=fl, pin=pin, dfl=dfl, maxoi=lv.get("max_oi_strike"), cwoi=cwoi, pwoi=pwoi)
    finally:
        c.close()
    out = pd.DataFrame.from_dict(rows, orient="index").rename(columns={"dfl": "dflip"})
    out = out.reindex(columns=LEVEL_COLS).astype(float)
    os.makedirs(os.path.dirname(cp), exist_ok=True)
    w = out.copy(); w["tag"] = tag
    w.to_csv(cp)
    out.index = [pd.Timestamp(x).date() for x in out.index]
    return out


def levels_for_days(sym: str, days: list) -> pd.DataFrame:
    """Row per day in `days`: the levels of the latest market date strictly before it (NaN if none within 5 days)."""
    g = gex_levels_full(sym)
    out = pd.DataFrame(index=days, columns=LEVEL_COLS, dtype=float)
    if g.empty:
        return out
    gd = sorted(g.index)
    import bisect
    for d in days:
        j = bisect.bisect_left(gd, d) - 1
        if j >= 0 and (d - gd[j]).days <= 5:
            out.loc[d] = g.loc[gd[j], LEVEL_COLS].astype(float).to_numpy()
    return out


# ---------------- VIX ----------------
def vix_prev_close(days: list) -> pd.Series:
    """Day D -> VIX close of the last trading day before D. Cached in runtime/vix.csv, refreshed once a day."""
    p = os.path.join(RUNTIME, "vix.csv")
    v = None
    if os.path.exists(p) and datetime.now().timestamp() - os.path.getmtime(p) < 6 * 3600:
        v = pd.read_csv(p, index_col=0, parse_dates=True)["close"]
    if v is None:
        try:
            import yfinance as yf
            h = yf.Ticker("^VIX").history(start="2025-01-01", interval="1d")
            v = h["Close"]; v.index = v.index.tz_localize(None).normalize()
            os.makedirs(RUNTIME, exist_ok=True)
            v.rename("close").to_csv(p)
        except Exception:  # noqa: BLE001
            v = pd.read_csv(p, index_col=0, parse_dates=True)["close"] if os.path.exists(p) else pd.Series(dtype=float)
    vd = {k.date(): float(x) for k, x in v.items()}
    keys = sorted(vd)
    import bisect
    return pd.Series({d: (vd[keys[j]] if (j := bisect.bisect_left(keys, d) - 1) >= 0 else np.nan) for d in days})
