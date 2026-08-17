"""
The live rule on QuantConnect -- v6.

ASCII only, under the 32000-char save limit, no LEAN name at module
scope except QCAlgorithm. See README.md; if it grows, cut comments.

Settled so far: -2.20%/trade realised, -1.05% at the mid, 0 of 972 exit
combinations above zero, and an entry edge of -1.7bp at 3 bars falling
to -6.9bp at 24 against a market drift of +0.07bp. Consistently wrong,
not random -- see INVERT.
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

# LEAN's default models IB and billed $854 the broker never charges.
# The BROKER's cut only, not the spread, which no broker waives.
ZERO_COMMISSION = True

# A contract quoted 12% wide starts the trade 6% down.
MAX_SPREAD_PCT = 0.08          # v1: no limit
STRIKE_SEARCH = 3

# Off: changes which trades exist, breaking comparability.
BLOCK_LUNCH = False
LUNCH_FROM, LUNCH_TO = (11, 30), (13, 30)

# Fade the cross instead of following it: a rule that wrong carries
# information with the sign reversed. TEST ON YEARS THE EDGE WAS NOT
# MEASURED ON -- it was found in 2025-05..2026-05, so re-running that
# same year inverted is circular and looks good either way.
INVERT = False

# Exits are a function of the price path after entry, so paths are
# recorded and every combination replayed at the end: one backtest, all
# of them, on THE SAME TRADES. Recording outlives the live exit.
SWEEP = True
PATH_BARS = 66                 # 5.5 hours, past the 60-bar winner cap

TP_GRID = [None, 0.30, 0.50, 0.80]          # None = no target (live rule)
STOP_GRID = [0.20, 0.30, 0.45]
SCALE_GRID = [None, 0.10, 0.25]             # None = no partial scale
DEAD_GRID = [None, 8, 14]
HOLD_GRID = [(36, 60), (24, 48), (60, 60)]  # (loser cap, winner cap)
TRAIL_GRID = [None, (0.20, 0.15), (0.35, 0.20)]   # (arm at, give back)
TOP_N = 15


class SessionVwap:
    """VWAP from the bell, reset each session. Not LEAN's built-in:
    a different one changes which signals fire."""

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
        self.trend = 0                 # +1 up, -1 down, 0 neutral
        self.prev_close = None
        self.prev_vwap = None
        # open position
        self.contract = None
        self.is_call = True
        self.ref_px = 0.0              # ask paid, for the exit thresholds
        self.bars = 0
        self.scaled = False
        self.closing = False           # BUGFIX 4: full exit already sent
        # realised cash
        self.cost = 0.0
        self.proceeds = 0.0
        # shadow: same trade marked at the mid
        self.qty0 = 0
        self.sold = 0
        self.mid_cost = 0.0
        self.mid_proceeds = 0.0
        self.entry_spread = 0.0
        self.last_reason = "?"
        self.tracks = []               # price paths being recorded
        # signal-edge probe: the UNDERLYING, not the option
        self.px5 = []
        self.day5 = []
        self.sigs = []                 # (bar index, +1 call / -1 put)
        # parity counters
        self.bars5 = 0
        self.signals = 0
        self.blocked = 0               # signal fired, no contract taken
        self.wide = 0                  # every strike too wide


def replay(ref, path, trends, want, p):
    """
    Re-run one recorded trade under one set of exit parameters, in
    _manage's order -- a different order is a different rule. Returns
    percent of premium; running out of path is the forced flat.
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


class LiveRuleOnRealQuotes(QCAlgorithm):

    def Initialize(self):
        self.SetStartDate(*RUN_FROM)
        self.SetEndDate(*RUN_TO)
        self.SetCash(100000)
        self.SetBenchmark("SPY")

        if ZERO_COMMISSION:
            self._zero_commission()

        self.books = {}
        self.by_contract = {}          # option symbol -> book
        self.trades = []               # one dict per closed trade
        self.exits = {}
        self.done_tracks = []          # finished price paths
        self.oe_seen = self.oe_lost = self.closes = self.dte_skips = 0

        for name in SYMBOLS:
            eq = self.AddEquity(name, Resolution.Minute)
            eq.SetDataNormalizationMode(DataNormalizationMode.Raw)
            opt = self.AddOption(name, Resolution.Minute)
            opt.SetFilter(lambda u: u.Strikes(-STRIKE_SEARCH, STRIKE_SEARCH)
                          .Expiration(MIN_DTE, MAX_DTE))

            self.books[name] = Book(name)

            c5 = TradeBarConsolidator(timedelta(minutes=5))
            c5.DataConsolidated += self._make_on5(name)
            self.SubscriptionManager.AddConsolidator(eq.Symbol, c5)

            c15 = TradeBarConsolidator(timedelta(minutes=15))
            c15.DataConsolidated += self._make_on15(name)
            self.SubscriptionManager.AddConsolidator(eq.Symbol, c15)

            # BUGFIX 5: the 15:55 test assumes a 16:00 bell; half
            # days held the position overnight, ~9 times a year.
            self.Schedule.On(self.DateRules.EveryDay(name),
                             self.TimeRules.BeforeMarketClose(name, 5),
                             self._make_eod(name))

        self.Debug("start=%s end=%s %s spread=%.0f%% comm=%s INVERT=%s"
                   % (RUN_FROM, RUN_TO, SYMBOLS, MAX_SPREAD_PCT * 100,
                      "ZERO" if ZERO_COMMISSION else "default", INVERT))

    def _zero_commission(self):
        """
        Drop the broker's cut, keep what the brokerage model sets.

        Built at runtime, NOT as a module-level subclass: subclassing
        a LEAN C# type runs at import, and an unexported name there
        kills the module. A lambda would drop the seeder too.
        """
        seeder = FuncSecuritySeeder(self.GetLastKnownPrices)
        base = None
        try:
            base = BrokerageModelSecurityInitializer(self.BrokerageModel, seeder)
        except Exception:                                    # noqa: BLE001
            self.Debug("note: no BrokerageModelSecurityInitializer available")

        def init(security):
            try:
                if base is not None:
                    base.Initialize(security)
                else:
                    seeder.SeedSecurity(security)
            except Exception:                                # noqa: BLE001
                pass
            security.SetFeeModel(ConstantFeeModel(0.0))

        self.SetSecurityInitializer(init)

    # ---- trend, 15 minute bar ----

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

    # ---- entry and management, 5 minute bar ----

    def _make_on5(self, name):
        def handler(_s, bar):
            b = self.books[name]
            b.bars5 += 1
            v, new_day = b.vwap5.update(bar)
            colour = b.ha5.update(bar)
            b.bb.Update(bar.EndTime, bar.Close)
            c = float(bar.Close)
            b.px5.append(c)
            b.day5.append(bar.EndTime.date().toordinal())

            # BUGFIX 1: yesterday's close vs a zeroed VWAP made the
            # 09:35 bar report a "cross" most mornings.
            if new_day:
                b.prev_close, b.prev_vwap = None, None
            prev_c, prev_v = b.prev_close, b.prev_vwap
            b.prev_close, b.prev_vwap = c, v

            # Before _manage: same trend value it reads. Open or flat.
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

            # The CROSSING bar is a condition: without it the rule is
            # just "above/below VWAP", 2,440 trades instead of hundreds.
            call = (b.trend == 1 and colour > 0 and c > v
                    and prev_c <= prev_v and 0.50 <= pb <= 1.50)
            put = (b.trend == -1 and colour < 0 and c < v
                   and prev_c >= prev_v and -0.50 <= pb <= 0.50)
            if not (call or put):
                return
            # Mutually exclusive (trend +1 vs -1), so negating flips.
            if INVERT:
                call = not call

            b.signals += 1
            b.sigs.append((len(b.px5) - 1, 1 if call else -1))
            if not self._enter(b, call):
                # A signal that never became a position still
                # belongs in the parity check.
                b.blocked += 1
        return handler

    def _make_eod(self, name):
        def handler():
            b = self.books[name]
            if b.contract is not None and not b.closing:
                self._sell(b, "forced_flat")
            # No path may cross a session boundary either.
            for tk in b.tracks:
                if tk["px"]:
                    self.done_tracks.append(tk)
            b.tracks = []
        return handler

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

        # One strike out at 5% beats this strike quoted 15% wide.
        cands = []
        today = self.Time.date()
        for k in chain:
            if k.Right != want:
                continue
            # BUGFIX 6: AddOptionContract keeps a contract in the
            # chain after it leaves SetFilter's window -- 0 DTE lottery
            # tickets. The filter is a hint; verify here.
            dte = (k.Expiry.date() - today).days
            if dte < MIN_DTE or dte > MAX_DTE:
                self.dte_skips += 1
                continue
            # Both sides quoted: a one-sided fill represents nothing.
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

        # BUGFIX 7 -- state first, registration second, ORDER LAST.
        # LEAN fills inside the MarketOrder call, so a book built after
        # it misses its own entry: 403 fills, zero trades. See README.
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

        self.AddOptionContract(best.Symbol, Resolution.Minute)
        self.MarketOrder(best.Symbol, qty)
        return True

    # ---- exits ----

    def _sell(self, b, reason, frac=1.0):
        held = self.Portfolio[b.contract].Quantity
        if not held:
            return
        n = int(abs(held)) if frac >= 1.0 else max(1, int(abs(held) * frac))

        # Mark at the mid BEFORE ordering; the fill returns the bid.
        sec = self.Securities[b.contract]
        bid, ask = float(sec.BidPrice), float(sec.AskPrice)
        mid = (bid + ask) / 2.0 if (bid > 0 and ask > 0) else bid
        if mid > 0:
            b.mid_proceeds += n * mid * 100.0
            b.sold += n

        # BUGFIX 8 -- BUGFIX 7 again: the fill happens inside
        # MarketOrder, so _close_out read last_reason before it was set.
        b.last_reason = reason
        if frac >= 1.0:
            b.closing = True           # BUGFIX 4
        self.exits[reason] = self.exits.get(reason, 0) + 1   # BUGFIX 3
        self.MarketOrder(b.contract, -n)

    def _manage(self, b, bar):
        # BUGFIX 4: a delayed fill once let the next bar re-sell.
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
        # Partial scale, once. Kept by request; the sweep prices it.
        if not b.scaled and chg >= SCALE_AT:
            b.scaled = True
            self._sell(b, "scale", SCALE_FRAC)
        # Dead trade BEFORE the timer: a flat range never reaches 36.
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

    def _close_out(self, b):
        # If a buy fill is ever missed, price the entry from the ask.
        cost = b.cost if b.cost > 0 else b.qty0 * b.ref_px * 100.0
        if cost <= 0:
            return
        self.closes += 1
        rec = {
            "ret": (b.proceeds - cost) / cost * 100.0,
            "mid": None,
            "bars": b.bars,
            "reason": b.last_reason,
            "spread": b.entry_spread * 100.0,
        }
        # Trust the shadow only when every contract left via our orders.
        if b.mid_cost > 0 and b.sold == b.qty0:
            rec["mid"] = (b.mid_proceeds - b.mid_cost) / b.mid_cost * 100.0
        self.trades.append(rec)

    def OnOrderEvent(self, ev):
        """Returns come from FILL PRICES, not from what this file
        expected them to be. That is why the run happens here."""
        if ev.Status != OrderStatus.Filled:
            return
        self.oe_seen += 1
        b = self.by_contract.get(ev.Symbol)
        if b is None:
            # Printed in PARITY: non-zero means blind again.
            self.oe_lost += 1
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
        # Expiry or assignment can flatten a position without an exit
        # order of ours. BUGFIX 2: v1 ignored pending orders here.
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

    def _score(self, params, key="px", refk="ref"):
        """One combination, replayed over every recorded trade."""
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
            "net": sum(rets) * RISK_PCT / LOT_DIVISOR,   # of equity
        }

    def _row(self, label, s, mark=""):
        if s is None:
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
        self.Debug("EXIT SWEEP -- same trades, %d paths" % len(self.done_tracks))
        self.Debug("#  h1/h2 = halves of the year. One-sided = noise.")
        self._row("LIVE RULE (baseline)", self._score(base), "<= today")
        self._row("  same, at mid prices", self._score(base, "mx", "refm"))

        # The scale exit alone; everything else held still.
        self.Debug("#  DOES THE +10% SCALE COST MONEY? (only knob moving)")
        for v in SCALE_GRID:
            p = dict(base)
            p["scale"] = v
            self._row("  scale=%s" % ("off" if v is None else "+%.0f%%" % (v * 100)),
                      self._score(p))

        self.Debug("#  ONE KNOB AT A TIME (others at live values)")
        ofat = [("tp", TP_GRID), ("stop", STOP_GRID), ("dead", DEAD_GRID),
                ("hold", HOLD_GRID), ("trail", TRAIL_GRID),
                ("struct", [True, False])]
        for key, grid in ofat:
            for v in grid:
                p = dict(base)
                p[key] = v
                self._row("  %s=%s" % (key, v), self._score(p))

        # Best average flatters; best worst-half survives.
        combos = list(product(TP_GRID, STOP_GRID, SCALE_GRID, DEAD_GRID,
                              HOLD_GRID, TRAIL_GRID))
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
        self.Debug("#  BEST BY WORST HALF -- the one to believe:")
        self._row("  %s" % (robust[0],), robust[1])

        pos = sum(1 for _p, s in scored if s["avg"] > 0)
        self.Debug("#  %d of %d combinations beat zero, over %d trades."
                   % (pos, len(scored), len(self.done_tracks)))
        self.Debug("#  Accept one only if BOTH halves are positive AND its")
        self.Debug("#  one-knob neighbours are too. A lone spike is luck.")

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
        days = max((self.EndDate - self.StartDate).days * 252.0 / 365.0, 1.0)
        tot = 0
        for name, b in self.books.items():
            rate = (b.signals / b.bars5 * 100.0) if b.bars5 else 0.0
            tot += b.signals
            self.Debug("  %-5s bars5=%-7d signals=%-5d rate=%.2f%% blocked=%d wide=%d"
                       % (name, b.bars5, b.signals, rate, b.blocked, b.wide))
        self.Debug("  signals/day = %.2f     local rule: about 0.9 for SPY+QQQ"
                   % (tot / days))

        self.Debug("  fills seen=%d unmatched=%d closes=%d dte_skips=%d"
                   % (self.oe_seen, self.oe_lost, self.closes, self.dte_skips))

        n = len(self.trades)
        if n == 0:
            self.Debug("  NO TRADES RECORDED. If fills were seen above")
            self.Debug("  that is a book-keeping fault, not a quiet rule.")
            self._finish()
            return

        real = self._stats(self.trades, "ret")
        shadow = self._stats(self.trades, "mid")

        self.Debug("")
        self.Debug("#  WHERE THE MONEY GOES -- realised vs mid")
        self.Debug("#  realised at bid/ask : n=%d avg=%+.2f%% wr=%.1f%% pf=%.2f"
                   % (real["n"], real["avg"], real["wr"], real["pf"]))
        if shadow:
            self.Debug("#  same trades at MID  : n=%d avg=%+.2f%% wr=%.1f%% pf=%.2f"
                       % (shadow["n"], shadow["avg"], shadow["wr"], shadow["pf"]))
            self.Debug("#  spread drag         : %.2f%% per trade"
                       % (shadow["avg"] - real["avg"]))
            self.Debug("#")
            if shadow["avg"] > 0.0:
                self.Debug("#  VERDICT: works at the mid; the spread takes it.")
                self.Debug("#  Fix EXECUTION -- limits, tighter cap, fewer trips.")
            else:
                self.Debug("#  VERDICT: negative even at the mid, where execution")
                self.Debug("#  is free. See SIGNAL EDGE below.")
        self.Debug("#  commission $%.2f (model=%s)"
                   % (float(self.Portfolio.TotalFees),
                      "ZERO" if ZERO_COMMISSION else "brokerage"))

        self.Debug("#  BY EXIT REASON -- which door winners leave by")
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
        self.Debug("#  best / worst  %+.1f%% / %+.1f%%   breakeven pf %.2f"
                   % (srt[-1], srt[0], (100.0 - real["wr"]) / real["wr"]))

        self._finish()

    def _edge(self):
        """
        Does the UNDERLYING move the signal's way? No spread, theta or
        expiry -- just SPY and QQQ after a signal versus after any bar.
        A drifting market makes calls look right on its own, so the rule
        must beat that drift over the same horizon and mix.
        """
        self.Debug("")
        self.Debug("=" * 70)
        self.Debug("SIGNAL EDGE -- the underlying alone (bp, signal direction)")
        self.Debug("#  1bp of underlying ~ 1% of premium; the spread")
        self.Debug("#  costs 1.15%, so under ~1.2bp it cannot pay.")
        for k in (3, 6, 12, 24, 36):
            sig, mkt, mix = [], [], 0
            for b in self.books.values():
                px, dy, n = b.px5, b.day5, len(b.px5)
                for i, d in b.sigs:
                    j = i + k
                    if j < n and dy[j] == dy[i] and px[i] > 0:
                        sig.append(d * (px[j] / px[i] - 1.0) * 10000.0)
                        mix += d
                for i in range(n - k):
                    if dy[i + k] == dy[i] and px[i] > 0:
                        mkt.append((px[i + k] / px[i] - 1.0) * 10000.0)
            if not sig or not mkt:
                continue
            s = sum(sig) / len(sig)
            # Same call/put mix, so drift is neither credited nor blamed.
            base = sum(mkt) / len(mkt) * mix / float(len(sig))
            hit = sum(1 for x in sig if x > 0) / float(len(sig)) * 100.0
            self.Debug("#  bars=%-3d n=%-4d sig=%+6.2f mkt=%+6.2f edge=%+6.2f hit=%.1f%%"
                       % (k, len(sig), s, base, s - base, hit))
        self.Debug("#  edge < 0 on every horizon is not noise: the rule")
        self.Debug("#  is informative with the sign reversed. See INVERT.")

    def _finish(self):
        """
        Reads price paths, never self.trades, so a book-keeping fault
        cannot silence it -- as an early return once did.
        """
        self._edge()
        if not SWEEP:
            return
        # Paths still recording at the end are shorter but valid.
        for b in self.books.values():
            for tk in b.tracks:
                if tk["px"]:
                    self.done_tracks.append(tk)
            b.tracks = []
        if self.done_tracks:
            self._sweep()
