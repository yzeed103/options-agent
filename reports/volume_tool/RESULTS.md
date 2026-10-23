# Volume tool, strength and persistence: result

Three questions, three plain answers (30 SIP symbols, test days 2026-03-10 onwards, pre-registered in PREREG.md):

1. **Best volume tool**: **slot-normalized relative volume (RVOL)**: the bar's volume over the median volume of the
   same minute of the day in the previous 20 sessions. It carries by far the most information, and only about one
   thing: **how much price will move next (range), not which way**. IC with the next-6-bar range expansion 0.28 on
   5m, 0.25 on 15m, 0.17 on 1h; the indicator's current rule (volume / SMA 20) scores 0.07. No tool predicts
   direction: every continuation IC is within ±0.02 of zero and every lift within ±4% of 1 (fitted ceiling included).
2. **Volume strength**: the pre-registered fixed-weight score (zRVOL, range, body) is **not better than RVOL alone**
   (range IC 0.27 vs 0.28) and, like everything else, predicts no direction (calibration slope 0.0009 per decile:
   flat). So the shipped "strength" number is simply RVOL. By the pre-registered rule (lift on direction targets) no
   tool is "useful"; RVOL is "descriptive only" for direction and "useful for range" on three timeframes.
3. **Volume persistence**: real and strong. Autocorrelation of log-RVOL at lag 1 is 0.72 (5m), 0.74 (15m), 0.68
   (1h). A strong-volume run (RVOL > 1.5) ends on the next bar with probability 0.59 after 1 bar, 0.43 after 2,
   0.33 after 3, 0.23 after 5: the longer it has lasted the longer it goes on. The hazard-based "next bar strong"
   prediction beats the base rate (Brier 0.198 vs 0.242 on 5m). But persistence adds **nothing** for direction
   (continuation lift: run of 1 bar 1.01, run of 3+ bars 1.00).

## Ranking (5m, test days; `ranking.png`, full numbers in `verdict.json`)
| tool | range expansion IC [95%] | lift (top decile) | continuation IC | label |
|---|---|---|---|---|
| RVOL / logRVOL | 0.281 [0.271, 0.291] | 1.50 | −0.001 | descriptive only (direction); useful for range on 5m, 15m, 1h |
| zRVOL | 0.274 | 1.46 | −0.001 | same |
| strength score | 0.266 | 1.45 | 0.000 | same |
| effort / result | 0.206 | 1.40 | 0.000 | same |
| pressure (close position × RVOL) | 0.175 | 1.43 | −0.009 | noise for direction |
| delta (sum of pressure, 20) | 0.148 | 1.37 | −0.009 | noise |
| Force, range/ATR, VWAP dist, Klinger, **vol/SMA(20)**, vol ROC | 0.06–0.08 | 1.10–1.15 | ~0 | descriptive / noise |
| MFI, CMF | 0.04–0.05 | 1.10–1.13 | −0.01 | noise |
| EOM, OBV slope, A/D slope | −0.03 to −0.06 | 0.9 | ~0 | noise |

Same ordering on 15m and 1h. On daily bars everything is weak (RVOL range IC 0.05, intervals wide, 30 blocks only).
Groups on 5m (index ETFs, mega-caps, high-beta): direction lifts 0.97–1.02 in every group, range IC 0.24–0.28 in every group.

## Hypotheses
- H1 (vol/SMA worse than slot RVOL on every target): **confirmed** (range IC 0.07 vs 0.28; lift at 1.5× 1.10 vs 1.37).
- H2 (volume predicts range far better than direction): **confirmed**, by a factor of more than 100.
- H3 (absorption = high volume with a small range predicts reversal): **rejected**: effort/result has IC 0.000 with
  continuation. Its one real effect is on breakouts, below.
- H4 (persistence real but adds nothing for direction): **confirmed** on both halves.
- H5 (first 30 minutes differ): **barely**: in the opening 30 minutes the strength score shows continuation IC 0.017
  [0.005, 0.029] and lift 1.04 [1.02, 1.07]; the rest of the day exactly zero. Real but tiny: not a rule.
- H6 (the 0.80 / 1.5 thresholds are not where the lift is): **confirmed for the old measure**: its lift curve is flat
  (1.04 at 0.8×, 1.10 at 1.5×, 1.09 at 3×). On RVOL the curve rises smoothly (1.12 at 0.8×, 1.37 at 1.5×, 1.48 at
  2×, 1.58 at 3×): there is no step anywhere, so 1.5 is as good a line as any; it is kept as the default.

## Breakouts (T4, 5m test days, 27,201 closes through prior-day POC / VAH / VAL or the GEX walls; base success 28%)
Breakouts on a bar in the top decile of: strength score **+30%** [24, 36] success, range/ATR +31%, vol/SMA +25%,
pressure +24%, RVOL +13%, **effort/result −13%** [−22, −3] (a big-volume, small-range bar through a level is a
worse breakout). This is the one place where the bar's size and volume together say something about what follows;
it was a secondary target (not in the "useful" rule) and is reported, not shipped.

## Pictures
`ranking.png`, `calibration_lift.png` (flat calibration on direction; the lift curves), `hazard.png`,
`chart_SPY.png`, `chart_COIN.png` (RVOL and strong bars on real candles).

## What was shipped (pine/volume_zones.pine v41)
Per the pre-registration's "nothing useful for direction" branch: the normalization. "قياس الفوليوم" defaults to
slot RVOL (one ring buffer per slot of the session, previous 20 sessions, needs 10); the old volume / SMA(20) rule
stays as an option; weak / strong thresholds unchanged (0.8 / 1.5) with the measured meaning in the tooltips; an
"RVOL" value in the data window; a status-panel row "الفوليوم الآن" with RVOL, the strong run length and the usual
remaining length from the 5m / 15m / 1h hazard curves, and the honest note that range expands, direction does not.
Parity against TradingView's own bars (SPY 5m, 131 sessions): **9,438 of 9,438 bars identical** (max difference 0.0,
`parity.json`). TradingView's volume on this chart (symbol BATS:SPY) is the BATS exchange's share only: median 13% of
the Alpaca SIP volume (10% to 18% bar to bar). RVOL is a ratio, so the level cancels, but the chart's RVOL is built
from a thinner, noisier count than the one the numbers above were measured on.

## Not verified / caveats
T3 (±1 ATR first passage within 24 bars) is undefined on 1h and daily (not enough bars in a session). Daily
persistence has no runs (one bar per session). The breakout result used the GEX walls only on days GEXRadar has
stored; prior-day value area from 5m bars, not TradingView's. TradingView's volume differs from the Alpaca SIP bars
(see parity.json): the RVOL *formula* matches, the *numbers* on the chart come from TradingView's volume.
