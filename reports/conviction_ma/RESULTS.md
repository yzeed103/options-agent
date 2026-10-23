# Conviction moving average for Heikin Ashi: result

**Verdict: the idea fails test 1 (planted trend). Per PREREG, the work stops here: no real-data tuning, no Pine line.**

## Gate (200 seeds, defaults law A, g 0.3, keep 0.6, p 1, 8 / 60), `python tools/conviction_eval.py planted`
| filter | drift lag (bars) | false flips / 100 sideways bars |
|---|---|---|
| conviction average A | 3.53 | 26.3 |
| EMA(8) of HA close (matched) | 3.50 | 19.4 |
| conviction B / C | 7.2 / 7.5 | 24.7 / 25.2 |
| streak EMA (baseline) | 10.9 | 13.1 |

Fewer false flips than the matched EMA: **-37% (95% interval -38% to -36%)**. Required: at least +25%. Fail.
Noise test (commit share on random walks) passes (0.72 vs 0.88), but the gate is the deciding test.

## Is it the defaults or the idea? (exploratory, after the result)
All 50 grid points (`tools/conviction_grid_planted.py`, `planted_grid.json`) and, with the trend lag that has no
drift trick (`tools/conviction_trend_lag.py`, `trend_lag.txt`):

| version | trend lag | flips | EMA at same lag | flips | fewer |
|---|---|---|---|---|---|
| A defaults | 4.22 | 26.2 | EMA(8) | 19.1 | -37% |
| A best grid (g 0.15, p 2) | 5.74 | 24.1 | EMA(11) | 17.9 | -34% |
| B | 4.69 | 24.8 | EMA(9) | 18.6 | -33% |
| C | 7.42 | 25.2 | EMA(14) | 17.3 | -45% |
| streak EMA (baseline) | 7.76 | 13.3 | EMA(15) | 17.3 | **+23%** |

No point of the grid has fewer false flips than an EMA of the same lag. The idea, not the settings, fails.

## Why
Heikin Ashi candles in a sideways market still come in short runs of strong-looking bodies. Candle strength
(body, wick, size vs ATR) rises on each run, so conviction rises and the average **speeds up inside the range**:
exactly where it should slow down. The plain colour-streak baseline does better (+23%, just under the 25% bar) because
it needs several same-colour candles in a row before it speeds up; adding candle strength makes it worse.

## What was not done (on purpose)
Real-data tuning and verdict, whipsaw / capture / trading / robustness tests, Pine line, parity, screenshot: all
conditional on passing test 1.
