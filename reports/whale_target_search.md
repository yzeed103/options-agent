# Catching price before it reaches whale levels (stocks only)
Stocks: COST, INTU, JNJ, UNH, HOOD, 15m, 2025-04-01 .. 2026-10-21. Targets = nearest whale level ahead (tall columns of
the 200-row profile of the latest completed sideways range, daily + weekly). Scripts: `whale_target_search.py`,
`whale_target_checks.py` (+ `.txt`, `whale_target_grid.csv`, `whale_target_test.csv`).

Search: 10 entries (incl. new "whale bounce": touch a whale level and close back on the side price came from) x 8
filters x 18 exits (stop 0.75/1/1.5 ATR, target the nearest whale level >= 1.5/2/3R away, intraday or hold up to
5 sessions) = 1,296 configs, chosen on 2025-04..2026-03 (pooled, positive on >= 4/5 stocks), top 3 frozen.

## Best rule
Whale bounce, any time of day, stop 1 ATR (15m), target = nearest whale level >= 3R away, hold up to 5 sessions.
| Period | Trades | Win | PF | R/trade | COST | HOOD | INTU | JNJ | UNH |
|---|---|---|---|---|---|---|---|---|---|
| Dev (selection) | 289 | 22.5% | 1.44 | +0.37 | -0.23 | +0.44 | +0.38 | +0.01 | +0.86 |
| **Test (once)** | 418 | 20.6% | **1.18** | **+0.17** | -0.24 | +0.46 | +0.33 | +0.03 | +0.37 |
| Test, 2x costs | 418 | 20.6% | 1.13 | +0.13 | | | | | |
Longs +0.25R, shorts +0.11R on the test period.

## Is it the whale levels?
| Same rule with... | Dev R/trade | Test R/trade |
|---|---|---|
| Whale levels (tall columns) | +0.37 (in-sample) | +0.17 |
| Thin columns of the same profile | -0.03 | +0.42 |
| Random levels in the same range (10 draws) | -0.03 avg (-0.28..+0.25) | -0.03 avg (-0.43..+0.19) |
Permutation (signal times shuffled within the day): p = 0.07.

**Verdict: promising but NOT proven.** The rule stayed profitable out of sample and after 2x costs, and beat the
average random level in both periods, but it is inside the range random levels can produce, thin columns were
better in one period and worse in the other, and the permutation test is not significant. Per stock it is
consistent: HOOD, INTU, UNH positive in both periods, COST negative in both, JNJ flat. Needs more data
(more stocks / longer history) or paper trading before real money.
