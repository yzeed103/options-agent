"""GEX agent: keeps the Volume Zones indicator's options levels up to date in TradingView Desktop, by itself.

Every few minutes it pulls a fresh block from the local GEXRadar, keeps only real changes (vzones/gex_watch.py:
confirmed on 2 polls, flip jitter ignored) and writes the block straight into the indicator's text input on every
open chart tab, through TradingView Desktop's local debug port (127.0.0.1 only). No mouse, no keyboard, no window
focus: you can keep working while it updates. Each push is shown as a Windows notification and logged.

    pythonw tools/gex_agent.py                 # run forever (the GEXAgent logon task does this)
    python  tools/gex_agent.py --once          # one poll + push, prints what it did

TradingView must be started with the debug port: tools/start_tradingview.ps1 (or the "TradingView GEX" shortcut).
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
    """Write the block into every chart tab. Returns totals."""
    import websocket
    tot = {"tabs": 0, "studies": 0, "set": 0, "same": 0}
    for t in cdp_pages(port):
        ws = websocket.create_connection(t["webSocketDebuggerUrl"], timeout=15, suppress_origin=True)
        try:
            ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                                "params": {"expression": JS_APPLY % json.dumps(block), "returnByValue": True}}))
            v = json.loads(ws.recv()).get("result", {}).get("result", {}).get("value") or {}
        finally:
            ws.close()
        if v.get("api"):
            tot["tabs"] += 1
            for k in ("studies", "set", "same"):
                tot[k] += v.get(k, 0)
    return tot


def in_session(now: datetime) -> bool:
    t = now.astimezone(NY)
    return t.weekday() < 5 and 4 * 60 <= t.hour * 60 + t.minute <= 20 * 60


def poll(w: Watch, a, state: dict) -> None:
    text, notes = gex_block.build(a.url.rstrip("/"), [], a.basis)
    changed, what = w.update(text)
    try:
        tot = push(w.block(), a.port)
    except Exception as e:  # noqa: BLE001 - TradingView closed or started without the port
        log.warning("TradingView not reachable on port %s: %s", a.port, type(e).__name__)
        if not state.get("tv_down"):
            gex_block.notify("وكيل GEX: TradingView غير متصل",
                             "افتح TradingView من اختصار TradingView GEX حتى يحدّث الوكيل المستويات")
        state["tv_down"] = True
        return
    if state.pop("tv_down", None):
        log.info("TradingView reachable again")
    log.info("poll: %s | tabs %d, studies %d, set %d, same %d%s", "; ".join(what) or "no change",
             tot["tabs"], tot["studies"], tot["set"], tot["same"], (" | " + "; ".join(notes)) if notes else "")
    if tot["studies"] == 0 and not state.get("warned_nostudy"):
        gex_block.notify("وكيل GEX", "لا يوجد مؤشر Volume Zones بخانة الكتلة في الشارتات المفتوحة")
        state["warned_nostudy"] = True
    if changed and tot["set"]:
        body = "؛ ".join(what[:3]) + (f" … و{len(what) - 3} أخرى" if len(what) > 3 else "")
        gex_block.notify("وكيل GEX: تحديث المستويات", body)
        if a.telegram:
            try:
                gex_block.send_telegram("GEX update\n" + "\n".join(what))
            except SystemExit as e:
                log.warning("telegram: %s", e)
    if a.once:
        print(json.dumps({"changes": what, **tot}, ensure_ascii=True))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--url", default="http://127.0.0.1:8000", help="GEXRadar address")
    ap.add_argument("--port", type=int, default=9222, help="TradingView Desktop debug port")
    ap.add_argument("--basis", default="oi", choices=["oi", "volume"])
    ap.add_argument("--every", type=int, default=300, help="seconds between polls in session (04:00-20:00 ET)")
    ap.add_argument("--idle", type=int, default=1800, help="seconds between polls outside the session")
    ap.add_argument("--confirm", type=int, default=2, help="polls a change must survive before it is pushed")
    ap.add_argument("--telegram", action="store_true", help="also send each update to Telegram")
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args()

    os.makedirs(LOG_DIR, exist_ok=True)
    h = RotatingFileHandler(os.path.join(LOG_DIR, "gex_agent.log"), maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(h)
    log.setLevel(logging.INFO)
    log.info("start (every %ss, confirm %d)", a.every, a.confirm)

    w, state = Watch(confirm=a.confirm), {}
    while True:
        try:
            poll(w, a, state)
        except Exception:  # noqa: BLE001 - GEXRadar down etc.: log and keep going
            log.exception("poll failed")
            if a.once:
                raise
        if a.once:
            return
        time.sleep(a.every if in_session(datetime.now(NY)) else a.idle)


if __name__ == "__main__":
    main()
