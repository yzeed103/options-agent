# Intraday data (5m / 15m)

Put one CSV per symbol here, named `<SYMBOL>_<minutes>m.csv` (for example `SPY_5m.csv`, `QQQ_15m.csv`)
with columns `time,open,high,low,close,volume`. Times are New York local time unless they carry a UTC offset.
At least 2 years of regular-trading-hours bars are needed. Record the source, date range and adjustments here.

## Files
- `SPY_5m.csv`: TradingView export, symbol BATS:SPY, 5-minute bars, regular trading hours only,
  2026-04-13 09:30 to 2026-10-21 10:35 New York, 134 sessions, 10,388 bars. Volume is BATS-only volume
  (a fraction of consolidated volume), so only RELATIVE volume is meaningful. Prices as exported (not adjusted).
  15-minute bars are built from it with `vzones.intraday.data.resample`.

Previous status (before the upload): The build environment could not reach any data provider (Polygon, Alpaca, Tiingo, Databento,
Yahoo, Stooq, Alpha Vantage were all blocked by the network policy), and the only reachable source
(QuantConnect Lean sample) has just 5 days of SPY minute data from October 2013.
