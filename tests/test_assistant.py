"""Tests for the paper-trading assistant (vzones/assistant). No network, no TradingView: synthetic bars.

- planted signal: a rule with a known positive expectancy is recovered and promoted; its siblings are not
- pure noise: nothing is promoted
- no lookahead: signals and closed trades on a prefix of the data equal those on the full data
- restart: stopping mid-trade and resuming from the journal gives the same trades as an uninterrupted run
- parity: the stored TradingView parity report keeps every kept signal at >= 95%
"""
import json
import os
import re

import numpy as np
import pandas as pd
import pytest

from vzones.assistant import journal, learn, live, sim

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOGEX = pd.DataFrame(columns=["cw", "pw", "flip", "pin", "dflip"], dtype=float)
NOVIX = pd.Series(dtype=float)


def synth_bars(days=260, seed=1):
    rng = np.random.default_rng(seed)
    sess = pd.bdate_range("2025-01-02", periods=days)
    idx = [pd.Timestamp(d).tz_localize("America/New_York") + pd.Timedelta(minutes=570 + 5 * k) for d in sess for k in range(78)]
    n = len(idx)
    ret = rng.normal(0, 0.0012, n)
    c = 100 * np.exp(np.cumsum(ret))
    o = np.r_[100, c[:-1]] * (1 + rng.normal(0, 0.0002, n))
    h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, 0.0006, n)))
    l = np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.0006, n)))
    v = rng.integers(1000, 5000, n).astype(float)
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": v}, index=pd.DatetimeIndex(idx, name="time"))


# ---------------- planted signal / noise ----------------
def planted_prepared(plant: bool, days=500, seed=7):
    rng = np.random.default_rng(seed)
    n = days * 78
    minute = np.tile(np.arange(78) * 5, days)
    sig = np.zeros(n, int)
    pos = rng.choice(np.arange(n - 20), size=days * 4, replace=False)
    sig[pos] = rng.choice([-1, 1], size=len(pos))
    inc = rng.normal(0, 0.08, n)
    if plant:                                      # first hour: the price drifts the signal's way for 8 bars
        for i in np.flatnonzero((sig != 0) & (minute < 60)):
            inc[i + 2:i + 10] += sig[i] * 0.08
    c = 100 + np.cumsum(inc)
    o = np.r_[100, c[:-1]]
    h = np.maximum(o, c) + 0.02
    l = np.minimum(o, c) - 0.02
    sess = pd.bdate_range("2025-01-02", periods=days)
    idx = pd.DatetimeIndex([pd.Timestamp(d).tz_localize("America/New_York") + pd.Timedelta(minutes=570 + 5 * k)
                            for d in sess for k in range(78)])
    d = pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": 1000.0, "atr": 0.15,
                      "session": [t.date() for t in idx], "minute": minute}, index=idx)
    for k in sim.SIGNALS:
        d[f"sig_{k}"] = 0
    d["sig_st"] = sig
    for k in ("wb_tgt", "ema20", "ema50", "pd_vah", "pd_val", "rvol", "datr", "vix", "gap_atr", "cw", "pw", "flip"):
        d[k] = np.nan
    return sim.Prepared("SYN", 5, d)


def learn_on(p, tmp_path, monkeypatch):
    monkeypatch.setattr(learn, "STATE", str(tmp_path / "learn_state.json"))
    c = journal.connect(str(tmp_path / "paper.db"))
    tr, lg = sim.simulate(p)
    days = sorted({t["signal_time"][:10] for t in tr})
    cut_live, split = days[int(len(days) * 0.7)], days[int(len(days) * 0.4)]
    rep = [t for t in tr if t["signal_time"][:10] < cut_live]
    liv = [t for t in tr if t["signal_time"][:10] >= cut_live]
    journal.upsert(c, rep, [], mode="replay")
    for t in liv:                                  # seen at the bar after the signal = live
        seen = (pd.Timestamp(t["signal_time"]) + pd.Timedelta(minutes=5)).isoformat()
        journal.upsert(c, [t], [], mode="live", seen=seen)
    json.dump({"frozen_at": cut_live, "split": split}, open(learn.STATE, "w"))
    ev, _ = learn.run(c)
    return ev.set_index("rule")


def test_planted_rule_is_recovered(tmp_path, monkeypatch):
    ev = learn_on(planted_prepared(True), tmp_path, monkeypatch)
    assert ev.loc["time=open", "verdict"] == "promoted", ev.loc["time=open"].to_dict()
    assert ev.loc["time=open", "held_mean"] > 0.5
    for other in ("time=mid", "time=late"):
        assert ev.loc[other, "verdict"] not in ("promoted", "candidate")


def test_noise_promotes_nothing(tmp_path, monkeypatch):
    ev = learn_on(planted_prepared(False), tmp_path, monkeypatch)
    assert not (ev.verdict == "promoted").any()
    assert not (ev.verdict == "candidate").any()


# ---------------- no lookahead ----------------
def test_no_lookahead():
    b = synth_bars()
    k = len(b) - 78 * 40 + 37                       # mid-session, 40 days before the end
    full = sim.prepare("SYN", b, gex=NOGEX, vix=NOVIX, use_yahoo=False)
    part = sim.prepare("SYN", b.iloc[:k], gex=NOGEX, vix=NOVIX, use_yahoo=False)
    for tf in (5, 15):
        f, p = full[tf].d, part[tf].d
        m = len(p) - 1                              # the prefix's own last 15m bar may be incomplete
        for col in ["sig_tl", "sig_st", "sig_ta", "sig_wb", "wb_tgt", "pd_vah", "atr"]:
            a, z = f[col].to_numpy()[:m], p[col].to_numpy()[:m]
            assert np.allclose(np.nan_to_num(a, nan=-9), np.nan_to_num(z, nan=-9)), (tf, col)
        assert (f.sig_tl != 0).sum() > 20 and (f.sig_wb != 0).sum() > 0
        cut = b.index[k - 1].isoformat()
        tf_full = {t["key"]: t for t in sim.simulate(full[tf])[0] if t["status"] == "closed" and t["exit_time"] < cut}
        tf_part = {t["key"]: t for t in sim.simulate(part[tf])[0] if t["status"] == "closed" and t["exit_time"] < cut}
        assert tf_full.keys() == tf_part.keys() and len(tf_full) > 50
        for key in tf_full:
            assert tf_full[key]["r"] == tf_part[key]["r"] and tf_full[key]["exit"] == tf_part[key]["exit"]


# ---------------- restart ----------------
def test_restart_mid_trade(tmp_path):
    b = synth_bars(days=120, seed=3)
    k = len(b) - 78 * 3 + 30
    opts = dict(gex=NOGEX, vix=NOVIX, use_cache=False, use_yahoo=False, since_days=0)
    c1 = journal.connect(str(tmp_path / "a.db"))
    live.process_symbol(c1, "SYN", b.iloc[:k], mode="live", seen="2026-01-01T00:00:00+00:00", **opts)
    open_keys = [k_ for (k_,) in c1.execute("select key from trades where status='open'")]
    assert open_keys, "the cut should leave a trade open"
    c1.close()
    c1 = journal.connect(str(tmp_path / "a.db"))          # "killed and restarted": a new connection, same journal
    live.process_symbol(c1, "SYN", b, mode="live", seen="2026-01-02T00:00:00+00:00", **opts)
    c2 = journal.connect(str(tmp_path / "b.db"))
    live.process_symbol(c2, "SYN", b, mode="live", seen="2026-01-02T00:00:00+00:00", **opts)
    q = "select key, status, entry, exit, reason, r from trades order by key"
    assert c1.execute(q).fetchall() == c2.execute(q).fetchall()
    for k_ in open_keys:
        assert c1.execute("select status from trades where key=?", (k_,)).fetchone()[0] == "closed"
    assert c1.execute("select count(*) from events where kind='anomaly'").fetchone()[0] == 0


# ---------------- parity ----------------
def test_parity_report():
    p = os.path.join(ROOT, "reports", "paper", "parity.txt")
    if not os.path.exists(p):
        pytest.skip("run tools/paper_parity.py with TradingView open")
    last = open(p, encoding="utf-8").read().strip().splitlines()[-1]
    got = {k: float(v) for k, v in re.findall(r"(\w+) \d+/\d+ = ([\d.]+)%", last)}
    for k in ("tl", "st", "ta", "wb"):
        assert got.get(k, 0) >= 95.0, (k, got)
