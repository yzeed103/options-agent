# Intraday data (5m / 15m)

Put one CSV per symbol here, named `<SYMBOL>_<minutes>m.csv` (for example `SPY_5m.csv`, `QQQ_15m.csv`)
with columns `time,open,high,low,close,volume`. Times are New York local time unless they carry a UTC offset.
At least 2 years of regular-trading-hours bars are needed. Record the source, date range and adjustments here.

## Files
- `QQQ_5m.csv`: TradingView export, BATS:QQQ, 5-minute, regular hours, 2026-04-20 to 2026-10-21 (129 sessions).
  The first 5 exported sessions (2026-04-13..17) had no volume and were dropped. BATS-only volume.
- `SPY_5m.csv`: TradingView export, symbol BATS:SPY, 5-minute bars, regular trading hours only,
  2026-04-13 09:30 to 2026-10-21 10:35 New York, 134 sessions, 10,388 bars. Volume is BATS-only volume
  (a fraction of consolidated volume), so only RELATIVE volume is meaningful. Prices as exported (not adjusted).
  15-minute bars are built from it with `vzones.intraday.data.resample`.

Previous status (before the upload): The build environment could not reach any data provider (Polygon, Alpaca, Tiingo, Databento,
Yahoo, Stooq, Alpha Vantage were all blocked by the network policy), and the only reachable source
(QuantConnect Lean sample) has just 5 days of SPY minute data from October 2013.
- `<SYM>_5m_alpaca.csv` (SPY QQQ COST INTU JNJ UNH HOOD): Alpaca IEX feed, 5-minute, regular hours, split-adjusted
  (not dividend-adjusted), 2025-04-01 to 2026-10-22, ~30k bars each (COST / INTU fewer: IEX had no trade in some bars).
  Volume is IEX-only. Fetched with `tools/fetch_alpaca_5m.py`. Checked against the TradingView SPY export: same bars,
  5m return correlation 0.994, constant per-day price ratio (TradingView adjusts for dividends).
