# QuantConnect backtest of the live rule

`main.py` is pasted into the QuantConnect web editor and run there. It
does not run locally: `AlgorithmImports` only exists inside LEAN.

Two constraints on that file, both learned the hard way:

- **ASCII only.** The save API rejects Arabic and emoji with "contains
  invalid characters".
- **Under 32,000 characters.** The save API rejects anything larger
  ("File main.py not saved. It exceeds the maximum size of 32000
  characters"). This is why the long-form notes live here instead of in
  the module docstring. If the file grows past the limit again, cut
  comments, never code.

## Why run it on QuantConnect at all

The local engine has no historical bid/ask. It prices the mid from the
archive and subtracts a modelled spread. Even after the 2026-08-16
rebuild -- per symbol, per session third, per distance from the money,
from 7.9M OPRA points -- it is still a model.

LEAN fills against the contract's actual quote in that minute, and this
file reads the **fill price** back out of `OnOrderEvent` rather than
computing what it thinks the fill should have been.

## Parity comes before profit

This is a second implementation of a rule that already exists in
`src/strategy.py`. The worst bug in this project's history had exactly
that shape: the backtest measured a crossover rule while the bot traded
`strategy.evaluate`. Two copies drift apart silently, and the
measurement then describes a strategy nobody runs.

So the report leads with **signal counts**, not profit:

    local rule: a signal on 2.7% of bars, 3.49/day across 8 symbols
                -> roughly 0.9/day across SPY+QQQ alone

A rate far from that means the rules diverged and the P&L below is
describing something else entirely.

## The run that motivated the current version

2025-05-15 -> 2026-05-15, SPY + QQQ:

| | |
|---|---|
| net | -5.34% |
| total orders | 404 (~185 trades) |
| win rate | 52% |
| profit/loss ratio | 0.68 |
| commission | $854 |
| drawdown | 7.9% |

Decomposed:

    avg win   +0.13% of equity on a ~1.2% position ->  +10.6% of premium
    avg loss  -0.20% of equity                     ->  -16.3% of premium
    expectancy 0.52(+10.6) + 0.48(-16.3)           ->   -2.3% per trade
    185 trades x -0.028% of equity                 ->   -5.2%  (matches)

Two things follow. The equity curve falls in almost a straight line, so
this is a steady cost leak, not a risk event. And commission is one
sixth of it -- removing it (the live broker charges none) moves the run
to about -4.49%, roughly -1.9% per trade. The rest is spread and signal.

At a 52% win rate, breakeven needs a profit/loss ratio of 0.92. The run
came in at 0.68: winners are being clipped, losers are not.

## What the report answers

**1. `WHERE THE MONEY GOES`** -- every trade is recorded twice: realised
from fill prices, and the same trade marked mid-to-mid. The difference
is spread drag per trade. This decides where the work goes:

- mid-to-mid positive -> the signal works and the spread eats it. Fix
  execution: limit orders at the mid, tighter `MAX_SPREAD_PCT`, fewer
  round trips (the scale exit pays the spread twice).
- mid-to-mid negative -> execution costs nothing at the mid and it still
  loses. No fill improvement can rescue it; the entry needs an edge
  before any exit knob is worth tuning.

**2. `BY EXIT REASON`** -- count, average return, win rate and average
hold per exit door, so the 0.68 ratio can be traced to the exit
responsible.

**3. `EXIT SWEEP`** -- 972 exit combinations replayed over the recorded
paths. Exits are a function of the contract's price path after entry, so
one backtest prices all of them, scored on **identical trades**. No
combination can look better merely by trading a different set.

Recording deliberately continues after the live rule exits, out to
`PATH_BARS` or the closing bell. A path truncated at the real exit
cannot answer "what if it had held longer", which is most of the
question.

The sweep is ranked twice: by average (flatters) and by worst half of
the year (survives). With ~185 trades and 972 settings the top row is
partly luck by construction. Accept a setting only when both halves are
positive **and** its neighbours in the one-knob table agree. A lone
spike is a fluke.

## Entry knobs need their own runs

They change which trades exist, and a trade that was never opened has no
path to replay. One backtest each, in this order:

1. `MAX_SPREAD_PCT` -- 0.05 / 0.08 / 0.12
2. `MIN_DTE, MAX_DTE` -- 2-8 / 5-15 / 10-25
3. `BLOCK_LUNCH` -- True
4. the %B band, widened and narrowed

## Bugs fixed since v1

1. **Session boundary.** The first 5m bar of each day compared
   yesterday's 16:00 close against a freshly zeroed VWAP, so the 09:35
   bar reported a "cross" most mornings. Those were session boundaries,
   not signals.
2. **Orphaned entries.** The `OnData` flatness sweep ran without
   checking for pending orders. Between placing an entry and its fill,
   `Invested` is False, so the book was dropped from `by_contract` and
   the fill arrived with nobody to record it -- the position stayed open
   while the algorithm believed it was flat.
3. **Exit counter.** Incremented even when no quantity was sold.
4. **Duplicate exits.** A full exit could be re-sent on the next bar
   while its fill was still in flight.
5. **Half days.** The forced-flat exit tested for a 15:55 bar, which
   never arrives when the session ends at 13:00, so the position was
   carried overnight about nine sessions a year. Replaced with a
   `BeforeMarketClose` schedule.

## Other changes

- **Zero commission.** Applied through a
  `BrokerageModelSecurityInitializer` subclass, not a lambda: a lambda
  drops the fill, slippage, settlement and margin models along with the
  fee, and the price seeder too, leaving contracts added at entry priced
  at zero until their next bar. Set `ZERO_COMMISSION = False` to restore
  the default model and reproduce the -5.34% run.
- **Spread filter.** Contract selection walks outward from the money to
  the first strike quoted inside `MAX_SPREAD_PCT` instead of taking the
  nearest one blind. A contract quoted 12% wide starts the trade 6%
  down. This is the only default that changes trading behaviour.

## The rule itself

Mirrors `src/strategy.py` and the six gates in `CLAUDE.md`:

```
trend  15m : close vs session VWAP, and Heikin Ashi colour, agreeing
entry   5m : the bar CROSSES VWAP, HA colour agrees, %B inside band
contract   : 2-8 DTE, closest to the money, quoted on both sides
context    : no entry after 14:00 ET, one position per symbol
exits      : +10% scale 25% . hard stop -30% . 36 bars (60 if up)
             . dead trade 8 bars . forced flat 15:55 ET
sizing     : 5% / 4 = 1.25% of equity per trade
```

The crossing condition is load-bearing. Without requiring the previous
close on the other side of VWAP, the rule degenerates to "above/below
VWAP" and the trade count explodes -- 2,440 trades locally versus a few
hundred.

## What this cannot settle

QuantConnect's data ends 2026-05-18 and clamps later requests silently.
One year is four quarters, not the nine the adoption bar asks for. And
~185 trades over two symbols cannot distinguish -2.3% per trade from
zero with confidence -- the run is a diagnostic, not a verdict on
profitability.
