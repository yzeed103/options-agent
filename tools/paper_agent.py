"""Paper-trading assistant, live shadow mode. Paper only: no broker order endpoint is ever called.

Every 5-minute bar close during regular hours (+75 s for the data feed): new bars for the watchlist (Alpaca IEX, keys
read in-process from GEXRadar's config, never printed) -> the indicator's signals in Python -> paper trades opened and
closed in runtime/paper.db -> the page runtime/paper_view.html. After 16:10 New York, once a day: the learning pass,
the daily Arabic report (reports/paper/YYYY-MM-DD.md), the graveyard and the history verdict.
A health line goes to runtime/paper_agent.log every cycle. Single instance (localhost port 47232).

    pythonw tools/paper_agent.py        # run forever (the PaperAgent logon task)
    python  tools/paper_agent.py --once # one cycle now, prints what it did
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import socket
import sys
import time
from datetime import datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from vzones.assistant import data, eyes, eyes_live, journal, learn, live, report  # noqa: E402

NY = ZoneInfo("America/New_York")
LOCK_PORT = 47232
STATE = os.path.join(data.RUNTIME, "paper_agent_state.json")
log = logging.getLogger("paper_agent")


def setup_log(console: bool):
    os.makedirs(data.RUNTIME, exist_ok=True)
    h = RotatingFileHandler(os.path.join(data.RUNTIME, "paper_agent.log"), maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(h)
    if console:
        log.addHandler(logging.StreamHandler(sys.stdout))
    log.setLevel(logging.INFO)


def lock():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", LOCK_PORT))
    except OSError:
        return None
    s.listen(1)
    return s


def load_state() -> dict:
    try:
        return json.load(open(STATE, encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def save_state(st: dict) -> None:
    json.dump(st, open(STATE + ".tmp", "w", encoding="utf-8"), indent=1)
    os.replace(STATE + ".tmp", STATE)


def cycle(c) -> dict:
    t0 = time.time()
    now = datetime.now(timezone.utc)
    seen = now.isoformat(timespec="seconds")
    syms = data.watchlist()
    h = {"time": datetime.now(NY).strftime("%H:%M"), "symbols": len(syms), "ok": 0, "new_trades": 0, "closed": 0,
         "anomalies": 0, "errors": []}
    try:
        added = data.update_bars(syms, now)
        h["bars_added"] = sum(added.values())
    except Exception as e:  # noqa: BLE001 - data feed down: keep the cached bars, try again next cycle
        h["errors"].append(f"bars: {type(e).__name__}")
    h["eyes"] = 0
    eyes_live.connect_schema(c)
    for s in syms:
        try:
            b = data.load_bars(s)
            if len(b) < 2000:
                continue
            for cnt in live.process_symbol(c, s, b, mode="live", seen=seen).values():
                for k in ("new_trades", "closed", "anomalies"):
                    h[k] += cnt[k]
            h["ok"] += 1
        except Exception as e:  # noqa: BLE001 - one symbol must not stop the others
            h["errors"].append(f"{s}: {type(e).__name__}: {str(e)[:80]}")
            continue
        try:                                   # the eyes: observations only, no trades
            fr = eyes.build(s, b, tfs=(5,), paths=False)
            h["eyes"] += eyes_live.upsert(c, eyes_live.observe_day(s, fr), seen)
        except Exception as e:  # noqa: BLE001
            h["errors"].append(f"eyes {s}: {type(e).__name__}: {str(e)[:80]}")
    try:
        last = c.execute("select max(date) from eyes_obs").fetchone()[0]
        if last:
            eyes_live.group_sync(c, last, seen)
            eyes_live.view(c, last)
    except Exception as e:  # noqa: BLE001
        h["errors"].append(f"eyes view: {type(e).__name__}")
    h["open"] = c.execute("select count(*) from trades where status='open'").fetchone()[0]
    h["seconds"] = round(time.time() - t0, 1)
    try:
        report.view(c, {k: h[k] for k in ("time", "ok", "open", "seconds")})
    except Exception as e:  # noqa: BLE001
        h["errors"].append(f"view: {type(e).__name__}")
    return h


def end_of_day(c, st: dict) -> None:
    ev, lst = learn.run(c)
    if not ev.empty:
        report.history_report(c, ev, lst)
        report.graveyard(ev)
    report.daily_report(c)
    last = c.execute("select max(date) from eyes_obs").fetchone()[0]
    if last:
        eyes_live.daily_report(c, last)
        eyes_live.update_observations(c)
    st["last_eod"] = datetime.now(NY).date().isoformat()
    save_state(st)
    log.info("end of day: verdicts %s", lst.get("counts"))


def next_wake(now: datetime) -> datetime:
    """Next 5-minute bar close + 75 s during regular hours; otherwise the next session's first close."""
    ny = now.astimezone(NY)
    m = ny.hour * 60 + ny.minute
    if ny.weekday() < 5 and 570 <= m < 960 + 2:
        nxt = ny.replace(second=0, microsecond=0) + timedelta(minutes=5 - ny.minute % 5)
        return (nxt + timedelta(seconds=75)).astimezone(timezone.utc)
    d = ny.date() + timedelta(days=0 if m < 570 and ny.weekday() < 5 else 1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return datetime(d.year, d.month, d.day, 9, 36, 15, tzinfo=NY).astimezone(timezone.utc)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--eod", action="store_true", help="with --once: also run the end-of-day pass")
    a = ap.parse_args()
    setup_log(console=a.once)
    lk = lock()
    if lk is None:
        log.info("another paper agent is running; exiting")
        return
    c = journal.connect()
    st = load_state()
    if a.once:
        h = cycle(c)
        log.info("cycle %s", json.dumps(h, ensure_ascii=False))
        if a.eod:
            end_of_day(c, st)
        return
    log.info("paper agent started (pid %s)", os.getpid())
    while True:
        try:
            h = cycle(c)
            log.info("cycle %s", json.dumps(h, ensure_ascii=False))
            ny = datetime.now(NY)
            if ny.weekday() < 5 and ny.hour * 60 + ny.minute >= 970 and st.get("last_eod") != ny.date().isoformat():
                end_of_day(c, st)
        except Exception as e:  # noqa: BLE001 - never die; the next cycle retries
            log.exception("cycle failed: %s", e)
            try:
                c.close()
            except Exception:  # noqa: BLE001
                pass
            c = journal.connect()
        now = datetime.now(timezone.utc)
        wake = next_wake(now)
        ny = now.astimezone(NY)
        eod = datetime(ny.year, ny.month, ny.day, 16, 10, 30, tzinfo=NY).astimezone(timezone.utc)
        if ny.weekday() < 5 and st.get("last_eod") != ny.date().isoformat() and now < eod < wake:
            wake = eod          # the end-of-day pass runs once even though no new bar comes after the close
        time.sleep(max(5.0, (wake - datetime.now(timezone.utc)).total_seconds()))


if __name__ == "__main__":
    main()
