"""Measured learning: which signal, in which context, has a real expectancy. Not a black box.

A rule = (signal, timeframe) alone, or limited to ONE context bucket (e.g. "tl 15m, trend=with").
Three batteries, by signal date:
  tuning   the first 60% of the replayed history
  held     the last 40% of the replayed history (never used to pick anything)
  live     paper trades the live agent saw as they happened, after the rules were frozen (runtime/learn_state.json)
Per battery: trades, win rate, mean R, t-stat, total R, max drawdown (R), 95% bootstrap interval of the mean.
The tuning mean is also shrunk toward the signal's overall mean (k = 30 trades), so a small bucket cannot look great.

Verdicts (a minimum of 30 trades in every battery a verdict reads):
  promoted   positive on all three batteries, t >= 2 on held and live      -> "worth watching"
  candidate  positive on tuning and held, t >= 2 on held; waiting for 30 live trades
  dead       negative on both tuning and held                             -> graveyard
  demoted    was promoted, the last 30 live trades average below zero
  watching   anything else (too few trades or mixed)
With hundreds of rules, about 2-3% clear t >= 2 on held by luck alone: that is why "candidate" is not "promoted".
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

from .data import RUNTIME
from .journal import event, now_iso

FEATURES = ["side", "time", "trend", "va", "rvol", "gex_wall", "gex_flip", "vix", "gap"]
STATE = os.path.join(RUNTIME, "learn_state.json")
MIN_N, T_MIN, SHRINK_K, TUNE_FRAC = 30, 2.0, 30, 0.60


def load(c) -> pd.DataFrame:
    t = pd.read_sql_query("select * from trades where status='closed'", c)
    if t.empty:
        return t
    ctx = pd.DataFrame([json.loads(x) for x in t.context]).add_prefix("c_")
    t = pd.concat([t.reset_index(drop=True), ctx], axis=1)
    t["date"] = pd.to_datetime(t.signal_time.str[:10]).dt.date
    return t


def state() -> dict:
    return json.load(open(STATE, encoding="utf-8")) if os.path.exists(STATE) else {}


def batteries(t: pd.DataFrame, st: dict) -> pd.Series:
    rep = t[t.source != "live"]
    days = sorted(rep.date.unique())
    split = st.get("split") or (str(days[int(len(days) * TUNE_FRAC)]) if days else None)
    freeze = st.get("frozen_at")
    b = pd.Series("held", index=t.index)
    if split:
        b[t.date.astype(str) < split] = "tuning"
    live = (t.source == "live")
    if freeze:
        live &= t.signal_time > freeze
    b[t.source == "live"] = "live_before_freeze"
    b[live] = "live"
    return b


def stats(r: np.ndarray, boot: bool = False, seed: int = 0) -> dict:
    n = len(r)
    if n == 0:
        return dict(n=0)
    m, sd = float(r.mean()), float(r.std(ddof=1)) if n > 1 else 0.0
    eq = np.cumsum(r)
    out = dict(n=n, win=round(float((r > 0).mean()), 3), mean=round(m, 4), t=round(m / (sd / np.sqrt(n)), 2) if sd > 0 else 0.0,
               total=round(float(r.sum()), 1), max_dd=round(float((eq - np.maximum.accumulate(np.r_[0, eq])[1:]).min()), 1))
    if boot and n >= 10:
        rng = np.random.default_rng(seed)
        ms = r[rng.integers(0, n, (2000, n))].mean(axis=1)
        out["ci"] = [round(float(np.percentile(ms, 2.5)), 4), round(float(np.percentile(ms, 97.5)), 4)]
    return out


def evaluate(t: pd.DataFrame, bat: pd.Series) -> pd.DataFrame:
    rows = []
    t = t.sort_values("signal_time")
    bat = bat.loc[t.index]
    for (sig, tf), g in t.groupby(["signal", "tf"]):
        gb = bat.loc[g.index]
        grand = g.r[gb == "tuning"].mean()
        rules = [("all", g.index)]
        for f in FEATURES:
            col = f"c_{f}"
            if col not in g:
                continue
            for v, gg in g.groupby(col):
                if v != "none":
                    rules.append((f"{f}={v}", gg.index))
        for name, ix in rules:
            row = dict(signal=sig, tf=int(tf), rule=name)
            for b in ("tuning", "held", "live"):
                r = t.loc[ix].r[bat.loc[ix] == b].to_numpy(float)
                s = stats(r, boot=b != "tuning")
                for k, v in s.items():
                    row[f"{b}_{k}"] = v
            n, m = row.get("tuning_n", 0), row.get("tuning_mean", np.nan)
            row["tuning_shrunk"] = round((n * m + SHRINK_K * grand) / (n + SHRINK_K), 4) if n else np.nan
            rl = t.loc[ix].r[bat.loc[ix] == "live"].to_numpy(float)
            row["live_last30"] = round(float(rl[-30:].mean()), 4) if len(rl) >= 30 else np.nan
            rows.append(row)
    return pd.DataFrame(rows)


def verdict(row, prev: str | None) -> str:
    g = lambda k, d=0: row.get(k, d) if pd.notna(row.get(k, d)) else d  # noqa: E731
    nt, nh, nl = g("tuning_n"), g("held_n"), g("live_n")
    mt, mh, ml = g("tuning_mean"), g("held_mean"), g("live_mean")
    if prev == "promoted" and pd.notna(row.get("live_last30")) and row["live_last30"] < 0:
        return "demoted"
    if nt >= MIN_N and nh >= MIN_N and mt < 0 and mh < 0:
        return "dead"
    if nt >= MIN_N and nh >= MIN_N and mt > 0 and mh > 0 and g("held_t") >= T_MIN:
        if nl >= MIN_N and ml > 0 and g("live_t") >= T_MIN:
            return "promoted"
        return "candidate"
    return "watching"


def run(c, freeze: bool = False) -> tuple[pd.DataFrame, dict]:
    """Evaluate every rule, record verdict changes. `freeze=True` (first run) stores the split date and the freeze time:
    from then on only trades after the freeze count as the live battery."""
    st = state()
    t = load(c)
    if t.empty:
        return pd.DataFrame(), st
    if freeze and not st.get("frozen_at"):
        rep_days = sorted(t[t.source != "live"].date.unique())
        st = {"frozen_at": now_iso(), "split": str(rep_days[int(len(rep_days) * TUNE_FRAC)]),
              "history": [str(rep_days[0]), str(rep_days[-1])], "rules_note": "exit rules and buckets fixed in vzones/assistant/sim.py"}
        os.makedirs(RUNTIME, exist_ok=True)
        json.dump(st, open(STATE, "w", encoding="utf-8"), indent=1)
        event(c, "freeze", st)
    bat = batteries(t, st)
    ev = evaluate(t, bat)
    prev = {r: v for r, v in c.execute(
        "select rule, verdict from verdicts v where ts = (select max(ts) from verdicts w where w.rule = v.rule)")}
    out = []
    ts = now_iso()
    for _, row in ev.iterrows():
        key = f"{row.signal}|{row.tf}|{row.rule}"
        v = verdict(row, prev.get(key))
        out.append(v)
        if prev.get(key) != v:
            detail = {k: row[k] for k in ("tuning_n", "tuning_mean", "held_n", "held_mean", "held_t", "live_n", "live_mean", "live_t") if k in row}
            c.execute("insert into verdicts values (?,?,?,?)", (ts, key, v, json.dumps(detail, default=float)))
            if prev.get(key) is not None:
                event(c, "verdict", {"rule": key, "from": prev.get(key), "to": v, **detail})
    ev["verdict"] = out
    c.commit()
    st["n_rules"] = len(ev)
    st["counts"] = {str(k): int(v) for k, v in ev.verdict.value_counts().items()}
    st["batteries"] = {str(k): int(v) for k, v in bat.value_counts().items()}
    return ev, st
