# Volume that supports the trend: pre-registration (2026-10-24, before any run)

Question (prompts/PROMPT_TREND_VOLUME.md): given a trend the Hull average already shows, does the volume pattern
along it (strong on the leg, weak on the pullback, strong on the resumption) say whether the trend goes on, **more
than the price pattern alone does**? Nothing below changes after results are seen; bugs are dated at the end.

## Data
SIP 5m bars, 30 symbols, regular session, 2025-04 to now; 15m and 1h by resampling within sessions. First 60% of
days train (quintile edges only), last 40% test. Groups as in reports/eyes/DEFINITIONS.md. RVOL = slot RVOL
(vzones/volume_tool.rvol_set, 20 sessions). ATR = Wilder 14 of the real candles. Events never cross a session.

## Trend line and states
M = HMA on close, length matched to a 10-bar trend lag per timeframe as measured in reports/hma_successor
(5m 67, 15m 66, 1h 56). slope = M − M[1].
- **trend bar** (up): close > M and slope > 0 on this and the previous 2 bars; down mirrored.
- **leg**: ≥ 5 consecutive trend bars in one direction. Its extreme = highest high (up) of the leg; its length in bars.
- **pullback** (up-trend): starts on the first bar after the leg whose close is below the previous close; continues
  while close ≥ M − 0.3 ATR; it fails (trend over, no event) when close < M − 0.3 ATR on two bars, or after 12 bars
  without a resumption; it must last ≥ 2 bars.
- **resumption bar** t: the first bar after a pullback of ≥ 2 bars whose close is above the leg's extreme (up).
  After t a new leg starts (its length counted from t). Down-trends mirrored.
- **climax bar** (exhaustion): the last bar of a leg of ≥ 8 bars where the last 3 bars have RVOL > 2 and shrinking
  ranges (range[t] < range[t−1] < range[t−2]). Price-only climax control: the same without the RVOL condition.

## Measures at the resumption bar (past bars only)
V_leg = mean RVOL of the leg's trend-direction bars (last 20 bars of the leg at most); V_pull = mean RVOL of the
pullback bars; V_res = RVOL[t].
1. **pattern score** P = ln(V_leg / V_pull) + ln(V_res / V_pull) (fixed, not fitted);
2. V_res alone; 3. ln(V_leg / V_pull) alone; 4. trend-volume ratio udR = up-volume / down-volume over leg + pullback
(down-trend: inverse); 5. delta slope = Σ over the leg of close-position × RVOL, signed by the trend; 6. OBV
divergence on the pullback = (OBV change over the pullback, signed by the trend) / Σ volume of the pullback;
7. effort/result of the resumption bar = RVOL[t] / max(range[t]/ATR, 0.1) (high = absorption, expected bad);
8. **price-only control** C = −(pullback depth in ATR) − 0.1 × (pullback length in bars) (shallow and short = good).
9. Hull-of-VWMA: HVW(n) = WMA(2·VWMA(n/2) − VWMA(n), √n) as a trend line, compared with HMA at the same length on
flips, noise and trend lag (hma_successor metrics), test days, 5m.

## Targets (future only, from the resumption close)
R1: first passage +1 ATR in the trend direction before −1 ATR within 24 bars (+1 / −1 / 0; hit = +1). R2: the new
leg's length ≥ the previous leg's length. R3: 24 bars later the close is on the trend side of M. Climax: first
passage −1 ATR (against the trend) before +1 ATR within 24 bars.

## Metrics
Per measure: hit rate of R1 (and R2, R3) by quintile of the measure (edges from train events); **lift** = top-quintile
hit rate / all-events hit rate; IC = Spearman of the measure with the continuous first-passage outcome (bars to the
+1 ATR touch, negative when −1 ATR came first), ranks within symbol. The same for the control C. **Paired
comparison**: lift(measure) − lift(control), interval by bootstrap over symbol-days of the events (2,000 draws).
Groups and the first 30 minutes (events with t in 09:30–09:59) reported on 5m. Event counts always shown.

## Planted tests (fresh seeds 30000..30039 for the gate; seeds below 30000 may be used while coding)
Synthetic 5m symbol-years (250 sessions × 78 bars): phases of trend legs (drift ±0.3σ, 20–80 bars), pullbacks against
the leg (3–8 bars), flat stretches; volume = U-shape × persistent lognormal noise, with the pullback phase at 0.6× and
the resumption bar at 2× on half of the pullbacks (independent of price).
- **Q1 no relation**: after a pullback the trend continues with probability 0.5 whatever the volume. Pass: every
  measure's lift over the control has an interval including 0, and no lift interval excludes 1.
- **Q2 planted**: continuation 0.70 when the resumption bar's RVOL > 1.5 and the pullback's mean RVOL < 0.8, else 0.5.
  Pass: the pattern score's top-quintile lift recovers ≥ 70% of the planted lift (hit rate among planted events over
  all events), and the control's lift interval includes 1.
If the score fails Q1 or Q2 the measurement is fixed and dated below; if it cannot be fixed, stop.

## Verdict rule (test days)
**works**: on 5m and 15m the pattern score's top-quintile lift on R1 beats the control's (paired interval excludes 0)
and its own lift interval excludes 1, in at least two symbol groups on 5m, and 1h is not reversed (paired point
estimate ≥ 0). **weak**: beats the control on one timeframe only, or with paired intervals including 0. **no**:
otherwise. Exhaustion judged the same way against the price-only climax (reversal hit rate, paired).

## Falsifiable statements
H1 the pattern has lift > 1 on R1. H2 it beats the price-only control. H3 V_res alone carries most of the effect.
H4 Hull-of-VWMA is not better than Hull (more flips or noise at equal lag). H5 climax bars reverse more often than
price-only climax bars. H6 the first 30 minutes do not show what the rest of the day shows.

## Changes after writing
(none yet)
