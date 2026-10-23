# PROMPT: The assistant as my eyes (observation round, no trades)

## Goal
This round the assistant does **not** open paper trades. It watches the market through my indicator and tells me
what it sees. I cannot sit in front of 45 charts and take notes; the assistant can. It must **test my thesis
against the data**, keep an eye on the live charts every day, and write down every observation that matters,
with numbers, in short Arabic with tables.

## My thesis (what I believe the chart is telling me)
1. **Trend entry** = a trendline break that is confirmed by a **moving-average crossover** (the four averages now in the
   indicator) and by the **direction-confirmation tool** (the instant trend reading: EMA 9/21 + DMI 7, and the
   Supertrend state). One signal alone is noise; the three together are the setup.
2. **The options walls are targets.** Price moves from one wall toward the other (call wall CW above, put wall PW
   below, and the open-interest walls CWOI / PWOI). A trend that starts near one wall is aiming at the next.
3. **The gamma-flip zones (FLIP, DFLIP) show the market maker's behaviour.** Above the flip, dealers dampen moves
   (price gets pinned, ranges hold); below it, they amplify them (trends run, stops get hit). The flip is where the
   character of the day changes.
4. **The whale zones are where price goes.** They are high-volume areas and price likes to revisit them. A whale
   level ahead of price is a magnet; the trend is more likely to reach it than to stop short.

Each of these is a **claim to be tested**, not a fact. I want the assistant to tell me, honestly, which parts of this
hold up in the data and which do not.

## Context you must read first
- Repo `yzeed103/options-agent`, branch `claude/gracious-johnson-g6tuct`, local `C:\project\options-agent`.
  Never commit to `main`. Commit and push after each phase. No PRs unless I ask.
- `prompts/PROMPT_TRADE_ASSISTANT.md` and `reports/paper/README.md`: the assistant that already exists.
  Reuse it: `vzones/assistant/signals.py` (Python twin of the indicator, parity 99.8–100% with TradingView),
  `vzones/assistant/data.py` (bars, options levels per day from GEXRadar, VIX), the whale levels per day,
  the journal `runtime/paper.db`, the live agent `tools/paper_agent.py` (logon task `PaperAgent`).
- `pine/volume_zones.pine`: the indicator. The four moving averages are in the section «المتوسطات المتحركة»
  (defaults SMA 20 / 50 / 100 / 200, only the 100 on by default; the agent tests all four).
- `reports/paper/history_verdict.md`: the first finding. **No single signal makes money after costs.** This round is
  about *combinations* and *where price goes*, not single signals.
- GEXRadar (`C:\project\gex_radar`): levels per symbol per day in its SQLite (`daily_levels`, basis `oi`).
  Read-only. Never open or print its `.env`; keys are read in-process only and never logged.

## Hard rules
1. **No trades this round.** The live agent keeps running, but the deliverable is observations, not paper P&L.
2. No Telegram, no outside messaging. Everything under `runtime/` or `reports/`. Nothing in AppData or OneDrive.
3. Never show API keys or passwords.
4. TradingView is read-only; never send keystrokes or clicks; restore any chart you touch.
5. No lookahead: an observation about bar *t* uses only data closed at bar *t*. Levels used on day D are the ones
   known before D's open.
6. Honesty above everything. Every claim gets a count, a base rate and a confidence interval. "It looks like" is not
   an observation. If my thesis is wrong, say so plainly, with the numbers that show it.
7. No tuning on results. Define each test once, in writing, before running it; keep the definition in the report.

## What to build

### Phase 1: define the tests (write them down first)
Write `reports/eyes/DEFINITIONS.md` with the exact rule for each item below **before** any test runs:
- **Confirmed trend entry**: trendline break + the fast average crossing the slow one in the same direction within
  N bars (N = 3 and N = 6, both reported) + instant trend and Supertrend agreeing. Report also each pair alone, so I
  can see which confirmation adds something and which only removes trades.
- **Reaching a level**: price touches the level (high ≥ level for a level above, low ≤ level below) before the
  session close / before touching the opposite level. "Near" = within 0.5 daily ATR.
- **Wall as target**: after a confirmed entry, how often does price reach the next wall in the trade's direction
  before the session ends? Compare with the base rate: how often it reaches that distance from a random bar at
  the same time of day.
- **Flip behaviour**: for each day, is price above or below FLIP at 10:00? Then measure the day's realised range
  in daily-ATR units, the number of trendline breaks, and how often a touch of a wall is rejected vs. passed.
  Above-flip days should be quieter and more pinned if the thesis is right.
- **Whale magnet**: when the nearest whale level in the trend's direction is X ATR away, how often is it touched
  within the session? Compare with the same distance to a non-whale price (a random level the same distance
  away). The difference is the "magnet effect"; report it with its confidence interval.
- **Rejection vs. pass-through** at each level type (CW, PW, CWOI, PWOI, FLIP, PIN, whale POC/VAH/VAL, whale peak):
  on a first touch, does price close back on the other side within 3 bars (rejection) or continue?

### Phase 2: history
Run every test on the stored 5m and 15m history (`runtime/bars/`, 30 symbols, 2025-04 → now) with the GEXRadar
levels for the days they exist. Report per test: sample size, rate, base rate, difference, 95% interval, and the
same split by timeframe and by symbol group (index ETFs / mega-caps / high-beta names). Use the held-out
discipline: define on the first 60% of days, confirm on the last 40%.

### Phase 3: the daily eyes
Extend `tools/paper_agent.py` (or add `tools/eyes_agent.py` on the same cycle) so that **every market day** it:
- records, per symbol: where price sat vs. FLIP at the open, which walls and whale levels were touched and when,
  rejection or pass-through, every confirmed trend entry and whether it reached the next wall / whale level,
  and the day's range in ATR;
- writes after the close `reports/eyes/YYYY-MM-DD.md` in short Arabic with tables: **the five most important
  things it saw today**, each with the symbol, the time, the level, and what happened next; then the running
  tallies (how the thesis is doing live vs. history);
- flags anything unusual the same day: a wall touched three times and held, a whale level that was crossed
  without reaction, a day where the flip changed sides and the character changed with it, an index where
  all its names did the same thing.
- keeps a running file `reports/eyes/OBSERVATIONS.md`: a numbered list of durable observations, each with the
  date added, the evidence (counts), and a status (holding / weakening / refuted). Update it, do not rewrite it.

### Phase 4: the picture
- One chart per thesis item (`reports/eyes/*.png`), drawn from real bars: the thing claimed vs. the base rate,
  so I can see the effect size, not just read it.
- A short page `runtime/eyes_view.html` (Arabic, right-to-left, dark, refreshes itself) with today's observations,
  the levels touched so far, and the thesis scorecard.

## Tests (must pass before each commit)
- **Planted magnet**: synthetic bars where price is pulled toward a planted level must show the magnet effect;
  pure random-walk bars must show none (rate ≈ base rate, interval contains zero).
- **No-lookahead**: shifting future bars changes no past observation.
- **Parity** of the Python signals stays ≥ 95% (existing test).
- **Restart**: killing the agent mid-day and restarting does not lose or duplicate an observation.

## Done means
- `DEFINITIONS.md` written before the tests, then the history report `reports/eyes/HISTORY.md` with every test,
  its numbers and a one-line verdict per thesis item: **holds / partly / does not hold**, with what "partly" means.
- The daily eyes running from logon, producing the daily report and the observation list.
- The pictures and the page.
- A final short Arabic summary for me: what holds, what does not, the single most useful thing you saw, and what
  was **not** verified.

Work through all phases without asking me for permission. Stop only if something would break a hard rule.
