"""Live record of the regime engine (table regime_obs in runtime/paper.db): at 10:00 / 11:00 / 12:00 the plain (B3)
and positioning (P) forecasts of the rest-of-day range, the pre-registered stop / no-trade mapping, and after the close
the realised range. Keyed by symbol|date|time, so re-running a cycle updates the row instead of adding one."""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

from . import regime as R
from .data import RUNTIME

MODEL = os.path.join(RUNTIME, "regime_model.json")
SCHEMA = """create table if not exists regime_obs (
  key text primary key, sym text, date text, time text, f_b3 real, f_p real, stop real, no_trade int, side int,
  realised real, updated text);"""


def load():
    return R.load_models(MODEL) if os.path.exists(MODEL) else None


def record(c, sym: str, d5: pd.DataFrame, models: dict, now: str) -> int:
    c.executescript(SCHEMA)
    day = d5["session"].iat[-1]
    rows = R.rows_for_symbol(sym, d5, live_day=day)
    if not rows or models is None:
        return 0
    df = pd.DataFrame(rows)
    n = 0
    for _, r in df.iterrows():
        mm = models.get(r.time)
        if mm is None:
            continue
        one = pd.DataFrame([r])
        fb3 = float(mm["B3"].predict(one)[0]) if one[R.B3_COLS].notna().all(axis=1).iat[0] else None
        fp = float(mm["P"].predict(one)[0]) if one[R.P_COLS].notna().all(axis=1).iat[0] else None
        f = fp if fp is not None else fb3
        stop, ok = R.stops_for(max(f, 0.0), r.datr, r.price) if f is not None else (None, False)
        c.execute("insert into regime_obs values (?,?,?,?,?,?,?,?,?,?,?) on conflict(key) do update set "
                  "f_b3=excluded.f_b3, f_p=excluded.f_p, stop=excluded.stop, no_trade=excluded.no_trade, "
                  "realised=excluded.realised, updated=excluded.updated",
                  (f"{sym}|{day}|{r.time}", sym, str(day), r.time, fb3, fp, stop, int(not ok), int(r.side),
                   None if not np.isfinite(r.y) else float(r.y), now))
        n += 1
    c.commit()
    return n


def summary(c) -> dict:
    """Live MAE of B3 and P on completed rows (the pre-registered comparison, now on days after the freeze)."""
    c.executescript(SCHEMA)
    from .eyes_live import live_start                       # days filled in after the fact are not live evidence
    d = pd.read_sql_query("select * from regime_obs where realised is not null and f_b3 is not null and f_p is not null "
                          "and date >= ?", c, params=(live_start(),))
    if d.empty:
        return {"n": 0}
    out = {"n": len(d)}
    for t, g in d.groupby("time"):
        out[t] = dict(n=len(g), mae_b3=float((g.f_b3 - g.realised).abs().mean()), mae_p=float((g.f_p - g.realised).abs().mean()))
    return out
