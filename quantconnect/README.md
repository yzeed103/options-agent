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

## v6 — the sign flip, measured

Two runs settled it.

**Run A, INVERT on, 2023-05..2025-05.** The inverted rule's edge came
back **negative** on every horizon, -0.23 to -5.46bp. Since INVERT
negates the traded direction, that puts the *original* rule near
**+5.46bp** in those years. Deduction, not measurement — the P&L of an
inverted run is not comparable (with `b.trend` opposite the position by
construction, the structural exit fires on the first profitable bar:
279 of 430 exits at 2.6 bars). Only the edge number transfers.

**Run B, INVERT off, 2023-05..2025-05.** The confirmation:

    #  bars=3   edge= +0.18 hit=53.1%
    #  bars=6   edge= +2.72 hit=55.5%
    #  bars=12  edge= +1.19 hit=49.7%
    #  bars=24  edge= +5.45 hit=53.0%
    #  bars=36  edge= +5.25 hit=51.5%

**+5.45bp measured against +5.46bp deduced.** Net +5.024% over 944
orders, 393 closed, `unmatched=0`, 57% win rate, PF 0.87. Realised
+1.14%/trade, +2.47% at the mid, 1.33% spread drag. 156 of 972 exit
combinations beat zero, against 0 of 972 in 2025-26.

So the same rule, unchanged, is **+5.45bp in 2023-05..2025-05 and
-6.88bp in 2025-05..2026-05**. The edge did not decay; it reversed.

Three things follow.

- The exit sweep's disagreements between eras were never noise about
  exits — they were two different underlying processes. `scale=off` is
  worth +0.87%/trade here and is the first knob to point the same way
  in both sweeps besides `HARD_STOP`.
- The best-by-worst-half combination has **both halves alive and
  nearly equal** (+2.07 / +2.05), which is the robustness bar set
  before the run, not after it.
- None of it is tradeable. The user trades in the era where the sign is
  **negative**. A rule that reverses is more dangerous than one that
  merely fails, because a live run in the wrong era loses at the same
  rate the backtest wins. The missing piece is a regime detector
  validated on a period used for neither of the two runs above.

## v7 — asking whether the flip was visible in advance

v6 established *that* the rule reverses. Averaging the two eras
together would only produce a number near zero that describes neither,
so v7 runs **2023-05..2026-05 in one pass** and adds three probes that
read prices and never place an order. None of them can be flattered by
an exit knob.

### BY PERIOD

Signals bucketed into 182-day blocks, edge at 24 bars. A single
three-year average hides a reversal; blocks cannot. This answers *when*
the sign changed and whether it changed **once** — a clean step is a
regime; a sign that flickers block to block is a rule with no stable
direction at all, and that reading is fatal in a way one flip is not.

### REGIME PROBE

The question that decides whether any of this is tradeable: **was the
flip visible before it was traded?**

At each signal, take the mean edge of the previous 20 signals *whose
24-bar window had already closed by that bar*, and split the signals
into two buckets by the sign of that number. It is the rule's own
recent record, and nothing else — no new indicator to fit.

The no-lookahead boundary is exactly `j + k <= i`, and it is
unit-tested three ways: the output matches a brute-force
recomputation; multiplying every bar strictly after a signal leaves
that signal's regime value unchanged; and a window closing *at* the
signal bar counts while one closing a bar later does not. The signal
bar's own close is read, which is legitimate — the entry rule reads it
too.

If the two buckets do not separate, then no detector built from the
rule's own history can save it, and the file is closed. If they do
separate, that is a **hypothesis, not a filter** — it was measured on
the same years it was found in. The bar for trading it is a third
period neither run has touched.

### TRADES THAT GOT A TIGHT QUOTE

Realised return of trades bucketed by entry spread. Deliberately *not*
labelled as a tighter `MAX_SPREAD_PCT`: lowering the cap makes `_enter`
buy a **further strike**, it does not skip the trade, so this is not a
re-simulation of that change. It answers the narrower question it can
answer honestly — were the tightly-quoted trades the better ones? With
1.33%/trade going to the spread against a +2.47% mid-price edge, that
is worth knowing before touching execution.

### Changes to the rule and the report

- **The +10% scale is off** (`SCALE_AT = None`). It is the only exit
  knob that costs money in *both* eras' sweeps — +0.87%/trade in
  2023-25 — and switching it off matched the best-by-worst-half
  combination on its own, which is what a real effect looks like next
  to fitted ones.
- **The 972-combination full cross is gone.** Each era named a
  different winner, which is what fitting noise looks like; over a run
  that *contains* the reversal, a "best" combination is an average of
  two opposite regimes and means nothing. One-knob-at-a-time survives,
  and its `h1`/`h2` columns now split roughly on the flip itself.
- **`tp` and `trail` are gone from the sweep.** Profit targets and
  trailing stops hurt in both eras. Settled; `replay` still supports
  them for the baseline.
- `_stats` absorbed `_score`; `_edge`, `_by_period` and `_by_regime`
  share `_fwd`, so there is one definition of "forward return in the
  signal direction" rather than three.

## The v7 run — 2023-05..2026-05, and what it settles

Net +4.001% over three years. **CAR 1.314%, annual sd 6.0%, Sharpe
-0.737** — QC's own Sharpe implies a risk-free rate of 5.74%, so the
strategy **underperformed cash by 4.4%/year**, with a 7.1% drawdown
that took 262 days to recover. 1,132 orders, 566 closed, `unmatched=0`.

### BY PERIOD — a step, not a flicker

    2023-02-05  n=39   edge= +1.19  (+0.1 sigma)
    2023-08-06  n=103  edge= +4.61  (+0.9)
    2024-02-04  n=99   edge= +0.49  (+0.1)
    2024-08-04  n=97   edge=+11.82  (+2.2)
    2025-02-02  n=97   edge= +4.76  (+0.9)
    2025-08-03  n=81   edge= -7.25  (-1.2)
    2026-02-01  n=56   edge=-11.80  (-1.7)

Five positive blocks, then two negative. It does **not** flicker, which
was the fatal reading and is now ruled out. Two caveats keep this from
being proof. A 24-bar SPY window is ~53bp, so the standard error on a
97-signal block is ~5.4bp: **only one block clears 2 sigma**, and the
shape carries the finding, not the levels. And a single changepoint in
seven blocks has a crude p of roughly 0.05-0.09 — before allowing that
the split was already known when the chart was drawn, which makes this
the same data re-plotted rather than independent confirmation.

What *is* new: the flip sits between the block starting 2025-02 and the
one starting 2025-08, so it is **later than the 2025-05 split assumed
earlier**, and the most recent block is the worst of the seven, on the
lowest hit rate (35.7%).

### REGIME PROBE — failed the pre-registered test

    was working  n=295  edge= +3.95  hit=49.2%
    was failing  n=237  edge= -1.21  hit=51.5%

The buckets point the right way and separate by 5.16bp — against a
standard error of 4.60bp. **1.12 sigma. That is not separation.**

The stated rule before the run was that if the buckets do not separate,
no detector built from the rule's own history can save it. They did not.

The failure mode is visible and structural, not a tuning problem. 573
signals over ~750 sessions across two books is ~0.38 signals/book/day,
so a 20-signal memory is ~52 sessions — about **2.5 months**, plus the
24-bar maturity lag. The detector is asked to catch a regime change
roughly a quarter after it starts, inside a bad era that lasts about
nine months. That is why `was failing` reads -1.21 while the period
table reads -7 to -12 over the same span: **the detector is late, and
it dilutes the bad era with the tail of the good one.** Shortening the
memory would fix the lag and fit the noise; that trade is not worth
making on data already used twice.

### Only one exit knob survives both halves

`h1`/`h2` split roughly on the flip in this run, so the both-halves
test is now a cross-regime test.

| knob | avg | h1 | h2 | verdict |
|---|---|---|---|---|
| `scale=None` vs `0.10` | +0.54 vs -0.13 | +0.65 | +0.69 | **two-sided — holds** |
| `stop=0.20` vs `0.30` | +0.54 vs +0.22 | +0.75 | -0.11 | one-sided |
| `struct=False` | +1.09 vs +0.54 | -0.05 | +1.16 | one-sided |
| `hold=(60,60)` | +0.58 vs +0.54 | 0.00 | +0.08 | nil |
| `dead=None` | +0.32 vs +0.54 | +0.32 | -0.75 | one-sided |

**`scale=off` is the only change that improves both halves**, and it is
already in. `struct=False` looks like the biggest number on the sheet
and is exactly the trap the h1/h2 columns exist to catch — it is worth
+1.16 in the second half and -0.05 in the first. `HARD_STOP = 0.20`
does not survive this run either; it stays because it still has the
best average, not because it is confirmed.

### Two hypotheses killed

**Tightening the spread cap would hurt.** Entry spread averages 1.0%,
and 529 of 566 trades were already inside 2%. The 37 trades quoted
wider than 2% averaged **+12.9%** each — going from `<=2%` to `<=8%`
moves the book from -0.23% to +0.63% per trade. Wide quotes mark the
volatile moments the winners come from. The `MAX_SPREAD_PCT = 0.08` cap
stays where it is.

**The P&L is carried by 10% of trades.** `timer` (n=35, +87.28%) and
`forced_flat` (n=22, +81.25%) are worth +4,842 points; the other 509
trades are worth **-4,485**. Best trade +535.7%. Any conclusion drawn
from the average is a conclusion about a handful of trades.

### The number that decides it

Spread drag is 1.37%/trade against a realised +0.63%, so execution
takes two thirds of the gross. But fixing execution entirely does not
save it: **at mid prices — zero spread, perfect fills — the sweep pays
+15.5% over three years, which is 4.92%/year against cash at 5.74%.**

The strategy does not clear the risk-free rate in its *best possible*
execution, over a window that includes its good era. QC also estimates
strategy capacity at **$14,000**.

### The only honest next step

Everything above was measured on years already used. One test remains
that nothing has touched: **run 2020-05..2023-05** — COVID recovery,
2021, the 2022 bear market — and read only `BY PERIOD` and `REGIME
PROBE`. If the step structure and the bucket ordering both reappear on
data neither run has seen, the regime hypothesis survives on its own
merits. If they do not, the file closes.

**Applied.** `main.py` now runs `2020-05-15 .. 2023-05-15` — adjacent
to the previous window, no overlap, so nothing in it has been used to
form any hypothesis above.

What each outcome means, written down **before** the run so the
reading cannot be chosen afterwards:

| BY PERIOD | REGIME PROBE | reading |
|---|---|---|
| step, one changepoint | buckets separate, same order | the hypothesis survives its first real test |
| step | buckets do not separate | regimes are real but **not detectable in advance** — the rule is untradeable, not merely unprofitable |
| flickers block to block | either | no stable direction; the 2023-26 step was an artifact and the file closes |
| all one sign | either | no reversal in this era at all; the flip is not a recurring feature |

The P&L of this run is **not** evidence either way. It will be read
and reported, but the mid-price ceiling of 4.92%/yr against 5.74% cash
already settles the capital question for the era we measured, and one
more window does not overturn that by being profitable.

Caveat: if signals come back at zero or the run errors on missing
data, that is options coverage for 2020-2022 on the account's data
tier, not a finding.

## v8 — where profit could still be, honestly ranked

### A methodological error, mine

`STOP_GRID = [0.20, 0.30, 0.45]` returned its best at **0.20**.
`HOLD_GRID = [(36,60), (24,48), (60,60)]` returned its best at
**(60,60)**. Both winners sat at the **boundary of the grid**, in both
the 2023-25 and 2023-26 sweeps. A grid whose optimum is at its own
edge has not found an optimum — it has run out of room, and I read the
edge as an answer twice.

Extended in the direction the data pointed:

    STOP_GRID = [0.10, 0.15, 0.20, 0.30]
    DEAD_GRID = [None, 4, 6, 8, 14]
    HOLD_GRID = [(36,60), (24,48), (60,60), (36,78), (24,78), (78,78)]
    PATH_BARS = 78          # a full session; 66 could not hold 78

`DEAD_GRID`'s optimum was interior (8, between None and 14), so it is
extended only for symmetry, not because it was blocked.

### Why the caps are the most likely place money is hiding

Sorted by holding time, the 2023-26 exits are **monotone**:

| exit | bars | n | avg |
|---|---|---|---|
| `hard_stop` | 7.5 | 223 | -23.52% |
| `dead` | 12.2 | 243 | +0.17% |
| `structure` | 27.4 | 43 | +16.71% |
| `forced_flat` | 38.3 | 22 | +81.25% |
| `timer` | 59.7 | 35 | +87.28% |

The only two exits that pay are the **time-terminal** ones — `timer`
fires at the 60-bar cap and `forced_flat` at the bell. A trade that
survives long enough to hit a clock is worth ~+85%. And the clock it
hits was the top of the grid. `PATH_BARS = 78` now records a full
session so `(78,78)` — hold to the bell — is testable at all.

This is a hypothesis with a mechanism, not a fitted number: a
positively-skewed book wants losers cut fast and winners uncapped, and
both grids were pinned exactly where that would show up.

### EDGE BY ENTRY CONDITION — the new instrument

Every knob touched so far is an **exit**. The exits have now been swept
across two eras and settled: one knob survives. If more profit exists,
it is in **which signals get taken**, and that has never been measured.

The probe buckets the signal's own forward edge — underlying only, no
spread, no exit — by `hour`, `%B` at entry, `side`, and `symbol`.
Exit-independent by construction, so nothing downstream can flatter it.

The ordering here is deliberate and worth stating: this runs on
**2020-05..2023-05, a window nothing has been fitted to**. A bucket
that stands out here can then be checked on 2023-05..2026-05 — data
that already exists and that the filter was not derived from.
Discovery on new data, validation on old. That is the one sequence
that produces a filter worth believing rather than a filter worth
publishing.

A bucket needs roughly **5bp over the rest** to clear the spread, and
**n ≥ 100** before it means anything.

### Removed, because they are settled

- **`tp` and `trail`** are gone from `replay` entirely. Profit targets
  and trailing stops hurt in both eras.
- **The spread-cap table** is gone. It killed its own hypothesis: the
  37 trades quoted wider than 2% averaged +12.9% each, so refusing
  wide quotes would cost money, not save it.
- **`INVERT`** is gone. It existed to infer the 2023-25 edge from an
  inverted run at +5.46bp; the direct measurement then returned
  +5.45bp. A scaffold that has been replaced by the building.

### What this cannot do

Nothing above changes the ceiling already measured. At **mid prices —
zero spread, perfect fills** — the 2023-26 book paid 4.92%/year against
cash at 5.74%. Extending the grids and filtering entries can move the
realised number toward that ceiling; neither raises the ceiling. The
entry probe is the only item here that could, and only if a bucket
separates by more than noise on a window it was not chosen from.

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
