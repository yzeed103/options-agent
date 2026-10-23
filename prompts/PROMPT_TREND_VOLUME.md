# PROMPT: Volume that supports the trend: strong → weak → strong again, together with the Hull average

You are working in `yzeed103/options-agent` (local `C:\project\options-agent`, branch `claude/gracious-johnson-g6tuct`).
Work through every phase without asking me for permission. Commit and push after each phase. No pull requests.
Never show API keys or passwords. Never open `C:\project\gex_radar\.env`. Never inject desktop keystrokes or clicks;
TradingView is reached read-only through the debug port 9222 and the chart is always restored afterwards.

Same discipline as before (`reports/conviction_ma`, `reports/hma_successor`, `reports/volume_tool`): pre-register,
planted tests with a known answer on fresh seeds, train / test split, intervals over symbol-days, verdict by a rule
written before the results, and an honest "it does not work" when that is the answer.

## 1. Where we stand (read first; do not redo)
- `reports/volume_tool/RESULTS.md`: on its own, **no volume tool predicts direction** (19 tools, continuation IC
  within ±0.02 of 0 on 5m / 15m / 1h, fitted ceiling included). Slot-normalized RVOL (`vzones/volume_tool.py`,
  `rvol_set`) predicts **range expansion** (IC 0.28) and strong volume **persists** (hazard curve in `verdict.json`).
  One secondary hint: breakouts through a level on a big, high-volume bar succeed +30% more; on an absorption bar
  (big volume, small range) −13%.
- `reports/hma_successor/RESULTS.md`: the Hull average HMA(68 on 5m, ≈ 10-bar trend lag) is the calmest trend line
  at equal lag; the damped Hull (`vzones/hma_successor.py`, `dhma`, g = 0.85) turns earlier at reversals. Both are in
  `pine/volume_zones.pine` (v41) as moving-average types.
- `vzones/assistant/eyes.py` (first-passage framework, slot base rates, groups) and the IC / lift / bootstrap code in
  `vzones/volume_tool.py` (`ic_pooled`, `lift`): reuse. Never use per-block Spearman with smoothed tools (artifact
  documented in `reports/volume_tool/PREREG.md`).
- Data: SIP only (`VZ_TAG=sip`, `runtime_sip/bars/<SYM>_5m.csv`, 30 symbols, 2025-04 to now, regular session).

So the question is **not** "does volume predict direction" (answered: no). It is the conditional one:

> Given a trend that the Hull average already shows, does the **pattern of volume along that trend** (strong on the
> trend legs, weak on the pullback, strong again on the resumption) tell us whether the trend goes on, more than the
> price pattern alone does?

## 2. Definitions to pre-register (exact, in `reports/trend_volume/PREREG.md`, committed before any run)
**Trend state** from the Hull average M (HMA, length matched to a 10-bar lag per timeframe, as in hma_successor):
- up-trend bar: close > M and M rising for ≥ 3 bars (slope > 0); down-trend mirrored; else no trend.
- **leg**: a run of ≥ 5 trend bars in one direction.
- **pullback**: after a leg, 2–12 bars moving against the trend while close stays on the trend side of M (or within
  0.3 ATR beyond it) and M keeps its sign of slope or flattens; a pullback that closes beyond M by more than 0.3 ATR
  for 2 bars ends the trend (no resumption event).
- **resumption bar**: the first bar after the pullback that closes in the trend direction beyond the pullback's
  extreme (new high in an up-trend). This is the event bar t.

**Volume pattern** (slot RVOL, `rvol_set`, 20 sessions; volume signed by the bar's direction where stated):
- V_leg = mean RVOL on the leg's trend-direction bars; V_pull = mean RVOL on the pullback bars;
  V_res = RVOL of the resumption bar.
- **pattern score** P = ln(V_leg / V_pull) + ln(V_res / V_pull) (strong → weak → strong; fixed, not fitted).
- Also tested one by one: V_res alone; V_leg / V_pull alone; trend-volume ratio (up-volume / down-volume over the
  leg + pullback, the indicator's `udR`); cumulative delta slope (sum of close-position × RVOL over the leg) aligned
  with the trend; OBV-vs-price divergence on the pullback; effort / result on the resumption bar (absorption flag);
  **Hull-of-VWMA** (the Hull formula on a volume-weighted price) vs plain Hull as the trend line; and the **price-only
  control**: the same events with no volume number at all (depth of the pullback in ATR, its length in bars).
- Exhaustion side (also pre-registered): a leg whose last 3 bars carry RVOL > 2 with shrinking range (climax).

**Targets** (future only): (R1) the trend continues: within 24 bars price reaches +1 ATR beyond the resumption close
before −1 ATR (first passage, slot base rate); (R2) the next leg is at least as long as the last (bars); (R3) the
trend is still alive 24 bars later (close on the trend side of M). For exhaustion: reversal within 24 bars.

**Metrics**: hit rate of R1–R3 by quintile of the volume measure, lift of the top quintile over all events, IC of the
measure with the continuous first-passage outcome; everything **paired against the price-only control** (same events,
the control's own quintiles): the volume measure must beat the control, not just the base rate. Intervals by
bootstrap over symbol-days; groups; 5m / 15m / 1h; first 30 minutes separately.

## 3. Planted tests (fresh seeds 30000..30039 for the gate)
- **Q1 no relation**: trends with pullbacks, volume with the U-shape and persistence but independent of what the
  trend does next: every measure's lift over the control must include 1 (a measure "finding" something is broken).
- **Q2 planted**: when the resumption bar's RVOL > 1.5 and the pullback's mean RVOL < 0.8, the trend continues with
  probability 0.70 instead of 0.50; the pattern score must recover ≥ 70% of the planted lift, and the price-only
  control must show none of it.

## 4. Verdict rule (test days)
**works**: on 5m and 15m (and not reversed on 1h), the pattern score's top-quintile lift on R1 beats the price-only
control's with intervals that do not overlap, lift interval excludes 1, in at least two symbol groups. **weak**: beats
the control on one timeframe only, or only with overlapping intervals. **no**: otherwise. The exhaustion test is
judged the same way against its own control (climax defined by price alone).

Falsifiable statements: (H1) the strong → weak → strong pattern has lift > 1 on R1; (H2) it beats the price-only
control; (H3) V_res alone carries most of the effect (the leg / pullback part adds little); (H4) Hull-of-VWMA is not
a better trend line than plain Hull at equal lag (volume weighting adds noise); (H5) climax bars reverse more often
than a price-only climax; (H6) nothing works in the first 30 minutes the way it works later.

## 5. Deliverables
1. `vzones/trend_volume.py`: trend state, legs, pullbacks, resumption events, the measures, the targets; pure
   functions of past bars except the targets (prefix test).
2. `tools/trend_volume_eval.py planted | verdict`, writing `reports/trend_volume/*.json`; `tests/test_trend_volume.py`.
3. `reports/trend_volume/RESULTS.md`: event counts, the paired tables (measure vs control), hit rate by quintile
   picture, an example chart with a leg / pullback / resumption marked on real candles, the exhaustion table, groups,
   first-30-minutes, the plain-words answer. If "no": say which part (volume, events, or both) failed and what was
   learned.
4. **Pine, only on "works"**: in `pine/volume_zones.pine`, a marker on the resumption bar ("استئناف بفوليوم" ▲ / ▼),
   coloured by the pattern score, drawn only when the Hull trend is on; an alert; a status-panel line "الاتجاه +
   الفوليوم" with the leg / pullback / resumption volumes and the measured hit rate; Arabic names and tooltips with the
   numbers; compile clean (`python tools/pine_check.py pine/volume_zones.pine`), copy to `pine/VolumeZones_full.txt`,
   save with `python tools/tv_pine_test.py --tf 5`, parity ≥ 99.9% of events matched against TradingView's values,
   screenshot through the debug port, restore the chart, send me the full file. On "weak": ship nothing, write what a
   trader would have to accept. On "no": ship nothing.

## 6. How to report (Arabic, short, with tables)
One line per question; the paired table (volume vs price-only); the best and the worst number; the exhaustion result;
what was not verified. Each English term on its own line. Be honest: after the last study the likely answer is "the
price pattern does the work and volume adds little"; if that is what the data says, say it in the first line.
