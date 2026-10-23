# Applying the papers: full-market data, HAR, trend spectrum, order imbalance (2026-10-23)

Each test was pre-registered before it ran (reports/invention/PREREG.md addendum A, PREREG_OFI.md).

## 1. Full-market (SIP) data instead of IEX
| | Value |
|---|---|
| SIP volume / IEX volume (median over 30 symbols) | 28.8x (range 15x to 70x): IEX is about 3.5% of the market |
| Close price difference (median) | 1.75 bp |
| Volume correlation, bar by bar | 0.76 |
| Signal agreement IEX vs SIP (same bar and side / events on either) | trendline 46%, trend alert 43%, Supertrend 31%, whale bounce 19% |

Even the price-only signal (Supertrend) differs, because IEX bars miss many real highs and lows. Every test was re-run
on SIP (runtime_sip/, reports/sip/). **The conclusions did not change:**
- Paper signals: all dead after costs (213 dead, 40 watching, 0 candidates; Supertrend 15m moved from watching to dead).
- Eyes: trend confirmation does not hold; walls are reached *less* than random prices (now real in all four
  period x timeframe cells); flip partly (range -0.15 daily ATR, then -0.05); whale magnet partly and tiny.
- Level reactions: PWOI first-touch rejection +14.1 pp (interval +1.4 to +25.5, 83 touches, one period) on both feeds;
  whale VAH +3.5 pp on SIP only. With about 44 comparisons, one or two pass by chance.
- Note: the user's TradingView chart is BATS, also a partial feed. The indicator's own volume is partial too.

## 2. HAR baseline (paper 2406.08041)
| Source | Time | HAR gain over plain regression | Passes (>= 2%, interval > 0) | Positioning on top of HAR |
|---|---|---|---|---|
| IEX | 10:00 | +2.6% (+0.0023 to +0.0093 ATR) | **yes** | -0.2% (no) |
| SIP | 10:00 | +2.4% (+0.0018 to +0.0085 ATR) | **yes** | -0.3% (no) |
| SIP | 11:00 | +0.7% | no | +1.5% (no, under 2%) |
| SIP | 12:00 | -0.1% | no | +1.5% (no, under 2%) |

HAR is the better range baseline at the open. Positioning adds nothing at 10:00 once HAR is in, and about 1.5% at
11:00 and 12:00 (real, under the bar).

## 3. Trend spectrum (paper 2607.19497)
Autocorrelation of volatility-normalised returns (SIP, 30 symbols) is near zero at 5m, **negative at 15m lag 1
(-0.013, interval -0.019 to -0.008)**, mixed at 60m and daily. The trend system's break-even cost per unit turnover
is negative (it loses before costs) at almost every span; the best case, 60m with a 100-bar span, breaks even at
+0.68 bp, far below our 2 bp. **There is no trend alpha at our horizons to capture**; that is why trendline rules lost.

## 4. Order flow imbalance before level touches (paper 1011.6402, PREREG_OFI.md)
2,143 first touches (729 at real levels), 8 liquid symbols, last 60 days, SIP trades and quotes.
| Test | Result |
|---|---|
| H1 real levels: pass rate, OFI toward the level vs not | 69.8% vs 77.9%: **-8.1 pp** (interval -16.5 to +0.6). **Failed**, and the interval rules out the +5 pp the test asked for |
| H2 random prices | +1.5 pp (-5.3 to +8.5): no effect |
| H3 top vs bottom third at real levels | 67.9% vs 74.9% pass |
| By type | PW -19.8 pp and whale VAH -21.9 pp (intervals below zero); others not distinguishable |

Pressure toward a real level *before* the touch, if anything, goes with **less** pass-through: an exhaustion pattern at
PW and whale VAH. It was not the registered hypothesis and the per-type samples are small (85 and 176); it is a new
hypothesis, not a finding.

## What this changes
1. The data feed matters for signals (19-46% agreement) but not for the verdicts: no edge on either feed.
2. Use HAR (with VIX) as the range baseline; positioning stays a small afternoon add-on at best.
3. Stop building trend-following rules at 5m-60m on these stocks: the return spectrum has no trend component.
4. Two candidates for live confirmation only: PWOI first-touch rejection, and the "exhaustion" pattern at PW / VAH.
