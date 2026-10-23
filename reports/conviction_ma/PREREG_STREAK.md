# Colour-streak average for Heikin Ashi: pre-registration (2026-10-23, before any run of this protocol)

Follows the failed conviction average (RESULTS.md). There, the plain streak baseline at its default (8 / 60, cap 10)
had 23% fewer sideways false flips than an EMA of the same trend lag on planted seeds 0..59. That number was seen,
so the gate below runs on **fresh seeds** that no one has looked at.

## Formula
HA candles. streak_t = earlier candles in a row with the same colour as candle t (0 on a colour change or doji).
`S = (min(streak, cap) / cap) ** p`, `a = a_slow + (a_fast - a_slow) S`, `a = 2 / (L + 1)`,
`M_t = M_{t-1} + a_t (HAclose_t - M_{t-1})`, seeded with the SMA of the first L_slow values.
Parameters (4): cap, p, L_fast, L_slow.

## Lag
**Trend lag** (primary): in the planted trends (bars 60..150 of each trend), mean(price - M) times the trend sign,
divided by the trend step per bar. EMA(n) of HA close is matched to the same trend lag (search n = 2..60). The drift
lag is reported but not used (it is unreliable for filters whose speed depends on candle colour).

## Step 1, choose settings (seeds 0..199, already seen)
Grid: cap {5, 10, 15} x p {1, 2} x L_fast {5, 8, 12} x L_slow {40, 60, 100} (54 points). Objective: largest
share of fewer sideways false flips than the matched EMA, subject to trend lag <= 8 bars. One point chosen.

## Step 2, gate (seeds 10000..10199, fresh)
The chosen point vs the EMA of the same trend lag (+-10%), paired by seed. **Pass**: at least 25% fewer false flips,
95% bootstrap interval > 0. Also: pure-noise commit share <= 1.10 x the matched EMA's. Also reported: delay to commit
after each trend start, and the dent from one strong red candle in the up trend. **If it fails: stop and report.**

## Step 3, real data (only if step 2 passes)
SIP 5-minute regular-session bars, the same 30 symbols; 15m and 1h by resampling within sessions; daily. First 60%
of days = train, last 40% = test. At the chosen point, on test data: sign flips of M per 100 bars, noise
(mean |second difference of M| / mean |dP|), and whipsaws per session, vs EMA, SMA, HMA, ALMA, KAMA, VIDYA,
McGinley and SuperSmoother, each with its length set on **train** so its median drift lag on real data equals the
streak average's drift lag (real data has no known trend, so the drift lag is used there; reported with that caveat).
Intervals by bootstrap over symbol-days.
- **better**: fewer flips **and** lower noise than the best baseline, intervals excluding zero;
- **equal**: within the best baseline's interval (named); **worse**: otherwise.

## Step 4, Pine (only if "better" or "equal")
A fifth average «متوسط الثبات (هيكين آشي)» with the chosen settings; parity >= 99.9% of bars within 1e-6.

## Changes after writing
(none yet)
