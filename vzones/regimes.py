"""Regime labels shared by the volatility-engine v2 study (reports/vol_engine_dev/PREREG.md, section Regimes).

trend state and S0 (vzones.trend_volume_model), heat bins (percent rank of the 24-bar expected move over 500 bars),
squeeze state (ATR14/ATR100 under the train threshold), VIX quintile and term structure, time-of-day bins, and the
event-day calendar (FOMC, NFP, OPEX, quarter-end; CPI deliberately absent)."""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

HEAT_EDGES = (20, 60, 80, 90)
HEAT_NAMES = ("cold", "mild", "warm", "hot", "extreme")
SQZ_THR = {5: 0.6967, "D": 0.8833}
TOD_NAMES = ("open", "mid", "lunch", "mid2", "close")
FOMC = [  # decision days (second day of each meeting), published calendars
    "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18", "2025-07-30", "2025-09-17", "2025-10-29", "2025-12-10",
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17", "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
    "2024-01-31", "2024-03-20", "2024-05-01", "2024-06-12", "2024-07-31", "2024-09-18", "2024-11-07", "2024-12-18",
    "2023-02-01", "2023-03-22", "2023-05-03", "2023-06-14", "2023-07-26", "2023-09-20", "2023-11-01", "2023-12-13",
    "2022-01-26", "2022-03-16", "2022-05-04", "2022-06-15", "2022-07-27", "2022-09-21", "2022-11-02", "2022-12-14",
    "2021-01-27", "2021-03-17", "2021-04-28", "2021-06-16", "2021-07-28", "2021-09-22", "2021-11-03", "2021-12-15",
    "2020-01-29", "2020-03-03", "2020-03-15", "2020-04-29", "2020-06-10", "2020-07-29", "2020-09-16", "2020-11-05", "2020-12-16",
]


def percent_rank(x: np.ndarray, n: int) -> np.ndarray:
    """rank of x[t] among x[t-n+1..t] in percent (0..100); NaN until n values exist. Same rule as Pine's ta.percentrank
    (share of previous values strictly below the current one)."""
    s = pd.Series(x)
    out = s.rolling(n).apply(lambda w: 100.0 * np.mean(w[:-1] < w[-1]), raw=True)
    return out.to_numpy()


def heat_bin(rank: np.ndarray) -> np.ndarray:
    """0 cold <20, 1 mild 20-60, 2 warm 60-80, 3 hot 80-90, 4 extreme >90; -1 where the rank is NaN"""
    out = np.full(len(rank), -1)
    ok = np.isfinite(rank)
    out[ok] = np.searchsorted(np.array(HEAT_EDGES, float), rank[ok], side="right")
    return out


def squeeze_state(comp: np.ndarray, thr: float, ongoing_after: int = 12) -> tuple[np.ndarray, np.ndarray]:
    """state per bar: 0 none, 1 entering (first bar under thr), 2 inside (< ongoing_after bars), 3 ongoing, 4 exiting
    (first bar back above). Also the number of bars spent inside so far (0 outside)."""
    n = len(comp); state = np.zeros(n, int); inside = np.zeros(n, int); run = 0
    for i in range(n):
        under = np.isfinite(comp[i]) and comp[i] < thr
        if under:
            run += 1; inside[i] = run
            state[i] = 1 if run == 1 else (3 if run >= ongoing_after else 2)
        else:
            if run > 0:
                state[i] = 4
            run = 0
    return state, inside


def tod_bin(index: pd.DatetimeIndex) -> np.ndarray:
    """0 open 09:30-10:00, 1 mid 10:00-12:00, 2 lunch 12:00-13:30, 3 mid2 13:30-15:15, 4 close 15:15-16:00 (NY)"""
    m = index.hour * 60 + index.minute
    return np.where(m < 600, 0, np.where(m < 720, 1, np.where(m < 810, 2, np.where(m < 915, 3, 4))))


def event_days(dates) -> dict[str, np.ndarray]:
    """flags per date: fomc, nfp (first Friday of the month), opex (third Friday), qend (last session of Mar/Jun/Sep/Dec)"""
    ds = pd.DatetimeIndex(pd.to_datetime(list(dates))).normalize()
    fomc = ds.isin(pd.to_datetime(FOMC))
    nfp = (ds.weekday == 4) & (ds.day <= 7)
    opex = (ds.weekday == 4) & (ds.day >= 15) & (ds.day <= 21)
    # quarter end: the last date in the list within each Mar/Jun/Sep/Dec
    qend = np.zeros(len(ds), bool)
    df = pd.DataFrame({"d": ds}); df["ym"] = ds.year * 100 + ds.month
    last = df.groupby("ym")["d"].max()
    for ym, d in last.items():
        if ym % 100 in (3, 6, 9, 12):
            qend |= np.asarray(ds == d)
    return dict(fomc=np.asarray(fomc), nfp=np.asarray(nfp), opex=np.asarray(opex), qend=qend, event=np.asarray(fomc) | np.asarray(nfp) | np.asarray(opex) | qend)


def vix_regime(vix: pd.Series, vix3m: pd.Series | None, n: int = 500) -> pd.DataFrame:
    """per VIX date: percent rank over the previous n days, quintile 0..4, backwardation flag (VIX > VIX3M)."""
    pr = percent_rank(vix.to_numpy(float), n)
    out = pd.DataFrame({"vix": vix.to_numpy(float), "vix_pct": pr}, index=vix.index)
    out["vix_q"] = np.where(np.isfinite(pr), np.minimum(4, (pr // 20).astype(float)), np.nan)
    if vix3m is not None:
        v3 = vix3m.reindex(vix.index)
        out["backwardation"] = (out["vix"] > v3.to_numpy(float)).astype(float).where(v3.notna())
    return out


def vix_for_dates(dates, reg: pd.DataFrame) -> pd.DataFrame:
    """the VIX regime of the latest VIX date strictly before each session date (no look-ahead)"""
    ds = pd.DatetimeIndex(pd.to_datetime(list(dates))).normalize()
    r = reg.copy(); r.index = pd.DatetimeIndex(r.index).normalize()
    pos = r.index.searchsorted(ds, side="left") - 1
    rows = [r.iloc[p] if p >= 0 else pd.Series({c: np.nan for c in r.columns}) for p in pos]
    out = pd.DataFrame(rows); out.index = ds
    return out


# ---------------- planted tests (PREREG R1-R3) ----------------
def planted(seed: int = 1234) -> dict:
    from vzones import conviction_ma as CM
    from vzones import trend_volume as TV
    rng = np.random.default_rng(seed)
    # R1: segments of known drift sign
    segs = []; r = []
    for k in range(12):
        sign = [1, -1, 0][k % 3]; L = 400
        segs += [sign] * L; r += list(rng.normal(0.0025 * sign, 0.004, L))
    c = 100 * np.exp(np.cumsum(r)); M = CM.hma(c, 67); st = TV.trend_state(c, M); segs = np.array(segs)
    ok = np.zeros(len(c), bool)
    for k in range(12):
        ok[k * 400 + 70:(k + 1) * 400] = True
    m = ok & (segs != 0); nz = m & (st != 0)
    agree = float(np.mean(st[nz] == segs[nz])); wrong = float(np.mean(st[m] == -segs[m])); zero = float(np.mean(st[m] == 0))
    flat_false = float(np.mean(st[ok & (segs == 0)] != 0))
    # R2: planted low-vol windows
    n = 20000; sig = np.full(n, 0.004); wins = []
    i = 500
    while i + 300 < n:
        sig[i:i + 60] = 0.0012; wins.append((i, i + 60)); i += int(rng.integers(400, 700))
    r2 = rng.normal(0, 1, n) * sig; c2 = 100 * np.exp(np.cumsum(r2))
    h2 = c2 * (1 + np.abs(rng.normal(0, 0.5, n)) * sig); l2 = c2 * (1 - np.abs(rng.normal(0, 0.5, n)) * sig)
    from vzones import volume_tool as VT
    A = VT.atr(h2, l2, c2); A100 = pd.Series(np.maximum(h2 - l2, 0)).ewm(alpha=1 / 100, adjust=False).mean().to_numpy(); comp = A / A100
    thr = float(np.nanpercentile(comp[:5000], 10))
    state, _ = squeeze_state(comp, thr)
    hit = float(np.mean([(state[a:b + 20] == 1).any() for a, b in wins]))
    outside = np.ones(n, bool)
    for a, b in wins:
        outside[max(0, a - 40):b + 60] = False
    starts = rng.integers(500, n - 40, 400); fp = float(np.mean([(state[s:s + 40] == 1).any() for s in starts if outside[s:s + 40].all()]))
    # R3: heat rank on iid data is uniform
    x = rng.normal(0, 1, 20000); pr = percent_rank(np.abs(x), 500); pr = pr[np.isfinite(pr)]
    from scipy import stats
    ks = stats.kstest(pr / 100.0, "uniform")
    res = dict(R1_sign_agreement_among_trend_bars=round(agree, 4), R1_wrong_sign_share=round(wrong, 4), R1_zero_share=round(zero, 4), R1_flat_segment_false_state=round(flat_false, 4), R2_squeeze_hit=round(hit, 4), R2_false_positive=round(fp, 4), R3_ks_p=round(float(ks.pvalue), 4),
               thr_used=round(thr, 4))
    res["pass"] = bool(agree >= 0.9 and wrong <= 0.05 and hit >= 0.8 and fp <= 0.05 and ks.pvalue > 0.01)
    return res
