"""
The live rule on QuantConnect -- v2, instrumented for cost attribution.

WARNING: This file does NOT run on your machine. Paste it into the
QuantConnect web editor and run a Backtest there. `AlgorithmImports`
does not exist locally. ASCII only -- the QuantConnect save API rejects
emoji and Arabic ("contains invalid characters").

WHAT CHANGED SINCE THE 2025-05-15 -> 2026-05-15 RUN
---------------------------------------------------
That run finished at -5.34% net, 404 orders, win rate 52%, profit/loss
ratio 0.68, fees $854. Decomposed:

    avg win   +0.13% of equity on a ~1.2% position ->  +10.6% of premium
    avg loss  -0.20% of equity                     ->  -16.3% of premium
    expectancy 0.52(+10.6) + 0.48(-16.3)           ->   -2.3% per trade
    185 trades x -0.028% of equity                 ->   -5.2%  (matches)

That run was charged $854 in commission, which the live broker does not
charge -- see ZERO_COMMISSION below. Removing it moves the same run to
about -4.49% net, roughly -1.9% per trade. Worth having, and nowhere
near enough: the remaining -1.9% is split between the BID/ASK ROUND
TRIP and the SIGNAL ITSELF, and the old file could not tell them apart.
Every order was a MarketOrder: bought at the ask, sold at the bid, and
reported only the net.

That distinction decides what to fix, and nothing else can decide it:

    mid-to-mid clearly positive -> the signal works, the spread eats it.
                                   Fix execution: limit orders, tighter
                                   contracts, fewer round trips.
    mid-to-mid also negative    -> no execution work will save this.
                                   The entry rule needs an edge first.

So this version records, for every trade, BOTH the realised return from
fill prices AND the same trade marked mid-to-mid. The report prints the
difference as a single line: spread drag per trade. Read it first.

ALSO IN HERE
------------
  * four bugs fixed (see BUGFIX comments) -- the session-boundary one
    was manufacturing a false VWAP cross on the first bar of every day
  * a spread filter: a contract quoted 12% wide cannot pay for itself
  * per-exit-reason statistics: which exit is destroying the winners
  * every tuning knob in one block, with the old value beside it

The rule, the gates, and the parity discipline are unchanged from v1.
"""
from AlgorithmImports import *

from datetime import timedelta
from itertools import product

RUN_FROM = (2025, 5, 15)
RUN_TO = (2026, 5, 15)

SYMBOLS = ["SPY", "QQQ"]

MIN_DTE, MAX_DTE = 2, 8
NO_ENTRY_AFTER = (14, 0)
FORCE_FLAT = (15, 55)

SCALE_AT, SCALE_FRAC = 0.10, 0.25
HARD_STOP = 0.30
MAX_HOLD_BARS, WINNER_HOLD_BARS = 36, 60
DEAD_BARS, DEAD_MOVE = 8, 0.04

RISK_PCT, LOT_DIVISOR = 0.05, 4
BB_PERIOD, BB_STD = 20, 2.0

# ---- knobs added in v2 -------------------------------------------------
# The live broker charges no commission, so LEAN's default -- which
# models Interactive Brokers -- was billing costs that will never be
# paid. Set False to put the modelled commission back and reproduce the
# -5.34% run exactly.
#
# This zeroes the BROKER's cut only. It does not touch the bid/ask
# spread, which is not a fee, is not refundable by any broker, and is
# the larger cost by roughly five to one in the run above.
ZERO_COMMISSION = True

# The only default that changes behaviour versus the -5.34% run. A
# contract quoted 12% wide starts the trade 6% down and has to make that
# back before the rule is even wrong. Walks outward from the money to the
# first strike that is quoted tightly enough, rather than refusing.
MAX_SPREAD_PCT = 0.08          # v1: no limit, nearest strike taken blind
STRIKE_SEARCH = 3              # how many strikes out to walk before giving up

# Off by default: it changes which trades exist, so turning it on breaks
# comparability with the run above. Turn it on ONLY after the report says
# the midday hours are where the money goes.
BLOCK_LUNCH = False
LUNCH_FROM, LUNCH_TO = (11, 30), (13, 30)

# ---- exit-parameter sweep, v3 ------------------------------------------
# Every exit rule is a function of one thing: the contract's price path
# after entry. So the path is recorded once per trade and every exit
# combination below is replayed over it when the run ends. One backtest
# prices hundreds of combinations, and prices them on THE SAME TRADES --
# no combination gets to look good by trading a different set.
#
# What makes this work is that recording does not stop when the live
# rule exits. The path keeps being sampled to PATH_BARS regardless, so
# "what if it had held longer" is answerable instead of unobservable.
#
# Entry knobs (the %B band, DTE, the time window, MAX_SPREAD_PCT) cannot
# be swept this way -- they change which trades exist, and a trade that
# was never opened has no path. Those need one backtest each. The report
# ends with the order to spend them in.
SWEEP = True
PATH_BARS = 66                 # 5.5 hours, past the 60-bar winner cap

TP_GRID = [None, 0.30, 0.50, 0.80]          # None = no profit target (live)
STOP_GRID = [0.20, 0.30, 0.45]
SCALE_GRID = [None, 0.10, 0.25]             # None = no partial scale
DEAD_GRID = [None, 8, 14]                   # None = never exit for going quiet
HOLD_GRID = [(36, 60), (24, 48), (60, 60)]  # (loser cap, winner cap)
TRAIL_GRID = [None, (0.20, 0.15), (0.35, 0.20)]   # (arm at, give back)
TOP_N = 15
# ------------------------------------------------------------------------


class SessionVwap:
    """
    Cumulative VWAP from the opening bell, reset every session.

    Not LEAN's built-in indicator on purpose: the project's rule builds
    VWAP from the bars of its own timeframe and zeroes it at the bell.
    An indicator with different behaviour changes which signals fire
    without raising anything -- the silent failure this file guards.
    """

    def __init__(self):
        self.day = None
        self.pv = 0.0
        self.vol = 0.0
        self.value = None

    def update(self, bar):
        d = bar.EndTime.date()
        new_day = d != self.day
        if new_day:
            self.day, self.pv, self.vol, self.value = d, 0.0, 0.0, None
        tp = (float(bar.High) + float(bar.Low) + float(bar.Close)) / 3.0
        v = float(bar.Volume)
        self.pv += tp * v
        self.vol += v
        self.value = (self.pv / self.vol) if self.vol > 0 else float(bar.Close)
        return self.value, new_day


class HeikinAshi:
    """Heikin Ashi. Only the colour is consumed, as in the live rule."""

    def __init__(self):
        self.o = None
        self.c = None

    def update(self, bar):
        o, h, l, c = (float(bar.Open), float(bar.High),
                      float(bar.Low), float(bar.Close))
        hc = (o + h + l + c) / 4.0
        ho = (o + c) / 2.0 if self.o is None else (self.o + self.c) / 2.0
        self.o, self.c = ho, hc
        return 1 if hc > ho else -1


class Book:
    """Per-symbol state: everything the entry and exit gates need."""

    def __init__(self, name):
        self.name = name
        self.vwap5 = SessionVwap()
        self.vwap15 = SessionVwap()
        self.ha5 = HeikinAshi()
        self.ha15 = HeikinAshi()
        self.bb = BollingerBands(BB_PERIOD, BB_STD, MovingAverageType.Simple)
        self.trend = 0                 # +1 up . -1 down . 0 neutral
        self.prev_close = None
        self.prev_vwap = None
        # open position
        self.contract = None
        self.is_call = True
        self.ref_px = 0.0              # ask paid, for the exit thresholds
        self.bars = 0
        self.scaled = False
        self.closing = False           # BUGFIX 4: full exit already sent
        # realised cash, filled in from OnOrderEvent
        self.cost = 0.0
        self.proceeds = 0.0
        # shadow accounting: the same trade marked at the mid, both sides
        self.qty0 = 0
        self.sold = 0
        self.mid_cost = 0.0
        self.mid_proceeds = 0.0
        self.entry_spread = 0.0
        self.last_reason = "?"
        self.tracks = []               # price paths being recorded, v3
        # parity counters
        self.bars5 = 0
        self.signals = 0
        self.blocked = 0               # signal fired, no contract taken
        self.wide = 0                  # signal fired, every strike too wide


def replay(ref, path, trends, want, p):
    """
    Re-run one recorded trade under one set of exit parameters.

    `ref` is what was paid, `path` is the contract's price at each 5
    minute bar after that, and the checks below fire in the same order
    `_manage` uses -- stop, target, scale, dead, timer, structure --
    because a different order is a different rule, and the whole point
    is to compare exit rules rather than to invent one.

    Returns the trade's return in percent of premium. Running out of
    path is the forced-flat exit: recording stops at 15:55 anyway.
    """
    if ref <= 0 or not path:
        return None
    left = 1.0                 # fraction of the position still held
    got = 0.0                  # proceeds, in units of one contract
    scaled = False
    peak = 0.0
    dead_bars, dead_move = p["dead"], DEAD_MOVE
    loser_cap, winner_cap = p["hold"]
    trail = p["trail"]

    for i, px in enumerate(path):
        if px <= 0:
            continue
        bars = i + 1
        chg = (px - ref) / ref
        if chg > peak:
            peak = chg

        if chg <= -p["stop"]:
            got += left * px
            left = 0.0
            break
        if p["tp"] is not None and chg >= p["tp"]:
            got += left * px
            left = 0.0
            break
        if p["scale"] is not None and not scaled and chg >= p["scale"]:
            scaled = True
            got += left * SCALE_FRAC * px
            left -= left * SCALE_FRAC
        if trail is not None and peak >= trail[0] and chg <= peak - trail[1]:
            got += left * px
            left = 0.0
            break
        if dead_bars is not None and bars >= dead_bars and abs(chg) < dead_move:
            got += left * px
            left = 0.0
            break
        cap = winner_cap if chg > 0 else loser_cap
        if bars >= cap:
            got += left * px
            left = 0.0
            break
        if p["struct"] and chg > 0 and trends[i] == -want:
            got += left * px
            left = 0.0
            break

    if left > 0.0:
        got += left * path[-1]
    return (got - ref) / ref * 100.0


class ZeroFeeInitializer(BrokerageModelSecurityInitializer):
    """
    Everything the brokerage model normally sets, minus the commission.

    Subclassed rather than replaced with a bare lambda on purpose. A
    lambda initializer silently drops the fill, slippage, settlement and
    margin models along with the fee, and drops the price seeder too --
    option contracts added mid-run would then sit at a price of zero
    until their next bar. Chaining to super() keeps all of that and
    overrides one model.
    """

    def __init__(self, brokerage_model, seeder):
        super().__init__(brokerage_model, seeder)

    def Initialize(self, security):
        super().Initialize(security)
        security.SetFeeModel(ConstantFeeModel(0.0))


class LiveRuleOnRealQuotes(QCAlgorithm):

    def Initialize(self):
        self.SetStartDate(*RUN_FROM)
        self.SetEndDate(*RUN_TO)
        self.SetCash(100000)
        self.SetBenchmark("SPY")

        # Set before any AddEquity / AddOption call so it applies to every
        # security, including the contracts AddOptionContract creates
        # later at entry time.
        if ZERO_COMMISSION:
            self.SetSecurityInitializer(ZeroFeeInitializer(
                self.BrokerageModel, FuncSecuritySeeder(self.GetLastKnownPrices)))

        self.books = {}
        self.by_contract = {}          # option symbol -> book
        self.trades = []               # one dict per closed trade
        self.exits = {}
        self.done_tracks = []          # finished price paths, v3 sweep

        for name in SYMBOLS:
            eq = self.AddEquity(name, Resolution.Minute)
            eq.SetDataNormalizationMode(DataNormalizationMode.Raw)
            opt = self.AddOption(name, Resolution.Minute)
            # Deliberately narrow: the bot buys at the money, and a wide
            # chain only slows the run without being used.
            opt.SetFilter(lambda u: u.Strikes(-STRIKE_SEARCH, STRIKE_SEARCH)
                          .Expiration(MIN_DTE, MAX_DTE))

            self.books[name] = Book(name)

            c5 = TradeBarConsolidator(timedelta(minutes=5))
            c5.DataConsolidated += self._make_on5(name)
            self.SubscriptionManager.AddConsolidator(eq.Symbol, c5)

            c15 = TradeBarConsolidator(timedelta(minutes=15))
            c15.DataConsolidated += self._make_on15(name)
            self.SubscriptionManager.AddConsolidator(eq.Symbol, c15)

            # BUGFIX 5: the 15:55 check inside _manage assumes the bell is
            # at 16:00. On a half day the session ends at 13:00, that bar
            # never arrives, and the position was carried overnight -- the
            # one thing the rule says it never does. About nine sessions a
            # year. BeforeMarketClose knows the real closing time.
            self.Schedule.On(self.DateRules.EveryDay(name),
                             self.TimeRules.BeforeMarketClose(name, 5),
                             self._make_eod(name))

        self.Debug("start=%s end=%s symbols=%s max_spread=%.0f%% commission=%s"
                   % (RUN_FROM, RUN_TO, SYMBOLS, MAX_SPREAD_PCT * 100,
                      "ZERO" if ZERO_COMMISSION else "brokerage default"))

    # ---- trend, from the 15 minute bar ----

    def _make_on15(self, name):
        def handler(_s, bar):
            b = self.books[name]
            v, _ = b.vwap15.update(bar)
            colour = b.ha15.update(bar)
            c = float(bar.Close)
            # Gate two: price, VWAP and colour must AGREE, else neutral.
            if v is not None and c > v and colour > 0:
                b.trend = 1
            elif v is not None and c < v and colour < 0:
                b.trend = -1
            else:
                b.trend = 0
        return handler

    # ---- entry and management, from the 5 minute bar ----

    def _make_on5(self, name):
        def handler(_s, bar):
            b = self.books[name]
            b.bars5 += 1
            v, new_day = b.vwap5.update(bar)
            colour = b.ha5.update(bar)
            b.bb.Update(bar.EndTime, bar.Close)
            c = float(bar.Close)

            # BUGFIX 1: yesterday's 16:00 close was being compared against
            # today's freshly zeroed VWAP, so the 09:35 bar reported a
            # "cross" on most mornings. Those were not signals, they were
            # a session boundary. Dropping the first bar of each day is the
            # whole fix; every later bar is unaffected.
            if new_day:
                b.prev_close, b.prev_vwap = None, None
            prev_c, prev_v = b.prev_close, b.prev_vwap
            b.prev_close, b.prev_vwap = c, v

            # Sampled before _manage, so the trend value here is the one
            # _manage is about to read. Runs whether or not a position is
            # open: a path that stopped at the live exit could not answer
            # "what if it had held longer", which is the main thing the
            # sweep is for.
            self._sample(b, bar)

            if b.contract is not None:
                self._manage(b, bar)
                return
            if not b.bb.IsReady or prev_c is None or prev_v is None or v is None:
                return

            t = bar.EndTime
            hm = (t.hour, t.minute)
            if hm >= NO_ENTRY_AFTER or hm < (9, 35):
                return
            if BLOCK_LUNCH and LUNCH_FROM <= hm < LUNCH_TO:
                return

            up = float(b.bb.UpperBand.Current.Value)
            lo = float(b.bb.LowerBand.Current.Value)
            width = up - lo
            if width <= 0:
                return
            pb = (c - lo) / width

            # The CROSSING bar is a condition, not decoration. Without
            # requiring that the previous close sat on the other side,
            # the rule degenerates to "above/below VWAP" and the trade
            # count explodes -- measured locally at 2,440 trades versus
            # a few hundred.
            call = (b.trend == 1 and colour > 0 and c > v
                    and prev_c <= prev_v and 0.50 <= pb <= 1.50)
            put = (b.trend == -1 and colour < 0 and c < v
                   and prev_c >= prev_v and -0.50 <= pb <= 0.50)
            if not (call or put):
                return

            b.signals += 1
            if not self._enter(b, call):
                # Counted, not swallowed: a signal that never became a
                # position still belongs in the parity check, otherwise
                # the rule looks quieter than it is.
                b.blocked += 1
        return handler

    # ---- end of session ----

    def _make_eod(self, name):
        def handler():
            b = self.books[name]
            if b.contract is not None and not b.closing:
                self._sell(b, "forced_flat")
            # A path must not run across a session boundary either: the
            # next day's prices answer a question nobody asked.
            for tk in b.tracks:
                if tk["px"]:
                    self.done_tracks.append(tk)
            b.tracks = []
        return handler

    # ---- path recording for the sweep ----

    def _sample(self, b, bar):
        if not SWEEP or not b.tracks:
            return
        hm = (bar.EndTime.hour, bar.EndTime.minute)
        still = []
        for tk in b.tracks:
            try:
                sec = self.Securities[tk["sym"]]
                bid, ask = float(sec.BidPrice), float(sec.AskPrice)
            except Exception:                                # noqa: BLE001
                bid, ask = 0.0, 0.0
            if bid > 0:
                tk["px"].append(bid)
                tk["mx"].append((bid + ask) / 2.0 if ask > 0 else bid)
                tk["tr"].append(b.trend)
            # Recording ends where the rule could not have held anyway:
            # the winner cap, or the forced-flat bell.
            if len(tk["px"]) >= PATH_BARS or hm >= FORCE_FLAT:
                self.done_tracks.append(tk)
                if not self.Portfolio[tk["sym"]].Invested:
                    try:
                        self.RemoveSecurity(tk["sym"])
                    except Exception:                        # noqa: BLE001
                        pass
            else:
                still.append(tk)
        b.tracks = still

    # ---- contract selection ----

    def _chain_for(self, name):
        sl = self.CurrentSlice
        if sl is None or sl.OptionChains is None:
            return None
        for kvp in sl.OptionChains:
            try:
                if str(kvp.Key.Underlying.Value).upper() == name:
                    return kvp.Value
            except Exception:                                # noqa: BLE001
                continue
        return None

    def _enter(self, b, is_call):
        chain = self._chain_for(b.name)
        if chain is None:
            return False
        spot = float(self.Securities[b.name].Price)
        if spot <= 0:
            return False
        want = OptionRight.Call if is_call else OptionRight.Put

        # v1 took the nearest strike and traded whatever spread it had.
        # Walk outward instead and stop at the first tightly quoted one:
        # the intent was always at-the-money, and one strike further out
        # with a 5% spread beats the exact strike quoted 15% wide.
        cands = []
        for k in chain:
            if k.Right != want:
                continue
            # Both sides must be quoted. A one-sided contract fills at a
            # price that represents nothing, which is worse than not
            # trading at all.
            bid, ask = float(k.BidPrice), float(k.AskPrice)
            if bid <= 0 or ask <= 0 or ask <= 0.05:
                continue
            cands.append((abs(float(k.Strike) - spot), bid, ask, k))
        if not cands:
            return False
        cands.sort(key=lambda x: x[0])

        best, best_spread = None, 0.0
        any_seen = False
        for _d, bid, ask, k in cands:
            any_seen = True
            mid = (bid + ask) / 2.0
            sp = (ask - bid) / mid if mid > 0 else 1.0
            if sp <= MAX_SPREAD_PCT:
                best, best_spread = k, sp
                break
        if best is None:
            if any_seen:
                b.wide += 1
            return False

        ask = float(best.AskPrice)
        mid_in = (float(best.BidPrice) + ask) / 2.0
        budget = float(self.Portfolio.TotalPortfolioValue) * RISK_PCT / LOT_DIVISOR
        qty = int(budget / (ask * 100.0))
        if qty < 1:
            return False

        self.AddOptionContract(best.Symbol, Resolution.Minute)
        self.MarketOrder(best.Symbol, qty)
        b.contract = best.Symbol
        b.is_call = is_call
        b.ref_px = ask
        b.bars = 0
        b.scaled = False
        b.closing = False
        b.cost = 0.0
        b.proceeds = 0.0
        b.qty0 = qty
        b.sold = 0
        b.mid_cost = qty * mid_in * 100.0
        b.mid_proceeds = 0.0
        b.entry_spread = best_spread
        b.last_reason = "?"
        self.by_contract[best.Symbol] = b

        if SWEEP:
            b.tracks.append({
                "sym": best.Symbol,
                "ref": ask,            # what was actually paid
                "refm": mid_in,        # the same entry marked at the mid
                "want": 1 if is_call else -1,
                "px": [], "mx": [], "tr": [],
            })
        return True

    # ---- exits ----

    def _sell(self, b, reason, frac=1.0):
        held = self.Portfolio[b.contract].Quantity
        if not held:
            return
        n = int(abs(held)) if frac >= 1.0 else max(1, int(abs(held) * frac))

        # Shadow leg: mark this same slice at the mid BEFORE sending the
        # order. The realised leg will come back from the fill at the bid;
        # the gap between the two is the spread, and printing it is the
        # entire point of this version.
        sec = self.Securities[b.contract]
        bid, ask = float(sec.BidPrice), float(sec.AskPrice)
        mid = (bid + ask) / 2.0 if (bid > 0 and ask > 0) else bid
        if mid > 0:
            b.mid_proceeds += n * mid * 100.0
            b.sold += n

        self.MarketOrder(b.contract, -n)
        b.last_reason = reason
        if frac >= 1.0:
            b.closing = True           # BUGFIX 4
        self.exits[reason] = self.exits.get(reason, 0) + 1   # BUGFIX 3

    def _manage(self, b, bar):
        # BUGFIX 4: v1 left b.contract set until the fill came back, so a
        # delayed fill let the next bar re-fire the same exit and send a
        # second sell order.
        if b.closing:
            return
        sec = self.Securities[b.contract]
        bid = float(sec.BidPrice)
        if bid <= 0 or b.ref_px <= 0:
            return
        b.bars += 1
        chg = (bid - b.ref_px) / b.ref_px
        t = bar.EndTime

        if (t.hour, t.minute) >= FORCE_FLAT:
            self._sell(b, "forced_flat")
            return
        if chg <= -HARD_STOP:
            self._sell(b, "hard_stop")
            return
        # Partial scale, once. Kept although the measurement is against
        # it -- the user asked for it explicitly and knows the cost. The
        # per-reason table below now prices that choice directly.
        if not b.scaled and chg >= SCALE_AT:
            b.scaled = True
            self._sell(b, "scale", SCALE_FRAC)
        # Dead trade comes BEFORE the timer: a flat range exits at 8
        # bars and never reaches 36.
        if b.bars >= DEAD_BARS and abs(chg) < DEAD_MOVE:
            self._sell(b, "dead")
            return
        cap = WINNER_HOLD_BARS if chg > 0 else MAX_HOLD_BARS
        if b.bars >= cap:
            self._sell(b, "timer")
            return
        # Structural exit, only while in profit -- as position_manager.
        if chg > 0:
            want = 1 if b.is_call else -1
            if b.trend == -want:
                self._sell(b, "structure")

    # ---- realised cash, read back from the engine ----

    def _close_out(self, b):
        if b.cost <= 0:
            return
        rec = {
            "ret": (b.proceeds - b.cost) / b.cost * 100.0,
            "mid": None,
            "bars": b.bars,
            "reason": b.last_reason,
            "spread": b.entry_spread * 100.0,
        }
        # Only trust the shadow when every contract left through one of
        # our own orders. Expiry and assignment have no mid to mark.
        if b.mid_cost > 0 and b.sold == b.qty0:
            rec["mid"] = (b.mid_proceeds - b.mid_cost) / b.mid_cost * 100.0
        self.trades.append(rec)

    def OnOrderEvent(self, ev):
        """
        Trade returns come from FILL PRICES, not from what this file
        expected the fill to be. That distinction is the entire reason
        for running on QuantConnect instead of locally.
        """
        if ev.Status != OrderStatus.Filled:
            return
        b = self.by_contract.get(ev.Symbol)
        if b is None:
            return
        cash = abs(float(ev.FillQuantity)) * float(ev.FillPrice) * 100.0
        if float(ev.FillQuantity) > 0:
            b.cost += cash
        else:
            b.proceeds += cash
        if b.contract is not None and not self.Portfolio[b.contract].Invested:
            self._close_out(b)
            self.by_contract.pop(b.contract, None)
            b.contract = None
            b.closing = False

    def OnData(self, data):
        # Last-resort guard: expiry or assignment can flatten a position
        # without an exit order of ours.
        #
        # BUGFIX 2: v1 ran this check with no regard for pending orders.
        # Between placing the entry and its fill, Invested is False, so
        # this loop could clear b.contract and drop the book out of
        # by_contract -- and then the fill arrived with nobody to record
        # it. The position stayed open in the portfolio while the
        # algorithm believed it was flat. Requiring a settled cost and no
        # live orders closes that window.
        for b in self.books.values():
            if b.contract is None or b.cost <= 0:
                continue
            if self.Portfolio[b.contract].Invested:
                continue
            if self.Transactions.GetOpenOrders(b.contract):
                continue
            self._close_out(b)
            self.by_contract.pop(b.contract, None)
            b.contract = None
            b.closing = False

    # ---- report ----

    def _score(self, params, key="px", refk="ref"):
        """One exit combination, replayed over every recorded trade."""
        rets = []
        for tk in self.done_tracks:
            r = replay(tk[refk], tk[key], tk["tr"], tk["want"], params)
            if r is not None:
                rets.append(r)
        if not rets:
            return None
        n = len(rets)
        half = n // 2
        wins = [x for x in rets if x > 0]
        gl = -sum(x for x in rets if x <= 0)
        h1 = rets[:half]
        h2 = rets[half:]
        return {
            "n": n,
            "avg": sum(rets) / n,
            "wr": len(wins) / n * 100.0,
            "pf": (sum(wins) / gl) if gl > 0 else float("inf"),
            "h1": (sum(h1) / len(h1)) if h1 else 0.0,
            "h2": (sum(h2) / len(h2)) if h2 else 0.0,
            # Every trade is sized RISK_PCT/LOT_DIVISOR of equity, so the
            # sum of returns scales straight into an equity estimate.
            "net": sum(rets) * RISK_PCT / LOT_DIVISOR,
        }

    def _row(self, label, s, mark=""):
        if s is None:
            self.Debug("#  %-26s (no data)" % label)
            return
        self.Debug("#  %-26s avg=%+6.2f%% pf=%.2f wr=%4.1f%% net=%+6.1f%% "
                   "h1=%+6.2f h2=%+6.2f %s"
                   % (label, s["avg"], s["pf"], s["wr"], s["net"],
                      s["h1"], s["h2"], mark))

    def _sweep(self):
        base = {"tp": None, "stop": HARD_STOP, "scale": SCALE_AT,
                "dead": DEAD_BARS, "hold": (MAX_HOLD_BARS, WINNER_HOLD_BARS),
                "trail": None, "struct": True}

        self.Debug("")
        self.Debug("=" * 70)
        self.Debug("EXIT SWEEP -- same trades, %d recorded paths" % len(self.done_tracks))
        self.Debug("=" * 70)
        self.Debug("#  h1/h2 = first and second half of the year, in order.")
        self.Debug("#  A combination that only works in one half is noise.")
        self.Debug("#")
        self._row("LIVE RULE (baseline)", self._score(base), "<= today")
        self._row("  same, at mid prices", self._score(base, "mx", "refm"))

        # The question asked directly: the scale exit, alone, nothing else
        # moved. Everything to its right in this table is held constant.
        self.Debug("#")
        self.Debug("#  DOES THE +10% SCALE COST MONEY? (only this knob moves)")
        for v in SCALE_GRID:
            p = dict(base)
            p["scale"] = v
            self._row("  scale=%s" % ("off" if v is None else "+%.0f%%" % (v * 100)),
                      self._score(p))

        self.Debug("#")
        self.Debug("#  ONE KNOB AT A TIME (all others at the live values)")
        ofat = [("tp", TP_GRID), ("stop", STOP_GRID), ("dead", DEAD_GRID),
                ("hold", HOLD_GRID), ("trail", TRAIL_GRID),
                ("struct", [True, False])]
        for key, grid in ofat:
            for v in grid:
                p = dict(base)
                p[key] = v
                self._row("  %s=%s" % (key, v), self._score(p))

        # Full cross. Ranked twice on purpose: the best average is the
        # number that flatters, the best worst-half is the number that
        # survives. Read the second one.
        combos = list(product(TP_GRID, STOP_GRID, SCALE_GRID, DEAD_GRID,
                              HOLD_GRID, TRAIL_GRID))
        self.Debug("#")
        self.Debug("#  FULL CROSS -- %d combinations over %d trades"
                   % (len(combos), len(self.done_tracks)))
        scored = []
        for tp, stop, scale, dead, hold, trail in combos:
            p = {"tp": tp, "stop": stop, "scale": scale, "dead": dead,
                 "hold": hold, "trail": trail, "struct": True}
            s = self._score(p)
            if s:
                scored.append((p, s))
        if not scored:
            return
        scored.sort(key=lambda x: -x[1]["avg"])
        self.Debug("#  top %d by average return:" % TOP_N)
        for p, s in scored[:TOP_N]:
            lab = "tp=%s st=%.2f sc=%s dd=%s hd=%s tr=%s" % (
                p["tp"], p["stop"], p["scale"], p["dead"],
                p["hold"][0], p["trail"][0] if p["trail"] else None)
            self._row("  " + lab, s, "OK" if min(s["h1"], s["h2"]) > 0 else "")

        robust = sorted(scored, key=lambda x: -min(x[1]["h1"], x[1]["h2"]))[0]
        self.Debug("#")
        self.Debug("#  BEST BY WORST HALF -- the one to believe:")
        self._row("  %s" % (robust[0],), robust[1])

        pos = sum(1 for _p, s in scored if s["avg"] > 0)
        self.Debug("#")
        self.Debug("#  %d of %d combinations beat zero. With %d trades and"
                   % (pos, len(scored), len(self.done_tracks)))
        self.Debug("#  %d of them searched, the best is partly luck by"
                   % len(scored))
        self.Debug("#  construction. Accept a setting only if BOTH halves")
        self.Debug("#  are positive AND its neighbours in the one-knob")
        self.Debug("#  table are positive too. A lone spike is a fluke.")
        self.Debug("#")
        self.Debug("#  ENTRY knobs cannot be swept here -- they change which")
        self.Debug("#  trades exist. Spend separate backtests in this order:")
        self.Debug("#    1. MAX_SPREAD_PCT  0.05 / 0.08 / 0.12")
        self.Debug("#    2. MIN_DTE,MAX_DTE  2-8 / 5-15 / 10-25")
        self.Debug("#    3. BLOCK_LUNCH      True")
        self.Debug("#    4. the %B band, widened and narrowed")

    def _stats(self, rows, key="ret"):
        vals = [r[key] for r in rows if r.get(key) is not None]
        if not vals:
            return None
        wins = [x for x in vals if x > 0]
        losses = [x for x in vals if x <= 0]
        gl = -sum(losses)
        return {
            "n": len(vals),
            "avg": sum(vals) / len(vals),
            "wr": len(wins) / len(vals) * 100.0,
            "pf": (sum(wins) / gl) if gl > 0 else float("inf"),
        }

    def OnEndOfAlgorithm(self):
        self.Debug("")
        self.Debug("=" * 70)
        self.Debug("PARITY -- read this BEFORE any profit number")
        self.Debug("=" * 70)
        days = max((self.EndDate - self.StartDate).days * 252.0 / 365.0, 1.0)
        tot = 0
        for name, b in self.books.items():
            rate = (b.signals / b.bars5 * 100.0) if b.bars5 else 0.0
            tot += b.signals
            self.Debug("  %-5s bars5=%-7d signals=%-5d rate=%.2f%%  blocked=%d  too_wide=%d"
                       % (name, b.bars5, b.signals, rate, b.blocked, b.wide))
        self.Debug("  signals/day = %.2f     local rule: about 0.9 for SPY+QQQ"
                   % (tot / days))
        self.Debug("  local signal rate = 2.7% of bars")
        self.Debug("  prior QC run  = 0.74/day at -5.34% net, 404 orders,")
        self.Debug("                  with $854 commission charged (-4.49% without)")

        n = len(self.trades)
        if n == 0:
            self.Debug("  NO CLOSED TRADES. A rule that never fires is not")
            self.Debug("  a rule that loses. Stop here and fix the gates.")
            return

        real = self._stats(self.trades, "ret")
        shadow = self._stats(self.trades, "mid")

        self.Debug("")
        self.Debug("#" * 70)
        self.Debug("#  WHERE THE MONEY GOES -- the question v1 could not answer")
        self.Debug("#" * 70)
        self.Debug("#  realised at bid/ask : n=%d avg=%+.2f%% wr=%.1f%% pf=%.2f"
                   % (real["n"], real["avg"], real["wr"], real["pf"]))
        if shadow:
            self.Debug("#  same trades at MID  : n=%d avg=%+.2f%% wr=%.1f%% pf=%.2f"
                       % (shadow["n"], shadow["avg"], shadow["wr"], shadow["pf"]))
            drag = shadow["avg"] - real["avg"]
            self.Debug("#  spread drag         : %.2f%% per trade" % drag)
            self.Debug("#")
            if shadow["avg"] > 0.0:
                self.Debug("#  VERDICT: the signal makes money at the mid and the")
                self.Debug("#  spread takes it. Work on EXECUTION -- limit orders")
                self.Debug("#  at the mid, a tighter MAX_SPREAD_PCT, fewer round")
                self.Debug("#  trips (the scale exit pays the spread twice).")
            else:
                self.Debug("#  VERDICT: negative even at the mid, where execution")
                self.Debug("#  costs nothing. No fill improvement can rescue this.")
                self.Debug("#  The ENTRY needs an edge before anything else is")
                self.Debug("#  worth tuning. Do not spend a run on exit knobs.")
        else:
            self.Debug("#  MID leg unavailable -- trades closed outside our orders.")
        fees = float(self.Portfolio.TotalFees)
        # Prints $0.00 while ZERO_COMMISSION is on. Stated either way so a
        # log read months from now cannot be mistaken for the $854 run.
        self.Debug("#  commission          : $%.2f over %d trades  (model=%s)"
                   % (fees, n, "ZERO" if ZERO_COMMISSION else "brokerage default"))
        self.Debug("#  the spread above is NOT a fee -- no broker waives it")

        self.Debug("#")
        self.Debug("#  BY EXIT REASON -- which door the winners leave by")
        for reason in sorted(set(r["reason"] for r in self.trades)):
            rows = [r for r in self.trades if r["reason"] == reason]
            s = self._stats(rows, "ret")
            bars = sum(r["bars"] for r in rows) / float(len(rows))
            self.Debug("#    %-12s n=%-4d avg=%+7.2f%%  wr=%5.1f%%  bars=%.1f"
                       % (reason, s["n"], s["avg"], s["wr"], bars))
        self.Debug("#  exit orders sent: %s" % (self.exits or "none"))

        sp = [r["spread"] for r in self.trades]
        self.Debug("#  entry spread        : avg %.1f%%  worst %.1f%%"
                   % (sum(sp) / len(sp), max(sp)))

        srt = sorted(r["ret"] for r in self.trades)
        med = (srt[n // 2] if n % 2 else (srt[n // 2 - 1] + srt[n // 2]) / 2.0)
        self.Debug("#")
        self.Debug("#  median        %+.2f%%" % med)
        self.Debug("#  best / worst  %+.1f%% / %+.1f%%" % (srt[-1], srt[0]))
        self.Debug("#  breakeven pf needs win rate %.1f%% -> pf %.2f"
                   % (real["wr"], (100.0 - real["wr"]) / real["wr"]))
        self.Debug("#  end equity    %s" % self.Portfolio.TotalPortfolioValue)
        self.Debug("#" * 70)

        if SWEEP:
            # Paths still being recorded when the run ended are shorter
            # than the rest but still valid: they end where the data ends.
            for b in self.books.values():
                for tk in b.tracks:
                    if tk["px"]:
                        self.done_tracks.append(tk)
                b.tracks = []
            if self.done_tracks:
                self._sweep()
