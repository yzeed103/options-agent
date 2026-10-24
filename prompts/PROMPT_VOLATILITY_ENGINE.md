# PROMPT: Put volatility to work in the indicator: expected move, squeeze, sizing, stops, and the fear regime, each calibrated and measured

You are working in `yzeed103/options-agent` (local `C:\project\options-agent`, branch `claude/gracious-johnson-g6tuct`).
Work through every phase without asking me for permission. Commit and push after each phase. No pull requests.
Never show API keys or passwords. Never open `C:\project\gex_radar\.env`. Never inject desktop keystrokes or clicks;
TradingView is reached read-only through the debug port 9222 and the chart is always restored afterwards.

Same discipline as every earlier study (`reports/volume_tool`, `reports/trend_volume_model`, `reports/structure_break`):
pre-register before any run, planted tests on fresh seeds, train / test split by time, intervals over symbol-days,
a control for every claim, a verdict by a rule written before the results, and an honest "this part does not work".
Ship only what passes.

## 1. The premise (measured, not assumed)
Volatility predicts **how much** price moves, not **where**: slot RVOL has IC 0.28 with the next-6-bar range and 0.00
with direction (`reports/volume_tool`); strong straight moves live 3–6 bars and die by 12–24 (`reports/trend_volume_
model`); breaks of any level continue 49% vs 49% at random (`reports/structure_break`). So volatility is used here
for the four things it is good for, plus one regime readout, and **never for direction**:
1. **expected move**: how far price is likely to travel in the next k bars (a calibrated band);
2. **squeeze**: when the range has compressed, how likely an expansion is within N bars, and how large;
3. **sizing**: how much to trade so that risk per trade stays constant when volatility changes (Moreira & Muir 2017);
4. **stops and targets**: where a stop has to sit so that noise alone does not hit it;
5. **fear regime** (index level, slow): VIX percentile and the variance risk premium as a context line with the
   measured forward tilt (Bollerslev, Tauchen & Zhou 2009), for the daily chart, never as a signal.

Reuse: `vzones/volume_tool.py` (rvol_set, atr, lift, ic_pooled), `vzones/assistant/data.py` (`vix_prev_close`,
`gex_levels_full`: check whether GEXRadar's stored payloads carry implied volatility per strike; if they do, build
an ATM IV series per symbol-day; if not, say so and drop VRP), the daily universe `runtime_sip/daily_universe/`
(177 symbols 2010–now), SIP 5m bars (`VZ_TAG=sip`, 30 symbols). Pine: `pine/volume_zones.pine` (v43) already has
slot RVOL and `atrV`.

## 2. Components to pre-register (exact formulas; borrow and cite)
**(a) Volatility forecast σ̂** per bar, three candidates, each a pure function of past bars:
- EWMA (RiskMetrics λ = 0.94 daily; on 5m λ set on train) of squared log returns;
- **GARCH(1,1)** with parameters fitted once on train per timeframe (not per symbol);
- **HAR-RV** (Corsi 2009): realized variance regressed on its daily, weekly, monthly means, fitted on train.
Price-only controls: the plain ATR(14) and the slot baseline of the range (the volume-tool median). Metric: QLIKE and
MSE of the next-k-bar realized range / variance on test (k = 6 and 24 bars on 5m; 1, 5, 20 days on daily), plus the
**coverage** of the expected-move band ±z·σ̂·√k at z = 1 and 2 (target 68% / 95%): a band is shipped only if its
test coverage is within ±3 points of the target on every timeframe and group.

**(b) Squeeze**: compression = ATR(14) / ATR(100) (and Bollinger width / its 100-bar median) below its train 10th
percentile (Bollinger's squeeze; the NR7 idea for the daily version). Claims: P(range of the next N bars > median of
the slot) is higher after a squeeze (lift over the unconditional base and over a **control of random bars**), the
expansion's size (next-N range / ATR) is larger, and **direction is 50/50** (state it, test it, show it). N = 12 on
5m, 5 days on daily.

**(c) Sizing**: units = (target risk per trade) / (σ̂·√k·price); the vol-managed test: a long-only daily portfolio of
the universe scaled by (target σ / σ̂) with monthly rebalancing vs the same unscaled, 2023–now, Sharpe, max drawdown,
turnover, costs 5 bp; Moreira–Muir's claim is a higher Sharpe at the same mean return. Control: constant sizing.

**(d) Stops**: the probability that a stop at d·σ̂·√k is hit by noise within k bars when the trade is right (the
"right" cases = the +1 first-passage cases); the d at which noise stop-outs fall below 20% on test, per timeframe;
vs a fixed-ATR stop (1 ATR) as the control. Also the target multiple whose hit rate matches its implied odds
(calibrated R:R).

**(e) Fear regime** (daily, SPY and QQQ only): VIX percentile over 2 years (we have VIX from 2025-04 only in
`vix_prev_close`; fetch ^VIX daily from Yahoo for 2010–now and ^VIX3M if available for the term structure); VRP =
IV²_30d − realized variance (20 days) when IV is available. Claims: forward 20- and 60-day SPY returns by VIX
quintile and by VRP quintile, with a **random-date control** (bootstrap over months); the "top quintile of fear →
positive forward tilt" statement ships as a context line only if its interval excludes 0 on test (2023–now) and the
sign holds in validation (2020–2022).

## 3. Planted tests (fresh seeds 70000..70039)
- **V1 constant volatility world**: a random walk with constant σ; GARCH / HAR must not "find" clustering (their
  forecasts must not beat EWMA by more than noise), the squeeze must show no expansion lift, the band coverage must
  equal the nominal.
- **V2 GARCH world** with known parameters and a planted squeeze–expansion structure (volatility regimes with
  transitions): the forecast must recover the true next-k variance with R² ≥ 0.5, the squeeze lift must recover ≥ 70%
  of the planted lift, and the band coverage must be within ±3 points.

## 4. Verdict rule (per component, test period)
**ship**: the component's pre-registered metric beats its control with an interval excluding 0 (forecast: lower
QLIKE than ATR; squeeze: expansion lift over random bars; sizing: higher Sharpe at equal mean; stops: fewer noise
stop-outs at equal R; fear: forward tilt interval excludes 0) **and** its calibration holds on test (coverage ±3
points, reliability slope 0.8–1.2). **ship as display only**: calibrated but no better than the control (then the
control is shipped, simpler). **drop**: otherwise. Falsifiable statements: (H1) GARCH beats ATR on QLIKE at 6 and 24
bars on 5m; (H2) the ±1σ band covers 68% ± 3 on test; (H3) a squeeze doubles the chance of an above-median range
within 12 bars; (H4) a squeeze says nothing about direction (50 ± 2%); (H5) vol-managed sizing raises Sharpe by ≥ 0.2
at the same mean; (H6) a 1-ATR stop is hit by noise > 35% of the time when the trade is right, and d·σ̂·√k with d
chosen on train brings it under 20%; (H7) top-quintile VIX → positive 60-day tilt with the interval excluding 0.

## 5. Deliverables
1. `vzones/vol_engine.py`: forecasts (EWMA, GARCH, HAR), bands, squeeze, sizing, stop odds, VIX / VRP series; pure
   functions of past bars except the targets (prefix test); `tests/test_vol_engine.py`.
2. `tools/vol_engine_eval.py fetch | planted | verdict | portfolio`, writing `reports/vol_engine/*.json`.
3. `reports/vol_engine/RESULTS.md`: the forecast table (QLIKE / MSE / coverage per timeframe), the squeeze table
   (lift, size, direction), the sizing table (Sharpe, drawdown, turnover, cost), the stop table (d vs noise stop-out
   rate), the fear table (forward returns by quintile vs random dates), the pictures (band on a real chart with the
   realized path; squeeze → expansion example; the two equity curves; the stop-out curve; the VIX quintile bars),
   and the plain-words answer per component.
4. **Pine, for shipped components**, one section «محرّك التذبذب»: the expected-move band for the next k bars
   (dashed, with "68% من الحالات تبقى داخله" in the tooltip and the measured coverage), a squeeze marker with the
   measured expansion odds and the explicit "الاتجاه 50/50", a status-panel line «التذبذب»: σ̂, expected move in
   points and %, the suggested size multiplier for a user-set risk (input «مخاطرة الصفقة %»), the noise-proof stop
   distance and the calibrated target, and on the daily chart the fear-regime line (VIX percentile and the measured
   tilt) — all with Arabic names and tooltips carrying the numbers; compile clean
   (`python tools/pine_check.py pine/volume_zones.pine`), copy to `pine/VolumeZones_full.txt`, save with
   `python tools/tv_pine_test.py --tf 5`, parity ≥ 99.9% of bars on σ̂ and the band against TradingView's values (the
   GARCH recursion in Pine with the train parameters; HAR needs daily aggregates, so ship it only if it can be
   computed in Pine from the chart's own bars, else ship GARCH or EWMA), screenshot through the debug port, restore
   the chart, send me the full file. Alerts: squeeze on, band touched.
5. If a component fails, say so in its line and ship the control instead (the ATR band is still useful if it is the
   best calibrated one).

## 6. How to report (Arabic, short, with tables)
One table: component → what it does for the trader → ships / control / dropped → the number. The chart pictures. The
best and the worst number. What the panel line would say right now on SPY. What was not verified (IV availability,
VIX history, survivorship). Each English term on its own line. Be plain: this engine tells the trader how far, how
likely to expand, how much to size, and where the stop survives noise; it does not and will not tell the direction.
