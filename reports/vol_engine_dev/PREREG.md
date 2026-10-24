# PREREG — Volatility engine v2: develop the six tools and map their regimes

Written 2026-10-24 before any run. Baseline: reports/vol_engine (Pine v47, pane v3). Every hypothesis below has a
statistic, a control, a margin, a split and a verdict rule. Changes after this point are appended as dated entries
at the end; the text above the "Changes" heading is never edited.

## Data and split
- 5m: 30 SIP symbols (runtime_sip/bars), 2025-04-01 → 2026-10-22, 393 sessions, regular hours only, real OHLC.
  Train = the first 60% of sessions (same cut as vol_engine_eval.tf_block), test = the rest. Fits and thresholds on
  train only; verdicts on test.
- Daily validation: 177-symbol universe, 2020-01 → 2022-12, for the tools that have a daily analogue
  (T1 fan k=5, T2 exits k=5, T5 squeeze daily threshold 0.8833, T6 heat × trend). Tools with no daily analogue
  (T3 day range, T4 intraday ladder, intraday seasonality) are 5m-only and say so in their verdict.
- Bootstrap: 1,000 draws over symbol-days (5m) or symbol-months (daily); 95% intervals. "Interval excludes 0"
  means the 2.5–97.5 interval of the paired difference does not contain 0.
- Costs where a PnL is computed: 5 bp per side.
- Minimum cell size for any regime claim: 200 symbol-days with at least one event; below that the cell is "not enough data".

## Regimes (vzones/regimes.py, planted tests in planted.json)
- Trend: Hull state from vzones.trend_volume_model (bars.state ∈ {−1, 0, +1}) and S0 quintile (train edges).
- Heat: percent rank of the 24-bar expected move (√(24·s2)·close / close) over the previous 500 bars:
  cold < 20, mild 20–60, warm 60–80, hot 80–90, extreme > 90.
- Squeeze: ATR14/ATR100 < 0.6967 (5m) / 0.8833 (daily): none / entering (first bar) / ongoing (≥ 12 bars) / exiting (first bar back above).
- VIX quintile: daily VIX percent rank over the previous 500 days, quintiles; term structure: VIX > VIX3M = backwardation.
- Time of day (NY): open 09:30–10:00, mid 10:00–12:00, lunch 12:00–13:30, mid2 13:30–15:15, close 15:15–16:00.
- Day type: event = FOMC decision day (published calendar 2025–2026), NFP (first Friday of the month),
  monthly OPEX (third Friday), quarter-end (last session of Mar/Jun/Sep/Dec). CPI is NOT in the calendar
  (no reliable date list in the repo; stated honestly). Ordinary = everything else.
- Planted tests for the labeller: (R1) a synthetic series with known up/down/flat segments: the Hull state must agree
  with the planted sign on ≥ 80% of bars after the first 70 of each segment; (R2) known low-vol windows: squeeze
  "entering" must fire inside ≥ 80% of planted windows and in ≤ 5% of random 40-bar windows outside them;
  (R3) heat rank on iid data is uniform (KS p > 0.01).

## Shared machinery
- s2 = EWMA(0.99) variance of session log returns (first bar of a session uses log(close/open)); move_k = √(k·s2)·close.
- Standardized forward move z_k = (c[t+k] − c[t]) / move_k[t].
- Forward realized range R24 = log(max high / min low over the next 24 bars).
- Random control bars: 20 random test bars of the same symbol and the same time-of-day slot per event
  (matched on slot so intraday seasonality cannot masquerade as an effect).
- Entry simulation (ladder, fade, sizing): first touch of stop / target / horizon using the bar path (high/low),
  entry at the close of the signal bar, 5 bp per side.

## T1 Fan
- H1.1 Fat tails. Train: pooled z_24 quantiles q2.5, q16, q84, q97.5 (per symbol standardized, then pooled) and a
  Student-t df fitted by maximum likelihood on z_24. Test: coverage of [q16, q84] and [q2.5, q97.5] overall and per
  heat bin; Gaussian ±1/±2 as control. Rule: PASS if the empirical band's coverage is within 68.3 ± 2 (inner) and
  95 ± 2 (outer) overall AND in every heat bin with ≥ 200 symbol-days, AND the pinball loss at 16/84 is lower than the
  Gaussian band's with the interval excluding 0. Ship: replace the ±1σ/±2σ multipliers in Pine by the train quantiles.
- H1.2 Asymmetry. Separate q16 and q84 (not forced symmetric). Rule: PASS if pinball loss at 16/84 is lower than the
  symmetric empirical band's with interval excluding 0 AND |q84| − |q16| differs from 0 with interval excluding 0.
- H1.3 Intraday seasonality. Train: slot factor f_j = median over sessions of (r²_j / mean_session r²) for slot j.
  Forecast: EWMA on r²/f, then Σ of the next 24 slots' factors. Rule: PASS if QLIKE(seasonal) − QLIKE(plain) < 0
  with interval excluding 0 on test AND ±1σ coverage stays within 68.3 ± 3.
- H1.4 Horizon law. Train: regress log E|z_k·move_1| on log k for k ∈ {3, 6, 12, 24, 48} per symbol-day block;
  α = slope. Rule: PASS if the bootstrap interval of α excludes 0.5 AND bands scaled by k^α have |coverage − 68.3|
  smaller than the √k bands at k = 6, 12, 48 on test with intervals excluding 0 for at least two of the three.
- H1.5 Event days. Coverage of the H1.1 band on event test days (needs ≥ 100 symbol-days). If outside 68.3 ± 3, fit
  on train a widening w = a + b·VIXpct and retest. Rule: PASS if the widened band is within 68.3 ± 3 on event test days.
- Daily validation for H1.1: coverage of the train-quantile band at k = 5 on 2020–22 within 68.3 ± 3.

## T4 Ladder
- Entries: every test bar where Hull state ≠ 0 and the damped line confirms (bars.confirmed), direction = state,
  at most one entry per symbol per 24 bars. Horizon 24 bars. Target 1× move_24, stop d × move_24.
- H4.1 Stop multiple by regime. Grid d ∈ {0.5, 0.75, 1.0, 1.25, 1.5} in cells heat(5) × trend(up/down). Train picks the
  best d per cell by expectancy; test: paired difference of expectancy vs d = 0.75 per cell. Rule: PASS for a cell if
  the difference > 0 with interval excluding 0; ship a per-cell table only for passing cells, else keep 0.75.
- H4.2 Structure-aware stop. stop = max(0.75 × move_24, |entry − nearest adverse level| + 0.1 ATR) with levels =
  prior-day VAL/VAH/POC and the day's GEX call/put wall. Rule: PASS if stop-out frequency is lower than H4.1's winner
  with interval excluding 0 AND expectancy is not lower (difference interval contains 0 or is above it).
- H4.3 Target odds by state. P(1× before stop within 24) and P(2× …) in cells trend(3) × S0 quintile(5). Rule: a cell
  PASSES if its interval excludes the pooled rate (25% / 8% in the baseline; recomputed here). Ship as a per-state
  table only for passing cells.
- H4.4 Time stop. Expectancy with horizon 24 vs horizon 78 (rest of session) with the same stop/target. Rule: PASS if
  the 24-bar version has higher expectancy with interval excluding 0.
- H4.5 Trailing stop. Stop trails the best price by 0.75 × move_24 of the current bar. Rule: PASS if expectancy beats
  the fixed stop with interval excluding 0.

## T3 Day range (5m only)
- m_day = √(78 · s2 at the first bar) × open; lines open ± m_day. Fuel = (high so far − low so far) / (2 m_day).
- H3.1 Fuel thresholds. Event: first bar where fuel crosses 0.8 / 1.0 / 1.2. Outcome: reversal = the 12-bar
  (and 24-bar) move after the event has the opposite sign to (close − open). Pre-stated expectation: P(reversal) above
  random matched bars. Rule: PASS for a threshold if P(reversal) − P(reversal at random same-slot bars) has an
  interval excluding 0 (either sign reported; only the pre-stated sign ships).
- H3.2 Remaining-range decay. From each bar j: band ±√(remaining bars × s2_j) × close vs ±√(g(slot_j) × s2_j) × close
  with g from train (median of (remaining realized move / s2) by slot). Rule: PASS if |coverage − 68.3| of the
  empirical band is smaller with interval excluding 0.
- H3.3 Gap. s2_open' = s2 + λ·gap² with gap = log(open / prior close) and λ fit on train by QLIKE over the first 12 bars.
  Rule: PASS if QLIKE improves over those bars with interval excluding 0.
- H3.4 Touch. First touch of the upper/lower line in a session: P(close 12 bars later is back inside) vs random
  same-slot bars' P(12-bar move against the current side). Rule as H3.1.

## T2 Band exit
- Exit: close beyond close[t−24] ± move_24[t−24]; direction = sign.
- H2.1 After an exit. Signed forward return over 6/12/24 bars (sign = exit direction) and R24, vs matched random bars;
  by heat × squeeze cells. Rule: ship a DIRECTION reading only if the signed-return lift has an interval excluding 0
  in at least one cell with ≥ 200 symbol-days on test AND the same sign on daily validation (k = 5 exits, 2020–22);
  otherwise ship as range-only (R24 lift reported).
- H2.2 Exit clustering. x = number of exits in the last 24 bars; y = R24. ic_pooled within heat-bin strata
  (control for the level). Rule: PASS if the stratified ic > 0 with interval excluding 0.
- H2.3 Trend vs shock exits. Continuation rate (sign of the next 12-bar return = exit direction) for exits with the
  Hull trend vs against it. Rule: PASS if the two rates' intervals do not overlap.

## T6 Heat
- H6.1 Normalization. Ranks: (a) 500-bar, (b) same-slot over 20 sessions, (c) VIX-conditioned (rank of move / VIX).
  Target: R24. Rule: the best rank PASSES if its ic_pooled exceeds each other's with the paired interval excluding 0.
- H6.2 Acceleration. x = heat rank − heat rank 12 bars ago; y = R24; ic within heat-bin strata. Rule: PASS if > 0 with interval excluding 0.
- H6.3 Intraday vol targeting. Entries as T4 (d = 0.75, target 1×, horizon 24); size = median(move_24)/move_24 capped at 2.
  Daily PnL Sharpe on test vs unsized, bootstrap over days. The daily version failed (−0.16); the bar here is a Sharpe
  gain with interval excluding 0. Rule: PASS only then.
- H6.4 Heat × trend. Expectancy of the T4 base rule by heat bin. Rule: a bin PASSES if its interval excludes the pooled expectancy.
- Daily validation for H6.4: the same by heat bin on 2020–22 (k = 5, Hull on daily).

## T5 Squeeze
- H5.1 Definitions. (a) ATR14/ATR100 < 0.6967; (b) Bollinger width (20, 2) < train 10th pct; (c) Keltner-inside-Bollinger
  (BB(20,2) inside KC(20,1.5)); (d) realized-variance ratio Σr²(14)/Σr²(100) < train 10th pct. Target: expansion = R12
  above the same-slot median; vs random same-slot bars. Rule: report each; a definition "finds expansion" only if the
  lift interval excludes 0 and is positive; if all are below random, say so (that is the baseline finding).
- H5.2 Duration. Expansion rate by bars inside the squeeze: 1–5, 6–12, 13–24, > 24. Rule: PASS if Spearman of bin
  index vs rate has an interval excluding 0 (sign reported).
- H5.3 Exit of squeeze. Expansion over 12/24 and direction (P up) after the first bar back above threshold vs random.
  Rule: PASS if the expansion lift interval excludes 0; direction PASSES only if P(up) interval excludes 0.5.
- H5.4 Fade rule. Swing-level breaks (vzones.trend_volume_model breaks, type swing*) that occur while squeeze is
  ongoing: enter against the break at the break bar's close, stop 0.75 × move_24, target 1×, horizon 24, 5 bp.
  Rule: PASS if expectancy > 0 with interval excluding 0 on test AND on daily validation 2020–22 (daily breaks from
  vzones.structure_break; if that module cannot supply them, the verdict is "no validation possible" and nothing ships).
- H5.5 Lunch. Expansion rate for squeezes entering in the lunch bin vs the others. Rule: PASS if the difference's interval excludes 0.
- H5.6 Low RVOL. Expansion rate when mean RVOL inside the squeeze < 0.8 vs ≥ 0.8. Rule as H5.5.

## Regime map
For every tool × regime dimension (trend, heat, squeeze, VIX quintile, time of day, day type): "value" if the tool's
primary statistic beats its control in that cell with interval excluding 0 on test (and the same sign on validation
where a validation exists); "no value" if the interval contains 0 with ≥ 200 symbol-days; "not enough data" otherwise.

## Shipping rule
Only PASS items go to Pine: price-scaled elements to pine/volume_zones.pine, strips to pine/volume_zones_pane.pane;
parity on BATS:SPY 5m for every new numeric plot; screenshots; chart restored. Failed items are written up in RESULTS.md
with their numbers and nothing is added "as an option".

## Changes
(none yet)
