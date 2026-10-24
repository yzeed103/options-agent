# PROMPT: Does breaking a *significant* swing high or low continue the move? Structure breaks across timeframes, measured against random entries

You are working in `yzeed103/options-agent` (local `C:\project\options-agent`, branch `claude/gracious-johnson-g6tuct`).
Work through every phase without asking me for permission. Commit and push after each phase. No pull requests.
Never show API keys or passwords. Never open `C:\project\gex_radar\.env`. Never inject desktop keystrokes or clicks;
TradingView is reached read-only through the debug port 9222 and the chart is always restored afterwards.

Same discipline as every earlier study (`reports/breakout_volume`, `reports/trend_volume_model`, `reports/eyes`):
pre-register before any run, planted tests on fresh seeds, train / test split by time, intervals over symbol-days (or
symbol-weeks on slow timeframes), a **random-entry control** for every "this predicts continuation" claim, a verdict
by a rule written before the results, and an honest "no" when that is the answer. Ship only what passes.

## 1. What is already known (read first; build on it)
- On **5m with 2-bar pivots** (`reports/breakout_volume`, `reports/trend_volume_model`): 4,085 swing-high breaks on
  test days reached +1 ATR before −1 ATR within two hours **47.6%** of the time, against **49–50%** for any bar;
  52% closed back below the level within 3 bars; 24% held 12 bars. The breaking bar's size lifts the hold rate ×1.4;
  volume adds only inside big bars. So on the fastest timeframe with the smallest swings, a break is not a
  continuation signal. The trader's belief is about **big** swings: levels that stood for days, were touched more
  than once, and sit in a trend. That is what this study measures.
- The random-entry control exists: `vzones/assistant/eyes.py` (first-passage outcomes vs a base rate from all bars
  of the same symbol, timeframe and slot; pseudo-levels drawn at random prices near the real ones). The breakout
  machinery exists: `vzones/breakout_volume.py` (levels, break events, hold / false / first-passage targets),
  `vzones/trend_volume.py` (`first_passage`, `paired_lift`), `vzones/trend_volume_model.py` (Hull state, inertia).
- Data: SIP 5m, 30 symbols, 2025-04 to now (`VZ_TAG=sip`) → 1h, 4h, daily by resampling. For daily and weekly
  swings this is too short (one and a half years), so **extend**: daily bars from Yahoo (`vzones/assistant/data.py`
  `daily_bars` already fetches them) for a pre-registered list of ~200 liquid US stocks and ETFs (the S&P 100, the
  Nasdaq 100 and the 30 SIP symbols; write the list to `reports/structure_break/UNIVERSE.md` before fetching), 2010
  to now, split-adjusted; cache in `runtime_sip/daily_universe/`. Train 2010–2019, validation 2020–2022, **test
  2023–now**; and the 30 SIP symbols 2025–26 as a second out-of-time check on 1h and 4h. Say what Yahoo could not
  deliver.

## 2. Definitions to pre-register (`reports/structure_break/PREREG.md`, committed before any run)
**Timeframes**: 1h and 4h (from SIP 5m, regular session), daily and weekly (universe). ATR = Wilder 14 of the
timeframe's own bars. Levels and events may cross sessions on 1h / 4h (unlike the 5m study); say so.

**Levels (price only)**:
- **swing** high / low with k bars on each side, k ∈ {5, 10, 20} (confirmed k bars later); live until the first close
  beyond; its **age** (bars since the pivot), **touches** (approaches within 0.25 ATR without a close beyond, ≥ 3 bars
  apart), **depth** (the pullback that formed it, in ATR: the distance from the pivot to the extreme of the move away
  from it before the return), and **hold-count** (how many prior closes came within 0.5 ATR and stayed on the near
  side).
- **Donchian** highs / lows: the highest high / lowest low of the last 20 and 55 bars (the turtle rule; Dennis /
  Eckhardt, 1983; Faber / Covel for the evidence), **prior-week high / low**, **prior-month high / low**, **52-week
  high / low** on daily.
- **Significance score** Σ (fixed weights, pre-registered): Σ = ln(1 + age/k) + 0.5·touches + 0.5·min(depth, 4) (and
  k itself as a level class). Price-only twin of Σ for the paired test: the single quantity age alone.
- **Context**: the higher-timeframe Hull state (daily Hull 67-equivalent lag, as in trend_volume_model.trend_state)
  at the break: with-trend / against / none; the market's state (SPY's daily state) as a second context.

**Break event**: the first close beyond a live level; variants pre-registered and all tested: (i) plain close
beyond; (ii) close beyond by ≥ 0.25 ATR; (iii) two consecutive closes beyond; (iv) break + successful retest (first
return within 0.25 ATR that closes on the far side). One event per level; a bar breaking several levels counts the
most significant one.

**Targets** (future only; horizons in bars of the timeframe, N = 24 on 1h, 12 on 4h, 10 on daily, 8 on weekly):
- **FP**: +1 ATR beyond the break close before −1 ATR, within N bars (+1 / −1 / 0); the continuation rate = share
  of +1.
- **FP2**: the same with ±2 ATR within 2N bars (the swing-trader's horizon).
- **hold**: no close back across within N bars and ≥ 0.5 ATR beyond at bar N; **false**: close back across within 3
  bars; **MFE / MAE** within N bars in ATR.
- **trend rule P&L**: enter on the break close, exit at a 2-ATR trailing stop or an opposite break, cost 5 bp per
  side (stocks) / 2 bp (ETFs); report the average R, hit rate, and the equity curve on test, vs the same rule at
  random entries.

**The random-entry control (the whole point)**: for each real break, 20 pseudo-entries at random bars of the same
symbol and timeframe within ±30 bars that are **not** within 3 bars of any break, with the same direction; their FP /
FP2 / hold rates give the base; **excess** = real − pseudo, interval by bootstrap over symbol-weeks. A second control
for direction: the same targets on bars where price merely closed above the prior bar's high (a "micro-break").

**Metrics**: continuation rate and excess over pseudo per timeframe, per level type and k, per Σ quintile, per
context (with / against the daily Hull), per variant (i–iv), up vs down; the paired lift of Σ against age alone; the
trend-rule R; false-break rate; reliability of a train table P(FP | timeframe, level class, Σ quintile, context) on
test.

**Volume, secondary and last**: RVOL of the breaking bar (daily: volume / 20-day median) against the bar's size, the
same paired test as before; the classic "breakout on ≥ 1.5× average volume" rule vs "breakout on a bar ≥ 1.5 ATR".
Report it; do not let it drive anything.

## 3. Planted tests (fresh seeds for the gate: 60000..60039)
Synthetic bars with regimes (trend / range) on each timeframe's scale; the same detector.
- **Y1 no relation**: continuation after a break equals the pseudo-entry rate; Σ, context and the variants must all
  show excess with intervals including 0 (a detector that "finds" continuation here is broken: look for look-ahead
  in the level confirmation).
- **Y2 planted**: after breaks of levels with Σ in the top quintile the next N bars carry a drift of +0.3 ATR / N
  with probability 0.7 (else 0.5). Pass: the top-Σ excess recovers ≥ 70% of the planted excess, pseudo-entries show
  none, and age alone recovers less than Σ.

## 4. Verdict rule (test period)
Per timeframe and level class: **real continuation** when the excess over pseudo-entries has an interval excluding
0 and the continuation rate is ≥ 55% (FP) on at least two timeframes among 1h / 4h / daily / weekly, in both
directions (or one direction with the other not reversed), and the trend rule's average R on test is > 0 after
costs with an interval excluding 0. **weak**: excess excludes 0 on one timeframe or only for one variant / context.
**no**: otherwise. Σ ships only if it beats age alone (paired interval excludes 0); context ships only if with-trend
breaks beat against-trend with an interval excluding 0. Falsifiable statements: (H1) big-swing breaks (k ≥ 10, daily)
continue more than 55% of the time; (H2) continuation rises with Σ; (H3) with-trend breaks continue more than
against-trend; (H4) the retest variant (iv) has the highest continuation and the lowest false rate but the fewest
events; (H5) Donchian 55 / 52-week breaks continue more than swing breaks; (H6) the 5m result (no edge) is a
timeframe effect, not a universal truth: continuation excess grows with the timeframe.

## 5. Deliverables
1. `vzones/structure_break.py`: universe loader, levels of all classes with age / touches / depth / Σ, context,
   events and variants, targets, pseudo-entries, trend rule; past-only except targets (prefix test).
2. `tools/structure_break_eval.py fetch | planted | verdict | pnl`, writing `reports/structure_break/*.json`;
   `tests/test_structure_break.py`.
3. `reports/structure_break/RESULTS.md`: the table timeframe × level class → continuation rate, pseudo rate, excess
   [interval], events; the Σ-quintile picture; the context table; the variant table; the trend-rule equity curves
   (real vs random) on test; the volume paragraph; a real-chart example on daily and on 1h; the plain-words answer:
   "a break of a level that stood X days and was touched Y times continues Z% of the time, against W% at random".
4. **Pine, only on "real continuation"**: in `pine/volume_zones.pine`, a «كسر هيكلي» marker on the breaking bar for
   the level classes that passed, with the measured continuation rate for that timeframe and class in the label, the
   with / against-trend context, and an alert; tooltips carrying the numbers and the timeframes they hold on;
   compile clean, copy to `pine/VolumeZones_full.txt`, save with `python tools/tv_pine_test.py --tf 60`, parity
   ≥ 99.9% of events against TradingView's values on 1h and daily, screenshot through the debug port, restore the
   chart, send me the full file. On "weak": ship nothing, write what a trader would have to accept. On "no": say in
   the first line that significant-swing breaks do not continue beyond chance on the data, and keep the 5m markers
   as they are.

## 6. How to report (Arabic, short, with tables)
First line: the answer to "does breaking a big swing high continue the move?" with the number and the random
baseline next to it. The timeframe × level-class table. The best and the worst number. What the trend rule earned
on test after costs, against random entries. What was not verified (Yahoo gaps, survivorship of the universe, the
short 1h / 4h history). Each English term on its own line. Be honest: the trader's belief gets its fairest test
here (big levels, slow timeframes, 15 years, random-entry control); whatever comes out is the answer.
