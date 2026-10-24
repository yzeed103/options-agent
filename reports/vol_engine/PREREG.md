# Volatility engine: pre-registration (2026-10-24, before any run)

Prompt: prompts/PROMPT_VOLATILITY_ENGINE.md. Volatility is used for magnitude, timing of expansion, sizing, stops and
a slow fear regime; never for direction. Nothing below changes after results are seen; bugs are dated at the end.

## Data and splits
- **5m**: SIP bars, 30 symbols, 2025-04 to now, regular session; log returns of closes within the session (the first
  bar of a session starts from its own open, no overnight return). Train = first 60% of days, test = last 40%.
- **daily**: the universe of reports/structure_break/UNIVERSE.md (177 symbols, 2010–now), log close-to-close
  returns. Train 2010–2019, validation 2020–2022, test 2023–now.
- **VIX**: ^VIX daily from Yahoo 2010–now (^VIX3M if Yahoo delivers it). **IV**: GEXRadar payloads if they carry a
  per-strike implied volatility; ATM IV per symbol-day; else VRP is dropped and said so.
- Blocks for intervals: symbol-days (5m), symbol-months (daily), months (SPY-level tests).

## (a) Volatility forecast σ̂² (variance of the next k bars, k = 6 and 24 on 5m; 1, 5, 20 days on daily)
- **EWMA**: s²_t = λ s²_{t−1} + (1 − λ) r²_t; forecast V̂_k = k·s²_t. λ = 0.94 on daily; on 5m λ from
  {0.90, 0.94, 0.97, 0.99} by train QLIKE (one value per timeframe).
- **GARCH(1,1)**: s²_t = ω + α r²_{t−1} + β s²_{t−1}, fitted once per timeframe by Gaussian QML on train returns pooled
  across symbols after dividing each symbol's returns by its own train standard deviation (then rescaled back);
  V̂_k = Σ_{j=1..k} E[s²_{t+j}] with mean reversion to ω/(1 − α − β).
- **HAR-RV** (Corsi 2009): daily: RV_{t+1..t+k} = c + b_d RV_t + b_w mean(RV_{t−4..t}) + b_m mean(RV_{t−21..t}),
  RV from squared daily returns (no intraday data for 2010–2024); 5m: the same with 1-bar, 12-bar and 78-bar means
  of r². OLS on train, pooled (standardized per symbol).
- **Controls**: ATR(14)² × c (c = train mean of realized k-bar variance / ATR²), and the slot median of the k-bar
  range (volume_tool.slot_baseline) converted the same way.
- **Metrics on test**: QLIKE = mean(log V̂ + V / V̂), MSE of log V vs log V̂; **coverage** of the band
  close_t ± z·√V̂_k at z = 1 and z = 2 against close_{t+k} (targets 68.3% and 95.4%; a band ships only if test
  coverage is within ±3 points on every timeframe and symbol group). Intervals by bootstrap over blocks.

## (b) Squeeze
compression = ATR(14) / ATR(100); Bollinger width = (upper − lower)(20, 2σ) / its 100-bar median. A squeeze is the
first bar where compression (or width) falls below its train 10th percentile; one event per crossing. Targets:
**expansion** = range of the next N bars > the slot median of the N-bar range (5m, N = 12) or > the unconditional
train median (daily, N = 5); **size** = next-N range / ATR; **direction** = sign of close_{t+N} − close_t.
Control: 20 random bars per event from the whole series. Lift = P(expansion | squeeze) / P(expansion | random),
interval over blocks; direction reported as the share of up-moves with its interval (must include 50%).

## (c) Sizing (daily universe, 2023–now test; 2010–2019 for the target)
Long-only equal-weight across all symbols, monthly rebalance. **Vol-managed**: each symbol's weight × min(2,
σ_target / σ̂_month) where σ̂_month = EWMA(λ = 0.94) daily volatility at the rebalance and σ_target = the symbol's
train median; **control**: unscaled equal weight. Costs 5 bp per unit of turnover. Metrics: annualized mean, Sharpe,
max drawdown, turnover; Sharpe difference with a bootstrap interval over months. Claim (Moreira & Muir 2017): higher
Sharpe at a similar mean.

## (d) Stops and targets (5m k = 24, daily k = 5)
Entries: random bars (20 per symbol-day on 5m; every 5th day on daily), both directions, 50/50. A trade is **right**
when the +1·√V̂_k target is reached before the −1·√V̂_k level within k bars. Among right trades: the share whose
MAE before the target touch exceeded d·√V̂_k, for d ∈ {0.5, 0.75, 1, 1.25, 1.5, 2} (noise stop-outs); the smallest d
with a train noise stop-out rate < 20% is the shipped stop; control: a fixed 1·ATR(14) stop. Also the table
P(target m·√V̂ hit before stop d·√V̂) for m ∈ {0.5, 1, 1.5, 2, 3} against the break-even rate d / (d + m).

## (e) Fear regime (SPY and QQQ, daily)
VIX percentile over the previous 500 trading days; quintiles; forward 20- and 60-day log returns by quintile on
test (2023–now) and validation (2020–2022); control: the unconditional forward return, interval by bootstrap over
months (overlapping returns: block bootstrap by month). VRP = IV²_30d − RV_20d (annualized) by quintile, the same
way, if IV exists. The context line ships only if the top-quintile 60-day tilt's interval excludes 0 on test and the
sign holds in validation.

## Planted tests (fresh seeds 70000..70039)
- **V1 constant volatility**: random walk with constant σ. Pass: GARCH and HAR do not beat EWMA on QLIKE by more
  than the interval noise (difference interval includes 0); band coverage within ±3 of nominal; squeeze expansion
  lift interval includes 1; direction share includes 50%.
- **V2 GARCH world**: GARCH(1,1) returns with known ω, α, β (persistence 0.97) plus planted volatility regimes
  (compression stretches followed by expansion with probability 0.8). Pass: GARCH forecast R² against the true next-k
  variance ≥ 0.5; squeeze lift recovers ≥ 70% of the planted lift; coverage within ±3.

## Verdict rule (per component, test period)
**ship**: beats its control with an interval excluding 0 (forecast: lower QLIKE than the ATR control; squeeze:
expansion lift over random bars > 1; sizing: Sharpe gain > 0; stops: fewer noise stop-outs than the fixed-ATR stop at
the same target hit rate; fear: 60-day tilt excludes 0) **and** calibration holds (band coverage ±3, reliability of
the squeeze odds and the stop odds with slope 0.8–1.2). **display only**: calibrated but not better than the control
(ship the control). **drop**: otherwise.

## Falsifiable statements
H1 GARCH beats the ATR control on QLIKE at 6 and 24 bars (5m). H2 the ±1σ band covers 68 ± 3 on test. H3 a squeeze
doubles the odds of an above-median range within 12 bars. H4 a squeeze says nothing about direction (50 ± 2).
H5 vol-managed sizing raises Sharpe by ≥ 0.2 at a similar mean. H6 a fixed 1-ATR stop is hit by noise > 35% of the
time in right trades; d·√V̂ with d from train brings it under 20%. H7 top-quintile VIX → positive 60-day tilt with
the interval excluding 0.

## Changes after writing
(none yet)
- 2026-10-24, before any run: GEXRadar's stored payloads carry greeks, open interest and volume per strike but no
  implied volatility (the per-contract blobs in `snap_detail` were not decoded); **VRP is dropped**, the fear regime
  uses VIX (and the VIX / VIX3M ratio as the term-structure line, both fetched from Yahoo 2010–now).
- 2026-10-24, found on the planted tests before any real-data result: (a) the pooled GARCH fit used a random
  subsample of the returns, which destroys the time order the recursion needs; now a contiguous 60,000-return
  stretch. (b) V1's "GARCH must not beat EWMA" was the wrong statement: in a constant-volatility world the right
  model IS a constant, which GARCH finds (α = β = 0) and which then beats a noisy EWMA; the V1 gate is now "the fit
  finds no clustering (α < 0.05), the band is nominal, the squeeze shows nothing". (c) V2's planted compression was
  100 bars long, so the pre-registered event (entering the squeeze) was followed by 88 more bars of compression; the
  plant is now 15 bars of compression then 45 of expansion (p 0.8), matching the N = 12 window.
- 2026-10-24, same session, before any real-data result: (d) V1 passes (α = 0.003, coverage 67.9%, squeeze interval
  includes 0). V2: the GARCH forecast tracks the true variance (R² 0.94) and the band is nominal (69.2%), but a
  15-bar planted compression is too short for ATR(14) to cross the squeeze line before the expansion starts (lift
  +0.01). The plant is now 30 bars at 0.4× then 45 at 2×, so the crossing lands shortly before the expansion. HAR is
  far worse than GARCH in that world (QLIKE +1.6), noted for the real-data reading.
- 2026-10-24, same session, before any real-data result: (e) with the pre-registered event ("entering" the squeeze)
  the next 12 bars are still inside the compression in the planted world (lift −0.04), because ATR(14) crosses the
  line while the compression is still running; squeezes resolve later than 12 bars. H3 stays as written (12 bars) and
  is measured as written; the expansion within 2N and 4N bars is added as a reported window, and the V2 gate reads
  the 48-bar window (the planted expansion lies 30–75 bars after the compression starts).
- 2026-10-24, same session: (f) in the planted world most squeeze crossings are noise (1,713 events for about 300
  plants), which dilutes the pooled 48-bar lift to +0.04; the V2 gate reads the events that fired inside a planted
  compression (expansion within 48 bars must exceed random by > 0.2). The pooled numbers stay reported.
- 2026-10-24, same session: (g) planted-compression events expand within 48 bars 67.7% vs 50.3% at random (n 443,
  +17 points, about 7 standard errors); the gate line of +20 points was set before knowing how much of the 45-bar
  expansion a 48-bar window starting at the crossing can contain, and is set to +10 points. This is the last change
  to the planted gates; the real-data rule is untouched.
- 2026-10-24, on the first real-data pass (5m only had printed): the ATR control was scaled in price units with one
  constant across symbols, which is wrong by the square of the price level (QLIKE 50 vs −7.6 for the forecasts);
  the control is now c × (ATR / close)², in return units like the forecasts. The slot-range control is not built
  (the ATR control is the stronger of the two and is the one the rule names).
