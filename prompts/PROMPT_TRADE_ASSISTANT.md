# PROMPT: Paper-trading assistant agent ("المساعد")

## Goal
Build a local agent that watches my signals, opens **simulated (paper) trades** on them, tracks every trade to
its exit, keeps a journal, and **learns which signals work under which conditions**, measured honestly.
It never trades real money.

## Context you must read first
- Repo: `yzeed103/options-agent`, branch `claude/gracious-johnson-g6tuct`, local clone `C:\project\options-agent`.
  Never commit to `main`. Commit and push after each phase. No PRs unless I ask.
- `pine/volume_zones.pine`: my TradingView indicator. Signals it already produces:
  trendline breaks (`tlBrkUp` / `tlBrkDn`), Supertrend flip, whale bounce (`wbSig`), trend alert outside
  yesterday's value area (`taFire`), weak volume, "reached whale line" (`hitHead`), the session POC / VAH / VAL,
  top-3 zones and the options levels (CW, PW, FLIP, PIN, DFLIP, MAXOI, CWOI, PWOI).
- `vzones/`: Python versions of parts of the indicator (`ranges.py`, `daily_trendlines.py`, `gex_block.py`).
- `tools/gex_agent.py`: the existing agent that talks to TradingView Desktop over the debug port (9222).
  Reuse its patterns: single-instance lock, state in `runtime/`, Windows scheduled task at logon.
- GEXRadar (`C:\project\gex_radar`, FastAPI on 127.0.0.1:8000): options levels per symbol per day.
  Never open or print its `.env`. Keys are read in-process only and never printed or logged.
- `tools/fetch_alpaca_5m.py`: 5-minute candles (Alpaca IEX).
- `reports/trendline_backtest.py`: already measured trendline breaks and found **no edge**. Earlier lab work also
  found trend-following negative, and "close below the value area" mildly positive. Treat all of these as
  hypotheses to re-test, not facts.

## Hard rules
1. **Paper only.** No broker order endpoints, no real or broker-paper accounts. The simulator is our own code.
2. No Telegram or any outside messaging.
3. Everything (database, logs, state, reports) lives under `C:\project\options-agent\runtime\` or `reports\`.
   Nothing in AppData or on the OneDrive desktop.
4. Never show API keys or passwords, in output, logs, or commits.
5. TradingView is **read-only** for this agent: read plots and drawings over the debug port. Never send keystrokes
   or clicks. Never leave my chart changed (symbol, timeframe, visibility); restore anything you touch.
6. No lookahead. A signal on bar *t* can only use data closed at bar *t*; entry is at the open of bar *t+1*.
7. Be honest. Report the real numbers, including when nothing works. No claim of an edge without the statistics below.

## What to build

### Phase 0: inventory and parity
- List every signal the indicator produces and how the agent will get it.
- Prefer **recomputing signals in Python** from candles (reproducible, testable on history). Use TradingView
  readings over the debug port only to **check parity**: for 5 symbols × 2 timeframes (5m, 15m), the Python signal
  bars must match the indicator's bars. Report the match rate, and fix or drop any signal below 95%.

### Phase 1: the simulator
- Trade record: symbol, timeframe, signal type, side, signal bar time, entry (next open), stop, target(s),
  timeout, exit reason, exit price, result in R and in %, plus costs (spread + slippage, configurable).
- Exit rules are **fixed per signal before any test** (e.g. stop beyond the signal bar or the nearest level,
  target 1R / 2R or the next options wall, timeout N bars, flat at session close). No exit tuned on results.
- One open trade per symbol and signal type. Trades outside regular hours are not allowed unless I enable them.
- Journal in SQLite (`runtime/paper.db`, WAL mode). Log **every signal, taken or skipped, with the reason**.
  Each signal also gets a context snapshot: time of day, distance to each options level in daily ATR,
  position vs. POC / value area, trend state, relative volume, VIX bucket, gap size.

### Phase 2: bootstrap on history
- Replay the stored 5m / 15m history through the same code path the live agent uses.
- Report per signal type: trade count, win rate, average R, expectancy, max drawdown, t-stat, and a
  95% bootstrap confidence interval.

### Phase 3: live shadow mode
- Runs at logon as a scheduled task, polls each bar close for my watchlist (the GEXRadar symbols), opens and
  closes paper trades, and writes a health line every cycle. Single-instance lock. Survives a TradingView or
  GEXRadar restart.
- Daily report after the close (`reports/paper/YYYY-MM-DD.md`), in **short Arabic with tables**: today's trades,
  open trades, running stats per signal.

### Phase 4: learning (measured, not black-box)
- "Learning" means estimating, per signal type × context bucket, whether the expectancy is real.
- Use shrinkage toward the overall mean, and a minimum sample per bucket (≥ 30 trades) before any decision.
- Walk-forward only. Three batteries: the tuning period, a held-out period never looked at while tuning,
  and fresh live paper trades after the rule was frozen. Report all three.
- A rule is **promoted** (the assistant starts flagging it as "worth watching") only if it is positive on all
  three batteries with t ≥ 2 on held-out and live data. It is **demoted** when live expectancy falls below zero
  over its last 30 trades. Every promotion and demotion is logged with the numbers.
- Keep a "graveyard" file of ideas that failed, with the numbers, so they are not retried blindly.

### Phase 5: the assistant view
- A local page (or a section of the daily report) showing: open paper trades, the signal that triggered each,
  the level context, and the current verdict per signal ("promoted / watching / dead") with its sample size.
- Optional, only if I ask later: draw the open paper trades on my TradingView chart through the indicator's
  text input, the same way the GEX agent pushes the levels block.

## Tests (must pass before each commit)
- **Planted-signal test:** a synthetic series where a planted rule has a known expectancy; the simulator and the
  learning step must recover it. A pure-noise series must produce **no** promoted rule.
- **No-lookahead test:** shifting future bars must not change any past signal or trade.
- **Parity test** from Phase 0.
- **Restart test:** kill the agent mid-trade; on restart the open trade continues correctly from the journal.

## Done means
- All tests pass. The agent runs from logon, journals live paper trades, and writes the daily Arabic report.
- A first honest verdict per signal type, with counts and confidence intervals, even if the verdict is
  "no edge".
- Each phase committed and pushed with a short message.
- A final short Arabic summary for me: what was built, the numbers, and what was **not** verified.

Work through all phases without asking me for permission. Stop only if something would break a hard rule.
