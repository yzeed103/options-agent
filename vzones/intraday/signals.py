"""Candidate setups. Each returns an int array: +1 long, -1 short, 0 none, decided at bar close."""
from __future__ import annotations
import numpy as np, pandas as pd


def orb(d: pd.DataFrame, rvol_min: float = 1.0, last_entry_min: int = 120) -> np.ndarray:
    c, ph, pl = d.close.to_numpy(), d.or_high.to_numpy(), d.or_low.to_numpy()
    first = ~d.session.duplicated()      # placeholder for per-session "first break" logic below
    sig = np.zeros(len(d), int); taken = set()
    for i in range(1, len(d)):
        s = d.session.iat[i]
        if s in taken or np.isnan(ph[i]) or d.minute_of_session.iat[i] > last_entry_min or not d.rvol.iat[i] >= rvol_min:
            continue
        if c[i] > ph[i] and c[i - 1] <= ph[i]: sig[i] = 1; taken.add(s)
        elif c[i] < pl[i] and c[i - 1] >= pl[i]: sig[i] = -1; taken.add(s)
    return sig


def va_reentry(d: pd.DataFrame) -> np.ndarray:
    """Prior-day 80% rule: open outside prior value, two closes back inside -> trade to the far edge."""
    c, vah, val = d.close.to_numpy(), d.pd_vah.to_numpy(), d.pd_val.to_numpy()
    sig = np.zeros(len(d), int); state = {}
    for i in range(1, len(d)):
        s = d.session.iat[i]
        if np.isnan(vah[i]): continue
        if s not in state:
            o = d.open.iat[i]; state[s] = 1 if o > vah[i] else (-1 if o < val[i] else 0); continue
        st = state[s]
        if st == 1 and c[i] < vah[i] and c[i - 1] < vah[i]: sig[i] = -1; state[s] = 9
        elif st == -1 and c[i] > val[i] and c[i - 1] > val[i]: sig[i] = 1; state[s] = 9
    return sig


def vwap_reclaim(d: pd.DataFrame, trend: bool = True) -> np.ndarray:
    c, vw = d.close.to_numpy(), d.vwap.to_numpy()
    up = (c > vw) & (np.r_[np.nan, c[:-1]] <= np.r_[np.nan, vw[:-1]])
    dn = (c < vw) & (np.r_[np.nan, c[:-1]] >= np.r_[np.nan, vw[:-1]])
    if trend:
        up &= (d.ema_f > d.ema_s).to_numpy(); dn &= (d.ema_f < d.ema_s).to_numpy()
    return np.where(up, 1, np.where(dn, -1, 0))


def _first_per_session(d, up, dn):
    sig = np.zeros(len(d), int); seen = set(); sess = d.session.to_numpy()
    for i in np.flatnonzero(up | dn):
        if sess[i] in seen: continue
        sig[i] = 1 if up[i] else -1; seen.add(sess[i])
    return sig


def va_accept(d: pd.DataFrame, n: int = 2) -> np.ndarray:
    """Acceptance outside prior-day value: n consecutive closes above VAH (or below VAL) -> continuation."""
    c = d.close
    up = (c > d.pd_vah).rolling(n).sum().eq(n).to_numpy() & (d.open.groupby(d.session).transform("first") <= d.pd_vah).to_numpy()
    dn = (c < d.pd_val).rolling(n).sum().eq(n).to_numpy() & (d.open.groupby(d.session).transform("first") >= d.pd_val).to_numpy()
    return _first_per_session(d, up, dn)


def ib_break(d: pd.DataFrame) -> np.ndarray:
    c, pc = d.close.to_numpy(), d.close.shift(1).to_numpy()
    up = (c > d.ib_high.to_numpy()) & (pc <= d.ib_high.to_numpy())
    dn = (c < d.ib_low.to_numpy()) & (pc >= d.ib_low.to_numpy())
    return _first_per_session(d, up, dn)


def poc_reclaim(d: pd.DataFrame) -> np.ndarray:
    c, pc, poc = d.close.to_numpy(), d.close.shift(1).to_numpy(), d.pd_poc.to_numpy()
    up = (c > poc) & (pc <= poc) & (d.ema_f > d.ema_s).to_numpy()
    dn = (c < poc) & (pc >= poc) & (d.ema_f < d.ema_s).to_numpy()
    return np.where(up, 1, np.where(dn, -1, 0))


def failed_break(d: pd.DataFrame, k: int = 3) -> np.ndarray:
    """Trap: price trades beyond prior-day high/low then closes back inside within k bars -> fade."""
    h, l, c = d.high, d.low, d.close
    poke_up = (h > d.pd_high).rolling(k).max().astype(bool)
    poke_dn = (l < d.pd_low).rolling(k).max().astype(bool)
    dn = (poke_up & (c < d.pd_high) & (c.shift(1) >= d.pd_high.shift(1)) | poke_up & (c < d.pd_high) & (h > d.pd_high)).to_numpy()
    up = (poke_dn & (c > d.pd_low) & (c.shift(1) <= d.pd_low.shift(1)) | poke_dn & (c > d.pd_low) & (l < d.pd_low)).to_numpy()
    return _first_per_session(d, up, dn)


def squeeze_release(d: pd.DataFrame) -> np.ndarray:
    was = d["sqz"].shift(1, fill_value=False).to_numpy().astype(bool)
    up = was & (d.close > d.bb_up).to_numpy(); dn = was & (d.close < d.bb_dn).to_numpy()
    return np.where(up, 1, np.where(dn, -1, 0))


SETUPS = {"orb": orb, "va_reentry": va_reentry, "vwap_reclaim": vwap_reclaim, "va_accept": va_accept,
          "ib_break": ib_break, "poc_reclaim": poc_reclaim, "failed_break": failed_break, "squeeze_release": squeeze_release}


def apply_filters(d: pd.DataFrame, sig: np.ndarray, trend: str = "any", window: str = "all", rvol_min: float = 0.0) -> np.ndarray:
    s = sig.copy()
    if trend == "with":
        tu = (d.ema_f > d.ema_s).to_numpy(); s = np.where(((s > 0) & tu) | ((s < 0) & ~tu), s, 0)
    elif trend == "against":
        tu = (d.ema_f > d.ema_s).to_numpy(); s = np.where(((s > 0) & ~tu) | ((s < 0) & tu), s, 0)
    m = d.minute_of_session.to_numpy()
    if window == "first2h": s = np.where(m < 120, s, 0)
    elif window == "after11": s = np.where((m >= 90) & (m < 360), s, 0)
    elif window == "nolast30": s = np.where(m < 360, s, 0)
    if rvol_min > 0:
        rv = d.rvol.fillna(0).to_numpy(); s = np.where(rv >= rvol_min, s, 0)
    return s
