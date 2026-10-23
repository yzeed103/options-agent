# PROMPT: Build something new enough to patent (or its equivalent), from what the measurements showed

## Why this prompt exists
Two rounds of honest measurement on my indicator (reports/paper/history_verdict.md, reports/eyes/HISTORY.md,
18 months, 30 symbols, 5m and 15m, held-out splits) produced these facts. They are the starting point, not the
hopes I had before:

1. **No single signal has an edge after costs.** Trendline breaks, Supertrend flips, trend alerts, whale bounces,
   wall rejections: all within noise before costs, all negative after 2 bp per side. On 5-minute bars the cost alone
   is 0.15–0.20 R per trade. Stacking confirmations (MA crossover, instant trend, Supertrend) removed trades without
   improving them.
2. **Levels are not magnets and not targets.** The next options wall is reached *slightly less* often than a random
   price at the same distance; whale lines pull price by at most 1.5 percentage points and only in one period.
   First-touch rejection at every level type is within noise of a random nearby price, with one candidate exception
   (the put open-interest wall PWOI: 35% vs 21% on 80 touches, one period, unconfirmed).
3. **The one thing that held in both periods is not about direction at all.** Where price sits relative to the
   gamma flip at 10:00 predicts the *size* of the rest of the day: above the flip the rest-of-day range is narrower
   (−0.15 daily ATR in the first period, −0.05 in the second; strongest in SPY/QQQ, present on calm days too).
   Dealer positioning says something about **volatility**, not about **where price goes**.
4. Every tool I know of, including mine, draws these levels as *lines to trade against*. The data says that is the
   wrong use of them.

## What I want
Something a patent examiner (or a serious quant reviewer) would call **new, non-obvious and useful**, with proof.
Not another indicator skin, not a parameter tune, not a dashboard. The bar: a method or system that does something
no existing product or paper does, that I can demonstrate working on real data, and that beats the sensible baseline
by a margin that survives a held-out period. Anything less is not accepted. If after honest work nothing clears
that bar, the deliverable is a written finding that says so with the numbers, and that is also acceptable.
What is not acceptable is a claim of novelty that the prior-art search or the held-out numbers do not support.

## Direction (start here, but prove or kill it)
The measured facts point to one inventive angle: **use dealer positioning to forecast the day's volatility regime
and let that forecast control risk, timeframe and exits, instead of using the levels as price targets.**
Concretely, a "regime engine" that each morning (and updated intraday) outputs for each symbol:
- an expected rest-of-day range (daily-ATR units) from: price vs gamma flip, distance to walls in ATR, the sign and
  size of net GEX, the hedging-flow proxy GEXRadar already stores (`hedge_flow`), VIX, time of day;
- a cost-aware **barrier recommendation**: the smallest stop/target pair and the timeframe at which a trade's
  expected move exceeds costs by a margin, or "do not trade this symbol today" when it cannot;
- an **invalidation trigger**: the flip changing sides (3 closes) re-rates the regime at once.
The novelty is in the coupling: positioning → volatility forecast → execution parameters, with the forecast
scored and recalibrated daily and the whole thing pre-registered. Direction stays unknown; the invention is
knowing *how big* and *how to size*, which is where the data says the information is.
Alternatives you must also consider, and may choose if the evidence is stronger: (a) the PWOI first-touch
rejection, if it confirms live and across symbols, as a conditional fade mechanism; (b) a different combination
of the stored data (OI snapshots per strike per day, hedge-flow buckets, intraday bars) that no one has used.

## Context you must read first
- `C:\project\options-agent` (branch `claude/gracious-johnson-g6tuct`; never commit to `main`; commit and push each
  phase; no PRs unless I ask). `prompts/PROMPT_TRADE_ASSISTANT.md`, `prompts/PROMPT_ASSISTANT_EYES.md` and the
  reports they produced. `vzones/assistant/` (signals twin, simulator, journal, learning, eyes). `reports/eyes/
  DEFINITIONS.md` for the measurement rules already fixed.
- GEXRadar (`C:\project\gex_radar`): `daily_levels` (per-strike OI and GEX for ~58 days, walls/flip for ~560 days
  on 7 big names), `hedge_flow` (216k rows of per-bucket buy/sell hedging estimates), `oi_snapshots`. Read-only.
  Never open or print its `.env`; keys in-process only, never logged.
- The memory of the user's constraints: no Telegram, everything under the project folder, no keys shown, short
  Arabic reports with tables, honesty above results.

## Hard rules
1. **Pre-register.** Before any model is fit: `reports/invention/PREREG.md` with the exact target variable, the
   features, the baseline, the metric, the held-out rule and the success threshold. Commit it. Then run.
2. **Baselines must be strong.** For a range forecast: yesterday's ATR, the ATR-scaled time-of-day profile, and a
   plain regression on VIX + ATR. The invention must beat all three on the held-out period.
3. **No lookahead**, same discipline as before; levels of day D are known before D's open; hedge-flow buckets used
   only up to the current bar.
4. **Costs in every trading claim**, 2 bp per side, and the result reported before and after.
5. **Prior-art search before building**: a written list (`reports/invention/PRIOR_ART.md`) of products, papers and
   patents that do something close (dealer gamma / vol forecasting / regime-controlled execution), with one line each
   on what they do and what the proposed method does that they do not. Use WebSearch; cite URLs. If something
   already does it, say so and move on.
6. Honesty: report what fails. A "partly" with numbers beats a "works" without.

## What to build
### Phase 1: prior art and pre-registration
PRIOR_ART.md and PREREG.md, both committed before any fitting.

### Phase 2: the regime engine on history
- Target: rest-of-day range after 10:00 in daily-ATR units (and after 11:00, 12:00 as updates).
- Features from positioning only vs positioning + VIX/ATR; show the marginal value of positioning (the invention's
  claim) with held-out R², mean absolute error, and calibration plots.
- Then the execution mapping: for each symbol-day, the recommended barrier/timeframe (or "no trade"), and the
  paper P&L of a fixed, dumb entry rule (e.g. the existing trendline break) **with vs without** the engine's
  sizing/exits, after costs. The engine must turn a losing baseline into something at least break-even on held-out,
  or the claim is "the forecast is real but not tradeable" (also a finding).
### Phase 3: the invention write-up
`reports/invention/INVENTION.md`: title, one-paragraph abstract, the problem, the method (steps, diagrams drawn
from real data as PNG), what is new vs prior art, the evidence tables, limitations, and draft **claims** in
patent style (independent method claim, independent system claim, 6–10 dependent claims). Plus a plain Arabic
summary for me. I will take it to a patent attorney; your job is the technical substance and the proof, not
legal advice.
### Phase 4: run it live
Hook the engine into `tools/paper_agent.py` as a daily output (per symbol: regime, expected range, barrier
recommendation, "no trade" flags) with the same journal/verify discipline, so the live record starts accumulating.

## Tests
- Pre-registered threshold met or not met, stated at the top of INVENTION.md.
- Planted test: synthetic days where range is driven by a planted positioning variable must be recovered; pure
  noise must give no held-out gain.
- No-lookahead test, restart test, as before.

## Done means
- PRIOR_ART.md and PREREG.md committed before results.
- INVENTION.md with the numbers, the pictures, the claims, and a clear verdict: clears the bar / does not.
- Live engine running from logon.
- A short Arabic summary: what was invented (or not), the single strongest number, and what is unverified.

Work through all phases without asking me for permission. Stop only if something would break a hard rule.
