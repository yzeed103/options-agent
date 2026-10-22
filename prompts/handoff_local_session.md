# Handoff: Volume Zones indicator project -> local session

You are continuing a long project with this user. Work locally on their Windows PC from now on.

## Repo
- GitHub: `yzeed103/options-agent`, branch `claude/gracious-johnson-g6tuct` (all work is pushed there; never commit to main, no PRs unless asked).
- Clone/pull it locally first: `git clone -b claude/gracious-johnson-g6tuct https://github.com/yzeed103/options-agent`

## What exists
- `pine/volume_zones.pine` = the TradingView indicator (Pine v5, ~1100 lines). `pine/VolumeZones_full.txt` = identical copy the user pastes. Keep both in sync.
  - All measurements use real candles via `ticker.standard()` (Heikin Ashi only changes the look).
  - Rolling profile on today's session by default (option: bar count), POC/VAH/VAL, heat-map ribbons (3 colours navy/purple/pink), top-3 zones, buy/sell profile at the right edge.
  - Prior-day value area + trend alert (only signal with a tested small edge, ~52%); faded when up/down volume (50 bars) opposes it.
  - Whale levels: every daily sideways range (first 10 days set top/bottom unless wider than 6x daily ATR; first daily close outside ends it, breakout day included), hidden 200-row profile from 15m bars -> tall columns (purple) + POC (red) / VAH / VAL (orange). Recomputed once per new day from completed days only (history == live). Whale bounce signal (experimental, not significant).
  - Heading line: nearest whale level ahead of price in the instant-trend direction (EMA 9/21 + DMI 7), thick purple until touched.
  - Trend hold: Supertrend(10,3) on real candles. Trendlines: 2-bar pivots on highs/lows, latest lower-high pair (red) / higher-low pair (green), extended; reverse-engineered from the user's own trendline indicator and matched exactly.
  - Arabic status panel (12 rows) incl. call/put whale targets hit today.
  - Alerts: trend alert, whale bounce, weak volume, reached whale level, Supertrend flip, trendline breaks.
  - Removed for no edge: HUNT, pool-break warning, rejection, early warning, VA re-entry.
- `vzones/ranges.py` = Python counterpart of the current Pine logic. `reports/readings_study.py` tested the newer readings: heading line no better than placebo levels, Supertrend flip weak edge, trendline break / call-put counts no edge. `reports/README.md` indexes reports; `reports/archive/` holds removed-signal results.
- `tools/pine_check.py` = static checker (pynescript). Run `python tools/pine_check.py pine/volume_zones.pine` after every Pine edit. It cannot catch TradingView runtime/type errors; the user tests in TradingView and sends screenshots.
- Data in `data/intraday/` (SPY/QQQ 5m+15m, 5 stocks 15m, INTU 5m TradingView export).

## Pine pitfalls learned (v5)
- `and`/`or` evaluate both sides: never index an array in the same expression that tests its size.
- `if/else if` used as a statement can fail type checks when branches end differently: prefer separate `if`s.
- Functions cannot assign global scalars: use arrays. Loops `for 0 to size-1` run backwards on empty arrays: guard.
- 500 line/box limits: the heat map caps itself to leave room.

## User preferences
- Writes in Arabic (Gulf dialect). Answer in Arabic, short and simple ("بسط" = simplify). When Arabic text contains an English word/term, put it on its own line, then continue Arabic on the next line.
- Always send the full code file after a change; verify with the checker before sending; be honest about what was not tested in TradingView.
- Prefers evidence: test ideas on data before adding; report failures plainly.

## Next task
1. The user has a local tool "GEXRadar" (desktop shortcut; code probably under `C:\project`, maybe another name). It computes for ~30 tickers from OCC open interest (+ Yahoo, Alpaca): net GEX, net DEX, call wall, put wall, gamma flip, delta flip, pin level, per-strike gamma/delta charts. Find it, read it fully without changing it, and summarise: data sources, how each level is computed, key files/functions, where results are stored, bugs you see. Never print API keys.
2. Plan agreed: Pine Seeds is closed to new repos, so the indicator gets a text-area input where the user pastes one daily block for all symbols, e.g. `INTU: CW=360 PW=340 FLIP=355 ...`; the indicator picks the line for the current ticker and draws the levels next to the whale levels. GEXRadar should generate that block (and optionally send it by Telegram). Later: TradingView alert webhooks -> small server (based on `app.py`) -> Telegram.
