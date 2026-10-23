# HMA successor for Heikin Ashi: pre-registration (2026-10-24, before any run)

Goal (prompts/PROMPT_HMA_SUCCESSOR.md): keep the Hull average's calm in trends, cut its overshoot and late turn at
reversals, without adding lag. Nothing below changes after results are seen; bugs are dated at the end.

## Reference
HMA(n) = WMA(2·WMA(n/2) − WMA(n), √n) on HA close, with n chosen on **train** data so its median lag in trends is
**10 bars** (on 5m that is n ≈ 68, the length now in the indicator). Every candidate is matched to the same 10-bar
trend lag on train data, by bisection on its length parameter.

## Candidates (5; formulas exact, source = HA close unless said)
1. **Damped HMA** `DHMA(n, g)` = WMA((2·WMA(n/2) − g·WMA(n)) / (2 − g), √n), g ∈ {0.6, 0.7, 0.8, 0.9, 1.0}. g = 1 is
   HMA. Shape parameter g; length n matched.
2. **Clamped HMA** `CHMA(n, k)` = HMA(n) clipped to [min(HA low), max(HA high)] of the last k candles, k ∈ {3, 5, 8,
   12}. Shape k; n matched.
3. **Damped Holt** `HOLT(a, phi)`: level `L = a·x + (1 − a)(L₁ + phi·T₁)`, trend `T = b·(L − L₁) + (1 − b)·phi·T₁`,
   output `M = L + phi·T` (one-step-ahead forecast, i.e. zero-lag form), b = a/5, phi ∈ {0.8, 0.85, 0.9, 0.95, 1.0}.
   Shape phi; a matched.
4. **Median of three** `MED3` = median(HMA(n₁), SuperSmoother(n₂), ALMA(n₃)), each member matched to the target lag on
   its own. No shape parameter.
5. **Regime blend** `BLEND(n, p)` = w·HMA(n) + (1 − w)·SuperSmoother(n₂), w = ER(20)^p, ER = Kaufman efficiency ratio
   (|x − x₂₀| / Σ|Δx| over 20 bars), p ∈ {0.5, 1, 2, 3}; both members matched to the target lag. Shape p.

Dropped before testing, with reasons: T3 and Laguerre (same zero-lag mechanism as HMA, no overshoot control of their
own), FRAMA / MAMA (cycle estimators need ≥ 200 bars of warm-up and were unstable on 5m in a quick look of the
formulas, not of data), Kalman and Savitzky–Golay (equivalent to Holt / local polynomial already covered), ZLEMA-EC
(its "error correction" is a gain search on the output, which fits the data; Holt covers the principled version),
reversal-gated HMA (needs a reversal detector, which is itself the thing being measured). JMA excluded (proprietary).

## Metrics (defined once; M = the average, P = HA close, ATR = Wilder 14 of the HA candles)
- **flips**: sign changes of ΔM per 100 bars (zero steps ignored). **noise**: mean|Δ²M| / mean|ΔP|.
- **whipsaws**: P-crosses-M events per session.
- **trend lag** (planted): mean of dir·(P − M) over bars 60..150 of each planted trend, divided by the trend step.
  (real data): Σ dir·(P − M) / Σ|slope| over trend bars labelled by the forward–backward EMA(20) (evaluation only).
- **reversal overshoot**: at a labelled reversal (planted: the V bar; real: the bar where the forward–backward EMA(20)
  slope changes sign with a ≥ 10-bar trend on both sides), turning price = the extreme of HA high/low within ±3 bars;
  overshoot = max over the next 30 bars of dirOld·(M − turning price), floored at 0, in ATR.
- **turn delay**: bars from the reversal until sign(ΔM) equals the new direction for 3 consecutive bars.
- **capture / false commit** and the **trading check** (long when M turns up, short when it turns down, 2 bp per
  side, fill at next bar's open): as in reports/conviction_ma/PREREG.md, vs the reference HMA.

## Step 1, choose the shape parameter (planted, seeds 0..99, seen)
Planted series (1,000 bars): 200 sideways (OU), 150 up (drift 0.25σ/bar), **V** into 150 down, **V** into 150 up,
150 sideways, 200 down. OHLC around the path, HA from that. For each candidate and shape value: match the length to
the reference lag, then score overshoot, turn delay, sideways flips. Choose the shape value with the lowest overshoot
subject to turn delay ≤ reference + 1 bar and sideways flips ≤ 1.10 × reference. Heat map: shape × target lag
{5, 10, 15, 20} of the overshoot reduction, to show a plateau.

## Step 2, gate (planted, fresh seeds 10000..10199, never looked at)
At the chosen shape value, each candidate vs the reference, paired by seed: **pass** = overshoot ≥ 30% lower
(95% bootstrap interval of the relative reduction excluding 0), turn delay ≤ reference + 1 bar (median), sideways flips
≤ 1.10 × reference. Candidates that fail are dropped. **If none passes: say so, stop, keep HMA.**

## Step 3, real data (passing candidates only)
SIP 5m bars, 30 symbols, 2025-04 to now; 15m, 1h by resampling within sessions; daily. First 60% of days train (lag
matching only), last 40% test. Per timeframe at matched lag vs the reference, intervals by bootstrap over symbol-days:
- **better**: overshoot lower (interval excludes 0) **and** flips and noise not worse (lower bound of the relative
  difference ≥ −10%); **equal**: overshoot interval includes 0 and flips / noise not worse; **worse**: otherwise.
Groups (index ETFs, mega-caps, high-beta) reported on 5m. A candidate goes to Pine only if better or equal on **all
four** timeframes and better on at least two.

## Falsifiable statements
- H1: damping g < 1 reduces overshoot monotonically in g.
- H2: the clamp removes ≥ 50% of overshoot at a cost < 0.5 bar of trend lag.
- H3: Holt with phi ≈ 0.9 matches the reference lag with less overshoot.
- H4: the median of three has less overshoot than each member without more noise.
- H5: whatever wins on 5m also wins on 15m, 1h and daily, and in every symbol group.

## Changes after writing
(none yet)
- 2026-10-24, after the runs (nothing above changed): (a) on the planted series the overshoot of every damped
  candidate was exactly 0 for most shape values, so the step-1 rule "lowest overshoot" picked the most damped grid
  point by tie-break (DHMA g 0.6, HOLT phi 0.8); the planted V was too easy to separate them. (b) The daily overshoot
  interval is NaN: only 89 labelled reversals, and bootstrap draws with zero reversals divide by zero. (c) An
  exploratory sweep of g on real 5m data was run **after** the verdict (tools/hma_successor_sweep.py); it is reported
  as exploratory, not as a result.
