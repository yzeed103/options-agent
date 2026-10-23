# PROMPT: Find the best volume tool, and measure volume strength and volume persistence, the honest way

You are working in `yzeed103/options-agent` (local `C:\project\options-agent`, branch `claude/gracious-johnson-g6tuct`).
Work through every phase without asking me for permission. Commit and push after each phase. No pull requests.
Never show API keys or passwords. Never open `C:\project\gex_radar\.env`. Never inject desktop keystrokes or clicks;
TradingView is reached read-only through the debug port 9222 and the chart is always restored afterwards.

Do this the same way the moving-average work was done (`reports/conviction_ma`, `reports/hma_successor`): pre-register
before any run, planted tests with a known answer, fresh seeds for the gate, train / test split on real data,
intervals over symbol-days, a verdict by a rule written before the results, and an honest "nothing works" if that is
what the data says.

## 1. Where we stand (read first, do not redo)
- `pine/volume_zones.pine` (v38) already has a volume section: `volMa = ta.sma(volume, 20)`, "weak volume" below
  0.80 × that average, "strong volume" above 1.5 ×, a buy / sell profile (volume split by where the close sits in the
  candle), a heat map of traded volume, HVN zones, POC / VAH / VAL. None of these thresholds was ever measured; they
  are defaults.
- `reports/eyes/DEFINITIONS.md`, `vzones/assistant/eyes.py`: the first-passage framework (did price go x ATR up or
  down within k bars, vs a base rate of the same symbol, timeframe and 30-minute slot), bootstrap over symbol-days,
  symbol groups (index ETFs, mega-caps, high-beta). Reuse it for every "does volume predict anything" question.
- `reports/sip/*` and `tools/source_compare.py`: IEX volume is about 1/29 of SIP volume and signals agree only 19–46%
  of the time between the two feeds. **Use SIP bars only** (`VZ_TAG=sip`, `runtime_sip/bars/<SYM>_5m.csv`, 30
  symbols, 2025-04 to now, regular session).
- `reports/papers_useful.md`: what the literature says about volume (volume–volatility relation, U-shaped intraday
  seasonality, volume clustering). Cite what you use.

## 2. The three questions, each with a measurable answer
1. **Best volume tool**: of the common volume indicators, which one carries the most information about what price
   does next, at equal smoothing?
2. **Volume strength**: a single number per bar, "how strong is this bar's volume", that is comparable across symbols,
   timeframes and times of day, and that actually predicts something (continuation of the bar's direction, range
   expansion, breakout success through a level).
3. **Volume persistence**: given strong volume now, how likely is strong volume to continue, for how many bars, and
   does persistent strong volume predict more than a single strong bar does?

"Best" is never "looks good on a chart". It is: higher information coefficient, higher lift over the base rate, stable
across groups and timeframes, and survives the test period.

## 3. Candidates (pre-register 6–8, say which you dropped and why)
**Normalization first** (every candidate is tested raw and normalized; expect the normalized one to win):
- **RVOL by slot**: volume / median volume of the same symbol in the same 5-minute slot over the last 20 sessions
  (kills the U-shape). Also log-RVOL and a robust z-score (MAD) over the last 20 sessions in the same slot.

**Volume tools** (standard definitions, same source, same data):
- volume / SMA(20) (the indicator's current rule), OBV slope, Accumulation / Distribution, Chaikin Money Flow (20),
  Money Flow Index (14), Force Index (13), Ease of Movement (14), Klinger oscillator, volume-weighted price pressure
  (close position in the candle × volume, "buy minus sell volume" like the indicator's profile), a cumulative-delta
  proxy from that pressure, VWAP distance in ATR, volume rate of change, the volume z-score above, and **volume ×
  range** (effort vs result: high volume with a small range = absorption; high volume with a large range = drive).
- **Volume strength score** (the thing to build): a combination of RVOL, candle-close position and range relative to
  ATR, with weights **fixed by hypothesis before testing**, not fitted. Also a fitted version (logistic on train) only
  to show the ceiling, reported separately and never shipped.
- **Persistence measures**: run length of RVOL above a threshold; autocorrelation of RVOL at lags 1–12; a hazard
  curve (probability the run ends at each length); "persistence score" = expected remaining run length given the
  current run and the current RVOL, from the train hazard curve.

## 4. Pre-registration (`reports/volume_tool/PREREG.md`, committed before any run)
Must contain:
- exact formulas and parameters of every candidate; the normalization; smoothing lengths and how they are matched
  (every tool at the same smoothing in bars, found on train, so no tool wins by being smoother);
- **targets**, defined once: (T1) continuation = sign of the next k-bar return equals the bar's direction, k ∈ {3, 6,
  12}; (T2) range expansion = next 6-bar range > median of the same slot; (T3) first passage = price reaches +1 ATR
  before −1 ATR (and the reverse) within 24 bars, vs the slot base rate; (T4) breakout success = after a close through
  a level (prior-day VAH / VAL, whale lines, CW / PW from the GEX block, POC) price holds 0.5 ATR beyond it for 12 bars;
- **metrics**: information coefficient (Spearman of the measure with the target's continuous form), lift = hit rate
  in the top decile / base rate, calibration slope, and for persistence the hazard curve and the Brier score of the
  persistence score; all with 95% bootstrap intervals over symbol-days;
- **planted tests** (fresh seeds for the gate): (P1) synthetic volume with a U-shaped seasonality and **no** relation to
  returns: every measure must show IC within its noise band, lift ≈ 1 (a measure that "finds" something here is
  broken); (P2) synthetic data where high RVOL raises the probability of continuation by a planted amount (say
  +15 points) and persists with a planted hazard: the strength score must recover ≥ 70% of the planted lift, the
  persistence score must recover the planted hazard within its interval. **If the score fails P1 or P2: fix the
  measurement before touching real data; if it cannot be fixed, stop and say so**;
- **real-data split**: first 60% of days train (thresholds, smoothing match, hazard curve), last 40% test (verdict);
- **verdict rule**: a tool is "useful" when on test data its lift interval on T1 or T3 excludes 1 and its IC interval
  excludes 0 on at least two timeframes and in at least two symbol groups; "descriptive only" when it is stable but
  predicts nothing; "noise" otherwise. The best tool is the useful one with the highest IC at matched smoothing; ties
  go to the simpler formula;
- **falsifiable statements**: (H1) raw volume / SMA(20) is worse than slot-RVOL on every target, because of the
  U-shape; (H2) volume predicts range expansion (T2) much better than direction (T1); (H3) absorption (high volume,
  small range) predicts reversal, drive (high volume, large range) predicts continuation; (H4) volume persistence is
  real (autocorrelation of RVOL at lag 1 > 0.3) but adds little to a single strong bar for T1; (H5) the first 30
  minutes behave differently from the rest of the day and must be reported separately; (H6) the indicator's current
  0.80 / 1.5 thresholds are not where the lift is.

## 5. Deliverables
1. `vzones/volume_tool.py`: normalization, every candidate, the strength score, the persistence score, the targets;
   pure functions of past bars only (prefix test), plus the hazard-curve fit.
2. `tools/volume_tool_eval.py planted | tune | verdict`, writing `reports/volume_tool/*.json`.
3. `tests/test_volume_tool.py`: prefix (no look-ahead), P1 and P2 reproduce, the slot normalization removes a planted
   U-shape, hazard fit recovers a planted hazard.
4. `reports/volume_tool/RESULTS.md`: the ranking table of tools (IC, lift, intervals, per timeframe and group), the
   strength-score calibration plot (predicted vs realized), the hazard curve picture, a chart picture with the score
   painted on real candles (SPY and one high-beta name, 5m), the first-30-minutes split, and a plain-words answer to
   the three questions. Also what was learned if the answer is "nothing predicts".
5. **Pine**, only for what passed as "useful": replace the indicator's volume rule (0.80 / 1.5 × SMA 20) with the
   measured one (slot-RVOL with measured thresholds; a strength score column in the status panel; a persistence
   readout "strong volume for N bars, usually lasts M more"), Arabic names and tooltips stating the measured numbers,
   compile clean (`python tools/pine_check.py pine/volume_zones.pine`), copy to `pine/VolumeZones_full.txt`, save with
   `python tools/tv_pine_test.py --tf 5`, parity ≥ 99.9% of bars within 1e-6 against TradingView's values (note:
   TradingView's SIP volume on the chart may differ from Alpaca SIP bars; measure the volume difference first and
   report it; parity is on the formula given the chart's own volume), screenshot through the debug port, restore the
   chart, send me the full file. Keep the old rule available as an option.
6. If nothing is "useful": keep the indicator as it is, say it plainly, and ship only the normalization (slot-RVOL) as
   the display since it is descriptively better even when it predicts nothing. Say that too.

## 6. How to report (Arabic, short, with tables)
The three questions answered in one line each; the ranking table; the best and the worst number; the recommended
thresholds per timeframe; the first-30-minutes caveat; what was not verified. Each English term on its own line.
Be honest: "volume predicts nothing here" is a result, and a cheaper one than a wrong rule on the chart.
