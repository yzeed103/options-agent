# PROMPT: Invent, build and test a "conviction moving average" for Heikin Ashi candles

## 1. What I want, in my own words
I trade on Heikin Ashi (HA) charts. I want a **new moving average** that behaves the way I read the candles:

- When the market is sideways, the average is calm and flat. It must not chase every small candle.
- When HA candles start printing **in one colour and one direction** (for example red and going down), the average
  should start to **commit** to that direction.
- **Every further candle of the same colour adds points** ("conviction"). The bigger and stronger the candle, the
  more points it adds. A strong red HA candle (big body, no upper wick) adds more than a small red candle with wicks.
- The longer the run lasts, the more points, so the average **locks onto the move** and follows it more closely.
- When the colour **changes**, the average must **not** throw everything away. It loses **some** points (a partial
  drop, a "step down"), not all of them. One opposite candle inside a strong run should only dent the conviction.
  Several opposite candles in a row should drain it, and then build conviction the other way.
- The result must sit **in the middle**: stable enough to ignore noise, responsive enough to follow a real run.
  It should settle ("ثبات"), not flicker.

Invent the formula. Do not just rename an existing average. But you must compare honestly against the existing
ones, and if an existing one already does exactly this, say so.

## 2. Context you must read first
- Repository `yzeed103/options-agent`, branch `claude/gracious-johnson-g6tuct`, local clone `C:\project\options-agent`.
  Never commit to `main`. Commit and push after each phase. No pull requests unless I ask.
- `pine/volume_zones.pine` is my TradingView indicator (Pine v6). It already has:
  - a moving-average section «المتوسطات المتحركة» (four averages, type / source / length / colour, optional higher
    timeframe);
  - Heikin Ashi detection: `chart.is_heikinashi` and `ticker.heikinashi(stdT)` through `request.security`. Copy the
    existing pattern of the trendline section, which reads HA candles automatically on an HA chart;
  - real candles `o_ h_ l_ c_` from `ticker.standard` with the dividend fix.
- After every change to the indicator: `python tools/pine_check.py pine/volume_zones.pine`, copy to
  `pine/VolumeZones_full.txt`, and save to TradingView with `python tools/tv_pine_test.py --tf 5`.
  That tool compiles on TradingView's servers and must report "compiler warnings: none".
- Data for testing:
  - full-market 5-minute bars, `runtime_sip/bars/<SYM>_5m.csv` (30 US stocks and ETFs, April 2025 to now, Alpaca SIP);
  - IEX bars, `runtime/bars/`;
  - daily bars can be built from these.
  Build HA candles from them yourself (ha_close = (o+h+l+c)/4; ha_open = (prev ha_open + prev ha_close)/2,
  seeded with (o+c)/2; ha_high = max(h, ha_open, ha_close); ha_low = min(l, ha_open, ha_close)).
- Existing Python helpers you may reuse: `vzones/assistant/signals.py` (Pine-exact RMA / EMA), and the cluster-bootstrap
  helpers in `vzones/assistant/eyes.py`.
- What we already measured on these stocks (do not repeat it, build on it):
  - no trend-following rule had an edge after 2 bp per side of costs;
  - the autocorrelation of volatility-normalised returns is about zero at 5m and slightly negative at 15m;
  - regular vs HA moving averages differ by only cents.
  So **the goal of this average is reading and stability, not a trading edge**. If your tests show it does give an
  edge, prove it with the held-out discipline below. Do not claim it.

## 3. Hard rules
1. **No lookahead.** The value at bar t uses only bars up to and including t. HA candles are causal by construction.
   Keep them that way.
2. **Deterministic and simple enough for Pine v6.** No machine learning in the final formula. Recursion and `var`
   state are fine. Use at most about 6 parameters, each with a meaning I can read.
3. **Pine and Python must match.** Build a Python reference and the Pine version, and check them against each other
   on TradingView's own bars, as `tools/paper_parity.py` does. The target is at least 99.9% of bars equal within
   1e-6 of the price.
4. **Pre-register.** Write `reports/conviction_ma/PREREG.md` before tuning anything: the metrics, the baselines,
   the data split, the success thresholds, and the parameter ranges you will search. Commit it, then run.
5. **Honest comparison.** Use the same data, the same split and the same metric for every average. Report where
   yours loses.
6. Everything you create goes inside the project folder (`reports/`, `runtime/`), never AppData or the desktop.
   Never show API keys. No Telegram.

## 4. Design guidance (starting points, not the answer)
Think of the average as an adaptive smoother `M_t = M_{t-1} + a_t * (src_t - M_{t-1})`, where the speed `a_t` comes
from a **conviction score** `S_t`:

- **Candle strength** `q_t` of each HA candle, in [0, 1]: body relative to range, body relative to ATR, and the missing
  wick on the "wrong" side. A red HA candle with no upper wick is strong bearish; long wicks on both sides is
  indecision.
- **Direction** `d_t` = +1 green, -1 red. Optionally 0 for a doji below a body threshold.
- **Conviction update.** Same colour as the running side: `S_t = S_{t-1} + gain * q_t`, capped at `S_max`.
  Opposite colour: **partial** loss, for example `S_t = S_{t-1} * keep` with keep in (0, 1), or
  `S_t = S_{t-1} - loss * q_t`. Once S crosses zero, the side flips and conviction starts building the other way.
  Explore at least three update laws (additive, multiplicative decay, leaky integrator) and pick by the tests,
  not by taste.
- **Mapping to speed.** `a_t = a_min + (a_max - a_min) * f(|S_t| / S_max)`, with f an S-curve or power, so low
  conviction means a very slow, flat average and high conviction means it follows closely. `a_min` and `a_max` can
  be expressed as EMA lengths (for example 60 and 8).
- **The "middle" requirement.** Show that one opposite candle in a long run dents the average only slightly, and
  that three to five opposite candles turn it.
- Optional: draw a conviction histogram or colour the average line by |S| (pale = low, deep = high), so I can see the
  points building on the chart.
- Optional source choice: HA close, real close, or HL2. Test whether the average should be fed the HA close (smooth)
  while the conviction comes from the HA candles (shape), or both from HA.

Name the result. Give the final formula in one block of mathematics and one block of plain English.

## 5. Baselines to beat or match (all on the same source and data)
EMA, SMA, Hull (HMA), ALMA, KAMA (Kaufman adaptive), VIDYA, McGinley Dynamic, Ehlers SuperSmoother, Jurik-style JMA
(if you can implement it faithfully; otherwise say so), and a plain "HA-colour streak EMA" (speed by streak length
only, no candle strength), so we know what the candle-strength part adds.

## 6. Tests (pre-registered, on held-out data)
Split by date: first 60% of days to choose parameters, last 40% untouched for the verdict. Report every metric on
both, per timeframe (5m, 15m, 1h, daily) and per symbol group (index ETFs, mega-caps, high-beta).

1. **Planted-trend test.** Synthetic prices: a sideways segment, then a clean trend, then noise, then a reversal,
   with known change points and a known noise level. Measure:
   - delay to commit after a trend starts (bars until the average's slope has the trend's sign, held for N bars);
   - false commitments in the sideways segment (slope sign flips per 100 bars);
   - delay to turn after the reversal;
   - how much a single opposite candle moves the average inside a trend (should be small).
   It must clearly beat EMA of comparable smoothness on "fewer false flips at equal lag". If it does not, the idea
   fails. Say so and stop.
2. **Pure-noise test.** Random walk: the average must not "commit" more often than the baselines.
3. **Real-data smoothness vs lag.** For each average, plot noise (mean absolute second difference, or residual
   variance against a centred reference filter) against lag (cross-correlation peak with the price). The trade-off
   curve is the result. Show where the new average sits relative to all baselines.
4. **Whipsaw count.** Price-crosses-average events per day and average slope flips per day, at matched lag.
5. **Trend-segment capture.** Mark trends on held-out data with a lookahead labeller (allowed for **evaluation
   only**, never as an input), then measure the share of each trend the average was committed to, and the share of
   sideways time it falsely committed.
6. **Optional trading check (honest).** A plain rule: long when the average turns up with conviction above a
   threshold, flat or short when it turns down. 2 bp per side, entry on the next bar's open. Report against the same
   rule on EMA and KAMA. Expect no edge. Report the numbers either way.
7. **Parameter robustness.** Heat maps of the main metric over the two most important parameters. A good design
   has a broad plateau, not a single sharp peak.
8. **Parity.** Python vs Pine on TradingView's own bars, at least 3 symbols on 5m and 15m, HA chart and regular
   chart. Use `tools/paper_parity.py` as the pattern: temporary copy, read the plot series, restore the chart. Never
   send keystrokes or clicks.

## 7. Deliverables
- `vzones/conviction_ma.py`: Python reference (vectorised where possible, a loop where the recursion needs it),
  with docstrings giving the formula.
- `tests/test_conviction_ma.py`: planted-trend, noise, no-lookahead (a prefix gives the same values) and
  parameter-bounds tests. All must pass.
- `reports/conviction_ma/PREREG.md` (committed before tuning), `RESULTS.md` (every table above, with intervals),
  pictures in `reports/conviction_ma/`:
  - the lag/noise frontier;
  - planted-trend plots with all averages;
  - a real HA chart of MSFT and SPY on 5m and 15m with the new average coloured by conviction;
  - parameter heat maps.
- **Indicator integration** in `pine/volume_zones.pine`:
  - a new type «متوسط الثبات (هيكين آشي)» selectable in each of the four averages, or a dedicated fifth line;
  - Arabic input names with ⓘ tooltips;
  - automatic HA reading on an HA chart, and an option to force HA or real candles, like the trendlines;
  - optional colouring by conviction;
  - compiled on TradingView with no warnings, `VolumeZones_full.txt` in sync, and a real screenshot taken through
    the debug port. Restore the chart afterwards.
- A short Arabic summary for me:
  - what the formula does, in simple words;
  - the single best and single worst number against the baselines;
  - the recommended settings;
  - what was **not** verified.

## 8. What "done" means
Every test above has been run and reported with numbers, including the ones the new average loses. Parity is at
least 99.9%. The indicator compiles clean and shows the average on a real chart. And there is a clear verdict:
- **better:** state on which metric and by how much;
- **equal:** say which existing average already does this;
- **worse:** say so plainly.

Work through every phase without asking me for permission. Stop only if something would break a hard rule.
