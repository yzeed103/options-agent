# Volume tool, strength and persistence: pre-registration (2026-10-24, before any run)

Goal (prompts/PROMPT_VOLUME_TOOL.md): which common volume tool carries the most information about what price does
next, a per-bar "volume strength" number that is comparable across symbols, timeframes and times of day, and how
volume persists. Nothing below changes after results are seen; bugs are dated at the end.

## Data
SIP 5-minute bars (`VZ_TAG=sip`), 30 symbols, regular session 09:30–16:00 ET, 2025-04 to now. 15m and 1h by
resampling within sessions, daily from the session. First 60% of days = train, last 40% = test.
Symbol groups as in reports/eyes/DEFINITIONS.md (index ETFs, mega-caps, high-beta).

## Normalization (the slot baseline)
- **slot**: the bar's position in the session (5m: 78 slots, 15m: 26, 1h: 7, daily: 1).
- **RVOL** = volume / median volume of the same symbol in the same slot over the previous 20 sessions (sessions
  strictly before today; the first 20 sessions have no value). **logRVOL** = ln(RVOL).
- **zRVOL** = (ln volume − median ln volume of the slot, 20 sessions) / (1.4826 × MAD of the same), robust z-score.
- ATR = Wilder 14 of the real candles (for range and return units).

## Candidates (all at one lookback L = 20 bars; robustness at L = 10 and 40, reported, not used for the verdict)
Signed tools (carry a direction): OBV slope (OBV − OBV[L]) / (ATR × Σ volume over L); A/D slope (same scaling);
CMF(L); MFI(L) − 50; Force Index = EMA(L) of (Δclose × volume) / (ATR × median volume); EOM(L) (Ease of Movement,
SMA L, in ATR units); Klinger(34, 55, 13) in units of the L-bar volume sum; **pressure** = ((close − low) − (high −
close)) / (high − low) × RVOL (the indicator's buy / sell split, one bar); **delta** = sum of pressure over L.
Unsigned tools (magnitude): **vol/SMA(L)** (the indicator's current rule); RVOL; logRVOL; zRVOL; vol ROC = volume /
volume[L] − 1; VWAP distance = |close − session VWAP| / ATR; **effort/result** = RVOL / max(range/ATR, 0.1) (high =
absorption, low = drive); range/ATR (no volume at all, the control).
Dropped before testing: volume-weighted MACD and PVT (same information as OBV / Force with extra smoothing), VPT,
NVI/PVI (daily-only constructs), Chaikin oscillator (CMF with two EMAs).

**Strength score (fixed weights, not fitted)**: `S = 0.5 zRVOL + 0.25 (range/ATR − 1) + 0.25 body/range`, where
body/range = |close − open| / (high − low). Directional form `S_dir = S × sign(close − open)`. A fitted logistic model
on train (same three inputs) is reported as the ceiling only, never shipped.

**Direction convention**: for the direction targets (T1, T3) an unsigned tool is multiplied by the bar's direction
sign(close − open); a signed tool is used as is. For the magnitude targets (T2) a signed tool enters as |value|.

## Targets (defined once; the "next" bars never include the current one)
- **T1 continuation**: y = (close[t+k] − close[t]) / ATR × sign(close[t] − open[t]), k ∈ {3, 6, 12} (continuous);
  binary = y > 0. Primary k = 6.
- **T2 range expansion**: y = ln(range of the next 6 bars / median of that range in the same slot over the previous
  20 sessions); binary = y > 0.
- **T3 first passage**: within 24 bars, price (high / low) reaches close ± 1 ATR; outcome +1 when the first touch is in
  the bar's direction, −1 opposite, 0 neither. Binary = +1. Base rate per symbol, timeframe and 30-minute slot.
- **T4 breakout**: a close through a level (prior-day VAH / VAL / POC from the day's 5m bars, CW / PW of the GEX block
  when available); success = price holds 0.5 ATR beyond the level for the next 12 bars. Binary.

## Metrics (95% bootstrap intervals over blocks: symbol-days on 5m / 15m, symbol-weeks on 1h, symbols on daily)
- **IC** = Spearman rank correlation between the tool and the target's continuous form, computed per block, then
  averaged; the interval is over blocks.
- **lift** = hit rate of the binary target among bars where the tool is above its **train** 90th percentile, divided
  by the hit rate of all bars (pooled over blocks); the interval by resampling blocks.
- **calibration slope** of the strength score: realized hit rate vs the score decile on test (slope of a line fit).
- **persistence**: strong = RVOL > 1.5. Run length r = consecutive strong bars. Hazard h(r) = P(next bar not strong |
  run length r), from train. Persistence score = expected remaining strong bars = Σ over m ≥ 1 of Π (1 − h) (capped at
  20). Autocorrelation of logRVOL at lags 1–12 per symbol. Brier score on test of the prediction "next bar strong" =
  1 − h(r), vs the constant base-rate prediction.
- **first 30 minutes** (slots 09:30–09:55) reported separately from the rest of the day for IC and lift on 5m.

## Planted tests (fresh seeds for the gate: 20000..20039; any seed < 20000 may be looked at while coding)
- **P1 no relation**: 40 synthetic symbol-years (250 sessions × 78 bars): returns iid normal; volume = U-shaped slot
  profile × lognormal noise with AR(1) 0.5 in log; no link between volume and returns. **Pass**: every tool's IC
  interval includes 0 on T1 and T2, and every lift interval includes 1. A tool failing P1 is broken and is removed.
- **P2 planted relation**: as P1, but when RVOL > 1.5 the sign of the next 6-bar return equals the bar's direction with
  probability 0.65 instead of 0.50 (+15 points), and strong runs end with a constant hazard 0.35. **Pass**: the
  strength score's lift on T1 (k = 6) recovers ≥ 70% of the planted lift (planted lift = 0.65 / base rate), and the
  fitted hazard at r = 1..5 is within ±0.08 of 0.35.
- If the score fails P1 or P2 the measurement is fixed and dated below; if it cannot be fixed, stop.

## Verdict rule (test data only)
A tool is **useful** when its lift interval on T1 (k = 6) or T3 excludes 1 **and** its IC interval excludes 0, on at
least two timeframes and in at least two symbol groups (5m). **descriptive only**: stable sign of IC across
timeframes but intervals include 0 or lifts include 1. **noise**: otherwise. Best tool = the useful one with the
highest mean IC at L = 20 over 5m / 15m / 1h; ties to the simpler formula. The strength score is judged by the same
rule; persistence by the Brier improvement over the base rate (interval over symbols) and the autocorrelation.

## Falsifiable statements
H1 vol/SMA(20) is worse than slot-RVOL on every target (U-shape). H2 volume predicts range expansion (T2) much better
than direction (T1): IC(T2) > 3 × IC(T1). H3 absorption (effort/result high) predicts reversal (negative IC with T1),
drive (low) predicts continuation. H4 persistence is real (autocorrelation of logRVOL at lag 1 > 0.3) but adds little
to one strong bar for T1 (lift of "run ≥ 3" within 10% of lift of "run = 1"). H5 the first 30 minutes differ from the
rest of the day (IC or lift intervals do not overlap). H6 the indicator's 0.80 / 1.5 × SMA(20) thresholds are not
where the lift is (the lift curve over vol/SMA(20) has no step there).

## Changes after writing
(none yet)
