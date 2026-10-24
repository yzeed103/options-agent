# Breaking a swing high or low with a strong bar: pre-registration (2026-10-24, before any run)

Question (prompts/PROMPT_BREAKOUT_VOLUME.md): at a level break, does the breaking bar's volume add to what its size
already says about whether the break holds? Nothing below changes after results are seen; bugs are dated at the end.

## Data
SIP 5m bars, 30 symbols, regular session, 2025-04 to now; 15m by resampling; 1h as a robustness line only. First
60% of days train (quintile edges), last 40% test. RVOL and zRVOL = slot RVOL (vzones/volume_tool.rvol_set), ATR =
Wilder 14. Groups as in reports/eyes/DEFINITIONS.md.

## Levels (price only, known before the break)
- **swing**: pivot high / low with k bars on each side (ta.pivothigh style), confirmed k bars after the pivot; the
  pre-chosen k = 2 (the indicator's trendline default); k = 5 reported. Same session only. A level is live from its
  confirmation until the first close beyond it.
- **prior-day high / low**; **prior-day POC / VAH / VAL** (70% value area from the day's 5m bars); **GEX walls CW /
  PW** of the day (stored days only).

## Break event (bar t)
The first close beyond a live level L with every close since the level's origin (the pivot bar, or the session start
for day levels) on the other side, and at least 10 bars since that origin. Up-break through a level above, down-break
through a level below. When one bar breaks several levels of the same type, the nearest to the previous close counts.
No event in the first 5 bars of a session.

## Measures at t (past only)
RVOL[t]; **range/ATR**[t]; body/range[t]; break strength **B** = 0.5·zRVOL + 0.25·(range/ATR − 1) + 0.25·body/range;
penetration = dir·(close − L)/ATR; **absorption** = RVOL > 1.5 and range/ATR < 0.7; touches = number of separate
approaches within 0.1 ATR of L in the 60 bars before t (clusters separated by ≥ 2 bars); VWAP distance of L in ATR.
**Price-only control** C = range/ATR[t].

## Targets (future only)
B1 **hold**: no close back across L in the next 12 bars and close[t+12] beyond L by ≥ 0.5 ATR (needs 12 bars in the
session). B2 **follow-through**: +1 ATR beyond close[t] before −1 ATR within 2 hours (24 bars on 5m, 8 on 15m).
B3 **false break**: a close back across L within 3 bars. B4 **size**: max favourable excursion in ATR within 12 bars.

## Metrics
Hit rate of B1 (and B2, B3) by quintile of each measure (edges from train events of the same level type and
timeframe); lift = top-quintile hit rate / all; **paired lift against C** (trend_volume.paired_lift, bootstrap over
symbol-days); IC with B4 (ranks within symbol); the **grid** range/ATR tercile × RVOL tercile of the B1 rate; per level
type; up vs down; groups on 5m; false breaks by absorption flag. Event counts always shown.

## Planted tests (fresh seeds 40000..40039 for the gate; lower seeds while coding)
Synthetic 5m symbol-years: random walk with mean-reverting range phases (so pivots and breaks occur), U-shaped
persistent volume; the same detector finds the breaks.
- **W1 no relation**: the breaking bar's volume is independent of the outcome. Pass: no measure beats the control
  (paired lower bound > 0 for none).
- **W2 planted**: prices first, breaks, then the break bar's volume set to 2× with an outcome-dependent probability so
  that P(B1 | RVOL > 1.5) ≈ 0.45 against ≈ 0.25 otherwise. Pass: RVOL's top-quintile lift recovers ≥ 70% of the
  planted lift (B1 rate among 2× bars over all), and the control's lift is unchanged between W1 and W2 (same prices).

## Verdict rule (test days, swing levels k = 2)
**works**: on 5m and 15m, RVOL's or B's top-quintile lift on B1 beats C's (paired interval excludes 0) and its own
lift interval excludes 1, the top RVOL tercile's B1 rate is above the tercile mean inside at least two of the three
range terciles, and the sign holds for up-breaks and down-breaks. **size only**: C's lift interval excludes 1 and the
paired volume-minus-size interval includes 0. **no**: otherwise. **Absorption warning**: B3 rate with the flag above
the rate without it, interval excluding 0, on both timeframes.

## Falsifiable statements
H1 big breaking bars hold more (C lift > 1). H2 volume adds to size (paired > 0). H3 absorption bars produce more
false breaks. H4 the effect is larger on swing levels than on value-area levels. H5 down-breaks on volume hold more
than up-breaks. H6 levels touched 3+ times break-and-hold more often than levels touched once (price only).

## Changes after writing
(none yet)
