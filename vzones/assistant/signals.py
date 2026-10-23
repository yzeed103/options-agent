"""Python twin of the Volume Zones signals (pine/volume_zones.pine, defaults). Every value at bar t uses bars <= t.

Signals (int arrays, +1 long / -1 short / 0 none, decided at the bar's close):
  tl  trendline break        alertconditions "كسر خط الترند الهابط / الصاعد"   ("ممتد" lines, 2-bar pivots, no hold)
  st  Supertrend flip         alertcondition "انكسار الترند (Supertrend)"     (factor 3, length 10)
  ta  trend alert             plotshape "تنبيه اتجاه صاعد / هابط"              (2 closes outside yesterday's value area)
  wb  whale bounce            plotshape "ارتداد حوت صعود / هبوط"               (touch of a whale level, target = next level)
  gx  options wall rejection  NOT in the indicator: our own candidate (touch CW / PW and close back)

Run `compute(bars, src15)` on regular-hours bars of the chart timeframe; `src15` = the 15-minute bars the whale profile
is built from (the indicator's default "فريم بيانات البروفايل" = 15).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

MINTICK = 0.01
WB_STOP, WB_MIN_R, WB_MAX_BARS = 1.0, 3.0, 130
WH_LEN, WH_MULT, WH_ROWS, WH_PEAKS, WH_KEEP = 10, 6.0, 200, 8, 2
VA_PCT, TA_ROWS, TA_BARS = 0.70, 30, 2
TL_LEN = 2
ST_FACTOR, ST_LEN = 3.0, 10


# ---------------- Pine primitives ----------------
def pine_sma_seeded(x: np.ndarray, n: int, alpha: float) -> np.ndarray:
    """Recursive average seeded with the SMA of the first n values (Pine's ta.rma; ta.ema with alpha 2/(n+1))."""
    x = np.asarray(x, float)
    out = np.full(len(x), np.nan)
    if len(x) < n:
        return out
    acc = np.nanmean(x[:n])
    out[n - 1] = acc
    for i in range(n, len(x)):
        acc = alpha * x[i] + (1 - alpha) * acc
        out[i] = acc
    return out


def rma(x, n):
    return pine_sma_seeded(x, n, 1.0 / n)


def ema(x, n):
    return pine_sma_seeded(x, n, 2.0 / (n + 1))


def true_range(h, l, c):
    pc = np.r_[np.nan, c[:-1]]
    return np.where(np.isnan(pc), h - l, np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc))))


def profile(h: np.ndarray, l: np.ndarray, v: np.ndarray, rows: int):
    """Volume per row over [min low, max high], each bar's volume spread evenly over its own high-low range
    (rows clipped as in the Pine loops; a zero-range bar puts its whole volume in its row).
    Returns (lo, step, pv) or None."""
    if len(h) == 0:
        return None
    lo, hi = float(np.min(l)), float(np.max(h))
    st = (hi - lo) / rows
    if not st > 0:
        return None
    edges = lo + st * np.arange(rows + 1)
    rg = np.maximum(h - l, MINTICK)
    dens = v / rg
    span = h - l
    cum = (np.clip(edges[:, None] - l[None, :], 0, span[None, :]) * dens[None, :]).sum(axis=1)
    pv = np.diff(cum)
    flat = span <= 0
    if flat.any():
        q = np.clip(((l[flat] - lo) / st).astype(int), 0, rows - 1)
        np.add.at(pv, q, v[flat])
    return lo, st, pv


def value_area(pv: np.ndarray, va: float = VA_PCT):
    rows = len(pv)
    pi = int(np.argmax(pv)); a0 = a1 = pi; acc = pv[pi]; tot = pv.sum()
    while acc < va * tot and (a0 > 0 or a1 < rows - 1):
        up = pv[a1 + 1] if a1 < rows - 1 else -1.0
        dn = pv[a0 - 1] if a0 > 0 else -1.0
        if up >= dn:
            a1 += 1; acc += up
        else:
            a0 -= 1; acc += dn
    return pi, a0, a1


# ---------------- whale levels (per day, from completed days only) ----------------
def _range_peaks(src: pd.DataFrame, t0, t1) -> list[float]:
    m = (src.index >= t0) & (src.index < t1)
    if m.sum() <= 10:
        return []
    b = src[m]
    p = profile(b.high.to_numpy(float), b.low.to_numpy(float), b.volume.fillna(0).to_numpy(float), WH_ROWS)
    if p is None:
        return []
    lo, st, pv = p
    sm = np.array([(pv[max(0, q - 1)] + pv[q] + pv[min(WH_ROWS - 1, q + 1)]) / 3 for q in range(WH_ROWS)])
    nb = max(2, WH_ROWS // 40)
    ms = sm.mean()
    cand = [q for q in range(WH_ROWS) if sm[q] >= 1.3 * ms and not (sm[max(0, q - nb):q + nb + 1] > sm[q]).any()]
    order = sorted(range(len(cand)), key=lambda j: -sm[cand[j]])            # stable, like array.sort_indices
    return [lo + (cand[j] + 0.5) * st for j in order[:WH_PEAKS]]


def whale_levels_by_day(day: pd.DataFrame, src: pd.DataFrame, cache: dict | None = None) -> dict:
    """day: daily bars (index = session date, ascending; the first row may be the day before the first chart bar).
    Returns {session date -> [levels in the indicator's order]} for every day after the first.
    `cache` maps (t0, t1) -> peaks for completed ranges (they never change)."""
    cache = {} if cache is None else cache
    H, L, C = day.high.to_numpy(float), day.low.to_numpy(float), day.close.to_numpy(float)
    dates = list(day.index)
    starts = [pd.Timestamp(d).tz_localize("America/New_York") for d in dates]
    out = {}
    datr = np.nan
    r_idx = None; r_hi = r_lo = np.nan
    rg0: list = []; rg1: list = []
    for n in range(len(dates) - 1):           # day n completed -> levels for day n+1
        today = starts[n + 1]
        pc = C[n - 1] if n > 0 else C[n]
        trd = max(H[n] - L[n], abs(H[n] - pc), abs(L[n] - pc))
        datr = trd if np.isnan(datr) else datr + (trd - datr) / 14
        if r_idx is None:
            r_idx, r_hi, r_lo = n, H[n], L[n]
        elif n - r_idx < WH_LEN:
            r_hi, r_lo = max(r_hi, H[n]), min(r_lo, L[n])
            if r_hi - r_lo > WH_MULT * datr:
                r_idx, r_hi, r_lo = n, H[n], L[n]
        elif C[n] > r_hi or C[n] < r_lo:
            rg0.append(starts[r_idx]); rg1.append(today)                  # breakout day included (default)
            while len(rg0) > WH_KEEP:
                rg0.pop(0); rg1.pop(0)
            r_idx, r_hi, r_lo = n, H[n], L[n]
        else:
            r_hi, r_lo = max(r_hi, H[n]), min(r_lo, L[n])
        lv = []
        for a, b in zip(rg0, rg1):
            if (a, b) not in cache:
                cache[(a, b)] = _range_peaks(src, a, b)
            lv += cache[(a, b)]
        if (n + 1) - r_idx >= WH_LEN:
            lv += _range_peaks(src, starts[r_idx], today)
        out[dates[n + 1]] = lv
    return out


# ---------------- main ----------------
def pivots(x: np.ndarray, k: int, high: bool) -> np.ndarray:
    """ta.pivothigh / ta.pivotlow(x, k, k): value at bar i is x[i-k] when it is a pivot, else NaN (known at bar i).
    Tie rule measured against TradingView (tools/paper_parity.py, SPY 5m, 1,248 breaks): a pivot high is >= the k bars
    on its left and strictly above the k bars on its right (99.9% match; strict on both sides: 91.7%)."""
    n = len(x); out = np.full(n, np.nan)
    for i in range(2 * k, n):
        p = i - k; v = x[p]; left = x[p - k:p]; right = x[p + 1:i + 1]
        if np.isnan(v) or np.isnan(left).any() or np.isnan(right).any():
            continue
        if (high and (left <= v).all() and (right < v).all()) or (not high and (left >= v).all() and (right > v).all()):
            out[i] = v
    return out


def compute(bars: pd.DataFrame, src15: pd.DataFrame, day_bars: pd.DataFrame | None = None,
            whale_cache: dict | None = None, whale_days: dict | None = None) -> pd.DataFrame:
    """bars: chart-timeframe regular-hours bars (tz-aware NY index). Returns a frame with the signals and the
    readings the context needs. `whale_days` = precomputed whale_levels_by_day result (live agent caches it)."""
    d = bars.copy()
    o, h, l, c = (d[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    v = d.volume.fillna(0).to_numpy(float)
    n = len(d)
    sess = np.array([t.date() for t in d.index])
    new_sess = np.r_[True, sess[1:] != sess[:-1]]
    trr = true_range(h, l, c)
    atr = rma(trr, 14)
    ema20, ema50 = ema(c, 20), ema(c, 50)
    d["atr"], d["ema20"], d["ema50"], d["session"] = atr, ema20, ema50, sess

    # --- Supertrend flip ---
    atr_s = rma(trr, ST_LEN); src = (h + l) / 2
    up_b = src + ST_FACTOR * atr_s; lo_b = src - ST_FACTOR * atr_s
    st_dir = np.full(n, np.nan); prev_st = 0.0; prev_lo = prev_up = 0.0
    for i in range(n):
        plo = 0.0 if i == 0 or np.isnan(lo_b[i - 1]) else lo_b[i - 1]
        pup = 0.0 if i == 0 or np.isnan(up_b[i - 1]) else up_b[i - 1]
        if not np.isnan(lo_b[i]):
            lo_b[i] = lo_b[i] if (lo_b[i] > plo or (i > 0 and c[i - 1] < plo)) else plo
            up_b[i] = up_b[i] if (up_b[i] < pup or (i > 0 and c[i - 1] > pup)) else pup
        if i == 0 or np.isnan(atr_s[i - 1]):
            dr = 1
        elif prev_st == pup:
            dr = -1 if c[i] > up_b[i] else 1
        else:
            dr = 1 if c[i] < lo_b[i] else -1
        stv = lo_b[i] if dr == -1 else up_b[i]
        prev_st = 0.0 if np.isnan(stv) else stv
        st_dir[i] = dr
    sig_st = np.zeros(n, int)
    ch = np.r_[False, st_dir[1:] != st_dir[:-1]]
    sig_st[ch] = np.where(st_dir[ch] < 0, 1, -1)

    # --- trend alert (yesterday's value area, 30 rows) ---
    pd_vah = np.full(n, np.nan); pd_val = np.full(n, np.nan); pd_poc = np.full(n, np.nan)
    sig_ta = np.zeros(n, int)
    cur_vah = cur_val = cur_poc = np.nan
    s_start = 0; sess_open = np.nan; up_cnt = dn_cnt = 0; fired = False
    for i in range(n):
        if new_sess[i]:
            if i > s_start:
                p = profile(h[s_start:i], l[s_start:i], v[s_start:i], TA_ROWS)
                if p is not None:
                    lo, st, pv = p
                    pi, a0, a1 = value_area(pv)
                    cur_poc, cur_vah, cur_val = lo + (pi + .5) * st, lo + (a1 + 1) * st, lo + a0 * st
            s_start = i; sess_open = o[i]; up_cnt = dn_cnt = 0; fired = False
        pd_vah[i], pd_val[i], pd_poc[i] = cur_vah, cur_val, cur_poc
        if not np.isnan(cur_vah):
            up_cnt = up_cnt + 1 if c[i] > cur_vah else 0
            dn_cnt = dn_cnt + 1 if c[i] < cur_val else 0
            if not fired and up_cnt >= TA_BARS and sess_open <= cur_vah and ema20[i] > ema50[i]:
                sig_ta[i] = 1
            elif not fired and dn_cnt >= TA_BARS and sess_open >= cur_val and ema20[i] < ema50[i]:
                sig_ta[i] = -1
            if sig_ta[i]:
                fired = True
    d["pd_vah"], d["pd_val"], d["pd_poc"] = pd_vah, pd_val, pd_poc

    # --- trendline break ("ممتد", no hold) ---
    ph, pl = pivots(h, TL_LEN, True), pivots(l, TL_LEN, False)
    sig_tl = np.zeros(n, int)
    last_ph = last_pl = None; dn = up = None
    for i in range(n):
        pb = i - TL_LEN
        if not np.isnan(ph[i]):
            if last_ph is not None and ph[i] < last_ph[1]:
                dn = (last_ph[0], last_ph[1], (ph[i] - last_ph[1]) / (pb - last_ph[0]))
            last_ph = (pb, ph[i])
        if not np.isnan(pl[i]):
            if last_pl is not None and pl[i] > last_pl[1]:
                up = (last_pl[0], last_pl[1], (pl[i] - last_pl[1]) / (pb - last_pl[0]))
            last_pl = (pb, pl[i])
        if i == 0:
            continue
        if dn is not None:
            now = dn[1] + dn[2] * (i - dn[0])
            if c[i] > now and c[i - 1] <= now - dn[2]:
                sig_tl[i] = 1
        if up is not None:
            now = up[1] + up[2] * (i - up[0])
            if c[i] < now and c[i - 1] >= now - up[2]:
                sig_tl[i] = -1 if sig_tl[i] == 0 else sig_tl[i]

    # --- whale bounce ---
    if whale_days is None:
        if day_bars is None:
            day_bars = bars.groupby(sess).agg(high=("high", "max"), low=("low", "min"), close=("close", "last"))
        whale_days = whale_levels_by_day(day_bars, src15, whale_cache)
    sig_wb = np.zeros(n, int); wb_tgt = np.full(n, np.nan)
    wb_open = 0; wb_t = wb_s = np.nan; wb_b = 0
    for i in range(n):
        free = wb_open == 0
        if wb_open != 0:
            hit_t = h[i] >= wb_t if wb_open > 0 else l[i] <= wb_t
            hit_s = l[i] <= wb_s if wb_open > 0 else h[i] >= wb_s
            if hit_t or hit_s or i - wb_b >= WB_MAX_BARS:
                wb_open = 0
        lv = whale_days.get(sess[i], [])
        if not (free and lv and i > 0 and atr[i] > 0):
            continue
        s = 0
        for L in lv:
            if c[i - 1] > L and l[i] <= L and c[i] > L:
                s = 1; break
            if c[i - 1] < L and h[i] >= L and c[i] < L:
                s = -1; break
        if s == 0:
            continue
        risk = WB_STOP * atr[i]; best = np.nan
        for L in lv:
            if (L - c[i]) * s >= WB_MIN_R * risk and (np.isnan(best) or abs(L - c[i]) < abs(best - c[i])):
                best = L
        if np.isnan(best):
            continue
        sig_wb[i] = s; wb_tgt[i] = best
        wb_open, wb_t, wb_s, wb_b = s, best, c[i] - s * risk, i
    d["sig_tl"], d["sig_st"], d["sig_ta"], d["sig_wb"], d["wb_tgt"] = sig_tl, sig_st, sig_ta, sig_wb, wb_tgt
    d["sig_gx"] = 0
    return d


def add_gex_signal(d: pd.DataFrame, lv: pd.DataFrame) -> pd.DataFrame:
    """gx: our own candidate on the options walls of the day (levels known before the open).
    Short when a bar trades up to the call wall and closes back below it; long mirrored at the put wall.
    First per session and side."""
    sess = d["session"].to_numpy()
    ss = pd.Series(sess)
    get = lambda col: ss.map(lv[col].astype(float).to_dict() if col in lv else {}).to_numpy(float)  # noqa: E731
    cw, pw, flip = get("cw"), get("pw"), get("flip")
    h, l, c = (d[k].to_numpy(float) for k in ("high", "low", "close"))
    pc = np.r_[np.nan, c[:-1]]
    sig = np.zeros(len(d), int); seen = set()
    for i in range(1, len(d)):
        if sess[i] != sess[i - 1]:
            continue                                   # needs a previous bar of the same session
        if not np.isnan(cw[i]) and pc[i] < cw[i] and h[i] >= cw[i] and c[i] < cw[i] and (sess[i], -1) not in seen:
            sig[i] = -1; seen.add((sess[i], -1))
        elif not np.isnan(pw[i]) and pc[i] > pw[i] and l[i] <= pw[i] and c[i] > pw[i] and (sess[i], 1) not in seen:
            sig[i] = 1; seen.add((sess[i], 1))
    d = d.copy()
    d["sig_gx"], d["cw"], d["pw"], d["flip"] = sig, cw, pw, flip
    return d
