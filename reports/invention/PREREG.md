# Pre-registration (written 2026-10-23, before any model was fitted)

Nothing below changes after results are seen. Bugs are fixed and dated at the end; thresholds are not.

## Unit and data
- One row per symbol-day with options levels known before the open (GEXRadar `daily_levels`, basis `oi`, the previous
  market date's row) and Alpaca 5-minute bars (`runtime/bars/`, 30 symbols, from 2025-04-01).
- Update times t = 10:00, 11:00, 12:00 New York (decision uses bars that closed by t).
- **Target**: rest-of-day range y_t = (highest high - lowest low of the bars from t to the close) / daily ATR
  (Wilder 14, completed days).
- Split by date: the first 60% of the dates in the data set = train, the last 40% = test. Every number used to judge
  success comes from the test dates.

## Models (all fitted on train only; no tuning on test)
Forecast = exp(prediction of log(y_t + 0.02)), so it is a median-type forecast. Linear least squares on standardised
features with ridge penalty 1.0 (fixed, not tuned).
- **B1 "yesterday's ATR"**: the train median of y_t at time t (one number per t).
- **B2 "ATR-scaled time-of-day profile"**: the train median of y_t per symbol and t (falls back to B1 if the symbol
  has fewer than 20 train days).
- **B3 "plain regression"**: log VIX (previous close), log(daily ATR / price), log(range from the open to t / daily
  ATR + 0.02), |gap| / daily ATR, symbol-group dummies (index ETFs / mega-caps / high-beta).
- **P "positioning engine"** = B3 features + positioning: side vs FLIP at t (+1 / -1), |close - FLIP| / daily ATR,
  distance to the nearest of CW / PW in daily ATR, gamma regime sign (net GEX > 0), and normalised net GEX
  (net GEX / mean |net GEX| of that symbol's previous 20 rows, past only, needs 5).
  Fields that exist only since August 2026 (hedge flow, flow per 1% move) are not used: too short to split.

## Forecast test (claim 1: positioning adds information)
- Metric: mean absolute error of y_t on test dates.
- Interval: 95% bootstrap resampling whole dates (2,000 draws) for MAE(B3) - MAE(P).
- **Success at t = 10:00**: P has the lowest test MAE of all four models, the interval of MAE(B3) - MAE(P) is above
  zero, and the improvement is at least 2% of MAE(B3). Reported also at 11:00 and 12:00 and per symbol group.

## Execution test (claim 2: the forecast turns a losing rule into a usable one)
Entry rule (fixed, deliberately plain): every 5-minute trendline break (`tl`, the indicator's rule, parity 99.8%)
from 10:00 to 15:00 on test dates; entry at the next bar's open; one open trade per symbol; flat at the close.
Costs 2 bp per side. Three arms, same entries:
- **A, ATR exits**: stop 1 chart ATR, target 2x stop (the simulator's rules).
- **B, B3-sized exits**: stop = 0.25 x the B3 forecast of the remaining range (latest update at or before the
  entry), target 2x stop; **no trade** if the round-trip cost exceeds 15% of the stop.
- **C, P-sized exits**: the same with the P forecast.
Metric: mean net return per trade (basis points, after costs), and total net return per day across symbols.
Interval: 95% bootstrap over dates.
**Success**: C's mean net return per trade is >= 0, and C - B has an interval above zero.
If claim 1 succeeds and claim 2 fails, the finding is "the forecast is real but not tradeable with this rule".

## Verdict
- **Clears the bar**: both claims succeed AND the prior-art review (PRIOR_ART.md) leaves a specific element that no
  listed source covers.
- **Does not clear**: anything else, reported with the numbers.

## Tests that must pass
- Planted: synthetic rows where log y depends on a planted positioning variable -> P beats B3 with an interval above
  zero; pure noise -> interval contains zero.
- No lookahead (features at t use bars closed by t and levels known before the open), restart of the live engine.

## Changes after writing
(none to the tests above)

## Addendum A, 2026-10-23, written before running: HAR baseline (paper 2406.08041, "HARd to Beat")
The first round's verdict stands as it was. This adds a stronger baseline and re-asks claim 1 against it.
- Daily realized variance RV_d = sum of squared 5-minute log returns of the regular session (the first bar uses
  open-to-close). HAR components known before day d's open, each as log(RV mean) - 2 log(daily ATR / price):
  `har1` (day d-1), `har5` (mean of d-5..d-1), `har22` (mean of d-22..d-1).
- **B4** = B3 + har1, har5, har22. **P4** = B4 + the same positioning features as P. Same ridge, same fit on train
  dates only, same test dates, same metric and interval.
- Questions, each with the claim-1 rule (lowest test MAE, interval of the difference above zero, >= 2%):
  (a) does HAR improve the plain forecast (B4 vs B3)? (b) does positioning add anything on top of HAR (P4 vs B4)?
- Run on both data sources: IEX (as before) and SIP (the consolidated feed). The SIP run is the one that counts,
  because its bars hold the whole market's trading.
