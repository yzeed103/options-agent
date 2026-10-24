# Volatility engine v2: results (2026-10-24)

Pre-registered in PREREG.md; planted tests in planted.json (all pass); numbers in verdict.json, regime cells in
regime_map.json; constants that ship in ship.json. 5m: 30 SIP symbols, train = sessions before 2026-03-10, test =
2026-03-10 → 2026-10-22 (4,740 symbol-days). Daily validation 2020–22 where a daily analogue exists. Intervals are
95% bootstrap over symbol-days; "excludes 0" = the paired difference's interval does not contain 0.

## Verdicts

| tool | hypothesis | number (test) | control | verdict | ships |
|---|---|---|---|---|---|
| T1 fan | H1.1 fat tails (train quantiles q16 −0.885, q84 +0.949, q2.5 −2.69, q97.5 +2.85; Student-t df 2.5) | inner 67.4% [66.9, 67.9], outer 94.2%; pinball −0.0008 [−0.0013, −0.0004]; daily 2020–22 66.9% | Gaussian ±1σ 70.4%, ±2σ 89.1% | **FAIL by rule**: passes overall and on daily, but per heat bin the band covers 59% in cold and 77% in extreme (every-cell clause) | no |
| T1 fan | H1.2 asymmetry | q84 + q16 = +0.064 [0.035, 0.095] (down moves are larger); pinball asym − sym −0.00003 [−0.0003, +0.0002] | symmetric band | FAIL (real asymmetry, no loss gain) | no |
| T1 fan | H1.3 intraday seasonality (78-slot variance profile) | QLIKE −0.283 [−0.294, −0.271]; coverage 67.5%. Pooled static profile (what Pine can hold): −0.278 [−0.289, −0.266], coverage 67.2%. Rolling 20-session profile: −0.248 but coverage 73.2% (fails ±3) | plain EWMA | **PASS** (per-symbol and pooled static) | **yes: pooled 78-slot profile** |
| T1 fan | H1.4 horizon law | α = 0.523 [0.519, 0.527] (excludes 0.5); k^α bands better only at k=48 (worse at 6 and 12) | √k | FAIL | no |
| T1 fan | H1.5 event days | coverage 63.9% [62.5, 65.4] on 600 event symbol-days (under-covers); VIX widening (a 0.458, b 0.00176) does not fix it: 63.5% | 68.3 ± 3 | FAIL (events are wider than any VIX-scaled band) | no |
| T4 ladder | H4.1 stop multiple by regime | no cell: best train d differs from 0.75 in 6 of 10 cells but every test difference includes 0 (e.g. cold|up d=1.0: −0.0002 [−0.0004, 0.0]) | fixed 0.75× | FAIL | no |
| T4 ladder | H4.2 structure-aware stop (VAL/VAH/POC/GEX walls) | stop-outs −8.3 points [−8.7, −7.8]; expectancy −0.019% [−0.027, −0.012] per trade | fixed 0.75× | FAIL (fewer stop-outs but it costs expectancy: the wider stop loses more when hit) | no |
| T4 ladder | H4.3 target odds by trend side × S0 quintile | pooled P(1× before stop) 24.7%, P(2×) 8.2%. Passing cells: up & S0 top quintile 30.7% [28.4, 33.1]; up & bottom quintile 20.7% [18.6, 22.9]; down & bottom quintile 20.9% [18.7, 22.9]; down & q2 for 2×: 6.9% [5.7, 8.1] | pooled rate | **PASS (4 cells)** | **yes: per-state odds on the ladder labels** |
| T4 ladder | H4.4 time stop (24 bars vs rest of session) | −0.00006 [−0.0002, +0.00007] | same stop/target, longer hold | FAIL | no |
| T4 ladder | H4.5 trailing stop at 0.75× | +0.032% [+0.018, +0.044] per trade | fixed stop | **PASS** | **yes: trailing line for the current trend** |
| T3 day range | H3.1 fuel 0.8 / 1.0 / 1.2 | reversal lift +0.2 / +1.1 / +1.7 points, all intervals include 0 (n 1,753 / 861 / 404) | random same-slot bars | FAIL | no |
| T3 day range | H3.2 remaining range to the close | empirical g(slot) band covers 69.9% vs √(remaining bars) 84.9%; |err| difference −0.150 [−0.154, −0.147] | √(remaining) | **PASS** | **yes: remaining-move band to the close** |
| T3 day range | H3.3 gap in the first-bar variance | λ = 0.05 (train); QLIKE −0.470 [−0.507, −0.433] over the first 12 bars | λ = 0 | **PASS** | **yes: s2 + 0.05·gap² at the open** |
| T3 day range | H3.4 touch of the day line | back-inside 50.1% vs random 50.7%; lift −0.6 [−2.6, +1.3] | random | FAIL | no |
| T2 exits | H2.1 direction after an exit | signed 6/12/24-bar return − random: −0.0001 / −0.00014 / −0.00005, all include 0; no heat × squeeze cell passes; daily 2020–22 −0.0003 [−0.0014, +0.0008] | matched random bars | FAIL for direction | range-only reading |
| T2 exits | H2.1 range after an exit | R24 − random +0.093% [+0.065, +0.120]; by heat: cold −0.15, mild +0.02, warm +0.09, hot +0.17, extreme +0.39 points of log range | matched random | **PASS (range)** | **yes: tooltip/panel wording** |
| T2 exits | H2.2 exit clustering | ic(count of exits in 24 bars, next range) = −0.241 [−0.254, −0.228] within heat strata | ic > 0 pre-stated | FAIL by rule (a strong NEGATIVE: after a cluster of exits the next range shrinks; exploratory, not shipped) | no |
| T2 exits | H2.3 with-trend vs against-trend exits | continuation 50.6% vs 55.8% [49.5, 62.2] (n 373) | non-overlap | FAIL | no |
| T6 heat | H6.1 normalization | ic with next-24-bar range: same-slot 20-session rank 0.151 [0.139, 0.163]; 500-bar rank −0.036 [−0.050, −0.023]; VIX-conditioned −0.068. Best − others: +0.187, +0.219 (both exclude 0) | each other | **PASS** | **yes: heat = same-slot rank** |
| T6 heat | H6.2 acceleration (Δ heat over 12 bars) | ic 0.084 [0.075, 0.093] within heat strata | 0 | **PASS** | **yes: "accelerating" note** |
| T6 heat | H6.3 intraday vol targeting | Sharpe −7.98 → −11.36 (both negative: the base rule loses); difference −3.39 [−4.38, −2.48] annualized | unsized | FAIL | no |
| T6 heat | H6.4 heat × trend | every bin's expectancy interval contains the pooled −0.088% per trade | pooled | FAIL | no |
| T5 squeeze | H5.1 definitions | expansion within 12 bars minus random: ATR −10.5 [−12.0, −9.0]; Bollinger width −6.8; Keltner-in-BB −2.2; realized-var ratio −4.8 points | random same-slot | all four: calm persists (the baseline finding, confirmed on a new test window) | wording |
| T5 squeeze | H5.2 duration | expansion 37.5% (1–5 bars), 37.7%, 38.9%, 41.8% (>24); slope +0.011/bin [0.001, 0.021] | monotone | **PASS** (rises slowly, stays below random 48.6%) | **yes: duration note** |
| T5 squeeze | H5.3 exit of squeeze | expansion12 −3.4 [−5.2, −1.6], expansion24 −4.6; P(up) 48.7% [47.1, 50.3] | random | expansion: still calm (PASS as a reading); direction FAIL | **yes: "exit ≠ move" wording** |
| T5 squeeze | H5.4 fade breaks inside a squeeze | −0.046% [−0.094, +0.003] per trade (n 3,385); daily 2020–22 −0.67% [−1.42, +0.10] (n 126) | 0 | FAIL | no |
| T5 squeeze | H5.5 lunch squeezes | 33.6% [30.2, 36.8] vs other 39.1% [37.3, 40.9] | non-overlap | **PASS** (lunch squeezes are the calmest) | **yes: lunch note** |
| T5 squeeze | H5.6 low-RVOL squeezes | 31.2% [28.8, 33.6] vs normal 43.0% [40.9, 45.1] | non-overlap | **PASS** | **yes: low-volume note** |

## What the numbers say
- The fan's real defect is **time of day**, not the tail shape: the plain EWMA band covers 60% at the open, 79–87% mid-day
  and 34% in the last 45 minutes (regime map, T1 by tod). The 78-slot variance profile (13× at 09:30, 0.4× at lunch,
  2× into the close) fixes it (QLIKE −0.28, coverage 67%). The fat-tail quantiles help overall but the real residual
  mis-coverage is by heat bin (59% cold, 77% extreme): the band is too narrow in calm and too wide in storms. That is a
  heat-conditioned band, which is not pre-registered and is left for a future study.
- Event days under-cover (64%) and VIX does not explain it.
- The ladder: no stop multiple beats 0.75× in any regime, the structure-aware stop trades fewer stop-outs for worse
  expectancy, the time stop does nothing, the trailing stop earns +0.03% per trade. Target odds move with trend
  strength: 31% for a strong up-state, 21% for the weakest fifth. The base trend rule itself loses −0.09% per trade after
  5 bp costs on the test window: everything in T4 is risk management on top of a rule with no edge.
- Day range: fuel and touches are nothing (50/50). What is real is the decay of the remaining move to the close: it
  is far smaller than √(remaining bars) says (the close is less volatile than the open), and the overnight gap belongs
  in the first-bar variance.
- Exits say nothing about direction, again (5m and daily). They say range: after an exit the next 24-bar range is
  larger, and much larger in hot/extreme heat; and a cluster of exits is followed by a smaller range (negative ic).
- Heat must be normalized by the same time of day: the 500-bar rank is slightly negatively related to the next range
  because the session shape dominates it. Acceleration of heat adds information.
- Squeeze: calm persists under every definition; the calm is deepest at lunch and when volume is low; it only slowly
  fades with duration; leaving the squeeze is not the start of a move; fading breaks inside a squeeze loses.

## Regime map (regime_map.json, regime_map.png)
Value = the tool's statistic beats its control in that cell with an interval excluding 0 (≥ 200 symbol-days).
- T1 fan (plain EWMA, as shipped before this study): value in mild heat, no squeeze, ordinary days, VIX q0/q2/q3,
  trend up/none; NO value at any time-of-day cell (the seasonal profile is the fix), on event days, in cold/extreme heat.
- T2 exits (range): value in almost every cell except cold heat and inside a squeeze.
- T3 fuel: no value anywhere it could be measured.
- T4 ladder (base rule expectancy): no value in any cell (negative everywhere).
- T5 squeeze (calm persists): value in every cell with enough data, strongest in lunch and cold heat; not enough
  data in warm/hot/extreme heat and at the open.
- T6 heat (500-bar rank, the pre-registered definition): value only in hot/extreme heat and by time of day; the
  same-slot rank (H6.1) is the version that works everywhere and ships.
Caveat carried from the planted tests: the Hull "trend" labels are noisy (65% of flat-segment bars carry a state), so
trend cells dilute any trend-conditioned effect toward zero.

## Failed and why (plain list)
H1.1 (heat-dependent coverage), H1.2 (no loss gain), H1.4 (helps only at 48 bars), H1.5 (events wider than VIX says),
H4.1 (no regime-specific stop), H4.2 (wider stop costs more than it saves), H4.4 (nothing), H3.1 (nothing), H3.4
(nothing), H2.1 direction (nothing, 5m and daily), H2.2 (sign opposite to the pre-stated one), H2.3 (overlap), H6.3
(sizing hurts), H6.4 (no bin differs), H5.4 (fade loses).

## Figures
band_heat.png, season.png, remaining_gap.png, ladder.png, exits.png, heat.png, squeeze.png, regime_map.png.
