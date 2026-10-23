# Conviction moving average for Heikin Ashi: pre-registration (2026-10-23, before any tuning)

Nothing below changes after results are seen. Bugs are fixed and dated at the end.

## Formula family (what is being tested)
Adaptive smoother `M_t = M_{t-1} + a_t (src_t - M_{t-1})`, seeded with the SMA of the first `L_slow` sources.

**Candle** (Heikin Ashi by default): `body = |c-o|`, `rng = h-l`, `atr` = Wilder ATR(14) of the same candles.
- direction `d_t = +1` (c > o), `-1` (c < o), `0` (doji: body < 0.10 atr).
- strength `q_t = clip(0.4 * body/rng + 0.3 * (1 - wrongWick/rng) + 0.3 * min(1, body/atr), 0, 1)`; wrongWick = upper
  wick for a red candle, lower wick for a green one. **The weights 0.4 / 0.3 / 0.3 are fixed, not tuned.**

**Conviction** `S_t` in [-1, 1] (sign = side, size = conviction). Three update laws, all tested:
- **A, additive**: same side (or S = 0): `S += g q d`; opposite: `S -= (1 - keep) q sign(S)` (partial; may cross zero
  and flip side); doji: `S *= 0.9`. Clamped to [-1, 1].
- **B, saturating-multiplicative**: same side: `S += g q d (1 - |S|)`; opposite: `S *= 1 - (1 - keep) q`; when
  |S| < 0.05 the next opposite candle starts the other side with `S = g q d`; doji: `S *= 0.9`.
- **C, leaky integrator**: `S = lam S + (1 - lam) q d` with `lam = 1 - g` (no explicit flip rule).

**Speed**: `a_t = a_slow + (a_fast - a_slow) |S_t|^p`, `a = 2/(L+1)`, lengths `L_fast < L_slow`.

**Parameters (6)**: law; `g` (conviction added by a full-strength candle of the running side); `keep` (how much
conviction survives one full-strength opposite candle: laws A and B; unused by C); `p` (power of the speed curve);
`L_fast`; `L_slow`.

Search grid (train data only): law in {A, B, C}; g in {0.15, 0.3, 0.5}; keep in {0.4, 0.6, 0.8}; p in {1, 2};
then for the best law: L_fast in {5, 8, 12} x L_slow in {40, 60, 100}. Source: HA close (main) and real close
(reported).

## Baselines (same source, same data)
EMA, SMA, Hull (HMA), ALMA (offset 0.85, sigma 6), KAMA (10, 2, 30), VIDYA (CMO 9), McGinley Dynamic, Ehlers
SuperSmoother (2-pole), and **streak EMA** (speed by HA colour-streak length only: |S| = min(streak, 10)/10, no
candle strength). Jurik JMA is **not** included: its exact algorithm is proprietary, and a "Jurik-style" clone would
not be a faithful baseline.

## Metrics (defined once)
- **lag** (bars): the k in 0..80 maximising corr(dM_t, dP_{t-k}) on first differences, refined by parabolic fit.
- **noise**: mean |second difference of M| / mean |dP|.
- **flips**: sign changes of dM per 100 bars (zero steps ignored).
- **whipsaws**: price-crosses-average events per session.
- **commit**: |dM| > 0.03 ATR per bar, in the direction of dM.
- **trend labels (evaluation only, uses the future)**: forward-backward EMA(20) of price; a bar is up / down trend
  when that filter's slope is above / below +-0.05 ATR per bar for at least 10 bars, else sideways.
  Capture = share of trend bars on which M commits in the trend's direction; false commit = share of sideways bars
  on which M commits.

## Matched-lag comparison
For each baseline, its length is chosen on the **train** data so its median lag equals the conviction average's
median lag (search lengths 3..200). Everything is then compared on the **test** data at that matched lag.

## Data and split
SIP 5-minute bars, 30 symbols, 2025-04 to now; 15m and 1h by resampling within sessions; daily from the session.
Regular-session bars only. First 60% of trading days = train (choose parameters), last 40% = test (verdict).
Groups: index ETFs (SPY, QQQ), mega-caps, high-beta (as in reports/eyes/DEFINITIONS.md). Tuning uses 10 symbols
(SPY QQQ AAPL AMZN META NVDA TSLA AMD PLTR COIN); the verdict uses all 30. (The recursions run as plain Python loops,
numba is not installed, so the grid is kept small.)

**Tuning objective (train, 5m)**: minimise flips per 100 bars subject to median lag <= the lag of EMA(20).

## Tests and thresholds
1. **Planted trend** (200 seeds): 300 sideways bars (mean-reverting), 150 up-trend bars (drift 0.25 sigma / bar),
   150 sideways, 150 down-trend; OHLC built around the path, HA from that. Metrics: commit delay after each trend
   start (bars until dM has the trend sign for 5 bars), false flips per 100 bars in the sideways parts, the dent from
   one injected strong opposite candle in mid-trend (|move of M| / sigma). **Pass**: at equal lag (+-10%) to an EMA,
   at least 25% fewer false flips in the sideways parts, 95% interval over seeds excluding zero. **If it fails: the
   idea fails; stop and report.**
2. **Pure noise** (200 random walks): commit share must not exceed the matched EMA's by more than 10%.
3. **Real data** (test): noise and flips at matched lag vs every baseline, per timeframe and group, with 95% intervals
   (bootstrap over symbol-days). Headline: flips and noise vs the best baseline at matched lag.
4. **Whipsaws**, 5. **trend capture / false commit**, 6. **trading check** (long when M turns up with |S| > 0.5,
   short when it turns down, 2 bp per side, next-bar open; vs the same rule on EMA and KAMA), 7. **robustness**
   (heat map of the tuning objective over g x keep), 8. **parity** (Python vs Pine, >= 99.9% of bars within 1e-6).

## Verdict
- **better**: passes test 1 and, on test data at matched lag, beats the best baseline on flips **and** noise with
  intervals excluding zero;
- **equal**: within the intervals of the best baseline (that baseline is named);
- **worse**: otherwise.

## Changes after writing
(none yet)
