# PROMPT: One model that reads the trend through volume: trend strength, the levels it builds, their breaks, and false breaks

You are working in `yzeed103/options-agent` (local `C:\project\options-agent`, branch `claude/gracious-johnson-g6tuct`).
Work through every phase without asking me for permission. Commit and push after each phase. No pull requests.
Never show API keys or passwords. Never open `C:\project\gex_radar\.env`. Never inject desktop keystrokes or clicks;
TradingView is reached read-only through the debug port 9222 and the chart is always restored afterwards.

Same discipline as every earlier study (`reports/volume_tool`, `reports/trend_volume`, `reports/breakout_volume`,
`reports/hma_successor`): pre-register before any run, planted tests with a known answer on fresh seeds, train /
test split by days, intervals over symbol-days, a **price-only control for every volume claim**, a verdict by a rule
written before the results, and an honest "this part does not work" per component. Ship only the parts that pass.

## 1. What is already known (read first; build on it, do not redo it)
- **Volume predicts the size of the next move, not its direction** (`reports/volume_tool`): slot-normalized RVOL
  (volume over the median of the same minute in the previous 20 sessions) has IC 0.28 with the next-6-bar range on
  5m; 19 volume tools have continuation IC within ±0.02 of zero. Strong volume persists (log-RVOL autocorrelation
  0.72; a strong run ends with probability 0.59 after one bar, 0.23 after five).
- **Along a trend, volume adds nothing over price** (`reports/trend_volume`): the strong → weak → strong pattern at
  resumptions has lift 1.03; leg life depends on the leg's speed, not its volume.
- **At level breaks, the bar's size does the work** (`reports/breakout_volume`): 12,160 swing breaks on 5m hold 24%;
  big bars 34–35% when volume is also high, 25–30% when not; volume alone is weaker than size (paired −0.21). Half of
  all breaks are false (back across within 3 bars); **absorption bars** (RVOL > 1.5 with range/ATR < 0.7) break
  falsely 65% vs 51%. 15m has too few in-session events; 1h none.
- **The trend line**: HMA matched to a 10-bar lag (67 on 5m) is the calmest at equal lag; the damped Hull (g 0.85)
  turns earlier at reversals (`reports/hma_successor`). Both are in `pine/volume_zones.pine` (v41).
- Code to reuse: `vzones/volume_tool.py` (rvol_set, atr, ic_pooled, lift), `vzones/trend_volume.py` (trend_state,
  paired_lift, first_passage), `vzones/breakout_volume.py` (levels, breaks, targets), `vzones/hma_successor.py`,
  `vzones/assistant/eyes.py` (first-passage framework, groups). Data: SIP only (`VZ_TAG=sip`, 30 symbols, 5m,
  2025-04 to now, regular session). Never per-block Spearman with smoothed series (artifact −0.13 on iid data).

So this is not "find a volume signal". It is: **build one coherent model whose every part is either already measured
or gets measured here, and that tells the trader, per bar, what the trend is, how strong it is, where its levels are,
whether a break is real, and how sure the model is.**

## 2. The model (pre-register the exact formulas; borrow freely, but name the source of each idea)
Think of price as a body moving through a medium. The ideas below are the allowed vocabulary; keep only the ones
that survive. Every quantity is a pure function of past bars; every parameter is either fixed by hypothesis or set
on train days once.

**(a) Trend state and strength: inertia and friction.**
- State from the Hull line M (up / down / range, as in trend_volume.trend_state), with the **damped Hull** as the
  early-turn line and the plain Hull as the confirming line (a turn is "confirmed" when both agree).
- **Inertia** I = Kaufman efficiency ratio over 20 bars (net move / path length): straight trends have high inertia,
  chop has low (Kaufman, 1995). **Friction** F = 1 − I.
- **Impulse** J = Σ over the last 10 bars of (close − open)/ATR × RVOL (physics: impulse = force × time; here force
  is the signed bar body in ATR, time-weighted by relative participation). A price-only twin J0 (RVOL = 1) is the
  control: the claim "volume-weighted impulse reads the trend better" must beat J0.
- **Trend strength** S ∈ [0, 1] = a fixed combination pre-registered as S = 0.5·I + 0.5·clip(|J0| / 3, 0, 1) for the
  price-only version and the same with J for the volume version. Test both; ship whichever predicts the trend's
  remaining life better (survival / hazard as in trend_volume), and say if neither does better than the state alone.

**(b) The levels the trend builds: mass.**
- Swing highs / lows (pivots, k = 2 and 5), prior-day high / low, POC / VAH / VAL, GEX walls, as in breakout_volume.
- **Mass** m(L) = volume traded within ±0.1 ATR of L since the level formed (volume-at-price, Market Profile), in
  units of the symbol's median bar volume. Price-only twin: the number of bars spent within ±0.1 ATR (time at level).
- Claim to test: a level with more mass is respected more (fewer closes through it per touch) and, when broken,
  holds less often (the break needs more energy, see (c)). Control: time at level.

**(c) The break: activation energy and the false break.**
- **Energy** of the breaking bar E = (range/ATR) × RVOL (effort × participation; Wyckoff's effort-vs-result read the
  other way). Price-only twin E0 = range/ATR (already measured: lift 1.42–1.50).
- **Activation energy** of the level E_a = c·m(L) with c set on train; a break is "powered" when E > E_a. Chemistry:
  the reaction happens when the collision carries more than the activation energy. Test whether E > E_a separates
  holds from false breaks better than E0 above its own train quantile (the control).
- **False-break flags** (all pre-registered, each tested alone and together): absorption (RVOL > 1.5, range/ATR
  < 0.7), close back inside within 1 bar, wick ratio (the breaking bar's wick beyond the level / its range > 0.5),
  break against the Hull state (counter-trend break), break on exhausted inertia (I in the bottom quintile).
- **Retest**: after a break, the first return to within 0.2 ATR of L; whether it holds (close stays beyond) and the
  volume on the retest bar vs the break bar (the classic "retest on lower volume" claim: test it against the
  price-only twin "retest with a smaller bar").

**(d) Regime: a two-state hidden Markov model on (I, RVOL run length)** as a statistics-side check of (a): fit on
train (two states, Gaussian emissions on I and log-RVOL), decode on test, report whether the HMM's "trending" state
agrees with the Hull state and whether it adds anything to the remaining-life prediction. Do not ship the HMM; it is
a check.

**(e) Confidence**: every output comes with a probability from a train-calibrated table (not a fitted model):
P(trend continues 12 bars | state, S quintile), P(hold | E tercile, m tercile, direction), P(false break | flags).
Calibration is tested on test days (reliability diagram, slope and intercept, Brier vs base rate).

## 3. Pre-registration (`reports/trend_volume_model/PREREG.md`, committed before any run)
Must contain: the exact formulas and fixed constants of (a)–(e); the targets (trend: remaining life, alive at 12 and
24 bars, first passage ±1 ATR within 2 hours; levels: respect rate per touch, hold rate when broken, false-break rate,
retest hold rate); the price-only twin of every volume quantity; metrics (lift of the top quintile, paired lift
against the twin, hazard / survival, calibration slope and Brier) with bootstrap intervals over symbol-days; groups
and up / down; 5m as the main timeframe, 15m as a robustness line where the events fit in a session; **planted
tests on fresh seeds** (a no-relation world where every volume quantity must fail to beat its twin, and a planted
world where a known effect in E and in m must be recovered ≥ 70% at the pre-registered measurement); the verdict
rule per component: **ship** when the volume quantity beats its price-only twin (paired interval excludes 0) and its
own lift interval excludes 1 on 5m, with the same sign in at least two symbol groups; **ship price-only** when the
twin has the lift and volume adds nothing; **drop** otherwise. Also the falsifiable statements, at least: (H1)
J beats J0 on remaining life; (H2) heavier levels are respected more; (H3) E > E_a separates holds from false breaks
better than bar size alone; (H4) absorption + counter-trend is the worst break; (H5) a retest on lower volume holds
more than a retest on a smaller bar (volume twin vs price twin); (H6) the HMM adds nothing to the Hull state.

## 4. Deliverables
1. `vzones/trend_volume_model.py`: one class `TrendVolumeModel` with `fit(train_frames)` (quantiles, c, calibration
   tables only) and `run(frame) -> DataFrame` with per-bar columns: state, I, J, J0, S, S0, level map (live levels with
   L, type, mass, time), break events with E, E0, E_a, flags, P(hold), P(false), retest outcome; plus the HMM check in
   a separate function. Pure functions of past bars except the targets (prefix test).
2. `tools/trend_volume_model_eval.py planted | verdict` writing `reports/trend_volume_model/*.json`;
   `tests/test_trend_volume_model.py` (prefix, planted plants reproduce, calibration table sums, level mass is
   causal).
3. `reports/trend_volume_model/RESULTS.md`: per-component verdict table (ship / ship price-only / drop), the paired
   tables, survival curves by S quintile, the mass-vs-respect picture, the break grid (E tercile × mass tercile), the
   false-break flag table, the retest table, the reliability diagrams, a real-chart example with state, levels with
   mass, a powered break and a false break marked, and the plain-words answer per component.
4. **Pine, only for shipped components**, into `pine/volume_zones.pine` as one section «نموذج الاتجاه والفوليوم»:
   trend state and strength readout with its calibrated probability, level labels with mass (e.g. «قمة · كتلة 3.2×»),
   a break marker with P(hold) and a false-break warning marker, a retest marker, alerts; Arabic names and tooltips
   with the measured numbers; compile clean (`python tools/pine_check.py pine/volume_zones.pine`), copy to
   `pine/VolumeZones_full.txt`, save with `python tools/tv_pine_test.py --tf 5`, parity ≥ 99.9% of bars / events
   against TradingView's values (note TradingView's BATS volume is ~13% of SIP; parity is on the formula), screenshot
   through the debug port, restore the chart, send me the full file. Price-only components ship with price-only
   formulas and say so in their tooltip.
5. If nothing volume-related ships: say it in the first line, ship the price-only model (state, strength, levels
   with time-at-level, break by size, false-break flags that passed), and write what was learned.

## 5. How to report (Arabic, short, with tables)
One table: component → what it reads → ships / price-only / dropped → the number. The two pictures a trader needs
(the break grid and the survival curves). The best and the worst number. What the model says on today's chart. What
was not verified. Each English term on its own line. Be honest: three studies already showed volume is about size,
not direction; the model's job is to put that to work correctly, not to rediscover a direction signal.
