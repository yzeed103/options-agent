# Whale levels (user's definition)
Latest sideways range on daily / half-weekly (3-day) / weekly candles -> fixed-range volume profile with 200 rows
built from intraday bars inside the range -> tall columns (local peaks) = whale levels, extended to the latest price.
Code: `vzones/whale_levels.py`; test: `reports/whale_levels_test.py`, output `.txt`, events `whale_levels_events.csv`;
picture: `reports/styles/O_whale_levels.png`.

Range = 20 daily / 15 three-day / 12 weekly candles with high-low span <= 6 / 5 / 5 ATR, extended while closes stay
inside; used only after the first close outside it. Levels evaluated until the next range completes (max 120 days).
Controls: thin columns (valleys) of the same profile, and random prices inside the same range.

Data: SPY hourly 1998-2021 (consolidated volume, 440 ranges) and SPY, QQQ, COST, INTU, JNJ, UNH, HOOD 15m
2025-26 (BATS volume, 237 ranges).

Reached as a target (same distance from price at the breakout):
| Distance (ATR) | Whale levels | Random levels | Thin levels |
|---|---|---|---|
| 0-1 | 74.5% | 76.8% | 80.9% |
| 1-2 | 54.8% | 56.4% | 51.3% |
| 2-4 | 34.4% | 32.1% | 29.7% |
| 4-8 | 16.8% | 13.6% | 17.1% |
| > 8 | 9.7% | 6.3% | 8.5% |
No difference is statistically significant (largest z = 1.9 at 4-8 ATR).

Respected (price back on the approach side 3 days after the first touch): whale 49-63% vs random 49-60% by
distance; no consistent advantage.

**Conclusion:** in this test, the tall columns of the latest range's profile are not reached more often and are not
respected more than random prices in the same range. A slight tendency to be reached more at large distances
(4-8+ ATR) is not significant.
