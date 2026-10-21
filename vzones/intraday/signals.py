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


SETUPS = {"orb": orb, "va_reentry": va_reentry, "vwap_reclaim": vwap_reclaim}
