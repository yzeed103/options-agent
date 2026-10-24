# One trend-volume model: pre-registration (2026-10-24, before any run)

Prompt: prompts/PROMPT_TREND_VOLUME_MODEL.md. Every volume quantity has a price-only twin; a component ships only
when it beats its twin. Nothing below changes after results are seen; bugs are dated at the end.

## Data
SIP 5m bars (main), 15m (robustness where events fit a session), 30 symbols, regular session, 2025-04 to now. First
60% of days train (quantiles, the constant c, calibration tables), last 40% test. RVOL = slot RVOL (20 sessions).
ATR = Wilder 14. Groups as in reports/eyes/DEFINITIONS.md. Blocks = symbol-days.

## (a) Trend state and strength
- M = HMA(67 on 5m, 66 on 15m) on close (confirming line); D = damped Hull g = 0.85, same length (early line).
- state (trend_volume.trend_state on M): +1 / −1 / 0. **turn confirmed** when D and M slopes agree after a sign change.
- **Inertia** I = |close − close[20]| / Σ|Δclose| over 20 bars (Kaufman efficiency ratio). Friction F = 1 − I.
- **Impulse** J = Σ over the last 10 bars of ((close − open)/ATR) × RVOL; twin **J0** with RVOL = 1.
- **Strength** S = 0.5·I + 0.5·clip(|J|/3, 0, 1); twin **S0** with J0. Signed by the trend state.
- Events: every 5th trend bar (states ±1) in a session. Targets: **alive12 / alive24** = close still on the trend
  side of M 12 / 24 bars later (needs the bars in the session); **fp** = +1 ATR before −1 ATR within 24 bars;
  **life** = bars until the first close beyond M against the trend by 0.3 ATR (censored at the session end, cap 48).
- Metrics: alive12 rate by quintile of S and of S0 (train edges), top-quintile lift, paired lift S vs S0; the same
  for J vs J0; survival curves by S quintile; Brier of the calibrated P(alive12 | state, S quintile) vs base.

## (b) Levels and mass
- Levels as in breakout_volume (swing pivots k = 2, prior-day H / L, POC / VAH / VAL, GEX walls), live from formation
  until the first close beyond.
- **Mass** m(L) = Σ volume of bars whose range came within ±0.1 ATR of L since the level formed, divided by the
  symbol's median bar volume over the previous 20 sessions (same-slot median not needed: a level spans slots). Twin:
  **time** τ(L) = number of such bars.
- **Touch** event: a bar whose high (resistance) or low (support) comes within 0.1 ATR of L without closing beyond it,
  at least 2 bars after the previous touch. Target **respect**: no close beyond L within the next 3 bars.
- Metrics: respect rate by tercile of m and of τ measured at the touch (train edges), paired lift m vs τ; hold rate of
  the eventual break by m tercile vs τ tercile.

## (c) Breaks, activation energy, false breaks, retests
- Break event as in breakout_volume (first close beyond a live level, ≥ 10 bars of age, not in the first 5 bars).
- **Energy** E = (range/ATR) × RVOL of the breaking bar; twin **E0** = range/ATR.
- **Activation energy** E_a = c·m(L), with c the train median of E / m over breaks that held (so "powered" means
  E > E_a; a fixed rule, one constant). Twin rule: E0 above its train 60th percentile.
- Targets: **hold** (no close back across L in 12 bars and ≥ 0.5 ATR beyond at bar 12), **false** (close back across
  within 3 bars), fp within 24 bars.
- Flags at the break bar (each tested alone on the false-break rate, then the combination "absorption or
  counter-trend"): absorption (RVOL > 1.5 and range/ATR < 0.7); wick (the wick beyond L / range > 0.5);
  counter-trend (break against the Hull state); exhausted (I in the bottom train quintile).
- **Retest**: after a break, the first bar within 0.2 ATR of L (same session, within 24 bars) without closing back
  across; target: close stays beyond L for the next 6 bars. Measure: RVOL(retest) / RVOL(break) (lower = "quiet
  retest"); twin: range(retest) / range(break).
- Metrics: hold and false rates by tercile of E vs E0; the rule E > E_a vs the twin rule (hit rates, paired); the
  grid E tercile × m tercile; flag table; retest table (quiet vs loud, paired against small vs big).

## (d) HMM check
Two-state Gaussian HMM (diagonal) on (I, log RVOL), EM on train, Viterbi on test. Reported: agreement of the
"trending" state with |Hull state| = 1, and the Brier of P(alive12) with and without the HMM state added to the
calibration key. Not shipped.

## (e) Calibration
Tables on train: P(alive12 | state, S quintile); P(hold | E tercile, m tercile, direction); P(false | flag set).
On test: reliability diagram per table (predicted vs realized by bin), slope, Brier vs the base rate.

## Planted tests (fresh seeds 50000..50039 for the gate; lower seeds while coding)
Synthetic 5m symbol-years (random walk with range phases, U-shaped persistent volume; prices first, events, then
volume by outcome):
- **Z1 no relation**: volume independent of every outcome. Pass: no volume quantity (J, S, m, E, retest ratio) beats
  its twin (paired lower bound > 0 for none).
- **Z2 planted**: (i) breaks that will hold get the break bar at 2.5× volume with an outcome-dependent probability
  (P(hold | 2.5×) ≈ 0.45 vs 0.25); (ii) levels that will never be broken in the session get the bars near them at
  2× volume (so m is high on respected levels). Pass: E's top-quintile lift recovers ≥ 70% of the planted hold
  lift, m's top-tercile respect lift recovers ≥ 70% of the planted respect lift, and the twins' lifts are unchanged
  between Z1 and Z2 (same prices).

## Verdict rule per component (test days, 5m; 15m as a robustness line)
**ship**: the volume quantity beats its twin (paired interval excludes 0), its own lift interval excludes 1, and the
sign holds in at least two symbol groups. **ship price-only**: the twin's lift interval excludes 1 and the paired
interval includes 0 or is negative. **drop**: neither. Flags ship when the flagged false-break rate exceeds the
unflagged with an interval excluding 0. The calibration tables ship with whatever ships, if their test slope is
within 0.5–1.5 and the Brier beats the base rate.

## Falsifiable statements
H1 J beats J0 on alive12. H2 heavier levels (m) are respected more than long-standing ones (τ). H3 E > E_a separates
holds from false breaks better than E0 alone. H4 absorption + counter-trend is the worst break. H5 a quiet retest
(low volume ratio) holds more than a small retest (low range ratio). H6 the HMM adds nothing to the Hull state.

## Changes after writing
(none yet)
