"""SQLite journal (runtime/paper.db, WAL). Every signal is logged, taken or skipped, with the reason and the context.

A trade row is keyed by symbol|timeframe|signal|signal time. The replay and the live agent write through the same
upsert: a new row records when it was first seen and whether it was seen live (within two bars of the signal) or filled
in from history. An already CLOSED trade whose numbers change on a later run is an anomaly (it would mean lookahead or a
data revision) and is logged in `events`, never silently overwritten.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone

from .data import RUNTIME

DB = os.path.join(RUNTIME, "paper.db")
SCHEMA = """
create table if not exists trades (
  key text primary key, sym text, tf int, signal text, side int, signal_time text, entry_time text, entry real,
  stop real, target real, risk real, cost_r real, status text, exit_time text, exit real, reason text, bars int,
  r real, pct real, context text, first_seen text, source text, updated text);
create table if not exists signals (
  key text primary key, sym text, tf int, signal text, side int, signal_time text, taken int, reason text,
  context text, first_seen text, source text);
create table if not exists events (ts text, kind text, detail text);
create table if not exists verdicts (ts text, rule text, verdict text, detail text);
create index if not exists ix_trades_sig on trades(signal, tf);
create index if not exists ix_trades_time on trades(signal_time);
"""
FIELDS = ["sym", "tf", "signal", "side", "signal_time", "entry_time", "entry", "stop", "target", "risk", "cost_r",
          "status", "exit_time", "exit", "reason", "bars", "r", "pct", "context"]
FIXED = ["entry_time", "entry", "stop", "target", "exit_time", "exit", "reason", "r"]


def connect(path: str = DB) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    c = sqlite3.connect(path, timeout=30)
    c.execute("pragma journal_mode=wal")
    c.executescript(SCHEMA)
    return c


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def event(c, kind: str, detail) -> None:
    c.execute("insert into events values (?,?,?)", (now_iso(), kind, detail if isinstance(detail, str) else json.dumps(detail)))


def _source(signal_time: str, seen: str, tf: int, mode: str) -> str:
    if mode == "replay":
        return "replay"
    lag = (datetime.fromisoformat(seen) - datetime.fromisoformat(signal_time)).total_seconds() / 60
    return "live" if lag <= tf * 3 + 10 else "backfill"   # signal bar close + agent cycle


def upsert(c, trades: list[dict], log: list[dict], mode: str = "replay", seen: str | None = None) -> dict:
    """mode 'replay' (history) or 'live'. Returns counts."""
    seen = seen or now_iso()
    cnt = {"new_trades": 0, "closed": 0, "anomalies": 0, "new_signals": 0}
    cur = {k: (st, dict(zip(FIXED, vals))) for k, st, *vals in
           c.execute(f"select key, status, {', '.join(FIXED)} from trades where key in ({','.join('?' * len(trades))})",
                     [t['key'] for t in trades])} if trades else {}
    for t in trades:
        k = t["key"]
        if k not in cur:
            c.execute(f"insert into trades (key, {', '.join(FIELDS)}, first_seen, source, updated) values (?{', ?' * (len(FIELDS) + 3)})",
                      [k] + [t.get(f) for f in FIELDS] + [seen, _source(t["signal_time"], seen, t["tf"], mode), seen])
            cnt["new_trades"] += 1
            continue
        st, old = cur[k]
        if st == "closed":
            diff = {f: (old[f], t.get(f)) for f in FIXED if old[f] != t.get(f) and not (isinstance(old[f], float) and t.get(f) is not None and abs(old[f] - t[f]) < 1e-6)}
            if diff:
                event(c, "anomaly", {"key": k, "diff": diff}); cnt["anomalies"] += 1
            continue
        c.execute(f"update trades set {', '.join(f + '=?' for f in FIELDS)}, updated=? where key=?",
                  [t.get(f) for f in FIELDS] + [seen, k])
        if t["status"] == "closed":
            cnt["closed"] += 1
    have = {k for (k,) in c.execute(f"select key from signals where key in ({','.join('?' * len(log))})", [x['key'] for x in log])} if log else set()
    for x in log:
        if x["key"] in have:
            c.execute("update signals set taken=?, reason=? where key=?", (x["taken"], x["reason"], x["key"]))
        else:
            c.execute("insert into signals values (?,?,?,?,?,?,?,?,?,?,?)",
                      (x["key"], x["sym"], x["tf"], x["signal"], x["side"], x["signal_time"], x["taken"], x["reason"],
                       x["context"], seen, _source(x["signal_time"], seen, x["tf"], mode)))
            cnt["new_signals"] += 1
    c.commit()
    return cnt
