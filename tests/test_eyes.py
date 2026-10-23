"""Tests of the eyes round (vzones/assistant/eyes.py, eyes_live.py). Synthetic bars, no network.

- planted magnet: price pulled toward a planted level shows a positive excess with an interval above zero
- random walk: the same test shows no effect (the interval contains zero)
- no lookahead: events and final observations on a prefix equal those on the full data
- restart: re-running the live step updates observations, never duplicates or loses them
"""
import numpy as np
import pandas as pd

from vzones.assistant import eyes, eyes_live, journal


def frame(days=300, seed=0, plant=False):
    rng = np.random.default_rng(seed)
    sess = pd.bdate_range("2025-01-02", periods=days)
    rows, whale = [], {}
    p = 100.0
    datr = 1.5
    for d in sess:
        side = rng.choice([-1, 1])
        L = p + side * rng.uniform(0.5, 1.5) * datr
        whale[d.date()] = [L]
        touched = False
        for k in range(78):
            step = rng.normal(0, 0.12)
            if plant and not touched:
                step += 0.02 * np.sign(L - p)
            o = p
            p = p + step
            h, l = max(o, p) + abs(rng.normal(0, 0.03)), min(o, p) - abs(rng.normal(0, 0.03))
            touched = touched or (l <= L <= h)
            rows.append((pd.Timestamp(d).tz_localize("America/New_York") + pd.Timedelta(minutes=570 + 5 * k), o, h, l, p, k * 5))
    d = pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "minute"]).set_index("time")
    d["session"] = [t.date() for t in d.index]
    d["slot"] = d["minute"] // 30
    d["atr"], d["datr"] = 0.15, datr
    eyes.add_paths(d)
    return d, whale


def magnet_excess(plant, seed):
    d, whale = frame(seed=seed, plant=plant)
    ev = pd.DataFrame(eyes.magnet_events("SYN", 5, d, [], whale, {}, eyes.Base(d)))
    return eyes.boot_excess(ev, "hit", "base")


def test_planted_magnet_is_found():
    r = magnet_excess(True, 1)
    assert r["lo"] > 0.02, r


def test_random_walk_shows_no_magnet():
    r = magnet_excess(False, 2)
    assert r["lo"] < 0 < r["hi"], r


def synth(days=90, seed=4):
    rng = np.random.default_rng(seed)
    sess = pd.bdate_range("2025-01-02", periods=days)
    idx = [pd.Timestamp(d).tz_localize("America/New_York") + pd.Timedelta(minutes=570 + 5 * k) for d in sess for k in range(78)]
    n = len(idx)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.0012, n)))
    o = np.r_[100, c[:-1]]
    h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, 0.0006, n)))
    l = np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.0006, n)))
    b = pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": rng.integers(1000, 5000, n).astype(float)},
                     index=pd.DatetimeIndex(idx, name="time"))
    closes = b.groupby(b.index.date).close.last()
    prev = closes.shift(1)
    gex = pd.DataFrame({"cw": prev * 1.004, "pw": prev * 0.996, "flip": prev, "pin": prev, "dflip": prev * 1.001,
                        "maxoi": prev, "cwoi": prev * 1.008, "pwoi": prev * 0.992})
    vix = pd.Series(18.0, index=closes.index)
    return b, gex, vix


def build(b, gex, vix, paths=True):
    return eyes.build("SYN", b, use_yahoo=False, gex=gex, vix=vix, use_cache=False, paths=paths)


def test_no_lookahead_history_events():
    b, gex, vix = synth()
    k = len(b) - 78 * 10 + 41
    full, part = build(b, gex, vix), build(b.iloc[:k], gex, vix)
    cut = b.index[k - 1]
    for tf in (5,):
        bf, bp = eyes.Base(full[tf]), eyes.Base(part[tf])
        ef = {(e["variant"], e["time"], e["side"]) for e in eyes.trend_events("SYN", tf, full[tf], bf) if e["time"] < cut - pd.Timedelta(minutes=5)}
        ep = {(e["variant"], e["time"], e["side"]) for e in eyes.trend_events("SYN", tf, part[tf], bp) if e["time"] < cut - pd.Timedelta(minutes=5)}
        assert ef == ep and len(ef) > 50
        lf = {(e["type"], e["time"], e["real"], e["passed"]) for e in eyes.level_events("SYN", tf, full[tf], full["whale"], full["whale_va"])
              if e["time"] < cut - pd.Timedelta(minutes=25)}
        lp = {(e["type"], e["time"], e["real"], e["passed"]) for e in eyes.level_events("SYN", tf, part[tf], part["whale"], part["whale_va"])
              if e["time"] < cut - pd.Timedelta(minutes=25)}
        assert lf == lp and len(lf) > 50


def _final(obs):
    return {o["key"]: o["outcome"] for o in obs if o["status"] == "final" and o["kind"] != "range"}


def test_no_lookahead_live_observations():
    b, gex, vix = synth()
    day = b.index[-1].date()
    k = len(b) - 30                                    # mid-session of the last day
    part = eyes_live.observe_day("SYN", build(b.iloc[:k], gex, vix, paths=False), day, session_over=False)
    full = eyes_live.observe_day("SYN", build(b, gex, vix, paths=False), day, session_over=True)
    fp, ff = _final(part), _final(full)
    assert fp and all(ff.get(key) == v for key, v in fp.items()), [key for key, v in fp.items() if ff.get(key) != v]


def test_restart_no_duplicates(tmp_path):
    b, gex, vix = synth()
    day = b.index[-1].date()
    k = len(b) - 30
    c1 = journal.connect(str(tmp_path / "a.db"))
    eyes_live.upsert(c1, eyes_live.observe_day("SYN", build(b.iloc[:k], gex, vix, paths=False), day, session_over=False), "t1")
    c1.close()
    c1 = journal.connect(str(tmp_path / "a.db"))         # restarted
    full = eyes_live.observe_day("SYN", build(b, gex, vix, paths=False), day, session_over=True)
    eyes_live.upsert(c1, full, "t2")
    eyes_live.upsert(c1, full, "t3")                     # a second cycle on the same bars
    c2 = journal.connect(str(tmp_path / "b.db"))
    eyes_live.upsert(c2, full, "t2")
    q = "select key, outcome, status from eyes_obs order by key"
    a, z = c1.execute(q).fetchall(), c2.execute(q).fetchall()
    keys_part = {r[0] for r in a}
    assert len(a) == len(set(r[0] for r in a))          # no duplicates
    # every final observation of the uninterrupted run is there with the same outcome
    assert {r for r in z if r[2] == "final"} <= set(a)
    assert keys_part
