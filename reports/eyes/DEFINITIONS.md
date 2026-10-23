# Eyes round: test definitions (written 2026-10-23, BEFORE any test was run)

These rules are fixed. Results are read against them; nothing here is changed after seeing a result. If a rule turns
out to be broken (a bug, not a disappointing number), the fix is dated and explained at the end of this file.

## Data
- Bars: Alpaca IEX 5-minute regular-hours bars, 30 symbols, 2025-04-01 to the last stored day (`runtime/bars/`);
  15-minute bars are built from them. Every test runs on both timeframes.
- Daily ATR (`datr`): Wilder ATR(14) of the daily bars, from completed days only (known before the open).
- Chart ATR: Wilder ATR(14) of the timeframe's bars, at the bar.
- Options levels for day D: GEXRadar `daily_levels` (basis `oi`), the LAST row of the previous market date:
  CW, PW, FLIP, DFLIP, PIN, MAXOI from the stored levels; CWOI / PWOI rebuilt from that row's strike table with
  `vzones.gex_block.oi_walls` (the same function the GEX block uses). Coverage: about 210 days for SPY, QQQ, AAPL,
  AMZN, META, NVDA, TSLA; about 40 days (since late August 2026) for most others; 2 days for COST, INTU, JNJ, UNH.
- Whale levels for day D: the indicator's rule (`vzones/assistant/signals.py`, parity 99.9%): tall-column peaks of
  the last two completed sideways ranges + the forming one, and each range's POC / VAH / VAL.
- Signals: trendline break (`tl`), Supertrend state, instant trend (EMA 9/21 + DMI 7, the panel's "now" reading),
  simple moving averages 20 / 50 / 100 / 200 on the close.
- Symbol groups: index ETFs = SPY, QQQ. Mega-caps = AAPL, AMZN, META, NVDA, AVGO, TSLA, LLY, ORCL, COST, JNJ, UNH,
  INTU, NOW. High-beta = every other symbol (AMD, PLTR, COIN, MSTR, MU, INTC, SMCI, CRWD, RKLB, MARA, MRVL, SOFI,
  HOOD, RIOT, RIVN).
- Held-out: all trading days sorted; the first 60% = "define", the last 40% = "confirm". Each test is reported on both.

## Shared rules
- **Touch** of level L: from below, the previous close < L and the bar's high >= L; from above, previous close > L and
  low <= L. "First touch" = the first such bar of the session for that level.
- **Reaching** a price before the close: some bar after the event bar, in the same session, trades through it.
- **Near** a level: within 0.5 daily ATR.
- **Base rate for a distance**: for an event at bar i, direction s, distance x (in daily ATR): the share of ALL bars of
  the same symbol and timeframe, in the same 30-minute slot of the session, from which price went x or more in
  direction s before the close. The event's excess = hit (0/1) - that share. This is the "random price at the same
  distance and time" comparison.
- **Intervals**: 95% bootstrap (2,000 draws), resampling whole symbol-days (events on the same day are not
  independent). A difference "is real" only when its interval excludes zero.
- **Practically tiny**: an effect under 2 percentage points (rates) or under 0.10 daily ATR (distances), even if real.

## Thesis 1: confirmed trend entry
Event: a trendline break at bar i in direction s.
- **tl**: entry at i.
- **tl+MA(N)**: SMA20 crosses SMA50 in direction s at a bar k with |k - i| <= N; entry at max(i, k). N = 3 and 6.
- **tl+IT**: instant trend = s at i. **tl+ST**: Supertrend direction = s at i.
- **tl+all(N)**: tl+MA(N), and at the entry bar the instant trend = s and Supertrend = s.
- Outcome A ("follow-through"): from the entry close, price reaches +1.5 chart ATR in direction s before -1.5 chart
  ATR, within the session (neither = no decision, counted separately and left out of the rate).
  Base: the same first-passage rate from all bars of the same symbol, timeframe, 30-minute slot and direction.
- Outcome B ("run"): the largest move in direction s until the close, in daily ATR, minus the same-slot average.
- Claim holds if tl+all has a real positive excess in both periods AND its excess is larger than tl alone's.
  Each confirmation alone is reported so it shows which one adds something and which only removes events.

## Thesis 2: walls are targets
Walls = CW, PW, CWOI, PWOI of the day. For each tl and tl+all(6) event on a day with walls:
- the next wall in direction s from the entry price (long: the lowest wall above; short: the highest below);
- hit = it is reached before the close; base = the distance base rate; excess = hit - base.
- also "before the opposite wall": hit only if the next wall is reached before the nearest wall behind.
- subset "starts near a wall": a wall behind the entry within 0.5 daily ATR.
Claim holds if the excess is real and positive in both periods (and not practically tiny).

## Thesis 3: the flip shows the market maker's behaviour
Per symbol-day with a FLIP: side = the 10:00 close (the 09:55 5-minute bar) above or below FLIP. After 10:00:
- range from 10:00 to the close, in daily ATR;
- number of 5-minute trendline breaks;
- wall rejection rate (first touches of CW / PW / CWOI / PWOI after 10:00, rule below).
Prediction: above-flip days have a smaller range and a higher wall rejection rate than below-flip days. Also reported
inside VIX buckets (below 20 / 20 and above), because below-flip days cluster on fearful days. Same for DFLIP.
"Flip changed sides" day: three consecutive 5-minute closes on the other side of FLIP after 10:00 (counted, and its
range after the change compared with before).
Claim holds if both predictions are real in both periods.

## Thesis 4: whale zones pull price
- **4a, with the trend**: for each tl event, the nearest whale level (peak or POC / VAH / VAL) in direction s within
  3 daily ATR; hit = reached before the close; excess over the distance base rate.
- **4b, without a signal**: at every bar starting at :00 or :30, the nearest whale level above and below (within 3
  daily ATR); same hit / base / excess.
- Both also by distance band: 0-0.5, 0.5-1, 1-2, 2-3 daily ATR.
Claim holds if 4a and 4b show a real positive excess in both periods and it is not practically tiny.

## Level reactions (CW, PW, CWOI, PWOI, FLIP, DFLIP, PIN, whale POC / VAH / VAL, whale peak)
On a first touch at bar t: **pass-through** if any close in bars t..t+3 is beyond the level on the far side;
otherwise **rejection**. Base: the same rule at two pseudo-levels per real level, the real level shifted by
+u and -u daily ATR, u drawn uniformly from 0.25 to 1.0 with a fixed seed per symbol-day (random prices near price).
Reported: rejection rate per level type vs the base rate, excess, interval, sample size.

## Verdict per thesis item
- **holds**: the claim's effect is real (interval excludes zero) in the predicted direction in BOTH periods, not
  practically tiny, and has the same sign in at least two of the three symbol groups in the confirm period.
- **partly**: real in one period only, or only on one timeframe or one group, or real but practically tiny.
  The report says which.
- **does not hold**: not real in either period, or real in the opposite direction ("opposite" is stated).

## Live eyes (daily)
The same rules, run on each day's bars as they arrive. Outcomes still open at a cycle are "pending" and resolved
when the bars come; nothing decided at bar t uses bars after t. Unusual-day flags:
- a wall touched 3+ times in the session with no pass-through;
- a whale level passed through on its first touch with no rejection bar (close beyond on the touch bar itself);
- flip changed sides (rule above);
- an index group in sync: at least 80% of the symbols moved the same way from the open by more than 0.3 daily ATR.

## Changes after writing
- 2026-10-23, measurement fix (not a result-driven change): "range before / after a change of flip side" was first
  computed as the window's high-low range divided by its number of bars. That penalises the longer window (a range
  grows slower than the number of bars), so "after" always looked quieter. It is now the average bar range
  (high - low) in daily ATR, which is comparable between windows of different length.
- 2026-10-23, detail not stated above: a bar that reaches both first-passage barriers counts as adverse first (the
  simulator's stop-first rule).
- 2026-10-23, reporting only (the rule is unchanged): "a whale level passed through on its first touch with no
  rejection bar" turned out to be common (about three quarters of first touches pass within 4 bars in history; 45
  in a single day). The daily report counts it against that rate instead of listing each one as unusual.
- 2026-10-23: live tallies count only days from the first live day on (runtime/eyes_state.json); days filled in
  after the fact are labelled and left out.
