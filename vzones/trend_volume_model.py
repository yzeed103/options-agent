"""One trend-volume model (reports/trend_volume_model/PREREG.md): trend state and strength (inertia, impulse), levels
with mass, touches, breaks with energy and false-break flags, retests. Every volume quantity has a price-only twin.
All per-bar quantities and events use past bars only; the targets use the future (evaluation only)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from vzones import conviction_ma as CM
from vzones import hma_successor as HS
from vzones import trend_volume as TV
from vzones import volume_tool as VT

HMA_LEN = {5: 67, 15: 66, 60: 56}
G_DAMP = 0.85
ER_N, IMP_N = 20, 10
BAND, RETEST_BAND = 0.1, 0.2
MIN_AGE, FIRST, HOLD, FALSE_N, BEYOND, RETEST_WIN, RETEST_HOLD = 10, 5, 12, 3, 0.5, 24, 6
STRONG, SMALL = 1.5, 0.7


def efficiency(c, n=ER_N):
    return HS.efficiency_ratio(c, n)


def impulse(o, c, A, rvol, n=IMP_N):
    body = (c - o) / A
    J = pd.Series(body * np.where(np.isfinite(rvol), rvol, 1.0)).rolling(n).sum().to_numpy()
    J0 = pd.Series(body).rolling(n).sum().to_numpy()
    return J, J0


def run(d: pd.DataFrame, tf_min: int, day_levels: pd.DataFrame | None = None, k: int = 2) -> dict:
    """Per-bar table, trend events (every 5th trend bar), touches, breaks (with retests)."""
    o, h, l, c, v = (d[x].to_numpy(float) for x in ("open", "high", "low", "close", "volume"))
    n = len(c)
    A = VT.atr(h, l, c)
    rvol = VT.rvol_set(d, tf_min)[0]
    sess, _ = VT.sessions_slots(d.index, tf_min)
    L_ = HMA_LEN.get(tf_min, 67)
    M = CM.hma(c, L_); D = HS.dhma(c, L_, G_DAMP)
    st = TV.trend_state(c, M)
    sM = np.sign(np.r_[np.nan, np.diff(M)]); sD = np.sign(np.r_[np.nan, np.diff(D)])
    confirmed = (sM == sD) & (sM != 0)
    I = efficiency(c); J, J0 = impulse(o, c, A, rvol)
    S = 0.5 * I + 0.5 * np.clip(np.abs(J) / 3, 0, 1); S0 = 0.5 * I + 0.5 * np.clip(np.abs(J0) / 3, 0, 1)
    rng = np.maximum(h - l, 1e-12)
    vmed = pd.Series(v).rolling(20 * (78 if tf_min == 5 else 26 if tf_min == 15 else 7), min_periods=200).median().to_numpy()
    bars = pd.DataFrame(dict(state=st, confirmed=confirmed, I=I, J=J, J0=J0, S=S, S0=S0, rvol=rvol, M=M, D=D, A=A), index=d.index)
    # ---- levels: mass and time, touches, breaks, retests
    hz = {5: 24, 15: 8, 60: 3}.get(tf_min, 24)
    live, watch, touches, breaks = [], [], [], []
    s_start = 0
    next_id = 0                                   # explicit level ids (Python's id() is reused after a level dies)
    for i in range(n):
        if i == 0 or sess[i] != sess[i - 1]:
            s_start = i; live = []; watch = []
            if day_levels is not None and sess[i] in day_levels.index:
                for name, L in day_levels.loc[sess[i]].items():
                    if np.isfinite(L) and L > 0:
                                live.append(dict(L=float(L), origin=i, side=0, type=name, mass=0.0, time=0, last_touch=-99, touches=0, lid=next_id)); next_id += 1
        p = i - k
        if p - k >= s_start and p >= 1:
            # a swing level starts with the mass and time of its own formation bars (p - k .. i)
            if h[p] > h[p - k:p].max() and h[p] > h[p + 1:i + 1].max():
                fb = [j for j in range(p - k, i + 1) if abs(h[j] - h[p]) <= BAND * A[j]]
                live.append(dict(L=float(h[p]), origin=p, side=-1, type="swing_high", mass=float(v[fb].sum()), time=len(fb), last_touch=i, touches=0, lid=next_id)); next_id += 1
            if l[p] < l[p - k:p].min() and l[p] < l[p + 1:i + 1].min():
                fb = [j for j in range(p - k, i + 1) if abs(l[j] - l[p]) <= BAND * A[j]]
                live.append(dict(L=float(l[p]), origin=p, side=1, type="swing_low", mass=float(v[fb].sum()), time=len(fb), last_touch=i, touches=0, lid=next_id)); next_id += 1
        for lv in live:
            if lv["side"] == 0 and lv["origin"] == i:
                lv["side"] = 1 if c[i] > lv["L"] else -1 if c[i] < lv["L"] else 0
        # retest watch (broken levels)
        for w in list(watch):
            if i - w["t"] > RETEST_WIN:
                watch.remove(w); continue
            if w["dir"] * (c[i] - w["L"]) <= 0:                      # closed back across: the break failed, no retest
                watch.remove(w); continue
            near = (w["dir"] > 0 and l[i] <= w["L"] + RETEST_BAND * A[i]) or (w["dir"] < 0 and h[i] >= w["L"] - RETEST_BAND * A[i])
            if near:
                w["retest_t"] = i; w["ratio_v"] = rvol[i] / w["rvol"] if np.isfinite(rvol[i]) and w["rvol"] > 0 else np.nan
                w["ratio_r"] = rng[i] / w["rng"]
                watch.remove(w)
        broken, cand = [], {}
        for lv in live:
            if lv["side"] == 0 or i == lv["origin"]:
                continue
            crossed = (lv["side"] < 0 and c[i] > lv["L"]) or (lv["side"] > 0 and c[i] < lv["L"])
            if crossed:
                broken.append(lv)
                if i - lv["origin"] >= MIN_AGE and i - s_start >= FIRST:
                    dist = abs(c[i - 1] - lv["L"])
                    if lv["type"] not in cand or dist < cand[lv["type"]][0]:
                        cand[lv["type"]] = (dist, lv)
                continue
            # touch: within the band on the level's side, no close beyond, >= 2 bars after the previous touch
            within = (lv["side"] < 0 and abs(h[i] - lv["L"]) <= BAND * A[i]) or (lv["side"] > 0 and abs(l[i] - lv["L"]) <= BAND * A[i])
            if within:
                if i - lv["last_touch"] >= 2 and i - lv["origin"] >= 3:
                    touches.append(dict(t=i, L=lv["L"], type=lv["type"], dir=-lv["side"], mass=lv["mass"] / vmed[i] if np.isfinite(vmed[i]) and vmed[i] > 0 else np.nan,
                                        time=lv["time"], n_touch=lv["touches"] + 1, level_id=lv["lid"]))
                    lv["last_touch"] = i; lv["touches"] += 1
                lv["mass"] += v[i]; lv["time"] += 1
        for lv in broken:
            live.remove(lv)
        for typ, (_, lv) in cand.items():
            dr = 1 if lv["side"] < 0 else -1; L = lv["L"]
            r_atr = rng[i] / A[i]
            wick = ((h[i] - c[i]) if dr > 0 else (c[i] - l[i])) / rng[i]
            breaks.append(dict(t=i, L=L, type=typ, dir=dr, origin=lv["origin"], mass=lv["mass"] / vmed[i] if np.isfinite(vmed[i]) and vmed[i] > 0 else np.nan, time=lv["time"],
                               n_touch=lv["touches"], rvol=rvol[i], range_atr=r_atr, E=r_atr * rvol[i], E0=r_atr, I=I[i], state=st[i],
                               absorption=bool(rvol[i] > STRONG and r_atr < SMALL), wick=bool(wick > 0.5), counter=bool(st[i] == -dr),
                               retest_t=np.nan, ratio_v=np.nan, ratio_r=np.nan, level_id=lv["lid"]))
            watch.append(dict(L=L, dir=dr, t=i, rvol=rvol[i], rng=rng[i], idx=len(breaks) - 1))
        # attach completed retests
        for w in [w for w in watch if "retest_t" in w]:
            pass
    # the retest fields are attached when found (watch entries hold the break index)
    return dict(bars=bars, touches=pd.DataFrame(touches), breaks=pd.DataFrame(breaks), frames=dict(o=o, h=h, l=l, c=c, A=A, M=M, sess=sess, rvol=rvol, hz=hz), st=st)


def _attach_retests(res):
    """second pass: retests found by re-walking the watch logic cheaply from the break table"""
    br = res["breaks"]; f = res["frames"]
    if len(br) == 0:
        return br
    h, l, c, A, sess, rvol = f["h"], f["l"], f["c"], f["A"], f["sess"], f["rvol"]
    rng = np.maximum(h - l, 1e-12)
    rt, rv, rr, rhold = [], [], [], []
    for t, dr, L in zip(br["t"], br["dir"], br["L"]):
        t = int(t); found = None
        for j in range(t + 1, min(len(c), t + RETEST_WIN + 1)):
            if sess[j] != sess[t] or dr * (c[j] - L) <= 0:
                break
            if (dr > 0 and l[j] <= L + RETEST_BAND * A[j]) or (dr < 0 and h[j] >= L - RETEST_BAND * A[j]):
                found = j; break
        if found is None:
            rt.append(np.nan); rv.append(np.nan); rr.append(np.nan); rhold.append(np.nan); continue
        rt.append(found); rv.append(rvol[found] / rvol[t] if np.isfinite(rvol[found]) and np.isfinite(rvol[t]) and rvol[t] > 0 else np.nan); rr.append(rng[found] / rng[t])
        ok = found + RETEST_HOLD < len(c) and sess[found + RETEST_HOLD] == sess[t]
        rhold.append(float(all(dr * (c[j] - L) > 0 for j in range(found + 1, found + RETEST_HOLD + 1))) if ok else np.nan)
    br["retest_t"], br["ratio_v"], br["ratio_r"], br["retest_hold"] = rt, rv, rr, rhold
    return br


# ---------------- targets (future) ----------------
def targets(res: dict) -> dict:
    f = res["frames"]; h, l, c, A, M, sess, hz = (f[k] for k in ("h", "l", "c", "A", "M", "sess", "hz"))
    st = res["st"]; bars = res["bars"]
    n = len(c)

    def remain(t):
        r = 0
        while t + r + 1 < n and sess[t + r + 1] == sess[t]:
            r += 1
        return r
    # trend events: every 5th trend bar of a run
    ev = []; run = 0; dr = 0
    for i in range(1, n):
        if sess[i] != sess[i - 1]:
            run = 0; continue
        if st[i] != 0 and st[i] == dr:
            run += 1
        elif st[i] != 0:
            dr, run = st[i], 1
        else:
            run = 0; continue
        if run % 5 != 0:
            continue
        rm = remain(i)
        life, cens = 0, True
        for j in range(i + 1, min(n, i + 49)):
            if sess[j] != sess[i]:
                break
            if dr * (c[j] - M[j]) < -0.3 * A[j]:
                cens = False; break
            life += 1
        fp, _ = TV.first_passage(h, l, c, A, sess, i, dr, hz)
        ev.append(dict(t=i, dir=dr, I=bars["I"].iloc[i], J=bars["J"].iloc[i] * dr, J0=bars["J0"].iloc[i] * dr, S=bars["S"].iloc[i], S0=bars["S0"].iloc[i], rvol=bars["rvol"].iloc[i],
                       alive12=float(dr * (c[i + 12] - M[i + 12]) > 0) if rm >= 12 else np.nan, alive24=float(dr * (c[i + 24] - M[i + 24]) > 0) if rm >= 24 else np.nan,
                       fp=fp, life=life, censored=cens))
    trend = pd.DataFrame(ev)
    # touches: respect = no close beyond L within 3 bars
    tc = res["touches"].copy()
    if len(tc):
        resp = []
        for t, L, dr in zip(tc["t"], tc["L"], tc["dir"]):
            t = int(t); rm = remain(t)
            resp.append(float(all(dr * (c[t + j] - L) <= 0 for j in range(1, 4))) if rm >= 3 else np.nan)
        tc["respect"] = resp
    # breaks: hold, false, fp, retest
    br = _attach_retests(res)
    if len(br):
        hold, false, fps = [], [], []
        for t, dr, L in zip(br["t"], br["dir"], br["L"]):
            t = int(t); rm = remain(t)
            hold.append(float(all(dr * (c[t + j] - L) > 0 for j in range(1, HOLD + 1)) and dr * (c[t + HOLD] - L) >= BEYOND * A[t]) if rm >= HOLD else np.nan)
            false.append(float(any(dr * (c[t + j] - L) <= 0 for j in range(1, FALSE_N + 1))) if rm >= FALSE_N else np.nan)
            fps.append(TV.first_passage(h, l, c, A, sess, t, dr, hz)[0])
        br["hold"], br["false"], br["fp"] = hold, false, fps
    return dict(trend=trend, touches=tc, breaks=br)
