"""GEX agent: keeps the Volume Zones indicator's options levels up to date in TradingView Desktop, by itself.

Every few minutes it pulls a fresh block from the local GEXRadar and decides what is worth pushing
(vzones/gex_watch.py): the gamma levels (CW PW FLIP PIN DFLIP) once a day at 09:35 ET, the open-interest levels
(MAXOI CWOI PWOI) whenever a change is confirmed on 2 polls. It writes the block straight into the indicator's text
input on every open chart tab, through TradingView Desktop's local debug port (127.0.0.1 only). No mouse, no keyboard,
no window focus. Each push is shown as a Windows notification and logged.

    pythonw tools/gex_agent.py                 # run forever (the GEXAgent logon task does this)
    python  tools/gex_agent.py --once          # one poll + push, prints what it did

TradingView must be started with the debug port: tools/start_tradingview.ps1 (the TradingViewGEX logon task and the
"TradingView GEX" desktop shortcut both run it).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import urllib.request
from datetime import datetime
from logging.handlers import RotatingFileHandler
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
from vzones.gex_watch import Watch  # noqa: E402
import gex_block  # noqa: E402  (build, notify, send_telegram)

NY = ZoneInfo("America/New_York")
LOG_DIR = os.path.join(os.environ.get("LOCALAPPDATA", HERE), "gex_agent")
RETRY = 60          # seconds to the next poll after a failure (boot: GEXRadar / TradingView still starting)
WARN_AFTER = 3      # consecutive failed polls before a notification (so a normal boot stays quiet)
LOCK_PORT = 47231   # single-instance lock (a localhost socket, released automatically when the process ends)
STATE = os.path.join(LOG_DIR, "state.json")
log = logging.getLogger("gex_agent")

# Runs inside each chart page. Finds every Volume Zones study on every chart of the tab and its GEXRadar text input
# (by input type + title, so it survives input reordering), and sets the block only where it differs.
JS_APPLY = """
((block) => {
  const a = window.TradingViewApi;
  if (!a) return {api: false};
  const out = {api: true, studies: 0, set: 0, same: 0};
  const n = a.chartsCount ? a.chartsCount() : 1;
  for (let i = 0; i < n; i++) {
    const ch = a.chartsCount ? a.chart(i) : a.activeChart();
    for (const s of ch.getAllStudies()) {
      if (!/Volume Zones/i.test(s.name)) continue;
      const st = ch.getStudyById(s.id);
      const info = (st.getInputsInfo ? st.getInputsInfo() : []).find(x => x.type === 'text_area' && /GEXRadar/.test(x.name));
      if (!info) continue;
      out.studies++;
      const cur = st.getInputValues().find(x => x.id === info.id);
      if (cur && cur.value === block) { out.same++; continue; }
      st.setInputValues([{id: info.id, value: block}]);
      out.set++;
    }
  }
  return out;
})(%s)
"""


def cdp_pages(port: int) -> list[dict]:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=5) as r:
        return [t for t in json.loads(r.read()) if t.get("type") == "page" and "/chart/" in t.get("url", "")]


def push(block: str, port: int) -> dict:
    """Write the block into every chart tab. A tab that errors (closing, still loading) is skipped, not fatal."""
    import websocket
    tot = {"tabs": 0, "studies": 0, "set": 0, "same": 0, "errors": 0}
    for t in cdp_pages(port):
        try:
            ws = websocket.create_connection(t["webSocketDebuggerUrl"], timeout=15, suppress_origin=True)
            try:
                ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                                    "params": {"expression": JS_APPLY % json.dumps(block), "returnByValue": True}}))
                r = json.loads(ws.recv())
            finally:
                ws.close()
        except Exception:  # noqa: BLE001
            tot["errors"] += 1
            continue
        v = r.get("result", {}).get("result", {}).get("value") or {}
        if r.get("result", {}).get("exceptionDetails"):
            tot["errors"] += 1
        if v.get("api"):
            tot["tabs"] += 1
            for k in ("studies", "set", "same"):
                tot[k] += v.get(k, 0)
    return tot


def in_session(now: datetime) -> bool:
    t = now.astimezone(NY)
    return t.weekday() < 5 and 4 * 60 <= t.hour * 60 + t.minute <= 20 * 60


def say(what: list[str]) -> str:
    """Changes in Arabic for the notification."""
    out = []
    for x in what:
        if x == "first block":
            out.append("أول تحميل للمستويات")
        elif x.startswith("new session"):
            out.append("مستويات جلسة جديدة " + x.split()[-1])
        elif x.startswith("opening snapshot"):
            out.append("لقطة الافتتاح لمستويات القاما")
        else:
            out.append(x)
    return "؛ ".join(out[:3]) + (f" … و{len(out) - 3} أخرى" if len(out) > 3 else "")


def strike(state: dict, key: str, title: str, body: str) -> None:
    """Count a failure; notify once when it has lasted WARN_AFTER polls."""
    state[key] = state.get(key, 0) + 1
    if state[key] == WARN_AFTER:
        gex_block.notify(title, body)


def poll(w: Watch, a, state: dict) -> bool:
    """One poll. Returns True when everything worked."""
    try:
        text, notes = gex_block.build(a.url.rstrip("/"), [], a.basis)
    except Exception as e:  # noqa: BLE001 - GEXRadar down or still loading
        log.warning("GEXRadar not reachable: %s", type(e).__name__)
        strike(state, "gex_down", "وكيل GEX: GEXRadar لا يرد", "المستويات لن تتحدث حتى يعود GEXRadar")
        return False
    state["gex_down"] = 0
    t = datetime.now(NY)
    changed, what = w.update(text, t.hour * 60 + t.minute)
    stale = [n for n in notes if "stale" in n]
    if stale and state.get("stale_warned") != w.date:
        state["stale_warned"] = w.date
        gex_block.notify("وكيل GEX: بيانات العقود قديمة", f"{len(stale)} سهم بفائدة مفتوحة ليست من آخر جلسة")
    try:
        tot = push(w.block(), a.port)
    except Exception as e:  # noqa: BLE001 - TradingView closed or opened without the port
        log.warning("TradingView not reachable on port %s: %s", a.port, type(e).__name__)
        strike(state, "tv_down", "وكيل GEX: TradingView غير متصل",
               "افتح TradingView من اختصار TradingView GEX حتى يحدّث الوكيل المستويات")
        return False
    state["tv_down"] = 0
    log.info("poll: %s | tabs %d, studies %d, set %d, same %d, errors %d%s", "; ".join(what) or "no change",
             tot["tabs"], tot["studies"], tot["set"], tot["same"], tot["errors"],
             (" | " + "; ".join(notes)) if notes else "")
    if tot["studies"] == 0:
        # right after TradingView starts the charts are still loading: only warn if it lasts
        strike(state, "no_study", "وكيل GEX", "لا يوجد مؤشر Volume Zones بخانة الكتلة في الشارتات المفتوحة")
        return False
    state["no_study"] = 0
    if changed and tot["set"]:
        gex_block.notify("وكيل GEX: تحديث المستويات", say(what))
        if a.telegram:
            try:
                gex_block.send_telegram("GEX update\n" + "\n".join(what))
            except SystemExit as e:
                log.warning("telegram: %s", e)
    if a.once:
        print(json.dumps({"changes": what, **tot}, ensure_ascii=True))
    return True


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--url", default="http://127.0.0.1:8000", help="GEXRadar address")
    ap.add_argument("--port", type=int, default=9222, help="TradingView Desktop debug port")
    ap.add_argument("--basis", default="oi", choices=["oi", "volume"])
    ap.add_argument("--every", type=int, default=300, help="seconds between polls in session (04:00-20:00 ET)")
    ap.add_argument("--idle", type=int, default=1800, help="seconds between polls outside the session")
    ap.add_argument("--confirm", type=int, default=2, help="polls an open-interest change must survive")
    ap.add_argument("--live-gamma", action="store_true",
                    help="also update the gamma levels during the day (measured: ~67 pushes a day)")
    ap.add_argument("--telegram", action="store_true", help="also send each update to Telegram")
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args()

    os.makedirs(LOG_DIR, exist_ok=True)
    h = RotatingFileHandler(os.path.join(LOG_DIR, "gex_agent.log"), maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(h)
    log.setLevel(logging.INFO)
    log.info("start (every %ss, confirm %d, live gamma %s)", a.every, a.confirm, a.live_gamma)

    # one agent at a time: two copies would each write their own version of the block over the other's
    import socket
    lock = socket.socket()
    try:
        lock.bind(("127.0.0.1", LOCK_PORT))
    except OSError:
        log.info("another agent is already running - exit")
        if a.once:
            print("another agent is already running (GEXAgent task): stop it first or just read its log")
        return

    w, state = Watch(confirm=a.confirm, live_gamma=a.live_gamma), {}
    try:
        with open(STATE, encoding="utf-8") as f:
            w.load(json.load(f))
        log.info("state loaded: %s, snapshot %s, %d symbols", w.date, w.snapped, len(w.applied))
    except (OSError, ValueError):
        pass
    while True:
        try:
            ok = poll(w, a, state)
        except Exception:  # noqa: BLE001 - never die: log and keep going
            log.exception("poll failed")
            ok = False
            if a.once:
                raise
        try:
            with open(STATE, "w", encoding="utf-8") as f:
                json.dump(w.to_json(), f)
        except OSError:
            log.warning("could not save state")
        if a.once:
            return
        time.sleep(RETRY if not ok else a.every if in_session(datetime.now(NY)) else a.idle)


if __name__ == "__main__":
    main()
