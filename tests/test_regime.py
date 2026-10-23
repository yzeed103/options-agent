"""Tests of the regime engine (vzones/assistant/regime.py), pre-registered in reports/invention/PREREG.md.

- planted: when log range depends on a planted positioning variable, P beats B3 with an interval above zero
- noise: when it does not, the interval contains zero
- no lookahead: features at an update time do not change when later bars are removed
- restart: the live record is keyed; re-running a cycle never duplicates rows
"""
import numpy as np
import pandas as pd

from vzones.assistant import journal, regime as R


def table(plant: bool, days=600, syms=8, seed=3):
    rng = np.random.default_rng(seed)
    rows = []
    dates = pd.bdate_range("2025-01-02", periods=days).date
    for d in dates:
        lvix = np.log(rng.uniform(12, 30))
        for s in range(syms):
            side = rng.choice([-1.0, 1.0])
            lmorn = np.log(rng.uniform(0.1, 0.6))
            t = -0.5 + 0.3 * lmorn + 0.2 * (lvix - 3) + (0.25 * side if plant else 0) + rng.normal(0, 0.3)
            rows.append(dict(sym=f"S{s}", date=d, time="10:00", y=np.exp(t), lvix=lvix, latr=np.log(0.02), lmorn=lmorn,
                             gap=abs(rng.normal(0, 0.2)), g_index=0.0, g_mega=0.0, side=side, dflip=rng.uniform(0, 2),
                             dwall=rng.uniform(0, 2), regime=float(rng.random() > 0.5), gexn=rng.normal()))
    df = pd.DataFrame(rows)
    cut = dates[int(len(dates) * 0.6)]
    tr, te = df[df.date < cut].reset_index(drop=True), df[df.date >= cut].reset_index(drop=True)
    return R.predict(R.fit_all(tr), te)


def test_planted_positioning_is_found():
    r = R.boot_mae_diff(table(True), "f_B3", "f_P")
    assert r["lo"] > 0 and r["rel"] > 0.02, r


def test_noise_gives_no_gain():
    r = R.boot_mae_diff(table(False), "f_B3", "f_P")
    assert r["lo"] < 0 < r["hi"] or r["hi"] <= 0, r


def frame(days=30, seed=5):
    rng = np.random.default_rng(seed)
    sess = pd.bdate_range("2025-03-03", periods=days)
    idx = [pd.Timestamp(d).tz_localize("America/New_York") + pd.Timedelta(minutes=570 + 5 * k) for d in sess for k in range(78)]
    n = len(idx)
    c = 100 + np.cumsum(rng.normal(0, 0.1, n))
    o = np.r_[100, c[:-1]]
    d = pd.DataFrame({"open": o, "high": np.maximum(o, c) + 0.03, "low": np.minimum(o, c) - 0.03, "close": c}, index=pd.DatetimeIndex(idx))
    d["session"] = [t.date() for t in d.index]
    d["minute"] = [(t.hour * 60 + t.minute) - 570 for t in d.index]
    d["datr"], d["vix"] = 1.2, 18.0
    prev = d.groupby("session").close.last().shift(1)
    d["flip"] = d.session.map(prev).fillna(100.0)
    d["cw"], d["pw"] = d.flip + 1, d.flip - 1
    return d


def test_no_lookahead_features():
    d = frame()
    day = d.session.iat[-1]
    cut = d.index.get_loc(d[(d.session == day) & (d.minute == 150)].index[0])
    full = {r["time"]: r for r in R.rows_for_symbol("SYN", d, live_day=day)}
    part = {r["time"]: r for r in R.rows_for_symbol("SYN", d.iloc[:cut], live_day=day)}
    for t in ("10:00", "11:00", "12:00"):
        for k in ("lmorn", "side", "dflip", "dwall", "close", "gap"):
            assert full[t][k] == part[t][k], (t, k)
    assert np.isfinite(full["10:00"]["y"]) and not np.isfinite(part["10:00"]["y"])   # the target needs the day's end


def test_restart_no_duplicates(tmp_path):
    from vzones.assistant import regime_live
    d = frame()
    models = R.fit_all(R.usable(pd.DataFrame([r for s in range(3) for r in R.rows_for_symbol(f"S{s}", d)]).assign(regime=1.0, gexn=0.0)))
    c = journal.connect(str(tmp_path / "x.db"))
    for _ in range(3):
        regime_live.record(c, "SYN", d, models, "t")
    c.close()
    c = journal.connect(str(tmp_path / "x.db"))
    regime_live.record(c, "SYN", d, models, "t2")
    n, k = c.execute("select count(*), count(distinct key) from regime_obs").fetchone()
    assert n == k and n >= 3
