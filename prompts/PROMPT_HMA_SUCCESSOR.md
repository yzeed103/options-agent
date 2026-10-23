# PROMPT: Improve the Hull moving average for Heikin Ashi charts, or build something that beats it

You are working in `yzeed103/options-agent` (local `C:\project\options-agent`, branch `claude/gracious-johnson-g6tuct`).
Work through every phase without asking me for permission. Commit and push after each phase. No pull requests.
Never show API keys or passwords. Never open `C:\project\gex_radar\.env`. Never inject desktop keystrokes or clicks;
TradingView is reached read-only through the debug port 9222 and the chart is always restored afterwards.

## 1. Where we stand (read these first, do not redo them)

- `reports/conviction_ma/RESULTS.md` and `RESULTS_STREAK.md`: two of our own ideas for a Heikin Ashi average
  ("conviction" speed from candle strength; speed from colour-streak length) were pre-registered, tested and **failed**
  on real data. Do not revive them.
- `reports/conviction_ma/streak_verdict_trend.json` and `averages_side_by_side.png`: at **equal lag in trends**
  (~10 bars), on 30 SIP symbols, test days only, the **Hull moving average (HMA)** had the fewest direction flips and
  the lowest noise on 5m, 15m, 1h and daily. Runner-ups: Ehlers SuperSmoother and ALMA. HMA(68) is now "average 2" in
  `pine/volume_zones.pine` (v35).
- `vzones/conviction_ma.py`: reference implementations of EMA, SMA, WMA, HMA, ALMA, KAMA, VIDYA, McGinley,
  SuperSmoother, Heikin Ashi, Wilder ATR, and the metrics (`flips`, `noise`, `whipsaws`, `commit_dir`,
  `trend_labels`, `lag_drift`). `tools/streak_verdict.py`: the matched-lag comparison on real data (5m/15m/1h/daily,
  train 60% of days, test 40%, bootstrap intervals over symbol-days, two lag definitions). Reuse both.
- Data: `runtime_sip/bars/<SYM>_5m.csv` (set `VZ_TAG=sip`), 30 symbols, 2025-04 to now, regular session.

## 2. What HMA is, and why it wins and where it loses

HMA(n) = WMA( 2·WMA(n/2) − WMA(n), √n ). The inner difference extrapolates the trend (it has **negative weights** on
old prices), the outer short WMA smooths the result. That is why in a steady trend it sits almost on the price with
little lag (low flips, low noise at equal lag). The same negative weights are its weakness: at a **reversal it keeps
going, overshoots, then bends back late**. We saw this in `averages_side_by_side.png` (SPY 10-07: HMA kept falling to
773 while price had already turned up). So the target is clear:

> Keep HMA's calm in trends, remove its overshoot and late turn at reversals, without adding lag elsewhere.

## 3. Candidate ideas (test several; rank them; you may add your own)

**A. Overshoot control on HMA itself**
1. *Clamped HMA*: never let M leave the range [min, max] of the last k HA candles (k ≈ √n). Overshoot is cut
   mechanically; measure what it costs in trend.
2. *Damped difference*: HMA with `2·WMA(n/2) − g·WMA(n)` and g in [0.7, 1.0], or with the inner difference capped at
   c·ATR. g = 1 is the standard HMA; smaller g = less extrapolation, less overshoot, more lag. Find the knee.
3. *Reversal-gated HMA*: when a reversal is detected (HA colour flips and holds 2–3 candles, or price crosses M), switch
   the inner extrapolation off for a few bars (blend to EMA or SuperSmoother of the same lag), then back.
4. *HMA on a less laggy source*: real close instead of HA close (HA adds its own ~1 bar of lag), and HA (open+close)/2.

**B. Other zero-lag families with a controllable overshoot** (same matched-lag protocol)
5. Ehlers **zero-lag EMA with error correction** (ZLEMA with gain limit), his **Instantaneous Trendline**, and
   **roofing filter + SuperSmoother**.
6. **T3** (Tillson, volume factor 0.7) and **Laguerre** filter (gamma 0.5–0.8).
7. **FRAMA** (fractal adaptive) and **MAMA/FAMA** (MESA adaptive): lag adapts to the dominant cycle.
8. **Holt's double exponential smoothing** (level + slope, with slope damping phi in [0.8, 1.0]): a principled
   "trend-following with brakes"; the damping parameter directly controls overshoot.
9. A **causal Savitzky–Golay** (local polynomial of degree 2) and a **local linear Kalman** filter with a measurement
   noise set from ATR.

**C. Combinations**
10. *Median of three*: median of HMA, SuperSmoother and ALMA at matched lag; the median kills the single filter's
    overshoot while keeping the common trend.
11. *Regime blend*: HMA weight w from an efficiency ratio (Kaufman's ER over n bars): w = ER^p; (1 − w) goes to
    SuperSmoother. Trend → HMA; chop → smoother.

Exclude Jurik JMA (proprietary) and anything that uses the future.

## 4. Hypotheses to write down before testing (pre-registration)

Write `reports/hma_successor/PREREG.md` **before** any run, and commit it. It must contain:
- the exact formulas and parameters of every candidate (3–6 candidates at most; say which you dropped and why);
- the metrics, defined once: flips per 100 bars, noise (mean |Δ²M| / mean |ΔP|), whipsaws per session,
  **reversal overshoot** (after a labelled trend reversal: max distance M travels past the turning price, in ATR) and
  **turn delay** (bars from the labelled reversal until M's slope changes sign), trend capture / false commit, and the
  trading check (long when M turns up, short when it turns down, 2 bp per side, next-bar open) vs HMA(68);
- lag matching: compare at **equal lag in trends** (the fair measure, `streak_verdict.py --lag trend`); report the
  drift lag only as a caveat;
- the gate: a planted series with **V-shaped reversals** (fresh seeds, never looked at before the gate) where the
  candidate must cut HMA's overshoot by ≥ 30% with turn delay not worse than HMA + 1 bar and sideways flips not worse
  than HMA + 10%, interval excluding zero. **If no candidate passes, say so and stop**;
- real-data verdict rules: on test days, at matched lag, "better" = beats HMA on overshoot **and** not worse on flips
  and noise (intervals), per timeframe; "equal" and "worse" as in `reports/conviction_ma/PREREG.md`;
- a heat map of the main parameter (g, phi, gamma or k) × lag, so the result is shown to be a plateau, not a spike.

Falsifiable statements to include (write them, then test them):
- H1: overshoot is caused by the negative weights; a damped difference (g < 1) reduces it monotonically.
- H2: a clamp to the recent candle range removes most overshoot at a cost of < 0.5 bar of trend lag.
- H3: Holt with damping phi ≈ 0.9 matches HMA's trend lag with less overshoot.
- H4: the median of three beats every single member on overshoot without losing on noise.
- H5: the gain holds on every timeframe and symbol group (index ETFs, mega-caps, high-beta), not only on 5m.

## 5. Deliverables

1. `vzones/hma_successor.py`: the candidates, pure functions `f(o, h, l, c, **params) -> M`, no look-ahead
   (prefix test: `f(x[:k]) == f(x)[:k]`), plus the two new metrics.
2. `tools/hma_successor_eval.py planted | tune | verdict`, writing `reports/hma_successor/*.json`.
3. `tests/test_hma_successor.py`: prefix (no look-ahead), bounds, planted gate reproduces, parity data.
4. `reports/hma_successor/RESULTS.md` with the tables (per timeframe, per group, intervals), the heat map, a
   side-by-side picture like `averages_side_by_side.png` with the winner added, and a reversal close-up picture.
5. Only if a candidate is "better" or "equal" on all four timeframes: add it to `pine/volume_zones.pine` as a new
   moving-average type (Arabic name, tooltip stating the measured numbers), compile clean
   (`python tools/pine_check.py pine/volume_zones.pine`), copy to `pine/VolumeZones_full.txt`, save with
   `python tools/tv_pine_test.py --tf 5`, prove parity ≥ 99.9% of bars within 1e-6 against TradingView's values on an
   HA chart and a regular chart, take a screenshot through the debug port, restore the chart, send me the full file.
6. If nothing beats HMA: say it plainly, keep HMA(68), and write what was learned (which direction reduced overshoot,
   at what cost) so the next attempt starts further along.

## 6. How to report (Arabic, short, with tables)

The formula of the winner in simple words; the best and the worst number; the reversal close-up; the recommended
settings per timeframe; what was not verified. Each English term on its own line. Be honest: a failed gate is a result.
