"""The eyes round: tests of the thesis (reports/eyes/DEFINITIONS.md) on history, and the same rules on today's bars.

Nothing here trades. Each function implements one definition; the definitions file is the spec.
"""
from __future__ import annotations

import hashlib
import os
import pickle

import numpy as np
import pandas as pd

from . import signals as S
from . import sim
from .data import LEVEL_COLS, RUNTIME, levels_for_days, resample15

GROUPS = {"index": {"SPY", "QQQ"},
          "mega": {"AAPL", "AMZN", "META", "NVDA", "AVGO", "TSLA", "LLY", "ORCL", "COST", "JNJ", "UNH", "INTU", "NOW"}}
WALLS = ("cw", "pw", "cwoi", "pwoi")
LEVEL_TYPES = ("cw", "pw", "cwoi", "pwoi", "flip", "dflip", "pin", "whale_poc", "whale_vah", "whale_val", "whale_peak")
FP_K = 1.5           # first-passage barrier, chart ATR
NEAR = 0.5           # "near", daily ATR
MAX_DIST = 3.0       # whale level search radius, daily ATR
CACHE = os.path.join(RUNTIME, "cache")


def group_of(sym: str) -> str:
    for g, s in GROUPS.items():
        if sym in s:
            return g
    return "high_beta"


# ---------------- frames ----------------
def _va_cache(sym):
    p = os.path.join(CACHE, f"whale_va_{sym}.pkl")
    try:
        return pickle.load(open(p, "rb")) if os.path.exists(p) else {}
    except Exception:  # noqa: BLE001
        return {}


def build(sym: str, bars5: pd.DataFrame, tfs=(5, 15), use_yahoo: bool = True, gex: pd.DataFrame | None = None,
          vix=None, use_cache: bool = True, whale_days=None, whale_va=None, paths: bool = True) -> dict:
    """{tf: frame} with bars, signals, readings, the day's options levels, excursions and first passages, plus
    {'whale': {date: [levels]}, 'whale_va': {date: [(poc, vah, val)]}}."""
    from .live import whale_days_cached
    days = sim.official_days(sym, sim.day_table(bars5), use_yahoo)
    if whale_days is None:
        whale_days = whale_days_cached(sym, bars5, use_cache, use_yahoo) if use_cache else \
            S.whale_levels_by_day(days, resample15(bars5))
    if whale_va is None:
        vc = _va_cache(sym) if use_cache else {}
        n0 = len(vc)
        whale_va = S.whale_va_by_day(days, resample15(bars5), vc)
        if use_cache and len(vc) != n0:
            os.makedirs(CACHE, exist_ok=True)
            pickle.dump(vc, open(os.path.join(CACHE, f"whale_va_{sym}.pkl"), "wb"))
    sessions = list(days.index)
    lv = levels_for_days(sym, sessions) if gex is None else gex.reindex(sessions)
    if vix is None:
        from .data import vix_prev_close
        vix = vix_prev_close(sessions)
    vx = vix
    prep = sim.prepare(sym, bars5, tfs=tfs, whale_days=whale_days, gex=lv, vix=vx, use_yahoo=use_yahoo)
    out = {"whale": whale_days, "whale_va": whale_va, "levels": lv}
    for tf, p in prep.items():
        d = p.d.copy()
        for col in LEVEL_COLS:
            d[col] = d["session"].map(lv[col].to_dict() if col in lv else {}).astype(float)
        d["slot"] = (d["minute"] // 30).astype(int)
        if paths:
            add_paths(d)
        out[tf] = d
    return out


def add_paths(d: pd.DataFrame) -> None:
    """Excursions to the close (daily ATR) and first passages of +-1.5 chart ATR, per bar (outcome rules)."""
    h, l, c = (d[k].to_numpy(float) for k in ("high", "low", "close"))
    atr, datr = d["atr"].to_numpy(float), d["datr"].to_numpy(float)
    sess = d["session"].to_numpy()
    n = len(d)
    end = np.empty(n, int)                       # index of the session's last bar
    last = np.r_[np.flatnonzero(sess[1:] != sess[:-1]), n - 1]
    start = 0
    for e in last:
        end[start:e + 1] = e
        start = e + 1
    fhi = np.full(n, np.nan); flo = np.full(n, np.nan)
    for e0, e1 in zip(np.r_[0, last[:-1] + 1], last):
        hh, ll = h[e0:e1 + 1], l[e0:e1 + 1]
        rh = np.maximum.accumulate(hh[::-1])[::-1]; rl = np.minimum.accumulate(ll[::-1])[::-1]
        fhi[e0:e1] = rh[1:]; flo[e0:e1] = rl[1:]
    d["fwd_hi"], d["fwd_lo"], d["end"] = fhi, flo, end
    d["e_up"] = (fhi - c) / datr
    d["e_dn"] = (c - flo) / datr
    t_up = np.full(n, -1); t_dn = np.full(n, -1)
    for i in range(n):
        e = end[i]
        if e <= i or not np.isfinite(atr[i]):
            continue
        up, dn = c[i] + FP_K * atr[i], c[i] - FP_K * atr[i]
        a = np.flatnonzero(h[i + 1:e + 1] >= up)
        b = np.flatnonzero(l[i + 1:e + 1] <= dn)
        t_up[i] = i + 1 + a[0] if len(a) else -1
        t_dn[i] = i + 1 + b[0] if len(b) else -1
    d["t_up"], d["t_dn"] = t_up, t_dn


def fp_outcome(t_up: int, t_dn: int, s: int):
    """First passage for direction s: 1 = favourable barrier first, 0 = adverse first (or both in one bar:
    adverse counted first, like the simulator's stop-first rule), nan = neither before the close."""
    fav, adv = (t_up, t_dn) if s > 0 else (t_dn, t_up)
    if fav < 0 and adv < 0:
        return np.nan
    if fav < 0:
        return 0.0
    if adv < 0:
        return 1.0
    return 1.0 if fav < adv else 0.0


# ---------------- base rates ----------------
class Base:
    """Same-symbol, same-timeframe, same 30-minute slot comparison rates."""

    def __init__(self, d: pd.DataFrame):
        self.e = {}
        self.fp = {}
        self.run = {}
        slot = d["slot"].to_numpy()
        tu, tn = d["t_up"].to_numpy(), d["t_dn"].to_numpy()
        for s, col in ((1, "e_up"), (-1, "e_dn")):
            v = d[col].to_numpy(float)
            for k in np.unique(slot):
                m = (slot == k) & np.isfinite(v)
                self.e[(k, s)] = np.sort(v[m])
                self.run[(k, s)] = float(v[m].mean()) if m.any() else np.nan
                o = np.array([fp_outcome(a, b, s) for a, b in zip(tu[slot == k], tn[slot == k])])
                o = o[np.isfinite(o)]
                self.fp[(k, s)] = float(o.mean()) if len(o) else np.nan

    def reach(self, slot: int, s: int, x: float) -> float:
        arr = self.e.get((slot, s))
        if arr is None or not len(arr) or not np.isfinite(x):
            return np.nan
        return 1.0 - np.searchsorted(arr, x, side="left") / len(arr)


# ---------------- events ----------------
def _cross(d: pd.DataFrame) -> np.ndarray:
    a, b = d["sma20"].to_numpy(float), d["sma50"].to_numpy(float)
    diff = np.sign(a - b)
    out = np.zeros(len(d), int)
    ok = np.isfinite(a) & np.isfinite(b)
    ch = np.r_[False, (diff[1:] != diff[:-1]) & ok[1:] & ok[:-1] & (diff[1:] != 0)]
    out[ch] = diff[ch].astype(int)
    return out


def trend_events(sym: str, tf: int, d: pd.DataFrame, base: Base) -> list[dict]:
    """Thesis 1 (+ the entries reused by thesis 2 and 4a)."""
    sig = d["sig_tl"].to_numpy()
    cr = _cross(d)
    it, st = d["it_dir"].to_numpy(), d["st_state"].to_numpy()
    sess, slot = d["session"].to_numpy(), d["slot"].to_numpy()
    tu, tn = d["t_up"].to_numpy(), d["t_dn"].to_numpy()
    eu, ed = d["e_up"].to_numpy(float), d["e_dn"].to_numpy(float)
    idx = d.index
    out = []
    for i in np.flatnonzero(sig):
        s = int(sig[i])
        ent = {"tl": i}
        if it[i] == s:
            ent["tl+IT"] = i
        if st[i] == s:
            ent["tl+ST"] = i
        for N in (3, 6):
            lo, hi = max(0, i - N), min(len(d) - 1, i + N)
            ks = [k for k in range(lo, hi + 1) if cr[k] == s and sess[k] == sess[i]]
            if not ks:
                continue
            j = i if any(k <= i for k in ks) else min(ks)
            ent[f"tl+MA{N}"] = j
            if it[j] == s and st[j] == s:
                ent[f"tl+all{N}"] = j
        for var, j in ent.items():
            run = eu[j] if s > 0 else ed[j]
            out.append(dict(sym=sym, tf=tf, date=sess[j], time=idx[j], i=int(j), variant=var, side=s, slot=int(slot[j]),
                            hitA=fp_outcome(tu[j], tn[j], s), baseA=base.fp.get((int(slot[j]), s), np.nan),
                            run=run, base_run=base.run.get((int(slot[j]), s), np.nan)))
    return out


def wall_events(d: pd.DataFrame, entries: list[dict], base: Base) -> list[dict]:
    """Thesis 2 on the tl and tl+all6 entries."""
    c, h, l = d["close"].to_numpy(float), d["high"].to_numpy(float), d["low"].to_numpy(float)
    datr, end = d["datr"].to_numpy(float), d["end"].to_numpy()
    W = d[list(WALLS)].to_numpy(float)
    out = []
    for e in entries:
        if e["variant"] not in ("tl", "tl+all6"):
            continue
        j, s = e["i"], e["side"]
        ws = np.unique(W[j][np.isfinite(W[j])])
        if not len(ws) or not np.isfinite(datr[j]) or end[j] <= j:
            continue
        ahead = ws[(ws - c[j]) * s > 0]
        if not len(ahead):
            continue
        tgt = ahead.min() if s > 0 else ahead.max()
        behind = ws[(ws - c[j]) * s < 0]
        opp = (behind.max() if s > 0 else behind.min()) if len(behind) else np.nan
        x = (tgt - c[j]) * s / datr[j]
        seg_h, seg_l = h[j + 1:end[j] + 1], l[j + 1:end[j] + 1]
        reach_t = np.flatnonzero(seg_h >= tgt) if s > 0 else np.flatnonzero(seg_l <= tgt)
        hit = float(len(reach_t) > 0)
        if np.isfinite(opp):
            opp_t = np.flatnonzero(seg_l <= opp) if s > 0 else np.flatnonzero(seg_h >= opp)
            hit_before_opp = float(len(reach_t) > 0 and (not len(opp_t) or reach_t[0] < opp_t[0]))
            near_behind = (c[j] - opp) * s / datr[j] <= NEAR
        else:
            hit_before_opp, near_behind = hit, False
        out.append(dict(e, dist=x, hit=hit, base=base.reach(e["slot"], s, x), hit_opp=hit_before_opp,
                        near_wall_behind=bool(near_behind)))
    return out


def _whale_list(day, whale, whale_va) -> np.ndarray:
    lv = list(whale.get(day, []))
    for t in whale_va.get(day, []):
        lv += list(t)
    return np.array(sorted(set(round(x, 4) for x in lv)), float)


def magnet_events(sym: str, tf: int, d: pd.DataFrame, entries: list[dict], whale: dict, whale_va: dict, base: Base) -> list[dict]:
    """Thesis 4a (tl entries) and 4b (bars at :00 and :30)."""
    c, datr, end = d["close"].to_numpy(float), d["datr"].to_numpy(float), d["end"].to_numpy()
    fhi, flo = d["fwd_hi"].to_numpy(float), d["fwd_lo"].to_numpy(float)
    sess, slot, minute = d["session"].to_numpy(), d["slot"].to_numpy(), d["minute"].to_numpy()
    idx = d.index
    cache = {}
    out = []

    def one(i, s, kind, variant=None):
        if end[i] <= i or not np.isfinite(datr[i]) or datr[i] <= 0:
            return
        day = sess[i]
        if day not in cache:
            cache[day] = _whale_list(day, whale, whale_va)
        lv = cache[day]
        ahead = lv[(lv - c[i]) * s > 0]
        if not len(ahead):
            return
        L = ahead.min() if s > 0 else ahead.max()
        x = (L - c[i]) * s / datr[i]
        if x > MAX_DIST:
            return
        hit = float(fhi[i] >= L) if s > 0 else float(flo[i] <= L)
        out.append(dict(sym=sym, tf=tf, date=day, time=idx[i], kind=kind, variant=variant, side=s, slot=int(slot[i]),
                        dist=x, hit=hit, base=base.reach(int(slot[i]), s, x)))

    for e in entries:
        if e["variant"] == "tl":
            one(e["i"], e["side"], "4a", "tl")
    for i in np.flatnonzero((minute % 30) == 0):
        one(i, 1, "4b")
        one(i, -1, "4b")
    return out


def _seed(*parts) -> int:
    return int(hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:8], 16)


def first_touches(c: np.ndarray, h: np.ndarray, l: np.ndarray, i0: int, i1: int, L: float):
    """First touch of L in bars i0+1..i1 (one session): (t, approach +1 from below / -1 from above, passed, pending)
    or None. passed = a close beyond L on the far side in bars t..t+3 (within the session); pending = fewer than 3
    bars after the touch so far and no pass yet (live only)."""
    pc, hh, ll = c[i0:i1], h[i0 + 1:i1 + 1], l[i0 + 1:i1 + 1]
    hit = ((pc < L) & (hh >= L)) | ((pc > L) & (ll <= L))
    if not hit.any():
        return None
    t = i0 + 1 + int(np.argmax(hit))
    a = 1 if c[t - 1] < L else -1
    w = c[t:min(t + 4, i1 + 1)]
    passed = bool(((w > L) if a > 0 else (w < L)).any())
    pending = (t + 3 > i1) and not passed
    return t, a, passed, pending


def level_events(sym: str, tf: int, d: pd.DataFrame, whale: dict, whale_va: dict, last_complete: bool = True) -> list[dict]:
    """Level reactions on first touch, real levels and two pseudo-levels per real level."""
    sess, datr = d["session"].to_numpy(), d["datr"].to_numpy(float)
    c, h, l = (d[k].to_numpy(float) for k in ("close", "high", "low"))
    bounds = np.r_[0, np.flatnonzero(sess[1:] != sess[:-1]) + 1, len(d)]
    idx = d.index
    out = []
    for b0, b1 in zip(bounds[:-1], bounds[1:]):
        i0, i1 = b0, b1 - 1
        day = sess[i0]
        if i1 - i0 < 4 or not np.isfinite(datr[i0]) or datr[i0] <= 0:
            continue
        levels = []
        for col in ("cw", "pw", "cwoi", "pwoi", "flip", "dflip", "pin"):
            v = d[col].iat[i0]
            if np.isfinite(v):
                levels.append((col, v))
        for t in whale_va.get(day, []):
            levels += [("whale_poc", t[0]), ("whale_vah", t[1]), ("whale_val", t[2])]
        levels += [("whale_peak", x) for x in whale.get(day, [])]
        for k, (typ, L) in enumerate(levels):
            rng = np.random.default_rng(_seed(sym, tf, day, typ, k))
            u = rng.uniform(0.25, 1.0, 2)
            for real, LL in ((1, L), (0, L + u[0] * datr[i0]), (0, L - u[1] * datr[i0])):
                ft = first_touches(c, h, l, i0, i1, LL)
                if ft is None:
                    continue
                t, a, passed, pending = ft
                if pending and last_complete:
                    pending = False                     # history: the session is over, fewer bars just remain
                out.append(dict(sym=sym, tf=tf, date=day, time=idx[t], type=typ, level=float(LL), real=real,
                                approach=a, passed=float(passed), rejected=float(not passed), pending=pending))
    return out


def flip_days(sym: str, d5: pd.DataFrame, level_ev: list[dict], vix: pd.Series | None = None) -> list[dict]:
    """Thesis 3, one row per symbol-day with a FLIP (and the same for DFLIP)."""
    sess = d5["session"].to_numpy()
    minute = d5["minute"].to_numpy()
    c, h, l = (d5[k].to_numpy(float) for k in ("close", "high", "low"))
    datr = d5["datr"].to_numpy(float)
    tl = d5["sig_tl"].to_numpy()
    rej = {}
    for e in level_ev:
        if e["real"] and e["type"] in WALLS and e["tf"] == 5 and e["time"].hour * 60 + e["time"].minute >= 600:
            r = rej.setdefault(e["date"], [0, 0])
            r[0] += e["rejected"]; r[1] += 1
    out = []
    bounds = np.r_[0, np.flatnonzero(sess[1:] != sess[:-1]) + 1, len(d5)]
    for b0, b1 in zip(bounds[:-1], bounds[1:]):
        day = sess[b0]
        k10 = [i for i in range(b0, b1) if minute[i] == 25]
        if not k10 or not np.isfinite(datr[b0]):
            continue
        i10 = k10[0]
        after = np.arange(i10 + 1, b1)
        if len(after) < 6:
            continue
        for col in ("flip", "dflip"):
            F = d5[col].iat[b0]
            if not np.isfinite(F):
                continue
            side = 1 if c[i10] > F else -1
            # change of side: three consecutive closes on the other side after 10:00
            other = (c[after] - F) * side < 0
            run = np.convolve(other.astype(int), np.ones(3, int), "valid")
            chg = int(np.argmax(run == 3)) if (run == 3).any() else -1
            row = dict(sym=sym, date=day, level=col, side=side, vix=float(vix.get(day, np.nan)) if vix is not None else np.nan,
                       range_atr=(h[after].max() - l[after].min()) / datr[b0], tl_breaks=int((tl[after] != 0).sum()),
                       wall_rej=rej.get(day, [0, 0])[0], wall_touch=rej.get(day, [0, 0])[1], changed=chg >= 0)
            if chg >= 0:
                k = after[chg + 2]
                bef, aft = np.arange(i10 + 1, k + 1), np.arange(k + 1, b1)
                # average bar range (high - low) in daily ATR: comparable between windows of different length
                row["range_before_per_bar"] = float(np.mean(h[bef] - l[bef]) / datr[b0])
                row["range_after_per_bar"] = float(np.mean(h[aft] - l[aft]) / datr[b0]) if len(aft) else np.nan
            out.append(row)
    return out


# ---------------- statistics ----------------
def boot_excess(df: pd.DataFrame, val: str, base: str | None = None, cluster=("sym", "date"), n=2000, seed=0):
    """Mean of val (or val - base) with a 95% interval resampling whole clusters (symbol-days)."""
    x = df[val].to_numpy(float) - (df[base].to_numpy(float) if base else 0)
    m = np.isfinite(x)
    if m.sum() < 5:
        return dict(n=int(m.sum()), mean=np.nan, lo=np.nan, hi=np.nan)
    g = pd.factorize(pd.Series(list(zip(*[df[cl].astype(str) for cl in cluster])))[m])[0] if len(cluster) > 1 else \
        pd.factorize(df[cluster[0]].astype(str)[m])[0]
    xs = x[m]
    k = g.max() + 1
    sums, cnts = np.bincount(g, xs, k), np.bincount(g, None, k)
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, k, (n, k))
    bs = sums[draws].sum(1) / cnts[draws].sum(1)
    return dict(n=int(m.sum()), mean=float(xs.mean()), lo=float(np.percentile(bs, 2.5)), hi=float(np.percentile(bs, 97.5)))


def boot_diff(df: pd.DataFrame, val: str, grp: str, cluster="date", n=2000, seed=0):
    """mean(val | grp True) - mean(val | grp False), resampling clusters (dates)."""
    d = df[np.isfinite(df[val].astype(float))]
    if d[grp].nunique() < 2:
        return dict(n1=int(d[grp].sum()), n0=int((~d[grp]).sum()), diff=np.nan, lo=np.nan, hi=np.nan)
    g = pd.factorize(d[cluster].astype(str))[0]
    k = g.max() + 1
    x, a = d[val].to_numpy(float), d[grp].to_numpy(bool)
    s1, c1 = np.bincount(g, x * a, k), np.bincount(g, a.astype(float), k)
    s0, c0 = np.bincount(g, x * ~a, k), np.bincount(g, (~a).astype(float), k)
    rng = np.random.default_rng(seed)
    dr = rng.integers(0, k, (n, k))
    b = s1[dr].sum(1) / np.maximum(c1[dr].sum(1), 1) - s0[dr].sum(1) / np.maximum(c0[dr].sum(1), 1)
    return dict(n1=int(a.sum()), n0=int((~a).sum()), m1=float(x[a].mean()), m0=float(x[~a].mean()),
                diff=float(x[a].mean() - x[~a].mean()), lo=float(np.percentile(b, 2.5)), hi=float(np.percentile(b, 97.5)))


def boot_two_sets(real: pd.DataFrame, pseudo: pd.DataFrame, val: str, cluster=("sym", "date"), n=2000, seed=0):
    """mean(real) - mean(pseudo), resampling symbol-days jointly."""
    key = lambda df: pd.Series(list(zip(*[df[c].astype(str) for c in cluster])), index=df.index)  # noqa: E731
    allk = pd.concat([key(real), key(pseudo)])
    codes, uniq = pd.factorize(allk)
    k = len(uniq)
    gr, gp = codes[:len(real)], codes[len(real):]
    xr, xp = real[val].to_numpy(float), pseudo[val].to_numpy(float)
    sr, cr = np.bincount(gr, xr, k), np.bincount(gr, None, k)
    sp, cp = np.bincount(gp, xp, k), np.bincount(gp, None, k)
    rng = np.random.default_rng(seed)
    dr = rng.integers(0, k, (n, k))
    b = sr[dr].sum(1) / np.maximum(cr[dr].sum(1), 1) - sp[dr].sum(1) / np.maximum(cp[dr].sum(1), 1)
    return dict(n=len(real), n_base=len(pseudo), rate=float(xr.mean()) if len(xr) else np.nan,
                base=float(xp.mean()) if len(xp) else np.nan, diff=float(xr.mean() - xp.mean()) if len(xr) and len(xp) else np.nan,
                lo=float(np.percentile(b, 2.5)), hi=float(np.percentile(b, 97.5)))


def run_symbol(sym: str, bars5: pd.DataFrame, use_yahoo=True, gex=None, vix=None, use_cache=True, frames=None) -> dict:
    """All history events of one symbol: {'trend', 'wall', 'magnet', 'level', 'flip'} -> list of dicts."""
    fr = frames or build(sym, bars5, use_yahoo=use_yahoo, gex=gex, vix=vix, use_cache=use_cache)
    out = {k: [] for k in ("trend", "wall", "magnet", "level", "flip")}
    for tf in (5, 15):
        if tf not in fr:
            continue
        d = fr[tf]
        b = Base(d)
        te = trend_events(sym, tf, d, b)
        out["trend"] += te
        out["wall"] += wall_events(d, te, b)
        out["magnet"] += magnet_events(sym, tf, d, te, fr["whale"], fr["whale_va"], b)
        out["level"] += level_events(sym, tf, d, fr["whale"], fr["whale_va"])
    if 5 in fr:
        vx = fr[5]["vix"].groupby(fr[5]["session"]).first()
        out["flip"] += flip_days(sym, fr[5], [e for e in out["level"] if e["tf"] == 5], vx)
    return out
