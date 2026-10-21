# Direction study (no stop, no target)
15m bars, SPY, QQQ, COST, INTU, JNJ, UNH, HOOD, 2025-04-01 .. 2026-10-21. Entry = next bar open.
Measured: move after 1 h and at the session close (in ATR), minutes the price stayed on the right side of the
entry price and of EMA20, best/worst move until the close. Baseline = ordinary bars at the same time of day, same
direction. Full table: `direction_study.csv`, console: `direction_study.txt`.

Key results (all symbols, longs + shorts pooled):
| Setup | Signals | Right at close | Edge to close vs baseline (ATR) | t | 1st half | 2nd half |
|---|---|---|---|---|---|---|
| Acceptance outside prior-day value, with trend | 828 | 52.1% | +0.16 | 1.97 | +0.15 | +0.18 |
| Acceptance outside prior-day value, any | 1354 | 49.9% | +0.10 | 1.55 | +0.08 | +0.12 |
| ORB with trend | 675 | 49.9% | +0.06 | 0.58 | -0.21 | +0.31 |
| VWAP reclaim | 5028 | 51.1% | +0.02 | 0.49 | 0.00 | +0.03 |
| Pool break (indicator) | 785 | 46.4% | **-0.13** | **-2.10** | -0.21 | -0.06 |
| Rejection (indicator) | 1309 | 48.9% | -0.08 | -1.36 | -0.09 | -0.08 |

- Only "acceptance outside prior-day value with trend" is positive in both halves; its edge is small (+0.16 ATR to the
  close, 52% right) and borderline significant (t ~ 2 among ~22 tested variants, so not proven).
- Pool breaks tend to REVERSE, not continue (negative in both halves).
- Time held above entry is close to baseline for every setup. Time held with EMA20 looks longer for trend-filtered
  setups, but that is mostly built in (price is already on the trend side of the EMA at the signal).
