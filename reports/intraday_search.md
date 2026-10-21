# Intraday (5m / 15m) strategy search: SPY, Apr-Oct 2026

**Result: no configuration passed. Do not trade any of these setups as a system.**

## Data and limits
- `data/intraday/SPY_5m.csv`: TradingView export BATS:SPY, 5-minute, regular hours, 2026-04-13 to 2026-10-21,
  134 sessions. 15m bars built by resampling. Volume is BATS-only (relative volume only).
- Far below the prompt's requirement (2 years, SPY **and** QQQ). Walk-forward windows were shortened to
  train 8 weeks / test 4 weeks. The hold-out is the last 27 sessions (about 5 weeks), touched once.

## What was tested
- 8 setups: opening-range breakout, prior-day value-area re-entry (80% rule), VWAP reclaim, acceptance outside
  prior-day value, initial-balance break, prior-day POC reclaim, failed break of prior-day high/low (trap),
  Bollinger-in-Keltner squeeze release.
- 12 filters: trend (any / with EMA20-50), time window (all / first 2 h / 11:00-15:30), relative volume vs same
  time of day (none / >= 1.2).
- 24 exits: stop 0.75 / 1.0 / 1.5 ATR x targets 2.5 / 4 / 6 ATR, nearest prior-day level or VWAP 2-sigma band
  at least 2R / 3R away, ATR trailing stop 2 / 3, 1R partial + runner.
- 2,208 configurations on 5m and 2,280 on 15m (4,488 total). Costs 0.02% round trip, and 2x for the hold-out.
  Entry next bar open, stop-first if stop and target hit in the same bar, gap fills at the open, flat at the close.

## Results (after costs)
| | 5m | 15m |
|---|---|---|
| Walk-forward (stitched test windows) | 25 trades, PF 1.10, +0.09R/trade, 1.8/week | 17 trades, PF 0.67, -0.30R/trade, 1.2/week |
| Frozen rule for the hold-out (best dev config with >= 3/week and avg win >= 2.5R) | IB break, first 2 h, stop 1 ATR, target 6 ATR | POC reclaim with trend, stop 0.75 ATR, trail 2 ATR |
| Same rule on the dev period | 80 trades, PF 1.11, +0.09R | 69 trades, PF 1.18, +0.14R |
| Permutation test on dev (shuffle signal time within the day) | p = 0.42 (not significant) | p = 0.18 (not significant) |
| **Hold-out (once)** | 20 trades, **PF 0.86**, -0.14R | 17 trades, **PF 0.05**, -0.95R |
| Hold-out at 2x costs | PF 0.69 | PF 0.02 |

Walk-forward picked a different setup in almost every window (squeeze, IB break, ORB, VWAP reclaim, POC
reclaim): a sign that no single setup carries a stable edge in this sample.

## Best near-miss (in-sample only, NOT validated)
15m opening-range breakout, first 2 hours, relative volume >= 1.2, stop 0.75 ATR: 31 dev trades, PF 1.4-1.6,
+0.35R/trade, average win ~2.8-3.1R. It fails the activity floor (1.4 trades/week, needs 3) and was not
selected by walk-forward consistently. Worth re-testing on 2+ years of SPY and QQQ before any use.

## Files
`reports/intraday_search.py` (protocol), `intraday_search.json` (summary), `intraday_grid.csv` (every
configuration), `intraday_walkforward_picks.csv`, `intraday_search.txt` (console output).

## Update: QQQ added (BATS:QQQ 5m, 129 sessions, 2026-04-20 to 2026-10-21)
### Same protocol run on QQQ alone (`intraday_search_QQQ.json`)
| | 5m | 15m |
|---|---|---|
| Walk-forward | 20 trades, PF 0.22 | 16 trades, PF 1.08, 1.2/week |
| Frozen rule | POC reclaim, first 2 h, trail 3 ATR | VWAP reclaim, first 2 h, stop 0.75, trail 2 ATR |
| Dev period | PF 1.14, permutation p = 0.29 | PF 1.49, +0.31R, permutation p = 0.04 |
| **Hold-out (once)** | 13 trades, **PF 0.09** | 22 trades, **PF 0.74** |

### SPY rules applied unchanged to QQQ (a symbol never used in the SPY search; `intraday_crosscheck.txt`)
| Rule (frozen on SPY) | QQQ | SPY, full period |
|---|---|---|
| 5m IB break, first 2 h, stop 1, target 6 ATR | 81 trades, PF 1.10, +0.09R | 100 trades, PF 1.05 |
| 15m POC reclaim with trend, trail 2 ATR | 94 trades, PF 1.23, +0.15R | 86 trades, PF 0.91 |
| 15m ORB first 2 h, RVOL >= 1.2, stop 0.75, target 6 ATR | 48 trades, PF 0.95 | 40 trades, PF 2.05 |
| 15m ORB first 2 h, RVOL >= 1.2, stop 0.75, trail 2 ATR | 48 trades, PF 1.21, +0.16R, avg win 3.8R | 40 trades, PF 2.11 |

**Conclusion after QQQ: still nothing passes.** Every frozen rule lost on its own hold-out. No rule is positive on
both symbols with a profit factor near the 1.3 bar, and the best cross-symbol candidate (15m ORB with
volume filter and a 2-ATR trail) trades only ~1.5-1.8 times a week. It is the only idea worth re-testing on a
longer history (15m exports cover about 3x more time for the same bar limit).
