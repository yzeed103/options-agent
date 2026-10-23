"""One processing step for one symbol, shared by the replay and the live agent: prepare -> simulate -> journal upsert.

Caches (runtime/cache/whale_<SYM>.pkl): the whale peaks of completed ranges (they never change once a range is done)
and the per-day whale levels, keyed by the last session date (levels for a day use completed days only, so they only
change when a new session starts).
"""
from __future__ import annotations

import hashlib
import os
import pickle
from datetime import timedelta

import pandas as pd

from . import journal, sim
from . import signals as S
from .data import RUNTIME, resample15

CACHE = os.path.join(RUNTIME, "cache")
LIVE_DAYS = 10        # live cycles re-journal only the last 10 days (+ open trades); history was checked by the replay


def _load_cache(sym: str) -> dict:
    p = os.path.join(CACHE, f"whale_{sym}.pkl")
    try:
        return pickle.load(open(p, "rb")) if os.path.exists(p) else {}
    except Exception:  # noqa: BLE001 - a broken cache is just rebuilt
        return {}


def _save_cache(sym: str, cache: dict) -> None:
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, f"whale_{sym}.pkl")
    pickle.dump(cache, open(p + ".tmp", "wb"))
    os.replace(p + ".tmp", p)


def whale_days_cached(sym: str, bars5: pd.DataFrame, use_cache: bool = True, use_yahoo: bool = True) -> dict:
    cache = _load_cache(sym) if use_cache else {}
    days = sim.official_days(sym, sim.day_table(bars5), use_yahoo)
    # fingerprint of the completed days' values: a revised or newly official daily bar invalidates the cache
    done = days.iloc[:-1].round(4)
    key = (str(days.index[0]), str(days.index[-1]), len(days), hashlib.sha1(done.to_numpy().tobytes()).hexdigest())
    hit = cache.get("__days__")
    if hit and hit[0] == key:
        return hit[1]
    peaks = {k: v for k, v in cache.items() if k != "__days__"}
    wd = S.whale_levels_by_day(days, resample15(bars5), peaks)
    if use_cache:
        peaks["__days__"] = (key, wd)
        _save_cache(sym, peaks)
    return wd


def process_symbol(c, sym: str, bars5, mode: str = "live", seen: str | None = None, tfs=(5, 15),
                   gex=None, vix=None, use_cache: bool = True, since_days: int | None = None, use_yahoo: bool = True) -> dict:
    wd = whale_days_cached(sym, bars5, use_cache, use_yahoo)
    prepared = sim.prepare(sym, bars5, tfs=tfs, whale_days=wd, gex=gex, vix=vix, use_yahoo=use_yahoo)
    if since_days is None:
        since_days = LIVE_DAYS if mode == "live" else 0
    cut = (bars5.index[-1] - timedelta(days=since_days)).isoformat() if since_days else ""
    out = {}
    for tf, p in prepared.items():
        tr, lg = sim.simulate(p)
        if cut:
            tr = [t for t in tr if t["signal_time"] >= cut or t["status"] == "open"]
            lg = [x for x in lg if x["signal_time"] >= cut]
        out[tf] = journal.upsert(c, tr, lg, mode=mode, seen=seen)
    return out
