"""Paper-trade simulator. The same function serves the history replay and the live agent (the live agent re-runs it
on the bars it has; past trades never change because nothing at bar t looks past bar t: tests/test_assistant.py).

Exit rules, FIXED before any test (2026-10-23) and never tuned on results:
  entry      open of the bar after the signal; a signal on the last bar of a session is skipped
  stop       1.0 x ATR(14) of the signal bar, from the entry
  target     tl / st / ta / gx: 2R.  wb: the indicator's own target (the next whale level, >= 3R by construction)
  session    flat at the close of the session (no overnight)
  fills      a bar that opens through the stop or target fills at its open; stop and target in one bar = stop first
  costs      0.02% of the price per side (spread + slippage), charged in R
  one open trade per symbol x timeframe x signal; signals during an open trade are logged as skipped
"""
from __future__ import annotations

import json
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import signals as S
from .data import daily_bars, levels_for_days, resample15, vix_prev_close

SIGNALS = ("tl", "st", "ta", "wb", "gx")
NAMES_AR = {"tl": "كسر خط الترند", "st": "انقلاب Supertrend", "ta": "تنبيه الاتجاه", "wb": "ارتداد الحوت", "gx": "ارتداد جدار الخيارات"}
STOP_ATR, TARGET_R, COST = 1.0, 2.0, 0.0002


@dataclass
class Prepared:
    sym: str
    tf: int
    d: pd.DataFrame          # bars + readings + signals + context columns


def day_table(bars5: pd.DataFrame) -> pd.DataFrame:
    sess = np.array([t.date() for t in bars5.index])
    return bars5.groupby(sess).agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"))


def official_days(sym: str, days: pd.DataFrame, use_yahoo: bool = True) -> pd.DataFrame:
    """Daily high / low / close for the whale ranges: Yahoo's official values where available (closer to the
    TradingView daily bars the indicator uses), the intraday aggregate otherwise (including today's partial day)."""
    out = days[["high", "low", "close"]].copy()
    if use_yahoo:
        y = daily_bars(sym, list(days.index))
        if y is not None:
            ok = y.notna().all(axis=1)
            # sanity: a Yahoo bar far from the intraday one (bad print, different adjustment) is not used
            ok &= (abs(y.close - out.close) / out.close < 0.02)
            out.loc[ok, ["high", "low", "close"]] = y.loc[ok, ["high", "low", "close"]].to_numpy()
    return out


def prepare(sym: str, bars5: pd.DataFrame, tfs=(5, 15), whale_cache: dict | None = None, whale_days: dict | None = None,
            gex: pd.DataFrame | None = None, vix: pd.Series | None = None, use_yahoo: bool = True) -> dict[int, Prepared]:
    """Signals + context for each timeframe. Whale levels depend only on completed days, so they are shared."""
    src15 = resample15(bars5)
    days = day_table(bars5)
    if whale_days is None:
        whale_days = S.whale_levels_by_day(official_days(sym, days, use_yahoo), src15, whale_cache)
    sessions = list(days.index)
    gex = levels_for_days(sym, sessions) if gex is None else gex
    vix = vix_prev_close(sessions) if vix is None else vix
    # daily ATR known before each day (Wilder, from completed days)
    trd = S.true_range(days.high.to_numpy(float), days.low.to_numpy(float), days.close.to_numpy(float))
    datr = S.rma(trd, 14)
    datr_prev = pd.Series(np.r_[np.nan, datr[:-1]], index=sessions)
    prev_close = pd.Series(np.r_[np.nan, days.close.to_numpy(float)[:-1]], index=sessions)
    out = {}
    for tf in tfs:
        bars = bars5 if tf == 5 else resample15(bars5)
        d = S.compute(bars, src15, whale_days=whale_days)
        d = S.add_gex_signal(d, gex)
        out[tf] = Prepared(sym, tf, add_context(d, datr_prev, prev_close, days.open, vix))
    return out


def add_context(d: pd.DataFrame, datr_prev, prev_close, day_open, vix) -> pd.DataFrame:
    d = d.copy()
    sess = d["session"]
    mins = d.index.hour * 60 + d.index.minute - 570
    d["minute"] = mins
    slot = d.index.hour * 60 + d.index.minute
    d["rvol"] = d.volume / d.volume.groupby(slot).transform(lambda x: x.shift(1).rolling(20, min_periods=5).mean())
    d["datr"] = sess.map(datr_prev).astype(float)
    d["gap_atr"] = ((sess.map(day_open) - sess.map(prev_close)) / d["datr"]).astype(float)
    d["vix"] = sess.map(vix).astype(float)
    return d


def bucket(row, side: int) -> dict:
    """Context snapshot of a signal bar, as labelled buckets (the learner groups on these)."""
    c = row["close"]
    m = row["minute"]
    ctx = {"side": "long" if side > 0 else "short",
           "time": "open" if m < 60 else ("mid" if m < 300 else "late"),
           "trend": ("with" if (row["ema20"] > row["ema50"]) == (side > 0) else "against") if np.isfinite(row["ema50"]) else "none"}
    vah, val = row["pd_vah"], row["pd_val"]
    ctx["va"] = "none" if not np.isfinite(vah) else ("above" if c > vah else ("below" if c < val else "inside"))
    rv = row["rvol"]
    ctx["rvol"] = "none" if not np.isfinite(rv) else ("low" if rv < 0.8 else ("high" if rv > 1.5 else "normal"))
    datr = row["datr"]
    walls = [x for x in (row.get("cw"), row.get("pw")) if x is not None and np.isfinite(x)]
    if walls and np.isfinite(datr) and datr > 0:
        dist = min(abs(c - w) for w in walls) / datr
        ctx["gex_wall"] = "near" if dist < 0.5 else ("mid" if dist < 1.5 else "far")
    else:
        ctx["gex_wall"] = "none"
    fl = row.get("flip")
    ctx["gex_flip"] = "none" if fl is None or not np.isfinite(fl) else ("above" if c > fl else "below")
    vx = row["vix"]
    ctx["vix"] = "none" if not np.isfinite(vx) else ("calm" if vx < 15 else ("normal" if vx < 20 else ("elevated" if vx < 25 else "fear")))
    g = row["gap_atr"]
    ctx["gap"] = "none" if not np.isfinite(g) else ("up" if g > 0.3 else ("down" if g < -0.3 else "flat"))
    return ctx


def simulate(p: Prepared) -> tuple[list[dict], list[dict]]:
    """Returns (trades, signal log). Open trades at the end of the data have status 'open'."""
    d = p.d
    o, h, l, c, atr = (d[k].to_numpy(float) for k in ("open", "high", "low", "close", "atr"))
    sess = d["session"].to_numpy()
    n = len(d)
    idx = d.index
    # last bar of a session: the next bar starts another day, or the bar itself ends at 16:00 (known from its own time,
    # so the newest bar of a finished day is closed out without waiting for tomorrow's data)
    ends = idx + pd.Timedelta(minutes=p.tf)
    last_bar = np.r_[sess[1:] != sess[:-1], False] | ((ends.hour == 16) & (ends.minute == 0))
    trades, log = [], []
    for name in SIGNALS:
        sig = d[f"sig_{name}"].to_numpy()
        busy_until = -1
        for i in np.flatnonzero(sig):
            s = int(sig[i])
            ctx = bucket(d.iloc[i], s)
            key = f"{p.sym}|{p.tf}|{name}|{idx[i].isoformat()}"
            base = dict(key=key, sym=p.sym, tf=p.tf, signal=name, side=s, signal_time=idx[i].isoformat(), context=json.dumps(ctx))
            if i <= busy_until:
                log.append(dict(base, taken=0, reason="already in a trade")); continue
            if last_bar[i]:
                log.append(dict(base, taken=0, reason="last bar of the session")); continue
            if i == n - 1:
                log.append(dict(base, taken=0, reason="waiting for the next bar")); continue
            if not np.isfinite(atr[i]) or atr[i] <= 0:
                log.append(dict(base, taken=0, reason="no ATR yet")); continue
            e = i + 1
            entry = o[e]
            risk = STOP_ATR * atr[i]
            stop = entry - s * risk
            tgt = d["wb_tgt"].iat[i] if name == "wb" else entry + s * TARGET_R * risk
            if not np.isfinite(tgt) or (tgt - entry) * s <= 0:
                log.append(dict(base, taken=0, reason="target already passed at the entry")); continue
            j = e
            exit_px = None; why = None
            while True:
                if j > e:
                    if (o[j] - stop) * s <= 0: exit_px, why = o[j], "stop (gap)"; break
                    if (o[j] - tgt) * s >= 0: exit_px, why = o[j], "target (gap)"; break
                if (l[j] <= stop) if s > 0 else (h[j] >= stop): exit_px, why = stop, "stop"; break
                if (h[j] >= tgt) if s > 0 else (l[j] <= tgt): exit_px, why = tgt, "target"; break
                if last_bar[j]: exit_px, why = c[j], "session close"; break
                if j == n - 1: break                                # still open
                j += 1
            cost_r = 2 * COST * entry / risk
            t = dict(base, entry_time=idx[e].isoformat(), entry=round(float(entry), 4), stop=round(float(stop), 4),
                     target=round(float(tgt), 4), risk=round(float(risk), 4), cost_r=round(float(cost_r), 4))
            if exit_px is None:
                t.update(status="open", exit_time=None, exit=None, reason=None, bars=int(j - e + 1),
                         r=round(float(s * (c[j] - entry) / risk - cost_r), 4), pct=None)
                busy_until = n
            else:
                r = s * (exit_px - entry) / risk - cost_r
                t.update(status="closed", exit_time=idx[j].isoformat(), exit=round(float(exit_px), 4), reason=why, bars=int(j - e + 1),
                         r=round(float(r), 4), pct=round(float(100 * (s * (exit_px - entry) / entry - 2 * COST)), 4))
                busy_until = j
            trades.append(t)
            log.append(dict(base, taken=1, reason="taken"))
    return trades, log
