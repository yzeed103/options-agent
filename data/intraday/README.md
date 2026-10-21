# Intraday data (5m / 15m)

Put one CSV per symbol here, named `<SYMBOL>_<minutes>m.csv` (for example `SPY_5m.csv`, `QQQ_15m.csv`)
with columns `time,open,high,low,close,volume`. Times are New York local time unless they carry a UTC offset.
At least 2 years of regular-trading-hours bars are needed. Record the source, date range and adjustments here.

Status: EMPTY. The build environment could not reach any data provider (Polygon, Alpaca, Tiingo, Databento,
Yahoo, Stooq, Alpha Vantage were all blocked by the network policy), and the only reachable source
(QuantConnect Lean sample) has just 5 days of SPY minute data from October 2013.
