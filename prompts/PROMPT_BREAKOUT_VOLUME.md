# PROMPT: Breaking a swing high or low with a strong bar: does volume make the break hold?

You are working in `yzeed103/options-agent` (local `C:\project\options-agent`, branch `claude/gracious-johnson-g6tuct`).
Work through every phase without asking me for permission. Commit and push after each phase. No pull requests.
Never show API keys or passwords. Never open `C:\project\gex_radar\.env`. Never inject desktop keystrokes or clicks;
TradingView is reached read-only through the debug port 9222 and the chart is always restored afterwards.

Same discipline as the earlier studies (`reports/volume_tool`, `reports/trend_volume`): pre-register, planted tests
on fresh seeds, train / test split, intervals over symbol-days, a price-only control, a verdict by a rule written
before the results, and an honest "no" when that is the answer.

## 1. Where we stand (read first; do not redo)
- `reports/volume_tool/RESULTS.md`, section "Breakouts (T4)": on 27,201 closes through prior-day POC / VAH / VAL and
  the GEX walls (test days, 5m), the base success (price holds 0.5 ATR beyond the level after 12 bars without closing
  back) is **28%**. On a bar in the top decile of the strength score (volume + range + body) success is +30%
  [24, 36]; of range/ATR alone +31%; of RVOL alone +13% [5, 20]; of effort/result (big volume, small range:
  absorption) **−13%** [−22, −3]. This was a secondary target, not pre-registered as the main claim, and the levels
  were value-area and gamma levels, **not** the swing highs and lows a trader draws. That is what this study tests.
- Volume on its own predicts no direction (19 tools), and the volume pattern along a trend adds nothing over price
  (`reports/trend_volume`). So the claim here is narrow: **at a level break, does the breaking bar's volume add to what
  its size already says?**
- Reuse: `vzones/volume_tool.py` (`rvol_set`, `atr`, `ic_pooled`, `lift`), `vzones/trend_volume.py` (`paired_lift`,
  `first_passage`), `vzones/assistant/data.py` (`levels_for_days` for the GEX walls), the pivot definition of the
  indicator's trendlines (`pine/volume_zones.pine`, `ta.pivothigh(tlH, tlLen, tlLen)` with tlLen = 2 by default,
  measured on 7 symbols; test tlLen 2 and 5 here).
- Data: SIP only (`VZ_TAG=sip`, `runtime_sip/bars/<SYM>_5m.csv`, 30 symbols, 2025-04 to now, regular session).
  5m and 15m; 1h only as a robustness line (few bars per session).

## 2. Definitions to pre-register (`reports/breakout_volume/PREREG.md`, committed before any run)
**Levels** (price only, known before the break): (a) swing highs and lows = pivot highs / lows with `k` bars on each
side (k = 2 and k = 5), confirmed k bars after the pivot, valid until broken; the nearest unbroken swing high above
price is "resistance", the nearest unbroken swing low below is "support"; (b) the prior day's high and low; (c) the
prior day's POC / VAH / VAL and the GEX walls CW / PW (for comparison with the earlier result). Levels from the same
session only for (a) unless pre-registered otherwise; say so.

**Break event** at bar t: the first close beyond a level L after at least 10 bars of closes on the other side; up-break
through resistance, down-break through support. One event per level. Never inside the first 5 bars of the session
(the level must be known).

**Measures at t (past only)**: RVOL[t] (slot RVOL); range/ATR[t]; body/range[t]; the fixed **break strength**
B = 0.5·zRVOL + 0.25·(range/ATR − 1) + 0.25·body/range (the earlier score); **penetration** = (close − L)/ATR in the
break direction; **absorption flag** = RVOL > 1.5 and range/ATR < 0.7; the number of touches of L before the break
(1, 2, 3+); the distance of L from the session VWAP in ATR. **Price-only control** C = range/ATR[t] (the breaking
bar's size alone). Also a two-way grid: range/ATR tercile × RVOL tercile.

**Targets** (future only): (B1) **hold**: no close back across L within 12 bars **and** close[t+12] beyond L by
≥ 0.5 ATR (the earlier definition); (B2) **follow-through**: +1 ATR beyond close[t] before −1 ATR, within 2 hours
(24 bars on 5m, 8 on 15m); (B3) **false break**: close back across L within 3 bars (the failure a trader fears);
(B4) the move's size: max favourable excursion in ATR within 12 bars (continuous).

**Metrics**: hit rates by quintile of each measure (edges from train events); lift of the top quintile over all
events; **paired lift against C** (`paired_lift`, bootstrap over symbol-days); IC with B4; per level type, per
timeframe, per symbol group; up-breaks and down-breaks separately; the two-way grid of B1 by range tercile × RVOL
tercile (this is the picture the trader needs: does volume add inside each bar-size bucket?). Also: given a false
break (B3), the measures' hit rates, to see whether volume helps avoid them.

## 3. Planted tests (fresh seeds 40000..40039 for the gate; lower seeds for coding)
Synthetic 5m symbol-years with real-looking swings (random walk with occasional range phases), U-shaped volume with
persistence; levels and breaks found by the same detector.
- **W1 no relation**: the breaking bar's volume is assigned independently of what follows. Pass: no measure beats
  the control (paired lower bound > 0 for none).
- **W2 planted**: after a break, the probability of B1 is 0.45 when the breaking bar's RVOL > 1.5 and 0.25 otherwise,
  assigned by outcome as in the trend-volume study (prices first, breaks, then volume). Pass: RVOL's top-quintile lift
  recovers ≥ 70% of the planted lift and the control's lift is unchanged between W1 and W2 (same prices).

## 4. Verdict rule (test days)
**works**: on 5m and 15m, for swing-level breaks (k = 2 or k = 5, say which was pre-chosen: k = 2, the indicator's
default), RVOL's or B's top-quintile lift on B1 beats the control's with the paired interval excluding 0, its own lift
interval excludes 1, and inside at least two of the three range terciles the top RVOL tercile's B1 rate is above the
tercile mean; and the same sign holds for up and down breaks. **size only**: the control (bar size) has the lift and
volume adds nothing beyond it (paired interval includes 0). **no**: neither.
The absorption flag is judged on its own: "warning" if B3 (false break) is higher with the flag, interval excluding
0, on both timeframes.

Falsifiable statements: (H1) big breaking bars hold more often (control lift > 1); (H2) volume adds to size (paired
> 0); (H3) absorption bars produce more false breaks; (H4) the effect is larger on swing levels than on value-area
levels (traders watch swings; more stops sit there); (H5) down-breaks on volume hold more than up-breaks (selling
climaxes); (H6) a level touched 3+ times breaks and holds more often than one touched once (price-only, reported).

## 5. Deliverables
1. `vzones/breakout_volume.py`: levels (pivots with k, prior-day H/L, value area, GEX walls), break events, measures,
   control, targets; past-only functions (prefix test) except the targets.
2. `tools/breakout_volume_eval.py planted | verdict`; `tests/test_breakout_volume.py`.
3. `reports/breakout_volume/RESULTS.md`: event counts per level type, the paired tables, the range × RVOL grid of
   B1 (picture), the false-break table, up vs down, groups, a real-chart example with the level, the break bar and the
   outcome marked, the plain-words answer.
4. **Pine, only on "works"**: in `pine/volume_zones.pine`, a marker on the breaking bar («اختراق بقوة» ▲ / ▼ for swing
   breaks on a top-quintile bar), an absorption warning marker if "warning", the measured hold rates in the tooltips
   and a status-panel line «آخر اختراق: … يثبت عادة x%», an alert; Arabic names; compile clean
   (`python tools/pine_check.py pine/volume_zones.pine`), copy to `pine/VolumeZones_full.txt`, save with
   `python tools/tv_pine_test.py --tf 5`, parity ≥ 99.9% of events matched against TradingView's values, screenshot
   through the debug port, restore the chart, send me the full file. On "size only": ship the marker on bar size
   alone if its own lift interval excludes 1, labelled so; otherwise nothing.

## 6. How to report (Arabic, short, with tables)
One line answering the question; the grid picture; the best and the worst number; what a trader should expect
(x of 10 breaks hold even with the best bar); the absorption warning if real; what was not verified. Each English
term on its own line. If the answer is "the bar's size does the work, volume adds little", say it in the first line.
