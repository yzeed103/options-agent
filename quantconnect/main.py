"""
The live rule on QuantConnect -- v8.

ASCII only, under 32000 chars, no LEAN name at module scope except
QCAlgorithm. See README.md; if it grows, cut comments.

CLOSED. Out of sample on 2020-05..2023-05 the edge per 182-day block
went - + - + - - -, against + + + + + - - for 2023-05..2026-05: six
sign flips in 13 blocks, block sd 7.5bp against 5.7bp of sampling
noise. No regime -- a zero-edge rule whose half-year estimates wander
by their own standard error. REGIME PROBE: 0.24 sigma. No entry
bucket cleared 5bp at n>=100. See README before running this again.
"""
from AlgorithmImports import *

from datetime import date, timedelta

RUN_FROM = (2020, 5, 15)       # untouched years -- adjacent, no overlap
RUN_TO = (2023, 5, 15)

SYMBOLS = ["SPY", "QQQ"]

MIN_DTE, MAX_DTE = 2, 8
NO_ENTRY_AFTER = (14, 0)
FORCE_FLAT = (15, 55)

SCALE_AT, SCALE_FRAC = None, 0.25    # None = no partial scale
HARD_STOP = 0.20               # was 0.30
MAX_HOLD_BARS, WINNER_HOLD_BARS = 36, 60
DEAD_BARS, DEAD_MOVE = 8, 0.04

RISK_PCT, LOT_DIVISOR = 0.05, 4
BB_PERIOD, BB_STD = 20, 2.0

# LEAN's default bills what the broker never charges.
ZERO_COMMISSION = True

MAX_SPREAD_PCT = 0.08          # 12% wide starts the trade 6% down
STRIKE_SEARCH = 3

# Measurement only, never an order. EDGE_K is the horizon the flip
# was measured at; REG_N is the detector's memory, in signals.
EDGE_K, REG_N, PERIOD_DAYS = 24, 20, 182

# Paths are recorded and replayed at the end: one backtest, many
# exit rules, on THE SAME TRADES.
SWEEP = True
PATH_BARS = 78                 # a FULL session: 60 could not be beaten

# Extended past the old optimum in v8. Out of sample BOTH extensions
# lost: stop 0.10/0.15 worse than 0.20, hold-to-bell the worst of all.
STOP_GRID = [0.10, 0.15, 0.20, 0.30]
SCALE_GRID = [None, 0.10, 0.25]             # None = no partial scale
DEAD_GRID = [None, 4, 6, 8, 14]
HOLD_GRID = [(36, 60), (24, 48), (60, 60),  # (loser cap, winner cap)
             (36, 78), (24, 78), (78, 78)]  # 78 = hold to the bell
# tp and trail are gone: both hurt in BOTH eras. Settled.


class SessionVwap:
    """VWAP from the bell, reset each session. Not LEAN's: another
    VWAP changes which signals fire."""

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
    """Heikin Ashi. Only the colour is used, as in the live rule."""

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
    """Per-symbol state for the entry and exit gates."""

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
        # shadow: the same trade marked at the mid
        self.qty0 = 0
        self.sold = 0
        self.mid_cost = 0.0
        self.mid_proceeds = 0.0
        self.entry_spread = 0.0
        self.last_reason = "?"
        self.tracks = []               # price paths being recorded
        # edge probe: the UNDERLYING, not the option
        self.px5 = []
        self.day5 = []
        self.sigs = []                 # (bar index, +1 call / -1 put)
        self.conds = []                # (hour, %B) at that same signal
        # parity counters
        self.bars5 = 0
        self.signals = 0
        self.blocked = 0               # signal fired, no contract
        self.wide = 0                  # every strike too wide


def replay(ref, path, trends, want, p):
    """One trade, one exit rule, in _manage's ORDER -- a different
    order is a different rule. Percent of premium."""
    if ref <= 0 or not path:
        return None
    left = 1.0                 # fraction of the position still held
    got = 0.0                  # proceeds, in units of one contract
    scaled = False
    dead_bars, dead_move = p["dead"], DEAD_MOVE
    loser_cap, winner_cap = p["hold"]

    for i, px in enumerate(path):
        if px <= 0:
            continue
        bars = i + 1
        chg = (px - ref) / ref
        if chg <= -p["stop"]:
            got += left * px
            left = 0.0
            break
        if p["scale"] is not None and not scaled and chg >= p["scale"]:
            scaled = True
            got += left * SCALE_FRAC * px
            left -= left * SCALE_FRAC
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

            # BUGFIX 5: a 15:55 test assumes a 16:00 bell.
            self.Schedule.On(self.DateRules.EveryDay(name),
                             self.TimeRules.BeforeMarketClose(name, 5),
                             self._make_eod(name))

        self.Debug("start=%s end=%s %s spread=%.0f%% comm=%s scale=%s"
                   % (RUN_FROM, RUN_TO, SYMBOLS, MAX_SPREAD_PCT * 100,
                      "ZERO" if ZERO_COMMISSION else "default", SCALE_AT))

    def _zero_commission(self):
        """Drop the broker's cut. Built at runtime, NOT as a module
        subclass -- that runs at import and kills it. See README."""
        seeder = FuncSecuritySeeder(self.GetLastKnownPrices)
        base = None
        try:
            base = BrokerageModelSecurityInitializer(self.BrokerageModel, seeder)
        except Exception:                                    # noqa: BLE001
            self.Debug("note: no BrokerageModelSecurityInitializer")

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

            # BUGFIX 1: no cross across the session boundary.
            if new_day:
                b.prev_close, b.prev_vwap = None, None
            prev_c, prev_v = b.prev_close, b.prev_vwap
            b.prev_close, b.prev_vwap = c, v

            self._sample(b, bar)      # same trend _manage will read

            if b.contract is not None:
                self._manage(b, bar)
                return
            if not b.bb.IsReady or prev_c is None or prev_v is None or v is None:
                return

            t = bar.EndTime
            hm = (t.hour, t.minute)
            if hm >= NO_ENTRY_AFTER or hm < (9, 35):
                return

            up = float(b.bb.UpperBand.Current.Value)
            lo = float(b.bb.LowerBand.Current.Value)
            width = up - lo
            if width <= 0:
                return
            pb = (c - lo) / width

            # The CROSSING bar is a condition: without it this
            # reads "above/below VWAP" and fires 10x as often.
            call = (b.trend == 1 and colour > 0 and c > v
                    and prev_c <= prev_v and 0.50 <= pb <= 1.50)
            put = (b.trend == -1 and colour < 0 and c < v
                   and prev_c >= prev_v and -0.50 <= pb <= 0.50)
            if not (call or put):
                return

            b.signals += 1
            b.sigs.append((len(b.px5) - 1, 1 if call else -1))
            b.conds.append((t.hour, pb))
            if not self._enter(b, call):
                # Counted even with no contract taken.
                b.blocked += 1
        return handler

    def _make_eod(self, name):
        def handler():
            b = self.books[name]
            if b.contract is not None and not b.closing:
                self._sell(b, "forced_flat")
            # No path may cross a session boundary.
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

        cands = []
        today = self.Time.date()
        for k in chain:
            if k.Right != want:
                continue
            # BUGFIX 6: the chain outlives SetFilter's window, so
            # 0 DTE leaks in. Verify, do not trust.
            dte = (k.Expiry.date() - today).days
            if dte < MIN_DTE or dte > MAX_DTE:
                self.dte_skips += 1
                continue
            bid, ask = float(k.BidPrice), float(k.AskPrice)   # both sides
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

        # BUGFIX 7 -- state, registration, ORDER LAST. LEAN fills
        # INSIDE MarketOrder: a book built after misses its own fill.
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

    def _sell(self, b, reason, frac=1.0):
        if b.contract is None:         # BUGFIX 9
            return
        held = self.Portfolio[b.contract].Quantity
        if not held:
            return
        n = int(abs(held)) if frac >= 1.0 else max(1, int(abs(held) * frac))

        # Mark at the mid BEFORE ordering; the fill returns bid.
        sec = self.Securities[b.contract]
        bid, ask = float(sec.BidPrice), float(sec.AskPrice)
        mid = (bid + ask) / 2.0 if (bid > 0 and ask > 0) else bid
        if mid > 0:
            b.mid_proceeds += n * mid * 100.0
            b.sold += n

        # BUGFIX 8 -- BUGFIX 7 again: set before the order.
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
        # qty0 >= 2 is BUGFIX 10: int(1 * 0.25) closed a one-lot
        # position WHOLE, a take-profit in disguise.
        if (SCALE_AT is not None and not b.scaled
                and chg >= SCALE_AT and b.qty0 >= 2):
            b.scaled = True
            self._sell(b, "scale", SCALE_FRAC)
            if b.contract is None or b.closing:   # BUGFIX 9
                return
        # Dead BEFORE the timer: a flat range never reaches it.
        if b.bars >= DEAD_BARS and abs(chg) < DEAD_MOVE:
            self._sell(b, "dead")
            return
        cap = WINNER_HOLD_BARS if chg > 0 else MAX_HOLD_BARS
        if b.bars >= cap:
            self._sell(b, "timer")
            return
        # Structural exit, only in profit -- as position_manager.
        if chg > 0:
            want = 1 if b.is_call else -1
            if b.trend == -want:
                self._sell(b, "structure")

    def _close_out(self, b):
        # If a buy fill is missed, price entry from the ask.
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
        # Trust the shadow only if all contracts left via our orders.
        if b.mid_cost > 0 and b.sold == b.qty0:
            rec["mid"] = (b.mid_proceeds - b.mid_cost) / b.mid_cost * 100.0
        self.trades.append(rec)

    def OnOrderEvent(self, ev):
        """Returns come from FILL PRICES, not from what this file
        expected. That is why the run happens."""
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
        # Expiry or assignment can flatten with no exit of ours.
        # BUGFIX 2: v1 ignored pending orders here.
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
        """One combination, replayed over every trade."""
        return self._stats([r for r in
                            (replay(tk[refk], tk[key], tk["tr"], tk["want"],
                                    params) for tk in self.done_tracks)
                            if r is not None])

    def _row(self, label, s, mark=""):
        if s is None:
            return
        self.Debug("#  %-26s avg=%+6.2f%% pf=%.2f wr=%4.1f%% net=%+6.1f%% "
                   "h1=%+6.2f h2=%+6.2f %s"
                   % (label, s["avg"], s["pf"], s["wr"], s["net"],
                      s["h1"], s["h2"], mark))

    def _sweep(self):
        base = {"stop": HARD_STOP, "scale": SCALE_AT, "dead": DEAD_BARS,
                "hold": (MAX_HOLD_BARS, WINNER_HOLD_BARS), "struct": True}

        self.Debug("")
        self.Debug("=" * 70)
        self.Debug("EXIT SWEEP -- %d paths" % len(self.done_tracks))
        self.Debug("#  h1/h2 = halves. One-sided = regime, not knob.")
        self._row("LIVE RULE (baseline)", self._score(base), "<= today")
        self._row("  same, at mid prices", self._score(base, "mx", "refm"))

        self.Debug("#  ONE KNOB AT A TIME (rest live)")
        ofat = [("scale", SCALE_GRID), ("stop", STOP_GRID),
                ("dead", DEAD_GRID), ("hold", HOLD_GRID),
                ("struct", [True, False])]
        for key, grid in ofat:
            for v in grid:
                p = dict(base)
                p[key] = v
                self._row("  %s=%s" % (key, v), self._score(p))

        # No full cross -- see README.

    def _col(self, rows, key="ret"):
        return [r[key] for r in rows if r.get(key) is not None]

    def _stats(self, vals):
        """n / avg / win rate / profit factor / halves / equity."""
        if not vals:
            return None
        n = len(vals)
        half = n // 2
        wins = [x for x in vals if x > 0]
        gl = -sum(x for x in vals if x <= 0)
        h1, h2 = vals[:half], vals[half:]
        return {
            "n": n,
            "avg": sum(vals) / n,
            "wr": len(wins) / n * 100.0,
            "pf": (sum(wins) / gl) if gl > 0 else float("inf"),
            "h1": (sum(h1) / len(h1)) if h1 else 0.0,
            "h2": (sum(h2) / len(h2)) if h2 else 0.0,
            "net": sum(vals) * RISK_PCT / LOT_DIVISOR,   # of equity
        }

    def _srow(self, label, s, tail=""):
        if s:
            self.Debug("#    %-18s n=%-4d avg=%+7.2f%% wr=%5.1f%% pf=%.2f%s"
                       % (label, s["n"], s["avg"], s["wr"], s["pf"], tail))

    def OnEndOfAlgorithm(self):
        self.Debug("")
        self.Debug("=" * 70)
        self.Debug("PARITY -- read this first")
        days = max((self.EndDate - self.StartDate).days * 252.0 / 365.0, 1.0)
        tot = 0
        for name, b in self.books.items():
            tot += b.signals
            self.Debug("  %-5s bars5=%-7d signals=%-5d blocked=%d wide=%d"
                       % (name, b.bars5, b.signals, b.blocked, b.wide))
        self.Debug("  signals/day = %.2f (local: ~0.9)" % (tot / days))

        self.Debug("  fills seen=%d unmatched=%d closes=%d dte_skips=%d"
                   % (self.oe_seen, self.oe_lost, self.closes, self.dte_skips))

        if not self.trades:
            self.Debug("  NO TRADES. With fills above, that is")
            self.Debug("  book-keeping, not a quiet rule.")
            self._finish()
            return

        real = self._stats(self._col(self.trades))
        shadow = self._stats(self._col(self.trades, "mid"))

        self.Debug("")
        self.Debug("#  WHERE THE MONEY GOES")
        self._srow("realised bid/ask", real)
        if shadow:
            self._srow("same trades at MID", shadow)
            self.Debug("#  spread drag: %.2f%%/trade  fees $%.2f"
                       % (shadow["avg"] - real["avg"],
                          float(self.Portfolio.TotalFees)))

        # Sorted by HOLDING TIME. The 2023-26 monotone pattern did
        # NOT hold out of sample.
        self.Debug("#  BY EXIT REASON")
        rs = {}
        for r in self.trades:
            rs.setdefault(r["reason"], []).append(r)
        for reason in sorted(rs, key=lambda k: sum(
                r["bars"] for r in rs[k]) / float(len(rs[k]))):
            rows = rs[reason]
            self._srow(reason, self._stats(self._col(rows)), "  bars=%.1f"
                       % (sum(r["bars"] for r in rows) / float(len(rows))))
        self.Debug("#  exit orders sent: %s" % (self.exits or "none"))

        sp = [r["spread"] for r in self.trades]
        self.Debug("#  entry spread avg %.1f%% worst %.1f%%"
                   % (sum(sp) / len(sp), max(sp)))

        srt = sorted(r["ret"] for r in self.trades)
        top = sum(srt[-int(len(srt) * 0.1 or 1):])
        self.Debug("#  best/worst %+.1f%%/%+.1f%% breakeven pf %.2f"
                   % (srt[-1], srt[0], (100.0 - real["wr"]) / real["wr"]))
        # The top 10%% are worth more than the whole book, twice
        # over: the average describes a handful of trades.
        self.Debug("#  top 10%% of trades = %+.0f pts of %+.0f total"
                   % (top, sum(srt)))

        self._finish()

    def _fwd(self, b, i, d, k):
        """Underlying return k bars past bar i, signed by the signal,
        in bp. None if the window leaves the session."""
        px, dy, n = b.px5, b.day5, len(b.px5)
        j = i + k
        if j >= n or dy[j] != dy[i] or px[i] <= 0:
            return None
        return d * (px[j] / px[i] - 1.0) * 10000.0

    def _bucket(self, label, v):
        if v:
            self.Debug("#    %-12s n=%-4d edge=%+6.2f hit=%.1f%%"
                       % (label, len(v), sum(v) / len(v),
                          sum(1 for x in v if x > 0) / len(v) * 100.0))

    def _edge(self):
        """Does the UNDERLYING move the signal's way? No spread or
        theta -- the index after a signal versus any bar, net of
        drift over the same horizon and call/put mix."""
        self.Debug("")
        self.Debug("=" * 70)
        self.Debug("SIGNAL EDGE -- the underlying alone (bp)")
        self.Debug("#  1bp of underlying ~ 1% of premium; the spread")
        self.Debug("#  costs ~1.4%, so under ~1.4bp it cannot pay.")
        edges, nsig = [], 0
        for k in (3, 6, 12, EDGE_K, 36):
            sig, mkt, mix = [], [], 0
            for b in self.books.values():
                px, dy, n = b.px5, b.day5, len(b.px5)
                for i, d in b.sigs:
                    e = self._fwd(b, i, d, k)
                    if e is not None:
                        sig.append(e)
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
            edges.append(s - base)
            nsig = max(nsig, len(sig))
            self.Debug("#  bars=%-3d n=%-4d sig=%+6.2f mkt=%+6.2f edge=%+6.2f hit=%.1f%%"
                       % (k, len(sig), s, base, s - base, hit))
        # SIGN IS NOT A FINDING. A 24-bar window is ~53bp, so one
        # standard error over n signals is 53/sqrt(n); v8 called
        # -0.07..-1.42bp "sign reversed" when all of it was noise.
        se = 53.0 / max(nsig, 1) ** 0.5
        big = [e for e in edges if abs(e) > se]
        if not big:
            self.Debug("#  all horizons inside 1 se (%.1fbp): NO EDGE." % se)
        elif min(big) > 0.0:
            self.Debug("#  edge > 0 past noise: informs as written.")
        elif max(big) < 0.0:
            self.Debug("#  edge < 0 past noise: sign reversed.")
        else:
            self.Debug("#  edge changes sign across horizons: nothing.")
        self._by_period()
        self._by_regime()
        self._by_entry()

    def _by_entry(self):
        """Does the edge LIVE somewhere? Entry conditions against
        the underlying afterwards, so no exit can flatter it."""
        self.Debug("#  EDGE BY ENTRY CONDITION at %d bars" % EDGE_K)
        dims = {}
        for b in self.books.values():
            for t, (i, d) in enumerate(b.sigs):
                e = self._fwd(b, i, d, EDGE_K)
                if e is None or t >= len(b.conds):
                    continue
                hr, pb = b.conds[t]
                for k, v in (("hour", "%02d:xx" % hr),
                             ("pctB", "%+.2f" % (round(pb * 4) / 4.0)),
                             ("side", "call" if d > 0 else "put"),
                             ("sym", b.name)):
                    dims.setdefault(k, {}).setdefault(v, []).append(e)
        for k in ("hour", "pctB", "side", "sym"):
            self.Debug("#   by %s" % k)
            for v in sorted(dims.get(k, {})):
                self._bucket(v, dims[k][v])
        self.Debug("#  Needs 5bp over the rest at n>=100. None did.")

    def _by_period(self):
        """WHEN the sign changed: one long average hides a reversal,
        blocks cannot. Gross of ~0.1bp drift."""
        self.Debug("#  BY PERIOD -- %d-day blocks at %d bars"
                   % (PERIOD_DAYS, EDGE_K))
        blocks = {}
        for b in self.books.values():
            for i, d in b.sigs:
                e = self._fwd(b, i, d, EDGE_K)
                if e is not None:
                    blocks.setdefault(b.day5[i] // PERIOD_DAYS, []).append(e)
        for k in sorted(blocks):
            self._bucket(str(date.fromordinal(k * PERIOD_DAYS)), blocks[k])

    def _regime(self, b, k, m):
        """At each signal, the mean edge of the previous m signals
        whose k-bar window had CLOSED by that bar. No bar AFTER the
        signal is read -- its own close is known -- so it runs live."""
        hist, cur, out = [], 0, []
        for i, _d in b.sigs:
            while cur < len(b.sigs) and b.sigs[cur][0] + k <= i:
                j, dj = b.sigs[cur]
                cur += 1
                e = self._fwd(b, j, dj, k)
                if e is not None:
                    hist.append(e)
            out.append(sum(hist[-m:]) / float(m) if len(hist) >= m else None)
        return out

    def _by_regime(self):
        """Was the flip visible BEFORE it was traded? They did not
        separate: 1.12 sigma, then 0.24 out of sample."""
        self.Debug("#  REGIME PROBE -- split by the rule's trailing")
        self.Debug("#  %d-signal record, read backward only." % REG_N)
        on, off = [], []
        for b in self.books.values():
            reg = self._regime(b, EDGE_K, REG_N)
            for t, (i, d) in enumerate(b.sigs):
                e = self._fwd(b, i, d, EDGE_K)
                if reg[t] is None or e is None:
                    continue
                (on if reg[t] > 0 else off).append(e)
        self._bucket("was working", on)
        self._bucket("was failing", off)
        self.Debug("#  A split is a hypothesis until other years agree")

    def _finish(self):
        """Reads paths, not self.trades: a book-keeping fault
        cannot silence it, as an early return once did."""
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
