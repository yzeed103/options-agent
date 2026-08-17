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
- **No LEAN name at module scope except `QCAlgorithm`.** Anything
  evaluated at import time -- a base class, a module-level constant
  built from a LEAN type -- runs before the algorithm exists. If that
  name is not exported by the running LEAN build, the entire module
  fails to import and the cloud reports:

  > Unable to import python module ./cache/algorithm/project/main.pyc.
  > Please ensure that one class inherits from QCAlgorithm.

  That message is misleading. The class does inherit from `QCAlgorithm`;
  the module simply never finished importing, so the loader found no
  classes at all. It names no line and no symbol, so the only way to
  find the cause is to check every name resolved at import time.

  This bit once already: `class ZeroFeeInitializer(
  BrokerageModelSecurityInitializer)` at module scope. It is now built
  inside `_zero_commission()` at runtime, where a missing type degrades
  to a fallback instead of killing the run. Keep it that way -- every
  other LEAN name in the file is referenced inside a method.

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

Two cautions on reading those counters. The per-bar rate is not
comparable: `bars5` counts every 5-minute bar of the session, while the
2.7% figure comes from a narrower local denominator. Compare the
per-day number instead. And signals are only counted while flat —
`_make_on5` hands off to `_manage` and returns before the gates when a
position is open — so the true firing rate is understated by however
often a second signal lands during a hold.

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

## The second run (zero commission, v3)

-3.11% net, 403 orders, win rate 56%, P/L ratio 0.66, $0 fees, drawdown
7.5%, 173 signals (0.69/day). Better than -5.34%, and still reporting:

    NO CLOSED TRADES. A rule that never fires is not a rule that loses.

403 orders had filled. `self.trades` was empty. Going back to the first
screenshot, v1 printed the same line — **every run so far has recorded
zero trades**, and the P&L blocks, the exit table and the entire sweep
have never once executed.

### BUGFIX 7 — why 400 fills recorded nothing

`_enter` placed the order before it registered the book:

```python
self.MarketOrder(best.Symbol, qty)     # LEAN can fill and raise
                                       # OnOrderEvent inside this call
b.contract = best.Symbol
b.cost = 0.0                           # erases the buy if it was credited
self.by_contract[best.Symbol] = b      # too late for the entry fill
```

At entry-fill time `by_contract` had no entry, so `OnOrderEvent`
returned early; and had it matched, `b.cost = 0.0` two lines later would
have wiped the credit anyway. Exit fills arrived after registration, so
`b.proceeds` filled up normally against a `b.cost` of zero — and
`_close_out` opens with `if cost <= 0: return`. Every trade fell through
that guard silently.

It never showed up as a crash because the flow still worked: exits fired,
books reset, trading continued all year. Only the ledger was blind.

Fixed by ordering the entry the only way that is safe with a synchronous
fill: **state first, registration second, order last.** Three defences
were added so this class of fault announces itself instead of hiding:

- `_close_out` falls back to `qty0 * ref_px * 100` when `cost` is zero,
  so a missed buy fill costs precision, not the whole trade.
- the parity block prints `fills seen / unmatched / closes`. A non-zero
  unmatched count means the book keeping is blind again.
- `OnEndOfAlgorithm` no longer returns early when no trades are
  recorded. The sweep reads price paths, not `self.trades`, and had no
  business being skipped by an unrelated accounting failure — but it
  was, which is how a whole run was spent for nothing.

### BUGFIX 6 — 0 DTE lottery tickets

`SetFilter(...Expiration(2, 8))` bounds the *universe*. `AddOptionContract`
adds a contract outside it, and it stays in the chain afterwards, so
already-traded strikes came back once they were expiring that day:

| date | contract | price | qty |
|---|---|---|---|
| 2026-03-16 | QQQ 260316C606 | $0.27 | 46 |
| 2025-12-18 | SPY 251218C679 | $0.67 | 19 |
| 2025-07-17 | QQQ 250717C559 | $1.00 | 12 |
| 2026-01-08 | SPY 260108C690 | $0.87 | 14 |

The size follows from the price: `budget / (ask * 100)` buys 46 contracts
at $0.27. These are same-day lottery tickets, not the 2-8 DTE rule.
`_enter` now checks `k.Expiry` against `self.Time` directly and counts
the rejects as `dte_skips`.

## The third run (v4) — the exits are settled

-3.128% net, 399 orders, 171 closed positions, 172 signals, `unmatched=0`,
`dte_skips=31`. The book keeping works and the 0 DTE tickets are gone.

The report finally ran, and it is decisive:

    realised at bid/ask : n=171 avg=-2.20% wr=46.8% pf=0.79
    same trades at MID  : n=171 avg=-1.05% wr=50.3% pf=0.90
    spread drag         : 1.15% per trade

**Negative at the mid**, where execution costs nothing. The sweep then
put a number on how much of that exits could recover: **0 of 972
combinations beat zero.** Not the best one, not the most robust one —
none.

Notable results inside the sweep:

| knob | result | reading |
|---|---|---|
| `scale=off` | -3.07% vs -3.27% | the scale costs ~0.2%/trade |
| `tp=0.3 / 0.5 / 0.8` | -4.51 / -4.08 / -4.27% | profit targets make it **worse** |
| `trail=(0.2,0.15)` | -3.80% | trailing stops make it **worse** |
| `hold=(24,48)` | -2.43% | shorter holds help, not enough |
| `dead=14` | -2.84% | ditto |

The targets and trailing stops deserve comment because they refute an
obvious hypothesis. The MFE column shows trades routinely giving back
large open gains, which argues for capping the upside. But best/worst
is **+440.7% / -46.2%**: one October trade returned 440%, and every rule
that caps the right tail loses more than it saves. The giveback is real;
the cure is worse.

Two more things the run exposed:

- **The 56% win rate on the Overview is not the position win rate.**
  QuantConnect counts each exit leg as a trade, and the +10% scale
  produces one guaranteed winning leg per scaled position. Per closed
  position the rate is **46.8%**.
- **One trade carries the year.** 2025-10-10 SPY 251013P669, $2.30 ->
  $14.62, +$5,068 including its scale leg, against a -$3,128 year.
  Without it the year is about -8.2%.

## v5 — measuring the entry instead

Exits are answered, so `_edge()` asks the only question left: does the
**underlying** move the signal's way? No spread, no theta, no strike, no
expiry — just SPY and QQQ after a signal, in basis points, at horizons
of 3/6/12/24/36 bars.

The comparison is the whole point. A market that drifts up makes every
call look right without the rule contributing anything, so each horizon
also reports the unconditional drift over the same window and the same
call/put mix, and the edge is the difference. Validated offline on four
synthetic series: a uniform uptrend with all-call signals reports
`hit=100%` and `edge=+0.00` — exactly the trap the baseline exists to
catch — while signals planted before real jumps report `edge=+16.8bp`.

Scale for reading it: an ATM 2-8 DTE option runs near 0.5 delta on a
~$600 underlying at ~$3 of premium, so **1bp of underlying is worth
roughly 1% of premium**. The measured spread is 1.15% per trade, so an
edge below about 1.2bp cannot pay for the trade no matter what the exits
do.

## The v5 run — the entry is measured

Identical trading to v4 by design (v5 changed only measurement), and the
numbers confirm it: -3.128% net, 399 orders, 171 closed, `unmatched=0`.

    #  bars=3   n=172  sig= -1.68 mkt= +0.01 edge= -1.69 hit=47.1%
    #  bars=6   n=172  sig= -2.41 mkt= +0.02 edge= -2.43 hit=44.2%
    #  bars=12  n=172  sig= -5.13 mkt= +0.04 edge= -5.17 hit=44.2%
    #  bars=24  n=172  sig= -6.81 mkt= +0.07 edge= -6.88 hit=45.9%
    #  bars=36  n=155  sig= -4.51 mkt= +0.06 edge= -4.56 hit=46.5%

The market drift is +0.01 to +0.07bp — nil. The entire effect is the
rule, and the rule is not merely edgeless: it is **negative on every
horizon and monotone out to two hours**. Random selection wanders around
zero; this does not.

The mechanism is ordinary. The rule buys the VWAP *breakout* in the
trend direction, and intraday VWAP crossings on index ETFs are
well-known for failing and reverting. It is buying the moment before the
snap-back.

Size of it: at ~1bp per 1% of premium, -5bp at an hour is about -5% of
premium per trade, against a 1.15% spread. That is why no exit rule
helped — the exits were being asked to repair a position that was
structurally wrong from the entry bar.

Two caveats, both load-bearing:

- **About 2 sigma.** Five-minute SPY bars run ~10bp, so a 12-bar window
  is ~35bp and the standard error over 172 signals is ~2.7bp. -5.17bp is
  roughly 1.9 sigma. The five horizons are nested windows, not five
  independent confirmations. Suggestive, not settled.
- **Found in-sample.** The sign was measured on 2025-05..2026-05.
  Inverting the rule and re-running that same year proves nothing.

### BY EXIT REASON, now that BUGFIX 8 lets it report

    dead         n=83   avg=  +1.43%  wr= 60.2%  bars=13.3
    forced_flat  n=7    avg=+101.01%  wr=100.0%  bars=41.3
    hard_stop    n=49   avg= -31.87%  wr=  0.0%  bars=11.3
    scale        n=7    avg= +12.58%  wr=100.0%  bars=5.7
    structure    n=13   avg= +20.27%  wr=100.0%  bars=28.2
    timer        n=12   avg=  +0.64%  wr= 25.0%  bars=44.2

49 stop-outs at -31.87% is -1,562 points; every other door together is
+1,185. Net -377 over 171 trades = -2.20%, matching the headline
exactly. The stop is where the loss is *realised*, not where it is
caused — moving it to -20% only recovers 0.34%/trade, because the
underlying really is moving the wrong way.

`scale n=7` is a quirk worth knowing: `max(1, int(1 * 0.25)) == 1`, so a
one-contract position is closed **entirely** by the "partial" scale at
+10%. It only bites the expensive contracts, which are the ones sized
down to a single lot.

## What INVERT is for

`INVERT = True` fades the cross instead of following it — one line, the
opposite side of the same signal. If the measured sign is real it is
worth roughly +5bp, or +5% of premium, against a 1.15% spread.

The discipline that makes it worth a backtest rather than a fantasy:
run it on **2023-05..2025-05**, years the edge was never measured on.
Only if it survives there is it a strategy rather than a description of
one year of SPY and QQQ.

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
6. **0 DTE contracts.** See above.
7. **Invisible entries.** See above.
8. **Exit reasons.** BUGFIX 7 again, one method over. `_sell` set
   `b.last_reason` *after* `MarketOrder`, and the fill happens inside
   that call, so `_close_out` read the previous value. 228 exits across
   six reasons logged as `"?"` (114, never scaled) and `"scale"` (57,
   had scaled) -- the table was reporting whether a position had scaled,
   not which door it left by. Reason and counter now precede the order.

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
